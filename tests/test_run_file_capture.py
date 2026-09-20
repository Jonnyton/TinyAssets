"""Standalone authoring -> immutable custody service, no public route enabled."""

import hashlib
import sqlite3

import pytest

from tinyassets import daemon_server, runs
from tinyassets.authoring import service
from tinyassets.authoring.store import AuthoringStore
from tinyassets.run_file_capture import capture_authoring_files
from tinyassets.storage import _connect as author_connection
from tinyassets.storage.run_files import FileCustodyRefused


@pytest.fixture
def intake(tmp_path, monkeypatch):
    daemon_server.initialize_author_server(tmp_path)
    with author_connection(tmp_path) as conn:
        conn.execute(
            "INSERT INTO universe_acl(universe_id,actor_id,permission,granted_at,granted_by) "
            "VALUES('u','owner','admin',1,'owner')"
        )
    store = AuthoringStore(tmp_path)
    store.initialize()
    session = service.start_session(
        actor_id="owner", artifact_kind="node", sketch="files", store=store
    )["session_id"]
    bodies = [bytes(range(256)) * 12288, b""]
    handles = [
        store.put_file_handle(
            session_id=session,
            owner_id="owner",
            input_name=f"file{i}",
            filename=f"original-{i}.bin",
            media_type="application/octet-stream",
            content=body,
            lifetime_seconds=3600,
        )
        for i, body in enumerate(bodies)
    ]
    sources = [{"session_id": session, "handle_id": handle["handle_id"]} for handle in handles]
    monkeypatch.setenv("TINYASSETS_RUN_FILE_CUSTODY_MAX_BYTES", str(64 * 1024 * 1024))
    return tmp_path, store, sources, bodies


def test_exact_atomic_multi_file_capture_replay_and_source_erasure_independence(intake):
    base, store, sources, bodies = intake
    refs = capture_authoring_files(
        base, owner_id="owner", universe_id="u", label="owned capture", sources=sources
    )
    assert len(refs) == 2
    for ref, body in zip(refs, bodies):
        assert ref["sha256"] == hashlib.sha256(body).hexdigest()
        assert ref["size_bytes"] == len(body)
        assert (base / ".run-file-custody" / (ref["file_id"] + ".body")).read_bytes() == body
    for source in sources:
        store.revoke_file_handle(source["handle_id"], actor_id="owner")
    assert (
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="owned capture", sources=sources
        )
        == refs
    )
    with runs._connect(base) as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='runs'").fetchone():
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM run_file_objects WHERE state='ready'").fetchone()[0]
            == 2
        )
        assert conn.execute("SELECT SUM(amount) FROM run_file_allocations").fetchone()[0] == sum(
            map(len, bodies)
        )
        assert conn.execute("SELECT kind,run_id,amount,reserved FROM workspace_ledger").fetchall()[
            0
        ][:] == ("bytes", "", sum(map(len, bodies)), 0)


def test_changed_request_under_same_operation_label_conflicts(intake):
    base, _, sources, _ = intake
    capture_authoring_files(base, owner_id="owner", universe_id="u", label="same", sources=sources)
    with pytest.raises(FileCustodyRefused, match="conflict"):
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="same", sources=sources[::-1]
        )


def test_foreign_principal_and_revoked_grant_refuse_before_copy(intake):
    base, _, sources, _ = intake
    with pytest.raises(FileCustodyRefused):
        capture_authoring_files(
            base, owner_id="other", universe_id="u", label="capture", sources=sources
        )
    with author_connection(base) as conn:
        conn.execute("DELETE FROM universe_acl")
    with pytest.raises(FileCustodyRefused):
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="capture", sources=sources
        )
    assert not (base / ".run-file-custody").exists()


def test_authority_revoke_during_stream_leaves_no_visible_bundle_and_counts_bytes(
    intake, monkeypatch
):
    from tinyassets.execution_authority.blob_proof import BlobProofStore

    base, _, sources, bodies = intake
    real_stage = BlobProofStore.stage_stream

    def stage(self, name, chunks, **kwargs):
        def revoke_after_first_chunk():
            iterator = iter(chunks)
            yield next(iterator)
            with author_connection(base) as conn:
                conn.execute("DELETE FROM universe_acl")
            yield from iterator

        return real_stage(self, name, revoke_after_first_chunk(), **kwargs)

    monkeypatch.setattr(BlobProofStore, "stage_stream", stage)
    with pytest.raises(Exception):
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="capture", sources=sources
        )
    with sqlite3.connect(runs.runs_db_path(base)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM run_file_objects").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM run_file_operations").fetchone()[0] == "cleanup"
        charged = conn.execute("SELECT amount,reserved FROM workspace_ledger").fetchone()
        assert charged[0] > 0 and charged[0] <= len(bodies[0]) and charged[1] == 0
        assert conn.execute("SELECT COUNT(*) FROM run_file_cleanup").fetchone()[0] == 1


def test_enospc_preserves_consumed_transport_and_owned_cleanup_debt(intake, monkeypatch):
    import errno

    from tinyassets.execution_authority import blob_stream

    base, _, sources, _ = intake
    real_write = blob_stream.os.write
    failed = False

    def disk_full(fd, data):
        nonlocal failed
        if len(data) > 1000 and not failed:
            failed = True
            real_write(fd, data[:123])
            raise OSError(errno.ENOSPC, "fixture disk full")
        return real_write(fd, data)

    monkeypatch.setattr(blob_stream.os, "write", disk_full)
    with pytest.raises(blob_stream.BlobStreamError):
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="full", sources=sources
        )
    with runs._connect(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM run_file_objects").fetchone()[0] == 0
        assert conn.execute("SELECT amount,reserved FROM workspace_ledger").fetchone()[:] == (
            1024 * 1024,
            0,
        )
        # No unproved physical refund: exactly inventoried partial bytes remain.
        assert conn.execute("SELECT state FROM run_file_allocations").fetchone()[0] == "releasing"
    partials = list((base / ".run-file-custody").glob("*.part"))
    assert len(partials) == 1 and partials[0].stat().st_size == 123


def test_failure_after_publication_before_metadata_commit_never_exposes_bundle(intake, monkeypatch):
    from tinyassets.storage import run_files

    base, _, sources, _ = intake

    def refuse(*args, **kwargs):
        raise ValueError("fault before acceptance")

    monkeypatch.setattr(run_files, "commit_objects_in_transaction", refuse)
    with pytest.raises(ValueError, match="fault before acceptance"):
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="fault", sources=sources
        )
    assert len(list((base / ".run-file-custody").glob("*.body"))) == 2
    with runs._connect(base) as conn:
        assert conn.execute("SELECT COUNT(*) FROM run_file_objects").fetchone()[0] == 0
        assert conn.execute("SELECT state FROM run_file_operations").fetchone()[0] == "cleanup"
    with pytest.raises(FileCustodyRefused, match="recovery_required"):
        capture_authoring_files(
            base, owner_id="owner", universe_id="u", label="fault", sources=sources
        )
