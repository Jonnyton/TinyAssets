"""Tests for the founder-scoped engine MCP server + its wiring.

Security-critical: this is the P0 engine-sandbox surface. These lock in the
confinement the 2026-08-13 Codex review required for the read-only slice —
verified-principal identity, hard fail-closed, the graph pin, and the
restricted read_graph target set — so a regression turns a gate red instead of
silently re-opening a cross-universe read.
"""
from __future__ import annotations

import json

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


# ── engine_mcp_server: shared commons (browse / read / remix) ───────────────

def _bind_ids(monkeypatch, actor="sub-1", graph="u-x"):
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    return s


def test_browse_commons_fails_closed_when_unbound(monkeypatch):
    s = _bind_ids(monkeypatch, actor="")  # no principal
    assert "refusing" in json.loads(s.browse_commons()).get("error", "")


def test_browse_commons_rejects_unknown_kind(monkeypatch):
    s = _bind_ids(monkeypatch)
    out = json.loads(s.browse_commons(kind="nodes"))
    assert "not available" in out.get("error", "")


def test_browse_commons_branches_lists_published_with_read_caps(monkeypatch):
    """branches → list_branches scope=published, viewer = bound founder, read-only caps."""
    import tinyassets.api.extensions as ext
    from tinyassets import engine_mcp_server as s
    from tinyassets.auth import middleware

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-9")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-9")
    captured: dict = {}

    def _fake(**kw):
        ident = middleware.current_identity()
        captured["kw"] = kw
        captured["user_id"] = ident.user_id
        captured["caps"] = set(ident.capabilities)
        return "{}"

    monkeypatch.setattr(ext, "_extensions_impl", _fake)
    s.browse_commons(kind="branches", author="someone")
    assert captured["kw"]["action"] == "list_branches"
    assert captured["kw"]["scope"] == "published"
    assert captured["kw"]["author"] == "someone"
    assert captured["user_id"] == "sub-9"  # viewer = founder
    assert captured["caps"] == {"read", "list"}  # least privilege


def test_browse_commons_agents_delegates_to_read_graph(monkeypatch):
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    _bind_ids(monkeypatch)
    captured: dict = {}
    monkeypatch.setattr(us, "read_graph", lambda **kw: (captured.update(kw), "{}")[1])
    s.browse_commons(kind="agents", query="triage", limit=5)
    assert captured["target"] == "agents"
    assert captured["query"] == "triage"
    assert captured["limit"] == 5


def test_read_commons_shape_reads_any_public_branch_by_id(monkeypatch):
    """NOT graph-pinned: the caller-supplied branch_id passes through; the
    canonical get_branch author-gates a private non-authored shape."""
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s
    from tinyassets.auth import middleware

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-9")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-9")
    captured: dict = {}

    def _fake(**kw):
        captured["kw"] = kw
        captured["caps"] = set(middleware.current_identity().capabilities)
        return "{}"

    monkeypatch.setattr(us, "read_graph", _fake)
    s.read_commons_shape(branch_id="other-universe-branch")
    assert captured["kw"] == {"target": "branch", "branch_id": "other-universe-branch"}
    assert captured["caps"] == {"read", "list"}  # read-only


def test_read_commons_shape_requires_exactly_one_id(monkeypatch):
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    _bind_ids(monkeypatch)
    calls = {"n": 0}
    monkeypatch.setattr(us, "read_graph", lambda **kw: (calls.update(n=1), "{}")[1])
    # neither -> error
    assert "exactly one" in json.loads(s.read_commons_shape()).get("error", "")
    # both -> error (Codex #7: must not silently pick branch_id)
    assert "exactly one" in json.loads(
        s.read_commons_shape(branch_id="b", agent_definition_id="a")
    ).get("error", "")
    assert calls["n"] == 0  # never reached the read


def test_remix_shape_requires_fork_from_and_name(monkeypatch):
    import tinyassets.engine_mcp_http as http
    from tinyassets import engine_mcp_server as s

    _bind_ids(monkeypatch, graph="u-ok")
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({"u-ok"}))
    assert "fork_from" in json.loads(s.remix_shape(name="x")).get("error", "")
    assert "name is required" in json.loads(
        s.remix_shape(fork_from="v-1")
    ).get("error", "")


