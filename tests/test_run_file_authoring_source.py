"""Real authoring-handle binary streaming on the native platform, no public route."""

from __future__ import annotations

import hashlib
import multiprocessing
import sqlite3
import time

import pytest

from tinyassets.authoring import service
from tinyassets.authoring.models import AuthoringAccessError
from tinyassets.authoring.store import AuthoringStore
from tinyassets.execution_authority.blob_proof import BlobProofStore
from tinyassets.run_file_sources import open_authoring_source


def _revoke_contender(base, handle, result, retry):
    store = AuthoringStore(base)
    with sqlite3.connect(store.path, timeout=0.15) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            result.put("blocked")
        else:
            result.put("unexpectedly-entered")
    if retry.wait(10):
        store.revoke_file_handle(handle, actor_id="owner")
        result.put("revoked")


@pytest.fixture
def source(tmp_path):
    store = AuthoringStore(tmp_path)
    store.initialize()
    session = service.start_session(
        actor_id="owner", artifact_kind="node", sketch="binary input", store=store
    )["session_id"]
    body = bytes(range(256)) * 12288  # 3 MiB, multi-chunk exact binary source.
    handle = store.put_file_handle(
        session_id=session,
        owner_id="owner",
        input_name="input",
        filename="Original 🧪.bin",
        media_type="application/octet-stream",
        content=body,
        lifetime_seconds=3600,
    )
    return store, session, handle, body


def test_authoring_source_exact_stream_into_private_staging(source, tmp_path):
    store, session, handle, body = source
    destination = tmp_path / "custody"
    destination.mkdir()
    target = BlobProofStore(destination)
    with open_authoring_source(
        store, owner_id="owner", session_id=session, handle_id=handle["handle_id"]
    ) as source_stream:
        ref = target.stage_stream("binary.part", source_stream.iter_chunks(), max_bytes=len(body))
        assert source_stream.metadata["filename"] == "Original 🧪.bin"
        source_stream.recheck()
    assert ref.size == len(body)
    assert ref.sha256 == hashlib.sha256(body).hexdigest()
    assert (destination / "binary.part").read_bytes() == body


@pytest.mark.parametrize(
    "change",
    [
        {"owner_id": "other"},
        {"session_id": "other"},
        {"handle_id": "../escape"},
        {"session_id": ""},
    ],
)
def test_foreign_or_incomplete_source_scope_refuses(source, change):
    store, session, handle, _ = source
    args = dict(owner_id="owner", session_id=session, handle_id=handle["handle_id"])
    args.update(change)
    with pytest.raises((AuthoringAccessError, ValueError)):
        with open_authoring_source(store, **args):
            pytest.fail("unowned source opened")


def test_revocation_between_chunks_stops_before_returning_more_bytes(source):
    store, session, handle, _ = source
    with pytest.raises(AuthoringAccessError):
        with open_authoring_source(
            store, owner_id="owner", session_id=session, handle_id=handle["handle_id"]
        ) as stream:
            chunks = stream.iter_chunks()
            assert len(next(chunks)) <= 1024 * 1024
            store.revoke_file_handle(handle["handle_id"], actor_id="owner")
            next(chunks)


def test_expiry_between_chunks_stops_and_no_writer_is_held(source, monkeypatch):
    store, session, handle, _ = source
    with pytest.raises(AuthoringAccessError):
        with open_authoring_source(
            store, owner_id="owner", session_id=session, handle_id=handle["handle_id"]
        ) as stream:
            chunks = stream.iter_chunks()
            next(chunks)
            with store._open(write=True) as conn:
                conn.execute("UPDATE authoring_file_handles SET expires_at=0")
            next(chunks)


def test_final_source_fence_orders_other_process_revocation_after_binding(source, tmp_path):
    from tinyassets.storage import run_files

    store, session, handle, body = source
    root = tmp_path / "custody"
    root.mkdir()
    conn = sqlite3.connect(tmp_path / "runs.db")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE runs(run_id TEXT PRIMARY KEY,owner_user_id TEXT,queue_universe_id TEXT)"
    )
    conn.execute("INSERT INTO runs VALUES('run','owner','universe')")
    run_files.ensure_schema(conn)
    conn.commit()
    item = run_files.CapturedFile.new(
        filename=handle["filename"],
        media_type=handle["media_type"],
        size_bytes=len(body),
        sha256=handle["sha256"],
    )
    conn.execute("BEGIN IMMEDIATE")
    run_files.reserve_in_transaction(
        conn,
        operation_id="capture",
        owner_id="owner",
        universe_id="universe",
        request_sha256="a" * 64,
        max_bytes=len(body),
        physical_root_id="root",
        ceiling_bytes=10 * len(body),
        free_bytes=10 * len(body),
        headroom_bytes=0,
    )
    run_files.inventory_in_transaction(
        conn,
        operation_id="capture",
        owner_id="owner",
        universe_id="universe",
        storage_keys=[item.file_id],
    )
    conn.commit()
    ctx = multiprocessing.get_context("spawn")
    result, retry = ctx.Queue(), ctx.Event()
    child = ctx.Process(
        target=_revoke_contender, args=(str(store.path.parent), handle["handle_id"], result, retry)
    )
    try:
        with open_authoring_source(
            store, owner_id="owner", session_id=session, handle_id=handle["handle_id"]
        ) as stream:
            blobs = BlobProofStore(root)
            staged = blobs.stage_stream(
                item.file_id + ".part", stream.iter_chunks(), max_bytes=len(body)
            )
            blobs.publish_staged(staged, item.file_id + ".body")
            with stream.commit_fence(timeout_seconds=1):
                child.start()
                assert result.get(timeout=10) == "blocked"
                conn.execute("BEGIN IMMEDIATE")
                run_files.commit_objects_in_transaction(
                    conn,
                    operation_id="capture",
                    owner_id="owner",
                    universe_id="universe",
                    objects=[item],
                )
                run_files.bind_in_transaction(
                    conn,
                    run_id="run",
                    owner_id="owner",
                    universe_id="universe",
                    field_name="file",
                    file_ids=[item.file_id],
                )
                conn.commit()
        retry.set()
        assert result.get(timeout=10) == "revoked"
        child.join(10)
        assert child.exitcode == 0
        conn.execute("BEGIN IMMEDIATE")
        assert (
            run_files.bound_file_in_transaction(
                conn, run_id="run", owner_id="owner", universe_id="universe", file_id=item.file_id
            )["sha256"]
            == item.sha256
        )
        conn.commit()
    finally:
        retry.set()
        if child.pid:
            child.join(10)
        result.close()
        conn.close()


def test_source_revoked_before_final_fence_refuses_and_wait_is_bounded(source):
    store, session, handle, _ = source
    with pytest.raises(AuthoringAccessError):
        with open_authoring_source(
            store, owner_id="owner", session_id=session, handle_id=handle["handle_id"]
        ) as stream:
            with store._open(write=True):
                started = time.monotonic()
                with pytest.raises(sqlite3.OperationalError):
                    with stream.commit_fence(timeout_seconds=0.05):
                        pytest.fail("writer fence bypassed")
                assert time.monotonic() - started < 1.0
            store.revoke_file_handle(handle["handle_id"], actor_id="owner")
            with stream.commit_fence(timeout_seconds=1):
                pytest.fail("revoked capture accepted")
