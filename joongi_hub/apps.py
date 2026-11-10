"""Origin-scoped MCP App resources and restricted view-to-server forwarding."""

import html
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse

from joongi_hub.errors import RpcError
from joongi_hub.resources import unwrap_resource

RELAY_SOURCE = (Path(__file__).parent / "static/app-relay.js").read_text(encoding="utf-8")


def app_resource_uri(tool):
    """Accept both the current nested and legacy MCP Apps metadata formats."""
    meta = tool.get("_meta", {})
    return meta.get("ui", {}).get("resourceUri") or meta.get("ui/resourceUri")


def wrap_app_html(content, server_id):
    """Relay an isolated view through its originating upstream namespace.

    The original document is never rewritten. Source-window checks bind its
    protocol messages to one nested iframe, including in external MCP hosts.
    """
    relay = RELAY_SOURCE.replace("__JOONGI_SOURCE__", json.dumps(server_id), 1)
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        "html,body{margin:0;width:100%;height:100%;}"
        "iframe{display:block;border:0;width:100%;height:100%;min-height:240px;}"
        '</style></head><body><iframe id="mcp-origin-view" title="MCP App view" '
        'sandbox="allow-scripts" '
        'srcdoc="'
        + html.escape(content, quote=True)
        + '"></iframe><script>'
        + relay
        + "</script></body></html>"
    )


def policy_origins(values, allow_about=False):
    if not isinstance(values, list):
        raise RpcError(-32602, "App CSP domains must be arrays")
    result = []
    for value in values:
        if allow_about and value == "about:":
            result.append(value)
            continue
        if not isinstance(value, str):
            raise RpcError(-32602, "Invalid App CSP domain")
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https", "wss"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or any(char in value for char in "\r\n;\"' ")
        ):
            raise RpcError(-32602, "App CSP domains must be explicit HTTP(S)/WSS origins")
        result.append(value.rstrip("/"))
    return result


class AppSessions:
    def __init__(self, hub):
        self.hub = hub
        self.sessions = {}

    def prepare(self, server_id, tool_name):
        client = self.hub.client(server_id)
        client.connect()
        tool = next((tool for tool in client.tools if tool["name"] == tool_name), None)
        if tool is None:
            raise RpcError(-32602, "Unknown App tool")
        uri = app_resource_uri(tool)
        if not uri:
            raise RpcError(-32602, "This tool does not declare an MCP App")
        resource = client.request("resources/read", {"uri": uri})
        contents = resource.get("contents", [])
        content = next(
            (
                item
                for item in contents
                if item.get("uri") == uri and item.get("mimeType", "").startswith("text/html")
            ),
            None,
        )
        if content is None or not isinstance(content.get("text"), str):
            raise RpcError(-32602, "App resource must contain HTML text")
        ui = content.get("_meta", {}).get("ui", {})
        csp = ui.get("csp", {})
        if not isinstance(csp, dict):
            raise RpcError(-32602, "App CSP must be an object")
        resources = " ".join(policy_origins(csp.get("resourceDomains", [])))
        connections = " ".join(policy_origins(csp.get("connectDomains", [])))
        frames = " ".join(policy_origins(csp.get("frameDomains", []), allow_about=True))
        policy = (
            "default-src 'none'; script-src 'unsafe-inline' "
            + resources
            + "; style-src 'unsafe-inline' "
            + resources
            + "; img-src data: blob: "
            + resources
            + "; font-src data: "
            + resources
            + "; connect-src "
            + (connections or "'none'")
            + "; frame-src about: "
            + frames
            + "; object-src 'none'; base-uri 'none'; form-action 'none'; "
            + "frame-ancestors 'self'; sandbox allow-scripts"
        )
        now = time.monotonic()
        self.sessions = {
            key: session for key, session in self.sessions.items() if session["expires"] > now
        }
        if len(self.sessions) >= 64:
            raise RpcError(-32000, "App view limit reached; close views or retry in ten minutes")
        token = secrets.token_urlsafe(24)
        self.sessions[token] = {
            "server": server_id,
            "tool": tool_name,
            "html": wrap_app_html(content["text"], server_id),
            "policy": policy,
            "expires": now + 600,
        }
        return {
            "token": token,
            "url": "/apps/" + token + "?profile=" + self.hub.profile_id,
            "server": server_id,
            "tool": tool_name,
        }

    def get(self, token):
        session = self.sessions.get(token)
        if session is None or session["expires"] < time.monotonic():
            raise RpcError(-32602, "App view expired; open it again")
        return session

    def request(self, token, method, params):
        session = self.get(token)
        if method not in {
            "tools/call",
            "resources/read",
            "resources/list",
            "resources/templates/list",
            "prompts/list",
            "prompts/get",
            "tasks/get",
            "tasks/result",
            "tasks/list",
            "tasks/cancel",
        }:
            raise RpcError(-32601, "This App request is not enabled")
        if not isinstance(params, dict):
            raise RpcError(-32602, "App request params must be an object")
        client = self.hub.client(session["server"])
        if method == "tools/call":
            name = params.get("name")
            if isinstance(name, str) and name.startswith(session["server"] + "__"):
                name = name[len(session["server"]) + 2 :]
            tool = next((tool for tool in client.tools if tool["name"] == name), None)
            if tool is None:
                raise RpcError(-32602, "App tool is outside its originating server")
            visibility = tool.get("_meta", {}).get("ui", {}).get("visibility", ["model", "app"])
            if "app" not in visibility:
                raise RpcError(-32602, "Tool is not visible to Apps")
            params = {**params, "name": session["server"] + "__" + name}
        if method == "tools/call" or method.startswith("tasks/"):
            # Each view is a distinct requester. An App cannot inspect or cancel
            # another view's tasks, even when they share an upstream server.
            response = self.hub.rpc(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                {
                    "version": "2025-11-25",
                    "ready": True,
                    "owner": "app:" + token,
                    "profile": self.hub.profile_id,
                },
            )
            if "error" in response:
                raise RpcError(**response["error"])
            return response["result"]
        if method == "resources/read" and isinstance(params.get("uri"), str):
            uri = params["uri"]
            if uri.startswith(("ui://hub/", "mcp-resource://hub/")):
                source, original = unwrap_resource(uri)
                if source != session["server"]:
                    raise RpcError(-32602, "App resource is outside its originating server")
                params = {**params, "uri": original}
        result = client.request(method, params)
        if method in {
            "resources/read",
            "resources/list",
            "resources/templates/list",
            "prompts/list",
        }:
            result.setdefault("ttlMs", 0)
            result.setdefault("cacheScope", "private")
        return result
