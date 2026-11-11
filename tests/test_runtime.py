"""Windows process completion is the process handle signal, not an early exit code."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from joongi_hub.runtime import process_alive


class ProcessLivenessTests(unittest.TestCase):
    def test_windows_waits_for_process_signal_before_reporting_exit(self):
        kernel = Mock()
        kernel.OpenProcess.return_value = 123
        kernel.GetExitCodeProcess.return_value = True
        kernel.WaitForSingleObject.return_value = 258
        with (
            patch("joongi_hub.runtime.os", SimpleNamespace(name="nt")),
            patch(
                "joongi_hub.runtime.ctypes.windll", SimpleNamespace(kernel32=kernel), create=True
            ),
        ):
            self.assertTrue(process_alive(12345))
            kernel.WaitForSingleObject.return_value = 0
            self.assertFalse(process_alive(12345))
        self.assertEqual(kernel.CloseHandle.call_count, 2)

    def test_invalid_process_ids_are_not_alive(self):
        for pid in (None, 0, -1, "123"):
            with self.subTest(pid=pid):
                self.assertFalse(process_alive(pid))
