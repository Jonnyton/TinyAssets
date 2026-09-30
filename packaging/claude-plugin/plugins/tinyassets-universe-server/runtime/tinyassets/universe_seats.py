"""Account-wide agent seats with interactive priority and a durable FIFO queue.

Workers acquire here, never request handlers that enqueue work. Over capacity
work waits. A blocking child borrows its parent's seat by an exclusive depth
transition; parallel siblings acquire their own. Holder identity and death proof
come from process_liveness under the seat ledger's root. Expiry alone never
reclaims a living or unprovable holder. A worker future owns release even when
its caller times out.
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)
_current_seat: ContextVar = ContextVar("account_seat", default=None)

LEDGER_NAME = ".account_seats.db"

CLASS_INTERACTIVE = "interactive"
CLASS_BACKGROUND = "background"
SEAT_CLASSES = (CLASS_INTERACTIVE, CLASS_BACKGROUND)

#: What kind of agent call holds the seat. Owner-facing only -- the ceiling depends
#: on the CLASS, never on the kind, so adding a kind cannot change who waits.
KIND_CHAT_TURN = "chat_turn"
KIND_AGENT_NODE = "agent_node"
KIND_AUTOMATION = "automation"
KIND_WAKE = "wake"
KIND_APP_EVENT = "app_event"

#: How long a seat survives its holder's silence. Deliberately far shorter than a
#: run's own timeout (`automations.DEFAULT_RUN_TIMEOUT_SECONDS`, 10800): a DEAD
#: holder's seat should strand capacity for two minutes, not three hours. A LIVE
#: long run keeps its seat indefinitely, because the refresher keeps stamping it --
#: "a served turn runs until it is finished" is not weakened by a short lease, only
#: by a missing refresher.
SEAT_LEASE_SECONDS = 120.0
#: Re-stamp cadence. A quarter of the lease, so two consecutive missed refreshes
#: still do not expire a live seat.
SEAT_REFRESH_SECONDS = 30.0
#: A waiter's own liveness lease. Longer than a seat's, because a waiter may sit for
#: as long as the work ahead of it takes and losing its position would be the drop
#: this module promises never to do.
WAITER_LEASE_SECONDS = 900.0
#: How long a bounded acquire waits before giving up. Used by callers whose work
#: is durable elsewhere and can be picked up on the next tick -- an automation
#: pump, a wake. NOT used by a chat turn, which waits until it is served
#: (`wait_s=None`); see `hold`.
SEAT_WAIT_SECONDS = 20.0
#: How often a caller that is waiting re-publishes its waiting state, so the
#: owner's "(N running)" count does not go stale while they watch it.
WAITING_NOTICE_SECONDS = 5.0
#: Poll cadence while blocking. Cheap next to an agent call measured in seconds.
_POLL_SECONDS = 0.1

def _holder(root: Path) -> str:
    from tinyassets.process_liveness import owner_token

    return owner_token(root)


class SeatLedgerUnusable(RuntimeError):
    """The seat store is tampered or unreadable.

    Raised, not swallowed. A seat store that cannot be trusted is a cross-universe
    concurrency escape -- admitting work without a seat because the ledger is a
    symlink is exactly the evasion the check exists to stop, and Hard Rule 8 says
    fail loudly rather than pretend.
    """


@dataclass(frozen=True)
class Seat:
    """A held seat. ``reentrant`` means it re-entered a parent's seat rather than
    taking a second one, so releasing it only decrements a depth."""

    seat_id: str
    account_id: str
    seat_class: str
    kind: str
    reentrant: bool = False
    depth: int = 1


@dataclass(frozen=True)
class Waiting:
    """No seat yet, and the queue position that guarantees one. Never a refusal:
    the caller's work still runs, once ``ticket`` reaches the front."""

    ticket: int
    account_id: str
    seat_class: str
    running: int
    waiting: int
    seats: int


