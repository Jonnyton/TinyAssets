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
from unittest.mock import AsyncMock, patch

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
from tinyassets.providers.claude_provider import ClaudeProvider
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


def test_plain_node_is_text_only_no_coding_capability():
    # INSEPARABILITY (latest-model FINDING 1): a non-coding node is NOT
    # os_sandbox_required, but it must NOT reach coding capability either — its
    # config DENIES Bash/Write/… so `claude -p`'s default tools cannot grant repo
    # write to a plain node. Coding tools flow ONLY from the coding classifier.
    node = NodeDefinition(
        node_id="summarize",
        display_name="Summarize",
        prompt_template="summarize it",
        output_keys=["summarize_out"],
    )
    cfg = _run_node_capturing_config(node)

    assert cfg is not None
    assert cfg.os_sandbox_required is False  # nothing to confine
    assert "Bash" in (cfg.disallowed_tools or ())  # coding capability denied
    assert "Write" in (cfg.disallowed_tools or ())
    assert "Bash" not in (cfg.allowed_tools or ())  # never granted


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
    n.node_kind = ""
    assert node_requires_sandbox(n) is False

    n.requires_sandbox = True
    assert node_requires_sandbox(n) is True

    d = N()
    d.requires_sandbox = False
    d.node_id = "draft_patch"
    d.node_kind = ""
    assert node_requires_sandbox(d) is True  # node_id backstop for the reference design


def test_renamed_coding_node_cannot_escape_via_rename():
    # Codex S3 FINDING 3: classify by the STABLE node_kind capability, not the
    # editable node_id. A remix renames draft_patch -> its own id but keeps
    # node_kind="coding" — it must STILL be sandbox-required.
    class N:
        pass

    r = N()
    r.requires_sandbox = False
    r.node_id = "write_the_fix"  # renamed away from draft_patch
    r.node_kind = "coding"
    assert node_requires_sandbox(r) is True

    # ...and through the compiler it receives the hardened config.
    node = NodeDefinition(
        node_id="write_the_fix",
        display_name="Write the fix",
        prompt_template="implement the fix",
        output_keys=["write_the_fix_out"],
        node_kind="coding",
    )
    assert node.requires_sandbox is False  # flag not set
    assert node.node_id not in ("draft_patch",)  # not the backstop id either
    cfg = _run_node_capturing_config(node)
    assert cfg is not None
    assert cfg.os_sandbox_required is True
    assert "mcp__*" in (cfg.disallowed_tools or ())
    assert "Bash" in (cfg.allowed_tools or ())


def test_node_requires_sandbox_accepts_raw_node_def_dicts():
    # build_branch / list_branches classify from persisted node_def DICTS (not
    # NodeDefinition objects), so the classifier must read either shape.
    assert node_requires_sandbox({"node_id": "x", "node_kind": "coding"}) is True
    assert node_requires_sandbox({"node_id": "x", "requires_sandbox": True}) is True
    assert node_requires_sandbox({"node_id": "draft_patch"}) is True  # backstop
    assert node_requires_sandbox({"node_id": "summarize", "node_kind": ""}) is False


def test_node_kind_round_trips_through_serialization():
    # node_kind must survive export/import so a remix carries its capability.
    node = NodeDefinition(
        node_id="draft_patch",
        display_name="Draft",
        prompt_template="do it",
        output_keys=["draft_patch_output"],
        node_kind="coding",
    )
    restored = NodeDefinition.from_dict(node.to_dict())
    assert restored.node_kind == "coding"


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


def test_enforce_os_sandbox_requires_whole_process_attestation(monkeypatch):
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    # Host-trusted config: no-op regardless of attestation.
    enforce_os_sandbox(ModelConfig())  # must not raise

    # Coding config with NO attestation: fail closed.
    with pytest.raises(SandboxUnavailableError):
        enforce_os_sandbox(coding_node_model_config(timeout=60))

    # Coding config WITH attestation: allowed.
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    enforce_os_sandbox(coding_node_model_config(timeout=60))  # must not raise


