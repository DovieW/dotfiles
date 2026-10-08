import contextlib
import fcntl
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class KrdpRefreshTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(ROOT / "scripts/refresh-krdp"))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.proc = root / "proc"
        self.process = self.proc / "123"
        self.process.mkdir(parents=True)
        (self.process / "exe").symlink_to("/usr/bin/krdpserver")
        (self.process / "maps").write_text("")
        (self.process / "stat").write_text("123 (krdpserver) " + " ".join(["S"] + ["0"] * 18 + ["100"]))
        self.state = root / "state"
        self.state.mkdir()
        self.runner = mock.Mock(side_effect=self.fake_run)
        patcher = mock.patch.dict(self.module["inspect"].__globals__, {
            "PROC": self.proc, "STATE": self.state, "run": self.runner,
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_run(self, *args):
        stdout = "MainPID=123\nActiveState=active\n" if "show" in args else ""
        return subprocess.CompletedProcess(args, 0, stdout, "")

    def stale(self, **overrides):
        return {"status": "stale", "pid": 123, "start_time": "100", "reasons": ["replaced shared library"],
                "plasma_session": True, "remote_viewing": False, "preparing": False, **overrides}

    def test_current_and_stale_loaded_code(self):
        self.assertEqual(self.module["inspect"]()["status"], "current")
        (self.process / "maps").write_text("1-2 r-xp 0 00:00 0 /usr/lib/libfreerdp3.so.3.32.0 (deleted)")
        self.assertEqual(self.module["inspect"]()["reasons"], ["replaced shared library"])
        (self.process / "exe").unlink()
        (self.process / "exe").symlink_to("/usr/bin/krdpserver (deleted)")
        self.assertIn("replaced executable", self.module["inspect"]()["reasons"])

    def test_inactive_service_is_never_started(self):
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], 0, "MainPID=0\nActiveState=inactive\n", "")
        self.assertEqual(self.module["refresh"]()["status"], "inactive")
        self.assertEqual(self.runner.call_count, 1)

    def test_current_service_is_never_restarted(self):
        self.assertEqual(self.module["refresh"]()["status"], "current")
        self.assertFalse(any("try-restart" in call.args for call in self.runner.call_args_list))

    def test_unreadable_unowned_and_unexpected_code_is_unknown(self):
        with mock.patch("os.readlink", side_effect=PermissionError):
            self.assertEqual(self.module["refresh"]()["status"], "unknown")
        with mock.patch("os.getuid", return_value=os.getuid() + 1):
            self.assertEqual(self.module["inspect"]()["status"], "unknown")
        (self.process / "exe").unlink()
        (self.process / "exe").symlink_to("/usr/bin/other")
        self.assertEqual(self.module["inspect"]()["status"], "unknown")
        self.assertFalse(any("try-restart" in call.args for call in self.runner.call_args_list))

    def test_socket_failure_and_corrupt_lease_prevent_restart(self):
        self.runner.side_effect = lambda *args: subprocess.CompletedProcess(args, 1, "", "") if args[0] == "ss" else self.fake_run(*args)
        self.assertEqual(self.module["refresh"]()["status"], "unknown")
        self.runner.side_effect = self.fake_run
        (self.state / "krdp-scale.json").write_text("{")
        self.assertEqual(self.module["refresh"]()["status"], "unknown")
        self.assertFalse(any("try-restart" in call.args for call in self.runner.call_args_list))

    def test_live_rdp_and_nomachine_connections_are_detected(self):
        for port in (3389, 4000):
            self.runner.side_effect = lambda *args: subprocess.CompletedProcess(args, 0, f"0 0 100.1.2.3:{port} 100.4.5.6:5000\n", "") if args[0] == "ss" else self.fake_run(*args)
            self.assertTrue(self.module["inspect"]()["remote_viewing"])

    def test_stale_code_waits_for_viewing_preparation_or_plasma(self):
        for flags in ({"remote_viewing": True}, {"preparing": True}, {"plasma_session": False}):
            with mock.patch.dict(self.module["refresh"].__globals__, {"inspect": mock.Mock(return_value=self.stale(**flags))}):
                self.assertEqual(self.module["refresh"]()["status"], "deferred")
        self.runner.assert_not_called()

    def test_preparation_lease_and_lock_are_respected(self):
        lease = self.state / "krdp-scale.json"
        lease.write_text(json.dumps({"prepared_until": 100}))
        with mock.patch("time.time", return_value=99):
            self.assertTrue(self.module["inspect"]()["preparing"])
        with mock.patch("time.time", return_value=101):
            self.assertFalse(self.module["inspect"]()["preparing"])
        self.runner.reset_mock()
        with (self.state / "krdp-scale.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.module["refresh"]()["status"], "deferred")
        self.runner.assert_not_called()

    def test_idle_stale_code_restarts_and_verifies_loaded_code(self):
        inspector = mock.Mock(side_effect=[self.stale(), self.stale(), {"status": "current"}])
        with mock.patch.dict(self.module["refresh"].__globals__, {"inspect": inspector}):
            self.assertEqual(self.module["refresh"]()["status"], "refreshed")
        self.runner.assert_called_once_with("systemctl", "--user", "try-restart", self.module["UNIT"])

    def test_changed_state_is_not_restarted(self):
        with mock.patch.dict(self.module["refresh"].__globals__, {"inspect": mock.Mock(side_effect=[self.stale(), self.stale(pid=456)])}):
            self.assertEqual(self.module["refresh"]()["status"], "deferred")
        self.runner.assert_not_called()

    def test_failed_restart_is_reported(self):
        self.runner.side_effect = None
        self.runner.return_value = subprocess.CompletedProcess([], 1, "", "")
        with mock.patch.dict(self.module["refresh"].__globals__, {"inspect": mock.Mock(return_value=self.stale())}):
            self.assertEqual(self.module["refresh"]()["status"], "unknown")

    def test_check_mode_never_calls_refresh_or_writes_state(self):
        checker = mock.Mock(return_value=self.stale())
        refresher = mock.Mock(side_effect=AssertionError("check must not mutate"))
        with mock.patch.dict(self.module["main"].__globals__, {"inspect": checker, "refresh": refresher}), \
                mock.patch("sys.argv", ["refresh-krdp", "--check"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.module["main"](), 0)
        self.assertEqual(list(self.state.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
