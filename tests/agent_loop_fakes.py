"""A scripted ``BoxProvider`` (``tinyassets.boxes``, target architecture D2).

It runs nothing. Each ``start_exec`` is recorded with its ``op_id`` and argv
and answered by a script the test supplies; a repeated ``op_id`` returns the
recorded execution and never runs the script again, which is the D2 contract
the loop's lost-reply handling relies on. Events use the real types:
``output`` (merged stdout/stderr, ``offset`` = chunk start) and ``exit``
(``exit_code``, ``killed``).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from tinyassets.boxes import BoxHandle, ExecEvent, ExecState, ExecStatus


@dataclass
class Exec:
    op_id: str
    argv: list[str]
    stdin: Any
    cwd: str
    limits: Any
    events: list[Any] = field(default_factory=list)
    cancelled: bool = False


def out(data: bytes, offset: int = 0) -> ExecEvent:
    return ExecEvent("output", offset=offset, data=data)


def exit_event(code: int | None, killed: str | None = None) -> ExecEvent:
    return ExecEvent("exit", exit_code=code, killed=killed)


class FakeBox:
    """Scripted executions keyed by op_id; ``script(argv, stdin) -> (bytes, code)``."""

    def __init__(self, script: Callable[[list[str], Any], tuple[bytes, int]] | None = None):
        self.script = script or (lambda argv, stdin: (b"ok\n", 0))
        self.execs: dict[str, Exec] = {}
        self.starts: list[str] = []
        self.cancels: list[str] = []
        self.binds: list[tuple[str, str, str | None]] = []
        self.awakened = 0
        self.fail_start: int = 0
        self.fail_stream: int = 0
        self.hang = False
        self.status_state = ExecState.UNKNOWN_AFTER_RESTORE
        self.released = threading.Event()
        self.lock = threading.Lock()

    # ── D2 surface ──────────────────────────────────────────────────────────
    def bind(self, command_center_id, *, account_id, turn_id=None):
        self.binds.append((command_center_id, account_id, turn_id))
        return BoxHandle(command_center_id, account_id, 1, turn_id)

    def ensure_awake(self, handle, *, reason):
        self.awakened += 1

    def start_exec(self, handle, op_id, argv, *, stdin=b"", env=None, cwd="/cc",
                   limits=None):
        with self.lock:
            self.starts.append(op_id)
            first = op_id not in self.execs
            if first:
                self.execs[op_id] = Exec(op_id, list(argv), stdin, cwd, limits)
        if first:
            # Outside the lock: concurrent executions really run concurrently.
            data, code = self.script(list(argv), stdin or None)
            self.execs[op_id].events = (
                [out(data, 0), exit_event(code)] if data else [exit_event(code)])
        with self.lock:
            if self.fail_start:
                self.fail_start -= 1
                raise ConnectionError("synthetic lost reply")
        return op_id

    def stream(self, handle, exec_id, *, from_offset=0, timeout=None):
        record = self.execs[exec_id]
        if self.fail_stream:
            self.fail_stream -= 1
            raise ConnectionError("synthetic stream break")
        if self.hang:
            # Running: a slice ends at its timeout without an exit event, until
            # a cancel lands.
            if self.released.wait(timeout if timeout is not None else 10):
                yield exit_event(137, "cancelled")
            return
        for event in record.events:
            if event.kind == "output" and event.offset + len(event.data) <= from_offset:
                continue
            yield event

    def cancel(self, handle, exec_id):
        self.cancels.append(exec_id)
        self.execs[exec_id].cancelled = True
        self.released.set()

    def exec_status(self, handle, op_id):
        return ExecStatus(op_id, op_id, self.status_state)
