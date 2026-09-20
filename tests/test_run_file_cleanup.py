"""Exact journal cleanup, never recursive or permission to delete ready inputs."""

import json

import pytest

from tests.test_run_file_capture import intake  # noqa: F401
from tinyassets import runs
from tinyassets.run_file_capture import capture_authoring_files
from tinyassets.run_file_cleanup import cleanup_file_operation
from tinyassets.storage import run_files
from tinyassets.storage.run_file_lock import try_file_operation_lock


@pytest.fixture
def debt(intake, monkeypatch):  # noqa: F811 - pytest fixture injection
    base, _, sources, _ = intake

    def fault(*args, **kwargs):
        raise ValueError("fixture interruption")

    with monkeypatch.context() as changes:
        changes.setattr(run_files, "commit_objects_in_transaction", fault)
        with pytest.raises(ValueError):
            capture_authoring_files(
                base, owner_id="owner", universe_id="u", label="debt", sources=sources
            )
    with runs._connect(base) as conn:
        operation = dict(conn.execute("SELECT * FROM run_file_operations").fetchone())
    return base, operation


def test_exact_body_cleanup_releases_allocation_only_after_absence_proof(debt):
    base, operation = debt
    assert len(list((base / ".run-file-custody").glob("*.body"))) == 2
    assert cleanup_file_operation(base, operation_id=operation["operation_id"])
    assert not list((base / ".run-file-custody").glob("*.body"))
    with runs._connect(base) as conn:
        assert conn.execute("SELECT state FROM run_file_operations").fetchone()[0] == "released"
        assert conn.execute("SELECT amount,state FROM run_file_allocations").fetchone()[:] == (
            0,
            "released",
        )
        assert conn.execute("SELECT amount FROM workspace_ledger").fetchone()[0] == 3 * 1024 * 1024
    assert cleanup_file_operation(base, operation_id=operation["operation_id"])


def test_live_publisher_guard_prevents_collection(debt):
    base, operation = debt
    with try_file_operation_lock(base, operation_id=operation["operation_id"]):
        assert not cleanup_file_operation(base, operation_id=operation["operation_id"])
    assert len(list((base / ".run-file-custody").glob("*.body"))) == 2


def test_corrupt_inventory_refuses_without_deleting_guessed_paths(debt):
    base, operation = debt
    victim = base / "victim.body"
    victim.write_bytes(b"must survive")
    with runs._connect(base) as conn:
        conn.execute("UPDATE run_file_cleanup SET inventory_json=?", (json.dumps(["../victim"]),))
    with pytest.raises(run_files.FileCustodyRefused):
        cleanup_file_operation(base, operation_id=operation["operation_id"])
    assert victim.read_bytes() == b"must survive"
    assert len(list((base / ".run-file-custody").glob("*.body"))) == 2


def test_ready_objects_are_not_cleanup_authority(intake):  # noqa: F811
    base, _, sources, _ = intake
    refs = capture_authoring_files(
        base, owner_id="owner", universe_id="u", label="ready", sources=sources
    )
    with runs._connect(base) as conn:
        operation = conn.execute("SELECT operation_id FROM run_file_operations").fetchone()[0]
    with pytest.raises(run_files.FileCustodyRefused):
        cleanup_file_operation(base, operation_id=operation)
    assert (base / ".run-file-custody" / (refs[0]["file_id"] + ".body")).exists()


def test_subset_cleanup_keeps_sibling_and_cannot_resurrect_released_member(intake):  # noqa: F811
    base, _, sources, bodies = intake
    refs = capture_authoring_files(
        base, owner_id="owner", universe_id="u", label="subset", sources=sources
    )
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        operation = conn.execute("SELECT operation_id FROM run_file_operations").fetchone()[0]
        run_files.mark_cleanup_in_transaction(
            conn,
            operation_id=operation,
            owner_id="owner",
            universe_id="u",
            file_ids=[refs[1]["file_id"]],
        )
        assert conn.execute("SELECT amount FROM run_file_allocations").fetchone()[0] == sum(
            map(len, bodies)
        )
    assert cleanup_file_operation(base, operation_id=operation)
    assert (base / ".run-file-custody" / (refs[0]["file_id"] + ".body")).read_bytes() == bodies[0]
    assert not (base / ".run-file-custody" / (refs[1]["file_id"] + ".body")).exists()
    with runs._connect(base) as conn:
        assert conn.execute("SELECT amount,state FROM run_file_allocations").fetchone()[:] == (
            len(bodies[0]),
            "retained",
        )
        assert conn.execute("SELECT state FROM run_file_operations").fetchone()[0] == "committed"
    with pytest.raises(run_files.FileCustodyRefused):
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="subset", sources=sources
        )
