"""Seats: how many agent calls one universe runs at once, and who waits.

Founder directive 2026-09-30: *"how many agent calls thier universe can
simoltaniously run ... a user could not prompt infinate agents at once without some
pending waiting on a avalable seat."*

**Pending, not refused.** That word is the whole contract. A user who starts four
agents on a three-seat account has not done anything wrong -- they asked for more
than fits at once -- so the extra work QUEUES and starts when a seat frees. Nothing
here ever refuses for want of a seat, and nothing here ever drops work.

A seat is one in-flight AGENT CALL: a `converse` chat turn, an agent node, an
automation run, an `event` / `once` / `app_event` wake. Not one provider attempt --
one agent call makes several (fallback chain, judge ensemble, retry), so charging at
`providers/router.py`'s existing slot would mean "3 seats" did not mean "3 agents".

Three layers, none of them duplicating another:

    universe seats        HERE      per-universe, tier-sized, QUEUES
      provider_admission  existing  host-wide, memory-sized, REFUSES
        _SYNC_CALL_MAX_WORKERS = 8  thread pool

`provider_admission` is a MEMORY bound derived from measured RSS on a 2 GB box; it
would exist with one user. Seats are a PRODUCT bound from the account tier; they
would exist on an infinite box. A universe can be seat-full with provider slots free,
and provider slots can be exhausted with seats free.

And one layer below in scope, not above: the per-agent lease
(`automations.universe_leases`) answers *"is THIS agent already running?"*. Seats
answer *"may ANY of this universe's agents start?"*. A due automation resolves its
own overlap policy FIRST and only then asks for a seat, so a `skip`-policy run never
occupies a queue position it will abandon.

Why SQLite leases and not a semaphore
-------------------------------------
1. Engine MCP runs as a CHILD PROCESS. `automations.py` already records what an
   in-memory map cost there: "a restarted process (empty map) could launch work an
   OLD process is still doing".
2. A deploy RECREATES THE CONTAINER. An in-memory count restarts at zero while
   provider subprocesses may still be dying.
3. A process that CRASHES without unwinding leaks a seat forever. An expiry cannot.

So: rows with an absolute `expires_at`, refreshed while the work is live, and reaped
by the next acquisition. Reaping is on the acquisition path rather than a timer --
after a deploy, the first acquisition is exactly when stale rows must be gone, and a
timer is one more thing that can be dead at that moment.

Fairness
--------
Background work occupies at most `seats - interactive_reserve`. The reserved seat is
a HARD guarantee that a runaway ping-pong of background wakes cannot make the owner's
chat wait: a priority ordering alone bounds the chat's wait by the longest background
run, which is `DEFAULT_RUN_TIMEOUT_SECONDS` (3 hours) by design. Within a class,
order is by a monotone ticket, so the longest-owed starts first.

What this module does NOT promise, stated because two of them read like promises
-----------------------------------------------------------------------------
* **Eventual background service.** Interactive work has absolute priority, so
  continuous interactive demand can defer background work indefinitely. The
  guarantee is one-directional by design: the owner's chat never waits on their
  automations. There is no aging, and background progress is conditional on
  interactive demand subsiding (astra round 1, finding 7). A universe's own chat
  starving its own automations is the owner's own doing, and it stops when they
  stop typing.
* **A durable queue for synchronous callers.** A waiter row is a QUEUE POSITION,
  not a work record (astra round 1, finding 3). Background work -- automations,
  wakes, agent nodes -- is already durable in its own tables, so waiting only
  delays it and nothing is dropped. A `converse` chat turn is a synchronous
  request: if it cannot get a seat it is TOLD so, and the caller retries. This
  module must not be read as promising to replay it later, because it does not
  store it.

Where the seat is taken, which is not where it is asked for
----------------------------------------------------------
The seat belongs to the code that EXECUTES the agent call, never to the code that
enqueues it (astra round 1, finding 2). `runs.py`'s `start_run` submits a worker and
returns `queued` immediately, and `graph_compiler` deliberately leaves an
already-started worker running after a node timeout. A seat held around either of
those releases while the work is still going. So: acquire inside the node executor
and the run worker, not in the API handler that started them.

`parent_seat_id` is passed EXPLICITLY, in-process only. It is deliberately not
carried on `ProviderInvocationCarrier`: that object is immutable, non-serializable
and process-bound, so it cannot transport a seat across the engine-MCP process
boundary (astra round 1, finding 5). A nested call in another process takes its own
seat, which is the safe direction. Inheritance is also keyed on the parent actually
being SUSPENDED, not on invocation depth -- a by-version invoke defaults to blocking
and waits, so depth alone answers the wrong question.
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_log = logging.getLogger(__name__)

LEDGER_NAME = ".universe_seats.db"

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
#: How long a blocking acquire waits before handing back a visible waiting state
#: instead of continuing to block. Matches `provider_admission`'s own judgement:
#: long enough to ride out a brief burst, short enough that a queued user gets an
#: answer rather than a hang.
SEAT_WAIT_SECONDS = 20.0
#: Poll cadence while blocking. Cheap next to an agent call measured in seconds.
_POLL_SECONDS = 0.1

#: This process's holder token. Identity for re-entrancy and for the refresher,
#: AND the key of the liveness lock that makes "this holder is still running" a
#: fact rather than a guess. Regenerated after a fork so a child cannot refresh
#: or re-enter its parent's seats.
#:
#: The shape is load-bearing: it must satisfy `automations._HOLDER_RE`
#: (``^[A-Za-z0-9_-]{1,128}$``), so `_` and not `:`. The first draft used
#: ``f"{pid}:{hex}"``, which the regex rejects -- `holder_liveness_path` then
#: returned None, every probe answered "unknown", and `holder_is_provably_alive`
#: could never be true. The liveness guard in `_reap` was dead code, and the test
#: that was supposed to catch that had monkeypatched the predicate it was testing.
#: A separator choice silently disabled a safety check.
_BOOT = secrets.token_hex(8)


def _holder() -> str:
    return f"seat{os.getpid()}_{_BOOT}"


def _reset_holder_after_fork() -> None:
    global _BOOT, _liveness_handle
    _BOOT = secrets.token_hex(8)
    # The parent's lock handle is not ours: the fd is inherited but the token it
    # proves belongs to the parent. Drop it so the child registers its own.
    _liveness_handle = None


if hasattr(os, "register_at_fork"):  # POSIX only; a no-op elsewhere
    os.register_at_fork(after_in_child=_reset_holder_after_fork)

#: The OS lock proving this process is alive. Held for the process lifetime --
#: the kernel drops it however the process dies, SIGKILL from a deploy included,
#: which is what lets another process distinguish "crashed" from "busy".
_liveness_handle: object | None = None
_liveness_root: Path | None = None


def _register_liveness(root: Path) -> None:
    """Take this process's liveness lock beside ``root``, once.

    Lazy rather than at import: a module import must not create files, and a
    reader that never acquires a seat has nothing to prove. Registered on the
    acquisition path, which is the only path where it can matter.

    Never raises into an acquisition. A process that cannot register is simply
    not provably alive, so its expired seats get reclaimed on the lease -- the
    previous behaviour, and a strictly safe direction to fail in.
    """
    global _liveness_handle, _liveness_root
    if _liveness_handle is not None and _liveness_root == root:
        return
    try:
        from tinyassets.automations import hold_process_liveness

        _liveness_handle = hold_process_liveness(root, _holder())
        _liveness_root = root
    except Exception:
        _log.warning(
            "seat liveness lock unavailable; this process's seats will be "
            "reclaimed on their lease rather than held while it runs",
            exc_info=True,
        )


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
    universe_id: str
    seat_class: str
    kind: str
    reentrant: bool = False


@dataclass(frozen=True)
class Waiting:
    """No seat yet, and the queue position that guarantees one. Never a refusal:
    the caller's work still runs, once ``ticket`` reaches the front."""

    ticket: int
    universe_id: str
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
    universe_id  TEXT NOT NULL,
    seat_class   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    holder       TEXT NOT NULL,
    depth        INTEGER NOT NULL DEFAULT 1,
    acquired_at  REAL NOT NULL,
    expires_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS universe_seats_universe
    ON universe_seats(universe_id, expires_at);

