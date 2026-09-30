"""Seats: the queue, the reserve, re-entry, and the leases that reap a dead holder.

Every test drives the REAL ledger through `acquire` / `release`, with an explicit
`db` and an explicit `now`, so nothing here depends on the refresher thread or on
wall-clock timing. `seats=` / `reserve=` are passed explicitly where the tier is
not what is under test -- resolving a tier needs a universe directory, and these
are tests of the seat algebra, not of subscription lookup.

Named regressions carry the astra round-1 finding they close, because the first
draft of `_admits` and `_reenter` were both wrong in ways a passing test would not
have noticed.
"""

from __future__ import annotations

import threading

import pytest

from tinyassets import universe_seats as seats
from tinyassets.universe_seats import (
    CLASS_BACKGROUND,
    CLASS_INTERACTIVE,
    Seat,
    Waiting,
)


@pytest.fixture
def db(tmp_path):
    return tmp_path / "seats.db"


def take(db, universe="u1", *, cls=CLASS_BACKGROUND, seats_n=3, reserve=1,
         ticket=None, parent=None, now=1000.0, kind="agent_node"):
    return seats.acquire(
        universe, seat_class=cls, kind=kind, ticket=ticket,
        parent_seat_id=parent, seats=seats_n, reserve=reserve, db=db, now=now,
    )


# -- Acquisition and release ------------------------------------------------- #


def test_a_seat_is_held_then_given_back(db):
    got = take(db)
    assert isinstance(got, Seat)
    assert seats.occupancy("u1", db=db, seats=3, now=1000.0)["running"] == 1
    assert seats.release(got.seat_id, db=db) is True
    assert seats.occupancy("u1", db=db, seats=3, now=1000.0)["running"] == 0


def test_release_is_safe_on_a_seat_that_is_already_gone(db):
    """Release runs from a `finally`, so the unwinding path must not raise when the
    seat was already reaped -- that is exactly when it will have been."""
    got = take(db)
    assert seats.release(got.seat_id, db=db) is True
    assert seats.release(got.seat_id, db=db) is False


@pytest.mark.parametrize(
    "ending",
    ["success", "failure", "cancellation", "timeout"],
)
def test_every_terminal_path_releases_the_seat(db, ending):
    """One seat, four ways for its work to end. `hold` releases in a `finally`, so
    the only path it cannot cover is a crash -- which is the lease's job."""
    class Cancelled(BaseException):
        """A cancellation is a BaseException in this tree; a bare `except
        Exception` in `hold` would leak the seat on exactly that path."""

    raised = {"failure": RuntimeError, "timeout": TimeoutError,
              "cancellation": Cancelled}.get(ending)
    with pytest.raises(raised) if raised else _nullctx():
        with seats.hold("u1", db=db, wait_s=0.0, seats=3, reserve=1) as held:
            assert isinstance(held, Seat)
            if raised:
                raise raised("ended")
    seats.stop_refresher()
    assert seats.occupancy("u1", db=db, seats=3)["running"] == 0


class _nullctx:
    def __enter__(self):
        return None

    def __exit__(self, *_):
        return False


# -- Waiting, for a caller that must not bounce ------------------------------ #


