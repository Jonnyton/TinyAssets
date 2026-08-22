from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from unittest.mock import patch

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


def _fresh_served_request(universe_dir, serving, *, request_id: str):
    from tinyassets.auth.middleware import (
        claim_provider_request,
        mint_provider_request_carrier,
        reserve_provider_request,
    )
    from tinyassets.config import load_universe_config

    reserve = reserve_provider_request(
        principal_id="owner-1",
        session_id=f"session-{request_id}",
        request_id=request_id,
        tool_name="converse",
    )
    capability = claim_provider_request(reserve, tool_name="converse")
    carrier = mint_provider_request_carrier(
        universe_id="u-owner",
        agent_binding_id=serving["agent_binding_id"],
        binding_revision=serving["revision"],
        operation="converse",
    )
    return capability, UniverseContext(
        universe_dir=universe_dir,
        config=load_universe_config(universe_dir),
        provider_request=carrier,
    )


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


def test_served_budget_overrun_is_per_call_and_releases_after_settle(tmp_path, monkeypatch):
    """An overrun is caught at ITS OWN settlement and does not brick the binding.

    The token/cost budget bounds only IN-FLIGHT reserved spend (2026-08-19 fix):
    a turn that overruns its reservation is held at that turn's settlement, but
    once it SETTLES the hold is RELEASED, so the next turn is admitted fresh
    (bounded per-turn by its own ``max_tokens``) instead of being permanently
    bricked. Under the old cumulative-lifetime semantics a single settled overrun
    held every future call at reservation time (``provider.calls == 1``); now both
    turns reach the provider and are each independently caught (``== 2``). The
    separate cumulative runaway guard is the invocation high-water — see
    ``test_binding_generation_high_water_blocks_runaway_across_requests``.
    """
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
        # Turn 1 overruns its reservation -> held at ITS settlement.
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
        # The settled overrun RELEASED its in-flight hold, so turn 2 is admitted
        # fresh (not permanently bricked). It overruns again and is likewise held
        # -- but only AFTER reaching the provider, at its own settlement.
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
    # Both turns REACHED the provider: a settled overrun does not pre-block the
    # next call. (Old cumulative-lifetime semantics held turn 2 at reservation
    # time with provider.calls == 1.)
    assert provider.calls == 2


@pytest.mark.skipif(os.name == "nt", reason="bubblewrap is a POSIX sandbox")
def test_served_turn_spawns_fake_codex_through_full_os_sandbox_command(
    tmp_path,
    monkeypatch,
):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.providers.codex_provider import CodexProvider
    from tinyassets.providers.router import ProviderRouter

    universe_dir, _, capability, context = _served_context(
        tmp_path,
        path_backed=True,
    )
    install_root = tmp_path / "codex-install"
    real_codex = install_root / "node_modules" / ".bin" / "codex"
    real_codex.parent.mkdir(parents=True)
    real_codex.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path

