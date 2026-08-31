"""The run lifecycle owes the workspace outbox its work (workspace-node D0/D6).

A run that held a scratch lease releases it THROUGH an outbox entry written in
the same transaction as its terminal status; both orphan-recovery paths do the
same; a once-per-process reconciler finishes what an earlier process left; and
every workspace refusal is a first-class failure class with an action.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from tinyassets import runs, workspace_pool

GIB = 1024 ** 3


class _NoopFs:
    """A filesystem that has nothing to delete: every entry completes."""

    def exists(self, path: Path) -> bool:
        return False

    def rename(self, src: Path, dst: Path) -> None:
        raise AssertionError("nothing exists, nothing to rename")

    def remove_tree_no_follow(self, path: Path) -> None:
        raise AssertionError("nothing exists, nothing to remove")


def _seed_run(base: Path, run_id: str, status: str = "running") -> None:
    runs.initialize_runs_db(base)
    with runs._connect(base) as conn:
        conn.execute(
            "INSERT INTO runs (run_id, branch_def_id, thread_id, status, started_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, "b1", f"t-{run_id}", status, time.time() - 7200),
        )


def _admit(base: Path, tmp: Path, run_id: str, universe: str = "u-1") -> workspace_pool.Lease:
    db = runs.runs_db_path(base)
    with runs._connect(base) as conn:
        workspace_pool.ensure_schema(conn)
    return workspace_pool.admit(
        db,
        universe_id=universe,
        connection_id="c1",
        repo_key="github.com--o--r",
        storage_class="scratch",
        run_id=run_id,
        max_bytes=GIB,
        pool_root=tmp / "scratch",
        universe_root=tmp / "universes" / universe,
    )


def _pending(base: Path, run_id: str) -> list[tuple]:
    conn = sqlite3.connect(runs.runs_db_path(base))
    try:
        return conn.execute(
            "SELECT action, lease_id FROM workspace_outbox WHERE run_id = ? AND done_at IS NULL",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()


def test_a_terminal_status_enqueues_the_lease_in_the_same_write(tmp_path, monkeypatch):
    base = tmp_path / "data"
    _seed_run(base, "r1")
    lease = _admit(base, tmp_path, "r1")
    kicks: list[Path] = []
    monkeypatch.setattr(runs, "_kick_workspace_sweep", lambda p: kicks.append(Path(p)))
    assert _pending(base, "r1") == []
    runs.update_run_status(base, "r1", status="running", last_node_id="n1")
    assert _pending(base, "r1") == [], "a non-terminal status owes nothing"
    assert kicks == [], "nothing owed, nothing kicked"
    runs.update_run_status(base, "r1", status="completed", finished_at=time.time())
    assert _pending(base, "r1") == [("wipe_scratch", lease.lease_id)]
    assert kicks == [base], "a finished run's release is kicked, not left to the tick"


def test_an_enqueue_failure_rolls_the_terminal_status_back(tmp_path, monkeypatch):
    """One transaction means one: if the outbox cannot take the entry, the
    status write must not land either (Codex, code round 1)."""
    base = tmp_path / "data"
    _seed_run(base, "r1c")
    _admit(base, tmp_path, "r1c")
    monkeypatch.setattr(runs, "_kick_workspace_sweep", lambda p: None)

    def _boom(conn, base_path, run_id):
        raise sqlite3.OperationalError("outbox unavailable")

    monkeypatch.setattr(runs, "_enqueue_workspace_terminal", _boom)
    with pytest.raises(sqlite3.OperationalError):
        runs.update_run_status(base, "r1c", status="completed", finished_at=time.time())
    conn = sqlite3.connect(runs.runs_db_path(base))
    try:
        status = conn.execute("SELECT status FROM runs WHERE run_id = ?", ("r1c",)).fetchone()[0]
    finally:
        conn.close()
    assert status == "running", "the terminal status rolled back with the failed enqueue"
    assert _pending(base, "r1c") == []


def test_the_kick_releases_the_lock_within_the_same_second(tmp_path, monkeypatch):
    base = tmp_path / "data"
    _seed_run(base, "r1b")
    lease = _admit(base, tmp_path, "r1b")
    monkeypatch.setattr("tinyassets.workspace_fs.RealPoolFilesystem", _NoopFs)
    threads: list = []
    real_kick = runs._kick_workspace_sweep
    monkeypatch.setattr(runs, "_kick_workspace_sweep", lambda p: threads.append(real_kick(p)))
    runs.update_run_status(base, "r1b", status="completed", finished_at=time.time())
    for t in threads:
        t.join(timeout=10)
    assert _pending(base, "r1b") == []
    after = workspace_pool.get_lease(runs.runs_db_path(base), lease.lease_id)
    assert after is not None and after.state == "AVAILABLE"
    conn = sqlite3.connect(runs.runs_db_path(base))
    try:
        held = conn.execute(
            "SELECT COUNT(*) FROM workspace_locks WHERE run_id = ?", ("r1b",)
        ).fetchone()[0]
    finally:
        conn.close()
    assert held == 0, "both locks are released by the kicked sweep"


def test_a_run_holding_only_the_lock_releases_it(tmp_path, monkeypatch):
    base = tmp_path / "data"
    _seed_run(base, "r2")
    lease = _admit(base, tmp_path, "r2")
    monkeypatch.setattr(runs, "_kick_workspace_sweep", lambda p: None)
    # Simulate a lease that already left ACTIVE (a discard) while the run's
    # universe lock is still held: the terminal write owes a lock release.
    conn = sqlite3.connect(runs.runs_db_path(base))
    conn.execute(
        "UPDATE workspace_leases SET state = 'AVAILABLE' WHERE lease_id = ?",
        (lease.lease_id,),
    )
    conn.commit()
    conn.close()
    runs.update_run_status(base, "r2", status="failed", error="boom")
    assert _pending(base, "r2") == [("release_lock_only", None)]


def test_read_time_orphan_recovery_enqueues(tmp_path, monkeypatch):
    base = tmp_path / "data"
    _seed_run(base, "r3", status="running")
    lease = _admit(base, tmp_path, "r3")
    monkeypatch.setattr(runs, "ensure_workspace_reconciled", lambda *_a, **_k: False)
    # No worker owns r3 and its progress is stale: the read path marks it
    # interrupted and, in the same transaction, owes the lease to the outbox.
    monkeypatch.setattr(runs, "_mark_orphaned_run_if_needed", _always_orphan)
    assert runs._recover_orphaned_runs_on_read(base) == 1
    assert _pending(base, "r3") == [("wipe_scratch", lease.lease_id)]


def _always_orphan(conn, *, run_id, status, started_at, now):
    conn.execute(
        "UPDATE runs SET status = 'interrupted', finished_at = ? WHERE run_id = ?",
        (now, run_id),
    )
    return True


def test_startup_recovery_enqueues_every_in_flight_run(tmp_path):
    base = tmp_path / "data"
    _seed_run(base, "r4", status="queued")
    _seed_run(base, "r5", status="completed")
    lease4 = _admit(base, tmp_path, "r4")
    assert runs.recover_in_flight_runs(base) == 1
    assert _pending(base, "r4") == [("wipe_scratch", lease4.lease_id)]
    assert _pending(base, "r5") == []


def test_the_reconciler_runs_once_and_finishes_old_entries(tmp_path, monkeypatch):
    base = tmp_path / "data"
    _seed_run(base, "r6")
    lease = _admit(base, tmp_path, "r6")
    monkeypatch.setattr(runs, "_kick_workspace_sweep", lambda p: None)
    runs.update_run_status(base, "r6", status="completed")
    assert _pending(base, "r6")
    monkeypatch.setattr("tinyassets.workspace_fs.RealPoolFilesystem", _NoopFs)
    import os

    runs._WORKSPACE_RECONCILED.discard((os.getpid(), str(base.resolve())))
    assert runs.ensure_workspace_reconciled(base, start_sweeper=False) is True
    assert runs.ensure_workspace_reconciled(base, start_sweeper=False) is False
    assert _pending(base, "r6") == []
    after = workspace_pool.get_lease(runs.runs_db_path(base), lease.lease_id)
    assert after is not None and after.state == "AVAILABLE"


def test_the_periodic_pass_leaves_a_permanent_generation_alone(tmp_path, monkeypatch):
    """An authoritative permanent generation stays ACTIVE after its run by
    design; the sweep must not re-enqueue it every tick."""
    base = tmp_path / "data"
    _seed_run(base, "r7b", status="completed")
    db = runs.runs_db_path(base)
    with runs._connect(base) as conn:
        workspace_pool.ensure_schema(conn)
    lease = workspace_pool.admit(
        db, universe_id="u-1", connection_id="c1", repo_key="github.com--o--r",
        storage_class="universe", run_id="r7b", max_bytes=GIB,
        pool_root=tmp_path / "scratch", universe_root=tmp_path / "universes" / "u-1",
        universe_quota_bytes=10 * GIB, universe_used_bytes_fn=lambda _u: 0,
    )
    monkeypatch.setattr("tinyassets.workspace_fs.RealPoolFilesystem", _NoopFs)
    runs._workspace_sweep_once(base, claimant="test")
    after = workspace_pool.get_lease(db, lease.lease_id)
    assert after is not None and after.state == "ACTIVE", "the generation is kept"
    conn = sqlite3.connect(db)
    try:
        held = conn.execute(
            "SELECT COUNT(*) FROM workspace_locks WHERE run_id = ?", ("r7b",)
        ).fetchone()[0]
        entries = conn.execute(
            "SELECT action FROM workspace_outbox WHERE run_id = ?", ("r7b",)
        ).fetchall()
    finally:
        conn.close()
    assert held == 0, "its locks were released through a lock-only entry"
    assert entries == [("release_lock_only",)]
    runs._workspace_sweep_once(base, claimant="test")
    conn = sqlite3.connect(db)
    try:
        again = conn.execute(
            "SELECT COUNT(*) FROM workspace_outbox WHERE run_id = ?", ("r7b",)
        ).fetchone()[0]
    finally:
        conn.close()
    assert again == 1, "a second tick enqueues nothing more"


def test_the_reconciler_retries_after_a_failed_attempt(tmp_path, monkeypatch):
    base = tmp_path / "data"
    runs.initialize_runs_db(base)
    calls = {"n": 0}

    def _fail_once(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("sweep exploded")
        return 0

    monkeypatch.setattr(workspace_pool, "startup_sweep", _fail_once)
    with pytest.raises(RuntimeError):
        runs.ensure_workspace_reconciled(base, start_sweeper=False)
    assert runs.ensure_workspace_reconciled(base, start_sweeper=False) is True
    assert runs.ensure_workspace_reconciled(base, start_sweeper=False) is False
    assert calls["n"] == 2


def test_the_periodic_pass_repairs_an_orphaned_active_lease(tmp_path, monkeypatch):
    base = tmp_path / "data"
    _seed_run(base, "r7", status="completed")
    lease = _admit(base, tmp_path, "r7")
    # The run is terminal but nothing enqueued (an older terminal writer): the
    # sweep notices the ACTIVE lease with a finished run and repairs it.
    monkeypatch.setattr("tinyassets.workspace_fs.RealPoolFilesystem", _NoopFs)
    assert _pending(base, "r7") == []
    runs._workspace_sweep_once(base, claimant="test")
    after = workspace_pool.get_lease(runs.runs_db_path(base), lease.lease_id)
    assert after is not None and after.state == "AVAILABLE"


def test_the_scratch_root_is_created_under_the_data_root(tmp_path, monkeypatch):
    """The adapter admits into ``<data>/scratch`` (one level above the
    universe directory); the creator must agree (Codex code round 2, #1)."""
    universe = tmp_path / "data" / "universe-x"
    universe.mkdir(parents=True)
    monkeypatch.setattr(workspace_pool, "startup_sweep", lambda *a, **k: 0)
    assert runs.ensure_workspace_reconciled(universe, start_sweeper=False) is True
    assert (tmp_path / "data" / "scratch").is_dir()
    assert not (universe / "scratch").exists()


def test_a_workspace_command_timeout_keeps_its_class():
    def classify(text):
        return runs._classify_failure({"status": "failed", "error": text})

    kind = classify("Workspace command timeout: node 'n1' ws.run exceeded 30s")
    assert kind == "workspace_command_timeout"
    assert classify("Node timeout: node 'n1' exceeded 300s") == "timeout"


def test_the_chain_closes_workspace_descriptors_on_revoke_and_settle():
    from tinyassets.effectors import EffectChain

    class _Mount:
        def __init__(self):
            self.closed = 0

        def close(self):
            self.closed += 1

    chain = EffectChain(run_id="r-close", base_path=None)
    a, b = _Mount(), _Mount()
    chain.register_workspace("checkout_a", a)
    chain.register_workspace("checkout_b", b)
    assert chain.revoke_workspace("checkout_a") is a
    assert a.closed == 1
    chain.revoke_workspace("checkout_a")
    assert a.closed == 1, "idempotent: a second revoke closes nothing twice"
    chain.settle()
    assert b.closed == 1, "settle closes what the run still held"
    assert chain.workspace_mount("checkout_b") is None


@pytest.mark.parametrize("kind", runs.WORKSPACE_FAILURE_KINDS)
def test_every_workspace_refusal_is_its_own_class_with_an_action(kind):
    summary = f"external write failed - checkout/workspace: refused [{kind}]"
    assert runs._classify_external_write(summary) == kind
    assert runs.external_write_suggested_action(kind)
    assert runs.ACTIONABLE_BY[kind] == "chatbot"


def test_non_workspace_summaries_classify_as_before():
    assert (
        runs._classify_external_write("external write failed - x [effect_budget_exhausted]")
        == "effect_budget_exhausted"
    )
    assert (
        runs._classify_external_write("external write failed - x [missing_consent]")
        == "external_write_refused"
    )
    assert runs._classify_external_write("external write failed - 422") == "external_write_failed"


def test_served_docs_name_the_workspace_sink():
    from tinyassets import engine_mcp_server as srv

    doc = srv.__doc__ or ""
    import inspect

    text = inspect.getsource(srv)
    for needle in (
        "WORKSPACES.",
        '"op": "checkout"',
        '"workspace": "<that node id>"',
        "ws.run(",
        "ws.bundle(",
        "workspace_command_timeout",
        "tiny/<universe>/<slug>",
    ):
        assert needle in text or needle in doc, needle
