"""Exercise the music command without contacting third-party services."""
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / "config/shell/ytm"


class MusicCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "args.json"
        self.destination = self.root / "Music: collection"
        self.env = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin", YTM_TEST_LOG=str(self.log))
        self.tool = self.bin / "yt-dlp"
        self.tool.write_text(
            '#!/usr/bin/python3\nimport json, os, sys\n'
            'with open(os.environ["YTM_TEST_LOG"], "w") as f: json.dump(sys.argv[1:], f)\n'
            'sys.exit(int(os.environ.get("YTM_TEST_STATUS", "0")))\n'
        )
        self.tool.chmod(0o755)

    def run_command(self, *args, **env):
        return subprocess.run([str(COMMAND), *args], env={**self.env, **env},
                              capture_output=True, text=True)

    def test_playlist_arguments_and_destination_are_preserved(self):
        urls = ["https://example.test/watch?v=one&list=two", "https://example.test/playlist?list=three"]
        result = self.run_command("-o", str(self.destination), "--items", "2-5,8", *urls)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.log.read_text())
        self.assertEqual(args[-3:], ["--", *urls])
        self.assertIn("--yes-playlist", args)
        self.assertEqual(args[args.index("--playlist-items") + 1], "2-5,8")
        self.assertEqual(args[args.index("--download-archive") + 1],
                         str(self.destination / ".ytm/archive-mp3.txt"))
        self.assertTrue((self.destination / ".ytm").is_dir())

    def test_preview_has_no_filesystem_side_effects_and_propagates_errors(self):
        result = self.run_command("--dry-run", "-o", str(self.destination),
                                  "https://example.test/playlist", YTM_TEST_STATUS="7")
        self.assertEqual(result.returncode, 7)
        self.assertFalse(self.destination.exists())
        args = json.loads(self.log.read_text())
        self.assertIn("--simulate", args)
        self.assertIn("--ignore-config", args)

    def test_single_flat_and_format_options(self):
        result = self.run_command("--single", "--flat", "--no-archive", "-f", "opus",
                                  "-o", str(self.destination), "https://example.test/watch")
        self.assertEqual(result.returncode, 0, result.stderr)
        args = json.loads(self.log.read_text())
        self.assertIn("--no-playlist", args)
        self.assertNotIn("--download-archive", args)
        self.assertFalse((self.destination / ".ytm").exists())
        self.assertNotIn("/", args[args.index("--output") + 1])
        self.assertEqual(args[args.index("--audio-format") + 1], "opus")

    def test_invalid_input_does_not_create_destination_or_start_downloader(self):
        for arguments in [[], ["--bad"], ["--output"], ["-f", "wav", "https://example.test/a"],
                          ["--", "--exec=unexpected"], ["not-a-url"]]:
            with self.subTest(arguments=arguments):
                result = self.run_command(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(self.log.exists())

    def test_help_works_without_dependencies_and_missing_dependency_is_clear(self):
        self.tool.unlink()
        # An isolated PATH with just Bash makes dependency checks deterministic.
        (self.bin / "bash").symlink_to(shutil.which("bash"))
        (self.bin / "cat").symlink_to(shutil.which("cat"))
        self.assertEqual(self.run_command("--help", PATH=str(self.bin)).returncode, 0)
        result = self.run_command("https://example.test/a", PATH=str(self.bin))
        self.assertEqual(result.returncode, 2)
        self.assertIn("yt-dlp is required", result.stderr)

    @unittest.skipUnless(shutil.which("yt-dlp"), "yt-dlp is not installed")
    def test_real_downloader_formats_safe_single_and_playlist_paths_offline(self):
        real_tool = shutil.which("yt-dlp")
        info = self.root / "info.json"
        track = {"id": "one", "title": "A / song", "extractor": "generic",
                 "extractor_key": "Generic", "webpage_url": "https://example.test/one",
                 "formats": [{"format_id": "audio", "url": "https://example.test/a.m4a",
                              "ext": "m4a", "vcodec": "none", "acodec": "aac"}]}
        self.run_command("--dry-run", "-o", str(self.destination), "https://example.test/a")
        args = json.loads(self.log.read_text())
        args = args[:args.index("--")]  # Replace the URL with an offline fixture.
        for playlist in [False, True]:
            with self.subTest(playlist=playlist):
                data = dict(track)
                if playlist:
                    data["playlist_title"] = "My / playlist"
                info.write_text(json.dumps(data))
                result = subprocess.run([real_tool, *args, "--load-info-json", str(info),
                                         "--print", "filename"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                filename = Path(result.stdout.splitlines()[-1])
                self.assertTrue(filename.is_relative_to(self.destination))
                self.assertEqual(filename.parent == self.destination, not playlist)
                self.assertIn("[one]", filename.name)
        self.assertFalse(self.destination.exists())

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("yt-dlp", "ffmpeg", "ffprobe")),
                         "real media tools are not installed")
    def test_local_playlist_conversion_cover_art_and_repeat_download(self):
        web = self.root / "web"
        web.mkdir()
        for command in (
            ["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2",
             "-c:a", "aac", str(web / "one.mp4")],
            ["ffmpeg", "-f", "lavfi", "-i", "color=red:s=32x32", "-frames:v", "1",
             "-threads", "1", str(web / "cover.jpg")],
        ):
            result = subprocess.run([*command[:1], "-hide_banner", "-loglevel", "error", *command[1:]],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        shutil.copyfile(web / "one.mp4", web / "two.mp4")
        (web / "index.html").write_text(
            '<html><title>Test playlist</title>'
            '<video src="one.mp4" poster="cover.jpg" controls></video>'
            '<video src="two.mp4" poster="cover.jpg" controls></video></html>'
        )

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(web)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            command = [str(COMMAND), "-o", str(self.destination),
                       f"http://127.0.0.1:{server.server_port}/index.html"]
            preview = subprocess.run([*command, "--dry-run"], capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertFalse(self.destination.exists())
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            files = sorted((self.destination / "Test playlist").glob("*.mp3"))
            self.assertEqual(len(files), 2)
            self.assertTrue(files[0].name.startswith("001 - "))
            self.assertTrue(files[1].name.startswith("002 - "))
            before = {f: (f.stat().st_mtime_ns, f.read_bytes()) for f in files}
            probe = subprocess.run(["ffprobe", "-v", "quiet", "-show_streams", "-show_format",
                                    "-of", "json", str(files[0])], capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            media = json.loads(probe.stdout)
            self.assertTrue(any(s["codec_name"] == "mp3" for s in media["streams"]))
            self.assertTrue(any(s.get("disposition", {}).get("attached_pic") for s in media["streams"]))
            self.assertIn("title", media["format"]["tags"])
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already been recorded in the archive", result.stdout)
            self.assertEqual(before, {f: (f.stat().st_mtime_ns, f.read_bytes()) for f in files})
            # yt-dlp can refresh tags/art when history is bypassed; audio stays.
            def audio_hash(file):
                result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(file),
                                         "-map", "0:a", "-c", "copy", "-f", "hash", "-"],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            audio_before = {f: audio_hash(f) for f in files}
            result = subprocess.run([*command, "--no-archive"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(audio_before, {f: audio_hash(f) for f in files})
            self.assertEqual(len((self.destination / ".ytm/archive-mp3.txt").read_text().splitlines()), 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
