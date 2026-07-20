"""Broker-backed engine binding and immutable execution snapshot tests."""

from __future__ import annotations

import pytest

from tinyassets.config import write_universe_config_fields
from tinyassets.credential_broker import (
    MIGRATION_MARKER_FILENAME,
    deposit_engine_api_key,
)
from tinyassets.engine_binding import (
    BYO_VAULT_ENCRYPTED_ENV,
    EngineMisconfiguredError,
    byo_credential_digest,
    byo_execution_enabled,
    execution_blocked_reason,
    non_ambient_work_enabled,
    pin_byo_execution_snapshot,
    resolve_engine_binding,
)


@pytest.fixture
def executable_byo(monkeypatch):
    import tinyassets.engine_binding as engine_binding

    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)


def _deposit(universe, *, service="anthropic", value="sk-ant-api03-test"):
    return deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service=service,
        api_key=value,
    )


def test_byo_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(BYO_VAULT_ENCRYPTED_ENV, raising=False)
    assert byo_execution_enabled(None) is False


def test_real_sandbox_default_keeps_byo_execution_disabled(
    tmp_path, monkeypatch
):
    """Do not stub the sandbox attestation: its production default is the gate."""
    import tinyassets.engine_binding as engine_binding

    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, "1")
    monkeypatch.setattr(
        engine_binding, "_vault_encryption_capability_attested", lambda *_: True
    )

    assert byo_execution_enabled(tmp_path) is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_byo_flag_still_requires_sandbox_attestation(monkeypatch, value):
    import tinyassets.engine_binding as engine_binding

    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, value)
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: False)
    monkeypatch.setattr(
        engine_binding, "_vault_encryption_capability_attested", lambda *_: True
    )
    assert byo_execution_enabled(None) is False


def test_non_ambient_flag(monkeypatch):
    monkeypatch.delenv("TINYASSETS_NON_AMBIENT_WORK", raising=False)
    assert non_ambient_work_enabled() is False
    monkeypatch.setenv("TINYASSETS_NON_AMBIENT_WORK", "true")
    assert non_ambient_work_enabled() is True


def test_fresh_universe_is_unbound(tmp_path):
    binding = resolve_engine_binding(tmp_path)
    assert binding.bound is False
    assert binding.capacity_kinds == ()
    assert binding.needs_migration is False


@pytest.mark.parametrize(
    "source", ["host_daemon", "market_rented", "self_hosted_endpoint"]
)
def test_declared_runtime_lane_is_inert(tmp_path, source):
    write_universe_config_fields(tmp_path, engine_source=source)
    binding = resolve_engine_binding(tmp_path)
    assert binding.bound is False
    assert "not available" in binding.reason


def test_broker_anthropic_binding_is_bound_only_when_fully_attested(
    platform_vault_env, executable_byo
):
    universe = platform_vault_env / "u-bound"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    _deposit(universe)

    binding = resolve_engine_binding(universe)

    assert binding.bound is True
    assert binding.eligible_providers == frozenset({"claude-code"})
    assert binding.vault_providers == frozenset({"claude-code"})


def test_broker_binding_is_dark_without_operator_opt_in(
    platform_vault_env, monkeypatch
):
    universe = platform_vault_env / "u-dark"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    _deposit(universe)
    monkeypatch.delenv(BYO_VAULT_ENCRYPTED_ENV, raising=False)

    assert resolve_engine_binding(universe).bound is False


def test_codex_byo_is_declared_not_executable(
    platform_vault_env, executable_byo
):
    universe = platform_vault_env / "u-codex"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    _deposit(universe, service="openai", value="sk-openai")

    binding = resolve_engine_binding(universe)

    assert binding.bound is False
    assert "no executable" in binding.reason


def test_declared_byo_without_binding_fails_loud(tmp_path):
    write_universe_config_fields(tmp_path, engine_source="byo_api_key")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(tmp_path)


def test_unknown_or_corrupt_config_fails_loud(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "engine_source: attacker_typo\n", encoding="utf-8"
    )
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(tmp_path)
    (tmp_path / "config.yaml").write_text("[not, a, mapping]", encoding="utf-8")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(tmp_path)


def test_unmigrated_legacy_plaintext_requires_record_migration(tmp_path):
    (tmp_path / ".credential-vault.json").write_text("{}", encoding="utf-8")
    binding = resolve_engine_binding(tmp_path)
    assert binding.needs_record_migration is True
    assert execution_blocked_reason(tmp_path) is not None


def test_migration_marker_requires_rebind(tmp_path):
    (tmp_path / MIGRATION_MARKER_FILENAME).write_text("{}", encoding="utf-8")
    binding = resolve_engine_binding(tmp_path)
    assert binding.retired_needs_rebind is True
    assert execution_blocked_reason(tmp_path) is not None


def test_migrated_universe_runs_after_sanctioned_rebind(
    platform_vault_env, executable_byo
):
    universe = platform_vault_env / "u-rebound"
    universe.mkdir()
    (universe / MIGRATION_MARKER_FILENAME).write_text("{}", encoding="utf-8")
    write_universe_config_fields(universe, engine_source="byo_api_key")
    _deposit(universe)

    assert resolve_engine_binding(universe).bound is True
    assert execution_blocked_reason(universe) is None


def test_snapshot_pins_opaque_ref_and_version(
    platform_vault_env, executable_byo
):
    universe = platform_vault_env / "u-snapshot"
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    _deposit(universe, value="sk-ant-api03-first")
    before = byo_credential_digest(universe)

    with pin_byo_execution_snapshot(universe) as snapshot:
        assert snapshot.credential_digest == before
        _deposit(universe, value="sk-ant-api03-second")
        assert byo_credential_digest(universe) != snapshot.credential_digest