def test_launchable_bwrap_alone_does_not_satisfy_the_gate(monkeypatch):
    # Codex S3 CRITICAL: a launchable bwrap proves only that bwrap CAN start a
    # sandbox — NOT that the running claude -p subprocess is confined. With bwrap
    # "available" but NO whole-process attestation, a coding node MUST still fail
    # closed (a bare Linux host with working bwrap must NOT pass the gate).
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_ON))
    with pytest.raises(SandboxUnavailableError):
        enforce_os_sandbox(coding_node_model_config(timeout=60))


def test_claude_coding_node_fails_closed_without_attestation(monkeypatch):
    # FINDING 1 + FINDING 2: without the whole-process attestation, the claude
    # coding node is REFUSED before any `claude -p` spawn — EVEN when bwrap can
    # launch. This asserts the fail-closed refusal (not merely a probe value),
    # replacing the old cli-args `run_cwd is None` assertion that locked in the
    # unconfined behavior.
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_ON))
    spawned: list = []

    async def _fake_exec(*_a, **_k):
        spawned.append(1)
        raise AssertionError("claude must NOT spawn a coding node unconfined")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    with pytest.raises(SandboxUnavailableError):
        asyncio.run(
            ClaudeProvider().complete("prompt", "", coding_node_model_config(timeout=60))
        )
    assert not spawned


def test_claude_coding_node_spawns_hardened_argv_under_attestation(monkeypatch, tmp_path):
    # Under the whole-process attestation the coding node DOES run — and the
    # ACTUAL spawned argv carries the hardened policy: ambient config stripped
    # (--setting-sources project), STRICT empty MCP config (FINDING 6), host
    # connectors denied (--disallowedTools mcp__*), coding tools pre-approved.
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    _mock_vault(monkeypatch, oauth="VAULT-oauth")  # per-universe vault auth
    captured: list = []
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"done", b""))
    mock_proc.returncode = 0
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()

    async def _fake_exec(*args, **_kwargs):
        captured.extend(args)
        return mock_proc

    with (
        patch(
            "tinyassets.providers.claude_provider._resolve_claude_cmd",
            return_value=(["claude"], False),
        ),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        asyncio.run(
            ClaudeProvider().complete(
                "prompt", "", coding_node_model_config(timeout=60),
                universe_dir=tmp_path,
            )
        )

    assert "--setting-sources" in captured
    assert captured[captured.index("--setting-sources") + 1] == "project"
    # FINDING 6: strict empty MCP config so no user/project/managed MCP loads.
    assert "--strict-mcp-config" in captured
    assert "--mcp-config" in captured
    mcp_arg = captured[captured.index("--mcp-config") + 1]
    assert "mcpServers" in mcp_arg
    import json as _json
    assert _json.loads(mcp_arg) == {"mcpServers": {}}  # empty → nothing loads
    # belt-and-braces tool policy still present.
    assert "--disallowedTools" in captured and "mcp__*" in captured
    assert "--allowedTools" in captured and "Bash" in captured


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

    # No whole-process attestation (bwrap "available" is deliberately irrelevant).
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_ON))
    router = ProviderRouter(providers={"claude-code": FakeProvider()})
    cfg = coding_node_model_config(timeout=60)

    with pytest.raises(SandboxUnavailableError):
        asyncio.run(router.call("writer", "prompt", "", cfg))
    # The point: NO provider (not even a local fallback) ran the node — so a
    # coding node can never silently produce output on an unattested host.
    assert not dispatched


def test_router_preflight_allows_under_attestation(monkeypatch):
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

    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    provider = FakeProvider()
    provider.supports_coding_sandbox = True  # capable → not filtered (FINDING 4)
    router = ProviderRouter(providers={"claude-code": provider})
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


# --------------------------------------------------------------------------- #
# (5) sanitized env is VAULT-ONLY + per-job scratch cwd
#     (Codex round-3 FINDING 1 + latest-model FINDING 2)
# --------------------------------------------------------------------------- #

