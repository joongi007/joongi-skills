"""Transport choices must preserve scope, state, ownership and call semantics."""

import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.connections import (
    ConnectionSettings,
    agent_value,
    configuration,
    running,
    select_bridge,
)
from joongi_hub.errors import RpcError
from joongi_hub.lifecycle import manage
from joongi_hub.server import HubServer
from joongi_hub.service import Hub
from joongi_hub.storage import atomic_json

ROOT = Path(__file__).resolve().parents[1]


class Connections(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.hub = Hub(ROOT / "skills", self.root / "state")
        self.addCleanup(self.hub.close)
        self.hub.agent_connections.home = self.home
        self.project_root = self.root / "project"
        self.project_root.mkdir()
        self.hub.projects.put(
            {"id": "p", "root": str(self.project_root), "common_skills": ["usual-korean"]}
        )
        self.panel = HubServer(("127.0.0.1", 0), self.hub)
        self.addCleanup(self.panel.server_close)
        self.addCleanup(self.panel.shutdown)
        threading.Thread(target=self.panel.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.panel.server_port}"
        atomic_json(
            self.root / "state/endpoint.json",
            {"pid": os.getpid(), "url": self.url, "instance": self.panel.instance_id},
        )

    def settings(self, mode="stdio", fallback="stdio"):
        return {"mode": mode, "url": self.url, "fallback": fallback}

    def request(self, path, body, headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.panel.server_port, timeout=5)
        client.request(
            "POST", path, json.dumps(body), {"Content-Type": "application/json", **(headers or {})}
        )
        response = client.getresponse()
        data = response.read()
        result = (response.status, json.loads(data) if data else None, dict(response.headers))
        client.close()
        return result

    def stdio(self, mode=None, extra=None):
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "resources/list", "params": {}},
        ]
        command = [
            sys.executable,
            "-B",
            "-m",
            "joongi_hub",
            "stdio",
            "--state-dir",
            str(self.root / "state"),
        ]
        if mode:
            command += ["--mode", mode]
        return subprocess.run(
            command + (extra or []),
            input="\n".join(json.dumps(m) for m in messages) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )

    def test_default_stdio_never_probes_http_and_hybrid_discovers_matching_store(self):
        with patch(
            "joongi_hub.connections.health", side_effect=AssertionError("stdio must not probe")
        ):
            self.assertIsNone(select_bridge(self.root / "state", self.settings()))
        self.assertEqual(select_bridge(self.root / "state", self.settings("hybrid")), self.url)
        self.assertIsNone(select_bridge(self.root / "other", self.settings("hybrid")))
        with self.assertRaises(RpcError):
            select_bridge(
                self.root / "state", {**self.settings("http"), "url": "http://127.0.0.1:1"}
            )
        with self.assertRaises(RpcError):
            select_bridge(self.root / "other", self.settings("http"))
        with self.assertRaises(RpcError):
            select_bridge(self.root / "other", self.settings("hybrid", "error"))

    def test_saved_modes_change_new_stdio_process_without_changing_store(self):
        for mode in ("stdio", "hybrid", "http"):
            self.hub.connection_settings.put(self.settings(mode))
            result = self.stdio()
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertIn("usual-korean", json.dumps(rows[-1]))
        # A command-line override wins over a saved HTTP mode.
        self.assertEqual(self.stdio("stdio").returncode, 0)

    def test_http_unavailable_is_error_and_hybrid_fallback_is_startup_only(self):
        self.assertNotEqual(self.stdio("http", ["--url", "http://127.0.0.1:1"]).returncode, 0)
        self.assertEqual(self.stdio("hybrid", ["--url", "http://127.0.0.1:1"]).returncode, 0)
        self.assertNotEqual(
            self.stdio("hybrid", ["--url", "http://127.0.0.1:1", "--fallback", "error"]).returncode,
            0,
        )

    def test_settings_inherit_and_override_without_changing_project_state(self):
        project = self.hub.scoped("p")
        before = project.state_dir
        self.hub.connection_settings.put(self.settings("hybrid"))
        self.assertEqual(project.connection_settings.get()["mode"], "hybrid")
        project.connection_settings.put(self.settings("http"))
        self.assertEqual(self.hub.connection_settings.get()["mode"], "hybrid")
        project.connection_settings.put({"inherit": True})
        self.assertEqual(project.connection_settings.get()["mode"], "hybrid")
        self.assertEqual(project.state_dir, before)

    def test_bridge_failure_after_initialize_does_not_switch_to_local_execution(self):
        command = [
            sys.executable,
            "-B",
            "-m",
            "joongi_hub",
            "stdio",
            "--mode",
            "hybrid",
            "--state-dir",
            str(self.root / "state"),
        ]
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        try:
            message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
            child.stdin.write(json.dumps(message) + "\n")
            child.stdin.flush()
            self.assertIn("result", json.loads(child.stdout.readline()))
            self.panel.shutdown()
            self.panel.server_close()
            output, error = child.communicate(
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "resources/list"}) + "\n",
                timeout=10,
            )
            self.assertEqual(child.returncode, 0, error)
            self.assertIn("error", json.loads(output))
        finally:
            if child.poll() is None:
                child.terminate()
                child.communicate(timeout=5)

    @unittest.skipIf(os.name == "nt", "Windows terminate uses immediate TerminateProcess")
    def test_stdio_sigterm_gracefully_closes_its_upstream(self):
        record = self.root / "upstream.pid"
        fixture = self.root / "owned-fixture.py"
        fixture.write_text(
            "import os,runpy,sys\nfrom pathlib import Path\n"
            + f"sys.path.insert(0,{str(ROOT)!r})\n"
            + f"Path({str(record)!r}).write_text(str(os.getpid()))\n"
            + f"runpy.run_path({str(ROOT / 'tests/fixtures/mcp_server.py')!r},"
            + "run_name='__main__')\n"
        )
        self.hub.register(
            {
                "id": "owned",
                "transport": "stdio",
                "command": sys.executable,
                "args": ["-B", str(fixture)],
            }
        )
        child = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-m",
                "joongi_hub",
                "stdio",
                "--mode",
                "stdio",
                "--state-dir",
                str(self.root / "state"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        owned_pid = None
        try:
            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "hub_connect", "arguments": {"server": "owned"}},
                },
            ]
            child.stdin.write("\n".join(json.dumps(m) for m in messages) + "\n")
            child.stdin.flush()
            self.assertIn("result", json.loads(child.stdout.readline()))
            self.assertIn("result", json.loads(child.stdout.readline()))
            owned_pid = int(record.read_text())
            child.terminate()
            child.wait(timeout=10)
            self.assertEqual(child.returncode, 0)
            from joongi_hub.runtime import process_alive

            self.assertFalse(process_alive(owned_pid))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()
            if owned_pid:
                from joongi_hub.runtime import process_alive

                if process_alive(owned_pid):
                    import signal

                    os.kill(owned_pid, signal.SIGTERM)

    def test_state_paths_are_absolute_in_generated_configs(self):
        original = Path.cwd()
        try:
            os.chdir(self.root)
            hub = Hub(ROOT / "skills", Path("relative-state"))
            try:
                self.assertTrue(hub.state_dir.is_absolute())
                cfg = configuration(hub)
                self.assertEqual(
                    cfg["args"][cfg["args"].index("--state-dir") + 1],
                    str(self.root / "relative-state"),
                )
            finally:
                hub.close()
        finally:
            os.chdir(original)

    def test_invalid_modes_urls_and_fields_are_rejected(self):
        for value in [
            [],
            {"mode": "http"},
            {**self.settings(), "mode": []},
            {**self.settings(), "extra": True},
            *[
                {**self.settings(), "url": url}
                for url in [
                    "https://example.com",
                    "http://127.0.0.1:1/mcp",
                    "http://user:secret@127.0.0.1:1",
                    "http://127.0.0.1:1#x",
                    "http://169.254.169.254:80",
                ]
            ],
        ]:
            with self.subTest(value=value), self.assertRaises(RpcError):
                self.hub.connection_settings.put(value)

    def test_http_project_url_binds_legacy_session_and_rejects_scope_conflicts(self):
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        }
        status, data, headers = self.request("/mcp/projects/p", initialize)
        self.assertEqual(status, 200, data)
        session = headers["Mcp-Session-Id"]
        h = {"Mcp-Session-Id": session}
        self.request(
            "/mcp/projects/p", {"jsonrpc": "2.0", "method": "notifications/initialized"}, h
        )
        status, data, _ = self.request(
            "/mcp/projects/p", {"jsonrpc": "2.0", "id": 2, "method": "resources/list"}, h
        )
        self.assertEqual(status, 200)
        self.assertIn("usual-korean", json.dumps(data))
        self.assertNotIn("engineering-playbook", json.dumps(data))
        self.assertEqual(
            self.request("/mcp/projects/p", initialize, {"X-Hub-Profile": "global"})[0], 400
        )
        self.assertEqual(self.request("/mcp/projects/missing", initialize)[0], 400)

    def test_modern_project_url_and_generated_agent_configs(self):
        self.hub.connection_settings.put(self.settings("http"))
        cfg = configuration(self.hub, "p")
        self.assertEqual(cfg, {"url": self.url + "/mcp/projects/p"})
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "resources/list",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
        }
        status, result, _ = self.request("/mcp/projects/p", request)
        self.assertEqual(status, 200, result)
        self.assertNotIn("engineering-playbook", json.dumps(result))
        self.assertEqual(agent_value("gemini", cfg), {"httpUrl": cfg["url"]})
        self.assertEqual(agent_value("opencode", cfg)["type"], "remote")
        self.assertEqual(agent_value("codex", cfg), cfg)

    def test_project_http_url_cannot_end_a_different_profile_session(self):
        self.panel.sessions["global-session"] = {"profile": "global"}
        client = http.client.HTTPConnection("127.0.0.1", self.panel.server_port)
        client.request("DELETE", "/mcp/projects/p", headers={"Mcp-Session-Id": "global-session"})
        response = client.getresponse()
        response.read()
        client.close()
        self.assertEqual(response.status, 400)
        self.assertIn("global-session", self.panel.sessions)

    def test_registration_plan_updates_all_six_agents_and_preserves_unrelated_values(self):
        (self.home / ".codex").mkdir()
        (self.home / ".codex/config.toml").write_text('model = "keep-me"\n')
        agents = ["codex", "claude", "cursor", "copilot", "gemini", "opencode"]
        for mode in ("stdio", "hybrid", "http"):
            self.hub.connection_settings.put(self.settings(mode))
            manager = self.hub.agent_connections
            plan = manager.plan(agents)
            manager.apply(plan["id"])
            self.assertIn('model = "keep-me"', (self.home / ".codex/config.toml").read_text())
            with self.assertRaises(RpcError):
                manager.apply(plan["id"])
        self.assertEqual(
            json.loads((self.home / ".gemini/settings.json").read_text())["mcpServers"][
                "joongi-hub"
            ],
            {"httpUrl": self.url + "/mcp"},
        )
        self.assertEqual(
            json.loads((self.home / ".claude.json").read_text())["mcpServers"]["joongi-hub"][
                "type"
            ],
            "http",
        )

    def test_registration_does_not_overwrite_unowned_or_edited_configs(self):
        (self.home / ".claude.json").write_text(
            '{"mcpServers":{"joongi-hub":{"command":"user-owned"}}}'
        )
        with self.assertRaises(RpcError):
            self.hub.agent_connections.plan(["claude"])
        plan = self.hub.agent_connections.plan(["codex"])
        (self.home / ".codex").mkdir()
        (self.home / ".codex/config.toml").write_text('model="changed-after-plan"')
        with self.assertRaises(RpcError):
            self.hub.agent_connections.apply(plan["id"])
        self.assertEqual(
            (self.home / ".codex/config.toml").read_text(), 'model="changed-after-plan"'
        )

    def test_plan_changes_settings_and_scope_are_rejected(self):
        manager = self.hub.agent_connections
        plan = manager.plan(["codex"])
        self.hub.connection_settings.put(self.settings("http"))
        with self.assertRaises(RpcError):
            manager.apply(plan["id"])
        with self.assertRaises(RpcError):
            self.hub.scoped("p").agent_connections.apply(plan["id"])

    def test_project_registrations_use_project_files_and_private_manifest(self):
        project = self.hub.scoped("p")
        project.connection_settings.put(self.settings("http"))
        manager = project.agent_connections
        plan = manager.plan(["claude", "copilot", "codex", "cursor", "gemini", "opencode"])
        manager.apply(plan["id"])
        self.assertIn("/mcp/projects/p", (self.project_root / ".mcp.json").read_text())
        self.assertIn("/mcp/projects/p", (self.project_root / ".github/mcp.json").read_text())
        self.assertTrue((self.project_root / ".joongi/private/mcp-installation.json").is_file())
        self.assertFalse((self.home / ".claude.json").exists())

    @unittest.skipIf(os.name == "nt", "WSL bridge is generated from its Linux environment")
    def test_windows_wsl_generator_uses_argument_array_and_rejects_bad_distribution(self):
        cfg = configuration(self.hub, "p", wsl_distribution="Ubuntu-24.04")
        self.assertEqual(cfg["command"], "wsl.exe")
        self.assertEqual(cfg["args"][:3], ["-d", "Ubuntu-24.04", "--exec"])
        self.assertIn("--profile", cfg["args"])
        with self.assertRaises(RpcError):
            configuration(self.hub, "p", wsl_distribution="Ubuntu; echo bad")

    def test_management_api_requires_token_and_settings_switch_leaves_tasks_unchanged(self):
        self.assertEqual(self.request("/api/v1/connection", self.settings("http"))[0], 403)
        task = self.hub.tasks.create("marker", "test")
        headers = {"X-Hub-Token": self.panel.token}
        self.assertEqual(self.request("/api/v1/connection", self.settings("http"), headers)[0], 200)
        self.assertEqual(self.hub.tasks.get(task["taskId"], "test")["taskId"], task["taskId"])
        self.assertEqual(
            self.request("/api/v1/runtime/stop", {"instance": "wrong"}, headers)[0], 400
        )


