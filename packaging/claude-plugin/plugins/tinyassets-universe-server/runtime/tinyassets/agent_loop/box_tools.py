"""The four box tools, forwarded to the turn's bound box by ``op_id``.

``read``, ``write``, ``edit`` and ``bash`` are the same four tools as the tool
jail serves today (:mod:`tinyassets.universe_tools`), with the same arguments
and the same text answers. What changes is where they run: each call is one
``start_exec`` on the command center's box through the :class:`BoxProvider`
(target architecture D2), never a process the loop starts itself.

Binding. The session is constructed with a handle the caller bound ONCE at
turn start (``BoxProvider.bind(cc, account=..., turn=...)``). No call looks a
box up by name, so a loop bug cannot route one owner's tool call into another
owner's box; the box host refuses a handle minted for another command center
or turn as well (D2 "Authentication of every operation").

Lost replies. Every call carries an ``op_id`` derived from the journal
position of the call (turn, round, call). D2 makes ``start_exec`` idempotent by
``op_id``: a retry returns the recorded execution and never re-runs it. So a
transport failure is resolved by asking again with the SAME ``op_id``, once,
and anything still unresolved -- including ``unknown_after_restore`` -- is
reported as an UNKNOWN outcome. The coordinator journals it as unknown and the
turn holds. Nothing here retries with a new ``op_id``.

Cancellation. A cancelled turn cancels the execution in the box
(``BoxProvider.cancel``, which kills the process tree there) before the
cancellation propagates.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Protocol

from tinyassets.engine_tool_client import EngineToolError

_LOG = logging.getLogger(__name__)

#: The tool names this module serves, in canonical order.
BOX_TOOLS: tuple[str, ...] = ("read", "write", "edit", "bash")

#: Where the command center's content sits inside its box (D2 default ``cwd``).
BOX_ROOT = "/cc"

_MiB = 1024 * 1024
MAX_WRITE_BYTES = 4 * _MiB
MAX_EDIT_BYTES = 1 * _MiB
DEFAULT_READ_LINES = 2000
DEFAULT_WALL_SECONDS = 120.0
MAX_BASH_SECONDS = 600.0
OUTPUT_BYTES = 64 * 1024
#: How long a cancelled execution may take to report its end before the
#: cancellation propagates anyway (the box host owns the kill).
_CANCEL_GRACE_SECONDS = 5.0


class BoxOperationRefused(RuntimeError):
    """The box host refused an operation BEFORE it existed.

    The one exception a driver may raise to say "nothing ran": a stale
    placement epoch, a handle for another command center, an account that does
    not own it. Anything else a driver raises is a transport failure, whose
    outcome is unknown until the box host says otherwise.
    """


class BoxExec(Protocol):
    """The part of ``BoxProvider`` (D2) the box tools use. Structural, so the
    real provider satisfies it without importing this module."""

    def start_exec(self, h: Any, op_id: str, argv: Sequence[str], *,
                   stdin: Any = None, env: Mapping[str, str] = ..., cwd: str = ...,
                   limits: Any) -> Any: ...

    def stream(self, h: Any, exec_id: Any, *, from_offset: int = 0) -> Iterator[Any]: ...

    def cancel(self, h: Any, exec_id: Any) -> None: ...

    def exec_status(self, h: Any, op_id: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class ExecOutcome:
    """What one execution reported: merged output, exit code, and why it was cut."""

    output: bytes
    exit_code: int | None
    killed: str | None = None


def _unknown() -> EngineToolError:
    return EngineToolError("box_tool_outcome_unknown", outcome="unknown")


def _event_kind(event: Any) -> str:
    return str(getattr(event, "kind", "") or "")


def _event_offset(event: Any, fallback: int) -> int:
    offset = getattr(event, "offset", None)
    return offset if type(offset) is int and offset >= 0 else fallback


class BoxExecutor:
    """Runs argv in ONE bound box by ``op_id``; the only door the tools use."""

    def __init__(self, provider: BoxExec, handle: Any, *, limits: Any,
                 cwd: str = BOX_ROOT) -> None:
        if handle is None:
            raise ValueError("a bound box handle is required")
        self._provider = provider
        self._handle = handle
        self._limits = limits
        self._cwd = cwd

    @property
    def handle(self) -> Any:
        return self._handle

    def _start(self, op_id: str, argv: Sequence[str], stdin: bytes | None) -> Any:
        kwargs: dict[str, Any] = {"cwd": self._cwd, "limits": self._limits}
        if stdin is not None:
            kwargs["stdin"] = stdin
        try:
            return self._provider.start_exec(self._handle, op_id, list(argv), **kwargs)
        except BoxOperationRefused:
            raise
        except Exception:
            # The reply was lost, not necessarily the operation. The same op_id
            # returns the recorded execution and never starts a second one.
            _LOG.warning("box start_exec reply lost; asking again with the same op_id")
            try:
                return self._provider.start_exec(self._handle, op_id, list(argv), **kwargs)
            except BoxOperationRefused:
                # Refused only on the retry: the first attempt may have run.
                raise _unknown() from None
            except Exception:
                raise _unknown() from None

    def _collect(self, exec_id: Any, op_id: str, cap: int, stop: Callable[[], bool]) -> ExecOutcome:
        """Read the execution's events to its end, resuming once by offset."""
        output = bytearray()
        offset = 0
        resumed = False
        while True:
            try:
                for event in self._provider.stream(self._handle, exec_id, from_offset=offset):
                    kind = _event_kind(event)
                    if kind in ("stdout", "stderr"):
                        data = bytes(getattr(event, "data", b"") or b"")
                        offset = _event_offset(event, offset + len(data))
                        room = cap - len(output)
                        output += data[:max(room, 0)]
                        if len(data) > room:
                            self._provider.cancel(self._handle, exec_id)
                            return ExecOutcome(bytes(output), None, "output_limit")
                    elif kind == "exit":
                        code = getattr(event, "code", None)
                        return ExecOutcome(bytes(output), code if type(code) is int else None)
                    if stop():
                        return ExecOutcome(bytes(output), None, "cancelled")
                # A stream that ends without an exit event is a lost reply.
                raise ConnectionError("box stream ended without an exit event")
            except Exception:
                if resumed:
                    break
                resumed = True
                _LOG.warning("box stream interrupted; resuming from offset %d", offset)
        status = None
        try:
            status = self._provider.exec_status(self._handle, op_id)
        except Exception:
            pass
        _LOG.warning("box execution outcome unresolved (status %r)", getattr(status, "state", None))
        raise _unknown()

    async def run(self, op_id: str, argv: Sequence[str], *, stdin: bytes | None = None,
                  wall_seconds: float, output_bytes: int = OUTPUT_BYTES) -> ExecOutcome:
        """One execution; a timeout or a cancelled turn kills it in the box."""
        if not isinstance(op_id, str) or not op_id:
            raise ValueError("an op_id is required")
        exec_id = await asyncio.to_thread(self._start, op_id, argv, stdin)
        stopping = False
        collector = asyncio.ensure_future(asyncio.to_thread(
            self._collect, exec_id, op_id, output_bytes, lambda: stopping,
        ))
        try:
            return await asyncio.wait_for(asyncio.shield(collector), wall_seconds)
        except TimeoutError:
            stopping = True
            await self._cancel(exec_id)
            outcome = await self._drain(collector)
            output = outcome.output if outcome is not None else b""
            return ExecOutcome(output, None, "timeout")
        except asyncio.CancelledError:
            stopping = True
            await self._cancel(exec_id)
            await self._drain(collector)
            raise

    async def _cancel(self, exec_id: Any) -> None:
        try:
            await asyncio.to_thread(self._provider.cancel, self._handle, exec_id)
        except Exception:  # noqa: BLE001 - the cancellation itself still propagates
            _LOG.warning("box cancel failed; the box host owns the execution now")

    async def _drain(self, collector: asyncio.Future) -> ExecOutcome | None:
        try:
            return await asyncio.wait_for(asyncio.shield(collector), _CANCEL_GRACE_SECONDS)
        except BaseException:  # noqa: BLE001 - a stuck reader never blocks the turn's end
            return None


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
#: Temp file plus rename, so a reader never sees half a file. ``$2`` is the
#: sha256 the file must still have (edit), or empty (write).
_WRITE = (
    'if [ -n "$2" ]; then '
    '[ -f "$1" ] && [ "$(sha256sum -- "$1" | cut -d" " -f1)" = "$2" ] '
    '|| { echo "$1 changed while it was being edited; read it again"; exit 3; }; '
    'else mkdir -p -- "$(dirname -- "$1")" || exit 1; fi; '
    't="$1.ta-write.$$"; cat > "$t" && mv -f -- "$t" "$1" || { rm -f -- "$t"; exit 1; }'
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
