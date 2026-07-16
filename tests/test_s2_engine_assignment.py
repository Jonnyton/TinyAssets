"""S2 — per-universe engine assignment (BYO API key) via universe action=set_engine.

Covers: config.yaml partial-merge write path, the llm_api_key vault type +
CLI-subprocess env injection, the founder-only set_engine action, and that the
API key never reaches the response or the ledger.
"""
from __future__ import annotations

import base64
import json

import pytest

from tinyassets.config import load_universe_config, write_universe_config_fields
from tinyassets.credential_vault import (
    provider_auth_env_overrides,
    supported_llm_api_key_services,
    write_credential_vault,
)
from tinyassets.providers.base import subprocess_env_for_provider


def test_write_universe_config_fields_merges_and_preserves(tmp_path):
    write_universe_config_fields(tmp_path, preferred_writer="codex")
    assert load_universe_config(tmp_path).preferred_writer == "codex"
    # A second partial write must preserve the earlier field.
    write_universe_config_fields(tmp_path, preferred_judge="gemini-free")
    cfg = load_universe_config(tmp_path)
    assert cfg.preferred_writer == "codex"
    assert cfg.preferred_judge == "gemini-free"


def _enable_byo(monkeypatch):
    """Simulate Phase-2: executable BYO on (flag + code-backed attestation)."""
    import tinyassets.engine_binding as eb

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setattr(eb, "_vault_encryption_capability_attested", lambda: True)


def test_byo_claude_injected_only_when_executable(tmp_path, monkeypatch):
    """C2: a claude BYO key is injected into the CLI env ONLY when executable BYO
    is enabled (attested). Even a LEGACY llm_api_key row is DARK by default."""
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-test-XYZ").decode("ascii"),
    }])
    # Gate OFF (default) → no BYO injection (C2 legacy-vault dark).
    assert "ANTHROPIC_API_KEY" not in provider_auth_env_overrides(tmp_path, "claude-code")
    env_off = subprocess_env_for_provider("claude-code", universe_dir=tmp_path)
    assert "ANTHROPIC_API_KEY" not in env_off

    # Gate ON (attested) → injected.
    _enable_byo(monkeypatch)
    assert provider_auth_env_overrides(
        tmp_path, "claude-code")["ANTHROPIC_API_KEY"] == "sk-ant-test-XYZ"
    env_on = subprocess_env_for_provider("claude-code", universe_dir=tmp_path)
    assert env_on.get("ANTHROPIC_API_KEY") == "sk-ant-test-XYZ"


def test_codex_byo_key_is_never_injected(tmp_path, monkeypatch):
    """C2: a Codex/OpenAI BYO key is NOT executable, so it is NEVER injected —
    not even with the encryption gate on (would run judge/extract on the key)."""
    _enable_byo(monkeypatch)
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai-test").decode("ascii"),
    }])
    overrides = provider_auth_env_overrides(tmp_path, "codex")
    assert "OPENAI_API_KEY" not in overrides
    assert "CODEX_API_KEY" not in overrides


def test_attestation_toctou_uses_one_snapshot(tmp_path, monkeypatch):
    """#2: subprocess_env_for_provider takes ONE attestation snapshot — a mid-call
    True→False flip cannot leave ambient CLAUDE_CONFIG_DIR + omit the BYO key."""
    import tinyassets.engine_binding as eb

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    # Attestation flips True on the 1st read, then False on every later read —
    # a race that would fail-open WITHOUT a single-snapshot decision.
    calls = {"n": 0}

    def _flipping():
        calls["n"] += 1
        return calls["n"] == 1

    monkeypatch.setattr(eb, "_vault_encryption_capability_attested", _flipping)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/global/.claude")  # ambient login
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "global-oauth")
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key", "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-byo").decode("ascii"),
    }])
    env = subprocess_env_for_provider("claude-code", universe_dir=tmp_path)
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-byo"
    # Round-12 #2: the ambient CLAUDE_CONFIG_DIR is scrubbed and REPLACED with an
    # isolated empty dir (bare mode) so ~/.claude host OAuth can't win.
    assert env.get("CLAUDE_CONFIG_DIR") != "/global/.claude"
    assert "claude-byo-isolated" in env.get("CLAUDE_CONFIG_DIR", "")
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env  # ambient oauth scrubbed


