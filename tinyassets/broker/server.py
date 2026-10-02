"""The broker process's server: many streams per connection (I14 decisions 1-4, 6, 7).

One asyncio server on a Unix socket. Each connection is classified by the
connecting process's uid (``SO_PEERCRED``) against the broker's own role map;
an unmapped uid is refused before a frame is read. Frames are
:mod:`tinyassets.rpc_frames`.

A stream's life, for an ``OPEN`` on an owner channel:

1. the frame is checked for the role (an owner names principal and command
   center; a box channel is not served yet and is refused);
2. the grant is authorized with ``ConnectionLedger.authorize_exact``, the same
   checks ``resolve_exact_scoped_proxy`` runs, as that principal;
3. the stream's ``(generation, token)`` must equal the persisted fence;
4. the operation is admitted in the op store (namespace = principal and
   command center, bound to a digest of the request). A known operation is
   never sent again: the stream ends ``refused``/``duplicate`` carrying the
   operation's recorded state;
5. on the stream's thread: ``may_have_sent`` is written durably and
   ``ADMITTED`` sent, then the request leaves -- every network send (the
   first, an OAuth resend) under the fence's send lock with the stream's
   cancellation re-checked immediately before it;
6. ``HEAD``, then ``DATA`` within the caller's credit, then ``END``.

``side_effect_state`` is the OPERATION's: ``none`` only when the broker can
show no byte of it was ever sent (no record, or a record that never reached
``may_have_sent``), ``unknown`` otherwise. ``stream_sent`` says whether THIS
stream wrote.

Bounds: credit at most ``MAX_WINDOW`` per stream, at most ``LOOKAHEAD`` read
past it, an absolute deadline over the whole stream (admission to ``END``,
credit waits included), and a per-connection output queue of at most
``MAX_QUEUED_FRAMES`` frames whose producers block when it is full.

The upstream exchange is the hardened synchronous driver, so each live stream
runs it on a thread of its own: a waiting stream costs that thread and its
window in the broker (an async upstream is a later step, measured first).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import socket
import struct
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tinyassets import rpc_frames as rf
from tinyassets.broker.fence import Fence, Fenced
from tinyassets.broker.ops import OpIdInvalid, OpStore

_LOG = logging.getLogger(__name__)

OWNER = "owner"
BOX = "box"
MAX_WINDOW = 256 * 1024
LOOKAHEAD = 16 * 1024
MAX_STREAMS = 4096
MAX_QUEUED_FRAMES = 64
#: Ordinary and longest per-request budgets (the driver's own) plus room for
#: the one OAuth resend; the stream's absolute deadline is drawn from these.
ORDINARY_BUDGET_S = 30.0
MAX_BUDGET_S = 600.0
RESEND_GRACE_S = 30.0
#: The fixed, secret-free error classes an END may carry.
ERROR_CLASSES = frozenset({
    "PermissionError", "GrantResolutionError", "AmbiguousProxyOutcome",
    "OutboundDeadlineExceeded", "ConnectionAuthorizationError", "ProxyRequestError",
    "SsrfValidationError", "fenced", "duplicate", "expired", "refused",
})


def peer_uid(sock: socket.socket) -> int:
    """The connecting process's uid, from the kernel. Linux only; fails closed elsewhere."""
    option = getattr(socket, "SO_PEERCRED", None)
    if option is None:
        raise PermissionError("peer credentials are unavailable on this host")
    _pid, uid, _gid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, option,
                                                         struct.calcsize("3i")))
    return uid


