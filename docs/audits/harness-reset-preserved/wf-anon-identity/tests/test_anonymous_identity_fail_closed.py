"""Fail-closed guards for unresolved connector identity.

An OAuth-backed anonymous request has neither a principal nor an implicit
universe scope.  Host-local defaults and mutable database rows are not
authority and must not make operational state observable.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider


class _AnonymousOAuthProvider(AuthProvider):
    """Production optional-auth shape: public reads, identity-gated writes."""

    def resolve_token(self, token: str):  # noqa: ANN201
        return None

    def is_auth_required(self) -> bool:
        return False

    def resolve_always_writes(self) -> bool:
        return True

    def register_client(self, metadata: dict) -> dict:
        return {}

    def create_authorization(self, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        return ""

    def exchange_code(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        return None


@pytest.fixture(autouse=True)
def _anonymous_oauth_request():
    set_provider(_AnonymousOAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


@pytest.fixture
def forged_host_state(tmp_path, monkeypatch):
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.storage import db_path

    host_universe = "u-host-private-state"
    (tmp_path / host_universe).mkdir()
    (tmp_path / host_universe / "PROGRAM.md").write_text(
        "A genuinely public premise.",
        encoding="utf-8",
    )
    (tmp_path / ".active_universe").write_text(host_universe, encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", host_universe)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "user_host_workos_principal")
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host-daemon-owner")

    initialize_author_server(tmp_path)
    # Direct DML simulates an attacker forging both the anonymous sentinel and
    # the ambient host principal into the mutable home-binding table.
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.executemany(
            "INSERT INTO founder_home (founder_sub, universe_id, created_at) "
            "VALUES (?, ?, 0)",
            [
                ("anonymous", host_universe),
                ("user_host_workos_principal", host_universe),
            ],
        )
    return host_universe


def test_unresolved_oauth_identity_ignores_ambient_host_principal(
    forged_host_state,
) -> None:
    from tinyassets.api import permissions
    from tinyassets.api.engine_helpers import _current_actor

    assert permissions.current_actor_id() == "anonymous"
    assert _current_actor() == "anonymous"


def test_raw_dml_and_host_defaults_cannot_forge_implicit_universe_scope(
    forged_host_state,
) -> None:
    from tinyassets.api.helpers import _request_universe
    from tinyassets.api.status import _resolve_entry_universe
    from tinyassets.api.universe import _universe_impl

    assert _request_universe("") == ""
    assert _resolve_entry_universe("") == ("", False)

    omitted = json.loads(_universe_impl(action="inspect"))
    assert omitted["error"] == "universe_scope_required"
    assert omitted["universe_id"] is None

    # Visibility is a separate boundary: an explicitly named public universe
    # remains resolvable for anonymous content reads.
    assert _request_universe(forged_host_state) == forged_host_state


def test_anonymous_status_returns_no_principal_scope_or_host_state(
    forged_host_state,
    monkeypatch,
) -> None:
    from tinyassets.api import status

    def _host_state_was_touched(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        raise AssertionError("anonymous status crossed into host state")

    monkeypatch.setattr(status, "_resolve_entry_universe", _host_state_was_touched)
    monkeypatch.setattr(status, "_compute_supervisor_liveness", _host_state_was_touched)
    monkeypatch.setattr(status, "_provider_auth_snapshot", _host_state_was_touched)

    payload = json.loads(status.get_status())

    assert payload["authentication"] == {
        "status": "unauthenticated",
        "principal": None,
        "universe_scope": None,
    }
    forbidden = {
        "active_host",
        "auto_ship_health",
        "evidence",
        "open_brain",
        "per_provider_cooldown_remaining",
        "provider_auth",
        "release_state",
        "sandbox_status",
        "session_boundary",
        "storage_utilization",
        "supervisor_liveness",
        "tier_routing_policy",
        "universe_id",
    }
    assert forbidden.isdisjoint(payload)
    serialized = json.dumps(payload)
    assert forged_host_state not in serialized
    assert "user_host_workos_principal" not in serialized
    assert "host-daemon-owner" not in serialized


def test_anonymous_public_content_read_redacts_daemon_liveness(
    forged_host_state,
) -> None:
    from tinyassets.api.universe import _universe_impl

    inspected = json.loads(_universe_impl(
        action="inspect",
        universe_id=forged_host_state,
    ))
    assert inspected["universe_id"] == forged_host_state
    assert inspected["premise"] == "A genuinely public premise."
    assert "daemon" not in inspected

    listed = json.loads(_universe_impl(action="list"))
    row = next(item for item in listed["universes"] if item["id"] == forged_host_state)
    assert {"phase", "phase_human", "staleness", "last_activity_at", "accept_rate"}.isdisjoint(row)
