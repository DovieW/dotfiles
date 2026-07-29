#!/usr/bin/env python3
import json
import os
from pathlib import Path
import pty
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
        self.assertIn("save", result.stdout)
        self.assertIn("update", result.stdout)

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

    def test_package_apply_explains_missing_noninteractive_sudo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "sudo").write_text("#!/bin/sh\nexit 1\n")
            (fake_bin / "ansible-playbook").write_text("#!/bin/sh\nexit 99\n")
            (fake_bin / "sudo").chmod(0o755)
            (fake_bin / "ansible-playbook").chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(root / "home")
            env["XDG_STATE_HOME"] = str(root / "state")
            env["PATH"] = os.pathsep.join(
                [str(fake_bin), "/home/linuxbrew/.linuxbrew/bin", "/usr/bin", "/bin"]
            )
            result = subprocess.run(
                [
                    str(DOT),
                    "apply",
                    "--profile",
                    "wsl-personal",
                    "--tags",
                    "packages",
                ],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Run `sudo -v` in an interactive terminal", result.stderr)

    def test_interactive_package_apply_prompts_for_sudo_before_ansible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            sudo_marker = root / "sudo-authorized"
            ansible_marker = root / "ansible-ran"
            (fake_bin / "sudo").write_text(
                "#!/bin/sh\n"
                'if [ "$1" = "-n" ]; then exit 1; fi\n'
                'if [ "$1" = "-v" ]; then touch "$DOT_TEST_SUDO_MARKER"; exit 0; fi\n'
                "exit 2\n"
            )
            (fake_bin / "ansible-playbook").write_text(
                "#!/bin/sh\n"
                'touch "$DOT_TEST_ANSIBLE_MARKER"\n'
            )
            (fake_bin / "sudo").chmod(0o755)
            (fake_bin / "ansible-playbook").chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(root / "home")
            env["XDG_STATE_HOME"] = str(root / "state")
            env["DOT_TEST_SUDO_MARKER"] = str(sudo_marker)
            env["DOT_TEST_ANSIBLE_MARKER"] = str(ansible_marker)
            env["PATH"] = os.pathsep.join(
                [str(fake_bin), "/home/linuxbrew/.linuxbrew/bin", "/usr/bin", "/bin"]
            )
            pid, fd = pty.fork()
            if pid == 0:
                os.execve(
                    str(DOT),
                    [
                        str(DOT),
                        "apply",
                        "--profile",
                        "wsl-personal",
                        "--tags",
                        "packages",
                    ],
                    env,
                )
            output = bytearray()
            while True:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
            _, status = os.waitpid(pid, 0)
            os.close(fd)
            self.assertEqual(os.waitstatus_to_exitcode(status), 0, output.decode(errors="replace"))
            self.assertTrue(sudo_marker.exists())
            self.assertTrue(ansible_marker.exists())
            self.assertIn(b"Administrator access is required", output)

    def test_codex_manifest_tracks_official_stable_channel(self):
        manifest = json.loads((ROOT / "packages/codex.yml").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["channel"], "stable")
        self.assertEqual(
            manifest["installer_url"],
            "https://chatgpt.com/codex/install.sh",
        )
        self.assertNotIn("release", manifest)
        self.assertNotIn("installer_sha256", manifest)

    def test_vite_plus_manifest_tracks_official_stable_channel(self):
        manifest = json.loads((ROOT / "packages/vite-plus.yml").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["channel"], "stable")
        self.assertEqual(manifest["installer_url"], "https://vite.plus")
        self.assertNotIn("release", manifest)
        self.assertNotIn("installer_sha256", manifest)

    def test_external_debs_resolve_stable_github_assets(self):
        manifest = json.loads((ROOT / "packages/external-deb.yml").read_text())
        for package in manifest["packages"].values():
            self.assertEqual(package["channel"], "stable")
            self.assertIn("/", package["source"])
            self.assertTrue(package["asset_regex"].endswith(r"\.deb$"))
            self.assertNotIn("version", package)

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

    def test_fzf_save_covers_preferences_and_shortcuts(self):
        text = DOT.read_text()
        self.assertIn('".config/spectaclerc"', text)
        self.assertIn('".config/kglobalshortcutsrc"', text)
        self.assertIn('"Settings to save › "', text)
        self.assertIn('"Save configuration changes\\tsave"', text)
        self.assertIn('"Update managed programs\\tupdate"', text)


if __name__ == "__main__":
    unittest.main()
