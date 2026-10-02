import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class KdeApplyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.home = self.root / "home"
        self.source = self.root / "config/kde/.config/kwinrc"
        self.live = self.home / ".config/kwinrc"
        self.source.parent.mkdir(parents=True)
        self.live.parent.mkdir(parents=True)
        self.baseline = self.root / "baseline.json"
        self.relative = ".config/kwinrc"
        self.module = runpy.run_path(str(ROOT / "bin/dot"))
        self.check = self.module["check_kde_apply_conflicts"]
        patches = [
            mock.patch.dict(self.check.__globals__, {
                "ROOT": self.root,
                "KDE_BASELINE": self.baseline,
                "BACKUP_DIR": self.root / "backups",
                "KDE_FILES": (self.relative,),
            }),
            mock.patch.object(Path, "home", return_value=self.home),
            mock.patch.dict(os.environ, {
                "DOTFILES_KDE_CHOICES": "{}", "DOTFILES_KDE_REVIEW_VALUES": "{}",
                "DOTFILES_FORCE_KDE": "0", "DOTFILES_KDE_PREFLIGHT_OK": "0",
            }),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def fixture(self, source, live, previous=None):
        self.source.write_text(source)
        self.live.write_text(live)
        if previous is not None:
            self.baseline.write_text(json.dumps({"sources": {self.relative: previous}}))

    def review(self, *answers):
        output = io.StringIO()
        with (
            mock.patch("sys.stdin.isatty", return_value=True),
            mock.patch("builtins.input", side_effect=answers) as prompt,
            contextlib.redirect_stdout(output),
        ):
            self.check()
        return output.getvalue(), prompt

    def apply_file(self, force=False):
        return self.module["copy_managed_kde_file"](self.relative, self.source, self.live, force=force)

    def value(self, key):
        return self.module["kde_values"](self.live.read_bytes()).get(("General", key))

    def test_independent_repository_updates_merge_with_local_preferences(self):
        self.fixture("[General]\nAnimation=0\nNewFeature=true\n", "[General]\nAnimation=0.1\nLocalOnly=keep\n", "[General]\nAnimation=0\n")
        text, _ = self.review("k")
        self.assertIn("This computer: 0.1", text)
        self.assertIn("Dotfiles:      0", text)
        self.apply_file()
        self.assertEqual(self.value("Animation"), "0.1")
        self.assertEqual(self.value("NewFeature"), "true")
        self.assertEqual(self.value("LocalOnly"), "keep")

    def test_keep_is_remembered_but_later_repository_changes_are_reviewed(self):
        self.fixture("[General]\nAnimation=0\n", "[General]\nAnimation=0.1\n", "[General]\nAnimation=0\n")
        self.review("k")
        self.apply_file()
        self.module["record_kde_baseline"]()
        self.assertTrue(self.module["kde_preferences_match"](self.relative))
        os.environ["DOTFILES_KDE_CHOICES"] = "{}"
        os.environ["DOTFILES_KDE_REVIEW_VALUES"] = "{}"
        _, prompt = self.review()
        prompt.assert_not_called()
        self.source.write_text("[General]\nAnimation=0.2\n")
        self.assertFalse(self.module["kde_preferences_match"](self.relative))
        _, prompt = self.review("u")
        prompt.assert_called_once()
        self.apply_file()
        self.assertEqual(self.value("Animation"), "0.2")

    def test_use_applies_owned_values_and_preserves_other_keys_and_comments(self):
        self.fixture("[General]\nAnimation=0\n", "# local comment\n[General]\nAnimation=0.1\nLocalOnly=keep\n[Host]\nDevice=mine\n")
        self.review("u")
        self.assertTrue(self.apply_file())
        self.assertEqual(self.value("Animation"), "0")
        self.assertIn("# local comment", self.live.read_text())
        self.assertEqual(self.value("LocalOnly"), "keep")
        self.assertIn("Device=mine", self.live.read_text())
        self.assertTrue(list((self.root / "backups").glob("*/manifest.json")))

    def test_skip_changes_neither_file_nor_baseline(self):
        self.fixture("[General]\nAnimation=0\nNewFeature=true\n", "[General]\nAnimation=0.1\n", "[General]\nAnimation=0\n")
        previous = self.baseline.read_bytes()
        self.review("s")
        self.assertFalse(self.apply_file())
        self.module["record_kde_baseline"]()
        self.assertEqual(self.value("Animation"), "0.1")
        self.assertIsNone(self.value("NewFeature"))
        self.assertEqual(json.loads(self.baseline.read_text())["sources"], json.loads(previous)["sources"])
        os.environ["DOTFILES_KDE_CHOICES"] = "{}"
        os.environ["DOTFILES_KDE_REVIEW_VALUES"] = "{}"
        _, prompt = self.review("k")
        prompt.assert_called_once()

    def test_keep_restores_reviewed_value_after_a_helper_changes_it(self):
        self.fixture("[General]\nAnimation=0\n", "[General]\nAnimation=0.1\n")
        self.review("k")
        self.live.write_text("[General]\nAnimation=0\n")
        self.apply_file()
        self.assertEqual(self.value("Animation"), "0.1")

    def test_key_order_and_host_only_keys_do_not_prompt(self):
        self.fixture("[General]\nA=1\nB=2\n", "[Runtime]\nSeen=true\n[General]\nB=2\nA=1\n", "[General]\nA=1\nB=2\n")
        _, prompt = self.review()
        prompt.assert_not_called()
        self.assertFalse(self.apply_file())

    def test_removed_owned_keys_are_removed_without_deleting_host_keys(self):
        self.fixture("[General]\nA=1\n", "[General]\nA=1\nRetired=old\nLocalOnly=keep\n", "[General]\nA=1\nRetired=old\n")
        _, prompt = self.review()
        prompt.assert_not_called()
        self.apply_file()
        self.assertIsNone(self.value("Retired"))
        self.assertEqual(self.value("LocalOnly"), "keep")

    def test_noninteractive_apply_keeps_local_choices_and_warns(self):
        self.fixture("[General]\nAnimation=0\nNewFeature=true\n", "[General]\nAnimation=0.1\n", "[General]\nAnimation=0\n")
        output = io.StringIO()
        with mock.patch("sys.stdin.isatty", return_value=False), contextlib.redirect_stderr(output):
            self.check()
        self.apply_file()
        self.assertIn("Run apply in a terminal", output.getvalue())
        self.assertEqual(self.value("Animation"), "0.1")
        self.assertEqual(self.value("NewFeature"), "true")

    def test_legacy_hash_recovers_source_from_local_git_history(self):
        self.fixture("[General]\nA=1\n", "[General]\nA=1\n")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        for arguments in (
            ["init"], ["add", "config"],
            ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-m", "old source"],
        ):
            subprocess.run(["git", *arguments], cwd=self.root, env=env, check=True, capture_output=True)
        digest = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.baseline.write_text(json.dumps({"schema_version": 1, "files": {self.relative: digest}}))
        self.source.write_text("[General]\nA=2\n")
        _, prompt = self.review()
        prompt.assert_not_called()
        self.apply_file()
        self.assertEqual(self.value("A"), "2")

    def test_ignored_kde_bookkeeping_survives_without_review(self):
        merge = self.module["kde_merge_plan"]
        for relative, source, live in (
            (".config/kdeglobals", b"[KDE]\nAnimationDurationFactor=0\n", b"[KFileDialog Settings]\nSort by=Date\n[General]\nColorSchemeHash=hash\n[KDE]\nAnimationDurationFactor=0\n"),
            (".config/plasmanotifyrc", b"[Notifications]\nPopupPosition=BottomRight\n", b"[Applications][chatgpt]\nSeen=true\n[Notifications]\nPopupPosition=BottomRight\n"),
            (".config/kglobalshortcutsrc", b"[app]\n_k_friendly_name=App (Development)\nkey=F3\n", b"[app]\n_k_friendly_name=App\nkey=F3\n"),
            (".config/kglobalshortcutsrc", b"[kwin]\nkey=F3\n[services][org.kde.spectacle.desktop]\n_launch=old cache\n", b"[kwin]\nkey=F3\n[services][org.kde.spectacle.desktop]\n_launch=\n"),
        ):
            with self.subTest(relative=relative):
                self.assertEqual(merge(relative, source, live)[1], [])
                path = self.root / "runtime-file"
                path.write_bytes(live)
                self.assertEqual(self.module["kde_destination_content"](relative, source, path), live)

    def test_retired_dolphin_binding_migrates_to_nemo(self):
        source = b"[kwin]\ndot-dolphin=none,none,Open or Focus Dolphin\ndot-nemo=Meta+E,none,Open or Focus Nemo\n"
        live = b"[kwin]\ndot-dolphin=Meta+E,none,Open or Focus Dolphin\n"
        merged, review = self.module["kde_merge_plan"](".config/kglobalshortcutsrc", source, live)
        self.assertEqual(review, [])
        self.assertEqual(merged[("kwin", "dot-dolphin")], "none,none,Open or Focus Dolphin")
        self.assertEqual(merged[("kwin", "dot-nemo")], "Meta+E,none,Open or Focus Nemo")

    def test_preserving_one_preference_does_not_acknowledge_changes_to_other_keys(self):
        self.fixture("[General]\nAnimation=0\nA=1\n", "[General]\nAnimation=0.1\nA=1\n", "[General]\nAnimation=0\nA=1\n")
        self.review("k")
        self.apply_file()
        self.module["record_kde_baseline"]()
        os.environ["DOTFILES_KDE_CHOICES"] = "{}"
        os.environ["DOTFILES_KDE_REVIEW_VALUES"] = "{}"
        self.source.write_text("[General]\nAnimation=0\nA=2\n")
        _, prompt = self.review()
        prompt.assert_not_called()
        self.apply_file()
        self.module["record_kde_baseline"]()
        os.environ["DOTFILES_KDE_REVIEW_VALUES"] = "{}"
        self.live.write_text(self.live.read_text().replace("A=2", "A=1"))
        text, prompt = self.review("k")
        prompt.assert_called_once()
        self.assertIn("This computer: 1", text)
        self.assertIn("Dotfiles:      2", text)

    def test_live_shortcut_activation_honors_reviewed_choices(self):
        activate = self.module["activate_kglobal_shortcuts"]
        os.environ["DOTFILES_KDE_REVIEW_VALUES"] = json.dumps({".config/kglobalshortcutsrc": [["kwin", "Window Close", "Meta+S,none,Close Window"]]})
        setter = mock.Mock()
        with mock.patch.dict(activate.__globals__, {"set_kglobal_shortcut": setter, "kglobal_shortcut": mock.Mock(return_value=[0])}):
            activate({("kwin", "Window Close", "KWin", "Close Window"): [268435537]})
        setter.assert_not_called()

    def test_theme_hash_with_an_unchanged_palette_is_not_a_preference_change(self):
        source = b"[Colors:Window]\nBackgroundNormal=22,27,34\n[General]\nColorScheme=GitHubDark\n"
        live = b"[Colors:Window]\nBackgroundNormal=22,27,34\n[General]\nColorSchemeHash=hash\n"
        merged, review = self.module["kde_merge_plan"](".config/kdeglobals", source, live)
        self.assertEqual(review, [])
        self.assertNotIn(("General", "ColorScheme"), merged)
        changed = live.replace(b"22,27,34", b"1,2,3")
        self.assertIn(("General", "ColorScheme"), self.module["kde_merge_plan"](".config/kdeglobals", source, changed)[1])

    def test_force_is_an_explicit_replacement(self):
        self.fixture("[General]\nAnimation=0\n", "[General]\nAnimation=0.1\nLocalOnly=keep\n")
        self.apply_file(force=True)
        self.assertEqual(self.value("Animation"), "0")
        self.assertIsNone(self.value("LocalOnly"))

    def test_palette_run_decisions_do_not_leak_to_next_apply(self):
        command = self.module["cmd_apply"]
        os.environ.pop("DOTFILES_KDE_CHOICES")
        os.environ.pop("DOTFILES_KDE_REVIEW_VALUES")
        os.environ.pop("DOTFILES_FORCE_KDE")
        def action(_args):
            os.environ["DOTFILES_KDE_CHOICES"] = json.dumps({self.relative: "skip"})
            os.environ["DOTFILES_KDE_REVIEW_VALUES"] = "{}"
            os.environ["DOTFILES_FORCE_KDE"] = "1"
        with mock.patch.dict(command.__globals__, {"_cmd_apply": action}):
            command(argparse.Namespace())
        for name in ("DOTFILES_KDE_CHOICES", "DOTFILES_KDE_REVIEW_VALUES", "DOTFILES_FORCE_KDE"):
            self.assertNotIn(name, os.environ)

    def test_ansible_child_receives_parent_choices(self):
        command = self.module["cmd_apply"]
        os.environ["DOTFILES_KDE_PREFLIGHT_OK"] = "1"
        os.environ["DOTFILES_KDE_CHOICES"] = json.dumps({self.relative: "skip"})
        def action(_args):
            self.assertEqual(json.loads(os.environ["DOTFILES_KDE_CHOICES"])[self.relative], "skip")
        action = mock.Mock(side_effect=action)
        with mock.patch.dict(command.__globals__, {"_cmd_apply": action}):
            command(argparse.Namespace())
        action.assert_called_once()
        self.assertEqual(json.loads(os.environ["DOTFILES_KDE_CHOICES"])[self.relative], "skip")

    def test_review_precedes_upgrades_and_administrator_prompt(self):
        command = self.module["cmd_apply"]
        events = []
        def review(**_kwargs):
            events.append("review")
            os.environ["DOTFILES_KDE_CHOICES"] = json.dumps({self.relative: "skip"})
        def execute(_command, **kwargs):
            events.append("ansible")
            self.assertEqual(json.loads(kwargs["env"]["DOTFILES_KDE_CHOICES"])[self.relative], "skip")
            self.assertEqual(kwargs["env"]["DOTFILES_KDE_PREFLIGHT_OK"], "1")
        with mock.patch.dict(command.__globals__, {
            "CONFIG_DIR": self.root / "missing",
            "STATE_DIR": self.root / "state",
            "load_profile": lambda _: {"name": "kubuntu-laptop", "features": {"kde": True}},
            "inherit_graphical_session_environment": mock.Mock(),
            "check_kde_apply_conflicts": review,
            "upgrade_ansible_controller": lambda *_args, **_kwargs: events.append("upgrade"),
            "ansible_become_arguments": lambda: events.append("administrator") or [],
            "command_exists": lambda _: True,
            "record_kde_baseline": mock.Mock(),
            "run": execute,
        }):
            command(argparse.Namespace(profile="kubuntu-laptop", tags="kde", check=False, direct=False))
        self.assertEqual(events, ["review", "upgrade", "administrator", "ansible"])


if __name__ == "__main__":
    unittest.main()
