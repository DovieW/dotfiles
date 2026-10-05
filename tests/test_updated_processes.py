import os
from pathlib import Path
import runpy
import tempfile
import unittest

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/audit-updated-processes.py"))


class UpdatedProcessesTests(unittest.TestCase):
    def test_current_code_and_deleted_temporary_data_are_not_stale(self):
        self.assertEqual(MODULE["stale_reasons"](
            "/usr/bin/app", "1-2 rw-p 0 00:00 0 /tmp/cache.so (deleted)\n"
            "1-2 rw-p 0 00:00 0 /usr/share/cache.dat (deleted)"), [])

    def test_replaced_executable_and_library_are_reported(self):
        self.assertEqual(MODULE["stale_reasons"](
            "/opt/app/app (deleted)",
            "1-2 r-xp 0 00:00 0 /usr/lib/libapp.so.1 (deleted)"),
            ["replaced executable", "replaced shared library"])

    def test_scan_handles_current_stale_and_exited_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for pid, exe in [(101, "/usr/bin/current"), (102, "/usr/bin/stale (deleted)")]:
                entry = root / str(pid)
                entry.mkdir()
                (entry / "exe").symlink_to(exe)
                (entry / "maps").write_text("")
                (entry / "comm").write_text("app\n")
            (root / "103").mkdir()
            result = MODULE["audit"](root)
            self.assertEqual([p["pid"] for p in result["stale_processes"]], [102])
            self.assertEqual(result["stale_processes"][0]["uid"], os.getuid())
            self.assertEqual(result["unreadable_processes"], 0)