def test_remix_shape_refused_off_allowlist(monkeypatch):
    """remix is a WRITE — refuse unless this universe is on the run_graph allowlist."""
    import tinyassets.engine_mcp_http as http
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    _bind_ids(monkeypatch, graph="u-not-listed")
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({"u-other"}))
    calls = {"n": 0}
    monkeypatch.setattr(us, "write_graph", lambda **kw: (calls.update(n=1), "{}")[1])
    out = json.loads(s.remix_shape(fork_from="v-1", name="mine"))
    assert "not enabled for this universe" in out.get("error", "")
    assert calls["n"] == 0  # never reached the write


def test_remix_shape_forks_private_with_minimal_caps(monkeypatch):
    import tinyassets.engine_mcp_http as http
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s
    from tinyassets.auth import middleware

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-9")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-9")
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({"u-9"}))
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: True)
    captured: dict = {}

    def _fake(**kw):
        captured["kw"] = kw
        captured["caps"] = set(middleware.current_identity().capabilities)
        return "{}"

    monkeypatch.setattr(us, "write_graph", _fake)
    s.remix_shape(fork_from="v-parent", name="my remix", description="tweaked")
    assert captured["kw"]["target"] == "branch"
    assert captured["kw"]["operation"] == "remix"
    spec = json.loads(captured["kw"]["payload_json"])
    assert spec["fork_from"] == "v-parent"
    assert spec["name"] == "my remix"
    assert spec["visibility"] == "private"  # private by default
    assert spec["description"] == "tweaked"
    # least-privilege branch-write caps (Codex #6): NOT submit_request.
    assert {"read", "list", "write", "costly"} == captured["caps"]
    assert "submit_request" not in captured["caps"]


def test_remix_shape_admission_fails_closed(monkeypatch):
    """remix passes fail_closed=True so a DB blip refuses rather than admits."""
    import tinyassets.engine_mcp_http as http
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    _bind_ids(monkeypatch, graph="u-9")
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({"u-9"}))
    seen = {}
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: seen.update(kw) or False)
    calls = {"n": 0}
    monkeypatch.setattr(us, "write_graph", lambda **kw: (calls.update(n=1), "{}")[1])
    out = json.loads(s.remix_shape(fork_from="v-1", name="mine"))
    assert seen.get("fail_closed") is True
    assert "rate limit" in out.get("error", "")
    assert calls["n"] == 0


def test_remix_shape_rate_limited(monkeypatch):
    import tinyassets.engine_mcp_http as http
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    _bind_ids(monkeypatch, graph="u-9")
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({"u-9"}))
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: False)  # over the cap
    calls = {"n": 0}
    monkeypatch.setattr(us, "write_graph", lambda **kw: (calls.update(n=1), "{}")[1])
    out = json.loads(s.remix_shape(fork_from="v-1", name="mine"))
    assert "rate limit" in out.get("error", "")
    assert calls["n"] == 0


def test_publish_shape_is_not_exposed_this_slice(monkeypatch):
    """PUBLISH is deferred to the consent-gated slice (Codex ADAPT #5) — the
    engine server must not expose it, and it is absent from the allowlist."""
    from tinyassets import engine_mcp_server as s
    from tinyassets import universe_intelligence as ui

    assert not hasattr(s, "publish_shape")
    assert "publish_shape" not in ui._ENGINE_MCP_TOOLS


def test_run_graph_refuses_foreign_private_branch(monkeypatch):
    """Codex ADAPT #1: a foreign-private branch id must be refused before the run
    path loads it — indistinguishable from missing."""
    import tinyassets.api.branches as branches
    import tinyassets.engine_mcp_http as http
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    _bind_ids(monkeypatch, graph="u-9")
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({"u-9"}))
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: True)
    # not readable by the founder -> None (foreign-private or missing)
    monkeypatch.setattr(branches, "_resolve_readable_branch", lambda *a, **k: None)
    calls = {"n": 0}
    monkeypatch.setattr(us, "run_graph", lambda **kw: (calls.update(n=1), "{}")[1])
    out = json.loads(s.run_graph(branch_def_id="foreign-private"))
    assert "not found" in out.get("error", "")
    assert calls["n"] == 0  # the run path was never reached


# ── engine_mcp_server: governed brain read-write loop ───────────────────────

