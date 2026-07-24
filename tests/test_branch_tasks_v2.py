from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from tinyassets.branch_tasks import (
    BranchTask,
    append_task,
    claim_task,
    read_queue,
)
from tinyassets.branch_tasks_v2 import (
    Epoch2BranchTaskAdapter,
    WorkerClaimDescriptor,
)
from tinyassets.daemon_server import initialize_author_server
from tinyassets.storage import db_path
from tinyassets.storage.request_admissions import (
    RequestAdmissionStore,
    migrate_request_admission_schema,
)


class _MutableClock:
    def __init__(self, value: str) -> None:
        self.set(value)

    def __call__(self) -> datetime:
        return self.value

    def set(self, value: str) -> None:
        self.value = datetime.fromisoformat(value.replace("Z", "+00:00"))


def _commit(
    base_path: Path,
    *,
    key: str = "hmac:epoch2-key-a",
    body: str = "sha256:epoch2-body-a",
    trigger_source: str = "operator_request",
    weight: float = 50.0,
    directed_daemon_id: str = "",
    created_at: str = "2026-07-24T08:00:00+00:00",
) -> dict:
    return RequestAdmissionStore(base_path).commit_admission(
        tenant_id="tenant-a",
        actor_id="actor-a",
        universe_id="universe-a",
        idempotency_key_hash=key,
        body_digest=body,
        body_digest_version="rfc8785-v1",
        request_type="general",
        text="repair the queue",
        branch_id="",
        branch_def_id="loop-branch",
        trigger_source=trigger_source,
        accepted_priority_weight=weight,
        policy_version="operator-priority-v1",
        grant_generation=3,
        receipt={"authority": "request-local"},
        directed_daemon_id=directed_daemon_id,
        created_at=created_at,
    )


def _descriptor(
    *,
    worker_id: str = "worker-a",
    universe_id: str = "universe-a",
    expires_at: str = "2026-07-24T08:02:15+00:00",
) -> WorkerClaimDescriptor:
    return WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id=worker_id,
        runtime_instance_id="runtime-a",
        boot_id="boot-a",
        build_sha="a" * 40,
        config_hash="b" * 64,
        universe_id=universe_id,
        expires_at=expires_at,
    )


