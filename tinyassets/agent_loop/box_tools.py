"""The four box tools, forwarded to the turn's bound box by ``op_id``.

``read``, ``write``, ``edit`` and ``bash`` are the same four tools as the tool
jail serves today (:mod:`tinyassets.universe_tools`), with the same arguments
and the same text answers. What changes is where they run: each call is one
``start_exec`` on the command center's box through the
:class:`~tinyassets.boxes.BoxProvider` (target architecture D2), never a process
the loop starts itself. The box enforces the wall clock and the output cap
(``ExecLimits``); the loop only collects.

Binding. The session is constructed with a handle the caller bound ONCE at
turn start (``BoxProvider.bind(cc, account_id=..., turn_id=...)``). No call
looks a box up by name, so a loop bug cannot route one owner's tool call into
another owner's box; the box host refuses a handle minted for another command
center or turn as well (D2 "Authentication of every operation").

Lost replies. Every call carries an ``op_id`` derived from the journal
position of the call (turn, round, call). D2 makes ``start_exec`` idempotent by
``op_id``: a retry with the same request returns the recorded execution and
never re-runs it. So a transport failure is resolved by asking again with the
SAME ``op_id`` and the same arguments, once, and anything still unresolved --
including an exit the box reports as ``unknown_after_restore`` -- is an UNKNOWN
outcome. The coordinator journals it as unknown and the turn holds.

Collection is a loop of bounded slices (``stream(timeout=SLICE_SECONDS)``),
with the turn's cancellation and a backstop deadline checked between them.
Each blocking provider call still runs inside an owned, capacity-bounded
boundary (``_in_thread``): the local driver takes untimed per-box locks, so a
call is not yet guaranteed to return (change ``control-plane-agent-loop``,
"PR 2 shape"). When the box contract bounds every call, that boundary goes.

Cancellation. A cancelled turn asks the box to cancel the execution
(``BoxProvider.cancel``: request accepted, not execution ended) before the
cancellation propagates; the coordinator records the call as unknown.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from tinyassets.boxes import (
    BOX_ROOT,
    BoxHandle,
    BoxOperationRefused,
    BoxProvider,
    ExecEvent,
    ExecLimits,
)
from tinyassets.engine_tool_client import EngineToolError

_LOG = logging.getLogger(__name__)

#: The tool names this module serves, in canonical order.
BOX_TOOLS: tuple[str, ...] = ("read", "write", "edit", "bash")

_MiB = 1024 * 1024
MAX_WRITE_BYTES = 4 * _MiB
MAX_EDIT_BYTES = 1 * _MiB
DEFAULT_READ_LINES = 2000
DEFAULT_WALL_SECONDS = 120.0
MAX_BASH_SECONDS = 600.0
OUTPUT_BYTES = 64 * 1024
#: One collection slice: the longest a ``stream`` call is asked to wait.
SLICE_SECONDS = 1.0
#: How far past the box's own wall clock the loop waits before it cancels
#: itself (the box enforces ``ExecLimits.wall_seconds``; this is the backstop).
_BACKSTOP_SECONDS = 10.0
#: How long a cancel, or a cancelled execution's end, may take before the turn
#: stops waiting for it (and reports the outcome as unknown).
_CANCEL_GRACE_SECONDS = 5.0
#: Box calls (starts and stream slices) that may be in flight in this process.
#: A call the box host never answers keeps its slot, so a host that stops
#: answering exhausts this bound and new calls are refused loudly, instead of
#: threads accumulating without limit.
MAX_BOX_CALLS = 512
_BOX_CALL_SLOTS = threading.BoundedSemaphore(MAX_BOX_CALLS)
#: Cancels in flight, bounded separately so a stuck cancel can never take the
#: slot a new call needs. With none free, a cancel is not sent and the outcome
#: is reported unknown (the turn holds) rather than spawning another thread.
MAX_BOX_CANCELS = 128
_BOX_CANCEL_SLOTS = threading.BoundedSemaphore(MAX_BOX_CANCELS)
#: ``killed`` values the box reports for an execution that provably ENDED.
_ENDED_KILLS = frozenset({None, "timeout", "output_limit", "cancelled", "supervisor_error"})


@dataclass(frozen=True, slots=True)
class ExecOutcome:
    """What one execution reported: merged output, exit code, and why it was cut."""

    output: bytes
    exit_code: int | None
    killed: str | None = None


def _unknown() -> EngineToolError:
    return EngineToolError("box_tool_outcome_unknown", outcome="unknown")


class _Collected:
    """Output and offset across slices; turns an exit event into an outcome."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        self.output = bytearray()
        self.offset = 0

    def feed(self, events: Sequence[ExecEvent]) -> ExecOutcome | None:
        for event in events:
            if event.kind == "output":
                data = bytes(event.data or b"")
                start = event.offset if type(event.offset) is int else self.offset
                if start + len(data) <= self.offset:
                    continue  # already have it (a resumed slice)
                data = data[max(self.offset - start, 0):]
                room = self.cap - len(self.output)
                self.output += data[:max(room, 0)]
                self.offset = max(self.offset, start + len(event.data or b""))
            elif event.kind == "exit":
                if event.killed not in _ENDED_KILLS:
                    # unknown_after_restore, or anything the box cannot vouch
                    # for: an exit event is not proof the effect is known.
                    raise _unknown()
                return ExecOutcome(bytes(self.output), event.exit_code, event.killed)
        return None


