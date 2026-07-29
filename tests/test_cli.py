#!/usr/bin/env python3
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOT = ROOT / "bin/dot"


class DotCliTests(unittest.TestCase):
    def run_dot(self, *args):
        return subprocess.run([str(DOT), *args], text=True, capture_output=True)

    def test_help(self):
        result = self.run_dot("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bootstrap", result.stdout)
        self.assertIn("doctor", result.stdout)

    def test_profiles_are_parseable(self):
        for path in (ROOT / "profiles").glob("*.yml"):
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)

    def test_unknown_profile_is_actionable(self):
        result = self.run_dot("doctor", "--profile", "does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot read", result.stderr)

    def test_windows_profile_does_not_install(self):
        profile = json.loads((ROOT / "profiles/windows-host.yml").read_text())
        self.assertTrue(profile["features"]["windows_inventory_only"])


if __name__ == "__main__":
    unittest.main()