# Process-global platform secrets seeded as DECOYS — a hostile coding node must
# NEVER see any of these; the only auth it may see is the owner's own vault auth.
_DECOY_PLATFORM_ENV = {
    "CODEX_HOME": "/data/.codex",  # platform-global codex auth on the shared vol
    "CLAUDE_CODE_OAUTH_TOKEN": "PLATFORM-oauth",
    "CLAUDE_CONFIG_DIR": "/data/.claude",
    "ANTHROPIC_API_KEY": "sk-ant-platform",
    "OPENAI_API_KEY": "sk-openai-platform",
    "TINYASSETS_SECRET_X": "tenant-secret",
    "WORKOS_API_KEY": "workos-secret",
    "GITHUB_TOKEN": "gh-secret",
}


def _seed_decoy_platform_env(monkeypatch):
    for k, v in _DECOY_PLATFORM_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.delenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", raising=False)


def test_sanitized_env_never_carries_platform_global_auth(monkeypatch, tmp_path):
    # FINDING 2: the sanitized env must NOT contain ANY process-global platform
    # auth or secret — only the owner's per-universe vault auth. With NO vault
    # mocked, the env carries no provider auth at all (spawn refuses upstream).
    from tinyassets.providers.base import sanitized_subprocess_env

    _seed_decoy_platform_env(monkeypatch)
    _mock_vault(monkeypatch)  # vault returns nothing for subscription homes

    for provider in ("claude-code", "codex"):
        env = sanitized_subprocess_env(provider, universe_dir=tmp_path)
        assert "PATH" in env  # allowlist essential
        for leaked in _DECOY_PLATFORM_ENV:
            assert env.get(leaked) != _DECOY_PLATFORM_ENV[leaked], (
                f"{leaked} platform value leaked into {provider} coding env"
            )
        # And no cross-tenant secret at all.
        for secret in ("TINYASSETS_SECRET_X", "WORKOS_API_KEY", "GITHUB_TOKEN"):
            assert secret not in env


def test_sanitized_env_uses_vault_auth_not_platform(monkeypatch, tmp_path):
    # Vault provides the owner's own codex home — the env carries THAT, never the
    # platform /data/.codex decoy.
    from tinyassets.providers.base import sanitized_subprocess_env

    _seed_decoy_platform_env(monkeypatch)
    _mock_vault(monkeypatch, codex_home="/vault/owner/.codex", oauth="VAULT-oauth")

    xe = sanitized_subprocess_env("codex", universe_dir=tmp_path)
    assert xe.get("CODEX_HOME") == "/vault/owner/.codex"  # vault, not /data/.codex
    assert xe.get("CODEX_HOME") != "/data/.codex"

    ce = sanitized_subprocess_env("claude-code", universe_dir=tmp_path)
    assert ce.get("CLAUDE_CODE_OAUTH_TOKEN") == "VAULT-oauth"  # vault, not PLATFORM
    assert "CODEX_HOME" not in ce  # never the other provider's auth


def _mk_proc():
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"done", b""))
    mock_proc.returncode = 0
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


def test_coding_spawn_refused_without_vault_auth(monkeypatch, tmp_path):
    # FINDING 2 fail-closed: no per-universe vault auth ⇒ refuse (even attested,
    # even with platform auth in the process env).
    from tinyassets.providers.base import sandbox_spawn_env_and_dir

    _seed_decoy_platform_env(monkeypatch)
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    _mock_vault(monkeypatch)  # vault provides nothing

    for provider in ("claude-code", "codex"):
        with pytest.raises(SandboxUnavailableError):
            sandbox_spawn_env_and_dir(
                provider, coding_node_model_config(timeout=60),
                universe_dir=tmp_path,
            )


