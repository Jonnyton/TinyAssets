from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tinyassets.storage.outbound_connections import (
    ConnectionLedger,
    CredentialBlindBroker,
    GrantResolutionError,
    ProxyRequestError,
)

ROOT = Path(__file__).resolve().parents[1]


def test_connection_and_per_universe_grant_persist_with_revocation(tmp_path):
    db_path = tmp_path / "boundary.db"
    ledger = ConnectionLedger(db_path)

    connection = ledger.create_connection(
        connection_id="conn-github",
        owner_user_id="user-1",
        connection_class="outbound-mcp",
        scopes=("pull_requests:write",),
        provider="github",
        destination="github.com/acme/widgets",
        credential_ref="vault://github/user-1",
    )
    grant = ledger.grant_connection(
        grant_id="grant-u1",
        connection_id=connection.connection_id,
        owner_user_id="user-1",
        universe_id="universe-1",
    )

    reopened = ConnectionLedger(db_path)
    assert reopened.get_connection("conn-github") == connection
    assert reopened.get_grant("grant-u1") == grant
    assert reopened.revoke_grant("grant-u1", revoked_at=123.0) is True
    assert reopened.get_grant("grant-u1").revoked_at == 123.0


def test_migration_010_persists_connections_grants_and_connector_artifacts():
    migration = (
        ROOT
        / "prototype"
        / "full-platform-v0"
        / "migrations"
        / "010_outbound_boundary.sql"
    )
    sql = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE boundary.connections" in sql
    assert "CREATE TABLE boundary.connection_grants" in sql
    assert "CREATE TABLE boundary.connector_artifacts" in sql
    assert "CREATE TABLE boundary.connector_artifact_edges" in sql


def _grant_github_connection(
    ledger: ConnectionLedger,
    *,
    connection_id: str = "conn-github",
    grant_id: str = "grant-github",
) -> None:
    ledger.create_connection(
        connection_id=connection_id,
        owner_user_id="user-1",
        connection_class="pull-request-writer",
        scopes=("pull_requests:write",),
        provider="github",
        destination="github.com/acme/widgets",
        credential_ref=f"vault://github/{connection_id}",
    )
    ledger.grant_connection(
        grant_id=grant_id,
        connection_id=connection_id,
        owner_user_id="user-1",
        universe_id="universe-1",
    )


def test_resolve_scoped_proxy_uses_only_current_exact_grant(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    _grant_github_connection(ledger)
    dispatched: list[tuple[str, str, object]] = []

    proxy = ledger.resolve_scoped_proxy(
        owner_user_id="user-1",
        universe_id="universe-1",
        connection_class="pull-request-writer",
        dispatch=lambda grant_id, verb, request: dispatched.append(
            (grant_id, verb, request)
        )
        or {"status": "created"},
    )

    assert proxy.provider == "github"
    assert proxy.destination == "github.com/acme/widgets"
    assert proxy.request("pull_requests:write", {"title": "Ship"}) == {
        "status": "created"
    }
    assert dispatched == [
        ("grant-github", "pull_requests:write", {"title": "Ship"})
    ]


@pytest.mark.parametrize("case", ["absent", "revoked", "ambiguous"])
def test_resolve_scoped_proxy_fails_closed_without_fallback(tmp_path, case):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    if case != "absent":
        _grant_github_connection(ledger)
    if case == "revoked":
        ledger.revoke_grant("grant-github")
    if case == "ambiguous":
        _grant_github_connection(
            ledger,
            connection_id="conn-github-2",
            grant_id="grant-github-2",
        )

    with pytest.raises(GrantResolutionError, match=case):
        ledger.resolve_scoped_proxy(
            owner_user_id="user-1",
            universe_id="universe-1",
            connection_class="pull-request-writer",
            dispatch=lambda *_: pytest.fail(
                "ambient or maintainer fallback must not dispatch"
            ),
        )


def test_adapter_cannot_recover_secret_from_state_environment_metadata_or_errors(
    tmp_path,
):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    _grant_github_connection(ledger)
    secret = "raw-secret-never-visible-to-adapter"
    audit: list[dict[str, object]] = []

    def explode(*, credential, **_):
        raise RuntimeError(f"provider echoed {credential}")

    broker = CredentialBlindBroker(
        ledger,
        resolve_credential=lambda credential_ref: (
            secret if credential_ref == "vault://github/conn-github" else ""
        ),
        network_request=explode,
        audit=audit.append,
    )
    proxy = ledger.resolve_scoped_proxy(
        owner_user_id="user-1",
        universe_id="universe-1",
        connection_class="pull-request-writer",
        dispatch=broker.dispatch,
    )
    graph_state = {"connection": proxy}
    request_metadata = {
        "provider": proxy.provider,
        "destination": proxy.destination,
        "scopes": proxy.scopes,
    }

    with pytest.raises(ProxyRequestError) as raised:
        proxy.request("pull_requests:write", {"title": "Ship"})

    adapter_observations = json.dumps(
        {
            "state": graph_state,
            "environment": dict(os.environ),
            "request_metadata": request_metadata,
            "proxy_error": str(raised.value),
            "proxy_repr": repr(proxy),
            "audit": audit,
        },
        default=repr,
        sort_keys=True,
    )
    assert secret not in adapter_observations
    assert "vault://github/conn-github" not in adapter_observations
    assert audit == [
        {
            "event": "outbound_proxy_error",
            "grant_id": "grant-github",
            "provider": "github",
            "destination": "github.com/acme/widgets",
            "verb": "pull_requests:write",
            "reason": "destination request failed",
        }
    ]


def test_connector_definition_and_mcp_config_are_attributed_remixable_artifacts(
    tmp_path,
):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    original = ledger.create_connector_artifact(
        artifact_id="connector-github-v1",
        owner_user_id="creator",
        connector_definition={
            "name": "GitHub PR writer",
            "connection_class": "pull-request-writer",
        },
        mcp_client_config={
            "server": "https://github.example/mcp",
            "auth": "oauth",
            "scopes": ["pull_requests:write"],
        },
        created_at=10.0,
    )
    remix = ledger.remix_connector_artifact(
        parent_artifact_id=original.artifact_id,
        artifact_id="connector-github-v2",
        owner_user_id="remixer",
        connector_definition={
            **original.connector_definition,
            "name": "Acme GitHub PR writer",
        },
        mcp_client_config=original.mcp_client_config,
        created_at=20.0,
    )

    assert original.attribution == ("creator",)
    assert remix.parent_artifact_id == original.artifact_id
    assert remix.attribution == ("creator", "remixer")
    assert ledger.get_connector_artifact(remix.artifact_id) == remix
