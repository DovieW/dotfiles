#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import pty
import re
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
DOT = ROOT / "bin/dot"


class DotCliTests(unittest.TestCase):
    def run_dot(self, *args):
        return subprocess.run([str(DOT), *args], text=True, capture_output=True)

    def test_help(self):
        result = self.run_dot("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bootstrap", result.stdout)
        self.assertIn("bootstrap-media", result.stdout)
        self.assertIn("codex", result.stdout)
        self.assertIn("doctor", result.stdout)
        self.assertIn("device", result.stdout)
        self.assertIn("finalize", result.stdout)
        self.assertIn("gestures", result.stdout)
        self.assertIn("nvim", result.stdout)
        self.assertIn("panel", result.stdout)
        self.assertIn("preflight", result.stdout)
        self.assertIn("save", result.stdout)
        self.assertIn("tailscale", result.stdout)
        self.assertIn("meshcentral", result.stdout)
        self.assertIn("update", result.stdout)

    def test_ci_runs_complete_pinned_validation(self):
        workflow = (ROOT / ".github/workflows/validate.yml").read_text()
        requirements = (
            ROOT / ".github/requirements-validation.txt"
        ).read_text()
        runner = (ROOT / "tests/run").read_text()
        safety = (ROOT / "scripts/check-public-safety").read_text()

        for action in (
            "actions/checkout",
            "actions/setup-python",
            "gitleaks/gitleaks-action",
        ):
            matches = re.findall(rf"{re.escape(action)}@([0-9a-f]{{40}})", workflow)
            self.assertTrue(matches, f"{action} must be pinned to a full commit SHA")
        for package in ("bats", "ripgrep", "shellcheck"):
            self.assertIn(package, workflow)
        self.assertIn("brew install neovim stylua", workflow)
        self.assertIn("RequiredVersion 6.0.0", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        for requirement in (
            "ansible-core==2.21.3",
            "ansible-lint==26.8.0",
            "yamllint==1.38.0",
        ):
            self.assertIn(requirement, requirements)
        self.assertIn('if [[ "${CI:-}" == true ]]', runner)
        self.assertIn("ripgrep is required", safety)

    def test_ansible_mutating_commands_report_changes(self):
        nomachine = (ROOT / "ansible/tasks/nomachine.yml").read_text()
        tailscale = (ROOT / "ansible/tasks/tailscale.yml").read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        self.assertIn("notify: Restart NoMachine", nomachine)
        self.assertIn("ansible.builtin.meta: flush_handlers", nomachine)
        self.assertIn("failed_when: false", nomachine)
        self.assertIn("when: not dot_nomachine_tailscale_ready", nomachine)
        self.assertIn("when: dot_nomachine_tailscale_ready", nomachine)
        self.assertIn("handlers:", playbook)
        operator = tailscale.split(
            "- name: Allow the desktop user to operate Tailscale", 1
        )[1].split("- name: Read Tailscale connection state", 1)[0]
        self.assertIn("changed_when: true", operator)

    def test_official_repositories_cover_supported_profiles(self):
        manifest = json.loads((ROOT / "repositories/official.yml").read_text())
        repositories = {entry["name"]: entry for entry in manifest["repositories"]}
        expected = {
            "obsidian-general",
            "obsidian-bnh",
            "obsidian-personal",
            "homelab-infra",
            "nvim-config",
            "openclaw-infra",
            "vscode-workspaces",
        }
        self.assertEqual(set(repositories), expected)
        supported = {"kubuntu-laptop", "windows-host", "wsl-personal", "wsl-work"}
        for name, entry in repositories.items():
            profiles = set(entry["profiles"])
            if name == "obsidian-personal":
                self.assertEqual(profiles, supported - {"wsl-work"})
            else:
                self.assertEqual(profiles, supported)
            self.assertTrue(entry["url"].startswith("git@github.com:DovieW/"))

    def test_repository_manifest_merge_and_https_bootstrap_url(self):
        module = runpy.run_path(str(DOT))
        official = json.loads((ROOT / "repositories/official.yml").read_text())
        duplicate = dict(official["repositories"][0])
        merged = module["merged_repositories"]({"repositories": [duplicate]})
        self.assertEqual(len(merged), len(official["repositories"]))
        self.assertEqual(
            module["github_https_url"]("git@github.com:DovieW/example.git"),
            "https://github.com/DovieW/example.git",
        )
        conflict = {**duplicate, "url": "git@github.com:DovieW/other.git"}
        with self.assertRaises(module["DotError"]):
            module["merged_repositories"]({"repositories": [conflict]})

    def test_bootstrap_media_verifies_checksums_bundle_and_secret_policy(self):
        module = runpy.run_path(str(DOT))
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory)
            payload = media / "payload"
            payload.mkdir()
            subprocess.run(
                ["git", "bundle", "create", str(payload / "dotfiles.bundle"), "HEAD"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
            manifest = {
                "schema_version": 1,
                "commit": subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                    check=True, capture_output=True,
                ).stdout.strip(),
                "contains_secrets": False,
            }
            (media / "manifest.json").write_text(json.dumps(manifest))
            paths = [media / "manifest.json", payload / "dotfiles.bundle"]
            import hashlib
            (media / "SHA256SUMS").write_text("".join(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(media).as_posix()}\n"
                for path in paths
            ))
            self.assertEqual(module["verify_bootstrap_media"](media)["commit"], manifest["commit"])
            (media / "manifest.json").write_text('{"contains_secrets": true}')
            with self.assertRaises(module["DotError"]):
                module["verify_bootstrap_media"](media)

    def test_bootstrap_media_rejects_unstable_device_paths(self):
        module = runpy.run_path(str(DOT))
        for target in ("/dev/sda", "/dev/disk/by-id/nvme-example", "relative"):
            with self.subTest(target=target), self.assertRaises(module["DotError"]):
                module["bootstrap_usb_info"](target)

    def test_bootstrap_media_recovers_usb_serial_from_udev(self):
        module = runpy.run_path(str(DOT))
        device = Path("/dev/disk/by-id/usb-Test_Drive_SERIAL123-0:0")
        lsblk = mock.Mock(
            stdout=json.dumps({
                "blockdevices": [{
                    "path": "/dev/sdz", "type": "disk", "tran": "usb",
                    "rm": True, "size": 1024, "model": "Test Drive",
                    "serial": None, "children": [],
                }]
            })
        )
        udev = mock.Mock(stdout="ID_SERIAL_SHORT=SERIAL123\n")
        findmnt = mock.Mock(stdout="/dev/nvme0n1p2\n")
        ancestry = mock.Mock(stdout="/dev/nvme0n1\n/dev/nvme0n1p2\n")
        function = module["bootstrap_usb_info"]
        with mock.patch.object(Path, "resolve", return_value=Path("/dev/sdz")), \
             mock.patch.dict(function.__globals__, {"run": mock.Mock(side_effect=[lsblk, udev, findmnt, ancestry])}):
            _, info = function(str(device))
        self.assertEqual(info["serial"], "SERIAL123")

    def test_bootstrap_media_recovers_partition_metadata_from_udev(self):
        module = runpy.run_path(str(DOT))
        device = Path("/dev/disk/by-id/usb-Test_Drive_SERIAL123-0:0")
        lsblk = mock.Mock(
            stdout=json.dumps({
                "blockdevices": [{
                    "path": "/dev/sdz", "type": "disk", "tran": "usb",
                    "rm": True, "size": 1024, "model": "Test Drive",
                    "serial": None, "children": [{
                        "path": "/dev/sdz1", "type": "part", "fstype": None,
                        "label": None, "mountpoints": [],
                    }],
                }]
            })
        )
        disk_udev = mock.Mock(stdout="ID_SERIAL_SHORT=SERIAL123\n")
        partition_udev = mock.Mock(
            stdout="ID_FS_TYPE=vfat\nID_FS_LABEL=DOTBOOT\n"
        )
        findmnt = mock.Mock(stdout="/dev/nvme0n1p2\n")
        ancestry = mock.Mock(stdout="/dev/nvme0n1\n/dev/nvme0n1p2\n")
        function = module["bootstrap_usb_info"]
        with mock.patch.object(Path, "resolve", return_value=Path("/dev/sdz")), \
             mock.patch.dict(function.__globals__, {"run": mock.Mock(side_effect=[
                 lsblk, disk_udev, partition_udev, findmnt, ancestry,
             ])}):
            _, info = function(str(device))
        partition = module["bootstrap_partition"](info)
        self.assertEqual(partition["fstype"], "vfat")
        self.assertEqual(partition["label"], "DOTBOOT")

    def test_bootstrap_media_uses_policykit_without_passwordless_sudo(self):
        module = runpy.run_path(str(DOT))
        function = module["bootstrap_media_privilege_prefix"]
        denied = mock.Mock(returncode=1)
        with mock.patch.dict(
            function.__globals__,
            {
                "run": mock.Mock(return_value=denied),
                "command_exists": mock.Mock(return_value=True),
            },
        ):
            self.assertEqual(function(), ["pkexec"])

    def test_bootstrap_prerequisites_and_chrome_are_managed(self):
        script = (ROOT / "scripts/bootstrap-prerequisites").read_text()
        launcher = (ROOT / "bootstrap-media/START-LINUX.sh").read_text()
        role = (ROOT / "ansible/tasks/chrome.yml").read_text()
        source = (ROOT / "config/apt/google-chrome.sources").read_text()
        kubuntu = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        windows = json.loads((ROOT / "profiles/windows-host.yml").read_text())
        self.assertTrue(kubuntu["features"]["google_chrome"])
        self.assertIn("EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796", script)
        self.assertIn("brew install ansible bitwarden-cli gh jq", script)
        self.assertIn("EB4C1BFD4F042F6DDDCCEC917721F63BD38B4796", role)
        self.assertIn("Signed-By: /usr/share/keyrings/google-chrome.gpg", source)
        for package in (
            "Bitwarden.CLI", "GitHub.cli", "Google.Chrome", "Python.Python.3.13"
        ):
            self.assertIn(package, windows["packages"]["winget"])
        self.assertIn("https://github.com/DovieW/dotfiles.git", launcher)
        self.assertIn("verified USB bundle", launcher)

    def test_bootstrap_preflight_rejects_identity_drift(self):
        module = runpy.run_path(str(DOT))
        function = module["bootstrap_preflight"]
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.dict(function.__globals__, {
                 "STATE_DIR": Path(directory),
                 "BOOTSTRAP_PREFLIGHT": Path(directory) / "preflight.json",
                 "inferred_device_id": mock.Mock(return_value="new-device"),
                 "capture_inventory_command": mock.Mock(
                     side_effect=lambda command: (
                         "rw,nosuid,nodev" if command[0] == "findmnt"
                         else "exit 0; no output"
                     )
                 ),
                 "run": mock.Mock(return_value=mock.Mock(returncode=0)),
             }):
            with self.assertRaises(module["DotError"]) as raised:
                function(module["load_profile"]("kubuntu-laptop"), "old-device")
        self.assertIn("dot device rename old-device new-device", str(raised.exception))

    def test_new_computer_finalization_is_a_repository_protocol(self):
        cli = DOT.read_text()
        agents = (ROOT / "AGENTS.md").read_text()
        docs = (ROOT / "docs/finalize-computer.md").read_text()
        example = json.loads((ROOT / "devices/example-device.yml").read_text())

        self.assertIn('choices=["auto", "new", "existing"]', cli)
        self.assertIn("FINALIZATION_DEFERRED_TAGS", cli)
        self.assertIn('command.extend(["--skip-tags", skip_tags])', cli)
        self.assertIn("write_finalization_handoff", cli)
        self.assertIn("finalize prepare", agents)
        self.assertIn("Finalize this computer", docs)
        self.assertEqual(example["schema_version"], 1)
        self.assertTrue(example["finalized"])
        self.assertFalse(any("serial" in key.lower() for key in example))

    def test_device_manifest_validation_is_strict(self):
        module = runpy.run_path(str(DOT))
        function = module["load_device_manifest"]
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            function.__globals__, {"DEVICE_DIR": Path(directory)}
        ):
            manifest = {
                "schema_version": 1,
                "device_id": "test-device",
                "profile": "kubuntu-laptop",
                "finalized": True,
                "approved_tags": ["gpu"],
            }
            (Path(directory) / "test-device.yml").write_text(json.dumps(manifest))
            self.assertEqual(function("test-device"), manifest)
            manifest["approved_tags"] = ["unknown-tag"]
            (Path(directory) / "test-device.yml").write_text(json.dumps(manifest))
            with self.assertRaises(module["DotError"]):
                function("test-device")

    def test_device_identity_rejects_path_traversal(self):
        module = runpy.run_path(str(DOT))
        function = module["ensure_device"]
        for device in ("../outside", "UPPERCASE", "contains space", ""):
            with self.subTest(device=device), self.assertRaises(module["DotError"]):
                function(device)

    def test_device_rename_requires_matching_system_hostname(self):
        module = runpy.run_path(str(DOT))
        function = module["cmd_device_rename"]
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config"
            state = Path(directory) / "state"
            config.mkdir()
            (config / "device.json").write_text(json.dumps({
                "schema_version": 1, "device_id": "old-device",
            }))
            with mock.patch.dict(
                function.__globals__, {"CONFIG_DIR": config, "STATE_DIR": state}
            ), mock.patch("socket.gethostname", return_value="different-device"):
                with self.assertRaises(module["DotError"]):
                    function(argparse.Namespace(
                        profile="kubuntu-laptop",
                        old_device="old-device",
                        new_device="new-device",
                    ))

    def test_device_rename_migrates_state_and_preserves_key_material(self):
        module = runpy.run_path(str(DOT))
        function = module["cmd_device_rename"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            state_dir = root / "state"
            home = root / "home"
            bootstrap_dir = state_dir / "bootstrap"
            config.mkdir()
            bootstrap_dir.mkdir(parents=True)
            home.mkdir()
            (config / "device.json").write_text(json.dumps({
                "schema_version": 1, "device_id": "old-device",
            }))
            state_path = bootstrap_dir / "kubuntu-laptop.json"
            state_path.write_text(json.dumps({
                "schema_version": 1,
                "profile": "kubuntu-laptop",
                "device": "old-device",
                "completed": ["identity"],
            }))
            item = {"id": "item-id", "name": "dotfiles/ssh/personal/old-device"}
            get_item = mock.Mock(side_effect=lambda name, *_args, **_kwargs: (
                dict(item) if name.endswith("/old-device") else None
            ))
            edit_item = mock.Mock(side_effect=lambda value, _session: dict(value))
            with mock.patch.object(Path, "home", return_value=home), \
                 mock.patch("socket.gethostname", return_value="new-device"), \
                 mock.patch.dict(function.__globals__, {
                     "CONFIG_DIR": config,
                     "STATE_DIR": state_dir,
                     "bw_session": mock.Mock(return_value=("session", False)),
                     "bw_get_item": get_item,
                     "bw_edit_item": edit_item,
                     "parse_bootstrap": mock.Mock(return_value={
                         "git_identities": {"personal": {
                             "name": "Dovie", "email": "dovie@example.com",
                         }}
                     }),
                     "key_parts": mock.Mock(return_value=("PRIVATE", "PUBLIC")),
                     "write_identity": mock.Mock(),
                     "write_finalization_handoff": mock.Mock(),
                     "run": mock.Mock(),
                 }):
                function(argparse.Namespace(
                    profile="kubuntu-laptop",
                    old_device="old-device",
                    new_device="new-device",
                ))
            self.assertEqual(
                json.loads((config / "device.json").read_text())["device_id"],
                "new-device",
            )
            self.assertEqual(json.loads(state_path.read_text())["device"], "new-device")
            self.assertEqual(
                (home / ".ssh/dotfiles-personal-new-device.pub").read_text(),
                "PUBLIC\n",
            )
            self.assertEqual(
                edit_item.call_args.args[0]["name"],
                "dotfiles/ssh/personal/new-device",
            )

    def test_codex_remote_control_tracks_desktop_core(self):
        service = (
            ROOT / "config/systemd/user/codex-remote-control.service"
        ).read_text()
        refresh_path = (
            ROOT / "config/systemd/user/codex-remote-control-refresh.path"
        ).read_text()
        refresh_service = (
            ROOT / "config/systemd/user/codex-remote-control-refresh.service"
        ).read_text()
        desktop_core = "/usr/lib/chatgpt/resources/codex"

        self.assertIn(f"ConditionFileIsExecutable={desktop_core}", service)
        self.assertIn(f"ExecStart={desktop_core} app-server", service)
        self.assertIn("TimeoutStopSec=15s", service)
        self.assertNotIn("%h/.local/bin/codex", service)
        self.assertIn(f"PathChanged={desktop_core}", refresh_path)
        self.assertIn(
            "Unit=codex-remote-control-refresh.service", refresh_path
        )
        self.assertIn(
            "--no-block try-restart codex-remote-control.service",
            refresh_service,
        )

        cli = DOT.read_text()
        self.assertIn('Path("/usr/lib/chatgpt/resources/codex")', cli)
        self.assertIn('"codex-remote-control-refresh.path"', cli)
        self.assertIn("Codex Remote Control version alignment", cli)

    def test_meshcentral_generated_command_is_parsed_without_shell_execution(self):
        module = runpy.run_path(str(DOT))
        parse = module["parse_meshcentral_install_command"]
        mesh_id = "a" * 31 + "@" + "b" * 31 + "$"
        command = (
            '(wget "https://mc.example.test/meshagents?script=1" '
            '-O ./meshinstall.sh || wget '
            '"https://mc.example.test/meshagents?script=1" '
            '-O ./meshinstall.sh --no-proxy) && '
            'chmod 755 ./meshinstall.sh && sudo -E ./meshinstall.sh '
            f"https://mc.example.test '{mesh_id}'"
        )
        self.assertEqual(
            parse(command),
            {
                "schema_version": 1,
                "server_url": "https://mc.example.test",
                "installer_url": "https://mc.example.test/meshagents?script=1",
                "mesh_id": mesh_id,
            },
        )

    def test_meshcentral_enrollment_rejects_insecure_or_cross_origin_urls(self):
        module = runpy.run_path(str(DOT))
        normalize = module["normalize_meshcentral_enrollment"]
        error = module["DotError"]
        baseline = {
            "schema_version": 1,
            "server_url": "https://mc.example.test",
            "installer_url": "https://mc.example.test/meshagents?script=1",
            "mesh_id": "a" * 64,
        }
        for changes in (
            {"server_url": "http://mc.example.test"},
            {"server_url": "https://mc.example.test/path"},
            {"installer_url": "https://evil.example/meshagents?script=1"},
            {"mesh_id": "a" * 63},
            {"mesh_id": "a" * 63 + "/"},
        ):
            with self.subTest(changes=changes), self.assertRaises(error):
                normalize({**baseline, **changes})

    def test_kubuntu_meshcentral_integration_is_explicit_and_documented(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        self.assertTrue(profile["features"]["meshcentral_agent"])
        self.assertIn(
            "tasks/meshcentral.yml",
            (ROOT / "ansible/local.yml").read_text(),
        )
        task = (ROOT / "ansible/tasks/meshcentral.yml").read_text()
        self.assertIn("meshagent.service", task)
        self.assertNotIn("mesh_id", task)
        docs = (ROOT / "docs/meshcentral.md").read_text()
        self.assertIn("dot meshcentral enroll", docs)
        self.assertIn("never evaluated by a shell", docs)
        self.assertIn("does not depend on Bitwarden", docs)
        cli = DOT.read_text()
        direct_enrollment = cli.split(
            'if action == "enroll":', 1
        )[1].split("else:", 1)[0]
        self.assertIn("getpass.getpass", direct_enrollment)
        self.assertNotIn("bw_session", direct_enrollment)
        self.assertIn('choices=["status", "enroll", "enroll-stored"]', cli)

    def test_bw_session_logs_in_when_cli_is_unauthenticated(self):
        module = runpy.run_path(str(DOT))
        bw_session = module["bw_session"]
        globals_ = bw_session.__globals__
        commands = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(
                command, 0, stdout='{"status":"unauthenticated"}\n', stderr=""
            )

        def fake_subprocess_run(command, **_kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(
                command, 0, stdout="fresh-session\n", stderr=""
            )

        with (
            mock.patch.dict(
                globals_,
                {
                    "run": fake_run,
                    "require_commands": lambda *_args, **_kwargs: None,
                },
            ),
            mock.patch.object(
                globals_["subprocess"], "run", side_effect=fake_subprocess_run
            ),
            mock.patch.dict(
                os.environ,
                {"BW_SESSION": "", "DOTFILES_BW_LOCK_AFTER_USE": ""},
            ),
        ):
            self.assertEqual(bw_session(), ("fresh-session", False))

        self.assertEqual(commands[-1], ["bw", "login", "--raw"])

    def test_bw_session_recovers_from_stale_cli_crypto_state(self):
        module = runpy.run_path(str(DOT))
        bw_session = module["bw_session"]
        globals_ = bw_session.__globals__
        regular_commands = []
        session_commands = []

        def fake_run(command, **_kwargs):
            regular_commands.append(command)
            if command == ["bw", "status"]:
                return subprocess.CompletedProcess(
                    command, 0, stdout='{"status":"locked"}\n', stderr=""
                )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        def fake_subprocess_run(command, **_kwargs):
            session_commands.append(command)
            if command[1] == "unlock":
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
            return subprocess.CompletedProcess(
                command, 0, stdout="recovered-session\n", stderr=""
            )

        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = True
        with (
            mock.patch.dict(
                globals_,
                {
                    "run": fake_run,
                    "require_commands": lambda *_args, **_kwargs: None,
                },
            ),
            mock.patch.object(
                globals_["subprocess"], "run", side_effect=fake_subprocess_run
            ),
            mock.patch.object(globals_["sys"], "stdin", fake_stdin),
            mock.patch("builtins.input", return_value="yes"),
            mock.patch.dict(
                os.environ,
                {"BW_SESSION": "", "DOTFILES_BW_LOCK_AFTER_USE": ""},
            ),
        ):
            self.assertEqual(bw_session(), ("recovered-session", False))

        self.assertEqual(
            session_commands,
            [["bw", "unlock", "--raw"], ["bw", "login", "--raw"]],
        )
        self.assertIn(["bw", "logout"], regular_commands)

    def test_bw_session_reuses_existing_in_process_session(self):
        module = runpy.run_path(str(DOT))
        bw_session = module["bw_session"]
        globals_ = bw_session.__globals__

        def fake_run(command, **_kwargs):
            return subprocess.CompletedProcess(
                command, 0, stdout='{"status":"unlocked"}\n', stderr=""
            )

        with (
            mock.patch.dict(
                globals_,
                {
                    "run": fake_run,
                    "require_commands": lambda *_args, **_kwargs: None,
                },
            ),
            mock.patch.object(globals_["subprocess"], "run") as process_run,
            mock.patch.dict(
                os.environ,
                {
                    "BW_SESSION": "existing-session",
                    "DOTFILES_BW_LOCK_AFTER_USE": "1",
                },
            ),
        ):
            self.assertEqual(bw_session(), ("existing-session", False))
            process_run.assert_not_called()

    def test_bw_session_can_lock_after_use_when_explicitly_requested(self):
        module = runpy.run_path(str(DOT))
        bw_session = module["bw_session"]
        globals_ = bw_session.__globals__
        status = subprocess.CompletedProcess(
            ["bw", "status"],
            0,
            stdout='{"status":"unauthenticated"}',
            stderr="",
        )
        with (
            mock.patch.dict(
                globals_,
                {
                    "run": mock.Mock(return_value=status),
                    "require_commands": lambda *_args, **_kwargs: None,
                    "_bw_capture_session": lambda _action: ("fresh-session", 0),
                },
            ),
            mock.patch.dict(
                os.environ,
                {"BW_SESSION": "", "DOTFILES_BW_LOCK_AFTER_USE": "1"},
            ),
        ):
            self.assertEqual(bw_session(), ("fresh-session", True))

    def test_profiles_are_parseable(self):
        for path in (ROOT / "profiles").glob("*.yml"):
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)

    def test_panel_profiles_are_complete_and_distinct(self):
        manifest = json.loads(
            (ROOT / "config/kde/panel-profiles.json").read_text()
        )
        self.assertEqual(manifest["default"], "windows-classic")
        self.assertEqual(
            list(manifest["profiles"]),
            [
                "windows-classic",
                "windows-refined",
                "centered-compact",
                "unified-pill",
            ],
        )
        profiles = manifest["profiles"]
        self.assertEqual(manifest["launcher_icon"], "windows11")
        self.assertEqual(
            manifest["launchers"],
            [
                "applications:google-chrome.desktop",
                "applications:com.mitchellh.ghostty.desktop",
                "applications:dot-obsidian.desktop",
            ],
        )
        self.assertEqual(
            manifest["tray"]["shown_items"],
            [
                "org.kde.plasma.networkmanagement",
                "org.kde.plasma.volume",
                "org.kde.plasma.battery",
            ],
        )
        self.assertIn(
            "Bitwarden_status_icon_1",
            manifest["tray"]["hidden_items"],
        )
        self.assertEqual(profiles["windows-refined"]["width_percent"], 94)
        self.assertEqual(profiles["centered-compact"]["width_percent"], 62)
        self.assertTrue(
            all(profile["task_manager"] == "icons" for profile in profiles.values())
        )
        self.assertEqual(profiles["unified-pill"]["length_mode"], "fit")
        self.assertFalse(profiles["unified-pill"]["spacers"])
        self.assertTrue(
            all("launcher_icon" not in profile for profile in profiles.values())
        )
        cli = DOT.read_text()
        self.assertIn('panel.lengthMode = cfg.length_mode', cli)
        self.assertIn('panel.floating = cfg.floating', cli)
        self.assertIn('icon: cfg.launcher_icon', cli)
        self.assertIn('"launchers": ",".join(manifest["launchers"])', cli)
        self.assertIn('sortingStrategy: "1"', cli)
        self.assertIn('showOnlyCurrentDesktop: "true"', cli)
        self.assertIn("if (liveLaunchers) launchers = liveLaunchers", cli)
        self.assertIn("def live_panel_launchers()", cli)
        self.assertNotIn('firstSpacer = panel.addWidget', cli)
        self.assertIn('ds[i].wallpaperPlugin = "org.kde.color"', cli)
        self.assertIn(
            '.dotfiles-never-show-desktop-icons',
            cli,
        )
        self.assertIn('return False, "widget order does not match"', cli)
        self.assertIn(
            'return False, "always-hidden tray icons do not match"',
            cli,
        )
        self.assertIn('"Save taskbar preferences"', cli)
        self.assertIn('"Check taskbar and System Tray"', cli)
        self.assertIn('panel_sub.add_parser("save")', cli)

    def test_panel_list_uses_classic_as_the_host_default(self):
        with tempfile.TemporaryDirectory() as directory:
            env = os.environ.copy()
            env["XDG_CONFIG_HOME"] = directory
            result = subprocess.run(
                [str(DOT), "panel", "list"],
                text=True,
                capture_output=True,
                env=env,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("* windows-classic", result.stdout)
        self.assertIn("windows-refined", result.stdout)
        self.assertIn("centered-compact", result.stdout)
        self.assertIn("unified-pill", result.stdout)

    def test_kde_normalization_ignores_runtime_shortcut_residue(self):
        normalize = runpy.run_path(str(DOT))["portable_kde_content"]
        tracked = b"""[kwin]\ndot-dolphin=Meta+E,none,Open Dolphin\nOther=Value\n\n[plasmashell]\nmanage activities=none,Meta+Q,Show Activity Switcher\nactivate widget 3=,none,Activate Launcher\n"""
        live = b"""[plasmashell]\nactivate widget 230=,none,Activate Launcher\nmanage activities=,Meta+Q,Show Activity Switcher\n\n[kwin]\nOther=Value\ndot-dolphin=Meta+E,none,Open Dolphin\n\n[services][com.mitchellh.ghostty.desktop]\n_launch=\n"""
        self.assertEqual(
            normalize(".config/kglobalshortcutsrc", tracked),
            normalize(".config/kglobalshortcutsrc", live),
        )

    def test_unknown_profile_is_actionable(self):
        result = self.run_dot("doctor", "--profile", "does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot read", result.stderr)

    def test_windows_profile_does_not_install(self):
        profile = json.loads((ROOT / "profiles/windows-host.yml").read_text())
        self.assertTrue(profile["features"]["windows_inventory_only"])

    def test_package_apply_explains_missing_noninteractive_sudo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "sudo").write_text("#!/bin/sh\nexit 1\n")
            (fake_bin / "ansible-playbook").write_text("#!/bin/sh\nexit 99\n")
            (fake_bin / "sudo").chmod(0o755)
            (fake_bin / "ansible-playbook").chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(root / "home")
            env["XDG_STATE_HOME"] = str(root / "state")
            env["PATH"] = os.pathsep.join(
                [str(fake_bin), "/home/linuxbrew/.linuxbrew/bin", "/usr/bin", "/bin"]
            )
            for profile, tag in (
                ("wsl-personal", "packages"),
                ("kubuntu-laptop", "clipboard"),
            ):
                with self.subTest(profile=profile, tag=tag):
                    result = subprocess.run(
                        [
                            str(DOT),
                            "apply",
                            "--profile",
                            profile,
                            "--tags",
                            tag,
                        ],
                        text=True,
                        capture_output=True,
                        env=env,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(
                        "Run this command in an interactive terminal",
                        result.stderr,
                    )

    def test_interactive_package_apply_asks_ansible_for_become_password(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            ansible_marker = root / "ansible-ran"
            ansible_args = root / "ansible-args"
            (fake_bin / "sudo-rs").write_text("#!/bin/sh\nexit 99\n")
            (fake_bin / "sudo").symlink_to(fake_bin / "sudo-rs")
            (fake_bin / "ansible-playbook").write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$@" > "$DOT_TEST_ANSIBLE_ARGS"\n'
                'touch "$DOT_TEST_ANSIBLE_MARKER"\n'
            )
            (fake_bin / "sudo-rs").chmod(0o755)
            (fake_bin / "ansible-playbook").chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(root / "home")
            env["XDG_STATE_HOME"] = str(root / "state")
            env["DOT_TEST_ANSIBLE_MARKER"] = str(ansible_marker)
            env["DOT_TEST_ANSIBLE_ARGS"] = str(ansible_args)
            env["PATH"] = os.pathsep.join(
                [str(fake_bin), "/home/linuxbrew/.linuxbrew/bin", "/usr/bin", "/bin"]
            )
            pid, fd = pty.fork()
            if pid == 0:
                os.execve(
                    str(DOT),
                    [
                        str(DOT),
                        "apply",
                        "--profile",
                        "wsl-personal",
                        "--tags",
                        "packages",
                    ],
                    env,
                )
            output = bytearray()
            while True:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
            _, status = os.waitpid(pid, 0)
            os.close(fd)
            self.assertEqual(os.waitstatus_to_exitcode(status), 0, output.decode(errors="replace"))
            self.assertTrue(ansible_marker.exists())
            arguments = ansible_args.read_text().splitlines()
            self.assertIn("--ask-become-pass", arguments)
            self.assertIn("sudo_rs", arguments)
            self.assertIn(b"Administrator access is required", output)

    def test_sudo_rs_become_plugin_matches_wrapped_prompt_prefix(self):
        plugin = (ROOT / "ansible/become_plugins/sudo_rs.py").read_text()
        self.assertIn('self.prompt = f"[sudo: {self.prompt}]"', plugin)
        self.assertIn('name = "sudo_rs"', plugin)
        dot = DOT.read_text()
        self.assertIn('Path("/usr/lib/cargo/bin/sudo")', dot)
        self.assertIn('["--become-method", "sudo_rs"]', dot)
        self.assertIn('apply_env["ANSIBLE_CONFIG"]', dot)
        config = (ROOT / "ansible/ansible.cfg").read_text()
        self.assertIn("become_plugins = become_plugins", config)
        self.assertNotIn("become_ask_pass", config)

    def test_codex_manifest_tracks_official_stable_channel(self):
        manifest = json.loads((ROOT / "packages/codex.yml").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["channel"], "stable")
        self.assertEqual(
            manifest["installer_url"],
            "https://chatgpt.com/codex/install.sh",
        )
        self.assertNotIn("release", manifest)
        self.assertNotIn("installer_sha256", manifest)

    def test_vite_plus_manifest_tracks_official_stable_channel(self):
        manifest = json.loads((ROOT / "packages/vite-plus.yml").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["channel"], "stable")
        self.assertEqual(manifest["installer_url"], "https://vite.plus")
        self.assertNotIn("release", manifest)
        self.assertNotIn("installer_sha256", manifest)

    def test_kubuntu_manages_chatgpt_desktop_from_openai_repository(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        role = (ROOT / "ansible/tasks/chatgpt.yml").read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        key = ROOT / "config/apt/chatgpt-archive-keyring.asc"
        source = ROOT / "config/apt/chatgpt.sources"

        self.assertTrue(profile["features"]["chatgpt_desktop"])
        self.assertIn("chatgpt", profile["packages"]["apt"])
        self.assertEqual(catalog["tools"]["chatgpt"]["provider"], "apt")
        self.assertIn("tasks/chatgpt.yml", playbook)
        self.assertIn(
            "https://persistent.oaistatic.com/codex-app-prod/linux/deb",
            source.read_text(),
        )
        self.assertIn("3BFA0E4AE8B8CC16A2D9BA684A3B4A566C4660E4", role)
        self.assertIn("state: latest", role)
        self.assertTrue(key.is_file())
        self.assertIn("BEGIN PGP PUBLIC KEY BLOCK", key.read_text())
        self.assertIn("Architectures: amd64", source.read_text())

    def test_kubuntu_and_wsl_own_native_docker_engine(self):
        for name in ("kubuntu-laptop", "wsl-personal", "wsl-work"):
            profile = json.loads((ROOT / f"profiles/{name}.yml").read_text())
            self.assertTrue(profile["features"]["docker_engine"])
        for name in ("wsl-personal", "wsl-work"):
            profile = json.loads((ROOT / f"profiles/{name}.yml").read_text())
            self.assertNotIn("docker", profile["packages"]["brew"])
            self.assertNotIn("docker-compose", profile["packages"]["brew"])

    def test_tailscale_runs_on_native_hosts_not_inside_wsl(self):
        kubuntu = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        windows = json.loads((ROOT / "profiles/windows-host.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        role = (ROOT / "ansible/tasks/tailscale.yml").read_text()
        local = (ROOT / "ansible/local.yml").read_text()
        systray = (
            ROOT / "config/tailscale/tailscale-systray.desktop"
        ).read_text()
        cli = DOT.read_text()
        git_config = (ROOT / "config/git/default.gitconfig").read_text()

        self.assertTrue(kubuntu["features"]["tailscale"])
        self.assertIn("tailscale", kubuntu["packages"]["apt"])
        self.assertIn("Tailscale.Tailscale", windows["packages"]["winget"])
        self.assertEqual(catalog["tools"]["tailscale"]["provider"], "apt")
        for name in ("wsl-personal", "wsl-work"):
            profile = json.loads((ROOT / f"profiles/{name}.yml").read_text())
            self.assertFalse(profile["features"].get("tailscale", False))
            self.assertNotIn("tailscale", profile["packages"]["apt"])

        self.assertIn("https://pkgs.tailscale.com/stable/ubuntu", role)
        self.assertIn("2596A99EAAB33821893C0A79458CA832957F5868", role)
        self.assertIn("state: latest", role)
        self.assertIn("name: tailscaled", role)
        self.assertIn("sudo tailscale up", role)
        self.assertIn("tailscale, get, operator", role)
        self.assertIn(
            'tailscale, set, "--operator={{ ansible_facts[\'user_id\'] }}"', role
        )
        portable_apply = local.split("- name: Apply portable configuration", 1)[1].split(
            "- name: Configure native application window frames", 1
        )[0]
        self.assertIn("- screenshots", portable_apply)
        self.assertIn("- tailscale", portable_apply)
        self.assertNotIn("auth-key", role)
        self.assertNotIn("tailscale up --authkey", role)
        self.assertIn("Exec=tailscale systray", systray)
        self.assertIn("OnlyShowIn=KDE;", systray)
        self.assertIn(
            'ROOT / "config/tailscale/tailscale-systray.desktop"', cli
        )
        self.assertIn(
            'Path.home() / ".config/autostart/tailscale-systray.desktop"',
            cli,
        )
        self.assertIn('"Tailscale enrollment"', cli)
        self.assertIn("editor = nvim", git_config)

    def test_nomachine_is_private_to_the_kubuntu_tailnet(self):
        kubuntu = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        local = (ROOT / "ansible/local.yml").read_text()
        task = (ROOT / "ansible/tasks/nomachine.yml").read_text()
        docs = (ROOT / "docs/nomachine.md").read_text()

        self.assertTrue(kubuntu["features"]["nomachine"])
        self.assertIn("tasks/nomachine.yml", local)
        self.assertIn("tailscale, ip, -4", task)
        self.assertIn("NoMachine was not installed", task)
        self.assertIn("failed_when: false", task)
        self.assertIn("NXDListenAddress", task)
        self.assertIn("NXUDPPort", task)
        self.assertIn("EnableLocalNetworkBroadcast", task)
        self.assertIn("EnableNetwork", task)
        self.assertIn("EnableUPnP", task)
        self.assertIn("sha256:", task)
        self.assertIn("nx://", task)
        self.assertIn("dot apply --profile kubuntu-laptop --tags nomachine", docs)

    def test_kubuntu_manages_ghostty_as_a_minimal_tmux_frontend(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        config = (ROOT / "config/ghostty/config").read_text()
        kdeglobals = (ROOT / "config/kde/.config/kdeglobals").read_text()
        cli = DOT.read_text()

        self.assertIn("ghostty", profile["packages"]["apt"])
        self.assertTrue(profile["features"]["firacode_nerd_font"])
        self.assertIn(
            'command = zsh -lic "exec tmux new-session -A -s main"',
            config,
        )
        self.assertIn("window-decoration = none", config)
        self.assertIn("window-show-tab-bar = never", config)
        self.assertIn("gtk-titlebar = false", config)
        self.assertIn("scrollbar = never", config)
        self.assertIn("maximize = true", config)
        self.assertIn("font-family = FiraCode Nerd Font Mono", config)
        self.assertIn("font-feature = -calt", config)
        self.assertIn("cursor-style = bar", config)
        self.assertIn("cursor-style-blink = false", config)
        self.assertIn("cursor-opacity = 1", config)
        self.assertIn("link-url = false", config)
        self.assertIn(
            "TerminalService=com.mitchellh.ghostty.desktop",
            kdeglobals,
        )
        self.assertIn("TerminalApplication=/usr/bin/ghostty", kdeglobals)
        self.assertIn(
            "font=Segoe UI Variable,9,-1,5,50,0,0,0,0,0",
            kdeglobals,
        )
        self.assertIn(
            "menuFont=Segoe UI Variable,9,-1,5,50,0,0,0,0,0",
            kdeglobals,
        )
        self.assertIn(
            "smallestReadableFont=Segoe UI Variable,8,-1,5,50,0,0,0,0,0",
            kdeglobals,
        )
        self.assertIn(
            "toolBarFont=Segoe UI Variable,9,-1,5,50,0,0,0,0,0",
            kdeglobals,
        )
        self.assertIn(
            "activeFont=Segoe UI Variable,9,-1,5,63,0,0,0,0,0",
            kdeglobals,
        )
        panel = (
            ROOT
            / "config/kde/.config/plasma-org.kde.plasma.desktop-appletsrc"
        ).read_text()
        self.assertIn(
            "launchers=applications:google-chrome.desktop,"
            "applications:com.mitchellh.ghostty.desktop,"
            "applications:dot-obsidian.desktop",
            panel,
        )
        self.assertNotIn("applications:org.kde.konsole.desktop", panel)
        self.assertIn('ROOT / "config/ghostty/config"', cli)
        self.assertIn(
            'ROOT / "config/environment.d/20-locale.conf"',
            cli,
        )
        self.assertIn(
            'ROOT / "config/environment.d/30-user-path.conf"',
            cli,
        )
        locale_environment = (
            ROOT / "config/environment.d/20-locale.conf"
        ).read_text()
        self.assertIn("LANG=en_US.UTF-8", locale_environment)
        self.assertIn("LC_TIME=en_US.UTF-8", locale_environment)
        user_path_environment = (
            ROOT / "config/environment.d/30-user-path.conf"
        ).read_text()
        self.assertIn("PATH=${HOME}/.vite-plus/bin:", user_path_environment)
        self.assertIn('"Ghostty configuration"', cli)
        self.assertIn('"terminal font"', cli)
        installer = (ROOT / "scripts/install-firacode-nerd-font").read_text()
        self.assertIn("releases/latest", installer)
        self.assertIn("FiraCode.tar.xz", installer)
        self.assertIn("SHA-256.txt", installer)
        self.assertNotIn("v3.", installer)

    def test_native_frame_updater_preserves_private_application_state(self):
        updater = ROOT / "scripts/configure-native-frames"
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            chrome = home / ".config/google-chrome/Default/Preferences"
            obsidian = home / ".config/obsidian/obsidian.json"
            chrome.parent.mkdir(parents=True)
            obsidian.parent.mkdir(parents=True)
            chrome.write_text(
                json.dumps(
                    {
                        "browser": {"custom_chrome_frame": True},
                        "private": {"account": "preserve-me"},
                    }
                )
            )
            obsidian.write_text(
                json.dumps(
                    {
                        "frame": "hidden",
                        "vaults": {"private-id": {"path": "/private/vault"}},
                    }
                )
            )
            environment = os.environ | {"HOME": str(home)}

            check = subprocess.run(
                [str(updater), "--check"],
                text=True,
                capture_output=True,
                env=environment,
            )
            self.assertEqual(check.returncode, 1)
            subprocess.run(
                [str(updater), "--ensure"],
                check=True,
                text=True,
                capture_output=True,
                env=environment,
            )

            chrome_data = json.loads(chrome.read_text())
            obsidian_data = json.loads(obsidian.read_text())
            self.assertIs(chrome_data["browser"]["custom_chrome_frame"], False)
            self.assertEqual(chrome_data["private"]["account"], "preserve-me")
            self.assertEqual(obsidian_data["frame"], "native")
            self.assertIs(obsidian_data["cli"], True)
            self.assertEqual(
                obsidian_data["vaults"]["private-id"]["path"],
                "/private/vault",
            )

    def test_docker_role_uses_official_native_engine_and_guards_wsl(self):
        role = (ROOT / "ansible/tasks/docker.yml").read_text()
        self.assertIn("https://download.docker.com/linux/ubuntu", role)
        self.assertIn("docker-ce", role)
        self.assertIn("docker-compose-plugin", role)
        self.assertIn("docker-buildx-plugin", role)
        self.assertIn("/run/systemd/system", role)
        self.assertIn("/mnt/wsl/docker-desktop/", role)
        self.assertIn("/var/run/docker.sock", role)
        self.assertIn("Docker Desktop WSL integration is active", role)
        self.assertIn("groups: docker", role)

    def test_docker_tag_requests_privilege_and_doctor_checks_runtime(self):
        text = DOT.read_text()
        self.assertIn(
            '"system-updates"',
            text,
        )
        self.assertIn('get("docker_engine", False)', text)
        self.assertIn('"Docker socket access"', text)
        self.assertIn('"WSL native Docker mode"', text)

    def test_external_debs_resolve_stable_github_assets(self):
        manifest = json.loads((ROOT / "packages/external-deb.yml").read_text())
        for package in manifest["packages"].values():
            self.assertEqual(package["channel"], "stable")
            self.assertIn("/", package["source"])
            self.assertTrue(package["asset_regex"].endswith(r"\.deb$"))
            self.assertNotIn("version", package)

    def test_kubuntu_manages_rustdesk_from_official_stable_releases(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        manifest = json.loads((ROOT / "packages/external-deb.yml").read_text())

        self.assertIn("rustdesk", profile["packages"]["deb"])
        self.assertEqual(
            manifest["packages"]["rustdesk"]["source"],
            "rustdesk/rustdesk",
        )
        self.assertEqual(manifest["packages"]["rustdesk"]["channel"], "stable")
        self.assertEqual(
            manifest["packages"]["rustdesk"]["asset_regex"],
            r"^rustdesk-[0-9.]+-x86_64\.deb$",
        )

    def test_kde_apply_refuses_uncaptured_local_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_home = Path(directory)
            config = fake_home / ".config"
            config.mkdir()
            shutil.copy2(ROOT / "config/kde/.config/kdeglobals", config / "kdeglobals")
            shortcuts = config / "kglobalshortcutsrc"
            shortcuts.write_text("[local-change]\nshortcut=Meta+S\n")
            env = os.environ.copy()
            env["HOME"] = str(fake_home)
            env["XDG_STATE_HOME"] = str(fake_home / ".local/state")
            result = subprocess.run(
                [
                    str(DOT),
                    "apply",
                    "--profile",
                    "kubuntu-laptop",
                    "--direct",
                ],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to overwrite KDE configuration drift", result.stderr)
            self.assertEqual(shortcuts.read_text(), "[local-change]\nshortcut=Meta+S\n")

    def test_linux_shell_profile_installs_dot_command(self):
        source = (ROOT / "bin/dot").resolve()
        text = DOT.read_text()
        self.assertIn('ROOT / "bin/dot": Path.home() / ".local/bin/dot"', text)
        self.assertTrue(source.is_file())

    def test_linux_shell_profile_installs_transcribe_command(self):
        source = ROOT / "config/transcription/transcribe"
        text = DOT.read_text()
        profile = json.loads((ROOT / "profiles/common-linux.yml").read_text())
        self.assertIn('transcribe_current.is_file()', text)
        self.assertIn('ROOT / "config/transcription/transcribe"', text)
        self.assertIn('Path.home() / ".local/bin/transcribe"', text)
        self.assertTrue(source.is_file())
        self.assertTrue(source.stat().st_mode & 0o111)
        self.assertIn("ffmpeg", profile["packages"]["apt"])
        self.assertIn("yt-dlp", profile["packages"]["brew"])

    def test_transcribe_installer_is_managed_by_dot(self):
        installer = ROOT / "scripts/install-transcribe"
        self.assertTrue(installer.stat().st_mode & 0o111)
        installer_text = installer.read_text()
        self.assertIn("DovieW/transcribe-cli", installer_text)
        self.assertIn('VERSION="2.0.0"', installer_text)
        self.assertIn("EXPECTED_SHA256", installer_text)
        self.assertIn("sha256sum --check", installer_text)
        self.assertNotIn("npm", installer_text)
        self.assertEqual(
            [path.name for path in (ROOT / "config/transcription").iterdir()],
            ["transcribe"],
        )
        cli = DOT.read_text()
        self.assertIn("def cmd_transcribe_install", cli)
        self.assertIn("def cmd_transcribe_update", cli)
        self.assertIn('sub.add_parser("transcribe")', cli)
        self.assertIn(
            '"transcribe",\n            transcribe_check.returncode == 0',
            cli,
        )

    def test_kde_diff_uses_delta_interactively(self):
        text = DOT.read_text()
        self.assertIn('["delta", "--paging=always"]', text)
        self.assertIn("sys.stdout.isatty()", text)

    def test_fzf_save_covers_preferences_and_shortcuts(self):
        text = DOT.read_text()
        self.assertIn('".config/spectaclerc"', text)
        self.assertIn('".config/kglobalshortcutsrc"', text)
        self.assertIn('"panel": {', text)
        self.assertIn('"Panel geometry and visibility"', text)
        self.assertIn('"Settings to save › "', text)
        self.assertIn('"Save, validate, commit, and push"', text)
        self.assertIn('"Capture selected KDE files"', text)
        self.assertIn("palette_kde_files", text)

    def test_update_orchestrates_every_native_provider(self):
        cli = DOT.read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        help_result = self.run_dot("update", "--help")

        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("--system", help_result.stdout)
        self.assertIn("--apps", help_result.stdout)
        self.assertIn("--check", help_result.stdout)
        self.assertNotIn("--profile PROFILE is required", help_result.stdout)
        self.assertIn("upgrade: dist", playbook)
        self.assertIn("Refresh every installed Snap", playbook)
        self.assertIn("Upgrade all installed Homebrew formulae", playbook)
        self.assertIn("tags: [packages, app-updates]", playbook)
        self.assertIn("active_package_transactions", cli)
        self.assertIn('"linux": "kubuntu-laptop"', cli)
        self.assertIn('"Update everything"', cli)
        self.assertIn('"Check for pending updates"', cli)
        self.assertIn("update_nvim_tools()", cli)
        self.assertIn("ThreadPoolExecutor", cli)
        self.assertIn("for future in as_completed(submitted)", cli)
        self.assertIn("results appear as they finish", cli)
        self.assertIn("{update.installed} -> {update.available}", cli)
        self.assertIn('"--json=v2"', cli)
        self.assertIn("check_nvim_updates", cli)
        self.assertIn("check_codex_updates", cli)
        self.assertIn("check_vite_plus_updates", cli)
        self.assertIn("[config, shell, tmux, app-updates]", playbook)

    def test_codex_permissions_are_managed_without_replacing_other_config(self):
        script = ROOT / "scripts/configure-codex"
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('model = "gpt-5.6-terra"\n\n[plugins]\nenabled = true\n')
            environment = os.environ.copy()
            environment["CODEX_CONFIG_FILE"] = str(config)
            applied = subprocess.run(
                [str(script)], text=True, capture_output=True, env=environment
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            text = config.read_text()
            self.assertIn('default_permissions = ":danger-full-access"', text)
            self.assertIn('approval_policy = "never"', text)
            self.assertIn('model = "gpt-5.6-terra"', text)
            self.assertIn("[plugins]\nenabled = true", text)
            checked = subprocess.run(
                [str(script), "--check"], text=True, capture_output=True, env=environment
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_update_metadata_preserves_installed_and_available_versions(self):
        module = runpy.run_path(str(DOT))

        apt_updates = module["parse_apt_updates"](
            "Inst curl [8.5.0-2ubuntu10.6] "
            "(8.5.0-2ubuntu10.8 Ubuntu:26.04/update [amd64])\n"
        )
        self.assertEqual(len(apt_updates), 1)
        self.assertEqual(apt_updates[0].name, "curl")
        self.assertEqual(apt_updates[0].installed, "8.5.0-2ubuntu10.6")
        self.assertEqual(apt_updates[0].available, "8.5.0-2ubuntu10.8")

        brew_updates = module["parse_brew_updates"](
            json.dumps(
                {
                    "formulae": [
                        {
                            "name": "fzf",
                            "installed_versions": ["0.61.1"],
                            "current_version": "0.62.0",
                        }
                    ]
                }
            )
        )
        self.assertEqual(len(brew_updates), 1)
        self.assertEqual(brew_updates[0].installed, "0.61.1")
        self.assertEqual(brew_updates[0].available, "0.62.0")

    def test_palette_uses_described_columns_and_exposes_every_workflow(self):
        text = DOT.read_text()
        self.assertIn('with_nth="2,3"', text)
        self.assertIn("DESCRIPTION  ·  {header}", text)
        for label in (
            "Update",
            "Apply and repair",
            "Save and configuration",
            "Neovim",
            "Repositories and packages",
            "Network and services",
            "Diagnostics",
            "Bootstrap and secrets",
            "Switch active profile",
        ):
            self.assertIn(f'"{label}"', text)
        for action in (
            "Update Neovim language tools",
            "Update Tmux plugins",
            "Add a package",
            "Sync managed repositories",
            "Install or repair Tailscale",
            "Sync secrets without GitHub",
            "Restore a configuration backup",
            "Rollback plugins",
        ):
            self.assertIn(f'"{action}"', text)

    def test_palette_renders_description_column_and_can_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            menu_log = root / "menu.log"
            args_log = root / "args.log"
            fake_fzf = fake_bin / "fzf"
            fake_fzf.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$@" > "$DOT_TEST_FZF_ARGS"\n'
                'rows="$(mktemp)"\n'
                'trap \'rm -f "$rows"\' EXIT\n'
                'tee "$DOT_TEST_FZF_LOG" > "$rows"\n'
                "awk -F '\\t' '$1 == \"exit\" { print; found=1; exit } "
                "END { if (!found) exit 1 }' \"$rows\"\n"
            )
            fake_fzf.chmod(0o755)
            env = os.environ.copy()
            env["HOME"] = str(root / "home")
            env["XDG_CONFIG_HOME"] = str(root / "config")
            env["XDG_STATE_HOME"] = str(root / "state")
            env["DOT_TEST_FZF_LOG"] = str(menu_log)
            env["DOT_TEST_FZF_ARGS"] = str(args_log)
            env["PATH"] = os.pathsep.join(
                [
                    str(fake_bin),
                    "/home/linuxbrew/.linuxbrew/bin",
                    "/usr/bin",
                    "/bin",
                ]
            )
            pid, fd = pty.fork()
            if pid == 0:
                os.execve(str(DOT), [str(DOT)], env)
            output = bytearray()
            while True:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                output.extend(chunk)
            _, status = os.waitpid(pid, 0)
            os.close(fd)
            self.assertEqual(
                os.waitstatus_to_exitcode(status),
                0,
                output.decode(errors="replace"),
            )
            rows = menu_log.read_text()
            self.assertIn("exit\tExit", rows)
            self.assertIn("Close the dot command palette", rows)
            self.assertIn("--with-nth=2,3", args_log.read_text())

    def test_native_plasma_panel_and_application_palette_are_managed(self):
        cli = DOT.read_text()
        panel = (ROOT / "config/kde/.config/plasma-org.kde.plasma.desktop-appletsrc").read_text()
        geometry = (ROOT / "config/kde/.config/plasmashellrc").read_text()
        runners = (ROOT / "config/kde/.config/krunnerrc").read_text()
        shortcuts = (ROOT / "config/kde/.config/kglobalshortcutsrc").read_text()
        kwin = (ROOT / "config/kde/.config/kwinrc").read_text()
        kdeglobals = (ROOT / "config/kde/.config/kdeglobals").read_text()
        input_config = (ROOT / "config/kde/.config/kcminputrc").read_text()
        launch_feedback = (ROOT / "config/kde/.config/klaunchrc").read_text()
        lock_screen = (ROOT / "config/kde/.config/kscreenlockerrc").read_text()
        plasma_pa = (ROOT / "config/kde/.config/plasmaparc").read_text()
        plasma_notify = (
            ROOT / "config/kde/.config/plasmanotifyrc"
        ).read_text()
        colors = (ROOT / "config/kde/GitHubDark.colors").read_text()

        self.assertIn("plugin=org.kde.plasma.icontasks", panel)
        self.assertNotIn("plugin=org.kde.plasma.taskmanager", panel)
        self.assertIn("plugin=org.kde.desktopcontainment", panel)
        self.assertIn("wallpaperplugin=org.kde.color", panel)
        self.assertIn("Color=0,0,0", panel)
        self.assertIn("PopupPosition=BottomRight", plasma_notify)
        self.assertIn('".config/plasmanotifyrc",', cli)
        self.assertIn('".config/klaunchrc",', cli)
        self.assertIn("BusyCursor=false", launch_feedback)
        self.assertIn("TaskbarButton=true", launch_feedback)
        self.assertIn(
            "Notification position is held by a process-wide Plasma singleton",
            cli,
        )
        self.assertNotIn("[Containments][1][Wallpaper][org.kde.image]", panel)
        self.assertNotIn("plugin=org.kde.plasma.folder", panel)
        self.assertEqual(panel.count("plugin=org.kde.plasma.panelspacer"), 1)
        self.assertEqual(panel.count("plugin=org.kde.plasma.kickoff"), 1)
        self.assertNotIn("plugin=org.kde.plasma.pager", panel)
        self.assertNotIn("plugin=org.kde.plasma.showdesktop", panel)
        self.assertIn("AppletOrder=3;5;29;7;22", panel)
        self.assertIn("middleClickAction=Close", panel)
        self.assertIn("onlyGroupWhenFull=false", panel)
        self.assertIn("separateLaunchers=true", panel)
        self.assertIn("showOnlyCurrentDesktop=true", panel)
        self.assertIn("sortingStrategy=1", panel)
        self.assertIn("panelLengthMode=0", geometry)
        self.assertIn("panelVisibility=1", geometry)
        self.assertIn("thickness=40", geometry)

        enabled = [
            line
            for line in runners.splitlines()
            if line.endswith("Enabled=true")
        ]
        self.assertEqual(enabled, ["krunner_servicesEnabled=true"])
        self.assertIn("FreeFloating=true", runners)
        self.assertIn("_launch=Alt+Space\\tAlt+F2", shortcuts)
        self.assertIn("activate application launcher=Meta\\tAlt+F1", shortcuts)
        self.assertIn("Show Desktop=Meta+D", shortcuts)
        self.assertIn("Window Close=Meta+Q\\tAlt+F4", shortcuts)
        self.assertIn("Window Maximize=Meta+Up\\tMeta+PgUp", shortcuts)
        self.assertIn("Window Quick Tile Top=,Meta+Up", shortcuts)
        self.assertIn("Overview=Meta+Tab\\tMeta+W", shortcuts)
        self.assertIn("Walk Through Windows=Alt+Tab", shortcuts)
        self.assertIn("Walk Through Windows (Reverse)=Alt+Shift+Tab", shortcuts)
        self.assertIn(
            "_launch=Ctrl+Shift+Esc,none,System Monitor",
            shortcuts,
        )
        self.assertIn("manage activities=none,Meta+Q", shortcuts)
        self.assertIn("sync_managed_kglobal_shortcuts()", cli)
        self.assertIn("org.kde.KGlobalAccel.setShortcut", cli)
        self.assertIn('"manage activities"', cli)
        self.assertIn('"Window Close"', cli)
        self.assertIn('"Window Maximize"', cli)
        self.assertIn('"Window Quick Tile Top"', cli)
        self.assertIn('"Overview"', cli)
        self.assertIn('"Walk Through Windows"', cli)
        self.assertIn('"org.kde.plasma-systemmonitor.desktop"', cli)
        self.assertIn("117440512", cli)
        self.assertIn("screenedgeEnabled=false", kwin)
        self.assertIn("shakecursorEnabled=false", kwin)
        self.assertIn("hidecursorEnabled=true", kwin)
        self.assertIn("[Effect-hidecursor]", kwin)
        self.assertIn("HideOnTyping=true", kwin)
        self.assertIn("InactivityDuration=1", kwin)
        self.assertIn("[TabBox]", kwin)
        self.assertIn("HighlightWindows=false", kwin)
        self.assertIn("LayoutName=io.github.doview.dotfiles.large-list", kwin)
        self.assertIn("ShowOutline=false", kwin)
        self.assertIn("ShowTabBox=true", kwin)
        self.assertIn('"Alt+Tab task switcher"', cli)
        switcher = ROOT / "config/kwin/tabbox-large-list"
        metadata = json.loads((switcher / "metadata.json").read_text())
        switcher_qml = (switcher / "contents/ui/main.qml").read_text()
        self.assertEqual(
            metadata["KPlugin"]["Id"],
            "io.github.doview.dotfiles.large-list",
        )
        self.assertIn("screenGeometry.width * 0.32", switcher_qml)
        self.assertIn("iconSizes.medium", switcher_qml)
        self.assertIn("font.pointSize", switcher_qml)
        self.assertIn("config/kwin/tabbox-large-list/metadata.json", cli)
        self.assertIn("task_switcher_destination", cli)
        self.assertIn("[org.kde.kdecoration2]", kwin)
        self.assertIn("ButtonsOnLeft=\n", kwin)
        self.assertIn("ButtonsOnRight=IAX", kwin)
        self.assertIn("BorderlessMaximizedWindows=true", kwin)
        self.assertIn("KWIN_ENABLED_EFFECTS", cli)
        self.assertIn('"hidecursor"', cli)
        self.assertIn('"window frames"', cli)
        self.assertIn('"native application frames"', cli)
        self.assertIn("configure-native-frames", cli)
        self.assertIn('"pointer auto-hide"', cli)
        self.assertIn("Name_1=General", kwin)
        self.assertIn("Name_2=Money", kwin)
        self.assertIn("desktopchangeosdEnabled=true", kwin)
        self.assertIn("[Script-desktopchangeosd]", kwin)
        self.assertIn("PopupHideDelay=200", kwin)
        self.assertIn("AnimationDurationFactor=0", kdeglobals)
        for effect in (
            "blendchanges",
            "fade",
            "fadedesktop",
            "fadingpopups",
            "fullscreen",
            "glide",
            "magiclamp",
            "maximize",
            "scale",
            "sheet",
            "slide",
            "slideback",
            "slidingpopups",
            "squash",
            "translucency",
            "windowaperture",
            "wobblywindows",
        ):
            self.assertIn(f"{effect}Enabled=false", kwin)
        self.assertIn("ElectricBorderDelay=0", kwin)
        self.assertIn("ElectricBorderCooldown=50", kwin)
        self.assertIn("[Greeter][LnF]\nshowMediaControls=false", lock_screen)
        self.assertIn("FillMode=2", lock_screen)
        self.assertNotIn("leaves_wallpaper", lock_screen)
        self.assertIn('"lock-screen media controls"', cli)
        self.assertIn('"lock-screen theme"', cli)
        self.assertIn('"lock-screen wallpaper"', cli)
        self.assertIn("LOCKSCREEN_PACKAGE_ID", cli)
        self.assertIn('"lockscreen-preview"', cli)
        self.assertIn('"lockscreen-apply"', cli)
        self.assertIn('"lockscreen-stock"', cli)
        self.assertIn("repos/files/leaves_wallpaper.jpg", cli)
        self.assertIn(
            ".local/share/wallpapers/dotfiles/leaves_wallpaper.jpg",
            cli,
        )
        self.assertIn(
            '("Greeter][Wallpaper][org.kde.image][General", "Image")',
            cli,
        )
        shell_state = (
            ROOT / "config/kde/.config/plasmashellrc"
        ).read_text()
        self.assertIn(
            "ShellPackage=io.github.doview.dotfiles.lockscreen",
            shell_state,
        )
        lock_package = (
            ROOT
            / "config/plasma/shells/io.github.doview.dotfiles.lockscreen"
        )
        metadata = json.loads((lock_package / "metadata.json").read_text())
        lock_qml = (
            lock_package / "contents/lockscreen/LockScreen.qml"
        ).read_text()
        self.assertEqual(metadata["KPackageStructure"], "Plasma/Shell")
        self.assertEqual(metadata["X-Plasma-APIVersion"], "2")
        self.assertEqual(
            metadata["X-Plasma-FallbackPackage"],
            "org.kde.plasma.desktop",
        )
        self.assertNotIn("MediaControls", lock_qml)
        self.assertIn("Segoe UI Variable", lock_qml)
        self.assertIn('displayName: "Dovie Weinstock"', lock_qml)
        self.assertIn("PasswordState.password", lock_qml)
        self.assertIn("Keyboards.KWinVirtualKeyboard", lock_qml)
        self.assertIn("PlasmaNM.ConnectionIcon", lock_qml)
        self.assertIn(
            "(Window.window && Window.window.active) || interaction.containsMouse",
            lock_qml,
        )
        self.assertNotIn("Fingerprint", lock_qml)
        self.assertNotIn("unlockButton", lock_qml)
        self.assertNotIn("go-next-symbolic", lock_qml)
        self.assertIn("entranceFade.start();", lock_qml)
        self.assertIn('displayName: "Dovie Weinstock"', lock_qml)
        self.assertIn('selectionColor: "#55ffffff"', lock_qml)
        self.assertIn('Qt.formatTime(clockSource.dateTime, "h:mm AP")', lock_qml)
        self.assertIn("Layout.preferredHeight: 48", lock_qml)
        self.assertIn("graceLockTimer.restart();", lock_qml)
        self.assertIn("id: graceLockTimer", lock_qml)
        self.assertIn("authenticator.startAuthenticating();", lock_qml)
        self.assertIn('property string queuedPassword: ""', lock_qml)
        self.assertIn("root.queuedPassword = text;", lock_qml)
        self.assertIn("authenticator.respond(password);", lock_qml)
        self.assertNotIn("enabled: !authenticator.graceLocked", lock_qml)
        self.assertIn("property bool keyboardRevealArmed: false", lock_qml)
        self.assertIn("id: initialShortcutGuard", lock_qml)
        self.assertIn("interaction.showLogin();", lock_qml)
        self.assertIn("initialShortcutGuard.start();", lock_qml)
        self.assertIn(
            "Component.onCompleted: {\n"
            "        entranceFade.start();\n"
            "        interaction.forceActiveFocus();\n"
            "        initialShortcutGuard.start();\n"
            "    }",
            lock_qml,
        )

        native_frames = (ROOT / "scripts/configure-native-frames").read_text()
        self.assertIn('"custom_chrome_frame"', native_frames)
        self.assertIn('data["frame"] = "native"', native_frames)
        self.assertIn('data["cli"] = True', native_frames)
        self.assertIn("Configure native application window frames", (ROOT / "ansible/local.yml").read_text())

        self.assertIn("ColorScheme=GitHubDark", kdeglobals)
        self.assertIn("LookAndFeelPackage=org.kde.breezedark.desktop", kdeglobals)
        self.assertIn("BackgroundNormal=13,17,23", colors)
        self.assertIn("PointerAccelerationProfile=1", input_config)
        self.assertIn("ScrollFactor=0.1", input_config)
        self.assertIn("DisableWhileTyping=false", input_config)
        self.assertIn("[Mouse]\ncursorSize=32\ncursorTheme=Breeze_Light", input_config)
        self.assertIn('"plasma-apply-cursortheme"', cli)
        self.assertIn('"Breeze_Light"', cli)
        self.assertIn("AudioFeedback=false", plasma_pa)
        self.assertIn('".config/plasmaparc"', cli)
        self.assertIn('"Updates", "PlasmaViews][Panel 2][Defaults"', cli)
        self.assertIn("plasma_evaluate(panel_profile_script(selected_panel))", cli)
        self.assertIn('"systemctl", "--user", "restart", "plasma-krunner.service"', cli)
        self.assertIn('"qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"', cli)
        self.assertIn('"org.kde.kwin.Effects.unloadEffect"', cli)
        self.assertIn("restore_backup(backup_run_id)", cli)
        self.assertIn('"Plasma panel layout"', cli)
        self.assertIn('"Plasma panel reveal"', cli)
        self.assertIn('"KRunner application palette"', cli)

    def test_meta_e_uses_one_taskbar_hidden_dolphin_window(self):
        cli = DOT.read_text()
        shortcuts = (
            ROOT / "config/kde/.config/kglobalshortcutsrc"
        ).read_text()
        kwin = (ROOT / "config/kde/.config/kwinrc").read_text()
        rules = (ROOT / "config/kde/.config/kwinrulesrc").read_text()
        script = (
            ROOT / "config/kwin/dot-dolphin/contents/code/main.js"
        ).read_text()
        service = (
            ROOT / "config/systemd/user/dot-dolphin-launch.service"
        ).read_text()
        metadata = (
            ROOT / "config/kwin/dot-dolphin/metadata.json"
        ).read_text()

        self.assertIn("dot-dolphinEnabled=true", kwin)
        self.assertIn("dot-dolphin=Meta+E", shortcuts)
        self.assertIn("_launch=none,Meta+E,Dolphin", shortcuts)
        self.assertIn("wmclass=org.kde.dolphin", rules)
        self.assertIn("wmclassmatch=1", rules)
        dolphin_rule = rules.split("[dolphin-skip-taskbar]", 1)[1].split(
            "[emoji-selector-ephemeral]", 1
        )[0]
        self.assertIn("skippager=true", dolphin_rule)
        self.assertIn("skippagerrule=2", dolphin_rule)
        self.assertIn("skipswitcher=true", dolphin_rule)
        self.assertIn("skipswitcherrule=2", dolphin_rule)
        self.assertIn("skiptaskbar=true", rules)
        self.assertIn("skiptaskbarrule=2", rules)
        self.assertIn(
            "rules=dolphin-skip-taskbar,emoji-selector-ephemeral,"
            "emoji-picker-ephemeral,copyq-ephemeral,flameshot-ephemeral,"
            "ghostty-all-desktops,system-settings-ephemeral,"
            "bitwarden-ephemeral,system-monitor-ephemeral",
            rules,
        )
        self.assertIn("[emoji-selector-ephemeral]", rules)
        self.assertIn("wmclass=org.kde.plasma.emojier", rules)
        self.assertIn("skippager=true", rules)
        self.assertIn("skippagerrule=2", rules)
        self.assertIn("skipswitcher=true", rules)
        self.assertIn("skipswitcherrule=2", rules)
        self.assertIn("[emoji-picker-ephemeral]", rules)
        self.assertIn("wmclass=emoji-picker", rules)
        self.assertIn("[copyq-ephemeral]", rules)
        self.assertIn("wmclass=com.github.hluk.copyq", rules)
        self.assertIn("[flameshot-ephemeral]", rules)
        self.assertIn("wmclass=flameshot", rules)
        self.assertIn("[ghostty-all-desktops]", rules)
        self.assertIn("wmclass=com.mitchellh.ghostty", rules)
        self.assertIn("desktops=\n", rules)
        self.assertIn("desktopsrule=2", rules)
        self.assertIn("[system-settings-ephemeral]", rules)
        self.assertIn("wmclass=systemsettings", rules)
        self.assertIn("[bitwarden-ephemeral]", rules)
        self.assertIn("wmclass=bitwarden", rules)
        self.assertIn("[system-monitor-ephemeral]", rules)
        self.assertIn("wmclass=org.kde.plasma-systemmonitor", rules)
        self.assertIn("workspace.stackingOrder", script)
        self.assertIn("workspace.activeWindow = window", script)
        self.assertIn("dot-dolphin-launch.service", script)
        self.assertIn("registerShortcut(", script)
        self.assertIn('"KPackageStructure": "KWin/Script"', metadata)
        self.assertIn("ExecStart=/usr/bin/dolphin", service)
        self.assertIn('".config/kwinrulesrc"', cli)
        self.assertIn('"config/kwin/dot-dolphin/metadata.json"', cli)
        self.assertIn('"config/kwin/dot-dolphin/contents/code/main.js"', cli)
        self.assertIn('"systemctl", "--user", "daemon-reload"', cli)
        self.assertIn('"Dolphin singleton shortcut"', cli)
        self.assertIn('"Dolphin taskbar rule"', cli)

    def test_obsidian_launcher_is_desktop_aware(self):
        cli = DOT.read_text()
        kwin = (ROOT / "config/kde/.config/kwinrc").read_text()
        script = (
            ROOT / "config/kwin/dot-obsidian/contents/code/main.js"
        ).read_text()
        launcher = (ROOT / "config/obsidian/dot-obsidian.desktop").read_text()
        mime_launcher = (ROOT / "config/obsidian/obsidian.desktop").read_text()
        service = (
            ROOT / "config/systemd/user/dot-obsidian-launch.service"
        ).read_text()

        self.assertIn("dot-obsidianEnabled=true", kwin)
        self.assertIn('window.desktopFileName === "obsidian"', script)
        self.assertIn("isOnDesktop(windows[index], desktop)", script)
        self.assertIn("window.desktops = [requestedDesktop]", script)
        self.assertIn("window.skipTaskbar = true", script)
        self.assertIn("workspace.activeWindow = window", script)
        self.assertIn("dot-obsidian-launch.service", script)
        self.assertIn('"dot-obsidian"', script)
        self.assertIn("org.kde.kglobalaccel.Component.invokeShortcut dot-obsidian", launcher)
        self.assertIn("StartupWMClass=dot-obsidian-launcher", launcher)
        self.assertIn(
            "Exec=/home/dovie/.local/bin/obsidian %U",
            mime_launcher,
        )
        self.assertIn(
            "Environment=SSH_AUTH_SOCK=%h/.bitwarden-ssh-agent.sock",
            service,
        )
        self.assertIn(
            "obsidian-cli command id=workspace:open-in-new-window", service
        )
        self.assertIn('"config/kwin/dot-obsidian/metadata.json"', cli)
        self.assertIn('"config/obsidian/dot-obsidian.desktop"', cli)
        self.assertIn('"config/obsidian/obsidian.desktop"', cli)
        self.assertIn(
            '".local/share/applications/md.obsidian.Obsidian.desktop"',
            cli,
        )
        self.assertIn('"Obsidian desktop-aware launcher"', cli)

    def test_alt_meta_arrows_move_active_window_and_follow_desktop(self):
        cli = DOT.read_text()
        kwin = (ROOT / "config/kde/.config/kwinrc").read_text()
        shortcuts = (
            ROOT / "config/kde/.config/kglobalshortcutsrc"
        ).read_text()
        script = (
            ROOT / "config/kwin/dot-window-desktop/contents/code/main.js"
        ).read_text()

        self.assertIn("dot-window-desktopEnabled=true", kwin)
        self.assertIn(
            "dot-window-desktop-left=Meta+Alt+Left",
            shortcuts,
        )
        self.assertIn(
            "dot-window-desktop-right=Meta+Alt+Right",
            shortcuts,
        )
        self.assertIn(
            "Switch Window Left=,Meta+Alt+Left",
            shortcuts,
        )
        self.assertIn(
            "Switch Window Right=,Meta+Alt+Right",
            shortcuts,
        )
        self.assertIn("window.desktops = [targetDesktop]", script)
        self.assertIn("workspace.currentDesktop = targetDesktop", script)
        self.assertIn("workspace.activeWindow = window", script)
        self.assertIn('if (!window || window.onAllDesktops)', script)
        self.assertIn('"dot-window-desktop-left"', script)
        self.assertIn('"dot-window-desktop-right"', script)
        self.assertIn('"config/kwin/dot-window-desktop/metadata.json"', cli)
        self.assertIn('"move window and follow shortcuts"', cli)

    def test_kubuntu_manages_windows_style_touchpad_gestures(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        manifest = json.loads((ROOT / "packages/inputactions.yml").read_text())
        gestures = (ROOT / "config/inputactions/config.yaml").read_text()
        desktop_adapter = (
            ROOT / "config/inputactions/dot-show-desktop"
        ).read_text()
        kwin = (ROOT / "config/kde/.config/kwinrc").read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        cli = DOT.read_text()
        builder = (ROOT / "scripts/build-inputactions").read_text()

        self.assertTrue(profile["features"]["inputactions"])
        self.assertEqual(manifest["channel"], "stable")
        self.assertNotIn("version", manifest)
        self.assertIn("latest_stable_tag", builder)
        self.assertIn("kwin_package_version", builder)
        self.assertIn("InputActions rebuilt from latest stable releases", builder)
        self.assertIn("tasks/inputactions.yml", playbook)
        self.assertIn("org.kde.kwin.Effects.loadEffect", playbook)
        self.assertIn("Apply the managed InputActions gesture configuration", playbook)
        self.assertIn("kwriteconfig6", playbook)
        self.assertNotIn(
            "tags: [config, shell, git, kde, tmux, gestures]",
            playbook,
        )
        self.assertIn("kwin_gesturesEnabled=true", kwin)
        self.assertIn("fingers: 3", gestures)
        self.assertIn("fingers: 4", gestures)
        self.assertRegex(
            gestures,
            r"(?s)fingers: 3\n\s+direction: up\n"
            r"\s+accelerated: true.*?interval: 10.*?keyboard: "
            r"\[volumeup\].*?fingers: 3\n\s+direction: down\n"
            r"\s+accelerated: true.*?interval: 10.*?keyboard: \[volumedown\]",
        )
        self.assertIn("plasma_shortcut: kwin,Walk Through Windows", gestures)
        self.assertRegex(
            gestures,
            r"(?s)fingers: 4\n\s+direction: left.*?"
            r"Switch One Desktop to the Left",
        )
        self.assertRegex(
            gestures,
            r"(?s)fingers: 4\n\s+direction: right.*?"
            r"Switch One Desktop to the Right",
        )
        self.assertIn(
            "command: $HOME/.local/bin/dot-show-desktop show",
            gestures,
        )
        self.assertIn(
            "command: $HOME/.local/bin/dot-show-desktop hide",
            gestures,
        )
        self.assertNotIn("plasma_shortcut: kwin,Show Desktop", gestures)
        self.assertIn("org.kde.kglobalaccel.Component.invokeShortcut", desktop_adapter)
        self.assertIn('"Show Desktop"', desktop_adapter)
        self.assertIn("org.freedesktop.DBus.Properties.Get", desktop_adapter)
        self.assertIn("dot-show-desktop", playbook)
        self.assertIn("dot-show-desktop", cli)
        self.assertIn("Backspace+Space+Enter", gestures)
        self.assertIn("def cmd_gestures", cli)
        self.assertIn('"InputActions KWin effect"', cli)
        self.assertIn('"services][org.kde.krunner.desktop"', cli)
        self.assertIn('"services][com.mitchellh.ghostty.desktop"', cli)
        self.assertIn('"gestures"', cli)

    def test_kubuntu_scopes_touchpad_jump_workaround(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        playbook = (ROOT / "ansible/local.yml").read_text()
        tasks = (ROOT / "ansible/tasks/touchpad.yml").read_text()
        quirk = (
            ROOT / "config/libinput/local-overrides.quirks"
        ).read_text()
        cli = DOT.read_text()

        self.assertTrue(profile["features"]["touchpad_jump_workaround"])
        self.assertIn("tasks/touchpad.yml", playbook)
        self.assertIn("libinput-tools", tasks)
        self.assertIn("quirks", tasks)
        self.assertIn("validate", tasks)
        self.assertIn("/etc/libinput/local-overrides.quirks", tasks)
        self.assertIn("MatchName=CIRQ1080:00 0488:1054 Touchpad", quirk)
        self.assertIn("MatchVendor=0x0488", quirk)
        self.assertIn("MatchProduct=0x1054", quirk)
        self.assertIn(
            "MatchDMIModalias=dmi:*:svnLENOVO:pn83JM:"
            "pvrIdeaPadPro516IAH10:*",
            quirk,
        )
        self.assertIn("ModelLenovoX1Gen6Touchpad=1", quirk)
        self.assertIn('"touchpad jump workaround"', cli)
        self.assertIn('"touchpad libinput match"', cli)
        self.assertIn('"touchpad"', cli)

    def test_kubuntu_routes_gui_ssh_through_bitwarden(self):
        cli = DOT.read_text()
        environment = (
            ROOT / "config/environment.d/10-bitwarden-ssh-agent.conf"
        ).read_text()
        self.assertIn(
            "SSH_AUTH_SOCK=${HOME}/.bitwarden-ssh-agent.sock",
            environment,
        )
        self.assertIn(
            'ROOT / "config/environment.d/10-bitwarden-ssh-agent.conf"',
            cli,
        )
        self.assertIn(
            '["systemctl", "--user", "mask", "--now", "ssh-agent.socket"]',
            cli,
        )
        self.assertIn('"dbus-update-activation-environment"', cli)
        self.assertIn('"set-environment"', cli)
        self.assertIn('"graphical SSH agent routing"', cli)
        self.assertIn('"competing OpenSSH agent disabled"', cli)
        self.assertIn('["ssh-add", "-L"]', cli)
        self.assertIn("timeout=5", cli)

    def test_kubuntu_never_sleeps_automatically(self):
        cli = DOT.read_text()
        profile_data = json.loads(
            (ROOT / "profiles/kubuntu-laptop.yml").read_text()
        )
        powerdevil = (ROOT / "config/kde/.config/powerdevilrc").read_text()
        for profile in ("AC", "Battery", "LowBattery"):
            section = f"[{profile}][SuspendAndShutdown]"
            self.assertIn(section, powerdevil)
        self.assertEqual(powerdevil.count("AutoSuspendAction=0"), 3)
        self.assertEqual(powerdevil.count("LidAction=0"), 3)
        self.assertEqual(powerdevil.count("PowerButtonAction=1"), 3)
        self.assertIn("[AC][Performance]\nPowerProfile=performance", powerdevil)
        self.assertIn("[Battery][Performance]\nPowerProfile=balanced", powerdevil)
        self.assertIn("[LowBattery][Performance]\nPowerProfile=power-saver", powerdevil)
        self.assertIn("[BatteryManagement]\nBatteryLowLevel=20", powerdevil)
        self.assertIn(
            "[AC][Display]\nDisplayBrightness=100\nUseProfileSpecificDisplayBrightness=true",
            powerdevil,
        )
        self.assertIn(
            "[Battery][Display]\nDisplayBrightness=100\nUseProfileSpecificDisplayBrightness=true",
            powerdevil,
        )
        self.assertIn(
            "[LowBattery][Display]\nDisplayBrightness=40\nUseProfileSpecificDisplayBrightness=true",
            powerdevil,
        )
        logind = (ROOT / "config/systemd/logind/60-dotfiles-lid.conf").read_text()
        self.assertIn("HandleLidSwitch=ignore", logind)
        self.assertIn("HandleLidSwitchExternalPower=ignore", logind)
        self.assertIn("HandleLidSwitchDocked=ignore", logind)
        self.assertIn("HandlePowerKey=suspend", logind)
        self.assertIn("IdleAction=ignore", logind)
        self.assertIn('"restart", "plasma-powerdevil.service"', cli)
        self.assertIn('"live lid action"', cli)
        self.assertTrue(profile_data["features"]["lid_power_saver"])
        self.assertIn("power-profiles-daemon", profile_data["packages"]["apt"])
        self.assertIn("upower", profile_data["packages"]["apt"])
        self.assertIn("libglib2.0-bin", profile_data["packages"]["apt"])
        lid_script = (ROOT / "config/power/dot-lid-power").read_text()
        self.assertIn('if [[ "$lid" == "true" ]]', lid_script)
        self.assertIn("power-saver", lid_script)
        self.assertIn("performance", lid_script)
        self.assertIn("balanced", lid_script)
        self.assertIn(
            '"$gdbus_command" monitor --system --dest org.freedesktop.UPower',
            lid_script,
        )
        self.assertIn("*LidIsClosed*", lid_script)
        self.assertIn("*OnBattery*", lid_script)
        self.assertIn("*Percentage*", lid_script)
        self.assertIn('"$previous_lid" == "true"', lid_script)
        self.assertIn("org.kde.Solid.PowerManagement", lid_script)
        self.assertIn("wakeup", lid_script)
        lid_unit = (
            ROOT / "config/systemd/user/dot-lid-power.service"
        ).read_text()
        self.assertIn("plasma-powerdevil.service", lid_unit)
        self.assertIn("PartOf=graphical-session.target", lid_unit)
        self.assertIn("WantedBy=graphical-session.target", lid_unit)
        self.assertIn("dot-lid-power watch", lid_unit)
        self.assertIn('"lid power-saver service"', cli)
        self.assertIn('"lid-aware power profile"', cli)
        playbook = (ROOT / "ansible/local.yml").read_text()
        self.assertIn("path: /etc/systemd/logind.conf.d", playbook)
        quiet_resume = (
            ROOT / "config/grub/99-dotfiles-quiet-resume.cfg"
        ).read_text()
        self.assertIn("quiet splash loglevel=3", quiet_resume)
        self.assertIn("systemd.show_status=false", quiet_resume)
        self.assertIn("rd.systemd.show_status=false", quiet_resume)
        self.assertIn("vt.global_cursor_default=0", quiet_resume)
        self.assertIn("dest: /etc/default/grub.d/99-dotfiles-quiet-resume.cfg", playbook)
        self.assertIn("argv: [update-grub]", playbook)
        self.assertIn('selected_tags & {"kde", "power"}', cli)
        portable_apply = playbook.split("- name: Apply portable configuration", 1)[1].split(
            "- name: Configure native application window frames", 1
        )[0]
        for tag in ("git", "kde", "lockscreen", "power", "tmux"):
            self.assertIn(f"- {tag}", portable_apply)

    def test_kubuntu_uses_ubuntu_recommended_nvidia_driver(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        role = (ROOT / "ansible/tasks/nvidia.yml").read_text()
        cli = DOT.read_text()
        self.assertTrue(profile["features"]["nvidia_driver"])
        self.assertFalse(profile["features"]["nvidia_dynamic_boost"])
        self.assertIn("ubuntu-drivers, devices", role)
        self.assertIn("recommended", role)
        self.assertIn("state: latest", role)
        self.assertIn("prime-select, on-demand", role)
        self.assertIn("nvidia-powerd.service", role)
        self.assertIn("systemctl, is-failed, --quiet, nvidia-powerd.service", role)
        self.assertIn("dot_nvidia_powerd_failed.rc == 0", role)
        self.assertIn('"NVIDIA userspace"', cli)
        self.assertIn('"NVIDIA Dynamic Boost workaround"', cli)
        self.assertNotIn("nvidia-driver-595", role)
        self.assertIn('"gpu",', cli)

    def test_kubuntu_manages_factory_internal_display_policy(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        manifest = json.loads(
            (
                ROOT
                / "config/display/lenovo-ideapad-pro-5-16iah10.json"
            ).read_text()
        )
        display = (ROOT / "scripts/configure-display").read_text()
        cli = DOT.read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()

        self.assertTrue(profile["features"]["factory_display_profile"])
        self.assertEqual(
            manifest["panel"]["edid_identifier"],
            "SDC 16900 0 0 2024 0",
        )
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["default_mode"], "windows-native")
        self.assertEqual(
            manifest["modes"]["windows-native"]["windows_filename"],
            "TPLCD_8BAD_Native.icm",
        )
        self.assertEqual(
            manifest["modes"]["windows-native"]["windows_color_state"],
            7,
        )
        self.assertEqual(
            manifest["modes"]["factory-accurate"]["windows_filename"],
            "TPLCD_8BAD_Default.icm",
        )
        self.assertEqual(
            manifest["modes"]["factory-accurate"]["windows_color_state"],
            4,
        )
        self.assertEqual(manifest["policy"]["adaptive_sync"], "Never")
        self.assertEqual(manifest["policy"]["rgb_range"], "Automatic")
        self.assertEqual(manifest["policy"]["color_profile_source"], "ICC")
        self.assertEqual(
            manifest["policy"]["color_power_tradeoff"],
            "PreferAccuracy",
        )
        self.assertFalse(manifest["policy"]["hdr"])
        self.assertFalse(manifest["policy"]["wide_color_gamut"])
        self.assertEqual(manifest["policy"]["max_bits_per_color"], 0)
        self.assertEqual(manifest["policy"]["sdr_gamut_wideness"], 1.0)
        self.assertIn('"udisksctl", "mount"', display)
        self.assertIn('"kscreen-doctor", command', display)
        self.assertIn("colorProfileSource", display)
        self.assertIn("maxbpc", display)
        self.assertIn("sdrGamut", display)
        self.assertIn('"factory_display_profile"', cli)
        self.assertIn('"Internal OLED display"', cli)
        self.assertIn('sub.add_parser("display")', cli)
        self.assertIn('"Internal OLED color mode"', cli)
        self.assertIn('"--mode"', display)
        self.assertIn('"--status"', display)
        self.assertIn('"internal display policy"', cli)
        portable_apply = playbook.split("- name: Apply portable configuration", 1)[1].split(
            "- name: Configure native application window frames", 1
        )[0]
        for tag in ("tmux", "nvim", "display", "vscode"):
            self.assertIn(f"- {tag}", portable_apply)

        chrome_wrapper = (ROOT / "config/chromium/google-chrome-stable").read_text()
        code_wrapper = (ROOT / "config/chromium/code").read_text()
        obsidian_wrapper = (ROOT / "config/obsidian/obsidian").read_text()
        chrome_desktop = (ROOT / "config/chromium/google-chrome.desktop").read_text()
        code_desktop = (ROOT / "config/chromium/code.desktop").read_text()
        obsidian_desktop = (ROOT / "config/obsidian/obsidian.desktop").read_text()
        for managed in (
            chrome_wrapper,
            code_wrapper,
            obsidian_wrapper,
            chrome_desktop,
            code_desktop,
        ):
            self.assertIn("--disable-features=WaylandWpColorManagerV1", managed)
        self.assertIn(
            'export SSH_AUTH_SOCK="${HOME}/.bitwarden-ssh-agent.sock"',
            obsidian_wrapper,
        )
        self.assertIn("config/chromium/google-chrome-stable", cli)
        self.assertIn(".local/bin/google-chrome-stable", cli)
        self.assertIn("config/chromium/code", cli)
        self.assertIn(".local/bin/code", cli)
        self.assertIn("config/obsidian/obsidian", cli)
        self.assertIn(".local/bin/obsidian", cli)
        self.assertIn("Chromium native-gamut policy", cli)

    def test_kubuntu_manages_vscode_and_fullscreen_rdp_files(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        playbook = (ROOT / "ansible/local.yml").read_text()
        vscode = (ROOT / "ansible/tasks/vscode.yml").read_text()
        rdp_role = (ROOT / "ansible/tasks/rdp.yml").read_text()
        rdp_launcher = (ROOT / "config/rdp/dot-rdp").read_text()
        remmina_launcher = (
            ROOT / "config/rdp/dot-remmina-f5"
        ).read_text()
        remmina_preferences = (
            ROOT / "config/rdp/configure-remmina"
        ).read_text()
        rdp_desktop = (
            ROOT / "config/rdp/io.github.doview.dotfiles.rdp.desktop"
        ).read_text()
        rdp_mime = (ROOT / "config/rdp/rdp-mime.xml").read_text()
        cli = DOT.read_text()

        self.assertTrue(profile["features"]["vscode"])
        self.assertTrue(profile["features"]["rdp_files"])
        self.assertIn("code", profile["packages"]["apt"])
        self.assertIn("freerdp-sdl", profile["packages"]["apt"])
        self.assertIn("remmina", profile["packages"]["apt"])
        self.assertIn("remmina-plugin-rdp", profile["packages"]["apt"])
        self.assertEqual(catalog["tools"]["code"]["provider"], "apt")
        self.assertEqual(catalog["tools"]["freerdp-sdl"]["provider"], "apt")
        self.assertEqual(catalog["tools"]["remmina"]["provider"], "apt")
        self.assertEqual(
            catalog["tools"]["remmina-plugin-rdp"]["provider"],
            "apt",
        )
        self.assertIn("tasks/vscode.yml", playbook)
        self.assertIn("tasks/rdp.yml", playbook)
        self.assertIn("https://packages.microsoft.com/repos/code", vscode)
        self.assertIn(
            "BC528686B50D79E339D3721CEB3E94ADBE1229CF",
            vscode,
        )
        self.assertIn("Pin-Priority: 9999", vscode)
        self.assertIn("state: latest", vscode)
        self.assertIn("- freerdp-sdl", rdp_role)
        self.assertIn("- remmina", rdp_role)
        self.assertIn("- remmina-plugin-rdp", rdp_role)
        self.assertIn("client_options=(/f /dynamic-resolution)", rdp_launcher)
        self.assertIn("gatewayaccesstoken:s:", rdp_launcher)
        self.assertIn("DOT_REMMINA_F5_HELPER", rdp_launcher)
        self.assertIn('"$client" /args-from:stdin', rdp_launcher)
        self.assertNotIn(
            'exec "$client" "$rdp_file" "${client_options[@]}"',
            rdp_launcher,
        )
        self.assertNotIn("cert:ignore", rdp_launcher)
        self.assertNotIn("/p:", rdp_launcher)
        self.assertIn('"scale": "1"', remmina_launcher)
        self.assertIn('"resolution_mode": "0"', remmina_launcher)
        self.assertIn('"resolution_width": "2880"', remmina_launcher)
        self.assertIn('"resolution_height": "1800"', remmina_launcher)
        self.assertIn('"viewmode": "4"', remmina_launcher)
        self.assertIn('"quality": "9"', remmina_launcher)
        self.assertNotIn('"--enable-fullscreen"', remmina_launcher)
        self.assertIn("DOT_REMMINA_CONFIGURE", remmina_launcher)
        self.assertIn('"cert_ignore": "0"', remmina_launcher)
        self.assertIn('"ignore-tls-errors": "0"', remmina_launcher)
        self.assertIn('"rdp_desktopScaleFactor": "175"', remmina_preferences)
        self.assertIn('"rdp_deviceScaleFactor": "180"', remmina_preferences)
        self.assertIn('"rdp_quality_9": "80"', remmina_preferences)
        self.assertIn('"start_dynres": "false"', remmina_preferences)
        self.assertIn(
            "MimeType=application/x-rdp;application/x-remmina;",
            rdp_desktop,
        )
        self.assertIn('type="application/x-rdp"', rdp_mime)
        self.assertIn('pattern="*.rdp"', rdp_mime)
        self.assertIn('pattern="*.rdpw"', rdp_mime)
        self.assertIn('"Visual Studio Code"', cli)
        self.assertIn('"Remote Desktop files"', cli)
        self.assertIn('"io.github.doview.dotfiles.rdp.desktop"', cli)
        self.assertIn('"application/x-remmina"', cli)
        self.assertIn("Always write an explicit default", cli)

    def test_kubuntu_manages_android_tools(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())

        self.assertIn("adb", profile["packages"]["apt"])
        self.assertIn("scrcpy", profile["packages"]["apt"])
        self.assertEqual(catalog["tools"]["adb"]["provider"], "apt")
        self.assertEqual(catalog["tools"]["scrcpy"]["provider"], "apt")

    def test_kubuntu_manages_anydesk_from_official_repository(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        role = (ROOT / "ansible/tasks/anydesk.yml").read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        key = ROOT / "config/apt/anydesk-archive-keyring.asc"

        self.assertTrue(profile["features"]["anydesk"])
        self.assertIn("anydesk", profile["packages"]["apt"])
        self.assertEqual(catalog["tools"]["anydesk"]["provider"], "apt")
        self.assertIn("tasks/anydesk.yml", playbook)
        self.assertIn("https://deb.anydesk.com", role)
        self.assertIn("06B5EA2FAE208E7CDA9761DCA2FB21D5A8772835", role)
        self.assertIn("state: latest", role)
        self.assertTrue(key.is_file())
        self.assertIn("BEGIN PGP PUBLIC KEY BLOCK", key.read_text())

    def test_kubuntu_manages_openssh_server(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())

        self.assertIn("openssh-server", profile["packages"]["apt"])
        self.assertEqual(catalog["tools"]["openssh-server"]["provider"], "apt")

    def test_tmux_configuration_is_managed(self):
        cli = DOT.read_text()
        config = (ROOT / "config/tmux/tmux.conf").read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        self.assertIn('ROOT / "config/tmux/tmux.conf"', cli)
        self.assertIn('Path.home() / ".config/tmux/tmux.conf"', cli)
        self.assertIn("set -g prefix C-Space", config)
        self.assertIn("C-MouseDown1Pane", config)
        self.assertIn("dot-open-link", config)
        self.assertIn("#{q:mouse_hyperlink}", config)
        self.assertIn("#{q:mouse_word}", config)
        self.assertIn("#{mouse_x}", config)
        self.assertIn("#{pane_left}", config)
        self.assertIn("#{q:mouse_line}", config)
        self.assertIn("--hyperlink=", config)
        self.assertIn("--line=", config)
        self.assertIn("extkeys", config)
        self.assertIn("set -s extended-keys always", config)
        self.assertIn("set -s extended-keys-format csi-u", config)
        self.assertIn("tmux-plugins/tpm", config)
        self.assertIn("~/.config/tmux/plugins/tpm/tpm", config)
        opener = (ROOT / "config/tmux/open-link").read_text()
        self.assertIn("http://*|https://*|mailto:*|file://*", opener)
        self.assertIn("DOT_TMUX_LINK_DRY_RUN", opener)
        self.assertIn('ROOT / "config/tmux/open-link"', cli)
        self.assertIn("Install or update tmux plugin manager", playbook)
        self.assertIn("Install configured tmux plugins", playbook)
        self.assertIn("'FATAL:' in dot_tmux_plugins_install.stderr", playbook)

    def test_portable_clipboard_commands_are_managed(self):
        cli = DOT.read_text()
        common = (ROOT / "config/shell/common.sh").read_text()
        powershell = (ROOT / "config/powershell/profile.ps1").read_text()
        termux = json.loads((ROOT / "profiles/termux.yml").read_text())

        self.assertIn('ROOT / "config/shell/clip"', cli)
        self.assertIn('ROOT / "config/shell/cclip"', cli)
        self.assertIn('Path.home() / ".local/bin/clip"', cli)
        self.assertIn('Path.home() / ".local/bin/cclip"', cli)
        self.assertIn('"clipboard commands"', cli)
        self.assertIn("function cclip", powershell)
        self.assertIn("clip.exe", powershell)
        self.assertIn("termux-api", termux["packages"]["pkg"])
        self.assertNotIn("alias clip=", common)

    def test_kubuntu_uses_separate_clipboard_and_emoji_tools(self):
        cli = DOT.read_text()
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        copyq = (ROOT / "config/copyq/configure.js").read_text()
        shortcuts = (ROOT / "config/kde/.config/kglobalshortcutsrc").read_text()
        installer = (ROOT / "scripts/install-emoji-picker").read_text()
        copyq_installer = (ROOT / "scripts/install-copyq").read_text()
        copyq_configurer = (ROOT / "scripts/configure-copyq").read_text()
        copyq_theme = (ROOT / "config/copyq/github-dark.ini").read_text()
        emoji_config = json.loads(
            (ROOT / "config/emoji-picker/config.json").read_text()
        )

        self.assertTrue(profile["features"]["copyq"])
        self.assertTrue(profile["features"]["emoji_picker"])
        self.assertIn("python3-pyqt6", profile["packages"]["apt"])
        self.assertIn("python3-gi-cairo", profile["packages"]["apt"])
        self.assertIn("ydotool", profile["packages"]["apt"])
        self.assertIn("wl-clipboard", profile["packages"]["apt"])
        self.assertIn("config('tabs', ['Clipboard'])", copyq)
        self.assertIn("config('clipboard_mime_size_limit', '.*:100M')", copyq)
        self.assertNotIn("Emoji", copyq)
        self.assertIn("dot-copyq-history-meta=Meta+V", shortcuts)
        self.assertIn("dot-copyq-history-ctrl=Ctrl+`", shortcuts)
        self.assertIn("dot-emoji-picker=Meta+.", shortcuts)
        self.assertIn("stock_emoji_picker: [0]", cli)
        self.assertIn("clipboard_history_meta: [268435542]", cli)
        self.assertIn("clipboard_history_ctrl: [67108960]", cli)
        self.assertNotIn("isGlobalShortcut: true", copyq)
        clipboard_script = (
            ROOT / "config/kwin/dot-clipboard/contents/code/main.js"
        ).read_text()
        history_script = (ROOT / "config/copyq/dot-copyq-history").read_text()
        self.assertIn('"Meta+V"', clipboard_script)
        self.assertIn('"Ctrl+`"', clipboard_script)
        self.assertIn('"Meta+."', clipboard_script)
        self.assertIn("dot-copyq-history.service", clipboard_script)
        self.assertIn("dot-emoji-picker.service", clipboard_script)
        self.assertIn('"RestartUnit"', clipboard_script)
        self.assertNotIn('"StartUnit"', clipboard_script)
        self.assertIn('${XDG_BIN_HOME:-$HOME/.local/bin}/copyq', history_script)
        self.assertIn("jockel09/emoji-picker", installer)
        self.assertIn("releases/latest", installer)
        self.assertNotIn("cmake", installer.lower())
        self.assertIn("QT_QPA_PLATFORM=wayland", copyq_installer)
        self.assertNotIn("export COPYQ_CLIPBOARD_MIME_SIZE_LIMIT", copyq_installer)
        self.assertIn("--appimage-extract", copyq_installer)
        self.assertIn('mktemp -d "$app_root/.install.XXXXXX"', copyq_installer)
        self.assertNotIn('work_dir="$(mktemp -d)"', copyq_installer)
        luna_installer = (ROOT / "scripts/install-luna-ocr").read_text()
        self.assertIn('temporary_root="$install_root"', luna_installer)
        self.assertIn('app_run="$app_dir/AppRun"', copyq_installer)
        self.assertIn('export APPDIR=', copyq_installer)
        self.assertIn(r'exec \"$app_run\"', copyq_installer)
        self.assertIn("global.dotfilesPasteVersion = 4", copyq)
        self.assertIn("global.dotfilesPaste = function()", copyq)
        self.assertNotIn("global.paste = function()", copyq)
        self.assertIn("Object.defineProperty(global, 'paste'", copyq)
        self.assertIn("var managedScriptResult = eval(managedScript)", copyq)
        self.assertIn("CopyQ Wayland paste override is not loaded.", copyq_configurer)
        self.assertNotIn('"$copyq_bin" exit', copyq_configurer)
        self.assertIn("global.paste === global.dotfilesPaste", copyq_configurer)
        self.assertIn("loadTheme(arguments[1])", copyq_configurer)
        self.assertIn("CopyQ GitHub Dark theme drifted.", copyq_configurer)
        self.assertIn("bg=#0d1117", copyq_theme)
        self.assertIn("fg=#e6edf3", copyq_theme)
        self.assertIn("sel_bg=#1f6feb", copyq_theme)
        self.assertIn("style_main_window=true", copyq_theme)
        self.assertIn('"clipboard",', cli)
        self.assertIn('"emoji",', cli)
        self.assertIn("startswith('CHANGED ')", (ROOT / "ansible/tasks/copyq.yml").read_text())
        emoji_tasks = (ROOT / "ansible/tasks/emoji-picker.yml").read_text()
        self.assertIn("startswith('CHANGED ')", emoji_tasks)
        self.assertIn("- /usr/bin/python3", emoji_tasks)
        self.assertEqual(emoji_config["insert_method"], "ydotool")
        self.assertTrue(emoji_config["close_on_select"])
        self.assertIn("def palette_clipboard_menu", cli)
        self.assertIn("def emoji_picker_runtime", cli)
        self.assertIn("def clipboard_shortcuts_runtime", cli)
        self.assertIn("PangoCairo.create_layout", cli)
        self.assertIn('"CopyQ clipboard history"', cli)
        self.assertIn('"Emoji Picker"', cli)
        self.assertNotIn(
            "            palette_execute(execute)\n\n\ndef palette_clipboard_menu",
            cli,
        )
        self.assertIn('clipboard = sub.add_parser("clipboard")', cli)
        self.assertIn("(?:@ai )?", cli)

    def test_kubuntu_routes_screenshot_shortcuts_to_flameshot(self):
        cli = DOT.read_text()
        shortcuts = (ROOT / "config/kde/.config/kglobalshortcutsrc").read_text()
        kwin = (ROOT / "config/kde/.config/kwinrc").read_text()
        script = (
            ROOT / "config/kwin/dot-screenshots/contents/code/main.js"
        ).read_text()
        region_service = (
            ROOT / "config/systemd/user/dot-flameshot-region-clipboard.service"
        ).read_text()
        full_service = (
            ROOT / "config/systemd/user/dot-flameshot-full-clipboard.service"
        ).read_text()
        window_service = (
            ROOT / "config/systemd/user/dot-active-window-clipboard.service"
        ).read_text()
        editor_service = (
            ROOT / "config/systemd/user/dot-flameshot-region-editor.service"
        ).read_text()
        probe_service = (
            ROOT / "config/systemd/user/dot-screenshots-probe.service"
        ).read_text()
        luna_ocr_service = (
            ROOT / "config/systemd/user/dot-luna-ocr-region.service"
        ).read_text()
        luna_assist_service = (
            ROOT / "config/systemd/user/dot-luna-assist-region.service"
        ).read_text()
        xkb_rules = (ROOT / "config/xkb/rules/evdev").read_text()
        xkb_symbols = (ROOT / "config/xkb/symbols/dotfiles").read_text()
        keyboard_config = (ROOT / "config/kde/.config/kxkbrc").read_text()
        active_capture = (ROOT / "scripts/capture-active-window").read_text()
        flameshot_capture = (ROOT / "scripts/capture-flameshot").read_text()
        config = (ROOT / "config/flameshot/flameshot.ini").read_text()

        self.assertIn("dot-screenshotsEnabled=true", kwin)
        self.assertIn(
            "dot-flameshot-region-clipboard=Meta+Shift+S",
            shortcuts,
        )
        self.assertIn("dot-flameshot-full-clipboard=Print", shortcuts)
        self.assertIn(
            "dot-active-window-clipboard=Alt+Print\\tMeta+Print",
            shortcuts,
        )
        self.assertIn("dot-flameshot-region-editor=Meta+Ctrl+Shift+S", shortcuts)
        self.assertIn("dot-luna-ocr-region=Meta+Shift+T", shortcuts)
        self.assertIn("dot-luna-assist-region=Meta+Shift+L", shortcuts)
        self.assertIn("ActiveWindowScreenShot=\n", shortcuts)
        self.assertIn("FullScreenScreenShot=\n", shortcuts)
        self.assertIn("RectangularRegionScreenShot=\n", shortcuts)
        self.assertIn('"RestartUnit"', script)
        self.assertIn('"dot-flameshot-region-clipboard.service"', script)
        self.assertIn('"dot-screenshots-probe.service"', script)
        self.assertIn('"dot-luna-ocr-region.service"', script)
        self.assertIn('"dot-luna-assist-region.service"', script)
        self.assertIn('"Alt+Print"', script)
        self.assertIn("dot-capture-flameshot region", region_service)
        self.assertIn("dot-capture-flameshot full", full_service)
        self.assertIn("flameshot gui --path", flameshot_capture)
        self.assertIn("flameshot full --path", flameshot_capture)
        self.assertIn("wl-copy --foreground --type image/png", flameshot_capture)
        self.assertIn('ROOT / "scripts/capture-flameshot"', cli)
        self.assertIn("dot-capture-active-window", window_service)
        self.assertIn("spectacle \\", active_capture)
        self.assertIn("--activewindow", active_capture)
        self.assertIn("--output", active_capture)
        self.assertIn("wl-copy --foreground --type image/png", active_capture)
        self.assertIn("ExecStart=/usr/bin/flameshot gui", editor_service)
        self.assertNotIn("--pin", editor_service)
        self.assertIn("RemainAfterExit=yes", probe_service)
        self.assertIn("luna-ocr capture", luna_ocr_service)
        self.assertIn("luna-ocr ask", luna_assist_service)
        self.assertIn(
            "LoadCredentialEncrypted=luna-ocr-openai-api-key",
            luna_ocr_service,
        )
        self.assertIn("showHelp=false", config)
        self.assertIn("uiColor=#161b22", config)
        self.assertIn("contrastUiColor=#58a6ff", config)
        self.assertIn("def sync_managed_screenshot_shortcuts", cli)
        self.assertIn("def managed_screenshot_callback_ok", cli)
        self.assertIn("org.kde.KGlobalAccel.unregister", cli)
        self.assertIn("kwin-dot-screenshots-runtime", cli)
        self.assertIn("config/xkb/rules/evdev", cli)
        self.assertIn("config/xkb/symbols/dotfiles", cli)
        self.assertIn('".config/kxkbrc"', cli)
        self.assertIn("dotfiles:alt_print", xkb_rules)
        self.assertIn("+dotfiles(alt_print)", xkb_rules)
        self.assertIn('type[Group1] = "TWO_LEVEL"', xkb_symbols)
        self.assertIn("[ Print, Print ]", xkb_symbols)
        self.assertIn("Options=dotfiles:alt_print", keyboard_config)
        self.assertIn('selected("screenshots", "kde")', cli)
        self.assertIn('"screenshots",', cli)
        fn_lock = (
            ROOT / "config/udev/90-dotfiles-ideapad-fn-lock.rules"
        ).read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        self.assertIn('KERNEL=="VPC2004:00"', fn_lock)
        self.assertIn('ATTR{fn_lock}="1"', fn_lock)
        self.assertIn("Make the IdeaPad screenshot key emit Print", playbook)
        self.assertIn("--sysname-match=VPC2004:00", playbook)

    def test_kubuntu_manages_bun_with_homebrew(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        self.assertIn("bun", profile["packages"]["brew"])
        self.assertEqual(catalog["tools"]["bun"]["provider"], "brew")

    def test_luna_ocr_release_installer_is_managed(self):
        cli = DOT.read_text()
        installer = (ROOT / "scripts/install-luna-ocr").read_text()
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        self.assertTrue(profile["features"]["luna_ocr"])
        self.assertIn("DovieW/luna-ocr", installer)
        self.assertIn("luna-ocr-linux-x64.sha256", installer)
        self.assertIn('sub.add_parser("luna-ocr")', cli)
        self.assertIn('ROOT / "scripts/install-luna-ocr"', cli)

    def test_zsh_uses_fzf_for_normal_tab_completion(self):
        common = json.loads((ROOT / "profiles/common-linux.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        zshrc = (ROOT / "config/shell/zshrc").read_text()

        self.assertIn("fzf-tab", common["packages"]["brew"])
        self.assertEqual(catalog["tools"]["fzf-tab"]["provider"], "brew")
        self.assertIn("opt/fzf-tab/share/fzf-tab/fzf-tab.zsh", zshrc)
        self.assertIn("zstyle ':completion:*' menu no", zshrc)
        self.assertIn("zstyle ':fzf-tab:*' fzf-flags", zshrc)
        self.assertIn("zle -A fzf-tab-complete _dot_fzf_tab_upstream", zshrc)
        self.assertIn("commands[dd]=/usr/bin/true", zshrc)
        self.assertIn("commands[gdd]=/usr/bin/true", zshrc)
        self.assertIn("zle -N fzf-tab-complete _dot_fzf_tab_complete", zshrc)
        self.assertLess(
            zshrc.index("opt/fzf-tab/share/fzf-tab/fzf-tab.zsh"),
            zshrc.index("share/zsh-autosuggestions/zsh-autosuggestions.zsh"),
        )

    def test_fzf_theme_is_shared_while_previews_remain_contextual(self):
        cli = DOT.read_text()
        shell = (ROOT / "config/shell/common.sh").read_text()
        zshrc = (ROOT / "config/shell/zshrc").read_text()
        git_switcher = (ROOT / "config/git/bin/git-switcher").read_text()
        powershell = (ROOT / "config/powershell/profile.ps1").read_text()
        neovim = (ROOT / "config/nvim/lua/dovie/plugins/init.lua").read_text()

        self.assertIn('ROOT / "config/fzf/fzfrc"', cli)
        self.assertIn('ROOT / "config/fzf/preview"', cli)
        self.assertIn("FZF_DEFAULT_OPTS_FILE", shell)
        self.assertIn("FZF_CTRL_T_OPTS", shell)
        self.assertIn("dot-fzf-preview {}", shell)
        self.assertNotIn("--preview", shell.split("FZF_CTRL_R_OPTS=", 1)[1].splitlines()[0])
        self.assertIn("fzf-preview", zshrc)
        self.assertIn("Recent commits", git_switcher)
        self.assertIn("FZF_DEFAULT_OPTS_FILE", powershell)
        self.assertIn('title = " FZF "', neovim)

    def test_git_sync_is_managed_and_enabled_for_primary_branches(self):
        cli = DOT.read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        root_gitconfig = (ROOT / "config/git/root.gitconfig").read_text()
        sync_gitconfig = (ROOT / "config/git/sync.gitconfig").read_text()
        installer = (ROOT / "scripts/install-git-sync").read_text()

        self.assertIn('scripts/install-git-sync', cli)
        self.assertIn('scripts/install-git-sync', playbook)
        self.assertIn('tags: [packages, config, git, app-updates]', playbook)
        self.assertIn('path = ~/repos/dotfiles/config/git/sync.gitconfig', root_gitconfig)
        self.assertIn('[branch "master"]', sync_gitconfig)
        self.assertIn('[branch "main"]', sync_gitconfig)
        self.assertEqual(sync_gitconfig.count("syncNewFiles = true"), 2)
        self.assertIn('https://github.com/simonthum/git-sync.git', installer)
        self.assertIn('git ls-remote', installer)

    def test_neovim_is_modern_managed_and_shared_with_wsl(self):
        common = json.loads((ROOT / "profiles/common-linux.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        cli = DOT.read_text()
        plugins = (ROOT / "config/nvim/lua/dovie/plugins/init.lua").read_text()
        lsp = (ROOT / "config/nvim/lua/dovie/plugins/lsp.lua").read_text()

        self.assertTrue(common["features"]["neovim"])
        for package in ("neovim", "stylua", "tree-sitter-cli"):
            self.assertIn(package, common["packages"]["brew"])
            self.assertEqual(catalog["tools"][package]["provider"], "brew")
        self.assertIn('ROOT / "config/nvim"', cli)
        self.assertIn('Path.home() / ".config/nvim"', cli)
        self.assertIn("def cmd_nvim", cli)
        self.assertIn("dot-nvim-", cli)
        self.assertIn("publish_nvim_lock", cli)
        self.assertIn('"ibhagwan/fzf-lua"', plugins)
        self.assertIn('"stevearc/oil.nvim"', plugins)
        self.assertIn('"ThePrimeagen/harpoon"', plugins)
        self.assertIn('"sindrets/diffview.nvim"', plugins)
        self.assertIn('"okuuva/auto-save.nvim"', plugins)
        self.assertIn('"saghen/blink.cmp"', lsp)
        self.assertIn("vim.lsp.config", lsp)
        self.assertIn('lsp_format = "fallback"', lsp)
        self.assertNotIn("telescope.nvim", plugins.lower())
        self.assertNotIn("noice.nvim", plugins.lower())
        self.assertNotIn("copilot", plugins.lower())

    def test_glow_is_managed_for_kubuntu_wsl_and_termux(self):
        common = json.loads((ROOT / "profiles/common-linux.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        termux = json.loads((ROOT / "profiles/termux.yml").read_text())

        self.assertIn("glow", common["packages"]["brew"])
        self.assertEqual(catalog["tools"]["glow"]["provider"], "brew")
        self.assertIn("glow", termux["packages"]["pkg"])
        for name in ("kubuntu-laptop", "wsl-personal", "wsl-work"):
            profile = json.loads((ROOT / f"profiles/{name}.yml").read_text())
            self.assertIn("common-linux", profile["inherits"])

    def test_neovim_lockfile_is_populated(self):
        lock = json.loads((ROOT / "config/nvim/lazy-lock.json").read_text())
        self.assertGreaterEqual(len(lock), 20)
        for plugin in ("lazy.nvim", "fzf-lua", "oil.nvim", "nvim-lspconfig"):
            self.assertIn(plugin, lock)

    def test_neovim_deployment_backs_up_and_restores_an_existing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            legacy = home / ".config/nvim"
            legacy.mkdir(parents=True)
            (legacy / "legacy.lua").write_text("-- keep me\n")
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["XDG_CONFIG_HOME"] = str(home / ".config")
            env["XDG_STATE_HOME"] = str(root / "state")
            env["PATH"] = os.pathsep.join(
                ["/home/linuxbrew/.linuxbrew/bin", "/usr/bin", "/bin"]
            )

            applied = subprocess.run(
                [
                    str(DOT),
                    "apply",
                    "--profile",
                    "wsl-personal",
                    "--direct",
                    "--tags",
                    "nvim",
                ],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertTrue(legacy.is_symlink())
            backups = list((root / "state/dotfiles/backups").iterdir())
            self.assertEqual(len(backups), 1)

            restored = subprocess.run(
                [str(DOT), "rollback", backups[0].name],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertTrue(legacy.is_dir())
            self.assertFalse(legacy.is_symlink())
            self.assertEqual((legacy / "legacy.lua").read_text(), "-- keep me\n")


if __name__ == "__main__":
    unittest.main()