def test_a_chat_turn_waits_until_served_instead_of_bouncing(db, monkeypatch):
    """`wait_s=None`. A turn that queued must not come back to the user after a
    timeout: a bounce reads as a refusal however it is worded, and the directive
    says work is never refused. So the turn waits, and is served when the seat
    frees."""
    # A short bounded deadline, so "waits far past where a bounce would fire"
    # is a fraction of a second rather than minutes.
    monkeypatch.setattr(seats, "SEAT_WAIT_SECONDS", 0.05)
    blocker = seats.acquire(
        "u1", seat_class=CLASS_INTERACTIVE, seats=1, reserve=0, db=db,
    )
    assert isinstance(blocker, Seat)

    served: list[object] = []
    notices: list[Waiting] = []

    def turn():
        with seats.hold(
            "u1", seat_class=CLASS_INTERACTIVE, kind=seats.KIND_CHAT_TURN,
            wait_s=None, on_waiting=notices.append, seats=1, reserve=0, db=db,
        ) as got:
            served.append(got)

    thread = threading.Thread(target=turn, daemon=True)
    thread.start()
    # Outlive the BOUNDED deadline by a wide margin. Joining for less than
    # `SEAT_WAIT_SECONDS` would pass even if `wait_s=None` silently bounced,
    # which is exactly what a mutation check caught.
    thread.join(timeout=seats.SEAT_WAIT_SECONDS * 8)
    assert thread.is_alive(), "an interactive turn must keep waiting, not bounce"
    assert not served, "nothing may be yielded before a seat exists"
    assert notices, "a waiting turn must publish its waiting state"
    assert notices[0].running == 1

    seats.release(blocker.seat_id, db=db)
    thread.join(timeout=5.0)
    seats.stop_refresher()
    assert not thread.is_alive()
    assert len(served) == 1
    assert isinstance(served[0], Seat), "the turn is served once a seat frees"


def test_the_waiting_notice_carries_the_live_running_count(db):
    """The owner watches this number, so it must come from the ledger each time
    rather than being captured once."""
    seats.acquire("u1", seat_class=CLASS_BACKGROUND, seats=2, reserve=1, db=db)
    waiting = seats.acquire("u1", seat_class=CLASS_BACKGROUND, seats=2, reserve=1, db=db)
    assert isinstance(waiting, Waiting)
    message = seats.waiting_message("u1", running=waiting.running, tier="free")
    assert "(1 running)" in message
    assert "[Upgrade](" in message


def test_a_bounded_waiter_keeps_its_ticket_when_it_gives_up(db):
    """A pump gives up and retries next tick. Its queue position must survive,
    or a busy universe would send it to the back forever."""
    seats.acquire("u1", seat_class=CLASS_BACKGROUND, seats=2, reserve=1, db=db)
    with seats.hold(
        "u1", seat_class=CLASS_BACKGROUND, wait_s=0.0, seats=2, reserve=1, db=db,
    ) as got:
        assert isinstance(got, Waiting)
        ticket = got.ticket
    again = seats.acquire(
        "u1", seat_class=CLASS_BACKGROUND, seats=2, reserve=1, ticket=ticket, db=db,
    )
    assert isinstance(again, Waiting)
    assert again.ticket == ticket, "giving up on a bounded wait must not lose the position"


def test_a_failing_waiting_notice_does_not_lose_the_seat(db):
    """A notice is a notification, not a step. If the owner's surface is down the
    caller must still get its seat."""
    blocker = seats.acquire(
        "u1", seat_class=CLASS_INTERACTIVE, seats=1, reserve=0, db=db,
    )

    calls: list[int] = []

    def boom(_state):
        calls.append(1)
        raise RuntimeError("owner surface unavailable")

    served: list[object] = []

    def turn():
        with seats.hold(
            "u1", seat_class=CLASS_INTERACTIVE, wait_s=None, on_waiting=boom,
            seats=1, reserve=0, db=db,
        ) as got:
            served.append(got)

    thread = threading.Thread(target=turn, daemon=True)
    thread.start()
    # Let it actually wait, so the notice actually fires and actually raises.
    thread.join(timeout=0.5)
    assert calls, "the notice must have been attempted while waiting"
    assert thread.is_alive()

    seats.release(blocker.seat_id, db=db)
    thread.join(timeout=5.0)
    seats.stop_refresher()
    assert served and isinstance(served[0], Seat), (
        "a notice that raises must not cost the caller the seat it is owed"
    )


# -- The queue --------------------------------------------------------------- #


def test_over_the_limit_work_waits_and_is_never_refused(db):
    held = [take(db, seats_n=3, reserve=1) for _ in range(2)]
    assert all(isinstance(h, Seat) for h in held)
    third = take(db, seats_n=3, reserve=1)
    assert isinstance(third, Waiting), "background work must queue, never refuse"
    assert third.running == 2
    assert third.ticket > 0


