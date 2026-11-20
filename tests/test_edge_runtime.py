"""Personal Edge contracts using disposable files; never touch real browser tabs/accounts."""

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.edge_companion.worker import (
    CONNECT,
    STATUS,
    Companion,
    allowed_url,
    check,
    tab_urls,
)
from joongi_hub.edge_runtime import command, server_config, unpack_package
from joongi_hub.errors import RpcError
from joongi_hub.sandbox import Execution, validate_sandbox

IDENT = "a" * 32
FINGERPRINT = "b" * 64
ORIGINS = ["https://example.com"]


class EdgeContracts(unittest.TestCase):
    def test_registry_cannot_supply_executable_script_path_or_environment(self):
        config = server_config(IDENT, FINGERPRINT)
        settings = config["sandbox"]
        self.assertEqual(config["policy"]["allowed_tools"], [STATUS])
        for extra in (
            {"read": ["/"]},
            {"write": ["/tmp"]},
            {"image": "anything"},
            {"edge_connection": "../../escape"},
            {"edge_fingerprint": "$command"},
        ):
            with self.subTest(extra=extra), self.assertRaises(RpcError):
                validate_sandbox({**settings, **extra})
        with patch("joongi_hub.edge_runtime.powershell", return_value="/fixed/powershell"):
            config.update(command="untrusted", args=["-c", "malicious"])
            execution = Execution(config, {"API_KEY": "must-not-inherit"})
            try:
                self.assertEqual(execution.command[0], "/fixed/powershell")
                self.assertNotIn("API_KEY", execution.environment)
                script = base64.b64decode(execution.command[-1]).decode("utf-16-le")
                self.assertNotIn("untrusted", script)
                self.assertNotIn("malicious", script)
                self.assertIn("ProtectedData]::Unprotect", script)
                self.assertIn(FINGERPRINT, script)
            finally:
                execution.cleanup()

    def test_navigation_tool_surface_and_output_limits(self):
        self.assertTrue(allowed_url("https://example.com/page", ORIGINS))
        for url in (
            None,
            "http://example.com",
            "file:///secret",
            "https://user@example.com",
            "https://example.com:444",
            "https://other.example",
            "https://[broken",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                check("browser_navigate", {"url": url}, ORIGINS)
        for name, args in (
            ("browser_evaluate", {"function": "code"}),
            ("browser_run_code", {}),
            ("browser_cookie_list", {}),
            ("browser_file_upload", {}),
            ("browser_take_screenshot", {"filename": "secret"}),
            ("browser_take_screenshot", {"fullPage": True}),
            ("browser_wait_for", {"time": 6}),
            ("browser_wait_for", {"time": "forever"}),
            ("browser_tabs", {"action": "unknown"}),
            ("browser_tabs", {"action": "new", "url": "file:///private"}),
            ("browser_tabs", {"action": "new", "isolatedContext": "other"}),
        ):
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                check(name, args, ORIGINS)
        args = {"type": "png", "scale": "device"}
        check("browser_take_screenshot", args, ORIGINS)
        self.assertEqual(args, {"type": "jpeg", "scale": "css"})

    def test_archive_traversal_links_and_duplicate_files_refused(self):
        for name, kind in (
            ("package/../../escape", tarfile.REGTYPE),
            ("package/link", tarfile.SYMTYPE),
            ("package/C:evil", tarfile.REGTYPE),
        ):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "/private"
                archive.addfile(member, io.BytesIO(b""))
            with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
                unpack_package(buffer.getvalue(), Path(directory))

    def companion(self, directory):
        root = Path(directory)
        (root / "settings.json").write_text(json.dumps({"profile": "Default", "origins": ORIGINS}))
        return Companion(root)

    def test_pending_does_not_execute_or_turn_into_timeout_error(self):
        with tempfile.TemporaryDirectory() as directory:
            companion = self.companion(directory)
            with patch.object(companion, "exchange") as upstream:
                result = companion.call("browser_navigate", {"url": "https://example.com"})
                value = json.loads(result["content"][0]["text"])
                self.assertEqual(value["state"], "disconnected")
                self.assertFalse(value["executed"])
                upstream.assert_not_called()
            with patch.object(companion, "pair"):
                start = time.monotonic()
                result = companion.call(CONNECT, {})
                self.assertLess(time.monotonic() - start, 1)
                value = json.loads(result["content"][0]["text"])
                self.assertEqual(value["state"], "awaiting_browser_approval")
                self.assertFalse(value["executed"])

    def test_pairing_accepts_only_one_blank_owned_tab(self):
        for text, expected in (
            ('### Result\n["about:blank"]', "ready"),
            ('### Result\n["https://example.com"]', "connection_failed"),
            ('### Result\n["about:blank", "about:blank"]', "connection_failed"),
            ("Unknown upstream format", "connection_failed"),
        ):
            with tempfile.TemporaryDirectory() as directory:
                companion = self.companion(directory)
                with (
                    patch.object(companion, "start"),
                    patch.object(
                        companion,
                        "exchange",
                        return_value={"content": [{"type": "text", "text": text}]},
                    ),
                ):
                    companion.pair()
                self.assertEqual(companion.state, expected)

    def test_top_level_drift_and_errors_fail_closed_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            companion = self.companion(directory)
            companion.state = "ready"
            with (
                patch.object(
                    companion,
                    "exchange",
                    return_value={
                        "content": [
                            {
                                "type": "text",
                                "text": '### Result\n["https://other.example"]',
                            }
                        ]
                    },
                ) as upstream,
                self.assertRaises(ValueError),
            ):
                companion.call("browser_click", {"ref": "e1", "element": "button"})
            self.assertEqual(upstream.call_count, 1)
            self.assertEqual(companion.state, "connection_failed")

    def test_tabs_parser_rejects_unknown_or_multiline_title(self):
        self.assertEqual(tab_urls({"content": [{"type": "text", "text": "not tabs"}]}), [])
        forged = "- 0: [title](https://evil.example/#](about:blank)"
        self.assertEqual(tab_urls({"content": [{"type": "text", "text": forged}]}), [])
        actual = "https://evil.example/#](about:blank"
        response = {"content": [{"type": "text", "text": "### Result\n" + json.dumps([actual])}]}
        self.assertEqual(tab_urls(response), [actual])
        self.assertFalse(allowed_url(actual, ORIGINS))

    def test_wire_discovery_and_status_do_not_start_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            self.companion(directory)
            Path(directory, "tools.json").write_text("[]")
            requests = [
                {"id": 1, "method": "initialize"},
                {"id": 2, "method": "tools/list"},
                {"id": 3, "method": "tools/call", "params": {"name": STATUS}},
                {"id": 4, "method": "resources/read", "params": {"uri": "file:///private"}},
            ]
            worker = Path(__file__).resolve().parents[1] / "joongi_hub/edge_companion/worker.py"
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-B", str(worker), directory],
                input="".join(json.dumps(r) + "\n" for r in requests),
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            replies = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(replies), 4)
            self.assertIn(CONNECT, [t["name"] for t in replies[1]["result"]["tools"]])
            self.assertEqual(
                json.loads(replies[2]["result"]["content"][0]["text"])["state"], "disconnected"
            )
            self.assertIn("error", replies[3])


