"""Differential guard for factoring create_run's caller-owned transaction seam."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from types import SimpleNamespace

import pytest

from tinyassets import runs
from tinyassets.principals import named_principal


def _legacy_create_run(
    base_path,
    *,
    branch_def_id,
    thread_id,
    inputs,
    actor,
    run_name="",
    branch_version_id=None,
    owner_user_id=None,
    daemon_id=None,
    runtime_instance_id=None,
    worker_id=None,
    branch_task_id=None,
    queue_universe_id=None,
):
    """Executable pre-extraction behavior from 89933afb, retained for comparison."""
    actor = named_principal(actor)
    if not actor:
        raise ValueError("create_run actor must be a real principal; an unowned value is not one")
    runs.initialize_runs_db(base_path)
    run_id = runs.uuid.uuid4().hex[:16]
    owner = (
        str(owner_user_id or "")
        if owner_user_id is not None
        else runs._resolve_owner_user_id(
            base_path,
            daemon_id,
        )
    )
    try:
        with runs._connect(base_path) as conn:
            conn.execute(
                """INSERT INTO runs (
                    run_id, branch_def_id, run_name, thread_id,
                    status, actor, owner_user_id, inputs_json, started_at,
                    branch_version_id, daemon_id, runtime_instance_id,
                    worker_id, branch_task_id, queue_universe_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    branch_def_id,
                    run_name,
                    thread_id,
                    runs.RUN_STATUS_QUEUED,
                    actor,
                    owner,
                    json.dumps(inputs, default=str),
                    runs._now(),
                    branch_version_id,
                    daemon_id,
                    runtime_instance_id,
                    worker_id,
                    branch_task_id,
                    queue_universe_id,
                ),
            )
    except sqlite3.IntegrityError as exc:
        if branch_task_id and "runs.branch_task_id" in str(exc):
            raise runs.BranchTaskRunReservationConflict(
                f"BranchTask {branch_task_id!r} already has a run reservation"
            ) from exc
        raise
    return run_id


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"actor": "system"},
        {"owner_user_id": "owner", "queue_universe_id": "u-owner"},
        {"owner_user_id": "", "thread_id": "existing-thread", "run_name": "Unicode 🧪"},
        {"branch_version_id": "version", "branch_task_id": "task", "worker_id": "worker"},
        {"runtime_instance_id": "runtime", "daemon_id": "absent-daemon"},
        {"inputs": {"legacy-non-json": datetime(2026, 9, 9), "number": 3}},
    ],
)
def test_normal_run_record_matches_pre_extraction_behavior(tmp_path, monkeypatch, options):
    monkeypatch.setattr(runs.uuid, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    monkeypatch.setattr(runs, "_now", lambda: 12345.0)
    kwargs = dict(branch_def_id="branch", thread_id="", inputs={"topic": "one"}, actor="owner")
    kwargs.update(options)
    records = []
    for name, create in (("legacy", _legacy_create_run), ("candidate", runs.create_run)):
        base = tmp_path / name
        run_id = create(base, **kwargs)
        assert run_id == "a" * 16
        with runs._connect(base) as conn:
            records.append(
                dict(conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())
            )
    assert records[0] == records[1]


@pytest.mark.parametrize("actor", ["", "anonymous", None])
def test_unowned_run_refusal_matches_legacy(tmp_path, actor):
    errors = []
    for name, create in (("legacy", _legacy_create_run), ("candidate", runs.create_run)):
        try:
            create(tmp_path / name, branch_def_id="b", thread_id="", inputs={}, actor=actor)
        except ValueError as exc:
            errors.append(str(exc))
    assert len(errors) == 2
    assert errors[0] == errors[1]


def test_internal_insert_does_not_commit_or_resolve_another_database(tmp_path, monkeypatch):
    runs.initialize_runs_db(tmp_path)

    def unexpected(*args, **kwargs):
        raise AssertionError("transaction-owned insert must not resolve ambient ownership")

    monkeypatch.setattr(runs, "_resolve_owner_user_id", unexpected)
    with runs._connect(tmp_path) as conn:
        with pytest.raises(ValueError, match="active caller-owned transaction"):
            runs._insert_run_in_transaction(
                conn,
                run_id="reserved",
                branch_def_id="b",
                thread_id="reserved",
                inputs={},
                actor="receiver",
                owner_user_id="receiver",
            )
        conn.execute("BEGIN IMMEDIATE")
        runs._insert_run_in_transaction(
            conn,
            run_id="reserved",
            branch_def_id="b",
            thread_id="reserved",
            inputs={},
            actor="receiver",
            owner_user_id="receiver",
        )
        assert conn.in_transaction
        conn.rollback()
    with runs._connect(tmp_path) as conn:
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_branch_task_unique_reservation_keeps_legacy_error(tmp_path):
    for name, create in (("legacy", _legacy_create_run), ("candidate", runs.create_run)):
        kwargs = dict(
            branch_def_id="b", thread_id="", inputs={}, actor="owner", branch_task_id="task"
        )
        create(tmp_path / name, **kwargs)
        with pytest.raises(
            runs.BranchTaskRunReservationConflict, match="already has a run reservation"
        ):
            create(tmp_path / name, **kwargs)
