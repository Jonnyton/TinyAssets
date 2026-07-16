"""S5 — per-universe engine-capacity binding resolver + non-ambient work flag.

Covers ``tinyassets.engine_binding``: the honest "can this universe run?"
predicate (bound vs idle-until-bound vs DECLARED-but-broken → fail loud) over
the SAME vault + config primitives the bind acts write, plus the default-OFF
feature flag that arms the non-ambient work gate.
"""
from __future__ import annotations

import base64

import pytest

from tinyassets.config import write_universe_config_fields
from tinyassets.credential_vault import write_credential_vault
from tinyassets.engine_binding import (
    NON_AMBIENT_WORK_ENV,
    EngineMisconfiguredError,
    non_ambient_work_enabled,
    resolve_engine_binding,
)

# ---- non_ambient_work_enabled: default OFF -------------------------------


def test_flag_defaults_off_when_unset(monkeypatch):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    assert non_ambient_work_enabled() is False


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  "])
def test_flag_off_for_falsey_values(monkeypatch, value):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, value)
    assert non_ambient_work_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "ON", "True"])
def test_flag_on_for_truthy_values(monkeypatch, value):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, value)
    assert non_ambient_work_enabled() is True


# ---- resolve_engine_binding: UNBOUND (fresh universe) --------------------


def test_fresh_universe_is_unbound(tmp_path):
    """A universe with no config.yaml and no vault is honestly idle-until-bound."""
    udir = tmp_path / "u-fresh"
    udir.mkdir()
    binding = resolve_engine_binding(udir)
    assert binding.bound is False
    assert binding.engine_source == ""
    assert binding.capacity_kinds == ()


def test_default_engine_source_alone_is_not_a_bind(tmp_path):
    """A config.yaml WITHOUT an explicit engine_source key (only unrelated
    fields) must not read as bound — the dataclass default ``byo_api_key`` is
    not a bind act."""
    udir = tmp_path / "u-cfg"
    udir.mkdir()
    write_universe_config_fields(udir, temperature=0.5, preferred_writer="codex")
    binding = resolve_engine_binding(udir)
    assert binding.bound is False


# ---- resolve_engine_binding: BOUND ---------------------------------------


def test_byo_api_key_in_vault_is_bound(tmp_path):
    udir = tmp_path / "u-byo"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-test").decode("ascii"),
    }])
    write_universe_config_fields(udir, engine_source="byo_api_key")
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert "byo_api_key" in binding.capacity_kinds
    assert binding.engine_source == "byo_api_key"


def test_subscription_record_in_vault_is_bound(tmp_path):
    udir = tmp_path / "u-sub"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription",
        "service": "claude",
        "oauth_token": "oauth-abc",
    }])
    write_universe_config_fields(udir, engine_source="subscription")
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert "subscription:claude" in binding.capacity_kinds


def test_self_hosted_endpoint_is_bound(tmp_path):
    udir = tmp_path / "u-self"
    udir.mkdir()
    write_universe_config_fields(
        udir,
        engine_source="self_hosted_endpoint",
        engine_endpoint="http://localhost:11434",
    )
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert "self_hosted_endpoint" in binding.capacity_kinds


def test_market_rented_is_bound(tmp_path):
    udir = tmp_path / "u-mkt"
    udir.mkdir()
    write_universe_config_fields(
        udir, engine_source="market_rented", market_model="glm-5.2",
    )
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert "market_rented" in binding.capacity_kinds


def test_host_daemon_declared_is_bound(tmp_path):
    """host_daemon is a recorded choice; the running daemon is the capacity."""
    udir = tmp_path / "u-host"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="host_daemon")
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert "host_daemon" in binding.capacity_kinds


# ---- resolve_engine_binding: MISCONFIGURED (declared but broken) → LOUD ---


def test_declared_byo_without_key_fails_loud(tmp_path):
    udir = tmp_path / "u-badbyo"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="byo_api_key")
    with pytest.raises(EngineMisconfiguredError) as excinfo:
        resolve_engine_binding(udir)
    assert excinfo.value.engine_source == "byo_api_key"


def test_declared_self_hosted_without_endpoint_fails_loud(tmp_path):
    udir = tmp_path / "u-badself"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="self_hosted_endpoint")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_declared_market_without_model_fails_loud(tmp_path):
    udir = tmp_path / "u-badmkt"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="market_rented")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_declared_subscription_without_credential_fails_loud(tmp_path):
    udir = tmp_path / "u-badsub"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="subscription")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_malformed_vault_fails_loud(tmp_path):
    """A vault that won't parse is a misconfiguration, not silent unbound."""
    from tinyassets.credential_vault import credential_vault_path

    udir = tmp_path / "u-badvault"
    udir.mkdir()
    credential_vault_path(udir).write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)
