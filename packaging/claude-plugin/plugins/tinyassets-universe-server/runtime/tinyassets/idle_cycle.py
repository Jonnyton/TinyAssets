"""Idle-cycle single-flight — dedupe no-claim heartbeats across local daemons.

Why this exists (root-caused live 2026-07-14): multiple daemon processes can
run the per-universe idle heartbeat tail when the dispatcher claims nothing.
Task claims were file-locked at the time of the incident (the JSON claim path
is now retired in favor of SQLite ``LeaseStore``), but the idle cycle was not,
so N healthy
daemons produced N duplicate cycles — observed as exact duplicate
``activity.log`` pairs every ~5min, 0–2s apart.

Mechanism — two layers, one lock file (Codex adversarial review 2026-07-14
required the first):

* **Run lock (mutual exclusion for the cycle's lifetime).** Acquisition
  takes a NONBLOCKING exclusive OS lock on ``.idle_cycle.lock`` and the
  winner HOLDS it until the cycle finishes (``IdleCycleSlot.release()``,
  wired into the daemon's ``_cleanup``) or the process dies (the OS
  releases file locks on process death — crash-safe, no heartbeat
  machinery needed). A cycle that runs longer than the freshness window —
  real writing cycles can take 6+ minutes — therefore still excludes other
  workers for its whole duration.
* **Stamp (rate limit between cycles).** Under the run lock, a stamp file
  records which worker last STARTED an idle cycle and when. A worker that
  wins the run lock still skips when a DIFFERENT worker's stamp is fresh.
  Own stamps never block, so a single-worker deployment (local tray, solo
  droplet) keeps exactly its current cadence — this module only removes
  multi-worker overlap. If the stamp holder dies mid-gap, any other worker
  acquires as soon as the stamp ages past the window, so the heartbeat
  fails over within one window.

Coordination failures fail OPEN (run the cycle): the worst case is the
status quo (duplicate idle cycles), never a stalled heartbeat. Lock
CONTENTION is not a failure — it is the signal that a cycle is already
running, and reads as skip.

Env controls
------------
``TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT``
    Default on. ``0`` / ``false`` / ``off`` / ``no`` disables the gate
    (escape hatch; N-worker duplicate cycles return).
``TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S``
    Freshness window in seconds (default 240; must be a finite positive
    number — anything else falls back to the default). Keep it below the
    supervisor's idle respawn period (~322s at the backoff ceiling) so a
    healthy fleet never starves its own heartbeat, and above the worker
    phase offset (~1s) so duplicates are caught. Also the maximum
    heartbeat gap after a stamp-holder death.

Worker identity resolves ``TINYASSETS_WORKER_ID`` (compose fleet) >
``UNIVERSE_SERVER_HOST_USER`` (tray/cloud identity) > ``"host"``. Two
unnamed daemons on the same machine therefore share an identity for the
stamp layer and do not rate-limit each other — acceptable: the run lock
still prevents them overlapping, the shipped fleets set distinct worker
ids, and the failure mode is the status quo, never a stalled heartbeat.

Stdlib only.
"""

from __future__ import annotations

import errno
import json
import logging
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

STAMP_FILENAME = ".idle_cycle_stamp.json"
LOCK_FILENAME = ".idle_cycle.lock"
DEFAULT_FOREIGN_FRESH_S = 240.0

_FALSY = {"0", "false", "off", "no"}

# errno values that mean "another holder has the lock" (a legitimate skip),
# as opposed to an I/O failure (fail open). Windows msvcrt LK_NBLCK raises
# EACCES on contention; POSIX flock LOCK_NB raises EWOULDBLOCK/EAGAIN
# (BlockingIOError). EDEADLK covers msvcrt's deadlock-detection variant.
_CONTENTION_ERRNOS = {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EDEADLK}


def single_flight_enabled() -> bool:
    """Default-on gate with an env escape hatch."""
    raw = os.environ.get("TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT", "").strip().lower()
    return raw not in _FALSY


def foreign_fresh_window_s() -> float:
    """Freshness window; only finite positive values are accepted
    (``inf`` would let a foreign stamp block forever, ``nan`` would
    silently disable the comparison — Codex review 2026-07-14)."""
    raw = os.environ.get("TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S", "").strip()
    if not raw:
        return DEFAULT_FOREIGN_FRESH_S
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "idle_cycle: invalid TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S=%r; "
            "using default %.0fs", raw, DEFAULT_FOREIGN_FRESH_S,
        )
        return DEFAULT_FOREIGN_FRESH_S
    if not math.isfinite(value) or value <= 0:
        logger.warning(
            "idle_cycle: TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S=%r is not a "
            "finite positive number; using default %.0fs",
            raw, DEFAULT_FOREIGN_FRESH_S,
        )
        return DEFAULT_FOREIGN_FRESH_S
    return value


def resolve_worker_identity() -> str:
    """Stable identity for stamp ownership.

    ``TINYASSETS_WORKER_ID`` (fleet workers get distinct ids from compose) >
    ``UNIVERSE_SERVER_HOST_USER`` (tray/cloud identity) > ``"host"``.
    """
    for var in ("TINYASSETS_WORKER_ID", "UNIVERSE_SERVER_HOST_USER"):
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return "host"


