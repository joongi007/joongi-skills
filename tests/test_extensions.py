"""Behavioral checks for native Skills, interactive Tasks and App trust boundaries."""

import base64
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import tests.test_hub as fixtures
from joongi_hub.apps import AppSessions, policy_origins
from joongi_hub.errors import RpcError
from joongi_hub.resources import resource_uri
from joongi_hub.skills import Skills, frontmatter
from joongi_hub.upstream import MODERN


class SkillExtensions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "rich-skill"
        self.folder.mkdir()
        self.text = (
            "---\nname: rich-skill\ndescription: >-\n  Review the project\n"
            '  and its assets.\nmetadata:\n  owner: "team: engineering"\n'
            "  tier: verification\ncustom:\n  enabled: true\n  tags: [review, quality]\n"
            "---\nRead assets/icon.png.\n"
        )
        (self.folder / "SKILL.md").write_text(self.text, encoding="utf-8")
        (self.folder / "assets").mkdir()
        self.binary = b"\x89PNG\r\n\x1a\n\x00\xff\x81"
        (self.folder / "assets/icon.png").write_bytes(self.binary)
        self.skills = Skills(self.root)

    def test_folded_yaml_and_nested_metadata_preserved(self):
        entry = self.skills.entry("rich-skill")
        self.assertEqual(entry["frontmatter"]["description"], "Review the project and its assets.")
        self.assertEqual(
            entry["frontmatter"]["metadata"],
            {"owner": "team: engineering", "tier": "verification"},
        )
        self.assertEqual(
            entry["frontmatter"]["custom"], {"enabled": True, "tags": ["review", "quality"]}
        )
        manifest = next(
            file for file in entry["resources"] if file["uri"].endswith("assets/icon.png")
        )
        self.assertEqual(manifest["digest"], "sha256:" + hashlib.sha256(self.binary).hexdigest())
        self.assertEqual(manifest["size"], len(self.binary))

    def test_binary_read_and_byte_exact_crlf(self):
        content = self.skills.read_uri("skill://rich-skill/assets/icon.png")
        self.assertEqual(content["mimeType"], "image/png")
        self.assertEqual(base64.b64decode(content["blob"]), self.binary)
        raw = self.text.replace("\n", "\r\n").encode()
        (self.folder / "SKILL.md").write_bytes(raw)
        self.assertEqual(self.skills.read("rich-skill")["content"].encode(), raw)

    def test_directory_lists_direct_children_and_blocks_ignored_paths(self):
        (self.folder / ".git").mkdir()
        (self.folder / ".git/config").write_text("private")
        listing = self.skills.read_directory("skill://rich-skill")
        self.assertEqual({item["name"] for item in listing}, {"SKILL.md", "assets"})
        child = self.skills.read_directory("skill://rich-skill/assets")
        self.assertEqual(child[0]["uri"], "skill://rich-skill/assets/icon.png")
        with self.assertRaises(RpcError):
            self.skills.read_directory("skill://rich-skill/.git")

    def test_yaml_tags_cycles_and_nonfinite_numbers_rejected(self):
        for value in ('!!python/object/apply:os.system ["false"]', "&a [*a]", ".nan"):
            with self.subTest(value=value), self.assertRaises(RpcError):
                frontmatter(
                    "---\nname: rich-skill\ndescription: Test\nmetadata: " + value + "\n---\n"
                )


