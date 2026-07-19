"""Regression guards for the production control-plane compute invariant."""

from __future__ import annotations

import ast
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import tinyassets.engine_binding as engine_binding
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.config import write_universe_config_fields
from tinyassets.credential_broker import deposit_engine_api_key
from tinyassets.engine_binding import (
    BYO_VAULT_ENCRYPTED_ENV,
    execution_blocked_reason,
    resolve_engine_binding,
)
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderUnavailableError,
)
from tinyassets.providers import base as provider_base
from tinyassets.providers.base import ModelConfig, subprocess_env_for_provider
from tinyassets.providers.claude_provider import ClaudeProvider
from tinyassets.providers.codex_provider import CodexProvider
from tinyassets.providers.router import ProviderRouter, _enforce_writer_binding
from tinyassets.runs import RUN_STATUS_QUEUED, execute_branch

ROOT = Path(__file__).resolve().parent.parent

PROVIDER_CREDENTIAL_ENV_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "XAI_API_KEY",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
    "TINYASSETS_CODEX_AUTH_JSON_B64",
    "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "TINYASSETS_ALLOW_API_KEY_PROVIDERS",
    "TINYASSETS_CLOUD_DAEMON_SUBSCRIPTION_ONLY",
)


class _RawProviderSpawnVisitor(ast.NodeVisitor):
    """Resolve common static aliases for dangerous process primitives.

    This is a best-effort source backstop, not the runtime security boundary.
    Dynamic import names, computed ``getattr`` strings, ``exec``/``eval``, and
    runtime monkeypatching remain outside static resolution; package-bootstrap
    environment scrubbing protects child processes even when syntax evades it.
    """

    _DANGEROUS_PRIMITIVES = frozenset(
        {
            ("subprocess", "run"),
            ("subprocess", "Popen"),
            ("subprocess", "call"),
            ("asyncio", "create_subprocess_exec"),
            ("asyncio", "create_subprocess_shell"),
            ("os", "system"),
        }
    )
    _MODULES = frozenset(module for module, _name in _DANGEROUS_PRIMITIVES)

    def __init__(self) -> None:
        self.function_stack: list[str] = []
        self.calls: list[tuple[str, int]] = []
        self.bindings: list[dict[str, tuple[str, str]]] = [{}]

    def _resolve(self, node: ast.expr) -> tuple[str, str] | None:
        if isinstance(node, ast.Name):
            return self.bindings[-1].get(node.id)
        if isinstance(node, ast.Attribute):
            owner = self._resolve(node.value)
            if owner and owner[0] == "module":
                primitive = (owner[1], node.attr)
                if primitive in self._DANGEROUS_PRIMITIVES:
                    return ("primitive", ".".join(primitive))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            owner = self._resolve(node.args[0])
            if owner and owner[0] == "module":
                primitive = (owner[1], node.args[1].value)
                if primitive in self._DANGEROUS_PRIMITIVES:
                    return ("primitive", ".".join(primitive))
        return None

    def _bind(self, target: ast.expr, value: tuple[str, str] | None) -> None:
        if not isinstance(target, ast.Name):
            return
        if value is None:
            self.bindings[-1].pop(target.id, None)
        else:
            self.bindings[-1][target.id] = value

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in self._MODULES:
                self.bindings[-1][alias.asname or alias.name] = (
                    "module",
                    alias.name,
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module not in self._MODULES:
            return
        for alias in node.names:
            primitive = (node.module, alias.name)
            if primitive in self._DANGEROUS_PRIMITIVES:
                self.bindings[-1][alias.asname or alias.name] = (
                    "primitive",
                    ".".join(primitive),
                )

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        value = self._resolve(node.value)
        for target in node.targets:
            self._bind(target, value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
            self._bind(node.target, self._resolve(node.value))
        else:
            self._bind(node.target, None)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.bindings.append(self.bindings[-1].copy())
        self.generic_visit(node)
        self.bindings.pop()
        self.function_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        resolved = self._resolve(node.func)
        if resolved and resolved[0] == "primitive":
            current = self.function_stack[-1] if self.function_stack else "<module>"
            self.calls.append((current, node.lineno))
        self.generic_visit(node)

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


def test_control_plane_bootstrap_scrubs_provider_credentials_from_process_and_raw_child(
    tmp_path,
) -> None:
    nested_code = (
        "import json, os; "
        f"print(json.dumps({{name: os.environ.get(name) for name in "
        f"{PROVIDER_CREDENTIAL_ENV_VARS!r}}}))"
    )
    bootstrap_code = f"""
import json
import os
import subprocess
import sys

import tinyassets.universe_server

names = {PROVIDER_CREDENTIAL_ENV_VARS!r}
child = subprocess.run(
    [sys.executable, "-c", {nested_code!r}],
    capture_output=True,
    check=True,
    text=True,
)
print(json.dumps({{
    "parent": {{name: os.environ.get(name) for name in names}},
    "child": json.loads(child.stdout),
    "preserved": {{
        "PATH": os.environ.get("PATH"),
        "TINYASSETS_DATA_DIR": os.environ.get("TINYASSETS_DATA_DIR"),
        "GIT_AUTHOR_NAME": os.environ.get("GIT_AUTHOR_NAME"),
    }},
}}))
"""
    env = os.environ.copy()
    env.update(
        {
            "TINYASSETS_CONTROL_PLANE": "1",
            "TINYASSETS_DATA_DIR": str(tmp_path / "control-plane-data"),
            "GIT_AUTHOR_NAME": "preserved-git-setting",
            **{name: f"ambient-{name.lower()}" for name in PROVIDER_CREDENTIAL_ENV_VARS},
        }
    )

    completed = subprocess.run(
        [sys.executable, "-c", bootstrap_code],
        capture_output=True,
        check=True,
        env=env,
        text=True,
    )
    result = json.loads(completed.stdout)

    assert result["parent"] == {
        name: None for name in PROVIDER_CREDENTIAL_ENV_VARS
    }
    assert result["child"] == {
        name: None for name in PROVIDER_CREDENTIAL_ENV_VARS
    }
    assert result["preserved"] == {
        "PATH": env["PATH"],
        "TINYASSETS_DATA_DIR": env["TINYASSETS_DATA_DIR"],
        "GIT_AUTHOR_NAME": "preserved-git-setting",
    }


def test_runtime_and_entrypoint_share_the_provider_credential_manifest() -> None:
    from tinyassets.control_plane import PROVIDER_CREDENTIAL_ENV_VARS as runtime_vars

    entrypoint = (ROOT / "deploy" / "docker-entrypoint.sh").read_text(
        encoding="utf-8"
    )

    assert runtime_vars == PROVIDER_CREDENTIAL_ENV_VARS
    assert "tinyassets/provider_credential_env_vars.txt" in entrypoint


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


def test_provider_modules_cannot_bypass_the_shared_spawn_gate() -> None:
    allowed_raw_calls = {
        ("base.py", "run_provider_subprocess"),
        ("base.py", "create_provider_subprocess_exec"),
        ("base.py", "create_provider_subprocess_shell"),
        # bwrap is a platform sandbox capability probe, not a provider/model child.
        ("base.py", "probe_sandbox_available"),
    }
    violations: list[str] = []
    for path in sorted((ROOT / "tinyassets" / "providers").glob("*.py")):
        visitor = _RawProviderSpawnVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        for function, lineno in visitor.calls:
            if (path.name, function) not in allowed_raw_calls:
                violations.append(f"{path.name}:{lineno} ({function})")

    assert violations == [], (
        "provider subprocess primitives must route through the shared gated "
        f"helpers in providers/base.py; raw calls: {violations}"
    )


@pytest.mark.parametrize(
    ("source", "lineno"),
    (
        ("import subprocess as sp\nsp.run(['true'])\n", 2),
        ("from subprocess import run\nrun(['true'])\n", 2),
        ("import subprocess\nlaunch = subprocess.run\nlaunch(['true'])\n", 3),
        ("import subprocess\ngetattr(subprocess, 'run')(['true'])\n", 2),
    ),
)
def test_raw_provider_spawn_visitor_resolves_static_aliases(source, lineno) -> None:
    visitor = _RawProviderSpawnVisitor()
    visitor.visit(ast.parse(source))

    assert visitor.calls == [("<module>", lineno)]


def test_control_plane_never_spawns_provider_processes_across_any_health_or_call_path(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def forbidden_sync(*_args, **_kwargs):
        calls.append("sync")
        raise AssertionError("control-plane provider subprocess must not spawn")

    async def forbidden_async(*_args, **_kwargs):
        calls.append("async")
        raise AssertionError("control-plane provider subprocess must not spawn")

    monkeypatch.setenv("TINYASSETS_CONTROL_PLANE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-openai-secret")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "ambient-claude-secret")
    monkeypatch.setattr(provider_base, "_sandbox_probe_cache", None)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/bwrap")
    monkeypatch.setattr(subprocess, "run", forbidden_sync)
    monkeypatch.setattr(subprocess, "Popen", forbidden_sync)
    monkeypatch.setattr(subprocess, "call", forbidden_sync)
    monkeypatch.setattr(os, "system", forbidden_sync)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_async)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", forbidden_async)

    sandbox_status = provider_base.get_sandbox_status()
    assert sandbox_status["bwrap_available"] is False
    assert "not applicable" in str(sandbox_status["reason"])

    probe = provider_base._codex_live_auth_probe(0.1)
    assert probe["status"] == "inconclusive"
    assert "control plane" in probe["detail"]

    for provider_name in ("codex", "claude-code"):
        health = provider_base.subscription_auth_health(provider_name)
        assert health["status"] == "not_applicable"
        assert "control plane" in health["detail"]

    router = ProviderRouter(auth_health=provider_base.subscription_auth_health)
    assert router._apply_auth_health_policy(["claude-code", "codex"]) == [
        "claude-code",
        "codex",
    ]

    for provider in (ClaudeProvider(), CodexProvider()):
        with pytest.raises(ProviderUnavailableError, match="control-plane"):
            asyncio.run(provider.complete("prompt", "", ModelConfig()))

    assert calls == []


def test_two_consecutive_bound_byo_claude_spawns_preserve_binding(
    platform_vault_env, monkeypatch
) -> None:
    import tinyassets.providers.claude_provider as claude_provider

    universe = platform_vault_env / "u-two-spawns"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service="anthropic",
        api_key="sk-ant-api03-two-spawn-regression",
    )
    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)
    monkeypatch.setattr(
        claude_provider, "_resolve_claude_cmd", lambda: (["claude"], False)
    )

    spawn_cwds: list[str] = []

    class SuccessfulProcess:
        returncode = 0

        async def communicate(self, *_args, **_kwargs):
            return b"ok", b""

        def kill(self) -> None:
            return None

        async def wait(self) -> int:
            return 0

    async def fake_exec(*_args, **kwargs):
        spawn_cwds.append(kwargs["cwd"])
        return SuccessfulProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    provider = ClaudeProvider()

    for _attempt in range(2):
        binding = resolve_engine_binding(universe)
        assert binding.bound is True
        assert execution_blocked_reason(universe) is None
        assert _enforce_writer_binding(
            ["claude-code"],
            role="writer",
            is_pinned_writer=False,
            pin_writer="",
            universe_dir=universe,
        ) == ["claude-code"]
        response = asyncio.run(
            provider.complete("prompt", "", ModelConfig(), universe_dir=universe)
        )
        assert response.text == "ok"

    expected_scratch = str(universe / ".engine-auth" / "claude-byo-scratch")
    assert spawn_cwds == [expected_scratch, expected_scratch]
    assert not (universe / ".credentials").exists()


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
    credential_manifest = (
        ROOT / "tinyassets" / "provider_credential_env_vars.txt"
    ).read_text(encoding="utf-8")

    for text in (entrypoint, deploy_workflow, dockerfile):
        assert "tinyassets.cloud_worker" not in text

    for token in (
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "TINYASSETS_CODEX_AUTH_JSON_B64",
        "TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64",
        "CLAUDE_CODE_OAUTH_TOKEN",
    ):
        assert token in credential_manifest
        assert f"set {token}" not in deploy_workflow
        assert token in deploy_workflow  # stale host env is deleted on deploy
    assert "provider_credential_env_vars.txt" in entrypoint
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
