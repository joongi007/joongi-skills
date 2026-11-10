"""Project scopes must isolate catalogs, upstreams, tasks and App callbacks."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub


def skill(root, name, body):
    directory = Path(root) / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill\n---\n{body}\n", encoding="utf-8"
    )
    return directory


class ProjectScopes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.common = self.root / "common/skills"
        skill(self.common, "shared", "common")
        skill(self.common, "hidden", "must not leak")
        self.hub = Hub(self.common, self.root / "state")
        self.addCleanup(self.hub.close)
        self.a = self.root / "a"
        self.b = self.root / "b"
        self.a.mkdir()
        self.b.mkdir()
        self.hub.projects.put({"id": "a", "root": str(self.a), "common_skills": ["shared"]})
        self.hub.projects.put({"id": "b", "root": str(self.b)})

    def test_stdio_profile_stays_bound_standalone_and_bridged(self):
        from joongi_hub.server import HubServer

        request = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "profile-test", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "resources/list",
                "params": {"_meta": {"joongi-hub/profile": "global"}},
            },
        ]
        request.insert(1, {"jsonrpc": "2.0", "method": "notifications/initialized"})

        def check():
            command = [
                sys.executable,
                "-m",
                "joongi_hub",
                "stdio",
                "--state-dir",
                str(self.root / "state"),
                "--skills-dir",
                str(self.common),
                "--profile",
                "a",
                "--mode",
                "hybrid",
            ]
            result = subprocess.run(
                command,
                input="\n".join(json.dumps(r) for r in request) + "\n",
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=15,
                check=True,
            )
            rows = [json.loads(line) for line in result.stdout.splitlines()]
            encoded = json.dumps(rows[1]["result"])
            self.assertIn("shared", encoded)
            self.assertNotIn("hidden", encoded)
            self.assertIn("error", rows[2])

        check()
        panel = HubServer(("127.0.0.1", 0), self.hub)
        self.addCleanup(panel.server_close)
        self.addCleanup(panel.shutdown)
        threading.Thread(target=panel.serve_forever, daemon=True).start()
        (self.root / "state/endpoint.json").write_text(
            json.dumps({"pid": os.getpid(), "url": f"http://127.0.0.1:{panel.server_port}"})
        )
        check()

    def test_project_override_and_common_selection_do_not_modify_common(self):
        skill(self.a / ".agents/skills", "shared", "local override")
        project = self.hub.scoped("a")
        self.assertEqual([s["name"] for s in project.skills.list()], ["shared"])
        self.assertIn("local override", project.skills.read("shared")["content"])
        self.assertIn("common", self.hub.skills.read("shared")["content"])
        with self.assertRaises(RpcError):
            project.skills.read("hidden")
        self.assertEqual(self.hub.scoped("b").skills.list(), [])

    def test_native_uri_and_directory_cannot_escape_selected_catalog(self):
        project = self.hub.scoped("a")
        self.assertEqual(project.skills.entry("shared")["uri"], "skill://shared/SKILL.md")
        with self.assertRaises(RpcError):
            project.skills.read_uri("skill://hidden/SKILL.md")
        with self.assertRaises(RpcError):
            project.skills.read_directory("skill://hidden")

    def test_upstreams_and_tasks_are_separate_and_inheritance_is_explicit(self):
        config = {"id": "server", "transport": "stdio", "command": "not-executed"}
        self.hub.register(config)
        self.assertEqual(self.hub.scoped("a").registry.list(), [])
        self.hub.projects.put({"id": "a", "root": str(self.a), "common_servers": ["server"]})
        project = self.hub.scoped("a")
        self.assertEqual(project.registry.list()[0]["id"], "server")
        with self.assertRaises(RpcError):
            project.registry.delete("server")
        task = project.tasks.create("test", "same-client")
        with self.assertRaises(RpcError):
            self.hub.scoped("b").tasks.get(task["taskId"], "same-client")

    def test_protocol_profile_is_bound_to_context(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "hub_search", "arguments": {"query": ""}},
        }
        context = {"version": "2025-11-25", "ready": True, "owner": "test", "profile": "a"}
        result = self.hub.rpc(request, context)
        self.assertNotIn("hidden", result["result"]["content"][0]["text"])
        request["params"]["_meta"] = {"joongi-hub/profile": "global"}
        result = self.hub.rpc(request, context)
        self.assertEqual(result["error"]["code"], -32602)

    def test_root_change_does_not_reuse_project_credentials(self):
        before = self.hub.scoped("a").state_dir
        self.hub.projects.put({"id": "a", "root": str(self.b)})
        self.assertNotEqual(before, self.hub.scoped("a").state_dir)

    def test_unregistered_and_symlink_project_skill_roots_rejected(self):
        with self.assertRaises(RpcError):
            self.hub.scoped("unknown")
        try:
            (self.a / ".agents").symlink_to(self.b, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaises(RpcError):
            self.hub.projects.put({"id": "unsafe", "root": str(self.a)})


if __name__ == "__main__":
    unittest.main()
