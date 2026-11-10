"""Retrieval contracts: identifiers, argument discovery, safe grep and scope."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.review_graph import tool_definitions
from joongi_hub.service import Hub

ROOT = Path(__file__).resolve().parents[1]


class CatalogSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hub = Hub(ROOT / "skills", Path(self.temp.name) / "state")
        self.addCleanup(self.hub.close)
        self.hub.register({"id": "docs", "transport": "stdio", "command": sys.executable})
        self.client = SimpleNamespace(
            version="2025-11-25",
            skill_entries=[],
            tools=[
                {
                    "name": "convert_to_markdown",
                    "description": "Convert a document to Markdown.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "source_uri": {
                                "type": "string",
                                "description": "The source file location.",
                            }
                        },
                    },
                },
                {
                    "name": "list_graph_stats_tool",
                    "description": "Get project graph statistics.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "repo_root": {
                                "type": "string",
                                "description": "Absolute project folder.",
                            }
                        },
                    },
                },
                {
                    "name": "getVersion",
                    "description": "Read the installed library version.",
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "a_general_guide",
                    "description": "convert to markdown " + ("generic tutorial " * 100),
                    "inputSchema": {"type": "object"},
                },
            ],
            close=lambda: None,
        )
        self.hub.clients["docs"] = self.client

    def test_exact_identifier_ranks_before_description_keyword_matches(self):
        result = self.hub.search("convert_to_markdown")
        self.assertEqual(result[0]["name"], "docs__convert_to_markdown")
        self.assertEqual(result[0]["kind"], "tool")

    def test_argument_names_are_searchable_and_camel_case_is_split(self):
        self.assertEqual(self.hub.search("repo_root")[0]["name"], "docs__list_graph_stats_tool")
        self.assertEqual(self.hub.search("get version", match="all")[0]["name"], "docs__getVersion")

    def test_bilingual_graph_keywords_find_same_tool_without_translation_service(self):
        self.client.tools = tool_definitions()
        for korean, english, name in [
            ("변경 영향", "affected", "get_impact_radius_tool"),
            ("호출 관계", "callers", "query_graph_tool"),
            ("코드 리뷰", "review context", "get_review_context_tool"),
            ("긴 함수", "large functions", "find_large_functions_tool"),
            ("도움말", "documentation", "get_docs_section_tool"),
            ("색인 상태", "index poll", "graph_project_status"),
            ("색인 생성", "background", "graph_build"),
        ]:
            for query in (korean, english):
                with self.subTest(query=query):
                    result = self.hub.search(query, kind="tool", match="all", limit=1)
                    self.assertEqual(result[0]["name"], "docs__" + name)

    def test_rare_terms_and_name_fields_outrank_description_noise(self):
        self.client.tools += [
            {
                "name": "a_noise_" + str(i),
                "description": "Convert document examples and broad examples.",
                "inputSchema": {},
            }
            for i in range(30)
        ]
        self.assertEqual(
            self.hub.search("convert markdown", limit=1)[0]["name"], "docs__convert_to_markdown"
        )

    def test_all_requires_both_terms_and_literal_does_not_interpret_regex(self):
        self.assertEqual(self.hub.search("markdown statistics", match="all"), [])
        self.assertEqual(self.hub.search("convert.*markdown", mode="literal"), [])
        result = self.hub.search("docs__convert_to_markdown", mode="literal")
        self.assertEqual([r["name"] for r in result], ["docs__convert_to_markdown"])

    def test_summary_then_exact_full_definition_keeps_origin_and_schema(self):
        small = self.hub.search("markdown", limit=1, detail="summary")[0]
        self.assertNotIn("inputSchema", small)
        self.assertEqual(small["server"], "docs")
        full = self.hub.search(small["name"], mode="literal", detail="full")[0]
        self.assertIn("source_uri", full["inputSchema"]["properties"])

    def test_filters_validation_and_no_automatic_connections(self):
        self.hub.register({"id": "pending", "transport": "stdio", "command": "missing-command"})
        self.assertTrue(self.hub.search("engineering", kind="skill"))
        self.assertEqual(self.hub.search("", server="pending"), [])
        self.assertNotIn("pending", self.hub.clients)
        for kwargs in [
            {"limit": True},
            {"limit": 0},
            {"limit": 101},
            {"mode": "semantic"},
            {"detail": "secret"},
            {"kind": "file"},
            {"match": "fuzzy"},
            {"server": 42},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(RpcError):
                self.hub.search("x", **kwargs)

    def test_korean_suffixes_and_schema_defaults_do_not_break_lookup(self):
        self.assertEqual(self.hub.search("한국어")[0]["name"], "usual-korean")
        self.client.tools[0]["inputSchema"]["properties"]["source_uri"]["default"] = (
            "NEVER_INDEX_TOKEN"
        )
        self.assertEqual(self.hub.search("NEVER_INDEX_TOKEN"), [])

    def test_regex_missing_binary_has_no_python_backtracking_fallback(self):
        with (
            patch("joongi_hub.search.shutil.which", return_value=None),
            self.assertRaises(RpcError),
        ):
            self.hub.search("graph|markdown", mode="regex")

    @unittest.skipUnless(shutil.which("rg"), "ripgrep optional")
    def test_regex_alternation_invalid_patterns_and_nested_repetition(self):
        result = self.hub.search("^convert_to_markdown$", mode="regex", kind="tool")
        self.assertEqual([r["name"] for r in result], ["docs__convert_to_markdown"])
        with self.assertRaises(RpcError):
            self.hub.search("(", mode="regex")
        with self.assertRaises(RpcError):
            self.hub.search("(?=graph)", mode="regex")
        self.client.tools.append(
            {"name": "long_text", "description": "a" * 7000 + "!", "inputSchema": {}}
        )
        self.assertEqual(self.hub.search("(a+)+$", mode="regex", kind="tool"), [])

    def test_mcp_search_options_and_read_only_annotation(self):
        descriptor = next(t for t in self.hub.tools() if t["name"] == "hub_search")
        self.assertTrue(descriptor["annotations"]["readOnlyHint"])
        self.assertIn("literal", descriptor["inputSchema"]["properties"]["mode"]["enum"])
        result = self.hub.invoke(
            "hub_search", {"query": "source_uri", "kind": "tool", "limit": 1, "detail": "summary"}
        )
        self.assertNotIn("inputSchema", result["content"][0]["text"])
