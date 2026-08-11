from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
)


class _RecordingProvider(BaseProvider):
    def __init__(self, name: str) -> None:
        self.name = name
        self.family = name
        self.calls = 0

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir=None,
    ) -> ProviderResponse:
        self.calls += 1
        return ProviderResponse(
            text=f"{self.name}:{prompt}",
            provider=self.name,
            model="fixture",
            family=self.family,
            latency_ms=1.0,
        )


def _definition() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "Served",
        "description": "router fixture",
        "tags": ["test"],
        "components": {"identity": {"kind": "soul", "config": {}}},
    }


def _binding() -> dict[str, object]:
    return {"schema_version": 1, "name": "Served", "role": "writer"}


def _served_context(
    tmp_path,
    *,
    capability_owner: str = "owner-1",
    path_backed: bool = False,
):
    from tinyassets.auth.middleware import (
        claim_provider_request,
        mint_provider_request_carrier,
        reserve_provider_request,
    )
    from tinyassets.config import load_universe_config
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    credential = {
        "credential_type": "llm_subscription",
        "service": "codex",
        "auth_json_b64": "e30=",
    }
    if path_backed:
        auth_home = universe_dir / "codex-auth"
        auth_home.mkdir()
        (auth_home / "auth.json").write_bytes(
            b'{"tokens":{"access_token":"first"}}'
        )
        credential = {
            "credential_type": "llm_subscription",
            "service": "codex",
            "codex_home": str(auth_home),
        }
    write_credential_vault(
        universe_dir,
        [credential],
        owner_user_id="owner-1",
        universe_id="u-owner",
    )
    definition = publish_definition(
        tmp_path,
        author_id="owner-1",
        payload=_definition(),
    )
    agent = create_binding(
        tmp_path,
        universe_id="u-owner",
        definition_id=definition["agent_definition_id"],
        created_by="owner-1",
        payload=_binding(),
    )
    connected = bind_serving_provider(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=1,
        provider="codex",
    )
    serving = set_serving(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"],
        enabled=True,
    )["agent_binding"]
    reserve = reserve_provider_request(
        principal_id=capability_owner,
        session_id="session-1",
        request_id="request-1",
        tool_name="converse",
    )
    capability = claim_provider_request(reserve, tool_name="converse")
    carrier = mint_provider_request_carrier(
        universe_id="u-owner",
        agent_binding_id=serving["agent_binding_id"],
        binding_revision=serving["revision"],
        operation="converse",
    )
    context = UniverseContext(
        universe_dir=universe_dir,
        config=load_universe_config(universe_dir),
        provider_request=carrier,
    )
    return universe_dir, serving, capability, context


