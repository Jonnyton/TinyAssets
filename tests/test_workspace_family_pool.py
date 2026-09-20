"""Real two-database family admission and outbox; no kernel success claim."""

import sqlite3

import pytest

from tests.test_workspace_family import _root, _row
from tests.test_workspace_pool import FakeFs
from tinyassets import runs
from tinyassets import workspace_family as family
from tinyassets import workspace_pool as pool


def _admit(db, base, run_id, admission=None):
    return pool.admit(
        db,
        universe_id="universe",
        connection_id="c",
        repo_key=run_id,
        storage_class="scratch",
        run_id=run_id,
        max_bytes=1,
        pool_root=base / "scratch",
        universe_root=base / "workspace",
        family_admission=admission,
    )


def _outbox(db, lease):
    with sqlite3.connect(db) as conn:
        conn.execute("BEGIN IMMEDIATE")
        pool.enqueue_terminal(conn, run_id=lease.run_id, universe_id="universe", lease=lease)
    entry = pool.claim_next(db, claimant="test")
    assert entry is not None
    return entry


def test_child_lease_reentrant_and_member_terminal_never_releases_root(tmp_path):
    runs.initialize_runs_db(tmp_path)
    root = _root(tmp_path)
    db = tmp_path / "separate-universe.db"
    with family.try_family_fence(tmp_path, "root") as fence:
        lease = _admit(db, tmp_path, "root", family.FamilyAdmission(fence, root))
        with runs._connect(tmp_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _row(conn, "child")
            child = family.assign_in_transaction(conn, fence, "child", parent=root)
            conn.execute("UPDATE runs SET status='completed' WHERE run_id='root'")
        child_lease = _admit(db, tmp_path, "child", family.FamilyAdmission(fence, child))
        assert child_lease.budget_root_run_id == "root" and child_lease.budget_epoch == 1
        assert pool.get_lease(db, child_lease.lease_id) == child_lease
        entry = _outbox(db, lease)
        assert not entry.release_universe_lock and not entry.release_host_lock
        assert pool.process_entry(db, entry, fs=FakeFs()) == pool.OUTCOME_WIPED
        with pytest.raises(pool.WorkspacePoolRefused):
            _admit(db, tmp_path, "unrelated")
        with sqlite3.connect(db) as conn:
            assert conn.execute(
                "SELECT DISTINCT run_id,budget_epoch FROM workspace_locks"
            ).fetchall() == [("root", 1)]


def test_root_release_requires_live_fence_empty_proof_and_matching_epoch(tmp_path):
    runs.initialize_runs_db(tmp_path)
    root = _root(tmp_path)
    db = tmp_path / "separate-universe.db"
    with family.try_family_fence(tmp_path, "root") as fence:
        lease = _admit(db, tmp_path, "root", family.FamilyAdmission(fence, root))
        with runs._connect(tmp_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE runs SET status='completed' WHERE run_id='root'")
            assert family.prepare_release_in_transaction(conn, fence, 1, empty=lambda: True)
        release = family.FamilyRelease(fence, "universe", 1, empty=lambda: True)
        with sqlite3.connect(db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            with pytest.raises(family.FamilyRefused, match="cleanup"):
                pool.enqueue_family_release(conn, release)
        entry = _outbox(db, lease)
        pool.process_entry(db, entry, fs=FakeFs())
        release = family.FamilyRelease(fence, "universe", 1, empty=lambda: True)
        with sqlite3.connect(db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            pool.enqueue_family_release(conn, release)
        entry = pool.claim_next(db, claimant="release")
        with pytest.raises(family.FamilyRefused):
            pool.process_entry(db, entry, fs=FakeFs())
        pool.process_entry(db, entry, fs=FakeFs(), family_release=release)
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT count(*) FROM workspace_locks").fetchone()[0] == 0
    _admit(db, tmp_path, "unrelated")


def test_legacy_terminal_intent_cannot_delete_new_managed_lock(tmp_path):
    runs.initialize_runs_db(tmp_path)
    root = _root(tmp_path)
    db = tmp_path / "separate-universe.db"
    with family.try_family_fence(tmp_path, "root") as fence:
        _admit(db, tmp_path, "root", family.FamilyAdmission(fence, root))
        with sqlite3.connect(db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            pool.enqueue_terminal(conn, run_id="root", universe_id="universe", lease=None)
        entry = pool.claim_next(db, claimant="old")
        pool.process_entry(db, entry, fs=FakeFs())
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT count(*) FROM workspace_locks").fetchone()[0] == 2


def test_retired_admission_is_not_a_cached_permission(tmp_path):
    runs.initialize_runs_db(tmp_path)
    root = _root(tmp_path)
    with family.try_family_fence(tmp_path, "root") as fence:
        admission = family.FamilyAdmission(fence, root)
    with pytest.raises(family.FamilyRefused, match="fence"):
        _admit(tmp_path / "universe.db", tmp_path, "root", admission)


def test_old_release_cannot_adopt_resumed_epoch_in_separate_pool_wal(tmp_path):
    runs.initialize_runs_db(tmp_path)
    root = _root(tmp_path)
    db = tmp_path / "separate-universe.db"
    with family.try_family_fence(tmp_path, "root") as fence:
        lease = _admit(db, tmp_path, "root", family.FamilyAdmission(fence, root))
        with runs._connect(tmp_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE runs SET status='interrupted'")
            family.close_in_transaction(conn, fence, 1, "interrupted")
        # Root WAL committed before universe cleanup: the original lock remains.
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT count(*) FROM workspace_locks").fetchone()[0] == 2
        member_cleanup = _outbox(db, lease)
        pool.process_entry(db, member_cleanup, fs=FakeFs())
        release1 = family.FamilyRelease(fence, "universe", 1, empty=lambda: True)
        with sqlite3.connect(db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            first = pool.enqueue_family_release(conn, release1)
            assert pool.enqueue_family_release(conn, release1) == first
        old_entry = pool.claim_next(db, claimant="release")
        pool.process_entry(db, old_entry, fs=FakeFs(), family_release=release1)
        with runs._connect(tmp_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            resumed = family.resume_in_transaction(conn, fence, root, empty=lambda: True)
            conn.execute("UPDATE runs SET status='running' WHERE run_id='root'")
        _admit(db, tmp_path, "root", family.FamilyAdmission(fence, resumed))
        with pytest.raises(family.FamilyRefused, match="current"):
            pool.process_entry(db, old_entry, fs=FakeFs(), family_release=release1)
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT DISTINCT budget_epoch FROM workspace_locks").fetchall() == [
                (2,)
            ]