def ledger_path() -> Path:
    """The seat store under the daemon's resolved data root.

    `tinyassets.storage.data_dir` -- `TINYASSETS_DATA_DIR` first, absolute, never
    the CWD (the configuration invariant in AGENTS.md).
    """
    from tinyassets.storage import data_dir

    return data_dir() / LEDGER_NAME


def _trusted(db: Path) -> bool:
    """Whether the store sits inside its data dir and is not a symlink.

    Same rule as `engine_admissions._ledger_is_trusted`, and for a sharper reason
    here: a seat store an attacker can redirect is a seat store whose counts they
    choose. A check that cannot complete is NOT trust -- it raises.
    """
    try:
        if db.is_symlink():
            return False
        root = os.path.realpath(db.parent)
        real = os.path.realpath(db)
        return real == root or real.startswith(root + os.sep)
    except OSError as exc:
        raise SeatLedgerUnusable(f"seat store could not be checked: {exc}") from exc


_SCHEMA = """
CREATE TABLE IF NOT EXISTS universe_seats (
    seat_id      TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL,
    seat_class   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    holder       TEXT NOT NULL,
    depth        INTEGER NOT NULL DEFAULT 1,
    acquired_at  REAL NOT NULL,
    expires_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS universe_seats_universe
    ON universe_seats(account_id, expires_at);

-- `ticket` is AUTOINCREMENT so "longest-owed" is an integer comparison: two
-- waiters enqueued in the same millisecond still have a total order, which a
-- float timestamp cannot promise. `enqueued_at` is kept for the owner-facing
-- "waiting since", never for ordering.
CREATE TABLE IF NOT EXISTS seat_waiters (
    ticket       INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  TEXT NOT NULL,
    seat_class   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    holder       TEXT NOT NULL,
    enqueued_at  REAL NOT NULL,
    expires_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS seat_waiters_universe
    ON seat_waiters(account_id, seat_class, ticket);
"""


def _connect(db: Path | None) -> sqlite3.Connection:
    db = db or ledger_path()
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # A data dir that does not exist yet must not mean "no limit".
        raise SeatLedgerUnusable(f"seat store parent unusable: {exc}") from exc
    if not _trusted(db):
        raise SeatLedgerUnusable(f"seat store is not inside its data dir: {db}")
    try:
        conn = sqlite3.connect(str(db), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn
    except sqlite3.Error as exc:
        raise SeatLedgerUnusable(f"seat store could not be opened: {exc}") from exc


@contextmanager
def _txn(db: Path | None):
    """One `BEGIN IMMEDIATE` per operation.

    The lock comes FIRST, so schema creation happens under it: two first touches
    used to both pass before either had created the tables
    (`engine_admissions`' round-1 P0, and `workspace_pool` repeats the note).
    """
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    except BaseException:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def _reap(conn: sqlite3.Connection, now: float, root: Path) -> None:
    """Reclaim only proven-dead holders; silence and missing proof are unknown."""
    expired = conn.execute(
        "SELECT seat_id, holder FROM universe_seats"
    ).fetchall()
    from tinyassets.process_liveness import DEAD, owner_state

    for row in expired:
        if owner_state(root, str(row["holder"])) != DEAD:
            continue
        conn.execute("DELETE FROM universe_seats WHERE seat_id = ?", (row["seat_id"],))
    # A waiter is a QUEUE POSITION, never work. Its expiry cannot lose work,
    # because the work it is waiting for is durable elsewhere (see `acquire`).
    conn.execute("DELETE FROM seat_waiters WHERE expires_at < ?", (now,))


def _running(
    conn: sqlite3.Connection, account_id: str, seat_class: str | None = None
) -> int:
    """Seats this account holds, optionally of one class only.

    Keyed on `account_id` alone -- no query here aggregates across universes,
    which is what keeps one universe's occupancy from consuming or revealing
    another's.
    """
    if seat_class is None:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM universe_seats WHERE account_id = ?",
                (account_id,),
            ).fetchone()[0]
        )
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM universe_seats "
            "WHERE account_id = ? AND seat_class = ?",
            (account_id, seat_class),
        ).fetchone()[0]
    )


