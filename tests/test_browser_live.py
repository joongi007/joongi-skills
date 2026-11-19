"""Explicit opt-in public demo test; never uses a user's Hub state or logins."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from joongi_hub.browser_runtime import server_config
from joongi_hub.errors import RpcError
from joongi_hub.service import Hub


@unittest.skipUnless(
    sys.platform == "linux" and os.environ.get("JOONGI_TEST_BROWSER_IMAGE"),
    "Opt-in prepared browser image and public Playwright demo required",
)
class LiveBrowser(unittest.TestCase):
    def test_search_approval_navigation_input_click_screenshot_and_cleanup(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(__file__).resolve().parents[1]
        hub = Hub(root / "skills", Path(directory.name))
        self.addCleanup(hub.close)
        config = server_config(
            os.environ["JOONGI_TEST_BROWSER_IMAGE"],
            ["https://demo.playwright.dev"],
            os.environ.get("JOONGI_TEST_BROWSER_DISPLAY", "headless"),
        )
        hub.register(config)
        self.assertEqual(hub.search("playwright", kind="server")[0]["status"], "disconnected")
        probe = hub.probe("playwright")
        names = {tool["name"] for tool in probe["tools"]}
        self.assertIn("browser_take_screenshot", names)
        self.assertNotIn("browser_evaluate", names)
        self.assertFalse(any(t["name"].startswith("playwright__") for t in hub.tools()))
        execution = hub.clients["playwright"].transport.execution.browser
        container = execution.container
        inspected = subprocess.run(
            [execution.engine, "inspect", container],
            capture_output=True,
            check=True,
            timeout=10,
        )
        state = json.loads(inspected.stdout)[0]
        self.assertEqual(state["HostConfig"]["NetworkMode"], "none")
        self.assertTrue(state["HostConfig"]["ReadonlyRootfs"])
        self.assertEqual(state["HostConfig"]["CapDrop"], ["ALL"])
        self.assertNotEqual(state["Config"]["User"].split(":")[0], "0")

        def approved(name, arguments):
            full = "playwright__" + name
            # Each request is first denied until exact-call consent is given.
            with self.assertRaises(RpcError) as pending:
                hub.invoke(full, arguments)
            self.assertIn("approval_id", pending.exception.data)
            hub.tool_policy.decide(pending.exception.data["approval_id"], True)
            result = hub.invoke(full, arguments)
            self.assertFalse(result.get("isError"), str(result)[:2000])
            return result

        approved("browser_navigate", {"url": "https://demo.playwright.dev/todomvc/"})
        snapshot = approved("browser_snapshot", {})
        self.assertIn("What needs to be done?", json.dumps(snapshot))
        approved(
            "browser_type",
            {"target": "input.new-todo", "text": "Hub browser verification", "submit": True},
        )
        snapshot = approved("browser_snapshot", {})
        self.assertIn("Hub browser verification", json.dumps(snapshot))
        approved("browser_click", {"target": "input.toggle"})
        snapshot = approved("browser_snapshot", {})
        self.assertIn("checked", json.dumps(snapshot))
        screenshot = approved("browser_take_screenshot", {})
        images = [c for c in screenshot["content"] if c["type"] == "image"]
        self.assertEqual(len(images), 1)
        self.assertLess(len(images[0]["data"]), 2 * 1024**2)
        approved("browser_close", {})
        hub.close()
        result = subprocess.run(
            [execution.engine, "inspect", container], capture_output=True, timeout=10
        )
        self.assertNotEqual(result.returncode, 0)
