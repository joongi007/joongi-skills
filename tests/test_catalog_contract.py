"""Search-first contracts across real HTTP and stdio, sources and selection boundaries."""

import base64
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from joongi_hub.errors import RpcError
from joongi_hub.resources import resource_uri
from joongi_hub.search import Document, SearchCache, rank
from joongi_hub.skills import Skills
from joongi_hub.upstream import MODERN, VERSIONS
from tests import test_hub as hub_fixtures

ROOT = Path(__file__).resolve().parents[1]
TOOLS = [
    {
        "name": "ordinary",
        "description": "Convert a report.",
        "inputSchema": {"type": "object", "properties": {"input": {"type": "string"}}},
    },
    {
        "name": "app",
        "description": "A visual application",
        "inputSchema": {"type": "object"},
        "_meta": {"ui": {"resourceUri": "ui://catalog/view"}},
    },
    {
        "name": "work",
        "description": "Task work",
        "inputSchema": {"type": "object"},
        "execution": {"taskSupport": "required"},
    },
]


def seed(hub):
    config = hub.register({"id": "fixture", "transport": "stdio", "command": sys.executable})
    client = SimpleNamespace(
        config=config,
        version="2025-11-25",
        tools=TOOLS,
        skill_entries=[],
        capabilities={},
        close=lambda: None,
        connect=lambda: None,
        request=Mock(return_value={"content": [{"type": "text", "text": "executed"}]}),
    )
    hub.clients["fixture"] = client
    return client


def skill_root(root, name="same-guide", text="Company guidance"):
    folder = root / name
    (folder / "references").mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {text}\n---\n# {text}\n", encoding="utf-8"
    )
    (folder / "references/rules.md").write_text(text, encoding="utf-8")
    return root


def modern(method, params):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {
            **params,
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": MODERN,
                "io.modelcontextprotocol/clientCapabilities": {
                    "extensions": {
                        "io.modelcontextprotocol/skills": {},
                        "io.modelcontextprotocol/ui": {},
                    }
                },
            },
        },
    }


