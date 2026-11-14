"""Execute hostile fake programs and observe the actual OS boundary."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.sandbox import Execution
from joongi_hub.upstream import stdio_environment


class SandboxBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.cache = self.root / "cache"
        self.project.mkdir()
        self.cache.mkdir()
        (self.project / "source.txt").write_text("project-data")
        self.secret = self.root / "unshared-private-secret"
        self.secret.write_text("fake-private-value-never-real")
        try:
            (self.project / "escape").symlink_to(self.secret)
        except OSError:
            pass

    def run_program(self, backend):
        code = """import json,os,socket,sys
from pathlib import Path
project,cache,secret=map(Path,sys.argv[1:])
def denied(action):
 try: action();return False
 except OSError:return True
result={'read':(project/'source.txt').read_text(),
 'private_read_denied':denied(lambda:secret.read_text()),
 'private_write_denied':denied(lambda:secret.write_text('changed')),
 'project_write_denied':denied(lambda:(project/'source.txt').write_text('changed')),
 'symlink_escape_denied':denied(lambda:(project/'escape').read_text()),
 'network_denied':denied(lambda:socket.create_connection(('127.0.0.1',9),timeout=.2)),
 'unix_socket_denied':denied(lambda:socket.socket(socket.AF_UNIX,socket.SOCK_STREAM).connect(str(project/'private.sock'))),
 'metadata_change_denied':denied(lambda:os.chmod(secret,0o777))}
(cache/'allowed-write').write_text('cache-data')
print(json.dumps(result))
"""
        config = {
            "command": sys.executable,
            "args": ["-B", "-c", code, str(self.project), str(self.cache), str(self.secret)],
            "sandbox": {
                "backend": backend,
                "read": [str(self.project)],
                "write": [str(self.cache)],
            },
        }
        service = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        service.bind(str(self.project / "private.sock"))
        service.listen(1)
        self.addCleanup(service.close)
        execution = Execution(config, stdio_environment())
        try:
            result = subprocess.run(
                execution.command,
                capture_output=True,
                env=execution.environment,
                timeout=15,
                start_new_session=os.name != "nt",
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
            values = json.loads(result.stdout)
            self.assertEqual(values.pop("read"), "project-data")
            self.assertTrue(all(values.values()), values)
            self.assertEqual((self.cache / "allowed-write").read_text(), "cache-data")
            self.assertEqual(self.secret.read_text(), "fake-private-value-never-real")
        finally:
            execution.cleanup()

    @unittest.skipUnless(sys.platform == "linux", "Linux native sandbox profile")
    def test_landlock_denies_ungranted_io_symlink_network_and_metadata_changes(self):
        self.run_program("landlock")

    @unittest.skipUnless(sys.platform == "linux", "Linux host runtime in Docker")
    def test_docker_native_denies_unmounted_io_symlink_network_and_readonly_writes(self):
        self.run_program("docker-native")

    def test_missing_backend_fails_before_running_the_program(self):
        with patch("joongi_hub.sandbox.sys.platform", "unsupported"):
            with self.assertRaises(RpcError):
                Execution(
                    {"command": sys.executable, "args": ["-c", 'print("must not run")']},
                    stdio_environment(),
                )
        self.assertEqual(self.secret.read_text(), "fake-private-value-never-real")

    def test_docker_without_resource_limits_or_seccomp_is_rejected(self):
        for info in (
            {"SecurityOptions": ["name=seccomp,profile=builtin"]},
            {"MemoryLimit": True, "PidsLimit": True, "CpuCfsQuota": True, "SecurityOptions": []},
        ):
            with (
                self.subTest(info=info),
                patch("joongi_hub.sandbox.shutil.which", return_value="/trusted/docker"),
                patch(
                    "joongi_hub.sandbox.subprocess.run",
                    return_value=subprocess.CompletedProcess([], 0, json.dumps(info).encode(), b""),
                ),
            ):
                with self.assertRaises(RpcError):
                    Execution(
                        {
                            "command": "python",
                            "sandbox": {"backend": "docker", "image": "example@sha256:" + "a" * 64},
                        },
                        stdio_environment(),
                    )

    def test_unsafe_grants_and_unverified_images_are_rejected(self):
        for policy in [
            {"write": [str(Path(__file__).resolve().parents[1])]},
            {"read": [str(Path.home())]},
            {"read": ["/run"]},
            {"backend": "docker", "image": "python:latest"},
        ]:
            with self.subTest(policy=policy), self.assertRaises(RpcError):
                Execution({"command": sys.executable, "sandbox": policy}, stdio_environment())

    @unittest.skipUnless(sys.platform == "linux", "Linux helper environment")
    def test_loader_injection_environment_is_not_applied_before_enforcement(self):
        config = {
            "command": sys.executable,
            "args": ["-c", "pass"],
            "sandbox": {"backend": "landlock"},
        }
        execution = Execution(
            config,
            {
                **stdio_environment(),
                "LD_PRELOAD": "/untrusted/library.so",
                "PYTHONPATH": "/untrusted/modules",
            },
        )
        try:
            self.assertNotIn("LD_PRELOAD", execution.environment)
            self.assertNotIn("PYTHONPATH", execution.environment)
        finally:
            execution.cleanup()