auth = json.loads((Path(os.environ["CODEX_HOME"]) / "auth.json").read_text())
print(json.dumps({
    "type": "item.completed",
    "item": {
        "type": "agent_message",
        "text": auth["tokens"]["access_token"],
    },
}))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}}))
""",
        encoding="utf-8",
    )
    real_codex.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "codex"
    wrapper.write_text(
        f'#!/usr/bin/env bash\nCODEX_BIN="{real_codex}"\nexec "$CODEX_BIN" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    bwrap_log = tmp_path / "bwrap-args.json"
    fake_bwrap = tmp_path / "fake-bwrap"
    fake_bwrap.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open({str(bwrap_log)!r}, "w", encoding="utf-8") as stream:
    json.dump(args, stream)
env = os.environ.copy()
for index, value in enumerate(args[:-2]):
    if value == "--ro-bind" and args[index + 2] == "/codex-home/auth.json":
        env["CODEX_HOME"] = os.path.dirname(args[index + 1])
separator = args.index("--")
command = args[separator + 1:]
os.execvpe(command[0], command, env)
""",
        encoding="utf-8",
    )
    fake_bwrap.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    try:
        with patch(
                "tinyassets.providers.codex_provider.get_sandbox_status",
                return_value={
                    "bwrap_available": True,
                    "bwrap_path": str(fake_bwrap),
                    "reason": None,
                },
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

    assert response.text == "first"
    assert response.input_tokens == 3
    assert response.output_tokens == 2
    captured = json.loads(bwrap_log.read_text(encoding="utf-8"))
    inner = captured[captured.index("--") + 1:]
    assert "--full-auto" in inner
    assert "--json" in inner
    assert "--ignore-user-config" in inner
    assert "--ignore-rules" in inner
    assert "shell_tool" in inner
    assert "unified_exec" in inner
    assert "--dangerously-bypass-approvals-and-sandbox" not in inner
    assert (
        "--tmpfs",
        "/workspace/.runtime/provider-launch-credentials",
    ) in zip(captured, captured[1:])
    mount_pairs = list(zip(captured, captured[1:], captured[2:]))
    assert ("--ro-bind", str(install_root), str(install_root)) in mount_pairs
    # CODEX_HOME is a private tmpfs (codex's launcher needs to create .lock)
    # with the snapshot's credential FILES bound read-only into it.
    assert ("--tmpfs", "/codex-home") in zip(captured, captured[1:])
    snapshot_mount = os.path.dirname(next(
        source
        for flag, source, target in mount_pairs
        if flag == "--ro-bind" and target == "/codex-home/auth.json"
    ))
    assert snapshot_mount != str(universe_dir / "codex-auth")
    # Never a writable bind of the snapshot, and never the snapshot dir itself.
    assert not any(
        flag == "--bind" and target.startswith("/codex-home")
        for flag, _source, target in mount_pairs
    )
    assert not any(
        flag == "--ro-bind" and target == "/codex-home"
        for flag, _source, target in mount_pairs
    )
    assert not os.path.exists(snapshot_mount)


def test_codex_wrapper_resolution_mounts_real_binary_tree(tmp_path):
    from tinyassets.providers.codex_provider import _codex_sandbox_mounts

    install_root = tmp_path / "codex-install"
    real_codex = install_root / "node_modules" / ".bin" / "codex"
    real_codex.parent.mkdir(parents=True)
    real_codex.write_text("fake executable", encoding="utf-8")
    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "codex"
    wrapper.write_text(
        f'#!/usr/bin/env bash\nCODEX_BIN="{real_codex}"\nexec "$CODEX_BIN" "$@"\n',
        encoding="utf-8",
    )

    mounts = _codex_sandbox_mounts([str(wrapper)])

    assert install_root.resolve() in mounts
    assert wrapper_dir.resolve() in mounts


def test_codex_wrapper_resolution_fails_closed_when_real_tree_is_missing(tmp_path):
    from tinyassets.exceptions import ProviderError
    from tinyassets.providers.codex_provider import _codex_sandbox_mounts

    wrapper = tmp_path / "codex"
    wrapper.write_text(
        '#!/usr/bin/env bash\nCODEX_BIN="/missing/codex-install/codex"\n',
        encoding="utf-8",
    )

    with pytest.raises(ProviderError, match="wrapper's real binary"):
        _codex_sandbox_mounts([str(wrapper)])


@pytest.mark.skipif(
    not (
        os.environ.get("TINYASSETS_REAL_CODEX_TEST_UNIVERSE")
        and os.environ.get("TINYASSETS_REAL_CODEX_TEST_SNAPSHOT")
    ),
    reason=(
        "set TINYASSETS_REAL_CODEX_TEST_UNIVERSE and "
        "TINYASSETS_REAL_CODEX_TEST_SNAPSHOT for the true Codex integration"
    ),
)
def test_true_codex_binary_served_adapter_integration():
    from pathlib import Path

    from tinyassets.providers.codex_provider import CodexProvider

    universe_dir = Path(os.environ["TINYASSETS_REAL_CODEX_TEST_UNIVERSE"])
    snapshot_dir = Path(os.environ["TINYASSETS_REAL_CODEX_TEST_SNAPSHOT"])
    response = asyncio.run(
        CodexProvider().complete(
            "Reply with only: integration-ok",
            "",
            ModelConfig(
                sandbox_workspace=True,
                max_tokens=32,
                credential_snapshot_dir=snapshot_dir,
            ),
            universe_dir=universe_dir,
        )
    )
    assert response.text == "integration-ok"


def test_path_backed_credential_snapshot_seals_inflight_cross_process_rotation(
    tmp_path,
):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.provider_assignment import load_provider_assignment
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving
    from tinyassets.providers.router import ProviderRouter

    universe_dir, serving, capability, context = _served_context(
        tmp_path,
        path_backed=True,
    )
    original_assignment = load_provider_assignment(tmp_path, universe_id="u-owner")

    class _SnapshotProvider(_RecordingProvider):
        def __init__(self, *, pause: bool) -> None:
            super().__init__("codex")
            self.pause = pause
            self.started = asyncio.Event()
            self.resume = asyncio.Event()
            self.snapshot_paths = []

        async def complete(self, prompt, system, config, *, universe_dir=None):
            self.calls += 1
            snapshot = config.credential_snapshot_dir
            assert snapshot is not None
            self.snapshot_paths.append(snapshot)
            auth_file = snapshot / "auth.json"
            before = json.loads(auth_file.read_text(encoding="utf-8"))
            self.started.set()
            if self.pause:
                await self.resume.wait()
            after = json.loads(auth_file.read_text(encoding="utf-8"))
            assert after == before
            return ProviderResponse(
                text=after["tokens"]["access_token"],
                provider=self.name,
                model="fixture",
                family=self.family,
                latency_ms=1.0,
            )

    provider = _SnapshotProvider(pause=True)

    async def _rotate_during_call():
        task = asyncio.create_task(
            ProviderRouter({"codex": provider}).call(
                "writer",
                "hello",
                "system",
                operation="converse",
                universe_context=context,
            )
        )
        await provider.started.wait()
        auth_file = universe_dir / "codex-auth" / "auth.json"
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; Path(r'"
                + str(auth_file)
                + "').write_text('{\"tokens\":{\"access_token\":\"rotated\"}}')",
            ],
            check=True,
        )
        provider.resume.set()
        return await task

    try:
        response = asyncio.run(_rotate_during_call())
    finally:
        revoke_provider_request(capability)

    assert response.text == "first"
    assert all(not path.exists() for path in provider.snapshot_paths)

    stale_capability, stale_context = _fresh_served_request(
        universe_dir,
        serving,
        request_id="after-raw-rotation",
    )
    try:
        with pytest.raises(ProviderAuthorityHeldError, match="Connect your provider"):
            asyncio.run(
                ProviderRouter({"codex": _SnapshotProvider(pause=False)}).call(
                    "writer",
                    "must revalidate",
                    "system",
                    operation="converse",
                    universe_context=stale_context,
                )
            )
    finally:
        revoke_provider_request(stale_capability)

    rebound = bind_serving_provider(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        agent_binding_id=serving["agent_binding_id"],
        expected_revision=serving["revision"],
        provider="codex",
    )
    rotated_assignment = load_provider_assignment(tmp_path, universe_id="u-owner")
    assert rotated_assignment.generation > original_assignment.generation
    assert (
        rotated_assignment.credential_reference_generation
        > original_assignment.credential_reference_generation
    )
    rotated_serving = set_serving(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="owner-1",
        universe_id="u-owner",
        agent_binding_id=serving["agent_binding_id"],
        expected_revision=rebound["agent_binding"]["revision"],
        enabled=True,
    )["agent_binding"]
    rotated_capability, rotated_context = _fresh_served_request(
        universe_dir,
        rotated_serving,
        request_id="after-rebind",
    )
    rotated_provider = _SnapshotProvider(pause=False)
    try:
        rotated_response = asyncio.run(
            ProviderRouter({"codex": rotated_provider}).call(
                "writer",
                "hello again",
                "system",
                operation="converse",
                universe_context=rotated_context,
            )
        )
    finally:
        revoke_provider_request(rotated_capability)
    assert rotated_response.text == "rotated"
    assert all(not path.exists() for path in rotated_provider.snapshot_paths)


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


