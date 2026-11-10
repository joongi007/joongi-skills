"""Separate stdio processes must not race shared credential updates."""

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from joongi_hub.auth import AuthManager

ROOT = Path(__file__).resolve().parents[1]


class CredentialProcesses(unittest.TestCase):
    def test_concurrent_process_updates_preserve_every_server(self):
        with tempfile.TemporaryDirectory() as directory:
            code = """import sys,time
from pathlib import Path
from joongi_hub.auth import AuthManager
manager=AuthManager(Path(sys.argv[1]))
config={'id':'s-'+sys.argv[2],'url':'http://127.0.0.1:1','auth':{'type':'bearer'}}
for index in range(8):
 manager.set_manual(config,{'token':'fake-'+sys.argv[2]})
"""
            children = [
                subprocess.Popen(
                    [sys.executable, "-B", "-c", code, directory, str(i)],
                    cwd=ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for i in range(4)
            ]
            for child in children:
                output, error = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, error)
            manager = AuthManager(Path(directory))
            with manager.lock:
                self.assertEqual(set(manager._read()), {"s-0", "s-1", "s-2", "s-3"})

    def test_process_exit_releases_os_lock_and_nested_calls_are_reentrant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = """import sys,time
from pathlib import Path
from joongi_hub.credential_lock import CredentialLock
root=Path(sys.argv[1])
with CredentialLock(root/'private.lock'):
 (root/'ready').write_text('ready')
 time.sleep(30)
"""
            child = subprocess.Popen([sys.executable, "-B", "-c", code, directory], cwd=ROOT)
            try:
                deadline = time.monotonic() + 10
                while not (root / "ready").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((root / "ready").exists())
            finally:
                child.terminate()
                child.wait(timeout=5)
            from joongi_hub.credential_lock import CredentialLock

            lock = CredentialLock(root / "private.lock")
            with lock, lock:
                (root / "after").write_text(json.dumps({"released": True}))
            self.assertTrue((root / "after").exists())