def _admits(
    conn: sqlite3.Connection,
    account_id: str,
    seat_class: str,
    *,
    seats: int,
    reserve: int,
) -> bool:
    """Whether capacity exists for one more seat of ``seat_class``.

    TWO predicates, and the difference is the whole meaning of a reserve
    (astra round 1, finding 6 -- a real bug in the first draft):

        total_live < seats                        always
        background_live < seats - reserve         background only

    The first draft compared TOTAL live against `seats - reserve` for background
    work. With 3 seats, 1 reserved and two INTERACTIVE holders, that refused
    background work while a seat sat free and no background work was running at
    all -- the reserve was protecting interactive work from itself. A reserve
    bounds the class it constrains, not the total.
    """
    if _running(conn, account_id) >= seats:
        return False
    if seat_class == CLASS_INTERACTIVE:
        return True
    return _running(conn, account_id, CLASS_BACKGROUND) < max(1, seats - reserve)


def _ahead_of(
    conn: sqlite3.Connection, account_id: str, seat_class: str, ticket: int | None
) -> int:
    """How many waiters are entitled to a seat before this caller.

    This is the fairness rule as a query, and it is the reason the queue is a queue:
    a caller that finds a seat free while someone is already owed one joins BEHIND
    them rather than taking it.

    An interactive waiter is counted ahead of everyone; a background waiter is
    counted ahead only of other background waiters. So an interactive caller is
    never behind a background one whatever the tickets say.

    ``ticket`` None means "not enqueued yet", which must count every live waiter as
    ahead -- otherwise a fresh arrival would tie with the front of the queue.
    """
    mine = ticket if ticket is not None else None
    if seat_class == CLASS_INTERACTIVE:
        if mine is None:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM seat_waiters "
                    "WHERE account_id = ? AND seat_class = ?",
                    (account_id, CLASS_INTERACTIVE),
                ).fetchone()[0]
            )
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters "
                "WHERE account_id = ? AND seat_class = ? AND ticket < ?",
                (account_id, CLASS_INTERACTIVE, mine),
            ).fetchone()[0]
        )
    # Background: every interactive waiter, plus earlier background waiters.
    interactive = int(
        conn.execute(
            "SELECT COUNT(*) FROM seat_waiters "
            "WHERE account_id = ? AND seat_class = ?",
            (account_id, CLASS_INTERACTIVE),
        ).fetchone()[0]
    )
    if mine is None:
        background = int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters "
                "WHERE account_id = ? AND seat_class = ?",
                (account_id, CLASS_BACKGROUND),
            ).fetchone()[0]
        )
    else:
        background = int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters "
                "WHERE account_id = ? AND seat_class = ? AND ticket < ?",
                (account_id, CLASS_BACKGROUND, mine),
            ).fetchone()[0]
        )
    return interactive + background


def _reenter(
    conn: sqlite3.Connection,
    account_id: str,
    parent_seat_id: str,
    now: float,
    lease_s: float,
    holder: str,
    parent_depth: int = 1,
) -> bool:
    """Increment a parent seat's depth, if this caller may re-enter it.

    A blocking nested agent call is not a second concurrent model call: its parent
    is BLOCKED waiting for it. Charging two seats would mean a 2-seat account cannot
    run a 2-deep agent chain at all -- the deadlock
    `provider_admission._NESTED_RESERVE` was added to fix one layer down.

    Both the universe AND the holder must match. Universe alone would let one
    universe name another's seat and ride it (the cross-user theft case); holder
    alone would let a sibling universe in the same process do the same. A seat id is
    not a capability, so it is never trusted on its own.

    **Exclusive transfer, not reference counting** (astra round 1, finding 4). The
    `depth = 1` predicate is what makes it exclusive: a seat may be lent to ONE
    nested call at a time. A blocked parent lending its seat is sound because the
    parent is not executing; a parent lending the same seat to three PARALLEL child
    agent nodes would put three model calls on one seat, which is the bound failing
    silently. A sibling that finds the seat already lent takes its own, and waits
    for it like any other caller -- correct, because it really is concurrent work.
    """
    updated = conn.execute(
        "UPDATE universe_seats SET depth = depth + 1, expires_at = ? "
        "WHERE seat_id = ? AND account_id = ? AND holder = ? AND depth = ?",
        (now + lease_s, parent_seat_id, account_id, holder, parent_depth),
    )
    return updated.rowcount == 1


