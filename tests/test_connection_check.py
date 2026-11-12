"""Failure interpretation without changing the host's network."""
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = runpy.run_path(str(Path(__file__).parents[1] / "scripts/connection-check"))
CHECK = MODULE["check"]
GLOBALS = CHECK.__globals__


class ConnectionCheckTests(unittest.TestCase):
    def test_no_route(self):
        with patch.dict(GLOBALS, run=lambda *a: (1, "", "unreachable")):
            self.assertIn("No usable IPv4", CHECK()["summary"])

    def sample(self, https=0, download=0, loss=0, changed=False):
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
                return 0, "freq: 5240\nsignal: -55 dBm", ""
            if args[-1].startswith("https://speed"):
                return download, "1000000 10000000 10", "timeout" if download else ""
            return https, "200 0.01 0.1", ""

        def ping(*args):
            return {"loss": loss, "avg": 30 if loss != 100 else None, "max": 40, "raw": "sample"}

        with patch.dict(GLOBALS, run=run, ping=ping):
            return CHECK()["summary"]

    def test_blocked_ping_does_not_mean_no_internet(self):
        text = self.sample(loss=100)
        self.assertIn("may be blocked", text)
        self.assertIn("DNS + HTTPS: working", text)

    def test_partial_download_not_reported_as_success(self):
        self.assertIn("download check incomplete", self.sample(download=28))

    def test_https_failure(self):
        self.assertIn("encountered a problem", self.sample(https=6))

    def test_loss_and_route_change(self):
        self.assertIn("packet loss detected", self.sample(loss=8.33))
        self.assertIn("Connection changed", self.sample(changed=True))


if __name__ == "__main__":
    unittest.main()
