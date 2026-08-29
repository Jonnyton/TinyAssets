from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path

import pytest

import tinyassets.runtime.assigned_queue_consumer as consumer_module
from tinyassets.background_served_provider import (
    BACKGROUND_BRANCH_RUN_OPERATION,
    _branch_roles,
    authorize_background_served_provider_call,
)
from tinyassets.branch_tasks_v2 import AssignedConsumerLease, Epoch2BranchTask
from tinyassets.runtime.assigned_queue_consumer import (
    AssignedQueueConsumer,
    assigned_queue_consumer_enabled,
)


def test_assigned_queue_consumer_flag_is_dark_by_default(monkeypatch) -> None:
    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    assert assigned_queue_consumer_enabled() is False


def test_flag_off_poll_performs_zero_claim_work(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()


def test_assigned_queue_consumer_flag_requires_explicit_truthy(monkeypatch) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "off")
    assert assigned_queue_consumer_enabled() is False
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "on")
    assert assigned_queue_consumer_enabled() is True


def test_background_authorizer_rejects_cross_consumer_before_provider_lookup(
    tmp_path,
) -> None:
    task = Epoch2BranchTask(
        branch_task_id="bt2_" + "a" * 32,
        branch_def_id="branch-a",
        universe_id="universe-a",
        claimed_by="assigned-consumer:one",
        claimed_at="2026-08-23T00:00:00+00:00",
        lease_expires_at="2026-08-23T00:30:00+00:00",
        automation_id="automation-a",
        automation_branch_version="version-a",
    )
    lease = AssignedConsumerLease(
        consumer_id="assigned-consumer:two",
        lease_id="lease-two",
        expires_at="2026-08-23T00:30:00+00:00",
    )

    try:
        authorize_background_served_provider_call(tmp_path, task, lease)
    except PermissionError as exc:
        assert "does not own" in str(exc)
    else:  # pragma: no cover - fail-closed assertion
        raise AssertionError("cross-consumer authority was accepted")


def test_background_operation_is_not_interactive_converse() -> None:
    assert BACKGROUND_BRANCH_RUN_OPERATION == "background_branch_run"
    assert BACKGROUND_BRANCH_RUN_OPERATION != "converse"


def test_background_roles_come_from_exact_immutable_branch(
    tmp_path, monkeypatch
) -> None:
    task = Epoch2BranchTask(
        branch_task_id="bt2_" + "a" * 32,
        branch_def_id="branch-a",
        universe_id="universe-a",
        automation_branch_version="version-a",
        automation_subject_digest="sha256:" + "b" * 64,
    )
    version = type(
        "Version",
        (),
        {
            "status": "active",
            "branch_def_id": "branch-a",
            "content_hash": "sha256:" + "b" * 64,
            "snapshot": {
                "node_defs": {
                    "draft": {"node_type": "prompt", "model_hint": "writer"},
                    "score": {"node_type": "prompt", "model_hint": "judge"},
                }
            },
        },
    )()
    monkeypatch.setattr("tinyassets.branch_versions.get_branch_version", lambda *_a: version)

    assert _branch_roles(tmp_path, task) == ("judge", "writer")

    version.snapshot["node_defs"]["draft"]["model_hint"] = "ambient-provider"
    try:
        _branch_roles(tmp_path, task)
    except PermissionError as exc:
        assert "unsupported provider role" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unsupported immutable role was accepted")


def test_universe_server_flag_off_constructs_no_consumer(tmp_path: Path, monkeypatch) -> None:
    import threading

    import tinyassets.engine_mcp_http as engine_http
    import tinyassets.provider_assignment as provider_assignment
    import tinyassets.universe_server as universe_server

    lifecycle: list[str] = []

    class _NoopThread:
        def __init__(self, **_kwargs):
            pass

        def start(self) -> None:
            pass

    class _MustNotConstruct:
        def __init__(self, _base_path):
            lifecycle.append("constructed")

    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(threading, "Thread", _NoopThread)
    monkeypatch.setattr(
        provider_assignment, "reconcile_orphaned_reservations_on_boot", lambda _root: 0
    )
    monkeypatch.setattr(engine_http, "start_engine_mcp_http_servers", lambda: [])
    monkeypatch.setattr(universe_server, "create_streamable_http_app", object)
    monkeypatch.setattr(universe_server.uvicorn, "run", lambda *_a, **_k: None)
    monkeypatch.setattr(consumer_module, "AssignedQueueConsumer", _MustNotConstruct)

    universe_server.main(host="127.0.0.1", port=0)

    assert lifecycle == []


