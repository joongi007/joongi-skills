"""Bound the full request, preserve TLS host identity and pin validated addresses."""

import http.client
import json
import socket
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.upstream import HttpTransport, StdioTransport, validate_url


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass


class TransportTests(unittest.TestCase):
    def start_server(self, mode):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                seen.append(self.headers.get("Host"))
                self.rfile.read(int(self.headers["Content-Length"]))
                if mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://169.254.169.254/metadata")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                elif mode in {"drip-json", "drip-sse"}:
                    self.send_response(200)
                    self.send_header(
                        "Content-Type",
                        "text/event-stream" if mode == "drip-sse" else "application/json",
                    )
                    self.send_header("Content-Length", "100000")
                    self.end_headers()
                    # Remain active more often than the inactivity timeout;
                    # neither a JSON response nor an SSE line ever completes.
                    for _ in range(100):
                        try:
                            self.wfile.write(b" ")
                            self.wfile.flush()
                        except OSError:
                            break
                        time.sleep(0.025)
                elif mode == "oversize":
                    self.send_response(200)
                    self.send_header("Content-Length", str(5 * 1024 * 1024))
                    self.end_headers()
                else:
                    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

        server = QuietServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1], seen

    @staticmethod
    def message():
        return {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}

    def test_ipv4_mapped_metadata_is_blocked(self):
        address = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:169.254.169.254", 80, 0, 0))
        with patch("joongi_hub.upstream.socket.getaddrinfo", return_value=[address]):
            with self.assertRaisesRegex(RpcError, "link-local"):
                validate_url("http://metadata.example/mcp")

    def test_resolution_is_bounded(self):
        def resolve(*args, **kwargs):
            time.sleep(0.3)
            return []

        started = time.monotonic()
        with patch("joongi_hub.upstream.socket.getaddrinfo", side_effect=resolve):
            with self.assertRaisesRegex(RpcError, "lookup timed out"):
                validate_url("http://slow.example/mcp", timeout=0.04)
        self.assertLess(time.monotonic() - started, 0.2)

    def test_connection_uses_verified_sockaddr_without_second_dns_lookup(self):
        port, seen = self.start_server("ok")
        address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
        with patch("joongi_hub.upstream.socket.getaddrinfo", return_value=[address]) as resolver:
            result = HttpTransport({"url": f"http://original.example:{port}/mcp"}).exchange(
                self.message()
            )
        self.assertEqual(result["id"], 1)
        self.assertEqual(resolver.call_count, 1)
        self.assertEqual(seen, [f"original.example:{port}"])

    def test_tls_connection_keeps_original_hostname(self):
        # HTTPSConnection supplies this hostname to TLS SNI and certificate
        # verification; only its _create_connection path is replaced.
        seen = []

        class FakeHTTPS(http.client.HTTPConnection):
            def __init__(self, host, port=None, timeout=None):
                seen.append(host)
                super().__init__(host, port, timeout=timeout)

        port, _ = self.start_server("ok")
        address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))
        with (
            patch("joongi_hub.upstream.socket.getaddrinfo", return_value=[address]),
            patch("joongi_hub.upstream.http.client.HTTPSConnection", FakeHTTPS),
        ):
            HttpTransport({"url": f"https://secure.example:{port}/mcp"}).exchange(self.message())
        self.assertEqual(seen, ["secure.example"])

    def test_http_redirect_is_not_followed(self):
        port, seen = self.start_server("redirect")
        with self.assertRaisesRegex(RpcError, "redirects are not followed"):
            HttpTransport({"url": f"http://127.0.0.1:{port}/mcp"}).exchange(self.message())
        self.assertEqual(len(seen), 1)

    def test_slow_drip_has_total_deadline_for_json_and_partial_sse_line(self):
        for mode in ("drip-json", "drip-sse"):
            with self.subTest(mode=mode):
                port, _ = self.start_server(mode)
                started = time.monotonic()
                with patch("joongi_hub.upstream.TIMEOUT", 0.15):
                    with self.assertRaises(RpcError):
                        HttpTransport({"url": f"http://127.0.0.1:{port}/mcp"}).exchange(
                            self.message()
                        )
                self.assertLess(time.monotonic() - started, 0.8)

    def test_oversize_content_length_fails_before_body(self):
        port, _ = self.start_server("oversize")
        with self.assertRaisesRegex(RpcError, "exceeds 4 MiB"):
            HttpTransport({"url": f"http://127.0.0.1:{port}/mcp"}).exchange(self.message())

    def test_subprocess_that_never_reads_cannot_block_pipe_write_forever(self):
        transport = StdioTransport(
            {"command": sys.executable, "args": ["-c", "import time; time.sleep(30)"]}
        )
        self.addCleanup(transport.close)
        message = self.message()
        message["params"] = {"large": "x" * (1024 * 1024)}
        started = time.monotonic()
        with patch("joongi_hub.upstream.TIMEOUT", 0.15):
            with self.assertRaises(RpcError):
                transport.exchange(message)
        self.assertLess(time.monotonic() - started, 1)
        self.assertIsNotNone(transport.process.poll())
