"""S6/S7/S8 — engine-source onboard choices + the market-offer supply side.

set_engine carries engine_source (byo_api_key | self_hosted_endpoint |
market_rented | host_daemon), all persisted to config.yaml; offer_engine records
the founder's market supply offers.
"""
from __future__ import annotations

import json

import pytest

from tinyassets.config import load_universe_config


def _setup(tmp_path, monkeypatch):
    from tinyassets.api import universe as uni

    udir = tmp_path / "u-eng"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-eng")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)
    return uni, udir


def test_byo_api_key_raw_deposit_refused_through_chat(tmp_path, monkeypatch):
    # C3: a raw BYO key can never be deposited through the chatbot — refused.
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    uni, udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps(
        {"service": "anthropic", "api_key": "sk-ant-api03-" + "A" * 40})))
    assert "error" in out and out.get("status") != "engine_set"
    from tinyassets.credential_vault import load_credential_vault
    assert load_credential_vault(udir) == []


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


def test_host_daemon_declares_not_executable(tmp_path, monkeypatch):
    """#4: host_daemon is a DECLARATION — executable:false, no daemon_summon
    instruction (the platform does not run it; own-device is the path)."""
    uni, udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "host_daemon", "provider": "codex"})))
    assert out["engine_source"] == "host_daemon"
    assert out["status"] == "engine_declared" and out["executable"] is False
    assert "daemon_summon" not in json.dumps(out)
    assert load_universe_config(udir).engine_source == "host_daemon"


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


@pytest.mark.parametrize("field,value", [
    ("rate", -1.0), ("cap", -0.5),
    ("rate", float("inf")), ("cap", float("nan")),
])
def test_r15_3_offer_engine_rejects_invalid_financials(
    tmp_path, monkeypatch, field, value,
):
    """Round-15 #3: offer_engine must reject non-finite (NaN/Infinity) + negative
    rate/cap (the same guard the market-rental declaration applies) — never persist
    them."""
    from tinyassets.api import permissions
    from tinyassets.api import universe as uni

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "founder-fin")
    payload = {"action": "set", "service": "anthropic", "model": "m",
               "rate": 0.5, "cap": 5.0}
    payload[field] = value
    out = json.loads(uni._action_offer_engine(inputs_json=json.dumps(payload)))
    assert "error" in out and out.get("status") != "offer_set"
    # Nothing persisted.
    listed = json.loads(uni._action_offer_engine(
        inputs_json=json.dumps({"action": "list"})))
    assert listed["offers"] == []


def test_r15_3_concurrent_offers_do_not_lose_each_other(tmp_path, monkeypatch):
    """Round-15 #3: the offer read-modify-write runs under a cross-process lock —
    interleaved offers for distinct keys all land (no lost-update clobber)."""
    import concurrent.futures

    from tinyassets.api import permissions
    from tinyassets.api import universe as uni

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "founder-conc")

    def _set(i):
        uni._action_offer_engine(inputs_json=json.dumps({
            "action": "set", "service": "anthropic", "model": f"m{i}",
            "rate": 0.1, "cap": 1.0}))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_set, range(16)))

    listed = json.loads(uni._action_offer_engine(
        inputs_json=json.dumps({"action": "list"})))
    keys = {o["key"] for o in listed["offers"]}
    for i in range(16):
        assert f"anthropic:m{i}" in keys, f"lost offer m{i} under concurrency"


def test_engine_actions_are_founder_admin_scoped():
    from tinyassets.api.universe import UNIVERSE_ACTIONS, WRITE_ACTIONS
    from tinyassets.auth.provider import _UNIVERSE_ADMIN_ACTIONS

    for action in ("set_engine", "offer_engine"):
        assert action in _UNIVERSE_ADMIN_ACTIONS
        assert action in WRITE_ACTIONS
        assert action in UNIVERSE_ACTIONS