def request_digest(*, grant_id: str, connection_id: str, verb: str, request: Any) -> str:
    """The request's identity for the op record: everything that shapes the effect.

    Transport options (``reply_budget_s``) are excluded; the rest of the request
    document (url, headers, ``header_name``, body) is canonical JSON.
    """
    document = dict(request) if isinstance(request, dict) else {"request": request}
    document.pop("reply_budget_s", None)
    canonical = json.dumps(
        {"grant": grant_id, "connection": connection_id, "verb": str(verb).upper(),
         "request": document},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stream_budget(request: dict[str, Any]) -> float:
    asked = request.get("reply_budget_s")
    if type(asked) in (int, float) and asked == asked and asked > ORDINARY_BUDGET_S:
        return min(float(asked), MAX_BUDGET_S) + RESEND_GRACE_S
    return ORDINARY_BUDGET_S + RESEND_GRACE_S


@dataclass
class _Stream:
    id: int
    generation: int
    token: str
    namespace: str
    op_id: str
    deadline: float
    credit: int = 0
    cancelled: bool = False
    sent: bool = False
    upstream: Any = None
    sockets: list[Any] = field(default_factory=list)
    wake: threading.Condition = field(default_factory=threading.Condition)


class BrokerServer:
    def __init__(self, *, ledger_for: Callable[[str], Any],
                 dispatch_for: Callable[..., Callable[..., Any]],
                 ops: OpStore, fence: Fence, roles: Mapping[int, str],
                 uid_of: Callable[[socket.socket], int] = peer_uid) -> None:
        self._ledger_for = ledger_for
        self._dispatch_for = dispatch_for
        self._ops = ops
        self._fence = fence
        self._roles = dict(roles)
        self._uid_of = uid_of
        self._streams: dict[tuple[int, int], _Stream] = {}
        self._streams_lock = threading.Lock()
        self._ops.recover()

    async def serve(self, path: Path) -> asyncio.AbstractServer:
        return await asyncio.start_unix_server(self._connection, path=str(path))

    async def _connection(self, reader: asyncio.StreamReader,
                          writer: asyncio.StreamWriter) -> None:
        sock = writer.get_extra_info("socket")
        try:
            role = self._roles.get(self._uid_of(sock))
        except Exception:  # noqa: BLE001 - no identity, no service
            role = None
        if role is None:
            writer.close()
            return
        connection = _Connection(self, writer, role)
        pump = asyncio.ensure_future(connection.pump())
        try:
            while (frame := await rf.read_frame(reader)) is not None:
                await connection.handle(frame)
        except rf.FrameError:
            _LOG.warning("broker peer broke the framing; dropping it")
        except (ConnectionError, OSError):
            pass
        finally:
            connection.abandon()
            pump.cancel()
            writer.close()

    def _cancel_older(self, generation: int) -> None:
        with self._streams_lock:
            older = [s for s in self._streams.values() if s.generation < generation]
        for stream in older:
            self.cancel(stream)

    def _close_older(self, generation: int) -> None:
        self._cancel_older(generation)

    @staticmethod
    def cancel(stream: _Stream) -> None:
        """Never blocks: marks the stream cancelled and shuts its sockets down."""
        from tinyassets.storage.outbound_connections import abort_socket

        with stream.wake:
            stream.cancelled = True
            stream.wake.notify_all()
        for sock in list(stream.sockets):
            abort_socket(sock)
        upstream = stream.upstream
        if upstream is not None:
            upstream.close()


class _Connection:
    """One peer: its streams, and one bounded output queue drained by a pump."""

    def __init__(self, server: BrokerServer, writer: asyncio.StreamWriter, role: str) -> None:
        self._server = server
        self._writer = writer
        self._role = role
        self._loop = asyncio.get_running_loop()
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(MAX_QUEUED_FRAMES)
        self._closed = threading.Event()
        self._key = id(self)

    async def pump(self) -> None:
        while True:
            frame = await self._queue.get()
            self._writer.write(frame)
            await self._writer.drain()

    def send(self, frame: bytes | list[bytes]) -> None:
        """From a stream thread: queue frames, blocking while the queue is full."""
        for item in frame if isinstance(frame, list) else [frame]:
            if self._closed.is_set():
                return
            future = asyncio.run_coroutine_threadsafe(self._queue.put(item), self._loop)
            while True:
                try:
                    future.result(timeout=1.0)
                    break
                except TimeoutError:
                    if self._closed.is_set():
                        future.cancel()
                        return

    async def send_async(self, frame: bytes) -> None:
        await self._queue.put(frame)

    async def handle(self, frame: rf.Frame) -> None:
        if frame.kind == rf.DATA:
            return  # request bodies are inline in v1; stray data is ignored
        doc = frame.control()
        op = doc["op"]
        if frame.stream == rf.CONNECTION:
            await self._connection_op(op, doc)
            return
        with self._server._streams_lock:
            stream = self._server._streams.get((self._key, frame.stream))
        if op == "OPEN":
            if stream is not None:
                raise rf.FrameError("stream id reused while open")
            await self._open(frame.stream, doc)
        elif op == "CREDIT" and stream is not None:
            amount = doc.get("n")
            if type(amount) is int and amount > 0:
                with stream.wake:
                    stream.credit = min(stream.credit + amount, MAX_WINDOW)
                    stream.wake.notify_all()
        elif op == "CANCEL" and stream is not None:
            await asyncio.to_thread(self._server.cancel, stream)

    async def _connection_op(self, op: str, doc: dict[str, Any]) -> None:
        if self._role != OWNER:
            raise rf.FrameError("only the owner channel may send connection operations")
        if op == "FENCE":
            try:
                generation, token = await asyncio.to_thread(
                    self._server._fence.barrier, doc.get("generation"), doc.get("proof"),
                    cancel_older=self._server._cancel_older,
                    close_older=self._server._close_older,
                )
            except Fenced:
                await self.send_async(rf.control(rf.CONNECTION, {"op": "FENCE_REFUSED"}))
                return
            await self.send_async(rf.control(rf.CONNECTION, {
                "op": "FENCE_ACK", "generation": generation, "token": token}))
        elif op == "STATUS":
            namespace = _namespace(doc.get("principal"), doc.get("command_center"))
            state, effect = await asyncio.to_thread(
                self._operation_state, namespace, str(doc.get("op_id", "")))
            await self.send_async(rf.control(rf.CONNECTION, {
                "op": "STATUS_IS", "op_id": doc.get("op_id"), "state": state,
                "side_effect_state": effect}))

    def _operation_state(self, namespace: str, op_id: str) -> tuple[str, str]:
        """``(state, side_effect_state)`` of an operation, never ``none`` on a guess."""
        try:
            record = self._server._ops.status(namespace, op_id)
        except OpIdInvalid:
            return "invalid", "none"  # never admissible, so never sent
        if record == "not_found":
            return "not_found", "none"
        if record == "expired":
            return "expired", "unknown"
        return record.state, "unknown" if record.sent else "none"

    async def _open(self, stream_id: int, doc: dict[str, Any]) -> None:
        principal, command_center = doc.get("principal"), doc.get("command_center")
        op_id = doc.get("op_id")

        async def refuse(error_class: str) -> None:
            effect = "unknown"
            if self._role == OWNER and isinstance(op_id, str):
                try:
                    namespace = _namespace(principal, command_center)
                    _, effect = await asyncio.to_thread(self._operation_state, namespace, op_id)
                except rf.FrameError:
                    effect = "none"  # no namespace: no operation it could name
            await self.send_async(rf.control(stream_id, {
                "op": "END", "outcome": "refused", "error_class": error_class,
                "stream_sent": False, "side_effect_state": effect}))

        if self._role != OWNER:
            await refuse("refused")  # the box channel's derivation lands with boxhostd
            return
        with self._server._streams_lock:
            crowded = len(self._server._streams) >= MAX_STREAMS
        if crowded:
            await refuse("refused")
            return
        grant_id, connection_id = doc.get("grant_id"), doc.get("connection_id")
        verb, request = doc.get("verb"), doc.get("request")
        generation, token = doc.get("generation"), doc.get("token")
        if not all(isinstance(v, str) and v for v in
                   (principal, command_center, grant_id, connection_id, verb, op_id)) \
                or not isinstance(request, dict) or type(generation) is not int \
                or not isinstance(token, str):
            await refuse("refused")
            return
        try:
            ledger = self._server._ledger_for(principal)
            _grant, resource = await asyncio.to_thread(
                ledger.authorize_exact, universe_id=command_center, grant_id=grant_id,
                connection_id=connection_id,
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a fixed class
            name = type(exc).__name__
            await refuse(name if name in ERROR_CLASSES else "GrantResolutionError")
            return
        if not self._server._fence.admits(generation, token):
            await refuse("fenced")
            return
        namespace = _namespace(principal, command_center)
        digest = request_digest(grant_id=grant_id, connection_id=connection_id, verb=verb,
                                request=request)
        try:
            admission = await asyncio.to_thread(self._server._ops.admit, namespace, op_id,
                                                digest)
        except OpIdInvalid:
            await refuse("refused")
            return
        if admission.kind != "new":
            await refuse({"expired": "expired", "existing": "duplicate",
                          "mismatch": "duplicate"}.get(admission.kind, "refused"))
            return
        stream = _Stream(stream_id, generation, token, namespace, op_id,
                         deadline=time.monotonic() + _stream_budget(request),
                         credit=min(max(int(doc.get("credit") or 0), 0), MAX_WINDOW))
        with self._server._streams_lock:
            self._server._streams[(self._key, stream_id)] = stream
        try:
            dispatch = self._server._dispatch_for(principal, command_center, grant_id,
                                                  resource)
            threading.Thread(
                target=self._run, args=(stream, dispatch, grant_id, verb, request,
                                        doc.get("idle_s")),
                name=f"broker-stream-{stream_id}", daemon=True,
            ).start()
        except Exception:  # noqa: BLE001 - nothing was sent: settle it as refused
            with self._server._streams_lock:
                self._server._streams.pop((self._key, stream_id), None)
            await asyncio.to_thread(self._server._ops.finish, namespace, op_id, "refused")
            await refuse("refused")

    @contextlib.contextmanager
    def _guard(self, stream: _Stream) -> Iterator[None]:
        """Held across each network send: fence and cancellation re-checked first."""
        with self._server._fence.send(stream.generation, stream.token):
            if stream.cancelled:
                raise _Cancelled
            if time.monotonic() >= stream.deadline:
                raise _Expired
            yield

    def _run(self, stream: _Stream, dispatch: Callable[..., Any], grant_id: str, verb: str,
             request: dict[str, Any], idle_s: Any) -> None:
        outcome, error_class, extra = "failed", "ProxyRequestError", {}
        try:
            if stream.cancelled:
                raise _Cancelled
            self._server._ops.mark_may_have_sent(stream.namespace, stream.op_id)
            self.send(rf.control(stream.id, {"op": "ADMITTED", "op_id": stream.op_id}))
            stream.sent = True
            upstream = dispatch(
                grant_id, verb, request, stream=True,
                idle_s=idle_s if type(idle_s) in (int, float) else None,
                guard=lambda: self._guard(stream), on_connect=stream.sockets.append,
            )
            stream.upstream = upstream
            if stream.cancelled:
                raise _Cancelled
            self.send(rf.control(stream.id, {
                "op": "HEAD", "status": upstream.status, "reason": upstream.reason,
                "headers": upstream.headers, "redirect_count": upstream.redirect_count,
            }))
            self._pump_body(stream, upstream)
            outcome, error_class = "completed", None
        except _Cancelled:
            outcome, error_class = "cancelled", None
        except (_Expired, TimeoutError):
            outcome, error_class = "failed", "OutboundDeadlineExceeded"
        except Fenced:
            outcome, error_class = "cancelled", "fenced"
        except Exception as exc:  # noqa: BLE001 - mapped to a fixed class
            if stream.cancelled:
                # Shutting the socket down is how a cancel unblocks a read; the
                # read's own error is that, not a destination failure.
                outcome, error_class = "cancelled", None
            else:
                name = type(exc).__name__
                error_class = name if name in ERROR_CLASSES else "ProxyRequestError"
                failure = getattr(exc, "failure", None)
                if name == "ConnectionAuthorizationError" and isinstance(failure, dict):
                    extra = {"failure": failure}
        finally:
            if stream.upstream is not None and outcome != "completed":
                stream.upstream.close()
            with self._server._streams_lock:
                self._server._streams.pop((self._key, stream.id), None)
            try:
                self._server._ops.finish(stream.namespace, stream.op_id,
                                         outcome if stream.sent else "refused")
            except Exception:  # noqa: BLE001 - the record keeps may_have_sent: unknown
                _LOG.warning("could not record the end of operation %s", stream.op_id)
            self.send(rf.control(stream.id, {
                "op": "END", "outcome": outcome, "error_class": error_class,
                "stream_sent": stream.sent,
                "side_effect_state": "unknown" if stream.sent else "none", **extra,
            }))

    def _pump_body(self, stream: _Stream, upstream: Any) -> None:
        buffered = bytearray()
        finished = False
        while True:
            with stream.wake:
                while True:
                    if stream.cancelled:
                        raise _Cancelled
                    if (buffered and stream.credit > 0) or (finished and not buffered) \
                            or (not finished and len(buffered) < LOOKAHEAD + stream.credit):
                        break
                    remaining = stream.deadline - time.monotonic()
                    if remaining <= 0:
                        raise _Expired
                    stream.wake.wait(remaining)
                credit = stream.credit
            if buffered and credit > 0:
                piece = bytes(buffered[:credit])
                del buffered[:len(piece)]
                with stream.wake:
                    stream.credit -= len(piece)
                self.send(rf.data(stream.id, piece))
                continue
            if finished:
                return
            if time.monotonic() >= stream.deadline:
                raise _Expired
            chunk = upstream.read(LOOKAHEAD + credit - len(buffered))
            if chunk is None:
                finished = True
            else:
                buffered += chunk

    def abandon(self) -> None:
        """The peer went away: stop queueing, cancel every stream it owned."""
        self._closed.set()
        with self._server._streams_lock:
            mine = [s for (key, _), s in self._server._streams.items() if key == self._key]
        for stream in mine:
            self._server.cancel(stream)


class _Cancelled(Exception):
    pass


class _Expired(Exception):
    pass


def _namespace(principal: Any, command_center: Any) -> str:
    if not isinstance(principal, str) or not isinstance(command_center, str) \
            or not principal or not command_center or "|" in principal:
        raise rf.FrameError("a namespace needs a principal and a command center")
    return f"{principal}|{command_center}"
