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


# ---- config-only CHOICE is NOT executable capacity → idle-until-bound -----
# A bare engine_source value persists a *choice*; the runtime that consumes work
# is provisioned separately. Without a live runtime instance, these must read as
# idle-until-bound (bound=False) so the non-ambient gate does NOT spawn for them.


@pytest.mark.parametrize("source,extra", [
    ("self_hosted_endpoint", {"engine_endpoint": "http://localhost:11434"}),
    ("self_hosted_endpoint", {}),          # even an empty endpoint: still no runtime
    ("market_rented", {"market_model": "glm-5.2"}),
    ("market_rented", {}),                  # empty model: still no runtime
    ("host_daemon", {}),
])
def test_config_only_choice_is_idle_until_bound(tmp_path, source, extra):
    udir = tmp_path / f"u-{source}-{len(extra)}"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source=source, **extra)
    binding = resolve_engine_binding(udir)
    assert binding.bound is False, f"{source} config-only must not count as bound"
    assert binding.capacity_kinds == ()
    assert binding.engine_source == source


# ---- config source WITH a live runtime instance → bound -------------------


def _assign_runtime(base, uid, *, status="provisioned"):
    from tinyassets.daemon_server import (
        initialize_author_server,
        retire_runtime_instance,
        spawn_runtime_instance,
    )

    initialize_author_server(base)
    inst = spawn_runtime_instance(
        base, universe_id=uid, author_id="author-1",
        provider_name="claude-code", model_name="claude", created_by="test",
    )
    if status == "retired":
        retire_runtime_instance(base, instance_id=inst["instance_id"])
    return inst


@pytest.mark.parametrize(
    "source", ["host_daemon", "market_rented", "self_hosted_endpoint"],
)
def test_config_source_with_live_runtime_is_bound(tmp_path, source):
    uid = f"u-rt-{source}"
    udir = tmp_path / uid
    udir.mkdir()
    write_universe_config_fields(udir, engine_source=source)
    _assign_runtime(tmp_path, uid)
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert f"runtime:{source}" in binding.capacity_kinds


def test_retired_runtime_instance_does_not_count(tmp_path):
    uid = "u-rt-retired"
    udir = tmp_path / uid
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="host_daemon")
    _assign_runtime(tmp_path, uid, status="retired")
    binding = resolve_engine_binding(udir)
    assert binding.bound is False


# ---- resolve_engine_binding: MISCONFIGURED (vault source, no credential) ---
# Only the vault-backed sources fail loud when declared without a credential —
# those bind acts deposit atomically, so a declared-without-credential state is
# genuinely broken (Hard Rule #8). Runtime-backed config choices do NOT fail
# loud (they are legitimately not-yet-provisioned; see idle-until-bound above).


def test_declared_byo_without_key_fails_loud(tmp_path):
    udir = tmp_path / "u-badbyo"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="byo_api_key")
    with pytest.raises(EngineMisconfiguredError) as excinfo:
        resolve_engine_binding(udir)
    assert excinfo.value.engine_source == "byo_api_key"


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