def test_two_consecutive_founder_turns_share_one_binding_without_rebind(tmp_path):
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.providers.router import ProviderRouter

    universe_dir, serving, original_capability, _ = _served_context(tmp_path)
    revoke_provider_request(original_capability)
    provider = _RecordingProvider("codex")
    router = ProviderRouter({"codex": provider})

    for turn in range(2):
        capability, context = _fresh_served_request(
            universe_dir,
            serving,
            request_id=f"turn-{turn}",
        )
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
        finally:
            revoke_provider_request(capability)

    assert provider.calls == 4


def test_binding_generation_high_water_blocks_runaway_across_requests(
    tmp_path,
    monkeypatch,
):
    import tinyassets.provider_serving_binding as serving_binding
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.router import ProviderRouter

    monkeypatch.setattr(serving_binding, "_MAX_BINDING_INVOCATIONS", 4)
    universe_dir, serving, original_capability, _ = _served_context(tmp_path)
    revoke_provider_request(original_capability)
    provider = _RecordingProvider("codex")
    router = ProviderRouter({"codex": provider})

    for turn in range(2):
        capability, context = _fresh_served_request(
            universe_dir,
            serving,
            request_id=f"bounded-turn-{turn}",
        )
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
        finally:
            revoke_provider_request(capability)

    runaway_capability, runaway_context = _fresh_served_request(
        universe_dir,
        serving,
        request_id="runaway",
    )
    try:
        with pytest.raises(ProviderAuthorityHeldError, match="budget"):
            asyncio.run(
                router.call(
                    "writer",
                    "fifth launch",
                    "system",
                    operation="converse",
                    universe_context=runaway_context,
                )
            )
    finally:
        revoke_provider_request(runaway_capability)
    assert provider.calls == 4


