"""Count the rendered Codex context and estimate its full catalog locally."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def tokenizer(requirements, home, model):
    root = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "dotfiles/context-tokenizer"
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    packages = root / f"{version}-{digest}" / "lib" / f"python{version}" / "site-packages"
    if not (packages / "tiktoken").is_dir():
        raise ValueError("The local tokenizer is unavailable. Run the AI Customization setup on this computer.")
    sys.path.insert(0, str(packages))
    os.environ["TIKTOKEN_CACHE_DIR"] = str(root / "vocabulary")
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model), False
    except KeyError:
        return tiktoken.get_encoding("o200k_base"), True


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def startup_inputs(prompt):
    """Keep the visible startup text and any inline definitions that Codex emitted."""
    instructions = []
    skill_entries = {}
    skill_catalog_size = []
    summaries = {}
    inline = {}
    for item in prompt:
        if item.get("type") == "additional_tools":
            for definition in item.get("tools", []):
                name = definition.get("name", "")
                if name.startswith("mcp__"):
                    inline.setdefault(name, []).append(compact(definition))
        for content in item.get("content", []):
            text = content.get("text", "")
            if text.startswith("# AGENTS.md instructions") and "\n<INSTRUCTIONS>\n" in text:
                instructions.append(text)
            if text.startswith("<skills_instructions>"):
                roots = dict(re.findall(r"(?m)^- `(r\d+)` = `([^\n]+)`$", text))
                for line in text.partition("### Available skills")[2].splitlines():
                    entry = re.match(r"^- (.+?) \(file: ([^()]+)\)$", line)
                    if entry:
                        summary, path = entry.groups()
                        name = summary.partition(": ")[0]
                        alias, _, relative = path.partition("/")
                        absolute = (Path(roots[alias]) / relative) if alias in roots else Path(path)
                        if absolute.is_absolute():
                            skill_entries[absolute.resolve()] = (name, line + "\n")
                skill_catalog_size.append(text)
            if text.startswith("<tools>"):
                for line in text.splitlines():
                    match = re.match(r"^- (mcp__[^: ]+):", line)
                    if match:
                        summaries.setdefault(match[1], []).append(line + "\n")
    return instructions, skill_entries, skill_catalog_size, summaries, inline


def instruction_details(text, codex, cwd, config, count):
    git = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                         capture_output=True, text=True, timeout=5)
    root = Path(git.stdout.strip()) if git.returncode == 0 else cwd
    roots = [root / part for part in cwd.relative_to(root).parents] if cwd.is_relative_to(root) else []
    directories = [codex, *reversed(roots), cwd]
    filenames = ("AGENTS.override.md", "AGENTS.md")
    fallback = tuple(config.get("project_doc_fallback_filenames") or ())
    found = []
    for index, directory in enumerate(dict.fromkeys(directories)):
        for name in filenames if index == 0 else (*filenames, *fallback):
            path = directory / name
            if not path.is_file():
                continue
            with path.open(encoding="utf-8", errors="replace") as stream:
                source = stream.read(len(text) + 1).strip()
            if source and source in text:
                found.append(f"{path}: {count(source):,} tokens")
                break
    return "Complete files matched in the rendered prompt:\n" + "\n".join(found) if found else ""


def estimate_context(prompt, native_skills, cached_skills, apps, servers, status, config, count, codex, cwd):
    instruction_text, entries, catalogs, summaries, inline = startup_inputs(prompt)
    rows = []

    def row(kind, name, upfront, full, detail="", references=None):
        rows.append({"kind": kind, "name": name, "upfront": upfront, "full": full,
                     "detail": detail, "references": references})

    if instruction_text:
        text = "\n".join(instruction_text)
        size = count(text)
        row("Instructions", "Effective AGENTS.md", size, size,
            instruction_details(text, codex, cwd, config, count))
    else:
        row("Instructions", "Effective AGENTS.md", None, None, "No recognizable instruction block in the rendered prompt.")

    skills = {Path(item["path"]).resolve(): (item["name"], item.get("enabled", True))
              for item in native_skills if item.get("path") and Path(item["path"]).is_absolute()}
    for name, item in cached_skills.items():
        skills.setdefault(Path(item["path"]).resolve(), (item["title"], item["enabled"]))
    for path, (name, _) in entries.items():
        skills.setdefault(path, (name, True))
    catalog_total = count("\n".join(catalogs)) if catalogs else None
    for path, (name, enabled) in skills.items():
        entry = entries.get(path)
        upfront = count(entry[1]) if entry else (0 if catalogs else None)
        full = references = None
        detail = str(path)
        if not enabled and not entry:
            upfront = full = 0
            detail += "\nDisabled in saved settings."
        elif path.is_file():
            full = (upfront or 0) + count(path.read_text(encoding="utf-8", errors="replace"))
            files = sorted(p for p in (path.parent / "references").rglob("*")
                           if p.suffix.lower() in {".md", ".txt"} and p.is_file() and not p.is_symlink())
            if files:
                references = sum(count(p.read_text(encoding="utf-8", errors="replace")) for p in files)
            if not entry:
                detail += "\nThe local guide is available. Its entry was absent from the rendered catalog."
        row("Skill", name, upfront, full, detail, references)

    app_config = config.get("apps") or {}
    server_config = config.get("mcp_servers") or {}
    known_apps = {name: (info["title"], app_config.get(name, {}).get("enabled", info["enabled"]))
                  for name, info in apps.items()}
    known_servers = {}
    for name, enabled in status["mcp"].items():
        known_servers[name] = (name, enabled)
    for name, settings in server_config.items():
        known_servers[name] = (name, settings.get("enabled", True))
    for name, enabled in status["plugin_mcp"].items():
        known_servers.setdefault(name.rsplit("/", 1)[-1], (name, enabled))

    definitions = {}
    for server in servers:
        server_name = server["name"]
        for tool in server.get("tools", {}).values():
            name = tool["name"]
            meta = tool.get("_meta") or {}
            visibility = (meta.get("ui") or {}).get("visibility")
            if visibility and "model" not in visibility:
                continue
            app_id = meta.get("connector_id") if server_name == "codex_apps" else None
            if app_id:
                prefix, _, short_name = name.partition(".")
                namespace = f"mcp__codex_apps__{prefix}"
                app_settings = app_config.get(app_id, {})
                known_apps.setdefault(app_id, (meta.get("connector_name") or prefix, app_settings.get("enabled", True)))
                key = "App", app_id, namespace
                name = short_name or name
                default = app_settings.get("default_tools_enabled", True)
                if not app_settings.get("tools", {}).get(name, {}).get("enabled", default):
                    continue
            else:
                known_servers.setdefault(server_name, (server_name, True))
                key = "MCP server", server_name, f"mcp__{server_name}"
                settings = server_config.get(server_name, {})
                allow = settings.get("enabled_tools")
                if name in (settings.get("disabled_tools") or ()) or (allow is not None and name not in allow):
                    continue
            definition = {"type": "function", "name": name, "description": tool.get("description") or "",
                          "parameters": tool.get("inputSchema") or {}}
            definitions.setdefault(key, []).append((name, count(compact(definition))))

    for kind, known in (("App", known_apps), ("MCP server", known_servers)):
        for key, (title, enabled) in known.items():
            matches = [(namespace, tools) for (group, identity, namespace), tools in definitions.items()
                       if group == kind and identity == key]
            if not enabled:
                row(kind, title, 0, 0, "Disabled in saved settings.")
                continue
            namespaces = {namespace for namespace, _ in matches}
            if kind == "MCP server":
                namespaces.add(f"mcp__{key}")
            summaries_size = sum(count(text) for ns in namespaces for text in summaries.get(ns, []))
            direct_size = sum(count(text) for ns in namespaces for text in inline.get(ns, []))
            upfront = summaries_size + direct_size if any(ns in summaries or ns in inline for ns in namespaces) else None
            tools = [tool for _, entries_for_namespace in matches for tool in entries_for_namespace]
            full = max(upfront or 0, summaries_size + sum(size for _, size in tools)) if tools else None
            detail = [f"{len(tools)} discoverable tools" if tools else "Tool catalog unavailable."]
            if tools:
                detail.append("Fully loaded uses catalog definitions. Codex may compact large schemas when exposing tools.")
            if namespaces & summaries.keys():
                detail.append("Upfront includes the deferred namespace description rendered by Codex.")
            if namespaces & inline.keys():
                detail.append("Upfront includes definitions embedded in Codex’s rendered input.")
            if upfront is None:
                detail.append("The rendered input did not identify the upfront contribution.")
            detail.extend(f"{name}: ≈{size:,} tokens" for name, size in sorted(tools))
            row(kind, title, upfront, full, "\n".join(detail))
    return rows, catalog_total
