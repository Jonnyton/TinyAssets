"""Provider sandbox seam (2026-07-03 live-test P0).

The founder-facing universe-intelligence turn must run the CLI subprocess
isolated to the universe's own dir with host tools denied. These guard the
``claude_provider`` flag/cwd builder that enforces it, and the ``ModelConfig``
fields that carry the policy.
"""
from __future__ import annotations

from pathlib import Path

from tinyassets.providers.base import ModelConfig
from tinyassets.providers.claude_provider import _sandbox_cli_args


def test_default_config_is_noop_for_host_trusted_roles():
    # A plain ModelConfig (branch runs, judges, etc.) must NOT be sandboxed —
    # no tool flags, no cwd override.
    flags, run_cwd = _sandbox_cli_args(ModelConfig(), Path("C:/repo"))
    assert flags == []
    assert run_cwd is None


def test_sandbox_emits_variadic_tool_flags_and_isolated_cwd(tmp_path):
    cfg = ModelConfig(
        sandbox_workspace=True,
        allowed_tools=("WebFetch",),
        disallowed_tools=("Bash", "Read", "Write"),
    )
    flags, run_cwd = _sandbox_cli_args(cfg, tmp_path)

    # cwd pinned to the universe's own dir (not the daemon checkout)
    assert run_cwd == str(tmp_path)
    # user-tier settings (MCP servers + bypassPermissions) are stripped so the
    # universe can't reach ambient MCP tools (e.g. mcp__codex → code exec)
    assert "--setting-sources" in flags
    assert flags[flags.index("--setting-sources") + 1] == "project"
    # variadic flags: each tool is its OWN argv token (a joined string would be
    # read as one bogus tool name and silently match nothing)
    assert "--allowedTools" in flags
    assert "WebFetch" in flags
    assert flags[flags.index("--allowedTools") + 1] == "WebFetch"
    assert "--disallowedTools" in flags
    for denied in ("Bash", "Read", "Write"):
        assert denied in flags


def test_sandbox_without_universe_dir_fails_closed():
    # A sandboxed turn with no universe_dir would inherit the daemon's cwd —
    # the exact leak this fixes. It must FAIL CLOSED, not run un-isolated.
    import pytest

    from tinyassets.exceptions import ProviderError

    with pytest.raises(ProviderError):
        _sandbox_cli_args(ModelConfig(sandbox_workspace=True), None)


def test_codex_refuses_a_sandboxed_founder_turn():
    # Codex cannot enforce the universe sandbox, so a founder-facing (sandboxed)
    # turn routed to Codex must fail closed rather than run unconfined.
    import asyncio

    import pytest

    from tinyassets.exceptions import ProviderError
    from tinyassets.providers.codex_provider import CodexProvider

    cfg = ModelConfig(sandbox_workspace=True)
    with pytest.raises(ProviderError):
        asyncio.run(
            CodexProvider().complete("hi", "", cfg, universe_dir=Path("C:/u"))
        )


def test_disallow_only_still_emits_deny_floor(tmp_path):
    # The deny floor is emitted even without an allowlist.
    cfg = ModelConfig(sandbox_workspace=True, disallowed_tools=("Bash",))
    flags, _ = _sandbox_cli_args(cfg, tmp_path)
    assert "--disallowedTools" in flags
    assert "Bash" in flags
    assert "--allowedTools" not in flags


def test_codex_fast_exit_excerpt_is_redacted_and_capped():
    from tinyassets.providers.codex_provider import _redacted_stderr_excerpt

    raw = "warning: x\nerror: auth failed token=sk-abcdefghijklmnop Bearer eyJhbGciOi.abcdefghijk\n"
    out = _redacted_stderr_excerpt(raw)
    assert "sk-abc" not in out and "eyJ" not in out and "[redacted]" in out
    # No generic long-token rule: hashes / paths / model ids stay readable.
    keep = "stream error for model gpt-5.5 at /opt/codex-install/node_modules/.bin/codex sha256:"
    keep += "a" * 64
    assert _redacted_stderr_excerpt(keep) == keep
    # Long lines keep head AND tail (codex appends its auth error code last).
    long = "x" * 400 + " auth error code: E_FOO"
    ex = _redacted_stderr_excerpt(long)
    assert len(ex) <= 240 and ex.endswith("E_FOO") and " ... " in ex
    assert _redacted_stderr_excerpt("") == "(no stderr)"


def test_bwrap_proc_mount_and_lock_signatures_are_sandbox_failures(monkeypatch):
    import sys

    import pytest

    from tinyassets.providers.base import SandboxUnavailableError, check_bwrap_failure

    monkeypatch.setattr(sys, "platform", "linux")
    for text in (
        "bwrap: Can't mount proc on /newroot/proc: Operation not permitted",
        "flock: cannot open lock file /codex-home/.lock: Read-only file system",
    ):
        with pytest.raises(SandboxUnavailableError):
            check_bwrap_failure(text)
    # an unrelated lock error is NOT a sandbox failure
    check_bwrap_failure("flock: cannot open lock file /data/.codex/.lock: Permission denied")


