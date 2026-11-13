"""Exercise shortcut classification and the two interacting tab filters."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    QApplication = None

ROOT = Path(__file__).resolve().parents[1]
if QApplication is not None:
    loader = importlib.machinery.SourceFileLoader("shortcuts", str(ROOT / "scripts/dot-shortcuts"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    helper = importlib.util.module_from_spec(spec)
    loader.exec_module(helper)


@unittest.skipIf(QApplication is None, "PyQt6 desktop widgets unavailable")
class ShortcutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.config = Path(temp.name)
        (self.config / "kglobalshortcutsrc").write_text(
            "[kwin]\n_k_friendly_name=KWin\n"
            "dot-paste-image-path=Meta+Shift+I,none,Paste Clipboard Image as Temporary Path\n"
            "dot-active-window-clipboard=Alt+Print,none,Copy Active Window Screenshot\n"
            "close=Meta+Q,Alt+F4,Close Window\n"
            "walk=Alt+Tab\\tAlt+Shift+Tab,Alt+Shift+Tab\\tAlt+Tab,Walk Windows\n"
            "disabled=none,Meta+X,Disabled Action\n"
            "comma=Ctrl+\\,,Ctrl+\\,,Comma Action\n"
        )
        self.codex = self.config / "codex.toml"
        self.codex.write_text('[tui.keymap.global]\ntoggle_fast_mode = "alt-shift-f"\n')

    def test_classifies_managed_changed_default_and_unassigned_bindings(self):
        rows = helper.shortcut_rows(self.config)
        self.assertIn(("Custom", "CopyQ", "Paste Clipboard Image as Temporary Path", "Meta+Shift+I"), rows)
        self.assertIn(("Custom", "Screenshots", "Copy Active Window Screenshot", "Alt+Print"), rows)
        self.assertIn(("Custom", "KWin", "Close Window", "Meta+Q"), rows)
        self.assertIn(("Defaults", "KWin", "Walk Windows", "Alt+Tab or Alt+Shift+Tab"), rows)
        self.assertIn(("Defaults", "KWin", "Comma Action", "Ctrl+,"), rows)
        self.assertFalse(any(row[2] == "Disabled Action" for row in rows))

    def test_remmina_preferences_are_in_custom(self):
        (self.config / "remmina").mkdir()
        (self.config / "remmina/remmina.pref").write_text(
            "[remmina_pref]\nhostkey=65508\nshortcutkey_clipboard=118\n")
        self.assertIn(("Custom", "Remmina", "Send clipboard as keystrokes", "Right Ctrl+V"), helper.shortcut_rows(self.config))

    def test_codex_overrides_replace_defaults_and_empty_arrays_unbind(self):
        self.codex.write_text('[tui.keymap.global]\nsubmit = "ctrl-enter"\n'
                              '[tui.keymap.composer]\nqueue = []\n'
                              'history_search_previous = ["alt-r", "ctrl-x r"]\n')
        rows, warning = helper.codex_rows(self.codex)
        self.assertFalse(warning)
        self.assertIn(("Custom", "Codex CLI", "Submit (global)", "ctrl-enter"), rows)
        self.assertIn(("Custom", "Codex CLI", "Previous history match (composer)", "alt-r or ctrl-x r"), rows)
        self.assertFalse(any(row[2] in ("Submit message (composer)", "Queue message (composer)") for row in rows))

    def test_codex_missing_and_malformed_config_do_not_break_desktop_reference(self):
        self.assertEqual(helper.codex_rows(self.config / "missing"), ([], ""))
        self.codex.write_text("[invalid")
        rows, warning = helper.codex_rows(self.codex)
        self.assertEqual(rows, [])
        self.assertIn("unavailable", warning)

    def select_app(self, dialog, label):
        labels = [dialog.app_tabs.tabText(i) for i in range(dialog.app_tabs.count())]
        dialog.app_tabs.setCurrentIndex(labels.index(label))

    def test_tab_filters_search_and_application_fallback(self):
        dialog = helper.ShortcutDialog(self.config, self.codex)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.kind_tabs.tabText(dialog.kind_tabs.currentIndex()), "Custom")
        self.select_app(dialog, "CopyQ")
        self.assertEqual(dialog.tree.topLevelItem(0).childCount(), 1)
        dialog.search.setText("temporary META+SHIFT+I")
        self.assertEqual(dialog.tree.topLevelItem(0).childCount(), 1)
        dialog.search.setText("unfindable")
        self.assertEqual(dialog.tree.topLevelItem(0).text(0), "No matching shortcuts")
        dialog.kind_tabs.setCurrentIndex(2)
        self.assertEqual(dialog.app_tabs.currentIndex(), 0)
        self.assertEqual(dialog.search.text(), "unfindable")
        dialog.search.clear()
        self.select_app(dialog, "Codex CLI")
        dialog.kind_tabs.setCurrentIndex(0)
        self.assertEqual(dialog.app_tabs.tabText(dialog.app_tabs.currentIndex()), "Codex CLI")
        dialog.search.setText("fast")
        self.assertEqual(dialog.tree.topLevelItem(0).child(0).text(1), "alt-shift-f")

    def test_application_choices_wrap_and_remain_clickable_after_resize(self):
        tabs = helper.ApplicationTabs()
        self.addCleanup(tabs.close)
        labels = ["All applications", "CopyQ", "Screenshots", "Codex CLI", "KWin", "Remmina", "Safe Paste"]
        for label in labels:
            tabs.addTab(label)
        tabs.resize(800, tabs.height())
        tabs.show()
        self.app.processEvents()
        wide_height = tabs.height()
        tabs.setCurrentIndex(3)
        tabs.resize(320, tabs.height())
        self.app.processEvents()
        self.assertGreater(tabs.height(), wide_height)
        self.assertEqual(tabs.currentIndex(), 3)
        for button in tabs.buttons:
            self.assertTrue(button.isVisible())
            self.assertTrue(tabs.rect().contains(button.geometry()))
            self.assertGreaterEqual(button.width(), button.sizeHint().width())
        tabs.buttons[-1].click()
        self.assertEqual(tabs.currentIndex(), len(labels) - 1)
        self.assertEqual(sum(button.isChecked() for button in tabs.buttons), 1)
        tabs.resize(800, tabs.height())
        self.app.processEvents()
        self.assertEqual(tabs.height(), wide_height)


if __name__ == "__main__":
    unittest.main()