-- `ticket` is AUTOINCREMENT so "longest-owed" is an integer comparison: two
-- waiters enqueued in the same millisecond still have a total order, which a
-- float timestamp cannot promise. `enqueued_at` is kept for the owner-facing
-- "waiting since", never for ordering.
CREATE TABLE IF NOT EXISTS seat_waiters (
    ticket       INTEGER PRIMARY KEY AUTOINCREMENT,
    universe_id  TEXT NOT NULL,
    seat_class   TEXT NOT NULL,
    kind         TEXT NOT NULL,
    run_id       TEXT NOT NULL DEFAULT '',
    holder       TEXT NOT NULL,
    enqueued_at  REAL NOT NULL,
    expires_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS seat_waiters_universe
    ON seat_waiters(universe_id, seat_class, ticket);
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
    """Reclaim expired seats and waiters whose holders are not provably alive.

    Called at the top of EVERY acquisition, not on a timer: after a deploy the
    first acquisition is exactly when the previous process's rows have to be gone.

    **Expiry is not unconditional reclamation.** Unconditional deletion admits a
    replacement while the original holder is still calling a provider: kill the
    refresher thread, leave its provider running, wait out the lease, and two agent
    calls execute on one seat (astra round 1, finding 1). `automations._lease_blocks`
    already refuses to do this, and for the same reason -- "a live holder that missed
    its refreshes may still be calling a provider".

    So an expired seat is reclaimed only when its holder is NOT provably alive.
    Provably alive means the holder still holds its OS liveness lock, which the
    kernel drops however the process dies, SIGKILL from a deploy included. A holder
    with no liveness file is not proven alive and is reclaimed -- the lease is the
    bound for a process that never registered, and refusing to ever reclaim those
    would strand capacity permanently.
    """
    expired = conn.execute(
        "SELECT seat_id, holder FROM universe_seats WHERE expires_at < ?", (now,)
    ).fetchall()
    for row in expired:
        if _holder_is_alive(str(row["holder"]), root):
            continue
        conn.execute("DELETE FROM universe_seats WHERE seat_id = ?", (row["seat_id"],))
    # A waiter is a QUEUE POSITION, never work. Its expiry cannot lose work,
    # because the work it is waiting for is durable elsewhere (see `acquire`).
    conn.execute("DELETE FROM seat_waiters WHERE expires_at < ?", (now,))


def _holder_is_alive(holder: str, root: Path) -> bool:
    """Whether ``holder``'s process provably still exists.

    Delegates to the consumer-liveness proof `automations` already maintains: a
    file per holder, OS-locked for the process lifetime. Never a guess -- an
    unknown holder, a missing file or a probe error all answer False, so this can
    only ever DELAY reclamation of a seat whose owner is demonstrably running.

    ``root`` is the SEAT STORE's own directory, not the global data dir. The proof
    has to live beside the ledger it is vouching for: reading it from
    `data_dir()` while reaping a ledger somewhere else consults the wrong
    process's evidence, and would make every test with an explicit ``db`` silently
    unable to see a live holder.
    """
    if holder == _holder():
        # Our own seats. This process is alive by construction, and this answer
        # must not depend on whether the liveness lock registered.
        return True
    try:
        from tinyassets.automations import holder_is_provably_alive

        return bool(holder_is_provably_alive(root, holder))
    except Exception:
        return False


def _running(
    conn: sqlite3.Connection, universe_id: str, seat_class: str | None = None
) -> int:
    """Seats this universe holds, optionally of one class only.

    Keyed on `universe_id` alone -- no query here aggregates across universes,
    which is what keeps one universe's occupancy from consuming or revealing
    another's.
    """
    if seat_class is None:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM universe_seats WHERE universe_id = ?",
                (universe_id,),
            ).fetchone()[0]
        )
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM universe_seats "
            "WHERE universe_id = ? AND seat_class = ?",
            (universe_id, seat_class),
        ).fetchone()[0]
    )


