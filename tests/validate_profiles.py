#!/usr/bin/env python3
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
profiles = {}
errors = []

for path in sorted((root / "profiles").glob("*.yml")):
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        errors.append(f"{path.name}: invalid JSON-compatible YAML: {exc}")
        continue
    profiles[data.get("name")] = data
    if data.get("schema_version") != 1:
        errors.append(f"{path.name}: schema_version must be 1")
    if data.get("name") != path.stem:
        errors.append(f"{path.name}: name must match filename")
    for provider, packages in data.get("packages", {}).items():
        if packages != sorted(set(packages), key=str.casefold):
            errors.append(f"{path.name}: {provider} packages must be sorted and unique")

for name, data in profiles.items():
    for parent in data.get("inherits", []):
        if parent not in profiles:
            errors.append(f"{name}: missing parent {parent}")

if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print(f"Validated {len(profiles)} profiles.")