class BoxExecutor:
    """Runs argv in ONE bound box by ``op_id``; the only door the tools use."""

    def __init__(self, provider: BoxProvider, handle: BoxHandle, *,
                 cwd: str = BOX_ROOT) -> None:
        if handle is None:
            raise ValueError("a bound box handle is required")
        self._provider = provider
        self._handle = handle
        self._cwd = cwd
        self._awake = False

    @property
    def handle(self) -> BoxHandle:
        return self._handle

    def _start(self, op_id: str, argv: Sequence[str], stdin: bytes,
               limits: ExecLimits) -> str:
        def start() -> str:
            if not self._awake:
                # bind() never wakes a box; the first execution does.
                self._provider.ensure_awake(self._handle, reason="tool")
                self._awake = True
            return self._provider.start_exec(self._handle, op_id, list(argv), stdin=stdin,
                                             cwd=self._cwd, limits=limits)

        try:
            return start()
        except BoxOperationRefused:
            raise
        except Exception:
            # The reply was lost, not necessarily the operation. The same op_id
            # with the same request returns the recorded execution, never a
            # second one.
            _LOG.warning("box start_exec reply lost; asking again with the same op_id")
            try:
                return start()
            except Exception:
                # Refused only on the retry: the first attempt may have run.
                raise _unknown() from None

    def _slice(self, exec_id: str, offset: int) -> list[ExecEvent]:
        """One bounded read: the events up to an exit, or until the slice ends."""
        return list(self._provider.stream(self._handle, exec_id, from_offset=offset,
                                          timeout=SLICE_SECONDS))

    async def run(self, op_id: str, argv: Sequence[str], *, stdin: bytes | None = None,
                  wall_seconds: float, output_bytes: int = OUTPUT_BYTES) -> ExecOutcome:
        """One execution; the box enforces its limits, the loop collects slices.

        A turn's cancellation, or the backstop past the box's own wall clock,
        cancels it in the box. A result that cannot be confirmed as ended is an
        UNKNOWN outcome, never a completed one.
        """
        if not isinstance(op_id, str) or not op_id:
            raise ValueError("an op_id is required")
        limits = ExecLimits(wall_seconds=float(wall_seconds), output_bytes=int(output_bytes))
        launch = _Launch(self, op_id, argv, bytes(stdin or b""), limits)
        try:
            exec_id = await _wait(launch.future)
        except asyncio.CancelledError:
            # The box may accept the command after the turn was cancelled.
            # Exactly one side cancels it: this one if the reply is in, else
            # the launching thread when the reply arrives, however late.
            launch.abandon()
            raise
        loop = asyncio.get_running_loop()
        collected = _Collected(limits.output_bytes)
        deadline = loop.time() + limits.wall_seconds + _BACKSTOP_SECONDS
        cancelled = False
        failures = 0
        try:
            while True:
                try:
                    events = await _wait(_in_thread(self._slice, exec_id, collected.offset,
                                                    slots=_BOX_CALL_SLOTS))
                except BoxOperationRefused:
                    # The command is running; only reading it was refused.
                    await self._cancel(exec_id)
                    raise _unknown() from None
                except Exception:  # noqa: BLE001 - a lost slice is resumed once
                    failures += 1
                    if failures > 1:
                        raise _unknown() from None
                    _LOG.warning("box stream slice lost; resuming from offset %d",
                                 collected.offset)
                    continue
                failures = 0
                outcome = collected.feed(events)
                if outcome is not None:
                    if cancelled:
                        return ExecOutcome(outcome.output, outcome.exit_code, "timeout")
                    return outcome
                if loop.time() > deadline:
                    if cancelled:
                        # Cancelled, and still no exit: it may still be running.
                        raise _unknown()
                    cancelled = True
                    if not await self._cancel(exec_id):
                        raise _unknown()
                    deadline = loop.time() + _CANCEL_GRACE_SECONDS
        except asyncio.CancelledError:
            await self._cancel(exec_id)
            raise

    async def _cancel(self, exec_id: Any) -> bool:
        """Ask the box to kill the execution; ``True`` only if it acknowledged in time."""
        try:
            await _wait(_in_thread(self._provider.cancel, self._handle, exec_id,
                                   slots=_BOX_CANCEL_SLOTS),
                        timeout=_CANCEL_GRACE_SECONDS)
            return True
        except Exception:  # noqa: BLE001 - an unacknowledged cancel is reported as unknown
            _LOG.warning("box cancel was not acknowledged; the outcome is unknown")
            return False

    def cancel_quietly(self, exec_id: Any) -> None:
        """Cancel from a thread that has no turn to report to (it recorded unknown)."""
        try:
            self._provider.cancel(self._handle, exec_id)
        except Exception:  # noqa: BLE001 - the turn already recorded an unknown outcome
            _LOG.warning("box cancel of an abandoned execution failed")

    def cancel_in_background(self, exec_id: Any) -> None:
        """``cancel_quietly`` on a cancel slot's thread; none free, it is logged."""
        if not _BOX_CANCEL_SLOTS.acquire(blocking=False):
            _LOG.warning("no cancel slot free; an abandoned box execution was not cancelled")
            return

        def work() -> None:
            try:
                self.cancel_quietly(exec_id)
            finally:
                _BOX_CANCEL_SLOTS.release()

        try:
            threading.Thread(target=work, name="box-cancel", daemon=True).start()
        except BaseException:
            _BOX_CANCEL_SLOTS.release()
            raise


