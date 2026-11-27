"""Validate reviewed marketplace sources and deterministic installation choices."""
from pathlib import Path
from runpy import run_path
import tempfile
import unittest


market = run_path(str(Path(__file__).resolve().parents[1] / "scripts/marketplace.py"))


class MarketplaceTest(unittest.TestCase):
    def test_skill_link_is_restricted_to_one_public_skill(self):
        link = market["skill_link"]
        self.assertEqual(link("https://skills.sh/vercel-labs/skills/find-skills"),
                         ["vercel-labs", "skills", "find-skills"])
        for malformed in ("https://skills.sh.attacker.test/foo/bar/skill",
                          "https://skills.sh/foo/bar/%2e%2e",
                          "https://skills.sh/p/full-pack"):
            with self.assertRaises(market["CatalogError"]):
                link(malformed)

    def test_snapshot_includes_bytes_and_executable_bit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            guide = folder / "SKILL.md"
            guide.write_text("Test instructions.")
            first, paths = market["project_files"](folder)
            self.assertEqual(paths, ["SKILL.md"])
            guide.chmod(0o700)
            self.assertNotEqual(market["project_files"](folder)[0], first)
            (folder / "outside").symlink_to("/etc/passwd")
            with self.assertRaises(market["CatalogError"]):
                market["project_files"](folder)

    def test_prefers_npm_to_pypi_and_keeps_credential_values_out(self):
        package = {"version": "1.2.3", "identifier": "harmless-mcp", "transport": {"type": "stdio"}}
        choices = market["mcp_choices"]({"name": "example.test/server",
            "remotes": [{"type": "streamable-http", "url": "https://example.test/mcp",
                         "headers": [{"isRequired": True, "isSecret": True, "name": "Authorization"}]},
                        {"type": "sse", "url": "https://example.test/sse"}],
            "packages": [{**package, "registryType": "pypi"}, {**package, "registryType": "npm"}]})
        self.assertEqual([choice["kind"] for choice in choices], ["https", "npm", "pypi"])
        self.assertEqual(market["mcp_configuration"](Path.home(), choices[0]),
                         {"url": "https://example.test/mcp", "env_http_headers": {
                             "Authorization": "MCP_EXAMPLE_TEST_SERVER_AUTHORIZATION"}, "enabled": False})