def acquire(
    account_id: str,
    *,
    seat_class: str = CLASS_BACKGROUND,
    kind: str = KIND_AGENT_NODE,
    run_id: str = "",
    ticket: int | None = None,
    parent_seat_id: str | None = None,
    parent_depth: int = 1,
    seats: int | None = None,
    reserve: int | None = None,
    db: Path | None = None,
    now: float | None = None,
    lease_s: float = SEAT_LEASE_SECONDS,
) -> Seat | Waiting:
    """Take a seat for ``account_id``, or join the queue.

    Returns a :class:`Seat` when held, or :class:`Waiting` carrying the queue
    position. NEVER refuses for want of a seat. ``ticket`` re-presents a position
    already held, so a polling caller keeps it rather than going to the back.

    One `BEGIN IMMEDIATE` transaction does all of it -- reap, re-entry, count,
    ceiling, queue position, insert -- so two concurrent acquisitions cannot both
    see the last seat free.
    """
    account_id = (account_id or "").strip()
    if not account_id:
        raise ValueError("a seat needs an account_id")
    if seat_class not in SEAT_CLASSES:
        raise ValueError(f"seat class must be one of {SEAT_CLASSES}, not {seat_class!r}")
    moment = time.time() if now is None else now
    if seats is None or reserve is None:
        limits = _limits(account_id, root=(db or ledger_path()).parent)
        seats = limits.seats if seats is None else seats
        reserve = limits.interactive_reserve if reserve is None else reserve
    total = max(1, int(seats))
    held_back = min(max(0, int(reserve)), total - 1)

    root = (db or ledger_path()).parent
    # Before the transaction: the lock is a filesystem operation, and taking it
    # inside `BEGIN IMMEDIATE` would hold the write lock across it.
    _holder(root)
    with _txn(db) as conn:
        _reap(conn, moment, root)
        if parent_seat_id and _reenter(
            conn, account_id, parent_seat_id, moment, lease_s, _holder(root), parent_depth
        ):
            if ticket is not None:
                conn.execute("DELETE FROM seat_waiters WHERE ticket = ?", (ticket,))
            return Seat(
                seat_id=parent_seat_id,
                account_id=account_id,
                seat_class=seat_class,
                kind=kind,
                reentrant=True,
                depth=parent_depth + 1,
            )
        running = _running(conn, account_id)
        ahead = _ahead_of(conn, account_id, seat_class, ticket)
        if _admits(conn, account_id, seat_class, seats=total, reserve=held_back) and (
            ahead == 0
        ):
            seat_id = secrets.token_hex(12)
            conn.execute(
                "INSERT INTO universe_seats (seat_id, account_id, seat_class, kind, "
                "run_id, holder, depth, acquired_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    seat_id, account_id, seat_class, kind, run_id, _holder(root),
                    moment, moment + lease_s,
                ),
            )
            if ticket is not None:
                conn.execute("DELETE FROM seat_waiters WHERE ticket = ?", (ticket,))
            return Seat(
                seat_id=seat_id,
                account_id=account_id,
                seat_class=seat_class,
                kind=kind,
            )
        # No seat: keep or take a queue position. Refreshing an existing ticket
        # rather than inserting a new one is what stops a polling caller from
        # walking to the back of its own queue every 100 ms.
        if ticket is not None:
            kept = conn.execute(
                "UPDATE seat_waiters SET expires_at = ? WHERE ticket = ?",
                (moment + WAITER_LEASE_SECONDS, ticket),
            )
            if kept.rowcount != 1:
                ticket = None
        if ticket is None:
            cur = conn.execute(
                "INSERT INTO seat_waiters (account_id, seat_class, kind, run_id, "
                "holder, enqueued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    account_id, seat_class, kind, run_id, _holder((db or ledger_path()).parent),
                    moment, moment + WAITER_LEASE_SECONDS,
                ),
            )
            ticket = int(cur.lastrowid or 0)
        waiting = int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters WHERE account_id = ?",
                (account_id,),
            ).fetchone()[0]
        )
        return Waiting(
            ticket=ticket,
            account_id=account_id,
            seat_class=seat_class,
            running=running,
            waiting=waiting,
            seats=total,
        )


