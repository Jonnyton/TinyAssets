"""Credential-driven daemon execution without a provider-shaped fleet."""

from __future__ import annotations

import traceback
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from tinyassets.assigned_credential_execution import AssignedCredentialAuthority
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    UniverseContext,
    subprocess_env_for_provider,
)
from tinyassets.providers.router import ProviderRouter


def _authority(universe: Path, *, provider: str = "codex"):
    return AssignedCredentialAuthority(
        universe_id=universe.name,
        owner_user_id="owner-a",
        agent_binding_id="agent-a",
        binding_revision=3,
        provider=provider,
        credential_snapshot_dir=universe / "snapshot",
        binding_id="binding-a",
        binding_generation=4,
        binding_digest="sha256:" + "1" * 64,
        assignment_generation=3,
        assignment_digest="sha256:" + "3" * 64,
        binding_revocation_generation=0,
        credential_reference_id="credential-a",
        credential_reference_generation=7,
        credential_reference_digest="sha256:" + "2" * 64,
        credential_service="codex" if provider == "codex" else "claude",
        max_invocations=100,
        max_tokens=4096,
        max_cost_microunits=1_000_000,
        allowed_operations=("converse",),
        allowed_roles=("writer",),
    )


def _seed_serving_assignment(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    universe = tmp_path / "u-owner"
    universe.mkdir()
    write_credential_vault(
        universe,
        [{
            "credential_type": "llm_subscription",
            "service": "codex",
            "auth_json_b64": "e30=",
        }],
        owner_user_id="owner-1",
        universe_id=universe.name,
    )
    definition = publish_definition(
        tmp_path,
        author_id="owner-1",
        payload={
            "schema_version": 1,
            "name": "Assigned executor",
            "description": "Exact serving fixture",
            "tags": ["test"],
            "components": {
                "identity": {"kind": "soul", "config": {"voice": "direct"}},
            },
        },
    )
    agent = create_binding(
        tmp_path,
        universe_id=universe.name,
        definition_id=definition["agent_definition_id"],
        created_by="owner-1",
        payload={"schema_version": 1, "name": "Assigned", "role": "writer"},
    )
    connected = bind_serving_provider(
        base_path=tmp_path,
        universe_dir=universe,
        owner_user_id="owner-1",
        universe_id=universe.name,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=agent["revision"],
        provider="codex",
    )
    configured = connected["agent_binding"]
    serving = set_serving(
        base_path=tmp_path,
        universe_dir=universe,
        owner_user_id="owner-1",
        universe_id=universe.name,
        agent_binding_id=configured["agent_binding_id"],
        expected_revision=configured["revision"],
        enabled=True,
    )
    return universe, serving["agent_binding"]


@pytest.fixture(autouse=True)
def _assigned_budget(monkeypatch: pytest.MonkeyPatch):
    from tinyassets import provider_assignment

    def reserve(*_args, **kwargs):
        output_tokens = kwargs["requested_output_tokens"]
        return SimpleNamespace(
            output_tokens=output_tokens,
            reserved_total_tokens=output_tokens + 1,
            reserved_cost_microunits=(output_tokens + 1) * 100,
        )

    monkeypatch.setattr(
        provider_assignment,
        "reserve_served_provider_budget",
        reserve,
    )
    monkeypatch.setattr(
        provider_assignment,
        "finalize_served_provider_budget",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        provider_assignment,
        "abandon_served_provider_budget",
        lambda *_a, **_k: None,
    )


class _Provider(BaseProvider):
    def __init__(self, name: str, *, failure: Exception | None = None) -> None:
        self.name = name
        self.family = name
        self.failure = failure
        self.calls: list[Path | None] = []

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        self.calls.append(universe_dir)
        if self.failure is not None:
            raise self.failure
        return ProviderResponse(
            text=f"served-by-{self.name}",
            provider=self.name,
            model=self.name,
            family=self.family,
            latency_ms=1.0,
        )


@pytest.mark.asyncio
async def test_assigned_credential_routes_to_exact_provider(tmp_path: Path) -> None:
    codex = _Provider("codex")
    claude = _Provider("claude-code")
    router = ProviderRouter({codex.name: codex, claude.name: claude})
    context = UniverseContext(
        universe_dir=tmp_path,
        assigned_credential=_authority(tmp_path),
    )

    response = await router.call(
        "writer",
        "prompt",
        "system",
        operation="run_graph",
        universe_context=context,
    )

    assert response.provider == "codex"
    assert codex.calls == [tmp_path]
    assert claude.calls == []


@pytest.mark.asyncio
async def test_assigned_credential_failure_never_tries_another_provider(
    tmp_path: Path,
) -> None:
    codex = _Provider("codex", failure=ProviderUnavailableError("rate limited"))
    claude = _Provider("claude-code")
    router = ProviderRouter({codex.name: codex, claude.name: claude})
    context = UniverseContext(
        universe_dir=tmp_path,
        assigned_credential=_authority(tmp_path),
    )

    with pytest.raises(AllProvidersExhaustedError, match="Assigned provider 'codex'"):
        await router.call(
            "writer",
            "prompt",
            "system",
            operation="run_graph",
            universe_context=context,
        )

    assert codex.calls == [tmp_path]
    assert claude.calls == []


@pytest.mark.asyncio
async def test_node_policy_cannot_replace_assigned_provider(tmp_path: Path) -> None:
    codex = _Provider("codex")
    claude = _Provider("claude-code")
    router = ProviderRouter({codex.name: codex, claude.name: claude})
    context = UniverseContext(
        universe_dir=tmp_path,
        assigned_credential=_authority(tmp_path),
    )

    text, provider, _meta = await router.call_with_policy(
        "writer",
        "prompt",
        "system",
        {"preferred": {"provider": "claude-code"}},
        operation="run_graph",
        universe_context=context,
    )

    assert text == "served-by-codex"
    assert provider == "codex"
    assert codex.calls == [tmp_path]
    assert claude.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authority_update", "role"),
    [
        ({"allowed_operations": ("repository_spec_delivery",)}, "writer"),
        ({"allowed_roles": ("judge",)}, "writer"),
    ],
)
async def test_noncanonical_serving_scope_holds_before_provider_launch(
    tmp_path: Path,
    authority_update: dict[str, object],
    role: str,
) -> None:
    from tinyassets.exceptions import ProviderAuthorityHeldError

    provider = _Provider("codex")
    router = ProviderRouter({provider.name: provider})
    authority = replace(_authority(tmp_path), **authority_update)
    context = UniverseContext(universe_dir=tmp_path, assigned_credential=authority)

    with pytest.raises(ProviderAuthorityHeldError):
        await router.call(
            role,
            "prompt",
            "system",
            operation="run_graph",
            universe_context=context,
        )

    assert provider.calls == []