def test_served_router_uses_only_universe_authorized_provider(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.providers.router import ProviderRouter

    _, _, capability, context = _served_context(tmp_path)
    codex = _RecordingProvider("codex")
    ambient = _RecordingProvider("claude-code")
    router = ProviderRouter({"codex": codex, "claude-code": ambient})
    try:
        response = asyncio.run(
            router.call(
                "writer",
                "hello",
                "system",
                operation="converse",
                universe_context=context,
            )
        )
    finally:
        revoke_provider_request(capability)

    assert response.provider == "codex"
    assert codex.calls == 1
    assert ambient.calls == 0


def test_served_router_fails_closed_without_exact_live_authority(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.provider_serving_binding import set_serving
    from tinyassets.providers.router import ProviderRouter

    universe_dir, serving, capability, context = _served_context(tmp_path)
    provider = _RecordingProvider("codex")
    router = ProviderRouter({"codex": provider})
    set_serving(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        agent_binding_id=serving["agent_binding_id"],
        expected_revision=serving["revision"],
        enabled=False,
    )
    try:
        with pytest.raises(ProviderAuthorityHeldError, match="Connect your provider"):
            asyncio.run(
                router.call(
                    "writer",
                    "must not run",
                    "system",
                    operation="converse",
                    universe_context=context,
                )
            )
    finally:
        revoke_provider_request(capability)
    assert provider.calls == 0


def test_served_router_rejects_request_principal_that_is_not_binding_owner(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.router import ProviderRouter

    _, _, capability, context = _served_context(
        tmp_path,
        capability_owner="visitor-1",
    )
    provider = _RecordingProvider("codex")
    try:
        with pytest.raises(ProviderAuthorityHeldError, match="Connect your provider"):
            asyncio.run(
                ProviderRouter({"codex": provider}).call(
                    "writer",
                    "must not run",
                    "system",
                    operation="converse",
                    universe_context=context,
                )
            )
    finally:
        revoke_provider_request(capability)
    assert provider.calls == 0


def test_served_router_rejects_credential_rotation_after_selection(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.router import ProviderRouter

    universe_dir, _, capability, context = _served_context(tmp_path)
    write_credential_vault(
        universe_dir,
        [{
            "credential_type": "llm_subscription",
            "service": "codex",
            "auth_json_b64": "eyJyb3RhdGVkIjp0cnVlfQ==",
        }],
    )
    provider = _RecordingProvider("codex")
    try:
        with pytest.raises(ProviderAuthorityHeldError, match="Connect your provider"):
            asyncio.run(
                ProviderRouter({"codex": provider}).call(
                    "writer",
                    "must not run",
                    "system",
                    operation="converse",
                    universe_context=context,
                )
            )
    finally:
        revoke_provider_request(capability)
    assert provider.calls == 0


def test_budget_reservation_revalidates_path_credential_at_moment_of_use(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.provider_assignment import (
        authorize_served_provider_call,
        reserve_served_provider_budget,
    )

    universe_dir, _, capability, context = _served_context(
        tmp_path,
        path_backed=True,
    )
    try:
        with authorize_served_provider_call(
            tmp_path,
            universe_dir=universe_dir,
            request_carrier=context.provider_request,
            role="writer",
            operation="converse",
        ) as authority:
            (universe_dir / "codex-auth" / "auth.json").write_bytes(
                b'{"tokens":{"access_token":"rotated"}}'
            )
            with pytest.raises(ProviderAuthorityHeldError, match="budget"):
                reserve_served_provider_budget(
                    tmp_path,
                    universe_dir=universe_dir,
                    authority=authority,
                    requested_output_tokens=8,
                    estimated_input_tokens=1,
                )
    finally:
        revoke_provider_request(capability)


@pytest.mark.parametrize("operation", [None, "run_graph"])
def test_universe_scoped_calls_never_route_from_config_without_live_authority(
    tmp_path,
    operation,
):
    from tinyassets.config import UniverseConfig
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.router import ProviderRouter

    universe_dir = tmp_path / "u-owner"
    universe_dir.mkdir()
    provider = _RecordingProvider("codex")
    context = UniverseContext(
        universe_dir=universe_dir,
        config=UniverseConfig(
            preferred_writer="codex",
            allowed_providers=["codex"],
            engine_assignment_state="ready",
        ),
    )

    with pytest.raises(ProviderAuthorityHeldError, match="Connect your provider"):
        asyncio.run(
            ProviderRouter({"codex": provider}).call(
                "writer",
                "must not run",
                "system",
                operation=operation,
                universe_context=context,
            )
        )
    assert provider.calls == 0


def test_served_budget_overrun_is_accounted_and_holds_future_calls(tmp_path, monkeypatch):
    import tinyassets.provider_serving_binding as serving_binding
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.router import ProviderRouter

    monkeypatch.setattr(serving_binding, "_MAX_TOKENS", 16)
    monkeypatch.setattr(serving_binding, "_MAX_COST_MICROUNITS", 1_600)
    _, _, capability, context = _served_context(tmp_path)

    class _OverBudgetProvider(_RecordingProvider):
        async def complete(self, prompt, system, config, *, universe_dir=None):
            self.calls += 1
            return ProviderResponse(
                text="overspent",
                provider=self.name,
                model="fixture",
                family=self.family,
                latency_ms=1.0,
                input_tokens=12,
                output_tokens=8,
                cost_microunits=2_000,
            )

    provider = _OverBudgetProvider("codex")
    router = ProviderRouter({"codex": provider})
    try:
        with pytest.raises(ProviderAuthorityHeldError, match="budget"):
            asyncio.run(
                router.call(
                    "writer",
                    "p",
                    "s",
                    config=ModelConfig(max_tokens=8),
                    operation="converse",
                    universe_context=context,
                )
            )
        with pytest.raises(ProviderAuthorityHeldError, match="budget"):
            asyncio.run(
                router.call(
                    "writer",
                    "p",
                    "s",
                    config=ModelConfig(max_tokens=1),
                    operation="converse",
                    universe_context=context,
                )
            )
    finally:
        revoke_provider_request(capability)
    assert provider.calls == 1


def test_served_turn_executes_real_codex_adapter_inside_os_sandbox(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.providers.codex_provider import CodexProvider
    from tinyassets.providers.router import ProviderRouter

    _, _, capability, context = _served_context(tmp_path)
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(
        b'\n'.join([
            json.dumps({
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "sandboxed reply"},
            }).encode(),
            json.dumps({
                "type": "turn.completed",
                "usage": {"input_tokens": 3, "output_tokens": 2},
            }).encode(),
        ]),
        b"",
    ))
    mock_proc.returncode = 0
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()
    captured: list[str] = []

    async def _fake_exec(*args, **kwargs):
        captured.extend(str(arg) for arg in args)
        return mock_proc

    try:
        with (
            patch(
                "tinyassets.providers.codex_provider._resolve_codex_cmd",
                return_value=(["/usr/bin/codex"], False),
            ),
            patch(
                "tinyassets.providers.codex_provider.get_sandbox_status",
                return_value={
                    "bwrap_available": True,
                    "bwrap_path": "/usr/bin/bwrap",
                    "reason": None,
                },
            ),
            patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
        ):
            response = asyncio.run(
                ProviderRouter({"codex": CodexProvider()}).call(
                    "writer",
                    "hello",
                    "system",
                    config=ModelConfig(sandbox_workspace=True, max_tokens=8),
                    operation="converse",
                    universe_context=context,
                )
            )
    finally:
        revoke_provider_request(capability)

    assert response.text == "sandboxed reply"
    assert response.input_tokens == 3
    assert response.output_tokens == 2
    assert captured[0] == "/usr/bin/bwrap"
    assert "--json" in captured
    assert "--ignore-user-config" in captured
    assert "--ignore-rules" in captured
    assert "shell_tool" in captured
    assert "unified_exec" in captured
    assert "--dangerously-bypass-approvals-and-sandbox" in captured


def test_served_request_budget_allows_reply_and_learning_only(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.router import ProviderRouter

    _, _, capability, context = _served_context(tmp_path)
    provider = _RecordingProvider("codex")
    router = ProviderRouter({"codex": provider})
    try:
        for prompt in ("reply", "learning"):
            asyncio.run(
                router.call(
                    "writer",
                    prompt,
                    "system",
                    operation="converse",
                    universe_context=context,
                )
            )
        with pytest.raises(ProviderAuthorityHeldError, match="Connect your provider"):
            asyncio.run(
                router.call(
                    "writer",
                    "third launch",
                    "system",
                    operation="converse",
                    universe_context=context,
                )
            )
    finally:
        revoke_provider_request(capability)
    assert provider.calls == 2