def account_for_universe(universe_id: str, *, root: Path | None = None) -> str:
    """Resolve the owning account from durable admin ownership, never the caller."""
    from tinyassets.storage import data_dir, db_path

    base = root if root is not None else data_dir()
    from contextlib import closing

    with closing(sqlite3.connect(db_path(base).as_uri() + "?mode=ro", uri=True)) as conn:
        rows = conn.execute(
            "SELECT actor_id, granted_by FROM universe_acl WHERE universe_id = ? "
            "AND permission = 'admin'", (universe_id,),
        ).fetchall()
        has_bindings = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_bindings'",
        ).fetchone()
        serving = conn.execute(
            "SELECT DISTINCT created_by FROM agent_bindings WHERE universe_id = ? "
            "AND status = 'serving'", (universe_id,),
        ).fetchall() if has_bindings else []
        home = conn.execute(
            "SELECT founder_sub FROM founder_home WHERE universe_id = ?", (universe_id,),
        ).fetchall()
    candidates = {row[0] for row in rows}
    founders = {row[0] for row in home}
    if not founders:
        founders = {row[0] for row in serving}
    if not founders:
        founders = {actor for actor, grantor in rows if actor == grantor}
    if not founders and len(candidates) == 1:
        founders = candidates
    if len(founders) != 1 or not next(iter(founders)):
        raise SeatLedgerUnusable("universe needs one unambiguous owning account")
    return str(next(iter(founders)))


def holder_is_named(root: Path, holder: str) -> bool:
    """Keep death proof until all seats naming it have been reclaimed."""
    from contextlib import closing

    db = root / LEDGER_NAME
    if not db.exists():
        return False
    with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
        return conn.execute(
            "SELECT 1 FROM universe_seats WHERE holder = ? LIMIT 1", (holder,),
        ).fetchone() is not None


def _limits(account_id: str, *, root=None):
    from tinyassets.usage_policy import limits_for_account

    return limits_for_account(account_id, root=root)



def refresh(seat_id: str, *, db: Path | None = None, now: float | None = None) -> bool:
    """Re-stamp a held seat's lease. False when there was no such seat to stamp --
    which means it was already reaped, and the caller should stop, not carry on
    holding capacity it no longer owns."""
    seat_id = (seat_id or "").strip()
    if not seat_id:
        return False
    moment = time.time() if now is None else now
    with _txn(db) as conn:
        cur = conn.execute(
            "UPDATE universe_seats SET expires_at = ? WHERE seat_id = ? AND holder = ?",
            (moment + SEAT_LEASE_SECONDS, seat_id, _holder((db or ledger_path()).parent)),
        )
        return cur.rowcount == 1


def release(seat_id: str, *, db: Path | None = None) -> bool:
    """Give a seat back. Decrements depth for a re-entered seat; deletes at zero.

    Called from a `finally`, so it must never raise on an already-gone seat: a
    reaped seat is exactly the case where the caller is unwinding.
    """
    seat_id = (seat_id or "").strip()
    if not seat_id:
        return False
    try:
        with _txn(db) as conn:
            row = conn.execute(
                "SELECT depth FROM universe_seats WHERE seat_id = ?", (seat_id,)
            ).fetchone()
            if row is None:
                return False
            if int(row["depth"]) > 1:
                conn.execute(
                    "UPDATE universe_seats SET depth = depth - 1 WHERE seat_id = ?",
                    (seat_id,),
                )
                return True
            conn.execute("DELETE FROM universe_seats WHERE seat_id = ?", (seat_id,))
            with _held_lock:
                _held.pop(seat_id, None)
            return True
    except SeatLedgerUnusable:
        # Unwinding is the wrong moment to raise about the store. The lease is the
        # backstop that makes this survivable, which is why it exists.
        _log.warning("seat %s could not be released; its lease will reap it", seat_id)
        return False


