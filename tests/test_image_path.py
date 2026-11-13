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
    def test_invalid_image_never_creates_file(self):
        with mock.patch.object(helper, 'read_image_data', return_value=b'not an image'), mock.patch.object(helper.tempfile, 'mkstemp') as create:
            with self.assertRaises(RuntimeError):
                helper.save_image()
            create.assert_not_called()

    def test_text_clipboard_falls_back_to_copyq_without_selecting(self):
        with mock.patch.object(helper, 'run', side_effect=[
            subprocess.CompletedProcess([], 0, b'text/plain\n'),
            subprocess.CompletedProcess([], 0, b'image bytes'),
        ]) as run:
            self.assertEqual(helper.read_image_data(), b'image bytes')
        command = run.call_args_list[-1]
        self.assertEqual(command.args[0][1:], ['eval', '-'])
        self.assertEqual(command.kwargs['input'], helper.COPYQ_IMAGE_SCRIPT.encode())

    def test_unavailable_live_clipboard_still_reads_history(self):
        with mock.patch.object(helper, 'run', side_effect=[
            subprocess.CalledProcessError(1, 'wl-paste'),
            subprocess.CompletedProcess([], 0, b'history image'),
        ]):
            self.assertEqual(helper.read_image_data(), b'history image')

    def test_missing_history_or_copyq_fails_without_creating_file(self):
        for error in [FileNotFoundError(), subprocess.CalledProcessError(1, 'copyq')]:
            with self.subTest(error=error), mock.patch.object(helper, 'run', side_effect=[
                subprocess.CompletedProcess([], 0, b'text/plain\n'), error,
            ]), mock.patch.object(helper.tempfile, 'mkstemp') as create:
                with self.assertRaises(RuntimeError):
                    helper.save_image()
                create.assert_not_called()

    def test_path_is_typed_only_after_physical_release(self):
        events = []
        with mock.patch.object(helper, 'run', side_effect=lambda *a, **k: events.append(('type', a[0]))), mock.patch.object(helper, 'wait_for_desktop_release', side_effect=lambda: events.append(('release', None))):
            helper.paste_path(Path('/tmp/dot-image-test.png'))
        self.assertEqual([event[0] for event in events], ['release', 'type'])
        command = events[1][1]
        self.assertEqual(command[1], 'type')
        self.assertEqual(command[-1], '/tmp/dot-image-test.png ')
        self.assertNotIn('\n', command[-1])

    def test_held_modifiers_prevent_typing(self):
        with mock.patch.object(helper, 'wait_for_desktop_release', side_effect=RuntimeError('held')), mock.patch.object(helper, 'run') as run:
            with self.assertRaises(RuntimeError):
                helper.paste_path(Path('/tmp/dot-image-test.png'))
            run.assert_not_called()

    def test_wait_requires_stable_release_and_times_out_when_held(self):
        clock = [0.0]
        def advance(seconds):
            clock[0] += seconds
        with mock.patch.object(helper.time, 'monotonic', side_effect=lambda: clock[0]), mock.patch.object(helper.time, 'sleep', side_effect=advance):
            helper.wait_for_modifiers(lambda: clock[0] < 0.5, lambda: None)
            self.assertGreaterEqual(clock[0], 0.85)
            with self.assertRaises(RuntimeError):
                helper.wait_for_modifiers(lambda: True, lambda: None, timeout=1)

    def test_check_never_saves_or_types(self):
        with mock.patch.object(helper.sys, 'argv', ['helper', '--check']), mock.patch.object(helper, 'check'), mock.patch.object(helper, 'save_image') as save, mock.patch.object(helper, 'paste_path') as paste:
            self.assertEqual(helper.main(), 0)
            save.assert_not_called()
            paste.assert_not_called()
