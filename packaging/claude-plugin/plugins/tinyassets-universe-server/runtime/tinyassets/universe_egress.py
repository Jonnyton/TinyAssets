"""Public network for the universe tool jail, through a checking proxy.

Change ``universe-agent-harness``, slice S3. The universe agent's ``bash`` had no
network at all, and that was the first thing tiny listed as blocking it ("Local
FastMCP/pytest/Ruff/browser capabilities remain absent"): no ``pip install``, no
``git clone``, no ``curl`` of a page.

The jail still has NO network interface of its own: it keeps its empty network
namespace. What it gets is one unix socket, bound in at :data:`JAIL_SOCKET`,
served by this module in the daemon. Inside the jail a tiny forwarder
(:data:`FORWARDER`) listens on ``127.0.0.1:3128`` and passes each connection to
that socket, and ``HTTP(S)_PROXY`` point standard clients at it. So the jail can
reach exactly what this proxy agrees to connect, and nothing else -- there is
no route around it, whatever the address family or protocol.

What it agrees to is the floor, which is cross-user only (founder, 2026-08-31):
the destination is resolved HERE, every resolved address must be globally
routable (``outbound_connections._classify_global_address``: no loopback,
private, link-local/metadata, CGNAT, ULA, NAT64-wrapped private and so on), and
the connection is made to the address that was checked, so DNS rebinding and
translated destinations cannot reach the host, the container network or another
universe's engine port. Outbound mail ports are refused because spam from the
shared address burns every user's reputation. Per-universe concurrency is
bounded because the box is shared. Nothing else is restricted: what a universe
fetches is its owner's business.
"""

from __future__ import annotations

import contextlib
import logging
import os
import select
import socket
import stat
import threading
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

#: Where the proxy socket appears inside the tool jail (on its private /tmp).
JAIL_SOCKET = "/tmp/.ta-egress.sock"
#: Where the in-jail forwarder listens.
JAIL_PROXY_URL = "http://127.0.0.1:3128"

#: SMTP submission and relay: mail from the shared address is cross-user harm.
REFUSED_PORTS = frozenset({25, 465, 587})
#: Concurrent connections one universe may hold through this process.
MAX_CONNECTIONS = 32
_HEAD_LIMIT = 16 * 1024
_HEAD_TIMEOUT_S = 30.0
_CONNECT_TIMEOUT_S = 15.0
_RESOLVE_TIMEOUT_S = 10.0
_IDLE_TIMEOUT_S = 300.0

#: The environment that points standard clients at the forwarder.
PROXY_ENV: tuple[tuple[str, str], ...] = tuple(
    (name, JAIL_PROXY_URL)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                 "ALL_PROXY", "all_proxy")
) + (("NO_PROXY", "localhost,127.0.0.1"), ("no_proxy", "localhost,127.0.0.1"))

#: Runs inside the jail as ``python3 -c FORWARDER <command...>``: binds the
#: forwarder port, forks a quiet child that relays each connection to the
#: proxy socket, then execs the command. The child dies with the jail.
FORWARDER = r'''
import os, socket, sys, threading
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 3128))
srv.listen(64)
if os.fork():
    srv.close()
    os.execvp(sys.argv[1], sys.argv[1:])
null = os.open(os.devnull, os.O_RDWR)
for fd in (0, 1, 2):
    os.dup2(null, fd)
threading.stack_size(256 * 1024)
slots = threading.BoundedSemaphore(16)
def pump(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    for s in (a, b):
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
def serve(c):
    u = socket.socket(socket.AF_UNIX)
    try:
        u.connect("/tmp/.ta-egress.sock")
    except OSError:
        c.close(); u.close(); slots.release(); return
    t = threading.Thread(target=pump, args=(u, c), daemon=True)
    t.start()
    pump(c, u)
    t.join()
    c.close(); u.close(); slots.release()
while True:
    c, _ = srv.accept()
    if not slots.acquire(blocking=False):
        c.close(); continue
    threading.Thread(target=serve, args=(c,), daemon=True).start()
'''


class EgressRefused(Exception):
    """The proxy will not make this connection; the message says why."""


def _destination(head: bytes) -> tuple[str, int, bytes | None]:
    """(host, port, bytes to send first) from a proxy request head.

    ``CONNECT host:port`` opens a tunnel (nothing to forward). An absolute-form
    ``http://`` request is forwarded with its request line rewritten to origin
    form. Anything else is refused.
    """
    try:
        line, _, rest = head.partition(b"\r\n")
        method, target, version = line.decode("ascii").split(" ")
    except (UnicodeDecodeError, ValueError):
        raise EgressRefused("not an HTTP proxy request") from None
    if method.upper() == "CONNECT":
        host, sep, port = target.rpartition(":")
        if not sep or not port.isdigit():
            raise EgressRefused("CONNECT needs host:port")
        return host.strip("[]"), int(port), None
    parts = urlsplit(target)
    if parts.scheme != "http" or not parts.hostname:
        raise EgressRefused("only http:// requests or CONNECT tunnels are proxied")
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    first = f"{method} {path} {version}\r\n".encode("ascii")
    return parts.hostname, parts.port or 80, first + rest


