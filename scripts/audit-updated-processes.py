#!/usr/bin/env python3
"""Report running installed code replaced on disk; never signal processes."""
import json
import os
from pathlib import Path


def installed_path(path):
    return path.startswith(("/usr/", "/opt/", "/lib/", "/lib64/", "/home/"))


def stale_reasons(executable, maps):
    reasons = set()
    if executable.endswith(" (deleted)") and installed_path(executable):
        reasons.add("replaced executable")
    for line in maps.splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6:
            continue
        path = fields[5]
        if path.endswith(" (deleted)") and installed_path(path) and ".so" in Path(path).name:
            reasons.add("replaced shared library")
    return sorted(reasons)


def audit(proc=Path("/proc")):
    stale, unreadable = [], 0
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            executable = os.readlink(entry / "exe")
            reasons = stale_reasons(executable, (entry / "maps").read_text())
            if reasons:
                stale.append({"pid": int(entry.name), "uid": entry.stat().st_uid,
                              "program": (entry / "comm").read_text().strip(),
                              "reasons": reasons})
        except PermissionError:
            unreadable += 1
        except (FileNotFoundError, ProcessLookupError):
            pass  # Kernel threads and processes that exited during the scan.
    return {"stale_processes": sorted(stale, key=lambda item: item["pid"]),
            "unreadable_processes": unreadable,
            "reboot_required": Path("/var/run/reboot-required").exists()}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
