"""Validate reviewed marketplace sources and deterministic installation choices."""
from pathlib import Path
from runpy import run_path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
market = run_path(str(SCRIPTS / "marketplace.py"))
import marketplace_updates as updates


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

    def test_registry_update_matches_registered_transport_and_shows_new_requirements(self):
        url = "https://example.test/mcp"
        name = "example.test/demo"
        old = {"kind": "https", "url": url, "registry": {"name": name, "version": "1.0.0"}}
        current = {"url": url, "enabled": True, "disabled_tools": ["unwanted"]}
        release = {"name": name, "version": "2.0.0", "remotes": [{"type": "streamable-http", "url": url,
                    "headers": [{"name": "Authorization", "isRequired": True}]}]}
        receipt = updates.mcp_receipt(old, current)
        with patch.object(updates, "mcp_record", return_value=release):
            review = updates.check_mcp(current, receipt)
            self.assertEqual((review["current"], review["available"]), ("1.0.0", "2.0.0"))
            self.assertIn("MCP_EXAMPLE_TEST_DEMO_AUTHORIZATION", review["preview"])
            new = review["value"]["next"]
            with patch.dict("os.environ", {}, clear=True):
                config = updates.updated_mcp(current, market["mcp_configuration"](Path.home(), new), old, new)
            self.assertFalse(config["enabled"])
            self.assertEqual(config["disabled_tools"], current["disabled_tools"])
            self.assertNotIn("value", updates.check_mcp({**current, "url": url + "/local"}, receipt))
            release["remotes"][0]["url"] = "https://new-provider.test/mcp"
            self.assertNotIn("value", updates.check_mcp(current, receipt))

    def test_skill_update_skips_unrelated_commits_and_previews_changed_files(self):
        with tempfile.TemporaryDirectory() as folder:
            old_folder, new_folder = (Path(folder) / name for name in ("old", "new"))
            old_folder.mkdir()
            new_folder.mkdir()
            (old_folder / "SKILL.md").write_text("Before\n")
            (new_folder / "SKILL.md").write_text("After\n")
            old = {"source": "example/demo", "revision": "a" * 40, "sha256": "1" * 64, "path": "SKILL.md"}
            latest = {**old, "revision": "b" * 40}
            catalog = Mock()
            catalog.skill_revision.return_value = latest["revision"]
            catalog.fetch_skill.return_value = (latest, [], "")
            self.assertIsNone(updates.check_skill(catalog, "demo", old))
            catalog.fetch_skill.return_value = ({**latest, "sha256": "2" * 64}, [], "")
            catalog.restore.side_effect = [old_folder, new_folder]
            item = updates.check_skill(catalog, "demo", old)
            self.assertIn("-Before\n+After", item["preview"])
            self.assertEqual(item["current"], old["revision"][:12])