def _request_status(base_path: Path, request_id: str) -> str:
    with sqlite3.connect(db_path(base_path)) as conn:
        row = conn.execute(
            "SELECT status FROM user_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
    assert row is not None
    return str(row[0])


@pytest.fixture
def epoch2(
    tmp_path: Path,
) -> tuple[Epoch2BranchTaskAdapter, dict, _MutableClock]:
    initialize_author_server(tmp_path)
    committed = _commit(tmp_path)
    clock = _MutableClock("2026-07-24T08:01:00+00:00")
    return Epoch2BranchTaskAdapter(tmp_path, clock=clock), committed, clock


def test_pretraffic_migration_adds_lease_column_to_existing_v2_store(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            "ALTER TABLE branch_tasks_v2 DROP COLUMN lease_expires_at"
        )
        migrate_request_admission_schema(conn)
        columns = {
            str(row[1])
            for row in conn.execute("PRAGMA table_info(branch_tasks_v2)")
        }

    assert "lease_expires_at" in columns


def test_adapter_reads_canonical_epoch2_task_and_ids_are_unique(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    first = _commit(tmp_path)
    second = _commit(
        tmp_path,
        key="hmac:epoch2-key-b",
        body="sha256:epoch2-body-b",
        created_at="2026-07-24T08:00:01+00:00",
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)

    candidates = adapter.list_candidates(universe_id="universe-a")

    assert [task.branch_task_id for task in candidates] == [
        first["branch_task_id"],
        second["branch_task_id"],
    ]
    assert len({
        first["request_id"],
        first["admission_id"],
        first["branch_task_id"],
        second["request_id"],
        second["admission_id"],
        second["branch_task_id"],
    }) == 6
    task = adapter.get(first["branch_task_id"])
    assert task is not None
    assert task.queue_epoch == 2
    assert task.protocol_version == 2
    assert task.request_id == first["request_id"]
    assert task.admission_id == first["admission_id"]
    assert task.inputs["request_type"] == "general"


def test_claim_rechecks_exact_live_descriptor_inside_transaction(
    epoch2: tuple[Epoch2BranchTaskAdapter, dict, _MutableClock],
) -> None:
    adapter, committed, clock = epoch2
    observed: list[bool] = []

    trusted_descriptor = _descriptor()

    def trusted(conn, _worker_id):
        observed.append(conn.in_transaction)
        return trusted_descriptor

    false_descriptor = _descriptor(universe_id="other-universe")
    assert adapter.claim(
        committed["branch_task_id"],
        descriptor=false_descriptor,
        descriptor_reader=trusted,
    ) is None
    assert observed == []

    expired = _descriptor(expires_at="2026-07-24T08:00:59+00:00")
    assert adapter.claim(
        committed["branch_task_id"],
        descriptor=expired,
        descriptor_reader=trusted,
    ) is None
    assert observed == [True]

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=_descriptor(),
        descriptor_reader=trusted,
        lease_seconds=90,
    )

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.claimed_by == "worker-a"
    assert claimed.lease_expires_at == "2026-07-24T08:02:30+00:00"
    assert observed == [True, True]
    assert _request_status(
        adapter.base_path,
        committed["request_id"],
    ) == "running"
    clock.set("2026-07-24T08:01:01+00:00")
    assert adapter.claim(
        committed["branch_task_id"],
        descriptor=_descriptor(worker_id="worker-b"),
        descriptor_reader=lambda _conn, _worker_id: _descriptor(
            worker_id="worker-b"
        ),
    ) is None


def test_claim_uses_transaction_time_for_descriptor_freshness(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    committed = _commit(tmp_path)
    clock = _MutableClock("2026-07-24T08:01:00+00:00")
    adapter = Epoch2BranchTaskAdapter(tmp_path, clock=clock)
    expired = _descriptor(expires_at="2026-07-24T08:00:59+00:00")

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=expired,
        descriptor_reader=lambda _conn, _worker_id: expired,
    )

    assert claimed is None
    overlong = _descriptor(expires_at="2026-07-24T08:02:31+00:00")
    assert adapter.claim(
        committed["branch_task_id"],
        descriptor=overlong,
        descriptor_reader=lambda _conn, _worker_id: overlong,
    ) is None
    live = _descriptor()
    with pytest.raises(ValueError, match="lease_seconds must be between"):
        adapter.claim(
            committed["branch_task_id"],
            descriptor=live,
            descriptor_reader=lambda _conn, _worker_id: live,
            lease_seconds=91,
        )
    task = adapter.get(committed["branch_task_id"])
    assert task is not None
    assert task.status == "pending"


def test_concurrent_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    initialize_author_server(tmp_path)
    committed = _commit(tmp_path)
    clock = _MutableClock("2026-07-24T08:01:00+00:00")
    barrier = threading.Barrier(3)
    results: dict[str, object] = {}
    errors: list[BaseException] = []
    result_lock = threading.Lock()

    def race(worker_id: str) -> None:
        try:
            descriptor = _descriptor(worker_id=worker_id)
            adapter = Epoch2BranchTaskAdapter(tmp_path, clock=clock)
            barrier.wait()
            claimed = adapter.claim(
                committed["branch_task_id"],
                descriptor=descriptor,
                descriptor_reader=lambda _conn, _worker_id: descriptor,
            )
            with result_lock:
                results[worker_id] = claimed
        except BaseException as exc:
            with result_lock:
                errors.append(exc)
            try:
                barrier.abort()
            except threading.BrokenBarrierError:
                pass

    threads = [
        threading.Thread(target=race, args=("worker-a",)),
        threading.Thread(target=race, args=("worker-b",)),
    ]
    for thread in threads:
        thread.start()
    try:
        barrier.wait(timeout=10)
    except threading.BrokenBarrierError:
        pass
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads)
    assert errors == []
    winners = [
        worker_id for worker_id, task in results.items() if task is not None
    ]
    assert len(winners) == 1
    task = Epoch2BranchTaskAdapter(tmp_path).get(
        committed["branch_task_id"]
    )
    assert task is not None
    assert task.status == "running"
    assert task.claimed_by == winners[0]
    with sqlite3.connect(db_path(tmp_path)) as conn:
        claim_events = conn.execute(
            """
            SELECT COUNT(*)
            FROM request_admission_events
            WHERE branch_task_id = ? AND event_type = 'claimed'
            """,
            (committed["branch_task_id"],),
        ).fetchone()
    assert claim_events is not None
    assert claim_events[0] == 1


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("queue_protocol_version", 1),
        ("capabilities", frozenset()),
        ("worker_id", "worker-other"),
        ("runtime_instance_id", "runtime-other"),
        ("boot_id", "boot-other"),
        ("build_sha", "c" * 40),
        ("config_hash", "d" * 64),
        ("universe_id", "universe-other"),
    ],
)
def test_claim_rejects_every_descriptor_identity_mismatch(
    epoch2: tuple[Epoch2BranchTaskAdapter, dict, _MutableClock],
    field_name: str,
    invalid_value,
) -> None:
    adapter, committed, _clock = epoch2
    trusted = _descriptor()
    offered = replace(trusted, **{field_name: invalid_value})

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=offered,
        descriptor_reader=lambda _conn, _worker_id: trusted,
    )

    assert claimed is None
    task = adapter.get(committed["branch_task_id"])
    assert task is not None
    assert task.status == "pending"


