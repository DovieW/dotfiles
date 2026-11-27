"""Context measurement uses the rendered prompt and returns counts, never its text."""
from pathlib import Path
from runpy import run_path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
context = run_path(str(ROOT / "scripts/context_sizes.py"))


class ContextSizesTest(unittest.TestCase):
    def test_context_report_counts_each_rendered_component_once(self):
        instructions = "# AGENTS.md instructions\n\n<INSTRUCTIONS>\nprivate project text\n</INSTRUCTIONS>"
        skills = "<skills_instructions>\nprivate skill descriptions\n</skills_instructions>"
        deferred = "<tools>\n- mcp__codex_apps__demo: private app description\n</tools>"
        tool = {"type": "function", "name": "mcp__demo__run", "description": "private tool description"}
        prompt = [{"type": "additional_tools", "tools": [tool]},
                  {"role": "developer", "content": [{"text": text} for text in (instructions, skills, deferred)]},
                  {"role": "user", "content": [{"type": "input_image"}]}]
        rows = [{"kind": "Skill", "upfront": 12, "full": 40, "references": 15},
                {"kind": "App", "upfront": None, "full": 30},
                {"kind": "MCP server", "upfront": 5, "full": 35}]
        window = {"tokens": 1000, "source": "Codex model catalog"}
        report = context["context_report"](prompt, rows, len, window)
        self.assertEqual(report["startup"], sum(map(len, (instructions, skills, deferred, context["compact"](tool)))))
        groups = {group["name"]: group["tokens"] for group in report["groups"]}
        self.assertEqual(groups["Skill catalog"], len(skills))
        self.assertEqual(groups["Inline MCP and app tools"], len(context["compact"](tool)))
        self.assertEqual(report["non_text_parts"], 1)
        self.assertEqual(report["references"], 15)
        self.assertEqual(report["window"], window)
        known = {row["name"]: (row["tokens"], row["known"], row["total"]) for row in report["on_demand"]}
        self.assertEqual(known, {"Skill": (28, 1, 1), "App": (None, 0, 1), "MCP server": (30, 1, 1)})
        self.assertNotIn("private", repr(report))

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

    def test_inline_counts_preserve_identities_and_report_partial_plugin_totals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local, bundled = root / "local/SKILL.md", root / "bundle/SKILL.md"
            def measured(kind, identity, upfront, full):
                return {"kind": kind, "id": identity, "name": "Same display title", "upfront": upfront, "full": full}
            rows = [measured("Skill", str(local), 4, 12), measured("Skill", str(bundled), 2, 10),
                    measured("App", "connector_other", 5, 17), measured("MCP server", "shared", 20, 60)]
            local_skills = [("demo", local, True)]
            status = {"mcp": {"shared": True}, "plugin_mcp": {"plugin@market/shared": True}, "plugins": {}}
            catalog = {"plugin_skills": {"demo": {"path": str(bundled)}},
                       "apps": {"connector_demo": {}, "connector_other": {}},
                       "plugins": {"plugin@market": {"skills": {"demo": str(bundled)}, "apps": ["connector_demo"]}}}
            result = context["inline_context"](rows, local_skills, catalog, status, {})
            self.assertEqual(result["skills"]["demo"]["full"], 12)
            self.assertEqual(result["plugin_skills"]["demo"]["full"], 10)
            self.assertIsNone(result["apps"]["connector_demo"])
            self.assertEqual(result["mcp"]["shared"]["upfront"], 20)
            self.assertNotIn("plugin@market/shared", result["plugin_mcp"])
            plugin = result["plugins"]["plugin@market"]
            self.assertTrue(plugin["upfront_partial"] and plugin["full_partial"])
            self.assertEqual((plugin["upfront"], plugin["full"]), (2, 10))
