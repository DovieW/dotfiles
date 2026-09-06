#!/usr/bin/env python3
"""Exercise KRdp display preparation without touching the real desktop."""

import contextlib
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


class KrdpScaleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name) / "krdp-scale.json"
        self.module = runpy.run_path(str(ROOT / "scripts/krdp-scale"))
        self.outputs = {"HDMI-A-1": 1.45}
        self.connected = mock.Mock(return_value=False)
        self.clock = mock.Mock()
        self.clock.time.return_value = 1000
        self.set_scale = mock.Mock(side_effect=self.apply_scale)
        self.read_outputs = mock.Mock(side_effect=lambda: [
            {"name": name, "scale": scale} for name, scale in self.outputs.items()
        ])
        patcher = mock.patch.dict(self.module["main"].__globals__, {
            "STATE_FILE": self.state,
            "connected": self.connected,
            "enabled_outputs": self.read_outputs,
            "set_scale": self.set_scale,
            "time": self.clock,
            "log": mock.Mock(),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def apply_scale(self, name, scale):
        self.outputs[name] = scale

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.module["prepare"]()

    def test_prepare_saves_original_geometry_and_sets_connection_grace(self):
        self.prepare()
        self.assertEqual(self.outputs, {"HDMI-A-1": 2.35})
        self.assertEqual(json.loads(self.state.read_text()), {
            "outputs": {"HDMI-A-1": 1.45}, "prepared_until": 1060,
        })

    def test_prepare_never_changes_an_existing_connections_geometry(self):
        self.connected.return_value = True
        self.prepare()
        self.set_scale.assert_not_called()
        self.read_outputs.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_second_preparation_cannot_replace_the_pending_one(self):
        self.prepare()
        saved = self.state.read_text()
        self.set_scale.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "already being prepared"):
            self.prepare()
        self.set_scale.assert_not_called()
        self.assertEqual(self.state.read_text(), saved)

    def test_idle_watcher_preserves_pending_preparation_then_expires_it(self):
        self.prepare()
        self.module["restore_if_idle"]()
        self.assertEqual(self.outputs["HDMI-A-1"], 2.35)
        self.clock.time.return_value = 1061
        self.module["restore_if_idle"]()
        self.assertEqual(self.outputs["HDMI-A-1"], 1.45)
        self.assertFalse(self.state.exists())

    def test_expired_preparation_is_not_restored_during_a_connection(self):
        self.prepare()
        self.clock.time.return_value = 2000
        self.connected.return_value = True
        self.module["restore_if_idle"]()
        self.assertEqual(self.outputs["HDMI-A-1"], 2.35)
        self.assertTrue(self.state.exists())

    def test_client_exit_waits_for_the_last_server_socket_to_close(self):
        self.prepare()
        self.connected.return_value = True
        self.module["restore_if_idle"](release=True)
        self.assertEqual(self.outputs["HDMI-A-1"], 2.35)
        self.assertEqual(self.module["prepared_until"](), 0)
        self.connected.return_value = False
        self.module["restore_if_idle"]()
        self.assertEqual(self.outputs["HDMI-A-1"], 1.45)
        self.assertFalse(self.state.exists())

    def test_failed_client_restores_without_waiting_for_grace_to_expire(self):
        self.prepare()
        self.module["restore_if_idle"](release=True)
        self.assertEqual(self.outputs["HDMI-A-1"], 1.45)
        self.assertFalse(self.state.exists())

    def test_retry_does_not_overwrite_the_original_physical_scale(self):
        self.prepare()
        self.clock.time.return_value = 1061
        self.prepare()
        self.assertEqual(self.module["load_state"](), {"HDMI-A-1": 1.45})
        self.module["restore_if_idle"](release=True)
        self.assertEqual(self.outputs["HDMI-A-1"], 1.45)

    def test_unapplied_scale_fails_preparation_and_remains_recoverable(self):
        self.set_scale.side_effect = None
        with self.assertRaisesRegex(RuntimeError, "did not apply"):
            self.prepare()
        self.assertEqual(self.module["prepared_until"](), 0)
        self.set_scale.side_effect = self.apply_scale
        self.module["restore_if_idle"]()
        self.assertFalse(self.state.exists())

    def test_socket_inspection_failure_does_not_restore_a_live_display(self):
        self.prepare()
        self.clock.time.return_value = 2000
        self.connected.side_effect = RuntimeError("ss failed")
        with self.assertRaisesRegex(RuntimeError, "ss failed"):
            self.module["restore_if_idle"]()
        self.assertEqual(self.outputs["HDMI-A-1"], 2.35)
        self.assertTrue(self.state.exists())


class KrdpWatcherTests(unittest.TestCase):
    def run_watcher(self, connections):
        module = runpy.run_path(str(ROOT / "scripts/krdp-panel-watch"))
        namespace = module["main"].__globals__
        calls = mock.Mock()
        remaining = len(connections)

        def pause(_seconds):
            nonlocal remaining
            remaining -= 1
            if remaining == 0:
                namespace["running"] = False

        with mock.patch.dict(namespace, {
            "connected": mock.Mock(side_effect=connections),
            "panel": calls.panel,
            "scale": calls.scale,
            "signal": mock.Mock(),
            "time": mock.Mock(sleep=mock.Mock(side_effect=pause)),
            "running": True,
        }):
            self.assertEqual(module["main"](), 0)
        return calls.mock_calls

    def test_connect_and_disconnect_never_activate_or_release_scale(self):
        self.assertEqual(self.run_watcher([False, True, True, False]), [
            mock.call.panel("deactivate"),
            mock.call.scale("restore-if-idle"),
            mock.call.panel("activate"),
            mock.call.panel("activate"),
            mock.call.panel("deactivate"),
            mock.call.scale("restore-if-idle"),
            mock.call.scale("restore-if-idle"),
        ])

    def test_stopping_watcher_only_requests_guarded_display_cleanup(self):
        self.assertEqual(self.run_watcher([True]), [
            mock.call.panel("activate"),
            mock.call.panel("deactivate"),
            mock.call.scale("restore-if-idle"),
        ])


class KrdpClientTests(unittest.TestCase):
    def run_client(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binaries = root / "bin"
            binaries.mkdir()
            events = root / "events"
            programs = {
                "pgrep": "exit 1\n",
                "kdialog": """
case "$1" in
  --password)
    printf 'prompt\\n' >> "$KRDP_TEST_EVENTS"
    printf 'simulated-input\\n'
    exit "${KRDP_TEST_PROMPT_EXIT:-0}" ;;
  --error) printf 'error-dialog\\n' >> "$KRDP_TEST_EVENTS" ;;
esac
""",
                "ssh": """
action="${@: -1}"
printf 'ssh:%s\\n' "$action" >> "$KRDP_TEST_EVENTS"
case "$action" in
  prepare) exit "${KRDP_TEST_PREPARE_EXIT:-0}" ;;
  release) exit "${KRDP_TEST_RELEASE_EXIT:-0}" ;;
  *) exit 92 ;;
esac
""",
                "xfreerdp": """
if [[ "$1" == /buildconfig ]]; then
  echo WITH_GFX_H264=ON
  exit 0
fi
printf 'client\\n' >> "$KRDP_TEST_EVENTS"
read -r input
[[ "$input" == simulated-input ]] || exit 93
for argument in "$@"; do
  [[ "$argument" != /p:* && "$argument" != *simulated-input* ]] || exit 94
done
exit "${KRDP_TEST_CLIENT_EXIT:-0}"
""",
            }
            for name, body in programs.items():
                path = binaries / name
                path.write_text("#!/usr/bin/env bash\nset -eu\n" + body)
                path.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": f"{binaries}:{os.environ['PATH']}",
                "HOMEBREW_PREFIX": str(root),
                "XDG_RUNTIME_DIR": str(root / "runtime"),
                "KRDP_TEST_EVENTS": str(events),
                **overrides,
            }
            result = subprocess.run(
                [str(ROOT / "config/rdp/krdp-client"), "test-desktop"],
                env=environment, text=True, capture_output=True, timeout=10,
            )
            return result, events.read_text().splitlines()

    def test_preparation_finishes_before_client_launch_and_releases_on_exit(self):
        result, events = self.run_client()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, ["prompt", "ssh:prepare", "client", "ssh:release"])

    def test_failed_preparation_never_connects_or_releases_another_preparation(self):
        result, events = self.run_client(KRDP_TEST_PREPARE_EXIT="1")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(events, ["prompt", "ssh:prepare", "error-dialog"])

    def test_cancelled_password_prompt_never_changes_the_display(self):
        result, events = self.run_client(KRDP_TEST_PROMPT_EXIT="1")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(events, ["prompt"])

    def test_failed_client_still_releases_and_preserves_its_exit_status(self):
        result, events = self.run_client(
            KRDP_TEST_CLIENT_EXIT="42", KRDP_TEST_RELEASE_EXIT="1",
        )
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertEqual(events, ["prompt", "ssh:prepare", "client", "ssh:release"])


if __name__ == "__main__":
    unittest.main()