def test_the_queue_runs_longest_owed_first(db):
    """A, B, C enqueue in that order behind one seat; they start in that order."""
    first = take(db, seats_n=2, reserve=1)
    assert isinstance(first, Seat)
    a, b, c = (take(db, seats_n=2, reserve=1) for _ in range(3))
    assert [w.ticket for w in (a, b, c)] == sorted(w.ticket for w in (a, b, c))

    seats.release(first.seat_id, db=db)
    # B and C must not overtake A even though a seat is free for all of them.
    assert isinstance(take(db, seats_n=2, reserve=1, ticket=b.ticket), Waiting)
    assert isinstance(take(db, seats_n=2, reserve=1, ticket=c.ticket), Waiting)
    promoted = take(db, seats_n=2, reserve=1, ticket=a.ticket)
    assert isinstance(promoted, Seat)


def test_an_arriving_call_does_not_overtake_an_owed_waiter(db):
    """The `ahead == 0` predicate is what makes the queue a queue: a fresh arrival
    finding a free seat still joins behind whoever is already owed one."""
    held = take(db, seats_n=2, reserve=1)
    waiter = take(db, seats_n=2, reserve=1)
    assert isinstance(waiter, Waiting)
    seats.release(held.seat_id, db=db)
    newcomer = take(db, seats_n=2, reserve=1)
    assert isinstance(newcomer, Waiting)
    assert newcomer.ticket > waiter.ticket


def test_a_waiter_keeps_its_position_while_it_polls(db):
    """A polling caller re-presents its ticket. Without that it would walk to the
    back of its own queue every poll and never be served."""
    take(db, seats_n=2, reserve=1)
    waiter = take(db, seats_n=2, reserve=1)
    assert isinstance(waiter, Waiting)
    for _ in range(5):
        again = take(db, seats_n=2, reserve=1, ticket=waiter.ticket)
        assert isinstance(again, Waiting)
        assert again.ticket == waiter.ticket


# -- The interactive reserve ------------------------------------------------- #


def test_background_work_can_never_take_the_last_seat(db):
    """Three seats, one reserved: background stops at two however hard it tries."""
    a = take(db, cls=CLASS_BACKGROUND, seats_n=3, reserve=1)
    b = take(db, cls=CLASS_BACKGROUND, seats_n=3, reserve=1)
    assert isinstance(a, Seat) and isinstance(b, Seat)
    third = take(db, cls=CLASS_BACKGROUND, seats_n=3, reserve=1)
    assert isinstance(third, Waiting)
    # ... and the seat it could not have is there for the chat.
    chat = take(db, cls=CLASS_INTERACTIVE, seats_n=3, reserve=1)
    assert isinstance(chat, Seat)


def test_interactive_work_is_ordered_ahead_of_every_background_waiter(db):
    take(db, cls=CLASS_BACKGROUND, seats_n=2, reserve=1)
    background = take(db, cls=CLASS_BACKGROUND, seats_n=2, reserve=1)
    assert isinstance(background, Waiting)
    # The chat arrives last and is served first: the reserve is its seat.
    chat = take(db, cls=CLASS_INTERACTIVE, seats_n=2, reserve=1)
    assert isinstance(chat, Seat)


def test_a_reserve_bounds_background_not_the_total(db):
    """astra round 1, finding 6. The first draft compared TOTAL live against
    `seats - reserve` for background work. With 3 seats, 1 reserved and two
    INTERACTIVE holders that refused background work while a seat sat free and no
    background work was running at all -- the reserve protecting interactive work
    from itself."""
    one = take(db, cls=CLASS_INTERACTIVE, seats_n=3, reserve=1)
    two = take(db, cls=CLASS_INTERACTIVE, seats_n=3, reserve=1)
    assert isinstance(one, Seat) and isinstance(two, Seat)
    background = take(db, cls=CLASS_BACKGROUND, seats_n=3, reserve=1)
    assert isinstance(background, Seat), (
        "one seat is free and no background work is running; the reserve "
        "constrains the background class, not the total"
    )