def test_byo_bound_broken_secret_fails_closed_no_ambient(tmp_path, monkeypatch):
    """#2: a BYO-bound spawn whose key cannot be produced FAILS (no dispatch) and
    never falls through to the scrubbed ambient auth."""
    _enable_byo(monkeypatch)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/global/.claude")
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key", "service": "anthropic",
        "secret_b64": "!!not-base64!!",  # decodes → ValueError in the overlay
    }])
    with pytest.raises(Exception):  # noqa: B017 — fail-closed, any loud error is fine
        subprocess_env_for_provider("claude-code", universe_dir=tmp_path)


def test_legacy_subscription_record_fails_loud_even_with_byo_key(tmp_path, monkeypatch):
    """Round-12 #1: a legacy Claude subscription record is a RETIRED lane —
    it must FAIL LOUD (quarantine), never be silently ignored, even alongside a
    valid BYO key. The platform never custodies subscription tokens."""
    from tinyassets.credential_vault import RetiredSubscriptionLaneError

    _enable_byo(monkeypatch)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/global/.claude")  # platform login
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "global-oauth")
    write_credential_vault(tmp_path, [
        {
            "credential_type": "llm_api_key",
            "service": "anthropic",
            "secret_b64": base64.b64encode(b"sk-ant-byo").decode("ascii"),
        },
        # A legacy (blocked-lane) subscription record — its mere presence fails loud.
        {
            "credential_type": "llm_subscription",
            "service": "claude",
            "oauth_token": "legacy-oauth",
        },
    ])
    with pytest.raises(RetiredSubscriptionLaneError):
        subprocess_env_for_provider("claude-code", universe_dir=tmp_path)


_VALID_ANTHROPIC_KEY = "sk-ant-api03-" + "A" * 40


def test_set_engine_byo_raw_key_always_refused_through_chat(tmp_path, monkeypatch):
    """C3: a raw BYO API key must NEVER be accepted through the chatbot/MCP —
    refused unconditionally (no flag unlocks a plaintext-through-chat path), and
    nothing is stored."""
    from tinyassets.api import universe as uni

    # Even with the encryption gate "on", the raw-key-through-chat path is refused.
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    udir = tmp_path / "u-raw"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-raw")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    out = json.loads(uni._action_set_engine(
        universe_id="u-raw",
        inputs_json=json.dumps({"service": "anthropic", "api_key": _VALID_ANTHROPIC_KEY}),
    ))
    assert "error" in out and out.get("status") != "engine_set"
    err = out["error"].lower()
    assert "chatbot" in err or "relay" in err or "out-of-chat" in err
    from tinyassets.credential_vault import load_credential_vault
    assert load_credential_vault(udir) == []  # no plaintext key stored


def test_no_raw_secret_field_advertised_in_set_engine_contract(monkeypatch, tmp_path):
    """F3: the RENDERED tool/help contract must not advertise any raw-secret
    field — a client following the schema must never be told to send an api_key."""
    from tinyassets.api import universe as uni

    udir = tmp_path / "u-contract"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-contract")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)
    # Empty-input help (what a client renders to learn the schema).
    help_text = uni._action_set_engine(universe_id="u-contract", inputs_json="")
    assert "api_key" not in help_text
    assert "secret" not in help_text.lower() or "never" in help_text.lower()
    # The MCP tool docstring (rendered in the connector catalog) too.
    doc = uni._action_set_engine.__doc__ or ""
    assert "api_key" not in doc
    assert '"api_key"' not in doc


def test_set_engine_ledger_extractor_never_leaks(tmp_path, monkeypatch):
    """Non-secret lane declarations (self_hosted / market / host_daemon) remain
    discoverable and record no secret."""
    from tinyassets.api import universe as uni

    udir = tmp_path / "u-lane"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-lane")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)
    out = json.loads(uni._action_set_engine(
        universe_id="u-lane",
        inputs_json=json.dumps({
            "engine_source": "self_hosted_endpoint",
            "endpoint": "http://localhost:11434",
        }),
    ))
    # #4: a declaration returns engine_declared + executable:false (not "will run").
    assert out["status"] == "engine_declared"
    assert out["executable"] is False
    # #3: the raw endpoint is never echoed — only a redacted host.
    assert "engine_endpoint" not in out
    assert out["engine_endpoint_redacted"] == "http://localhost:11434"


