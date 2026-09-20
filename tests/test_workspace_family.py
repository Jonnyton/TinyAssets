"""Core family authority uses real SQLite rows and real OS process exclusion."""

from __future__ import annotations

import multiprocessing

import pytest

from tinyassets import runs
from tinyassets import workspace_family as family


def _row(conn, run_id, *, owner="owner", universe="universe", status="running"):
    runs._insert_run_in_transaction(
        conn,
        run_id=run_id,
        branch_def_id="branch",
        thread_id=run_id,
        inputs={},
        actor="actor",
        owner_user_id=owner,
        queue_universe_id=universe,
        _workspace_authenticated=False,
    )
    conn.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))


@pytest.fixture
def base(tmp_path):
    runs.initialize_runs_db(tmp_path)
    return tmp_path


def _root(base, root="root"):
    with family.try_family_fence(base, root) as fence:
        assert fence is not None
        with runs._connect(base) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _row(conn, root)
            return family.assign_in_transaction(conn, fence, root)


def test_migration_never_infers_legacy_root_from_lineage(base):
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _row(conn, "legacy")
        row = conn.execute(
            "SELECT workspace_budget_root_run_id, workspace_budget_epoch, "
            "workspace_budget_closing_reason FROM runs WHERE run_id='legacy'"
        ).fetchone()
        assert tuple(row) == (None, None, None)
    with family.try_family_fence(base, "legacy") as fence, runs._connect(base) as conn:
        with pytest.raises(family.FamilyRefused, match="unknown"):
            family.member_in_transaction(conn, fence, "legacy")


def test_completed_parent_allows_child_second_node_and_late_grandchild(base):
    root = _root(base)
    with family.try_family_fence(base, "root") as fence, runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _row(conn, "child")
        child = family.assign_in_transaction(conn, fence, "child", parent=root)
        conn.execute("UPDATE runs SET status='completed' WHERE run_id='root'")
        assert family.validate_in_transaction(conn, fence, child) == child
        _row(conn, "grandchild")
        grandchild = family.assign_in_transaction(conn, fence, "grandchild", parent=child)
        assert grandchild.root_run_id == "root" and grandchild.epoch == 1
        assert not family.prepare_release_in_transaction(conn, fence, 1, empty=lambda: True)
        conn.execute("UPDATE runs SET status='completed' WHERE run_id IN ('child','grandchild')")
        assert not family.prepare_release_in_transaction(conn, fence, 1, empty=lambda: False)
        assert family.prepare_release_in_transaction(conn, fence, 1, empty=lambda: True)
        with pytest.raises(family.FamilyRefused, match="closed"):
            family.validate_in_transaction(conn, fence, child)


@pytest.mark.parametrize("mismatch", ["owner", "universe"])
def test_child_owner_scope_never_borrowed(base, mismatch):
    root = _root(base)
    with family.try_family_fence(base, "root") as fence, runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _row(conn, "child", **{mismatch: "someone-else"})
        with pytest.raises(family.FamilyRefused, match="identity"):
            family.assign_in_transaction(conn, fence, "child", parent=root)


def test_close_after_root_completed_refuses_late_join_without_rewriting_result(base):
    root = _root(base)
    with family.try_family_fence(base, "root") as fence, runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _row(conn, "child")
        child = family.assign_in_transaction(conn, fence, "child", parent=root)
        conn.execute(
            "UPDATE runs SET status='completed', output_json='{"
            + '"ok":true'
            + "}' WHERE run_id='root'"
        )
        assert family.close_in_transaction(conn, fence, 1, "memory_limit")
        assert family.close_in_transaction(conn, fence, 1, "cancelled")
        row = conn.execute(
            "SELECT status,output_json,workspace_budget_closing_reason FROM runs "
            "WHERE run_id='root'"
        ).fetchone()
        assert tuple(row) == ("completed", '{"ok":true}', "memory_limit")
        with pytest.raises(family.FamilyRefused, match="closed"):
            family.validate_in_transaction(conn, fence, child)
        _row(conn, "grandchild")
        with pytest.raises(family.FamilyRefused, match="closed"):
            family.assign_in_transaction(conn, fence, "grandchild", parent=child)


