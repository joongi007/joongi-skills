"""Installer scenarios use isolated fake homes; never modify the developer's agents."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.install_manager import (
    Installer,
    InstallError,
    download_bundle,
    jsonc_data,
    jsonc_update,
    main,
)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.source = self.root / "source"
        self.skill = self.source / "skills/example"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text(
            "---\nname: example\ndescription: Example\n---\nContent\n"
        )
        package = self.source / "joongi_hub"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "__main__.py").write_text("print('hub-ok')\n")

    def installer(self, dry_run=False):
        return Installer(self.home, self.source, dry_run)

    def test_install_update_detects_new_agent_and_removes_deleted_reference(self):
        (self.home / ".claude").mkdir()
        (self.skill / "old.md").write_text("old")
        self.installer().install()
        (self.home / ".cursor").mkdir()
        (self.skill / "old.md").unlink()
        (self.skill / "SKILL.md").write_text("updated")
        self.installer().install()
        self.assertEqual((self.home / ".claude/skills/example/SKILL.md").read_text(), "updated")
        self.assertFalse((self.home / ".claude/skills/example/old.md").exists())
        self.assertTrue((self.home / ".cursor/skills/example/SKILL.md").exists())

    def test_dry_run_writes_nothing(self):
        installer = self.installer(dry_run=True)
        installer.install(["claude", "codex"])
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertTrue(installer.messages)

    def test_cli_uses_utf8_for_korean_paths_under_legacy_windows_encoding(self):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(Path(__file__).resolve().parents[1] / "scripts/install_manager.py"),
                "install",
                "--home",
                str(self.root / "한국어 홈"),
                "--source",
                str(self.source),
                "--agent",
                "codex",
            ],
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("한국어 홈", result.stdout)

    def test_foreign_skill_conflict_aborts_before_runtime_install(self):
        foreign = self.home / ".claude/skills/example"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("mine")
        with self.assertRaises(InstallError):
            self.installer().install(["claude"])
        self.assertFalse((self.home / ".local").exists())
        self.assertEqual((foreign / "SKILL.md").read_text(), "mine")

    def test_modified_skill_is_preserved_on_update_and_uninstall(self):
        self.installer().install(["claude"])
        target = self.home / ".claude/skills/example/SKILL.md"
        target.write_text("local edits")
        with self.assertRaises(InstallError):
            self.installer().install(["claude"])
        self.installer().uninstall()
        self.assertEqual(target.read_text(), "local edits")
        self.assertFalse((self.home / ".local/share/joongi-skills/runtime").exists())

    def test_json_registration_preserves_unrelated_settings_and_secret(self):
        config = self.home / ".claude.json"
        unrelated = {
            "mcpServers": {"other": {"command": "other", "env": {"TOKEN": "secret"}}},
            "theme": "light",
        }
        config.write_text(json.dumps(unrelated))
        self.installer().install(["claude"])
        installed = json.loads(config.read_text())
        self.assertEqual(installed["mcpServers"]["other"], unrelated["mcpServers"]["other"])
        manifest = (self.home / ".local/share/joongi-skills/installation.json").read_text()
        self.assertNotIn("secret", manifest)
        self.installer().uninstall()
        self.assertEqual(json.loads(config.read_text()), unrelated)

    def test_codex_registration_preserves_toml_and_removes_only_managed_block(self):
        config = self.home / ".codex/config.toml"
        config.parent.mkdir()
        original = 'model = "example"\n[mcp_servers.other]\ncommand = "other"\n'
        config.write_text(original)
        self.installer().install(["codex"])
        self.assertTrue((self.home / ".agents/skills/example/SKILL.md").exists())
        self.installer().install(["codex"])
        self.assertEqual(config.read_text().count("BEGIN joongi-skills"), 1)
        self.installer().uninstall()
        self.assertEqual(config.read_text(), original)

    def test_existing_mcp_name_is_not_overwritten(self):
        config = self.home / ".claude.json"
        config.write_text('{"mcpServers":{"joongi-hub":{"command":"mine"}}}')
        with self.assertRaises(InstallError):
            self.installer().install(["claude"])
        self.assertEqual(
            json.loads(config.read_text())["mcpServers"]["joongi-hub"]["command"], "mine"
        )
        self.assertFalse((self.home / ".local").exists())

    def test_copilot_registration_tools_and_unrelated_settings(self):
        path = self.home / ".copilot/mcp-config.json"
        path.parent.mkdir()
        original = {"mcpServers": {"other": {"command": "other"}}, "preference": "keep"}
        path.write_text(json.dumps(original))
        self.installer().install(["copilot"])
        data = json.loads(path.read_text())
        self.assertEqual(data["mcpServers"]["joongi-hub"]["type"], "local")
        self.assertEqual(data["mcpServers"]["joongi-hub"]["tools"], ["*"])
        self.installer().install(["copilot"])
        self.installer().uninstall()
        self.assertEqual(json.loads(path.read_text()), original)

    def test_opencode_jsonc_preserves_comments_strings_and_user_changes(self):
        path = self.home / ".config/opencode/opencode.jsonc"
        path.parent.mkdir(parents=True)
        original = (
            '{ // user preferences\n  "model": "keep, } // literal",\n'
            '  "mcp": { /* servers */ "other": {"type":"local", "command":["other"]}, },\n}\n'
        )
        path.write_text(original)
        self.installer().install(["opencode"])
        installed = path.read_text()
        self.assertIn("// user preferences", installed)
        self.assertIn("/* servers */", installed)
        self.assertIn('"model": "keep, } // literal"', installed)
        data = jsonc_data(installed)
        self.assertEqual(data["mcp"]["joongi-hub"]["command"][-1], "stdio")
        self.installer().install(["opencode"])
        path.write_text(
            path.read_text().replace('"model": "keep, } // literal"', '"model": "new-model"')
        )
        self.installer().uninstall()
        remaining = path.read_text()
        self.assertIn("// user preferences", remaining)
        self.assertEqual(jsonc_data(remaining)["model"], "new-model")
        self.assertNotIn("joongi-hub", jsonc_data(remaining)["mcp"])
        self.assertEqual(jsonc_data(remaining)["mcp"]["other"], data["mcp"]["other"])

    def test_opencode_both_config_files_keep_precedence_and_detect_conflicts(self):
        directory = self.home / ".config/opencode"
        directory.mkdir(parents=True)
        (directory / "opencode.json").write_text('{"model":"baseline"}')
        (directory / "opencode.jsonc").write_text('{/* override */"model":"override"}')
        self.installer().install(["opencode"])
        self.assertEqual((directory / "opencode.json").read_text(), '{"model":"baseline"}')
        self.assertIn("joongi-hub", jsonc_data((directory / "opencode.jsonc").read_text())["mcp"])
        self.installer().uninstall()
        (directory / "opencode.json").write_text('{"mcp":{"joongi-hub":{"type":"local"}}}')
        with self.assertRaises(InstallError):
            self.installer().install(["opencode"])

    def test_opencode_foreign_and_modified_registration_is_preserved(self):
        path = self.home / ".config/opencode/opencode.json"
        path.parent.mkdir(parents=True)
        path.write_text('{"mcp":{"joongi-hub":{"type":"local","command":["mine"]}}}')
        with self.assertRaises(InstallError):
            self.installer().install(["opencode"])
        path.write_text("{}")
        self.installer().install(["opencode"])
        data = json.loads(path.read_text())
        data["mcp"]["joongi-hub"]["enabled"] = False
        path.write_text(json.dumps(data))
        self.installer().uninstall()
        self.assertFalse(json.loads(path.read_text())["mcp"]["joongi-hub"]["enabled"])

    def test_jsonc_remove_any_member_position_keeps_valid_siblings(self):
        for original in [
            '{"mcp":{"joongi-hub":{},"a":{}}}',
            '{"mcp":{"a":{},"joongi-hub":{},"z":{}}}',
            '{"mcp":{"a":{},"joongi-hub":{}}}',
            '{"mcp":{"joongi-hub":{},}}',
        ]:
            with self.subTest(original=original):
                expected = jsonc_data(original)
                del expected["mcp"]["joongi-hub"]
                self.assertEqual(
                    jsonc_data(jsonc_update(original, "mcp", "joongi-hub", None)), expected
                )

    def test_jsonc_rejects_ambiguous_duplicates_and_invalid_comments(self):
        for value in ['{"mcp":{},"mcp":{}}', "{ /* unfinished", '{"mcp": []}']:
            with self.subTest(value=value), self.assertRaises((InstallError, ValueError)):
                jsonc_update(value, "mcp", "joongi-hub", {})

    def test_update_detects_copilot_and_opencode_without_manual_registration(self):
        self.installer().install(["claude"])
        (self.home / ".copilot").mkdir()
        (self.home / ".config/opencode").mkdir(parents=True)
        self.installer().install()
        self.assertIn(
            "joongi-hub",
            json.loads((self.home / ".copilot/mcp-config.json").read_text())["mcpServers"],
        )
        self.assertIn(
            "joongi-hub",
            jsonc_data((self.home / ".config/opencode/opencode.json").read_text())["mcp"],
        )

    def test_modified_mcp_registration_is_preserved(self):
        self.installer().install(["claude"])
        config = self.home / ".claude.json"
        value = json.loads(config.read_text())
        value["mcpServers"]["joongi-hub"]["args"] = ["mine"]
        config.write_text(json.dumps(value))
        self.installer().uninstall()
        self.assertEqual(
            json.loads(config.read_text())["mcpServers"]["joongi-hub"]["args"], ["mine"]
        )

    @unittest.skipIf(os.name == "nt", "symlink privileges vary on Windows")
    def test_symlinked_agent_directory_is_rejected(self):
        external = self.root / "external"
        external.mkdir()
        (self.home / ".claude").symlink_to(external, target_is_directory=True)
        with self.assertRaises(InstallError):
            self.installer().install(["claude"])
        self.assertEqual(list(external.iterdir()), [])

    @unittest.skipIf(os.name == "nt", "POSIX launcher; Windows exercised through installer tests")
    def test_launcher_handles_spaces_and_does_not_modify_runtime(self):
        self.installer().install(["claude"])
        launcher = self.home / ".local/bin/joongi-hub"
        result = subprocess.run([str(launcher)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), "hub-ok")
        runtime = self.home / ".local/share/joongi-skills/runtime"
        self.assertEqual(list(runtime.rglob("__pycache__")), [])
        self.installer().install(["claude"])

    def test_uninstall_is_idempotent_and_keeps_foreign_skill(self):
        self.installer().install(["cursor"])
        foreign = self.home / ".cursor/skills/mine"
        foreign.mkdir()
        (foreign / "SKILL.md").write_text("mine")
        self.installer().uninstall()
        self.installer().uninstall()
        self.assertEqual((foreign / "SKILL.md").read_text(), "mine")

    def test_no_agents_still_installs_hub_without_creating_agent_dirs(self):
        self.installer().install()
        self.assertTrue((self.home / ".local/share/joongi-skills/runtime").exists())
        self.assertFalse((self.home / ".claude").exists())

    def test_update_removes_retired_skills_but_preserves_foreign_skills(self):
        self.installer().install(["claude"])
        foreign = self.home / ".claude/skills/foreign"
        foreign.mkdir()
        (foreign / "SKILL.md").write_text("mine")
        shutil.rmtree(self.skill)
        self.installer().install(["claude"])
        self.assertFalse((self.home / ".claude/skills/example").exists())
        self.assertEqual((foreign / "SKILL.md").read_text(), "mine")

    def test_download_rejects_traversal_before_writing(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            info = tarfile.TarInfo("../escaped")
            info.size = 4
            archive.addfile(info, io.BytesIO(b"oops"))
        raw = data.getvalue()
        manifest = json.dumps({"sha256": hashlib.sha256(raw).hexdigest()}).encode()
        with patch("urllib.request.urlopen", side_effect=[io.BytesIO(manifest), io.BytesIO(raw)]):
            with self.assertRaises(InstallError):
                download_bundle("https://example.invalid", self.root / "extract")
        self.assertFalse((self.root / "escaped").exists())

    def test_download_rejects_checksum_mismatch(self):
        manifest = json.dumps({"sha256": "0" * 64}).encode()
        with patch(
            "urllib.request.urlopen", side_effect=[io.BytesIO(manifest), io.BytesIO(b"wrong")]
        ):
            with self.assertRaises(InstallError):
                download_bundle("https://example.invalid", self.root / "extract")

    def test_stale_manifest_aborts_without_changing_newer_installation(self):
        first = self.installer()
        second = self.installer()
        first.install(["claude"])
        with self.assertRaises(InstallError):
            second.install(["cursor"])
        self.assertFalse((self.home / ".cursor").exists())
        self.assertEqual(self.installer().manifest["agents"], ["claude"])

    def test_write_failure_rolls_back_existing_skill_and_runtime(self):
        self.installer().install(["claude"])
        original = (self.home / ".claude/skills/example/SKILL.md").read_text()
        (self.skill / "SKILL.md").write_text("new source")
        original_write = Path.write_bytes

        def fail_launcher(path, content):
            if path.name.startswith("joongi-hub"):
                raise OSError("simulated disk failure")
            return original_write(path, content)

        with patch.object(Path, "write_bytes", fail_launcher):
            with self.assertRaises(OSError):
                self.installer().install(["claude"])
        self.assertEqual((self.home / ".claude/skills/example/SKILL.md").read_text(), original)
        launcher_name = "joongi-hub.cmd" if os.name == "nt" else "joongi-hub"
        self.assertTrue((self.home / ".local/bin" / launcher_name).exists())
        self.assertFalse((self.home / ".local/share/joongi-skills/install.lock").exists())

    def test_update_remembers_pages_source(self):
        with patch.dict(
            os.environ, {"JOONGI_INSTALL_DOWNLOAD_BASE": "https://example.invalid/project"}
        ):
            self.assertEqual(
                main(["install", "--home", str(self.home), "--source", str(self.source)]), 0
            )
        with patch("scripts.install_manager.download_bundle", return_value=self.source) as download:
            self.assertEqual(main(["update", "--home", str(self.home)]), 0)
            self.assertEqual(download.call_args[0][0], "https://example.invalid/project")

    def test_explicit_local_source_clears_saved_pages_url(self):
        installer = self.installer()
        installer.manifest["download_base"] = "https://example.invalid/project"
        installer.install()
        with patch("scripts.install_manager.download_bundle") as download:
            self.assertEqual(
                main(["update", "--home", str(self.home), "--source", str(self.source)]), 0
            )
            download.assert_not_called()
        self.assertNotIn("download_base", self.installer().manifest)

    def test_codex_inline_or_single_quoted_existing_name_is_preserved(self):
        config = self.home / ".codex/config.toml"
        config.parent.mkdir()
        for original in ("[mcp_servers.'joongi-hub']\ncommand='mine'\n", "mcp_servers = {}\n"):
            config.write_text(original)
            with self.assertRaises(InstallError):
                self.installer().install(["codex"])
            self.assertEqual(config.read_text(), original)

    def test_manifest_parent_traversal_cannot_remove_files_outside_home(self):
        outside = self.root / "external.txt"
        outside.write_text("do not delete")
        installer = self.installer()
        installer.manifest["entries"]["../external.txt"] = {
            "kind": "file",
            "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
        }
        with self.assertRaises(InstallError):
            installer.uninstall()
        self.assertEqual(outside.read_text(), "do not delete")

    def test_settings_changed_during_planning_are_not_overwritten(self):
        config = self.home / ".claude.json"
        config.write_text('{"theme":"original"}')
        installer = self.installer()
        installer._config("claude", self.home / ".local/bin/joongi-hub")
        config.write_text('{"theme":"changed while planning"}')
        with self.assertRaises(InstallError):
            installer._apply()
        self.assertEqual(json.loads(config.read_text()), {"theme": "changed while planning"})


if __name__ == "__main__":
    unittest.main()
