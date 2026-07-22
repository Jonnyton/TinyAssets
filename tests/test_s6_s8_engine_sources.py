"""S6/S7/S8 — engine-source onboard choices + the market-offer supply side.

set_engine carries engine_source (byo_api_key | self_hosted_endpoint |
market_rented | host_daemon), all persisted to config.yaml; offer_engine records
the founder's market supply offers.
"""
from __future__ import annotations

import json

from tinyassets.config import load_universe_config


def _setup(tmp_path, monkeypatch):
    from tinyassets.api import universe as uni

    udir = tmp_path / "u-eng"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-eng")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)
    return uni, udir


def test_byo_api_key_still_works_and_records_source(tmp_path, monkeypatch):
    uni, udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(
        inputs_json=json.dumps({"service": "anthropic", "api_key": "sk-x"})))
    assert out["engine_source"] == "byo_api_key"  # default source
    assert load_universe_config(udir).engine_source == "byo_api_key"


def test_self_hosted_endpoint_persists(tmp_path, monkeypatch):
    uni, udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "self_hosted_endpoint",
        "endpoint": "http://localhost:11434",
        "preferred_writer": "ollama-local"})))
    assert out["engine_source"] == "self_hosted_endpoint"
    cfg = load_universe_config(udir)
    assert cfg.engine_source == "self_hosted_endpoint"
    assert cfg.engine_endpoint == "http://localhost:11434"
    assert cfg.allowed_providers == ["ollama-local"]
    assert out["allowed_providers"] == ["ollama-local"]


def test_market_rented_persists_rate_and_cap(tmp_path, monkeypatch):
    uni, udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "market_rented", "market_model": "glm-5.2",
        "market_rate": 0.5, "spending_cap": 20.0})))
    assert out["engine_source"] == "market_rented"
    cfg = load_universe_config(udir)
    assert cfg.market_model == "glm-5.2"
    assert cfg.market_rate == 0.5
    assert cfg.spending_cap == 20.0
    assert cfg.allowed_providers == []
    assert out["allowed_providers"] == []


def test_host_daemon_persists_and_points_at_summon(tmp_path, monkeypatch):
    uni, udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "host_daemon", "provider": "codex"})))
    assert out["engine_source"] == "host_daemon"
    assert "daemon_summon" in out["next_step"]
    cfg = load_universe_config(udir)
    assert cfg.engine_source == "host_daemon"
    assert cfg.preferred_writer == "codex"
    assert cfg.allowed_providers == []
    assert out["allowed_providers"] == []
    assert out["credential_binding_status"] == "pending"


def test_unknown_engine_source_errors(tmp_path, monkeypatch):
    uni, _udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(
        inputs_json=json.dumps({"engine_source": "telepathy"})))
    assert "error" in out


def test_market_required_fields_enforced(tmp_path, monkeypatch):
    uni, _udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(
        inputs_json=json.dumps({"engine_source": "market_rented"})))
    assert "error" in out  # market_model required


def test_offer_engine_set_list_toggle(tmp_path, monkeypatch):
    from tinyassets.api import permissions
    from tinyassets.api import universe as uni

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "founder-42")

    setres = json.loads(uni._action_offer_engine(inputs_json=json.dumps({
        "action": "set", "service": "anthropic", "model": "sonnet",
        "rate": 0.3, "cap": 100.0})))
    assert setres["status"] == "offer_set"
    key = setres["offer_key"]

    listed = json.loads(uni._action_offer_engine(
        inputs_json=json.dumps({"action": "list"})))
    match = [o for o in listed["offers"] if o["key"] == key]
    assert match and match[0]["enabled"] is True

    toggled = json.loads(uni._action_offer_engine(
        inputs_json=json.dumps({"action": "toggle", "key": key})))
    assert toggled["status"] == "offer_toggled"
    listed2 = json.loads(uni._action_offer_engine(
        inputs_json=json.dumps({"action": "list"})))
    assert [o for o in listed2["offers"] if o["key"] == key][0]["enabled"] is False


def test_engine_actions_are_founder_admin_scoped():
    from tinyassets.api.universe import UNIVERSE_ACTIONS, WRITE_ACTIONS
    from tinyassets.auth.provider import _UNIVERSE_ADMIN_ACTIONS

    for action in ("set_engine", "offer_engine"):
        assert action in _UNIVERSE_ADMIN_ACTIONS
        assert action in WRITE_ACTIONS
        assert action in UNIVERSE_ACTIONS