def test_universe_server_enabled_consumer_is_started_and_stopped(
    tmp_path: Path, monkeypatch
) -> None:
    import threading

    import tinyassets.engine_mcp_http as engine_http
    import tinyassets.provider_assignment as provider_assignment
    import tinyassets.universe_server as universe_server

    lifecycle: list[str] = []

    class _NoopThread:
        def __init__(self, **_kwargs):
            pass

        def start(self) -> None:
            pass

    class _FakeConsumer:
        def __init__(self, base_path):
            assert Path(base_path) == tmp_path
            lifecycle.append("constructed")

        def start(self) -> None:
            lifecycle.append("started")

        def stop(self) -> None:
            lifecycle.append("stopped")

    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "on")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(threading, "Thread", _NoopThread)
    monkeypatch.setattr(
        provider_assignment, "reconcile_orphaned_reservations_on_boot", lambda _root: 0
    )
    monkeypatch.setattr(engine_http, "start_engine_mcp_http_servers", lambda: [])
    monkeypatch.setattr(universe_server, "create_streamable_http_app", object)
    monkeypatch.setattr(universe_server.uvicorn, "run", lambda *_a, **_k: None)
    monkeypatch.setattr(consumer_module, "AssignedQueueConsumer", _FakeConsumer)

    universe_server.main(host="127.0.0.1", port=0)

    assert lifecycle == ["constructed", "started", "stopped"]


def test_poll_once_respects_global_concurrency_cap(tmp_path: Path, monkeypatch) -> None:
    tasks = {
        universe_id: Epoch2BranchTask(
            branch_task_id="bt2_" + marker * 32,
            branch_def_id=f"branch-{marker}",
            universe_id=universe_id,
            automation_id=f"automation-{marker}",
            automation_executor_class="cloud",
            automation_branch_version=f"version-{marker}",
        )
        for universe_id, marker in (("universe-a", "a"), ("universe-b", "b"))
    }
    claims: list[str] = []

    class _Adapter:
        def __init__(self, _base_path):
            pass

        def recover_expired(self, **_kwargs):
            return []

        def list_candidates(self, *, universe_id, limit):
            assert limit == 20
            return [tasks[universe_id]]

        def claim_assigned(self, candidate, *, consumer_lease, authority_claim=None):
            assert authority_claim is not None
            claims.append(consumer_lease.consumer_id)
            return candidate

    class _Executor:
        def submit(self, *_args):
            return Future()

        def shutdown(self, **_kwargs):
            pass

    import tinyassets.provider_serving_binding as serving_module

    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "on")
    monkeypatch.setattr(consumer_module, "Epoch2BranchTaskAdapter", _Adapter)
    monkeypatch.setattr(
        serving_module,
        "list_serving_universes",
        lambda _base_path: ["universe-a", "universe-b"],
    )
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    consumer._executor.shutdown(wait=False, cancel_futures=True)
    consumer._executor = _Executor()

    assert consumer.poll_once() == 1
    assert consumer.poll_once() == 0
    assert claims == [consumer.consumer_id]
    assert not hasattr(consumer, "worker_id_for")
    consumer.stop()


def test_poll_once_halts_on_the_universe_pause_sentinel(tmp_path: Path, monkeypatch) -> None:
    """`.pause` must stop background claims and pumping for that universe.

    The P0 provider_exhaustion repair writes `.pause` into every universe; until the
    host-run fleet was deleted it also `docker stop`ped the worker. The daemon-owned
    consumer is now the only background executor, so it has to honour the sentinel
    itself -- and removing the file must resume the universe without a restart.
    Mutation: drop `_paused` from `poll_once` and the first assertion goes red.
    """
    task = Epoch2BranchTask(
        branch_task_id="bt2_" + "p" * 32,
        branch_def_id="branch-p",
        universe_id="universe-p",
        automation_id="automation-p",
        automation_executor_class="cloud",
        automation_branch_version="version-p",
    )
    claims: list[str] = []

    class _Adapter:
        def __init__(self, _base_path):
            pass

        def recover_expired(self, **_kwargs):
            return []

        def list_candidates(self, *, universe_id, limit):
            return [task]

        def claim_assigned(self, candidate, *, consumer_lease, authority_claim=None):
            claims.append(consumer_lease.consumer_id)
            return candidate

    class _Executor:
        def submit(self, *_args):
            return Future()

        def shutdown(self, **_kwargs):
            pass

    import tinyassets.provider_serving_binding as serving_module
    from tinyassets.storage.assigned_queue_refusals import AssignedQueueRefusalStore

    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "on")
    monkeypatch.setattr(consumer_module, "Epoch2BranchTaskAdapter", _Adapter)
    monkeypatch.setattr(
        serving_module, "list_serving_universes", lambda _base_path: ["universe-p"]
    )
    universe = tmp_path / "universe-p"
    universe.mkdir()
    pause = universe / ".pause"
    pause.write_text("", encoding="utf-8")
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    consumer._executor.shutdown(wait=False, cancel_futures=True)
    consumer._executor = _Executor()

    assert consumer.poll_once() == 0
    assert claims == []
    reasons = AssignedQueueRefusalStore(tmp_path).fresh_reasons(
        universe_id="universe-p", max_age_seconds=60
    )
    assert reasons == {"universe:universe-p:-": "paused"}

    pause.unlink()
    assert consumer.poll_once() == 1
    assert claims == [consumer.consumer_id]
    consumer.stop()


