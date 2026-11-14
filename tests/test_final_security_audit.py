"""Local, fake-data reproductions for the final trust-boundary review."""

import socket
import sys
import unittest
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.upstream import HttpTransport, StdioTransport, validate_url


class FinalSecurityAudit(unittest.TestCase):
    def addresses(self, *ips):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80)) for ip in ips]

    def test_plain_http_outside_loopback_is_rejected_before_credentials_are_sent(self):
        with patch(
            "joongi_hub.upstream.socket.getaddrinfo", return_value=self.addresses("203.0.113.10")
        ):
            with (
                patch.dict("os.environ", {"JOONGI_AUDIT_FAKE_TOKEN": "fake-audit-value-not-real"}),
                patch(
                    "joongi_hub.upstream.http.client.HTTPConnection",
                    side_effect=AssertionError("Plain HTTP connection attempted"),
                ) as connection,
            ):
                with self.assertRaises(RpcError):
                    HttpTransport(
                        {
                            "url": "http://audit.example/mcp",
                            "headers": {"Authorization": "JOONGI_AUDIT_FAKE_TOKEN"},
                        }
                    ).exchange({"jsonrpc": "2.0", "id": 1, "method": "ping"})
                connection.assert_not_called()

    def test_https_and_loopback_remain_supported_but_mixed_resolution_is_rejected(self):
        with patch(
            "joongi_hub.upstream.socket.getaddrinfo", return_value=self.addresses("203.0.113.10")
        ):
            self.assertTrue(validate_url("https://audit.example/mcp"))
        with patch(
            "joongi_hub.upstream.socket.getaddrinfo", return_value=self.addresses("127.0.0.1")
        ):
            self.assertTrue(validate_url("http://local.audit.example/mcp"))
        with patch(
            "joongi_hub.upstream.socket.getaddrinfo",
            return_value=self.addresses("127.0.0.1", "203.0.113.10"),
        ):
            with self.assertRaises(RpcError):
                validate_url("http://mixed.audit.example/mcp")

    def test_stdio_does_not_inherit_ambient_secrets_but_explicit_mapping_works(self):
        code = """import json,os,sys
for line in sys.stdin:
 request=json.loads(line)
 print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':{
  'ambient_secret': 'JOONGI_AUDIT_FAKE_TOKEN' in os.environ,
  'mapped_correct':os.environ.get('TOOL_TOKEN')=='fake-audit-value-not-real',
  'path_available':bool(os.environ.get('PATH')),
 }}),flush=True)
"""
        with patch.dict("os.environ", {"JOONGI_AUDIT_FAKE_TOKEN": "fake-audit-value-not-real"}):
            for mapped in (False, True):
                config = {"command": sys.executable, "args": ["-B", "-c", code]}
                if mapped:
                    config["env"] = {"TOOL_TOKEN": "JOONGI_AUDIT_FAKE_TOKEN"}
                transport = StdioTransport(config)
                try:
                    result = transport.exchange({"jsonrpc": "2.0", "id": 1, "method": "inspect"})[
                        "result"
                    ]
                    self.assertFalse(result["ambient_secret"])
                    self.assertEqual(result["mapped_correct"], mapped)
                    self.assertTrue(result["path_available"])
                finally:
                    transport.close()
