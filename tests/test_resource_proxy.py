"""Resource namespace changes must preserve opaque application payloads."""

import copy
import unittest

from joongi_hub.service import resource_uri, rewrite_resources, unwrap_resource


class ResourceProxyTests(unittest.TestCase):
    def test_uri_round_trip_preserves_opaque_and_hierarchical_identifiers(self):
        for uri in (
            "urn:manual:7",
            "https://docs.example/a?q=one#part",
            "skill://review/SKILL.md",
            "file:///a/b.md",
        ):
            with self.subTest(uri=uri):
                self.assertEqual(unwrap_resource(resource_uri("source", uri)), ("source", uri))
        self.assertTrue(
            resource_uri("source", "skill://review/SKILL.md").endswith("/review/SKILL.md")
        )

    def test_tool_result_preserves_business_payload_and_schema(self):
        payload = {
            "structuredContent": {
                "uri": "https://business.example/invoice/7",
                "resources": [{"uri": "asset:7"}],
            },
            "_meta": {
                "business": {"uri": "opaque:invoice"},
                "ui": {"resourceUri": "ui://panel/main"},
            },
            "inputSchema": {"properties": {"uri": {"default": "https://business.example"}}},
            "content": [{"type": "text", "text": "uri://literal", "uri": "opaque:text-field"}],
        }
        original = copy.deepcopy(payload)
        result = rewrite_resources(payload, "billing")
        self.assertEqual(result["structuredContent"], original["structuredContent"])
        self.assertEqual(result["inputSchema"], original["inputSchema"])
        self.assertEqual(result["content"], original["content"])
        self.assertEqual(result["_meta"]["business"], original["_meta"]["business"])
        self.assertEqual(
            result["_meta"]["ui"]["resourceUri"], resource_uri("billing", "ui://panel/main")
        )
        self.assertEqual(payload, original)

    def test_tool_content_resources_and_links_are_namespaced(self):
        result = rewrite_resources(
            {
                "content": [
                    {"type": "resource_link", "uri": "file:///manual.md", "name": "manual"},
                    {
                        "type": "resource",
                        "resource": {
                            "uri": "ui://panel/main",
                            "mimeType": "text/html",
                            "text": "<p>URI stays literal</p>",
                        },
                    },
                ]
            },
            "docs",
        )
        self.assertEqual(result["content"][0]["uri"], resource_uri("docs", "file:///manual.md"))
        self.assertEqual(
            result["content"][1]["resource"]["uri"], resource_uri("docs", "ui://panel/main")
        )
        self.assertEqual(result["content"][1]["resource"]["text"], "<p>URI stays literal</p>")

    def test_skill_manifests_keep_digests_and_frontmatter_opaque(self):
        entry = {
            "uri": "skill://review/SKILL.md",
            "frontmatter": {"name": "review", "uri": "custom:metadata"},
            "resources": [{"uri": "skill://review/refs.md", "size": 3, "digest": "sha256:abc"}],
        }
        result = rewrite_resources({"skills": [entry]}, "remote")["skills"][0]
        self.assertEqual(result["uri"], resource_uri("remote", entry["uri"]))
        self.assertEqual(result["frontmatter"], entry["frontmatter"])
        self.assertEqual(
            result["resources"][0],
            {
                "uri": resource_uri("remote", "skill://review/refs.md"),
                "size": 3,
                "digest": "sha256:abc",
            },
        )
        self.assertEqual(rewrite_resources(entry, "remote"), result)
        self.assertEqual(rewrite_resources([entry], "remote"), [result])

    def test_resource_read_list_and_prompt_embedded_resources(self):
        uri = "file:///doc.md"
        payload = {"contents": [{"uri": uri, "text": "body", "_meta": {"uri": "business:opaque"}}]}
        result = rewrite_resources(payload, "docs")
        self.assertEqual(result["contents"][0]["uri"], resource_uri("docs", uri))
        self.assertEqual(result["contents"][0]["_meta"]["uri"], "business:opaque")
        self.assertEqual(
            rewrite_resources([{"uri": uri, "name": "doc"}], "docs")[0]["uri"],
            resource_uri("docs", uri),
        )
        prompt = {
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "resource", "resource": {"uri": uri, "text": "body"}},
                }
            ]
        }
        self.assertEqual(
            rewrite_resources(prompt, "docs")["messages"][0]["content"]["resource"]["uri"],
            resource_uri("docs", uri),
        )

    def test_apps_schema_defaults_remain_unchanged(self):
        tool = {
            "name": "remote__app",
            "inputSchema": {"properties": {"uri": {"default": "urn:input"}}},
            "_meta": {
                "ui": {"resourceUri": "ui://app/main"},
                "provider": {"resourceUri": "urn:opaque"},
            },
        }
        result = rewrite_resources(tool, "remote")
        self.assertEqual(result["inputSchema"], tool["inputSchema"])
        self.assertEqual(result["_meta"]["provider"], tool["_meta"]["provider"])
        self.assertEqual(
            result["_meta"]["ui"]["resourceUri"], resource_uri("remote", "ui://app/main")
        )
