"""Per-universe usage ledger: effects, compute-minutes, storage.

One ledger, three dimensions (design decision 5). A universe's answer to "what did
I use" must come from a single place; three subsystems with their own stores multiply
the failure modes and cannot be reconciled.

**Effects are reserved, not counted.** Counting completed effects would put the cap
*after* an irreversible outbound write — an accounting record, not a control. So the
lifecycle mirrors the receipt lifecycle that already exists next door in
``external_write_receipts``:

    reserve  -> before the write; refuses here when the budget is exhausted
    release  -> the write failed; the slot returns and the attempt cost nothing
    commit   -> the write succeeded; the slot is spent

``commit`` is **transition-sensitive**: it moves ``reserved -> committed`` and reports
whether it actually moved anything. A commit against an already-committed row changes
no rows and returns False, so a replayed finalization cannot double-charge. This
matters because the receipt layer is state-idempotent but not accounting-idempotent —
``finalize_receipt`` returns True when replayed against an already-succeeded row
(Codex ADAPT 2026-08-28 C), so "it returned True" is not a licence to increment.

Compute settles idempotently on ``run_id`` for the same reason.
"""

from __future__ import annotations

import sqlite3
import time as _time
from pathlib import Path

_DB_FILENAME = ".usage_ledger.db"

#: Effect reservation states. A row exists from reservation until it is either
#: released (deleted) or committed. Both states occupy budget — an in-flight effect
#: must hold its slot, or concurrent effects could each pass a check that the other
#: is about to invalidate.
STATE_RESERVED = "reserved"
STATE_COMMITTED = "committed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS effect_reservations (
    settlement_key TEXT PRIMARY KEY,
    state          TEXT NOT NULL,
    reserved_at    REAL NOT NULL,
    settled_at     REAL
);

CREATE INDEX IF NOT EXISTS idx_effect_reserved_at
    ON effect_reservations(reserved_at);

