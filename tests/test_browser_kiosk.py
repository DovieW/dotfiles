import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest import mock

K = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/browser-kiosk'))


class KioskTests(unittest.TestCase):
    def test_normal_mode_does_not_allow_google_account_settings(self):
        self.assertEqual(K['policy']()['URLAllowlist'], ['https://.photos.google.com'])
        self.assertIn('chrome://*', K['policy']()['URLBlocklist'])
        self.assertNotIn('https://.accounts.google.com', K['policy']()['URLAllowlist'])
        self.assertIn('https://.accounts.google.com', K['policy'](True)['URLAllowlist'])

    def test_policy_mutation_requires_root_before_reading_account(self):
        with mock.patch('os.geteuid', return_value=1000), mock.patch('pwd.getpwnam') as lookup:
            with self.assertRaises(RuntimeError):
                K['set_policy'](True)
            lookup.assert_not_called()

    def test_x11_guest_session_cannot_reach_stock_wrapper(self):
        with mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_name='photos-kiosk')), mock.patch('os.execv') as launch:
            with self.assertRaises(RuntimeError):
                K['guard']('x11', ['/bin/sh'])
            launch.assert_not_called()

    def test_normal_user_retains_original_session_arguments(self):
        with mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_name='owner')), mock.patch('os.execv') as launch:
            K['guard']('wayland', ['startplasma-wayland --example'])
            launch.assert_called_once_with('/usr/share/sddm/scripts/wayland-session', ['/usr/share/sddm/scripts/wayland-session', 'startplasma-wayland --example'])

    def test_unacknowledged_lock_never_switches_session(self):
        fn = K['start']
        runner = mock.Mock(return_value=mock.Mock(stdout='no\n'))
        with mock.patch.dict(os.environ, {'XDG_SESSION_ID': '123'}), mock.patch.dict(fn.__globals__, {'run': runner}), mock.patch('time.sleep'):
            with self.assertRaises(RuntimeError):
                fn()
        self.assertFalse(any('qdbus6' in str(c) for c in runner.call_args_list))

    def test_policy_write_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.write_text('unchanged')
            link = Path(directory) / 'link'
            link.symlink_to(target)
            with self.assertRaises(RuntimeError):
                K['write'](link, 'overwrite')
            self.assertEqual(target.read_text(), 'unchanged')

    def test_personal_user_cannot_launch_kiosk_browser(self):
        with mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_name='owner')), mock.patch('subprocess.run') as launch:
            with self.assertRaises(RuntimeError):
                K['browser']()
            launch.assert_not_called()

    def test_guest_cannot_run_session_before_owner_is_locked(self):
        fn = K['session']
        runner = mock.Mock(side_effect=[mock.Mock(stdout='4 1000 owner seat0 1 user tty2 no -\n'), mock.Mock(stdout='Type=wayland\nLockedHint=no\n')])
        with mock.patch('pwd.getpwnam', return_value=mock.Mock(pw_uid=os.getuid())), mock.patch.dict(fn.__globals__, {'run': runner}), mock.patch('os.execv') as launch:
            with self.assertRaisesRegex(RuntimeError, 'Lock all'):
                fn()
            launch.assert_not_called()

    def test_missing_policy_never_starts_browser(self):
        with mock.patch('pwd.getpwuid', return_value=mock.Mock(pw_name='photos-kiosk')), mock.patch('pathlib.Path.read_text', side_effect=FileNotFoundError), mock.patch('subprocess.run') as launch:
            with self.assertRaises(FileNotFoundError):
                K['browser']()
            launch.assert_not_called()
