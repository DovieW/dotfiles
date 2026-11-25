import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
D = runpy.run_path(str(ROOT / 'scripts/diagnostics'))
RESUME = runpy.run_path(str(ROOT / 'scripts/diagnostic-resume'))
WAKE = runpy.run_path(str(ROOT / 'scripts/diagnostic-wake'))
PEER = runpy.run_path(str(ROOT / 'scripts/crash-peer'))


class DiagnosticsTests(unittest.TestCase):
    def test_peer_distinguishes_reboot_sleep_and_network_outage(self):
        classify = PEER['reconnect_event']
        old = {'boot_id': 'before', 'suspended_s': 10}
        self.assertEqual(classify(old, {'boot_id': 'after', 'suspended_s': 0}), 'peer_rebooted')
        self.assertEqual(classify(old, {'boot_id': 'before', 'suspended_s': 14}), 'peer_slept_during_gap')
        self.assertEqual(classify(old, {'boot_id': 'before', 'suspended_s': 10}), 'peer_reachable_again')

    def test_peer_key_rejects_shell_and_extra_arguments(self):
        for request in ('', 'sh', 'snapshot extra', 'watch; sh', 'sudo reboot'):
            with self.subTest(request=request), mock.patch.dict(os.environ, {'SSH_ORIGINAL_COMMAND': request}), \
                    mock.patch('os.execv') as execv, self.assertRaises(SystemExit):
                PEER['inbound']()
                execv.assert_not_called()

    def test_resume_trace_distinguishes_queued_and_delivered_events(self):
        events = RESUME['trace_summary'](
            ' sleep-10 [000] .... 82.111: suspend_resume: machine_suspend[3] end\n'
            ' kwin_wayland-20 [001] .... 82.112: drm_vblank_event_queued: file=ffff1234, crtc=0, seq=9\n'
            ' irq-40 [002] .... 82.120: intel_crtc_flip_done: dev 0000:00:02.0, pipe A, frame=9, scanline=1\n'
            ' irq-40 [002] .... 82.121: drm_vblank_event_delivered: file=ffff1234, crtc=0, seq=9\n'
            ' irq-40 [002] .... 82.132: drm_vblank_event_delivered: file=ffff1234, crtc=0, seq=10\n')
        self.assertEqual([event['event'] for event in events], [
            'suspend_resume', 'drm_vblank_event_queued', 'intel_crtc_flip_done', 'drm_vblank_event_delivered'])
        self.assertEqual((events[-1]['first_s'], events[-1]['last_s'], events[-1]['count']), ('82.121', '82.132', 2))
        self.assertNotIn('ffff1234', json.dumps(events))

    def test_wake_trace_preserves_sleep_markers_and_wakeup_device_names(self):
        result = WAKE['trace_evidence'](
            ' sleep-10 [000] .... 82.111: suspend_resume: machine_suspend[3] begin\n'
            ' irq-40 [002] .... 82.120: wakeup_source_activate: ACPI:Event state=0x40210001\n'
            ' irq-40 [002] .... 82.121: suspend_resume: machine_suspend[3] end\n')
        self.assertEqual([event['detail'] for event in result['events']], [
            'machine_suspend[3] begin', 'ACPI:Event', 'machine_suspend[3] end'])

    def test_wake_hook_persists_paired_wake_even_when_tracefs_is_unavailable(self):
        pre, post = WAKE['pre'], WAKE['post']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pending = root / 'pending.json'
            state = root / 'wakes'
            acpi = root / 'acpi'
            acpi.mkdir()
            (acpi / 'gpe37').write_text('4 enabled\n')
            (acpi / 'gpe38').write_text('9 enabled\n')
            (root / 'pm_wakeup_irq').write_text('9\n')
            irq = root / '9'
            irq.mkdir()
            (irq / 'actions').write_text('acpi\n')
            with mock.patch.dict(pre.__globals__, {
                'STATE': state, 'PENDING': pending, 'POWER': root, 'IRQ': root,
                'ACPI_INTERRUPTS': acpi, 'TRACE': root / 'missing' / 'instance',
            }):
                pre('suspend', 'suspend', 'boot')
                (acpi / 'gpe37').write_text('6 enabled\n')
                post('suspend', 'suspend', 'boot')
            before, after = [json.loads(line) for line in next(state.glob('*.jsonl')).read_text().splitlines()]
            self.assertEqual(before['boottime_ns'], after['before_ns'])
            self.assertEqual(after['irq'], {'status': 'reported', 'number': 9, 'actions': 'acpi'})
            self.assertEqual(after['acpi_count_increases'], {'gpe37': 2})
            self.assertEqual(after['trace']['status'], 'unavailable')
            self.assertFalse(pending.exists())

    def test_wake_history_stays_bounded_and_survives_a_hundred_retries(self):
        record = WAKE['record']
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'wakes'
            with mock.patch.dict(record.__globals__, {'STATE': state}):
                for i in range(102):
                    record('pre_sleep', 'boot', attempt=i)
                    record('post_sleep', 'boot', attempt=i, trace='x' * 3800)
                self.assertIn('"attempt":0', next(state.glob('*.jsonl')).read_text())
                for i in range(12):
                    record('post_sleep', 'boot', attempt=i + 102, trace='x' * (480 * 1024))
            files = list(state.glob('*.jsonl'))
            self.assertEqual(len(files), 4)
            self.assertTrue(all(p.stat().st_size <= 1024 * 1024 for p in files))
            self.assertIn('"attempt":113', max(files).read_text())

    def test_resume_connector_parser_keeps_the_internal_panel_pipe(self):
        state = ('plane[31]: primary\n\tcrtc=pipe A\n'
                 'connector[98]: eDP-1\n\tcrtc=pipe B\n'
                 'connector[101]: DP-1\n\tcrtc=(null)\n')
        self.assertEqual(RESUME['panel_crtc'](state, 'eDP-1'), 'pipe B')
        self.assertIsNone(RESUME['panel_crtc'](state.replace('\tcrtc=pipe B\n', ''), 'eDP-1'))

    def test_resume_collects_external_hdmi_and_ignores_writeback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('card1-HDMI-A-1', 'card1-Writeback-1'):
                (root / name).mkdir()
                (root / name / 'status').write_text('connected\n')
            debug = root / 'debug' / '1'
            debug.mkdir(parents=True)
            (debug / 'state').write_text('connector[5]: HDMI-A-1\n\tcrtc=pipe A\n')
            probe = RESUME['display_state']
            with mock.patch.dict(probe.__globals__, {'DRM': root, 'DEBUG_DRM': root / 'debug', 'BACKLIGHT': root / 'lights'}):
                connectors = probe()['connectors']
        self.assertEqual(list(connectors), ['card1-HDMI-A-1'])
        self.assertEqual(connectors['card1-HDMI-A-1']['crtc'], 'pipe A')
        self.assertFalse(connectors['card1-HDMI-A-1']['internal'])

    def test_resume_records_kernel_and_session_when_drm_state_read_hangs(self):
        release = threading.Event()
        capture = RESUME['capture']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'test.jsonl'
            (root / 'capture').write_text(json.dumps(dict(name=path.name, sleep=False, started=False)))
            try:
                with mock.patch.dict(capture.__globals__, {
                    'STATE': root, 'RUNTIME': root, 'TRACE': root / 'missing-trace',
                    'DELAYS': (0,), 'display_state': release.wait,
                    'session_state': lambda: {'kwin': {'status': 'ok'}},
                }), contextlib.redirect_stdout(io.StringIO()):
                    capture()
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                self.assertEqual([row['phase'] for row in rows], ['kernel', 'session', 'display', 'complete'])
                self.assertEqual(rows[1]['session']['kwin']['status'], 'ok')
                self.assertEqual(rows[2]['display']['status'], 'timeout')
                self.assertFalse((root / 'capture').exists())
            finally:
                release.set()

    def test_lid_open_dispatches_only_when_sleep_hook_does_not_own_capture(self):
        on_lid = RESUME['lid_changed']
        for slept in (False, True):
            with self.subTest(slept=slept), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                data = dict(name='test.jsonl', sleep=slept, started=False)
                (root / 'capture').write_text(json.dumps(data))
                with mock.patch.dict(on_lid.__globals__, {'RUNTIME': root, 'STATE': root}), \
                        mock.patch('subprocess.run') as dispatch:
                    on_lid(False)
                event = json.loads((root / data['name']).read_text())
                self.assertEqual(event['phase'], 'lid_open')
                self.assertIn('lid_open_s', json.loads((root / 'capture').read_text()))
                self.assertEqual(dispatch.call_count, int(not slept))

    def test_suspend_keeps_trace_already_armed_by_lid_close(self):
        arm = RESUME['arm']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dict(name='test.jsonl', sleep=False, started=False)
            (root / 'capture').write_text(json.dumps(data))
            with mock.patch.dict(arm.__globals__, {'RUNTIME': root, 'STATE': root}), \
                    mock.patch.dict(arm.__globals__, {'arm_capture': mock.Mock()}) as env:
                arm()
                env['arm_capture'].assert_not_called()
            self.assertTrue(json.loads((root / 'capture').read_text())['sleep'])
            self.assertEqual(json.loads((root / data['name']).read_text())['phase'], 'pre_sleep')

    def test_planned_signal_collector_stop_is_not_a_crash(self):
        proc = mock.Mock()
        proc.stdout = []
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        fn = D['signals']
        output = io.StringIO()
        stop = mock.Mock()
        stop.is_set.return_value = True
        with mock.patch.dict(fn.__globals__, {'STOP': stop}), mock.patch('subprocess.Popen', return_value=proc), contextlib.redirect_stdout(output):
            fn()
        self.assertTrue(json.loads(output.getvalue())['expected'])

    def test_unexpected_signal_collector_eof_is_a_failure(self):
        proc = mock.Mock()
        proc.stdout = []
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        fn = D['signals']
        stop = mock.Mock()
        stop.is_set.return_value = False
        with mock.patch.dict(fn.__globals__, {'STOP': stop}), mock.patch('subprocess.Popen', return_value=proc):
            with self.assertRaises(RuntimeError):
                fn()

    def test_signal_generation_is_not_confused_with_exit(self):
        kind, event = D['signal_record']('signal\t123\t10\t11\t22\t9\t0\t1\t0\t900\tsender\ttarget\n')
        self.assertEqual(kind, 'signal')
        self.assertEqual(event['target_tid'], 22)
        self.assertNotIn('target_pid', event)
        self.assertEqual(event['sender_start_ns'], 900)
        self.assertEqual(D['signal_record']('exit\t124\t22\t9\t800\ttarget\n')[1]['wait_status'], 9)

    def test_pipewire_export_strips_user_content(self):
        data = D['pw_changes']({'id': 1, 'info': {'state': 'running', 'props': {
            'application.name': 'Chrome', 'application.process.id': 123,
            'media.title': 'private meeting', 'media.filename': '/secret/path',
            'application.process.arguments': 'token=secret'}, 'params': {'secret': 'audio'}}})
        output = json.dumps(data)
        self.assertIn('Chrome', output)
        for forbidden in ('private meeting', '/secret/path', 'token=', 'audio'):
            self.assertNotIn(forbidden, output)

    def test_retention_preserves_active_and_never_unlinks_foreign_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for prefix in ('20260101T000000Z', '20260102T000000Z'):
                for suffix in ('.meta', '.index', '.0'):
                    path = root / (prefix + suffix)
                    path.write_text('x' * 10)
                    os.utime(path, (1, 1))
            (root / 'unrelated.meta').write_text('keep')
            removed = D['prune_archives'](root, active='20260102T000000Z', budget=1)
            self.assertEqual(removed, ['20260101T000000Z'])
            self.assertTrue((root / '20260102T000000Z.meta').exists())
            self.assertTrue((root / 'unrelated.meta').exists())

    def test_snapshot_write_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state/test.json'
            D['atomic'](path, {'status': 'ok'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(path.read_text()), {'status': 'ok'})

    def test_compressed_archive_retention_is_also_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for suffix in ('.meta.gz', '.index', '.0.gz'):
                (root / ('20260101T000000Z' + suffix)).write_bytes(b'x' * 10)
            self.assertEqual(D['prune_archives'](root, budget=1), ['20260101T000000Z'])
            self.assertEqual(list(root.iterdir()), [])

    def test_resource_time_conversion_and_timeline(self):
        self.assertEqual(D['pcp_time']('2026-11-17T07:49:17-05:00'), '@2026-11-17 12:49:17 UTC')
        row = {'@timestamp': '2026-11-17T12:49:47', 'proc': {'memory': {'rss': {'@instances': [
            {'name': 'test', 'value': 100}]}}}}
        text = json.dumps({'//': 'header'}) + json.dumps({'@pcp': {'@hosts': [{'@metrics': [row]}]}})
        events = list(D['resource_timeline'](text))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][1], 'resources')
        self.assertEqual(json.loads(events[0][2])['top_rss'][0]['name'], 'test')

    def test_export_rejects_ambiguous_or_reverse_time_before_writing(self):
        for start, end in [('2026-11-17T01:00:00', '2026-11-17T02:00:00'),
                           ('2026-11-17T02:00:00+00:00', '2026-11-17T01:00:00+00:00')]:
            with mock.patch('sys.argv', ['diagnostics', 'export', '--since', start,
                             '--until', end, '--output', '/not-created']), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    D['main']()


if __name__ == '__main__':
    unittest.main()