def _admits(
    conn: sqlite3.Connection,
    universe_id: str,
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
    if _running(conn, universe_id) >= seats:
        return False
    if seat_class == CLASS_INTERACTIVE:
        return True
    return _running(conn, universe_id, CLASS_BACKGROUND) < max(1, seats - reserve)


def _ahead_of(
    conn: sqlite3.Connection, universe_id: str, seat_class: str, ticket: int | None
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
                    "WHERE universe_id = ? AND seat_class = ?",
                    (universe_id, CLASS_INTERACTIVE),
                ).fetchone()[0]
            )
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters "
                "WHERE universe_id = ? AND seat_class = ? AND ticket < ?",
                (universe_id, CLASS_INTERACTIVE, mine),
            ).fetchone()[0]
        )
    # Background: every interactive waiter, plus earlier background waiters.
    interactive = int(
        conn.execute(
            "SELECT COUNT(*) FROM seat_waiters "
            "WHERE universe_id = ? AND seat_class = ?",
            (universe_id, CLASS_INTERACTIVE),
        ).fetchone()[0]
    )
    if mine is None:
        background = int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters "
                "WHERE universe_id = ? AND seat_class = ?",
                (universe_id, CLASS_BACKGROUND),
            ).fetchone()[0]
        )
    else:
        background = int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters "
                "WHERE universe_id = ? AND seat_class = ? AND ticket < ?",
                (universe_id, CLASS_BACKGROUND, mine),
            ).fetchone()[0]
        )
    return interactive + background