def abandon(ticket: int | None, *, db: Path | None = None) -> bool:
    """Give up a queue position. For a caller that decided not to run after all --
    never for one that is still waiting, which would be the drop this module
    promises not to do."""
    if ticket is None:
        return False
    try:
        with _txn(db) as conn:
            cur = conn.execute("DELETE FROM seat_waiters WHERE ticket = ?", (int(ticket),))
            return cur.rowcount == 1
    except SeatLedgerUnusable:
        return False


def occupancy(
    account_id: str,
    *,
    db: Path | None = None,
    now: float | None = None,
    seats: int | None = None,
) -> dict[str, object]:
    """What the owner is shown: seats total, running, waiting, and the ceiling
    background work may reach. Read-only, and it reaps nothing -- an observation
    must not change what it observes."""
    account_id = (account_id or "").strip()
    limits = None
    if seats is None:
        limits = _limits(account_id, root=(db or ledger_path()).parent)
        seats = limits.seats
    moment = time.time() if now is None else now
    out: dict[str, object] = {
        "seats": int(seats),
        "running": 0,
        "waiting": 0,
        "background_seats": limits.background_seats if limits else int(seats),
    }
    if not account_id:
        return out
    db = db or ledger_path()
    if not db.exists():
        return out
    from contextlib import closing

    try:
        if not _trusted(db):
            raise SeatLedgerUnusable("untrusted seat ledger")
        with closing(sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)) as conn:
            out["running"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM universe_seats "
                    "WHERE account_id = ?",
                    (account_id,),
                ).fetchone()[0]
            )
            out["waiting"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM seat_waiters "
                    "WHERE account_id = ? AND expires_at >= ?",
                    (account_id, moment),
                ).fetchone()[0]
            )
            out["interactive_waiting"] = int(conn.execute(
                "SELECT COUNT(*) FROM seat_waiters WHERE account_id = ? "
                "AND seat_class = ? AND expires_at >= ?",
                (account_id, CLASS_INTERACTIVE, moment),
            ).fetchone()[0])
    except (SeatLedgerUnusable, sqlite3.Error, OSError):
        out["availability"] = "unavailable"
    return out


def waiting_message(
    account_id: str,
    *,
    running: int,
    tier: str | None = None,
) -> str:
    """The one line an owner sees while work waits.

    "Waiting for a free seat (2 running). Upgrade for more seats." -- an inline
    clickable link, never a banner, button, card or modal (founder, 2026-09-30).
    Empty upgrade half on the top tier, so the caller concatenates unconditionally.
    """
    from tinyassets.usage_policy import upgrade_sentence

    if tier is None:
        tier = _limits(account_id).name
    head = f"Waiting for a free seat ({int(running)} running)"
    tail = upgrade_sentence(tier, what="seats")
    return f"{head} \u2014 {tail}" if tail else head



# --------------------------------------------------------------------------- #
# The refresher: one thread for every seat this process holds
# --------------------------------------------------------------------------- #
# Deliberately NOT started on import. A periodic thread that starts itself
# pollutes a monkeypatched global in whatever test happens to run next, and unit
# tests here drive `now` explicitly and never need it. `hold` starts it; tests
# that use `hold` stop it.
_held_lock = threading.Lock()
_held: dict[str, Path | None] = {}
_refresher: threading.Thread | None = None
_refresher_stop = threading.Event()