def _seed_brain_universe(monkeypatch, tmp_path, uid="u-brain"):
    """Seed a real OKF bundle and point the engine + resolver at it."""
    import tinyassets.api.helpers as helpers
    from tinyassets import engine_mcp_server as s
    from tinyassets.universe_bundle import seed_okf_bundle

    monkeypatch.setattr(helpers, "_base_path", lambda: tmp_path)
    # _engine_run_admit keys its rolling-limit ledger off TINYASSETS_DATA_DIR
    # (not _base_path), so isolate it per test or the shared ledger exhausts the
    # 20/window cap across the suite and later writes are spuriously rate-limited.
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / uid
    seed_okf_bundle(udir, purpose="help the founder", loop_branch_def_id="")
    monkeypatch.setattr(s, "_ACTOR_ID", "sub-brain")
    monkeypatch.setattr(s, "_GRAPH_ID", uid)
    import tinyassets.engine_mcp_http as http
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({uid}))
    return udir


def test_read_brain_returns_editable_sections(monkeypatch, tmp_path):
    from tinyassets import engine_mcp_server as s

    _seed_brain_universe(monkeypatch, tmp_path)
    out = json.loads(s.read_brain())
    assert set(out["brain"]) == {"identity", "founder", "origin", "body"}
    # identity/founder/origin/body are governed-editable by the seeded policy
    assert set(out["editable_sections"]) == {"identity", "founder", "origin", "body"}
    assert "self_model" in out


def test_write_brain_then_next_system_prompt_reflects_it(monkeypatch, tmp_path):
    """THE loop: a write_brain edit lands in the files the NEXT turn's system
    prompt is rebuilt from."""
    from tinyassets import engine_mcp_server as s
    from tinyassets.universe_intelligence import _build_persona_system_prompt

    udir = _seed_brain_universe(monkeypatch, tmp_path)
    marker = "I am Aria, a research companion who tracks the founder's reading list."
    res = json.loads(s.write_brain(identity=marker, name="Aria"))
    assert res.get("ok") is True

    # Next turn: the system prompt is rebuilt from the universe's brain files.
    # T2 = the founder disclosure tier (full grounding).
    prompt = _build_persona_system_prompt(udir, universe_id="u-brain", tier="T2")
    assert "Aria" in prompt
    assert "research companion" in prompt


def test_brain_read_write_round_trip_does_not_nest_frontmatter(monkeypatch, tmp_path):
    """read_brain returns the clean body, so write -> read -> write-back is stable
    and never nests managed frontmatter (Codex brain-loop review)."""
    from tinyassets import engine_mcp_server as s

    _seed_brain_universe(monkeypatch, tmp_path)
    marker = "I am Aria, the founder's research companion."
    s.write_brain(identity=marker)
    body1 = json.loads(s.read_brain())["brain"]["identity"]
    assert marker in body1
    assert "---" not in body1  # no frontmatter leaked into the body
    # Echo the read body back; it must not accumulate frontmatter.
    s.write_brain(identity=body1)
    body2 = json.loads(s.read_brain())["brain"]["identity"]
    assert body2 == body1


def test_write_brain_cannot_touch_soul_md(monkeypatch, tmp_path):
    """soul.md (its frontmatter carries the executable loop_branch_def_id) is not
    an accepted section and is never written by write_brain."""
    from tinyassets import engine_mcp_server as s

    udir = _seed_brain_universe(monkeypatch, tmp_path)
    before = (udir / "soul.md").read_text(encoding="utf-8")
    s.write_brain(identity="I am Aria, the founder's research companion.")
    after = (udir / "soul.md").read_text(encoding="utf-8")
    assert before == after  # soul.md untouched
    # and there is no soul/harness-code parameter on the tool
    import inspect
    params = set(inspect.signature(getattr(s.write_brain, "fn", s.write_brain)).parameters)
    assert "soul" not in params and "source_code" not in params