class _Launch:
    """One ``start_exec`` whose late reply is never orphaned.

    If the turn stops waiting before the box answers, whichever side sees the
    other's state second cancels the execution the box accepted: the turn, if
    the exec id is already in; else the launching thread, when it arrives.
    """

    def __init__(self, executor: BoxExecutor, op_id: str, argv: Sequence[str],
                 stdin: bytes, limits: ExecLimits) -> None:
        self._executor = executor
        self._lock = threading.Lock()
        self._abandoned = False
        self._exec_id: Any = None
        self._started = False
        self.future = _in_thread(self._run, op_id, argv, stdin, limits,
                                 slots=_BOX_CALL_SLOTS)

    def _run(self, op_id: str, argv: Sequence[str], stdin: bytes,
             limits: ExecLimits) -> Any:
        exec_id = self._executor._start(op_id, argv, stdin, limits)
        with self._lock:
            self._started, self._exec_id = True, exec_id
            abandoned = self._abandoned
        if abandoned:
            self._executor.cancel_quietly(exec_id)
        return exec_id

    def abandon(self) -> None:
        with self._lock:
            self._abandoned = True
            started, exec_id = self._started, self._exec_id
        if started:
            self._executor.cancel_in_background(exec_id)


async def _wait(future: asyncio.Future, *, timeout: float | None = None) -> Any:
    """Await ``future`` without cancelling it: a timeout or a cancelled caller
    leaves the box call to finish on its own thread, which owns its cleanup."""
    done, _ = await asyncio.wait({future}, timeout=timeout)
    if not done:
        raise TimeoutError
    return future.result()


