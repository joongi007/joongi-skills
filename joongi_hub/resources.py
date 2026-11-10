"""Reversible upstream namespaces that preserve native skill directory paths."""

import base64
from urllib.parse import quote, unquote, urlparse

from joongi_hub.errors import RpcError


def resource_uri(server_id, original):
    parsed = urlparse(original)
    if parsed.scheme == "skill":
        origin = "skill://"
        suffix = parsed.netloc + parsed.path
    else:
        origin = parsed.scheme + ("://" + parsed.netloc if "://" in original else ":")
        suffix = parsed.path
    if parsed.query:
        suffix += "?" + parsed.query
    if parsed.fragment:
        suffix += "#" + parsed.fragment
    encoded = base64.urlsafe_b64encode(origin.encode()).decode().rstrip("=")
    scheme = "ui" if original.startswith("ui://") else "mcp-resource"
    return f"{scheme}://hub/{server_id}/{encoded}/" + quote(suffix, safe="/")


def unwrap_resource(uri):
    try:
        _, _, host, server_id, tail = uri.split("/", 4)
        if host != "hub":
            raise ValueError
        encoded, separator, suffix = tail.partition("/")
        original = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        if separator:
            original += unquote(suffix)
        return server_id, original
    except (ValueError, UnicodeError) as exc:
        raise RpcError(-32602, "Invalid proxied resource URI") from exc
