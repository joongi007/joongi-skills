"""Stopping a daemon waits for process cleanup, including separately started daemons."""

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from joongi_hub.lifecycle import stop
from joongi_hub.runtime import process_alive


class LifecycleCleanup(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "regression targets the missing POSIX wait")
    def test_stop_waits_for_a_daemon_started_by_another_process(self):
        record = {"pid": 12345, "instance": "fake-instance", "url": "http://127.0.0.1:12345"}
        with (
            patch("joongi_hub.lifecycle.running", side_effect=[record, None]),
            patch("joongi_hub.lifecycle.local_token", return_value="fake-local-token"),
            patch("joongi_hub.lifecycle.http.client.HTTPConnection") as connection,
            patch("joongi_hub.lifecycle.process_alive", side_effect=[True, False, False]) as alive,
            patch("joongi_hub.lifecycle.time.sleep"),
            patch.dict("joongi_hub.lifecycle._children", {}, clear=True),
        ):
            connection.return_value.getresponse.return_value.status = 200
            self.assertTrue(stop(Path("/unused-fixture-state"))["stopped"])
            self.assertGreaterEqual(alive.call_count, 2)

    @unittest.skipUnless(sys.platform == "linux", "Linux process lifecycle")
    def test_an_exited_unreaped_child_does_not_count_as_running(self):
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        try:
            deadline = time.monotonic() + 5
            path = Path("/proc") / str(child.pid) / "stat"
            while time.monotonic() < deadline:
                if path.exists() and path.read_text().rsplit(")", 1)[1].split()[0] == "Z":
                    break
                time.sleep(0.01)
            else:
                self.fail("Child did not reach the exited state")
            self.assertFalse(process_alive(child.pid))
        finally:
            child.wait(timeout=5)