def _set_engine(monkeypatch, tmp_path, uid, payload):
    from tinyassets.api import universe as uni

    udir = tmp_path / uid
    udir.mkdir(exist_ok=True)
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": uid)
    monkeypatch.setattr(uni, "_universe_dir", lambda _uid: udir)
    return json.loads(uni._action_set_engine(universe_id=uid, inputs_json=json.dumps(payload)))


@pytest.mark.parametrize("endpoint", [
    "ftp://host/x",            # non-http(s) scheme
    "not-a-url",              # no scheme/host
    "http://",                # no host
    "http://user:pw@host",    # embedded credentials
    "http://169.254.169.254/latest/meta-data",  # cloud-metadata SSRF target
])
def test_set_engine_self_hosted_rejects_bad_endpoint(tmp_path, monkeypatch, endpoint):
    """F6: an invalid / SSRF self-hosted endpoint is rejected loudly."""
    out = _set_engine(monkeypatch, tmp_path, "u-badurl", {
        "engine_source": "self_hosted_endpoint", "endpoint": endpoint,
    })
    assert "error" in out and out.get("status") != "engine_set"


def test_set_engine_self_hosted_accepts_valid_endpoint(tmp_path, monkeypatch):
    out = _set_engine(monkeypatch, tmp_path, "u-goodurl", {
        "engine_source": "self_hosted_endpoint", "endpoint": "https://ollama.example.com:11434",
    })
    assert out["status"] == "engine_declared"
    assert out["executable"] is False


def test_set_engine_self_hosted_rejects_query_secret(tmp_path, monkeypatch):
    """#3: a ?api_key= credential smuggled in the endpoint URL is rejected + not stored."""
    out = _set_engine(monkeypatch, tmp_path, "u-qsecret", {
        "engine_source": "self_hosted_endpoint",
        "endpoint": "https://engine.example/v1?api_key=SECRET",
    })
    assert "error" in out and out.get("status") != "engine_declared"
    assert "SECRET" not in json.dumps(out)  # never echoed


def test_set_engine_self_hosted_rejects_extra_secret_field(tmp_path, monkeypatch):
    """#3: an extra api_key field on the non-secret lane is rejected + not stored."""
    out = _set_engine(monkeypatch, tmp_path, "u-extra", {
        "engine_source": "self_hosted_endpoint",
        "endpoint": "https://engine.example",
        "api_key": "SECRET",
    })
    assert "error" in out and out.get("status") != "engine_declared"
    assert "SECRET" not in json.dumps(out)


def test_set_engine_market_declares_not_runs(tmp_path, monkeypatch):
    """#4: market declaration returns executable:false, not "your universe will run"."""
    out = _set_engine(monkeypatch, tmp_path, "u-market", {
        "engine_source": "market_rented", "market_model": "glm-5.2",
        "market_rate": 0.5, "spending_cap": 10.0,
    })
    assert out["status"] == "engine_declared" and out["executable"] is False
    assert "will run" not in json.dumps(out).lower()


def test_set_engine_host_daemon_declares_no_summon(tmp_path, monkeypatch):
    """#4: host_daemon declaration returns executable:false and no daemon_summon instruction."""
    out = _set_engine(monkeypatch, tmp_path, "u-hd", {
        "engine_source": "host_daemon", "provider": "claude-code",
    })
    assert out["status"] == "engine_declared" and out["executable"] is False
    assert "daemon_summon" not in json.dumps(out)


