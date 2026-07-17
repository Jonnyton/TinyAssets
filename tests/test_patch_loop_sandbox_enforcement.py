"""Patch-loop S3a — coding-node sandbox ENFORCEMENT (fail-closed, Phase 1).

The patch loop is a *user branch*: an arbitrary user remixes it, binds their own
repo, and runs it in OUR cloud. Its ``draft_patch`` node drives a coding agent
(``claude -p`` / ``codex exec``) that would write a patch against that repo — a
code-execution surface a malicious remix could abuse.

S3a is ENFORCEMENT-ONLY. There is NO per-job sandbox runner subsystem in this
deployment (prepared per-job checkout + tenant isolation + scoped credentials +
egress/resource limits) — that runner is a host-approved *Phase-2* slice, NOT
built here (see
``docs/exec-plans/active/2026-07-16-patch-loop-phase2-sandbox-runner.md``). So
this slice does NOT run coding nodes under a hardened policy; it proves they
cannot run at all until the runner lands. These tests prove:

  (1) a repo-touching node (source_exec / coding / repo_exec / repo_read —
      classified by the ACTUAL executable nature for source_code, else the STABLE
      ``node_kind`` with node_id backstops) FAILS CLOSED deterministically at the
      graph choke point in ``_build_node``, before any ModelConfig / provider /
      scratch / env code runs; ``coding_nodes_runnable()`` is a hard-coded
      ``False`` that validate, get_status, the enqueue refusal, and the runtime
      all read, so readiness never drifts from runtime. A ``source_code`` node
      (in-process host code) is ALWAYS ``source_exec`` regardless of
      user-controlled ``node_kind`` / ``requires_sandbox`` — the Codex S3 r11
      metadata-downgrade escape (approve → reclassify ``text`` → skip the gate)
      cannot spoof it;
  (2) the ``draft_patch`` node class is repo-touching BY DEFAULT — a remix that
      renames the node still carries its ``node_kind`` and cannot escape the
      refusal;
  (3) the refusal holds at EVERY layer (node runtime, both subprocess providers,
      and the router) — codex NEVER uses
      ``--dangerously-bypass-approvals-and-sandbox`` and claude never runs with an
      open tool surface for such a node; the only node that RUNS is a plain TEXT
      node under a CLOSED tool surface (claude ``--tools ""``); and
  (4) the existing universe-intelligence isolation is UNCHANGED (not weakened,
      and it must NOT become os_sandbox_required — WebFetch-only + the closed tool
      surface keep it RUNNABLE on bwrap-less hosts as DEFENSE-IN-DEPTH; note the
      Codex S3 r15 #2 caveat that a tool-less claude -p is not a COMPLETE sandbox
      because managed-settings hooks load regardless of CLI flags — the complete
      boundary for untrusted execution is the Phase-2 OS-isolation worker).
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


def _run_node_expect_fail_closed(node: NodeDefinition):
    """Compile *node* and assert it FAILS CLOSED (raises SandboxUnavailableError)
    before any provider is ever called."""
    called: list = []

    def stub(prompt: str, system: str, *, role: str = "writer", config=None) -> str:
        called.append(1)
        return "SHOULD NOT RUN"

    fn = _build_prompt_template_node(node, provider_call=stub, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})
    assert not called, "a repo-touching node must NEVER reach the provider"


def test_repo_touching_node_fails_closed_no_runner():
    # REFRAME (Codex S3 REJECT): a coding/repo node has NO per-job sandbox runner
    # in this deploy, so it fails closed on EVERY provider, deterministically,
    # before any provider spawn — never runs against an empty workspace.
    for node in (
        NodeDefinition(node_id="dev", display_name="Dev", prompt_template="x",
                       output_keys=["dev_out"], requires_sandbox=True),
        NodeDefinition(node_id="verify", display_name="Verify",
                       prompt_template="run {verify_command}",
                       output_keys=["verify_out"]),  # repo_exec backstop
        NodeDefinition(node_id="investigate", display_name="Investigate",
                       prompt_template="inspect the repo",
                       output_keys=["investigate_out"]),  # repo_read backstop
    ):
        _run_node_expect_fail_closed(node)


def test_plain_node_is_text_only_closed_surface():
    # INSEPARABILITY (FINDING 1): a non-coding node is a pure TEXT node — closed
    # tool surface (no built-in tools at all), NOT os_sandbox_required, and it
    # reaches no coding capability. Coding tools flow ONLY from the coding
    # classifier, which fails closed. A de-classified node grants nothing.
    node = NodeDefinition(
        node_id="summarize",
        display_name="Summarize",
        prompt_template="summarize it",
        output_keys=["summarize_out"],
    )
    cfg = _run_node_capturing_config(node)

    assert cfg is not None
    assert cfg.os_sandbox_required is False  # nothing to confine
    assert cfg.closed_tool_surface is True   # --tools "" → no built-in tools
    assert not (cfg.allowed_tools or ())     # nothing granted


# --------------------------------------------------------------------------- #
# (2) draft_patch is a coding node — fails closed by default (no flag needed)
# --------------------------------------------------------------------------- #


def test_draft_patch_fails_closed_no_runner_even_without_flag():
    # A remix that omits requires_sandbox on its draft_patch node still fails
    # closed — draft_patch is a coding-capability node by the backstop.
    node = NodeDefinition(
        node_id="draft_patch",
        display_name="Draft the patch (coding agent)",
        prompt_template="implement the fix on a new branch",
        output_keys=["draft_patch_output"],
    )
    assert node.requires_sandbox is False  # author did NOT set it
    _run_node_expect_fail_closed(node)


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
    # Classify by the STABLE node_kind capability, not the editable node_id. A
    # remix renames draft_patch -> its own id but keeps node_kind="coding" — it is
    # STILL a coding node and STILL fails closed (no runner) through the compiler.
    class N:
        pass

    r = N()
    r.requires_sandbox = False
    r.node_id = "write_the_fix"  # renamed away from draft_patch
    r.node_kind = "coding"
    assert node_requires_sandbox(r) is True

    node = NodeDefinition(
        node_id="write_the_fix",
        display_name="Write the fix",
        prompt_template="implement the fix",
        output_keys=["write_the_fix_out"],
        node_kind="coding",
    )
    assert node.requires_sandbox is False  # flag not set
    assert node.node_id not in ("draft_patch",)  # not the backstop id either
    _run_node_expect_fail_closed(node)  # fails closed despite the rename


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


def test_codex_bypass_requires_attestation_for_all_nodes(monkeypatch):
    # C1 (Codex S3 REJECT): codex honors NO tool policy, so classification is
    # irrelevant — the bypass grants shell/repo to ANY node. It is gated on
    # attestation, independent of os_sandbox_required.
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)

    for cfg in (ModelConfig(), ModelConfig(os_sandbox_required=True)):
        # bwrap present -> real per-call sandbox, no bypass (unchanged droplet path)
        assert _codex_sandbox_args(cfg, _BWRAP_ON) == ["--full-auto"]
        # bwrap absent + UNATTESTED -> REFUSE (never the dangerous bypass)
        with pytest.raises(SandboxUnavailableError):
            _codex_sandbox_args(cfg, _BWRAP_OFF)

    # bwrap absent + ATTESTED (whole process externally isolated) -> bypass OK
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    assert _codex_sandbox_args(ModelConfig(), _BWRAP_OFF) == [
        "--dangerously-bypass-approvals-and-sandbox"
    ]


def test_codex_bwrap_less_unattested_never_emits_bypass(monkeypatch):
    # The actual multi-tenant escape: declassified/text node routed to codex on a
    # bwrap-less unattested host must NEVER get --dangerously-bypass (shell).
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    with pytest.raises(SandboxUnavailableError):
        _codex_sandbox_args(ModelConfig(), _BWRAP_OFF)


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
            CodexProvider().complete("prompt", "", ModelConfig(os_sandbox_required=True))
        )
    assert not spawned


def test_enforce_os_sandbox_requires_whole_process_attestation(monkeypatch):
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    # Host-trusted config: no-op regardless of attestation.
    enforce_os_sandbox(ModelConfig())  # must not raise

    # Coding config with NO attestation: fail closed.
    with pytest.raises(SandboxUnavailableError):
        enforce_os_sandbox(ModelConfig(os_sandbox_required=True))

    # Coding config WITH attestation: allowed.
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    enforce_os_sandbox(ModelConfig(os_sandbox_required=True))  # must not raise


def test_launchable_bwrap_alone_does_not_satisfy_the_gate(monkeypatch):
    # Codex S3 CRITICAL: a launchable bwrap proves only that bwrap CAN start a
    # sandbox — NOT that the running claude -p subprocess is confined. With bwrap
    # "available" but NO whole-process attestation, a coding node MUST still fail
    # closed (a bare Linux host with working bwrap must NOT pass the gate).
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    monkeypatch.setattr(base_mod, "get_sandbox_status", lambda: dict(_BWRAP_ON))
    with pytest.raises(SandboxUnavailableError):
        enforce_os_sandbox(ModelConfig(os_sandbox_required=True))


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
            ClaudeProvider().complete("prompt", "", ModelConfig(os_sandbox_required=True))
        )
    assert not spawned


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
    cfg = ModelConfig(os_sandbox_required=True)

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
    cfg = ModelConfig(os_sandbox_required=True)

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
    # Must NOT become os_sandbox_required: WebFetch-only (no filesystem tools) is
    # DEFENSE-IN-DEPTH (not a proven-complete boundary — see the r15 #2
    # managed-hooks caveat), and requiring bwrap would wrongly break the founder
    # turn on bwrap-less hosts. The complete boundary is the Phase-2 OS worker.
    assert cfg.os_sandbox_required is False


def test_codex_still_refuses_the_universe_conversation_sandbox():
    from tinyassets.exceptions import ProviderError

    cfg = ModelConfig(sandbox_workspace=True)
    with pytest.raises(ProviderError):
        asyncio.run(CodexProvider().complete("hi", "", cfg, universe_dir=Path("/tmp/u")))


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


def _mk_proc():
    mock_proc = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"done", b""))
    mock_proc.returncode = 0
    mock_proc.kill = AsyncMock()
    mock_proc.wait = AsyncMock()
    return mock_proc


# --------------------------------------------------------------------------- #
# (6) Codex round-3 FINDING 3 — sandbox nodes refuse a config-less bridge
# --------------------------------------------------------------------------- #


def test_coding_node_fails_closed_before_any_bridge():
    # A coding node fails closed at the runner gate BEFORE any bridge is called —
    # a config-less bridge that would bypass policy is never even reached.
    node = NodeDefinition(
        node_id="draft_patch",
        display_name="Draft",
        prompt_template="do it",
        output_keys=["draft_patch_output"],
    )

    def config_less(prompt, system, *, role="writer"):  # no `config` kwarg
        raise AssertionError("a coding node must NOT reach ANY bridge")

    fn = _build_prompt_template_node(node, provider_call=config_less, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_text_node_runs_through_a_config_accepting_bridge():
    # A TEXT node runs and receives the closed-surface config.
    node = NodeDefinition(
        node_id="summarize",
        display_name="Summarize",
        prompt_template="do it",
        output_keys=["summarize_out"],
    )
    seen: dict = {}

    def config_ok(prompt, system, *, role="writer", config=None):
        seen["config"] = config
        return "ok"

    fn = _build_prompt_template_node(node, provider_call=config_ok, event_sink=None)
    out = fn({})
    assert out["summarize_out"] == "ok"
    assert seen["config"] is not None
    assert seen["config"].closed_tool_surface is True
    assert seen["config"].os_sandbox_required is False


def test_text_node_refuses_a_config_less_bridge():
    # C1c (Codex S3 REJECT r3): a text node carries the CLOSED tool surface
    # (`--tools ""`). A config-less bridge cannot propagate that, so dispatching
    # would leave the provider unrestricted (claude with default Bash). The node
    # must FAIL CLOSED, never run unrestricted.
    node = NodeDefinition(
        node_id="summarize",
        display_name="Summarize",
        prompt_template="do it",
        output_keys=["summarize_out"],
    )

    def config_less(prompt, system, *, role="writer"):  # no `config` kwarg
        raise AssertionError("config-less bridge must NOT run a hardened node")

    fn = _build_prompt_template_node(node, provider_call=config_less, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


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
            config=ModelConfig(os_sandbox_required=True),
            needs_sandbox=True,
        )


def test_policy_router_runs_hardened_config_accepting_for_sandbox_node():
    from tinyassets.graph_compiler import _call_policy_router_with_retry

    router = _ConfigRouter()
    text, provider, _meta = _call_policy_router_with_retry(
        router,
        role="writer", prompt="p", system="", policy={},
        config=ModelConfig(os_sandbox_required=True),
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
    # the classifier True→False. The escape must grant NOTHING: the node becomes a
    # plain TEXT node with the CLOSED tool surface (no built-in tools at all), no
    # os_sandbox, and it never reaches any coding config or coding spawn path.
    # Coding tools flow ONLY from the coding classifier (which fails closed).
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
    assert cfg.os_sandbox_required is False   # nothing to confine
    assert cfg.closed_tool_surface is True    # --tools "" → no tools at all
    assert not (cfg.allowed_tools or ())      # nothing granted (no Bash/Write)


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
        router.call("writer", "p", "", ModelConfig(os_sandbox_required=True))
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
            router.call("writer", "p", "", ModelConfig(os_sandbox_required=True))
        )
    assert text.calls == 0  # never a fake 'patched'


# --------------------------------------------------------------------------- #
# (11) C1 end-to-end — codex never spawns the bypass on a bwrap-less unattested
# host (the actual escape), for ANY node.
# --------------------------------------------------------------------------- #


def test_codex_complete_refuses_and_never_spawns_bypass_bwrap_less_unattested(monkeypatch):
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    monkeypatch.setattr(
        "tinyassets.providers.codex_provider.get_sandbox_status",
        lambda: dict(_BWRAP_OFF),
    )
    spawned_argv: list = []

    async def _fake_exec(*args, **_k):
        spawned_argv.extend(args)
        raise AssertionError("codex must NOT spawn on a bwrap-less unattested host")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    # A plain host/text config (declassified node routed to codex) still refuses —
    # the bypass grants shell regardless of node classification.
    with pytest.raises(SandboxUnavailableError):
        asyncio.run(CodexProvider().complete("p", "", ModelConfig()))
    assert not spawned_argv  # argv never built → never contains --dangerously-bypass
    assert "--dangerously-bypass-approvals-and-sandbox" not in spawned_argv


# --------------------------------------------------------------------------- #
# (12) C2 — the run's per-universe UniverseContext is threaded; universe A's run
# never cross-resolves universe B's credentials.
# --------------------------------------------------------------------------- #


def test_bridge_carries_run_universe_context_and_never_crosses():
    import functools

    from tinyassets.providers.base import UniverseContext

    uctx_a = UniverseContext(universe_dir=Path("/u/A"))
    uctx_b = UniverseContext(universe_dir=Path("/u/B"))
    seen: dict = {}

    def stub(prompt, system, *, role="writer", config=None, universe_context=None):
        seen["uctx"] = universe_context
        return "ok"

    # run_branch binds the run's OWN universe (A) into the provider bridge.
    bound = functools.partial(stub, universe_context=uctx_a)
    node = NodeDefinition(
        node_id="summarize", display_name="S", prompt_template="do it",
        output_keys=["summarize_out"],
    )
    fn = _build_prompt_template_node(node, provider_call=bound, event_sink=None)
    fn({})
    assert seen["uctx"] is uctx_a  # the run's own universe...
    assert seen["uctx"] is not uctx_b  # ...never another universe's vault scope
    assert seen["uctx"].universe_dir == Path("/u/A")


def test_policy_router_forwards_universe_context():
    from tinyassets.graph_compiler import _call_policy_router_with_retry
    from tinyassets.providers.base import UniverseContext

    seen: dict = {}

    class _UctxRouter:
        def call_with_policy_sync(
            self, role, prompt, system, policy, config=None, *, universe_context=None,
        ):
            seen["uctx"] = universe_context
            return ("ran", "codex", {})

    uctx_a = UniverseContext(universe_dir=Path("/u/A"))
    _call_policy_router_with_retry(
        _UctxRouter(), role="writer", prompt="p", system="", policy={},
        config=None, universe_context=uctx_a,
    )
    assert seen["uctx"] is uctx_a


def test_run_universe_context_resolves_the_runs_own_universe(monkeypatch, tmp_path):
    import tinyassets.api.runs as runs_mod

    udir_a = tmp_path / "A"
    udir_a.mkdir()
    monkeypatch.setattr(runs_mod, "_request_universe", lambda _x: "A")
    monkeypatch.setattr(runs_mod, "_universe_dir", lambda _uid: udir_a)
    monkeypatch.setattr(
        "tinyassets.config.load_universe_config", lambda _udir: object(),
    )
    uctx = runs_mod._run_universe_context("A")
    assert uctx is not None
    assert uctx.universe_dir == udir_a


def test_run_universe_context_fails_closed_when_bound_universe_broken(monkeypatch, tmp_path):
    # C2 r2: a BOUND universe whose config can't load must RAISE (fail closed),
    # never silently fall back to process-global creds.
    import tinyassets.api.runs as runs_mod

    udir_a = tmp_path / "A"
    udir_a.mkdir()
    monkeypatch.setattr(runs_mod, "_request_universe", lambda _x: "A")
    monkeypatch.setattr(runs_mod, "_universe_dir", lambda _uid: udir_a)

    def _boom(_udir):
        raise RuntimeError("universe config is broken")

    monkeypatch.setattr("tinyassets.config.load_universe_config", _boom)
    with pytest.raises(RuntimeError):
        runs_mod._run_universe_context("A")


def test_bind_universe_context_binds_and_resolves_only_the_runs_universe(monkeypatch, tmp_path):
    # resume_run + run_branch_version both route through _bind_universe_context —
    # the run's own universe is bound into the bridge, never another tenant's.
    import functools

    import tinyassets.api.runs as runs_mod

    udir_a = tmp_path / "A"
    udir_a.mkdir()
    monkeypatch.setattr(runs_mod, "_request_universe", lambda x: x or "default")
    monkeypatch.setattr(runs_mod, "_universe_dir", lambda uid: udir_a if uid == "A" else None)
    monkeypatch.setattr(
        "tinyassets.config.load_universe_config", lambda _udir: object(),
    )

    def raw_call(prompt, system, *, role="writer", config=None, universe_context=None):
        return "ok"

    bound = runs_mod._bind_universe_context(raw_call, "A")
    assert isinstance(bound, functools.partial)
    assert bound.keywords["universe_context"].universe_dir == udir_a
    # Legacy UNBOUND call (empty id) → provider_call unchanged (global fallback OK).
    assert runs_mod._bind_universe_context(raw_call, "") is raw_call
    # EXPLICIT binding "B" whose dir is missing → FAIL CLOSED (C2 r3), never global.
    with pytest.raises(SandboxUnavailableError):
        runs_mod._bind_universe_context(raw_call, "B")


# --------------------------------------------------------------------------- #
# (13) C1 r2 real-boundary — codex -C is ALWAYS a per-job scratch (never the
# daemon repo) for EVERY node kind; closed-surface nodes never reach codex.
# --------------------------------------------------------------------------- #


def test_codex_text_node_workdir_is_always_scratch_never_daemon_repo(monkeypatch):
    # A text / declassified (host ModelConfig) node routed to codex must spawn
    # with -C = a fresh scratch dir, NEVER the daemon repo checkout — so codex's
    # workspace-write (--full-auto) lands in an empty scratch, not the checkout.
    import tinyassets.providers.codex_provider as codex_provider

    captured: dict = {}

    async def _fake_exec(*args, **_k):
        captured["args"] = list(args)
        return _mk_proc()

    with (
        patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
              return_value=(["codex"], False)),
        patch("tinyassets.providers.codex_provider.get_sandbox_status",
              return_value=dict(_BWRAP_ON)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        asyncio.run(CodexProvider().complete("p", "", ModelConfig()))  # plain/text

    args = captured["args"]
    workdir = args[args.index("-C") + 1]
    assert "tinyassets-sandbox-job-" in workdir  # per-job scratch...
    repo_root = str(Path(codex_provider.__file__).resolve().parents[2])
    assert workdir != repo_root  # ...NEVER the daemon repo checkout
    assert "/data" not in workdir


def test_closed_surface_call_routes_only_to_enforcing_provider(monkeypatch):
    # A closed_tool_surface (text) call must reach ONLY a provider that honors
    # `--tools ""` (claude); codex (which ignores tool policy) is excluded.
    from tinyassets.providers.base import BaseProvider, ProviderResponse
    from tinyassets.providers.router import ProviderRouter

    called: list = []

    class _Claude(BaseProvider):
        name = "claude-code"
        family = "anthropic"
        enforces_closed_tool_surface = True

        async def complete(self, prompt, system, config, *, universe_dir=None):
            called.append("claude")
            return ProviderResponse(text="text-ok", provider=self.name, model="m",
                                    family=self.family, latency_ms=1.0)

    class _Codex(BaseProvider):
        name = "codex"
        family = "openai"
        enforces_closed_tool_surface = False

        async def complete(self, prompt, system, config, *, universe_dir=None):
            called.append("codex")
            return ProviderResponse(text="LEAK", provider=self.name, model="m",
                                    family=self.family, latency_ms=1.0)

    from tinyassets.sandbox_policy import text_node_model_config
    cfg = text_node_model_config(timeout=60)
    router = ProviderRouter(providers={"claude-code": _Claude(), "codex": _Codex()})
    resp = asyncio.run(router.call("writer", "p", "", cfg))
    assert resp.text == "text-ok"
    assert "codex" not in called  # codex NEVER served the closed-surface node


def test_closed_surface_call_with_only_codex_fails_loud(monkeypatch):
    from tinyassets.exceptions import AllProvidersExhaustedError
    from tinyassets.providers.base import BaseProvider
    from tinyassets.providers.router import ProviderRouter
    from tinyassets.sandbox_policy import text_node_model_config

    class _Codex(BaseProvider):
        name = "codex"
        family = "openai"
        enforces_closed_tool_surface = False

        async def complete(self, prompt, system, config, *, universe_dir=None):
            raise AssertionError("codex must NOT serve a closed-surface node")

    router = ProviderRouter(providers={"codex": _Codex()})
    with pytest.raises(AllProvidersExhaustedError):
        asyncio.run(router.call("writer", "p", "", text_node_model_config(timeout=60)))


# --------------------------------------------------------------------------- #
# (14) C1b/C3/C4 r3 — config-build fail-closed, tool-less providers safe for a
# closed surface, claude text-node cwd is a scratch (never the daemon repo).
# --------------------------------------------------------------------------- #


def test_config_build_failure_fails_closed_never_unrestricted(monkeypatch):
    # C1b: if the ModelConfig can't build (e.g. a bad value that slipped past
    # authoring), the node must FAIL CLOSED — never dispatch a config-less /
    # unrestricted bridge.
    import tinyassets.sandbox_policy as sp_mod

    def _boom(*_a, **_k):
        raise ValueError("cannot build config (e.g. int(nan))")

    monkeypatch.setattr(sp_mod, "text_node_model_config", _boom)
    node = NodeDefinition(
        node_id="summarize", display_name="S", prompt_template="do it",
        output_keys=["summarize_out"],
    )
    ran: list = []

    def stub(prompt, system, *, role="writer", config=None):
        ran.append(1)
        return "SHOULD NOT RUN"

    fn = _build_prompt_template_node(node, provider_call=stub, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})
    assert not ran  # never reached the provider


def test_closed_surface_ollama_only_branch_runs_not_exhausted(monkeypatch):
    # C3: ollama (and gemini/groq/grok) are inherently tool-less HTTP providers —
    # SAFE for a closed-surface node — so an ollama-only closed-surface call runs
    # rather than exhausting.
    from tinyassets.providers.base import BaseProvider, ProviderResponse
    from tinyassets.providers.router import ProviderRouter
    from tinyassets.sandbox_policy import text_node_model_config

    class _Ollama(BaseProvider):
        name = "ollama-local"
        family = "local"
        enforces_closed_tool_surface = True

        async def complete(self, prompt, system, config, *, universe_dir=None):
            return ProviderResponse(text="local-text", provider=self.name, model="m",
                                    family=self.family, latency_ms=1.0)

    router = ProviderRouter(providers={"ollama-local": _Ollama()})
    resp = asyncio.run(router.call("writer", "p", "", text_node_model_config(timeout=60)))
    assert resp.text == "local-text"  # ran on the tool-less provider


def test_claude_text_node_cwd_is_scratch_never_daemon_repo(monkeypatch):
    # C4: a hardened claude spawn (closed text surface) pins cwd to a fresh
    # per-job SCRATCH dir — never the daemon repo — so a malicious repo
    # .claude/settings.json hook is never in scope. The scratch has no .claude/,
    # so `--setting-sources project` loads nothing.
    import tinyassets.providers.claude_provider as claude_provider
    from tinyassets.sandbox_policy import text_node_model_config

    captured: dict = {}

    async def _fake_exec(*_args, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        return _mk_proc()

    with (
        patch("tinyassets.providers.claude_provider._resolve_claude_cmd",
              return_value=(["claude"], False)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        asyncio.run(
            ClaudeProvider().complete("p", "", text_node_model_config(timeout=60))
        )

    cwd = captured["cwd"]
    assert cwd and "tinyassets-sandbox-job-" in cwd  # per-job scratch...
    repo_root = str(Path(claude_provider.__file__).resolve().parents[2])
    assert cwd != repo_root  # ...NEVER the daemon repo checkout


# --------------------------------------------------------------------------- #
# (15) r9 — compat router / shell wrapper / choke-point gate fail closed
# --------------------------------------------------------------------------- #


def test_policy_router_refuses_config_less_for_closed_surface_text_node():
    # r9 #1: an ordinary (text/closed_tool_surface) node must NOT run through a
    # legacy policy router that can't carry its config — it would dispatch
    # UNRESTRICTED. Refuse, no dispatch.
    from tinyassets.graph_compiler import _call_policy_router_with_retry
    from tinyassets.sandbox_policy import text_node_model_config

    class _ConfigLessRouter:
        def call_with_policy_sync(self, role, prompt, system, policy):  # no config
            raise AssertionError("router must NOT be dispatched")

    with pytest.raises(SandboxUnavailableError):
        _call_policy_router_with_retry(
            _ConfigLessRouter(), role="writer", prompt="p", system="", policy={},
            config=text_node_model_config(timeout=60), needs_sandbox=False,
        )


def test_policy_router_refuses_when_universe_context_cannot_forward():
    # r9 #1: a supplied scoped UniverseContext the router can't forward would fall
    # back to process-global creds — refuse rather than drop tenant scope.
    from tinyassets.graph_compiler import _call_policy_router_with_retry
    from tinyassets.providers.base import UniverseContext
    from tinyassets.sandbox_policy import text_node_model_config

    class _NoUctxRouter:
        def call_with_policy_sync(self, role, prompt, system, policy, config=None):
            raise AssertionError("router must NOT be dispatched")

    with pytest.raises(SandboxUnavailableError):
        _call_policy_router_with_retry(
            _NoUctxRouter(), role="writer", prompt="p", system="", policy={},
            config=text_node_model_config(timeout=60),
            universe_context=UniverseContext(universe_dir=Path("/u/A")),
        )


def test_claude_hardened_call_refuses_windows_shell_wrapper(monkeypatch):
    # r9 #2: a hardened claude call routed through a Windows .cmd/.bat wrapper
    # (use_shell=True) would have its `--tools ""` mangled to literal '' by
    # shlex.join under cmd.exe — refuse rather than run un-hardened, no spawn.
    from tinyassets.sandbox_policy import text_node_model_config

    spawned: list = []

    async def _fake(*_a, **_k):
        spawned.append(1)
        raise AssertionError("must not spawn a hardened call through the shell")

    monkeypatch.setattr("asyncio.create_subprocess_shell", _fake)
    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake)
    with patch(
        "tinyassets.providers.claude_provider._resolve_claude_cmd",
        return_value=(["claude.cmd"], True),  # .cmd wrapper → use_shell=True
    ):
        with pytest.raises(SandboxUnavailableError):
            asyncio.run(
                ClaudeProvider().complete("p", "", text_node_model_config(timeout=60))
            )
    assert not spawned


def test_source_code_repo_node_fails_closed_at_choke_point():
    # r9 #3: a source_code node classified repo-touching must fail closed at the
    # single choke point (_build_node) — it must NOT route around the gate through
    # the source_code adapter (validation + runtime now agree).
    from tinyassets.graph_compiler import _build_node

    node = NodeDefinition(
        node_id="inspect_repo",
        display_name="Inspect",
        source_code="def run(state):\n    return {'x': 'EXECUTED'}",
        output_keys=["x"],
        node_kind="repo_read",
    )
    fn = _build_node(node, provider_call=None, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_claude_text_node_spawns_closed_surface_argv(monkeypatch):
    # The LIVE hardened path: a text node's spawned argv carries the closed tool
    # surface (--tools "") + strict empty MCP config + stripped ambient config.
    from tinyassets.sandbox_policy import text_node_model_config

    captured: list = []

    async def _fake_exec(*args, **_k):
        captured.extend(args)
        return _mk_proc()

    with (
        patch("tinyassets.providers.claude_provider._resolve_claude_cmd",
              return_value=(["claude"], False)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        asyncio.run(
            ClaudeProvider().complete("p", "", text_node_model_config(timeout=60))
        )

    assert "--tools" in captured
    assert captured[captured.index("--tools") + 1] == ""  # closed surface
    assert "--setting-sources" in captured
    assert captured[captured.index("--setting-sources") + 1] == "project"
    assert "--strict-mcp-config" in captured
    assert "--mcp-config" in captured


# --------------------------------------------------------------------------- #
# Codex S3 r11 — source_code is in-process host code: it fails closed at the
# sandbox choke-point regardless of user-controlled metadata (the escape).
# --------------------------------------------------------------------------- #


def _approved_source_node(node_id="n", *, node_kind="", requires_sandbox=False):
    from tinyassets.branches import NodeDefinition

    n = NodeDefinition(
        node_id=node_id, display_name="N",
        source_code="def run(state):\n    return {'proof': 'host code executed'}\n",
        node_kind=node_kind, requires_sandbox=requires_sandbox,
    )
    n.mark_approved(approved_by="host")  # genuine approval (matching hash)
    return n


def test_source_code_node_fails_closed_at_choke_point():
    """A source_code node is classified source_exec (repo/host-code touching) and
    fails closed at the graph choke-point — the in-process ``exec`` never runs."""
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import (
        node_capability,
        node_requires_sandbox_runner,
    )

    n = _approved_source_node()
    assert node_capability(n) == "source_exec"
    assert node_requires_sandbox_runner(n) is True
    fn = _build_node(n, provider_call=None, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_source_code_metadata_downgrade_still_fails_closed():
    """The exact Codex r11 escape: approve a source_code node, then reclassify it
    ``text`` / requires_sandbox=False. Classification is derived from the ACTUAL
    source_code, not the mutable metadata — so it STILL fails closed and the
    malicious host code is NEVER executed in-process."""
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import node_capability

    n = _approved_source_node(node_kind="coding", requires_sandbox=True)
    assert node_capability(n) == "source_exec"
    # Downgrade the mutable metadata (the escape) — approval hash still matches.
    n.node_kind = "text"
    n.requires_sandbox = False
    assert n.approved is True and n.approved_source_hash  # approval untouched
    # Classification is unspoofable: still source_exec, still fails closed.
    assert node_capability(n) == "source_exec"
    fn = _build_node(n, provider_call=None, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_legacy_unclassified_approved_source_fails_closed():
    """A legacy approved source_code node with NO node_kind and requires_sandbox
    False (the pre-classification shape) also fails closed — approval alone can
    never authorize in-process host-code execution in Phase 1."""
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import node_capability

    n = _approved_source_node(node_kind="", requires_sandbox=False)
    assert node_capability(n) == "source_exec"
    fn = _build_node(n, provider_call=None, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


# --------------------------------------------------------------------------- #
# Codex S3 r12 #1 — opaque ADAPTER callables are classified by their registered
# capability (not node fields). A repo-touching or UNCLASSIFIED opaque adapter
# fails closed at the SAME choke point, before dispatch.
# --------------------------------------------------------------------------- #


@pytest.fixture
def _opaque_registry():
    """Snapshot + restore the domain registry so per-test registrations don't
    leak. Ensures the platform effectors are registered for the test."""
    import tinyassets.domain_registry as dr
    import tinyassets.effectors  # noqa: F401 — registers read_repo_files etc.

    saved = dict(dr._REGISTRY)
    saved_cap = dict(dr._CAPABILITY_REGISTRY)
    saved_host = dict(dr._HOST_ONLY_REGISTRY)
    yield dr
    dr._REGISTRY.clear()
    dr._REGISTRY.update(saved)
    dr._CAPABILITY_REGISTRY.clear()
    dr._CAPABILITY_REGISTRY.update(saved_cap)
    dr._HOST_ONLY_REGISTRY.clear()
    dr._HOST_ONLY_REGISTRY.update(saved_host)


def test_opaque_repo_read_adapter_fails_closed(_opaque_registry):
    """read_repo_files reads a user-bound repo — declared capability=repo_read, so
    it fails closed at the choke point (the sibling of the source_code escape:
    a real repo adapter that classified as `text` and EXECUTED)."""
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import effective_node_capability

    node = NodeDefinition(node_id="read_repo_files", display_name="Read")
    assert effective_node_capability(node, "tinyassets") == "repo_read"
    fn = _build_node(node, provider_call=None, event_sink=None, domain_id="tinyassets")
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_unclassified_opaque_adapter_fails_closed(_opaque_registry):
    """An opaque adapter registered with NO declared capability is UNCLASSIFIED
    and must refuse — never default to text (Codex S3 r12 #1)."""
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import effective_node_capability

    _opaque_registry.register_domain_callable(
        "testdom", "mystery", lambda s: {"x": 1},  # NO capability declared
    )
    node = NodeDefinition(node_id="mystery", display_name="Mystery")
    assert effective_node_capability(node, "testdom") == "opaque_unclassified"
    fn = _build_node(node, provider_call=None, event_sink=None, domain_id="testdom")
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_text_declared_opaque_adapter_runs(_opaque_registry):
    """A safe opaque adapter that DECLARES capability=text runs (it is not a
    repo/exec surface) — the classifier doesn't over-block."""
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import effective_node_capability

    _opaque_registry.register_domain_callable(
        "testdom", "safe", lambda s: {"safe_out": "ok"}, capability="text",
    )
    node = NodeDefinition(node_id="safe", display_name="Safe", output_keys=["safe_out"])
    assert effective_node_capability(node, "testdom") == "text"
    fn = _build_node(node, provider_call=None, event_sink=None, domain_id="testdom")
    assert fn({}) == {"safe_out": "ok"}


# --------------------------------------------------------------------------- #
# Codex S3 r12 #2 — provider_call is a CAPABILITY-BEARING interface. A provider
# that cannot carry the hardened `config` is REJECTED (fail closed), not run
# unrestricted. Proven directly, not via a **kwargs-swallowing stub.
# --------------------------------------------------------------------------- #


def _text_node() -> NodeDefinition:
    return NodeDefinition(
        node_id="t", display_name="T", prompt_template="do {x}",
        input_keys=["x"], output_keys=["t_out"],
    )


def test_config_less_provider_rejected_for_closed_surface_node():
    """Every runnable text node is closed_tool_surface; a provider_call whose
    signature carries NEITHER `config` NOR `**kwargs` cannot receive the hardened
    tool policy, so the bridge REFUSES it before dispatch (fail closed) rather
    than run claude with default Bash."""
    called: list = []

    def legacy(prompt, system, *, role="writer"):  # NO config, NO **kwargs
        called.append(1)
        return "unrestricted"

    fn = _build_prompt_template_node(_text_node(), provider_call=legacy, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({"x": "1"})
    assert not called, "a config-less provider must be refused BEFORE dispatch"


def test_config_bearing_provider_receives_hardened_config():
    """A provider that names `config` receives the closed-tool-surface config —
    proving the config actually reaches the (would-be) subprocess."""
    captured: list = []

    def provider(prompt, system, *, role="writer", config=None):
        captured.append(config)
        return "ok"

    fn = _build_prompt_template_node(_text_node(), provider_call=provider, event_sink=None)
    fn({"x": "1"})
    assert captured and captured[-1] is not None
    assert getattr(captured[-1], "closed_tool_surface", False) is True


def test_kwargs_provider_carries_config():
    """A `**kwargs` provider (the real bridge is `call_provider` + partial) IS
    config-bearing — it receives the hardened config, so it is not refused."""
    captured: dict = {}

    def provider(prompt, system, *, role="writer", **kw):
        captured.update(kw)
        return "ok"

    fn = _build_prompt_template_node(_text_node(), provider_call=provider, event_sink=None)
    fn({"x": "1"})
    assert "config" in captured
    assert getattr(captured["config"], "closed_tool_surface", False) is True


# --------------------------------------------------------------------------- #
# Codex S3 r13 #1 — HOST-ONLY vs COMMUNITY-CALLABLE trust boundary. A user-
# authored (untrusted) branch cannot compile/queue/execute a host-only adapter;
# only a trusted (daemon) compile may.
# --------------------------------------------------------------------------- #


def test_host_only_adapter_refused_for_user_branch(_opaque_registry):
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import branch_sandbox_status, effective_node_capability

    _opaque_registry.register_domain_callable(
        "hostdom", "danger", lambda s: {"ran": True}, host_only=True,
    )
    node = NodeDefinition(node_id="danger", display_name="Danger")
    # Classifier reports it as host_only → blocked for user branches.
    assert effective_node_capability(node, "hostdom") == "host_only"
    assert branch_sandbox_status([node], "hostdom")[0] is True
    # Untrusted (user) compile fails closed — never reaches the callable.
    fn = _build_node(
        node, provider_call=None, event_sink=None, domain_id="hostdom", trusted=False,
    )
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_host_only_adapter_allowed_for_trusted_compile(_opaque_registry):
    from tinyassets.graph_compiler import _build_node

    _opaque_registry.register_domain_callable(
        "hostdom", "danger", lambda s: {"ran": True}, host_only=True,
    )
    node = NodeDefinition(node_id="danger", display_name="Danger", output_keys=["ran"])
    # A trusted (daemon) compile is permitted to build + run the host-only adapter.
    fn = _build_node(
        node, provider_call=None, event_sink=None, domain_id="hostdom", trusted=True,
    )
    assert fn({}) == {"ran": True}


# --------------------------------------------------------------------------- #
# Codex S3 r13 #2 — a typo'd / unknown capability at REGISTRATION is treated as
# UNCLASSIFIED permanently (fail closed), never accepted.
# --------------------------------------------------------------------------- #


def test_unknown_capability_registration_fails_closed(_opaque_registry, monkeypatch):
    import tinyassets.sandbox_policy as sp
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import effective_node_capability

    # A repo_read typo — must NOT be accepted as some runnable repo capability.
    _opaque_registry.register_domain_callable(
        "typodom", "x", lambda s: {"ran": True}, capability="repo_raed",
    )
    assert _opaque_registry.resolve_domain_capability("typodom", "x") is None
    node = NodeDefinition(node_id="x", display_name="X")
    assert effective_node_capability(node, "typodom") == "opaque_unclassified"
    # Even with a (simulated) runner present, an unclassified adapter refuses.
    monkeypatch.setattr(sp, "coding_nodes_runnable", lambda: (True, "runner"))
    fn = _build_node(node, provider_call=None, event_sink=None, domain_id="typodom")
    with pytest.raises(SandboxUnavailableError):
        fn({})


# --------------------------------------------------------------------------- #
# Codex S3 r13 #3 — no mock response in production (Hard Rule 8). A prompt node
# with provider_call=None FAILS LOUD unless the explicit test-only force-mock
# switch is on.
# --------------------------------------------------------------------------- #


def test_no_provider_fails_loud_in_production(monkeypatch):
    from tinyassets.graph_compiler import CompilerError, _build_node
    from tinyassets.providers import call as _call

    # Simulate production: the test-only force-mock switch is OFF.
    monkeypatch.setattr(_call, "_force_mock", False)
    node = NodeDefinition(
        node_id="t", display_name="T", prompt_template="hi", output_keys=["t_out"],
    )
    fn = _build_node(node, provider_call=None, event_sink=None)
    with pytest.raises(CompilerError, match="no provider|fail loud|Mock|mock"):
        fn({})


def test_mock_still_works_behind_force_mock_switch():
    """Sanity: with the force-mock switch ON (the conftest default), the mock
    path is available for tests — it is a test-only affordance, not removed."""
    from tinyassets.graph_compiler import _build_node
    from tinyassets.providers.call import is_force_mock

    assert is_force_mock() is True  # conftest sets it session-wide
    node = NodeDefinition(
        node_id="t", display_name="T", prompt_template="hi", output_keys=["t_out"],
    )
    fn = _build_node(node, provider_call=None, event_sink=None)
    out = fn({})
    assert "Mock response" in out["t_out"]


# --------------------------------------------------------------------------- #
# Codex S3 r14 #1 — classifier precedence: registered adapter trust DOMINATES
# mutable node metadata; most-restrictive rank wins. Runner-enabled so a mistaken
# non-text classification would actually EXECUTE (proving the fix, not luck).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("node_kind", ["", "text", "coding", "repo_read", "repo_exec"])
def test_host_only_dominates_every_node_kind(_opaque_registry, monkeypatch, node_kind):
    import tinyassets.sandbox_policy as sp
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import effective_node_capability

    monkeypatch.setattr(sp, "coding_nodes_runnable", lambda: (True, "runner on"))
    _opaque_registry.register_domain_callable(
        "hd", "danger", lambda s: {"ran": True}, host_only=True,
    )
    node = NodeDefinition(node_id="danger", display_name="D", node_kind=node_kind)
    # Mutable node_kind can NEVER lower host_only below sandbox-required.
    assert effective_node_capability(node, "hd") == "host_only"
    fn = _build_node(node, provider_call=None, event_sink=None, domain_id="hd", trusted=False)
    with pytest.raises(SandboxUnavailableError):
        fn({})


@pytest.mark.parametrize("node_kind", ["", "text", "coding", "repo_exec"])
def test_unclassified_dominates_every_node_kind(_opaque_registry, monkeypatch, node_kind):
    import tinyassets.sandbox_policy as sp
    from tinyassets.graph_compiler import _build_node
    from tinyassets.sandbox_policy import effective_node_capability

    monkeypatch.setattr(sp, "coding_nodes_runnable", lambda: (True, "runner on"))
    _opaque_registry.register_domain_callable(
        "ud", "myst", lambda s: {"ran": True},  # NO declared capability
    )
    node = NodeDefinition(node_id="myst", display_name="M", node_kind=node_kind)
    assert effective_node_capability(node, "ud") == "opaque_unclassified"
    fn = _build_node(node, provider_call=None, event_sink=None, domain_id="ud", trusted=False)
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_declared_adapter_capability_not_reduced_by_node_metadata(_opaque_registry):
    """A declared repo_read adapter tagged node_kind=text must stay repo_read
    (metadata may escalate, never reduce below the adapter's demand)."""
    from tinyassets.sandbox_policy import effective_node_capability

    _opaque_registry.register_domain_callable(
        "rd", "rr", lambda s: {"ran": True}, capability="repo_read",
    )
    downgrade = NodeDefinition(node_id="rr", display_name="R", node_kind="text")
    assert effective_node_capability(downgrade, "rd") == "repo_read"
    # And node metadata MAY escalate the restriction (repo_read → coding).
    escalate = NodeDefinition(node_id="rr", display_name="R", node_kind="coding")
    assert effective_node_capability(escalate, "rd") == "coding"


# --------------------------------------------------------------------------- #
# Codex S3 r14 #2 — the fail-closed user-branch capability validator is enforced
# at the STORAGE choke point (save_branch_definition), so NO persistence path can
# bypass it. A host-only / unclassified selection is refused before persistence.
# --------------------------------------------------------------------------- #


def test_save_branch_definition_refuses_host_only_user_branch(_opaque_registry, tmp_path):
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    _opaque_registry.register_domain_callable(
        "hd", "danger", lambda s: {"ran": True}, host_only=True,
    )
    base = tmp_path / "out"
    base.mkdir()
    initialize_author_server(base)
    branch_def = {
        "branch_def_id": "b1", "name": "evil", "domain_id": "hd",
        "entry_point": "danger",
        "node_defs": [{"node_id": "danger", "display_name": "D"}],
        "graph_nodes": [{"id": "danger", "node_def_id": "danger"}],
        "edges": [{"from_node": "START", "to_node": "danger"},
                  {"from_node": "danger", "to_node": "END"}],
    }
    # The storage choke point refuses (fail closed) — no path can persist it.
    with pytest.raises(ValueError, match="HOST-ONLY|may never run|host-only"):
        save_branch_definition(base, branch_def=branch_def)
    # A trusted (daemon-internal) persist may pass the gate.
    save_branch_definition(base, branch_def=branch_def, _trusted=True)


def test_save_branch_definition_refuses_unclassified_user_branch(_opaque_registry, tmp_path):
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    _opaque_registry.register_domain_callable("ud", "myst", lambda s: {"ran": True})
    base = tmp_path / "out"
    base.mkdir()
    initialize_author_server(base)
    branch_def = {
        "branch_def_id": "b2", "name": "x", "domain_id": "ud",
        "entry_point": "myst",
        "node_defs": [{"node_id": "myst", "display_name": "M"}],
        "graph_nodes": [{"id": "myst", "node_def_id": "myst"}],
        "edges": [{"from_node": "START", "to_node": "myst"},
                  {"from_node": "myst", "to_node": "END"}],
    }
    with pytest.raises(ValueError, match="unclassified|never run"):
        save_branch_definition(base, branch_def=branch_def)


# --------------------------------------------------------------------------- #
# Codex S3 r15 #1 — source_exec (in-process exec) has its OWN readiness gate,
# SEPARATE from the per-job REPO runner. Repo-runner readiness must NEVER enable
# in-process exec.
# --------------------------------------------------------------------------- #


def test_source_exec_refused_even_when_repo_runner_ready(monkeypatch):
    import tinyassets.sandbox_policy as sp
    from tinyassets.graph_compiler import _build_node

    # Simulate the FUTURE repo runner becoming ready.
    monkeypatch.setattr(sp, "coding_nodes_runnable", lambda: (True, "repo runner ready"))
    assert sp.source_exec_runnable()[0] is False  # its own gate stays closed
    src = "def run(state):\n    return {'proof': 'ran'}\n"
    node = NodeDefinition(node_id="evil", display_name="E", source_code=src, approved=True)
    node.mark_approved()
    # branch_sandbox_status must also still block it (no drift from runtime).
    assert sp.branch_sandbox_status([node])[0] is True
    fn = _build_node(node, provider_call=None, event_sink=None)
    with pytest.raises(SandboxUnavailableError):
        fn({})


def test_repo_read_runs_when_repo_runner_ready_proving_the_split(_opaque_registry, monkeypatch):
    """The split is a SEPARATION, not a blanket block: a repo_read adapter DOES
    run when the repo runner is ready (only source_exec stays closed)."""
    import tinyassets.sandbox_policy as sp
    from tinyassets.graph_compiler import _build_node

    monkeypatch.setattr(sp, "coding_nodes_runnable", lambda: (True, "repo runner ready"))
    _opaque_registry.register_domain_callable(
        "rd", "rr", lambda s: {"ok": True}, capability="repo_read",
    )
    node = NodeDefinition(node_id="rr", display_name="R", output_keys=["ok"])
    out = _build_node(
        node, provider_call=None, event_sink=None, domain_id="rd",
    )({})
    assert out == {"ok": True}


# --------------------------------------------------------------------------- #
# Codex S3 r15 #3 — the persistence choke point validates the FULLY-MERGED
# record on EVERY write path (legacy `nodes` + update_branch_definition), not
# just the new node_defs.
# --------------------------------------------------------------------------- #


def _host_reg(reg):
    reg.register_domain_callable("hd", "danger", lambda s: {"ran": True}, host_only=True)


def test_save_via_legacy_nodes_refuses_host_only(_opaque_registry, tmp_path):
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    _host_reg(_opaque_registry)
    base = tmp_path / "out"
    base.mkdir()
    initialize_author_server(base)
    # Legacy `nodes` (no node_defs) carrying a host-only selection.
    rec = {
        "branch_def_id": "b1", "name": "evil", "domain_id": "hd",
        "entry_point": "danger", "nodes": [{"node_id": "danger", "display_name": "D"}],
        "edges": [],
    }
    with pytest.raises(ValueError, match="HOST-ONLY|may never run|host-only"):
        save_branch_definition(base, branch_def=rec)


def test_update_branch_definition_refuses_host_only(_opaque_registry, tmp_path):
    from tinyassets.daemon_server import (
        get_branch_definition,
        initialize_author_server,
        save_branch_definition,
        update_branch_definition,
    )

    _host_reg(_opaque_registry)
    base = tmp_path / "out"
    base.mkdir()
    initialize_author_server(base)
    save_branch_definition(base, branch_def={
        "branch_def_id": "b2", "name": "x", "domain_id": "workflow",
        "entry_point": "n",
        "node_defs": [{"node_id": "n", "display_name": "N", "prompt_template": "hi"}],
        "edges": [],
    })
    # update_branch_definition writes node_defs + domain directly.
    with pytest.raises(ValueError, match="HOST-ONLY|may never run|host-only"):
        update_branch_definition(base, branch_def_id="b2", updates={
            "domain_id": "hd", "node_defs": [{"node_id": "danger", "display_name": "D"}],
        })
    # And nothing was persisted — the node set is unchanged.
    persisted = get_branch_definition(base, branch_def_id="b2")["node_defs"]
    assert [n["node_id"] for n in persisted] == ["n"]


def test_update_domain_only_refuses_when_existing_node_becomes_host_only(
    _opaque_registry, tmp_path,
):
    """A domain-only update can turn an existing benign node into a host-only
    selection — the merged record must be re-validated."""
    from tinyassets.daemon_server import (
        initialize_author_server,
        save_branch_definition,
        update_branch_definition,
    )

    _host_reg(_opaque_registry)
    base = tmp_path / "out"
    base.mkdir()
    initialize_author_server(base)
    # Persist under a domain where "danger" is NOT host-only (workflow) — allowed.
    save_branch_definition(base, branch_def={
        "branch_def_id": "b3", "name": "y", "domain_id": "workflow",
        "entry_point": "danger",
        "node_defs": [{"node_id": "danger", "display_name": "D"}],
        "edges": [],
    })
    # Now flip ONLY the domain to "hd" — "danger" becomes host-only.
    with pytest.raises(ValueError, match="HOST-ONLY|may never run|host-only"):
        update_branch_definition(base, branch_def_id="b3", updates={"domain_id": "hd"})


def test_trusted_persist_bypasses_the_gate(_opaque_registry, tmp_path):
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    _host_reg(_opaque_registry)
    base = tmp_path / "out"
    base.mkdir()
    initialize_author_server(base)
    # _trusted=True (daemon-internal) may persist a host-only node.
    save_branch_definition(base, branch_def={
        "branch_def_id": "b4", "name": "t", "domain_id": "hd",
        "entry_point": "danger",
        "node_defs": [{"node_id": "danger", "display_name": "D"}], "edges": [],
    }, _trusted=True)
