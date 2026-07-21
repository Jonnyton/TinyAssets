"""Direct coverage for the surviving non-ambient engine-binding gate.

The retired platform ``cloud_worker`` used to drive these assertions.  The
security boundary itself lives in :mod:`tinyassets.engine_binding`, so these
tests exercise that boundary without recreating a platform executor.
"""

from __future__ import annotations

import pytest

import tinyassets.engine_binding as engine_binding
from tinyassets.config import write_universe_config_fields
from tinyassets.credential_broker import deposit_engine_api_key
from tinyassets.engine_binding import (
    BYO_VAULT_ENCRYPTED_ENV,
    NON_AMBIENT_WORK_ENV,
    EngineMisconfiguredError,
    non_ambient_work_enabled,
    resolve_engine_binding,
)


@pytest.fixture
def attested_byo(monkeypatch):
    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)


def _bound_anthropic_universe(root, name: str = "u-bound"):
    universe = root / name
    universe.mkdir()
    write_universe_config_fields(universe, engine_source="byo_api_key")
    deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service="anthropic",
        api_key="sk-ant-api03-direct-gate-test",
    )
    return universe


def test_declared_broken_binding_fails_closed_even_with_rollout_flag_off(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    write_universe_config_fields(tmp_path, engine_source="byo_api_key")

    assert non_ambient_work_enabled() is False
    with pytest.raises(EngineMisconfiguredError, match="no active broker-backed"):
        resolve_engine_binding(tmp_path)


def test_unbound_universe_has_no_executable_or_provider_capacity(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")

    binding = resolve_engine_binding(tmp_path)

    assert non_ambient_work_enabled() is True
    assert binding.bound is False
    assert binding.capacity_kinds == ()
    assert binding.eligible_providers == frozenset()
    assert binding.is_eligible_for("claude-code") is False
    assert binding.is_eligible_for("codex") is False


@pytest.mark.parametrize(
    "engine_source", ["host_daemon", "market_rented", "self_hosted_endpoint"]
)
def test_declared_runtime_route_is_not_local_executable_capacity(
    tmp_path, engine_source
):
    write_universe_config_fields(tmp_path, engine_source=engine_source)

    binding = resolve_engine_binding(tmp_path)

    assert binding.bound is False
    assert binding.capacity_kinds == ()
    assert "executor route is not available" in binding.reason


def test_provider_pinned_route_rejects_a_nonmatching_provider(
    platform_vault_env, attested_byo
):
    universe = _bound_anthropic_universe(platform_vault_env)

    binding = resolve_engine_binding(universe)

    assert binding.bound is True
    assert binding.is_eligible_for("claude-code") is True
    assert binding.is_eligible_for("codex") is False


def test_byo_bound_universe_is_executable_only_when_fully_attested(
    platform_vault_env, attested_byo
):
    universe = _bound_anthropic_universe(platform_vault_env)

    binding = resolve_engine_binding(universe)

    assert binding.bound is True
    assert binding.capacity_kinds == ("byo_api_key",)
    assert binding.eligible_providers == frozenset({"claude-code"})


def test_missing_sandbox_attestation_keeps_byo_binding_ineligible(
    platform_vault_env, monkeypatch
):
    monkeypatch.setenv(BYO_VAULT_ENCRYPTED_ENV, "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: False)
    universe = _bound_anthropic_universe(platform_vault_env)

    binding = resolve_engine_binding(universe)

    assert binding.bound is False
    assert binding.capacity_kinds == ()
    assert "sandbox must all pass" in binding.reason


def test_unknown_engine_source_fails_loud(tmp_path):
    write_universe_config_fields(tmp_path, engine_source="ambient_magic")

    with pytest.raises(EngineMisconfiguredError, match="unknown engine_source"):
        resolve_engine_binding(tmp_path)