def _refresh_loop() -> None:
    while not _refresher_stop.wait(SEAT_REFRESH_SECONDS):
        with _held_lock:
            current = dict(_held)
        if not current:
            continue
        for seat_id, db in current.items():
            try:
                if not refresh(seat_id, db=db):
                    # Already reaped. Stop stamping it; the holder will find out
                    # when it releases. Keeping it in the map would re-create a
                    # seat row the ledger has deliberately forgotten.
                    with _held_lock:
                        _held.pop(seat_id, None)
            except SeatLedgerUnusable:
                _log.warning("seat refresh failed for %s", seat_id)


def _start_refresher() -> None:
    global _refresher
    with _held_lock:
        if _refresher is not None and _refresher.is_alive():
            return
        _refresher_stop.clear()
        _refresher = threading.Thread(
            target=_refresh_loop, name="universe-seat-refresh", daemon=True
        )
        _refresher.start()


def stop_refresher() -> None:
    """Stop the refresh thread and forget what it was stamping. For tests and for
    tests; release or proven process death still ends held seats."""
    global _refresher
    _refresher_stop.set()
    thread = _refresher
    if thread is not None:
        thread.join(timeout=2.0)
    with _held_lock:
        _refresher = None
        _held.clear()


def acquire_blocking(
    account_id: str,
    *,
    seat_class: str = CLASS_BACKGROUND,
    kind: str = KIND_AGENT_NODE,
    run_id: str = "",
    parent_seat_id: str | None = None,
    parent_depth: int = 1,
    wait_s: float | None = SEAT_WAIT_SECONDS,
    on_waiting: object | None = None,
    seats: int | None = None,
    reserve: int | None = None,
    db: Path | None = None,
) -> Seat | Waiting:
    """`acquire`, but WAIT for a seat rather than returning a queue position.

    The wait loop, shared by `hold` and by call sites whose surrounding
    `try`/`finally` is already explicit (the agent node's, which wraps a
    hundred lines this must not re-indent). A held seat is registered with the
    refresher here, so the caller only has to release it.

    Returns a :class:`Seat`, or a :class:`Waiting` if a BOUNDED ``wait_s``
    elapsed. ``wait_s=None`` waits until served.
    """
    deadline = None if wait_s is None else time.monotonic() + max(0.0, wait_s)
    ticket: int | None = None
    notified_at: float | None = None

    def _notify(state: Waiting) -> None:
        nonlocal notified_at
        if on_waiting is None or not callable(on_waiting):
            return
        now_m = time.monotonic()
        if notified_at is not None and now_m - notified_at < WAITING_NOTICE_SECONDS:
            return
        notified_at = now_m
        try:
            on_waiting(state)
        except Exception:
            # A notice that fails must not lose the seat the caller is owed.
            _log.warning("waiting notice failed for %s", account_id, exc_info=True)

    outcome: Seat | Waiting = acquire(
        account_id,
        seat_class=seat_class,
        kind=kind,
        run_id=run_id,
        parent_seat_id=parent_seat_id,
        parent_depth=parent_depth,
        seats=seats,
        reserve=reserve,
        db=db,
    )
    while isinstance(outcome, Waiting) and (
        deadline is None or time.monotonic() < deadline
    ):
        ticket = outcome.ticket
        _notify(outcome)
        time.sleep(_POLL_SECONDS)
        # Re-presenting the ticket both keeps the queue position AND refreshes
        # the waiter's lease, so an unbounded wait cannot age out of its own
        # queue while it is still waiting.
        outcome = acquire(
            account_id,
            seat_class=seat_class,
            kind=kind,
            run_id=run_id,
            ticket=ticket,
            parent_seat_id=parent_seat_id,
        parent_depth=parent_depth,
            seats=seats,
            reserve=reserve,
            db=db,
        )
    if isinstance(outcome, Seat) and not outcome.reentrant:
        # A re-entered seat is its parent's: the parent's refresher already
        # stamps it, and registering it twice would have two owners racing to
        # drop it.
        with _held_lock:
            _held[outcome.seat_id] = db
        _start_refresher()
    return outcome


