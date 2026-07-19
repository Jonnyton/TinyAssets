"""Regression guards for the production control-plane compute invariant."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.config import write_universe_config_fields
from tinyassets.engine_binding import execution_blocked_reason
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import subprocess_env_for_provider
from tinyassets.providers.router import _enforce_writer_binding
from tinyassets.runs import RUN_STATUS_QUEUED, execute_branch

ROOT = Path(__file__).resolve().parent.parent

COMPUTE_OWNERSHIP_INVARIANT = """### Compute ownership invariant

TinyAssets production services are control-plane only. Every executable
job lease is fulfilled by either an owner-authorized BYO daemon or a
resource-market host selected through the same daemon claim, lease,
heartbeat, and fenced-result protocol.

TinyAssets and its founder own no shared coding-worker fleet and provide
no platform-capacity fallback. The founder is an ordinary user under the
same identity, capability, daemon-registration, claim, and review rules.

When no eligible BYO or market daemon is online, jobs remain pending.
“Zero hosts online” uptime applies to authoring, browsing, collaboration,
routing, universe/job state, review, and market state; it does not imply
that executable jobs progress without external compute.

B2 and B3 are dependency-ordered validation slices of this one end-state
architecture: B2 proves the protocol with an owner daemon; B3 places
market matching in front of the unchanged protocol.
"""


def test_autouse_fixture_pins_each_test_to_a_throwaway_data_root(tmp_path) -> None:
    data_root = Path(os.environ["TINYASSETS_DATA_DIR"]).resolve()

    assert data_root.exists()
    assert data_root != tmp_path.resolve()
    assert not data_root.is_relative_to(tmp_path.resolve())
    assert data_root.parent == tmp_path.resolve().parent
    assert data_root.name.startswith("tinyassets-data")
    if os.name == "nt":
        live_root = Path.home() / "AppData" / "Roaming" / "TinyAssets"
        assert not data_root.is_relative_to(live_root.resolve())


def test_plan_contains_compute_ownership_invariant_verbatim() -> None:
    plan = (ROOT / "PLAN.md").read_text(encoding="utf-8")
    assert COMPUTE_OWNERSHIP_INVARIANT in plan


def test_compose_contains_only_control_plane_services() -> None:
    compose_path = ROOT / "deploy" / "compose.yml"
    compose_text = compose_path.read_text(encoding="utf-8")
    compose = yaml.safe_load(compose_text)

    assert set(compose["services"]) == {"daemon", "cloudflared", "logs"}
    assert "tinyassets.cloud_worker" not in compose_text
    assert "node-executor" not in compose_text

    for service_name, service in compose["services"].items():
        command = " ".join(str(part) for part in service.get("command", []))
        environment = service.get("environment") or {}
        volumes = " ".join(str(volume) for volume in service.get("volumes", []))
        assert "cloud_worker" not in command, service_name
        assert " codex" not in f" {command}", service_name
        assert " claude" not in f" {command}", service_name
        assert "CODEX_HOME" not in environment, service_name
        assert "CLAUDE_CONFIG_DIR" not in environment, service_name
        assert "TINYASSETS_ALLOW_API_KEY_PROVIDERS" not in environment, service_name
        assert "TINYASSETS_CLOUD_DAEMON_SUBSCRIPTION_ONLY" not in environment, service_name
        assert "/.codex" not in volumes, service_name
        assert "/.claude" not in volumes, service_name

    assert "seccomp=unconfined" not in compose_text
    assert "apparmor=unconfined" not in compose_text
    assert compose["services"]["daemon"]["environment"][
        "TINYASSETS_CONTROL_PLANE"
    ] == "1"


def _provider_branch() -> BranchDefinition:
    return BranchDefinition(
        branch_def_id="control-plane-provider-guard",
        name="Control-plane provider guard",
        entry_point="provider",
        node_defs=[
            NodeDefinition(
                node_id="provider",
                display_name="Provider",
                prompt_template="say hi",
                output_keys=["result"],
            )
        ],
        graph_nodes=[GraphNodeRef(id="provider", node_def_id="provider")],
        edges=[EdgeDefinition(from_node="provider", to_node="END")],
    )


@pytest.mark.parametrize(
    "engine_source", ("host_daemon", "market_rented", "self_hosted_endpoint")
)
def test_unresolved_external_engine_stays_queued_before_provider_dispatch(
    tmp_path, monkeypatch, engine_source
) -> None:
    universe = tmp_path / f"u-{engine_source}"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source=engine_source)
    calls = {"count": 0}

    def provider_call(*_args, **_kwargs):
        calls["count"] += 1
        return "ambient execution must be unreachable"

    reason = execution_blocked_reason(universe)
    outcome = execute_branch(
        tmp_path,
        branch=_provider_branch(),
        inputs={},
        provider_call=provider_call,
        _enqueue_universe_id=universe.name,
    )

    assert reason is not None
    assert "no_eligible_external_daemon" in reason
    assert outcome.status == RUN_STATUS_QUEUED
    assert "no_eligible_external_daemon" in outcome.error
    assert calls["count"] == 0


@pytest.mark.parametrize(
    "engine_source", ("host_daemon", "market_rented", "self_hosted_endpoint")
)
def test_unresolved_external_engine_quarantines_env_and_writer_route(
    tmp_path, monkeypatch, engine_source
) -> None:
    universe = tmp_path / f"u-{engine_source}"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source=engine_source)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ambient-platform-token")

    with pytest.raises(ProviderUnavailableError, match="external daemon") as exc:
        subprocess_env_for_provider("claude-code", universe_dir=universe)
    assert "ambient-platform-token" not in str(exc.value)

    with pytest.raises(AllProvidersExhaustedError, match="external daemon"):
        _enforce_writer_binding(
            ["claude-code"],
            role="writer",
            is_pinned_writer=False,
            pin_writer="",
            universe_dir=universe,
        )


def test_control_plane_provider_spawn_refuses_even_without_credentials(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("TINYASSETS_CONTROL_PLANE", "1")

    with pytest.raises(ProviderUnavailableError, match="control-plane"):
        subprocess_env_for_provider("claude-code", universe_dir=tmp_path)


def test_platform_worker_modules_are_retired_without_a_shim() -> None:
    assert not (ROOT / "tinyassets" / "cloud_worker.py").exists()
    assert not (ROOT / "tinyassets" / "cloud_worker_healthcheck.py").exists()
    plugin_runtime = (
        ROOT
        / "packaging"
        / "claude-plugin"
        / "plugins"
        / "tinyassets-universe-server"
        / "runtime"
        / "tinyassets"
    )
    assert not (plugin_runtime / "cloud_worker.py").exists()
    assert not (plugin_runtime / "cloud_worker_healthcheck.py").exists()


def test_production_entrypoints_do_not_start_workers_or_manage_provider_auth() -> None:
    entrypoint = (ROOT / "deploy" / "docker-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    deploy_workflow = (
        ROOT / ".github" / "workflows" / "deploy-prod.yml"
    ).read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    for text in (entrypoint, deploy_workflow, dockerfile):
        assert "tinyassets.cloud_worker" not in text

    for token in (
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "TINYASSETS_CODEX_AUTH_JSON_B64",
        "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        assert token in entrypoint
        assert f"set {token}" not in deploy_workflow
        assert token in deploy_workflow  # stale host env is deleted on deploy
    assert '_provider_auth_env=(' in entrypoint
    assert 'unset "${_name}"' in entrypoint

    assert "Verify cloud worker is running" not in deploy_workflow
    assert "Prepare codex auth persistent volume" not in deploy_workflow
    assert "Verify subscription LLM binding" not in deploy_workflow
    assert not (ROOT / ".github" / "workflows" / "codex-auth-keepalive.yml").exists()
    assert not (ROOT / ".github" / "workflows" / "claude-auth-keepalive.yml").exists()
    assert not (ROOT / ".github" / "workflows" / "llm-binding-canary.yml").exists()


def test_systemd_retires_removed_compose_services_as_orphans() -> None:
    unit = (ROOT / "deploy" / "tinyassets-daemon.service").read_text(
        encoding="utf-8"
    )
    start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    stop = next(line for line in unit.splitlines() if line.startswith("ExecStop="))
    assert "--remove-orphans" in start
    assert "--remove-orphans" in stop


def test_platform_secret_inventory_has_no_model_provider_credentials() -> None:
    expiry = (
        ROOT / ".github" / "workflows" / "secrets-expiry-check.yml"
    ).read_text(encoding="utf-8")
    env_template = (ROOT / "deploy" / "tinyassets-env.template").read_text(
        encoding="utf-8"
    )
    for token in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "TINYASSETS_CODEX_AUTH_JSON_B64",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        assert token not in expiry
        assert token not in env_template