def _reenter(
    conn: sqlite3.Connection,
    universe_id: str,
    parent_seat_id: str,
    now: float,
    lease_s: float,
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
        "UPDATE universe_seats SET depth = 2, expires_at = ? "
        "WHERE seat_id = ? AND universe_id = ? AND holder = ? AND depth = 1",
        (now + lease_s, parent_seat_id, universe_id, _holder()),
    )
    return updated.rowcount == 1


def acquire(
    universe_id: str,
    *,
    seat_class: str = CLASS_BACKGROUND,
    kind: str = KIND_AGENT_NODE,
    run_id: str = "",
    ticket: int | None = None,
    parent_seat_id: str | None = None,
    seats: int | None = None,
    reserve: int | None = None,
    db: Path | None = None,
    now: float | None = None,
    lease_s: float = SEAT_LEASE_SECONDS,
) -> Seat | Waiting:
    """Take a seat for ``universe_id``, or join the queue.

    Returns a :class:`Seat` when held, or :class:`Waiting` carrying the queue
    position. NEVER refuses for want of a seat. ``ticket`` re-presents a position
    already held, so a polling caller keeps it rather than going to the back.

    One `BEGIN IMMEDIATE` transaction does all of it -- reap, re-entry, count,
    ceiling, queue position, insert -- so two concurrent acquisitions cannot both
    see the last seat free.
    """
    universe_id = (universe_id or "").strip()
    if not universe_id:
        raise ValueError("a seat needs a universe_id")
    if seat_class not in SEAT_CLASSES:
        raise ValueError(f"seat class must be one of {SEAT_CLASSES}, not {seat_class!r}")
    moment = time.time() if now is None else now
    if seats is None or reserve is None:
        limits = _limits(universe_id)
        seats = limits.seats if seats is None else seats
        reserve = limits.interactive_reserve if reserve is None else reserve
    total = max(1, int(seats))
    held_back = min(max(0, int(reserve)), total - 1)

    root = (db or ledger_path()).parent
    # Before the transaction: the lock is a filesystem operation, and taking it
    # inside `BEGIN IMMEDIATE` would hold the write lock across it.
    _register_liveness(root)
    with _txn(db) as conn:
        _reap(conn, moment, root)
        if parent_seat_id and _reenter(
            conn, universe_id, parent_seat_id, moment, lease_s
        ):
            if ticket is not None:
                conn.execute("DELETE FROM seat_waiters WHERE ticket = ?", (ticket,))
            return Seat(
                seat_id=parent_seat_id,
                universe_id=universe_id,
                seat_class=seat_class,
                kind=kind,
                reentrant=True,
            )
        running = _running(conn, universe_id)
        ahead = _ahead_of(conn, universe_id, seat_class, ticket)
        if _admits(conn, universe_id, seat_class, seats=total, reserve=held_back) and (
            ahead == 0
        ):
            seat_id = secrets.token_hex(12)
            conn.execute(
                "INSERT INTO universe_seats (seat_id, universe_id, seat_class, kind, "
                "run_id, holder, depth, acquired_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    seat_id, universe_id, seat_class, kind, run_id, _holder(),
                    moment, moment + lease_s,
                ),
            )
            if ticket is not None:
                conn.execute("DELETE FROM seat_waiters WHERE ticket = ?", (ticket,))
            return Seat(
                seat_id=seat_id,
                universe_id=universe_id,
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
                "INSERT INTO seat_waiters (universe_id, seat_class, kind, run_id, "
                "holder, enqueued_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    universe_id, seat_class, kind, run_id, _holder(),
                    moment, moment + WAITER_LEASE_SECONDS,
                ),
            )
            ticket = int(cur.lastrowid or 0)
        waiting = int(
            conn.execute(
                "SELECT COUNT(*) FROM seat_waiters WHERE universe_id = ?",
                (universe_id,),
            ).fetchone()[0]
        )
        return Waiting(
            ticket=ticket,
            universe_id=universe_id,
            seat_class=seat_class,
            running=running,
            waiting=waiting,
            seats=total,
        )


