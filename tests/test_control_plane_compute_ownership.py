"""Regression guards for the production control-plane compute invariant."""

from __future__ import annotations

from pathlib import Path

import yaml


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
