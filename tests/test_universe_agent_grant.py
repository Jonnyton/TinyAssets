"""Who gets hands, and who does not.

The grant IS the authorization. There is no downstream check to fall back on —
`api/wiki.py:2523-2541` deliberately skips the MCP ACL gate for first-party
canon writes on the grounds that something upstream already proved ownership.
So these tests are that proof, and they must fail loudly if the tier check ever
stops deciding the grant.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tinyassets.providers.base import ModelConfig, UniverseContext
from tinyassets.providers.claude_provider import _sandbox_cli_args
from tinyassets.universe_intelligence import _ENGINE_TOOL_SERVER, _sandboxed_config


@pytest.fixture
def ctx(tmp_path):
    universe = tmp_path / "u-grant"
    universe.mkdir()
    return UniverseContext(universe_dir=universe, config=None)


# --------------------------------------------------------------------------
# The grant
# --------------------------------------------------------------------------


def test_an_ungranted_turn_gets_no_tool_server(ctx):
    config = _sandboxed_config(ctx, grant_tools=False)
    assert config.mcp_config_path == ""
    assert "mcp__*" in config.disallowed_tools
    assert "ToolSearch" in config.disallowed_tools
    assert config.allowed_tools == ("WebFetch",)


def test_a_granted_turn_gets_exactly_its_own_server(ctx):
    config = _sandboxed_config(ctx, grant_tools=True)
    assert config.mcp_config_path
    assert f"mcp__{_ENGINE_TOOL_SERVER}__*" in config.allowed_tools
    assert "WebFetch" in config.allowed_tools


def test_a_granted_turn_can_actually_see_its_tools(ctx):
    """`ToolSearch` and `mcp__*` must BOTH stop being denied.

    Verified live 2026-08-07: MCP tools arrive deferred, and with `ToolSearch`
    denied the granted server is invisible — the turn reports "no tool by that
    name exists". A grant the model cannot see is not a grant.
    """
    config = _sandboxed_config(ctx, grant_tools=True)
    assert "ToolSearch" not in config.disallowed_tools
    assert "mcp__*" not in config.disallowed_tools
    assert "ToolSearch" in config.allowed_tools


def test_a_granted_turn_still_has_no_shell_or_filesystem(ctx):
    """Hands, not the host. The 2026-07-03 leak must stay closed."""
    config = _sandboxed_config(ctx, grant_tools=True)
    for tool in ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "Monitor", "Task"):
        assert tool in config.disallowed_tools, tool


def test_the_grant_file_is_written_outside_the_workspace(ctx):
    """Otherwise the agent's own file tools could rewrite its own grant."""
    config = _sandboxed_config(ctx, grant_tools=True)
    grant = Path(config.mcp_config_path).resolve()
    universe = Path(ctx.universe_dir).resolve()
    assert not grant.is_relative_to(universe)


def test_the_grant_names_this_universe_and_only_this_universe(ctx):
    import json

    config = _sandboxed_config(ctx, grant_tools=True)
    payload = json.loads(Path(config.mcp_config_path).read_text(encoding="utf-8"))
    servers = payload["mcpServers"]
    assert list(servers) == [_ENGINE_TOOL_SERVER]
    env = servers[_ENGINE_TOOL_SERVER]["env"]
    assert env["TINYASSETS_AGENT_UNIVERSE_DIR"] == str(ctx.universe_dir)


# --------------------------------------------------------------------------
# The CLI flags
# --------------------------------------------------------------------------


def test_strict_mcp_config_always_accompanies_the_grant(tmp_path):
    """`--mcp-config` WITHOUT `--strict-mcp-config` re-opens ambient MCP.

    That is the 2026-07-03 hole (the sandboxed turn saw `mcp__codex__codex` →
    arbitrary code execution). The two flags are one decision and must never be
    separable.
    """
    universe = tmp_path / "u-flags"
    universe.mkdir()
    config = ModelConfig(
        sandbox_workspace=True,
        allowed_tools=("WebFetch",),
        disallowed_tools=("Bash",),
        mcp_config_path=str(tmp_path / "grant.json"),
    )
    flags, _ = _sandbox_cli_args(config, universe)
    assert "--mcp-config" in flags
    assert "--strict-mcp-config" in flags
    assert flags[flags.index("--mcp-config") + 1] == str(tmp_path / "grant.json")


def test_no_grant_means_no_mcp_flags(tmp_path):
    universe = tmp_path / "u-flags"
    universe.mkdir()
    config = ModelConfig(
        sandbox_workspace=True,
        allowed_tools=("WebFetch",),
        disallowed_tools=("Bash", "mcp__*"),
    )
    flags, _ = _sandbox_cli_args(config, universe)
    assert "--mcp-config" not in flags
    assert "--strict-mcp-config" not in flags


# --------------------------------------------------------------------------
# The decision point itself
# --------------------------------------------------------------------------


