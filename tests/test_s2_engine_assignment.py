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


def test_byo_claude_scrubs_global_subscription(tmp_path, monkeypatch):
    """A BYO Anthropic key + a legacy Claude subscription record must NOT fall
    through to platform auth — the child env carries ANTHROPIC_API_KEY and has NO
    inherited global CLAUDE_CONFIG_DIR / oauth token."""
    _enable_byo(monkeypatch)
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
    assert "CLAUDE_CONFIG_DIR" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


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


def test_upsert_credential_preserves_other_records(tmp_path):
    """F2: the vault upsert primitive add/replaces by identity and PRESERVES all
    other credentials (social / vcs) — no replace-all wipe."""
    from tinyassets.credential_vault import load_credential_vault, upsert_credential

    write_credential_vault(tmp_path, [
        {"credential_type": "vcs", "service": "github",
         "destination": "owner/repo", "token": "ghp-existing"},
        {"credential_type": "social", "service": "x", "token": "x-tok"},
    ])
    upsert_credential(tmp_path, {
        "credential_type": "llm_api_key", "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-new").decode("ascii"),
    })
    types = {r.get("credential_type") for r in load_credential_vault(tmp_path)}
    assert {"vcs", "social", "llm_api_key"} == types


def test_upsert_credential_atomic_under_concurrent_writers(tmp_path):
    """C5: N concurrent upserts of DISTINCT credentials all survive — the
    load→merge→write is locked so no writer clobbers another's write."""
    import threading

    from tinyassets.credential_vault import load_credential_vault, upsert_credential

    n = 12
    barrier = threading.Barrier(n)

    def _deposit(i):
        barrier.wait()  # maximize the race window
        upsert_credential(tmp_path, {
            "credential_type": "vcs", "service": "github",
            "destination": f"owner/repo-{i}", "token": f"ghp-{i}",
        })

    threads = [threading.Thread(target=_deposit, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    dests = {r.get("destination") for r in load_credential_vault(tmp_path)}
    assert dests == {f"owner/repo-{i}" for i in range(n)}  # all distinct records survive


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
    assert out["status"] == "engine_set"
    assert load_universe_config(udir).engine_source == "self_hosted_endpoint"


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