@contextmanager
def hold(
    account_id: str,
    *,
    seat_class: str = CLASS_BACKGROUND,
    kind: str = KIND_AGENT_NODE,
    run_id: str = "",
    parent_seat_id: str | None = None,
    parent_depth: int = 1,
    wait_s: float | None = SEAT_WAIT_SECONDS,
    on_waiting: object | None = None,
    seats: int | None = None,
    reserve: int | None = None,
    db: Path | None = None,
):
    """Hold a seat for the body, waiting for one.

    ``wait_s=None`` waits until served. That is what an INTERACTIVE chat turn
    passes, and it is the directive's own contract: work *"is never refused and
    never dropped"*, so a turn that has queued must not bounce back to the user
    after 20 seconds -- a bounce reads as a refusal however it is worded. The wait
    is bounded in practice by the interactive reserve: an interactive turn only
    ever waits behind ANOTHER interactive turn, never behind background work.

    A float ``wait_s`` gives up after that long, and is for callers whose work is
    durable elsewhere and will be retried on the next tick -- an automation pump,
    a wake. Giving up there costs nothing, because the row is still due.

    ``on_waiting`` is called with the :class:`Waiting` as soon as the caller
    starts waiting and every `WAITING_NOTICE_SECONDS` after, so the owner sees
    "Waiting for a free seat (N running)" with a live count instead of a silent
    hang. It must not raise; it is a notification, not a step.

    Yields a :class:`Seat` when held, or a :class:`Waiting` if a BOUNDED wait
    elapsed. Check `isinstance(x, Seat)`.

    ``seats`` / ``reserve`` override the tier lookup. Production callers leave
    them None so the account's own tier decides; they exist so a test can drive
    the real wait loop against a chosen seat algebra instead of reimplementing it.

    Released on every exit path including exceptions -- success, failure,
    cancellation and timeout. A crash is covered by the lease, the only path a
    `finally` cannot reach.
    """
    outcome = acquire_blocking(
        account_id,
        seat_class=seat_class,
        kind=kind,
        run_id=run_id,
        parent_seat_id=parent_seat_id,
        parent_depth=parent_depth,
        wait_s=wait_s,
        on_waiting=on_waiting,
        seats=seats,
        reserve=reserve,
        db=db,
    )
    if isinstance(outcome, Waiting):
        # A BOUNDED wait elapsed. Hand it back WITHOUT abandoning the ticket:
        # the position is the promise that the work runs.
        yield outcome
        return
    token = _current_seat.set(outcome)
    try:
        yield outcome
    finally:
        _current_seat.reset(token)
        with _held_lock:
            _held.pop(outcome.seat_id, None)
        release(outcome.seat_id, db=db)


__all__ = [
    "CLASS_BACKGROUND",
    "CLASS_INTERACTIVE",
    "KIND_AGENT_NODE",
    "KIND_APP_EVENT",
    "KIND_AUTOMATION",
    "KIND_CHAT_TURN",
    "KIND_WAKE",
    "SEAT_CLASSES",
    "SEAT_LEASE_SECONDS",
    "SEAT_REFRESH_SECONDS",
    "SEAT_WAIT_SECONDS",
    "WAITING_NOTICE_SECONDS",
    "WAITER_LEASE_SECONDS",
    "Seat",
    "SeatLedgerUnusable",
    "Waiting",
    "abandon",
    "acquire",
    "acquire_blocking",
    "hold",
    "ledger_path",
    "occupancy",
    "refresh",
    "release",
    "stop_refresher",
    "waiting_message",
]


@contextmanager
def worker_seat(universe_id, *, root, kind=KIND_AGENT_NODE, interactive=False):
    """Executor scope. An in-process blocking child borrows exclusively."""
    account = account_for_universe(universe_id, root=Path(root))
    parent = _current_seat.get()
    with hold(
        account, db=Path(root) / LEDGER_NAME, wait_s=None, kind=kind,
        seat_class=CLASS_INTERACTIVE if interactive else CLASS_BACKGROUND,
        parent_seat_id=parent.seat_id if parent else None,
        parent_depth=parent.depth if parent else 1,
    ) as seat:
        yield seat