def test_runaway_guard_ages_out_and_never_permanently_bricks(tmp_path, monkeypatch):
    """The runaway guard is a ROLLING WINDOW: it blocks a burst but ages out.

    The invocation ceiling counts only rows created within `_RUNAWAY_WINDOW_S`,
    so a burst is held while recent (runaway prevention) but once those
    invocations fall outside the window the binding serves again — it never
    permanently bricks a 24/7 binding (Codex reject #3). Contrast the old
    lifetime count, which stayed tripped forever.
    """
    import sqlite3

    import tinyassets.provider_serving_binding as serving_binding
    from tinyassets.auth.middleware import revoke_provider_request
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.providers.router import ProviderRouter
    from tinyassets.storage import db_path

    monkeypatch.setattr(serving_binding, "_MAX_BINDING_INVOCATIONS", 4)
    universe_dir, serving, original_capability, _ = _served_context(tmp_path)
    revoke_provider_request(original_capability)
    provider = _RecordingProvider("codex")
    router = ProviderRouter({"codex": provider})

    # Fill the window to the cap (2 turns x 2 calls = 4).
    for turn in range(2):
        capability, context = _fresh_served_request(
            universe_dir, serving, request_id=f"fill-{turn}"
        )
        try:
            for prompt in ("reply", "learning"):
                asyncio.run(
                    router.call(
                        "writer", prompt, "system",
                        operation="converse", universe_context=context,
                    )
                )
        finally:
            revoke_provider_request(capability)
    assert provider.calls == 4

    # 5th call is blocked while all 4 invocations are inside the window.
    cap5, ctx5 = _fresh_served_request(universe_dir, serving, request_id="blocked")
    try:
        with pytest.raises(ProviderAuthorityHeldError, match="budget"):
            asyncio.run(
                router.call(
                    "writer", "fifth", "system",
                    operation="converse", universe_context=ctx5,
                )
            )
    finally:
        revoke_provider_request(cap5)
    assert provider.calls == 4

    # Age the recorded invocations out of the rolling window.
    conn = sqlite3.connect(db_path(universe_dir.parent))
    try:
        conn.execute(
            "UPDATE served_provider_budget_reservations "
            "SET created_at = created_at - ?",
            (2 * 3600.0,),
        )
        conn.commit()
    finally:
        conn.close()

    # The binding serves again — the guard did not permanently brick it.
    cap6, ctx6 = _fresh_served_request(universe_dir, serving, request_id="recovered")
    try:
        asyncio.run(
            router.call(
                "writer", "sixth", "system",
                operation="converse", universe_context=ctx6,
            )
        )
    finally:
        revoke_provider_request(cap6)
    assert provider.calls == 5


def test_claude_serving_held_by_default_without_optin(tmp_path, monkeypatch):
    """claude-code serving stays HELD unless the host explicitly opts in.

    The OpenSpec design forbids silently bypassing the role-completeness hold
    merely because converse asks only for writer (Codex reject #2). The default
    (no flag) must therefore refuse claude-code serving.
    """
    from tinyassets.provider_serving_binding import bind_serving_provider

    monkeypatch.delenv("TINYASSETS_ALLOW_CLAUDE_SERVING", raising=False)
    with pytest.raises(PermissionError, match="held by default"):
        bind_serving_provider(
            base_path=str(tmp_path),
            universe_dir=str(tmp_path),
            owner_user_id="owner-1",
            universe_id="u-owner",
            agent_binding_id="binding-1",
            expected_revision=1,
            provider="claude-code",
        )


def test_claude_serving_optin_clears_the_hold(tmp_path, monkeypatch):
    """With the explicit opt-in AND writer-only serving scope, the hold clears.

    Proven by getting PAST the claude hold to the next validation (missing
    owner -> ValueError, NOT the PermissionError hold).
    """
    from tinyassets.provider_serving_binding import bind_serving_provider

    monkeypatch.setenv("TINYASSETS_ALLOW_CLAUDE_SERVING", "1")
    with pytest.raises(ValueError):
        bind_serving_provider(
            base_path=str(tmp_path),
            universe_dir=str(tmp_path),
            owner_user_id="",  # cleared the claude hold; fails later on owner
            universe_id="u-owner",
            agent_binding_id="binding-1",
            expected_revision=1,
            provider="claude-code",
        )


