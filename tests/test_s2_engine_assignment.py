"""S2/S5 engine assignment through the provider-generic credential broker."""

from __future__ import annotations

import json

import pytest

from tinyassets.config import load_universe_config, write_universe_config_fields
from tinyassets.credential_broker import (
    BINDING_STATUS_NEEDS_REDEPOSIT,
    BINDING_STATUS_REVOKED,
    ENGINE_DESTINATION,
    ENGINE_PURPOSE,
    deposit_engine_api_key,
    platform_store,
    provider_auth_env_overrides,
    record_binding,
    resolve_credential,
    supported_llm_api_key_services,
)
from tinyassets.credentials import (
    CredentialUnavailable,
    SecretBinding,
    SecretKind,
    SecretScope,
    VaultErrorCode,
    new_secret_ref,
)
from tinyassets.providers.base import subprocess_env_for_provider


@pytest.fixture
def executable_byo(monkeypatch):
    import tinyassets.engine_binding as engine_binding

    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)


def test_write_universe_config_fields_merges_and_preserves(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "preferred_judge: gemini-free\ntemperature: 0.3\n", encoding="utf-8"
    )
    write_universe_config_fields(
        tmp_path, preferred_writer="claude-code", engine_source="byo_api_key"
    )
    cfg = load_universe_config(tmp_path)
    assert cfg.preferred_writer == "claude-code"
    assert cfg.engine_source == "byo_api_key"
    assert cfg.preferred_judge == "gemini-free"


def test_anthropic_key_isolated_and_injected(
    platform_vault_env, monkeypatch, executable_byo
):
    universe = platform_vault_env / "u-key"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service="anthropic",
        api_key="sk-ant-api03-" + "A" * 40,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "HOST_AMBIENT_SECRET")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "HOST_OAUTH")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/host/claude")

    env = subprocess_env_for_provider("claude-code", universe_dir=universe)

    assert env["ANTHROPIC_API_KEY"].startswith("sk-ant-api03-")
    assert "HOST_AMBIENT_SECRET" not in env.values()
    assert "HOST_OAUTH" not in env.values()
    assert env["CLAUDE_CONFIG_DIR"] == str(
        universe / ".engine-auth" / "claude"
    )
    assert env["CLAUDE_CONFIG_DIR"] != "/host/claude"
    assert env["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"] == "1"


def test_openai_key_maps_only_to_codex_broker_overlay(platform_vault_env):
    universe = platform_vault_env / "u-openai"
    universe.mkdir()
    deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service="openai",
        api_key="sk-openai-test",
    )
    assert provider_auth_env_overrides("codex", universe)["OPENAI_API_KEY"] == (
        "sk-openai-test"
    )
    assert provider_auth_env_overrides("claude-code", universe) == {}


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (None, VaultErrorCode.NOT_FOUND),
        (BINDING_STATUS_NEEDS_REDEPOSIT, VaultErrorCode.REAUTHORIZATION_REQUIRED),
        (BINDING_STATUS_REVOKED, VaultErrorCode.REVOKED),
    ],
)
def test_missing_or_inactive_byo_never_inherits_host_identity(
    platform_vault_env, monkeypatch, executable_byo, status, expected_code
):
    universe = platform_vault_env / f"u-{status or 'missing'}"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    if status is not None:
        record_binding(
            SecretBinding(
                ref=new_secret_ref(),
                kind=SecretKind.API_KEY,
                scope=SecretScope(
                    founder_id="founder-1",
                    universe_id=universe.name,
                    provider="anthropic",
                    destination=ENGINE_DESTINATION,
                    purpose=ENGINE_PURPOSE,
                ),
                store=platform_store(),
            ),
            status=status,
        )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "HOST_AMBIENT_SECRET")

    with pytest.raises((CredentialUnavailable, Exception)) as exc:
        subprocess_env_for_provider("claude-code", universe_dir=universe)
    if isinstance(exc.value, CredentialUnavailable):
        assert exc.value.code == expected_code
    assert "HOST_AMBIENT_SECRET" not in str(exc.value)