class TaskExtensions(unittest.TestCase):
    def setUp(self):
        fixtures.HubTest.setUp(self)

    def test_legacy_upstream_task_augmentation_requires_server_capability(self):
        fixtures.HubTest.register(self, version="2025-11-25")
        client = self.hub.client("fixture")
        client.capabilities.pop("tasks", None)
        with self.assertRaises(RpcError):
            self.hub.invoke("fixture__ask", {})
        echo = next(tool for tool in client.tools if tool["name"] == "echo")
        echo["execution"] = {"taskSupport": "optional"}
        with patch.object(client, "request", wraps=client.request) as request:
            self.hub.invoke("fixture__echo", {"message": "synchronous fallback"})
        self.assertNotIn("task", request.call_args.args[1])

    def test_native_discovery_preserves_schema_and_versioned_task_contract(self):
        fixtures.HubTest.register(self)
        for version in (MODERN, "2025-11-25"):
            tools = fixtures.HubTest.call(self, "tools/list", version=version)["tools"]
            by_name = {tool["name"]: tool for tool in tools}
            self.assertIn("fixture__echo", by_name)
            self.assertEqual(by_name["fixture__echo"]["inputSchema"], {"type": "object"})
            if version == MODERN:
                self.assertNotIn("execution", by_name["fixture__ask"])
            else:
                self.assertEqual(by_name["fixture__ask"]["execution"]["taskSupport"], "required")
                self.assertEqual(by_name["hub_call"]["execution"]["taskSupport"], "optional")

    def test_native_required_task_rejects_legacy_synchronous_request(self):
        fixtures.HubTest.register(self)
        response = self.hub.rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "fixture__ask", "arguments": {}},
            },
            {"version": "2025-11-25", "ready": True, "owner": "test"},
        )
        self.assertEqual(response["error"]["code"], -32602)

    def test_interactive_task_update_and_result(self):
        fixtures.HubTest.register(self)
        result = fixtures.HubTest.call(
            self,
            "tools/call",
            {"name": "hub_call", "arguments": {"name": "fixture__ask", "arguments": {}}},
            extensions={"io.modelcontextprotocol/tasks": {}},
        )
        task_id = result["taskId"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.hub.tasks.get(task_id)["status"] == "working":
            time.sleep(0.01)
        self.assertEqual(self.hub.tasks.get(task_id)["status"], "input_required")
        with self.assertRaises(RpcError):
            self.hub.respond_task(task_id, {}, "wrong-owner")
        self.assertEqual(self.hub.respond_task(task_id, {"never-issued": {}}, "test"), {})
        self.assertEqual(self.hub.tasks.get(task_id)["status"], "input_required")
        ack = fixtures.HubTest.call(
            self,
            "tasks/update",
            {
                "taskId": task_id,
                "inputResponses": {"name": {"action": "accept", "content": {"name": "Joongi"}}},
            },
            extensions={"io.modelcontextprotocol/tasks": {}},
        )
        self.assertEqual(ack["resultType"], "complete")
        task = fixtures.HubTest.wait_task(self, task_id)
        self.assertEqual(task["status"], "completed")
        self.assertIn("Joongi", task["result"]["content"][0]["text"])

    def test_modern_cancel_returns_empty_ack(self):
        task = self.hub.tasks.create("pending", "test")
        result = fixtures.HubTest.call(
            self,
            "tasks/cancel",
            {"taskId": task["taskId"]},
            version=MODERN,
            extensions={"io.modelcontextprotocol/tasks": {}},
        )
        self.assertEqual(result, {"resultType": "complete"})
        self.assertEqual(self.hub.tasks.get(task["taskId"])["status"], "cancelled")

    def test_synchronous_multi_round_trip_preserves_opaque_request_state(self):
        fixtures.HubTest.register(self)
        initial = fixtures.HubTest.call(
            self,
            "tools/call",
            {"name": "hub_call", "arguments": {"name": "fixture__confirm", "arguments": {}}},
        )
        self.assertEqual(initial["resultType"], "input_required")
        self.assertIn("consent", initial["inputRequests"])
        final = fixtures.HubTest.call(
            self,
            "tools/call",
            {
                "name": "hub_call",
                "arguments": {"name": "fixture__confirm", "arguments": {}},
                "requestState": initial["requestState"],
                "inputResponses": {"consent": {"action": "accept", "content": {"confirmed": True}}},
            },
        )
        self.assertEqual(final["content"][0]["text"], "Confirmed True")

    def test_input_before_remote_task_creation_is_exposed_through_local_task(self):
        fixtures.HubTest.register(self)
        task = self.hub.start_task("fixture__confirm", {}, "test")
        deadline = time.monotonic() + 5
        while (
            time.monotonic() < deadline
            and self.hub.tasks.get(task["taskId"])["status"] == "working"
        ):
            time.sleep(0.01)
        self.assertEqual(self.hub.tasks.get(task["taskId"])["status"], "input_required")
        self.hub.respond_task(
            task["taskId"],
            {"consent": {"action": "accept", "content": {"confirmed": True}}},
            "test",
        )
        final = fixtures.HubTest.wait_task(self, task["taskId"])
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["result"]["content"][0]["text"], "Confirmed True")


