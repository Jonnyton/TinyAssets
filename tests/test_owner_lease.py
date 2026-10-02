"""One owner commits per command center, and a successor is proven, not guessed.

Change ``execution-owner-lease`` slice B1. Process death is simulated the way the
kernel performs it: a tree member's lock is released (``OwnerTree.leave``), which
is exactly what happens to its descriptors when the process dies.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tinyassets import owner_lease
from tinyassets.owner_lease import (
    LeaseBusy,
    LeaseLost,
    OwnerTree,
    RestoreInProgress,
    acquire,
    key_for,
    using_tree,
)
from tinyassets.storage.owner_fence import advance_fence, check_fence, stored_fences

A, B = key_for("cc-a"), key_for("cc-b")


def _store(base: Path) -> Path:
    """An owner store with a fence table, registered in the catalog."""
    path = base / "owned.db"
    sqlite3.connect(path).close()
    owner_lease.register_store(base, path, "agent_turn_journal")
    return path


def _fenced_write(store: Path, lease) -> None:
    conn = sqlite3.connect(store, isolation_level=None)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS t (v TEXT)")
        conn.execute("BEGIN IMMEDIATE")
        check_fence(conn, lease)
        conn.execute("INSERT INTO t VALUES ('x')")
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


@pytest.fixture
def base(tmp_path):
    return tmp_path


@pytest.fixture
def owner(base):
    tree = OwnerTree.start(base)
    with using_tree(tree):
        yield tree
    tree.leave()


def test_first_use_takes_generation_one_and_rereading_keeps_it(base, owner):
    _store(base)
    first = acquire(base, A)
    assert first.generation == 1 and first.held()
    assert acquire(base, A).generation == 1
    assert first.verify(1, first.proof) and not first.verify(1, "0" * 64)
    assert not first.verify(2, first.proof)


def test_a_live_owner_is_never_displaced(base, owner):
    acquire(base, A)
    rival = OwnerTree.start(base)
    try:
        with using_tree(rival), pytest.raises(LeaseBusy):
            acquire(base, A, wait_s=0.2)
    finally:
        rival.leave()
    assert acquire(base, A).generation == 1


def test_a_dead_owner_is_succeeded_and_its_writes_are_fenced_off(base, owner):
    store = _store(base)
    old = acquire(base, A)
    _fenced_write(store, old)
    owner.leave()  # the old owner's whole tree dies
    heir = OwnerTree.start(base)
    try:
        with using_tree(heir):
            new = acquire(base, A, wait_s=1)
            assert new.generation == 2
            assert stored_fences(store)[A] == 2
            _fenced_write(store, new)
            # The old owner, resumed with what it believed, commits NOTHING.
            with pytest.raises(LeaseLost):
                _fenced_write(store, old)
            assert not old.held()
    finally:
        heir.leave()


def test_moving_one_command_center_does_not_fence_another(base, owner):
    store = _store(base)
    a = acquire(base, A)
    b = acquire(base, B)
    owner_lease.release(b)  # B goes idle and moves
    heir = OwnerTree.start(base)
    try:
        with using_tree(heir):
            assert acquire(base, B).generation == 2
        _fenced_write(store, a)  # A's owner keeps committing
        with pytest.raises(LeaseLost):
            _fenced_write(store, b)
    finally:
        heir.leave()


def test_a_voluntary_release_is_taken_without_any_death(base, owner):
    _store(base)
    lease = acquire(base, A)
    assert owner_lease.release(lease) is True
    assert owner_lease.release(lease) is False  # not twice
    heir = OwnerTree.start(base)
    try:
        with using_tree(heir):
            assert acquire(base, A, wait_s=0).generation == 2
    finally:
        heir.leave()


def test_a_member_that_joins_late_cannot_act_for_the_moved_key(base, owner):
    """Round-3 refute finding 1: the old tree gained a member after its death was
    proven. It joins, but the key has a living owner now, and its old generation
    is fenced off."""
    store = _store(base)
    old = acquire(base, A)
    owner.leave()
    heir = OwnerTree.start(base)
    try:
        with using_tree(heir):
            acquire(base, A, wait_s=1)
        late = OwnerTree(base, owner.tree_id).join()  # the delayed child
        try:
            with using_tree(late):
                with pytest.raises(LeaseBusy):
                    acquire(base, A, wait_s=0.2)
                with pytest.raises(LeaseLost):
                    _fenced_write(store, old)
        finally:
            late.leave()
    finally:
        heir.leave()


def test_a_joining_member_blocks_the_death_proof(base, owner):
    """The gate: while someone is joining the tree, it is not provably dead."""
    acquire(base, A)
    owner.leave()
    gate = owner_lease._try_lock(base / owner_lease.TREE_DIR / owner.tree_id / ".gate")
    assert gate is not None
    try:
        assert owner_lease.tree_alive(base, owner.tree_id) is True
    finally:
        owner_lease._unlock(gate)
    assert owner_lease.tree_alive(base, owner.tree_id) is False


def test_an_unprovable_tree_blocks_it_is_never_read_as_dead(base, owner):
    acquire(base, A)
    with owner_lease.lease_db(base) as conn:
        conn.execute("UPDATE owner_lease SET holder_tree = ? WHERE owner_key = ?",
                     ("f" * 32, A))
    assert owner_lease.tree_alive(base, "f" * 32) is True
    with pytest.raises(LeaseBusy):
        acquire(base, A, wait_s=0.2)


def test_advance_fence_refuses_a_lost_lease_and_never_lowers(base, owner):
    store = _store(base)
    old = acquire(base, A)
    owner.leave()
    heir = OwnerTree.start(base)
    try:
        with using_tree(heir):
            acquire(base, A, wait_s=1)
        with pytest.raises(LeaseLost):
            advance_fence(store, old)
        assert stored_fences(store)[A] == 2
    finally:
        heir.leave()


# --- restore ----------------------------------------------------------------


def _restore():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import owner_lease_restore

    return owner_lease_restore


def test_an_interrupted_restore_fails_closed(base, owner):
    restore = _restore()
    restore.begin(base)
    with pytest.raises(RestoreInProgress):
        acquire(base, A)
    restore.finish(base, restore.high_water(base))
    assert acquire(base, A).generation == 1


def test_restore_high_water_includes_the_recovered_lease_and_every_store(base, owner):
    """Round-2 refute finding 3: a lease committed at 9 whose fences stayed at 8
    must not be restored to 8 and re-issued as 9."""
    from tinyassets.storage import DB_FILENAME

    journal_store = base / DB_FILENAME
    conn = sqlite3.connect(journal_store)
    conn.execute("CREATE TABLE owner_fence (owner_key TEXT PRIMARY KEY, generation INTEGER)")
    conn.execute("INSERT INTO owner_fence VALUES (?, 8)", (A,))
    conn.execute("CREATE TABLE agent_turns (universe_id TEXT, owner_generation INTEGER)")
    conn.execute("INSERT INTO agent_turns VALUES ('cc-b', 12)")
    conn.commit()
    conn.close()
    with owner_lease.lease_db(base) as lease_conn:
        lease_conn.execute(
            "INSERT INTO owner_lease VALUES (?, 9, ?, 'x', 'open', 'now', NULL)",
            (A, "e" * 32),
        )
    restore = _restore()
    manifest = restore.run(base)
    assert manifest["high_water"] == {A: 9, B: 12}
    assert acquire(base, A, wait_s=0).generation == 10
    assert acquire(base, B, wait_s=0).generation == 13


def test_every_store_kind_has_an_enumerator_that_finds_its_store(base):
    from tinyassets.owner_stores import FENCED
    from tinyassets.storage import DB_FILENAME

    for kind in set(FENCED.values()):
        assert kind in owner_lease.STORE_ENUMERATORS, kind
    (base / DB_FILENAME).write_bytes(b"")
    assert owner_lease.STORE_ENUMERATORS["agent_turn_journal"](base) == [base / DB_FILENAME]


# --- the tree reaches every executor the owner spawns -----------------------


def test_the_daemon_advertises_its_tree_to_children(base, monkeypatch):
    # Recorded first, so teardown restores the variable's absence even though
    # start_owner_tree writes os.environ directly.
    monkeypatch.setenv(owner_lease.TREE_ENV, "")
    tree = owner_lease.start_owner_tree(base)
    try:
        import os

        assert os.environ[owner_lease.TREE_ENV] == tree.tree_id
        # A child process inherits it and joins the SAME tree: alive while it is.
        child = subprocess.run(
            [sys.executable, "-c",
             "import os, sys; from tinyassets import owner_lease; "
             "t = owner_lease.current_tree(sys.argv[1]); "
             "print(t.tree_id == os.environ[owner_lease.TREE_ENV])", str(base)],
            capture_output=True, text=True, timeout=60,
        )
        assert child.stdout.strip() == "True", child.stderr
    finally:
        tree.leave()


def test_engine_spawns_carry_the_owner_tree(monkeypatch, tmp_path):
    monkeypatch.setenv(owner_lease.TREE_ENV, "a" * 32)
    from tinyassets import engine_mcp_http

    seen = {}

    def fake_popen(argv, env=None, **kwargs):
        seen.update(env or {})

        class P:
            def poll(self):
                return None
        return P()

    monkeypatch.setattr(engine_mcp_http.subprocess, "Popen", fake_popen)
    instance = engine_mcp_http._EngineServer("u", "o", 1, str(tmp_path))
    assert instance.start() is True
    assert seen[owner_lease.TREE_ENV] == "a" * 32
