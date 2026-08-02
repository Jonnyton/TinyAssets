from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest

from tests.test_agent_runtime_invocation import NOW, _request
from tests.test_agent_runtime_provider_execution import _admitted_invocation
from tinyassets.provider_work_authority import ProviderInvocationReservationState
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
from tinyassets.providers.router import ProviderRouter
from tinyassets.storage import db_path


class _RecordingProvider(BaseProvider):
    name = "codex"
    family = "gpt"

    def __init__(
        self,
        *,
        text: str = "approved patch",
        error: Exception | None = None,
        on_call=None,
    ):
        self.text = text
        self.error = error
        self.on_call = on_call
        self.calls: list[tuple[str, str, ModelConfig, Path | None]] = []

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        self.calls.append((prompt, system, config, universe_dir))
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        return ProviderResponse(
            text=self.text,
            provider=self.name,
            model="gpt-test",
            family=self.family,
            latency_ms=12.5,
        )


def _execution_service(tmp_path, authenticate_request):
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    manifest, grant_resolver, provider_resolver, _admission, admitted = _admitted_invocation(
        tmp_path, authenticate_request
    )
    universe_dir = tmp_path / "universes" / "universe_alice"
    universe_dir.mkdir(parents=True)
    with sqlite3.connect(db_path(tmp_path)) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS universes (
                universe_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                host_path TEXT NOT NULL,
                created_at REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO universes VALUES (?, ?, ?, ?, ?)",
            ("universe_alice", "Alice", str(universe_dir), NOW.timestamp(), "{}"),
        )
    return (
        AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=grant_resolver,
            provider_binding_resolver=provider_resolver,
            clock=lambda: NOW,
        ),
        admitted,
        universe_dir,
        manifest,
    )


def test_actual_provider_call_uses_exact_manifest_input_and_registered_universe(
    tmp_path, authenticate_request, monkeypatch
) -> None:
    from tinyassets.agent_runtime_provider_execution import AgentProviderOutcomeState

    service, admitted, universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    wrong_universe = tmp_path / "ambient-other-universe"
    wrong_universe.mkdir()
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(wrong_universe))
    provider = _RecordingProvider()
    router = ProviderRouter({"codex": provider})

    result = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=router,
    )

    assert result.state is AgentProviderOutcomeState.SUCCEEDED
    assert result.typed_output == {
        "kind": "provider_text",
        "text": "approved patch",
    }
    assert result.provider == "codex"
    assert result.model == "gpt-test"
    assert result.invocation_id == admitted.invocation.invocation_id
    assert len(provider.calls) == 1
    prompt, system, config, seen_universe = provider.calls[0]
    assert '"kind":"repository_patch_request"' in prompt
    assert system == "apply the typed request"
    assert config.max_tokens == admitted.command.budget.max_tokens
    assert seen_universe == universe_dir.resolve()
    assert seen_universe != wrong_universe.resolve()
    assert service.get_provider_outcome(admitted.invocation.invocation_id) == result
    reservation = service.provider_store.get_reservation(result.reservation_id)
    assert reservation is not None
    assert reservation.state is ProviderInvocationReservationState.SUCCEEDED
    replay = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=router,
    )
    assert replay == result
    assert len(provider.calls) == 1


def test_changed_typed_input_is_rejected_before_reservation_or_call(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
    )

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    provider = _RecordingProvider()

    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="typed input"):
        service.execute_provider_call(
            admitted.invocation.invocation_id,
            typed_input={"kind": "repository_patch_request", "request": "different"},
            router=ProviderRouter({"codex": provider}),
        )

    assert provider.calls == []
    assert service.get_continuation(admitted.invocation.invocation_id) is None
    assert service.get_provider_outcome(admitted.invocation.invocation_id) is None


def test_provider_error_is_indeterminate_and_never_falls_back(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import AgentProviderOutcomeState
    from tinyassets.exceptions import ProviderTimeoutError

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    selected = _RecordingProvider(error=ProviderTimeoutError("uncertain timeout"))
    fallback = _RecordingProvider(text="must not run")
    fallback.name = "ollama-local"

    result = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": selected, "ollama-local": fallback}),
    )

    assert result.state is AgentProviderOutcomeState.INDETERMINATE
    assert result.typed_output is None
    assert result.blocker_code == "provider_call_indeterminate"
    assert len(selected.calls) == 1
    assert fallback.calls == []
    reservation = service.provider_store.get_reservation(result.reservation_id)
    assert reservation is not None
    assert reservation.state is ProviderInvocationReservationState.INDETERMINATE


