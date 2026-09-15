"""Namespace-local registry proxy, with no host network or checkout access.

This stdlib-only source is executed in the acquisition jail. The supervisor
supplies a private connected Unix packet socket as stdin; package-manager
children must have DEVNULL stdin and close_fds=True. Only a newly created local
Unix relay is handed to the parent broker, never a namespace TCP socket or an
upstream host-network socket. The parent independently admits CONNECT hosts,
pins every DNS answer and enforces the shared transfer budget.

This component is not an execution supervisor, consent, or provisioning caller.
The coordinator must impose the outer process deadline, terminate the whole
jail and broker and revoke this channel before offline installation begins.
"""

from __future__ import annotations

import array
import math
import os
import select
import socket
import threading
import time

_RELAY_MESSAGE = b"registry-relay-v1"
_BUFFER_BOUND = 64 * 1024


class NamespaceProxyError(RuntimeError):
    """Fixed local failure classification; no forwarded error text."""


class NamespaceRegistryProxy:
    """Bounded private listener for the fixed acquisition-only proxy URL.

    Takes ownership of control. Call close() even if start() raises. Worker
    threads own their sockets and exit within the bounded select interval;
    the external supervisor remains responsible for verified process exit.
    """

    def __init__(self, control: socket.socket, *, timeout_s: float,
                 max_connections: int = 64, max_active: int = 8):
        if os.name != "posix" or not hasattr(socket, "SCM_RIGHTS"):
            raise NotImplementedError("registry proxy requires POSIX Unix sockets")
        if (control.family != socket.AF_UNIX
                or control.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_SEQPACKET):
            raise ValueError("registry control must be a private Unix packet socket")
        control.getpeername()
        if (isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float))
                or not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ValueError("proxy timeout must be positive and finite")
        if any(type(value) is not int or value <= 0
               for value in (max_connections, max_active)):
            raise ValueError("proxy connection limits must be positive integers")
        self.control = control
        self.control.set_inheritable(False)
        self.control.settimeout(min(0.1, timeout_s))
        self.deadline = time.monotonic() + timeout_s
        self.max_connections = max_connections
        self.max_active = max_active
        self._stop = threading.Event()
        self._state_lock = threading.Lock()
        self._listener: socket.socket | None = None
        self._workers: list[threading.Thread] = []
        self._thread: threading.Thread | None = None
        self.failure: str | None = None

    def start(self) -> None:
        if self._thread is not None or self._stop.is_set():
            raise ValueError("proxy is single-use")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Loopback belongs to the acquisition namespace, not the host.
            listener.bind(("127.0.0.1", 3128))
            listener.listen(self.max_active)
            listener.setblocking(False)
            self._listener = listener
            self._thread = threading.Thread(target=self._serve, daemon=True)
            self._thread.start()
        except BaseException:
            listener.close()
            self._listener = None
            self._thread = None
            self._fail("transport_failed")
            raise

    def _fail(self, reason: str) -> None:
        # Any failure stops the attempt; detailed provider errors stay in the broker.
        with self._state_lock:
            self.failure = self.failure or reason
            self._stop.set()

    def _serve(self) -> None:
        connections = 0
        try:
            while not self._stop.is_set():
                if time.monotonic() >= self.deadline:
                    raise NamespaceProxyError("timeout")
                ready, _, _ = select.select([self._listener, self.control], [], [], 0.1)
                if self.control in ready:
                    # The broker sends no payload/fd back. EOF means revocation;
                    # any reverse payload violates this one-way protocol.
                    self.control.recv(1)
                    raise NamespaceProxyError("broker_closed")
                if self._listener not in ready:
                    continue
                client, _ = self._listener.accept()
                try:
                    self._workers = [worker for worker in self._workers if worker.is_alive()]
                    if connections >= self.max_connections or len(self._workers) >= self.max_active:
                        raise NamespaceProxyError("connection_limit")
                    connections += 1
                    relay, broker_end = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
                    try:
                        handles = array.array("i", [broker_end.fileno()])
                        count = self.control.sendmsg(
                            [_RELAY_MESSAGE], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, handles)])
                        if count != len(_RELAY_MESSAGE):
                            raise NamespaceProxyError("transport_failed")
                        worker = threading.Thread(
                            target=self._pump, args=(client, relay), daemon=True)
                        worker.start()
                        self._workers.append(worker)
                    except BaseException:
                        relay.close()
                        raise
                    finally:
                        broker_end.close()
                except BaseException:
                    client.close()
                    raise
        except NamespaceProxyError as error:
            self._fail(str(error))
        except (OSError, RuntimeError):
            self._fail("transport_failed")
        finally:
            self._stop.set()

    def _pump(self, client: socket.socket, relay: socket.socket) -> None:
        sockets = (client, relay)
        other = {client: relay, relay: client}
        pending = {client: bytearray(), relay: bytearray()}
        readable = set(sockets)
        shut = set()
        try:
            for stream in sockets:
                stream.setblocking(False)
            while not self._stop.is_set() and (readable or any(pending.values())):
                for target in sockets:
                    if other[target] not in readable and not pending[target] and target not in shut:
                        target.shutdown(socket.SHUT_WR)
                        shut.add(target)
                readers = [stream for stream in readable
                           if len(pending[other[stream]]) < _BUFFER_BOUND]
                writers = [stream for stream in sockets if pending[stream]]
                reads, writes, _ = select.select(readers, writers, [], 0.1)
                for stream in reads:
                    try:
                        chunk = stream.recv(_BUFFER_BOUND - len(pending[other[stream]]))
                    except BlockingIOError:
                        continue
                    if chunk:
                        pending[other[stream]].extend(chunk)
                    else:
                        readable.remove(stream)
                for stream in writes:
                    try:
                        count = stream.send(pending[stream])
                    except BlockingIOError:
                        continue
                    if not count:
                        raise NamespaceProxyError("transport_failed")
                    del pending[stream][:count]
        except (OSError, NamespaceProxyError):
            self._fail("transport_failed")
        finally:
            client.close()
            relay.close()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        for worker in self._workers:
            worker.join(timeout=1)
        if self._listener is not None:
            self._listener.close()
        self.control.close()
        if ((self._thread is not None and self._thread.is_alive())
                or any(worker.is_alive() for worker in self._workers)):
            raise NamespaceProxyError("termination_unconfirmed")
