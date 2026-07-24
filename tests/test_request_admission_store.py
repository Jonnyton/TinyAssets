from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tinyassets.daemon_server import initialize_author_server
from tinyassets.storage import db_path
from tinyassets.storage.request_admissions import (
    COMMIT_STEPS,
    IdempotencyKeyBodyConflict,
    RequestAdmissionStore,
)


def _commit_kwargs(**overrides):
    values = {
        "tenant_id": "tenant-a",
        "actor_id": "alice",
        "universe_id": "universe-a",
        "idempotency_key_hash": "hmac:scope-key-a",
        "body_digest": "sha256:body-a",
        "body_digest_version": "rfc8785-v1",
        "request_type": "general",
        "text": "repair the queue",
        "branch_id": "",
        "branch_def_id": "loop-branch",
        "trigger_source": "operator_request",
        "accepted_priority_weight": 50.0,
        "policy_version": "operator-priority-v1",
        "grant_generation": 3,
        "receipt": {"authority": "exact-universe-grant"},
        "directed_daemon_id": "",
        "created_at": "2026-07-24T08:00:00Z",
    }
    values.update(overrides)
    return values


def _connect(base: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(base), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_count(base: Path, table: str) -> int:
    with _connect(base) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_author_server_pretraffic_init_migrates_epoch2_schema(tmp_path):
    initialize_author_server(tmp_path)
    with _connect(tmp_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "request_admissions",
            "request_admission_events",
            "branch_tasks_v2",
            "branch_tasks_v2_quarantine",
            "request_admission_rollouts",
        } <= tables
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_migrates_prechange_database_without_losing_requests(tmp_path):
    path = db_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE user_requests (
                request_id TEXT PRIMARY KEY,
                universe_id TEXT NOT NULL,
                branch_id TEXT,
                user_id TEXT NOT NULL,
                request_type TEXT NOT NULL,
                text TEXT NOT NULL,
                preferred_author_id TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );
            INSERT INTO user_requests (
                request_id, universe_id, branch_id, user_id, request_type,
                text, preferred_author_id, status, created_at, updated_at,
                metadata_json
            ) VALUES (
                'legacy-request', 'legacy-universe', NULL, 'alice', 'general',
                'keep me', NULL, 'open', 1.0, 1.0, '{}'
            );
            """
        )

    initialize_author_server(tmp_path)

    with _connect(tmp_path) as conn:
        assert conn.execute(
            "SELECT text FROM user_requests WHERE request_id='legacy-request'"
        ).fetchone()[0] == "keep me"
        assert conn.execute(
            "SELECT COUNT(*) FROM request_admissions"
        ).fetchone()[0] == 0


def test_commit_links_request_admission_task_and_event(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)

    result = store.commit_admission(**_commit_kwargs())

    assert result == {
        "universe_id": "universe-a",
        "admission_id": result["admission_id"],
        "admission_state": "committed",
        "request_id": result["request_id"],
        "branch_task_id": result["branch_task_id"],
        "request_status": "pending",
        "trigger_source": "operator_request",
        "accepted_priority_weight": 50.0,
        "priority_weight_cap": 100,
        "priority_policy_version": "operator-priority-v1",
        "idempotent_replay": False,
        "directed_daemon_id": "",
    }
    assert result["request_id"]
    assert result["admission_id"]
    assert result["branch_task_id"]

    with _connect(tmp_path) as conn:
        admission = conn.execute(
            "SELECT * FROM request_admissions"
        ).fetchone()
        task = conn.execute("SELECT * FROM branch_tasks_v2").fetchone()
        event = conn.execute(
            "SELECT * FROM request_admission_events"
        ).fetchone()
        assert admission["request_id"] == result["request_id"]
        assert admission["branch_task_id"] == result["branch_task_id"]
        assert task["admission_id"] == result["admission_id"]
        assert task["request_id"] == result["request_id"]
        assert task["queue_epoch"] == 2
        assert event["admission_id"] == result["admission_id"]
        assert event["request_id"] == result["request_id"]
        assert event["branch_task_id"] == result["branch_task_id"]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_schema_rejects_out_of_range_weight_and_duplicate_links(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)
    committed = store.commit_admission(**_commit_kwargs())

    with _connect(tmp_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE request_admissions
                SET accepted_priority_weight = 100.000001
                WHERE admission_id = ?
                """,
                (committed["admission_id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO request_admissions (
                    admission_id, request_id, branch_task_id, tenant_id,
                    actor_id, universe_id, idempotency_key_hash, body_digest,
                    body_digest_version, trigger_source,
                    accepted_priority_weight, priority_policy_version,
                    grant_generation, receipt_json, result_json, state,
                    created_at, updated_at
                )
                SELECT
                    'duplicate-admission', request_id, branch_task_id,
                    tenant_id, actor_id, universe_id, idempotency_key_hash,
                    body_digest, body_digest_version, trigger_source,
                    accepted_priority_weight, priority_policy_version,
                    grant_generation, receipt_json, result_json, state,
                    created_at, updated_at
                FROM request_admissions
                WHERE admission_id = ?
                """,
                (committed["admission_id"],),
            )


@pytest.mark.parametrize(
    "weight",
    [-1.0, 100.000001, float("inf"), float("-inf"), float("nan")],
)
def test_commit_rejects_nonfinite_or_out_of_range_weight(tmp_path, weight):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)

    with pytest.raises(
        ValueError,
        match=r"accepted_priority_weight must be finite and within \[0, 100\]",
    ):
        store.commit_admission(
            **_commit_kwargs(accepted_priority_weight=weight),
        )

    assert _table_count(tmp_path, "user_requests") == 0
    assert _table_count(tmp_path, "request_admissions") == 0


@pytest.mark.parametrize("fault_step", COMMIT_STEPS)
def test_precommit_fault_rolls_back_entire_aggregate(tmp_path, fault_step):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)

    def inject(step, _conn):
        if step == fault_step:
            raise RuntimeError(f"fault:{step}")

    with pytest.raises(RuntimeError, match=f"fault:{fault_step}"):
        store.commit_admission(
            **_commit_kwargs(),
            fault_injector=inject,
        )

    for table in (
        "user_requests",
        "request_admissions",
        "branch_tasks_v2",
        "request_admission_events",
    ):
        assert _table_count(tmp_path, table) == 0


def test_replay_returns_original_ids_without_new_rows_or_event(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)
    first = store.commit_admission(**_commit_kwargs())

    replay = store.commit_admission(**_commit_kwargs(text="ignored on replay"))

    assert replay == {**first, "idempotent_replay": True}
    assert _table_count(tmp_path, "user_requests") == 1
    assert _table_count(tmp_path, "request_admissions") == 1
    assert _table_count(tmp_path, "branch_tasks_v2") == 1
    assert _table_count(tmp_path, "request_admission_events") == 1


def test_random_id_collision_retries_in_a_fresh_transaction(tmp_path):
    initialize_author_server(tmp_path)
    first = RequestAdmissionStore(tmp_path).commit_admission(
        **_commit_kwargs()
    )
    generated = iter([
        first["request_id"],
        "unused-admission",
        "unused-task",
        "unused-event",
        "req_unique",
        "adm_unique",
        "bt2_unique",
        "evt_unique",
    ])
    store = RequestAdmissionStore(
        tmp_path,
        id_factory=lambda _prefix: next(generated),
    )

    second = store.commit_admission(
        **_commit_kwargs(
            idempotency_key_hash="hmac:scope-key-b",
            body_digest="sha256:body-b",
        )
    )

    assert second["request_id"] == "req_unique"
    assert second["admission_id"] == "adm_unique"
    assert second["branch_task_id"] == "bt2_unique"
    assert _table_count(tmp_path, "request_admissions") == 2


def test_concurrent_same_key_commits_one_aggregate(tmp_path):
    initialize_author_server(tmp_path)

    def commit(_index):
        return RequestAdmissionStore(tmp_path).commit_admission(
            **_commit_kwargs()
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(commit, range(32)))

    assert len({row["request_id"] for row in results}) == 1
    assert len({row["admission_id"] for row in results}) == 1
    assert len({row["branch_task_id"] for row in results}) == 1
    assert sum(not row["idempotent_replay"] for row in results) == 1
    assert _table_count(tmp_path, "user_requests") == 1
    assert _table_count(tmp_path, "request_admissions") == 1
    assert _table_count(tmp_path, "branch_tasks_v2") == 1
    assert _table_count(tmp_path, "request_admission_events") == 1


def test_changed_body_replay_conflicts_without_mutation(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)
    store.commit_admission(**_commit_kwargs())

    with pytest.raises(IdempotencyKeyBodyConflict):
        store.commit_admission(
            **_commit_kwargs(body_digest="sha256:different-body"),
        )

    assert _table_count(tmp_path, "request_admissions") == 1
    assert _table_count(tmp_path, "request_admission_events") == 1


def test_authority_check_runs_inside_transaction_and_can_abort(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)
    observed = []

    def deny(conn):
        observed.append(conn.in_transaction)
        raise PermissionError("revoked")

    with pytest.raises(PermissionError, match="revoked"):
        store.commit_admission(
            **_commit_kwargs(),
            authority_check=deny,
        )

    assert observed == [True]
    assert _table_count(tmp_path, "user_requests") == 0


def test_claim_transition_quarantine_and_universe_delete(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)
    committed = store.commit_admission(**_commit_kwargs())

    candidates = store.list_v2_candidates(universe_id="universe-a")
    assert [row["branch_task_id"] for row in candidates] == [
        committed["branch_task_id"]
    ]

    claimed = store.claim_v2_task(
        committed["branch_task_id"],
        worker_id="worker-1",
        queue_protocol_version=2,
        capabilities={"operator_request_v1"},
        claimed_at="2026-07-24T08:01:00Z",
    )
    assert claimed["status"] == "running"
    assert claimed["claimed_by"] == "worker-1"
    assert store.claim_v2_task(
        committed["branch_task_id"],
        worker_id="worker-2",
        queue_protocol_version=2,
        capabilities={"operator_request_v1"},
        claimed_at="2026-07-24T08:01:01Z",
    ) is None

    store.transition_task(
        committed["branch_task_id"],
        expected_statuses={"running"},
        new_status="failed",
        at="2026-07-24T08:02:00Z",
        detail={"error": "fixture"},
    )
    receipt = store.quarantine_task(
        committed["branch_task_id"],
        reason="invalid_operator_admission",
        observed_at="2026-07-24T08:03:00Z",
    )
    assert receipt["reason"] == "invalid_operator_admission"
    replayed_receipt = store.quarantine_task(
        committed["branch_task_id"],
        reason="invalid_operator_admission",
        observed_at="2026-07-24T08:04:00Z",
    )
    assert replayed_receipt["row_digest"] == receipt["row_digest"]
    assert _table_count(tmp_path, "branch_tasks_v2_quarantine") == 1
    with _connect(tmp_path) as conn:
        quarantine = conn.execute(
            """
            SELECT first_seen_at, last_seen_at, seen_count
            FROM branch_tasks_v2_quarantine
            WHERE row_digest = ?
            """,
            (receipt["row_digest"],),
        ).fetchone()
        assert dict(quarantine) == {
            "first_seen_at": "2026-07-24T08:03:00Z",
            "last_seen_at": "2026-07-24T08:04:00Z",
            "seen_count": 2,
        }
        assert conn.execute(
            """
            SELECT COUNT(*)
            FROM request_admission_events
            WHERE branch_task_id = ? AND event_type = 'quarantined'
            """,
            (committed["branch_task_id"],),
        ).fetchone()[0] == 1

    assert store.delete_universe("universe-a") == 1
    assert _table_count(tmp_path, "user_requests") == 0
    assert _table_count(tmp_path, "request_admissions") == 0
    assert _table_count(tmp_path, "branch_tasks_v2") == 0


def test_terminal_compaction_retains_tombstone_but_not_private_detail(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path)
    terminal = store.commit_admission(**_commit_kwargs())
    pending = store.commit_admission(
        **_commit_kwargs(
            idempotency_key_hash="hmac:scope-key-b",
            body_digest="sha256:body-b",
            text="keep pending detail",
        )
    )
    store.transition_task(
        terminal["branch_task_id"],
        expected_statuses={"pending"},
        new_status="succeeded",
        at="2026-06-01T00:00:00Z",
        detail={"private": "remove me"},
    )

    assert store.compact_terminal_details(
        terminal_before="2026-06-24T00:00:00Z",
        compacted_at="2026-07-24T08:05:00Z",
    ) == 1

    with _connect(tmp_path) as conn:
        terminal_request = conn.execute(
            "SELECT text FROM user_requests WHERE request_id = ?",
            (terminal["request_id"],),
        ).fetchone()
        pending_request = conn.execute(
            "SELECT text FROM user_requests WHERE request_id = ?",
            (pending["request_id"],),
        ).fetchone()
        admission = conn.execute(
            "SELECT body_digest, idempotency_key_hash, result_json, compacted_at "
            "FROM request_admissions WHERE admission_id = ?",
            (terminal["admission_id"],),
        ).fetchone()
        assert terminal_request["text"] == ""
        assert pending_request["text"] == "keep pending detail"
        assert admission["body_digest"] == "sha256:body-a"
        assert admission["idempotency_key_hash"] == "hmac:scope-key-a"
        assert json.loads(admission["result_json"]) == {
            "admission_id": terminal["admission_id"],
            "branch_task_id": terminal["branch_task_id"],
            "request_id": terminal["request_id"],
            "request_status": "succeeded",
            "universe_id": "universe-a",
        }
        assert admission["compacted_at"] == "2026-07-24T08:05:00Z"


def test_sqlite_pragmas_and_concurrent_initialization(tmp_path):
    def initialize(_index):
        initialize_author_server(tmp_path)
        store = RequestAdmissionStore(tmp_path)
        with store.connection() as conn:
            return (
                conn.execute("PRAGMA journal_mode").fetchone()[0],
                conn.execute("PRAGMA foreign_keys").fetchone()[0],
                conn.execute("PRAGMA busy_timeout").fetchone()[0],
            )

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(initialize, range(64)))

    assert all(str(mode).lower() == "wal" for mode, _, _ in results)
    assert all(foreign_keys == 1 for _, foreign_keys, _ in results)
    assert all(busy_timeout == 30000 for _, _, busy_timeout in results)
    with _connect(tmp_path) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_lock_error_propagates_without_partial_admission(tmp_path):
    initialize_author_server(tmp_path)
    store = RequestAdmissionStore(tmp_path, busy_timeout_ms=1)

    with _connect(tmp_path) as locker:
        locker.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            store.commit_admission(**_commit_kwargs())
        locker.rollback()

    assert _table_count(tmp_path, "user_requests") == 0
    assert _table_count(tmp_path, "request_admissions") == 0
    assert _table_count(tmp_path, "branch_tasks_v2") == 0
    assert _table_count(tmp_path, "request_admission_events") == 0