def test_a_reserve_can_never_consume_every_seat(db):
    """A reserve at or above the seat count would refuse all background work to
    protect a chat nobody is having. Clamped, so background always has one."""
    got = take(db, cls=CLASS_BACKGROUND, seats_n=2, reserve=9)
    assert isinstance(got, Seat)


def test_the_total_still_binds_interactive_work(db):
    """Interactive work may take every seat -- and no more."""
    held = [take(db, cls=CLASS_INTERACTIVE, seats_n=2, reserve=1) for _ in range(2)]
    assert all(isinstance(h, Seat) for h in held)
    assert isinstance(take(db, cls=CLASS_INTERACTIVE, seats_n=2, reserve=1), Waiting)


# -- Re-entry ---------------------------------------------------------------- #


def test_a_blocking_nested_call_runs_on_its_parents_seat(db):
    """One background seat, a two-deep blocking chain. Without inheritance the
    child waits for a seat its own blocked parent is holding -- a deadlock against
    itself."""
    parent = take(db, seats_n=2, reserve=1)
    assert isinstance(parent, Seat)
    child = take(db, seats_n=2, reserve=1, parent=parent.seat_id)
    assert isinstance(child, Seat)
    assert child.reentrant is True
    assert child.seat_id == parent.seat_id
    assert seats.occupancy("u1", db=db, seats=2, now=1000.0)["running"] == 1


def test_releasing_a_nested_seat_leaves_the_parent_holding_it(db):
    parent = take(db, seats_n=2, reserve=1)
    child = take(db, seats_n=2, reserve=1, parent=parent.seat_id)
    assert seats.release(child.seat_id, db=db) is True
    assert seats.occupancy("u1", db=db, seats=2, now=1000.0)["running"] == 1
    assert seats.release(parent.seat_id, db=db) is True
    assert seats.occupancy("u1", db=db, seats=2, now=1000.0)["running"] == 0


def test_a_seat_is_lent_to_one_nested_call_at_a_time(db):
    """astra round 1, finding 4. Reference counting would let a blocked parent lend
    one seat to three PARALLEL child agent nodes -- three model calls on one seat,
    the bound failing silently. Inheritance is an exclusive transfer, so the second
    sibling takes its own seat."""
    parent = take(db, seats_n=3, reserve=1)
    first = take(db, seats_n=3, reserve=1, parent=parent.seat_id)
    assert isinstance(first, Seat) and first.reentrant is True
    sibling = take(db, seats_n=3, reserve=1, parent=parent.seat_id)
    assert isinstance(sibling, Seat)
    assert sibling.reentrant is False, "a parallel sibling pays its own seat"
    assert sibling.seat_id != parent.seat_id
    assert seats.occupancy("u1", db=db, seats=3, now=1000.0)["running"] == 2


def test_another_universe_cannot_ride_a_seat_by_naming_it(db):
    """Cross-user seat theft. A seat id is not a capability: re-entry matches on
    the universe AND the holder, so naming someone else's seat takes a new one in
    your own universe rather than riding theirs."""
    theirs = take(db, universe="victim", seats_n=3, reserve=1)
    assert isinstance(theirs, Seat)
    mine = take(db, universe="attacker", seats_n=3, reserve=1, parent=theirs.seat_id)
    assert isinstance(mine, Seat)
    assert mine.reentrant is False
    assert mine.seat_id != theirs.seat_id
    assert seats.occupancy("victim", db=db, seats=3, now=1000.0)["running"] == 1
    assert seats.occupancy("attacker", db=db, seats=3, now=1000.0)["running"] == 1


def test_a_nonexistent_parent_seat_is_not_an_error(db):
    got = take(db, parent="deadbeef" * 3)
    assert isinstance(got, Seat)
    assert got.reentrant is False


# -- Leases and reaping ------------------------------------------------------ #