def test_resumed_child_new_epoch_does_not_adopt_old_siblings_or_cleanup(base):
    root = _root(base)
    with family.try_family_fence(base, "root") as fence, runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _row(conn, "child")
        child = family.assign_in_transaction(conn, fence, "child", parent=root)
        _row(conn, "sibling")
        sibling = family.assign_in_transaction(conn, fence, "sibling", parent=root)
        conn.execute("UPDATE runs SET status='interrupted'")
        family.close_in_transaction(conn, fence, 1, "interrupted")
        with pytest.raises(family.FamilyRefused, match="empty"):
            family.resume_in_transaction(conn, fence, child, empty=lambda: False)
        resumed = family.resume_in_transaction(conn, fence, child, empty=lambda: True)
        assert resumed.epoch == 2
        conn.execute("UPDATE runs SET status='running' WHERE run_id='child'")
        assert family.validate_in_transaction(conn, fence, resumed) == resumed
        for stale in (root, child, sibling):
            with pytest.raises(family.FamilyRefused, match="epoch"):
                family.validate_in_transaction(conn, fence, stale)
        assert not family.close_in_transaction(conn, fence, 1, "cancelled")
        assert not family.prepare_release_in_transaction(conn, fence, 1, empty=lambda: True)
        row = conn.execute(
            "SELECT workspace_budget_epoch FROM runs WHERE run_id='sibling'"
        ).fetchone()
        assert row[0] == 1
        _row(conn, "new-grandchild")
        assert (
            family.assign_in_transaction(conn, fence, "new-grandchild", parent=resumed).epoch == 2
        )


def test_resume_does_not_broaden_status_or_clear_cancel(base):
    root = _root(base)
    with family.try_family_fence(base, "root") as fence, runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE runs SET status='failed'")
        family.close_in_transaction(conn, fence, 1, "memory_limit")
        with pytest.raises(family.FamilyRefused, match="interrupted"):
            family.resume_in_transaction(conn, fence, root, empty=lambda: True)
        conn.execute("UPDATE runs SET status='interrupted'")
        conn.execute("INSERT INTO run_cancels VALUES ('root',1)")
        with pytest.raises(family.FamilyRefused, match="cancel"):
            family.resume_in_transaction(conn, fence, root, empty=lambda: True)


def _take_fence(base, pipe):
    with family.try_family_fence(base, "root") as fence:
        pipe.send(fence is not None)


def test_fence_excludes_an_independent_process_and_releases_after_exit(base):
    context = multiprocessing.get_context("spawn")
    with family.try_family_fence(base, "root") as fence:
        assert fence is not None
        receiving, sending = context.Pipe(False)
        process = context.Process(target=_take_fence, args=(base, sending))
        process.start()
        assert receiving.poll(15)
        assert receiving.recv() is False
        process.join(15)
        assert process.exitcode == 0
        receiving.close()
        sending.close()
    with family.try_family_fence(base, "root") as replacement:
        assert replacement is not None


def test_retired_or_wrong_database_fence_never_authorizes(base, tmp_path):
    root = _root(base)
    with family.try_family_fence(base, "root") as fence:
        pass
    with runs._connect(base) as conn:
        with pytest.raises(family.FamilyRefused, match="fence"):
            family.validate_in_transaction(conn, fence, root)


def test_replaced_worker_cannot_reuse_same_epoch_context(base):
    root = _root(base)
    with family.try_family_fence(base, "root") as fence, runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE runs SET runtime_instance_id='replacement',worker_id='new-worker'")
        with pytest.raises(family.FamilyRefused, match="identity"):
            family.validate_in_transaction(conn, fence, root)
