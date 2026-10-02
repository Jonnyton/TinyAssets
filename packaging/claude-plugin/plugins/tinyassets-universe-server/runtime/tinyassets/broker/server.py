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
5. ``may_have_sent`` is written durably, ``ADMITTED`` is sent, and only then
   does the request leave, under the fence's send lock;
6. ``HEAD``, then ``DATA`` within the caller's credit, then ``END``.

The upstream exchange is the hardened synchronous driver, so each live stream
runs it on a thread of its own (the broker's memory per stream is that thread
plus its window; an async upstream is a later step, measured first).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import socket
import struct
import threading
from collections.abc import Callable, Mapping
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


@dataclass
class _Stream:
    id: int
    generation: int
    namespace: str
    op_id: str
    credit: int = 0
    cancelled: bool = False
    sent: bool = False
    upstream: Any = None
    wake: threading.Condition = field(default_factory=threading.Condition)


DispatchFor = Callable[[str, str], Callable[..., Any]]
"""``dispatch_for(principal, universe_id, grant_id, connection_id)`` -> dispatch callable."""


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

    # ── connections ─────────────────────────────────────────────────────────

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
        try:
            while (frame := await rf.read_frame(reader)) is not None:
                await connection.handle(frame)
        except rf.FrameError:
            _LOG.warning("broker peer broke the framing; dropping it")
        finally:
            connection.abandon()
            writer.close()

    # ── barrier, used by the connection and by tests ────────────────────────

    def _cancel_older(self, generation: int) -> None:
        with self._streams_lock:
            older = [s for s in self._streams.values() if s.generation < generation]
        for stream in older:
            self._cancel(stream)

    def _close_older(self, generation: int) -> None:
        self._cancel_older(generation)

    @staticmethod
    def _cancel(stream: _Stream) -> None:
        with stream.wake:
            stream.cancelled = True
            stream.wake.notify_all()
        upstream = stream.upstream
        if upstream is not None:
            upstream.close()


