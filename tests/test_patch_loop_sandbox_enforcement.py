"""Patch-loop S3 — coding-node sandbox enforcement (the build-blocking gate).

The patch loop is a *user branch*: an arbitrary user remixes it, binds their own
repo, and runs it in OUR cloud. Its ``draft_patch`` node drives a coding agent
(``claude -p`` / ``codex exec``) that writes a patch against that repo — a code
execution surface a malicious remix could abuse. These tests prove:

  (1) a ``requires_sandbox`` node's coding-agent call runs with the hardened,
      OS-sandboxed posture (repo-confined tool policy: host connectors + mcp__*
      + Monitor denied, coding tools kept, os_sandbox_required set);
  (2) the ``draft_patch`` node class requires the sandbox BY DEFAULT — a remix
      cannot drop the flag to escape confinement;
  (3) a required-but-unavailable sandbox FAILS CLOSED at every layer (node
      runtime, both subprocess providers, and the router) — codex NEVER uses
      ``--dangerously-bypass-approvals-and-sandbox`` for such a node; and
  (4) the existing universe-intelligence isolation is UNCHANGED (not weakened,
      and it must NOT become os_sandbox_required — WebFetch-only is safe
      unsandboxed, so it must keep running on bwrap-less hosts).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tinyassets.branches import NodeDefinition
from tinyassets.graph_compiler import _build_prompt_template_node
from tinyassets.providers import base as base_mod
from tinyassets.providers.base import (
    ModelConfig,
    SandboxUnavailableError,
    UniverseContext,
    enforce_os_sandbox,
)
from tinyassets.providers.claude_provider import ClaudeProvider, _sandbox_cli_args
from tinyassets.providers.codex_provider import CodexProvider, _codex_sandbox_args
from tinyassets.sandbox_policy import (
    CODING_NODE_ALLOWED_TOOLS,
    CODING_NODE_DISALLOWED_TOOLS,
    coding_node_model_config,
    node_requires_sandbox,
)

_BWRAP_OFF = {"bwrap_available": False, "reason": "test: no bwrap"}
_BWRAP_ON = {"bwrap_available": True, "reason": None}


# --------------------------------------------------------------------------- #
# (1) Node runtime builds the hardened config for a requires_sandbox node
# --------------------------------------------------------------------------- #


def _run_node_capturing_config(node: NodeDefinition) -> ModelConfig | None:
    """Compile *node* and run it with a config-capturing provider stub.

    The stub declares a ``config`` param so the compiler threads the built
    ModelConfig to it — the exact object the real provider would receive.
    """
    captured: list = []

    def stub(prompt: str, system: str, *, role: str = "writer", config=None) -> str:
        captured.append(config)
        return "ok"

    fn = _build_prompt_template_node(node, provider_call=stub, event_sink=None)
    fn({})
    assert captured, "provider stub was never called"
    return captured[-1]


def test_requires_sandbox_node_runs_with_hardened_config():
    node = NodeDefinition(
        node_id="dev",
        display_name="Dev (coding)",
        prompt_template="implement the fix",
        output_keys=["dev_out"],
        requires_sandbox=True,
    )
    cfg = _run_node_capturing_config(node)

    assert cfg is not None
    # OS-sandbox required => provider fails closed + never bypasses.
    assert cfg.os_sandbox_required is True
    # host connectors / side-effect tools denied (the exfil surface)
    assert "mcp__*" in (cfg.disallowed_tools or ())
    assert "Monitor" in (cfg.disallowed_tools or ())
    assert "WebFetch" in (cfg.disallowed_tools or ())
    assert "SendMessage" in (cfg.disallowed_tools or ())
    # coding tools KEPT so the agent can actually write the patch...
    assert "Bash" in (cfg.allowed_tools or ())
    assert "Write" in (cfg.allowed_tools or ())
    # ...and NOT accidentally denied (posture not self-contradicting)
    assert "Bash" not in (cfg.disallowed_tools or ())
    assert "Write" not in (cfg.disallowed_tools or ())


def test_plain_node_is_not_sandboxed_backward_compat():
    node = NodeDefinition(
        node_id="summarize",
        display_name="Summarize",
        prompt_template="summarize it",
        output_keys=["summarize_out"],
    )
    cfg = _run_node_capturing_config(node)

    assert cfg is not None
    # A normal prompt node keeps today's behavior: no OS-sandbox requirement,
    # no coding denylist (else every branch node would fail closed off-Linux).
    assert cfg.os_sandbox_required is False
    assert not (cfg.disallowed_tools or ())
    assert not (cfg.allowed_tools or ())


# --------------------------------------------------------------------------- #
# (2) draft_patch node class is sandbox-required by DEFAULT (no flag needed)
# --------------------------------------------------------------------------- #


def test_draft_patch_defaults_to_sandbox_even_without_the_flag():
    # A remix that omits requires_sandbox on its draft_patch node must STILL run
    # confined — a user shouldn't have to opt in to safety.
    node = NodeDefinition(
        node_id="draft_patch",
        display_name="Draft the patch (coding agent)",
        prompt_template="implement the fix on a new branch",
        output_keys=["draft_patch_output"],
    )
    assert node.requires_sandbox is False  # author did NOT set it

    cfg = _run_node_capturing_config(node)
    assert cfg is not None
    assert cfg.os_sandbox_required is True
    assert "mcp__*" in (cfg.disallowed_tools or ())
    assert "Bash" in (cfg.allowed_tools or ())


def test_node_requires_sandbox_helper():
    class N:
        pass

    n = N()
    n.requires_sandbox = False
    n.node_id = "summarize"
    assert node_requires_sandbox(n) is False

    n.requires_sandbox = True
    assert node_requires_sandbox(n) is True

    d = N()
    d.requires_sandbox = False
    d.node_id = "draft_patch"
    assert node_requires_sandbox(d) is True  # sandbox-by-default kind


# --------------------------------------------------------------------------- #
# (3) fail-closed everywhere: codex never bypasses; claude/router refuse
# --------------------------------------------------------------------------- #


def test_codex_coding_node_fails_closed_and_never_bypasses():
    cfg = coding_node_model_config(timeout=60)

    # No OS sandbox -> refuse, and NEVER emit the dangerous bypass flag.
    with pytest.raises(SandboxUnavailableError):
        _codex_sandbox_args(cfg, _BWRAP_OFF)

    # OS sandbox present -> sandboxed auto mode only, still no bypass.
    args = _codex_sandbox_args(cfg, _BWRAP_ON)
    assert args == ["--full-auto"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in args


def test_codex_host_trusted_call_keeps_legacy_behavior():
    # A non-coding (host-trusted) call is unchanged: hosted bypass mode when
    # bwrap is absent, sandboxed auto mode when present.
    host = ModelConfig()
    assert _codex_sandbox_args(host, _BWRAP_OFF) == [
        "--dangerously-bypass-approvals-and-sandbox"
    ]
    assert _codex_sandbox_args(host, _BWRAP_ON) == ["--full-auto"]


def test_codex_provider_complete_fails_closed_before_spawning(monkeypatch):
    spawned: list = []

    async def _fake_exec(*_a, **_k):
        spawned.append(1)
        raise AssertionError("codex must NOT spawn a coding node unconfined")

    monkeypatch.setattr(
        "tinyassets.providers.codex_provider.get_sandbox_status",
        lambda: dict(_BWRAP_OFF),
    )
    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)

    with pytest.raises(SandboxUnavailableError):
        asyncio.run(
            CodexProvider().complete("prompt", "", coding_node_model_config(timeout=60))
        )
    assert not spawned


def test_enforce_os_sandbox_helper(monkeypatch):
    # Host-trusted config: no-op regardless of sandbox availability.
    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_OFF))
    enforce_os_sandbox(ModelConfig())  # must not raise

    # Coding config on a no-sandbox host: fail closed.
    with pytest.raises(SandboxUnavailableError):
        enforce_os_sandbox(coding_node_model_config(timeout=60))

    # Coding config WITH a sandbox: allowed.
    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_ON))
    enforce_os_sandbox(coding_node_model_config(timeout=60))  # must not raise


def test_claude_provider_complete_fails_closed_before_spawning(monkeypatch):
    spawned: list = []

    async def _fake_exec(*_a, **_k):
        spawned.append(1)
        raise AssertionError("claude must NOT spawn a coding node unconfined")

    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_OFF))
    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)

    with pytest.raises(SandboxUnavailableError):
        asyncio.run(
            ClaudeProvider().complete("prompt", "", coding_node_model_config(timeout=60))
        )
    assert not spawned


def test_claude_coding_node_cli_args_strip_config_and_deny_connectors():
    # A coding node applies --setting-sources project + the tool policy WITHOUT
    # requiring a universe_dir (it runs in the repo checkout, confined by the OS
    # sandbox), so _sandbox_cli_args must not fail-closed on a missing dir here.
    cfg = coding_node_model_config(timeout=60)
    flags, run_cwd = _sandbox_cli_args(cfg, None)

    assert "--setting-sources" in flags
    assert flags[flags.index("--setting-sources") + 1] == "project"
    assert "--allowedTools" in flags and "Bash" in flags
    assert "--disallowedTools" in flags
    assert "mcp__*" in flags and "Monitor" in flags
    assert run_cwd is None  # repo checkout, not a pinned universe dir


def test_router_preflight_fails_closed_and_never_dispatches(monkeypatch):
    from tinyassets.providers.base import BaseProvider, ProviderResponse
    from tinyassets.providers.router import ProviderRouter

    dispatched: list = []

    class FakeProvider(BaseProvider):
        name = "claude-code"
        family = "anthropic"

        async def complete(self, prompt, system, config, *, universe_dir=None):
            dispatched.append(1)
            return ProviderResponse(
                text="x", provider="claude-code", model="m",
                family="anthropic", latency_ms=1.0,
            )

    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_OFF))
    router = ProviderRouter(providers={"claude-code": FakeProvider()})
    cfg = coding_node_model_config(timeout=60)

    with pytest.raises(SandboxUnavailableError):
        asyncio.run(router.call("writer", "prompt", "", cfg))
    # The point: NO provider (not even a local fallback) ran the node — so a
    # coding node can never silently produce output on a no-sandbox host.
    assert not dispatched


def test_router_preflight_allows_when_sandbox_available(monkeypatch):
    from tinyassets.providers.base import BaseProvider, ProviderResponse
    from tinyassets.providers.router import ProviderRouter

    dispatched: list = []

    class FakeProvider(BaseProvider):
        name = "claude-code"
        family = "anthropic"

        async def complete(self, prompt, system, config, *, universe_dir=None):
            dispatched.append(config)
            return ProviderResponse(
                text="patched", provider="claude-code", model="m",
                family="anthropic", latency_ms=1.0,
            )

    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_ON))
    router = ProviderRouter(providers={"claude-code": FakeProvider()})
    cfg = coding_node_model_config(timeout=60)

    resp = asyncio.run(router.call("writer", "prompt", "", cfg))
    assert resp.text == "patched"
    assert dispatched and dispatched[0].os_sandbox_required is True


# --------------------------------------------------------------------------- #
# (4) universe-intelligence isolation is UNCHANGED and NOT weakened
# --------------------------------------------------------------------------- #


def test_universe_intelligence_denylist_still_denies_filesystem_and_shell():
    import tinyassets.universe_intelligence as ui

    assert ui._ENGINE_ALLOWED_TOOLS == ("WebFetch",)
    for denied in ("Bash", "Read", "Write", "Edit", "WebSearch", "Task", "mcp__*", "Monitor"):
        assert denied in ui._ENGINE_DISALLOWED_TOOLS


def test_universe_intelligence_config_is_conversation_not_os_sandbox():
    import tinyassets.universe_intelligence as ui

    cfg = ui._sandboxed_config(UniverseContext())
    # Conversation profile: cwd-pinned, WebFetch-only.
    assert cfg.sandbox_workspace is True
    assert cfg.allowed_tools == ("WebFetch",)
    # Must NOT become os_sandbox_required: it is safe unsandboxed (no filesystem
    # tools), so requiring bwrap would wrongly break the founder turn on
    # bwrap-less hosts.
    assert cfg.os_sandbox_required is False


def test_codex_still_refuses_the_universe_conversation_sandbox():
    from tinyassets.exceptions import ProviderError

    cfg = ModelConfig(sandbox_workspace=True)
    with pytest.raises(ProviderError):
        asyncio.run(CodexProvider().complete("hi", "", cfg, universe_dir=Path("/tmp/u")))


def test_coding_node_policy_does_not_overlap_allow_and_deny():
    # Sanity: a tool is never both pre-approved and denied.
    overlap = set(CODING_NODE_ALLOWED_TOOLS) & set(CODING_NODE_DISALLOWED_TOOLS)
    assert not overlap, f"tool listed as both allowed and denied: {overlap}"