def test_heartbeat_cancel_terminal_and_expired_recovery(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    first = _commit(tmp_path)
    second = _commit(
        tmp_path,
        key="hmac:epoch2-key-b",
        body="sha256:epoch2-body-b",
    )
    clock = _MutableClock("2026-07-24T08:01:00+00:00")
    adapter = Epoch2BranchTaskAdapter(tmp_path, clock=clock)

    def trusted_a(_conn, _worker_id):
        return _descriptor()

    def trusted_b(_conn, _worker_id):
        return _descriptor(worker_id="worker-b")

    adapter.claim(
        first["branch_task_id"],
        descriptor=_descriptor(),
        descriptor_reader=trusted_a,
        lease_seconds=30,
    )
    adapter.claim(
        second["branch_task_id"],
        descriptor=_descriptor(worker_id="worker-b"),
        descriptor_reader=trusted_b,
        lease_seconds=30,
    )

    clock.set("2026-07-24T08:01:10+00:00")
    assert adapter.heartbeat(
        first["branch_task_id"],
        worker_id="wrong-worker",
    ) is None
    heartbeat = adapter.heartbeat(
        first["branch_task_id"],
        worker_id="worker-a",
        lease_seconds=90,
    )
    assert heartbeat is not None
    assert heartbeat.heartbeat_at == "2026-07-24T08:01:10+00:00"
    assert heartbeat.lease_expires_at == "2026-07-24T08:02:40+00:00"

    clock.set("2026-07-24T08:01:20+00:00")
    cancel_requested = adapter.request_cancel(first["branch_task_id"])
    assert cancel_requested.status == "cancel_requested"
    clock.set("2026-07-24T08:01:30+00:00")
    cancelled = adapter.finish(
        first["branch_task_id"],
        worker_id="worker-a",
        status="cancelled",
    )
    assert cancelled.status == "cancelled"
    assert cancelled.terminal_at == "2026-07-24T08:01:30+00:00"

    clock.set("2026-07-24T08:01:31+00:00")
    recovered = adapter.recover_expired()
    assert [task.branch_task_id for task in recovered] == [
        second["branch_task_id"]
    ]
    assert recovered[0].status == "pending"
    assert recovered[0].claimed_by == ""
    assert recovered[0].lease_expires_at == ""
    assert _request_status(
        tmp_path,
        second["request_id"],
    ) == "pending"


def test_pending_cancel_is_terminal_without_claim(
    epoch2: tuple[Epoch2BranchTaskAdapter, dict, _MutableClock],
) -> None:
    adapter, committed, _clock = epoch2

    cancelled = adapter.request_cancel(committed["branch_task_id"])

    assert cancelled.status == "cancelled"
    assert cancelled.terminal_at == "2026-07-24T08:01:00+00:00"
    assert _request_status(
        adapter.base_path,
        committed["request_id"],
    ) == "cancelled"
    assert adapter.list_candidates(universe_id="universe-a") == []


def test_expired_worker_cannot_heartbeat_or_finish_before_recovery(
    epoch2: tuple[Epoch2BranchTaskAdapter, dict, _MutableClock],
) -> None:
    adapter, committed, clock = epoch2
    adapter.claim(
        committed["branch_task_id"],
        descriptor=_descriptor(),
        descriptor_reader=lambda _conn, _worker_id: _descriptor(),
        lease_seconds=30,
    )

    clock.set("2026-07-24T08:01:31+00:00")
    assert adapter.heartbeat(
        committed["branch_task_id"],
        worker_id="worker-a",
    ) is None
    with pytest.raises(PermissionError, match="branch_task_lease_expired"):
        adapter.finish(
            committed["branch_task_id"],
            worker_id="worker-a",
            status="succeeded",
        )
    recovered = adapter.recover_expired()
    assert [task.status for task in recovered] == ["pending"]


def test_cancel_requested_task_recovers_to_cancelled(
    epoch2: tuple[Epoch2BranchTaskAdapter, dict, _MutableClock],
) -> None:
    adapter, committed, clock = epoch2
    adapter.claim(
        committed["branch_task_id"],
        descriptor=_descriptor(),
        descriptor_reader=lambda _conn, _worker_id: _descriptor(),
        lease_seconds=30,
    )
    clock.set("2026-07-24T08:01:10+00:00")
    requested = adapter.request_cancel(committed["branch_task_id"])
    assert requested.status == "cancel_requested"
    assert _request_status(
        adapter.base_path,
        committed["request_id"],
    ) == "cancel_requested"

    clock.set("2026-07-24T08:01:31+00:00")
    recovered = adapter.recover_expired()

    assert [task.status for task in recovered] == ["cancelled"]
    assert recovered[0].terminal_at == "2026-07-24T08:01:31+00:00"
    assert _request_status(
        adapter.base_path,
        committed["request_id"],
    ) == "cancelled"
    assert adapter.list_candidates(universe_id="universe-a") == []


def test_claim_event_failure_rolls_back_running_transition(
    epoch2: tuple[Epoch2BranchTaskAdapter, dict, _MutableClock],
) -> None:
    adapter, committed, _clock = epoch2
    with sqlite3.connect(db_path(adapter.base_path)) as conn:
        conn.executescript(
            """
            CREATE TRIGGER fail_claim_event
            BEFORE INSERT ON request_admission_events
            WHEN NEW.event_type = 'claimed'
            BEGIN
                SELECT RAISE(ABORT, 'claim event failure');
            END;
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="claim event failure"):
        adapter.claim(
            committed["branch_task_id"],
            descriptor=_descriptor(),
            descriptor_reader=lambda _conn, _worker_id: _descriptor(),
        )

    task = adapter.get(committed["branch_task_id"])
    assert task is not None
    assert task.status == "pending"
    assert task.claimed_by == ""
    assert task.heartbeat_at == ""
    assert task.lease_expires_at == ""
    assert _request_status(
        adapter.base_path,
        committed["request_id"],
    ) == "pending"


def test_v1_claim_code_cannot_open_or_mutate_epoch2(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    committed = _commit(tmp_path)
    adapter = Epoch2BranchTaskAdapter(tmp_path)
    universe_path = tmp_path / "universe-a"
    universe_path.mkdir()
    v1 = BranchTask(
        branch_task_id="v1-task",
        branch_def_id="loop-branch",
        universe_id="universe-a",
    )
    append_task(universe_path, v1)

    claimed_v1 = claim_task(universe_path, "v1-task", "legacy-worker")
    claimed_v2 = claim_task(
        universe_path,
        committed["branch_task_id"],
        "legacy-worker",
    )

    assert claimed_v1 is not None
    assert claimed_v1.status == "running"
    assert claimed_v2 is None
    assert [task.status for task in read_queue(universe_path)] == ["running"]
    epoch2_task = adapter.get(committed["branch_task_id"])
    assert epoch2_task is not None
    assert epoch2_task.status == "pending"


def test_v2_worker_can_drain_both_epochs_through_epoch_specific_claimers(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    committed = _commit(tmp_path)
    adapter = Epoch2BranchTaskAdapter(
        tmp_path,
        clock=_MutableClock("2026-07-24T08:01:00+00:00"),
    )
    universe_path = tmp_path / "universe-a"
    universe_path.mkdir()
    append_task(
        universe_path,
        BranchTask(
            branch_task_id="v1-task",
            branch_def_id="loop-branch",
            universe_id="universe-a",
        ),
    )
    descriptor = _descriptor()

    claimed_v1 = claim_task(
        universe_path,
        "v1-task",
        descriptor.worker_id,
    )
    claimed_v2 = adapter.claim(
        committed["branch_task_id"],
        descriptor=descriptor,
        descriptor_reader=lambda _conn, _worker_id: descriptor,
    )

    assert claimed_v1 is not None
    assert claimed_v1.status == "running"
    assert claimed_v2 is not None
    assert claimed_v2.status == "running"


def test_directed_epoch2_task_preserves_owner_tier_and_assignment(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    committed = _commit(
        tmp_path,
        trigger_source="owner_queued",
        weight=25,
        directed_daemon_id="daemon-a",
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)

    task = adapter.get(committed["branch_task_id"])

    assert task is not None
    assert task.trigger_source == "owner_queued"
    assert task.priority_weight == 25
    assert task.directed_daemon_id == "daemon-a"
