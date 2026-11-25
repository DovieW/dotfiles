"""Battery telemetry accounting, sensor provenance and storage boundaries."""

from contextlib import closing
import datetime as dt
import gzip
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

MODULES = Path(__file__).resolve().parents[1] / 'config/power/charge-telemetry'
sys.path.insert(0, str(MODULES))
try:
    import battery_collect
    import battery_report as report
    import battery_store as store
finally:
    sys.path.remove(str(MODULES))


def sample(ts, soc=80, **changes):
    return dict(timestamp=ts, source='local', kind='sample', boot_id='one',
                soc_pct=soc, monotonic_s=ts, boottime_s=ts, period_s=60,
                ac_online=True, adapter_class='mains_unidentified',
                battery_status='Charging', battery_power_w=24,
                battery_power_source='sysfs_power_now', design_wh=84) | changes


class AccountingTest(unittest.TestCase):
    def test_linear_threshold_crossings_and_signed_energy_on_ac(self):
        a = sample(0, soc=96, battery_power_w=-18, battery_status='Discharging',
                   battery_temp_c=39)
        b = sample(60, soc=94, battery_power_w=-30, battery_status='Discharging',
                   battery_temp_c=41)
        data = report.summarize([a, b], 0, 60, 'lifetime', dt.UTC)['lifetime']
        self.assertAlmostEqual(data['soc_above_seconds']['95'], 30)
        self.assertAlmostEqual(data['battery_temp_above_seconds']['40'], 30)
        self.assertAlmostEqual(data['discharged_on_ac_wh'], 0.4)
        self.assertAlmostEqual(data['equivalent_full_cycles'], 0.4 / 84)
        self.assertEqual(data['soc_coverage_pct'], 100)

    def test_sleep_boot_service_clock_and_adapter_boundaries(self):
        a = sample(0)
        for changes in (
            {'boot_id': 'two'}, {'boottime_s': 100}, {'monotonic_s': 59.8},
            {'period_s': 30, 'timestamp': 130, 'boottime_s': 130, 'monotonic_s': 130},
            {'kind': 'resume'}, {'requested_pct': 100}, {'ac_online': False}, {'power_transition': True},
            {'usb_sources': [{'port': 'one', 'type': 'PD', 'source_limit_w': 100}]},
        ):
            with self.subTest(changes=changes):
                self.assertFalse(report.compatible(a, sample(60, **changes), []))
        self.assertFalse(report.compatible(a, sample(60), [30]))
        self.assertTrue(report.compatible(a, sample(60, kind='suspend'), [60]))
        self.assertTrue(report.compatible(sample(0, kind='resume'), sample(60), [0]))
        data = report.summarize([a, sample(60, kind='resume')], 0, 60, 'lifetime', dt.UTC)['lifetime']
        self.assertEqual(data['soc_unknown_seconds'], 60)
        self.assertEqual(data['estimated_seconds']['battery_temp'], 0)

    def test_unknown_ac_cannot_count_as_zero_discharge_on_ac(self):
        rows = [sample(ts, battery_power_w=-10, battery_status='Discharging', ac_online=None)
                for ts in (0, 60)]
        data = report.summarize(rows, 0, 60, 'lifetime', dt.UTC)['lifetime']
        self.assertGreater(data['discharged_wh'], 0)
        self.assertEqual(data['estimated_seconds']['battery_power_ac_context'], 0)

    def test_full_requires_terminal_observation(self):
        rows = [sample(0, 80), sample(60, 98), sample(120, 100)]
        first = list(report.charging_sessions(rows, []))[0]
        self.assertEqual(first['seconds_to_observation']['98'], 60)
        self.assertNotIn('100', first['seconds_to_observation'])
        rows.append(sample(180, 100, genuinely_full=True, battery_status='Full'))
        first = list(report.charging_sessions(rows, []))[0]
        self.assertEqual(first['seconds_to_observation']['100'], 180)
        rows[3]['kind'] = 'resume'
        self.assertNotIn('100', list(report.charging_sessions(rows, []))[0]['seconds_to_observation'])

    def test_hold_missed_and_unknown_deadlines(self):
        origin = dt.datetime(2026, 11, 23, tzinfo=dt.UTC).timestamp()
        windows = [{'days': [0], 'start': '06:00', 'ready': '06:02', 'end': '08:00'}]
        policy = dict(timestamp=origin, source='local', kind='policy', timezone='UTC', windows=windows)
        times = [origin + 21600 + seconds for seconds in (0, 60, 120)]
        close = origin + 28800
        rows = [sample(ts, 98) for ts in times]
        for changed, cuts, expected in (
            (rows, [], 'missed_estimated'),
            ([], [], 'unknown'),
            (rows, [times[0] + 30], 'unknown'),
            ([rows[0], sample(times[1], 100, genuinely_full=True), rows[2]], [], 'met'),
            ([rows[0], sample(times[1], override={'percent': 80, 'until': times[2]}), rows[2]], [], 'override_observed'),
            ([sample(times[0], 100), rows[1], rows[2]], [], 'unknown'),
        ):
            with self.subTest(expected=expected):
                result = list(report.deadline_results([policy], changed, cuts, close, dt.UTC))[0]
                self.assertEqual(result['outcome'], expected)

    def test_dst_resolution_and_daily_coverage(self):
        tz = ZoneInfo('America/New_York')
        gap = store.wall_time(dt.date(2026, 3, 8), '02:30', tz)
        fold = store.wall_time(dt.date(2026, 11, 1), '01:30', tz)
        self.assertEqual(dt.datetime.fromtimestamp(gap, tz).strftime('%H:%M %Z'), '03:00 EDT')
        self.assertEqual(dt.datetime.fromtimestamp(fold, tz).strftime('%H:%M %Z'), '01:30 EDT')
        start = store.wall_time(dt.date(2026, 3, 8), '00:00', tz)
        end = store.wall_time(dt.date(2026, 3, 9), '00:00', tz)
        result = report.summarize([], start, end, 'daily', tz)
        self.assertEqual(result['2026-03-08']['soc_unknown_seconds'], 23 * 3600)


