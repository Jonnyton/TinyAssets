from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from tests.test_agent_runtime_invocation import NOW, _request
from tests.test_agent_runtime_provider_call import _execution_service, _RecordingProvider
from tinyassets.agent_runtime_provider_execution import (
    AgentRuntimeProviderExecutionService,
)
from tinyassets.providers.router import ProviderRouter
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import AutomationActivationStore


def _restarted(service, tmp_path, *, seconds: int):
    return AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=service.grant_resolver,
        provider_binding_resolver=service.provider_binding_resolver,
        clock=lambda: NOW + timedelta(seconds=seconds),
    )


def test_private_health_reports_admission_as_useful_progress(
    tmp_path, authenticate_request, monkeypatch
) -> None:
    from tinyassets.agent_runtime_health import AgentRuntimeHealthState

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    monkeypatch.setattr(
        AgentRuntimeProviderExecutionService,
        "_validated_store_grant",
        lambda *_args, **_kwargs: pytest.fail("health must not mint store authority"),
    )

    health = service.project_useful_progress(
        admitted.invocation.invocation_id,
        no_progress_after_seconds=60,
    )

    assert health.state is AgentRuntimeHealthState.ACTIVE
    assert health.useful_milestone == "invocation_admitted"
    assert health.no_progress_seconds == 0
    assert health.authority_current is True
    assert health.alarm is None


def test_heartbeat_churn_cannot_hide_stall_and_alarm_deduplicates(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_health import AgentRuntimeHealthState

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)
    continuation = service.prepare_continuation(invocation_id).record
    assert continuation is not None
    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute("CREATE TABLE irrelevant_heartbeats (invocation_id TEXT, seen_at TEXT)")
        connection.executemany(
            "INSERT INTO irrelevant_heartbeats VALUES (?, ?)",
            [(invocation_id, f"2026-08-02T12:00:{second:02d}Z") for second in range(10)],
        )

    def observe(_index: int):
        return _restarted(service, tmp_path, seconds=61).project_useful_progress(
            invocation_id,
            no_progress_after_seconds=60,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(observe, range(8)))

    assert all(item.state is AgentRuntimeHealthState.STALLED for item in results)
    assert all(item.useful_milestone == "continuation_prepared" for item in results)
    assert len({item.alarm.alarm_id for item in results if item.alarm}) == 1
    with sqlite3.connect(db_path(tmp_path)) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM agent_runtime_no_progress_alarms").fetchone()[
                0
            ]
            == 1
        )
    changed_threshold = _restarted(service, tmp_path, seconds=61).project_useful_progress(
        invocation_id,
        no_progress_after_seconds=30,
    )
    assert changed_threshold.alarm is not None
    assert changed_threshold.alarm.threshold_seconds == 30
    assert changed_threshold.alarm.alarm_id != results[0].alarm.alarm_id
    with sqlite3.connect(db_path(tmp_path)) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM agent_runtime_no_progress_alarms").fetchone()[
                0
            ]
            == 2
        )


def test_terminal_outcome_is_useful_progress_and_never_alarms(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_health import AgentRuntimeHealthState

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    result = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": _RecordingProvider()}),
    )

    health = _restarted(service, tmp_path, seconds=1_000).project_useful_progress(
        admitted.invocation.invocation_id,
        no_progress_after_seconds=60,
    )

    assert health.state is AgentRuntimeHealthState.TERMINAL
    assert health.useful_milestone == "provider_outcome_recorded"
    assert health.terminal_outcome_state == result.state.value
    assert health.alarm is None


def test_health_refuses_partial_continuation_lineage(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
    )

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    reservation = service.reserve(invocation_id).record
    assert reservation is not None
    assert service.prepare_continuation(invocation_id).record is not None

    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            "DELETE FROM provider_invocation_reservations WHERE reservation_id = ?",
            (reservation.reservation_id,),
        )

    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="incomplete"):
        service.project_useful_progress(
            invocation_id,
            no_progress_after_seconds=60,
        )


def test_health_refuses_self_consistent_continuation_not_anchored_to_command(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
    )
    from tinyassets.cloud_automation_continuation import (
        AgentInvocationCloudContinuation,
    )

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)
    continuation = service.prepare_continuation(invocation_id).record
    assert isinstance(continuation, AgentInvocationCloudContinuation)
    values = {
        name: getattr(continuation, name)
        for name in AgentInvocationCloudContinuation._FIELDS
        if name != "continuation_digest"
    }
    values["typed_input_digest"] = f"sha256:{'9' * 64}"
    tampered = AgentInvocationCloudContinuation.build(**values)
    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            """
            UPDATE cloud_execution_continuations
            SET continuation_digest = ?, record_json = ?
            WHERE continuation_id = ?
            """,
            (
                tampered.continuation_digest,
                json.dumps(
                    tampered.to_dict(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                tampered.continuation_id,
            ),
        )

    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="lineage"):
        service.project_useful_progress(
            invocation_id,
            no_progress_after_seconds=60,
        )


def test_stale_activation_is_visible_and_cannot_report_healthy(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_health import AgentRuntimeHealthState

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    activation_store = AutomationActivationStore(tmp_path, clock=lambda: NOW)
    active = activation_store.get(
        admitted.command.universe_id,
        admitted.command.activation_automation_id,
    )
    assert active is not None
    assert activation_store.stop(expected=active) is not None

    health = service.project_useful_progress(
        admitted.invocation.invocation_id,
        no_progress_after_seconds=60,
    )

    assert health.state is AgentRuntimeHealthState.BLOCKED
    assert health.authority_current is False
    assert health.alarm is None


def test_stale_provider_budget_pin_is_visible_as_blocked(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_health import AgentRuntimeHealthState

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    service.provider_binding_resolver.revoke()

    health = service.project_useful_progress(
        admitted.invocation.invocation_id,
        no_progress_after_seconds=60,
    )

    assert health.state is AgentRuntimeHealthState.BLOCKED
    assert health.authority_current is False


def test_future_useful_progress_timestamp_fails_closed(tmp_path, authenticate_request) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
    )

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    observer = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=service.grant_resolver,
        provider_binding_resolver=service.provider_binding_resolver,
        clock=lambda: NOW - timedelta(seconds=1),
    )

    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="in the future"):
        observer.project_useful_progress(
            admitted.invocation.invocation_id,
            no_progress_after_seconds=60,
        )


def test_forged_alarm_payload_fails_integrity_replay(tmp_path, authenticate_request) -> None:
    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id
    observer = _restarted(service, tmp_path, seconds=61)
    first = observer.project_useful_progress(
        invocation_id,
        no_progress_after_seconds=60,
    )
    assert first.alarm is not None
    with sqlite3.connect(db_path(tmp_path)) as connection:
        row = connection.execute(
            "SELECT record_json FROM agent_runtime_no_progress_alarms"
        ).fetchone()
        payload = json.loads(row[0])
        payload["raised_at"] = "2099-01-01T00:00:00Z"
        connection.execute(
            "UPDATE agent_runtime_no_progress_alarms SET record_json = ?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")),),
        )

    with pytest.raises(ValueError, match="integrity"):
        observer.project_useful_progress(
            invocation_id,
            no_progress_after_seconds=60,
        )
