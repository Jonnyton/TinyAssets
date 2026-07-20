"""get_status projection for broker-backed engine bindings."""

from __future__ import annotations

import json

from tinyassets.config import write_universe_config_fields
from tinyassets.credential_broker import MIGRATION_MARKER_FILENAME, deposit_engine_api_key
from tinyassets.engine_binding import NON_AMBIENT_WORK_ENV
from tinyassets.universe_server import get_status


def _make_universe(root, monkeypatch, uid):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    universe = root / uid
    universe.mkdir(parents=True, exist_ok=True)
    return universe


def test_status_reports_unbound_universe(tmp_path, monkeypatch):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    _make_universe(tmp_path, monkeypatch, "u-idle")
    payload = json.loads(get_status(universe_id="u-idle"))
    binding = payload["engine_binding"]
    assert binding["bound"] is False
    assert binding["workable"] is False
    assert binding["non_ambient_gate"] is False
    assert "idle" in binding["note"].lower()
    assert "ambient" not in " ".join(payload["caveats"]).lower()


def test_status_gate_on_makes_unbound_universe_idle(tmp_path, monkeypatch):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    _make_universe(tmp_path, monkeypatch, "u-idle")
    binding = json.loads(get_status(universe_id="u-idle"))["engine_binding"]
    assert binding["bound"] is False
    assert binding["workable"] is False
    assert "idle" in binding["note"].lower()


def test_status_reports_real_broker_binding(
    platform_vault_env, monkeypatch
):
    import tinyassets.engine_binding as engine_binding

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(platform_vault_env))
    monkeypatch.setenv("TINYASSETS_BYO_VAULT_ENCRYPTED", "1")
    monkeypatch.setattr(engine_binding, "_sandbox_execution_attested", lambda: True)
    universe = _make_universe(platform_vault_env, monkeypatch, "u-bound")
    write_universe_config_fields(universe, engine_source="byo_api_key")
    deposit_engine_api_key(
        universe_id=universe.name,
        founder_id="founder-1",
        service="anthropic",
        api_key="sk-ant-api03-" + "A" * 40,
    )

    binding = json.loads(get_status(universe_id=universe.name))["engine_binding"]

    assert binding["bound"] is True
    assert binding["capacity_kinds"] == ["byo_api_key"]


def test_status_reports_declared_missing_binding_without_crashing(
    tmp_path, monkeypatch
):
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    universe = _make_universe(tmp_path, monkeypatch, "u-broken")
    write_universe_config_fields(universe, engine_source="byo_api_key")
    binding = json.loads(get_status(universe_id=universe.name))["engine_binding"]
    assert binding["bound"] is False
    assert binding["misconfigured"] is True
    assert binding["workable"] is False


def test_status_distinguishes_pre_and_post_migration(tmp_path, monkeypatch):
    pre = _make_universe(tmp_path, monkeypatch, "u-pre")
    (pre / ".credential-vault.json").write_text("{}", encoding="utf-8")
    pre_binding = json.loads(get_status(universe_id=pre.name))["engine_binding"]
    assert pre_binding["needs_record_migration"] is True

    post = _make_universe(tmp_path, monkeypatch, "u-post")
    (post / MIGRATION_MARKER_FILENAME).write_text("{}", encoding="utf-8")
    post_binding = json.loads(get_status(universe_id=post.name))["engine_binding"]
    assert post_binding["retired_needs_rebind"] is True
    assert post_binding["needs_record_migration"] is False


def test_status_reports_inert_host_daemon_choice(tmp_path, monkeypatch):
    universe = _make_universe(tmp_path, monkeypatch, "u-host")
    write_universe_config_fields(universe, engine_source="host_daemon")
    binding = json.loads(get_status(universe_id=universe.name))["engine_binding"]
    assert binding["bound"] is False
    assert binding.get("misconfigured") is not True
