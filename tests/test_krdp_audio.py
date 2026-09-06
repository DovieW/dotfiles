#!/usr/bin/env python3
"""Regression tests for the encrypted, session-scoped two-way audio bridge."""

import contextlib
import copy
import fcntl
import io
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class AudioRoutingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.state_file = self.directory / "audio.json"
        self.module = runpy.run_path(str(ROOT / "scripts/krdp-audio"))
        self.defaults = {"sink": "speakers", "source": "microphone"}
        self.data = {
            "sinks": [{"index": 10, "name": "speakers"}, {"index": 11, "name": "hdmi"}],
            "sources": [{"index": 20, "name": "microphone"}, {"index": 21, "name": "usb-mic"}],
            "sink-inputs": [
                {"index": 30, "sink": 11, "properties": {"object.serial": "30"}},
                {"index": 31, "sink": 10, "properties": {"object.serial": "31"}},
            ],
            "source-outputs": [
                {"index": 40, "source": 21, "properties": {"object.serial": "40"}},
            ],
        }
        self.modules = {}
        self.events = []
        self.fail_source = False
        patcher = mock.patch.dict(self.module["main"].__globals__, {
            "STATE_DIR": self.directory,
            "STATE_FILE": self.state_file,
            "LOCK_FILE": self.directory / "audio.lock",
            "items": lambda kind: copy.deepcopy(self.data[kind]),
            "pulse": self.pulse,
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        output = contextlib.redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def pulse(self, *args):
        self.events.append(args)
        command = args[0]
        if command.startswith("get-default-"):
            return self.defaults[command.removeprefix("get-default-")]
        if command.startswith("set-default-"):
            device = command.removeprefix("set-default-")
            self.defaults[device] = args[1]
            return ""
        if command.startswith("move-"):
            streams = command.removeprefix("move-") + "s"
            device = "sink" if streams == "sink-inputs" else "source"
            destination = next(item["index"] for item in self.data[device + "s"] if item["name"] == args[2])
            next(item for item in self.data[streams] if str(item["index"]) == args[1])[device] = destination
            return ""
        if command == "load-module":
            device = args[1].removeprefix("module-tunnel-")
            if self.fail_source and device == "source":
                raise RuntimeError("source tunnel failed")
            name = next(arg.split("=", 1)[1] for arg in args if arg.startswith(f"{device}_name="))
            number = "100" if device == "sink" else "101"
            self.modules[number] = (args[1], " ".join(args[2:]))
            self.data[device + "s"].append({"index": int(number), "name": name})
            return number
        if args == ("list", "short", "modules"):
            return "\n".join(f"{index}\t{name}\t{arguments}\tn/a" for index, (name, arguments) in self.modules.items())
        if command == "unload-module":
            module, _arguments = self.modules.pop(args[1])
            kind = module.removeprefix("module-tunnel-") + "s"
            self.data[kind] = [item for item in self.data[kind] if item["index"] != int(args[1])]
            return ""
        self.fail(f"unexpected pactl call: {args}")

    def activate(self):
        self.module["activate"](Path("/run/user/1000/dotfiles/test.sock"))

    def test_both_directions_use_private_ssh_socket_and_capture_original_routes(self):
        self.activate()
        saved = json.loads(self.state_file.read_text())
        self.assertEqual(saved["defaults"], {"sink": "speakers", "source": "microphone"})
        self.assertEqual(saved["streams"]["sink-inputs"]["30"]["device"], "hdmi")
        self.assertEqual(saved["streams"]["source-outputs"]["40"]["device"], "usb-mic")
        self.assertEqual(self.defaults, {"sink": "dot_krdp_audio", "source": "dot_krdp_microphone"})
        self.assertEqual(self.data["source-outputs"][0]["source"], 101)
        loads = [event for event in self.events if event[0] == "load-module"]
        self.assertEqual(len(loads), 2)
        for event in loads:
            self.assertIn("server=unix:/run/user/1000/dotfiles/test.sock", event)
            self.assertFalse(any("cookie=" in arg or "tcp:" in arg for arg in event))
        self.assertEqual(self.state_file.stat().st_mode & 0o777, 0o600)

    def test_cleanup_restores_individual_routes_and_new_stream_defaults(self):
        self.activate()
        self.data["sink-inputs"].append({"index": 32, "sink": 100})
        self.data["source-outputs"].append({"index": 41, "source": 101})
        self.module["restore"]()
        self.assertEqual([item["sink"] for item in self.data["sink-inputs"]], [11, 10, 10])
        self.assertEqual([item["source"] for item in self.data["source-outputs"]], [21, 20])
        self.assertEqual(self.defaults, {"sink": "speakers", "source": "microphone"})
        self.assertFalse(self.state_file.exists())
        self.assertEqual(self.modules, {})
        self.assertLess(self.events.index(("move-sink-input", "30", "hdmi")), self.events.index(("set-default-sink", "speakers")))

    def test_manual_device_changes_are_preserved(self):
        self.activate()
        self.defaults = {"sink": "hdmi", "source": "usb-mic"}
        self.data["sink-inputs"][0]["sink"] = 10
        self.data["source-outputs"][0]["source"] = 20
        self.module["restore"]()
        self.assertEqual(self.defaults, {"sink": "hdmi", "source": "usb-mic"})
        self.assertEqual(self.data["sink-inputs"][0]["sink"], 10)
        self.assertEqual(self.data["source-outputs"][0]["source"], 20)

    def test_reused_stream_index_does_not_inherit_an_old_devices_route(self):
        self.activate()
        self.data["sink-inputs"][0]["properties"]["object.serial"] = "999"
        self.module["restore"]()
        self.assertEqual(self.data["sink-inputs"][0]["sink"], 10)

    def test_partial_tunnel_failure_can_be_reaped_without_changing_other_modules(self):
        self.modules["900"] = ("module-tunnel-sink", "sink_name=unrelated")
        self.fail_source = True
        with self.assertRaisesRegex(RuntimeError, "source tunnel failed"):
            self.activate()
        self.module["restore"]()
        self.assertEqual(list(self.modules), ["900"])
        self.assertFalse(self.state_file.exists())

    def test_missing_original_hardware_uses_an_available_non_monitor_device(self):
        self.activate()
        self.data["sources"] = [item for item in self.data["sources"] if item["name"] != "microphone"]
        self.data["source-outputs"].append({"index": 41, "source": 101})
        self.module["restore"]()
        self.assertEqual(self.defaults["source"], "usb-mic")
        self.assertEqual(self.data["source-outputs"][-1]["source"], 21)

    def test_reaper_leaves_a_living_sessions_routes_alone(self):
        self.activate()
        with (self.directory / "audio.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with mock.patch("sys.argv", ["krdp-audio", "reap"]):
                self.assertEqual(self.module["main"](), 0)
        self.assertEqual(self.defaults["source"], "dot_krdp_microphone")
        with mock.patch("sys.argv", ["krdp-audio", "reap"]):
            self.assertEqual(self.module["main"](), 0)
        self.assertEqual(self.defaults["source"], "microphone")

    def test_no_saved_state_means_no_audio_changes(self):
        self.module["restore"]()
        self.assertEqual(self.events, [])


class AudioLifetimeTests(unittest.TestCase):
    def test_server_requires_rdp_from_the_same_ssh_peer(self):
        function = runpy.run_path(str(ROOT / "scripts/krdp-audio"))["rdp_connected"]
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout="0 0 100.1.1.1:3389 100.2.2.2:45678\n")):
            self.assertTrue(function("100.2.2.2"))
            self.assertFalse(function("100.3.3.3"))

    def test_client_uses_reverse_unix_forwarding_and_stops_on_pid_reuse(self):
        module = runpy.run_path(str(ROOT / "config/rdp/krdp-audio-client"))
        process = mock.Mock()
        process.poll.return_value = None
        with mock.patch.dict(module["main"].__globals__, {
            "identity": mock.Mock(side_effect=["original", "original", "original", "new", "new", "new"]),
            "time": mock.Mock(),
        }), mock.patch("sys.argv", ["audio-client", "test-desktop", "test-user", "123"]), mock.patch(
            "signal.signal"
        ), mock.patch("pathlib.Path.is_socket", return_value=True), mock.patch(
            "subprocess.run", return_value=mock.Mock(stdout="/run/user/2000/dotfiles\n")
        ), mock.patch("subprocess.Popen", return_value=process) as launch:
            self.assertEqual(module["main"](), 0)
        argv = launch.call_args.args[0]
        forward = argv[argv.index("-R") + 1]
        self.assertRegex(forward, r"^/run/user/2000/dotfiles/krdp-audio-[0-9a-f]{16}\.sock:/run/user/\d+/pulse/native$")
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("ExitOnForwardFailure=yes", argv)
        self.assertIn("test-user@test-desktop", argv)
        process.stdin.write.assert_called_once_with(b"alive\n")
        process.stdin.close.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_broken_control_pipe_still_reaps_the_ssh_child(self):
        function = runpy.run_path(str(ROOT / "config/rdp/krdp-audio-client"))["terminate"]
        process = mock.Mock()
        process.stdin.close.side_effect = BrokenPipeError()
        process.wait.side_effect = [subprocess.TimeoutExpired("ssh", 5), 0]
        function(process)
        process.terminate.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)


if __name__ == "__main__":
    unittest.main()
