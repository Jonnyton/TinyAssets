"""Finite unbound retention never takes over a live capture or expires bindings."""

import time

import pytest

from tests.test_run_file_capture import intake  # noqa: F401
from tinyassets import runs
from tinyassets.run_file_capture import capture_authoring_files
from tinyassets.storage import run_files
from tinyassets.storage.run_file_lock import try_file_operation_lock


def captured(fixture):
    base, _, sources, bodies = fixture
    refs = capture_authoring_files(
        base, owner_id="owner", universe_id="u", label="retention", sources=sources
    )
    with runs._connect(base) as conn:
        operation = dict(conn.execute("SELECT * FROM run_file_operations").fetchone())
    return base, refs, bodies, operation


def expire(base):
    with runs._connect(base) as conn:
        conn.execute("UPDATE run_file_operations SET unbound_expires_at=?", (time.time() - 1,))


def tick(base, **kwargs):
    from tinyassets.run_file_retention import reconcile_run_files

    return reconcile_run_files(base, **kwargs)


def test_unbound_deadline_and_exact_collection(intake):  # noqa: F811
    base, refs, _, operation = captured(intake)
    assert operation["created_at"] > 0
    assert 3500 < operation["unbound_expires_at"] - time.time() <= 3600
    tick(base)
    assert all((base / ".run-file-custody" / (ref["file_id"] + ".body")).exists() for ref in refs)
    expire(base)
    tick(base)
    assert not list((base / ".run-file-custody").glob("*.body"))
    with runs._connect(base) as conn:
        assert conn.execute("SELECT amount FROM run_file_allocations").fetchone()[0] == 0
        assert conn.execute("SELECT amount FROM workspace_ledger").fetchone()[0] > 0


def test_expired_live_operation_is_not_stolen(intake):  # noqa: F811
    base, refs, _, operation = captured(intake)
    expire(base)
    with try_file_operation_lock(base, operation_id=operation["operation_id"]):
        tick(base)
    assert (base / ".run-file-custody" / (refs[0]["file_id"] + ".body")).exists()
    tick(base)
    assert not list((base / ".run-file-custody").glob("*.body"))


def test_expiry_preserves_bound_terminal_input_not_unbound_sibling(intake):  # noqa: F811
    base, refs, bodies, _ = captured(intake)
    run_id = runs.create_run(
        base,
        branch_def_id="branch",
        thread_id="",
        inputs={},
        actor="owner",
        owner_user_id="owner",
        queue_universe_id="u",
    )
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        run_files.bind_in_transaction(
            conn,
            run_id=run_id,
            owner_id="owner",
            universe_id="u",
            field_name="file",
            file_ids=[refs[0]["file_id"]],
        )
        conn.execute("UPDATE runs SET status='completed' WHERE run_id=?", (run_id,))
    expire(base)
    tick(base)
    assert (base / ".run-file-custody" / (refs[0]["file_id"] + ".body")).read_bytes() == bodies[0]
    assert not (base / ".run-file-custody" / (refs[1]["file_id"] + ".body")).exists()


def test_expired_unbound_reference_cannot_gain_new_binding(intake):  # noqa: F811
    base, refs, _, _ = captured(intake)
    run_id = runs.create_run(
        base,
        branch_def_id="branch",
        thread_id="",
        inputs={},
        actor="owner",
        owner_user_id="owner",
        queue_universe_id="u",
    )
    expire(base)
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(run_files.FileCustodyRefused):
            run_files.bind_in_transaction(
                conn,
                run_id=run_id,
                owner_id="owner",
                universe_id="u",
                field_name="file",
                file_ids=[refs[0]["file_id"]],
            )


def test_unknown_legacy_deadline_does_not_authorize_deletion(intake):  # noqa: F811
    base, refs, _, _ = captured(intake)
    with runs._connect(base) as conn:
        conn.execute("UPDATE run_file_operations SET unbound_expires_at=0")
    tick(base)
    assert (base / ".run-file-custody" / (refs[0]["file_id"] + ".body")).exists()


def test_absent_subsystem_does_not_create_database(tmp_path):
    tick(tmp_path)
    assert not runs.runs_db_path(tmp_path).exists()


def test_failed_cleanup_retains_debt_then_existing_tick_retries(intake, monkeypatch):  # noqa: F811
    from tinyassets import run_file_retention

    base, refs, bodies, _ = captured(intake)
    expire(base)
    with monkeypatch.context() as changes:

        def fail(*args, **kwargs):
            raise OSError("fixture disk unavailable")

        changes.setattr(run_file_retention, "cleanup_file_operation", fail)
        tick(base)
    with runs._connect(base) as conn:
        assert conn.execute("SELECT state FROM run_file_operations").fetchone()[0] == "cleanup"
        assert conn.execute("SELECT amount FROM run_file_allocations").fetchone()[0] == sum(
            map(len, bodies)
        )
    assert (base / ".run-file-custody" / (refs[0]["file_id"] + ".body")).exists()
    tick(base)
    assert not list((base / ".run-file-custody").glob("*.body"))


def test_bounded_scan_rotates_past_live_operation(intake):  # noqa: F811
    base, _, sources, _ = intake
    captured(intake)
    capture_authoring_files(base, owner_id="owner", universe_id="u", label="other", sources=sources)
    expire(base)
    with runs._connect(base) as conn:
        first, second = [
            row[0]
            for row in conn.execute(
                "SELECT operation_id FROM run_file_operations ORDER BY operation_id"
            )
        ]
    with try_file_operation_lock(base, operation_id=first):
        cursor = tick(base, limit=1)
        assert cursor == first
        assert tick(base, limit=1, after_operation_id=cursor) == second
    with runs._connect(base) as conn:
        assert (
            conn.execute(
                "SELECT state FROM run_file_operations WHERE operation_id=?", (second,)
            ).fetchone()[0]
            == "released"
        )


def test_additive_migration_keeps_unknown_deadline_zero(tmp_path):
    runs.initialize_runs_db(tmp_path)
    with runs._connect(tmp_path) as conn:
        run_files.ensure_schema(conn)
        conn.execute("ALTER TABLE run_file_operations DROP COLUMN created_at")
        conn.execute("ALTER TABLE run_file_operations DROP COLUMN unbound_expires_at")
        conn.execute(
            "INSERT INTO run_file_operations(operation_id,owner_id,universe_id,request_sha256,"
            "max_bytes,physical_root_id,state) VALUES('old','owner','u',?,1,'root','pending')",
            ("f" * 64,),
        )
        run_files.ensure_schema(conn)
        assert conn.execute(
            "SELECT created_at,unbound_expires_at FROM run_file_operations"
        ).fetchone()[:] == (0, 0)