def test_no_universe_call_cannot_inherit_host_provider_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "ambient-codex"))
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-secret")

    with pytest.raises(ProviderUnavailableError, match="assigned credential"):
        subprocess_env_for_provider("codex")


def test_resolver_snapshots_exact_serving_credential_and_cleans_it(
    tmp_path: Path,
) -> None:
    from tinyassets import assigned_credential_execution as execution

    universe, agent = _seed_serving_assignment(tmp_path)

    with execution.resolve_assigned_credential(tmp_path, universe) as authority:
        assert authority.provider == "codex"
        assert authority.credential_snapshot_dir.is_dir()
        assert authority.agent_binding_id == agent["agent_binding_id"]
        assert authority.allowed_operations == ("converse",)
        assert authority.allowed_roles == ("writer",)
        assert authority.binding_id.startswith("pwb_")
        snapshot_dir = authority.credential_snapshot_dir

    assert not snapshot_dir.exists()


def test_resolver_maps_missing_assignment_to_typed_hold(tmp_path: Path) -> None:
    from tinyassets.assigned_credential_execution import (
        NO_REQUESTER_OWNED_EXECUTOR,
        NoRequesterOwnedExecutor,
        resolve_assigned_credential,
    )

    universe = tmp_path / "u-empty"
    universe.mkdir()

    with pytest.raises(NoRequesterOwnedExecutor) as held:
        with resolve_assigned_credential(tmp_path, universe):
            raise AssertionError("unreachable")

    assert held.value.reason == NO_REQUESTER_OWNED_EXECUTOR


def test_provider_body_exception_is_not_reclassified_as_credential_hold(
    tmp_path: Path,
) -> None:
    from tinyassets.assigned_credential_execution import resolve_assigned_credential

    universe, _agent = _seed_serving_assignment(tmp_path)
    with pytest.raises(RuntimeError, match="provider body failed"):
        with resolve_assigned_credential(tmp_path, universe):
            raise RuntimeError("provider body failed")


