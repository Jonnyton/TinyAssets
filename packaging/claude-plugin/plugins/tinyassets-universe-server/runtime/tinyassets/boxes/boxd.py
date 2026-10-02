"""`boxd`: the agent inside an isolating box. It serves the `BoxProvider` contract over one socket.

The gVisor (and later Firecracker) box host starts this as the box's only long-lived
process. It runs **inside** the sandbox, so every path it resolves and every
command it runs is confined by the box's own kernel boundary: a planted link
resolves inside the box, and an exec's children die with the box.

It does no authorization. The box host has already checked the owner, the epoch,
the owner fence and the op id before forwarding, and it can always kill the
whole box. Inside, `boxd` reuses the local driver's descriptor-safe core (paths,
exec supervision, atomic writes, bounded calls), rooted at ``/cc``.

It shares the box with the commands it runs, so a hostile command can replace it.
The host therefore treats every reply as data about this box only. Ownership,
fences, op ids and kill-the-box are decided on the host, and none of them depends on
what `boxd` says.

Wire: one request per connection, over `tinyassets.rpc_frames` on stream 1, keeping
that module's conventions (upper-case ops; a stream ends with one ``END`` frame
carrying ``outcome``, ``error_class`` and ``side_effect_state``; ``deadline_ms`` on
the request).

    request   CONTROL {"op": <METHOD>, "args": {...}, "deadline_ms": <epoch ms>}
              [DATA ...]  then  CONTROL {"op": "END", "outcome": "completed"}
                                                         (only methods with input bytes)
    response  [CONTROL {"op": "EVENT", ...}] [DATA ...]
              then CONTROL {"op": "END", "outcome": "completed", "value": ...}
              or   CONTROL {"op": "END", "outcome": "refused" | "failed",
                            "error_class": <box error class>,
                            "side_effect_state": "none" | "unknown", "message": ...}

The box host gives each request its own connection. Cancelling an in-flight
request is closing its connection. Cancelling an exec is its own request,
``CANCEL_EXEC``, so it never queues behind another request.
"""

from __future__ import annotations

import argparse
import base64
import dataclasses
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

from tinyassets import rpc_frames
from tinyassets.boxes.provider import (
    BOX_ROOT,
    BoxError,
    BoxOperationRefused,
    ExecLimits,
    ExportProfile,
    WriteMode,
)

__all__ = ["BOX_ACCOUNT", "BOX_CC", "serve"]

