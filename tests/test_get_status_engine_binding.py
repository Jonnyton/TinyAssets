"""S5 — get_status engine-binding onboarding surface + subscription bind path.

get_status honestly reports whether a universe has engine/daemon capacity bound
to it and, when it does not, surfaces the "bind an engine so your universe can
run" next step (design note 2026-07-15 gap G7). The bind surface itself
(``universe action=set_engine``) gains a ``subscription`` engine_source so the
onboarding menu is complete (subscription CLI / BYO API key / local / offered
cloud / hosted daemon).
"""
from __future__ import annotations

import base64
import json

from tinyassets.config import load_universe_config
from tinyassets.credential_vault import resolve_claude_oauth_token, write_credential_vault
from tinyassets.engine_binding import NON_AMBIENT_WORK_ENV
from tinyassets.universe_server import get_status


def _make_universe(tmp_path, monkeypatch, uid):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / uid
    udir.mkdir(parents=True, exist_ok=True)
    return udir


# ---- get_status: idle-until-bound honesty ---------------------------------


def test_status_reports_unbound_universe_idle_until_bound(tmp_path, monkeypatch):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    _make_universe(tmp_path, monkeypatch, "u-idle")
    payload = json.loads(get_status(universe_id="u-idle"))

    eb = payload["engine_binding"]
    assert eb["bound"] is False
    # Flag OFF (default): ambient work still runs today, so workable stays True.
    assert eb["workable"] is True
    assert eb["non_ambient_gate"] is False
    # The founder is offered the bind next step.
    steps = " ".join(payload["actionable_next_steps"]).lower()
    assert "bind an engine" in steps
    assert "set_engine" in steps
    # Finding 2 regression: with the gate OFF the caveat must NOT falsely claim
    # the universe is idle-until-bound (it IS being worked via ambient legacy
    # execution today). It should say so honestly.
    combined = " ".join(payload["caveats"]).lower()
    assert "idle-until-bound" not in combined
    assert "ambient" in combined and "workable" in combined


def test_status_unbound_with_gate_on_is_not_workable(tmp_path, monkeypatch):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    _make_universe(tmp_path, monkeypatch, "u-idle2")
    payload = json.loads(get_status(universe_id="u-idle2"))

    eb = payload["engine_binding"]
    assert eb["bound"] is False
    assert eb["non_ambient_gate"] is True
    # Gate on → an unbound universe is genuinely idle-until-bound.
    assert eb["workable"] is False
    assert "idle" in eb["note"].lower()


def test_status_reports_bound_universe(tmp_path, monkeypatch):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = _make_universe(tmp_path, monkeypatch, "u-bound")
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-test").decode("ascii"),
    }])
    from tinyassets.config import write_universe_config_fields
    write_universe_config_fields(udir, engine_source="byo_api_key")

    payload = json.loads(get_status(universe_id="u-bound"))
    eb = payload["engine_binding"]
    assert eb["bound"] is True
    assert "byo_api_key" in eb["capacity_kinds"]
    # A bound universe does not nag with the bind next step.
    steps = " ".join(payload["actionable_next_steps"]).lower()
    assert "bind an engine so your universe can run" not in steps


def test_status_reports_misconfigured_binding_without_crashing(tmp_path, monkeypatch):
    """A declared-but-broken binding is reported (not raised) by get_status."""
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = _make_universe(tmp_path, monkeypatch, "u-broken")
    from tinyassets.config import write_universe_config_fields
    # Declared byo_api_key (vault source) with NO vault key = genuinely broken.
    write_universe_config_fields(udir, engine_source="byo_api_key")

    payload = json.loads(get_status(universe_id="u-broken"))
    eb = payload["engine_binding"]
    assert eb["bound"] is False
    assert eb.get("misconfigured") is True
    combined = " ".join(payload["caveats"]).lower()
    assert "misconfigured" in combined


def test_engine_binding_is_in_status_contract(tmp_path, monkeypatch):
    _make_universe(tmp_path, monkeypatch, "u-contract")
    payload = json.loads(get_status(universe_id="u-contract"))
    assert "engine_binding" in payload
    assert isinstance(payload["engine_binding"], dict)


# ---- set_engine subscription bind path ------------------------------------


def _setup_set_engine(tmp_path, monkeypatch, uid):
    from tinyassets.api import universe as uni

    udir = tmp_path / uid
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": uid)
    monkeypatch.setattr(uni, "_universe_dir", lambda _uid: udir)
    return uni, udir


def test_set_engine_subscription_claude_deposits_and_binds(tmp_path, monkeypatch):
    uni, udir = _setup_set_engine(tmp_path, monkeypatch, "u-sub-claude")
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "subscription",
        "service": "claude",
        "oauth_token": "oauth-SECRET-abc",
    })))
    assert out["status"] == "engine_set"
    assert out["engine_source"] == "subscription"
    assert out["preferred_writer"] == "claude-code"
    # The token is NEVER echoed back.
    assert "oauth-SECRET-abc" not in json.dumps(out)
    # It resolves end-to-end from the vault, and the resolver reads it as bound.
    assert resolve_claude_oauth_token(udir) == "oauth-SECRET-abc"
    assert load_universe_config(udir).engine_source == "subscription"
    from tinyassets.engine_binding import resolve_engine_binding
    assert resolve_engine_binding(udir).bound is True


def test_set_engine_subscription_requires_auth_material(tmp_path, monkeypatch):
    uni, _udir = _setup_set_engine(tmp_path, monkeypatch, "u-sub-empty")
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "subscription", "service": "claude",
    })))
    assert "error" in out  # no oauth_token → refused, never a phantom binding


def test_set_engine_subscription_preserves_other_credentials(tmp_path, monkeypatch):
    """Binding a subscription must not clobber a previously bound github token."""
    uni, udir = _setup_set_engine(tmp_path, monkeypatch, "u-sub-merge")
    write_credential_vault(udir, [{
        "credential_type": "vcs",
        "service": "github",
        "destination": "owner/repo",
        "token": "ghp-existing",
    }])
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "subscription", "service": "codex",
        "auth_json_b64": base64.b64encode(b"{}").decode("ascii"),
    })))
    assert out["status"] == "engine_set"
    from tinyassets.credential_vault import load_credential_vault
    types = {r.get("credential_type") for r in load_credential_vault(udir)}
    assert "vcs" in types  # github token preserved
    assert "llm_subscription" in types
