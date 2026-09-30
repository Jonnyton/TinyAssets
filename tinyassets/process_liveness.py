"""Proof that a process is alive or dead, from an OS lock the kernel releases.

Every process that owns durable in-flight work -- an automation lease, a run, a
seat -- holds an exclusive OS lock on ``<data>/.consumer_liveness/<token>.lock``
for its whole life. The kernel drops that lock when the process dies, however it
dies, a deploy's SIGKILL included. So "its owner is dead" is a fact another
process can check (the file exists and nobody holds its lock) rather than a guess
from a heartbeat that stopped or a table row that went quiet.

Three answers, never a guess: ``alive``, ``dead`` or ``unknown``. A token with
no file (never registered, or a probe error) is ``unknown``, and ``unknown`` is
never treated as dead.

``owner_token()`` is this process's own token for runs and seats. The automation
consumer keeps its own lease-holder token; one process may hold several.
"""

from __future__ import annotations

import os
import re
import secrets
import threading
from pathlib import Path
from typing import Any

#: Directory under the data root holding one lock file per live owner token.
LIVENESS_DIR = ".consumer_liveness"

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

ALIVE = "alive"
DEAD = "dead"
UNKNOWN = "unknown"


def liveness_path(base_path: str | Path, token: str) -> Path | None:
    """The lock file that proves ``token``'s process is alive, or None.

    None for a token that is not a plain token: such a token can never be
    proven dead, so whatever it holds is honoured until it expires.
    """
    if not _TOKEN_RE.match(token or ""):
        return None
    return Path(base_path) / LIVENESS_DIR / f"{token}.lock"


def hold_liveness(base_path: str | Path, token: str) -> Any:
    """Take ``token``'s liveness lock. Keep the result for the process life.

    Cleanup removes a DEAD token's file, and a fresh registrant's file reads as
    dead between its creation and its lock. So after locking, the registrant
    checks that the path still names the file it locked; if cleanup unlinked
    it meanwhile, it locks a new one. Without this a live process would hold a
    lock on a deleted file, and its runs would be unprovable ("unknown")
    forever once it died (Codex refute 2026-09-30, round 2).
    """
    from tinyassets.singleton_lock import acquire_singleton_lock, release_singleton_lock

    path = liveness_path(base_path, token)
    if path is None:
        raise ValueError(f"liveness token {token!r} is not a plain token")
    for _attempt in range(5):
        held = acquire_singleton_lock(path)
        if not held.acquired or held.fd is None:
            return held
        try:
            same = os.path.samestat(os.fstat(held.fd), os.stat(path))
        except OSError:
            same = False
        if same:
            return held
        release_singleton_lock(held)
    raise RuntimeError(f"could not keep a liveness file for token {token}")


def owner_state(base_path: str | Path, token: str) -> str:
    """``alive``, ``dead`` or ``unknown`` -- read-only, never deletes.

    The file is the proof, and one owner can hold work in many places, so a
    probe that deleted it after reclaiming ONE thing would leave every other
    thing of that dead owner unprovable (Codex round 2, 2026-09-27).
    """
    from tinyassets.singleton_lock import _lock_fd, _unlock_fd

    path = liveness_path(base_path, token)
    if path is None or not path.is_file():
        return UNKNOWN
    try:
        fd = os.open(str(path), os.O_RDWR)
    except OSError:
        return UNKNOWN
    try:
        if not _lock_fd(fd):
            return ALIVE
        _unlock_fd(fd)
        return DEAD
    finally:
        os.close(fd)


# -- This process's owner token -------------------------------------------------

_TOKEN = f"proc_{secrets.token_hex(12)}"
#: The liveness lock held per data root, for the process lifetime.
_HELD: dict[str, Any] = {}
_HELD_LOCK = threading.Lock()


def _reset_after_fork() -> None:
    """A forked child is a different process: its own token, no inherited claim.

    Its copies of the parent's lock descriptors are closed: the lock belongs to
    the open file, so a child keeping a copy would keep a dead parent "alive".
    """
    global _TOKEN, _HELD_LOCK
    _TOKEN = f"proc_{secrets.token_hex(12)}"
    for held in _HELD.values():
        fd = getattr(held, "fd", None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
    _HELD.clear()
    _HELD_LOCK = threading.Lock()


if hasattr(os, "register_at_fork"):  # pragma: no branch - POSIX only
    os.register_at_fork(after_in_child=_reset_after_fork)


def owner_token(base_path: str | Path) -> str:
    """This process's owner token, with its liveness lock held under ``base_path``.

    Taken before the token is first written anywhere, so no row can name an
    owner whose proof does not exist yet. Fails loudly: a run stamped with a
    token nobody can prove would never be recovered.
    """
    key = str(Path(base_path).resolve())
    with _HELD_LOCK:
        if key not in _HELD:
            lock = hold_liveness(base_path, _TOKEN)
            if not getattr(lock, "acquired", False):
                raise RuntimeError(
                    f"could not take the liveness lock for owner token {_TOKEN}"
                )
            _HELD[key] = lock
    return _TOKEN
