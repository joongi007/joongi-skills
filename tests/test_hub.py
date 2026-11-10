"""Behavior tests across real subprocess and HTTP protocol boundaries."""

import hashlib
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from joongi_hub.skills import Skills
from joongi_hub.storage import atomic_json
from joongi_hub.upstream import MODERN, VERSIONS, validate_server
from tests.fixtures.mcp_server import Fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/mcp_server.py"


class HubTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.hub = Hub(ROOT / "skills", self.directory)
        self.addCleanup(self.hub.close)

    def register(self, version=MODERN, server_id="fixture"):
        self.hub.register(
            {
                "id": server_id,
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(FIXTURE), "--version", version],
            }
        )
        return self.hub.probe(server_id)

    def call(self, method, params=None, version=MODERN, context=None, extensions=None):
        params = dict(params or {})
        context = (
            context if context is not None else {"version": version, "ready": True, "owner": "test"}
        )
        if version == MODERN:
            params["_meta"] = {
                "io.modelcontextprotocol/protocolVersion": MODERN,
                "io.modelcontextprotocol/clientCapabilities": {"extensions": extensions or {}},
            }
        response = self.hub.rpc(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, context
        )
        if "error" in response:
            raise AssertionError(response)
        return response["result"]

    def wait_task(self, task_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            task = self.hub.tasks.get(task_id)
            if task["status"] not in {"working", "input_required"}:
                return task
            time.sleep(0.01)
        self.fail("Task never completed")

    def test_nine_client_upstream_version_combinations(self):
        for upstream_version in VERSIONS:
            server_id = "server-" + upstream_version
            probe = self.register(upstream_version, server_id)
            self.assertEqual(probe["protocol_version"], upstream_version)
            for client_version in VERSIONS:
                with self.subTest(client=client_version, upstream=upstream_version):
                    result = self.call(
                        "tools/call",
                        {
                            "name": "hub_call",
                            "arguments": {
                                "name": server_id + "__echo",
                                "arguments": {"message": "안녕"},
                            },
                        },
                        version=client_version,
                    )
                    self.assertEqual(json.loads(result["content"][0]["text"]), {"message": "안녕"})
                    self.assertEqual("resultType" in result, client_version == MODERN)

    def test_search_does_not_execute_unregistered_commands(self):
        self.hub.register({"id": "pending", "transport": "stdio", "command": "/missing"})
        self.assertTrue(self.hub.search("engineering"))
        self.assertNotIn("pending", self.hub.clients)

    def test_native_skills_manifest_and_on_demand_read(self):
        entries = self.call("skills/list", extensions={"io.modelcontextprotocol/skills": {}})[
            "skills"
        ]
        self.assertGreaterEqual(len(entries), 2)
        for entry in entries:
            self.assertTrue(entry["frontmatter"]["description"])
            file = entry["resources"][0]
            read = self.call("resources/read", {"uri": file["uri"]})["contents"][0]["text"].encode()
            self.assertEqual(file["size"], len(read))
            self.assertEqual(file["digest"], "sha256:" + hashlib.sha256(read).hexdigest())

    def test_skill_path_confinement(self):
        for path in [
            "../../README.md",
            "/etc/passwd",
            "references/../../../README.md",
            "..\\README.md",
        ]:
            with self.subTest(path=path), self.assertRaises(RpcError):
                self.hub.skills.read("engineering-playbook", path)

    def test_symlink_escape_blocked(self):
        directory = self.directory / "skills"
        folder = directory / "demo"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\nname: demo\ndescription: Test\n---\n")
        try:
            (folder / "outside.md").symlink_to(ROOT / "README.md")
        except OSError:
            self.skipTest("Symlink creation is not permitted on this platform")
        with self.assertRaises(RpcError):
            Skills(directory).read("demo", "outside.md")

    def test_legacy_handshake_and_unknown_version(self):
        context = {"owner": "test"}
        init = self.hub.rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
            },
            context,
        )
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        not_ready = self.hub.rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, context)
        self.assertIn("error", not_ready)
        self.hub.rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, context)
        self.assertIn(
            "result", self.hub.rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, context)
        )
        unknown = self.hub.rpc(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "ping",
                "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "1900-01-01"}},
            },
            context,
        )
        self.assertEqual(unknown["error"]["code"], -32022)

    def test_apps_metadata_namespaced_and_host_gated(self):
        self.register()
        plain = self.call("tools/list")["tools"]
        app = next(tool for tool in plain if tool["name"] == "fixture__app")
        self.assertNotIn("ui", app.get("_meta", {}))
        tools = self.call("tools/list", extensions={"io.modelcontextprotocol/ui": {}})["tools"]
        app = next(tool for tool in tools if tool["name"] == "fixture__app")
        uri = app["_meta"]["ui"]["resourceUri"]
        self.assertTrue(uri.startswith("ui://hub/fixture/"))
        content = self.call("resources/read", {"uri": uri})
        self.assertEqual(content["contents"][0]["uri"], uri)

    def test_upstream_skills_are_searchable_with_verified_resources(self):
        self.register()
        search = self.hub.search("remote-review")
        entry = next(item for item in search if item["kind"] == "skill")
        self.assertEqual(entry["name"], "fixture__remote-review")
        result = self.hub.read_resource(entry["uri"])
        self.assertIn("Review carefully", result["contents"][0]["text"])
        client = self.hub.client("fixture")
        client.skill_entries[0]["resources"][0]["digest"] = "sha256:invalid"
        with self.assertRaises(RpcError):
            self.hub.read_resource(entry["uri"])

    def test_manifest_get_refreshes_cached_digest(self):
        self.register()
        client = self.hub.client("fixture")
        client.skill_entries[0]["resources"][0]["digest"] = "sha256:old"
        uri = self.hub.search("remote-review")[0]["uri"]
        self.call("skills/get", {"uri": uri}, extensions={"io.modelcontextprotocol/skills": {}})
        self.assertIn("Review carefully", self.hub.read_resource(uri)["contents"][0]["text"])

    def test_apps_original_tool_alias_and_ambiguity(self):
        self.register()
        result = self.hub.invoke("echo", {"app": "original name"})
        self.assertEqual(json.loads(result["content"][0]["text"])["app"], "original name")
        tools = self.call("tools/list", extensions={"io.modelcontextprotocol/ui": {}})["tools"]
        alias = next(tool for tool in tools if tool["name"] == "echo")
        self.assertEqual(alias["_meta"]["ui"]["visibility"], ["app"])
        self.register(server_id="other")
        with self.assertRaises(RpcError):
            self.hub.invoke("echo", {})
        self.assertIn("content", self.hub.invoke("fixture__echo", {}))

    def test_task_only_legacy_tool_receives_task_augmentation(self):
        self.register("2025-11-25")
        client = self.hub.client("fixture")
        next(tool for tool in client.tools if tool["name"] == "echo")["execution"] = {
            "taskSupport": "required"
        }
        original = client.request

        def strict_request(method, params=None):
            if method == "tools/call":
                self.assertIn("task", params)
            return original(method, params)

        with patch.object(client, "request", side_effect=strict_request):
            self.hub.invoke("fixture__echo", {})

    def test_modern_task_result_and_legacy_task_result(self):
        self.register()
        for version in [MODERN, "2025-11-25"]:
            with self.subTest(version=version):
                params = {
                    "name": "hub_call",
                    "arguments": {"name": "fixture__echo", "arguments": {"a": 1}},
                }
                if version != MODERN:
                    params["task"] = {}
                result = self.call(
                    "tools/call",
                    params,
                    version=version,
                    extensions={"io.modelcontextprotocol/tasks": {}},
                )
                task = result if version == MODERN else result["task"]
                self.assertNotIn("owner", task)
                stored = self.wait_task(task["taskId"])
                self.assertEqual(stored["status"], "completed")
                method = "tasks/get" if version == MODERN else "tasks/result"
                completed = self.call(
                    method,
                    {"taskId": task["taskId"]},
                    version=version,
                    extensions={"io.modelcontextprotocol/tasks": {}},
                )
                self.assertIn("result" if version == MODERN else "content", completed)

    def test_upstream_tasks_both_eras(self):
        for version in [MODERN, "2025-11-25"]:
            self.register(version, "async-" + version)
            task = self.hub.start_task("async-" + version + "__async", {}, "test")
            stored = self.wait_task(task["taskId"])
            self.assertEqual(stored["status"], "completed")
            self.assertIn("Async complete", stored["result"]["content"][0]["text"])

    def test_domain_error_completes_task(self):
        self.register()
        task = self.hub.start_task("fixture__error", {}, "test")
        result = self.wait_task(task["taskId"])
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["result"]["isError"])

    def test_cancel_never_resurrects_and_owner_scopes(self):
        self.register()
        task = self.hub.start_task("fixture__delay", {"seconds": 0.15}, "test")
        with self.assertRaises(RpcError):
            self.hub.tasks.get(task["taskId"], "other-owner")
        self.hub.cancel_task(task["taskId"], "test")
        time.sleep(0.25)
        self.assertEqual(self.hub.tasks.get(task["taskId"])["status"], "cancelled")

    def test_persistence_and_interrupted_task_recovery(self):
        task = self.hub.tasks.create("pending", "test")
        with self.hub.tasks.connection() as db:
            task["executorPid"] = 2147483647
            db.execute("UPDATE tasks SET body = ? WHERE id = ?", (json.dumps(task), task["taskId"]))
        replacement = Hub(ROOT / "skills", self.directory)
        self.addCleanup(replacement.close)
        self.assertEqual(replacement.tasks.get(task["taskId"])["status"], "failed")

    def test_second_process_does_not_fail_live_tasks(self):
        task = self.hub.tasks.create("live", "test")
        replacement = Hub(ROOT / "skills", self.directory)
        self.addCleanup(replacement.close)
        self.assertEqual(replacement.tasks.get(task["taskId"])["status"], "working")

    def test_registry_validation(self):
        for bad in [
            [],
            {"id": "../a", "transport": "stdio", "command": "x"},
            {"id": "a", "transport": "stdio", "command": "x", "args": "shell command"},
            {"id": "a", "transport": "http", "url": "http://169.254.169.254/latest"},
            {
                "id": "a",
                "transport": "stdio",
                "command": "x",
                "env": {"KEY": "literal secret value"},
            },
        ]:
            with self.subTest(bad=bad), self.assertRaises(RpcError):
                validate_server(bad)

    def test_real_stdio_hub(self):
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "hub_search", "arguments": {"query": "engineering"}},
            },
        ]
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "joongi_hub",
                "stdio",
                "--state-dir",
                str(self.directory / "stdio"),
            ],
            input="\n".join(json.dumps(m) for m in messages) + "\n",
            text=True,
            capture_output=True,
            timeout=10,
            cwd=ROOT,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses), 2)
        self.assertIn("engineering-playbook", responses[-1]["result"]["content"][0]["text"])


