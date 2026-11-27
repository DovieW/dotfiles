"""Context measurement uses the rendered prompt and returns counts, never its text."""
from pathlib import Path
from runpy import run_path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
context = run_path(str(ROOT / "scripts/context_sizes.py"))


class ContextSizesTest(unittest.TestCase):
    def test_rendered_entries_and_deferred_tool_catalog_count_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill = root / "sample/SKILL.md"
            skill.parent.mkdir()
            skill.write_text("Sample skill instructions")
            refs = skill.parent / "references"
            refs.mkdir()
            (refs / "guide.md").write_text("reference material")
            private = "Private instruction text"
            instructions = f"# AGENTS.md instructions\n\n<INSTRUCTIONS>\n{private}\n</INSTRUCTIONS>"
            skill_line = "- sample: Shortened description (file: r0/sample/SKILL.md)\n"
            summary = "- mcp__codex_apps__sample: A connector description\n"
            catalog = f"<skills_instructions>\n- `r0` = `{root}`\n### Available skills\n{skill_line}"
            prompt = [{"content": [{"text": instructions}, {"text": catalog}, {"text": f"<tools>\n{summary}"}]}]
            schema = {"type": "object", "properties": {"query": {"type": "string"}}}
            tool = {"name": "sample.search", "description": "Search the sample database", "inputSchema": schema,
                    "_meta": {"connector_id": "connector_test"}}
            status = {"mcp": {"missing": True, "disabled": False}, "plugin_mcp": {}}
            rows, catalog_size = context["estimate_context"](
                prompt, [{"name": "sample", "path": str(skill)}], {},
                {"connector_test": {"title": "Sample App", "enabled": True}},
                [{"name": "codex_apps", "tools": {"search": tool}}],
                status, {}, len, root, root,
            )
            by_name = {row["name"]: row for row in rows}
            self.assertEqual(catalog_size, len(catalog))
            self.assertEqual(by_name["Effective AGENTS.md"]["upfront"], len(instructions))
            self.assertEqual(by_name["sample"]["upfront"], len(skill_line))
            self.assertEqual(by_name["sample"]["full"], len(skill_line) + len(skill.read_text()))
            self.assertEqual(by_name["sample"]["references"], len("reference material"))
            self.assertEqual(by_name["Sample App"]["upfront"], len(summary))
            self.assertGreater(by_name["Sample App"]["full"], len(summary))
            self.assertIsNone(by_name["missing"]["upfront"])
            self.assertIsNone(by_name["missing"]["full"])
            self.assertEqual(by_name["disabled"]["full"], 0)
            self.assertNotIn(private, repr(rows))

    def test_undocumented_line_without_description_is_still_counted(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SKILL.md"
            text = f"<skills_instructions>\n### Available skills\n- sample (file: {path})"
            _, entries, _, _, _ = context["startup_inputs"]([{"content": [{"text": text}]}])
            self.assertEqual(entries[path][0], "sample")