def test_an_expired_seat_of_a_dead_holder_is_reaped(db):
    """The only path a `finally` cannot cover is a crash, so the lease has to."""
    stranded = take(db, now=1000.0)
    assert isinstance(stranded, Seat)
    import subprocess
    import sys

    from tinyassets.process_liveness import DEAD, owner_state

    script = (
        "import os, sys; from tinyassets.process_liveness import hold_liveness; "
        "proof = hold_liveness(sys.argv[1], 'dead_holder'); os._exit(7)"
    )
    crashed = subprocess.run([sys.executable, "-c", script, str(db.parent)], check=False)
    assert crashed.returncode == 7
    assert owner_state(db.parent, "dead_holder") == DEAD
    _reseat_to(db, "dead_holder")
    later = take(db, now=1000.0 + seats.SEAT_LEASE_SECONDS + 1)
    assert isinstance(later, Seat), "a crashed holder's seat must not strand capacity"
    assert seats.occupancy(
        "u1", db=db, seats=3, now=1000.0 + seats.SEAT_LEASE_SECONDS + 1
    )["running"] == 1


def _reseat_to(db, holder: str) -> None:
    """Rewrite the holder of every seat row, standing in for a seat taken by a
    different process."""
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE universe_seats SET holder = ?", (holder,))
    conn.commit()
    conn.close()


def test_the_holder_token_is_one_the_liveness_lock_can_verify(db):
    """The bug that made the guard below dead code, pinned directly.

    The first draft's holder was `f"{pid}:{hex}"`. `automations._HOLDER_RE` is
    `^[A-Za-z0-9_-]{1,128}$`, so the colon meant `holder_liveness_path` returned
    None, every probe answered "unknown", and `holder_is_provably_alive` could
    never be true. A separator choice silently disabled a safety check, and the
    test that should have caught it had monkeypatched the predicate.
    """
    from tinyassets.process_liveness import ALIVE, liveness_path, owner_state

    holder = seats._holder(db.parent)
    assert liveness_path(db.parent, holder) is not None
    assert owner_state(db.parent, holder) == ALIVE


def test_taking_a_seat_registers_this_process_as_provably_alive(db):
    import sqlite3

    from tinyassets.process_liveness import ALIVE, owner_state

    got = take(db)
    assert isinstance(got, Seat)
    with sqlite3.connect(db) as conn:
        holder = conn.execute("SELECT holder FROM universe_seats").fetchone()[0]
    assert owner_state(db.parent, holder) == ALIVE


def test_a_live_holder_keeps_an_expired_seat(db):
    """astra round 1, finding 1. Unconditional reclamation admits a replacement
    while the original holder is still calling a provider: kill the refresher,
    leave the provider running, wait out the lease, and two agent calls execute on
    one seat. `automations._lease_blocks` refuses this for the same reason.

    Drives the REAL liveness probe against a REAL OS lock -- no monkeypatch of
    `_holder_is_alive`, because mocking it is exactly how the broken holder token
    stayed hidden.
    """
    from tinyassets.process_liveness import hold_liveness as hold_process_liveness

    other = "seat_other_process_1"
    lock = hold_process_liveness(db.parent, other)
    assert getattr(lock, "acquired", True), "test could not take the liveness lock"

    take(db, seats_n=2, reserve=1, now=1000.0)
    _reseat_to(db, other)
    expired = 1000.0 + seats.SEAT_LEASE_SECONDS + 1

    blocked = take(db, seats_n=2, reserve=1, now=expired)
    assert isinstance(blocked, Waiting), (
        "an expired lease whose holder is PROVABLY ALIVE must not be reclaimed: "
        "the holder may still be calling a provider"
    )

    # Now the holder dies -- the kernel drops its lock -- and the seat is free.
    # The ticket from the blocked attempt is re-presented, because that attempt
    # took a queue position and the no-overtake rule would otherwise put this
    # call behind it.
    import os

    os.close(lock.fd)
    reclaimed = take(db, seats_n=2, reserve=1, ticket=blocked.ticket, now=expired)
    assert isinstance(reclaimed, Seat), (
        "once the holder is provably dead its seat must not strand capacity"
    )


