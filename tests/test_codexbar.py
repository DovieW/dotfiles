import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch


MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/codexbar-release.py"))


class CodexBarActivationTests(unittest.TestCase):
    def setUp(self):
        self.proc = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.desktop = MODULE["DESKTOP"]

    def process(self, name, executable, maps=""):
        entry = self.proc / "101"
        entry.mkdir()
        (entry / "comm").write_text(name)
        (entry / "exe").symlink_to(executable)
        (entry / "maps").write_text(maps)

    def test_inactive(self):
        self.assertEqual(MODULE["activation_status"](self.proc), "CodexBar is inactive.")

    def test_current_desktop(self):
        self.process("codexbar-linux", self.desktop)
        self.assertIn("No replaced code detected", MODULE["activation_status"](self.proc))

    def test_replaced_desktop_requires_reopen(self):
        self.process("codexbar-linux", f"{self.desktop} (deleted)")
        self.assertIn("Quit and reopen CodexBar", MODULE["activation_status"](self.proc))

    def test_replaced_qt_library_requires_reopen(self):
        self.process("codexbar-linux", self.desktop, "1-2 r-xp 0 00:00 0 /usr/lib/libQt6Core.so.6 (deleted)")
        self.assertIn("Quit and reopen CodexBar", MODULE["activation_status"](self.proc))

    def test_running_older_cli_requires_rerun(self):
        self.process("CodexBarCLI", MODULE["RELEASES"] / "v0.0.0/CodexBarCLI")
        self.assertIn("Rerun any active CodexBar CLI", MODULE["activation_status"](self.proc))

    def test_unreadable_desktop_process_is_reported(self):
        self.process("codexbar-linux", self.desktop)
        readlink = os.readlink
        desktop_exe = self.proc / "101/exe"

        def read_process_link(path, *args, **kwargs):
            if path == desktop_exe:
                raise PermissionError
            return readlink(path, *args, **kwargs)

        with patch("os.readlink", side_effect=read_process_link):
            self.assertIn("inspection was incomplete", MODULE["activation_status"](self.proc))


class CodexBarInstallTests(unittest.TestCase):
    def test_managed_release_accepts_upstream_cli_symlink(self):
        with tempfile.TemporaryDirectory() as home:
            home = Path(home)
            release = home / ".local/lib/dotfiles/codexbar/v0.84.0"
            bin_dir = home / ".local/bin"
            release.mkdir(parents=True)
            bin_dir.mkdir()
            (release / "codexbar").symlink_to("CodexBarCLI")
            (release / "VERSION").touch()
            (release / "CodexBar_CodexBarCore.bundle").mkdir()
            cli, desktop = bin_dir / "codexbar", bin_dir / "codexbar-linux"
            cli.symlink_to(release / "codexbar")
            for directory in (home / ".local/share/applications", home / ".config/autostart"):
                directory.mkdir(parents=True)
                (directory / "com.steipete.CodexBar.desktop").touch()
            installed_version = MODULE["installed_version"]
            with patch.dict(installed_version.__globals__, {
                "HOME": home, "CLI": cli, "DESKTOP": desktop, "RELEASES": release.parent,
                "executable_version": lambda _path, _name: "0.84.0",
            }), patch.dict(os.environ, {"XDG_CONFIG_HOME": "", "XDG_DATA_HOME": ""}):
                self.assertEqual(installed_version(), "0.84.0")