class HttpHubTest(unittest.TestCase):
    def setUp(self):
        HubTest.setUp(self)
        self.server = HubServer(("127.0.0.1", 0), self.hub)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method="GET", path="/api/v1/state", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        data = json.dumps(body).encode() if body is not None else None
        connection.request(
            method, path, body=data, headers={"Content-Type": "application/json", **(headers or {})}
        )
        response = connection.getresponse()
        raw = response.read()
        result = (response.status, dict(response.getheaders()), raw)
        connection.close()
        return result

    def test_http_panel_and_security_boundaries(self):
        status, headers, body = self.request(path="/")
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html", body.lower())
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(self.request(headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request(headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request(headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request("POST", "/api/v1/servers", {})[0], 403)
        session = json.loads(self.request(path="/api/v1/session")[2])
        status, _, _ = self.request(
            "POST",
            "/api/v1/servers",
            {"id": "test", "transport": "stdio", "command": "missing"},
            {"X-Hub-Token": session["token"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.request(path="/static/../../README.md")[0], 404)

    def test_http_modern_and_legacy_sessions(self):
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "server/discover",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": MODERN}},
        }
        status, _, body = self.request("POST", "/mcp", request)
        self.assertEqual(status, 200)
        self.assertIn(MODERN, json.loads(body)["result"]["supportedVersions"])
        init = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        }
        _, headers, _ = self.request("POST", "/mcp", init)
        session = {"Mcp-Session-Id": headers["Mcp-Session-Id"]}
        self.assertEqual(
            self.request(
                "POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, session
            )[0],
            202,
        )
        _, _, body = self.request(
            "POST", "/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}, session
        )
        self.assertIn("tools", json.loads(body)["result"])
        self.assertEqual(self.request("DELETE", "/mcp", headers=session)[0], 204)

    def test_stdio_bridge_uses_running_panel(self):
        atomic_json(
            self.directory / "endpoint.json",
            {"pid": os.getpid(), "url": f"http://127.0.0.1:{self.server.server_port}"},
        )
        task = self.hub.tasks.create("marker", "test")
        # Connection discovery performed in the panel must be visible through stdio.
        self.hub.register(
            {
                "id": "shared",
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(FIXTURE)],
            }
        )
        self.hub.probe("shared")
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "hub_search",
                "arguments": {"query": "remote-review"},
                "_meta": {"io.modelcontextprotocol/protocolVersion": MODERN},
            },
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "joongi_hub",
                "stdio",
                "--mode",
                "hybrid",
                "--state-dir",
                str(self.directory),
            ],
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("shared__remote-review", result.stdout)
        self.assertEqual(self.hub.tasks.get(task["taskId"])["status"], "working")
        invalid = subprocess.run(
            [
                sys.executable,
                "-m",
                "joongi_hub",
                "stdio",
                "--mode",
                "hybrid",
                "--state-dir",
                str(self.directory),
            ],
            input="[]\n",
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=10,
        )
        self.assertEqual(invalid.returncode, 0, invalid.stderr)
        self.assertEqual(json.loads(invalid.stdout)["error"]["code"], -32600)

    def test_http_upstream_actual_transport_both_eras(self):
        for version in [MODERN, "2025-11-25"]:
            fixture = Fixture(version)

            class FixtureHandler(BaseHTTPRequestHandler):
                def log_message(self, *args):
                    pass

                def do_POST(self):
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    result = self.server.fixture.handle(body)
                    encoded = json.dumps(result).encode()
                    self.send_response(200 if result else 202)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)

            server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
            server.fixture = fixture
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                server_id = "http-" + version
                self.hub.register(
                    {
                        "id": server_id,
                        "transport": "http",
                        "url": f"http://127.0.0.1:{server.server_port}/mcp",
                    }
                )
                self.hub.probe(server_id)
                result = self.hub.invoke(server_id + "__echo", {"transport": "http"})
                self.assertEqual(json.loads(result["content"][0]["text"]), {"transport": "http"})
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
