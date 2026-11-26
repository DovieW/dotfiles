"""Regression checks for scoped reconciliation and Codex's native TOML writer."""
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
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
            config.write_text('model = "old" # preserve\n[mcp_servers.test]\nurl = "http://localhost:8000"\n')
            self.manifest["shared"]["mcp"]["test"] = False
            self.manifest["shared"]["plugins"]["demo@market.example"] = False
            self.manifest["shared"]["skills"]["chrome-devtools-cli"] = "off"
            app.apply(self.manifest, SOURCE, "first")
            app.apply(self.manifest, SOURCE, "first", check=True)
            text, parsed = app.config()
            self.assertIn("# preserve", text)
            self.assertEqual(parsed["mcp_servers"]["test"]["url"], "http://localhost:8000")
            self.assertFalse(parsed["mcp_servers"]["test"]["enabled"])
            self.assertFalse(parsed["plugins"]["demo@market.example"]["enabled"])
            self.assertTrue(app.skill_target("dovie-android-control"))
            app.write_config(text, [(("model_reasoning_effort",), "high")])
            self.assertEqual(app.status(self.manifest)["drift"]["model_reasoning_effort"], "high")
            with self.assertRaisesRegex(ai.Error, "Local settings"):
                app.apply(self.manifest, SOURCE, "local")
            app.apply(self.manifest, SOURCE, "local", resolve=True)
            self.assertEqual(app.status(self.manifest)["drift"], {})
