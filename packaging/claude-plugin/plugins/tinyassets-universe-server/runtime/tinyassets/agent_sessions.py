"""Long-lived agent sessions: one continuing native session per thread or agent node.

Founder, 2026-10-01: the universe agent should keep working like Claude Code,
not start over on every message. Before this, every served turn was a fresh
``--ephemeral`` process that saw a 20-message, 7,000-character text summary of
the conversation and none of its own earlier tool calls or results, and every
background wake rebuilt that same context from scratch (change
``universe-agent-harness``, design §2).

A *session* is keyed by what it continues: the founder's conversation thread
(``thread:<principal>``) or one agent node (``node:<node key>``). An adapter
that can resume declares ``native_resume`` and keeps its native session files
under :func:`native_store`; this module only remembers which native session a
key is on, so the next turn of the same key resumes it and sends just the new
input. No vendor is named here: the handle is opaque to the platform.

Everything lives under the universe's ``.runtime/`` directory, which is absent
from the agent's tool jail, so the agent cannot forge which session it resumes
or what that session contains.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from tinyassets.providers.provider_jail import PLATFORM_RUNTIME_DIR

logger = logging.getLogger(__name__)

#: Where session records and native session files live, inside ``.runtime``.
SESSIONS_DIR = Path(PLATFORM_RUNTIME_DIR) / "agent-sessions"

_ADAPTER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentSessionRef:
    """Which session a turn continues, and what to send if it can.

    ``fresh_prompt_digest`` names the exact prompt the turn was built with; an
    adapter resumes only when the prompt it was handed is still that one, so a
    caller that rewrote the input (a continuation after a capacity retry, for
    instance) never has its rewrite silently replaced. ``resume_prompt`` is what
    a resumed native session receives instead: only what it has not seen.
    ``built_at`` is when the turn read the conversation, recorded so the next
    turn of this key knows which messages arrived after it.
    """

    universe_dir: Path
    key: str
    fresh_prompt_digest: str
    resume_prompt: str = field(repr=False)
    built_at: float = 0.0


def _record_path(universe_dir: Path, key: str) -> Path:
    return Path(universe_dir) / SESSIONS_DIR / f"{digest(key)[:32]}.json"


def native_store(universe_dir: Path, adapter: str) -> Path:
    """The persistent directory an adapter keeps its native session files in."""
    if not _ADAPTER.match(adapter or ""):
        raise ValueError(f"invalid adapter name for a session store: {adapter!r}")
    path = Path(universe_dir) / SESSIONS_DIR / "native" / adapter
    path.mkdir(parents=True, exist_ok=True)
    return path


def load(universe_dir: Path, key: str) -> dict | None:
    """The stored record for ``key``, or ``None`` when there is none or it is unreadable."""
    path = _record_path(universe_dir, key)
    try:
        if path.is_symlink():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.warning("agent session record for %s is unreadable; starting fresh", key)
        return None
    if not isinstance(record, dict) or record.get("key") != key:
        return None
    return record


def save(ref: AgentSessionRef, *, adapter: str, model: str, handle: str, system: str) -> None:
    """Remember that ``ref.key`` now continues native session ``handle``."""
    if not handle:
        return
    path = _record_path(ref.universe_dir, ref.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "version": 1,
        "key": ref.key,
        "adapter": adapter,
        "model": model or "",
        "handle": handle,
        "system_digest": digest(system or ""),
        "consumed_at": ref.built_at or time.time(),
        "updated_at": time.time(),
    }
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, path)


def clear(ref: AgentSessionRef) -> None:
    with contextlib.suppress(FileNotFoundError):
        _record_path(ref.universe_dir, ref.key).unlink()


def consumed_at(universe_dir: Path, key: str) -> float | None:
    """When the session for ``key`` last read the conversation, if it exists."""
    record = load(universe_dir, key)
    if record is None:
        return None
    try:
        return float(record.get("consumed_at"))
    except (TypeError, ValueError):
        return None


def resumable(ref: AgentSessionRef | None, *, adapter: str, model: str,
              prompt: str) -> dict | None:
    """The record to resume for this launch, or ``None`` to start a new session.

    A record resumes only on the same adapter and model it was made on, and only
    when the launch is still sending the prompt the turn was built with.
    """
    if ref is None or digest(prompt) != ref.fresh_prompt_digest:
        return None
    record = load(ref.universe_dir, ref.key)
    if record is None or not record.get("handle"):
        return None
    if record.get("adapter") != adapter or (record.get("model") or "") != (model or ""):
        return None
    return record


def resume_input(ref: AgentSessionRef, record: dict, system: str) -> str:
    """What a resumed session receives: the new input, plus changed instructions."""
    if record.get("system_digest") == digest(system or "") or not system:
        return ref.resume_prompt
    return (
        "My standing instructions have changed since my last turn. They now read:\n"
        "<<< INSTRUCTIONS >>>\n" + system + "\n<<< END INSTRUCTIONS >>>\n\n"
        + ref.resume_prompt
    )


@contextlib.contextmanager
def exclusive(ref: AgentSessionRef | None) -> Iterator[bool]:
    """Hold the session for one launch; yields ``False`` when another launch has it.

    Two processes resuming one native session at once would interleave its
    history, so the second one runs as a fresh, unrecorded session instead.
    """
    if ref is None:
        yield False
        return
    try:
        import fcntl
    except ImportError:  # Windows tray: native sessions are not resumed there.
        yield False
        return
    lock_path = _record_path(ref.universe_dir, ref.key).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logger.info("agent session %s is busy; this turn runs unrecorded", ref.key)
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def unseen(history, since: float | None, *, speakers: frozenset[str] | None = None) -> list:
    """Messages from ``history`` after ``since`` (all of them when ``since`` is None).

    ``speakers`` narrows to those speakers; items are ``conversation_memory.Msg``
    or anything with ``speaker`` and ``ts``.
    """
    out = []
    for item in history or ():
        speaker = getattr(item, "speaker", None)
        ts = getattr(item, "ts", None)
        if isinstance(item, dict):
            speaker, ts = item.get("speaker"), item.get("ts")
        if speakers is not None and speaker not in speakers:
            continue
        try:
            when = float(ts) if ts is not None else None
        except (TypeError, ValueError):
            when = None
        if since is not None and (when is None or when <= since):
            continue
        out.append(item)
    return out
