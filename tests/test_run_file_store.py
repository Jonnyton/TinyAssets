"""Internal custody transactions, not proof of physical streaming or public intake."""

from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets.storage import run_files as files


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "runs.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE runs(run_id TEXT PRIMARY KEY, owner_user_id TEXT, "
            "queue_universe_id TEXT, inputs_json TEXT, status TEXT)"
        )
        conn.executemany(
            "INSERT INTO runs VALUES(?,?,?,'{}','queued')",
            [("r", "alice", "u"), ("child", "alice", "u"), ("foreign", "bob", "v")],
        )
        files.ensure_schema(conn)
    return path


def connection(db):
    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("BEGIN IMMEDIATE")
    return conn


def reserve(conn, **overrides):
    args = dict(
        operation_id="op",
        owner_id="alice",
        universe_id="u",
        request_sha256="a" * 64,
        max_bytes=30,
        physical_root_id="root",
        ceiling_bytes=100,
        free_bytes=1000,
        headroom_bytes=10,
    )
    args.update(overrides)
    return files.reserve_in_transaction(conn, **args)


def new_file(size=20):
    return files.CapturedFile.new(
        filename="original\u2603.bin",
        media_type="application/x-custom",
        size_bytes=size,
        sha256=hashlib.sha256(b"x" * size).hexdigest(),
    )


def inventory(conn, *objects):
    files.inventory_in_transaction(
        conn,
        operation_id="op",
        owner_id="alice",
        universe_id="u",
        storage_keys=[item.file_id for item in objects],
    )


def test_capacity_configuration_is_explicit_and_not_a_tier(monkeypatch):
    monkeypatch.delenv("TINYASSETS_RUN_FILE_CUSTODY_MAX_BYTES", raising=False)
    monkeypatch.setenv("TINYASSETS_FREE_STORAGE_MB", "999999")
    with pytest.raises(files.FileCustodyRefused, match="not_configured"):
        files.capacity_limit()
    for value in ("0", "-1", "1.5", "NaN", "true", "9223372036854775808"):
        monkeypatch.setenv("TINYASSETS_RUN_FILE_CUSTODY_MAX_BYTES", value)
        with pytest.raises(files.FileCustodyRefused, match="invalid"):
            files.capacity_limit()
    monkeypatch.setenv("TINYASSETS_RUN_FILE_CUSTODY_MAX_BYTES", "300")
    assert files.capacity_limit() == 300


def test_requires_transaction_before_any_reservation(db):
    with sqlite3.connect(db) as conn:
        with pytest.raises(ValueError, match="transaction"):
            reserve(conn)


def test_replay_is_scoped_and_immutable(db):
    with connection(db) as conn:
        first = reserve(conn)
        assert reserve(conn) == first
        for override in (
            {"owner_id": "bob"},
            {"universe_id": "v"},
            {"request_sha256": "b" * 64},
            {"max_bytes": 31},
            {"physical_root_id": "other"},
        ):
            with pytest.raises(files.FileCustodyRefused, match="conflict"):
                reserve(conn, **override)
        assert conn.execute("SELECT COUNT(*) FROM run_file_operations").fetchone()[0] == 1


def test_pending_capacity_is_atomic_between_connections(db):
    def contender(index):
        with connection(db) as conn:
            try:
                reserve(conn, operation_id=f"op{index}", max_bytes=60)
                return True
            except files.FileCustodyRefused:
                return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(contender, range(2))) == 1


def test_unknown_and_insufficient_free_space_refuse(db):
    with connection(db) as conn:
        for free in (None, 0, 39):
            with pytest.raises(files.FileCustodyRefused):
                reserve(conn, free_bytes=free)
        assert conn.execute("SELECT COUNT(*) FROM run_file_operations").fetchone()[0] == 0


