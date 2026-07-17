"""S6/S7/S8 — engine-source onboard choices.

set_engine carries engine_source (byo_api_key | self_hosted_endpoint |
market_rented | host_daemon), all persisted to config.yaml. (The premature
offer_engine market-supply scaffolding was removed in round-16 #3 — that
capability belongs to the paid-market domain via the canonical API.)
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


def test_r21_3_endpoint_with_credential_in_path_is_rejected(tmp_path, monkeypatch):
    """Round-21 #3: an endpoint with an API key smuggled into the PATH must be
    REJECTED (it would be stored plaintext in config.yaml). Nothing is persisted."""
    uni, udir = _setup(tmp_path, monkeypatch)
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "self_hosted_endpoint",
        "endpoint": "https://engine.example/v1/sk-ant-api03-" + "A" * 40,
        "preferred_writer": "ollama-local"})))
    assert "error" in out
    assert "credential" in out["error"].lower() or "path" in out["error"].lower()
    # The secret-carrying endpoint is NOT persisted (no plaintext custody).
    assert load_universe_config(udir).engine_source != "self_hosted_endpoint"


def test_r21_3_endpoint_validator_unit_matrix():
    """Round-21 #3 unit matrix: the validator rejects credential-shaped path content
    while allowing legitimate base paths, route segments, and lowercase UUIDs."""
    from tinyassets.api.universe import _validate_engine_endpoint

    # Rejected: known key prefixes + high-entropy secret segment anywhere in the path.
    for bad in (
        "https://engine.example/v1/sk-ant-api03-SECRETSECRETSECRETSECRET",
        "https://engine.example/sk-openai-abc123",
        "https://engine.example/xai-DEADBEEFdeadbeef1234567890",
        "https://engine.example/path/Ab3Xy9Zk7Qw2Er5Ty8Ui0Op1As4Df6Gh",  # 32+ mixed
    ):
        assert _validate_engine_endpoint(bad) is not None, bad
    # Allowed: base paths, route segments, and a lowercase UUID model id.
    for ok in (
        "http://localhost:11434",
        "https://engine.example/v1",
        "https://engine.example/v1/chat/completions",
        "https://engine.example/v1/models/550e8400-e29b-41d4-a716-446655440000",
    ):
        assert _validate_engine_endpoint(ok) is None, ok


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


def test_offer_engine_removed_r16(tmp_path):
    """Round-16 #3: the premature offer_engine scaffolding was REMOVED (wrong
    surface — reachable only via the deprecated hidden `universe` tool — and a
    parallel founder-offer JSON store, not the paid-market domain). The market
    supply/offer capability belongs to the paid-market domain
    (``tinyassets/paid_market/``) via the canonical API, done as a separate lane."""
    from tinyassets.api import universe as uni
    from tinyassets.auth.provider import _UNIVERSE_ADMIN_ACTIONS

    assert "offer_engine" not in uni.UNIVERSE_ACTIONS
    assert "offer_engine" not in uni.WRITE_ACTIONS
    assert "offer_engine" not in _UNIVERSE_ADMIN_ACTIONS
    assert not hasattr(uni, "_action_offer_engine")


def test_engine_actions_are_founder_admin_scoped():
    from tinyassets.api.universe import UNIVERSE_ACTIONS, WRITE_ACTIONS
    from tinyassets.auth.provider import _UNIVERSE_ADMIN_ACTIONS

    # set_engine (the S5 engine-onboarding action) stays founder-admin scoped;
    # offer_engine was removed (round-16 #3, paid-market domain).
    assert "set_engine" in _UNIVERSE_ADMIN_ACTIONS
    assert "set_engine" in WRITE_ACTIONS
    assert "set_engine" in UNIVERSE_ACTIONS
