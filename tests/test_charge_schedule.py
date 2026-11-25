import datetime as dt
import json
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / 'scripts/dot-charge'))
WINDOWS = json.loads((ROOT / 'devices/dovie-ideapad-linux.yml').read_text())['charge_schedule']


class ChargeScheduleTests(unittest.TestCase):
    def test_daily_and_workday_windows(self):
        for stamp, expected, boundary in (
            ('2026-11-25 04:59', 80, '2026-11-25 05:00'),
            ('2026-11-25 06:00', 100, '2026-11-25 08:00'),
            ('2026-11-25 08:00', 80, '2026-11-25 15:00'),
            ('2026-11-25 16:15', 100, '2026-11-25 16:30'),
            ('2026-11-27 10:44', 80, '2026-11-27 10:45'),
            ('2026-11-27 12:00', 100, '2026-11-27 12:15'),
            ('2026-11-28 15:00', 80, '2026-11-29 05:00'),
        ):
            with self.subTest(stamp=stamp):
                self.assertEqual(MODULE['schedule'](dt.datetime.fromisoformat(stamp), WINDOWS['full_charge_windows']),
                                 (expected, dt.datetime.fromisoformat(boundary).timestamp()))

    def test_override_wins_until_expiry_then_schedule_returns(self):
        policy = MODULE['policy']
        now = dt.datetime(2026, 11, 25, 6, 0)
        expiry = now.timestamp() + 3600
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            config = folder / 'schedule.json'
            config.write_text(json.dumps(WINDOWS))
            (folder / 'override.json').write_text(json.dumps({'until': expiry, 'percent': 80}))
            with patch.dict(policy.__globals__, STATE=folder, CONFIG=config):
                self.assertEqual(policy(now), (80, expiry, 'override expires'))
                self.assertEqual(policy(dt.datetime.fromtimestamp(expiry))[0], 100)