def test_complete_and_bind_is_atomic_independent_of_receipt(db):
    captured = new_file()
    with connection(db) as conn:
        reserve(conn)
        inventory(conn, captured)
        files.commit_objects_in_transaction(
            conn, operation_id="op", owner_id="alice", universe_id="u", objects=[captured]
        )
        files.bind_in_transaction(
            conn,
            run_id="r",
            owner_id="alice",
            universe_id="u",
            field_name="upload",
            file_ids=[captured.file_id],
        )
    with connection(db) as conn:
        actual = files.bound_file_in_transaction(
            conn, run_id="r", owner_id="alice", universe_id="u", file_id=captured.file_id
        )
        assert actual["filename"] == "original\u2603.bin"
        assert actual["size_bytes"] == 20
        # No personal receipt tables even exist in this fixture.
        files.bind_in_transaction(
            conn,
            run_id="child",
            owner_id="alice",
            universe_id="u",
            field_name="copy",
            file_ids=[captured.file_id],
        )
        assert conn.execute("SELECT SUM(amount) FROM run_file_allocations").fetchone()[0] == 20
        for owner, universe, run in [("bob", "v", "foreign"), ("alice", "v", "r")]:
            with pytest.raises(files.FileCustodyRefused, match="not_found"):
                files.bound_file_in_transaction(
                    conn, run_id=run, owner_id=owner, universe_id=universe, file_id=captured.file_id
                )


def test_bad_bundle_never_leaves_partial_objects_even_if_error_caught(db):
    with connection(db) as conn:
        reserve(conn)
        with pytest.raises(files.FileCustodyRefused, match="limit"):
            files.commit_objects_in_transaction(
                conn,
                operation_id="op",
                owner_id="alice",
                universe_id="u",
                objects=[new_file(20), new_file(20)],
            )
        assert conn.execute("SELECT COUNT(*) FROM run_file_objects").fetchone()[0] == 0
        assert conn.execute("SELECT amount FROM run_file_allocations").fetchone()[0] == 30


def test_binding_rejects_forged_run_owner_and_changed_field(db):
    with connection(db) as conn:
        reserve(conn)
        one, two = new_file(10), new_file(10)
        inventory(conn, one, two)
        files.commit_objects_in_transaction(
            conn, operation_id="op", owner_id="alice", universe_id="u", objects=[one, two]
        )
        with pytest.raises(files.FileCustodyRefused, match="not_found"):
            files.bind_in_transaction(
                conn,
                run_id="foreign",
                owner_id="alice",
                universe_id="u",
                field_name="upload",
                file_ids=[one.file_id],
            )
        files.bind_in_transaction(
            conn,
            run_id="r",
            owner_id="alice",
            universe_id="u",
            field_name="upload",
            file_ids=[one.file_id],
        )
        with pytest.raises(files.FileCustodyRefused, match="conflict"):
            files.bind_in_transaction(
                conn,
                run_id="r",
                owner_id="alice",
                universe_id="u",
                field_name="upload",
                file_ids=[two.file_id],
            )


def test_retained_bytes_not_subtracted_twice_from_free_space(db):
    with connection(db) as conn:
        reserve(conn, max_bytes=60)
        captured = new_file(60)
        inventory(conn, captured)
        files.commit_objects_in_transaction(
            conn, operation_id="op", owner_id="alice", universe_id="u", objects=[captured]
        )
        reserve(conn, operation_id="new", max_bytes=30, free_bytes=40)


def test_cleanup_debt_retains_allocation_until_verified(db):
    with connection(db) as conn:
        reserve(conn)
        files.mark_cleanup_in_transaction(
            conn, operation_id="op", owner_id="alice", universe_id="u"
        )
        assert conn.execute("SELECT state FROM run_file_operations").fetchone()[0] == "cleanup"
        assert conn.execute("SELECT amount FROM run_file_allocations").fetchone()[0] == 30
        with pytest.raises(files.FileCustodyRefused, match="cleanup"):
            reserve(conn)
        # Physical cleanup evidence is supplied only by the future held-operation collector.
        files.finish_cleanup_in_transaction(
            conn, operation_id="op", owner_id="alice", universe_id="u"
        )
        assert conn.execute("SELECT SUM(amount) FROM run_file_allocations").fetchone()[0] == 0


def test_completed_custody_rejects_republication(db):
    with connection(db) as conn:
        reserve(conn)
        one = new_file()
        inventory(conn, one)
        files.commit_objects_in_transaction(
            conn, operation_id="op", owner_id="alice", universe_id="u", objects=[one]
        )
        assert files.commit_objects_in_transaction(
            conn, operation_id="op", owner_id="alice", universe_id="u", objects=[one]
        ) == [one.file_id]
        with pytest.raises(files.FileCustodyRefused, match="conflict"):
            files.commit_objects_in_transaction(
                conn, operation_id="op", owner_id="alice", universe_id="u", objects=[new_file()]
            )
