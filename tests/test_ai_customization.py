"""Regression checks for scoped reconciliation and Codex's native TOML writer."""
import base64
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
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
        self.manifest["hosts"][IDEAPAD]["skills"] = {"chrome-devtools-cli": "manual"}
        local = ai.effective(self.manifest, IDEAPAD, "Private note")
        peer = ai.effective(self.manifest, DESKTOP)
        self.assertIn("This is the Kubuntu IdeaPad", local["instructions"])
        self.assertTrue(local["instructions"].endswith("Private note\n"))
        self.assertNotIn("Private note", peer["instructions"])
        self.assertEqual(local["skills"]["chrome-devtools-cli"], "manual")
        self.assertEqual(peer["skills"]["chrome-devtools-cli"], "automatic")

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

    def test_manual_skill_keeps_other_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            policy = source / "agents/openai.yaml"
            policy.parent.mkdir()
            policy.write_text("interface:\n  display_name: Example\npolicy:\n  products: [CODEX]\n")
            self.assertIn("  display_name: Example", ai.skill_policy(source, "manual"))
            self.assertIn("  allow_implicit_invocation: false", ai.skill_policy(source, "manual"))

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
            self.manifest["shared"]["skills"]["chrome-devtools-cli"] = "off"
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

    def test_config_catalog_merges_engine_schemas_and_local_values(self):
        common = {"type": "string", "description": "A setting known to both builds."}
        cli_schema = {"properties": {
            "common": common,
            "cli_only": {"type": "boolean"},
            "approval_policy": {"oneOf": [{"enum": ["on-request"]}, {"const": "never"},
                                            {"type": "object"}, {"enum": ["on-request"]}]},
            "mcp_servers": {"additionalProperties": {"$ref": "#/definitions/Server"}},
        }, "definitions": {"Server": {"properties": {
            "url": {"type": "string"},
            "args": {"items": {"properties": {"name": {"type": "string"}}}},
        }}}}
        desktop_schema = {"properties": {"common": common, "app_only": {"type": "boolean"}}}
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
        with patch.object(app, "config", return_value=("", raw)), \
                patch.object(app, "config_engines", return_value=local), \
                patch.object(app, "call_peer", return_value=peer) as probe, \
                patch.object(app, "config_schema", side_effect=[cli_schema, desktop_schema]) as schema:
            catalog = app.config_catalog(with_peer=True)
        probe.assert_called_once_with("config-engines", timeout=40)
        self.assertEqual([call.args[0] for call in schema.call_args_list], ["2.0.0", "1.0.0-alpha.1"])
        cli, desktop = f"{DESKTOP}/CLI", f"{IDEAPAD}/Desktop app"
        fields = catalog["settings"]
        self.assertEqual(set(fields["common"]["support"]), {cli, desktop})
        self.assertNotIn("value", fields["cli_only"])
        self.assertEqual(set(fields["app_only"]["support"]), {desktop})
        self.assertEqual(fields["features.future"]["support"][cli]["stage"], "experimental")
        self.assertEqual(catalog["builds"][cli]["approval_policies"], ["on-request", "never"])
        self.assertEqual(fields["unknown"]["value"], "true")
        self.assertIn("mcp_servers.<name>.args[].name", fields)
        concrete = fields['mcp_servers."test.example".url']
        self.assertEqual(set(concrete["support"]), {cli})
        self.assertEqual(concrete["value"], "Set · value hidden")
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
                '# preserve\n[plugins."sample@debug".mcp_servers.example]\nenabled = false\n'
                '[[hooks.SessionStart]]\n[[hooks.SessionStart.hooks]]\ntype = "command"\ncommand = "inline"\n')
            self.manifest["shared"]["mcp"]["fixture"] = False
            self.manifest["shared"]["plugin_mcp"]["sample@debug/example"] = "default"
            self.manifest["shared"]["skills"]["chrome-devtools-cli"] = "off"
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