def test_refresh_keeps_a_long_running_seat_alive(db):
    """A served turn runs until it is finished. A short lease bounds how long a
    DEAD holder's seat survives, never how long a live one may run."""
    held = take(db, now=1000.0)
    assert seats.refresh(held.seat_id, db=db, now=5000.0) is True
    assert seats.occupancy(
        "u1", db=db, seats=3, now=5000.0 + seats.SEAT_LEASE_SECONDS - 1
    )["running"] == 1


def test_refresh_reports_a_seat_that_was_already_reaped(db):
    assert seats.refresh("nope" * 6, db=db) is False


def test_an_expired_waiter_loses_only_its_position(db):
    """A waiter row is a queue position, not work. Its expiry cannot lose work,
    because the work is durable in its own tables."""
    take(db, seats_n=2, reserve=1, now=1000.0)
    waiter = take(db, seats_n=2, reserve=1, now=1000.0)
    assert isinstance(waiter, Waiting)
    late = 1000.0 + seats.WAITER_LEASE_SECONDS + 1
    again = take(db, seats_n=2, reserve=1, ticket=waiter.ticket, now=late)
    assert isinstance(again, Waiting)
    assert again.ticket != waiter.ticket, "a lapsed position is re-taken, not revived"


# -- Cross-universe isolation ------------------------------------------------ #


def test_one_universe_at_its_limit_does_not_affect_another(db):
    """Two seats, one reserved, so universe `a`'s background ceiling is one."""
    assert isinstance(take(db, universe="a", seats_n=2, reserve=1), Seat)
    assert isinstance(take(db, universe="a", seats_n=2, reserve=1), Waiting)
    theirs = take(db, universe="b", seats_n=2, reserve=1)
    assert isinstance(theirs, Seat), "a full universe must not slow another down"


def test_occupancy_of_one_universe_never_counts_another(db):
    take(db, universe="a", seats_n=3, reserve=1)
    take(db, universe="a", seats_n=3, reserve=1)
    take(db, universe="b", seats_n=3, reserve=1)
    assert seats.occupancy("a", db=db, seats=3, now=1000.0)["running"] == 2
    assert seats.occupancy("b", db=db, seats=3, now=1000.0)["running"] == 1


# -- Concurrency ------------------------------------------------------------- #


def test_two_concurrent_acquisitions_cannot_both_take_the_last_seat(db):
    """One `BEGIN IMMEDIATE` per acquisition is the whole reason this holds."""
    results: list[object] = []
    lock = threading.Lock()

    def grab():
        got = seats.acquire(
            "u1", seat_class=CLASS_BACKGROUND, seats=2, reserve=1, db=db,
        )
        with lock:
            results.append(got)

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    held = [r for r in results if isinstance(r, Seat)]
    assert len(held) == 1, f"one background seat, {len(held)} handed out"
    assert len(results) == 8, "everyone else got a queue position, not a refusal"


# -- The ledger is not negotiable ------------------------------------------- #


def test_a_symlinked_seat_store_is_refused_loudly(db, tmp_path):
    """A seat store an attacker can redirect is a seat store whose counts they
    choose. Fail loudly, never admit because the check failed."""
    target = tmp_path / "elsewhere" / "seats.db"
    target.parent.mkdir()
    target.touch()
    link = tmp_path / "linked.db"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(seats.SeatLedgerUnusable):
        seats.acquire("u1", seats=3, reserve=1, db=link)


# -- What the owner sees ----------------------------------------------------- #


def test_the_waiting_message_names_the_running_count_and_links_upgrade():
    message = seats.waiting_message("u1", running=2, tier="free")
    assert "Waiting for a free seat (2 running)" in message
    assert "[Upgrade](https://tinyassets.io/" in message
    assert "?upgrade=1)" in message
    assert "for more seats." in message


def test_the_top_tier_is_not_asked_to_upgrade():
    message = seats.waiting_message("u1", running=2, tier="paid")
    assert "Waiting for a free seat (2 running)" in message
    assert "Upgrade" not in message


