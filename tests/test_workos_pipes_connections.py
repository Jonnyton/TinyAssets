from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.api import cloud_connections
from tinyassets.storage.outbound_connections import ConnectionLedger
from tinyassets.workos_pipes import ConnectedAccount, WorkOSPipesClient, WorkOSPipesError


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self._payload


def test_workos_client_uses_exact_owner_paths_and_redacts_contract():
    calls: list[tuple[str, str, bytes | None]] = []

    def request(req, timeout):
        del timeout
        calls.append((req.method, req.full_url, req.data))
        if req.method == "POST" and req.full_url.endswith("/authorize"):
            return _Response({"url": "https://api.workos.com/data-integrations/github/authorize-redirect"})
        if req.method == "GET":
            return _Response(
                {"id": "data_installation_1", "state": "connected", "scopes": ["repo"]}
            )
        return _Response({"active": True, "credential": {"value": "never-in-response"}})

    client = WorkOSPipesClient("sk_test_hidden", request=request)
    assert client.authorization_url(
        user_id="user_123", return_to="https://tinyassets.io/mcp"
    ).startswith("https://")
    assert client.connected_account(user_id="user_123") == ConnectedAccount(
        state="connected", account_id="data_installation_1", scopes=("repo",)
    )
    assert client.vend_credential(user_id="user_123") == "never-in-response"
    assert calls[0][0] == "POST"
    assert b"user_123" in (calls[0][2] or b"")
    assert all("sk_test_hidden" not in str(call) for call in calls)


def test_workos_client_rejects_invalid_user_and_url():
    client = WorkOSPipesClient("sk_test_hidden", request=lambda *_args, **_kwargs: None)
    with pytest.raises(WorkOSPipesError):
        client.connected_account(user_id="not-a-workos-id")
    with pytest.raises(WorkOSPipesError):
        client.authorization_url(user_id="user_123", return_to="http://insecure")


def test_reconcile_is_owner_scoped_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(cloud_connections, "_actor", lambda: "user_123")
    monkeypatch.setattr(cloud_connections, "_request_universe", lambda _uid: "universe_1")
    monkeypatch.setattr(cloud_connections, "_base_path", lambda: tmp_path)

    class _Permissions:
        @staticmethod
        def universe_access_allows(_uid, *, write):
            return write is True

        @staticmethod
        def is_authenticated_request():
            return True

        @staticmethod
        def current_actor_id():
            return "user_123"

    monkeypatch.setattr(
        "tinyassets.api.permissions.universe_access_allows",
        _Permissions.universe_access_allows,
    )

    class _Client:
        def connected_account(self, *, user_id):
            assert user_id == "user_123"
            return ConnectedAccount("connected", "data_installation_1", ("repo",))

        def authorization_url(self, **_kwargs):
            return "https://api.workos.com/return"

    monkeypatch.setattr(cloud_connections, "WorkOSPipesClient", _Client)
    first = cloud_connections.cloud_connections(
        action="reconcile",
        universe_id="universe_1",
        payload={"destination": "Jonnyton/TinyAssets", "user_id": "user_attacker"},
    )
    second = cloud_connections.cloud_connections(
        action="reconcile",
        universe_id="universe_1",
        payload={"destination": "Jonnyton/TinyAssets"},
    )
    assert first["status"] == second["status"] == "connected"
    assert first["grant_id"] == second["grant_id"]
    assert "credential_ref" not in first
    ledger = ConnectionLedger(Path(tmp_path) / "outbound.db")
    assert len(ledger.list_grants(owner_user_id="user_123", universe_id="universe_1")) == 1