class CatalogBoundaries(unittest.TestCase):
    setUp = hub_fixtures.HubTest.setUp

    def test_three_stages_keep_summary_light_and_schema_exact(self):
        seed(self.hub)
        summary = self.hub.search("ordinary")
        self.assertEqual(len(summary), 1)
        self.assertNotIn("inputSchema", summary[0])
        detail = self.hub.catalog_item("tool", "fixture__ordinary")
        self.assertEqual(detail["inputSchema"], TOOLS[0]["inputSchema"])
        self.assertNotIn("result", detail)
        value = self.hub.invoke("hub_call", {"name": "fixture__ordinary", "arguments": {}})
        self.assertEqual(value["content"][0]["text"], "executed")
        self.assertEqual(len(self.hub.search("")), 5)
        self.assertTrue(all("files" not in item for item in self.hub.search("")))

    def test_source_namespaces_preserve_original_bytes_manifests_and_directory_names(self):
        roots = [skill_root(self.directory / name, text=name) for name in ("company", "private")]
        self.hub.configure_catalog(
            {
                "sources": [
                    {"id": name, "path": str(root)}
                    for name, root in zip(("company", "private"), roots, strict=True)
                ]
            }
        )
        for name, root in zip(("company", "private"), roots, strict=True):
            identity = name + "__same-guide"
            item = self.hub.catalog_item("skill", identity)
            self.assertEqual(item["uri"], f"skill://{identity}/same-guide/SKILL.md")
            manifest = self.hub.skills.entry(identity)
            self.assertEqual(manifest["frontmatter"]["name"], "same-guide")
            content = self.hub.skills.read_uri(item["uri"])
            self.assertEqual(
                content["content"].encode(), (root / "same-guide/SKILL.md").read_bytes()
            )
            for resource in manifest["resources"]:
                raw = self.hub.skills.read_uri(resource["uri"])
                data = (
                    raw["content"].encode() if "content" in raw else base64.b64decode(raw["blob"])
                )
                self.assertEqual(resource["digest"], "sha256:" + hashlib.sha256(data).hexdigest())
            listing = self.hub.skills.read_directory(f"skill://{identity}/same-guide/references")
            self.assertEqual(
                listing[0]["uri"], f"skill://{identity}/same-guide/references/rules.md"
            )
        self.hub.configure_catalog({"disabled": {"source": ["company"]}})
        with self.assertRaises(RpcError):
            self.hub.skills.read("company__same-guide")
        self.assertEqual(self.hub.skills.read("private__same-guide")["name"], "private__same-guide")

    def test_project_selects_qualified_common_source_without_crossing_project_boundaries(self):
        root = skill_root(self.directory / "company")
        self.hub.configure_catalog({"sources": [{"id": "company", "path": str(root)}]})
        project = self.directory / "project"
        project.mkdir()
        self.hub.projects.put(
            {"id": "one", "root": str(project), "common_skills": ["company__same-guide"]}
        )
        child = self.hub.scoped("one")
        self.assertEqual([s["name"] for s in child.skills.list()], ["company__same-guide"])
        self.assertIn("Company", child.skills.read("company__same-guide")["content"])
        with self.assertRaises(RpcError):
            child.skills.read("usual-korean")
        self.hub.configure_catalog({"disabled": {"source": ["company"]}})
        with self.assertRaises(RpcError):
            child.skills.read("company__same-guide")

    def test_disabling_skill_or_category_hides_all_local_read_paths_and_reset_restores(self):
        identity = "applying-design-systems"
        self.hub.configure_catalog({"disabled": {"category": ["design"]}})
        self.assertFalse(self.hub.search(identity))
        self.assertNotIn(identity, [s["name"] for s in self.hub.skills.list()])
        self.assertNotIn(Skills.uri(identity), [s["uri"] for s in self.hub.resources()])
        for operation in [
            lambda: self.hub.skills.read(identity),
            lambda: self.hub.read_resource(Skills.uri(identity)),
            lambda: self.hub.skills.read_directory(f"skill://{identity}/references"),
            lambda: self.hub.catalog_item("skill", identity),
        ]:
            with self.assertRaises(RpcError):
                operation()
        self.hub.configure_catalog(reset=True)
        self.assertTrue(self.hub.search(identity))

    def test_remote_disabled_skill_cannot_be_read_by_saved_resource_or_native_uri(self):
        client = seed(self.hub)
        uri = "skill://remote-guide/SKILL.md"
        client.skill_entries = [
            {"uri": uri, "frontmatter": {"name": "remote-guide"}, "resources": [{"uri": uri}]}
        ]
        client.request.reset_mock()
        self.hub.configure_catalog({"disabled": {"skill": ["fixture__remote-guide"]}})
        proxied = resource_uri("fixture", uri)
        with self.assertRaises(RpcError):
            self.hub.read_resource(proxied)
        for method in ("skills/get", "resources/directory/read"):
            response = self.hub.rpc(modern(method, {"uri": proxied}), {})
            self.assertIn("error", response)
        for resources in ([{"uri": uri}], "dynamic"):
            client.skill_entries[0]["resources"] = resources
            for original in (
                "skill://remote-guide/references/unlisted.md",
                "skill://remote-guide/references",
            ):
                with self.assertRaises(RpcError):
                    self.hub.read_resource(resource_uri("fixture", original))
                response = self.hub.rpc(
                    modern("resources/directory/read", {"uri": resource_uri("fixture", original)}),
                    {},
                )
                self.assertIn("error", response)
        self.assertEqual(client.request.call_count, 0)

    def test_namespace_collisions_rejected_in_both_registration_orders(self):
        seed(self.hub)
        root = skill_root(self.directory / "external")
        with self.assertRaises(RpcError):
            self.hub.configure_catalog({"sources": [{"id": "fixture", "path": str(root)}]})
        self.hub.configure_catalog({"sources": [{"id": "company", "path": str(root)}]})
        with self.assertRaises(RpcError):
            self.hub.register({"id": "company", "transport": "stdio", "command": sys.executable})

    def test_readonly_mcp_cannot_change_owner_preferences_even_through_hub_call(self):
        for name, arguments in [
            ("hub_catalog_configure", {"patch": {"exposure": "all-native"}}),
            ("hub_catalog_reset", {}),
            ("hub_catalog_usage_reset", {}),
        ]:
            with self.assertRaises(RpcError):
                self.hub.invoke(name, arguments)
            with self.assertRaises(RpcError):
                self.hub.invoke("hub_call", {"name": name, "arguments": arguments})
        self.hub.invoke(
            "hub_catalog_configure", {"patch": {"usage_enabled": True}}, local_owner=True
        )
        self.assertTrue(self.hub.catalog_preferences.get()["usage_enabled"])

    def test_statistics_store_only_verified_names_and_failure_does_not_change_actual_call(self):
        seed(self.hub)
        self.assertFalse(self.hub.usage_stats.path.exists())
        self.hub.configure_catalog({"usage_enabled": True})
        secret = "sk-sensitive-pretend-token"
        for call in [
            lambda: self.hub.invoke("hub_get_item", {"kind": "skill", "name": secret}),
            lambda: self.hub.invoke("hub_read_skill", {"name": secret}),
            lambda: self.hub.invoke("fixture__" + secret, {}),
        ]:
            with self.assertRaises(RpcError):
                call()
        self.hub.search(secret)
        snapshot = self.hub.usage_stats.snapshot(enabled=True)
        self.assertNotIn(secret, json.dumps(snapshot))
        self.assertNotIn(secret.encode(), self.hub.usage_stats.path.read_bytes())
        with patch.object(
            self.hub.usage_stats, "record", side_effect=RpcError(-1, "stats unavailable")
        ):
            self.assertTrue(self.hub.search("engineering"))
            self.assertEqual(
                self.hub.invoke("fixture__ordinary", {})["content"][0]["text"], "executed"
            )

    def test_preparation_cache_invalidation_boundedness_and_result_isolation(self):
        cache = SearchCache()

        def doc(name, description):
            return Document(
                {"kind": "skill", "name": name, "description": description},
                {
                    "name": name,
                    "aliases": name,
                    "description": description,
                    "server": "",
                    "parameters": "",
                },
            )

        first = [doc("first", "zebra")]
        self.assertEqual(rank(first, "zebra", cache=cache)[0]["name"], "first")
        result = rank(first, "zebra", cache=cache)
        result[0]["name"] = "mutated"
        self.assertEqual(rank(first, "zebra", cache=cache)[0]["name"], "first")
        self.assertGreater(cache.status()["hits"], 0)
        self.assertFalse(rank([doc("first", "tiger")], "zebra", cache=cache))
        rank([doc("second", "another")], "another", cache=cache)
        self.assertEqual(cache.status()["entries"], 2)