def test_oversized_provider_output_is_failed_without_persisting_text(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import AgentProviderOutcomeState

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    provider = _RecordingProvider(text="x" * (64 * 1024))

    result = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": provider}),
    )

    assert result.state is AgentProviderOutcomeState.FAILED
    assert result.typed_output is None
    assert result.blocker_code == "provider_output_too_large"
    with sqlite3.connect(db_path(tmp_path)) as connection:
        raw = connection.execute(
            "SELECT record_json FROM agent_invocation_provider_outcomes"
        ).fetchone()[0]
    assert "x" * 1024 not in raw
    reservation = service.provider_store.get_reservation(result.reservation_id)
    assert reservation is not None
    assert reservation.state is ProviderInvocationReservationState.FAILED


def test_authority_lost_during_call_records_indeterminate_not_output(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import AgentProviderOutcomeState

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    provider = _RecordingProvider(
        text="must not finalize",
        on_call=service.provider_binding_resolver.revoke,
    )

    result = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": provider}),
    )

    assert result.state is AgentProviderOutcomeState.INDETERMINATE
    assert result.typed_output is None
    assert result.blocker_code == "provider_authority_lost_after_call"
    reservation = service.provider_store.get_reservation(result.reservation_id)
    assert reservation is not None
    assert reservation.state is ProviderInvocationReservationState.INDETERMINATE


@pytest.mark.parametrize("stage", ["admitted", "reserved", "prepared"])
def test_restart_before_launch_resumes_same_reservation_and_spends_once(
    tmp_path, authenticate_request, stage
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id
    original = None
    original_continuation = None
    if stage in {"reserved", "prepared"}:
        service.issue_receipt(invocation_id)
        service.claim(invocation_id)
        original = service.reserve(invocation_id).record
        assert original is not None
    if stage == "prepared":
        original_continuation = service.prepare_continuation(invocation_id).record

    restarted = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=service.grant_resolver,
        provider_binding_resolver=service.provider_binding_resolver,
        clock=lambda: NOW,
    )

    provider = _RecordingProvider()
    result = restarted.execute_provider_call(
        invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": provider}),
    )

    assert result.state.value == "succeeded"
    if original is not None:
        assert result.reservation_id == original.reservation_id
    if original_continuation is not None:
        assert result.continuation_id == original_continuation.continuation_id
    assert len(provider.calls) == 1


def test_uncertain_launch_waits_for_original_claim_then_blocks_without_remint(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentProviderOutcomeState,
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id
    service.issue_receipt(invocation_id)
    service.claim(invocation_id)
    service.reserve(invocation_id)
    continuation = service.prepare_continuation(invocation_id).record
    assert continuation is not None
    service.arm_launch(invocation_id)
    launched = service.provider_store.get_reservation(continuation.reservation_id)
    assert launched is not None

    provider = _RecordingProvider()
    restarted_before_expiry = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=service.grant_resolver,
        provider_binding_resolver=service.provider_binding_resolver,
        clock=lambda: NOW,
    )
    with pytest.raises(
        AgentRuntimeProviderExecutionBlocked,
        match="requires uncertain-call reconciliation",
    ):
        restarted_before_expiry.execute_provider_call(
            invocation_id,
            typed_input=_request().typed_input,
            router=ProviderRouter({"codex": provider}),
        )
    assert provider.calls == []
    assert service.provider_store.get_reservation(launched.reservation_id) == launched

    with pytest.raises(AgentRuntimeProviderExecutionBlocked, match="may still be active"):
        service.reconcile_uncertain_provider_call(invocation_id)

    def recover(_index: int):
        return AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=service.grant_resolver,
            provider_binding_resolver=service.provider_binding_resolver,
            clock=lambda: NOW + timedelta(seconds=301),
        ).reconcile_uncertain_provider_call(invocation_id)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(recover, range(8)))
    result = results[0]
    assert len({item.outcome_digest for item in results}) == 1
    recovered = AgentRuntimeProviderExecutionService(
        tmp_path,
        grant_resolver=service.grant_resolver,
        provider_binding_resolver=service.provider_binding_resolver,
        clock=lambda: NOW + timedelta(seconds=301),
    )

    assert result.state is AgentProviderOutcomeState.INDETERMINATE
    assert result.blocker_code == "provider_call_lost_after_launch"
    assert result.invocation_id == invocation_id
    assert result.continuation_id == continuation.continuation_id
    assert result.reservation_id == launched.reservation_id
    assert result.launch_reservation_digest == launched.reservation_digest
    assert recovered.reconcile_uncertain_provider_call(invocation_id) == result
    terminal = recovered.provider_store.get_reservation(launched.reservation_id)
    assert terminal is not None
    assert terminal.state is ProviderInvocationReservationState.INDETERMINATE
    with sqlite3.connect(db_path(tmp_path)) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM agent_invocation_provider_outcomes"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM provider_invocation_reservations").fetchone()[
                0
            ]
            == 1
        )