def test_write_brain_refuses_hardlinked_governed_file(monkeypatch, tmp_path):
    """Codex brain-loop review: if identity.md is a hardlink aliasing soul.md,
    write_brain must NOT mutate soul.md's (executable) frontmatter through it."""
    import os

    from tinyassets import engine_mcp_server as s

    udir = _seed_brain_universe(monkeypatch, tmp_path)
    identity = udir / "identity.md"
    soul = udir / "soul.md"
    soul_before = soul.read_text(encoding="utf-8")
    # Plant the alias: identity.md becomes a hardlink to soul.md (same inode).
    identity.unlink()
    os.link(soul, identity)

    out = json.loads(s.write_brain(identity="I am Aria, the research companion."))
    assert out.get("error")  # refused, not ok
    assert soul.read_text(encoding="utf-8") == soul_before  # soul.md untouched


def test_write_brain_snapshot_sink_cannot_alias_soul(monkeypatch, tmp_path):
    """Codex re-review BLOCKER: the SECONDARY soul-edit sinks (log/snapshot/index)
    must not write through a hardlink either. Atomic writes repoint the name to a
    fresh inode, so a soul_versions/index.md hardlinked to soul.md cannot overwrite
    it during the snapshot."""
    import os

    from tinyassets import engine_mcp_server as s

    udir = _seed_brain_universe(monkeypatch, tmp_path)
    soul = udir / "soul.md"
    soul_before = soul.read_text(encoding="utf-8")
    index = udir / "soul_versions" / "index.md"
    index.parent.mkdir(parents=True, exist_ok=True)
    if index.exists():
        index.unlink()
    os.link(soul, index)  # predictable-name sink aliased to soul.md

    s.write_brain(identity="I am Aria, the founder's research companion.")
    assert soul.read_text(encoding="utf-8") == soul_before  # soul.md untouched


def test_write_brain_rejects_oversized_name(monkeypatch, tmp_path):
    from tinyassets import engine_mcp_server as s

    _seed_brain_universe(monkeypatch, tmp_path)
    out = json.loads(s.write_brain(name="x" * (s._BRAIN_MAX_NAME_BYTES + 1)))
    assert "name is too long" in out.get("error", "")


def test_write_brain_refused_off_allowlist(monkeypatch, tmp_path):
    import tinyassets.engine_mcp_http as http
    from tinyassets import engine_mcp_server as s

    _seed_brain_universe(monkeypatch, tmp_path)
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset({"u-other"}))
    out = json.loads(s.write_brain(identity="x is a specific grounded fact here"))
    assert "not enabled for this universe" in out.get("error", "")


def test_write_brain_requires_something_to_write(monkeypatch, tmp_path):
    from tinyassets import engine_mcp_server as s

    _seed_brain_universe(monkeypatch, tmp_path)
    assert "nothing to write" in json.loads(s.write_brain()).get("error", "")


def test_write_brain_rejects_oversized_section(monkeypatch, tmp_path):
    """A brain section is system-prompt material, so an unbounded body is refused
    (Codex brain-loop review)."""
    from tinyassets import engine_mcp_server as s

    _seed_brain_universe(monkeypatch, tmp_path)
    huge = "x" * (s._BRAIN_MAX_SECTION_BYTES + 1)
    out = json.loads(s.write_brain(identity=huge))
    assert "too large" in out.get("error", "")


def test_write_brain_admission_fails_closed(monkeypatch, tmp_path):
    from tinyassets import engine_mcp_server as s

    _seed_brain_universe(monkeypatch, tmp_path)
    seen = {}
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: seen.update(kw) or False)
    out = json.loads(s.write_brain(name="Aria"))
    assert seen.get("fail_closed") is True
    assert "rate limit" in out.get("error", "")


def test_read_brain_fails_closed_unbound(monkeypatch):
    s = _bind_ids(monkeypatch, actor="")
    assert "refusing" in json.loads(s.read_brain()).get("error", "")


def test_write_brain_uses_least_privilege_caps(monkeypatch, tmp_path):
    """The brain write binds read/list/write only — no costly/submit (Codex #5)."""
    import tinyassets.universe_intelligence as ui
    from tinyassets import engine_mcp_server as s
    from tinyassets.auth import middleware

    _seed_brain_universe(monkeypatch, tmp_path)
    caps = {}
    monkeypatch.setattr(
        ui, "commit_learning",
        lambda udir, proposed, **kw: (
            caps.update(c=set(middleware.current_identity().capabilities)),
            {"updated_files": ["identity.md"]},
        )[1],
    )
    s.write_brain(identity="I am Aria, the founder's research companion.")
    assert caps["c"] == {"read", "list", "write"}
    assert "costly" not in caps["c"] and "submit_request" not in caps["c"]


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
    # read-only commons + brain handles are admitted; remix + publish are held
    # off every served allowlist pending the closure-sanitize / consent gate.
    for _h in (
        "browse_commons", "read_commons_shape",
        "read_brain", "write_brain",
    ):
        assert f"mcp__tinyassets__{_h}" in cfg.allowed_tools, _h
    assert "mcp__tinyassets__publish_shape" not in cfg.allowed_tools
    assert "mcp__tinyassets__remix_shape" not in cfg.allowed_tools
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


