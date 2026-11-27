"""Compare installed marketplace items with their source and prepare reviewed updates."""
from concurrent.futures import ThreadPoolExecutor
import difflib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlsplit

from marketplace import Catalog, CatalogError, PLUGIN_ID, mcp_choices, mcp_link, mcp_record, plugin_link


TRANSPORT_FIELDS = ("url", "command", "args")
MCP_RECEIPTS = "marketplace-mcp.json"


def transport(config):
    return {key: config[key] for key in TRANSPORT_FIELDS if key in config}


def read_json(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def mcp_receipt(choice, config):
    registry = choice.get("registry")
    if not registry:
        return None
    if (not isinstance(registry.get("name"), str) or registry["name"].count("/") != 1
            or not isinstance(registry.get("version"), str) or not registry["version"]):
        raise CatalogError("Invalid MCP Registry source.")
    return {"choice": choice, "transport": transport(config)}


def origin(url):
    address = urlsplit(url)
    return address.scheme, address.hostname, address.port or 443


def same_mcp_source(previous, proposed):
    if previous["kind"] != proposed["kind"]:
        return False
    if proposed["kind"] == "https":
        return origin(previous["url"]) == origin(proposed["url"])
    return previous["package"] == proposed["package"]


def updated_mcp(existing, generated, previous, proposed):
    """Preserve local policy, credentials and filters when the registered release changes."""
    if not same_mcp_source(previous, proposed) or previous["registry"]["name"] != proposed["registry"]["name"]:
        raise CatalogError("The MCP transport or provider changed. Review and reconfigure it manually.")
    result = existing | transport(generated)
    if proposed["kind"] == "https":
        headers = existing.get("env_http_headers", {})
        static_headers = existing.get("http_headers", {})
        required = {key: name for key, name in proposed.get("headers", {}).items() if key not in static_headers}
        old_required = previous.get("headers", {})
        merged = {key: value for key, value in headers.items()
                  if key in required or value != old_required.get(key)}
        merged = required | merged
        if merged or "env_http_headers" in existing:
            result["env_http_headers"] = merged
        new_requirements = [required[key] for key in required.keys() - old_required.keys() - headers.keys()]
    else:
        required = proposed.get("env_vars", [])
        old_required = previous.get("env_vars", [])
        custom = [key for key in existing.get("env_vars", []) if key not in old_required]
        if required or custom or "env_vars" in existing:
            result["env_vars"] = list(dict.fromkeys([*custom, *required]))
        new_requirements = set(required) - set(old_required) - set(custom) - existing.get("env", {}).keys()
    if any(not os.environ.get(key) for key in new_requirements):
        result["enabled"] = False
    return result


def file_changes(before, after):
    """Show a bounded text diff and distinguish binary or oversized changed files."""
    left = {p.relative_to(before): p for p in before.rglob("*") if p.is_file() and not p.is_symlink()}
    right = {p.relative_to(after): p for p in after.rglob("*") if p.is_file() and not p.is_symlink()}
    lines = []
    for path in sorted(left.keys() | right.keys()):
        a, b = left.get(path), right.get(path)
        if a and b and a.read_bytes() == b.read_bytes():
            if a.stat().st_mode & 0o100 != b.stat().st_mode & 0o100:
                lines.append(f"Executable permission changed · {path}")
            continue
        verb = "Modified" if a and b else "Added" if b else "Removed"
        lines.append(f"{verb} · {path}")
        try:
            if any(p.stat().st_size > 72_000 for p in (a, b) if p):
                raise ValueError("large file")
            old, new = (p.read_text().splitlines() if p else [] for p in (a, b))
            if any("\0" in line for line in (*old, *new)):
                raise ValueError("binary file")
            lines.extend(difflib.unified_diff(old, new, str(path), str(path), lineterm=""))
        except ValueError:
            lines.append("Binary or large file. Open the source to inspect it.")
        if len(lines) > 350:
            return "\n".join(lines[:350]) + "\n\nPreview shortened. Open the source for the complete diff."
    return "\n".join(lines)


def json_changes(before, after):
    left, right = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).splitlines() for value in (before, after))
    diff = "\n".join(difflib.unified_diff(left, right, "Installed", "Available", lineterm=""))
    return diff or "The provider published a new version with the same visible configuration."


def earlier_version(current, candidate):
    releases = [re.match(r"[0-9]+(?:\.[0-9]+)+", version) for version in (current, candidate)]
    if not all(releases):
        return False
    existing, reported = (tuple(map(int, match[0].split("."))) for match in releases)
    length = max(len(existing), len(reported))
    return reported + (0,) * (length - len(reported)) < existing + (0,) * (length - len(existing))


