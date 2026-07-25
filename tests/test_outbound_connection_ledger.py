from __future__ import annotations

import gc
import hashlib
import inspect
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from tinyassets.storage.outbound_connections import (
    AmbiguousProxyOutcome,
    ConnectionLedger,
    CredentialBlindBroker,
    GrantResolutionError,
    ProxyRequestError,
)

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class _JsonlDispatch:
    path: str

    def records(self):
        path = Path(self.path)
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]


@dataclass
class _JsonlAudit:
    path: str

    def __call__(self, record):
        with Path(self.path).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")

    def records(self):
        path = Path(self.path)
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]


def _runtime_log(tmp_path, grant_id, filename):
    runtime_id = hashlib.sha256(grant_id.encode("utf-8")).hexdigest()
    return tmp_path / ".outbound-proxy" / runtime_id / filename


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


def test_revoking_connection_invalidates_all_grants_and_cap_evaluation(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        verify_authenticated_principal=lambda: "user-1",
    )
    _grant_github_connection(ledger)

    assert ledger.revoke_connection("conn-github", revoked_at=321.0) is True
    assert ledger.get_connection("conn-github").revoked_at == 321.0
    with pytest.raises(GrantResolutionError, match="revoked"):
        ledger.evaluate_unprompted_action_cap(
            grant_id="grant-github",
            action_value=1,
            action_unit="pull_requests",
        )
    with pytest.raises(GrantResolutionError, match="revoked"):
        ledger.resolve_scoped_proxy(
            universe_id="universe-1",
            connection_class="pull-request-writer",
        )


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
    provider: str = "test-fixture.created",
    credential_ref: str = "test-fixture://nonsecret",
) -> None:
    ledger.create_connection(
        connection_id=connection_id,
        owner_user_id="user-1",
        connection_class="pull-request-writer",
        scopes=("pull_requests:write",),
        provider=provider,
        destination="github.com/acme/widgets",
        credential_ref=credential_ref,
    )
    ledger.grant_connection(
        grant_id=grant_id,
        connection_id=connection_id,
        owner_user_id="user-1",
        universe_id="universe-1",
    )


