from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

try:
    from tinyassets.execution_authority import evidence_store as _evidence_store
except ModuleNotFoundError:
    _evidence_store = None


_TEST_KEY = b"d0-execution-evidence-test-key"


@pytest.fixture
def evidence_api() -> ModuleType:
    assert _evidence_store is not None, "D0 execution evidence store is not implemented"
    return _evidence_store


@pytest.fixture
def connection(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        tmp_path / "execution-evidence.sqlite",
        timeout=0.05,
    )
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _payload(
    *,
    job_id: str = "job-1",
    generation: int = 1,
    fence: int = 1,
    idempotency_key: str = "complete-1",
    terminal_state: str = "succeeded",
    result_digest: str = "a" * 64,
) -> dict[str, Any]:
    return {
        "fence": fence,
        "generation": generation,
        "idempotency_key": idempotency_key,
        "job_id": job_id,
        "result_digest": result_digest,
        "terminal_state": terminal_state,
    }


def _signed_fact(payload: dict[str, Any], *, key: bytes = _TEST_KEY) -> bytes:
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()
    return json.dumps(
        {"payload": payload, "signature": signature},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _verifier(api: ModuleType) -> Callable[[bytes], Any | None]:
    def verify(fact_bytes: bytes) -> Any | None:
        try:
            envelope = json.loads(fact_bytes)
            payload = envelope["payload"]
            signature = envelope["signature"]
            payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        expected = hmac.new(_TEST_KEY, payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        return api.VerifiedTerminalView(
            job_id=payload["job_id"],
            generation=payload["generation"],
            fence=payload["fence"],
            idempotency_key=payload["idempotency_key"],
            fact_digest=hashlib.sha256(payload_bytes).hexdigest(),
            terminal_state=payload["terminal_state"],
            result_digest=payload["result_digest"],
        )

    return verify


def _store(
    api: ModuleType,
    connection: sqlite3.Connection,
    *,
    initialize: bool = True,
) -> Any:
    return api.ExecutionEvidenceStore(
        _database_path(connection),
        initialize=initialize,
    )


def _database_path(connection: sqlite3.Connection) -> Path:
    row = connection.execute("PRAGMA main.database_list").fetchone()
    assert row is not None and row[2]
    return Path(row[2])


def _external_begin_immediate(database: Path) -> subprocess.CompletedProcess[str]:
    script = """
import sqlite3
import sys

connection = sqlite3.connect(sys.argv[1], timeout=0, isolation_level=None)
try:
    connection.execute("BEGIN IMMEDIATE")
except sqlite3.OperationalError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(73)
else:
    connection.rollback()
"""
    return subprocess.run(
        [sys.executable, "-c", script, str(database)],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


def test_generation_and_fence_floor_survives_mutable_projection_restore(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    first = store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    second = store.allocate_lease(job_id="job-1", lease_id="lease-2", evidence_bytes=b"lease-two")
    assert (first.generation, first.fence) == (1, 1)
    assert (second.generation, second.fence) == (2, 2)

    connection.execute(
        """
        UPDATE execution_lease_projection
        SET generation = 1, fence = 1, lease_id = 'restored-lease'
        WHERE job_id = 'job-1'
        """
    )
    connection.commit()

    third = store.allocate_lease(job_id="job-1", lease_id="lease-3", evidence_bytes=b"lease-three")
    assert (third.generation, third.fence) == (3, 3)


def test_superseded_signed_terminal_cannot_pass_after_projection_restore(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )
    current = store.replay_terminal("job-1", _verifier(evidence_api))
    assert current is not None

    store.allocate_lease(job_id="job-1", lease_id="lease-2", evidence_bytes=b"lease-two")
    connection.execute(
        """
        UPDATE execution_lease_projection
        SET generation = 1, fence = 1, lease_id = 'restored-lease'
        WHERE job_id = 'job-1'
        """
    )
    connection.commit()

    assert store.replay_terminal("job-1", _verifier(evidence_api)) is None


@pytest.mark.parametrize("table", ["execution_lease_events", "execution_terminal_evidence"])
@pytest.mark.parametrize("mutation", ["update", "delete", "replace", "upsert"])
def test_evidence_tables_reject_replacement_and_mutation(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
    table: str,
    mutation: str,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )

    if table == "execution_lease_events":
        statements = {
            "update": "UPDATE execution_lease_events SET evidence_bytes=X'00'",
            "delete": "DELETE FROM execution_lease_events",
            "replace": """
                INSERT OR REPLACE INTO execution_lease_events
                    (event_id, job_id, lease_id, generation, fence,
                     evidence_bytes, recorded_at_ns)
                VALUES ('job-1:1:1', 'job-1', 'lease-1', 1, 1, X'00', 1)
            """,
            "upsert": """
                INSERT INTO execution_lease_events
                    (event_id, job_id, lease_id, generation, fence,
                     evidence_bytes, recorded_at_ns)
                VALUES ('job-1:1:1', 'job-1', 'lease-1', 1, 1, X'00', 1)
                ON CONFLICT(event_id) DO UPDATE SET evidence_bytes=X'00'
            """,
        }
    else:
        statements = {
            "update": "UPDATE execution_terminal_evidence SET fact_bytes=X'00'",
            "delete": "DELETE FROM execution_terminal_evidence",
            "replace": """
                INSERT OR REPLACE INTO execution_terminal_evidence
                    (evidence_id, job_id, fact_bytes, recorded_at_ns)
                VALUES ('terminal-1', 'job-1', X'00', 1)
            """,
            "upsert": """
                INSERT INTO execution_terminal_evidence
                    (evidence_id, job_id, fact_bytes, recorded_at_ns)
                VALUES ('terminal-1', 'job-1', X'00', 1)
                ON CONFLICT(evidence_id) DO UPDATE SET fact_bytes=X'00'
            """,
        }

    with pytest.raises(sqlite3.IntegrityError, match="append_only"):
        connection.execute(statements[mutation])


@pytest.mark.parametrize(
    "tamper_sql",
    [
        "DROP INDEX ux_execution_lease_events_job_fence",
        "DROP TRIGGER execution_terminal_evidence_no_update",
        """
        CREATE INDEX unexpected_execution_terminal_index
        ON execution_terminal_evidence(recorded_at_ns)
        """,
    ],
)
def test_exact_schema_validation_rejects_missing_or_extra_owned_objects(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
    tamper_sql: str,
) -> None:
    store = _store(evidence_api, connection)
    connection.execute(tamper_sql)
    connection.commit()

    with pytest.raises(evidence_api.EvidenceSchemaError):
        store.current_floor("job-1")


def test_exact_schema_validation_rejects_wrong_preexisting_table(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    connection.execute("CREATE TABLE execution_lease_events (event_id TEXT PRIMARY KEY)")
    connection.commit()

    with pytest.raises(evidence_api.EvidenceSchemaError):
        _store(evidence_api, connection)

    columns = connection.execute("PRAGMA table_info(execution_lease_events)").fetchall()
    assert [column["name"] for column in columns] == ["event_id"]


def test_external_temp_shadow_cannot_enter_the_owned_connection(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    connection.execute("CREATE TEMP TABLE execution_terminal_evidence (evidence_id TEXT)")

    assert store.current_floor("job-1") == evidence_api.EvidenceFloor(0, 0)


def test_replay_ignores_junk_and_collapses_identical_valid_facts(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    fact = _signed_fact(_payload())
    store.append_terminal_evidence(evidence_id="junk", job_id="job-1", fact_bytes=b"not-json")
    store.append_terminal_evidence(evidence_id="terminal-1", job_id="job-1", fact_bytes=fact)
    store.append_terminal_evidence(
        evidence_id="terminal-duplicate", job_id="job-1", fact_bytes=fact
    )

    first = store.replay_terminal("job-1", _verifier(evidence_api))
    second = store.replay_terminal("job-1", _verifier(evidence_api))

    assert first is not None
    assert first == second
    assert first.job_id == "job-1"
    assert first.generation == 1
    assert first.fence == 1
    assert first.idempotency_key == "complete-1"


def test_replay_rederives_receipt_after_mutable_terminal_projection_reset(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )
    receipt = store.replay_terminal("job-1", _verifier(evidence_api))
    assert receipt is not None

    connection.execute(
        """
        UPDATE execution_terminal_projection
        SET receipt_id='restored', fact_digest=?, generation=0, fence=0
        WHERE job_id='job-1'
        """,
        ("0" * 64,),
    )
    connection.commit()

    replayed = store.replay_terminal("job-1", _verifier(evidence_api))
    assert replayed == receipt
    projection = connection.execute(
        """
        SELECT receipt_id, fact_digest, generation, fence
        FROM execution_terminal_projection WHERE job_id='job-1'
        """
    ).fetchone()
    assert dict(projection) == {
        "receipt_id": receipt.receipt_id,
        "fact_digest": receipt.fact_digest,
        "generation": 1,
        "fence": 1,
    }


def test_same_idempotency_key_with_changed_verified_fact_conflicts(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )
    store.append_terminal_evidence(
        evidence_id="terminal-2",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload(result_digest="b" * 64)),
    )

    with pytest.raises(evidence_api.IdempotencyConflictError):
        store.replay_terminal("job-1", _verifier(evidence_api))


def test_distinct_valid_terminal_facts_are_stored_state_corruption(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload(idempotency_key="complete-1")),
    )
    store.append_terminal_evidence(
        evidence_id="terminal-2",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload(idempotency_key="complete-2", result_digest="b" * 64)),
    )

    with pytest.raises(evidence_api.StoredTerminalCorruptionError):
        store.replay_terminal("job-1", _verifier(evidence_api))


@pytest.mark.parametrize("operation", ["allocate", "append", "replay"])
def test_schema_is_revalidated_inside_the_decision_transaction(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    store = _store(evidence_api, connection)
    if operation in {"append", "replay"}:
        store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    if operation == "replay":
        store.append_terminal_evidence(
            evidence_id="terminal-1",
            job_id="job-1",
            fact_bytes=_signed_fact(_payload()),
        )

    original_transaction = store._transaction
    tampered = False

    @contextmanager
    def tamper_immediately_before_transaction():
        nonlocal tampered
        if not tampered:
            connection.execute("DROP TRIGGER execution_terminal_evidence_no_update")
            connection.commit()
            tampered = True
        with original_transaction():
            yield

    monkeypatch.setattr(store, "_transaction", tamper_immediately_before_transaction)
    actions = {
        "allocate": lambda: store.allocate_lease(
            job_id="job-1", lease_id="lease-race", evidence_bytes=b"lease-race"
        ),
        "append": lambda: store.append_terminal_evidence(
            evidence_id="terminal-race",
            job_id="job-1",
            fact_bytes=_signed_fact(_payload()),
        ),
        "replay": lambda: store.replay_terminal("job-1", _verifier(evidence_api)),
    }

    with pytest.raises(evidence_api.EvidenceSchemaError):
        actions[operation]()

    if operation == "allocate":
        assert connection.execute("SELECT COUNT(*) FROM execution_lease_events").fetchone()[0] == 0
    elif operation == "append":
        assert (
            connection.execute("SELECT COUNT(*) FROM execution_terminal_evidence").fetchone()[0]
            == 0
        )


def test_idempotency_key_cannot_change_fact_across_generations(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-generation-1",
        job_id="job-1",
        fact_bytes=_signed_fact(
            _payload(
                generation=1,
                fence=1,
                idempotency_key="complete-stable",
                result_digest="a" * 64,
            )
        ),
    )
    store.allocate_lease(job_id="job-1", lease_id="lease-2", evidence_bytes=b"lease-two")
    store.append_terminal_evidence(
        evidence_id="terminal-generation-2",
        job_id="job-1",
        fact_bytes=_signed_fact(
            _payload(
                generation=2,
                fence=2,
                idempotency_key="complete-stable",
                result_digest="b" * 64,
            )
        ),
    )

    with pytest.raises(evidence_api.IdempotencyConflictError):
        store.replay_terminal("job-1", _verifier(evidence_api))


def test_erased_authority_schema_is_not_treated_as_a_virgin_database(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    database = tmp_path / "erased-authority.sqlite"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    for table in (
        "execution_lease_projection",
        "execution_terminal_projection",
        "execution_lease_events",
        "execution_terminal_evidence",
    ):
        connection.execute(f"DROP TABLE {table}")
    connection.commit()
    connection.close()

    restored = sqlite3.connect(database)
    restored.row_factory = sqlite3.Row
    try:
        with pytest.raises(evidence_api.EvidenceSchemaError):
            _store(evidence_api, restored, initialize=False)
        assert (
            restored.execute(
                """
            SELECT COUNT(*) FROM main.sqlite_master
            WHERE name LIKE 'execution_%'
            """
            ).fetchone()[0]
            == 0
        )
    finally:
        restored.close()


def test_authority_namespace_marker_tamper_fails_closed(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    connection.execute("PRAGMA application_id = 0")
    connection.commit()

    with pytest.raises(evidence_api.EvidenceSchemaError, match="namespace"):
        store.current_floor("job-1")


def test_external_temp_shadow_cannot_block_main_schema_creation(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    connection.execute("CREATE TEMP TABLE execution_terminal_evidence (evidence_id TEXT)")

    store = _store(evidence_api, connection)

    assert (
        connection.execute(
            """
        SELECT COUNT(*) FROM main.sqlite_master
        WHERE name LIKE 'execution_%'
        """
        ).fetchone()[0]
        > 0
    )
    assert store.current_floor("job-1") == evidence_api.EvidenceFloor(0, 0)
    assert (
        connection.execute(
            """
        SELECT COUNT(*) FROM temp.sqlite_master
        WHERE name = 'execution_terminal_evidence'
        """
        ).fetchone()[0]
        == 1
    )


def test_concurrent_allocations_serialize_to_distinct_monotonic_floors(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    database = tmp_path / "concurrent-authority.sqlite"
    first_connection = sqlite3.connect(database, check_same_thread=False, timeout=5)
    second_connection = sqlite3.connect(database, check_same_thread=False, timeout=5)
    first_store = _store(evidence_api, first_connection)
    second_store = _store(evidence_api, second_connection, initialize=False)
    barrier = threading.Barrier(2)

    def allocate(store: Any, lease_id: str) -> Any:
        barrier.wait(timeout=5)
        return store.allocate_lease(
            job_id="job-1",
            lease_id=lease_id,
            evidence_bytes=lease_id.encode("utf-8"),
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (
                pool.submit(allocate, first_store, "lease-1"),
                pool.submit(allocate, second_store, "lease-2"),
            )
            allocations = tuple(future.result(timeout=5) for future in futures)
        assert {(allocation.generation, allocation.fence) for allocation in allocations} == {
            (1, 1),
            (2, 2),
        }
        assert first_store.current_floor("job-1") == evidence_api.EvidenceFloor(
            generation=2, fence=2
        )
    finally:
        first_connection.close()
        second_connection.close()


def test_public_transaction_validates_and_allows_nested_store_operations(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)

    with store.transaction():
        allocation = store.allocate_lease(
            job_id="job-1",
            lease_id="lease-1",
            evidence_bytes=b"lease-one",
        )
        store.append_terminal_evidence(
            evidence_id="terminal-1",
            job_id="job-1",
            fact_bytes=_signed_fact(_payload()),
        )

    assert (allocation.generation, allocation.fence) == (1, 1)
    assert store.replay_terminal("job-1", _verifier(evidence_api)) is not None


def test_replay_rejects_same_store_reentrant_mutation_and_rolls_it_back(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )
    verify_fact = _verifier(evidence_api)

    def reentrant_verifier(fact_bytes: bytes) -> Any | None:
        store.allocate_lease(
            job_id="job-1",
            lease_id="lease-reentrant",
            evidence_bytes=b"lease-reentrant",
        )
        return verify_fact(fact_bytes)

    with pytest.raises(RuntimeError, match="reentrant"):
        store.replay_terminal("job-1", reentrant_verifier)

    assert store.current_floor("job-1") == evidence_api.EvidenceFloor(
        generation=1,
        fence=1,
    )


def test_replay_rejects_direct_connection_mutation_from_verifier_callback(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )
    verify_fact = _verifier(evidence_api)

    def advancing_verifier(fact_bytes: bytes) -> Any | None:
        connection.execute(
            """
            INSERT INTO execution_lease_events (
                event_id, job_id, lease_id, generation, fence,
                evidence_bytes, recorded_at_ns
            ) VALUES ('job-1:2:2', 'job-1', 'lease-direct', 2, 2, X'01', 1)
            """
        )
        return verify_fact(fact_bytes)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        store.replay_terminal("job-1", advancing_verifier)

    assert store.current_floor("job-1") == evidence_api.EvidenceFloor(
        generation=1,
        fence=1,
    )
    assert (
        connection.execute(
            """
        SELECT COUNT(*) FROM execution_terminal_projection
        WHERE job_id = 'job-1'
        """
        ).fetchone()[0]
        == 0
    )


def test_one_thread_cannot_savepoint_inside_another_threads_transaction(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    connection = sqlite3.connect(
        tmp_path / "shared-connection.sqlite",
        check_same_thread=False,
        timeout=5,
    )
    connection.row_factory = sqlite3.Row
    store = _store(evidence_api, connection)
    started = threading.Event()
    finished = threading.Event()

    def allocate() -> Any:
        started.set()
        try:
            return store.allocate_lease(
                job_id="job-1",
                lease_id="lease-worker",
                evidence_bytes=b"lease-worker",
            )
        finally:
            finished.set()

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        with store.transaction():
            future = pool.submit(allocate)
            assert started.wait(5)
            worker_was_blocked = not finished.wait(0.25)
        allocation = future.result(timeout=5)
        assert worker_was_blocked
        assert (allocation.generation, allocation.fence) == (1, 1)
    finally:
        pool.shutdown(wait=True)
        connection.close()


def test_opening_a_virgin_database_requires_explicit_initialization(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(evidence_api.EvidenceSchemaError, match="namespace|initial"):
        evidence_api.ExecutionEvidenceStore(_database_path(connection))

    assert (
        connection.execute(
            """
        SELECT COUNT(*) FROM main.sqlite_master
        WHERE name LIKE 'execution_%'
        """
        ).fetchone()[0]
        == 0
    )


def test_explicit_initialization_creates_the_first_authority_schema(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = evidence_api.ExecutionEvidenceStore(
        _database_path(connection),
        initialize=True,
    )

    assert store.current_floor("job-1") == evidence_api.EvidenceFloor(0, 0)


def test_erasing_schema_and_namespace_marker_cannot_trigger_reinitialization(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    database = tmp_path / "fully-erased-authority.sqlite"
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    for table in (
        "execution_lease_projection",
        "execution_terminal_projection",
        "execution_lease_events",
        "execution_terminal_evidence",
    ):
        connection.execute(f"DROP TABLE {table}")
    connection.execute("PRAGMA application_id = 0")
    connection.commit()
    connection.close()

    restored = sqlite3.connect(database)
    try:
        with pytest.raises(evidence_api.EvidenceSchemaError, match="namespace|initial"):
            evidence_api.ExecutionEvidenceStore(_database_path(restored))
        assert (
            restored.execute(
                """
            SELECT COUNT(*) FROM main.sqlite_master
            WHERE name LIKE 'execution_%'
            """
            ).fetchone()[0]
            == 0
        )
    finally:
        restored.close()


def test_verifier_callback_cannot_commit_schema_mutation(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )
    verify_fact = _verifier(evidence_api)

    def committing_verifier(fact_bytes: bytes) -> Any | None:
        connection.set_authorizer(None)
        try:
            connection.execute("DROP TRIGGER execution_terminal_evidence_no_update")
        finally:
            connection.commit()
        return verify_fact(fact_bytes)

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        store.replay_terminal("job-1", committing_verifier)

    assert (
        connection.execute(
            """
        SELECT COUNT(*) FROM main.sqlite_master
        WHERE type = 'trigger'
          AND name = 'execution_terminal_evidence_no_update'
        """
        ).fetchone()[0]
        == 1
    )
    assert store.current_floor("job-1") == evidence_api.EvidenceFloor(1, 1)


def test_store_does_not_replace_an_external_connection_authorizer(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    authorizer_calls = 0

    def prior_authorizer(
        _action: int,
        _argument_one: str | None,
        _argument_two: str | None,
        _database_name: str | None,
        _trigger_name: str | None,
    ) -> int:
        nonlocal authorizer_calls
        authorizer_calls += 1
        return sqlite3.SQLITE_OK

    connection.set_authorizer(prior_authorizer)
    store = _store(evidence_api, connection)
    store.allocate_lease(job_id="job-1", lease_id="lease-1", evidence_bytes=b"lease-one")
    store.append_terminal_evidence(
        evidence_id="terminal-1",
        job_id="job-1",
        fact_bytes=_signed_fact(_payload()),
    )
    store.replay_terminal("job-1", _verifier(evidence_api))
    calls_before_external_query = authorizer_calls

    connection.execute("SELECT 1").fetchone()

    assert authorizer_calls > calls_before_external_query


def test_store_requires_a_database_path_instead_of_connection_authority(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(TypeError, match="filesystem path"):
        evidence_api.ExecutionEvidenceStore(connection, initialize=True)


def test_store_rejects_hardlinked_database_path(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    original = tmp_path / "original.sqlite"
    original.touch()
    hardlink = tmp_path / "hardlink.sqlite"
    hardlink.hardlink_to(original)

    with pytest.raises(evidence_api.EvidenceSchemaError, match="hardlinked"):
        evidence_api.ExecutionEvidenceStore(hardlink, initialize=True)


def test_store_rejects_symlinked_database_path(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    original = tmp_path / "original.sqlite"
    original.touch()
    symlink = tmp_path / "symlink.sqlite"
    try:
        symlink.symlink_to(original)
    except OSError as exc:
        pytest.skip(f"this host cannot create file symlinks: {exc}")

    with pytest.raises(evidence_api.EvidenceSchemaError, match="plain|secure"):
        evidence_api.ExecutionEvidenceStore(symlink, initialize=True)


def test_store_rejects_database_check_use_swap(
    evidence_api: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "swapped.sqlite"
    database.touch()
    original_connect = evidence_api.sqlite3.connect

    def swapping_connect(path: Path, *args: Any, **kwargs: Any):
        displaced = database.with_name("displaced.sqlite")
        try:
            database.replace(displaced)
        except PermissionError as exc:
            raise evidence_api.EvidenceSchemaError(
                "database was held against a check/use swap"
            ) from exc
        database.touch()
        return original_connect(path, *args, **kwargs)

    monkeypatch.setattr(evidence_api.sqlite3, "connect", swapping_connect)

    with pytest.raises(
        evidence_api.EvidenceSchemaError,
        match="changed while opening|held against",
    ):
        evidence_api.ExecutionEvidenceStore(database, initialize=True)


def test_invalid_parent_path_is_not_created(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    database = tmp_path / "missing" / "authority.sqlite"

    # Match the stable prefix, not the platform-specific tail. The guard has
    # ~10 distinct messages and which one fires for a missing parent depends on
    # the OS's directory-open path (Linux picked an "ancestor" wording, so
    # match="parent" failed there). "evidence database" still pins that this is
    # the evidence-store guard rather than some unrelated error.
    with pytest.raises(evidence_api.EvidenceSchemaError, match="evidence database"):
        evidence_api.ExecutionEvidenceStore(database, initialize=True)

    # These two are the invariant the test is NAMED for, and they are exact:
    # a rejected open must not have created anything on the way to failing.
    assert not database.parent.exists()
    assert not database.exists()


def test_initialize_false_does_not_create_an_absent_database(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    database = tmp_path / "absent.sqlite"

    with pytest.raises(evidence_api.EvidenceSchemaError, match="absent"):
        evidence_api.ExecutionEvidenceStore(database)

    assert not database.exists()


def test_intermediate_ancestor_alias_is_rejected_during_construction(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first-root"
    (first_root / "state").mkdir(parents=True)
    alias = tmp_path / "authority-alias"
    if os.name == "nt":
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(alias), str(first_root)],
            capture_output=True,
            check=False,
            text=True,
        )
        if created.returncode:
            pytest.skip(f"this host cannot create a directory junction: {created.stderr}")
    else:
        alias.symlink_to(first_root, target_is_directory=True)

    database = alias / "state" / "authority.sqlite"
    with pytest.raises(
        evidence_api.EvidenceSchemaError,
        match="alias|reparse|ancestor",
    ):
        evidence_api.ExecutionEvidenceStore(database, initialize=True)


@pytest.mark.skipif(os.name == "nt", reason="POSIX SQLite lock semantics")
def test_closing_second_store_does_not_release_first_store_lock(
    evidence_api: ModuleType,
    tmp_path: Path,
) -> None:
    database = tmp_path / "authority.sqlite"
    first = evidence_api.ExecutionEvidenceStore(database, initialize=True)
    second = evidence_api.ExecutionEvidenceStore(database)
    try:
        with first.transaction():
            second.close()
            external = _external_begin_immediate(database)
            assert external.returncode == 73, external.stderr
            assert "locked" in external.stderr
    finally:
        first.close()
        second.close()


@pytest.mark.skipif(os.name == "nt", reason="POSIX SQLite lock semantics")
def test_failed_second_construction_preserves_lock_without_fd_leak(
    evidence_api: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "authority.sqlite"
    first = evidence_api.ExecutionEvidenceStore(database, initialize=True)
    original_connect = evidence_api.sqlite3.connect
    fd_root = Path("/proc/self/fd")
    before_fds = len(tuple(fd_root.iterdir())) if fd_root.is_dir() else None

    def failing_connect(*args: Any, **kwargs: Any):
        raise sqlite3.OperationalError("injected construction failure")

    try:
        with first.transaction():
            monkeypatch.setattr(evidence_api.sqlite3, "connect", failing_connect)
            with pytest.raises(sqlite3.OperationalError, match="injected"):
                evidence_api.ExecutionEvidenceStore(database)
            monkeypatch.setattr(evidence_api.sqlite3, "connect", original_connect)
            if before_fds is not None:
                assert len(tuple(fd_root.iterdir())) == before_fds
            external = _external_begin_immediate(database)
            assert external.returncode == 73, external.stderr
            assert "locked" in external.stderr
    finally:
        first.close()


def test_close_releases_the_store_owned_connection(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
) -> None:
    store = _store(evidence_api, connection)

    store.close()
    store.close()

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        store.current_floor("job-1")


@pytest.mark.parametrize("object_type", ["index", "trigger"])
def test_external_temp_owned_object_name_is_connection_local(
    evidence_api: ModuleType,
    connection: sqlite3.Connection,
    object_type: str,
) -> None:
    store = _store(evidence_api, connection)
    connection.execute("CREATE TEMP TABLE unrelated_temp_table (value INTEGER)")
    if object_type == "index":
        connection.execute(
            """
            CREATE INDEX temp.ux_execution_lease_events_job_fence
            ON unrelated_temp_table(value)
            """
        )
    else:
        connection.execute(
            """
            CREATE TRIGGER temp.execution_terminal_evidence_no_update
            BEFORE UPDATE ON unrelated_temp_table
            BEGIN
                SELECT 1;
            END
            """
        )

    assert store.current_floor("job-1") == evidence_api.EvidenceFloor(0, 0)