class AppExtensions(unittest.TestCase):
    def setUp(self):
        fixtures.HubTest.setUp(self)
        fixtures.HubTest.register(self)
        self.apps = AppSessions(self.hub)

    def test_app_task_lifecycle_and_view_ownership(self):
        view = self.apps.prepare("fixture", "app")["token"]
        other = self.apps.prepare("fixture", "app")["token"]
        created = self.apps.request(
            view,
            "tools/call",
            {
                "name": "delay",
                "arguments": {"seconds": 0.05, "message": "app-task"},
                "task": {"ttl": 60000},
            },
        )
        task_id = created["task"]["taskId"]
        for method in ("tasks/get", "tasks/cancel", "tasks/result"):
            with self.subTest(method=method), self.assertRaises(RpcError):
                self.apps.request(other, method, {"taskId": task_id})
        self.assertEqual(self.apps.request(other, "tasks/list", {})["tasks"], [])
        fixtures.HubTest.wait_task(self, task_id)
        status = self.apps.request(view, "tasks/get", {"taskId": task_id})
        self.assertEqual(status["status"], "completed")
        result = self.apps.request(view, "tasks/result", {"taskId": task_id})
        self.assertIn("app-task", result["content"][0]["text"])

    def test_app_task_cancel_and_origin_validation(self):
        view = self.apps.prepare("fixture", "app")["token"]
        created = self.apps.request(
            view,
            "tools/call",
            {"name": "delay", "arguments": {"seconds": 0.2}, "task": {"ttl": 60000}},
        )
        task_id = created["task"]["taskId"]
        cancelled = self.apps.request(view, "tasks/cancel", {"taskId": task_id})
        self.assertEqual(cancelled["status"], "cancelled")
        with self.assertRaises(RpcError):
            self.apps.request(view, "tools/call", {"name": "elsewhere__echo", "task": {}})

    def test_legacy_app_resource_metadata_is_normalized_and_namespaced(self):
        client = self.hub.client("fixture")
        tool = next(tool for tool in client.tools if tool["name"] == "app")
        tool["_meta"] = {"ui/resourceUri": "ui://fixture/panel.html"}
        tools = self.hub.tools()
        forwarded = next(tool for tool in tools if tool["name"] == "fixture__app")
        uri = forwarded["_meta"]["ui"]["resourceUri"]
        self.assertEqual(uri, resource_uri("fixture", "ui://fixture/panel.html"))
        self.assertEqual(forwarded["_meta"]["ui/resourceUri"], uri)
        self.assertIn("url", self.apps.prepare("fixture", "app"))

    def test_resource_policy_has_opaque_sandbox_and_no_parent_access(self):
        view = self.apps.prepare("fixture", "app")
        session = self.apps.get(view["token"])
        self.assertIn("sandbox allow-scripts", session["policy"])
        self.assertNotIn("allow-same-origin", session["policy"])
        self.assertIn("connect-src 'none'", session["policy"])
        self.assertIn("app-echo", session["html"])

    def test_original_tool_calls_scoped_to_own_server_even_with_collisions(self):
        fixtures.HubTest.register(self, server_id="other")
        view = self.apps.prepare("fixture", "app")
        result = self.apps.request(
            view["token"], "tools/call", {"name": "echo", "arguments": {"message": "from app"}}
        )
        self.assertEqual(json.loads(result["content"][0]["text"])["message"], "from app")
        with self.assertRaises(RpcError):
            self.apps.request(view["token"], "tools/call", {"name": "other__echo"})
        with self.assertRaises(RpcError):
            self.apps.request(view["token"], "servers/register", {})

    def test_app_csp_injection_and_expiry_rejected(self):
        for origin in (
            "https://good.example; script-src *",
            "https://user:secret@example.test",
            "file:///etc/passwd",
        ):
            with self.subTest(origin=origin), self.assertRaises(RpcError):
                policy_origins([origin])
        view = self.apps.prepare("fixture", "app")
        self.apps.sessions[view["token"]]["expires"] = 0
        with self.assertRaises(RpcError):
            self.apps.get(view["token"])

    def test_skill_manifest_bytes_are_not_changed_by_app_wrapping(self):
        client = self.hub.client("fixture")
        uri = "ui://fixture/panel.html"
        original = client.request("resources/read", {"uri": uri})["contents"][0]["text"]
        raw = original.encode("utf-8")
        client.skill_entries.append(
            {
                "uri": "skill://protected-ui/SKILL.md",
                "frontmatter": {"name": "protected-ui", "description": "Integrity protected HTML"},
                "resources": [
                    {
                        "uri": uri,
                        "size": len(raw),
                        "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    }
                ],
            }
        )
        result = self.hub.read_resource(resource_uri("fixture", uri))
        self.assertEqual(result["contents"][0]["text"], original)
