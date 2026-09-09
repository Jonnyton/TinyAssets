"""Connect requests follow current universe authority, not a surviving binding row."""

import sqlite3

import pytest

from tests.test_open_serving_bind import _CONN_ID, _GRANT_ID, _bound_and_serving
from tinyassets.api.pending_requests import _serving_llm_bound


def test_current_open_connection_satisfies_the_connect_request(tmp_path, monkeypatch):
    _bound_and_serving(tmp_path, monkeypatch)
    assert _serving_llm_bound(tmp_path, "u-owner", "owner-1") is True
    assert _serving_llm_bound(tmp_path, "u-owner", "someone-else") is False


@pytest.mark.parametrize("change", ["revoke_grant", "rotate_reference"])
def test_a_surviving_binding_does_not_hide_a_broken_connection_request(
    tmp_path, monkeypatch, change
):
    from tinyassets.provider_serving_binding import resolve_serving_agent_binding
    from tinyassets.storage.outbound_connections import ConnectionLedger

    _bound_and_serving(tmp_path, monkeypatch)
    assert _serving_llm_bound(tmp_path, "u-owner", "owner-1") is True
    if change == "revoke_grant":
        ledger = ConnectionLedger(
            tmp_path / "outbound.db", verify_authenticated_principal=lambda: "owner-1"
        )
        ledger.revoke_grant(_GRANT_ID)
    else:
        with sqlite3.connect(tmp_path / "outbound.db") as conn:
            conn.execute(
                "UPDATE outbound_connections SET credential_ref = ? WHERE connection_id = ?",
                ("vault://http/replaced", _CONN_ID),
            )
    # Reproduce the exact old premise: the serving row still exists.
    assert resolve_serving_agent_binding(
        tmp_path, universe_id="u-owner", owner_user_id="owner-1"
    )
    assert _serving_llm_bound(tmp_path, "u-owner", "owner-1") is False


def test_connect_detection_uses_explicit_universe_authority(tmp_path, monkeypatch):
    from types import SimpleNamespace

    calls = []

    def resolve(base, **kwargs):
        calls.append((base, kwargs))
        return SimpleNamespace(provider="a-future-provider")

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.resolve_current_serving_provider_authority",
        resolve,
    )
    assert _serving_llm_bound(tmp_path, "u-owner", "owner-1") is True
    assert calls == [(tmp_path, {
        "universe_dir": tmp_path / "u-owner",
        "universe_id": "u-owner",
        "owner_user_id": "owner-1",
    })]


def test_subscription_custody_loss_restores_the_actual_request_rail(tmp_path, monkeypatch):
    from tests.test_provider_serving_binding import _seed_universe
    from tinyassets.api.pending_requests import list_requests
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.daemon_server import grant_universe_access
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir, agent = _seed_universe(tmp_path)
    grant_universe_access(
        tmp_path, universe_id="u-owner", actor_id="owner-1",
        permission="admin", granted_by="owner-1",
    )
    connected = bind_serving_provider(
        base_path=tmp_path, universe_dir=udir, owner_user_id="owner-1",
        universe_id="u-owner", agent_binding_id=agent["agent_binding_id"],
        expected_revision=1, provider="codex",
    )
    set_serving(
        base_path=tmp_path, universe_dir=udir, owner_user_id="owner-1",
        universe_id="u-owner", agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"], enabled=True,
    )
    identity = Identity(user_id="owner-1", username="owner-1", capabilities=["read"])
    with identity_context(identity):
        assert list_requests(universe_id="u-owner")["pending"] == []
        # Test-only vault contents; no real user credential or provider call.
        write_credential_vault(udir, [], owner_user_id="owner-1", universe_id="u-owner")
        rail = list_requests(universe_id="u-owner")
        again = list_requests(universe_id="u-owner")
    assert rail["pending"][0]["request_id"] == "sys_connect_llm"
    assert rail["pending"][0]["sticky"] is True
    assert rail["pending"] == again["pending"], "polling must not create duplicate asks"
