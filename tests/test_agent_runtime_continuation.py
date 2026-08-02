from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_agent_runtime_invocation import NOW, _capture, _request
from tests.test_agent_runtime_provider_execution import _admitted_invocation
from tinyassets.agent_runtime_invocation import AgentInvocationConflict
from tinyassets.agent_runtime_provider_execution import (
    AgentRuntimeProviderExecutionBlocked,
    AgentRuntimeProviderExecutionService,
)
from tinyassets.cloud_automation_continuation import (
    AgentInvocationCloudContinuation,
    CloudContinuationWriteOutcome,
)
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import AutomationActivationStore


def _service(tmp_path, grant_resolver, provider_resolver):
    return AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=grant_resolver,
        provider_binding_resolver=provider_resolver,
        clock=lambda: NOW,
    )


def test_agent_continuation_replays_exact_runtime_identities_without_branch_attempt(
    tmp_path, authenticate_request
) -> None:
    _manifest, grant_resolver, provider_resolver, _admission, admitted = (
        _admitted_invocation(tmp_path, authenticate_request)
    )
    invocation_id = admitted.invocation.invocation_id
    service = _service(tmp_path, grant_resolver, provider_resolver)
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    reservation = service.reserve(invocation_id).record
    assert reservation is not None

    first = service.prepare_continuation(invocation_id)
    replay = _service(tmp_path, grant_resolver, provider_resolver).prepare_continuation(
        invocation_id
    )

    assert first.outcome is CloudContinuationWriteOutcome.APPLIED
    assert replay.outcome is CloudContinuationWriteOutcome.REPLAYED
    assert replay.record == first.record
    assert isinstance(first.record, AgentInvocationCloudContinuation)
    assert first.record.invocation_id == invocation_id
    assert first.record.command_id == admitted.command.command_id
    assert first.record.execution_subject == admitted.command.execution_subject
    assert first.record.reservation_id == reservation.reservation_id
    assert first.record.activation_lease_id == admitted.command.lease_id
    with sqlite3.connect(db_path(tmp_path)) as connection:
        background_attempt_tables = connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name = 'background_branch_attempts'
            """
        ).fetchone()[0]
    assert background_attempt_tables == 0


def test_concurrent_agent_continuation_preparation_has_one_identity(
    tmp_path, authenticate_request
) -> None:
    _manifest, grant_resolver, provider_resolver, _admission, admitted = (
        _admitted_invocation(tmp_path, authenticate_request)
    )
    invocation_id = admitted.invocation.invocation_id
    service = _service(tmp_path, grant_resolver, provider_resolver)
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)

    def prepare(_index: int):
        return _service(tmp_path, grant_resolver, provider_resolver).prepare_continuation(
            invocation_id
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(prepare, range(8)))

    assert sum(
        result.outcome is CloudContinuationWriteOutcome.APPLIED for result in results
    ) == 1
    assert len({result.record.continuation_id for result in results}) == 1


def test_restart_after_launch_arm_reconciles_existing_continuation(
    tmp_path, authenticate_request
) -> None:
    _manifest, grant_resolver, provider_resolver, _admission, admitted = (
        _admitted_invocation(tmp_path, authenticate_request)
    )
    invocation_id = admitted.invocation.invocation_id
    service = _service(tmp_path, grant_resolver, provider_resolver)
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)
    prepared = service.prepare_continuation(invocation_id).record
    assert prepared is not None
    service.arm_launch(invocation_id)

    replay = _service(tmp_path, grant_resolver, provider_resolver).prepare_continuation(
        invocation_id
    )
    assert replay.outcome is CloudContinuationWriteOutcome.REPLAYED
    assert replay.record == prepared


def test_agent_continuation_revalidates_activation_before_write(
    tmp_path, authenticate_request
) -> None:
    _manifest, grant_resolver, provider_resolver, admission, admitted = (
        _admitted_invocation(tmp_path, authenticate_request)
    )
    invocation_id = admitted.invocation.invocation_id
    service = _service(tmp_path, grant_resolver, provider_resolver)
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)
    activation_store = AutomationActivationStore(tmp_path, clock=lambda: NOW)
    active = activation_store.get(
        admitted.command.universe_id,
        admitted.command.activation_automation_id,
    )
    assert active is not None
    assert activation_store.stop(expected=active) is not None

    with pytest.raises(
        AgentRuntimeProviderExecutionBlocked,
        match="activation is not current",
    ):
        service.prepare_continuation(invocation_id)

    with sqlite3.connect(db_path(tmp_path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM cloud_execution_continuations"
        ).fetchone()[0]
    assert count == 0


def test_changed_input_still_conflicts_before_second_continuation(
    tmp_path, authenticate_request
) -> None:
    _manifest, grant_resolver, provider_resolver, admission, admitted = (
        _admitted_invocation(tmp_path, authenticate_request)
    )
    invocation_id = admitted.invocation.invocation_id
    service = _service(tmp_path, grant_resolver, provider_resolver)
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)
    first = service.prepare_continuation(invocation_id)

    with pytest.raises(AgentInvocationConflict):
        admission.admit(
            _capture(admission),
            _request(
                typed_input={
                    "kind": "repository_patch_request",
                    "repository": "github:alice/example",
                    "request": "a different patch",
                }
            ),
        )
    assert service.get_continuation(invocation_id) == first.record