class SensorAndStorageTest(unittest.TestCase):
    def test_missing_and_derived_sensors(self):
        with tempfile.TemporaryDirectory() as root:
            battery = Path(root)
            (battery / 'uevent').write_text(
                'POWER_SUPPLY_STATUS=Discharging\nPOWER_SUPPLY_POWER_NOW=16000000\n'
                'POWER_SUPPLY_VOLTAGE_NOW=16000000\nPOWER_SUPPLY_CAPACITY=100\n'
                'POWER_SUPPLY_SERIAL_NUMBER=private\n'
            )
            (battery / 'charge_types').write_text('Fast Standard [Long_Life]\n')
            data = battery_collect.battery_fields(battery)
            self.assertEqual(data['battery_power_w'], -16)
            self.assertEqual(data['battery_current_a'], -1)
            self.assertEqual(data['battery_current_source'], 'derived_power_over_voltage')
            self.assertEqual(data['firmware_mode'], 'Long_Life')
            self.assertFalse(data['genuinely_full'])
            self.assertIsNone(data['battery_temp_c'])
            self.assertIsNone(data['end_threshold_pct'])
            self.assertNotIn('private', str(data))

    def test_usb_limit_and_generic_mains_identity(self):
        with tempfile.TemporaryDirectory() as root:
            power = Path(root)
            mains = power / 'ADP0'
            mains.mkdir()
            (mains / 'type').write_text('Mains')
            (mains / 'online').write_text('1')
            self.assertEqual(battery_collect.adapter(power)['adapter_class'], 'mains_unidentified')
            usb = power / 'ucsi-test'
            usb.mkdir()
            for name, value in (
                ('type', 'USB'), ('online', '1'), ('usb_type', 'DCP [PD]'),
                ('voltage_max', '20000000'), ('current_max', '5000000'),
            ):
                (usb / name).write_text(value)
            data = battery_collect.adapter(power)
            self.assertEqual(data['adapter_class'], 'usb_c')
            self.assertEqual(data['usb_sources'][0]['source_limit_w'], 100)

    def test_gpu_reads_only_runtime_metadata(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(battery_collect, 'read') as read:
            root = Path(directory)
            (root / 'card0').mkdir()
            (root / 'card0-HDMI-A-1').mkdir()
            read.return_value = 'suspended'
            self.assertEqual(battery_collect.gpu_runtime(root), {'card0': 'suspended'})
            read.assert_called_once_with(root / 'card0/device/power/runtime_status')

    def test_legacy_import_deduplicates_and_snapshot_restores(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'charge.dat'
            source.write_text('100\t80.000\tcharging\n130\t100.000\tcharging\n150\t98.000\tfully-charged\n')
            path = root / 'battery.sqlite3'
            historical = list(battery_collect.historical_rows({'charge': source}))
            with store.connect(path, writable=True) as db:
                store.append(db, historical)
                store.append(db, historical)
            with store.connect(path) as db:
                rows = store.records(db, 0, 200)
                self.assertEqual(len(rows), 3)
                self.assertTrue(all(not row['genuinely_full'] for row in rows))
            with (patch.object(battery_collect, 'BASE', root),
                  patch.object(battery_collect, 'connect', lambda: store.connect(path)),
                  patch('sys.stdout', new_callable=io.StringIO)):
                battery_collect.backup()
            backups = list((root / 'backups').glob('daily*'))
            self.assertEqual(len(backups), 1)
            restored = root / 'restored.sqlite3'
            restored.write_bytes(gzip.decompress(backups[0].read_bytes()))
            with closing(sqlite3.connect(restored)) as db:
                self.assertEqual(db.execute('PRAGMA quick_check').fetchone()[0], 'ok')
                self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0], 3)

    def test_same_second_legacy_conflicts_are_retained_and_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'charge.dat'
            source.write_text('100 96 charging\n120 97 charging\n120 98 discharging\n140 99 charging\n')
            rows = sorted((dict(row, source=src, kind=kind)
                           for src, kind, row in battery_collect.historical_rows({'charge': source})),
                          key=lambda row: row['timestamp'])
        conflict = next(row for row in rows if row['kind'] == 'legacy_conflict')
        self.assertEqual(conflict['detail'], [['97', 'charging'], ['98', 'discharging']])
        data = report.summarize(rows, 100, 140, 'lifetime', dt.UTC)['lifetime']
        self.assertEqual(data['soc_unknown_seconds'], 40)


if __name__ == '__main__':
    unittest.main()
