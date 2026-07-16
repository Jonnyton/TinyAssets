"""S2 — per-universe engine assignment (BYO API key) via universe action=set_engine.

Covers: config.yaml partial-merge write path, the llm_api_key vault type +
CLI-subprocess env injection, the founder-only set_engine action, and that the
API key never reaches the response or the ledger.
"""
from __future__ import annotations

import base64
import json

from tinyassets.config import load_universe_config, write_universe_config_fields
from tinyassets.credential_vault import (
    provider_auth_env_overrides,
    resolve_llm_api_key,
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


def test_llm_api_key_injects_into_claude_cli_env(tmp_path):
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-test-XYZ").decode("ascii"),
    }])
    assert resolve_llm_api_key(tmp_path, "ANTHROPIC_API_KEY") == "sk-ant-test-XYZ"
    # provider_auth_env_overrides maps it to the CLI env var.
    overrides = provider_auth_env_overrides(tmp_path, "claude-code")
    assert overrides["ANTHROPIC_API_KEY"] == "sk-ant-test-XYZ"
    # The subprocess env carries it even though the global api-key strip runs first.
    env = subprocess_env_for_provider("claude-code", universe_dir=tmp_path)
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-test-XYZ"


def test_openai_key_maps_to_codex_only(tmp_path):
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai-test").decode("ascii"),
    }])
    assert provider_auth_env_overrides(tmp_path, "codex")["OPENAI_API_KEY"] == "sk-openai-test"
    # The wrong provider does not receive it (no cross-provider bleed).
    assert "OPENAI_API_KEY" not in provider_auth_env_overrides(tmp_path, "claude-code")
    assert "ANTHROPIC_API_KEY" not in provider_auth_env_overrides(tmp_path, "claude-code")


def test_byo_codex_overlay_sets_codex_api_key_and_isolates_home(tmp_path, monkeypatch):
    """Codex round-6 Finding 2: non-interactive `codex exec` authenticates via
    CODEX_API_KEY. A BYO-keyed codex spawn env must set CODEX_API_KEY AND point
    CODEX_HOME at an isolated key-only dir — never inherit the global login."""
    monkeypatch.setenv("CODEX_HOME", "/global/.codex")  # the platform subscription login
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai-byo").decode("ascii"),
    }])
    overrides = provider_auth_env_overrides(tmp_path, "codex")
    # codex exec's auth var carries the BYO key.
    assert overrides["CODEX_API_KEY"] == "sk-openai-byo"
    assert overrides["OPENAI_API_KEY"] == "sk-openai-byo"
    # CODEX_HOME is redirected to an isolated per-universe dir, NOT the global login.
    assert overrides["CODEX_HOME"] != "/global/.codex"
    assert "codex-byo" in overrides["CODEX_HOME"]
    # The isolated home holds NO auth.json (so the KEY authenticates, not a sub).
    from pathlib import Path
    assert not (Path(overrides["CODEX_HOME"]) / "auth.json").exists()


def test_byo_codex_full_env_isolates_global_home(tmp_path, monkeypatch):
    """The composed subprocess env for a BYO codex spawn does not inherit the
    global CODEX_HOME login and carries CODEX_API_KEY."""
    monkeypatch.setenv("CODEX_HOME", "/global/.codex")
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai-byo").decode("ascii"),
    }])
    env = subprocess_env_for_provider("codex", universe_dir=tmp_path)
    assert env.get("CODEX_API_KEY") == "sk-openai-byo"
    assert env.get("CODEX_HOME") != "/global/.codex"


