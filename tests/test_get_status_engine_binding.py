"""S5 — get_status engine-binding onboarding surface + sanctioned bind lanes.

get_status honestly reports whether a universe has engine/daemon capacity bound
to it and, when it does not, surfaces the "bind an engine so your universe can
run" next step (design note 2026-07-15 gap G7). The sanctioned founder lanes are
BYO API key / self-hosted endpoint / market-rented / host_daemon; per-universe
subscription custody is a BLOCKED lane (2026-07-02 custody research) and
set_engine rejects it.
"""
from __future__ import annotations

import base64
import json

from tinyassets.credential_vault import write_credential_vault
from tinyassets.engine_binding import NON_AMBIENT_WORK_ENV
from tinyassets.universe_server import get_status


def _make_universe(tmp_path, monkeypatch, uid):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / uid
    udir.mkdir(parents=True, exist_ok=True)
    return udir


# ---- get_status: idle-until-bound honesty ---------------------------------


def test_status_reports_unbound_universe_idle_until_bound(tmp_path, monkeypatch):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    monkeypatch.delenv("TINYASSETS_BYO_VAULT_ENCRYPTED", raising=False)  # BYO dark
    _make_universe(tmp_path, monkeypatch, "u-idle")
    payload = json.loads(get_status(universe_id="u-idle"))

    eb = payload["engine_binding"]
    assert eb["bound"] is False
    # Flag OFF (default): ambient work still runs today, so workable stays True.
    assert eb["workable"] is True
    assert eb["non_ambient_gate"] is False
    # Honest Phase-1 guidance: hosted engines are NOT available yet (out-of-chat
    # deposit + KMS + executor are Phase 2), and no raw key travels over the chat.
    steps = " ".join(payload["actionable_next_steps"]).lower()
    assert "not available yet" in steps
    assert "phase 2" in steps
    assert "chatbot" in steps  # raw key must never travel over the relay
    assert "your own device" in steps
    # Finding 2 regression: with the non-ambient gate OFF the caveat must NOT
    # falsely claim the universe is idle-until-bound (ambient work runs today).
    combined = " ".join(payload["caveats"]).lower()
    assert "idle-until-bound" not in combined
    assert "ambient" in combined and "workable" in combined


def test_status_unbound_with_gate_on_is_not_workable(tmp_path, monkeypatch):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    _make_universe(tmp_path, monkeypatch, "u-idle2")
    payload = json.loads(get_status(universe_id="u-idle2"))

    eb = payload["engine_binding"]
    assert eb["bound"] is False
    assert eb["non_ambient_gate"] is True
    # Gate on → an unbound universe is genuinely idle-until-bound.
    assert eb["workable"] is False
    assert "idle" in eb["note"].lower()


def test_status_reports_bound_universe(tmp_path, monkeypatch):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")  # executable BYO on
    import tinyassets.credential_vault as _cv
    import tinyassets.engine_binding as _eb
    monkeypatch.setattr(_eb, "_vault_encryption_capability_attested", lambda *a, **k: True)
    monkeypatch.setattr(_eb, "_sandbox_execution_attested", lambda: True)
    # Round-18 #1: anthropic custody sanctioned so the attested key can bind.
    monkeypatch.setattr(
        _cv, "_SANCTIONED_CUSTODY_SERVICES", frozenset({"anthropic"}),
    )
    udir = _make_universe(tmp_path, monkeypatch, "u-bound")
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(
            ("sk-ant-api03-" + "A" * 40).encode()).decode("ascii"),
    }])
    from tinyassets.config import write_universe_config_fields
    write_universe_config_fields(udir, engine_source="byo_api_key")

    payload = json.loads(get_status(universe_id="u-bound"))
    eb = payload["engine_binding"]
    assert eb["bound"] is True
    assert "byo_api_key" in eb["capacity_kinds"]
    # A bound universe does not nag with the bind next step.
    steps = " ".join(payload["actionable_next_steps"]).lower()
    assert "bind an engine so your universe can run" not in steps


def test_status_reports_misconfigured_binding_without_crashing(tmp_path, monkeypatch):
    """A declared-but-broken binding is reported (not raised) by get_status."""
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = _make_universe(tmp_path, monkeypatch, "u-broken")
    from tinyassets.config import write_universe_config_fields
    # Declared byo_api_key (vault source) with NO vault key = genuinely broken.
    write_universe_config_fields(udir, engine_source="byo_api_key")

    payload = json.loads(get_status(universe_id="u-broken"))
    eb = payload["engine_binding"]
    assert eb["bound"] is False
    assert eb.get("misconfigured") is True
    combined = " ".join(payload["caveats"]).lower()
    assert "misconfigured" in combined


def test_engine_binding_is_in_status_contract(tmp_path, monkeypatch):
    _make_universe(tmp_path, monkeypatch, "u-contract")
    payload = json.loads(get_status(universe_id="u-contract"))
    assert "engine_binding" in payload
    assert isinstance(payload["engine_binding"], dict)


