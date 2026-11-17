"""Only negotiated owner-host replies can approve explicit one-time snapshots."""

import json
import os
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from joongi_hub.errors import RpcError
from joongi_hub.native_consent import StdioChannel, review, supports_form
from joongi_hub.tool_policy import ToolPolicy


class NativeConsent(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hub = SimpleNamespace(
            tool_policy=ToolPolicy(Path(self.temp.name)), profile_id="global"
        )

    def pending(self, value):
        with self.assertRaises(RpcError) as raised:
            self.hub.tool_policy.authorize(
                {"id": "notion", "policy": {}}, {"name": "read"}, {"value": value}
            )
        return raised.exception.data["approval_id"]

    def test_only_supported_version_and_negotiated_form_uses_native_consent(self):
        for capability in ({}, {"form": {}}, {"url": {}}):
            context = {"version": "2025-11-25", "capabilities": {"elicitation": capability}}
            self.assertEqual(supports_form(context), capability != {"url": {}})
        self.assertFalse(
            supports_form({"version": "2026-07-28", "capabilities": {"elicitation": {}}})
        )
        self.assertFalse(supports_form({"version": "2025-11-25"}))
        self.assertFalse(
            supports_form(
                {"version": "2025-11-25", "capabilities": {"elicitation": {"form": {}}}},
                {"params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}},
            )
        )

    def test_accepted_snapshot_excludes_new_arrivals_and_unselected_calls(self):
        first, second = self.pending(1), self.pending(2)
        later = []

        def ask(params, **kwargs):
            properties = params["requestedSchema"]["properties"]
            self.assertEqual(len(properties), 2)
            self.assertTrue(all(row["default"] is False for row in properties.values()))
            later.append(self.pending(3))
            return {"action": "accept", "content": {"request_0": True, "request_1": False}}

        self.assertEqual(review(self.hub, first, SimpleNamespace(ask=ask)), (True, "approved"))
        self.assertEqual(self.hub.tool_policy.get(second)["status"], "pending")
        self.assertEqual(self.hub.tool_policy.get(later[0])["status"], "pending")
        self.assertEqual(self.hub.tool_policy.grants(), [])

    def test_invalid_timeout_empty_or_stale_replies_never_approve(self):
        first = self.pending(1)
        for answer in (
            None,
            {"action": []},
            {"action": {}},
            {"action": "accept", "content": {"request_0": 1}},
            {"action": "accept", "content": {"request_8": True}},
            {"action": "accept", "content": {}},
        ):
            channel = SimpleNamespace(ask=lambda *a, answer=answer, **kw: answer)
            self.assertFalse(review(self.hub, first, channel)[0])
            self.assertEqual(self.hub.tool_policy.get(first)["status"], "pending")

        def changed(*args, **kwargs):
            self.hub.tool_policy.decide(first, False)
            return {"action": "accept", "content": {"request_0": True}}

        self.assertEqual(review(self.hub, first, SimpleNamespace(ask=changed)), (False, "changed"))

    def test_decline_denies_only_triggering_call(self):
        first, second = self.pending(1), self.pending(2)
        channel = SimpleNamespace(ask=lambda *a, **kw: {"action": "decline"})
        self.assertEqual(review(self.hub, first, channel), (False, "decline"))
        self.assertEqual(self.hub.tool_policy.get(first)["status"], "denied")
        self.assertEqual(self.hub.tool_policy.get(second)["status"], "pending")

    def test_transport_matches_private_request_id_and_preserves_other_messages(self):
        incoming = queue.Queue()
        source = SimpleNamespace(readline=lambda size: incoming.get())

        def send(request):
            incoming.put(b'{"jsonrpc":"2.0","id":"wrong","result":{"action":"accept"}}\n')
            incoming.put(b'{"jsonrpc":"2.0","id":11,"method":"ping"}\n')
            incoming.put(
                json.dumps(
                    {"jsonrpc": "2.0", "id": request["id"], "result": {"action": "cancel"}}
                ).encode()
            )

        channel = StdioChannel(source, send, 4096)
        self.addCleanup(incoming.put, b"")
        self.assertEqual(channel.ask({}, timeout=1), {"action": "cancel"})
        self.assertEqual(json.loads(channel.next())["id"], "wrong")
        self.assertEqual(json.loads(channel.next())["method"], "ping")

    def test_parent_cancellation_abandons_form_without_a_decision(self):
        incoming = queue.Queue()
        source = SimpleNamespace(readline=lambda size: incoming.get())

        def send(request):
            incoming.put(
                b'{"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":7}}\n'
            )

        channel = StdioChannel(source, send, 4096)
        self.addCleanup(incoming.put, b"")
        self.assertIsNone(channel.ask({}, timeout=1, parent_id=7))

    def test_raw_pipe_preserves_lines_and_eof_and_enforces_size_limit(self):
        for payload, limit, expected in (
            (b"one\ntwo", 16, [b"one\n", b"two", b""]),
            (b"123456\n", 4, [b"12345"]),
        ):
            with self.subTest(payload=payload):
                reader, writer = os.pipe()
                source = os.fdopen(reader, "rb", buffering=0)
                self.addCleanup(source.close)
                os.write(writer, payload)
                os.close(writer)
                channel = StdioChannel(source, lambda value: None, limit)
                self.assertEqual([channel.next() for _ in expected], expected)

    def test_timeout_cancels_the_outstanding_host_form(self):
        incoming = queue.Queue()
        sent = []
        channel = StdioChannel(
            SimpleNamespace(readline=lambda size: incoming.get()), sent.append, 4096
        )
        self.addCleanup(incoming.put, b"")
        self.assertIsNone(channel.ask({}, timeout=0.01))
        self.assertEqual(sent[-1]["method"], "notifications/cancelled")
        self.assertEqual(sent[-1]["params"]["requestId"], sent[0]["id"])


if __name__ == "__main__":
    unittest.main()