def test_explicit_host_daemon_may_inherit_host_auth(tmp_path, monkeypatch):
    write_universe_config_fields(tmp_path, engine_source="host_daemon")
    monkeypatch.setenv("CODEX_HOME", "/host/codex")
    assert subprocess_env_for_provider("codex", universe_dir=tmp_path)[
        "CODEX_HOME"
    ] == "/host/codex"


def test_set_engine_deposits_opaque_ref(platform_vault_env, monkeypatch):
    from tinyassets.api import universe as universe_api

    universe = platform_vault_env / "u-set"
    universe.mkdir()
    monkeypatch.setattr(universe_api, "_request_universe", lambda universe_id="": "u-set")
    monkeypatch.setattr(universe_api, "_universe_dir", lambda uid: universe)

    response = json.loads(
        universe_api._action_set_engine(
            universe_id="u-set",
            inputs_json=json.dumps(
                {"service": "anthropic", "api_key": "sk-secret-KEY"}
            ),
        )
    )

    assert response["status"] == "engine_set"
    assert response["credential_ref"].startswith("secret:v1:")
    assert "sk-secret-KEY" not in json.dumps(response)
    assert load_universe_config(universe).engine_source == "byo_api_key"
    with resolve_credential(
        "u-set", "anthropic", ENGINE_PURPOSE, ENGINE_DESTINATION
    ) as lease:
        assert lease.reveal() == b"sk-secret-KEY"


def test_set_engine_blocks_unmigrated_legacy_state(platform_vault_env, monkeypatch):
    from tinyassets.api import universe as universe_api

    universe = platform_vault_env / "u-legacy"
    universe.mkdir()
    (universe / ".credential-vault.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        universe_api, "_request_universe", lambda universe_id="": universe.name
    )
    monkeypatch.setattr(universe_api, "_universe_dir", lambda uid: universe)
    response = json.loads(
        universe_api._action_set_engine(
            universe_id=universe.name,
            inputs_json=json.dumps({"service": "anthropic", "api_key": "secret"}),
        )
    )
    assert "unmigrated legacy" in response["error"]


def _set_engine(monkeypatch, tmp_path, uid, payload):
    from tinyassets.api import universe as universe_api

    universe = tmp_path / uid
    universe.mkdir(exist_ok=True)
    monkeypatch.setattr(universe_api, "_request_universe", lambda universe_id="": uid)
    monkeypatch.setattr(universe_api, "_universe_dir", lambda _uid: universe)
    return json.loads(
        universe_api._action_set_engine(
            universe_id=uid, inputs_json=json.dumps(payload)
        )
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "ftp://host/x",
        "not-a-url",
        "http://",
        "http://user:pw@host",
        "http://169.254.169.254/latest/meta-data",
        "https://engine.example/v1?api_key=SECRET",
    ],
)
def test_self_hosted_declaration_rejects_unsafe_endpoint(
    tmp_path, monkeypatch, endpoint
):
    response = _set_engine(
        monkeypatch,
        tmp_path,
        "u-bad-endpoint",
        {"engine_source": "self_hosted_endpoint", "endpoint": endpoint},
    )
    assert "error" in response
    assert "SECRET" not in json.dumps(response)


def test_inert_lane_declaration_does_not_change_live_writer(tmp_path, monkeypatch):
    response = _set_engine(
        monkeypatch,
        tmp_path,
        "u-market",
        {
            "engine_source": "market_rented",
            "market_model": "glm-5.2",
            "market_rate": 0.5,
            "spending_cap": 10.0,
            "preferred_writer": "codex",
        },
    )
    assert response["status"] == "engine_declared"
    assert response["executable"] is False
    config = load_universe_config(tmp_path / "u-market")
    assert config.preferred_writer == ""
    assert config.extra["declared_preferred_writer"] == "codex"


def test_supported_services_cover_cli_broker_routes():
    assert {"anthropic", "openai"} <= supported_llm_api_key_services()


def test_set_engine_is_founder_admin_scoped():
    from tinyassets.api.universe import WRITE_ACTIONS

    assert "set_engine" in WRITE_ACTIONS
