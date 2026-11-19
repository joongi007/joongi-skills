"""Browser profile contracts; mock destinations, never probe private services."""

import json
import os
import runpy
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.browser_proxy import EgressProxy, origins, public_addresses
from joongi_hub.browser_runtime import BrowserExecution, server_config
from joongi_hub.errors import RpcError
from joongi_hub.sandbox import Execution, validate_sandbox

IMAGE = "sha256:" + "a" * 64
ROOT = Path(__file__).resolve().parents[1]


class BrowserContracts(unittest.TestCase):
    def test_origins_are_exact_https_hosts_without_wildcards_or_credentials(self):
        self.assertEqual(
            origins(["https://EXAMPLE.com/", "https://example.com"]), ["https://example.com"]
        )
        for value in (
            [],
            ["http://example.com"],
            ["https://127.0.0.1"],
            ["https://[::1]"],
            ["https://*.example.com"],
            ["https://example.com:8443"],
            ["https://user@example.com"],
            ["https://example.com/path"],
            ["https://example.com?token=a"],
            ["https://example.com#fragment"],
            [None],
        ):
            with self.subTest(value=value), self.assertRaises(RpcError):
                origins(value)

    def test_dns_mixed_private_reserved_and_special_answers_fail_closed(self):
        for answers in (
            [],
            ["127.0.0.1"],
            ["10.0.0.1"],
            ["169.254.169.254"],
            ["100.64.0.1"],
            ["0.0.0.0"],
            ["224.0.0.1"],
            ["93.184.215.14", "192.168.1.1"],
        ):
            records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in answers]
            with (
                self.subTest(answers=answers),
                patch("socket.getaddrinfo", return_value=records),
                self.assertRaises(ValueError),
            ):
                public_addresses("example.com")
        with patch(
            "socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))],
        ):
            self.assertEqual(public_addresses("example.com"), ["93.184.215.14"])

    def test_profile_cannot_enable_mounts_host_secrets_or_unpinned_images(self):
        config = server_config(IMAGE, ["https://example.com"])
        self.assertIn("policy", config)
        self.assertEqual(config["policy"]["allowed_tools"], [])
        for changed in (
            {"image": "browser:latest"},
            {"read": ["/home"]},
            {"mounts": []},
            {"browser_display": "x11"},
            {"cpu_seconds": 120},
        ):
            with self.subTest(changed=changed), self.assertRaises(RpcError):
                validate_sandbox({**config["sandbox"], **changed})
        for extra in (
            {"env": {"KEY": "SECRET"}},
            {"auth": {"type": "oauth"}},
            {"policy": {"allowed_tools": ["*"]}},
        ):
            with self.subTest(extra=extra), self.assertRaises(RpcError):
                BrowserExecution({**config, **extra})

    @unittest.skipUnless(sys.platform == "linux", "Linux/WSL container profile")
    def test_execution_ignores_supplied_command_and_environment(self):
        config = server_config(IMAGE, ["https://example.com"])
        config.update(command="malicious-command", args=["/private"], enabled=True)
        with (
            patch("joongi_hub.browser_runtime.engine_info", return_value="/docker"),
            patch("subprocess.run"),
            patch("joongi_hub.browser_runtime.EgressProxy"),
        ):
            execution = Execution(config, {"SECRET": "must-not-pass"})
            try:
                command = execution.command
                self.assertIn("--network=none", command)
                self.assertIn("--read-only", command)
                self.assertIn("--cap-drop=ALL", command)
                self.assertIn("--pull=never", command)
                self.assertEqual(command[-1], IMAGE)
                self.assertNotIn("SECRET", " ".join(command))
                self.assertNotIn("malicious-command", command)
                self.assertNotIn("--privileged", command)
                self.assertEqual(sum(arg.startswith("type=bind,") for arg in command), 1)
            finally:
                execution.cleanup()

    def test_reduced_surface_rejects_code_files_unbounded_images_and_navigation(self):
        with patch.dict(os.environ, JOONGI_BROWSER_ORIGINS='["https://example.com"]'):
            entry = runpy.run_path(str(ROOT / "joongi_hub/browser_container/entry.py"))
        check = entry["check"]
        check("browser_navigate", {"url": "https://example.com/path"})
        check("browser_take_screenshot", {})
        for name, arguments in (
            ("browser_evaluate", {"function": "() => 1"}),
            ("browser_file_upload", {}),
            ("browser_take_screenshot", {"fullPage": True}),
            ("browser_snapshot", {"filename": "/tmp/file"}),
            ("browser_navigate", {"url": "file:///etc/passwd"}),
            ("browser_navigate", {"url": "https://other.example/"}),
            ("browser_navigate", {"url": "https://user@example.com/"}),
            ("browser_mouse_click_xy", {"x": 1280, "y": 10}),
            ("browser_wait_for", {"time": 11}),
        ):
            with self.subTest(name=name, arguments=arguments), self.assertRaises(ValueError):
                check(name, arguments)

    @unittest.skipUnless(hasattr(socket, "AF_UNIX") and sys.platform != "win32", "Unix sockets")
    def test_proxy_rejects_unapproved_host_before_dns_or_connection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proxy.sock"
            proxy = EgressProxy(path, ["https://example.com"])
            try:
                with patch(
                    "socket.getaddrinfo", side_effect=AssertionError("No DNS for unapproved hosts")
                ):
                    with socket.socket(socket.AF_UNIX) as client:
                        client.settimeout(2)
                        client.connect(str(path))
                        client.sendall(b"CONNECT other.example:443 HTTP/1.1\r\n\r\n")
                        self.assertIn(b"403 Forbidden", client.recv(1024))
            finally:
                proxy.close()

    @unittest.skipUnless(hasattr(socket, "AF_UNIX") and sys.platform != "win32", "Unix sockets")
    def test_proxy_pins_validated_numeric_address_and_relays_both_directions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proxy.sock"
            proxy = EgressProxy(path, ["https://example.com"])
            origin, remote = socket.socketpair()
            self.addCleanup(origin.close)
            self.addCleanup(remote.close)
            remote.settimeout(2)
            public = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.215.14", 443))]
            try:
                with (
                    patch(
                        "socket.getaddrinfo",
                        side_effect=[public, AssertionError("DNS re-resolved")],
                    ) as dns,
                    patch("socket.create_connection", return_value=origin) as connect,
                ):
                    with socket.socket(socket.AF_UNIX) as client:
                        client.settimeout(2)
                        client.connect(str(path))
                        client.sendall(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
                        self.assertIn(b"200 Connection Established", client.recv(1024))
                        client.sendall(b"client-fixture")
                        self.assertEqual(remote.recv(1024), b"client-fixture")
                        remote.sendall(b"server-fixture")
                        self.assertEqual(client.recv(1024), b"server-fixture")
                    self.assertEqual(dns.call_count, 1)
                    connect.assert_called_once_with(("93.184.215.14", 443), timeout=8)
            finally:
                proxy.close()

    def test_dependency_lock_pins_official_runtime_integrity(self):
        lock = json.loads((ROOT / "joongi_hub/browser_container/package-lock.json").read_text())
        package = lock["packages"]["node_modules/@playwright/mcp"]
        self.assertEqual(package["version"], "0.0.86")
        self.assertEqual(
            package["integrity"],
            "sha512-4SL9OSINmik3+EObCYJIxH8BkhcqqGU6CM8XIgztW015iBVR9WR6Q0xF180Ery+xuEVyyK5r6nC2bOg3zjgCoA==",
        )
