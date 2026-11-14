"""The code graph parses real source, detects staleness and works through Hub."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.code_graph import CodeGraph, rpc, server_config
from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from joongi_hub.upstream import VERSIONS
from scripts.check_code_graph import register

ROOT = Path(__file__).resolve().parents[1]


class CodeGraphTests(unittest.TestCase):
    def setUp(self):
        if os.name == "nt":
            from tests.fixtures.protocol_execution import ProtocolExecution

            executor = patch("joongi_hub.sandbox.Execution", ProtocolExecution)
            executor.start()
            self.addCleanup(executor.stop)

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        (self.project / "core.py").write_text(
            '"""Core module."""\ndef leaf():\n    return 3\n\n'
            "class Worker:\n    def work(self):\n        return leaf()\n"
        )
        (self.project / "entry.py").write_text(
            "from core import leaf as calculate\n\n"
            "def entry():\n    return calculate()\n\n"
            "def outer():\n    def nested():\n        return entry()\n    return nested()\n"
        )

    def test_cross_module_alias_callers_and_transitive_impact(self):
        graph = CodeGraph(self.project)
        callers = graph.query("graph_callers", {"symbol": "core.leaf"})["edges"]
        self.assertEqual(
            {item["source"].split(":")[0] for item in callers}, {"entry.entry", "core.Worker.work"}
        )
        impact = graph.query("graph_impact", {"symbol": "core.leaf", "depth": 4})
        self.assertIn(
            "entry.outer.nested", {item["symbol"]["qualified"] for item in impact["affected"]}
        )
        self.assertTrue(graph.status()["fresh"])

    def test_changes_additions_and_removals_require_explicit_reindex(self):
        graph = CodeGraph(self.project)
        (self.project / "added.py").write_text("def added():\n    return 1\n")
        self.assertEqual(graph.status()["changed_files"], ["added.py"])
        with self.assertRaises(RpcError):
            graph.query("graph_symbols", {"query": "added"})
        graph.query("graph_index", {})
        self.assertEqual(graph.query("graph_symbols", {"query": "added.added"})["total"], 1)
        (self.project / "added.py").unlink()
        self.assertFalse(graph.status()["fresh"])

    def test_relative_import_and_self_call_resolution(self):
        package = self.project / "pkg"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "core.py").write_text("def leaf():\n    return 1\n")
        (package / "api.py").write_text(
            "from .core import leaf\nclass Work:\n"
            "    def perform(self):\n        return leaf()\n"
            "    def run(self):\n        return self.perform()\n"
        )
        graph = CodeGraph(self.project)
        self.assertEqual(graph.query("graph_callers", {"symbol": "pkg.core.leaf"})["total"], 1)
        callers = graph.query("graph_callers", {"symbol": "pkg.api.Work.perform"})["edges"]
        self.assertTrue(callers[0]["source"].startswith("pkg.api.Work.run:"))

    def test_excluded_dependencies_and_unresolved_calls_remain_explicit(self):
        dependency = self.project / "node_modules/package"
        dependency.mkdir(parents=True)
        (dependency / "ignored.py").write_text("def hidden():\n    return 0\n")
        (self.project / "dynamic.py").write_text("def dispatch(callback):\n    return callback()\n")
        graph = CodeGraph(self.project)
        self.assertEqual(graph.query("graph_symbols", {"query": "hidden"})["total"], 0)
        edges = graph.query("graph_callees", {"symbol": "dynamic.dispatch"})["edges"]
        self.assertEqual(edges[0]["resolution"], "unresolved")
        self.assertIsNone(edges[0]["target"])

    def test_oversized_source_is_rejected_before_parsing(self):
        (self.project / "large.py").write_bytes(b"#" * (2 * 1024 * 1024 + 1))
        with self.assertRaises(RpcError):
            CodeGraph(self.project)

    def test_source_is_never_executed_and_errors_are_reported(self):
        marker = self.root / "should-not-exist"
        (self.project / "dangerous.py").write_text(f"open({str(marker)!r}, 'w').write('bad')\n")
        (self.project / "invalid.py").write_text("def invalid(:\n")
        graph = CodeGraph(self.project)
        self.assertFalse(marker.exists())
        self.assertEqual(graph.status()["parse_errors"][0]["path"], "invalid.py")

    def test_context_and_unknown_tool_validation(self):
        graph = CodeGraph(self.project)
        context = graph.query("graph_context", {"symbol": "core.leaf"})
        self.assertIn("return 3", context["source"])
        for name, args in [
            ("unknown", {}),
            ("graph_symbols", {"limit": 0}),
            ("graph_impact", {"symbol": "core.leaf", "depth": 99}),
        ]:
            with self.subTest(name=name), self.assertRaises(RpcError):
                graph.query(name, args)

    def test_symlink_sources_are_not_followed(self):
        external = self.root / "private.py"
        external.write_text("def secret():\n    return 'private'\n")
        try:
            (self.project / "outside.py").symlink_to(external)
        except OSError:
            self.skipTest("Symlink creation not available")
        self.assertEqual(
            CodeGraph(self.project).query("graph_symbols", {"query": "secret"})["total"], 0
        )

    def test_real_graph_server_through_hub_and_both_protocol_eras(self):
        for version in VERSIONS:
            with self.subTest(version=version):
                hub = Hub(ROOT / "skills", self.root / ("state-" + version))
                try:
                    config = server_config(self.project)
                    config["protocol_version"] = version
                    hub.register(config)
                    probe = hub.probe("code-graph")
                    self.assertEqual(probe["protocol_version"], version)
                    result = hub.invoke("code-graph__graph_callers", {"symbol": "core.leaf"})
                    self.assertEqual(result["structuredContent"]["total"], 2)
                    self.assertIn("graph_impact", [tool["name"] for tool in probe["tools"]])
                finally:
                    hub.close()

    def test_registration_never_replaces_another_server_implicitly(self):
        config = server_config(self.project)
        directory = self.root / "registry"
        register(config, directory)
        changed = {**config, "name": "someone else's server"}
        with self.assertRaises(RpcError):
            register(changed, directory)
        register(changed, directory, replace=True)

    def test_config_starts_from_any_working_directory(self):
        config = server_config(self.project)
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "server/discover",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
        }
        process = subprocess.run(
            [config["command"], *config["args"]],
            input=json.dumps(request) + "\n",
            capture_output=True,
            text=True,
            cwd=self.root,
            timeout=10,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("2026-07-28", json.loads(process.stdout)["result"]["supportedVersions"])

    def test_rpc_invalid_parameters(self):
        graph = CodeGraph(self.project)
        response = rpc(
            graph,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"},
                    "name": "graph_symbols",
                    "arguments": [],
                },
            },
            {},
        )
        self.assertEqual(response["error"]["code"], -32602)


if __name__ == "__main__":
    unittest.main()
