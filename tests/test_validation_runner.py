"""The validation entry point must report all independent failures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ValidationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        (self.root / "scripts").mkdir()
        self.runner = self.root / "tests/run"
        shutil.copy2(ROOT / "tests/run", self.runner)
        (self.root / "tests/validate_profiles.py").write_text(
            'import os, sys\nprint("profile check ran")\n'
            'sys.exit(int(os.environ.get("PROFILE_STATUS", "0")))\n'
        )
        safety = self.root / "scripts/check-public-safety"
        safety.write_text('#!/bin/sh\necho "safety check ran"\nexit "${SAFETY_STATUS:-0}"\n')
        safety.chmod(0o755)

    def run_checks(self, *checks, **env):
        return subprocess.run([str(self.runner), *checks], capture_output=True,
                              text=True, env={**os.environ, **env})

    def test_failure_does_not_hide_later_checks(self):
        result = self.run_checks("profiles", "safety", PROFILE_STATUS="7")
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL profiles", result.stderr)
        self.assertIn("safety check ran", result.stdout)
        self.assertIn("PASS safety", result.stdout)

    def test_later_failure_is_not_lost(self):
        result = self.run_checks("profiles", "safety", SAFETY_STATUS="9")
        self.assertEqual(result.returncode, 1)
        self.assertIn("PASS profiles", result.stdout)
        self.assertIn("FAIL safety", result.stderr)

    def test_successful_checks_succeed(self):
        result = self.run_checks("profiles", "safety")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS profiles", result.stdout)
        self.assertIn("PASS safety", result.stdout)

    @unittest.skipUnless(shutil.which("nvim") or
                         Path("/home/linuxbrew/.linuxbrew/bin/nvim").is_file(),
                         "Neovim is not installed")
    def test_nvim_uses_tracked_config_and_propagates_smoke_assertions(self):
        config = self.root / "config/nvim"
        (config / "tests").mkdir(parents=True)
        (config / "init.lua").write_text(
            'vim.api.nvim_create_user_command("Lazy", function() end, '
            '{bang=true, nargs="*"})\n'
        )
        smoke = config / "tests/smoke.lua"
        for source, status in (('print("fixture smoke passed")', 0),
                               ('error("synthetic smoke assertion")', 1)):
            with self.subTest(status=status):
                smoke.write_text(source)
                result = self.run_checks("nvim")
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertIn("fixture smoke passed" if status == 0 else
                              "synthetic smoke assertion", result.stderr)

    def test_unknown_check_fails_clearly(self):
        result = self.run_checks("misspelled-check")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Unknown check: misspelled-check", result.stderr)


if __name__ == "__main__":
    unittest.main()
