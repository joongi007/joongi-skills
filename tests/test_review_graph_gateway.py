"""A common graph MCP must isolate every explicitly selected repository."""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.service import Hub
from joongi_hub.storage import atomic_json

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "linux", "native graph sandbox requires Linux/WSL")
class ReviewGraphGatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Model a genuinely installed backend; importing it through ambient
        # PYTHONPATH would contradict the production credential boundary.
        cls.backend_home = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.backend_home.cleanup)
        directory = Path(cls.backend_home.name)
        venv.EnvBuilder(with_pip=False, symlinks=os.name != "nt").create(directory)
        cls.interpreter = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        library = Path(
            subprocess.check_output(
                [
                    str(cls.interpreter),
                    "-c",
                    "import sysconfig;print(sysconfig.get_path('purelib'))",
                ],
                text=True,
            ).strip()
        )
        shutil.copytree(
            ROOT / "tests/fixtures/graph_backend/code_review_graph", library / "code_review_graph"
        )

    def setUp(self):
        from joongi_hub.review_graph import Gateway

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a, self.b = self.root / "skills", self.root / "game"
        for repo, name in [(self.a, "skill_only"), (self.b, "game_only")]:
            repo.mkdir()
            (repo / ".git").mkdir()
            (repo / (name + ".py")).write_text("def " + name + "():\n return 1\n")
        self.gateway = Gateway(self.interpreter, self.root / "cache", [self.root], "landlock")
        self.addCleanup(self.gateway.close)

    def build(self, repo):
        self.gateway.query("graph_build", {"repo_root": str(repo)})
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = self.gateway.query("graph_project_status", {"repo_root": str(repo)})[
                "structuredContent"
            ]
            if result["status"] != "building":
                self.assertEqual(result["status"], "ready", result)
                return result
            time.sleep(0.03)
        self.fail("Build did not finish")

    def test_two_repositories_keep_separate_graphs_when_calls_alternate(self):
        a, b = self.build(self.a), self.build(self.b)
        self.assertNotEqual(a["data_dir"], b["data_dir"])
        before = (Path(a["data_dir"]) / "graph.db").read_bytes()
        for repo, expected in [
            (self.a, "skill_only.py"),
            (self.b, "game_only.py"),
            (self.a, "skill_only.py"),
        ]:
            result = self.gateway.query("list_graph_stats_tool", {"repo_root": str(repo)})
            self.assertEqual(result["structuredContent"]["files"], [expected])
        self.assertEqual((Path(a["data_dir"]) / "graph.db").read_bytes(), before)
        self.assertFalse((self.a / ".code-review-graph").exists())
        self.assertFalse((self.b / ".code-review-graph").exists())

    def test_nested_build_and_analysis_do_not_inherit_ambient_secrets(self):
        with patch.dict(os.environ, {"JOONGI_AUDIT_FAKE_TOKEN": "fake-only-not-real"}):
            self.build(self.a)
            content = self.gateway.query("list_graph_stats_tool", {"repo_root": str(self.a)})[
                "structuredContent"
            ]
        self.assertFalse(content["build_ambient_secret"])
        self.assertFalse(content["serve_ambient_secret"])

    def test_every_analysis_tool_requires_explicit_repository(self):
        from joongi_hub.review_graph import tool_definitions

        for tool in tool_definitions():
            self.assertIn("repo_root", tool["inputSchema"]["required"])
        with self.assertRaises(RpcError):
            self.gateway.query("list_graph_stats_tool", {})
        with self.assertRaises(RpcError):
            self.gateway.query("list_graph_stats_tool", {"repo_root": "relative/game"})

    def test_ready_is_not_reported_until_worker_releases_its_log(self):
        root, folder = self.gateway.select(str(self.a))
        (folder / "data").mkdir(exist_ok=True)
        (folder / "data/graph.db").touch()
        atomic_json(folder / "build.json", {"status": "ready", "pid": 12345})
        with patch("joongi_hub.review_graph.process_alive", return_value=True):
            self.assertEqual(self.gateway.status(root, folder)["status"], "building")
        with patch("joongi_hub.review_graph.process_alive", return_value=False):
            self.assertEqual(self.gateway.status(root, folder)["status"], "ready")

    def test_unindexed_repo_has_actionable_status_without_using_another_graph(self):
        self.build(self.a)
        result = self.gateway.query("graph_project_status", {"repo_root": str(self.b)})
        self.assertEqual(result["structuredContent"]["status"], "not_indexed")
        with self.assertRaises(RpcError):
            self.gateway.query("list_graph_stats_tool", {"repo_root": str(self.b)})
        self.assertEqual(
            self.gateway.query("list_graph_stats_tool", {"repo_root": str(self.a)})[
                "structuredContent"
            ]["files"],
            ["skill_only.py"],
        )

    def test_another_gateway_process_sees_completed_index_and_build_is_idempotent(self):
        from joongi_hub.review_graph import Gateway

        first = self.build(self.a)
        other = Gateway(self.interpreter, self.root / "cache", [self.root], "landlock")
        self.addCleanup(other.close)
        second = other.query("graph_build", {"repo_root": str(self.a)})["structuredContent"]
        self.assertEqual(second["status"], "ready")
        self.assertEqual(first["data_dir"], second["data_dir"])

    @unittest.skipIf(os.name == "nt", "POSIX symlink")
    def test_symlink_alias_uses_the_same_cache(self):
        first = self.build(self.a)
        alias = self.root / "alias"
        alias.symlink_to(self.a, target_is_directory=True)
        result = self.gateway.query("graph_project_status", {"repo_root": str(alias)})[
            "structuredContent"
        ]
        self.assertEqual(first["data_dir"], result["data_dir"])

    def test_non_git_project_requires_explicit_marker_creation(self):
        repo = self.root / "no-git"
        repo.mkdir()
        with self.assertRaises(RpcError):
            self.gateway.query("graph_build", {"repo_root": str(repo)})
        self.assertFalse((repo / ".code-review-graph").exists())
        self.gateway.query("graph_build", {"repo_root": str(repo), "initialize_project": True})
        self.assertTrue((repo / ".code-review-graph").is_dir())
        self.build(repo)

    def test_hub_stdio_routes_two_projects_and_new_connection_reuses_the_index(self):
        from joongi_hub.review_graph import server_config

        config = server_config(
            self.interpreter,
            self.root / "cache",
            read_roots=[self.a, self.b],
            process_backend="landlock",
        )
        first = Hub(ROOT / "skills", self.root / "hub")
        self.addCleanup(first.close)
        first.register(config)
        self.assertEqual(len(first.probe("code-review-graph")["tools"]), 9)
        self.build(self.a)
        self.build(self.b)
        for repo, filename in [(self.a, "skill_only.py"), (self.b, "game_only.py")]:
            response = first.invoke(
                "code-review-graph__list_graph_stats_tool", {"repo_root": str(repo)}
            )
            self.assertEqual(response["structuredContent"]["files"], [filename])
        second = Hub(ROOT / "skills", self.root / "hub")
        self.addCleanup(second.close)
        response = second.invoke(
            "code-review-graph__list_graph_stats_tool", {"repo_root": str(self.b)}
        )
        self.assertEqual(response["structuredContent"]["files"], ["game_only.py"])