def _in_thread(fn: Callable[..., Any], /, *args: Any,
               slots: threading.BoundedSemaphore) -> asyncio.Future:
    """Run a blocking call on a fresh daemon thread; its result as a future.

    The call holds one of ``slots`` until it returns; none free means the box
    host has stopped answering, and the call is refused before it is sent.
    """
    if not slots.acquire(blocking=False):
        raise BoxOperationRefused("every box call slot is waiting on the box host")
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()
    # A call nobody waits for any more must not report its failure as unhandled.
    future.add_done_callback(lambda done: done.cancelled() or done.exception())

    def deliver(setter: Callable[[Any], None], value: Any) -> None:
        if not future.done():
            setter(value)

    def work() -> None:
        try:
            result = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - delivered to the awaiting task
            with contextlib.suppress(RuntimeError):  # the loop already closed
                loop.call_soon_threadsafe(deliver, future.set_exception, exc)
        else:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(deliver, future.set_result, result)
        finally:
            slots.release()

    try:
        threading.Thread(target=work, name="box-op", daemon=True).start()
    except BaseException:
        slots.release()
        raise
    return future


# ── the four tools ──────────────────────────────────────────────────────────


def box_path(path: str, root: str = BOX_ROOT) -> str:
    """The path as the box sees it: relative paths are under the box root.

    No containment check on purpose: the box is the boundary, and a path
    outside the command center does not exist inside it.
    """
    raw = (path or "").strip()
    if not raw:
        raise ValueError("a path is required")
    if "\x00" in raw:
        raise ValueError("a path may not contain a NUL byte")
    candidate = PurePosixPath(raw)
    if not candidate.is_absolute():
        candidate = PurePosixPath(root) / candidate
    return str(candidate)