def check_skill(catalog, name, pin):
    revision = catalog.skill_revision(pin["source"])
    if revision == pin["revision"]:
        return None
    new, _, _ = catalog.fetch_skill(name, pin["source"], revision)
    if (new["sha256"], new["path"]) == (pin["sha256"], pin["path"]):
        return None
    old_files = catalog.restore(name, pin)
    new_files = catalog.restore(name, new)
    text = file_changes(old_files, new_files)
    if pin["path"] != new["path"]:
        text = f"Guide moved from {pin['path']} to {new['path']}\n\n{text}"
    return {"current": pin["revision"][:12], "available": revision[:12], "preview": text,
            "url": f"https://github.com/{pin['source']}/compare/{pin['revision']}...{revision}",
            "value": {"previous": pin, "next": new}}


def check_mcp(config, receipt):
    if not receipt or transport(config) != receipt["transport"]:
        return {"note": "This registration needs a matching Marketplace source to check its version."}
    old = receipt["choice"]
    source = old["registry"]
    server = mcp_record(source["name"], "latest")
    if server["version"] == source["version"]:
        return None
    if earlier_version(source["version"], server["version"]):
        return {"current": source["version"], "available": server["version"], "url": mcp_link(server),
                "note": "The latest registry record is older than the installed registration."}
    choices = [choice for choice in mcp_choices(server) if same_mcp_source(old, choice)]
    if not choices:
        return {"current": source["version"], "available": server["version"], "url": mcp_link(server),
                "note": "The new release needs a different endpoint origin, package, or setup. Review its listing."}
    new = next((choice for choice in choices if choice.get("url") == old.get("url")), choices[0])
    return {"current": source["version"], "available": server["version"], "url": mcp_link(server),
            "preview": server.get("description", "") + "\n\n" + json_changes(old, new),
            "value": {"previous": old, "next": new}}


def installed_plugin(app, identity):
    name, market = identity.split("@")
    cache = app.codex / "plugins/cache" / market / name
    path = max((p.parent.parent for p in cache.glob("*/.codex-plugin/plugin.json") if p.is_file()),
               key=lambda p: p.stat().st_mtime_ns, default=None)
    meta = read_json(path / ".codex-plugin/plugin.json") if path else {}
    remote = read_json(cache / ".codex-remote-plugin-install.json").get("remote_plugin_id")
    return path, meta, remote


def plugin_bundle(folder, manifest):
    def include(field, default):
        path = (folder / (manifest.get(field) or default)).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise CatalogError("The plugin component path is outside the bundle.")
        return path

    apps = read_json(include("apps", ".app.json"))
    servers = read_json(include("mcpServers", ".mcp.json"))
    return {"description": manifest.get("description", ""),
            "skills": sorted(path.parent.name for path in include("skills", "skills").glob("*/SKILL.md")),
            "apps": sorted(value.get("id") or name for name, value in apps.get("apps", {}).items()),
            "mcpServers": sorted(servers.get("mcpServers", servers)),
            "hooks": bool(manifest.get("hooks") or (folder / "hooks/hooks.json").is_file())}


def remote_plugin_detail(app, remote, market):
    # The native app server can refresh installed bundles on startup. Read the
    # catalog in a separate home with only the current access credential.
    auth = read_json(app.codex / "auth.json")
    tokens = auth.get("tokens") or {}
    if auth.get("auth_mode") != "chatgpt" or not tokens.get("access_token"):
        raise CatalogError("Remote plugin discovery needs a current Codex sign-in.")
    snapshot = {"auth_mode": "chatgpt", "last_refresh": auth.get("last_refresh"), "tokens": {
        **{key: tokens[key] for key in ("id_token", "access_token", "account_id", "oauth_provenance", "login_owner_id")
           if key in tokens},
        "refresh_token": "",
    }}
    with tempfile.TemporaryDirectory(prefix="dot-ai-plugin-preview-") as directory:
        isolated = Path(directory)
        auth_file = isolated / "auth.json"
        auth_file.touch(mode=0o600)
        auth_file.write_text(json.dumps(snapshot))
        with app.codex_rpc(app.home / ".local/bin/codex", experimental=True, codex_home=isolated) as request:
            return request("plugin/read", {"pluginName": remote, "remoteMarketplaceName": market})["plugin"]


