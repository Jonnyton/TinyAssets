"""Idle-cycle single-flight — dedupe the no-claim heartbeat across workers.

Why this exists (root-caused live 2026-07-14): every healthy cloud worker
supervises a ``fantasy_daemon`` subprocess that, when the dispatcher claims
nothing, runs the per-universe idle heartbeat tail (soul-loop driver or the
fantasy universe cycle). Task claims are file-locked
(``branch_tasks.claim_task``) but the idle cycle was not, so N healthy
workers produced N duplicate cycles — observed as exact duplicate
``activity.log`` pairs every ~5min, 0–2s apart, from ``worker-claude-1`` /
``worker-claude-2`` (both settled at the supervisor backoff ceiling with a
~1s phase offset from simultaneous compose-up).

Mechanism: a per-universe stamp file records which worker last STARTED an
idle cycle and when, guarded by a sidecar file lock (same msvcrt/fcntl
pattern as ``branch_tasks._file_lock``). A worker skips its idle cycle only
when a DIFFERENT worker's stamp is fresh. Own stamps never block, so a
single-worker deployment (local tray, solo droplet) keeps exactly its
current cadence — this module only removes multi-worker overlap. If the
stamp holder dies, any other worker acquires the slot as soon as the stamp
ages past the freshness window, so the heartbeat fails over within one
window.

Env controls
------------
``TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT``
    Default on. ``0`` / ``false`` / ``off`` / ``no`` disables the gate
    (escape hatch; N-worker duplicate cycles return).
``TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S``
    Freshness window in seconds (default 240). Must sit below the
    supervisor's idle respawn period (~322s at the backoff ceiling) so a
    healthy solo worker is never blocked by its own predecessor's foreign
    takeover, and above the worker phase offset (~1s) so duplicates are
    caught. Also the maximum heartbeat gap after a stamp-holder death.

Worker identity resolves ``TINYASSETS_WORKER_ID`` (compose fleet) >
``UNIVERSE_SERVER_HOST_USER`` (tray/cloud identity) > ``"host"``. Two
unnamed daemons on the same machine therefore share an identity and do not
dedupe each other — acceptable: the shipped fleets set distinct worker ids,
and the failure mode is the status quo (duplicate idle cycles), never a
stalled heartbeat.

Stdlib only.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

STAMP_FILENAME = ".idle_cycle_stamp.json"
LOCK_FILENAME = ".idle_cycle_stamp.lock"
DEFAULT_FOREIGN_FRESH_S = 240.0

_FALSY = {"0", "false", "off", "no"}


def single_flight_enabled() -> bool:
    """Default-on gate with an env escape hatch."""
    raw = os.environ.get("TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT", "").strip().lower()
    return raw not in _FALSY


def foreign_fresh_window_s() -> float:
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
    if value <= 0:
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


@contextmanager
def _stamp_lock(universe_path: Path) -> Iterator[None]:
    """Blocking exclusive lock on the stamp's own sidecar lock file.

    Deliberately NOT ``branch_tasks._file_lock`` — that sidecar serializes
    the (busy) claim path; the idle stamp gets its own file so heartbeat
    coordination never contends with task claims.
    """
    universe_path.mkdir(parents=True, exist_ok=True)
    lock_file = universe_path / LOCK_FILENAME
    fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if sys.platform == "win32":
            import msvcrt
            # LK_LOCK blocks up to ~10s per call then raises — loop until
            # acquired (critical section is a tiny JSON read/write).
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    continue
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


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
    return {"worker_id": worker_id, "started_at": float(started_at)}


def try_acquire_idle_cycle_slot(
    universe_path: Path | str,
    *,
    worker_id: str | None = None,
    foreign_fresh_s: float | None = None,
    now_fn=time.time,
) -> tuple[bool, str]:
    """Atomically check-and-set the idle-cycle stamp for *universe_path*.

    Returns ``(acquired, reason)``. On acquisition the stamp is rewritten
    to ``{worker_id, started_at=now}`` under the sidecar lock. Skip
    (``acquired=False``) happens ONLY when a different worker's stamp is
    fresh; the caller should clean-exit without running the idle cycle.

    Never raises for coordination failures: lock/stamp I/O errors fail
    OPEN (acquired=True) so a broken stamp file can degrade to the status
    quo (duplicate cycles), never to a stalled heartbeat.
    """
    universe_path = Path(universe_path)
    me = (worker_id or resolve_worker_identity()).strip() or "host"
    window = foreign_fresh_s if foreign_fresh_s is not None else foreign_fresh_window_s()
    stamp_path = universe_path / STAMP_FILENAME

    try:
        with _stamp_lock(universe_path):
            now = float(now_fn())
            stamp = _read_stamp(stamp_path)
            if stamp is not None and stamp["worker_id"] != me:
                age = now - stamp["started_at"]
                # A stamp from the far future (clock skew / corruption)
                # must not block forever: only |age| within the window
                # counts as fresh.
                if -window < age < window:
                    return False, (
                        f"worker {stamp['worker_id']!r} started an idle "
                        f"cycle {age:.1f}s ago (< {window:.0f}s window); "
                        f"skipping as {me!r}"
                    )
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
            return True, f"acquired as {me!r} ({prior})"
    except OSError as exc:
        logger.warning(
            "idle_cycle: stamp coordination failed (%s); failing open", exc,
        )
        return True, f"failing open as {me!r}: stamp coordination error ({exc})"
