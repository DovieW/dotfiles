"""Recovery must preserve other live work and never guess a Codex conversation."""
import contextlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[1]
HERDR = shutil.which("herdr")


class RecoveryStateTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(ROOT / "scripts/herdr-workspace"))

    def test_only_official_codex_uuid_is_resumed(self):
        session = {"source": "herdr:codex", "agent": "codex", "kind": "id", "value": str(uuid.uuid4())}
        validate = self.module["codex_session"]
        self.assertEqual(validate({"agent_session": session}), session["value"])
        for patch in ({"source": "custom"}, {"agent": "claude"}, {"value": "--last"}, {"kind": "path"}):
            self.assertIsNone(validate({"agent_session": {**session, **patch}}))

    def test_history_is_private_bounded_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.module["Store"]("/test/session.sock", Path(directory) / "state")
            for index in range(35):
                wid = str(index)
                with store.locked() as state:
                    state["live"][wid] = {"id": wid}
                    self.module["remember"](state, wid, "server1")
                    state["live"][wid] = {"id": wid}
                    self.module["remember"](state, wid, "server1")
            with store.locked() as state:
                self.assertEqual(len(state["closed"]), 30)
                self.assertEqual(state["closed"][-1]["workspace"]["id"], "34")
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.root.stat().st_mode & 0o777, 0o700)

    def test_unavailable_session_does_not_start_an_application(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sock"
            with self.assertRaises(OSError):
                self.module["Client"](path).snapshot()
            self.assertFalse(path.exists())

    def test_duplicate_shortcut_invocations_are_serialized(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.module["Store"]("/test/session.sock", Path(directory))
            with store.operation():
                with self.assertRaises(BlockingIOError), store.operation():
                    self.fail("second recovery acquired the same session lock")


@unittest.skipUnless(HERDR, "Herdr integration tests require the installed binary")
class RecoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(ROOT / "scripts/herdr-workspace"))
        self.temp = tempfile.TemporaryDirectory(prefix="dot-herdr-recovery-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = self.root / "config/herdr"
        config.mkdir(parents=True)
        (config / "config.toml").write_text(
            'onboarding=false\n[terminal]\ndefault_shell="/bin/sh"\nshell_mode="non_login"\n'
            '[ui]\npane_outer_borders=false\npane_gaps=false\n'
        )
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        self.arguments = self.root / "codex-arguments"
        fake = fake_bin / "codex"
        fake.write_text('#!/usr/bin/python3\nimport sys,time,json\n'
                        f'open({str(self.arguments)!r},"w").write(json.dumps(sys.argv[1:]))\n'
                        'time.sleep(60)\n')
        fake.chmod(0o700)
        env = {key: value for key, value in os.environ.items() if not key.startswith("HERDR_")}
        env.update(XDG_CONFIG_HOME=str(self.root / "config"), XDG_STATE_HOME=str(self.root / "state"),
                   XDG_DATA_HOME=str(self.root / "data"), XDG_CACHE_HOME=str(self.root / "cache"),
                   PATH=str(fake_bin) + os.pathsep + env["PATH"])
        self.server = subprocess.Popen([HERDR, "server"], env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_server)
        self.client = self.module["Client"](config / "herdr.sock")
        self.store = self.module["Store"](config / "herdr.sock", self.root / "history")
        self.until(lambda: self.client.snapshot())
        self.observer = None

    def until(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = predicate()
                if result:
                    return result
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.025)
        self.fail("Timed out waiting for isolated Herdr state")

    def stop_server(self):
        if self.server.poll() is None:
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                self.client.call("server.stop")
            try:
                self.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server.terminate()
                self.server.wait(timeout=5)
        observer = getattr(self, "observer", None)
        if observer:
            observer.join(timeout=5)

    def create(self, label):
        return self.client.call("workspace.create", cwd=str(self.root), label=label, focus=False)

    def test_reopen_restores_tabs_splits_cwd_focus_and_exact_codex_id(self):
        original = self.create("untouched")
        created = self.create("recover me")
        wid = created["workspace"]["workspace_id"]
        tree = {"type": "split", "direction": "right", "ratio": 0.35,
                "first": {"type": "split", "direction": "down", "ratio": 0.6,
                          "first": {"type": "pane", "cwd": str(self.root), "label": "code"},
                          "second": {"type": "pane", "cwd": str(self.root), "label": "shell"}},
                "second": {"type": "pane", "cwd": str(self.root), "label": "logs"}}
        layout = self.client.call("layout.apply", tab_id=created["tab"]["tab_id"],
                                  tab_label="coding", root=tree, focus=False)["layout"]
        pane = self.module["layout_ids"](layout["root"])[0]
        session = str(uuid.uuid4())
        self.client.call("pane.report_agent_session", pane_id=pane, source="herdr:codex",
                         agent="codex", agent_session_id=session)
        self.client.call("tab.create", workspace_id=wid, label="second tab", cwd=str(self.root))
        self.client.call("pane.focus", pane_id=pane)
        self.module["close_workspace"](self.client, self.store, wid)
        self.module["reopen"](self.client, self.store)
        snapshot = self.client.snapshot()
        restored = next(w for w in snapshot["workspaces"] if w["label"] == "recover me")
        self.assertNotEqual(restored["workspace_id"], wid)
        self.assertEqual((restored["tab_count"], restored["pane_count"]), (2, 4))
        sentinel = self.client.call("pane.get", pane_id=original["root_pane"]["pane_id"])["pane"]
        self.assertEqual(sentinel["terminal_id"], original["root_pane"]["terminal_id"])
        self.until(self.arguments.exists)
        self.assertEqual(json.loads(self.arguments.read_text()), ["resume", session])
        captured = self.module["capture"](snapshot)[restored["workspace_id"]]
        self.assertEqual(captured["tabs"][0]["tree"]["direction"], "right")
        self.assertAlmostEqual(captured["tabs"][0]["tree"]["ratio"], 0.35, places=5)
        self.assertEqual(captured["tabs"][0]["tree"]["first"]["direction"], "down")
        self.assertEqual(snapshot["focused_workspace_id"], restored["workspace_id"])
        self.assertEqual(snapshot["focused_pane_id"], captured["tabs"][0]["focused"])
        self.assertNotIn("resume_argv", self.store.path.read_text())
        with self.store.locked() as state:
            self.assertFalse(state["closed"])

    def test_native_close_is_observed_and_server_stop_is_not_a_closure(self):
        patcher = mock.patch.dict(self.module["watch_session"].__globals__, {"Store": lambda path: self.store})
        patcher.start()
        self.addCleanup(patcher.stop)

        def observe():
            with contextlib.suppress(OSError):
                self.module["watch_session"](self.client.path)

        self.observer = threading.Thread(target=observe, daemon=True)
        self.observer.start()
        first = self.create("native close")["workspace"]["workspace_id"]

        def recorded():
            return json.loads(self.store.path.read_text())

        self.until(lambda: recorded()["live"].get(first))
        self.client.call("workspace.close", workspace_id=first)
        self.until(lambda: len(recorded()["closed"]) == 1)
        second = self.create("keep on stop")["workspace"]["workspace_id"]
        self.until(lambda: recorded()["live"].get(second))
        self.stop_server()
        self.assertEqual(len(recorded()["closed"]), 1)

    def test_missing_directory_preserves_history_without_creating_workspace(self):
        missing = self.root / "gone"
        missing.mkdir()
        created = self.client.call("workspace.create", cwd=str(missing), label="missing")
        self.module["close_workspace"](self.client, self.store, created["workspace"]["workspace_id"])
        missing.rmdir()
        before = len(self.client.snapshot()["workspaces"])
        with self.assertRaisesRegex(ValueError, "directory is unavailable"):
            self.module["reopen"](self.client, self.store)
        self.assertEqual(len(self.client.snapshot()["workspaces"]), before)
        with self.store.locked() as state:
            self.assertEqual(len(state["closed"]), 1)

    def test_interrupted_restore_preserves_partial_without_duplicate_retry(self):
        created = self.create("partial")
        self.module["close_workspace"](self.client, self.store, created["workspace"]["workspace_id"])
        real_call = self.client.call

        def fail_layout(method, **params):
            if method == "layout.apply":
                raise TimeoutError("simulated transport failure")
            return real_call(method, **params)

        with mock.patch.object(self.client, "call", side_effect=fail_layout):
            with self.assertRaises(TimeoutError):
                self.module["reopen"](self.client, self.store)
        before = len(self.client.snapshot()["workspaces"])
        self.module["reopen"](self.client, self.store)
        self.assertEqual(len(self.client.snapshot()["workspaces"]), before)
        with self.store.locked() as state:
            self.assertIn("restoring", state["closed"][-1])

    def test_repeated_reopen_uses_most_recent_closure_first(self):
        for label in ("older", "newer"):
            created = self.create(label)
            self.module["close_workspace"](self.client, self.store, created["workspace"]["workspace_id"])
        self.module["reopen"](self.client, self.store)
        self.assertEqual([w["label"] for w in self.client.snapshot()["workspaces"]], ["newer"])
        self.module["reopen"](self.client, self.store)
        self.assertEqual([w["label"] for w in self.client.snapshot()["workspaces"]], ["newer", "older"])

    def test_already_active_conversation_is_not_started_a_second_time(self):
        session = str(uuid.uuid4())
        active = self.create("active conversation")
        closed = self.create("duplicate conversation")
        for workspace in (active, closed):
            self.client.call("pane.report_agent_session", pane_id=workspace["root_pane"]["pane_id"],
                             source="herdr:codex", agent="codex", agent_session_id=session)
        self.module["close_workspace"](self.client, self.store, closed["workspace"]["workspace_id"])
        self.module["reopen"](self.client, self.store)
        self.assertFalse(self.arguments.exists())
        self.assertEqual(len(self.client.snapshot()["workspaces"]), 2)


if __name__ == "__main__":
    unittest.main()