#: Inside the box there is exactly one command center, at /cc.
BOX_CC = "cc"
BOX_ACCOUNT = "box"
STREAM = 1
_INPUT = {"WRITE", "IMPORT_BUNDLE"}
#: Error classes a reply may name; anything else is reported as BoxError.
_CLASSES = {"BoxAuthError", "BoxBusy", "BoxDeadline", "BoxDeadlineBeforeStart", "BoxError",
            "BoxNotFound", "BoxOperationRefused", "BoxPathError", "OpIdReuse", "StaleHandle",
            "StaleOwner", "WriteConflict"}


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, bytes):
        return {"__b64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
        return value.value  # str enums
    return value


class _Server:
    def __init__(self, core) -> None:
        self._core = core
        self._handle = core.bind(BOX_CC, account_id=BOX_ACCOUNT)

    def _call(self, op: str, args: dict, payload: bytes, conn: socket.socket) -> Any:
        h = self._handle
        if op == "ping":
            return {"ok": True}
        if op == "read":
            return self._core.read(h, args["path"], offset=args.get("offset", 0),
                                   max_bytes=args["max_bytes"])
        if op == "read_many":
            snap = self._core.read_many(h, args["paths"], max_total=args["max_total"])
            return {"files": snap.files, "missing": snap.missing, "generation": snap.generation}
        if op == "write":
            return self._core.write(h, args["op_id"], args["path"], payload,
                                    max_bytes=args["max_bytes"], mode=WriteMode(args["mode"]),
                                    expect_generation=args.get("expect_generation"))
        if op == "list":
            return self._core.list(h, args["path"], cursor=args.get("cursor"),
                                   limit=args.get("limit", 200))
        if op == "stat":
            return self._core.stat(h, args["path"])
        if op == "remove":
            self._core.remove(h, args["op_id"], args["path"])
            return None
        if op == "start_exec":
            lim = args.get("limits") or {}
            return self._core.start_exec(
                h, args["op_id"], args["argv"],
                stdin=base64.b64decode(args.get("stdin_b64", "")), env=args.get("env") or {},
                cwd=args.get("cwd", BOX_ROOT),
                limits=ExecLimits(**lim) if lim else ExecLimits())
        if op == "cancel_exec":
            self._core.cancel(h, args["exec_id"])
            return None
        if op == "exec_status":
            return self._core.exec_status(h, args["op_id"])
        if op == "usage":
            return self._core.usage(h)
        if op == "generation":
            return self._core.committed_generation(h)
        if op == "idle":
            return {"idle": self._core.is_idle(BOX_CC)}
        if op == "import_bundle":
            return self._core.import_bundle(h, args["op_id"], [payload],
                                            profile=ExportProfile(args["profile"]))
        if op == "stream":
            for ev in self._core.stream(h, args["exec_id"], from_offset=args.get("from_offset", 0),
                                        timeout=args.get("timeout")):
                if ev.kind == "output":
                    _send(conn, rpc_frames.control(STREAM, {"op": "EVENT", "kind": "output",
                                                            "offset": ev.offset}))
                    for frame in rpc_frames.data(STREAM, ev.data):
                        _send(conn, frame)
                else:
                    _send(conn, rpc_frames.control(STREAM, {
                        "op": "EVENT", "kind": "exit", "offset": ev.offset,
                        "exit_code": ev.exit_code, "killed": ev.killed}))
            return None
        if op == "download":
            for block in self._core.download(h, args["path"]):
                for frame in rpc_frames.data(STREAM, block):
                    _send(conn, frame)
            return None
        if op == "export":
            for block in self._core.export(h, profile=ExportProfile(args["profile"])):
                for frame in rpc_frames.data(STREAM, block):
                    _send(conn, frame)
            return None
        raise BoxError(f"unknown box operation {op!r}")

    def handle(self, conn: socket.socket) -> None:
        conn.settimeout(600)
        try:
            first = rpc_frames.read_frame_blocking(conn)
            if first is None or first.kind != rpc_frames.CONTROL:
                return
            request = first.control()
            op, args = request["op"], request.get("args") or {}
            payload = b""
            if op in _INPUT:
                parts = []
                while True:
                    frame = rpc_frames.read_frame_blocking(conn)
                    if frame is None:
                        return
                    if frame.kind == rpc_frames.DATA:
                        parts.append(frame.payload)
                    elif frame.control().get("op") == "END":
                        break
                payload = b"".join(parts)
            deadline_ms = request.get("deadline_ms")
            remaining = None if deadline_ms is None else deadline_ms / 1000 - time.time()
            try:
                method = op.lower()
                if remaining is not None:
                    with self._core.bounded(max(0.0, remaining)):
                        value = self._call(method, args, payload, conn)
                else:
                    value = self._call(method, args, payload, conn)
                _send(conn, rpc_frames.control(STREAM, {"op": "END", "outcome": "completed",
                                                        "value": _jsonable(value)}))
            except Exception as exc:  # noqa: BLE001 - every failure crosses the wire typed
                refused = isinstance(exc, BoxOperationRefused)
                name = type(exc).__name__
                _send(conn, rpc_frames.control(STREAM, {
                    "op": "END", "outcome": "refused" if refused else "failed",
                    "error_class": name if name in _CLASSES else "BoxError",
                    "side_effect_state": "none" if refused else "unknown",
                    "message": str(exc)[:2000]}))
        except (rpc_frames.FrameError, OSError):
            return  # a broken peer: drop it
        finally:
            try:
                conn.close()
            except OSError:
                pass


def _send(conn: socket.socket, frame: bytes) -> None:
    conn.sendall(frame)


def serve(socket_path: str, root: str, state_dir: str, *, ready_file: str | None = None) -> None:
    from tinyassets.boxes.local import LocalBoxProvider

    # Inside the sandbox the box IS isolated: the local core is the right engine here.
    core = LocalBoxProvider(boxes_root=Path(root).parent, state_dir=Path(state_dir),
                            owner_of=lambda cc: BOX_ACCOUNT if cc == BOX_CC else None,
                            allow_unisolated=True)
    if Path(root).name != BOX_CC:
        raise SystemExit(f"boxd serves exactly {BOX_ROOT}; got {root}")
    server = _Server(core)
    try:
        os.unlink(socket_path)
    except FileNotFoundError:
        pass
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(socket_path)
    os.chmod(socket_path, 0o600)
    listener.listen(64)
    if ready_file:
        Path(ready_file).write_text("ready")
    while True:
        conn, _ = listener.accept()
        threading.Thread(target=server.handle, args=(conn,), daemon=True).start()


def _main() -> None:
    parser = argparse.ArgumentParser(prog="boxd")
    parser.add_argument("--socket", required=True)
    parser.add_argument("--root", default=BOX_ROOT)
    parser.add_argument("--state", default="/run/boxd")
    parser.add_argument("--ready-file")
    args = parser.parse_args()
    serve(args.socket, args.root, args.state, ready_file=args.ready_file)


if __name__ == "__main__":
    _main()

