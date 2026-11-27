"""Local caches for the customization window's read-only previews."""
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import tempfile


class WindowCache:
    def __init__(self, root=None):
        home = Path.home()
        cache = Path(os.environ.get("XDG_CACHE_HOME", home / ".cache"))
        codex = Path(os.environ.get("CODEX_HOME", home / ".codex")).expanduser().absolute()
        identity = sha256(json.dumps([socket.gethostname(), str(codex)]).encode()).hexdigest()
        self.root = root if root is not None else cache / "dotfiles/ai-customization" / identity

    def read(self, key):
        try:
            item = json.loads((self.root / f"{key}.json").read_text())
            payload = item.get("data")
            if item.get("version") == 1 and isinstance(payload, dict):
                return payload
        except (OSError, ValueError, AttributeError):
            pass
        return {}

    def write(self, key, data):
        temp = None
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(mode="w", dir=self.root, delete=False) as stream:
                temp = Path(stream.name)
                json.dump({"version": 1, "data": data}, stream, separators=(",", ":"))
            temp.replace(self.root / f"{key}.json")
        except OSError:
            pass
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass

    def catalog(self):
        data = self.read("config-catalog")
        return data if (isinstance(data.get("settings"), dict) and isinstance(data.get("builds"), dict)
                        and isinstance(data.get("peer_available"), bool)) else {}

    def save_catalog(self, data):
        # Persist the catalog, while reading setting values and account capabilities again for edits.
        settings = {}
        for name, setting in data["settings"].items():
            entry = {key: value for key, value in setting.items() if key not in ("value", "choice")}
            if "value" in setting:
                entry["value"] = "Previously set"
            settings[name] = entry
        builds = {name: {key: engine[key] for key in ("version", "schema", "package") if key in engine}
                  for name, engine in data["builds"].items()}
        self.write("config-catalog", {"settings": settings, "builds": builds, "peer_available": data["peer_available"]})

    @staticmethod
    def context_key(profile, project, model):
        # Keep the requested path: the other computer may resolve a symlink differently.
        path = os.path.normpath(os.path.expanduser(project))
        return "context-" + sha256(json.dumps([profile, path, model]).encode()).hexdigest()

    def context(self, profile, project, model):
        data = self.read(self.context_key(profile, project, model))
        if (data.get("profile") == profile and isinstance(data.get("measured_at"), int)
                and all(isinstance(data.get(key), str) for key in ("project", "model", "encoding"))
                and isinstance(data.get("fallback"), bool) and isinstance(data.get("tables"), dict)
                and isinstance(data.get("rows"), list) and isinstance(data.get("notes"), list)
                and (not model or data["model"] == model)):
            return data
        return {}

    def save_context(self, project, model, result):
        fields = ("upfront", "full", "references", "upfront_partial", "full_partial")

        def numbers(row):
            return {key: row[key] for key in fields if key in row} if row is not None else None

        payload = {key: result[key] for key in ("profile", "project", "model", "encoding", "fallback", "measured_at")}
        payload["rows"] = [{"kind": row["kind"], "name": row.get("name", row["kind"]), **numbers(row)}
                           for row in result["rows"]]
        payload["tables"] = {group: {name: numbers(row) for name, row in entries.items()}
                             for group, entries in result["tables"].items()}
        if "report" in result:
            report = result["report"]
            payload["report"] = {**report, "groups": [{"name": group["name"], "tokens": group["tokens"]}
                                                      for group in report["groups"]]}
        payload["notes"] = []
        payload["cached"] = True
        self.write(self.context_key(result["profile"], project, result["model"]), payload)
        if not model:
            self.write(self.context_key(result["profile"], project, ""), payload)
