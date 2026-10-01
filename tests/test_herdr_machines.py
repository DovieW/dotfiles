import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class HerdrMachinesTests(unittest.TestCase):
    def setUp(self):
        self.reconcile = runpy.run_path(str(ROOT / "scripts/configure-herdr-machines"))["reconcile"]
        self.source = ROOT / "config/herdr/machines.json"
        self.existing = {"id": "existing", "label": "Desktop", "target": "dovie-desktop-linux",
                         "session": "default", "enabled": True}

    def run_reconcile(self, saved, results=(), check=False):
        responses = [subprocess.CompletedProcess([], 0, json.dumps(saved), ""), *results]
        calls = mock.Mock(side_effect=responses)
        output = io.StringIO()
        with mock.patch.dict(self.reconcile.__globals__, {"command": calls}), contextlib.redirect_stdout(output):
            status = self.reconcile(self.source, check)
        return status, calls.call_args_list, output.getvalue()

    def test_existing_alias_is_idempotent_and_preserves_other_machines(self):
        other = {**self.existing, "id": "other", "label": "Other", "target": "other"}
        status, calls, _ = self.run_reconcile([other, self.existing])
        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 1)

    def test_missing_machine_registers_after_noninteractive_ssh(self):
        ok = subprocess.CompletedProcess([], 0, "", "")
        status, calls, output = self.run_reconcile([], [ok, ok])
        self.assertEqual(status, 0)
        self.assertIn("BatchMode=yes", calls[1].args[0])
        self.assertIn("StrictHostKeyChecking=yes", calls[1].args[0])
        self.assertEqual(calls[2].args[0], ["herdr", "machine", "add", "dovie@dovie-desktop-linux",
                                          "--label", "Desktop", "--remote-session", "default"])
        self.assertIn("CHANGED", output)

    def test_offline_machine_defers_without_registration(self):
        failure = subprocess.CompletedProcess([], 255, "", "offline")
        status, calls, output = self.run_reconcile([], [failure])
        self.assertEqual(status, 0)
        self.assertEqual(len(calls), 2)
        self.assertIn("DEFERRED", output)

    def test_incompatible_remote_defers_without_failing_setup(self):
        ok = subprocess.CompletedProcess([], 0, "", "")
        failure = subprocess.CompletedProcess([], 1, "", "incompatible")
        status, _, output = self.run_reconcile([], [ok, failure])
        self.assertEqual(status, 0)
        self.assertIn("DEFERRED", output)

    def test_timeout_defers_without_failing_setup(self):
        status, _, output = self.run_reconcile([], [subprocess.TimeoutExpired("ssh", 10)])
        self.assertEqual(status, 0)
        self.assertIn("DEFERRED", output)

    def test_check_missing_is_read_only_and_fails(self):
        status, calls, _ = self.run_reconcile([], check=True)
        self.assertEqual(status, 1)
        self.assertEqual(len(calls), 1)

    def test_disabled_machine_is_enabled_without_duplicate(self):
        ok = subprocess.CompletedProcess([], 0, "", "")
        status, calls, _ = self.run_reconcile([{**self.existing, "enabled": False}], [ok])
        self.assertEqual(status, 0)
        self.assertEqual(calls[1].args[0], ["herdr", "machine", "enable", "existing"])

    def test_label_collision_preserves_existing_target(self):
        with self.assertRaisesRegex(RuntimeError, "another target"):
            self.run_reconcile([{**self.existing, "target": "other"}])

    def test_profile_inheritance_enables_laptops_only(self):
        load = runpy.run_path(str(ROOT / "bin/dot"))["load_profile"]
        self.assertTrue(load("kubuntu-laptop")["features"]["herdr_desktop_machine"])
        self.assertFalse(load("kubuntu-desktop")["features"]["herdr_desktop_machine"])


if __name__ == "__main__":
    unittest.main()
