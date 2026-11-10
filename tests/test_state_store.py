"""Regressions for registry divergence, loss and concurrent stdio writers."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from joongi_hub.state_store import default_directory, describe, import_servers, restore_backup
from joongi_hub.storage import Registry
from joongi_hub.upstream import validate_server
from scripts.install_manager import Installer

ROOT = Path(__file__).resolve().parents[1]


class StateStore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.server = validate_server(
            {"id": "one", "transport": "stdio", "command": sys.executable}
        )

    def test_installed_default_is_pinned_but_explicit_cli_path_still_works(self):
        with patch.dict(
            os.environ,
            {
                "JOONGI_HUB_INSTALL_STATE_DIR": str(self.root / "installed"),
                "JOONGI_HUB_STATE_DIR": str(self.root / "old-review"),
            },
        ):
            self.assertEqual(default_directory(), self.root / "installed")
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "joongi_hub",
                    "state",
                    "--state-dir",
                    str(self.root / "explicit"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        self.assertEqual(json.loads(result.stdout)["state_dir"], str(self.root / "explicit"))

    def test_installed_launcher_uses_same_home_for_web_and_stdio_defaults(self):
        home = self.root / "home"
        home.mkdir()
        Installer(home, ROOT).install([])
        launcher = home / ".local/bin" / ("joongi-hub.cmd" if os.name == "nt" else "joongi-hub")
        with patch.dict(os.environ, {"JOONGI_HUB_STATE_DIR": str(self.root / "unrelated")}):
            result = subprocess.run(
                [str(launcher), "state"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=20,
            )
        self.assertEqual(
            json.loads(result.stdout)["state_dir"], str(home / ".local/share/joongi-hub")
        )

    def test_missing_registry_is_reported_and_requires_explicit_restore(self):
        registry = Registry(self.root)
        registry.put(self.server)
        registry.path.unlink()
        with self.assertRaises(RpcError):
            registry.list()
        self.assertIsNone(describe(self.root)["server_count"])
        self.assertEqual(restore_backup(self.root), {"restored": 1})
        self.assertEqual(registry.list(), [self.server])
        with self.assertRaises(RpcError):
            restore_backup(self.root)

    def test_last_deleted_server_stays_deleted_after_backup_restore(self):
        registry = Registry(self.root)
        registry.put(self.server)
        registry.delete("one")
        registry.path.unlink()
        restore_backup(self.root)
        self.assertEqual(registry.list(), [])

    def test_import_merges_preserves_source_and_refuses_all_on_conflict(self):
        source, target = self.root / "source", self.root / "target"
        Registry(source).put(self.server)
        before = (source / "servers.json").read_bytes()
        result = import_servers(target, source)
        self.assertEqual(result["imported"], ["one"])
        self.assertEqual((source / "servers.json").read_bytes(), before)
        self.assertEqual(import_servers(target, source)["imported"], [])
        Registry(source).put({**self.server, "command": "different"})
        Registry(source).put({**self.server, "id": "two"})
        with self.assertRaises(RpcError):
            import_servers(target, source)
        self.assertEqual(Registry(target).list(), [self.server])
        self.assertFalse((target / "credentials.json").exists())

    def test_corrupt_or_absent_source_is_never_imported_as_empty(self):
        for content in [None, "{}", "[]bad", '[{"id":"bad"}]']:
            source = self.root / "source"
            source.mkdir(exist_ok=True)
            if content is not None:
                (source / "servers.json").write_text(content)
            with self.subTest(content=content), self.assertRaises(RpcError):
                import_servers(self.root / "target", source)
        self.assertFalse((self.root / "target/servers.json").exists())

    def test_independent_processes_do_not_lose_registrations(self):
        code = (
            "from pathlib import Path; from joongi_hub.storage import Registry; import sys; "
            "Registry(Path(sys.argv[1])).put({'id':sys.argv[2]})"
        )
        children = [
            subprocess.Popen([sys.executable, "-B", "-c", code, str(self.root), str(i)], cwd=ROOT)
            for i in range(8)
        ]
        for child in children:
            self.assertEqual(child.wait(timeout=30), 0)
        self.assertEqual(
            {item["id"] for item in Registry(self.root).list()}, {str(i) for i in range(8)}
        )

    def test_project_diagnostics_count_selected_common_servers(self):
        hub = Hub(ROOT / "skills", self.root / "state")
        self.addCleanup(hub.close)
        project = self.root / "project"
        project.mkdir()
        hub.register(self.server)
        hub.projects.put({"id": "project", "root": str(project), "common_servers": ["one"]})
        scoped = hub.scoped("project")
        self.assertEqual(scoped.state()["storage"]["server_count"], 1)
        result = json.loads(scoped.invoke("hub_status", {})["content"][0]["text"])
        self.assertEqual(result["server_count"], 1)
        self.assertFalse(any("등록된 MCP가 없습니다" in warning for warning in result["warnings"]))

    def test_http_service_and_new_stdio_process_see_same_registry(self):
        hub = Hub(ROOT / "skills", self.root)
        self.addCleanup(hub.close)
        hub.register(self.server)
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "check", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "hub_status", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "hub_list_servers", "arguments": {}},
            },
        ]
        result = subprocess.run(
            [sys.executable, "-B", "-m", "joongi_hub", "stdio", "--state-dir", str(self.root)],
            input="".join(json.dumps(m) + "\n" for m in messages),
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
            timeout=20,
        )
        responses = {
            item["id"]: item
            for line in result.stdout.splitlines()
            if (item := json.loads(line)).get("id")
        }
        status = json.loads(responses[2]["result"]["content"][0]["text"])
        servers = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertEqual(status["state_dir"], hub.state()["storage"]["state_dir"])
        self.assertEqual(status["server_count"], 1)
        self.assertEqual([s["id"] for s in servers], ["one"])
        self.assertIn("임시 저장소", result.stderr)


if __name__ == "__main__":
    unittest.main()