def _text(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def _trailer(outcome: ExecOutcome, wall: float, output_bytes: int) -> str:
    if outcome.killed == "timeout":
        return f"[killed: ran longer than {wall:g}s]"
    if outcome.killed == "output_limit":
        return f"[killed: output passed {output_bytes} bytes]"
    if outcome.killed == "cancelled":
        return "[cancelled]"
    if outcome.killed == "supervisor_error":
        return "[killed: the box could not supervise the command]"
    if outcome.exit_code is None:
        return "[exit code unknown]"
    if outcome.exit_code in (128 + 24, 128 + 9):
        return "[killed: a cpu time or memory limit]"
    return f"[exit code {outcome.exit_code}]"


def _failed(outcome: ExecOutcome, wall: float, output_bytes: int) -> str:
    return "error: " + (_text(outcome.output).strip() or _trailer(outcome, wall, output_bytes))


_READ = (
    '[ -e "$1" ] || { echo "no such file: $1"; exit 1; }; '
    'if [ -d "$1" ]; then ls -la -- "$1"; exit $?; fi; '
    'tail -n "+$2" -- "$1" | head -n "$3"'
)
_CAT = '[ -f "$1" ] || { echo "no such file: $1"; exit 1; }; cat -- "$1"'
#: The content lands in a temp file first; the rename then happens under an
#: exclusive ``flock`` on the target's DIRECTORY, so a reader never sees half a
#: file and every write through these tools is ordered. The lock is on the
#: directory, not the file, because the rename replaces the file's inode: a
#: lock on the file would let a waiter on the old inode and a newcomer on the
#: new one run together. ``$2`` is the sha256 the target must still have
#: (edit), checked under the same lock, or empty (write). Two edits, or an
#: edit and a write, can therefore never silently overwrite each other: the
#: later one finds the hash changed and refuses. A process in the box that
#: writes the file WITHOUT the lock (an arbitrary ``bash`` command) is not
#: ordered by it; that residual is the same as for any editor. ``flock``
#: (util-linux) is a box-image requirement; without it the write fails loudly
#: rather than racing.
_WRITE = (
    'd="$(dirname -- "$1")"; '
    '[ -n "$2" ] || mkdir -p -- "$d" || exit 1; '
    't="$1.ta-write.$$"; cat > "$t" || { rm -f -- "$t"; exit 1; }; '
    'flock -x "$d" sh -c '
    '\'if [ -n "$2" ]; then [ -f "$1" ] || exit 4; '
    '[ "$(sha256sum -- "$1" | cut -d" " -f1)" = "$2" ] || exit 3; fi; '
    'mv -f -- "$3" "$1"\' '
    'sh "$1" "$2" "$t"; '
    'rc=$?; [ "$rc" -eq 0 ] && exit 0; rm -f -- "$t"; '
    '[ "$rc" -eq 3 ] && echo "$1 changed while it was being edited; read it again"; '
    '[ "$rc" -eq 4 ] && echo "no such file: $1"; '
    'exit "$rc"'
)


class BoxTools:
    """``read``/``write``/``edit``/``bash`` over one bound box."""

    def __init__(self, executor: BoxExecutor, *, root: str = BOX_ROOT) -> None:
        self._exec = executor
        self._root = root

    async def read(self, op_id: str, path: str, offset: int = 0, limit: int = 0) -> str:
        target = box_path(path, self._root)
        start = max(1, int(offset or 1))
        count = int(limit) if limit and int(limit) > 0 else DEFAULT_READ_LINES
        outcome = await self._exec.run(
            op_id, ["/bin/sh", "-c", _READ, "sh", target, str(start), str(count)],
            wall_seconds=DEFAULT_WALL_SECONDS,
        )
        if outcome.killed == "output_limit":
            return (_text(outcome.output) + f"\n[truncated at {OUTPUT_BYTES} bytes; read a "
                    "smaller range with offset and limit]")
        if outcome.killed or outcome.exit_code != 0:
            return _failed(outcome, DEFAULT_WALL_SECONDS, OUTPUT_BYTES)
        return _text(outcome.output)

    async def _put(self, op_id: str, target: str, payload: bytes, expect: str) -> ExecOutcome:
        return await self._exec.run(
            op_id, ["/bin/sh", "-c", _WRITE, "sh", target, expect],
            stdin=payload, wall_seconds=DEFAULT_WALL_SECONDS,
        )

    async def write(self, op_id: str, path: str, content: str) -> str:
        target = box_path(path, self._root)
        payload = (content or "").encode("utf-8")
        if len(payload) > MAX_WRITE_BYTES:
            return f"error: content is over the {MAX_WRITE_BYTES}-byte write limit"
        outcome = await self._put(op_id, target, payload, "")
        if outcome.killed or outcome.exit_code != 0:
            return _failed(outcome, DEFAULT_WALL_SECONDS, OUTPUT_BYTES)
        return f"wrote {len(payload)} bytes to {target}"

    async def edit(self, op_id: str, path: str, old_text: str, new_text: str) -> str:
        target = box_path(path, self._root)
        if not old_text:
            return "error: old_text is required: the exact passage to replace"
        read = await self._exec.run(
            op_id + "/read", ["/bin/sh", "-c", _CAT, "sh", target],
            wall_seconds=DEFAULT_WALL_SECONDS, output_bytes=MAX_EDIT_BYTES,
        )
        if read.killed == "output_limit":
            return f"error: {target} is over the {MAX_EDIT_BYTES}-byte edit limit; use bash"
        if read.killed or read.exit_code != 0:
            return _failed(read, DEFAULT_WALL_SECONDS, MAX_EDIT_BYTES)
        try:
            current = read.output.decode("utf-8")
        except UnicodeDecodeError:
            return f"error: {target} is not UTF-8 text; use bash"
        found = current.count(old_text)
        if found == 0:
            return f"error: old_text was not found in {target}"
        if found > 1:
            return (f"error: old_text matches {found} places in {target}; include more "
                    "surrounding text so it matches exactly one")
        # Written only if the file still has the bytes just read: a concurrent
        # writer (a bash call, another agent of this command center) wins.
        payload = current.replace(old_text, new_text, 1).encode("utf-8")
        outcome = await self._put(
            op_id + "/write", target, payload, hashlib.sha256(read.output).hexdigest(),
        )
        if outcome.killed or outcome.exit_code != 0:
            return _failed(outcome, DEFAULT_WALL_SECONDS, OUTPUT_BYTES)
        return f"edited {target}"

    async def bash(self, op_id: str, command: str, timeout: float = 0) -> str:
        if not (command or "").strip():
            return "error: a command is required"
        wall = float(timeout) if timeout and float(timeout) > 0 else DEFAULT_WALL_SECONDS
        wall = min(max(wall, 1.0), MAX_BASH_SECONDS)
        # argv, never a command string to the box API: the command is bash's
        # argument, exactly as the tool jail runs it.
        outcome = await self._exec.run(
            op_id, ["/bin/bash", "-c", command], wall_seconds=wall,
        )
        body = _text(outcome.output)
        if body and not body.endswith("\n"):
            body += "\n"
        return body + _trailer(outcome, wall, OUTPUT_BYTES)

    async def call(self, name: str, op_id: str, arguments: Mapping[str, Any]) -> str:
        """Dispatch one validated call; an argument the tool does not take is refused."""
        handler, allowed = {
            "read": (self.read, {"path", "offset", "limit"}),
            "write": (self.write, {"path", "content"}),
            "edit": (self.edit, {"path", "old_text", "new_text"}),
            "bash": (self.bash, {"command", "timeout"}),
        }[name]
        unexpected = set(arguments) - allowed
        if unexpected:
            return f"error: {name} does not take {sorted(unexpected)}"
        try:
            return await handler(op_id, **arguments)
        except (TypeError, ValueError) as exc:
            return f"error: {exc}"


#: The model-facing definitions. Arguments and meaning are the tool jail's
#: (``engine_mcp_server`` ``read``/``write``/``edit``/``bash``); only the root
#: is the box's. ``tests/test_agent_loop_box_tools.py`` pins the parity.
def box_tool_definitions(root: str = BOX_ROOT) -> dict[str, dict[str, Any]]:
    def schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {"type": "object", "properties": properties, "required": required}

    text = {"type": "string"}
    integer = {"type": "integer"}
    return {
        "read": {
            "description": (f"Read a file in your folder {root} (relative paths are under "
                            f"{root}).\noffset: first line (1-based); limit: line count "
                            "(default 2000)."),
            "inputSchema": schema(
                {"path": text, "offset": dict(integer, default=0),
                 "limit": dict(integer, default=0)}, ["path"]),
        },
        "write": {
            "description": f"Create or replace a file in {root}, making parent folders.",
            "inputSchema": schema({"path": text, "content": text}, ["path", "content"]),
        },
        "edit": {
            "description": (f"In a file in {root}, replace old_text (must match exactly "
                            "once) with new_text."),
            "inputSchema": schema({"path": text, "old_text": text, "new_text": text},
                                  ["path", "old_text", "new_text"]),
        },
        "bash": {
            "description": (f"Run a bash command in {root}. Memory, processes and time are "
                            "limited.\ntimeout: seconds (default 120, max 600)."),
            "inputSchema": schema({"command": text, "timeout": dict(integer, default=0)},
                                  ["command"]),
        },
    }
