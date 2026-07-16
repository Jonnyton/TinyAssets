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
    # Provider-level eligibility: an Anthropic key serves claude-code, NOT codex.
    assert binding.eligible_providers == frozenset({"claude-code"})
    assert binding.is_eligible_for("claude-code") is True
    assert binding.is_eligible_for("codex") is False
    assert binding.serves_via_vault("claude-code") is True


def test_byo_openai_key_is_eligible_for_codex_only(tmp_path):
    udir = tmp_path / "u-byo-openai"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "openai",
        "secret_b64": base64.b64encode(b"sk-openai").decode("ascii"),
    }])
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert binding.eligible_providers == frozenset({"codex"})
    assert binding.is_eligible_for("codex") is True
    assert binding.is_eligible_for("claude-code") is False


def test_subscription_vault_row_is_not_founder_capacity(tmp_path):
    """Founder subscription custody is a BLOCKED lane (2026-07-02 custody
    research). A subscription vault row is NOT counted as capacity — a universe
    holding only one reads as idle-until-bound, and resolve does not crash."""
    udir = tmp_path / "u-sub"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription",
        "service": "claude",
        "oauth_token": "oauth-abc",
    }])
    write_universe_config_fields(udir, engine_source="subscription")
    binding = resolve_engine_binding(udir)  # must not raise
    assert binding.bound is False
    assert binding.capacity_kinds == ()
    assert binding.eligible_providers == frozenset()


def test_malformed_byo_unknown_service_fails_loud(tmp_path):
    """Finding 4: a BYO row whose service maps to no provider is not usable."""
    udir = tmp_path / "u-byo-badservice"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "nonsense",
        "secret_b64": base64.b64encode(b"k").decode("ascii"),
    }])
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_malformed_byo_empty_secret_fails_loud(tmp_path):
    """Finding 4: a BYO row with no decodable secret is not usable."""
    udir = tmp_path / "u-byo-nosecret"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",  # known service, but no secret at all
    }])
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_malformed_byo_alongside_valid_byo_stays_bound(tmp_path):
    """Finding 4 scoping: a broken BYO row must not DoS a universe with a real
    key — it is simply not counted, and eligibility reflects only the valid key."""
    udir = tmp_path / "u-byo-mixed"
    udir.mkdir()
    write_credential_vault(udir, [
        {
            "credential_type": "llm_api_key",
            "service": "anthropic",
            "secret_b64": base64.b64encode(b"sk-ant-real").decode("ascii"),
        },
        {"credential_type": "llm_api_key", "service": "nonsense"},
    ])
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert binding.eligible_providers == frozenset({"claude-code"})


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


# ---- runtime-backed sources are a DECLARED CHOICE, never executable in S5 ---
# The runtime-heartbeat capacity path was REMOVED (both latest-model gates,
# 2026-07-15): metadata.worker_id is forgeable via daemon_summon, updated_at is
# not a running-worker heartbeat, and there is no executor lease/routing. So a
# runtime-instance row can NEVER make a universe bound — the only executable
# founder lane in S5 is a validated BYO API key.


def _summon_runtime(base, uid, *, worker_id="w-forged", provider_name="claude-code"):
    """Create a runtime instance for *uid* (as `daemon_summon` would), optionally
    with a FORGED metadata.worker_id — proving a summoned row cannot buy liveness."""
    from tinyassets.daemon_server import (
        initialize_author_server,
        list_runtime_instances,
        spawn_runtime_instance,
        update_runtime_instance_status,
    )

    initialize_author_server(base)
    inst = spawn_runtime_instance(
        base, universe_id=uid, author_id="author-1",
        provider_name=provider_name, model_name="claude", created_by="test",
    )
    if worker_id:
        update_runtime_instance_status(
            base, instance_id=inst["instance_id"], status="provisioned",
            metadata_patch={"worker_id": worker_id},
        )
    return list_runtime_instances(base, universe_id=uid)[0]


@pytest.mark.parametrize(
    "source", ["host_daemon", "market_rented", "self_hosted_endpoint"],
)
def test_runtime_backed_source_is_never_bound(tmp_path, source):
    """Even WITH a provisioned runtime row carrying a worker_id, a runtime-backed
    declared source reads as idle — there is no real executor routing in S5."""
    uid = f"u-rt-{source}"
    udir = tmp_path / uid
    udir.mkdir()
    write_universe_config_fields(udir, engine_source=source)
    _summon_runtime(tmp_path, uid, worker_id="w-live")
    binding = resolve_engine_binding(udir)
    assert binding.bound is False
    assert binding.capacity_kinds == ()
    assert "not available yet" in binding.reason


def test_forged_worker_id_runtime_does_not_bind(tmp_path):
    """A user can set metadata.worker_id via daemon_summon — forging "liveness".
    It must NOT produce bound=True (the discriminator is gone entirely)."""
    uid = "u-forged"
    udir = tmp_path / uid
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="host_daemon")
    _summon_runtime(tmp_path, uid, worker_id="totally-forged-worker")
    binding = resolve_engine_binding(udir)
    assert binding.bound is False


