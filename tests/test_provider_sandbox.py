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
