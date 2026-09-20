"""Exact owned run-bound export before public or sandbox adapters are enabled."""

import base64
import json

import pytest

from tests.test_run_file_capture import intake  # noqa: F401
from tinyassets import runs
from tinyassets.run_file_capture import capture_authoring_files
from tinyassets.run_file_reader import read_bound_file
from tinyassets.storage import _connect as author_connection
from tinyassets.storage import run_files


@pytest.fixture
def bound(intake):  # noqa: F811 - imported pytest fixture is injected here
    base, _, sources, bodies = intake
    refs = capture_authoring_files(
        base, owner_id="owner", universe_id="u", label="reader", sources=sources
    )
    run_id = runs.create_run(
        base,
        branch_def_id="branch",
        thread_id="",
        inputs={"files": refs},
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
            field_name="files",
            file_ids=[ref["file_id"] for ref in refs],
        )
    return base, run_id, refs, bodies


def test_exact_owned_chunks_zero_byte_and_byte_only_charge(bound):
    base, run_id, refs, bodies = bound
    result = read_bound_file(
        base,
        owner_id="owner",
        universe_id="u",
        run_id=run_id,
        file_id=refs[0]["file_id"],
        offset=7,
        count=1024 * 1024,
    )
    assert base64.b64decode(result["bytes_base64"]) == bodies[0][7 : 7 + 1024 * 1024]
    assert result["reference"] == refs[0]
    assert result["next_offset"] == 7 + 1024 * 1024 and not result["eof"]
    empty = read_bound_file(
        base,
        owner_id="owner",
        universe_id="u",
        run_id=run_id,
        file_id=refs[1]["file_id"],
        offset=0,
        count=1024,
    )
    assert empty["eof"] and empty["bytes_base64"] == ""
    with runs._connect(base) as conn:
        assert (
            conn.execute(
                "SELECT SUM(amount) FROM workspace_ledger WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            == 1024 * 1024
        )
        assert (
            conn.execute("SELECT COUNT(*) FROM workspace_ledger WHERE kind='jobs'").fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    "changed",
    [
        {"owner_id": "other"},
        {"universe_id": "other"},
        {"run_id": "other"},
        {"file_id": "0" * 32},
        {"offset": -1},
        {"count": True},
        {"count": 1024 * 1024 + 1},
    ],
)
def test_reader_rejects_foreign_scope_or_invalid_range(bound, changed):
    base, run_id, refs, _ = bound
    args = dict(
        owner_id="owner",
        universe_id="u",
        run_id=run_id,
        file_id=refs[0]["file_id"],
        offset=0,
        count=32,
    )
    args.update(changed)
    with pytest.raises((run_files.FileCustodyRefused, ValueError)):
        read_bound_file(base, **args)


def test_permission_revocation_before_return_never_returns_bytes(bound, monkeypatch):
    from tinyassets.execution_authority.blob_stream import HeldBlobStream

    base, run_id, refs, _ = bound
    actual = HeldBlobStream.read_range

    def revoke(self, *args):
        result = actual(self, *args)
        with author_connection(base) as conn:
            conn.execute("DELETE FROM universe_acl")
        return result

    monkeypatch.setattr(HeldBlobStream, "read_range", revoke)
    with pytest.raises(run_files.FileCustodyRefused):
        read_bound_file(
            base,
            owner_id="owner",
            universe_id="u",
            run_id=run_id,
            file_id=refs[0]["file_id"],
            offset=0,
            count=123,
        )
    with runs._connect(base) as conn:
        assert conn.execute(
            "SELECT amount,reserved FROM workspace_ledger WHERE run_id=?", (run_id,)
        ).fetchone()[:] == (123, 0)


def test_per_file_release_refuses_active_binding_then_preserves_sibling_read(bound):
    from tinyassets.run_file_release import release_owned_file

    base, run_id, refs, _ = bound
    with pytest.raises(run_files.FileCustodyRefused, match="active_use"):
        release_owned_file(base, owner_id="owner", universe_id="u", file_id=refs[0]["file_id"])
    runs.update_run_status(base, run_id, status="completed")
    assert (
        release_owned_file(base, owner_id="owner", universe_id="u", file_id=refs[0]["file_id"])[
            "state"
        ]
        == "released"
    )
    with pytest.raises(run_files.FileCustodyRefused):
        read_bound_file(
            base,
            owner_id="owner",
            universe_id="u",
            run_id=run_id,
            file_id=refs[0]["file_id"],
            offset=0,
            count=10,
        )
    sibling = read_bound_file(
        base,
        owner_id="owner",
        universe_id="u",
        run_id=run_id,
        file_id=refs[1]["file_id"],
        offset=0,
        count=10,
    )
    assert sibling["eof"] and sibling["bytes_base64"] == ""
    assert (
        release_owned_file(base, owner_id="owner", universe_id="u", file_id=refs[0]["file_id"])[
            "state"
        ]
        == "released"
    )
    assert (
        release_owned_file(base, owner_id="owner", universe_id="u", file_id=refs[1]["file_id"])[
            "state"
        ]
        == "released"
    )


def test_failed_subset_cleanup_retains_all_debt_until_retry_proves_absence(bound, monkeypatch):
    from tinyassets import run_file_release

    base, run_id, refs, bodies = bound
    runs.update_run_status(base, run_id, status="completed")

    def fault(*args, **kwargs):
        raise OSError("fixture cannot delete yet")

    with monkeypatch.context() as changes:
        changes.setattr(run_file_release, "cleanup_file_operation", fault)
        assert (
            run_file_release.release_owned_file(
                base, owner_id="owner", universe_id="u", file_id=refs[0]["file_id"]
            )["state"]
            == "cleanup_pending"
        )
        with runs._connect(base) as conn:
            assert conn.execute("SELECT amount,state FROM run_file_allocations").fetchone()[:] == (
                sum(map(len, bodies)),
                "releasing",
            )
        with pytest.raises(run_files.FileCustodyRefused, match="cleanup_pending"):
            run_file_release.release_owned_file(
                base, owner_id="owner", universe_id="u", file_id=refs[1]["file_id"]
            )
        # Unrelated ready siblings remain usable even while physical deletion
        # of the requested object is failing, including a new active binding.
        sibling_run = runs.create_run(
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
                run_id=sibling_run,
                owner_id="owner",
                universe_id="u",
                field_name="sibling",
                file_ids=[refs[1]["file_id"]],
            )
        for reader_run in (run_id, sibling_run):
            assert read_bound_file(
                base,
                owner_id="owner",
                universe_id="u",
                run_id=reader_run,
                file_id=refs[1]["file_id"],
                offset=0,
                count=1,
            )["eof"]
    assert (
        run_file_release.release_owned_file(
            base, owner_id="owner", universe_id="u", file_id=refs[0]["file_id"]
        )["state"]
        == "released"
    )
    assert read_bound_file(
        base,
        owner_id="owner",
        universe_id="u",
        run_id=run_id,
        file_id=refs[1]["file_id"],
        offset=0,
        count=1,
    )["eof"]


@pytest.mark.parametrize("journal", ["missing", "malformed", "includes_ready", "foreign_key"])
def test_cleanup_state_requires_exact_exclusion_for_read_and_new_binding(bound, journal):
    base, run_id, refs, _ = bound
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        operation = conn.execute("SELECT operation_id FROM run_file_operations").fetchone()[0]
        run_files.mark_cleanup_in_transaction(
            conn,
            operation_id=operation,
            owner_id="owner",
            universe_id="u",
            file_ids=[refs[0]["file_id"]],
        )
        if journal == "missing":
            conn.execute("DELETE FROM run_file_cleanup")
        else:
            value = {
                "malformed": "not json",
                "includes_ready": json.dumps([refs[1]["file_id"]]),
                "foreign_key": json.dumps(["f" * 32]),
            }[journal]
            conn.execute("UPDATE run_file_cleanup SET inventory_json=?", (value,))
    with pytest.raises(run_files.FileCustodyRefused):
        read_bound_file(
            base,
            owner_id="owner",
            universe_id="u",
            run_id=run_id,
            file_id=refs[1]["file_id"],
            offset=0,
            count=1,
        )
    with runs._connect(base) as conn:
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(run_files.FileCustodyRefused):
            run_files.bind_in_transaction(
                conn,
                run_id=run_id,
                owner_id="owner",
                universe_id="u",
                field_name="new_binding",
                file_ids=[refs[1]["file_id"]],
            )
