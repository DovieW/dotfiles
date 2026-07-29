#!/usr/bin/env python3
import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOT = ROOT / "bin/dot"


class DotCliTests(unittest.TestCase):
    def run_dot(self, *args):
        return subprocess.run([str(DOT), *args], text=True, capture_output=True)

    def test_help(self):
        result = self.run_dot("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bootstrap", result.stdout)
        self.assertIn("codex", result.stdout)
        self.assertIn("doctor", result.stdout)
        self.assertIn("save", result.stdout)
        self.assertIn("update", result.stdout)

    def test_profiles_are_parseable(self):
        for path in (ROOT / "profiles").glob("*.yml"):
            self.assertEqual(json.loads(path.read_text())["schema_version"], 1)

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
            result = subprocess.run(
                [
                    str(DOT),
                    "apply",
                    "--profile",
                    "wsl-personal",
                    "--tags",
                    "packages",
                ],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Run this command in an interactive terminal", result.stderr)

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

    def test_kubuntu_and_wsl_own_native_docker_engine(self):
        for name in ("kubuntu-laptop", "wsl-personal", "wsl-work"):
            profile = json.loads((ROOT / f"profiles/{name}.yml").read_text())
            self.assertTrue(profile["features"]["docker_engine"])
        for name in ("wsl-personal", "wsl-work"):
            profile = json.loads((ROOT / f"profiles/{name}.yml").read_text())
            self.assertNotIn("docker", profile["packages"]["brew"])
            self.assertNotIn("docker-compose", profile["packages"]["brew"])

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
        self.assertIn('selected_tags & {"packages", "docker", "gpu"}', text)
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

    def test_kde_diff_uses_delta_interactively(self):
        text = DOT.read_text()
        self.assertIn('["delta", "--paging=always"]', text)
        self.assertIn("sys.stdout.isatty()", text)

    def test_fzf_save_covers_preferences_and_shortcuts(self):
        text = DOT.read_text()
        self.assertIn('".config/spectaclerc"', text)
        self.assertIn('".config/kglobalshortcutsrc"', text)
        self.assertIn('"Settings to save › "', text)
        self.assertIn('"Save configuration changes\\tsave"', text)
        self.assertIn('"Update managed programs\\tupdate"', text)

    def test_kubuntu_never_sleeps_automatically(self):
        cli = DOT.read_text()
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
        logind = (ROOT / "config/systemd/logind/60-dotfiles-lid.conf").read_text()
        self.assertIn("HandleLidSwitch=ignore", logind)
        self.assertIn("HandleLidSwitchExternalPower=ignore", logind)
        self.assertIn("HandleLidSwitchDocked=ignore", logind)
        self.assertIn("HandlePowerKey=suspend", logind)
        self.assertIn("IdleAction=ignore", logind)
        self.assertIn('"restart", "plasma-powerdevil.service"', cli)
        self.assertIn('"live lid action"', cli)
        playbook = (ROOT / "ansible/local.yml").read_text()
        self.assertIn("path: /etc/systemd/logind.conf.d", playbook)

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
        self.assertIn('"NVIDIA userspace"', cli)
        self.assertIn('"NVIDIA Dynamic Boost workaround"', cli)
        self.assertNotIn("nvidia-driver-595", role)
        self.assertIn('{"packages", "docker", "gpu"}', cli)

    def test_tmux_configuration_is_managed(self):
        cli = DOT.read_text()
        config = (ROOT / "config/tmux/tmux.conf").read_text()
        playbook = (ROOT / "ansible/local.yml").read_text()
        self.assertIn('ROOT / "config/tmux/tmux.conf"', cli)
        self.assertIn('Path.home() / ".config/tmux/tmux.conf"', cli)
        self.assertIn("set -g prefix C-Space", config)
        self.assertIn("tmux-plugins/tpm", config)
        self.assertIn("~/.config/tmux/plugins/tpm/tpm", config)
        self.assertIn("Install or update tmux plugin manager", playbook)
        self.assertIn("Install configured tmux plugins", playbook)
        self.assertIn("'FATAL:' in dot_tmux_plugins_install.stderr", playbook)
        self.assertIn('{"config", "shell", "git", "kde", "tmux"}', cli)


if __name__ == "__main__":
    unittest.main()