class Lifecycle(unittest.TestCase):
    def test_real_start_status_restart_stop_and_state_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            settings = ConnectionSettings(state)
            settings.put({"mode": "hybrid", "url": "http://127.0.0.1:8765", "fallback": "stdio"})
            try:
                first = manage("start", state, ROOT / "skills", 0)
                self.assertTrue(first["running"])
                self.assertEqual(
                    manage("start", state, ROOT / "skills")["instance"], first["instance"]
                )
                self.assertTrue(manage("status", state, ROOT / "skills")["running"])
                second = manage("restart", state, ROOT / "skills")
                self.assertNotEqual(first["instance"], second["instance"])
                self.assertEqual(first["url"], second["url"])
                self.assertEqual(settings.get()["mode"], "hybrid")
            finally:
                manage("stop", state, ROOT / "skills")
            self.assertFalse(manage("status", state, ROOT / "skills")["running"])
            self.assertFalse(manage("stop", state, ROOT / "skills")["stopped"])

    def test_install_and_start_survives_download_source_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "download"
            home = root / "home"
            source.mkdir()
            (source / "scripts").mkdir()
            for name in ("joongi_hub", "skills"):
                shutil.copytree(
                    ROOT / name, source / name, ignore=shutil.ignore_patterns("__pycache__")
                )
            shutil.copy2(ROOT / "scripts/install_manager.py", source / "scripts/install_manager.py")
            state = home / ".local/share/joongi-hub"
            command = [
                sys.executable,
                "-B",
                str(source / "scripts/install_manager.py"),
                "install",
                "--home",
                str(home),
                "--mode",
                "hybrid",
                "--start",
                "--port",
                "0",
            ]
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True, encoding="utf-8", timeout=30
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                record = running(state)
                self.assertIsNotNone(record)
                shutil.rmtree(source)
                from urllib.parse import urlsplit

                address = urlsplit(record["url"])
                client = http.client.HTTPConnection(address.hostname, address.port, timeout=5)
                client.request("GET", "/")
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn(b"Joongi Hub", response.read())
                client.request("GET", "/api/v1/connection")
                response = client.getresponse()
                info = json.loads(response.read())
                self.assertEqual(info["settings"]["mode"], "hybrid")
                self.assertIn(
                    repr(str(home / ".local/share/joongi-skills/runtime")),
                    info["connection"]["args"][1],
                )
                client.close()
            finally:
                manage("stop", state, ROOT / "skills")

    def test_cli_installer_mode_http_has_native_registration_and_update_detects_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".codex").mkdir()
            cmd = [
                sys.executable,
                "-B",
                str(ROOT / "scripts/install_manager.py"),
                "install",
                "--home",
                str(home),
                "--agent",
                "codex",
                "--mode",
                "http",
                "--url",
                "http://127.0.0.1:12345",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", timeout=30
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                'url = "http://127.0.0.1:12345/mcp"', (home / ".codex/config.toml").read_text()
            )
            self.assertEqual(
                ConnectionSettings(home / ".local/share/joongi-hub").get()["mode"], "http"
            )
