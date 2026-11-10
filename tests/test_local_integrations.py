"""A local inventory must preserve origins without disclosing executable configuration."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.collect_local_integrations import collect, markdown


class LocalInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_jsonc_inventory_omits_secrets_and_executable_content(self):
        self.write(
            "project/.cursor/mcp.json",
            """{
          // This existing config is never modified or executed.
          "mcpServers": {"search": {
            "command": "SECRET-command", "args": ["SECRET-arg"],
            "env": {"SECRET-key": "SECRET-value"},
            "url": "https://user:SECRET-password@example.com/?key=SECRET-query",
            "headers": {"Authorization": "SECRET-header"},
            "description": "SECRET-description", "disabled": true,
          },},
        }""",
        )
        with patch("subprocess.run", side_effect=AssertionError("must not execute")):
            report = collect(self.root)
        self.assertEqual(len(report["mcp"]), 1)
        entry = report["mcp"][0]
        self.assertEqual(entry["name"], "search")
        self.assertEqual(entry["source"], "project/.cursor/mcp.json")
        self.assertEqual(entry["transport"], "stdio")
        self.assertFalse(entry["enabled"])
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertNotIn("SECRET", markdown(report))

    def test_skill_fingerprints_group_copies_without_copying_body(self):
        text = "---\nname: example\ndescription: SECRET-description\n---\nSECRET-body\n"
        self.write("one/.agents/skills/example/SKILL.md", text)
        self.write("two/skills/example/SKILL.md", text)
        self.write("one/node_modules/pkg/SKILL.md", text)
        self.write("one/.validation-tmp/copy/SKILL.md", text)
        report = collect(self.root)
        self.assertEqual(report["summary"]["skills"], 2)
        self.assertEqual(report["summary"]["unique_skill_contents"], 1)
        self.assertEqual(len(report["duplicate_skills"]), 1)
        self.assertNotIn("SECRET", json.dumps(report))

    def test_supported_container_formats(self):
        self.write("a/.vscode/mcp.json", '{"servers":{"one":{"url":"https://example.com"}}}')
        self.write("b/opencode.jsonc", '{"mcp":{"two":{"type":"local","command":["x"]}}}')
        self.write("c/settings.json", '{"mcp":{"servers":{"three":{"type":"http"}}}}')
        report = collect(self.root)
        self.assertEqual({item["name"] for item in report["mcp"]}, {"one", "two", "three"})

    def test_codex_toml(self):
        try:
            import tomllib  # noqa: F401
        except ImportError:
            self.skipTest("TOML inventory requires Python 3.11+")
        self.write("project/.codex/config.toml", '[mcp_servers.docs]\ncommand="SECRET"\n')
        report = collect(self.root)
        self.assertEqual(report["mcp"][0]["name"], "docs")
        self.assertNotIn("SECRET", json.dumps(report))

    def test_embedded_or_unknown_transport_is_not_assumed_http(self):
        self.write(
            "project/.mcp.json",
            '{"mcpServers":{"internal":{"type":"sdk"},"unknown":{"type":"custom"}}}',
        )
        entries = {entry["name"]: entry for entry in collect(self.root)["mcp"]}
        self.assertEqual(entries["internal"]["transport"], "sdk")
        self.assertEqual(entries["unknown"]["transport"], "unknown")

    def test_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside)
            (target / ".mcp.json").write_text('{"mcpServers":{"foreign":{"command":"x"}}}')
            try:
                (self.root / "linked").symlink_to(target, target_is_directory=True)
                (self.root / ".mcp.json").symlink_to(target / ".mcp.json")
            except OSError:
                self.skipTest("symlink creation is unavailable")
            self.assertEqual(collect(self.root)["mcp"], [])

    def test_bad_and_oversized_inputs_do_not_echo_content(self):
        self.write("a/.mcp.json", '{"SECRET-parse-error":')
        self.write("b/SKILL.md", "---\nname: invalid NAME SECRET\n---\n")
        self.write("c/mcp.json", "SECRET" * 30)
        with patch("scripts.collect_local_integrations.MAX_BYTES", 100):
            report = collect(self.root)
        self.assertEqual(len(report["issues"]), 3)
        self.assertNotIn("SECRET", json.dumps(report))

    def test_scan_limits_are_visible(self):
        self.write("project/a.txt", "x")
        self.write("project/b.txt", "x")
        with patch("scripts.collect_local_integrations.MAX_FILES", 1):
            self.assertTrue(collect(self.root)["truncated"])


if __name__ == "__main__":
    unittest.main()