def latest_plugin(catalog, identity, local, remote):
    name, market = identity.split("@")
    if remote:
        detail = remote_plugin_detail(catalog.app, remote, market)
        summary = detail["summary"]
        if summary["id"] != identity:
            raise CatalogError("Codex reported a different plugin identity.")
        components = {}
        for group in ("skills", "apps", "mcpServers"):
            keys = [item.get("id") or item.get("name") if isinstance(item, dict) else item
                    for item in detail.get(group, []) or []]
            components[group] = sorted(str(key) for key in keys if key)
        components["description"] = detail.get("description", "")
        components["hooks"] = bool(detail.get("hooks"))
        return summary.get("version"), components, plugin_link(summary.get("interface") or {}, detail.get("shareUrl"))
    source = (local or {}).get("source", {})
    if source.get("type") != "local":
        return None, {}, ""
    folder = Path(source["path"])
    manifest = read_json(folder / ".codex-plugin/plugin.json")
    if manifest.get("name") != name:
        return None, {}, ""
    return manifest.get("version"), plugin_bundle(folder, manifest), plugin_link(manifest.get("interface") or {})


def local_plugins(catalog):
    app = catalog.app
    result = catalog.run([str(app.home / ".local/bin/codex"), "plugin", "marketplace", "list", "--json"],
                         "/", dict(os.environ, CODEX_HOME=str(app.codex)), 15,
                         "Could not read the configured plugin marketplaces.")
    plugins = {}
    for market in json.loads(result)["marketplaces"]:
        if not market.get("root"):
            continue
        root = Path(market["root"]).resolve()
        manifest = next((root / name for name in (".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json")
                         if (root / name).is_file()), None)
        if manifest is None:
            continue
        for plugin in read_json(manifest).get("plugins", []):
            source = plugin.get("source")
            if isinstance(source, dict):
                source = source.get("path") if source.get("source") == "local" else None
            if not isinstance(source, str) or not source.startswith("./"):
                continue
            folder = (root / source).resolve()
            if folder.is_relative_to(root):
                plugins[f"{plugin['name']}@{market['name']}"] = {"source": {"type": "local", "path": str(folder)}}
    return plugins


def check_plugin(catalog, name, local):
    folder, manifest, remote = installed_plugin(catalog.app, name)
    if not folder or not manifest.get("version"):
        return {"note": "No installed plugin version is available."}
    current = manifest["version"]
    latest, components, url = latest_plugin(catalog, name, local, remote)
    if not latest:
        return {"current": current, "note": "Codex did not report an available version from this marketplace."}
    if latest == current:
        return None
    if earlier_version(current, latest):
        return {"current": current, "available": latest, "url": url,
                "note": "The catalog reports an older version than the installed plugin."}
    return {"current": current, "available": latest, "url": url,
            "preview": json_changes(plugin_bundle(folder, manifest), components),
            "value": {"previous": current, "next": latest, "remote": remote}}


def check_updates(app, settings, raw, error_type):
    catalog = Catalog(app)
    probes = [("skills", name, check_skill, (catalog, name, pin))
              for name, pin in settings["skill_pins"].items()
              if settings["skills"].get(name) in ("manual", "automatic") and app.skill_target(name)]
    receipts = read_json(app.state / MCP_RECEIPTS)
    probes += [("mcp", name, check_mcp, (entry, receipts.get(name)))
               for name, entry in raw.get("mcp_servers", {}).items() if name != "node_repl"]
    remote_cache = app.codex / "plugins/cache"
    cached_installations = {f"{path.parent.name}@{path.parent.parent.name}" for path in
                            remote_cache.glob("*/*/.codex-remote-plugin-install.json")}
    plugins = sorted(name for name in set(raw.get("plugins", {})) | cached_installations if PLUGIN_ID.fullmatch(name))
    warnings = []
    if plugins:
        try:
            local = local_plugins(catalog)
        except (error_type, OSError, ValueError, KeyError):
            local = {}
            warnings.append("Codex's local plugin catalog could not be read.")
        probes += [("plugins", name, check_plugin, (catalog, name, local.get(name))) for name in plugins]

    def inspect(probe):
        group, name, check, args = probe
        try:
            result = check(*args)
        except (error_type, OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
            result = {"note": "The installed version or its source could not be checked. Try again later."}
        return {"group": group, "name": name, "profile": app.profile, **result} if result else None

    with ThreadPoolExecutor(max_workers=5) as workers:
        results = list(workers.map(inspect, probes))
    return {"items": [row for row in results if row], "current": results.count(None), "warnings": warnings}
