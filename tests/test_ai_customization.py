"""Regression checks for scoped reconciliation and Codex's native TOML writer."""
import base64
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
loader = importlib.machinery.SourceFileLoader("ai_customization", str(ROOT / "scripts/ai-customization"))
spec = importlib.util.spec_from_loader(loader.name, loader)
ai = importlib.util.module_from_spec(spec)
loader.exec_module(ai)
SOURCE = ROOT / ai.REL
DESKTOP = "kubuntu-desktop"
IDEAPAD = "kubuntu-laptop"


class CustomizationTest(unittest.TestCase):
    def setUp(self):
        self.manifest = ai.validate(ai.load(SOURCE / ai.PREFS))

    def test_instructions_and_machine_scope(self):
        self.manifest["hosts"][IDEAPAD]["skills"] = {"chrome-toolkit": "manual"}
        local = ai.effective(self.manifest, IDEAPAD, "Private note")
        peer = ai.effective(self.manifest, DESKTOP)
        self.assertIn("This is the Kubuntu IdeaPad", local["instructions"])
        self.assertTrue(local["instructions"].endswith("Private note\n"))
        self.assertNotIn("Private note", peer["instructions"])
        self.assertEqual(local["skills"]["chrome-toolkit"], "manual")
        self.assertEqual(peer["skills"]["chrome-toolkit"], "automatic")

    def test_toolkit_policy_removes_previously_managed_browser_entries(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"CODEX_HOME": str(Path(folder) / "codex"), "XDG_STATE_HOME": str(Path(folder) / "state")}
        ):
            app = ai.Customization(DESKTOP, Path(folder))
            old_entries = ["chrome-devtools-cli", "playwright-cli"]
            source = SOURCE / "skills/chrome-toolkit"
            for name in old_entries:
                app.install_skill(source, name, ai.skill_policy(source, "automatic"))
            ai.atomic(app.state / "applied.json", ai.encode({"skills": old_entries}))
            with patch.object(app, "write_config"):
                app.apply(self.manifest, SOURCE, "toolkit")
            self.assertTrue(app.skill_target("chrome-toolkit"))
            self.assertTrue(set(old_entries).isdisjoint(app.status(self.manifest)["skills"]))

    def test_independent_edits_merge_and_overlapping_edits_stop(self):
        local = copy.deepcopy(self.manifest)
        remote = copy.deepcopy(self.manifest)
        local["hosts"][DESKTOP]["mcp"] = {"filmcraft": False}
        remote["hosts"][IDEAPAD]["plugins"] = {"x@market": False}
        result = ai.merge(self.manifest, local, remote)
        self.assertFalse(result["hosts"][DESKTOP]["mcp"]["filmcraft"])
        self.assertFalse(result["hosts"][IDEAPAD]["plugins"]["x@market"])
        remote["hosts"][DESKTOP]["mcp"] = {"filmcraft": True}
        with self.assertRaises(ai.Error):
            ai.merge(self.manifest, local, remote)

    def test_app_owned_server_cannot_be_adopted(self):
        self.manifest["shared"]["mcp"]["node_repl"] = False
        with self.assertRaisesRegex(ai.Error, "Codex app"):
            ai.validate(self.manifest)

    def test_plugin_content_inventory_reports_native_policies(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"CODEX_HOME": folder}):
            app = ai.Customization(DESKTOP, Path(folder))
            release = app.codex / "plugins/cache/market/demo/1.0.0"
            manifest = release / ".codex-plugin/plugin.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(ai.encode({"name": "demo", "skills": "./skills", "apps": "./.app.json",
                                           "interface": {"displayName": "Demo App", "longDescription": "About the plugin"}}))
            (release / ".mcp.json").write_text(ai.encode({"mcpServers": {"demo_server": {}}}))
            (release / ".app.json").write_text(ai.encode({"apps": {"demo": {"id": "app_demo",
                                                                            "description": "About this app"}}}))
            skill = release / "skills/example/SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: example\ndescription: Sample workflow\n---\n")
            original = {"skills": {"config": [{"path": str(skill), "enabled": True},
                                               {"name": "example", "enabled": True}]}}
            overrides = ai.skill_overrides(original, {"example": False})
            self.assertEqual(overrides, [{"path": str(skill), "enabled": True},
                                         {"name": "example", "enabled": False}])
            self.assertEqual(ai.skill_overrides({"skills": {"config": overrides}}, {"example": False}), overrides)
            (app.codex / "config.toml").write_text(
                '[[skills.config]]\nname = "example"\nenabled = false\n[apps.app_demo]\nenabled = false\n')
            rows = app.plugin_content()
            self.assertEqual(rows["apps"]["app_demo"]["title"], "Demo App")
            self.assertEqual(rows["apps"]["app_demo"]["description"], "About this app")
            self.assertEqual(rows["plugins"]["demo@market"]["description"], "About the plugin")
            self.assertEqual(rows["plugin_skills"]["example"]["description"], "Sample workflow")
            self.assertFalse(rows["apps"]["app_demo"]["enabled"])
            self.assertFalse(rows["plugin_skills"]["example"]["enabled"])
            status = app.status(self.manifest)
            self.assertEqual(status["manifest"], self.manifest)
            self.assertTrue(status["plugin_mcp"]["demo@market/demo_server"])

    def test_integration_tool_policy_keeps_unrelated_filters(self):
        config = {"mcp_servers": {"demo": {"disabled_tools": ["keep_off", "read"], "enabled_tools": ["old"]}}}
        policies = {"mcp|demo|read": True, "mcp|demo|write": False, "apps|connector_demo|repo/list": False,
                    "plugin_mcp|sample@market/server|ping": False}
        self.manifest["shared"]["tool_states"] = policies
        ai.validate(self.manifest)
        changes = dict(ai.tool_changes(config, policies, {"sample@market/server"}))
        self.assertEqual(changes[("mcp_servers", "demo", "disabled_tools")], ["keep_off", "write"])
        self.assertEqual(changes[("mcp_servers", "demo", "enabled_tools")], ["old", "read"])
        self.assertFalse(changes[("apps", "connector_demo", "tools", "repo/list", "enabled")])
        self.assertEqual(changes[("plugins", "sample@market", "mcp_servers", "server", "disabled_tools")],
                         ["ping"])

    def test_app_catalog_identifier_migrates_existing_scope(self):
        suffix = "a" * 32
        self.manifest["shared"]["apps"] = {"asdk_app_" + suffix: False}
        ai.validate(self.manifest)
        self.assertEqual(self.manifest["shared"]["apps"], {"connector_" + suffix: False})

    def test_manual_skill_keeps_other_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            policy = source / "agents/openai.yaml"
            policy.parent.mkdir()
            policy.write_text("interface:\n  display_name: Example\npolicy:\n  products: [CODEX]\n")
            self.assertIn("  display_name: Example", ai.skill_policy(source, "manual"))
            self.assertIn("  allow_implicit_invocation: false", ai.skill_policy(source, "manual"))

    @unittest.skipUnless((Path.home() / ".local/bin/codex").is_file(), "managed Codex is unavailable")
    def test_reviewed_mcp_and_plugin_updates_preserve_local_settings(self):
        from marketplace_updates import MCP_RECEIPTS, check_plugin, installed_plugin, local_plugins
        from marketplace import Catalog

        codex = (Path.home() / ".local/bin/codex").resolve()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "CODEX_HOME": str(Path(folder) / "codex"), "XDG_STATE_HOME": str(Path(folder) / "state"),
        }):
            home = Path(folder)
            launcher = home / ".local/bin/codex"
            launcher.parent.mkdir(parents=True)
            launcher.symlink_to(codex)
            app = ai.Customization(DESKTOP, home)
            app.codex.mkdir()
            app.manifest = lambda: self.manifest
            origin = "https://example.test"
            old = {"kind": "https", "url": origin + "/v1", "registry": {"name": "example.test/demo", "version": "1.0.0"}}
            new = {"kind": "https", "url": origin + "/v2", "registry": {"name": "example.test/demo", "version": "2.0.0"}}
            server = ("mcp_servers", "fixture")
            request = {"group": "mcp", "name": "fixture", "operation": "add", "value": old}
            self.assertEqual(app.entry_result(request), {"ok": True})
            app.write_config(app.config()[0], [((*server, "disabled_tools"), ["unwanted"]), ((*server, "enabled"), False)])
            update = {**request, "operation": "update", "value": {"previous": old, "next": new}}
            self.assertEqual(app.entry_result(update), {"ok": True})
            self.assertEqual(app.entry_result(update), {"ok": True})
            updated = ai.setting(app.config()[1], server)
            self.assertEqual(updated, {"url": origin + "/v2", "enabled": False, "disabled_tools": ["unwanted"]})
            self.assertEqual(ai.load(app.state / MCP_RECEIPTS)["fixture"]["choice"], new)
            app.write_config(app.config()[0], [((*server, "url"), origin + "/private-setting")])
            self.assertIn("changed after review", app.entry_result(update)["error"])

            market = home / "market"
            manifest = market / ".agents/plugins/marketplace.json"
            plugin = market / "plugins/fixture/.codex-plugin/plugin.json"
            ai.atomic(manifest, ai.encode({"name": "fixture-market", "plugins": [
                {"name": "fixture", "source": {"source": "local", "path": "./plugins/fixture"}}]}))
            ai.atomic(plugin, ai.encode({"name": "fixture", "version": "1.0.0", "description": "Old fixture"}))
            subprocess.run([str(codex), "plugin", "marketplace", "add", "./market", "--json"],
                           cwd=home, check=True, capture_output=True, timeout=20)
            name = "fixture@fixture-market"
            request = {"group": "plugins", "name": name, "operation": "add"}
            self.assertEqual(app.entry_result(request), {"ok": True})
            app.write_config(app.config()[0], [(("plugins", name, "enabled"), False),
                                               (("plugins", name, "mcp_servers", "keep"), {"enabled": False})])
            ai.atomic(plugin, ai.encode({"name": "fixture", "version": "1.1.0", "description": "New fixture"}))
            catalog = Catalog(app)
            available = check_plugin(catalog, name, local_plugins(catalog)[name])
            self.assertIn("New fixture", available["preview"])
            self.assertEqual(installed_plugin(app, name)[1]["version"], "1.0.0")
            request.update(operation="update", value=available["value"])
            self.assertEqual(app.entry_result(request), {"ok": True})
            self.assertEqual(app.entry_result(request), {"ok": True})
            self.assertIsNone(check_plugin(catalog, name, local_plugins(catalog)[name]))
            self.assertEqual(app.config()[1]["plugins"][name], {"enabled": False, "mcp_servers": {"keep": {"enabled": False}}})

    def test_skill_link_is_generated_and_removed_for_the_selected_host(self):
        parent, child = "chrome-toolkit", "dovie-android-control"
        source = SOURCE / "skills" / parent / "SKILL.md"
        original = source.read_text()
        reference = f"~/.agents/skills/{child}/SKILL.md"
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
            "CODEX_HOME": str(Path(folder) / "codex"), "XDG_STATE_HOME": str(Path(folder) / "state"),
        }):
            app = ai.Customization(DESKTOP, Path(folder))
            self.manifest["shared"]["skill_links"] = {f"{parent}/{child}": True}
            ai.validate(self.manifest)
            with patch.object(app, "write_config"):
                app.apply(self.manifest, SOURCE, "linked")
                installed = app.skills / parent / "SKILL.md"
                self.assertIn(reference, installed.read_text())
                self.assertIn("allow_implicit_invocation: false", (app.skills / child / "agents/openai.yaml").read_text())
                ai.remove_policies(self.manifest, {"group": "skills", "name": child, "scope": DESKTOP})
                app.apply(self.manifest, SOURCE, "removed")
                self.assertEqual(installed.read_text(), original)
            peer = ai.effective(self.manifest, IDEAPAD)
            self.assertEqual(ai.skill_references(peer), {parent: [child]})
            self.assertEqual(source.read_text(), original)

    @unittest.skipUnless((Path.home() / ".local/bin/codex").is_file(), "managed Codex is unavailable")
    def test_native_write_keeps_unmanaged_settings_and_detects_drift(self):
        real_codex = Path.home() / ".local/bin/codex"
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"CODEX_HOME": str(Path(folder) / "codex"), "XDG_STATE_HOME": str(Path(folder) / "state")}
        ):
            home = Path(folder)
            (home / ".local/bin").mkdir(parents=True)
            (home / ".local/bin/codex").symlink_to(real_codex.resolve())
            app = ai.Customization(DESKTOP, home)
            app.codex.mkdir()
            config = app.codex / "config.toml"
            config.write_text('model = "old" # preserve\n[mcp_servers.test]\nurl = "http://localhost:8000"\n'
                              '[plugins."demo@market.example"]\nenabled = true\n')
            self.manifest["shared"]["mcp"]["test"] = False
            self.manifest["shared"]["plugins"]["demo@market.example"] = False
            self.manifest["shared"]["plugins"]["absent@market.example"] = False
            app.apply(self.manifest, SOURCE, "first")
            app.apply(self.manifest, SOURCE, "first", check=True)
            text, parsed = app.config()
            self.assertIn("# preserve", text)
            self.assertEqual(parsed["mcp_servers"]["test"]["url"], "http://localhost:8000")
            self.assertFalse(parsed["mcp_servers"]["test"]["enabled"])
            self.assertFalse(parsed["plugins"]["demo@market.example"]["enabled"])
            self.assertNotIn("absent@market.example", parsed["plugins"])
            self.assertTrue(app.skill_target("dovie-android-control"))
            app.write_config(text, [(("model_reasoning_effort",), "high")])
            self.assertEqual(app.status(self.manifest)["drift"]["model_reasoning_effort"], "high")
            with self.assertRaisesRegex(ai.Error, "Local settings"):
                app.apply(self.manifest, SOURCE, "local")
            app.apply(self.manifest, SOURCE, "local", resolve=True)
            self.assertEqual(app.status(self.manifest)["drift"], {})

    def test_scoped_mutation_reports_both_hosts(self):
        app = ai.Customization(DESKTOP)
        request = {"scope": "shared", "group": "mcp", "operation": "add", "name": "fixture",
                   "value": "https://example.org/mcp"}
        with patch.object(app, "entry_result", return_value={"ok": True}) as local, \
                patch.object(app, "call_peer", return_value={}) as peer:
            results = app.edit_scope(request)
            local.assert_called_once_with(request)
            self.assertEqual(peer.call_args.args, ("entry-local",))
            self.assertEqual(json.loads(peer.call_args.kwargs["data"]), request)
            self.assertEqual(results[DESKTOP], {"ok": True})
            self.assertIn("error", results[IDEAPAD])
            local.reset_mock()
            self.assertEqual(set(app.edit_scope({**request, "scope": IDEAPAD})), {IDEAPAD})
            local.assert_not_called()

    def test_removing_scoped_plugin_preserves_other_hosts_and_clears_its_server_policies(self):
        shared = self.manifest["shared"]
        shared["plugins"] = {"example@store": True, "keep@store": False}
        shared["plugin_mcp"] = {"example@store/tools": False, "keep@store/tools": True}
        self.manifest["hosts"][IDEAPAD]["plugins"] = {"example@store": False}
        removal = {"group": "plugins", "name": "example@store", "scope": DESKTOP}
        ai.remove_policies(self.manifest, removal)
        desktop = ai.effective(self.manifest, DESKTOP)
        laptop = ai.effective(self.manifest, IDEAPAD)
        self.assertEqual(desktop["plugins"], {"keep@store": False})
        self.assertEqual(desktop["plugin_mcp"], {"keep@store/tools": True})
        self.assertFalse(laptop["plugins"]["example@store"])
        self.assertFalse(laptop["plugin_mcp"]["example@store/tools"])
        ai.remove_policies(self.manifest, {**removal, "scope": "shared"})
        self.assertNotIn("example@store", ai.effective(self.manifest, IDEAPAD)["plugins"])
        self.assertNotIn("example@store/tools", ai.effective(self.manifest, IDEAPAD)["plugin_mcp"])

    def test_pending_removals_retry_only_the_host_that_failed(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"XDG_STATE_HOME": str(Path(folder) / "state")}
        ):
            app = ai.Customization(DESKTOP, Path(folder))
            jobs = app.state / "pending-removals.json"
            request = {"group": "mcp", "name": "fixture", "operation": "remove", "revision": "a" * 40}
            ai.atomic(jobs, ai.encode([{"id": profile, "request": {**request, "scope": profile}}
                                       for profile in (DESKTOP, IDEAPAD)]))
            with patch.object(app, "edit_scope", side_effect=[{DESKTOP: {"ok": True}},
                                                            {IDEAPAD: {"error": "Offline"}}]) as execute:
                report = app.finish_removals()
            self.assertEqual([item["profile"] for item in report], [DESKTOP, IDEAPAD])
            self.assertEqual(execute.call_count, 2)
            self.assertEqual([job["id"] for job in ai.load(jobs)], [IDEAPAD])
            with patch.object(app, "edit_scope", return_value={IDEAPAD: {"ok": True}}) as retry:
                app.finish_removals()
            retry.assert_called_once_with({**request, "scope": IDEAPAD})
            self.assertFalse(jobs.exists())

    def test_marketplace_install_queue_retries_only_failed_scope(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"XDG_STATE_HOME": folder}):
            app = ai.Customization(DESKTOP, Path(folder))
            queue = app.state / "pending-installs.json"
            request = {"group": "mcp", "name": "sample", "operation": "add",
                       "value": {"kind": "https", "url": "https://example.test/mcp"}, "scope": "shared"}
            draft = {"base": self.manifest, "desired": self.manifest, "installs": [request]}
            revision = "a" * 40
            with patch.object(app, "git", return_value=subprocess.CompletedProcess([], 0, stdout=revision.encode())), \
                    patch.object(app, "manifest", return_value=self.manifest), \
                    patch.object(app, "edit_scope") as execute:
                app.publish(draft)
                execute.assert_not_called()
            with patch.object(app, "edit_scope", side_effect=[{DESKTOP: {"ok": True}}, {IDEAPAD: {"error": "Offline"}}]):
                self.assertEqual(len(app.finish_entries("installs")), 2)
            self.assertEqual([job["request"]["scope"] for job in ai.load(queue)], [IDEAPAD])
            with patch.object(app, "edit_scope", return_value={IDEAPAD: {"ok": True}}) as retry:
                app.finish_entries("installs")
            retry.assert_called_once_with({**request, "scope": IDEAPAD})
            self.assertFalse(queue.exists())

    def test_scoped_pinned_skill_removal_keeps_peer_pin(self):
        pin = {"source": "owner/repo", "path": "skills/example/SKILL.md",
               "revision": "a" * 40, "sha256": "b" * 64}
        self.manifest["shared"]["skill_pins"] = {"example": pin}
        self.manifest["shared"]["skills"]["example"] = "manual"
        ai.validate(self.manifest)
        ai.remove_policies(self.manifest, {"scope": DESKTOP, "group": "skills", "name": "example"})
        self.assertNotIn("example", ai.effective(self.manifest, DESKTOP)["skill_pins"])
        self.assertEqual(ai.effective(self.manifest, IDEAPAD)["skill_pins"]["example"], pin)

    def test_publish_queues_removals_after_pushing_policy(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"XDG_STATE_HOME": str(Path(folder) / "state")}
        ):
            app = ai.Customization(DESKTOP, Path(folder))
            self.manifest["shared"]["mcp"] = {"fixture": True}
            draft = {"base": self.manifest, "desired": self.manifest, "removals": [
                {"group": "mcp", "name": "fixture", "operation": "remove", "scope": "shared"},
            ]}
            revision = "a" * 40
            pending = app.state / "pending-removals.json"
            pushed = []

            def git(*args, **kwargs):
                if args[:2] == ("worktree", "add"):
                    (Path(args[-2]) / ai.REL).mkdir(parents=True)
                if args[0] == "push":
                    pushed.append(ai.load(kwargs["cwd"] / ai.REL / ai.PREFS))
                    self.assertFalse(pending.exists())
                return subprocess.CompletedProcess(args, 0, stdout=revision.encode())

            with patch.object(app, "git", side_effect=git), \
                    patch.object(app, "manifest", return_value=self.manifest), \
                    patch.object(app, "apply"), patch.object(app, "edit_scope") as execute, \
                    patch.object(ai, "run", return_value=subprocess.CompletedProcess([], 0)):
                self.assertEqual(app.publish(draft), revision)
                execute.assert_not_called()
            self.assertEqual(pushed[0]["shared"]["mcp"], {})
            self.assertEqual({job["request"]["scope"] for job in ai.load(pending)}, {DESKTOP, IDEAPAD})
            self.assertTrue(all(job["request"]["revision"] == revision for job in ai.load(pending)))

    def test_config_catalog_merges_engine_schemas_and_local_values(self):
        common = {"type": "string", "description": "A setting known to both builds."}
        cli_schema = {"properties": {
            "common": common,
            "cli_only": {"type": "boolean"},
            "approval_policy": {"oneOf": [{"enum": ["on-request"]}, {"const": "never"},
                                            {"type": "object"}, {"enum": ["on-request"]}]},
            "mcp_servers": {"description": "Configure MCP servers.",
                            "additionalProperties": {"$ref": "#/definitions/Server"}},
        }, "definitions": {"Server": {"properties": {
            "url": {"type": "string"},
            "args": {"items": {"properties": {"name": {"type": "string"}}}},
        }}}}
        desktop_schema = {"properties": {"common": {**common, "description": "The desktop description."},
                                         "app_only": {"type": "boolean"}}}
        local = {"profile": DESKTOP, "engines": {
            "CLI": {"version": "2.0.0", "features": {"future": {"stage": "experimental", "enabled": False}}},
        }}
        peer = {"profile": IDEAPAD, "engines": {
            "Desktop app": {"version": "1.0.0-alpha.1", "features": {}},
        }}
        app = ai.Customization(DESKTOP)
        raw = {"common": "enabled", "unknown": True, "mcp_servers": {
            "test.example": {"url": "https://private.example/path", "args": [{"name": "private-arg"}]},
        }}
        reference = ai.reference_fields({"mcp_servers.<id>.url": "URL of the server."})
        with patch.object(app, "config", return_value=("", raw)), \
                patch.object(app, "config_engines", return_value=local), \
                patch.object(app, "call_peer", return_value=peer) as probe, \
                patch.object(app, "config_help_sources", return_value=(reference, {"2.0.0": {"future": "A beta feature."}})), \
                patch.object(app, "config_schema", side_effect=[cli_schema, desktop_schema]) as schema:
            catalog = app.config_catalog(with_peer=True)
        probe.assert_called_once_with("config-engines", timeout=40)
        self.assertEqual([call.args[0] for call in schema.call_args_list], ["2.0.0", "1.0.0-alpha.1"])
        cli, desktop = f"{DESKTOP}/CLI", f"{IDEAPAD}/Desktop app"
        fields = catalog["settings"]
        self.assertEqual(set(fields["common"]["support"]), {cli, desktop})
        self.assertEqual([note["text"] for note in fields["common"]["documentation"]],
                         [common["description"], "The desktop description."])
        self.assertNotIn("value", fields["cli_only"])
        self.assertEqual(set(fields["app_only"]["support"]), {desktop})
        self.assertEqual(fields["features.future"]["support"][cli]["stage"], "experimental")
        self.assertEqual(fields["features.future"]["documentation"][0]["text"], "A beta feature.")
        self.assertEqual(catalog["builds"][cli]["approval_policies"], ["on-request", "never"])
        self.assertEqual(fields["unknown"]["value"], "true")
        self.assertEqual(fields["unknown"]["documentation"], [])
        self.assertIn("mcp_servers.<name>.args[].name", fields)
        concrete = fields['mcp_servers."test.example".url']
        self.assertEqual(set(concrete["support"]), {cli})
        self.assertEqual(concrete["value"], "Set · value hidden")
        self.assertEqual(concrete["documentation"][0]["text"], "URL of the server.")
        self.assertEqual(fields["mcp_servers.<name>.args[].name"]["documentation"][0]["related"], "mcp_servers")
        self.assertNotIn("private.", json.dumps(catalog))

    def test_config_catalog_follows_installed_schema_and_hides_retired_keys(self):
        app = ai.Customization(DESKTOP)
        def installed(version, stage):
            return {"profile": DESKTOP, "engines": {"CLI": {"version": version, "features": {
                "past": {"stage": stage, "enabled": False},
            }}}}

        old = {"properties": {"mode": {"enum": ["first", "second"]}, "old_key": {"type": "boolean"}}}
        new = {"properties": {
            "mode": {"oneOf": [{"enum": ["second", "new"]}, {"deprecated": True, "enum": ["first"]}]},
            "retired": {"deprecated": True, "enum": ["past"]},
            "lists": {"type": "array", "items": {"enum": ["left", "right"]}},
            "future": {"type": "boolean"},
        }}
        with patch.object(app, "config_engines", side_effect=[installed("1.0.0", "stable"),
                                                              installed("2.0.0", "removed")]), \
                patch.object(app, "config_schema", side_effect=[old, new]), \
                patch.object(app, "config_help_sources", return_value=({}, {})), \
                patch.object(app, "config", return_value=("", {"old_key": False})):
            first = app.config_catalog(with_peer=False)["settings"]
            second = app.config_catalog(with_peer=False)["settings"]
        cli = f"{DESKTOP}/CLI"
        self.assertEqual(first["mode"]["options"][cli]["values"], ["first", "second"])
        self.assertEqual(second["mode"]["options"][cli]["values"], ["second", "new"])
        self.assertEqual(second["future"]["options"][cli]["values"], [True, False])
        self.assertEqual(second["lists"]["options"][cli], {"multiple": True, "values": ["left", "right"]})
        self.assertNotIn("lists[]", second)
        self.assertNotIn("features.past", second)
        self.assertNotIn("retired", second)
        self.assertEqual(second["old_key"]["support"], {})
        self.assertEqual(second["old_key"]["value"], "false")

    def test_config_help_decodes_reference_and_feature_descriptions(self):
        page = r'''
## `config.toml`
<ConfigTable options={[
  {
    key: "tools.<id>.enabled",
    description:
      "Enable the tool for this profile. Enter \"true\" to include it.",
  },
]}/>
## `requirements.toml`
<ConfigTable options={[
  {
    key: "tools.<id>.enabled",
    description: "Enforce the policy.",
  },
]}/>
'''
        fields = ai.reference_fields(ai.reference_descriptions(page))
        self.assertEqual(fields[("tools", "<name>", "enabled")]["text"],
                         'Enable the tool for this profile. Enter "true" to include it.')
        registry = '''
pub enum Feature {
    /// Show a status line.
    /// It supports custom labels.
    StatusLine,
    Undocumented,
}
FeatureSpec {
    id: Feature::StatusLine,
    key: "status_line",
},
FeatureSpec {
    id: Feature::Undocumented,
    key: "undocumented",
},
'''
        self.assertEqual(ai.feature_descriptions(registry),
                         {"status_line": "Show a status line.\nIt supports custom labels."})

    def test_skill_import_and_recoverable_remove(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"XDG_STATE_HOME": str(Path(folder) / "state")}
        ):
            app = ai.Customization(DESKTOP, Path(folder))
            request = {"group": "skills", "name": "fixture", "operation": "add", "value": {
                "SKILL.md": {"content": base64.b64encode(b"# Example").decode(), "executable": False},
                "scripts/example": {"content": base64.b64encode(b"exit 0").decode(), "executable": True},
            }}
            self.assertEqual(app.entry_result(request), {"ok": True})
            self.assertEqual(app.entry_result(request), {"ok": True})
            path = app.skills / "fixture"
            self.assertTrue((path / "scripts/example").stat().st_mode & 0o100)
            invalid = {**request, "name": "bad", "value": {**request["value"],
                       "../outside": request["value"]["SKILL.md"]}}
            self.assertIn("unsafe", app.entry_result(invalid)["error"])
            self.assertEqual(app.entry_result({**request, "operation": "remove"}), {"ok": True})
            self.assertFalse(path.exists())
            backup, = (app.state / "removed-skills").iterdir()
            self.assertEqual((backup / "SKILL.md").read_text(), "# Example")

    def test_config_choice_edits_indexed_field_without_replacing_its_siblings(self):
        raw = {"entries": [{"settings": {"mode": "old", "other": True}}, {"mode": "second"}]}
        path = ("entries", 0, "settings", "mode")
        key, result = ai.config_edit(raw, path, "new")
        self.assertEqual(key, ("entries",))
        self.assertEqual(result, [{"settings": {"mode": "new", "other": True}}, {"mode": "second"}])
        self.assertEqual(raw["entries"][0]["settings"]["mode"], "old")
        _, result = ai.config_edit(raw, path, None)
        self.assertEqual(result[0]["settings"], {"other": True})
        with self.assertRaisesRegex(ai.Error, "no longer exists"):
            ai.config_edit(raw, ("entries", 3, "mode"), "new")

    @unittest.skipUnless((Path.home() / ".local/bin/codex").is_file(), "managed Codex is unavailable")
    def test_native_entry_changes_in_isolated_home(self):
        real_codex = Path.home() / ".local/bin/codex"
        with tempfile.TemporaryDirectory() as folder, patch.dict(
            os.environ, {"CODEX_HOME": str(Path(folder) / "codex"), "XDG_STATE_HOME": str(Path(folder) / "state")}
        ):
            home = Path(folder)
            launcher = home / ".local/bin/codex"
            launcher.parent.mkdir(parents=True)
            launcher.symlink_to(real_codex.resolve())
            app = ai.Customization(DESKTOP, home)
            app.codex.mkdir()
            (app.codex / "config.toml").write_text(
                'model = "old" # preserve\n[plugins."sample@debug".mcp_servers.example]\nenabled = false\n'
                '[[hooks.SessionStart]]\n[[hooks.SessionStart.hooks]]\ntype = "command"\ncommand = "inline"\n')
            self.manifest["shared"]["mcp"]["fixture"] = False
            self.manifest["shared"]["plugin_mcp"]["sample@debug/example"] = "default"
            app.manifest = lambda: self.manifest

            def edit(group, name, operation, value=None):
                self.assertEqual(app.entry_result({"group": group, "operation": operation,
                                                  "name": name, "value": value}), {"ok": True})

            edit("mcp", "fixture", "add", '/bin/echo "two words"')
            self.assertEqual(app.config()[1]["mcp_servers"]["fixture"],
                             {"command": "/bin/echo", "args": ["two words"], "enabled": False})
            edit("hooks", "SessionStart", "add", {"handler": {"type": "command", "command": "user"}})
            edit("hooks", "SessionStart", "add", {"handler": {"type": "command", "command": "user"}})
            edit("hooks", "SessionStart", "add", {"handler": {"type": "command", "command": "keep"}})
            entries = {entry["description"]: key for key, entry in app.status()["hook_entries"].items()}
            self.assertEqual(len(entries), 3)
            edit("hooks", entries["inline"], "remove")
            edit("hooks", entries["user"], "remove")
            self.assertEqual(list(app.status()["hook_entries"]), [entries["keep"]])
            app.apply(self.manifest, SOURCE, "test")
            self.assertIsNone(ai.setting(app.config()[1], ("plugins", "sample@debug", "mcp_servers", "example", "enabled")))
            plugin_servers = ("plugins", "sample@debug", "mcp_servers")
            app.write_config(app.config()[0], [((*plugin_servers, "keep"), {"enabled": False})])
            edit("plugin_mcp", "sample@debug/example", "remove")
            servers = ai.setting(app.config()[1], plugin_servers)
            self.assertNotIn("example", servers)
            self.assertFalse(servers["keep"]["enabled"])
            edit("mcp", "fixture", "remove")
            self.assertFalse(app.status()["drift"])
            self.assertIn("# preserve", app.config()[0])

            engines = {"engines": {"CLI": {"version": "1.0.0", "features": {}}}}
            schema = {"properties": {"web_search": {"enum": ["disabled", "cached", "live"]}}}
            with patch.object(app, "config_engines", return_value=engines), \
                    patch.object(app, "config_schema", return_value=schema):
                edit("config", "web_search", "add", {"path": ["web_search"], "choice": "cached"})
                self.assertEqual(app.config()[1]["web_search"], "cached")
                with self.assertRaisesRegex(ai.Error, "does not match"):
                    app.edit_config_choice(["web_search"], "unknown")
                self.assertEqual(app.config()[1]["web_search"], "cached")
                edit("config", "web_search", "remove", {"path": ["web_search"]})
                self.assertNotIn("web_search", app.config()[1])

            market = home / "market"
            plugin = market / "plugins/fixture/.codex-plugin/plugin.json"
            plugin.parent.mkdir(parents=True)
            plugin.write_text(json.dumps({"name": "fixture", "version": "1.0.0", "description": "Fixture"}))
            index = market / ".agents/plugins/marketplace.json"
            index.parent.mkdir(parents=True)
            index.write_text(json.dumps({"name": "fixture-market", "plugins": [
                {"name": "fixture", "source": {"source": "local", "path": "./plugins/fixture"}}]}))
            subprocess.run([str(launcher), "plugin", "marketplace", "add", str(market)],
                           cwd="/", check=True, capture_output=True)
            edit("plugins", "fixture@fixture-market", "add")
            self.assertTrue(app.status()["plugin_installed"]["fixture@fixture-market"])
            edit("plugins", "fixture@fixture-market", "remove")
            self.assertNotIn("fixture@fixture-market", app.status()["plugins"])