def test_r21_4_status_pre_migration_says_run_the_migration(tmp_path, monkeypatch):
    """Round-21 #4: a universe with a RAW llm_subscription record present →
    needs_record_migration; get_status tells the operator to RUN the migration."""
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = _make_universe(tmp_path, monkeypatch, "u-pre-mig")
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription", "service": "claude",
        "oauth_token": "legacy",
    }])
    payload = json.loads(get_status(universe_id="u-pre-mig"))
    eb = payload["engine_binding"]
    assert eb["needs_record_migration"] is True
    assert eb["retired_needs_rebind"] is False
    assert eb["needs_migration"] is True  # umbrella still true (not workable)
    steps = " ".join(payload["actionable_next_steps"]).lower()
    assert "run" in steps and "migration" in steps  # remediation = run the migration


def test_r21_4_status_post_migration_says_rebind_not_rerun(tmp_path, monkeypatch):
    """Round-21 #4: a MARKER-ONLY universe (migration already done, raw record
    removed) → retired_needs_rebind; get_status tells the operator to RE-BIND and must
    NOT tell them to re-run the already-completed migration (the pre-r21 bug)."""
    from tinyassets.credential_vault import quarantine_legacy_subscription_records

    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = _make_universe(tmp_path, monkeypatch, "u-post-mig")
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription", "service": "claude",
        "oauth_token": "legacy",
    }])
    quarantine_legacy_subscription_records(udir)  # raw record → non-secret marker

    payload = json.loads(get_status(universe_id="u-post-mig"))
    eb = payload["engine_binding"]
    assert eb["retired_needs_rebind"] is True
    assert eb["needs_record_migration"] is False
    assert eb["needs_migration"] is True  # umbrella still true (fail closed)
    assert eb["bound"] is False
    steps = " ".join(payload["actionable_next_steps"]).lower()
    caveats = " ".join(payload["caveats"]).lower()
    # Remediation = RE-BIND, and explicitly NOT "re-run the migration".
    assert "re-bind" in steps or "rebind" in steps or "write_graph target=engine" in steps
    assert "do not re-run" in steps or "do not re-run" in caveats or "already" in caveats


def test_get_status_reports_host_daemon_choice_as_idle(tmp_path, monkeypatch):
    """A host_daemon declaration reads as idle (declared choice, not executable in
    S5) — get_status surfaces it as unbound, not misconfigured, not crashing."""
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = _make_universe(tmp_path, monkeypatch, "u-hostdaemon-status")
    from tinyassets.config import write_universe_config_fields
    write_universe_config_fields(udir, engine_source="host_daemon")

    payload = json.loads(get_status(universe_id="u-hostdaemon-status"))
    eb = payload["engine_binding"]
    assert eb["bound"] is False
    assert eb.get("misconfigured") is not True


# ---- set_engine: subscription is a BLOCKED lane (custody note compliance) --


def _setup_set_engine(tmp_path, monkeypatch, uid):
    from tinyassets.api import universe as uni

    udir = tmp_path / uid
    udir.mkdir()
    monkeypatch.setattr(uni, "_request_universe", lambda universe_id="": uid)
    monkeypatch.setattr(uni, "_universe_dir", lambda _uid: udir)
    return uni, udir


def test_set_engine_subscription_is_rejected_with_guidance(tmp_path, monkeypatch):
    """Per-universe subscription custody is a BLOCKED lane (2026-07-02 custody
    research). set_engine must REJECT it with the sanctioned lanes and store
    nothing (no shims — the surface is removed)."""
    uni, udir = _setup_set_engine(tmp_path, monkeypatch, "u-sub-blocked")
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "subscription",
        "service": "claude",
        "oauth_token": "oauth-SECRET-abc",
    })))
    assert "error" in out
    assert out.get("status") != "engine_set"
    guidance = json.dumps(out).lower()
    # Advertises the NON-SECRET sanctioned lanes (no raw-key solicitation, F3).
    assert "self_hosted_endpoint" in guidance or "endpoint" in guidance
    assert "market_rented" in guidance or "market" in guidance
    assert "host_daemon" in guidance or "own device" in guidance
    assert "api_key" not in guidance  # never solicit a raw key
    # Nothing was persisted — no phantom subscription binding, no token leak.
    from tinyassets.credential_vault import load_credential_vault
    assert load_credential_vault(udir) == []
    assert "oauth-SECRET-abc" not in guidance


def test_set_engine_byo_raw_key_refused_through_chat(tmp_path, monkeypatch):
    """C3: any raw BYO key deposit through the chatbot is refused (no flag unlocks
    it) and stores nothing — even the encryption gate 'on'."""
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    uni, udir = _setup_set_engine(tmp_path, monkeypatch, "u-byo-raw")
    out = json.loads(uni._action_set_engine(inputs_json=json.dumps({
        "engine_source": "byo_api_key", "service": "anthropic",
        "api_key": "sk-ant-api03-" + "A" * 40,
    })))
    assert "error" in out
    assert out.get("status") != "engine_set"
    err = json.dumps(out).lower()
    assert "chatbot" in err or "out-of-chat" in err
    from tinyassets.credential_vault import load_credential_vault
    assert load_credential_vault(udir) == []


def test_legacy_subscription_row_reads_not_capacity_and_no_crash(tmp_path, monkeypatch):
    """A legacy llm_subscription vault row (from the removed lane) must read as
    NOT capacity and MUST NOT crash resolve."""
    from tinyassets.engine_binding import resolve_engine_binding

    udir = tmp_path / "u-legacy-sub"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription",
        "service": "claude",
        "oauth_token": "oauth-legacy",
    }])
    binding = resolve_engine_binding(udir)  # must not raise
    assert binding.bound is False
    assert binding.capacity_kinds == ()
