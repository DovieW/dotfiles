import contextlib
import io
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class FileManagerTests(unittest.TestCase):
    def test_first_full_apply_installs_and_runs_dolphin_before_activating_its_shortcut(self):
        module = runpy.run_path(str(ROOT / "bin/dot"))
        apply = module["apply_direct"]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            script = home / ".local/share/kwin/scripts/dot-dolphin/contents/code/main.js"
            loaded = set()
            activations = []

            def run(command, **kwargs):
                output = ""
                returncode = 0
                if "org.kde.kwin.Scripting.loadScript" in command:
                    loaded.add(command[-1])
                    output = "17\n"
                elif "org.kde.kwin.Scripting.unloadScript" in command:
                    loaded.discard(command[-1])
                elif "org.kde.kwin.Scripting.isScriptLoaded" in command:
                    output = "true\n" if command[-1] in loaded or command[-1] == "dot-clipboard" else "false\n"
                elif command[0] == "kwriteconfig6" and command[-2].endswith("Enabled"):
                    name = command[-2].removesuffix("Enabled")
                    if command[-1] == "true":
                        loaded.add(name)
                    else:
                        loaded.discard(name)
                elif command[:3] == ["systemctl", "--user", "is-active"]:
                    returncode = 1
                return subprocess.CompletedProcess(command, returncode, output, "")

            def activate(desired, **kwargs):
                if any(action[1] == "dot-dolphin" for action in desired):
                    self.assertTrue(script.is_file(), "Dolphin's script has not been installed yet")
                    self.assertIn("dot-dolphin", loaded, "Dolphin's script has not registered its shortcut yet")
                    activations.append("dolphin")
                else:
                    activations.append("other")

            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ),
                mock.patch.dict(apply.__globals__, {
                    "STATE_DIR": home / "state",
                    "CONFIG_DIR": home / "config",
                    "BACKUP_DIR": home / "backups",
                    "KDE_FILES": (),
                    "load_profile": lambda _: {"features": {"kde": True, "copyq": True}},
                    "command_exists": lambda command: command in {"qdbus6", "gdbus", "systemctl", "kwriteconfig6"},
                    "check_kde_apply_conflicts": mock.Mock(),
                    "record_kde_baseline": mock.Mock(),
                    "configure_desktop_wallet_check": mock.Mock(return_value=0),
                    "provision_lockscreen_assets": mock.Mock(return_value=0),
                    "configure_dolphin_default": mock.Mock(return_value=0),
                    "managed_clipboard_callback_ok": mock.Mock(return_value=True),
                    "managed_screenshot_callback_ok": mock.Mock(return_value=True),
                    "activate_kglobal_shortcuts": activate,
                    "run": run,
                }),
                mock.patch("time.sleep"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertFalse(script.exists())
                apply("kubuntu-laptop")
            self.assertIn("dolphin", activations)
            self.assertNotEqual(activations[0], "dolphin")

    def test_clipboard_shortcuts_do_not_require_desktop_scripts(self):
        module = runpy.run_path(str(ROOT / "bin/dot"))
        sync = module["sync_managed_kglobal_shortcuts"]
        activate = mock.Mock()
        with mock.patch.dict(sync.__globals__, {"activate_kglobal_shortcuts": activate, "command_exists": lambda _: True}):
            sync(clipboard_only=True)
        actions = {action[1] for action in activate.call_args.args[0]}
        self.assertIn("dot-copyq-history-meta", actions)
        self.assertIn("dot-clipboard-probe", actions)
        self.assertNotIn("dot-dolphin", actions)
        self.assertNotIn("dot-nemo", actions)
        self.assertNotIn("dot-brightness-up", actions)
        self.assertNotIn("dot-window-desktop-left", actions)

    @unittest.skipUnless(
        shutil.which("kwriteconfig6") and shutil.which("xdg-mime"),
        "KDE and XDG tools are required for native preference testing",
    )
    def test_targeted_apply_preserves_other_settings_and_is_repeatable(self):
        module = runpy.run_path(str(ROOT / "bin/dot"))
        configure = module["configure_dolphin_file_manager"]
        native_run = module["run"]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / ".config"
            apps = home / ".local/share/applications"
            config.mkdir()
            apps.mkdir(parents=True)
            fixtures = {
                "kwinrc": "[Desktops]\nNumber=2\n[Xwayland]\nScale=2.35\n[Plugins]\ndot-dolphinEnabled=false\ndot-nemoEnabled=true\notherEnabled=true\n",
                "kwinrulesrc": (
                    "[General]\ncount=4\nrules=other-rule,dolphin-skip-taskbar,nemo-skip-taskbar,bitwarden-ephemeral\n"
                    "[other-rule]\nwmclass=keep-me\n"
                    "[dolphin-skip-taskbar]\nwmclass=org.kde.dolphin\nskiptaskbar=true\n"
                    "[nemo-skip-taskbar]\nwmclass=nemo\nskipswitcher=true\n"
                    "[bitwarden-ephemeral]\nwmclass=bitwarden\nskippager=true\n"
                ),
                "kglobalshortcutsrc": "[kwin]\nCustom=Ctrl+Alt+F,none,Keep this\ndot-nemo=Meta+E,none,Open or Focus Nemo\n",
                "mimeapps.list": "[Default Applications]\ninode/directory=nemo.desktop;\ntext/plain=editor.desktop;\n",
                "kde-mimeapps.list": "[Default Applications]\ninode/directory=nemo.desktop;\napplication/pdf=reader.desktop;\n",
                "kcminputrc": "[Touchpad]\nDisableWhileTyping=false\n",
                "powerdevilrc": "[AC][Performance]\nPowerProfile=performance\n",
            }
            for name, content in fixtures.items():
                (config / name).write_text(content)
            for name in ("nemo", "org.kde.dolphin"):
                (apps / f"{name}.desktop").write_text(
                    f"[Desktop Entry]\nType=Application\nName={name}\nExec=/usr/bin/true\nMimeType=inode/directory;\n"
                )

            def run(command, **kwargs):
                if command[0] in {"qdbus6", "systemctl"}:
                    return subprocess.CompletedProcess(command, 0, "true\n", "")
                return native_run(command, **kwargs)

            environment = {
                "XDG_CONFIG_HOME": str(config),
                "XDG_CONFIG_DIRS": str(config),
                "XDG_DATA_HOME": str(home / ".local/share"),
                "XDG_DATA_DIRS": str(home / ".local/share"),
                "XDG_CURRENT_DESKTOP": "KDE",
                "KDE_SESSION_VERSION": "6",
                "QT_QPA_PLATFORM": "offscreen",
            }
            with (
                mock.patch.object(Path, "home", return_value=home),
                mock.patch.dict(os.environ, environment),
                mock.patch.dict(configure.__globals__, {
                    "BACKUP_DIR": home / "backups",
                    "require_commands": mock.Mock(),
                    "run": run,
                    "activate_kglobal_shortcuts": mock.Mock(),
                }),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertGreater(configure(), 0)
                self.assertEqual(configure(), 0)
            get = module["kconfig_get"]
            for section, key, value in (
                ("Desktops", "Number", "2"),
                ("Xwayland", "Scale", "2.35"),
                ("Plugins", "otherEnabled", "true"),
                ("Plugins", "dot-dolphinEnabled", "true"),
                ("Plugins", "dot-nemoEnabled", "false"),
            ):
                self.assertEqual(get((config / "kwinrc").read_bytes(), section, key), value)
            self.assertEqual(get((config / "kwinrulesrc").read_bytes(), "other-rule", "wmclass"), "keep-me")
            self.assertEqual(get((config / "kwinrulesrc").read_bytes(), "General", "rules"), "other-rule")
            self.assertEqual(get((config / "kwinrulesrc").read_bytes(), "General", "count"), "1")
            for name in module["RETIRED_WINDOW_HIDING_RULES"]:
                self.assertNotIn(f"[{name}]", (config / "kwinrulesrc").read_text())
            self.assertIn("Custom=Ctrl+Alt+F,none,Keep this", (config / "kglobalshortcutsrc").read_text())
            self.assertEqual(get((config / "kglobalshortcutsrc").read_bytes(), "kwin", "dot-dolphin"), "Meta+E,none,Open or Focus Dolphin")
            self.assertEqual(get((config / "kglobalshortcutsrc").read_bytes(), "kwin", "dot-nemo"), "none,none,Open or Focus Nemo")
            for name in ("mimeapps.list", "kde-mimeapps.list"):
                self.assertEqual(get((config / name).read_bytes(), "Default Applications", "inode/directory").rstrip(";"), "org.kde.dolphin.desktop")
            self.assertIn("text/plain=editor.desktop;", (config / "mimeapps.list").read_text())
            self.assertIn("application/pdf=reader.desktop;", (config / "kde-mimeapps.list").read_text())
            for name in ("kcminputrc", "powerdevilrc"):
                self.assertEqual((config / name).read_text(), fixtures[name])

    def test_file_manager_tag_does_not_apply_full_kde_configuration(self):
        module = runpy.run_path(str(ROOT / "bin/dot"))
        apply = module["apply_direct"]
        configure = mock.Mock(return_value=3)
        with (
            mock.patch.dict(apply.__globals__, {
                "configure_dolphin_file_manager": configure,
                "configure_dolphin_network_places": mock.Mock(return_value=0),
                "check_kde_apply_conflicts": mock.Mock(side_effect=AssertionError("full KDE preflight")),
                "copy_managed_kde_file": mock.Mock(side_effect=AssertionError("full KDE copy")),
            }),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(apply("kubuntu-desktop", selected_tags={"file-manager"}), 3)
        configure.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
