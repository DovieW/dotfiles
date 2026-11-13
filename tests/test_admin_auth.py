import argparse
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class AdminAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(ROOT / "bin/dot"))
        self.globals = self.module["administrator_password"].__globals__
        self.enterContext(mock.patch.dict(os.environ, {}, clear=True))
        self.enterContext(mock.patch.dict(self.globals, {
            "inherit_graphical_session_environment": lambda: None,
        }))

    def test_routing_and_explicit_override(self):
        for mode, tty, expected in (
            ("auto", True, False), ("auto", False, True),
            ("gui", True, True), ("terminal", False, False),
        ):
            with self.subTest(mode=mode, tty=tty), \
                 mock.patch.dict(os.environ, {"DOTFILES_AUTH_MODE": mode}), \
                 mock.patch("sys.stdin.isatty", return_value=tty):
                self.assertEqual(self.module["gui_admin_authentication"](), expected)
        os.environ["DOTFILES_AUTH_MODE"] = "invalid"
        with self.assertRaisesRegex(self.module["DotError"], "must be"):
            self.module["gui_admin_authentication"]()

    def test_dialog_preserves_spaces_and_captures_secret(self):
        os.environ.update(DOTFILES_AUTH_MODE="gui", WAYLAND_DISPLAY="wayland-test")
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, " secret with spaces \n", ""))
        with mock.patch.dict(self.globals, {"command_exists": lambda _: True}), \
             mock.patch("subprocess.run", runner):
            self.assertEqual(self.module["administrator_password"](), " secret with spaces ")
        self.assertTrue(runner.call_args.kwargs["capture_output"])
        self.assertNotIn("secret with spaces", str(runner.call_args.args))

    def test_cancel_and_dialog_failure_do_not_expose_output_or_fallback(self):
        os.environ.update(DOTFILES_AUTH_MODE="gui", DISPLAY=":test")
        for code in (1, -6):
            with mock.patch.dict(self.globals, {"command_exists": lambda _: True}), \
                 mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], code, "secret", "secret")), \
                 mock.patch("getpass.getpass") as terminal:
                with self.assertRaises(self.module["DotError"]) as error:
                    self.module["administrator_password"]()
                self.assertNotIn("secret", str(error.exception))
                terminal.assert_not_called()

    def test_unavailable_desktop_or_dialog_fails_without_prompting(self):
        os.environ["DOTFILES_AUTH_MODE"] = "gui"
        for display, installed in (("", True), (":test", False)):
            with mock.patch.dict(os.environ, {"DISPLAY": display}), \
                 mock.patch.dict(self.globals, {"command_exists": lambda _: installed}), \
                 mock.patch("subprocess.run") as runner:
                with self.assertRaisesRegex(self.module["DotError"], "desktop session"):
                    self.module["administrator_password"]()
                runner.assert_not_called()

    def test_terminal_mode_without_terminal_fails_without_getpass(self):
        os.environ["DOTFILES_AUTH_MODE"] = "terminal"
        with mock.patch("sys.stdin.isatty", return_value=False), mock.patch("getpass.getpass") as prompt:
            with self.assertRaisesRegex(self.module["DotError"], "interactive terminal"):
                self.module["administrator_password"]()
            prompt.assert_not_called()

    def test_root_and_cached_sudo_do_not_open_dialog(self):
        for uid, status in ((0, 1), (1000, 0)):
            with mock.patch("os.geteuid", return_value=uid), \
                 mock.patch.dict(self.globals, {
                     "run": mock.Mock(return_value=subprocess.CompletedProcess([], status)),
                     "require_commands": lambda *a: None,
                     "administrator_password": mock.Mock(side_effect=AssertionError("unexpected dialog")),
                 }):
                self.module["ansible_become_arguments"]()

    def test_apply_releases_password_after_success_and_failure(self):
        for failed in (False, True):
            def apply(args):
                self.globals["_CODEX_ADMIN_PASSWORD"] = "synthetic-test-password"
                if failed:
                    raise RuntimeError("test failure")
            with mock.patch.dict(self.globals, {"_cmd_apply": apply}):
                try:
                    self.module["cmd_apply"](argparse.Namespace())
                except RuntimeError:
                    pass
                self.assertIsNone(self.globals["_CODEX_ADMIN_PASSWORD"])

    def test_noninteractive_apply_transports_dialog_password_to_ansible(self):
        if os.geteuid() == 0:
            self.skipTest("root does not need administrator authentication")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            programs = {
                "sudo": "#!/bin/sh\nexit 1\n",
                "systemctl": "#!/bin/sh\nexit 1\n",
                "kdialog": "#!/bin/sh\nprintf '%s\\n' 'synthetic-test-password'\n",
                "ansible-playbook": (
                    "#!/usr/bin/python3\nimport os,sys\nfrom pathlib import Path\n"
                    "assert os.environ.get('ANSIBLE_BECOME_PASS') == 'synthetic-test-password'\n"
                    "assert '--ask-become-pass' not in sys.argv\n"
                    "assert 'synthetic-test-password' not in str(sys.argv)\n"
                    "Path(os.environ['DOT_TEST_MARKER']).touch()\n"
                ),
            }
            for name, content in programs.items():
                path = binaries / name
                path.write_text(content)
                path.chmod(0o700)
            marker = root / "ansible-ran"
            env = {
                "PATH": f"{binaries}:/home/linuxbrew/.linuxbrew/bin:/usr/bin:/bin", "HOME": str(root / "home"),
                "XDG_STATE_HOME": str(root / "state"), "DISPLAY": ":test",
                "DOTFILES_TESTING": "1", "DOT_TEST_MARKER": str(marker),
            }
            result = subprocess.run([
                str(ROOT / "bin/dot"), "apply", "--profile", "kubuntu-desktop", "--tags", "nomachine",
            ], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(marker.exists())
            self.assertNotIn("synthetic-test-password", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