class CatalogTransport(unittest.TestCase):
    setUp = hub_fixtures.HttpHubTest.setUp
    request = hub_fixtures.HttpHubTest.request

    def test_real_stdio_and_http_list_search_and_detail_agree_in_every_protocol_version(self):
        seed(self.hub)
        code = (
            "import sys; from pathlib import Path; from joongi_hub.service import Hub; "
            "from joongi_hub.__main__ import serve_stdio; "
            "from tests.test_catalog_contract import seed; "
            "h=Hub(Path(sys.argv[1]),Path(sys.argv[2])); seed(h); "
            "serve_stdio(h); h.close()"
        )
        for version in VERSIONS:

            def message(identity, method, params, version=version):
                if version == MODERN:
                    params = {
                        **params,
                        "_meta": {"io.modelcontextprotocol/protocolVersion": version},
                    }
                return {"jsonrpc": "2.0", "id": identity, "method": method, "params": params}

            messages = (
                [message(1, "server/discover", {})]
                if version == MODERN
                else [
                    message(1, "initialize", {"protocolVersion": version}),
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                ]
            )
            requests = [
                message(2, "tools/list", {}),
                message(3, "tools/call", {"name": "hub_search", "arguments": {"query": ""}}),
                message(
                    4,
                    "tools/call",
                    {
                        "name": "hub_get_item",
                        "arguments": {"kind": "tool", "name": "fixture__ordinary"},
                    },
                ),
            ]
            process = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    code,
                    str(ROOT / "skills"),
                    str(self.directory / ("stdio-" + version)),
                ],
                cwd=ROOT,
                input="".join(json.dumps(m) + "\n" for m in messages + requests),
                encoding="utf-8",
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            replies = {row["id"]: row for row in map(json.loads, process.stdout.splitlines())}
            _, headers, body = self.request("POST", "/mcp", messages[0])
            self.assertIn("result", json.loads(body))
            session = (
                {
                    "MCP-Session-Id": next(
                        value for key, value in headers.items() if key.lower() == "mcp-session-id"
                    )
                }
                if version != MODERN
                else {}
            )
            if version != MODERN:
                self.request("POST", "/mcp", messages[1], headers=session)
            for message_ in requests:
                _, _, body = self.request("POST", "/mcp", message_, headers=session)
                response = json.loads(body)
                self.assertEqual(response["result"], replies[message_["id"]]["result"])
            listed = replies[2]["result"]["tools"]
            names = {item["name"] for item in listed}
            self.assertNotIn("fixture__ordinary", names)
            self.assertIn("fixture__app", names)
            self.assertIn("fixture__work", names)
            results = json.loads(replies[3]["result"]["content"][0]["text"])
            self.assertLessEqual(len(results), 5)
            self.assertTrue(all("inputSchema" not in item for item in results))
        self.hub.configure_catalog({"exposure": "all-native"})
        response = self.hub.rpc(modern("tools/list", {}), {})
        self.assertIn("fixture__ordinary", {item["name"] for item in response["result"]["tools"]})

    def test_http_api_uses_same_defaults_and_mutations_require_management_auth(self):
        seed(self.hub)
        status, _, body = self.request(path="/api/v1/search?q=")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), self.hub.search(""))
        status, _, body = self.request(path="/api/v1/catalog/item?kind=tool&name=fixture__ordinary")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["inputSchema"], TOOLS[0]["inputSchema"])
        status, _, _ = self.request("POST", "/api/v1/catalog/settings", {"usage_enabled": True})
        self.assertEqual(status, 403)
        status, _, _ = self.request(
            "POST",
            "/api/v1/catalog/settings",
            {"usage_enabled": True},
            headers={"X-Hub-Token": self.server.token},
        )
        self.assertEqual(status, 200)