def _claude_authority(tmp_path):
    from tinyassets.provider_assignment import ServedProviderAuthority

    return ServedProviderAuthority(
        provider="claude-code",
        max_invocations=10,
        request_max_invocations=2,
        max_tokens=1000,
        max_cost_microunits=100_000,
        owner_user_id="o",
        universe_id="u",
        agent_binding_id="b",
        binding_revision=1,
        binding_id="bid",
        binding_generation=1,
        binding_digest="d",
        credential_reference_id="c",
        credential_reference_generation=1,
        credential_reference_digest="cd",
        credential_service="claude-code",
        credential_snapshot_dir=tmp_path,
        request_capability=object(),
    )


def test_reserve_holds_claude_serving_authority_without_optin(tmp_path, monkeypatch):
    """Serve-time re-check: a persisted claude-code serving authority is HELD on
    every served call unless the host opts in — closing the grandfathered-binding
    gap where a binding created while the flag was on keeps serving after it is
    cleared (Codex re-review #1). The check returns before any DB access.
    """
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.provider_assignment import reserve_served_provider_budget

    monkeypatch.delenv("TINYASSETS_ALLOW_CLAUDE_SERVING", raising=False)
    with pytest.raises(ProviderAuthorityHeldError, match="claude-code serving is held"):
        reserve_served_provider_budget(
            str(tmp_path),
            universe_dir=str(tmp_path),
            authority=_claude_authority(tmp_path),
            requested_output_tokens=10,
            estimated_input_tokens=10,
        )


def test_reserve_passes_claude_hold_with_optin(tmp_path, monkeypatch):
    """With the opt-in the serve-time claude hold clears; the call proceeds past
    it and fails on the (absent) binding/custody, NOT on the claude hold."""
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.provider_assignment import reserve_served_provider_budget

    monkeypatch.setenv("TINYASSETS_ALLOW_CLAUDE_SERVING", "1")
    with pytest.raises(ProviderAuthorityHeldError) as exc:
        reserve_served_provider_budget(
            str(tmp_path),
            universe_dir=str(tmp_path),
            authority=_claude_authority(tmp_path),
            requested_output_tokens=10,
            estimated_input_tokens=10,
        )
    assert "claude-code serving is held" not in str(exc.value)


def test_finalize_tolerates_row_already_reconciled(tmp_path):
    """A call that outran its lease is settled by the reconciler; its late
    finalize must return gracefully, NOT raise an accounting error (Codex
    re-review #4). A genuinely MISSING row still raises.
    """
    import sqlite3

    from tinyassets import provider_assignment as pa
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.provider_assignment import (
        ServedProviderBudgetReservation,
        finalize_served_provider_budget,
    )
    from tinyassets.storage import db_path

    authority = _claude_authority(tmp_path)  # provider irrelevant to finalize
    reservation = ServedProviderBudgetReservation(
        reservation_id="r-reconciled",
        binding_id=authority.binding_id,
        binding_generation=authority.binding_generation,
        output_tokens=50,
        reserved_total_tokens=100,
        reserved_cost_microunits=10_000,
    )
    conn = sqlite3.connect(db_path(tmp_path))
    try:
        pa._ensure_served_budget_schema(conn)
        # The reconciler already settled this row as succeeded.
        conn.execute(
            "INSERT INTO served_provider_budget_reservations "
            "(reservation_id, binding_id, binding_generation, state, "
            "reserved_total_tokens, reserved_cost_microunits, "
            "actual_total_tokens, actual_cost_microunits, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("r-reconciled", authority.binding_id, authority.binding_generation,
             "succeeded", 100, 10_000, 100, 10_000, 1.0),
        )
        conn.commit()
    finally:
        conn.close()

    # Already-reconciled: returns without raising.
    finalize_served_provider_budget(
        str(tmp_path),
        authority=authority,
        reservation=reservation,
        input_tokens=10,
        output_tokens=40,
        cost_microunits=5_000,
    )

    # A truly missing reservation is still an accounting anomaly.
    missing = ServedProviderBudgetReservation(
        reservation_id="r-missing",
        binding_id=authority.binding_id,
        binding_generation=authority.binding_generation,
        output_tokens=50,
        reserved_total_tokens=100,
        reserved_cost_microunits=10_000,
    )
    with pytest.raises(ProviderAuthorityHeldError, match="accounting failed"):
        finalize_served_provider_budget(
            str(tmp_path),
            authority=authority,
            reservation=missing,
            input_tokens=10,
            output_tokens=40,
            cost_microunits=5_000,
        )
