import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = runpy.run_path(str(ROOT / "scripts/chrome-recovery"))
RECORDER = runpy.run_path(str(ROOT / "scripts/freeze-recorder"))


class RecoveryTests(unittest.TestCase):
    def fixture(self, root):
        source, state = root / "chrome", root / "backups"
        sessions = source / "Default/Sessions"
        sessions.mkdir(parents=True)
        (sessions / "Session_123").write_bytes(b"SNSS\x03\0\0\0" + struct.pack("<HB", 1, 255))
        leveldb = source / "Default/Sync Data/LevelDB"
        leveldb.mkdir(parents=True)
        (leveldb / "CURRENT").write_text("MANIFEST-000001\n")
        (leveldb / "MANIFEST-000001").write_bytes(b"manifest fixture")
        (leveldb / "000001.log").write_bytes(b"data fixture")
        (leveldb / "LOCK").touch()
        return source, state

    def test_framing_rejects_empty_truncated_and_unknown_version(self):
        for value in (b"", b"SNSS\x03\0\0\0", b"SNSS\x03\0\0\0\x04\0a", b"SNSS\x09\0\0\0\x01\0x"):
            self.assertFalse(RECOVERY["snss"](value)["valid"])
        self.assertTrue(RECOVERY["snss"](b"SNSS\x03\0\0\0\x01\0\xff")["valid"])

    def test_snapshot_verification_dedup_and_pinning(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            source, state = self.fixture(Path(directory))
            first = RECOVERY["snapshot"](source, state, pin=True)
            second = RECOVERY["snapshot"](source, state)
            data = RECOVERY["verify"](second)
            self.assertEqual(len(data["files"]), 4)
            self.assertTrue((first / "PINNED").exists())
            relative = "Default/Sessions/Session_123"
            self.assertEqual((first / relative).stat().st_ino, (second / relative).stat().st_ino)
            self.assertEqual(state.stat().st_mode & 0o777, 0o700)
            self.assertEqual((second / relative).stat().st_mode & 0o777, 0o600)
            self.assertNotEqual((second / relative).stat().st_ino, (source / relative).stat().st_ino)
            (source / relative).write_bytes(b"")
            third = RECOVERY["snapshot"](source, state)
            self.assertFalse(RECOVERY["verify"](third)["files"][relative]["snss"]["valid"])
            self.assertTrue(RECOVERY["verify"](first)["files"][relative]["snss"]["valid"])

    def test_changing_source_never_publishes_or_prunes(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            source, state = self.fixture(Path(directory))
            first = RECOVERY["snapshot"](source, state)
            function = RECOVERY["snapshot"]
            inventory = RECOVERY["inventory"]
            def unstable(root):
                result = inventory(root)
                unstable.calls += 1
                if unstable.calls % 2 == 0:
                    result["mutation"] = (1, 2, 3, 4)
                return result
            unstable.calls = 0
            with mock.patch.dict(function.__globals__, {"inventory": unstable}), mock.patch("time.sleep"):
                with self.assertRaises(RuntimeError):
                    function(source, state)
            self.assertEqual(RECOVERY["generations"](state), [first])
            self.assertEqual(list(state.glob(".pending-*")), [])

    def test_checksum_damage_detected(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            source, state = self.fixture(Path(directory))
            snapshot = RECOVERY["snapshot"](source, state)
            (snapshot / "Default/Sessions/Session_123").write_bytes(b"bad")
            with self.assertRaises(RuntimeError):
                RECOVERY["verify"](snapshot)

    def test_retention_is_bounded_but_keeps_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            start = dt.datetime(2026, 1, 1)
            paths = [Path(directory) / (start + dt.timedelta(minutes=i * 5)).strftime("%Y%m%dT%H%M%S.000000Z") for i in range(12000)]
            paths[0].mkdir()
            (paths[0] / "PINNED").touch()
            keep = RECOVERY["retained"](paths)
            self.assertIn(paths[0], keep)
            self.assertTrue(set(paths[-72:]).issubset(keep))
            self.assertLessEqual(len(keep), 72 + 48 + 30 + 1)
            self.assertNotIn(paths[1], keep)

    def test_snapshot_cannot_be_inside_chrome(self):
        with tempfile.TemporaryDirectory() as directory:
            source, _ = self.fixture(Path(directory))
            with self.assertRaises(RuntimeError):
                RECOVERY["snapshot"](source, source / "backups")

    def test_export_is_independent_and_refuses_live_or_existing_target(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            source, state = self.fixture(root)
            generation = RECOVERY["snapshot"](source, state)
            destination = root / "export"
            command = ["python3", str(ROOT / "scripts/chrome-recovery"), "export", generation.name,
                       "--source", str(source), "--state", str(state), "--destination"]
            subprocess.run(command + [str(destination)], check=True, capture_output=True)
            relative = "Default/Sessions/Session_123"
            self.assertEqual((destination / relative).read_bytes(), (source / relative).read_bytes())
            self.assertNotEqual((destination / relative).stat().st_ino, (generation / relative).stat().st_ino)
            for unsafe in (source / "new-profile", state / "export", destination):
                self.assertNotEqual(subprocess.run(command + [str(unsafe)], capture_output=True).returncode, 0)

    def test_missing_leveldb_manifest_preserves_old_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            source, state = self.fixture(Path(directory))
            old = RECOVERY["snapshot"](source, state)
            (source / "Default/Sync Data/LevelDB/MANIFEST-000001").unlink()
            with mock.patch("time.sleep"), self.assertRaises(RuntimeError):
                RECOVERY["snapshot"](source, state)
            self.assertEqual(RECOVERY["generations"](state), [old])

    def test_recorder_rotates_and_writes_parseable_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            RECORDER["write_sample"](state, {"test": 1})
            with (state / "samples.jsonl").open("ab") as stream:
                stream.truncate(16 * 1024 * 1024)
            RECORDER["write_sample"](state, {"test": 2})
            self.assertTrue((state / "samples.1.jsonl").exists())
            self.assertEqual(json.loads((state / "samples.jsonl").read_text()), {"test": 2})


if __name__ == "__main__":
    unittest.main()
