"""Private Unix-socket HTTPS egress for a network-less browser container."""

import ipaddress
import re
import select
import socket
import socketserver
import threading
import time
from urllib.parse import urlsplit

from joongi_hub.errors import RpcError


def origins(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise RpcError(-32602, "브라우저가 방문할 HTTPS origin을 1–32개 지정하세요.")
    result = []
    for entry in value:
        try:
            parsed = urlsplit(entry)
            host = parsed.hostname or ""
            if (
                parsed.scheme != "https"
                or parsed.port not in (None, 443)
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", host)
                or "." not in host
                or any(not part or len(part) > 63 for part in host.split("."))
            ):
                raise ValueError
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError
        except (ValueError, TypeError, AttributeError) as exc:
            raise RpcError(-32602, "와일드카드·IP·경로 없는 HTTPS origin을 지정하세요.") from exc
        canonical = "https://" + host
        if canonical not in result:
            result.append(canonical)
    return result


def public_addresses(host):
    # IPv4 only: no IPv4-mapped/NAT64/6to4 route to private destinations.
    addresses = {
        row[4][0] for row in socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
    }
    if not addresses or any(
        not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast
        for address in addresses
    ):
        raise ValueError("Public IPv4 DNS answers required")
    return sorted(addresses)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.request.settimeout(5)
            header = bytearray()
            while not header.endswith(b"\r\n\r\n"):
                byte = self.request.recv(1)
                if not byte or len(header) >= 16384:
                    raise ValueError("Invalid proxy header")
                header.extend(byte)
            first = header.split(b"\r\n", 1)[0].decode("ascii").split(" ")
            if len(first) != 3 or first[0] != "CONNECT" or first[2] != "HTTP/1.1":
                raise ValueError("HTTPS CONNECT only")
            authority = first[1]
            if authority not in self.server.authorities:
                raise ValueError("Origin not enabled")
            host = authority[:-4]
            addresses = public_addresses(host)
            # Connect to a validated numeric address, never resolve the host a second time.
            with socket.create_connection((addresses[0], 443), timeout=8) as upstream:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                deadline, transferred = time.monotonic() + 120, 0
                sockets = [self.request, upstream]
                while (
                    not self.server.stopped.is_set()
                    and time.monotonic() < deadline
                    and transferred < 32 * 1024**2
                ):
                    readable, _, _ = select.select(sockets, [], [], 1)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        transferred += len(data)
                        (upstream if source is self.request else self.request).sendall(data)
        except (OSError, ValueError, UnicodeError):
            try:
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
        finally:
            self.server.slots.release()


class EgressProxy(
    socketserver.ThreadingMixIn, getattr(socketserver, "UnixStreamServer", socketserver.TCPServer)
):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16

    def __init__(self, path, allowed):
        self.authorities = {urlsplit(origin).hostname + ":443" for origin in origins(allowed)}
        self.slots = threading.BoundedSemaphore(16)
        self.stopped = threading.Event()
        super().__init__(str(path), Handler)
        path.chmod(0o600)
        self.thread = threading.Thread(target=self.serve_forever, daemon=True)
        self.thread.start()

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def close(self):
        self.stopped.set()
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=2)
