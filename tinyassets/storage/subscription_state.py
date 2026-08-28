"""Per-universe subscription tier.

Deliberately small: this is the ONLY durable state the billing path needs. Usage
metering is a separate, unlanded change — nothing here counts, limits, or enforces
anything. A universe is `paid` while it has an entitling subscription and `free`
otherwise, and that is the whole model.

Free is the ABSENCE of a subscription rather than a separate plan record, so there
is one less state to drift out of sync with Stripe.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_FILENAME = ".subscription_state.db"

TIER_FREE = "free"
TIER_PAID = "paid"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscription_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_TIER_KEY = "tier"
_EVENT_AT_KEY = "tier_event_at"
_CHECKOUT_CLAIM_KEY = "checkout_claim_at"

#: How long a Checkout Session we create stays completable. Stripe's floor for
#: ``expires_at`` is 30 minutes; the extra minute absorbs clock skew between the
#: anchor we compute it from and Stripe's own validation of it.
CHECKOUT_SESSION_SECONDS = 1860.0

#: How long the claim guarding that session is held. It must be LONGER than the
#: session, because the claim's whole job is to be the only completable checkout.
#:
#: The previous value was 900s with no ``expires_at`` sent at all -- so Stripe applied
#: its 24-hour default and the session outlived its guard by nearly a day. After 15
#: minutes a second session could be created while the first was still completable,
#: and completing both billed one universe twice: exactly the outcome the claim exists
#: to prevent (Codex, 2026-08-28).
CHECKOUT_WINDOW_SECONDS = CHECKOUT_SESSION_SECONDS + 120.0


def state_db_path(universe_dir: str | Path) -> Path:
    return Path(universe_dir) / _DB_FILENAME


def _connect(universe_dir: str | Path) -> sqlite3.Connection:
    path = state_db_path(universe_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def get_tier(universe_dir: str | Path, *, default: str = TIER_FREE) -> str:
    """This universe's tier. Absent, or unreadable, means free.

    Falling back rather than raising is deliberate twice over: a universe with no
    billing record is the ordinary case and must not be an error, and a database we
    cannot read must never silently grant the PAID tier.
    """
    try:
        with _connect(universe_dir) as conn:
            conn.executescript(_SCHEMA)
            row = conn.execute(
                "SELECT value FROM subscription_meta WHERE key = ?", (_TIER_KEY,)
            ).fetchone()
    except sqlite3.Error:
        return default
    return str(row[0]) if row is not None else default


def apply_tier_event(
    universe_dir: str | Path, *, tier: str, event_created: float
) -> bool:
    """Apply a billing event's tier only if it is not older than the last applied.

    Stripe does not guarantee delivery order and retries deliveries, so a delayed
    but validly-signed `active` can arrive after a cancellation. Without ordering it
    would silently hand back a paid tier nobody is paying for. The webhook
    signature's replay window bounds re-delivery of ONE event; it says nothing about
    ordering between different events.

    Stripe timestamps are second-granularity, so ties are ordinary. Ties resolve
    toward DE-ESCALATION — a same-second cancel beats a same-second activate — so
    entitlement is never granted by arrival-order coin flip.

    Returns True when applied, False when ignored.
    """
    if not tier:
        raise ValueError("tier is required")
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT value FROM subscription_meta WHERE key = ?", (_EVENT_AT_KEY,)
            ).fetchone()
            try:
                last = float(row[0]) if row is not None else float("-inf")
            except (TypeError, ValueError):
                last = float("-inf")
            if event_created < last:
                conn.execute("ROLLBACK")
                return False
            if event_created == last:
                current = conn.execute(
                    "SELECT value FROM subscription_meta WHERE key = ?", (_TIER_KEY,)
                ).fetchone()
                if (
                    current is not None
                    and str(current[0]) == TIER_FREE
                    and tier != TIER_FREE
                ):
                    conn.execute("ROLLBACK")
                    return False
            for key, value in ((_TIER_KEY, tier), (_EVENT_AT_KEY, str(event_created))):
                conn.execute(
                    "INSERT INTO subscription_meta (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise


def claim_checkout(
    universe_dir: str | Path,
    *,
    now: float,
    ttl_seconds: float = CHECKOUT_WINDOW_SECONDS,
) -> float | None:
    """Exclusive, expiring claim on starting a checkout for this universe.

    Returns the claim's ANCHOR -- the timestamp it was taken at -- or ``None`` when
    another claim already holds. The anchor identifies this attempt, and both the
    session's expiry and its Stripe idempotency key are derived from it, so a retry
    of the same attempt is deduplicated while a genuinely new attempt is not. Keying
    those on a wall-clock bucket instead made a resubscribe inside the same bucket
    replay the ORIGINAL completed session (Codex, 2026-08-28).

    Asking Stripe whether a subscription exists and then creating a session is
    check-then-act: two concurrent clicks can both see "none" and both create
    sessions that become two subscriptions billing one universe twice. Stripe cannot
    close that for us, because a pending Checkout Session is not yet a subscription,
    so the mutual exclusion lives here.

    The claim expires so an abandoned checkout cannot lock a universe out forever --
    but never BEFORE the session it guards, or the lockout is traded for a second
    completable session.
    """
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT value FROM subscription_meta WHERE key = ?",
                (_CHECKOUT_CLAIM_KEY,),
            ).fetchone()
            if row is not None:
                try:
                    held_since = float(row[0])
                except (TypeError, ValueError):
                    held_since = 0.0
                if now - held_since < ttl_seconds:
                    conn.execute("ROLLBACK")
                    return None
            conn.execute(
                "INSERT INTO subscription_meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_CHECKOUT_CLAIM_KEY, str(now)),
            )
            conn.execute("COMMIT")
            return now
        except Exception:
            conn.execute("ROLLBACK")
            raise


def release_checkout_claim(universe_dir: str | Path) -> None:
    """Drop the claim after a failed start, so a retry is not made to wait."""
    with _connect(universe_dir) as conn:
        conn.executescript(_SCHEMA)
        conn.execute(
            "DELETE FROM subscription_meta WHERE key = ?", (_CHECKOUT_CLAIM_KEY,)
        )