@unittest.skipUnless(os.name == "nt", "Windows DPAPI companion gate")
class WindowsEdgeGate(unittest.TestCase):
    def test_live_stdio_reply_does_not_wait_for_stdin_eof(self):
        import queue
        import shutil
        import threading
        import uuid

        from joongi_hub.credential_store import dpapi
        from joongi_hub.edge_runtime import ps_command

        executable = sys.executable.replace("'", "''")
        prerequisite = subprocess.run(
            ps_command(
                "$s=Get-AuthenticodeSignature -LiteralPath '" + executable + "';"
                "if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject "
                "-match 'O=Python Software Foundation(?:,|$)'){exit 0}else{exit 1}"
            ),
            capture_output=True,
            timeout=15,
        )
        if prerequisite.returncode:
            self.skipTest(
                "Functional gate requires a valid PSF-signed Python; untrusted runtimes are refused"
            )

        known = subprocess.check_output(
            ps_command("[Console]::Write([Environment]::GetFolderPath('LocalApplicationData'))"),
            text=True,
        )
        ident = uuid.uuid4().hex
        root = Path(known) / "joongi-hub/edge" / ident
        root.mkdir(parents=True)
        process = None
        try:
            worker = root / "worker.py"
            worker.write_text(
                "import sys\nfor line in sys.stdin:\n print(line.strip(), flush=True)\n"
            )
            descriptor = {
                "python": sys.executable,
                "python_hash": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
                "files": {"worker.py": hashlib.sha256(worker.read_bytes()).hexdigest()},
            }
            plain = json.dumps(descriptor).encode()
            (root / "descriptor.dpapi").write_bytes(dpapi(plain))
            process = subprocess.Popen(
                command(
                    {
                        "backend": "first-party-edge",
                        "edge_connection": ident,
                        "edge_fingerprint": hashlib.sha256(plain).hexdigest(),
                    }
                ),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            output = queue.Queue()
            threading.Thread(
                target=lambda: output.put(process.stdout.readline()), daemon=True
            ).start()
            process.stdin.write(b'{"id":123,"probe":"disposable"}\n')
            process.stdin.flush()
            self.assertEqual(output.get(timeout=15), b'{"id":123,"probe":"disposable"}\r\n')
            self.assertIsNone(process.poll(), "Gate should remain open for the next request")
        finally:
            if process:
                process.stdin.close()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                process.stdout.close()
            shutil.rmtree(root)

    def test_changed_file_is_rejected_before_worker_execution(self):
        import shutil
        import uuid

        from joongi_hub.credential_store import dpapi
        from joongi_hub.edge_runtime import ps_command

        known = subprocess.check_output(
            ps_command("[Console]::Write([Environment]::GetFolderPath('LocalApplicationData'))"),
            text=True,
        )
        ident = uuid.uuid4().hex
        root = Path(known) / "joongi-hub/edge" / ident
        root.mkdir(parents=True)
        try:
            worker = root / "worker.py"
            worker.write_text("raise RuntimeError('must not execute')")
            descriptor = {
                "python": sys.executable,
                "python_hash": "0" * 64,
                "files": {"worker.py": hashlib.sha256(worker.read_bytes()).hexdigest()},
            }
            plain = json.dumps(descriptor).encode()
            (root / "descriptor.dpapi").write_bytes(dpapi(plain))
            worker.write_text("print('UNTRUSTED EXECUTION')")
            result = subprocess.run(
                command(
                    {
                        "backend": "first-party-edge",
                        "edge_connection": ident,
                        "edge_fingerprint": hashlib.sha256(plain).hexdigest(),
                    }
                ),
                input=b"",
                capture_output=True,
                timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"")
        finally:
            shutil.rmtree(root)