@dataclass
class IdleCycleSlot:
    """Result of ``try_acquire_idle_cycle_slot``.

    When ``acquired`` is True the slot HOLDS the run lock: keep the object
    alive for the duration of the idle cycle and call ``release()`` when
    the cycle ends (the daemon wires this into ``_cleanup``). Process death
    releases the OS lock automatically, so a crashed holder never wedges
    the heartbeat. ``release()`` is idempotent.
    """

    acquired: bool
    reason: str
    _fd: int | None = field(default=None, repr=False)

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass  # closing the fd below releases the lock regardless
        finally:
            os.close(fd)


def _try_lock_nonblocking(lock_file: Path) -> tuple[int | None, str]:
    """Attempt a nonblocking exclusive lock. Returns ``(fd, "")`` on
    success, ``(None, reason)`` on contention. Raises OSError only for
    genuine I/O failures (caller fails open)."""
    fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if exc.errno in _CONTENTION_ERRNOS:
                    os.close(fd)
                    return None, "run lock held (idle cycle already running)"
                raise
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in _CONTENTION_ERRNOS:
                    os.close(fd)
                    return None, "run lock held (idle cycle already running)"
                raise
    except OSError:
        os.close(fd)
        raise
    return fd, ""


def _read_stamp(stamp_path: Path) -> dict | None:
    """Parse the stamp; any corruption reads as absent (fail open —
    worst case is one duplicate idle cycle, never a stalled heartbeat)."""
    try:
        raw = stamp_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    worker_id = data.get("worker_id")
    started_at = data.get("started_at")
    if not isinstance(worker_id, str) or not isinstance(started_at, (int, float)):
        return None
    if not math.isfinite(float(started_at)):
        return None
    return {"worker_id": worker_id, "started_at": float(started_at)}


def try_acquire_idle_cycle_slot(
    universe_path: Path | str,
    *,
    worker_id: str | None = None,
    foreign_fresh_s: float | None = None,
    now_fn=time.time,
) -> IdleCycleSlot:
    """Try to win the idle-cycle slot for *universe_path*.

    Skip (``acquired=False``) when EITHER another holder is mid-cycle (run
    lock contention — covers cycles longer than the freshness window) OR a
    different worker's stamp is fresh (rate limit between cycles). On
    acquisition the stamp is rewritten and the run lock is HELD — keep the
    returned slot alive for the cycle and ``release()`` it when done.

    Never raises for coordination failures: I/O errors fail OPEN
    (``acquired=True`` with no held lock) so a broken lock/stamp file can
    degrade to the status quo (duplicate cycles), never to a stalled
    heartbeat.
    """
    universe_path = Path(universe_path)
    me = (worker_id or resolve_worker_identity()).strip() or "host"
    window = foreign_fresh_s if foreign_fresh_s is not None else foreign_fresh_window_s()
    stamp_path = universe_path / STAMP_FILENAME

    try:
        universe_path.mkdir(parents=True, exist_ok=True)
        fd, contention_reason = _try_lock_nonblocking(universe_path / LOCK_FILENAME)
        if fd is None:
            return IdleCycleSlot(False, f"{contention_reason}; skipping as {me!r}")
    except OSError as exc:
        logger.warning(
            "idle_cycle: run-lock coordination failed (%s); failing open", exc,
        )
        return IdleCycleSlot(
            True, f"failing open as {me!r}: run-lock error ({exc})",
        )

    # Run lock held from here. The stamp is only ever written under it, so
    # no separate stamp lock is needed.
    try:
        now = float(now_fn())
        stamp = _read_stamp(stamp_path)
        if stamp is not None and stamp["worker_id"] != me:
            age = now - stamp["started_at"]
            # A stamp from the far future (clock skew / corruption) must
            # not block forever: only |age| within the window is fresh.
            if -window < age < window:
                reason = (
                    f"worker {stamp['worker_id']!r} started an idle cycle "
                    f"{age:.1f}s ago (< {window:.0f}s window); "
                    f"skipping as {me!r}"
                )
                slot = IdleCycleSlot(False, reason, _fd=fd)
                slot.release()
                return slot
        payload = json.dumps(
            {"worker_id": me, "started_at": now}, ensure_ascii=True,
        )
        tmp_path = stamp_path.with_suffix(".json.tmp")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, stamp_path)
        prior = (
            "no prior stamp" if stamp is None
            else f"prior stamp {stamp['worker_id']!r} "
                 f"age {now - stamp['started_at']:.1f}s"
        )
        return IdleCycleSlot(True, f"acquired as {me!r} ({prior})", _fd=fd)
    except OSError as exc:
        # Stamp I/O failed while holding the lock: fail open but keep the
        # run lock held for the cycle — mutual exclusion still works even
        # when the rate-limit stamp cannot be written.
        logger.warning(
            "idle_cycle: stamp write failed (%s); failing open with run "
            "lock held", exc,
        )
        return IdleCycleSlot(
            True, f"failing open as {me!r}: stamp error ({exc})", _fd=fd,
        )