def test_claude_coding_node_spawns_with_vault_env_and_scratch_cwd(monkeypatch, tmp_path):
    _seed_decoy_platform_env(monkeypatch)
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    _mock_vault(monkeypatch, oauth="VAULT-oauth")
    captured: dict = {}

    async def _fake_exec(*_args, **kwargs):
        captured["env"] = kwargs.get("env")
        captured["cwd"] = kwargs.get("cwd")
        return _mk_proc()

    with (
        patch(
            "tinyassets.providers.claude_provider._resolve_claude_cmd",
            return_value=(["claude"], False),
        ),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        asyncio.run(
            ClaudeProvider().complete(
                "p", "", coding_node_model_config(timeout=60), universe_dir=tmp_path,
            )
        )

    env = captured["env"]
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "VAULT-oauth"  # vault, not platform
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") != "PLATFORM-oauth"
    assert "CODEX_HOME" not in env  # other provider stripped
    assert "TINYASSETS_SECRET_X" not in env  # tenant secret stripped
    assert "WORKOS_API_KEY" not in env
    cwd = captured["cwd"]
    assert cwd and "tinyassets-sandbox-job-" in cwd  # per-job scratch dir
    assert "/data" not in cwd  # not /data, not the repo checkout


def test_codex_coding_node_spawns_with_vault_env_and_scratch_workdir(monkeypatch, tmp_path):
    _seed_decoy_platform_env(monkeypatch)
    _mock_vault(monkeypatch, codex_home="/vault/owner/.codex")
    captured: dict = {}

    async def _fake_exec(*args, **kwargs):
        captured["args"] = list(args)
        captured["env"] = kwargs.get("env")
        return _mk_proc()

    with (
        patch(
            "tinyassets.providers.codex_provider._resolve_codex_cmd",
            return_value=(["codex"], False),
        ),
        patch(
            "tinyassets.providers.codex_provider.get_sandbox_status",
            return_value=dict(_BWRAP_ON),
        ),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        asyncio.run(
            CodexProvider().complete(
                "p", "", coding_node_model_config(timeout=60), universe_dir=tmp_path,
            )
        )

    env = captured["env"]
    assert env.get("CODEX_HOME") == "/vault/owner/.codex"  # vault, not /data/.codex
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env  # other provider stripped
    assert "TINYASSETS_SECRET_X" not in env  # tenant secret stripped
    args = captured["args"]
    workdir = args[args.index("-C") + 1]  # codex pins cwd via -C
    assert "tinyassets-sandbox-job-" in workdir  # per-job scratch, not repo root


# --------------------------------------------------------------------------- #
# (6) Codex round-3 FINDING 3 — sandbox nodes refuse a config-less bridge
# --------------------------------------------------------------------------- #


def test_sandbox_node_refuses_a_config_less_bridge():
    # A legacy/tolerant bridge that cannot carry the hardened config would run the
    # coding node WITHOUT the sandbox tool/env policy — must fail closed.
    node = NodeDefinition(
        node_id="draft_patch",
        display_name="Draft",
        prompt_template="do it",
        output_keys=["draft_patch_output"],
    )

    def config_less(prompt, system, *, role="writer"):  # no `config` kwarg
        raise AssertionError("a config-less bridge must NOT run a coding node")

    fn = _build_prompt_template_node(node, provider_call=config_less, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_sandbox_node_runs_through_a_config_accepting_bridge():
    node = NodeDefinition(
        node_id="draft_patch",
        display_name="Draft",
        prompt_template="do it",
        output_keys=["draft_patch_output"],
    )
    seen: dict = {}

    def config_ok(prompt, system, *, role="writer", config=None):
        seen["config"] = config
        return "ok"

    fn = _build_prompt_template_node(node, provider_call=config_ok, event_sink=None)
    out = fn({})
    assert out["draft_patch_output"] == "ok"
    assert seen["config"] is not None and seen["config"].os_sandbox_required is True


def test_ordinary_node_still_runs_through_a_config_less_bridge():
    # Non-sandbox nodes keep the tolerant legacy behavior.
    node = NodeDefinition(
        node_id="summarize",
        display_name="Summarize",
        prompt_template="do it",
        output_keys=["summarize_out"],
    )

    def config_less(prompt, system, *, role="writer"):
        return "ok"

    fn = _build_prompt_template_node(node, provider_call=config_less, event_sink=None)
    out = fn({})
    assert out["summarize_out"] == "ok"


# --------------------------------------------------------------------------- #
# (7) Codex round-4 FINDING 1 — vault overlay honors provider-scope + opt-in
# --------------------------------------------------------------------------- #


def _mock_vault(monkeypatch, *, codex_home="", claude_dir="", oauth=""):
    import tinyassets.credential_vault as cv

    monkeypatch.setattr(cv, "ensure_codex_home_from_vault", lambda ud: codex_home)
    monkeypatch.setattr(cv, "ensure_claude_config_dir_from_vault", lambda ud: claude_dir)
    monkeypatch.setattr(cv, "resolve_claude_oauth_token", lambda ud: oauth)
    monkeypatch.setattr(cv, "resolve_llm_api_key", lambda ud, var: "VAULT-" + var)
    return cv


def test_vault_overlay_gates_api_keys_on_include_flag(monkeypatch):
    cv = _mock_vault(monkeypatch)

    # include_api_keys=False → subscription auth only, NO vault API key.
    assert "ANTHROPIC_API_KEY" not in cv.provider_auth_env_overrides(
        "/u", "claude-code", include_api_keys=False
    )
    assert "OPENAI_API_KEY" not in cv.provider_auth_env_overrides(
        "/u", "codex", include_api_keys=False
    )

    # include_api_keys=True → ONLY the provider's OWN key, never the other's.
    c = cv.provider_auth_env_overrides("/u", "claude-code", include_api_keys=True)
    assert c.get("ANTHROPIC_API_KEY") == "VAULT-ANTHROPIC_API_KEY"
    assert "OPENAI_API_KEY" not in c
    x = cv.provider_auth_env_overrides("/u", "codex", include_api_keys=True)
    assert x.get("OPENAI_API_KEY") == "VAULT-OPENAI_API_KEY"
    assert "ANTHROPIC_API_KEY" not in x


def test_sandbox_env_drops_vault_api_key_without_opt_in(monkeypatch, tmp_path):
    from tinyassets.providers.base import sanitized_subprocess_env

    monkeypatch.delenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", raising=False)
    _mock_vault(monkeypatch, oauth="oauth-tok")

    env = sanitized_subprocess_env("claude-code", universe_dir=tmp_path)
    # Opt-in unset ⇒ the vault OPENAI/ANTHROPIC keys are NOT re-added...
    assert "ANTHROPIC_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    # ...but the job's own subscription auth still overlays.
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "oauth-tok"


def test_sandbox_env_includes_only_own_vault_api_key_with_opt_in(monkeypatch, tmp_path):
    from tinyassets.providers.base import sanitized_subprocess_env

    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    _mock_vault(monkeypatch)

    ce = sanitized_subprocess_env("claude-code", universe_dir=tmp_path)
    assert ce.get("ANTHROPIC_API_KEY") == "VAULT-ANTHROPIC_API_KEY"  # own key
    assert "OPENAI_API_KEY" not in ce  # never the OTHER provider's key

    xe = sanitized_subprocess_env("codex", universe_dir=tmp_path)
    assert xe.get("OPENAI_API_KEY") == "VAULT-OPENAI_API_KEY"  # own key
    assert "ANTHROPIC_API_KEY" not in xe  # never the OTHER provider's key


# --------------------------------------------------------------------------- #
# (8) Codex round-4 FINDING 2 — policy router cannot run a sandbox node un-hardened
# --------------------------------------------------------------------------- #


class _ConfigLessRouter:
    def call_with_policy_sync(self, role, prompt, system, policy):  # no `config`
        return ("policy-ran", "codex", {})


class _ConfigRouter:
    def __init__(self):
        self.seen_config = "unset"

    def call_with_policy_sync(self, role, prompt, system, policy, config=None):
        self.seen_config = config
        return ("policy-ran", "codex", {})


def test_policy_router_refuses_config_less_for_sandbox_node():
    from tinyassets.graph_compiler import _call_policy_router_with_retry

    with pytest.raises(SandboxUnavailableError):
        _call_policy_router_with_retry(
            _ConfigLessRouter(),
            role="writer", prompt="p", system="", policy={},
            config=coding_node_model_config(timeout=60),
            needs_sandbox=True,
        )


def test_policy_router_runs_hardened_config_accepting_for_sandbox_node():
    from tinyassets.graph_compiler import _call_policy_router_with_retry

    router = _ConfigRouter()
    text, provider, _meta = _call_policy_router_with_retry(
        router,
        role="writer", prompt="p", system="", policy={},
        config=coding_node_model_config(timeout=60),
        needs_sandbox=True,
    )
    assert text == "policy-ran"
    assert router.seen_config is not None
    assert router.seen_config.os_sandbox_required is True


def test_policy_router_config_less_ok_for_ordinary_node():
    from tinyassets.graph_compiler import _call_policy_router_with_retry

    text, _provider, _meta = _call_policy_router_with_retry(
        _ConfigLessRouter(),
        role="writer", prompt="p", system="", policy={},
        config=None,
        needs_sandbox=False,
    )
    assert text == "policy-ran"


# --------------------------------------------------------------------------- #
# (9) latest-model FINDING 1 — coding capability is INSEPARABLE from the sandbox
# --------------------------------------------------------------------------- #


def test_renamed_and_cleared_node_gets_no_coding_capability():
    # A remixer renames the node AND clears node_kind + requires_sandbox to flip
    # the classifier True→False. The escape must grant NOTHING: the node is a
    # plain TEXT node (Bash/Write DENIED, no os_sandbox), and it never reaches the
    # coding config or the coding spawn path.
    from tinyassets.sandbox_policy import node_coding_capability

    node = NodeDefinition(
        node_id="totally_innocent_text_node",  # renamed away from draft_patch
        display_name="Innocent",
        prompt_template="do it",
        output_keys=["totally_innocent_text_node_out"],
        requires_sandbox=False,  # cleared
        node_kind="",            # cleared
    )
    assert node_coding_capability(node) is False

    cfg = _run_node_capturing_config(node)
    assert cfg is not None
    # No coding config: not sandbox-required, Bash NOT granted, Bash DENIED.
    assert cfg.os_sandbox_required is False
    assert "Bash" not in (cfg.allowed_tools or ())
    assert "Write" not in (cfg.allowed_tools or ())
    assert "Bash" in (cfg.disallowed_tools or ())
    assert "Write" in (cfg.disallowed_tools or ())


# --------------------------------------------------------------------------- #
# (10) latest-model FINDING 4 — fallback chain admits ONLY coding-capable providers
# --------------------------------------------------------------------------- #


def _router_with(providers: dict):
    from tinyassets.providers.router import ProviderRouter

    return ProviderRouter(providers=providers)


class _CapableProvider:  # declares + enforces the coding-sandbox contract
    name = "claude-code"
    family = "anthropic"
    supports_coding_sandbox = True

    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, system, config, *, universe_dir=None):
        from tinyassets.providers.base import ProviderResponse

        self.calls += 1
        return ProviderResponse(
            text="real-work", provider=self.name, model="m",
            family=self.family, latency_ms=1.0,
        )


class _TextProvider:  # ignores the hardened config, would fake a 'patched'
    name = "ollama-local"
    family = "local"
    supports_coding_sandbox = False

    def __init__(self):
        self.calls = 0

    async def complete(self, prompt, system, config, *, universe_dir=None):
        from tinyassets.providers.base import ProviderResponse

        self.calls += 1
        return ProviderResponse(
            text="patched", provider=self.name, model="m",
            family=self.family, latency_ms=1.0,
        )


def test_sandbox_call_never_dispatches_to_a_text_provider(monkeypatch):
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    capable = _CapableProvider()
    text = _TextProvider()
    router = _router_with({"claude-code": capable, "ollama-local": text})

    resp = asyncio.run(
        router.call("writer", "p", "", coding_node_model_config(timeout=60))
    )
    assert resp.text == "real-work"  # served by the capable provider
    assert text.calls == 0  # ollama NEVER invoked for a coding node


def test_sandbox_call_with_only_text_providers_fails_loud(monkeypatch):
    from tinyassets.exceptions import AllProvidersExhaustedError

    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    text = _TextProvider()
    router = _router_with({"ollama-local": text})

    with pytest.raises(AllProvidersExhaustedError):
        asyncio.run(
            router.call("writer", "p", "", coding_node_model_config(timeout=60))
        )
    assert text.calls == 0  # never a fake 'patched'