def test_occupancy_reports_what_the_owner_needs(db):
    take(db, seats_n=3, reserve=1)
    take(db, seats_n=3, reserve=1)
    take(db, seats_n=3, reserve=1)  # queues
    snapshot = seats.occupancy("u1", db=db, seats=3, now=1000.0)
    assert snapshot["running"] == 2
    assert snapshot["waiting"] == 1
    assert snapshot["seats"] == 3


# -- Input validation -------------------------------------------------------- #


def test_a_seat_without_a_universe_fails_loudly(db):
    with pytest.raises(ValueError, match="account_id"):
        seats.acquire("  ", seats=3, reserve=1, db=db)


def test_an_unknown_seat_class_fails_loudly(db):
    with pytest.raises(ValueError, match="seat class"):
        seats.acquire("u1", seat_class="vip", seats=3, reserve=1, db=db)


def test_universes_share_their_owners_pool_but_not_another_accounts(db):
    import sqlite3

    from tinyassets.storage import db_path

    with sqlite3.connect(db_path(db.parent)) as conn:
        conn.execute("CREATE TABLE universe_acl (universe_id, actor_id, permission, granted_by)")
        conn.execute("CREATE TABLE founder_home (founder_sub, universe_id)")
        conn.execute("CREATE TABLE agent_bindings (created_by, universe_id, status)")
        conn.executemany("INSERT INTO universe_acl VALUES (?, ?, 'admin', '')",
                         [("village", "alice"), ("work", "alice"), ("home", "bob")])
    alice = seats.account_for_universe("village", root=db.parent)
    same = seats.account_for_universe("work", root=db.parent)
    bob = seats.account_for_universe("home", root=db.parent)
    assert alice == same == "alice"
    assert isinstance(take(db, universe=alice), Seat)
    assert isinstance(take(db, universe=same), Seat)
    assert isinstance(take(db, universe=alice), Waiting)
    assert isinstance(take(db, universe=bob), Seat)
    assert seats.occupancy(bob, db=db, seats=3, now=1000)["running"] == 1


def test_death_proof_stays_until_seats_are_reclaimed(db):
    import subprocess
    import sys

    from tinyassets.process_liveness import DEAD, owner_state, remove_if_dead

    child = subprocess.run([
        sys.executable, "-c",
        "import os,sys; from pathlib import Path; "
        "from tinyassets import universe_seats as s; "
        "s.acquire('alice',db=Path(sys.argv[1]),seats=3,reserve=1); os._exit(7)",
        str(db.parent / seats.LEDGER_NAME),
    ], check=False)
    assert child.returncode == 7
    import sqlite3

    with sqlite3.connect(db.parent / seats.LEDGER_NAME) as conn:
        holder = conn.execute("SELECT holder FROM universe_seats").fetchone()[0]
    assert owner_state(db.parent, holder) == DEAD
    assert not remove_if_dead(db.parent, holder,
                              lambda token: seats.holder_is_named(db.parent, token))
    seats.acquire("alice", db=db.parent / seats.LEDGER_NAME, seats=3, reserve=1)
    assert remove_if_dead(db.parent, holder,
                          lambda token: seats.holder_is_named(db.parent, token))


def test_three_deep_transfer_is_exclusive_at_each_depth(db):
    parent = take(db, seats_n=2)
    child = take(db, seats_n=2, parent=parent.seat_id)
    grandchild = seats.acquire(
        "u1", db=db, seats=2, reserve=1, parent_seat_id=child.seat_id,
        parent_depth=child.depth, now=1000,
    )
    assert isinstance(grandchild, Seat) and grandchild.reentrant
    sibling = seats.acquire(
        "u1", db=db, seats=2, reserve=1, parent_seat_id=child.seat_id,
        parent_depth=child.depth, now=1000,
    )
    assert isinstance(sibling, Waiting)
    for held in (grandchild, child, parent):
        seats.release(held.seat_id, db=db)
    assert seats.occupancy("u1", db=db, seats=2, now=1000)["running"] == 0