class _Connection:
    """One peer: its streams, its write queue."""

    def __init__(self, server: BrokerServer, writer: asyncio.StreamWriter, role: str) -> None:
        self._server = server
        self._writer = writer
        self._role = role
        self._loop = asyncio.get_running_loop()
        self._key = id(self)

    def send(self, frame: bytes | list[bytes]) -> None:
        """Thread-safe: queue frames for this peer on the event loop."""
        frames = frame if isinstance(frame, list) else [frame]

        def write() -> None:
            if not self._writer.is_closing():
                for item in frames:
                    self._writer.write(item)

        self._loop.call_soon_threadsafe(write)

    def end(self, stream_id: int, **fields: Any) -> None:
        fields.setdefault("side_effect_state", "unknown")
        self.send(rf.control(stream_id, {"op": "END", **fields}))

    async def handle(self, frame: rf.Frame) -> None:
        if frame.kind == rf.DATA:
            return  # request bodies are inline in v1; stray data is ignored
        doc = frame.control()
        op = doc["op"]
        if frame.stream == rf.CONNECTION:
            await self._connection_op(op, doc)
            return
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
            self._server._cancel(stream)

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
                self.send(rf.control(rf.CONNECTION, {"op": "FENCE_REFUSED"}))
                return
            self.send(rf.control(rf.CONNECTION, {"op": "FENCE_ACK", "generation": generation,
                                                 "token": token}))
        elif op == "STATUS":
            namespace = _namespace(doc.get("principal"), doc.get("command_center"))
            try:
                record = self._server._ops.status(namespace, str(doc.get("op_id", "")))
            except OpIdInvalid:
                record = "invalid"
            if isinstance(record, str):
                answer = {"op": "STATUS_IS", "op_id": doc.get("op_id"), "state": record}
            else:
                answer = {"op": "STATUS_IS", "op_id": record.op_id, "state": record.state,
                          "side_effect_state": "unknown" if record.sent else "none"}
            self.send(rf.control(rf.CONNECTION, answer))

    async def _open(self, stream_id: int, doc: dict[str, Any]) -> None:
        def refuse(error_class: str, *, sent: bool = False) -> None:
            self.end(stream_id, outcome="refused", error_class=error_class,
                     stream_sent=False, side_effect_state="unknown" if sent else "none")

        if self._role != OWNER:
            refuse("refused")  # the box channel's principal derivation lands with boxhostd
            return
        if len(self._server._streams) >= MAX_STREAMS:
            refuse("refused")
            return
        principal, command_center = doc.get("principal"), doc.get("command_center")
        grant_id, connection_id = doc.get("grant_id"), doc.get("connection_id")
        verb, request, op_id = doc.get("verb"), doc.get("request"), doc.get("op_id")
        generation, token = doc.get("generation"), doc.get("token")
        if not all(isinstance(v, str) and v for v in
                   (principal, command_center, grant_id, connection_id, verb, op_id)) \
                or not isinstance(request, dict) or type(generation) is not int \
                or not isinstance(token, str):
            refuse("refused")
            return
        try:
            ledger = self._server._ledger_for(principal)
            _grant, resource = await asyncio.to_thread(
                ledger.authorize_exact, universe_id=command_center, grant_id=grant_id,
                connection_id=connection_id,
            )
        except Exception as exc:  # noqa: BLE001 - mapped to a fixed class
            refuse(type(exc).__name__ if type(exc).__name__ in ERROR_CLASSES
                   else "GrantResolutionError")
            return
        if not self._server._fence.admits(generation, token):
            refuse("fenced")
            return
        namespace = _namespace(principal, command_center)
        digest = request_digest(grant_id=grant_id, connection_id=connection_id, verb=verb,
                                request=request)
        try:
            admission = await asyncio.to_thread(self._server._ops.admit, namespace, op_id,
                                                digest)
        except OpIdInvalid:
            refuse("refused")
            return
        if admission.kind in ("expired", "future", "full"):
            refuse("expired" if admission.kind == "expired" else "refused")
            return
        if admission.kind in ("existing", "mismatch"):
            refuse("duplicate", sent=admission.record.sent)
            return
        stream = _Stream(stream_id, generation, namespace, op_id,
                         credit=min(max(int(doc.get("credit") or 0), 0), MAX_WINDOW))
        self._server._streams[(self._key, stream_id)] = stream
        await asyncio.to_thread(self._server._ops.mark_may_have_sent, namespace, op_id)
        stream.sent = True
        self.send(rf.control(stream_id, {"op": "ADMITTED", "op_id": op_id}))
        dispatch = self._server._dispatch_for(principal, command_center, grant_id, resource)
        threading.Thread(
            target=self._run, args=(stream, dispatch, grant_id, verb, request, token,
                                    doc.get("idle_s")),
            name=f"broker-stream-{stream_id}", daemon=True,
        ).start()

    def _run(self, stream: _Stream, dispatch: Callable[..., Any], grant_id: str, verb: str,
             request: dict[str, Any], token: str, idle_s: Any) -> None:
        outcome, error_class = "failed", "ProxyRequestError"
        try:
            with self._server._fence.send(stream.generation, token):
                if stream.cancelled:
                    raise _Cancelled
                upstream = dispatch(grant_id, verb, request, stream=True,
                                    idle_s=idle_s if isinstance(idle_s, (int, float)) else None)
                stream.upstream = upstream
            if stream.cancelled:
                upstream.close()
                raise _Cancelled
            self.send(rf.control(stream.id, {
                "op": "HEAD", "status": upstream.status, "reason": upstream.reason,
                "headers": upstream.headers, "redirect_count": upstream.redirect_count,
            }))
            buffered = bytearray()
            finished = False
            while True:
                with stream.wake:
                    while (not stream.cancelled and stream.credit <= 0
                           and (finished or len(buffered) >= LOOKAHEAD)):
                        stream.wake.wait()
                    if stream.cancelled:
                        raise _Cancelled
                    credit = stream.credit
                if credit > 0 and buffered:
                    piece = bytes(buffered[:credit])
                    del buffered[:len(piece)]
                    with stream.wake:
                        stream.credit -= len(piece)
                    self.send(rf.data(stream.id, piece))
                    continue
                if finished:
                    outcome, error_class = "completed", None
                    break
                chunk = upstream.read(max(credit, 0) + LOOKAHEAD - len(buffered) or 1)
                if chunk is None:
                    finished = True
                    if not buffered:
                        outcome, error_class = "completed", None
                        break
                    continue
                buffered += chunk
        except _Cancelled:
            outcome, error_class = "cancelled", None
        except Fenced:
            outcome, error_class = "cancelled", "fenced"
        except Exception as exc:  # noqa: BLE001 - mapped to a fixed class
            if stream.cancelled:
                # Closing the upstream is how a cancel unblocks a read; the
                # read's own error is that, not a destination failure.
                outcome, error_class = "cancelled", None
            else:
                name = type(exc).__name__
                error_class = name if name in ERROR_CLASSES else "ProxyRequestError"
        finally:
            upstream_left = stream.upstream
            if upstream_left is not None and outcome != "completed":
                upstream_left.close()
            with self._server._streams_lock:
                self._server._streams.pop((self._key, stream.id), None)
            try:
                self._server._ops.finish(stream.namespace, stream.op_id, outcome)
            except Exception:  # noqa: BLE001 - the record keeps may_have_sent: unknown
                _LOG.warning("could not record the end of operation %s", stream.op_id)
            self.end(stream.id, outcome=outcome, error_class=error_class, stream_sent=True,
                     side_effect_state="unknown")

    def abandon(self) -> None:
        """The peer went away: cancel every stream it owned."""
        with self._server._streams_lock:
            mine = [s for (key, _), s in self._server._streams.items() if key == self._key]
        for stream in mine:
            self._server._cancel(stream)


class _Cancelled(Exception):
    pass


def _namespace(principal: Any, command_center: Any) -> str:
    if not isinstance(principal, str) or not isinstance(command_center, str) \
            or not principal or not command_center or "|" in principal:
        raise rf.FrameError("a namespace needs a principal and a command center")
    return f"{principal}|{command_center}"