def _capture_turn(monkeypatch, tmp_path, tier):
    """Run one `converse` turn and return the ModelConfig it launched with."""
    from tinyassets import universe_intelligence as ui
    from tinyassets.universe_bundle import seed_okf_bundle

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    universe = tmp_path / "u-gate"
    universe.mkdir()
    seed_okf_bundle(universe, purpose="grant gate test")
    # A universe with nothing learned withholds content from lower tiers, which
    # is correct — but it would make this a test of persona visibility rather
    # than of the tool grant. Give it something every tier may read.
    (universe / "identity.md").write_text(
        "\n".join(
            [
                "---",
                "type: Universe Identity",
                "status: learned",
                "name: Gate",
                "---",
                "",
                "I am a test universe.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    captured: dict = {}

    def _fake_call_provider(prompt, *, system="", role="", universe_context=None,
                            config=None, **kwargs):
        captured["config"] = config
        return "a reply"

    monkeypatch.setattr(ui, "call_provider", _fake_call_provider)
    # Persona visibility is a separate gate with its own tests, and it needs a
    # registered universe. Stub it so a failure here can only mean the TOOL
    # GRANT changed — otherwise this test would go green for the wrong reason
    # the moment visibility started refusing.
    monkeypatch.setattr(
        ui, "_build_persona_system_prompt", lambda *a, **k: "you are a test universe"
    )
    # Learning persistence is not under test here and would need real storage.
    monkeypatch.setattr(ui, "extract_learning", lambda *a, **k: {})
    monkeypatch.setattr(ui, "commit_learning", lambda *a, **k: None)

    ui.converse("u-gate", "hello", tier=tier)
    return captured["config"]


def test_a_founder_turn_is_launched_with_hands(monkeypatch, tmp_path):
    from tinyassets.api import interlocutor

    config = _capture_turn(monkeypatch, tmp_path, interlocutor.FOUNDER)
    assert config.mcp_config_path, "the founder's own turn got no tool server"


def test_a_non_founder_turn_is_launched_with_none(monkeypatch, tmp_path):
    """The gate, stated as a test.

    Mutation-probe target for task 3.3: replacing the tier check with a constant
    `True` must turn this red. If it does not, the gate is decorative and a
    stranger in a Slack channel can write to the founder's brain.
    """
    from tinyassets.api import interlocutor

    # T1, not T0: an anonymous T0 reader is refused before the model is even
    # reached on a private universe, which would make this pass for the wrong
    # reason. T1 gets a real reply and must still get no hands.
    config = _capture_turn(monkeypatch, tmp_path, interlocutor.T1)
    assert config.mcp_config_path == "", "a non-founder turn was handed tools"
    assert "mcp__*" in config.disallowed_tools


def test_the_grant_makes_the_server_importable(ctx):
    """The server runs with the SANDBOXED cwd, so it needs PYTHONPATH.

    Found live 2026-08-07: without it the server started and died with
    "No module named 'tinyassets'". The CLI surfaces that only as
    "Connection closed", and the turn simply sees a tool that is not there — so
    a missing PYTHONPATH is indistinguishable from a policy refusal unless
    someone reads the MCP log.
    """
    import json
    from pathlib import Path as _Path

    import tinyassets

    config = _sandboxed_config(ctx, grant_tools=True)
    payload = json.loads(_Path(config.mcp_config_path).read_text(encoding="utf-8"))
    env = payload["mcpServers"][_ENGINE_TOOL_SERVER]["env"]
    package_root = str(_Path(tinyassets.__file__).resolve().parent.parent)
    assert package_root in env["PYTHONPATH"].split(os.pathsep)


def test_a_granted_turn_is_told_it_has_hands(monkeypatch, tmp_path):
    """Tools it does not know about are tools it does not use.

    Observed live 2026-08-07: the turn discovered the server via ToolSearch and
    made 26 `workspace_read` calls, then wrote nothing — because its prompt still
    described a universe whose files were maintained for it.
    """
    from tinyassets import universe_intelligence as ui
    from tinyassets.api import interlocutor

    captured: dict = {}
    real = ui._build_persona_system_prompt
    monkeypatch.setattr(ui, "_build_persona_system_prompt", lambda *a, **k: "PERSONA")

    def _capture(prompt, *, system="", **kwargs):
        captured.setdefault("systems", []).append(system)
        return "reply"

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    universe = tmp_path / "u-hands"
    universe.mkdir()
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: universe)
    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-hands")
    monkeypatch.setattr(ui, "call_provider", _capture)
    monkeypatch.setattr(ui, "extract_learning", lambda *a, **k: {})
    monkeypatch.setattr(ui, "commit_learning", lambda *a, **k: None)

    ui.converse("u-hands", "hello", tier=interlocutor.FOUNDER)
    assert "workspace_write" in captured["systems"][0]
    assert "not a description of what I AM" in captured["systems"][0]
    assert real is not None  # keep the real builder referenced for clarity


def test_an_ungranted_turn_is_not_told_about_tools(monkeypatch, tmp_path):
    """Describing tools a turn does not hold makes it promise what it cannot do."""
    from tinyassets import universe_intelligence as ui
    from tinyassets.api import interlocutor

    captured: dict = {}
    monkeypatch.setattr(ui, "_build_persona_system_prompt", lambda *a, **k: "PERSONA")

    def _capture(prompt, *, system="", **kwargs):
        captured.setdefault("systems", []).append(system)
        return "reply"

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    universe = tmp_path / "u-nohands"
    universe.mkdir()
    monkeypatch.setattr(ui, "_universe_dir", lambda uid: universe)
    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-nohands")
    monkeypatch.setattr(ui, "call_provider", _capture)

    ui.converse("u-nohands", "hello", tier=interlocutor.T1)
    assert "workspace_write" not in captured["systems"][0]