def test_declared_host_daemon_with_only_byo_key_is_idle(tmp_path):
    """Lane-matching: a universe that SELECTED host_daemon must NOT be satisfied by
    a stray BYO key in the vault — the declared lane is not the BYO lane."""
    uid = "u-hostdaemon-strayvault"
    udir = tmp_path / uid
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-stray").decode("ascii"),
    }])
    write_universe_config_fields(udir, engine_source="host_daemon")
    binding = resolve_engine_binding(udir)
    assert binding.bound is False  # BYO key does NOT satisfy a host_daemon universe


# ---- resolve_engine_binding: MISCONFIGURED (BYO lane, no/broken credential) --


def test_declared_byo_without_key_fails_loud(tmp_path):
    udir = tmp_path / "u-badbyo"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="byo_api_key")
    with pytest.raises(EngineMisconfiguredError) as excinfo:
        resolve_engine_binding(udir)
    assert excinfo.value.engine_source == "byo_api_key"


def test_subscription_row_never_counts_and_never_crashes(tmp_path):
    """A subscription vault row (even a malformed one) is not founder capacity —
    it is ignored, so resolve returns idle-until-bound and never raises on it."""
    udir = tmp_path / "u-badsub2"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription",
        "service": "codex",
        "auth_json_b64": "not-base64!",
    }])
    binding = resolve_engine_binding(udir)  # must not raise
    assert binding.bound is False


def test_subscription_row_alongside_real_byo_binds_via_byo(tmp_path):
    """A subscription row does not add capacity; a real BYO key still binds and
    eligibility reflects only the BYO key."""
    udir = tmp_path / "u-mixed"
    udir.mkdir()
    write_credential_vault(udir, [
        {
            "credential_type": "llm_api_key",
            "service": "anthropic",
            "secret_b64": base64.b64encode(b"sk-ant-real").decode("ascii"),
        },
        {
            "credential_type": "llm_subscription",
            "service": "codex",
            "oauth_token": "oauth-x",
        },
    ])
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert "byo_api_key" in binding.capacity_kinds
    assert binding.eligible_providers == frozenset({"claude-code"})


def test_declared_subscription_source_is_idle_not_loud(tmp_path):
    """A legacy engine_source=subscription (retired lane) reads as idle, never
    a hard misconfiguration."""
    udir = tmp_path / "u-legacy-subsrc"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="subscription")
    binding = resolve_engine_binding(udir)  # must not raise
    assert binding.bound is False


def test_gemini_byo_row_is_not_founder_capacity(tmp_path):
    """Finding 2: gemini/groq/xai keys have no per-universe consumption wiring —
    a gemini-only vault does not read as bound (fails loud as an unusable BYO)."""
    udir = tmp_path / "u-gemini"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "gemini",
        "secret_b64": base64.b64encode(b"g-key").decode("ascii"),
    }])
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_gemini_byo_alongside_valid_openai_binds_via_codex(tmp_path):
    """A non-consumable gemini row is ignored; a real openai key still binds."""
    udir = tmp_path / "u-gemini-mixed"
    udir.mkdir()
    write_credential_vault(udir, [
        {
            "credential_type": "llm_api_key",
            "service": "openai",
            "secret_b64": base64.b64encode(b"sk-openai").decode("ascii"),
        },
        {
            "credential_type": "llm_api_key",
            "service": "gemini",
            "secret_b64": base64.b64encode(b"g-key").decode("ascii"),
        },
    ])
    binding = resolve_engine_binding(udir)
    assert binding.bound is True
    assert binding.eligible_providers == frozenset({"codex"})


# ---- Finding 4: malformed / unknown config declarations fail loud ----------


def test_corrupt_config_yaml_fails_loud(tmp_path):
    udir = tmp_path / "u-corruptcfg"
    udir.mkdir()
    (udir / "config.yaml").write_text("engine_source: [unterminated\n", encoding="utf-8")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_non_mapping_config_fails_loud(tmp_path):
    udir = tmp_path / "u-listcfg"
    udir.mkdir()
    (udir / "config.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_unknown_engine_source_fails_loud(tmp_path):
    udir = tmp_path / "u-unknownsrc"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="telepathy")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)


def test_absent_config_is_quiet_unbound(tmp_path):
    """A genuinely missing config file is a fresh unbound universe, not loud."""
    udir = tmp_path / "u-nocfg"
    udir.mkdir()
    binding = resolve_engine_binding(udir)  # must not raise
    assert binding.bound is False
    assert binding.engine_source == ""


def test_empty_config_file_is_quiet_unbound(tmp_path):
    udir = tmp_path / "u-emptycfg"
    udir.mkdir()
    (udir / "config.yaml").write_text("", encoding="utf-8")
    binding = resolve_engine_binding(udir)  # empty file = no overrides, not loud
    assert binding.bound is False


def test_malformed_vault_fails_loud(tmp_path):
    """A vault that won't parse is a misconfiguration, not silent unbound."""
    from tinyassets.credential_vault import credential_vault_path

    udir = tmp_path / "u-badvault"
    udir.mkdir()
    credential_vault_path(udir).write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(EngineMisconfiguredError):
        resolve_engine_binding(udir)