def test_task_exception_is_terminalized_without_escaping_daemon_boundary(
    tmp_path: Path, monkeypatch
) -> None:
    finishes: list[tuple[str, str]] = []

    class _Adapter:
        def __init__(self, _base_path):
            pass

        def finish(self, branch_task_id, *, worker_id, status, detail):
            finishes.append((branch_task_id, status))

    monkeypatch.setattr(consumer_module, "Epoch2BranchTaskAdapter", _Adapter)
    monkeypatch.setattr(
        "tinyassets.background_served_provider.start_background_queue_authority",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "tinyassets.background_served_provider.terminalize_background_queue_authority",
        lambda *_a, **_k: None,
    )
    from tinyassets.runtime.claimed_branch_execution import ClaimedBranchExecutorIdentity

    monkeypatch.setattr(
        "tinyassets.background_served_provider.load_background_executor_identity",
        lambda *_a, **_k: ClaimedBranchExecutorIdentity(
            daemon_id="daemon-a",
            worker_id="assigned-consumer:boot-a",
            runtime_instance_id="runtime-a",
        ),
    )
    monkeypatch.setattr(
        "tinyassets.background_served_provider.authorize_background_served_provider_call",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("task boom")),
    )
    task = Epoch2BranchTask(
        branch_task_id="bt2_" + "a" * 32,
        branch_def_id="branch-a",
        universe_id="universe-a",
        claimed_by="assigned-consumer:boot-a",
    )
    lease = AssignedConsumerLease(
        consumer_id="assigned-consumer:boot-a",
        lease_id="assigned-lease:boot-a",
        expires_at="2099-01-01T00:00:00+00:00",
    )
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)

    consumer._execute(task, lease)

    assert finishes == [(task.branch_task_id, "failed")]
    consumer.stop()


@pytest.mark.parametrize(
    "reason",
    [
        "background_binding_absent",
        "background_binding_inactive",
        "background_binding_expired",
        "background_binding_executor_identity_missing",
        "background_attempt_inactive",
        "background_attempt_lease_expired",
    ],
)
def test_background_binding_identity_failure_terminalizes_with_named_reason(
    tmp_path: Path, monkeypatch, reason: str
) -> None:
    finishes: list[dict[str, str]] = []

    class _Adapter:
        def __init__(self, _base_path):
            pass

        def finish(self, _branch_task_id, *, worker_id, status, detail):
            assert worker_id == "assigned-consumer:boot-a"
            assert status == "failed"
            finishes.append(detail)

    from tinyassets.background_served_provider import BackgroundExecutorIdentityError

    monkeypatch.setattr(consumer_module, "Epoch2BranchTaskAdapter", _Adapter)
    monkeypatch.setattr(
        "tinyassets.background_served_provider.start_background_queue_authority",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "tinyassets.background_served_provider.terminalize_background_queue_authority",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "tinyassets.background_served_provider.load_background_executor_identity",
        lambda *_a, **_k: (_ for _ in ()).throw(
            BackgroundExecutorIdentityError(reason)
        ),
    )
    task = Epoch2BranchTask(
        branch_task_id="bt2_" + "a" * 32,
        branch_def_id="branch-a",
        universe_id="universe-a",
        claimed_by="assigned-consumer:boot-a",
    )
    lease = AssignedConsumerLease(
        consumer_id="assigned-consumer:boot-a",
        lease_id="assigned-lease:boot-a",
        expires_at="2099-01-01T00:00:00+00:00",
    )
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)

    consumer._execute(task, lease)

    assert finishes == [{"error": reason}]
    consumer.stop()


def test_start_is_a_noop_when_dark(tmp_path, monkeypatch) -> None:
    """With the flag unset, start() spins up NO coordinator thread — the dark guarantee
    is 'no side effect when off', not merely 'no DB writes' (Codex #6, #2516)."""
    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    c = AssignedQueueConsumer(tmp_path)
    c.start()
    assert c._thread is None
    c.stop()
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "on")
    c.start()
    assert c._thread is not None
    c.stop()


def test_migrate_creates_no_background_authority_schema_when_dark(tmp_path) -> None:
    """A dark consumer leaves ZERO background-authority schema: migrate creates the
    epoch-2 tables but NOT the consumer's authority tables — the shared claim guard is
    missing-table-safe (Codex #6, #2516)."""
    import sqlite3

    from tinyassets.storage.request_admissions import migrate_request_admission_schema

    conn = sqlite3.connect(":memory:")
    try:
        migrate_request_admission_schema(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "branch_tasks_v2" in tables
        assert "background_branch_authority_owners" not in tables
        assert "background_branch_bindings" not in tables
    finally:
        conn.close()