# ── codex_provider._codex_engine_mcp_args: the codex CLI wiring ──────────────

_UNTRUSTED = ["-c", 'projects."/workspace".trust_level="untrusted"']


def test_codex_engine_mcp_args_off_adds_only_untrusted_workspace(tmp_path):
    """Engine MCP off: no server, but /workspace is still forced untrusted so no
    project .codex/config.toml (or its mcp_servers) loads (Codex #3)."""
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.codex_provider import _codex_engine_mcp_args

    env: dict = {}
    cfg = ModelConfig(engine_mcp_enabled=False)
    assert _codex_engine_mcp_args(cfg, env) == _UNTRUSTED
    assert "TINYASSETS_ENGINE_MCP_BEARER" not in env


def test_codex_engine_mcp_args_fail_closed_without_route(tmp_path):
    """Engine MCP requested but no running HTTP server -> no server, no bearer."""
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.codex_provider import _codex_engine_mcp_args

    env = {"TINYASSETS_DATA_DIR": str(tmp_path)}  # no routes file present
    cfg = ModelConfig(
        engine_mcp_enabled=True, engine_mcp_actor_id="sub", engine_mcp_graph_id="u-9"
    )
    assert _codex_engine_mcp_args(cfg, env) == _UNTRUSTED
    assert "TINYASSETS_ENGINE_MCP_BEARER" not in env


def test_codex_engine_mcp_args_wires_trusted_http_server(tmp_path):
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.codex_provider import (
        _ENGINE_MCP_ENABLED_TOOLS,
        _codex_engine_mcp_args,
    )

    (tmp_path / ".engine_mcp_http_routes.json").write_text(
        json.dumps({"u-9": {"url": "http://127.0.0.1:8790/mcp", "secret": "s3cr3t"}}),
        encoding="utf-8",
    )
    env = {"TINYASSETS_DATA_DIR": str(tmp_path)}
    cfg = ModelConfig(
        engine_mcp_enabled=True, engine_mcp_actor_id="sub", engine_mcp_graph_id="u-9"
    )
    args = _codex_engine_mcp_args(cfg, env)
    # /workspace untrusted comes first, then the one trusted server.
    assert args[:2] == _UNTRUSTED
    assert args[2] == "-c"
    server = args[3]
    assert server.startswith("mcp_servers.tinyassets={")  # dotted merge
    assert 'url="http://127.0.0.1:8790/mcp"' in server
    assert 'bearer_token_env_var="TINYASSETS_ENGINE_MCP_BEARER"' in server
    assert "required=true" in server
    # restricted to exactly the declared tools; publish is NOT among them
    for _t in _ENGINE_MCP_ENABLED_TOOLS:
        assert f'"{_t}"' in server
    assert "publish_shape" not in server
    # secret goes in the subprocess env (read via bearer_token_env_var), NOT argv
    assert env["TINYASSETS_ENGINE_MCP_BEARER"] == "s3cr3t"
    assert "s3cr3t" not in server


def test_codex_engine_mcp_args_fail_closed_missing_secret(tmp_path):
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.codex_provider import _codex_engine_mcp_args

    (tmp_path / ".engine_mcp_http_routes.json").write_text(
        json.dumps({"u-9": {"url": "http://127.0.0.1:8790/mcp", "secret": ""}}),
        encoding="utf-8",
    )
    env = {"TINYASSETS_DATA_DIR": str(tmp_path)}
    cfg = ModelConfig(
        engine_mcp_enabled=True, engine_mcp_actor_id="sub", engine_mcp_graph_id="u-9"
    )
    assert _codex_engine_mcp_args(cfg, env) == _UNTRUSTED
    assert "TINYASSETS_ENGINE_MCP_BEARER" not in env