def test_snapshot_failure_secret_is_not_attached_to_typed_hold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tinyassets import assigned_credential_execution as execution

    universe, _agent = _seed_serving_assignment(tmp_path)

    def fail_snapshot(**_kwargs):
        raise ValueError("secret=must-not-leak")

    monkeypatch.setattr(execution, "snapshot_llm_subscription_credential", fail_snapshot)
    with pytest.raises(execution.NoRequesterOwnedExecutor) as caught:
        with execution.resolve_assigned_credential(tmp_path, universe):
            raise AssertionError("unreachable")

    rendered = "".join(traceback.format_exception(caught.value))
    assert "must-not-leak" not in rendered


def test_snapshot_is_cleaned_when_authority_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tinyassets import assigned_credential_execution as execution

    universe, _agent = _seed_serving_assignment(tmp_path)
    snapshot = SimpleNamespace(directory=universe / ".snapshot")
    cleaned: list[object] = []
    monkeypatch.setattr(
        execution,
        "snapshot_llm_subscription_credential",
        lambda **_kwargs: snapshot,
    )
    monkeypatch.setattr(execution, "cleanup_llm_credential_snapshot", cleaned.append)

    def fail_authority(**_kwargs):
        raise ValueError("construction failed")

    monkeypatch.setattr(execution, "AssignedCredentialAuthority", fail_authority)
    with pytest.raises(ValueError, match="construction failed"):
        with execution.resolve_assigned_credential(tmp_path, universe):
            raise AssertionError("unreachable")

    assert cleaned == [snapshot]


def test_refresh_pending_holds_tracks_current_credential_availability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tinyassets import assigned_credential_execution as execution
    from tinyassets.branch_tasks import BranchTask, append_task, read_queue

    universe = tmp_path / "u-a"
    universe.mkdir()
    append_task(
        universe,
        BranchTask(
            branch_task_id="task-a",
            branch_def_id="branch-a",
            universe_id="u-a",
        ),
    )

    def unavailable(*_args, **_kwargs):
        raise execution.NoRequesterOwnedExecutor()

    monkeypatch.setattr(execution, "assigned_credential_availability", unavailable)
    execution.refresh_pending_credential_holds(tmp_path, universe)
    assert read_queue(universe)[0].hold_reason == "no_requester_owned_executor"

    def available(*_args, **_kwargs):
        return object()

    monkeypatch.setattr(execution, "assigned_credential_availability", available)
    execution.refresh_pending_credential_holds(tmp_path, universe)
    assert read_queue(universe)[0].hold_reason == ""


def test_bound_branch_provider_call_carries_assigned_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tinyassets import assigned_credential_execution as execution

    universe = tmp_path / "u-a"
    universe.mkdir()
    authority = _authority(universe)

    @contextmanager
    def resolved(*_args, **_kwargs):
        yield authority

    monkeypatch.setattr(execution, "resolve_assigned_credential", resolved)
    seen: list[UniverseContext] = []

    def provider_call(_prompt: str, _system: str = "", **kwargs):
        seen.append(kwargs["universe_context"])
        return "ok"

    with execution.bind_assigned_provider_call(
        tmp_path,
        universe,
        provider_call,
    ) as bound:
        assert bound("prompt") == "ok"

    assert len(seen) == 1
    assert seen[0].universe_dir == universe
    assert seen[0].assigned_credential is authority


def test_daemon_does_not_claim_queue_when_credential_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from fantasy_daemon import __main__ as daemon_main
    from tinyassets import assigned_credential_execution as execution
    from tinyassets.branch_tasks import BranchTask, append_task, read_queue

    universe = tmp_path / "u-a"
    universe.mkdir()
    append_task(
        universe,
        BranchTask(
            branch_task_id="task-a",
            branch_def_id="branch-a",
            universe_id="u-a",
        ),
    )
    monkeypatch.setenv("TINYASSETS_UNIFIED_EXECUTION", "1")
    monkeypatch.setenv("TINYASSETS_DISPATCHER_ENABLED", "on")

    def unavailable(base_path: Path, universe_dir: Path) -> bool:
        assert Path(base_path) == tmp_path
        assert Path(universe_dir) == universe
        from tinyassets.branch_tasks import set_task_hold_reason

        set_task_hold_reason(
            universe,
            "task-a",
            execution.NO_REQUESTER_OWNED_EXECUTOR,
        )
        return False

    monkeypatch.setattr(
        execution,
        "refresh_pending_credential_holds",
        unavailable,
    )

    claimed, inputs = daemon_main._try_dispatcher_pick(universe, "daemon-a")

    assert claimed is None
    assert inputs == {}
    queued = read_queue(universe)[0]
    assert queued.status == "pending"
    assert queued.hold_reason == execution.NO_REQUESTER_OWNED_EXECUTOR