CREATE TABLE IF NOT EXISTS usage_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compute_settlements (
    run_id     TEXT PRIMARY KEY,
    seconds    REAL NOT NULL,
    settled_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compute_settled_at
    ON compute_settlements(settled_at);
"""


def usage_ledger_path(universe_dir: str | Path) -> Path:
    """Resolve the per-universe usage ledger path."""
    return Path(universe_dir) / _DB_FILENAME


def _connect(universe_dir: str | Path) -> sqlite3.Connection:
    path = usage_ledger_path(universe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None so BEGIN IMMEDIATE is ours to place explicitly: the
    # count-then-insert in reserve_effect must be one transaction or two callers
    # can both pass a full cap (the TOCTOU that _engine_run_admit already closes).
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize_usage_ledger(universe_dir: str | Path) -> Path:
    """Create the ledger if absent; return its path. Safe to call repeatedly."""
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
    return usage_ledger_path(universe_dir)


def _effects_in_window(conn: sqlite3.Connection, cutoff: float) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM effect_reservations WHERE reserved_at >= ?",
        (cutoff,),
    ).fetchone()
    return int(row[0])


def reserve_effect(
    universe_dir: str | Path,
    *,
    settlement_key: str,
    limit: int,
    window_seconds: float,
    now: float | None = None,
) -> bool:
    """Reserve one effect slot, or refuse when the rolling budget is exhausted.

    ``settlement_key`` identifies the effect (the receipt's identity). Re-reserving
    an existing key is a replay of the *same* effect and succeeds without consuming a
    second slot — otherwise a retried outbound write would be charged twice.

    Returns True when the effect may proceed. Refusal is a real pre-flight control:
    the caller must not perform the outbound write.
    """
    if not settlement_key:
        raise ValueError("settlement_key is required")
    stamp = _time.time() if now is None else now
    cutoff = stamp - window_seconds
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                "SELECT state FROM effect_reservations WHERE settlement_key = ?",
                (settlement_key,),
            ).fetchone()
            if existing is not None:
                # Same effect, already holding (or having spent) its slot.
                conn.execute("COMMIT")
                return True
            if _effects_in_window(conn, cutoff) >= limit:
                conn.execute("ROLLBACK")
                return False
            conn.execute(
                "INSERT INTO effect_reservations "
                "(settlement_key, state, reserved_at) VALUES (?, ?, ?)",
                (settlement_key, STATE_RESERVED, stamp),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise


def release_effect(universe_dir: str | Path, *, settlement_key: str) -> bool:
    """Return a reserved slot after a failed write. Returns True if one was held.

    Only a *reserved* slot releases. A committed effect has already reached the
    world and cannot be un-spent.
    """
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        cur = conn.execute(
            "DELETE FROM effect_reservations "
            "WHERE settlement_key = ? AND state = ?",
            (settlement_key, STATE_RESERVED),
        )
        return cur.rowcount > 0


def commit_effect(
    universe_dir: str | Path,
    *,
    settlement_key: str,
    now: float | None = None,
) -> bool:
    """Settle a reserved slot as spent. True only on an actual transition.

    Returns False when the row is already committed — the guard against
    double-charging a replayed finalization. Callers must treat False as
    "already settled", never as "settle again".
    """
    stamp = _time.time() if now is None else now
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        cur = conn.execute(
            "UPDATE effect_reservations SET state = ?, settled_at = ? "
            "WHERE settlement_key = ? AND state = ?",
            (STATE_COMMITTED, stamp, settlement_key, STATE_RESERVED),
        )
        return cur.rowcount > 0


def settle_compute(
    universe_dir: str | Path,
    *,
    run_id: str,
    seconds: float,
    max_chargeable_seconds: float,
    now: float | None = None,
) -> bool:
    """Record a run's worker-held duration. Idempotent on ``run_id``.

    ``seconds`` is clamped to ``max_chargeable_seconds`` so an abandoned or wedged
    run cannot accrue without bound, and negative input is floored at zero. Returns
    True only when this call recorded the run — a repeat returns False.
    """
    if not run_id:
        raise ValueError("run_id is required")
    charged = max(0.0, min(float(seconds), float(max_chargeable_seconds)))
    stamp = _time.time() if now is None else now
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        cur = conn.execute(
            "INSERT OR IGNORE INTO compute_settlements "
            "(run_id, seconds, settled_at) VALUES (?, ?, ?)",
            (run_id, charged, stamp),
        )
        return cur.rowcount > 0


def usage_summary(
    universe_dir: str | Path,
    *,
    window_seconds: float,
    now: float | None = None,
) -> dict[str, float]:
    """Return this universe's usage over the rolling window.

    ``effects`` counts both reserved and committed slots, because an in-flight
    effect is holding budget. ``effects_committed`` is the billable figure.
    """
    stamp = _time.time() if now is None else now
    cutoff = stamp - window_seconds
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        held = _effects_in_window(conn, cutoff)
        committed = int(
            conn.execute(
                "SELECT COUNT(*) FROM effect_reservations "
                "WHERE reserved_at >= ? AND state = ?",
                (cutoff, STATE_COMMITTED),
            ).fetchone()[0]
        )
        compute = conn.execute(
            "SELECT COALESCE(SUM(seconds), 0.0) FROM compute_settlements "
            "WHERE settled_at >= ?",
            (cutoff,),
        ).fetchone()[0]
    return {
        "effects": float(held),
        "effects_committed": float(committed),
        "compute_seconds": float(compute),
    }


def prune_before(universe_dir: str | Path, *, cutoff: float) -> int:
    """Drop settled rows older than ``cutoff``; return how many were removed.

    Reserved rows are never pruned — an in-flight effect keeps its slot however
    long it takes, or a slow write would silently free budget it still holds.
    """
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        removed = conn.execute(
            "DELETE FROM effect_reservations "
            "WHERE reserved_at < ? AND state = ?",
            (cutoff, STATE_COMMITTED),
        ).rowcount
        removed += conn.execute(
            "DELETE FROM compute_settlements WHERE settled_at < ?",
            (cutoff,),
        ).rowcount
        return removed


_TIER_KEY = "tier"


def get_tier(universe_dir: str | Path, *, default: str = "free") -> str:
    """Read this universe's tier. Absent means the free tier.

    Deliberately falls back rather than raising: a universe with no billing record
    is a free universe, which is the common case and must not be an error.
    """
    try:
        with _connect(universe_dir) as conn:
            conn.executescript(_SCHEMA)
            row = conn.execute(
                "SELECT value FROM usage_meta WHERE key = ?", (_TIER_KEY,)
            ).fetchone()
    except sqlite3.Error:
        # A ledger we cannot read must not silently grant the paid tier.
        return default
    return str(row[0]) if row is not None else default


def set_tier(universe_dir: str | Path, *, tier: str) -> None:
    """Record this universe's tier. Written by the billing adapter only."""
    if not tier:
        raise ValueError("tier is required")
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO usage_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_TIER_KEY, tier),
        )


_TIER_EVENT_AT_KEY = "tier_event_at"


def apply_tier_event(
    universe_dir: str | Path, *, tier: str, event_created: float
) -> bool:
    """Apply a billing event's tier only if it is NEWER than the last applied.

    Stripe does not guarantee delivery order, and a retried delivery can arrive
    long after the event it describes. Without this, a delayed-but-validly-signed
    ``active`` event silently overwrites a newer cancellation and hands back a paid
    tier nobody is paying for (Codex REJECT 2026-08-28 C). The 5-minute signature
    tolerance bounds replay of the *same* event; it says nothing about ordering
    between different ones.

    Returns True when applied, False when ignored as stale.
    """
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT value FROM usage_meta WHERE key = ?", (_TIER_EVENT_AT_KEY,)
            ).fetchone()
            last = float(row[0]) if row is not None else float("-inf")
            if event_created < last:
                conn.execute("ROLLBACK")
                return False
            conn.execute(
                "INSERT INTO usage_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_TIER_KEY, tier),
            )
            conn.execute(
                "INSERT INTO usage_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_TIER_EVENT_AT_KEY, str(event_created)),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise
