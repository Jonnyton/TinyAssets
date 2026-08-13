"""Tests for the founder-scoped engine MCP server + its wiring.

Security-critical: this is the P0 engine-sandbox surface. These lock in the
confinement the 2026-08-13 Codex review required for the read-only slice —
verified-principal identity, hard fail-closed, the graph pin, and the
restricted read_graph target set — so a regression turns a gate red instead of
silently re-opening a cross-universe read.
"""
from __future__ import annotations

import json
import os

from tinyassets.auth.provider import ANONYMOUS

# ── engine_mcp_server: fail-closed + confinement ────────────────────────────

def test_binding_error_fails_closed_without_both_ids(monkeypatch):
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", "")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-x")
    assert s._binding_error() is not None

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "")
    assert s._binding_error() is not None

    monkeypatch.setattr(s, "_GRAPH_ID", "u-x")
    assert s._binding_error() is None


def test_read_graph_refuses_unpinned_targets(monkeypatch):
    """Codex #5: only graph_id-keyed targets are exposed; the rest are refused."""
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-x")
    for bad in ("runs", "run", "branch", "goals", "goal", "agents", "agent_binding"):
        out = json.loads(s.read_graph(target=bad))
        assert "not available" in out.get("error", ""), bad


def test_read_graph_pins_graph_id_and_target(monkeypatch):
    """The pinned graph_id is the ONLY selector passed to the real handler."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    captured: dict = {}
    monkeypatch.setattr(us, "read_graph", lambda **kw: (captured.update(kw), "{}")[1])
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")

    s.read_graph(target="graph")
    assert captured == {"target": "graph", "graph_id": "u-pinned"}


def test_get_status_pins_universe_id(monkeypatch):
    """Codex #9: get_status keys off universe_id, not graph_id — pin the right arg."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    captured: dict = {}
    monkeypatch.setattr(us, "get_status", lambda **kw: (captured.update(kw), "{}")[1])
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")

    s.get_status()
    assert captured == {"universe_id": "u-pinned"}


_FULL_STATUS = {
    "schema_version": 1,
    "universe_id": "u-pinned",
    "universe_exists": True,
    "persona": {"name": "Tiny"},
    "universe_serving": {"provider": "claude-code"},
    # host/global fields that MUST be projected away (Codex ADAPT #3):
    "active_host": {"llm_endpoint_bound": "codex"},
    "storage_utilization": {"root": "C:/secret/path"},
    "release_state": {"git_sha": "abc", "extra": {"oops_secret": "x"}},
    "sandbox_status": {"binary": "/usr/bin/bwrap"},
    "evidence": ["/abs/host/path"],
    "future_unknown_field": {"anything": True},
}


def test_get_status_projects_to_universe_whitelist(monkeypatch):
    """Codex ADAPT #3: host/global fields (incl. receipt `extra` passthrough and
    any FUTURE field) never reach the engine — whitelist projection."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(us, "get_status", lambda **kw: json.dumps(_FULL_STATUS))
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")

    out = json.loads(s.get_status())
    assert set(out) == {
        "schema_version", "universe_id", "universe_exists", "persona",
        "universe_serving",
    }
    assert "active_host" not in out
    assert "release_state" not in out
    assert "future_unknown_field" not in out


def test_read_graph_status_also_projects(monkeypatch):
    """read_graph target=status routes to the same full handler — it must NOT be
    a projection bypass."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(us, "get_status", lambda **kw: json.dumps(_FULL_STATUS))
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")

    out = json.loads(s.read_graph(target="status"))
    assert "active_host" not in out
    assert "storage_utilization" not in out
    assert out["universe_id"] == "u-pinned"


def test_status_projection_refuses_unprojectable(monkeypatch):
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(us, "get_status", lambda **kw: "not-json")
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")
    assert "error" in json.loads(s.get_status())


def test_status_projection_fixed_refusal_on_upstream_error(monkeypatch):
    """Codex residuals #2: an upstream error object gets a FIXED refusal, not an
    empty-but-OK ``{}`` and not the upstream error text (which can carry host
    detail)."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(
        us, "get_status",
        lambda **kw: json.dumps({"error": "boom at C:/host/secret/path"}),
    )
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")
    out = json.loads(s.get_status())
    assert out == {"error": "status unavailable."}
    assert "secret" not in json.dumps(out)


def test_status_projection_whitelists_nested_serving(monkeypatch):
    """Codex residuals #2 (reproduced): universe_serving.detail can embed a host
    path — only the nested whitelist (provider, state) passes."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    full = dict(_FULL_STATUS)
    full["universe_serving"] = {
        "provider": "claude-code",
        "state": "ready",
        "lookup_failed": True,
        "detail": "C:/host/secret/vault/path",
    }
    monkeypatch.setattr(us, "get_status", lambda **kw: json.dumps(full))
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")
    out = json.loads(s.get_status())
    assert out["universe_serving"] == {"provider": "claude-code", "state": "ready"}
    assert "detail" not in json.dumps(out)


def test_inspect_not_found_does_not_enumerate(tmp_path, monkeypatch):
    """Codex ADAPT #2: a missing universe must not enumerate directory names."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    (tmp_path / "u-secret-alpha").mkdir()
    (tmp_path / "u-secret-beta").mkdir()

    from tinyassets.api.universe import _action_inspect_universe

    out = json.loads(_action_inspect_universe(universe_id="u-nope"))
    assert "not found" in out.get("error", "")
    assert "available" not in out
    assert "u-secret-alpha" not in json.dumps(out)


def test_inspect_omitted_id_denial_echoes_no_resolved_name(tmp_path, monkeypatch):
    """Codex residuals #3 (reproduced): when an OMITTED-id inspect resolves to a
    universe that then DENIES metadata, the denial must not echo the name the
    default resolution landed on — the caller never named it."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    # A non-serial directory: exactly what _designated_public_universe / default
    # resolution can land on for a caller with no home.
    (tmp_path / "u-secret-alpha").mkdir()

    from tinyassets.api import visibility
    from tinyassets.api.universe import _action_inspect_universe

    monkeypatch.setattr(visibility, "visibility_permits", lambda *a, **k: False)
    out = json.loads(_action_inspect_universe(universe_id=""))
    assert "error" in out
    assert "u-secret-alpha" not in json.dumps(out)


def test_handlers_refused_when_unbound(monkeypatch):
    """No principal/graph → refuse without ever reaching the real handler."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    calls = {"n": 0}

    def _boom(**kw):
        calls["n"] += 1
        return "{}"

    monkeypatch.setattr(us, "read_graph", _boom)
    monkeypatch.setattr(us, "get_status", _boom)
    monkeypatch.setattr(s, "_ACTOR_ID", "")  # unbound
    monkeypatch.setattr(s, "_GRAPH_ID", "u-x")

    assert "refusing" in json.loads(s.read_graph(target="graph")).get("error", "")
    assert "refusing" in json.loads(s.get_status()).get("error", "")
    assert calls["n"] == 0


def test_bind_founder_identity_uses_verified_principal(monkeypatch):
    """Codex #1/#2: identity is the verified principal with least-privilege reads."""
    from tinyassets import engine_mcp_server as s
    from tinyassets.auth import middleware

    monkeypatch.setattr(s, "_ACTOR_ID", "workos-sub-123")
    token = s._bind_founder_identity()
    try:
        ident = middleware.current_identity()
        assert ident.user_id == "workos-sub-123"
        assert set(ident.capabilities) == {"read", "list"}
        assert "write" not in ident.capabilities
        assert "submit_request" not in ident.capabilities
    finally:
        middleware._current_identity.reset(token)


def test_bind_founder_identity_anonymous_without_actor(monkeypatch):
    from tinyassets import engine_mcp_server as s
    from tinyassets.auth import middleware

    monkeypatch.setattr(s, "_ACTOR_ID", "")
    token = s._bind_founder_identity()
    try:
        assert middleware.current_identity() is ANONYMOUS
    finally:
        middleware._current_identity.reset(token)


# ── universe_intelligence._sandboxed_config: the enable gate ────────────────

def _fake_ctx():
    class _Cfg:
        timeout = 300

    class _Ctx:
        config = _Cfg()

    return _Ctx()


def test_sandboxed_config_engine_mcp_off_by_default(monkeypatch):
    from tinyassets import universe_intelligence as ui

    monkeypatch.setattr(ui, "_engine_mcp_enabled", lambda: False)
    cfg = ui._sandboxed_config(
        _fake_ctx(), founder_principal="sub", universe_id="u", granted=True
    )
    assert cfg.engine_mcp_enabled is False
    assert "mcp__tinyassets__read_graph" not in (cfg.allowed_tools or ())
    assert "mcp__*" in (cfg.disallowed_tools or ())


def test_sandboxed_config_fails_closed_non_founder_or_no_principal(monkeypatch):
    from tinyassets import universe_intelligence as ui

    monkeypatch.setattr(ui, "_engine_mcp_enabled", lambda: True)
    # granted but no verified principal → off
    cfg = ui._sandboxed_config(
        _fake_ctx(), founder_principal="", universe_id="u", granted=True
    )
    assert cfg.engine_mcp_enabled is False
    # principal present but not a founder turn → off
    cfg = ui._sandboxed_config(
        _fake_ctx(), founder_principal="sub", universe_id="u", granted=False
    )
    assert cfg.engine_mcp_enabled is False
    # the default (learning-extractor) call → off
    assert ui._sandboxed_config(_fake_ctx()).engine_mcp_enabled is False


def test_sandboxed_config_on_when_all_conditions_met(monkeypatch):
    from tinyassets import universe_intelligence as ui

    monkeypatch.setattr(ui, "_engine_mcp_enabled", lambda: True)
    cfg = ui._sandboxed_config(
        _fake_ctx(), founder_principal="sub-9", universe_id="u-9", granted=True
    )
    assert cfg.engine_mcp_enabled is True
    assert "mcp__tinyassets__read_graph" in cfg.allowed_tools
    assert "mcp__tinyassets__get_status" in cfg.allowed_tools
    # the wildcard deny is dropped so the tinyassets handles are admittable...
    assert "mcp__*" not in cfg.disallowed_tools
    # ...but the resource readers stay denied (surface = exactly the handles)
    assert "ReadMcpResourceTool" in cfg.disallowed_tools
    assert cfg.engine_mcp_actor_id == "sub-9"
    assert cfg.engine_mcp_graph_id == "u-9"


# ── claude_provider._engine_mcp_flags: the CLI wiring ───────────────────────

def test_engine_mcp_flags_fail_closed_without_ids(tmp_path):
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.claude_provider import _engine_mcp_flags

    cfg = ModelConfig(
        engine_mcp_enabled=True, engine_mcp_actor_id="", engine_mcp_graph_id="u"
    )
    assert _engine_mcp_flags(cfg, tmp_path) == []
    cfg = ModelConfig(
        engine_mcp_enabled=True, engine_mcp_actor_id="sub", engine_mcp_graph_id=""
    )
    assert _engine_mcp_flags(cfg, tmp_path) == []


def test_engine_mcp_flags_emits_strict_config_and_pins(tmp_path):
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.claude_provider import _engine_mcp_flags

    cfg = ModelConfig(
        engine_mcp_enabled=True,
        engine_mcp_actor_id="sub-9",
        engine_mcp_graph_id="u-9",
    )
    flags = _engine_mcp_flags(cfg, tmp_path)
    assert "--strict-mcp-config" in flags
    assert "--mcp-config" in flags

    data = json.loads((tmp_path / ".engine_mcp_config.json").read_text())
    srv = data["mcpServers"]["tinyassets"]
    assert srv["args"] == ["-m", "tinyassets.engine_mcp_server"]
    assert srv["env"]["TINYASSETS_ENGINE_ACTOR_ID"] == "sub-9"
    assert srv["env"]["TINYASSETS_ENGINE_GRAPH_ID"] == "u-9"


def test_engine_mcp_flags_propagates_package_root_on_pythonpath(tmp_path):
    """The stdio child runs from the universe dir — it can only import
    `tinyassets` if the daemon's package root is propagated (reproduced live:
    every tool call failed 'No module named tinyassets' without this)."""
    from pathlib import Path

    import tinyassets
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.claude_provider import _engine_mcp_flags

    cfg = ModelConfig(
        engine_mcp_enabled=True,
        engine_mcp_actor_id="sub-9",
        engine_mcp_graph_id="u-9",
    )
    _engine_mcp_flags(cfg, tmp_path)
    data = json.loads((tmp_path / ".engine_mcp_config.json").read_text())
    pythonpath = data["mcpServers"]["tinyassets"]["env"]["PYTHONPATH"]
    pkg_root = str(Path(tinyassets.__file__).resolve().parent.parent)
    assert pythonpath.split(os.pathsep)[0] == pkg_root


def test_sandbox_cli_args_fails_closed_when_strict_not_installed(monkeypatch, tmp_path):
    """Codex ADAPT #1: engine MCP requested but strict-config not installed (e.g.
    the config write failed) must FAIL the turn, not run with a relaxed policy
    that fails open to ambient connectors."""
    import pytest

    from tinyassets.exceptions import ProviderError
    from tinyassets.providers import claude_provider as cp
    from tinyassets.providers.base import ModelConfig

    monkeypatch.setattr(cp, "_engine_mcp_flags", lambda c, d: [])  # write failed
    cfg = ModelConfig(
        sandbox_workspace=True,
        engine_mcp_enabled=True,
        engine_mcp_actor_id="sub",
        engine_mcp_graph_id="u",
        allowed_tools=("WebFetch", "mcp__tinyassets__read_graph"),
        disallowed_tools=("Bash",),  # mcp__* already dropped by the caller
    )
    with pytest.raises(ProviderError):
        cp._sandbox_cli_args(cfg, tmp_path)


def test_sandbox_cli_args_includes_strict_when_installed(monkeypatch, tmp_path):
    from tinyassets.providers import claude_provider as cp
    from tinyassets.providers.base import ModelConfig

    monkeypatch.setattr(
        cp, "_engine_mcp_flags",
        lambda c, d: ["--mcp-config", "x", "--strict-mcp-config"],
    )
    cfg = ModelConfig(
        sandbox_workspace=True,
        engine_mcp_enabled=True,
        engine_mcp_actor_id="sub",
        engine_mcp_graph_id="u",
    )
    flags, _cwd = cp._sandbox_cli_args(cfg, tmp_path)
    assert "--strict-mcp-config" in flags