def _limits(universe_id: str):
    """This universe's tier limits. Resolved here so no caller passes its own."""
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.usage_policy import limits_for, limits_for_universe

    try:
        return limits_for_universe(_universe_dir(universe_id))
    except Exception:
        # `get_tier` already swallows its own failures and returns free; this
        # catches a failure to RESOLVE the directory at all. Free is the safe
        # answer: it is the tier that grants least.
        _log.warning("could not resolve tier for %s; using free", universe_id)
        from tinyassets.usage_policy import TIER_FREE

        return limits_for(TIER_FREE)


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
            (moment + SEAT_LEASE_SECONDS, seat_id, _holder()),
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
    universe_id: str,
    *,
    db: Path | None = None,
    now: float | None = None,
    seats: int | None = None,
) -> dict[str, object]:
    """What the owner is shown: seats total, running, waiting, and the ceiling
    background work may reach. Read-only, and it reaps nothing -- an observation
    must not change what it observes."""
    universe_id = (universe_id or "").strip()
    limits = None
    if seats is None:
        limits = _limits(universe_id)
        seats = limits.seats
    moment = time.time() if now is None else now
    out: dict[str, object] = {
        "seats": int(seats),
        "running": 0,
        "waiting": 0,
        "background_seats": limits.background_seats if limits else int(seats),
    }
    if not universe_id:
        return out
    try:
        with _txn(db) as conn:
            out["running"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM universe_seats "
                    "WHERE universe_id = ? AND expires_at >= ?",
                    (universe_id, moment),
                ).fetchone()[0]
            )
            out["waiting"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM seat_waiters "
                    "WHERE universe_id = ? AND expires_at >= ?",
                    (universe_id, moment),
                ).fetchone()[0]
            )
    except SeatLedgerUnusable:
        out["availability"] = "unavailable"
    return out


def waiting_message(
    universe_id: str,
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
        from tinyassets.storage.subscription_state import TIER_FREE, get_tier

        try:
            from tinyassets.api.helpers import _universe_dir

            tier = get_tier(_universe_dir(universe_id))
        except Exception:
            tier = TIER_FREE
    head = f"Waiting for a free seat ({int(running)} running)."
    tail = upgrade_sentence(tier, what="seats")
    return f"{head} {tail}".strip()


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
    a graceful shutdown; a held seat then expires on its lease, which is correct."""
    global _refresher
    _refresher_stop.set()
    thread = _refresher
    if thread is not None:
        thread.join(timeout=2.0)
    with _held_lock:
        _refresher = None
        _held.clear()


@contextmanager
def hold(
    universe_id: str,
    *,
    seat_class: str = CLASS_BACKGROUND,
    kind: str = KIND_AGENT_NODE,
    run_id: str = "",
    parent_seat_id: str | None = None,
    wait_s: float = SEAT_WAIT_SECONDS,
    db: Path | None = None,
):
    """Hold a seat for the body, waiting up to ``wait_s`` for one.

    Yields a :class:`Seat` when held, or a :class:`Waiting` when the bounded wait
    elapsed -- the caller then surfaces the waiting state rather than blocking
    forever, and the queue POSITION IS KEPT so the work is not dropped. Check
    `isinstance(x, Seat)`.

    Released on every exit path including exceptions, which is success, failure,
    cancellation and timeout. A crash is covered by the lease instead, and that is
    the only path a `finally` cannot reach.
    """
    deadline = time.monotonic() + max(0.0, wait_s)
    ticket: int | None = None
    outcome: Seat | Waiting = acquire(
        universe_id,
        seat_class=seat_class,
        kind=kind,
        run_id=run_id,
        parent_seat_id=parent_seat_id,
        db=db,
    )
    while isinstance(outcome, Waiting) and time.monotonic() < deadline:
        ticket = outcome.ticket
        time.sleep(_POLL_SECONDS)
        outcome = acquire(
            universe_id,
            seat_class=seat_class,
            kind=kind,
            run_id=run_id,
            ticket=ticket,
            parent_seat_id=parent_seat_id,
            db=db,
        )
    if isinstance(outcome, Waiting):
        # Still waiting. Hand it back WITHOUT abandoning the ticket: the position
        # is the promise that the work runs.
        yield outcome
        return
    # A re-entered seat is its parent's: the parent's refresher already stamps it,
    # and registering it twice would have two owners racing to drop it.
    if not outcome.reentrant:
        with _held_lock:
            _held[outcome.seat_id] = db
        _start_refresher()
    try:
        yield outcome
    finally:
        if not outcome.reentrant:
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
    "WAITER_LEASE_SECONDS",
    "Seat",
    "SeatLedgerUnusable",
    "Waiting",
    "abandon",
    "acquire",
    "hold",
    "ledger_path",
    "occupancy",
    "refresh",
    "release",
    "stop_refresher",
    "waiting_message",
]
