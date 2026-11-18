#!/usr/bin/env python3
"""Manage the matching upstream CodexBar desktop and CLI releases on Kubuntu."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = "steipete/CodexBar"
APP_ID = "com.steipete.CodexBar"
VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"
HOME = Path.home()
BIN = HOME / ".local/bin"
RELEASES = HOME / ".local/lib/dotfiles/codexbar"
CLI = BIN / "codexbar"
DESKTOP = BIN / "codexbar-linux"


def xdg_dir(variable, fallback):
    path = Path(os.environ.get(variable, ""))
    return path if path.is_absolute() else HOME / fallback


def missing_runtime():
    os_release = platform.freedesktop_os_release()
    widgets = "libqt6widgets6t64" if os_release.get("VERSION_CODENAME") == "noble" else "libqt6widgets6"
    packages = [
        "ca-certificates", "curl", widgets, "libqt6svg6", "qt6-wayland",
        "qml6-module-qtquick", "qml6-module-qtquick-controls", "qml6-module-qtquick-layouts",
        "qml6-module-qtquick-templates", "qml6-module-qtquick-window", "qml6-module-qtqml-workerscript",
    ]
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Package} ${db:Status-Status}\n", *packages],
        capture_output=True, text=True, check=False,
    )
    installed = {line.split()[0] for line in result.stdout.splitlines() if line.endswith(" installed")}
    return [package for package in packages if package not in installed]


def curl(url, *options):
    return subprocess.check_output(
        ["curl", "--fail", "--silent", "--show-error", "--location", "--retry", "2",
         "--connect-timeout", "15", "--max-time", "120", *options, url],
    )


def latest_release():
    arch = platform.machine()
    if arch not in ("x86_64", "aarch64"):
        raise ValueError(f"unsupported CodexBar architecture: {arch}")
    release = json.loads(curl(f"https://api.github.com/repos/{REPO}/releases/latest"))
    tag = release["tag_name"]
    if not re.fullmatch(f"v{VERSION}", tag) or release.get("draft") or release.get("prerelease"):
        raise ValueError(f"unexpected stable CodexBar tag: {tag}")
    assets = {asset["name"]: asset for asset in release["assets"]}
    names = [f"CodexBar{component}-{tag}-linux-{arch}.tar.gz" for component in ("CLI", "Desktop")]
    return tag[1:], [assets[name] for name in names]


def executable_version(path, name):
    try:
        output = subprocess.check_output(
            [str(path), "--version"], stderr=subprocess.DEVNULL, text=True, timeout=15,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.fullmatch(rf"{name} ({VERSION})", output)
    return match[1] if match else None


def has_cli_bundle(directory):
    return (directory / "CodexBar_CodexBarCore.bundle").is_dir() and (directory / "VERSION").is_file()


def installed_version():
    version = executable_version(CLI, "CodexBar")
    if not version or CLI.resolve() != (RELEASES / f"v{version}" / "codexbar").resolve():
        return None
    desktop_file = f"{APP_ID}.desktop"
    if (
        has_cli_bundle(CLI.resolve().parent)
        and executable_version(DESKTOP, "codexbar-linux") == version
        and (xdg_dir("XDG_DATA_HOME", ".local/share") / "applications" / desktop_file).is_file()
        and (xdg_dir("XDG_CONFIG_HOME", ".config") / "autostart" / desktop_file).is_file()
    ):
        return version
    return None


def install(version, assets):
    with tempfile.TemporaryDirectory(prefix=".install-", dir=RELEASES) as directory:
        work = Path(directory)
        archives = []
        for asset in assets:
            archive = work / asset["name"]
            digest = asset.get("digest") or ""
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise ValueError(f"missing SHA-256 digest for {archive.name}")
            curl(asset["browser_download_url"], "--output", str(archive))
            with archive.open("rb") as contents:
                actual = hashlib.file_digest(contents, "sha256").hexdigest()
            if digest != f"sha256:{actual}":
                raise ValueError(f"checksum mismatch for {archive.name}")
            archives.append(archive)

        cli_stage = work / "cli"
        desktop_stage = work / archives[1].name.removesuffix(".tar.gz")
        for archive, target in zip(archives, (cli_stage, work), strict=True):
            with tarfile.open(archive) as bundle:
                bundle.extractall(target, filter="data")
        if not has_cli_bundle(cli_stage) or executable_version(cli_stage / "codexbar", "CodexBar") != version:
            raise ValueError("CodexBar CLI bundle does not match the release")
        if executable_version(desktop_stage / "bin/codexbar-linux", "codexbar-linux") != version:
            raise ValueError("CodexBar desktop does not match the release or cannot load its Qt runtime")

        cli_release = RELEASES / f"v{version}"
        release_cli = cli_release / "codexbar"
        if not has_cli_bundle(cli_release) or executable_version(release_cli, "CodexBar") != version:
            if cli_release.exists():
                cli_release.rename(work / "previous-cli")
            cli_stage.rename(cli_release)
        subprocess.run(
            [sys.executable, str(desktop_stage / "Integrations/Linux/install.py"), "--cli", str(release_cli)],
            check=True,
        )
        with tempfile.TemporaryDirectory(prefix=".codexbar-", dir=BIN) as bin_stage:
            link = Path(bin_stage) / "codexbar"
            link.symlink_to(release_cli)
            link.replace(CLI)


def activation_status(proc=Path("/proc")):
    """Report replaced executables and libraries without stopping a user's app."""
    stale_reasons = runpy.run_path(str(Path(__file__).with_name("audit-updated-processes.py")))["stale_reasons"]
    current_cli = CLI.resolve()
    running, stale, unreadable = set(), set(), False
    for entry in proc.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            name = (entry / "comm").read_text().strip()
            if name not in {"codexbar", "codexbar-linux", "CodexBarCLI"}:
                continue
            executable = os.readlink(entry / "exe")
            path = Path(executable.removesuffix(" (deleted)"))
            if path != DESKTOP and not path.is_relative_to(RELEASES):
                continue
            running.add(name)
            reasons = stale_reasons(executable, (entry / "maps").read_text())
            if reasons or executable.endswith(" (deleted)") or (name != "codexbar-linux" and path != current_cli):
                stale.add("desktop" if name == "codexbar-linux" else "CLI")
        except PermissionError:
            unreadable = True
        except (FileNotFoundError, ProcessLookupError):
            continue
    messages = []
    if "desktop" in stale:
        messages.append("Quit and reopen CodexBar from the Plasma launcher to activate the update.")
    if "CLI" in stale:
        messages.append("Rerun any active CodexBar CLI commands to use the updated release.")
    if unreadable:
        messages.append("CodexBar process inspection was incomplete.")
    if not messages:
        messages.append("No replaced code detected in running CodexBar processes." if running else "CodexBar is inactive.")
    return " ".join(messages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("ensure", "check", "status", "missing-runtime"):
        modes.add_argument(f"--{mode}", action="store_true")
    args = parser.parse_args()
    if args.missing_runtime:
        print("\n".join(missing_runtime()))
        return 0
    if args.status:
        version = installed_version()
        print(f"CodexBar {version} desktop and CLI" if version else "CodexBar desktop or CLI needs installation or repair")
        return 0 if version else 1
    if args.check:
        latest, _ = latest_release()
        print(json.dumps({"installed": installed_version(), "available": latest}))
        return 0

    missing = missing_runtime()
    if missing:
        raise ValueError("install the CodexBar runtime through the Ansible profile: " + ", ".join(missing))
    RELEASES.mkdir(parents=True, exist_ok=True)
    with (RELEASES / ".install.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        version, assets = latest_release()
        if installed_version() == version:
            print(f"CodexBar {version} desktop and CLI are current.")
        else:
            install(version, assets)
            if installed_version() != version:
                raise ValueError("CodexBar could not verify the installed desktop and CLI pair")
            print(f"Installed CodexBar {version} desktop and CLI.")
        print(activation_status())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as error:
        sys.exit(f"CodexBar: {error}")
