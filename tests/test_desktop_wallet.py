import argparse
import contextlib
import io
from pathlib import Path
import runpy
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
WALLET = runpy.run_path(str(ROOT / "scripts/desktop-wallet"))
DOT = runpy.run_path(str(ROOT / "bin/dot"))


def result(output="", code=0):
    return subprocess.CompletedProcess([], code, output, "")


class DesktopWalletTests(unittest.TestCase):
    def test_lock_probe_reads_only_default_collection_state(self):
        for value, expected in (("b true", 1), ("b false", 0)):
            with self.subTest(value=value), mock.patch("shutil.which", return_value="busctl"), \
                    mock.patch("subprocess.run", side_effect=[
                        result('o "/org/freedesktop/secrets/collection/kdewallet"'),
                        result(value),
                    ]) as run:
                status, detail = WALLET["wallet_status"]()
                self.assertEqual(status, expected)
                if status == 1:
                    self.assertIn("KWalletManager", detail)
                    self.assertIn("Automatic login", detail)
                self.assertEqual(len(run.call_args_list), 2)
                first, second = (call.args[0] for call in run.call_args_list)
                self.assertEqual(first[-3:], ["ReadAlias", "s", "default"])
                self.assertEqual(second[-1], "Locked")
                for call in run.call_args_list:
                    self.assertIn("--auto-start=no", call.args[0])
                    self.assertLessEqual(call.kwargs["timeout"], 3)

    def test_unknown_state_is_never_reported_as_unlocked(self):
        cases = (
            [result('o "/"')],
            [result("malformed")],
            [result('o "/org/freedesktop/secrets/collection/kdewallet"', 1)],
            [result('o "/collection"'), result("b maybe")],
            [result('o "/collection"'), result("b false", 1)],
            [subprocess.TimeoutExpired("busctl", 3)],
            [result('o "/collection"'), subprocess.TimeoutExpired("busctl", 3)],
            [FileNotFoundError("busctl")],
        )
        for responses in cases:
            with self.subTest(responses=responses), \
                    mock.patch("shutil.which", return_value="busctl"), \
                    mock.patch("subprocess.run", side_effect=responses):
                self.assertEqual(WALLET["wallet_status"]()[0], 2)
        with mock.patch("shutil.which", return_value=None), mock.patch("subprocess.run") as run:
            self.assertEqual(WALLET["wallet_status"]()[0], 2)
            run.assert_not_called()

    def test_login_warning_only_for_persistently_locked_wallet(self):
        notify = WALLET["notify_when_locked"]
        for statuses, notifications in (
            ([(0, "unlocked")], 0),
            ([(1, "locked"), (0, "unlocked")], 0),
            ([(2, "unavailable")] * 3, 0),
            ([(1, "locked")] * 3, 1),
        ):
            with self.subTest(statuses=statuses), mock.patch.dict(notify.__globals__, {
                "wallet_status": mock.Mock(side_effect=statuses),
            }), mock.patch("time.sleep"), mock.patch("shutil.which", return_value="notify-send"), \
                    mock.patch("subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(notify(), 0)
                self.assertEqual(run.call_count, notifications)
                if notifications:
                    self.assertEqual(run.call_args.args[0][0], "notify-send")
                    self.assertIn("Unlock KDE Wallet for Bitwarden", run.call_args.args[0])

    def test_github_auth_timeout_does_not_become_a_new_login_attempt(self):
        function = DOT["ensure_github_authorization"]
        run = mock.Mock(side_effect=subprocess.TimeoutExpired("gh", 15))
        with mock.patch.dict(function.__globals__, {
            "command_exists": mock.Mock(return_value=True), "run": run,
        }), self.assertRaisesRegex(DOT["DotError"], "timed out.*KWalletManager"):
            function()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["timeout"], 15)
        self.assertEqual(run.call_args.args[0][:3], ["gh", "auth", "status"])

    def test_locked_wallet_stops_secret_sync_before_authorization(self):
        function = DOT["cmd_secrets_sync"]
        authorize = mock.Mock()
        session = mock.Mock()
        with mock.patch.dict(function.__globals__, {
            "load_profile": mock.Mock(return_value={"features": {"kde": True}}),
            "desktop_wallet_status": mock.Mock(return_value=(1, WALLET["RECOVERY"])),
            "ensure_github_authorization": authorize,
            "bw_session": session,
        }), self.assertRaisesRegex(DOT["DotError"], "KDE Wallet is locked"):
            function(argparse.Namespace(profile="kubuntu-desktop"))
        authorize.assert_not_called()
        session.assert_not_called()

    def test_doctor_skips_credentials_only_when_wallet_is_known_locked(self):
        function = DOT["cmd_doctor"]
        for status in (0, 1, 2):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                agent = socket.socket(socket.AF_UNIX)
                self.addCleanup(agent.close)
                agent.bind(str(home / ".bitwarden-ssh-agent.sock"))
                run = mock.Mock(return_value=result())
                github = mock.Mock(return_value=(True, DOT["GITHUB_REQUIRED_SCOPES"]))
                output = io.StringIO()
                with mock.patch.dict(function.__globals__, {
                    "load_profile": mock.Mock(return_value={
                        "name": "kubuntu-desktop", "features": {"git": True},
                    }),
                    "CONFIG_DIR": home / "config",
                    "HOMELAB_REPO": home / "homelab",
                    "desktop_wallet_status": mock.Mock(return_value=(status, "wallet detail")),
                    "github_auth_state": github,
                    "command_exists": mock.Mock(return_value=True),
                    "run": run,
                }), mock.patch.object(Path, "home", return_value=home), \
                        contextlib.redirect_stdout(output), self.assertRaises(DOT["DotError"]):
                    function(argparse.Namespace(profile="kubuntu-desktop"))
                queried_agent = any(call.args[0][0] == "ssh-add" for call in run.call_args_list)
                self.assertEqual(queried_agent, status != 1)
                self.assertEqual(github.called, status != 1)
                self.assertIn("desktop wallet: wallet detail", output.getvalue())
                if status == 1:
                    self.assertIn("not checked: wallet detail", output.getvalue())

    def test_installation_is_idempotent_and_starts_only_in_graphical_session(self):
        install = DOT["configure_desktop_wallet_check"]
        for graphical in (True, False):
            with self.subTest(graphical=graphical), tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                run = mock.Mock(side_effect=lambda command, **kwargs: result(
                    "enabled" if "is-enabled" in command else "",
                    1 if "is-active" in command and not graphical else 0,
                ))
                with mock.patch.dict(install.__globals__, {
                    "command_exists": mock.Mock(return_value=True), "run": run,
                }), mock.patch.object(Path, "home", return_value=home):
                    self.assertEqual(install(), 2)
                    self.assertEqual(install(), 0)
                self.assertTrue((home / ".local/bin/dot-desktop-wallet").is_symlink())
                self.assertEqual(
                    sum("daemon-reload" in call.args[0] for call in run.call_args_list), 1,
                )
                self.assertEqual(
                    any("start" in call.args[0] for call in run.call_args_list), graphical,
                )

    def test_wallet_only_apply_preserves_other_desktop_configuration(self):
        function = DOT["apply_direct"]
        install = mock.Mock(return_value=3)
        run = mock.Mock(side_effect=AssertionError("unrelated command during wallet-only apply"))
        with mock.patch.dict(function.__globals__, {
            "configure_desktop_wallet_check": install, "run": run,
        }), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(function("kubuntu-desktop", selected_tags={"wallet"}), 3)
        install.assert_called_once_with()

    def test_wallet_packages_are_managed_on_both_kubuntu_profiles(self):
        for name in ("kubuntu-desktop", "kubuntu-laptop"):
            packages = DOT["load_profile"](name)["packages"]["apt"]
            self.assertIn("libpam-kwallet5", packages)
            self.assertIn("kwalletmanager", packages)


if __name__ == "__main__":
    unittest.main()
