"""Red-first generic file foundation; no live accounts or file API exposure."""

from __future__ import annotations

import copy
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets import daemon_server as author
from tinyassets import workspace_pool as pool
from tinyassets.branch_versions import get_branch_version, publish_branch_version
from tinyassets.branches import BranchDefinition


def manifest():
    return {
        "inputs": [
            {
                "name": "photos",
                "io_type": "file_bundle",
                "max_count": 4,
                "max_bytes": 123456,
                "media_types": ["image/png"],
            }
        ],
        "outputs": [{"name": "result", "io_type": "file", "max_bytes": 234567}],
    }


def test_manifest_roundtrip_is_lossless_and_detached():
    original = {"branch_def_id": "files", "name": "files", "io_manifest": manifest()}
    branch = BranchDefinition.from_dict(original)
    assert branch.to_dict()["io_manifest"] == manifest()
    assert branch.graph_json()["io_manifest"] == manifest()
    original["io_manifest"]["inputs"][0]["max_count"] = 90
    assert branch.io_manifest == manifest()
    exported = branch.to_dict()
    exported["io_manifest"]["inputs"].clear()
    assert branch.io_manifest == manifest()
    assert BranchDefinition.from_json(branch.to_json()).io_manifest == manifest()


def test_legacy_manifest_stays_absent_in_serialization():
    branch = BranchDefinition.from_dict({"name": "old"})
    assert "io_manifest" not in branch.to_dict()
    assert "io_manifest" not in branch.graph_json()


@pytest.mark.parametrize("bad", [[], "files", 1, {"inputs": "file"}])
def test_malformed_manifest_refuses_instead_of_disappearing(bad):
    with pytest.raises(ValueError, match="io_manifest"):
        BranchDefinition.from_dict({"io_manifest": bad})


def test_manifest_survives_database_update_fork_and_version(tmp_path):
    author.initialize_author_server(tmp_path)
    value = {
        "branch_def_id": "files",
        "name": "files",
        "author": "alice",
        "io_manifest": manifest(),
    }
    author.save_branch_definition(tmp_path, branch_def=value)
    saved = author.get_branch_definition(tmp_path, branch_def_id="files")
    assert BranchDefinition.from_dict(saved).io_manifest == manifest()
    changed = copy.deepcopy(manifest())
    changed["inputs"][0]["max_count"] = 2
    saved = author.update_branch_definition(
        tmp_path, branch_def_id="files", updates={"io_manifest": changed}
    )
    assert BranchDefinition.from_dict(saved).io_manifest == changed
    fork = author.fork_branch_definition(tmp_path, branch_def_id="files", author="bob")
    assert BranchDefinition.from_dict(fork).io_manifest == changed
    published = publish_branch_version(tmp_path, branch_dict=saved, publisher="alice")
    version = get_branch_version(tmp_path, published.branch_version_id)
    assert BranchDefinition.from_dict(version.snapshot).io_manifest == changed


def test_byte_only_reservation_keeps_workspace_job_behavior(tmp_path):
    db = tmp_path / "runs.db"
    assert (
        pool.reserve_transfer_bytes(
            db, universe_id="u", run_id="r", operation_id="file:1", max_bytes=100
        )
        == 100
    )
    pool.reserve_operation_bytes(
        db, universe_id="u", run_id="r", operation_id="workspace:1", max_bytes=50
    )
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT kind, amount FROM workspace_ledger WHERE operation_id=?", ("file:1",)
        ).fetchall() == [(pool.KIND_BYTES, 100)]
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM workspace_ledger WHERE kind=?", (pool.KIND_JOBS,)
            ).fetchone()[0]
            == 1
        )
    assert pool.reconcile_operation_bytes(db, "file:1", 30) == 30
    # An aborted copy still consumed transport, not a zero-byte success.
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT amount, reserved FROM workspace_ledger WHERE operation_id=?", ("file:1",)
        ).fetchone() == (30, 0)


def test_byte_only_replay_cannot_borrow_another_scope(tmp_path):
    db = tmp_path / "runs.db"
    pool.reserve_transfer_bytes(
        db, universe_id="u", run_id="r", operation_id="file:1", max_bytes=100
    )
    assert (
        pool.reserve_transfer_bytes(
            db, universe_id="u", run_id="r", operation_id="file:1", max_bytes=100
        )
        == 100
    )
    for universe, run in [("foreign", "r"), ("u", "other")]:
        with pytest.raises(ValueError, match="scope"):
            pool.reserve_transfer_bytes(
                db, universe_id=universe, run_id=run, operation_id="file:1", max_bytes=100
            )


def test_byte_only_concurrent_capacity_is_shared_with_workspace(tmp_path):
    db = tmp_path / "runs.db"
    pool.reserve_operation_bytes(
        db,
        universe_id="u",
        run_id="r",
        operation_id="workspace:1",
        max_bytes=40,
        bytes_per_hour=100,
    )

    def reserve(i):
        try:
            pool.reserve_transfer_bytes(
                db,
                universe_id="u",
                run_id="r",
                operation_id=f"file:{i}",
                max_bytes=60,
                bytes_per_hour=100,
            )
            return True
        except pool.WorkspacePoolRefused:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(reserve, range(2))) == 1


def test_standalone_capture_bytes_do_not_invent_run_or_job(tmp_path):
    db = tmp_path / "runs.db"
    pool.reserve_transfer_bytes(
        db, universe_id="u", run_id="", operation_id="file:capture:owned", max_bytes=100
    )
    with pytest.raises(ValueError, match="scope"):
        pool.reserve_transfer_bytes(
            db, universe_id="u", run_id="real-run", operation_id="file:capture:owned", max_bytes=100
        )
    assert pool.reconcile_operation_bytes(db, "file:capture:owned", 37) == 37
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT kind,run_id,amount,reserved FROM workspace_ledger"
        ).fetchall() == [(pool.KIND_BYTES, "", 37, 0)]


@pytest.mark.parametrize("invalid", [None, False, 0])
def test_standalone_capture_requires_explicit_string_run_scope(tmp_path, invalid):
    with pytest.raises(ValueError, match="scope"):
        pool.reserve_transfer_bytes(
            tmp_path / "runs.db",
            universe_id="u",
            run_id=invalid,
            operation_id="file:capture:owned",
            max_bytes=100,
        )