def test_workflow_node_call_is_pinned_to_its_universe_with_host_tools_denied(tmp_path):
    # A workflow node call (2026-09-24 latency root cause): cwd pinned to the
    # universe, project-only settings, shell/filesystem builtins denied, and
    # the node's own denies kept. Web tools are not the host's and stay.
    from tinyassets.providers.base import ACCOUNT_REACH_TOOLS, HOST_REACH_TOOLS

    cfg = ModelConfig(workflow_node=True, disallowed_tools=("CronCreate",))
    flags, run_cwd = _sandbox_cli_args(cfg, tmp_path)

    assert run_cwd == str(tmp_path)
    assert flags[flags.index("--setting-sources") + 1] == "project"
    denied = flags[flags.index("--disallowedTools") + 1:]
    assert denied == ["CronCreate", *HOST_REACH_TOOLS, *ACCOUNT_REACH_TOOLS]
    assert "--allowedTools" not in flags
    assert "WebSearch" not in denied and "WebFetch" not in denied


def test_workflow_node_call_without_a_universe_fails_closed():
    import pytest

    from tinyassets.exceptions import ProviderError

    with pytest.raises(ProviderError):
        _sandbox_cli_args(ModelConfig(workflow_node=True), None)


def test_account_reach_tools_are_denied_on_both_confined_paths(tmp_path):
    """One constant, both call paths -- the gap found reviewing CLI 2.1.288.

    These act on the DAEMON HOST'S claude.ai account, so neither the OS jail
    (nothing touches disk, no shell starts) nor ``--strict-mcp-config`` (they
    are builtins, not MCP servers) bounds them. The engine turn denied them; a
    WORKFLOW NODE denied only ``HOST_REACH_TOOLS``, so a node could publish an
    artifact or message another session on the host's account.
    """
    from tinyassets.providers.base import ACCOUNT_REACH_TOOLS
    from tinyassets.universe_intelligence import (
        _ENGINE_DISALLOWED_TOOLS,
        _ENGINE_DISALLOWED_TOOLS_WITH_MCP,
    )

    assert ACCOUNT_REACH_TOOLS, "the constant must not be empty"

    node_flags, _cwd = _sandbox_cli_args(ModelConfig(workflow_node=True), tmp_path)
    node_denied = node_flags[node_flags.index("--disallowedTools") + 1:]
    for tool in ACCOUNT_REACH_TOOLS:
        assert tool in node_denied, f"{tool} callable on a workflow node"
        assert tool in _ENGINE_DISALLOWED_TOOLS, f"{tool} callable on an engine turn"
        # Also denied when engine MCP is on: that turn drops only the ``mcp__*``
        # wildcard and ``ToolSearch``, never a builtin.
        assert tool in _ENGINE_DISALLOWED_TOOLS_WITH_MCP, f"{tool} callable with MCP on"


def test_the_two_reach_constants_stay_separate_and_disjoint():
    """Host reach and account reach are different boundaries, not one list.

    ``HOST_REACH_TOOLS`` is bounded by the OS jail and is also a latency
    control on nodes; ``ACCOUNT_REACH_TOOLS`` is bounded by neither the jail
    nor strict MCP. Merging them would lose the reason either exists.
    """
    from tinyassets.providers.base import ACCOUNT_REACH_TOOLS, HOST_REACH_TOOLS

    assert not set(HOST_REACH_TOOLS) & set(ACCOUNT_REACH_TOOLS)
    assert len(set(ACCOUNT_REACH_TOOLS)) == len(ACCOUNT_REACH_TOOLS), "no duplicates"
    # SendMessage lives in the account constant, not as a second literal in the
    # engine list: one definition is the point.
    assert "SendMessage" in ACCOUNT_REACH_TOOLS


def test_the_engine_denylist_has_no_duplicate_names(tmp_path):
    """Splatting a shared constant must not leave a name listed twice."""
    from tinyassets.universe_intelligence import _ENGINE_DISALLOWED_TOOLS

    duplicated = sorted({
        t for t in _ENGINE_DISALLOWED_TOOLS
        if _ENGINE_DISALLOWED_TOOLS.count(t) > 1
    })
    assert duplicated == [], duplicated

    node_flags, _cwd = _sandbox_cli_args(
        ModelConfig(workflow_node=True, disallowed_tools=("Artifact",)), tmp_path,
    )
    node_denied = node_flags[node_flags.index("--disallowedTools") + 1:]
    # A node that already denied one of them by name keeps exactly one copy.
    assert node_denied.count("Artifact") == 1
