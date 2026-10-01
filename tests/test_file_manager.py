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
    @unittest.skipUnless(
        shutil.which("kwriteconfig6") and shutil.which("xdg-mime"),
        "KDE and XDG tools are required for native preference testing",
    )
    def test_targeted_apply_preserves_other_settings_and_is_repeatable(self):
        module = runpy.run_path(str(ROOT / "bin/dot"))
        configure = module["configure_nemo_file_manager"]
        native_run = module["run"]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / ".config"
            apps = home / ".local/share/applications"
            config.mkdir()
            apps.mkdir(parents=True)
            fixtures = {
                "kwinrc": "[Desktops]\nNumber=2\n[Xwayland]\nScale=2.35\n[Plugins]\ndot-dolphinEnabled=true\notherEnabled=true\n",
                "kwinrulesrc": (
                    "[General]\ncount=4\nrules=other-rule,dolphin-skip-taskbar,nemo-skip-taskbar,bitwarden-ephemeral\n"
                    "[other-rule]\nwmclass=keep-me\n"
                    "[dolphin-skip-taskbar]\nwmclass=org.kde.dolphin\nskiptaskbar=true\n"
                    "[nemo-skip-taskbar]\nwmclass=nemo\nskipswitcher=true\n"
                    "[bitwarden-ephemeral]\nwmclass=bitwarden\nskippager=true\n"
                ),
                "kglobalshortcutsrc": "[kwin]\nCustom=Ctrl+Alt+F,none,Keep this\ndot-dolphin=Meta+E,none,Open or Focus Dolphin\n",
                "mimeapps.list": "[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\ntext/plain=editor.desktop;\n",
                "kde-mimeapps.list": "[Default Applications]\ninode/directory=org.kde.dolphin.desktop;\napplication/pdf=reader.desktop;\n",
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
                ("Plugins", "dot-dolphinEnabled", "false"),
                ("Plugins", "dot-nemoEnabled", "true"),
            ):
                self.assertEqual(get((config / "kwinrc").read_bytes(), section, key), value)
            self.assertEqual(get((config / "kwinrulesrc").read_bytes(), "other-rule", "wmclass"), "keep-me")
            self.assertEqual(get((config / "kwinrulesrc").read_bytes(), "General", "rules"), "other-rule")
            self.assertEqual(get((config / "kwinrulesrc").read_bytes(), "General", "count"), "1")
            for name in module["RETIRED_WINDOW_HIDING_RULES"]:
                self.assertNotIn(f"[{name}]", (config / "kwinrulesrc").read_text())
            self.assertIn("Custom=Ctrl+Alt+F,none,Keep this", (config / "kglobalshortcutsrc").read_text())
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
                "configure_nemo_file_manager": configure,
                "check_kde_apply_conflicts": mock.Mock(side_effect=AssertionError("full KDE preflight")),
                "copy_managed_kde_file": mock.Mock(side_effect=AssertionError("full KDE copy")),
            }),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(apply("kubuntu-desktop", selected_tags={"file-manager"}), 3)
        configure.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