def test_byo_claude_scrubs_global_subscription_and_fails_no_open(tmp_path, monkeypatch):
    """Codex F3: a BYO Anthropic key + a legacy Claude subscription record must
    NOT fall through to platform auth — the child env carries ANTHROPIC_API_KEY
    and has NO inherited global CLAUDE_CONFIG_DIR / oauth token."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/global/.claude")  # platform login
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "global-oauth")
    write_credential_vault(tmp_path, [
        {
            "credential_type": "llm_api_key",
            "service": "anthropic",
            "secret_b64": base64.b64encode(b"sk-ant-byo").decode("ascii"),
        },
        # A legacy (blocked-lane) subscription record that must NOT be consulted.
        {
            "credential_type": "llm_subscription",
            "service": "claude",
            "oauth_token": "legacy-oauth",
        },
    ])
    env = subprocess_env_for_provider("claude-code", universe_dir=tmp_path)
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-byo"
    # Global subscription auth scrubbed — the key authenticates, not the platform.
    assert "CLAUDE_CONFIG_DIR" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_byo_codex_isolation_failure_fails_closed(tmp_path, monkeypatch):
    """Codex F3: if CODEX_HOME isolation cannot be materialized for a BYO codex
    spawn, the env build FAILS LOUD — never falls through to platform auth."""
    import tinyassets.credential_vault as cv

    monkeypatch.setenv("CODEX_HOME", "/global/.codex")
    write_credential_vault(tmp_path, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai-byo").decode("ascii"),
    }])
    # Simulate an isolation failure (mkdir/ACL error → None).
    monkeypatch.setattr(cv, "_byo_codex_home", lambda _udir: None)
    import pytest
    with pytest.raises(Exception):  # noqa: B017 — fail-closed, any loud error is fine
        subprocess_env_for_provider("codex", universe_dir=tmp_path)


_VALID_ANTHROPIC_KEY = "sk-ant-api03-" + "A" * 40


def test_set_engine_refused_when_byo_gate_off(tmp_path, monkeypatch):
    """F3: hosted BYO deposit is REFUSED until the vault-encryption gate opens —
    the platform must not store a plaintext key. Independent of any other flag."""
    from tinyassets.api import universe as uni

    monkeypatch.delenv("TINYASSETS_BYO_VAULT_ENCRYPTED", raising=False)
    udir = tmp_path / "u-gateoff"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-gateoff")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    out = json.loads(uni._action_set_engine(
        universe_id="u-gateoff",
        inputs_json=json.dumps({"service": "anthropic", "api_key": _VALID_ANTHROPIC_KEY}),
    ))
    assert "error" in out and out.get("status") != "engine_set"
    assert "vault encryption" in out["error"].lower()
    # Nothing stored.
    from tinyassets.credential_vault import load_credential_vault
    assert load_credential_vault(udir) == []


def test_set_engine_action_writes_vault_and_config(tmp_path, monkeypatch):
    from tinyassets.api import universe as uni

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")  # gate on for deposit
    udir = tmp_path / "u-test"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-test")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    out = json.loads(uni._action_set_engine(
        universe_id="u-test",
        inputs_json=json.dumps({"service": "anthropic", "api_key": _VALID_ANTHROPIC_KEY}),
    ))
    assert out["status"] == "engine_set"
    assert out["preferred_writer"] == "claude-code"  # inferred from service
    # The key is NEVER echoed in the response.
    assert _VALID_ANTHROPIC_KEY not in json.dumps(out)
    # config.yaml + vault were written and resolve end-to-end.
    assert load_universe_config(udir).preferred_writer == "claude-code"
    assert resolve_llm_api_key(udir, "ANTHROPIC_API_KEY") == _VALID_ANTHROPIC_KEY


def test_set_engine_preserves_other_credentials(tmp_path, monkeypatch):
    """F2: an engine bind must UPSERT (not replace-all) — a founder's other
    credentials (social / vcs) survive."""
    from tinyassets.api import universe as uni

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    udir = tmp_path / "u-preserve"
    udir.mkdir()
    write_credential_vault(udir, [
        {"credential_type": "vcs", "service": "github",
         "destination": "owner/repo", "token": "ghp-existing"},
        {"credential_type": "social", "service": "x", "token": "x-tok"},
    ])
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-preserve")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    out = json.loads(uni._action_set_engine(
        universe_id="u-preserve",
        inputs_json=json.dumps({"service": "anthropic", "api_key": _VALID_ANTHROPIC_KEY}),
    ))
    assert out["status"] == "engine_set"
    from tinyassets.credential_vault import load_credential_vault
    types = {r.get("credential_type") for r in load_credential_vault(udir)}
    assert {"vcs", "social", "llm_api_key"} <= types  # all preserved + the new key


def test_set_engine_config_failure_rolls_back_vault(tmp_path, monkeypatch):
    """F2 transactionality: a config-write failure rolls back the vault deposit —
    no orphan key left behind."""
    from tinyassets import config as cfg
    from tinyassets.api import universe as uni

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    udir = tmp_path / "u-rollback"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-rollback")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(cfg, "write_universe_config_fields", _boom)
    out = json.loads(uni._action_set_engine(
        universe_id="u-rollback",
        inputs_json=json.dumps({"service": "anthropic", "api_key": _VALID_ANTHROPIC_KEY}),
    ))
    assert "error" in out and out.get("status") != "engine_set"
    from tinyassets.credential_vault import load_credential_vault
    assert load_credential_vault(udir) == []  # deposit rolled back (no orphan key)


def test_set_engine_requires_key_and_known_service(tmp_path, monkeypatch):
    from tinyassets.api import universe as uni

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    udir = tmp_path / "u-x"
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": "u-x")
    monkeypatch.setattr(uni, "_universe_dir", lambda uid: udir)

    missing_key = json.loads(uni._action_set_engine(
        universe_id="u-x", inputs_json=json.dumps({"service": "anthropic"})))
    assert "error" in missing_key

    bad_service = json.loads(uni._action_set_engine(
        universe_id="u-x",
        inputs_json=json.dumps({"service": "nonsense", "api_key": "k"})))
    assert "error" in bad_service
    assert "nonsense" in bad_service["error"]


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