def _checked_addresses(host: str, port: int) -> list[str]:
    """Every address ``host`` resolves to, each proven globally routable."""
    from tinyassets.storage.outbound_connections import (
        SsrfValidationError,
        _classify_global_address,
        _make_default_resolver,
        _resolve_pinned_addresses,
    )

    if port in REFUSED_PORTS:
        raise EgressRefused(f"port {port} (outbound mail) is not reachable from a universe")
    if not 0 < port < 65536:
        raise EgressRefused(f"port {port} is not a valid port")
    try:
        return _resolve_pinned_addresses(
            host, port, resolver=_make_default_resolver(_RESOLVE_TIMEOUT_S),
            validator=_classify_global_address,
        )
    except SsrfValidationError as exc:
        raise EgressRefused(f"{host}: {exc}") from None


def _open(addresses: list[str], port: int) -> socket.socket:
    last: OSError | None = None
    for address in addresses:
        try:
            return socket.create_connection((address, port), timeout=_CONNECT_TIMEOUT_S)
        except OSError as exc:
            last = exc
    raise EgressRefused(f"could not connect: {last}")


def _read_head(conn: socket.socket) -> bytes:
    conn.settimeout(_HEAD_TIMEOUT_S)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            raise EgressRefused("the request ended before its head")
        data += chunk
        if len(data) > _HEAD_LIMIT:
            raise EgressRefused("request head too large")
    return data


def _relay(a: socket.socket, b: socket.socket) -> None:
    """Copy both ways until both sides finish, or nothing moves for the idle bound."""
    a.settimeout(None)
    b.settimeout(None)
    reading = {a: b, b: a}
    while reading:
        readable, _, _ = select.select(list(reading), [], [], _IDLE_TIMEOUT_S)
        if not readable:
            return
        for sock in readable:
            target = reading[sock]
            try:
                data = sock.recv(65536)
            except OSError:
                return
            if not data:
                del reading[sock]
                with contextlib.suppress(OSError):
                    target.shutdown(socket.SHUT_WR)
                continue
            try:
                target.sendall(data)
            except OSError:
                return


def _refuse(conn: socket.socket, status: str, reason: str) -> None:
    body = f"egress refused: {reason}\n".encode("utf-8", "replace")
    with contextlib.suppress(OSError):
        conn.sendall(
            f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii")
            + body
        )


class EgressProxy:
    """One universe's proxy in this process, listening on a unix socket."""

    def __init__(self, socket_path: Path, universe: str, dir_fd: int) -> None:
        self.socket_path = socket_path
        self.universe = universe
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        name = socket_path.name
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name, dir_fd=dir_fd)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        # Bound through the directory descriptor, never the path: the folder is
        # writable by the universe's own workflow processes, so a component
        # swapped for a link after the descriptor was opened changes nothing.
        server.bind(f"/proc/self/fd/{dir_fd}/{name}")
        os.chmod(name, 0o600, dir_fd=dir_fd, follow_symlinks=False)
        server.listen(64)
        self._server = server
        self._inode = os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_ino
        thread = threading.Thread(target=self._accept, name=f"egress-{universe}", daemon=True)
        thread.start()

    def alive(self) -> bool:
        """Whether the socket file this proxy listens on is still the one in place."""
        try:
            on_disk = os.lstat(self.socket_path)
        except OSError:
            return False
        return stat.S_ISSOCK(on_disk.st_mode) and on_disk.st_ino == self._inode

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._server.close()

    def _accept(self) -> None:
        while True:
            try:
                conn, _ = self._server.accept()
            except OSError:
                return
            if not self._slots.acquire(blocking=False):
                _refuse(conn, "503 Service Unavailable",
                        f"this universe already has {MAX_CONNECTIONS} open connections")
                conn.close()
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        upstream = None
        try:
            head = _read_head(conn)
            host, port, first = _destination(head)
            upstream = _open(_checked_addresses(host, port), port)
            if first is None:
                conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            else:
                upstream.sendall(first)
            _relay(conn, upstream)
        except EgressRefused as exc:
            logger.info("egress refused for %s: %s", self.universe, exc)
            _refuse(conn, "403 Forbidden", str(exc))
        except OSError:
            pass
        finally:
            for sock in (conn, upstream):
                if sock is not None:
                    with contextlib.suppress(OSError):
                        sock.close()
            self._slots.release()


_PROXIES: dict[str, EgressProxy] = {}
_LOCK = threading.Lock()


def ensure_proxy(universe_dir: Path) -> Path | None:
    """The proxy socket for ``universe_dir`` in this process, started on first use.

    Returns ``None`` where unix sockets or no-follow directory creation are
    unavailable (a Windows tray): the jail then has no network, as before.
    """
    if not hasattr(socket, "AF_UNIX") or not hasattr(os, "O_NOFOLLOW"):
        return None
    from tinyassets.universe_files import open_runtime_dir

    root = Path(universe_dir).resolve()
    key = str(root)
    with _LOCK:
        proxy = _PROXIES.get(key)
        if proxy is not None and proxy.alive():
            return proxy.socket_path
        if proxy is not None:
            proxy.close()
        dir_fd = open_runtime_dir(root, "egress")
        try:
            path = root / ".runtime" / "egress" / f"{os.getpid()}.sock"
            proxy = EgressProxy(path, root.name, dir_fd)
        finally:
            os.close(dir_fd)
        _PROXIES[key] = proxy
        return path