def test_resolve_scoped_proxy_uses_only_current_exact_grant(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    _grant_github_connection(ledger)
    dispatched = _JsonlDispatch(
        str(_runtime_log(tmp_path, "grant-github", "network.jsonl"))
    )

    proxy = ledger.resolve_scoped_proxy(
        universe_id="universe-1",
        connection_class="pull-request-writer",
    )

    assert proxy.provider == "test-fixture.created"
    assert proxy.destination == "github.com/acme/widgets"
    assert proxy.request("pull_requests:write", {"title": "Ship"}) == {
        "status": "created"
    }
    assert dispatched.records() == [{
        "provider": "test-fixture.created",
        "destination": "github.com/acme/widgets",
        "verb": "pull_requests:write",
        "request": {"title": "Ship"},
    }]
    parameters = inspect.signature(ledger.resolve_scoped_proxy).parameters
    assert "dispatch" not in parameters
    assert "dispatch_factory" not in parameters
    assert "dispatch_config" not in parameters
    assert "owner_user_id" not in parameters


def test_resolve_scoped_proxy_refuses_caller_supplied_owner_identity(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
    )
    _grant_github_connection(ledger)
    forged_owner = ledger.get_grant("grant-github").owner_user_id

    with pytest.raises(TypeError, match="owner_user_id"):
        ledger.resolve_scoped_proxy(
            owner_user_id=forged_owner,
            universe_id="universe-1",
            connection_class="pull-request-writer",
        )


def test_resolve_scoped_proxy_fails_closed_without_principal_verifier(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
    )
    _grant_github_connection(ledger)

    with pytest.raises(PermissionError, match="principal verifier"):
        ledger.resolve_scoped_proxy(
            universe_id="universe-1",
            connection_class="pull-request-writer",
        )


def test_proxy_api_rejects_caller_supplied_factory_or_config(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    _grant_github_connection(ledger)
    with pytest.raises(TypeError, match="dispatch_factory"):
        ledger.resolve_scoped_proxy(
            universe_id="universe-1",
            connection_class="pull-request-writer",
            dispatch_factory="evil.module:leak_secret",
        )
    with pytest.raises(TypeError, match="dispatch_config"):
        ledger.resolve_scoped_proxy(
            universe_id="universe-1",
            connection_class="pull-request-writer",
            dispatch_config={"payload": "raw-secret"},
        )


def test_test_fixture_transport_is_disabled_by_default(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        verify_authenticated_principal=lambda: "user-1",
    )
    _grant_github_connection(ledger)
    proxy = ledger.resolve_scoped_proxy(
        universe_id="universe-1",
        connection_class="pull-request-writer",
    )

    with pytest.raises(ProxyRequestError, match="outbound request failed"):
        proxy.request("pull_requests:write", {"title": "Must fail closed"})


@pytest.mark.parametrize("case", ["absent", "revoked", "ambiguous"])
def test_resolve_scoped_proxy_fails_closed_without_fallback(tmp_path, case):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
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
            universe_id="universe-1",
            connection_class="pull-request-writer",
        )


def test_adapter_cannot_recover_secret_from_state_environment_metadata_or_errors(
    tmp_path,
):
    secret = "raw-secret-never-visible-to-adapter"
    vault_path = tmp_path / "vault-secret.txt"
    vault_path.write_text(secret, encoding="utf-8")
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    _grant_github_connection(
        ledger,
        provider="test-fixture.explode",
        credential_ref=f"test-vault-file:{vault_path}",
    )
    audit = _JsonlAudit(
        str(_runtime_log(tmp_path, "grant-github", "audit.jsonl"))
    )
    proxy = ledger.resolve_scoped_proxy(
        universe_id="universe-1",
        connection_class="pull-request-writer",
    )
    graph_state = {"connection": proxy}
    request_metadata = {
        "provider": proxy.provider,
        "destination": proxy.destination,
        "scopes": proxy.scopes,
    }
    assert not hasattr(proxy, "_dispatch")
    assert not hasattr(proxy, "_dispatch_handle")
    assert proxy._channel._process.pid != os.getpid()
    assert not hasattr(proxy._channel._process, "_args")
    assert "_PROXY_DISPATCHERS" not in vars(
        __import__(
            "tinyassets.storage.outbound_connections",
            fromlist=["outbound_connections"],
        )
    )
    gc.collect()
    assert not any(
        isinstance(candidate, CredentialBlindBroker)
        for candidate in gc.get_objects()
    )

    with pytest.raises(ProxyRequestError) as raised:
        proxy.request("pull_requests:write", {"title": "Ship"})

    adapter_observations = json.dumps(
        {
            "state": graph_state,
            "environment": dict(os.environ),
            "request_metadata": request_metadata,
            "proxy_error": str(raised.value),
            "proxy_repr": repr(proxy),
            "audit": audit.records(),
        },
        default=repr,
        sort_keys=True,
    )
    assert secret not in adapter_observations
    assert "test-vault-file:" not in adapter_observations
    assert audit.records() == [
        {
            "event": "outbound_proxy_error",
            "grant_id": "grant-github",
            "provider": "test-fixture.explode",
            "destination": "github.com/acme/widgets",
            "verb": "pull_requests:write",
            "reason": "destination request failed",
        }
    ]


def test_credential_resolver_exception_cannot_leak_secret_to_proxy_error(tmp_path):
    secret = "vault-provider-echoed-secret"
    vault_path = tmp_path / "vault-secret.txt"
    vault_path.write_text(secret, encoding="utf-8")
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    _grant_github_connection(
        ledger,
        provider="test-fixture.explode",
        credential_ref=f"test-vault-error:{vault_path}",
    )
    audit = _JsonlAudit(
        str(_runtime_log(tmp_path, "grant-github", "audit.jsonl"))
    )
    proxy = ledger.resolve_scoped_proxy(
        universe_id="universe-1",
        connection_class="pull-request-writer",
    )

    with pytest.raises(ProxyRequestError) as raised:
        proxy.request("pull_requests:write", {"title": "Ship"})

    assert secret not in str(raised.value)
    assert secret not in json.dumps(audit.records())
    assert audit.records()[0]["reason"] == "credential unavailable"


def test_ambiguous_transport_error_cannot_leak_credential_material(tmp_path):
    secret = "transport-echoed-bearer-secret"
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    _grant_github_connection(ledger)

    def raise_secret_bearing_error(**_kwargs):
        raise AmbiguousProxyOutcome(
            f"connection reset after send; Authorization: Bearer {secret}"
        )

    broker = CredentialBlindBroker(
        ledger,
        resolve_credential=lambda _ref: secret,
        network_request=raise_secret_bearing_error,
    )

    with pytest.raises(AmbiguousProxyOutcome) as raised:
        broker.dispatch(
            "grant-github",
            "pull_requests:write",
            {"title": "Ship"},
        )

    assert secret not in str(raised.value)


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
