#!/usr/bin/env python3
import json
import os
from pathlib import Path
import pty
import runpy
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
        self.assertIn("gestures", result.stdout)
        self.assertIn("nvim", result.stdout)
        self.assertIn("panel", result.stdout)
        self.assertIn("save", result.stdout)
        self.assertIn("tailscale", result.stdout)
        self.assertIn("update", result.stdout)

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
        self.assertEqual(profiles["centered-compact"]["task_manager"], "icons")
        self.assertEqual(profiles["unified-pill"]["length_mode"], "fit")
        self.assertFalse(profiles["unified-pill"]["spacers"])
        self.assertEqual(profiles["unified-pill"]["launcher_icon"], "windows11")
        cli = DOT.read_text()
        self.assertIn('panel.lengthMode = cfg.length_mode', cli)
        self.assertIn('panel.floating = cfg.floating', cli)
        self.assertIn('icon: cfg.launcher_icon', cli)
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
        self.assertIn('"Save System Tray choices"', cli)
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

    def test_tailscale_runs_on_native_hosts_not_inside_wsl(self):
        kubuntu = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        windows = json.loads((ROOT / "profiles/windows-host.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        role = (ROOT / "ansible/tasks/tailscale.yml").read_text()
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
        self.assertNotIn("auth-key", role)
        self.assertNotIn("tailscale up --authkey", role)
        self.assertIn('"Tailscale enrollment"', cli)
        self.assertIn("editor = nvim", git_config)

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
        panel = (
            ROOT
            / "config/kde/.config/plasma-org.kde.plasma.desktop-appletsrc"
        ).read_text()
        self.assertIn(
            "launchers=applications:google-chrome.desktop,"
            "applications:com.mitchellh.ghostty.desktop,"
            "applications:obsidian.desktop",
            panel,
        )
        self.assertNotIn("applications:org.kde.konsole.desktop", panel)
        self.assertIn('ROOT / "config/ghostty/config"', cli)
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
        self.assertIn("[config, shell, tmux, app-updates]", playbook)

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
        lock_screen = (ROOT / "config/kde/.config/kscreenlockerrc").read_text()
        plasma_pa = (ROOT / "config/kde/.config/plasmaparc").read_text()
        plasma_notify = (
            ROOT / "config/kde/.config/plasmanotifyrc"
        ).read_text()
        colors = (ROOT / "config/kde/GitHubDark.colors").read_text()

        self.assertIn("plugin=org.kde.plasma.taskmanager", panel)
        self.assertIn("plugin=org.kde.desktopcontainment", panel)
        self.assertIn("wallpaperplugin=org.kde.color", panel)
        self.assertIn("Color=0,0,0", panel)
        self.assertIn("PopupPosition=BottomRight", plasma_notify)
        self.assertIn('".config/plasmanotifyrc",', cli)
        self.assertIn(
            "Notification position is held by a process-wide Plasma singleton",
            cli,
        )
        self.assertNotIn("[Containments][1][Wallpaper][org.kde.image]", panel)
        self.assertNotIn("plugin=org.kde.plasma.folder", panel)
        self.assertEqual(panel.count("plugin=org.kde.plasma.panelspacer"), 2)
        self.assertEqual(panel.count("plugin=org.kde.plasma.kickoff"), 1)
        self.assertNotIn("plugin=org.kde.plasma.pager", panel)
        self.assertNotIn("plugin=org.kde.plasma.showdesktop", panel)
        self.assertIn("AppletOrder=3;28;5;29;7;22", panel)
        self.assertIn("middleClickAction=Close", panel)
        self.assertIn("onlyGroupWhenFull=false", panel)
        self.assertIn("showOnlyCurrentDesktop=true", panel)
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

        native_frames = (ROOT / "scripts/configure-native-frames").read_text()
        self.assertIn('"custom_chrome_frame"', native_frames)
        self.assertIn('data["frame"] = "native"', native_frames)
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
        self.assertIn("skiptaskbar=true", rules)
        self.assertIn("skiptaskbarrule=2", rules)
        self.assertIn(
            "rules=dolphin-skip-taskbar,emoji-selector-ephemeral,"
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
        self.assertIn('"dbus-update-activation-environment"', cli)
        self.assertIn('"set-environment"', cli)
        self.assertIn('"graphical SSH agent routing"', cli)
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
        self.assertIn("git, kde, lockscreen, power, tmux", playbook)

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
        self.assertEqual(
            manifest["factory_profile"]["windows_filename"],
            "TPLCD_8BAD_Default.icm",
        )
        self.assertEqual(manifest["policy"]["adaptive_sync"], "Automatic")
        self.assertEqual(manifest["policy"]["rgb_range"], "Automatic")
        self.assertEqual(manifest["policy"]["color_profile_source"], "ICC")
        self.assertEqual(
            manifest["policy"]["color_power_tradeoff"],
            "PreferAccuracy",
        )
        self.assertFalse(manifest["policy"]["hdr"])
        self.assertFalse(manifest["policy"]["wide_color_gamut"])
        self.assertEqual(manifest["policy"]["max_bits_per_color"], 0)
        self.assertIn('"udisksctl", "mount"', display)
        self.assertIn('"kscreen-doctor", command', display)
        self.assertIn("colorProfileSource", display)
        self.assertIn("maxbpc", display)
        self.assertIn('"factory_display_profile"', cli)
        self.assertIn('"Internal OLED display"', cli)
        self.assertIn('"internal display policy"', cli)
        self.assertIn("tmux, nvim, display", playbook)

    def test_kubuntu_manages_vscode_and_fullscreen_rdp_files(self):
        profile = json.loads((ROOT / "profiles/kubuntu-laptop.yml").read_text())
        catalog = json.loads((ROOT / "packages/catalog.yml").read_text())
        playbook = (ROOT / "ansible/local.yml").read_text()
        vscode = (ROOT / "ansible/tasks/vscode.yml").read_text()
        rdp_role = (ROOT / "ansible/tasks/rdp.yml").read_text()
        rdp_launcher = (ROOT / "config/rdp/dot-rdp").read_text()
        rdp_desktop = (
            ROOT / "config/rdp/io.github.doview.dotfiles.rdp.desktop"
        ).read_text()
        rdp_mime = (ROOT / "config/rdp/rdp-mime.xml").read_text()
        cli = DOT.read_text()

        self.assertTrue(profile["features"]["vscode"])
        self.assertTrue(profile["features"]["rdp_files"])
        self.assertIn("code", profile["packages"]["apt"])
        self.assertIn("freerdp-sdl", profile["packages"]["apt"])
        self.assertEqual(catalog["tools"]["code"]["provider"], "apt")
        self.assertEqual(catalog["tools"]["freerdp-sdl"]["provider"], "apt")
        self.assertIn("tasks/vscode.yml", playbook)
        self.assertIn("tasks/rdp.yml", playbook)
        self.assertIn("https://packages.microsoft.com/repos/code", vscode)
        self.assertIn(
            "BC528686B50D79E339D3721CEB3E94ADBE1229CF",
            vscode,
        )
        self.assertIn("Pin-Priority: 9999", vscode)
        self.assertIn("state: latest", vscode)
        self.assertIn("name: freerdp-sdl", rdp_role)
        self.assertIn("client_options=(/f /dynamic-resolution)", rdp_launcher)
        self.assertIn("enablecredsspsupport:i:0", rdp_launcher)
        self.assertIn("client_options+=(/p)", rdp_launcher)
        self.assertIn(
            'exec "$client" "$rdp_file" "${client_options[@]}"',
            rdp_launcher,
        )
        self.assertNotIn("cert:ignore", rdp_launcher)
        self.assertNotIn("/p:", rdp_launcher)
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
