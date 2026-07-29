#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
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
        self.assertIn("codex", result.stdout)
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

    def test_codex_manifest_is_pinned_to_official_installer(self):
        manifest = json.loads((ROOT / "packages/codex.yml").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertRegex(manifest["release"], r"^\d+\.\d+\.\d+")
        self.assertEqual(
            manifest["installer_url"],
            "https://chatgpt.com/codex/install.sh",
        )
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", manifest["installer_sha256"]))

    def test_kde_apply_refuses_uncaptured_local_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_home = Path(directory)
            config = fake_home / ".config"
            config.mkdir()
            shutil.copy2(ROOT / "config/kde/.config/kdeglobals", config / "kdeglobals")
            shortcuts = config / "kglobalshortcutsrc"
            shortcuts.write_text("[local-change]\nshortcut=Meta+S\n")
            env = os.environ.copy()
            env["HOME"] = str(fake_home)
            env["XDG_STATE_HOME"] = str(fake_home / ".local/state")
            result = subprocess.run(
                [
                    str(DOT),
                    "apply",
                    "--profile",
                    "kubuntu-laptop",
                    "--direct",
                ],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to overwrite KDE configuration drift", result.stderr)
            self.assertEqual(shortcuts.read_text(), "[local-change]\nshortcut=Meta+S\n")

    def test_linux_shell_profile_installs_dot_command(self):
        source = (ROOT / "bin/dot").resolve()
        text = DOT.read_text()
        self.assertIn('ROOT / "bin/dot": Path.home() / ".local/bin/dot"', text)
        self.assertTrue(source.is_file())

    def test_kde_diff_uses_delta_interactively(self):
        text = DOT.read_text()
        self.assertIn('["delta", "--paging=always"]', text)
        self.assertIn("sys.stdout.isatty()", text)


if __name__ == "__main__":
    unittest.main()
