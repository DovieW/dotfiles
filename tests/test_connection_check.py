"""Failure interpretation without changing the host's network."""
import fcntl
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = runpy.run_path(str(Path(__file__).parents[1] / "scripts/connection-check"))
CHECK = MODULE["check"]
GLOBALS = CHECK.__globals__


class ConnectionCheckTests(unittest.TestCase):
    def test_lock_is_released_when_the_test_finishes(self):
        run_check = MODULE["run_check"]
        result = {"summary": "Finished", "details": ""}
        with tempfile.TemporaryDirectory() as runtime, patch.dict(os.environ, XDG_RUNTIME_DIR=runtime):
            lock_path = Path(runtime) / f"connection-check-{os.getuid()}.lock"
            with patch.dict(run_check.__globals__, check=lambda long: result):
                with lock_path.open("w") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    self.assertIn("Another test is running", run_check()["summary"])
                self.assertEqual(run_check(), result)
                self.assertEqual(run_check(), result)

    def test_no_route(self):
        with patch.dict(GLOBALS, run=lambda *a: (1, "", "unreachable")):
            self.assertIn("No usable IPv4", CHECK()["summary"])

    def sample(self, https=0, download=0, loss=0, changed=False, speed=5_000_000,
               signal=-55, latency=30):
        calls = []

        def run(args, timeout=15):
            calls.append(args)
            if args[0] == "ip":
                count = sum(c[0] == "ip" for c in calls)
                dev = "wlan1" if changed and count > 1 else "wlan0"
                return 0, '[{"dev":"' + dev + '","gateway":"192.168.1.1"}]', ""
            if args[0] == "nmcli":
                return 0, "<test & network>", ""
            if args[0] == "iw":
                return 0, f"freq: 5240\nsignal: {signal} dBm", ""
            if args[-1].startswith("https://speed"):
                return download, f"{speed} 10000000 10", "timeout" if download else ""
            return https, "200 0.01 0.1", ""

        def ping(target, interface):
            if target != "1.1.1.1":
                return {"loss": 0, "avg": 2, "max": 4, "raw": "sample"}
            return {"loss": loss, "avg": latency if loss != 100 else None, "max": 40, "raw": "sample"}

        with patch.dict(GLOBALS, run=run, ping=ping):
            return CHECK()

    def test_blocked_ping_does_not_mean_no_internet(self):
        result = self.sample(loss=100)
        text = result["summary"]
        self.assertIn("may be blocked", text)
        self.assertIn("DNS + HTTPS: working", text)
        self.assertEqual(result["rating"], "Unrated")

    def test_partial_download_not_reported_as_success(self):
        result = self.sample(download=28)
        self.assertIn("download check incomplete", result["summary"])
        self.assertEqual(result["metrics"][-1]["rating"], "Unrated")

    def test_https_failure(self):
        self.assertIn("encountered a problem", self.sample(https=6)["summary"])

    def test_loss_and_route_change(self):
        self.assertIn("packet loss detected", self.sample(loss=8.33)["summary"])
        result = self.sample(changed=True)
        self.assertIn("Connection changed", result["summary"])
        self.assertTrue(all(row["rating"] == "Unrated" for row in result["metrics"]))

    def test_rating_cutoffs_and_overall_status(self):
        self.assertEqual(self.sample()["rating"], "Good")
        result = self.sample(speed=625_000, signal=-75, latency=150, loss=20)
        ratings = {row["name"]: row["rating"] for row in result["metrics"]}
        self.assertEqual(ratings["Wi-Fi signal"], "Fair")
        self.assertEqual(ratings["Internet latency"], "Fair")
        self.assertEqual(ratings["Download speed"], "Fair")
        self.assertEqual(ratings["Internet packet loss"], "Poor")
        self.assertEqual(result["rating"], "Poor")


if __name__ == "__main__":
    unittest.main()
