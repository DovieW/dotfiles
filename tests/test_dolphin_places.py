import contextlib
import io
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest import mock
from xml.dom import minidom


ROOT = Path(__file__).resolve().parents[1]


class DolphinPlacesTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(ROOT / "bin/dot"))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data/user-places.xbel"
        self.path.parent.mkdir()
        self.backup = mock.Mock(return_value="test-backup")
        self.configure = self.module["configure_dolphin_network_places"]
        patch = mock.patch.dict(self.configure.__globals__, {
            "dolphin_places_path": lambda: self.path,
            "backup_paths": self.backup,
        })
        patch.start()
        self.addCleanup(patch.stop)

    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.configure()

    def test_create_and_repeat_without_changes_or_backups(self):
        self.assertEqual(self.apply(), 1)
        content = self.path.read_bytes()
        self.assertTrue(self.module["dolphin_network_places_ok"]())
        self.assertEqual(self.apply(), 0)
        self.assertEqual(self.path.read_bytes(), content)
        self.backup.assert_called_once_with([self.path])

    def test_preserve_existing_bookmarks_metadata_and_comments(self):
        self.path.write_text('''<?xml version="1.0"?><!DOCTYPE xbel>
<xbel xmlns:custom="urn:custom"><!--keep--><info><custom:data value="abc"/></info>
<bookmark href="file:///home/dovie"><title>Home</title></bookmark>
<bookmark href="smb://truenas-scale/"><title>My NAS</title><info>
<metadata owner="http://www.kde.org"><isHidden>true</isHidden><ID>existing</ID></metadata>
</info></bookmark></xbel>''')
        self.assertEqual(self.apply(), 1)
        doc = minidom.parseString(self.path.read_bytes())
        bookmarks = doc.getElementsByTagName("bookmark")
        self.assertEqual(len(bookmarks), 3)
        self.assertEqual(bookmarks[0].getAttribute("href"), "file:///home/dovie")
        self.assertEqual(bookmarks[1].getElementsByTagName("title")[0].firstChild.nodeValue, "My NAS")
        self.assertEqual(bookmarks[1].getElementsByTagName("ID")[0].firstChild.nodeValue, "existing")
        self.assertEqual(doc.getElementsByTagName("custom:data")[0].getAttribute("value"), "abc")
        self.assertIn(b"<!--keep-->", self.path.read_bytes())
        self.assertIn(b"<!DOCTYPE xbel>", self.path.read_bytes())
        self.assertTrue(self.module["dolphin_network_places_ok"]())
        self.assertEqual(self.apply(), 0)

    def test_malformed_or_wrong_root_leaves_original_untouched(self):
        for content in (b"", b"<xbel><bookmark", b"<other/>"):
            self.path.write_bytes(content)
            with self.assertRaises(self.module["DotError"]):
                self.apply()
            self.assertEqual(self.path.read_bytes(), content)
            self.assertFalse(self.module["dolphin_network_places_ok"]())
        self.backup.assert_not_called()

    def test_preserve_private_file_permissions(self):
        self.path.write_bytes(b"<xbel/>")
        self.path.chmod(0o600)
        self.apply()
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_concurrent_change_is_not_overwritten(self):
        self.backup.side_effect = lambda _: self.path.write_bytes(b"<xbel><!--new--></xbel>")
        with self.assertRaises(self.module["DotError"]):
            self.apply()
        self.assertEqual(self.path.read_bytes(), b"<xbel><!--new--></xbel>")

    def test_profile_inheritance_and_tag_selection(self):
        load = self.module["load_profile"]
        for profile in ("kubuntu-laptop", "kubuntu-desktop"):
            self.assertTrue(load(profile)["features"]["dolphin_network_places"])
        for profile in ("common-linux", "wsl-personal", "wsl-work", "termux", "windows-host"):
            self.assertFalse(load(profile)["features"].get("dolphin_network_places", False))
        apply = self.module["apply_direct"]
        configure = mock.Mock(return_value=1)
        with mock.patch.dict(apply.__globals__, {
            "load_profile": lambda _: {"features": {"dolphin_network_places": True}},
            "configure_dolphin_network_places": configure,
        }), contextlib.redirect_stdout(io.StringIO()):
            for tags in (None, {"config"}, {"kde"}, {"file-manager"}):
                configure.reset_mock()
                apply("test", selected_tags=tags)
                configure.assert_called_once_with()
            configure.reset_mock()
            apply("test", selected_tags={"git"})
            configure.assert_not_called()

    def test_xdg_data_home(self):
        # The real helper remains available despite the function-global mock.
        with mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.directory.name}):
            self.assertEqual(self.module["dolphin_places_path"](), Path(self.directory.name) / "user-places.xbel")


if __name__ == "__main__":
    unittest.main()
