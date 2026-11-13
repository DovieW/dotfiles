import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest import mock

try:
    from PyQt6.QtGui import QImage
except ImportError:
    QImage = None

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("image_path", str(ROOT / "scripts/dot-paste-image-path"))
spec = importlib.util.spec_from_loader(loader.name, loader)
helper = importlib.util.module_from_spec(spec)
loader.exec_module(helper)


class ImagePathTests(unittest.TestCase):
    @unittest.skipIf(QImage is None, "PyQt6 desktop image codecs unavailable")
    def test_clipboard_image_is_converted_to_private_png_without_writing_clipboard(self):
        from PyQt6.QtCore import QBuffer, QIODevice
        image = QImage(2, 2, QImage.Format.Format_RGB32)
        image.fill(0xff123456)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.assertTrue(image.save(buffer, "JPEG"))
        with mock.patch.object(helper, "run", side_effect=[
            subprocess.CompletedProcess([], 0, b"text/plain\nimage/jpeg\n"),
            subprocess.CompletedProcess([], 0, bytes(buffer.data())),
        ]) as run:
            path = helper.save_image()
        try:
            self.assertEqual(path.parent, Path('/tmp'))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertTrue(all(call.args[0][0] == 'wl-paste' for call in run.call_args_list))
        finally:
            path.unlink()

    @unittest.skipIf(QImage is None, "PyQt6 desktop image codecs unavailable")
    def test_nonimage_and_invalid_image_never_create_file(self):
        for results in [[subprocess.CompletedProcess([], 0, b'text/plain\n')], [
            subprocess.CompletedProcess([], 0, b'image/png\n'),
            subprocess.CompletedProcess([], 0, b'not an image'),
        ]]:
            with self.subTest(results=results), mock.patch.object(helper, 'run', side_effect=results), mock.patch.object(helper.tempfile, 'mkstemp') as create:
                with self.assertRaises(RuntimeError):
                    helper.save_image()
                create.assert_not_called()

    def test_path_is_typed_without_enter_or_clipboard_replacement(self):
        with mock.patch.object(helper, 'run') as run, mock.patch.object(helper.time, 'sleep'):
            helper.paste_path(Path('/tmp/dot-image-test.png'))
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][1], 'key')
        self.assertTrue(all(key.endswith(':0') for key in commands[0][2:]))
        self.assertEqual(commands[1][-1], '/tmp/dot-image-test.png ')
        self.assertNotIn('\n', commands[1][-1])

    def test_check_never_saves_or_types(self):
        with mock.patch.object(helper.sys, 'argv', ['helper', '--check']), mock.patch.object(helper, 'check'), mock.patch.object(helper, 'save_image') as save, mock.patch.object(helper, 'paste_path') as paste:
            self.assertEqual(helper.main(), 0)
            save.assert_not_called()
            paste.assert_not_called()
