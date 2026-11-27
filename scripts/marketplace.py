"""Discovery and review for the marketplaces exposed by AI Customization."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

SKILLS = "https://skills.sh"
REGISTRY = "https://registry.modelcontextprotocol.io"
ROOT = Path(__file__).resolve().parents[1]
SKILLS_PACKAGE = ROOT / "config/ai-customization/skills-sh"
PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
REF = re.compile(r"[a-f0-9]{40}")
LIMIT = 5 * 1024 * 1024
ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
HEADER_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,80}")
PLUGIN_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9_][A-Za-z0-9_.-]*")


class CatalogError(ValueError):
    pass


def https_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        return False
    try:
        url = urlsplit(value)
    except ValueError:
        return False
    return url.scheme == "https" and bool(url.hostname) and url.username is None and url.password is None


def skill_link(value):
    if not https_url(value):
        raise CatalogError("Paste a link to one skill on skills.sh.")
    url = urlsplit(value)
    parts = url.path.strip("/").split("/")
    if (url.netloc not in ("skills.sh", "www.skills.sh") or len(parts) != 3
            or not all(PART.fullmatch(part) for part in parts)):
        raise CatalogError("Use a skills.sh link with an owner, repository, and skill name.")
    return parts


def json_request(base, query):
    url = base + "?" + urlencode(query)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Dotfiles AI Customization"})
    with urlopen(request, timeout=12) as response:
        body = response.read(8 * 1024 * 1024 + 1)
    if len(body) > 8 * 1024 * 1024:
        raise CatalogError("The marketplace returned too much data. Narrow your search.")
    return json.loads(body)


def project_files(folder):
    total = 0
    digest = hashlib.sha256()
    entries = []
    for file in sorted(folder.rglob("*")):
        path = file.relative_to(folder)
        if ".git" in path.parts or file.is_symlink():
            raise CatalogError("The selected skill contains an unsupported link or Git directory.")
        if file.is_dir():
            continue
        if not file.is_file():
            raise CatalogError("The selected skill contains an unsupported file.")
        with file.open("rb") as stream:
            content = stream.read(LIMIT - total + 1)
        total += len(content)
        if total > LIMIT or len(entries) >= 500:
            raise CatalogError("The selected skill exceeds the import size or file limit.")
        executable = bool(file.stat().st_mode & 0o100)
        digest.update(json.dumps([path.as_posix(), len(content), executable]).encode() + b"\0" + content)
        entries.append(path.as_posix())
    if "SKILL.md" not in entries:
        raise CatalogError("The selected skill has no SKILL.md.")
    return digest.hexdigest(), entries


def node_path(home):
    env = dict(os.environ, PATH=f"{home}/.vite-plus/bin:" + os.environ.get("PATH", os.defpath))
    try:
        result = subprocess.check_output(["node", "-p", "process.execPath"], env=env, timeout=8, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CatalogError("The managed Node runtime is unavailable.") from exc
    return Path(result.strip())


class Catalog:
    def __init__(self, app, install_package=None):
        self.app = app
        self.install_package = install_package or SKILLS_PACKAGE

    def run(self, args, cwd, env, timeout, error):
        result = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise CatalogError(error)
        return result.stdout

    def search(self, catalog, query, cursor=None):
        if catalog == "skills":
            if len(query) < 2:
                return {"items": [], "cursor": None}
            response = json_request(SKILLS + "/api/search", {"q": query, "limit": 30})
            items = []
            for entry in response.get("skills", []):
                source = entry.get("source", "")
                slug = entry.get("skillId", "")
                parts = [*source.split("/"), slug]
                if len(parts) != 3 or not all(PART.fullmatch(part) for part in parts):
                    continue
                link = f"{SKILLS}/{source}/{slug}"
                items.append({"id": link, "title": entry.get("name") or slug, "source": source,
                              "description": f"{entry['installs']:,} installs" if type(entry.get("installs")) is int else "",
                              "url": link})
            return {"items": items, "cursor": None}
        if catalog == "mcp":
            params = {"version": "latest", "limit": 30}
            if query:
                params["search"] = query
            if cursor:
                params["cursor"] = cursor
            response = json_request(REGISTRY + "/v0.1/servers", params)
            items = []
            for entry in response.get("servers", []):
                server = entry["server"]
                items.append({"id": [server["name"], server["version"]],
                              "title": server.get("title") or server["name"], "source": server["name"],
                              "description": server.get("description", ""), "url": mcp_link(server)})
            return {"items": items, "cursor": response.get("metadata", {}).get("nextCursor")}
        if catalog != "plugins":
            raise CatalogError("Unknown marketplace.")
        with self.app.codex_rpc(self.app.home / ".local/bin/codex", experimental=True) as request:
            if query:
                payload = {"searchTerm": query, "limit": 30}
                if cursor:
                    payload["cursor"] = cursor
                response = request("plugin/search", payload)
                results = response["data"]
            else:
                response = request("plugin/list", {"marketplaceKinds": ["local"]})
                results = [dict(plugin=item, marketplaceName=market["name"],
                                marketplacePath=market.get("path"))
                           for market in response["marketplaces"] for item in market["plugins"]]
        items = []
        for result in results:
            plugin = result["plugin"]
            interface = plugin.get("interface") or {}
            remote_id = plugin.get("remotePluginId") if not result.get("marketplacePath") else None
            items.append({"id": {"pluginName": remote_id or plugin["name"],
                                 "marketplacePath": result.get("marketplacePath"),
                                 "remoteMarketplaceName": result["marketplaceName"] if not result.get("marketplacePath") else None},
                          "title": interface.get("displayName") or plugin["name"],
                          "source": result["marketplaceName"],
                          "description": interface.get("shortDescription") or "", "url": plugin_link(interface)})
        return {"items": items, "cursor": response.get("nextCursor")}

    def preview(self, catalog, identifier):
        if catalog == "skills":
            owner, repo, name = skill_link(identifier)
            source = f"{owner}/{repo}"
            revision = self.skill_revision(source)
            pin, files, overview = self.fetch_skill(name, source, revision)
            scripts = [file for file in files if file.startswith("scripts/") or Path(file).suffix in (".sh", ".py", ".js")]
            return {"name": name, "title": name, "source": source, "description": overview,
                    "url": f"{SKILLS}/{source}/{name}", "pin": pin,
                    "details": [f"Revision {revision}", f"{len(files)} files",
                                *([f"Bundled scripts: {', '.join(scripts)}"] if scripts else []), *files]}
        if catalog == "mcp":
            name, version = identifier
            server = mcp_record(name, version)
            description = server.get("description", "")
            return {"name": re.sub(r"[^A-Za-z0-9_.-]", "-", name.rsplit("/", 1)[-1]),
                    "title": server.get("title") or name, "source": name,
                    "description": description, "url": mcp_link(server),
                    "details": [f"Registry version {version}"], "choices": mcp_choices(server)}
        if catalog != "plugins":
            raise CatalogError("Unknown marketplace.")
        plugin = self.plugin_detail(identifier)
        summary = plugin["summary"]
        interface = summary.get("interface") or {}
        name = summary["id"]
        parts = []
        if summary.get("version"):
            parts.append(f"Marketplace version {summary['version']}")
        for key, label in (("skills", "Skills"), ("apps", "Apps"), ("mcpServers", "MCP servers")):
            names = [item.get("name") or item.get("title") or item.get("id") if isinstance(item, dict) else item
                     for item in plugin.get(key, [])]
            if names:
                parts.append(f"{label}: " + ", ".join(str(item) for item in names if item))
        return {"name": name, "title": interface.get("displayName") or summary["name"],
                "source": str(plugin.get("marketplaceName") or name.split("@", 1)[-1]),
                "description": interface.get("longDescription") or interface.get("shortDescription") or "",
                "url": plugin_link(interface, plugin.get("shareUrl")), "details": parts,
                "installed": summary.get("installed", False)}

    def skill_revision(self, source):
        if len(source.split("/")) != 2 or not all(PART.fullmatch(part) for part in source.split("/")):
            raise CatalogError("Invalid skill repository.")
        output = self.run(["git", "ls-remote", f"https://github.com/{source}.git", "HEAD"],
                          Path("/"), public_env(self.app.home), 12, "Could not resolve the skill repository.")
        revision = output.split(maxsplit=1)[0] if output else ""
        if not REF.fullmatch(revision):
            raise CatalogError("The source did not report a Git commit.")
        return revision

    def plugin_detail(self, identifier):
        with self.app.codex_rpc(self.app.home / ".local/bin/codex", experimental=True) as request:
            return request("plugin/read", {key: value for key, value in identifier.items() if value is not None})["plugin"]

    def skills_cli(self, node):
        lock = self.install_package / "package-lock.json"
        version = hashlib.sha256(lock.read_bytes()).hexdigest()
        root = self.app.home / ".local/share/dotfiles/skills-sh"
        def executable(path):
            return path / "node_modules/skills/bin/cli.mjs"

        target = root / version
        root.mkdir(parents=True, exist_ok=True)
        with (root / "install.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
            if executable(target).is_file():
                return executable(target)
            with tempfile.TemporaryDirectory(dir=root) as scratch:
                package = Path(scratch) / "package"
                package.mkdir()
                for name in ("package.json", "package-lock.json"):
                    shutil.copyfile(self.install_package / name, package / name)
                self.run([str(node), str(node.parent / "npm"), "ci", "--ignore-scripts", "--engine-strict",
                          "--no-audit", "--no-fund"], package,
                         dict(os.environ, PATH=f"{node.parent}:{os.defpath}"), 45,
                         "Could not install the pinned skills.sh fetcher.")
                package.rename(target)
        return executable(target)

    def fetch_skill(self, name, source, revision):
        cache = self.app.state / "marketplace-skills"
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        node = node_path(self.app.home)
        cli = self.skills_cli(node)
        with tempfile.TemporaryDirectory(dir=cache) as temp:
            stage = Path(temp)
            work = stage / "work"
            home = stage / "home"
            work.mkdir()
            home.mkdir()
            env = public_env(home, f"{node.parent}:{os.defpath}")
            self.run([str(node), str(cli), "add", f"{source}@{revision}", "--skill", name,
                      "--agent", "codex", "--yes", "--copy"], work, env, 50,
                     "Could not fetch that skill at the selected revision.")
            installed = work / ".agents/skills" / name
            lock = json.loads((work / "skills-lock.json").read_text())["skills"][name]
            if lock.get("commit") != revision or lock.get("source") != source:
                raise CatalogError("The fetcher did not confirm the requested skill revision.")
            sha256, files = project_files(installed)
            pin = {"source": source, "revision": revision, "path": lock["skillPath"], "sha256": sha256}
            import yaml

            with (installed / "SKILL.md").open() as stream:
                header = stream.read(16384).split("\n---", 1)[0].removeprefix("---\n")
            metadata = yaml.safe_load(header)
            if not isinstance(metadata, dict) or metadata.get("name") != name:
                raise CatalogError("The skill's declared name does not match the marketplace entry.")
            overview = str(metadata.get("description", ""))
            destination = cache / sha256
            with self.app.locked("marketplace-cache.lock"):
                if not destination.exists():
                    installed.rename(destination)
                elif project_files(destination)[0] != sha256:
                    raise CatalogError("A cached skill failed its checksum.")
            return pin, files, overview

    def restore(self, name, pin, check=False):
        path = self.app.state / "marketplace-skills" / pin["sha256"]
        if not path.is_dir():
            if check:
                raise CatalogError(f"The pinned source for {name} must be fetched before apply.")
            restored, _, _ = self.fetch_skill(name, pin["source"], pin["revision"])
            if restored != pin:
                raise CatalogError(f"The files for {name} differ from the reviewed skill.")
        if project_files(path)[0] != pin["sha256"]:
            raise CatalogError(f"The cached files for {name} failed their checksum.")
        return path


def public_env(home, path=os.defpath):
    return {"HOME": str(home), "PATH": path, "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_STATE_HOME": str(home / ".local/state"), "DISABLE_TELEMETRY": "1",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0", "CI": "1", "LANG": "C.UTF-8"}


def plugin_link(interface, share=None):
    return next((url for url in (share, interface.get("websiteUrl"), "https://chatgpt.com/plugins")
                 if https_url(url)), "")


def mcp_link(server):
    link = server.get("websiteUrl") or (server.get("repository") or {}).get("url")
    return link if https_url(link) else REGISTRY + "/?" + urlencode({"q": server["name"]})


def mcp_record(name, version):
    server = json_request(f"{REGISTRY}/v0.1/servers/{quote(name, safe='')}/versions/{quote(version, safe='')}", {})["server"]
    if server.get("name") != name or version != "latest" and server.get("version") != version:
        raise CatalogError("The registry returned a different server release.")
    return server


def fixed_arguments(arguments):
    args = []
    for arg in arguments:
        value = arg.get("value") or arg.get("default")
        if not isinstance(value, str) or "{" in value or arg.get("isSecret"):
            if arg.get("isRequired"):
                return None
            continue
        if arg.get("type") == "named":
            flag = arg.get("name", "")
            if not re.fullmatch(r"--?[A-Za-z][\w-]*", flag):
                return None
            args.append(flag)
        elif arg.get("type") != "positional":
            return None
        args.append(value)
    return args


def mcp_choices(server):
    choices = []
    for remote in server.get("remotes", []):
        url = remote.get("url")
        if (remote.get("type") != "streamable-http" or not https_url(url)
                or "{" in url or urlsplit(url).query):
            continue
        prefix = re.sub(r"[^A-Z0-9]+", "_", server.get("name", "server").upper()).strip("_")[-60:]
        headers = {}
        for header in remote.get("headers", []):
            if header.get("isRequired"):
                name = header.get("name", "")
                if not HEADER_NAME.fullmatch(name):
                    break
                headers[name] = f"MCP_{prefix}_{name.upper().replace('-', '_')}"
        else:
            choices.append({"label": "Remote HTTPS", "kind": "https", "url": url,
                            "headers": headers,
                            "optional_headers": [h["name"] for h in remote.get("headers", [])
                                                 if not h.get("isRequired") and HEADER_NAME.fullmatch(h.get("name", ""))]})
    packages = server.get("packages", [])
    for ecosystem in ("npm", "pypi"):
        for package in packages:
            if package.get("registryType") != ecosystem or package.get("transport", {}).get("type") != "stdio":
                continue
            identifier, version = package.get("identifier"), package.get("version")
            if not isinstance(identifier, str) or not isinstance(version, str):
                continue
            pattern = r"(?:@[a-z0-9][a-z0-9_.-]*/)?[a-z0-9][a-z0-9_.-]*" if ecosystem == "npm" else r"[A-Za-z0-9][A-Za-z0-9_.-]*"
            if not re.fullmatch(pattern, identifier) or not re.fullmatch(r"\d[\w.+-]*", version, re.ASCII):
                continue
            runtime = package.get("runtimeHint")
            if runtime and runtime != ("npx" if ecosystem == "npm" else "uvx"):
                continue
            args = fixed_arguments(package.get("packageArguments", []))
            requirements = [entry.get("name") for entry in package.get("environmentVariables", [])
                            if entry.get("isRequired")]
            if (args is None or package.get("runtimeArguments")
                    or not all(isinstance(item, str) and ENV_NAME.fullmatch(item) for item in requirements)):
                continue
            choices.append({"label": f"{ecosystem} · {identifier} {version}", "kind": ecosystem,
                            "package": identifier, "version": version, "arguments": args,
                            "env_vars": sorted(set(requirements))})
    registry = {"name": server["name"], "version": server["version"]} if "version" in server else None
    return [{**choice, "registry": registry} for choice in choices] if registry else choices


def mcp_configuration(home, choice):
    kind = choice.get("kind")
    if kind == "https":
        url = choice.get("url")
        if not https_url(url) or urlsplit(url).query or "{" in url:
            raise CatalogError("The registry needs a valid HTTPS endpoint.")
        headers = choice.get("headers", {})
        if not isinstance(headers, dict) or not all(HEADER_NAME.fullmatch(k) and ENV_NAME.fullmatch(v)
                                                    for k, v in headers.items()):
            raise CatalogError("The registry header settings are invalid.")
        result = {"url": url}
        if headers:
            result["env_http_headers"] = headers
            if not all(os.environ.get(name) for name in headers.values()):
                result["enabled"] = False
        return result
    if kind not in ("npm", "pypi"):
        raise CatalogError("Unsupported registry package type.")
    package = choice.get("package", "")
    pattern = r"(?:@[a-z0-9][a-z0-9_.-]*/)?[a-z0-9][a-z0-9_.-]*" if kind == "npm" else r"[A-Za-z0-9][A-Za-z0-9_.-]*"
    version = choice.get("version", "")
    arguments = choice.get("arguments")
    variables = choice.get("env_vars")
    if (not re.fullmatch(pattern, package) or not re.fullmatch(r"\d[\w.+-]*", version, re.ASCII)
            or not isinstance(arguments, list) or not all(isinstance(arg, str) and "\0" not in arg for arg in arguments)
            or not isinstance(variables, list) or not all(ENV_NAME.fullmatch(name) for name in variables)):
        raise CatalogError("The registry package settings are invalid.")
    if kind == "npm":
        npx = home / ".vite-plus/bin/npx"
        if not npx.is_file():
            raise CatalogError("The managed npm runner is unavailable.")
        configuration = {"command": str(npx), "args": ["--yes", "--", f"{package}@{version}", *arguments]}
    else:
        try:
            uvx = subprocess.check_output([str(ROOT / "scripts/install-marketplace-uv")], text=True,
                                          stderr=subprocess.DEVNULL, timeout=75).strip()
        except (OSError, subprocess.SubprocessError) as error:
            raise CatalogError("The pinned Python package runner could not be installed.") from error
        configuration = {"command": uvx, "args": ["--from", f"{package}=={version}", package, *arguments]}
    if variables:
        configuration["env_vars"] = variables
        if not all(os.environ.get(name) for name in variables):
            configuration["enabled"] = False
    return configuration