def test_r12_5_lane_switch_replaces_engine_namespace(tmp_path, monkeypatch):
    """Round-12 #5: switching engine lanes REPLACES the engine namespace — stale
    fields from the previous lane (market_rate / spending_cap / market_model /
    preferred_writer) must not survive in the new lane's config.yaml."""
    import yaml

    uid = "u-lane-switch"
    # 1) market_rented writes market_model + market_rate + spending_cap + writer.
    out1 = _set_engine(monkeypatch, tmp_path, uid, {
        "engine_source": "market_rented", "market_model": "glm-5.2",
        "market_rate": 0.5, "spending_cap": 10.0, "preferred_writer": "codex",
    })
    assert out1["status"] == "engine_declared"
    raw1 = yaml.safe_load((tmp_path / uid / "config.yaml").read_text())
    assert raw1["market_model"] == "glm-5.2" and raw1["preferred_writer"] == "codex"

    # 2) switch to self_hosted_endpoint — the market_* + preferred_writer fields
    # MUST be cleared from the on-disk config (replaced, not merged).
    out2 = _set_engine(monkeypatch, tmp_path, uid, {
        "engine_source": "self_hosted_endpoint",
        "endpoint": "https://ollama.example.com",
    })
    assert out2["status"] == "engine_declared"
    raw2 = yaml.safe_load((tmp_path / uid / "config.yaml").read_text())
    assert raw2["engine_source"] == "self_hosted_endpoint"
    assert raw2["engine_endpoint"] == "https://ollama.example.com"
    for stale in ("market_model", "market_rate", "spending_cap", "preferred_writer"):
        assert stale not in raw2, f"stale {stale!r} leaked across the lane switch"
    # And the loaded config reflects the cleared defaults.
    cfg2 = load_universe_config(tmp_path / uid)
    assert cfg2.market_model == "" and cfg2.spending_cap == 0.0
    assert cfg2.preferred_writer == ""


@pytest.mark.parametrize("field,value", [
    ("spending_cap", -1.0),
    ("market_rate", -0.5),
    ("spending_cap", float("inf")),
    ("spending_cap", float("nan")),
])
def test_set_engine_market_rejects_bad_numbers(tmp_path, monkeypatch, field, value):
    """F6: market rate/cap must be finite non-negative — reject NaN/inf/negative."""
    payload = {"engine_source": "market_rented", "market_model": "glm-5.2",
               "market_rate": 0.5, "spending_cap": 10.0}
    payload[field] = value
    out = _set_engine(monkeypatch, tmp_path, "u-badnum", payload)
    assert "error" in out and out.get("status") != "engine_set"


def test_set_engine_host_daemon_rejects_unknown_provider(tmp_path, monkeypatch):
    """F6: host_daemon provider must be a known writer provider."""
    out = _set_engine(monkeypatch, tmp_path, "u-badprov", {
        "engine_source": "host_daemon", "provider": "novelist-9000",
    })
    assert "error" in out and out.get("status") != "engine_set"


def test_model_hint_write_surface_accepts_free_form():
    """Round-11 revert: model_hint is stored FREE-FORM (no authoring whitelist —
    that was a breaking API change). The security invariant lives at the router
    boundary (see test_provider_auth_router_quarantine's ALL-dispatch-path tests
    proving an unknown role is classified as a writer route + enforced)."""
    from tinyassets.api.branches import _coerce_model_hint_update

    val, err = _coerce_model_hint_update("reviewer", "model_hint")
    assert err == "" and val == "reviewer"  # previously-valid value preserved
    val2, err2 = _coerce_model_hint_update("checker", "model_hint")
    assert err2 == "" and val2 == "checker"


def test_ledger_extractor_never_leaks_the_key():
    from tinyassets.api.universe import _extract_set_engine

    target, summary, payload = _extract_set_engine(
        {"inputs_json": json.dumps({"api_key": "sk-SECRET-LEDGER"})},
        {"universe_id": "u-1", "service": "anthropic",
         "preferred_writer": "claude-code", "status": "engine_set"},
    )
    assert "sk-SECRET-LEDGER" not in json.dumps([target, summary, payload])


def test_set_engine_is_founder_admin_scoped():
    from tinyassets.api.universe import WRITE_ACTIONS
    from tinyassets.auth.provider import _UNIVERSE_ADMIN_ACTIONS

    # Founder-only (admin scope) + ledger/ACL-write gated.
    assert "set_engine" in _UNIVERSE_ADMIN_ACTIONS
    assert "set_engine" in WRITE_ACTIONS


def test_supported_services_cover_both_cli_routes():
    services = supported_llm_api_key_services()
    assert {"anthropic", "openai"} <= services
