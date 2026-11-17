import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
D = runpy.run_path(str(ROOT / 'scripts/diagnostics'))


class DiagnosticsTests(unittest.TestCase):
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
