"""connect_http — provision a generic outbound http connection (Slice 1).

Requirement source:
``openspec/changes/provision-http-connection-channel/specs/outbound-connection-provisioning/spec.md``.

Covers: owner (admin, not write) gate, the vault http deposit + connection +
grant round-trip, endpoint SSRF pre-validation (nothing mutated on bad input),
idempotency + secret rotation, policy-immutable conflict (endpoint-change is a
conflict, never a silent reuse), inert-self-heal after a mid-provision fault,
cross-owner transfer refusal, response/log redaction, the write_graph dispatch,
and the no-new-advertised-handle invariant.

The primitive is channel-agnostic: these tests use a neutral example host
(``api.example.com``) on purpose. No real service is named anywhere in the code —
the owner supplies the host + secret at build time.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity


class _StaticAuthProvider(AuthProvider):
    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "valid" else None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict[str, Any]) -> dict[str, Any]:
        return {"client_id": "test-client", **metadata}

    def create_authorization(self, *a: Any, **k: Any) -> str:
        return "test-code"

    def exchange_code(self, *a: Any, **k: Any) -> dict[str, Any] | None:
        return None


def _login(user_id: str) -> None:
    set_provider(
        _StaticAuthProvider(
            Identity(
                user_id=user_id,
                username=user_id,
                capabilities=["tinyassets.universe.write"],
            )
        )
    )
    auth_middleware("valid")


def _logout() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)


@pytest.fixture(autouse=True)
def _reset_auth() -> Any:
    _logout()
    yield
    _logout()


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


def _make_universe(base: Path, uid: str, *, admin: str = "", write: str = "") -> Path:
    from tinyassets.daemon_server import grant_universe_access

    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    if admin:
        grant_universe_access(
            base, universe_id=uid, actor_id=admin, permission="admin", granted_by=admin
        )
    if write:
        grant_universe_access(
            base, universe_id=uid, actor_id=write, permission="write", granted_by=admin
        )
    return udir


# Neutral example host — the primitive names no real service.
_EP = [{"host": "api.example.com", "path_template": "/v1/messages", "methods": ["POST"]}]


def _connect(
    uid: str,
    *,
    destination: str = "webhook:acme",
    secret: str = "sk-SECRET-token",
    endpoints: Any = None,
    auth_scheme: str | None = None,
) -> dict[str, Any]:
    from tinyassets.api.http_connection import connect_http

    doc: dict[str, Any] = {
        "destination": destination,
        "secret": secret,
        "allowed_endpoints": _EP if endpoints is None else endpoints,
    }
    if auth_scheme is not None:
        doc["auth_scheme"] = auth_scheme
    return connect_http(universe_id=uid, payload=json.dumps(doc))


def _ledger(base: Path, actor: str) -> Any:
    from tinyassets.storage.outbound_connections import ConnectionLedger

    return ConnectionLedger(
        base / "outbound.db", verify_authenticated_principal=lambda: actor
    )


def _http_records(udir: Path) -> list[dict[str, Any]]:
    from tinyassets.credential_vault import load_credential_vault

    return [r for r in load_credential_vault(udir) if r.get("credential_type") == "http"]


# --------------------------------------------------------------------------- #
# Positive round-trip.
# --------------------------------------------------------------------------- #


def test_owner_provisions_http_connection_round_trip(base: Path) -> None:
    from tinyassets.api.http_connection import _ids

    udir = _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    result = _connect("u-owner")

    assert result["status"] == "provisioned"
    assert result["auth_scheme"] == "bearer"
    assert result["destination"] == "webhook:acme"
    assert result["allowed_endpoints"][0]["host"] == "api.example.com"
    blob = json.dumps(result)
    assert "sk-SECRET-token" not in blob
    assert "vault://http" not in blob  # credential_ref never surfaced

    # Vault: exactly one http record, keyed by destination, secret in `token`.
    recs = _http_records(udir)
    assert len(recs) == 1
    assert recs[0]["destination"] == "webhook:acme"
    assert recs[0]["service"] == "webhook:acme"
    assert recs[0]["token"] == "sk-SECRET-token"

    # Ledger: connection is http, endpoint stored, grant bound to the universe.
    conn_id, grant_id = _ids(universe_id="u-owner", destination="webhook:acme")
    ledger = _ledger(base, "founder")
    resource = ledger._get_connection_resource(conn_id)
    assert resource is not None
    assert resource.connection_type == "http"
    assert resource.destination == "webhook:acme"
    assert resource.credential_ref == "vault://http/webhook:acme"
    assert resource.owner_user_id == "founder"
    assert [e.host for e in resource.allowed_endpoints] == ["api.example.com"]
    grant = ledger.get_grant(grant_id)
    assert grant is not None
    assert grant.universe_id == "u-owner"
    assert grant.connection_id == conn_id


def test_provision_routes_through_write_graph(base: Path) -> None:
    import importlib

    from tinyassets import universe_server as us

    importlib.reload(us)
    try:
        _make_universe(base, "u-route", admin="founder")
        _login("founder")
        raw = us.write_graph(
            target="connection",
            operation="connect_http",
            graph_id="u-route",
            payload_json=json.dumps(
                {"destination": "webhook:r", "secret": "sk-r", "allowed_endpoints": _EP}
            ),
        )
        payload = json.loads(raw)
        assert payload["status"] == "provisioned"
        assert payload["destination"] == "webhook:r"
    finally:
        importlib.reload(us)


# --------------------------------------------------------------------------- #
# Auth gates.
# --------------------------------------------------------------------------- #


def test_anonymous_refused_before_any_write(base: Path) -> None:
    udir = _make_universe(base, "u-anon", admin="founder")
    result = _connect("u-anon")
    assert result["error"] == "authentication_required"
    assert _http_records(udir) == []
    assert not (base / "outbound.db").exists()


def test_write_collaborator_refused(base: Path) -> None:
    udir = _make_universe(base, "u-collab", admin="founder", write="collab")
    _login("collab")
    result = _connect("u-collab")
    assert result == {"error": "not_found", "resource": "connection"}
    assert _http_records(udir) == []


def test_foreign_universe_admin_refused(base: Path) -> None:
    _make_universe(base, "u-a", admin="founder-a")
    victim = _make_universe(base, "u-b", admin="founder-b")
    _login("founder-a")  # admin of A, nothing on B
    result = _connect("u-b")
    assert result == {"error": "not_found", "resource": "connection"}
    assert _http_records(victim) == []


# --------------------------------------------------------------------------- #
# Fail-closed input validation (nothing mutated).
# --------------------------------------------------------------------------- #


def test_bad_destination_grammar_rejected(base: Path) -> None:
    udir = _make_universe(base, "u-dg", admin="founder")
    _login("founder")
    result = _connect("u-dg", destination="Bad Dest!/../x")
    assert result["error"] == "connection_setup_invalid"
    assert _http_records(udir) == []


def test_empty_endpoints_rejected(base: Path) -> None:
    udir = _make_universe(base, "u-ee", admin="founder")
    _login("founder")
    result = _connect("u-ee", endpoints=[])
    assert result["error"] == "connection_setup_invalid"
    assert _http_records(udir) == []


def test_unsupported_auth_scheme_rejected(base: Path) -> None:
    udir = _make_universe(base, "u-as", admin="founder")
    _login("founder")
    result = _connect("u-as", auth_scheme="oauth1a")
    assert result["error"] == "unsupported_auth_scheme"
    assert _http_records(udir) == []


def test_ssrf_endpoint_rejected_nothing_mutated(base: Path) -> None:
    """An IP-literal / metadata host is rejected by the endpoint validator BEFORE
    the vault deposit — no credential and no connection are created."""
    udir = _make_universe(base, "u-ssrf", admin="founder")
    _login("founder")
    result = _connect(
        "u-ssrf",
        endpoints=[{"host": "169.254.169.254", "path_template": "/latest", "methods": ["GET"]}],
    )
    assert result["error"] in ("endpoint_not_permitted", "connection_setup_invalid")
    assert _http_records(udir) == []
    assert not (base / "outbound.db").exists()


# --------------------------------------------------------------------------- #
# Idempotency + rotation + conflict.
# --------------------------------------------------------------------------- #


def test_reprovision_is_idempotent_and_rotates_secret(base: Path) -> None:
    udir = _make_universe(base, "u-idem", admin="founder")
    _login("founder")

    first = _connect("u-idem", secret="sk-v1")
    second = _connect("u-idem", secret="sk-v2")

    # Same deterministic ids (one connection per (universe, destination)).
    assert first["connection_id"] == second["connection_id"]
    assert first["grant_id"] == second["grant_id"]
    # Exactly one http record; the secret was rotated to v2.
    recs = _http_records(udir)
    assert len(recs) == 1
    assert recs[0]["token"] == "sk-v2"


def test_reordered_endpoints_and_methods_are_idempotent(base: Path) -> None:
    """Endpoints, methods, and allowed_query names are UNORDERED sets at runtime,
    so a re-provision that only REORDERS an otherwise-identical policy must stay
    idempotent — same deterministic ids, secret rotated, NOT a false
    connection_conflict (Codex review finding #2, order-insensitive compare)."""
    udir = _make_universe(base, "u-reorder", admin="founder")
    _login("founder")

    ep_a = {
        "host": "api.example.com",
        "path_template": "/v1/messages",
        "methods": ["GET", "POST"],
        "allowed_query": ["alpha", "beta"],
    }
    ep_b = {
        "host": "other.example.com",
        "path_template": "/v1/models",
        "methods": ["POST", "PUT"],
    }
    first = _connect("u-reorder", secret="sk-v1", endpoints=[ep_a, ep_b])
    assert first["status"] == "provisioned"

    # Identical policy, everything reordered: endpoint list swapped, methods
    # swapped within each endpoint, allowed_query names swapped. Secret rotated.
    ep_a_reordered = {
        "host": "api.example.com",
        "path_template": "/v1/messages",
        "methods": ["POST", "GET"],
        "allowed_query": ["beta", "alpha"],
    }
    ep_b_reordered = {
        "host": "other.example.com",
        "path_template": "/v1/models",
        "methods": ["PUT", "POST"],
    }
    second = _connect(
        "u-reorder", secret="sk-v2", endpoints=[ep_b_reordered, ep_a_reordered]
    )

    # A pure reorder is NOT a conflict — same ids, secret rotated to v2.
    assert second.get("status") == "provisioned", second
    assert second["connection_id"] == first["connection_id"]
    assert second["grant_id"] == first["grant_id"]
    recs = _http_records(udir)
    assert len(recs) == 1
    assert recs[0]["token"] == "sk-v2"


def test_reprovision_with_changed_endpoints_is_a_conflict(base: Path) -> None:
    """A re-provision that changes the egress policy (a different endpoint
    allow-list) must be refused as a conflict BEFORE the vault write — never a
    silent reuse of the old connection under a rotated secret. The owner must
    revoke-then-reprovision to change policy (Codex review finding #2)."""
    udir = _make_universe(base, "u-epchg", admin="founder")
    _login("founder")

    assert _connect("u-epchg", secret="sk-v1")["status"] == "provisioned"
    changed = _connect(
        "u-epchg",
        secret="sk-v2",
        endpoints=[
            {"host": "other.example.com", "path_template": "/v1/messages", "methods": ["POST"]}
        ],
    )
    assert changed == {"error": "connection_conflict", "resource": "connection"}
    # Old secret + old endpoint policy are untouched — no rotation on conflict.
    recs = _http_records(udir)
    assert len(recs) == 1
    assert recs[0]["token"] == "sk-v1"
    from tinyassets.api.http_connection import _ids

    conn_id, _ = _ids(universe_id="u-epchg", destination="webhook:acme")
    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert [e.host for e in resource.allowed_endpoints] == ["api.example.com"]


def test_second_admin_cannot_transfer_existing_credential(base: Path) -> None:
    from tinyassets.daemon_server import grant_universe_access

    udir = _make_universe(base, "u-co", admin="founder")
    grant_universe_access(
        base, universe_id="u-co", actor_id="coadmin", permission="admin", granted_by="founder"
    )
    _login("founder")
    assert _connect("u-co", secret="founder-secret")["status"] == "provisioned"

    _login("coadmin")  # admin, but not the connection/credential owner
    result = _connect("u-co", secret="coadmin-secret")
    # Caught at the connection-ownership conflict BEFORE the vault is touched — a
    # stronger guarantee than the vault's own ownership refusal: nothing mutated.
    assert result["error"] == "connection_conflict"
    recs = _http_records(udir)
    assert len(recs) == 1
    assert recs[0]["token"] == "founder-secret"


def test_inert_self_heal_after_grant_fault(base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A mid-provision fault (the grant write raises after the vault + connection
    landed) leaves only INERT partial state — a connection with no grant, which
    cannot authorize a call. The deterministic-id retry completes it (Codex review
    finding #1: the claim is inert-self-heal, not all-or-nothing)."""
    from tinyassets.storage import outbound_connections as oc

    udir = _make_universe(base, "u-heal", admin="founder")
    _login("founder")

    real_grant = oc.ConnectionLedger.grant_connection
    calls = {"n": 0}

    def _flaky_grant(self: Any, *a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected grant fault")
        return real_grant(self, *a, **k)

    monkeypatch.setattr(oc.ConnectionLedger, "grant_connection", _flaky_grant)

    # First call: vault + connection land, grant raises. The fault surfaces, not
    # a usable connection.
    with pytest.raises(RuntimeError):
        _connect("u-heal")
    from tinyassets.api.http_connection import _ids

    conn_id, grant_id = _ids(universe_id="u-heal", destination="webhook:acme")
    ledger = _ledger(base, "founder")
    assert ledger._get_connection_resource(conn_id) is not None  # inert connection
    assert ledger.get_grant(grant_id) is None  # no grant → cannot authorize a call

    # Retry (same deterministic ids): reuses the inert connection, completes the
    # grant. Now usable, exactly once.
    healed = _connect("u-heal")
    assert healed["status"] == "provisioned"
    assert healed["connection_id"] == conn_id
    assert ledger.get_grant(grant_id) is not None
    assert len(_http_records(udir)) == 1


def test_create_fault_orphan_is_owner_locked_then_original_owner_heals(
    base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A create-stage fault (create_connection raises AFTER the vault deposit)
    leaves an orphaned http vault record with no connection row. A SECOND admin
    then finds no ledger conflict (resource is None), so the ONLY thing that can
    stop them overwriting the orphaned secret and provisioning as themselves is
    the vault's own depositor-ownership enforcement — which must now cover http
    records (Codex CRITICAL finding). The original owner's retry still completes.
    """
    from tinyassets.daemon_server import grant_universe_access
    from tinyassets.storage import outbound_connections as oc

    udir = _make_universe(base, "u-orphan", admin="founder")
    grant_universe_access(
        base, universe_id="u-orphan", actor_id="coadmin",
        permission="admin", granted_by="founder",
    )

    real_create = oc.ConnectionLedger.create_connection
    calls = {"n": 0}

    def _flaky_create(self: Any, *a: Any, **k: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("injected create fault")
        return real_create(self, *a, **k)

    monkeypatch.setattr(oc.ConnectionLedger, "create_connection", _flaky_create)

    # 1. Founder's first call: the vault deposit lands (owner recorded), then
    #    create_connection raises. The fault surfaces; no connection row exists.
    _login("founder")
    with pytest.raises(RuntimeError):
        _connect("u-orphan", secret="founder-secret")

    from tinyassets.api.http_connection import _ids

    conn_id, grant_id = _ids(universe_id="u-orphan", destination="webhook:acme")
    ledger = _ledger(base, "founder")
    assert ledger._get_connection_resource(conn_id) is None  # orphaned: no row
    recs = _http_records(udir)
    assert len(recs) == 1 and recs[0]["token"] == "founder-secret"  # orphaned cred

    # 2. Second admin tries to seize the orphaned credential. No ledger conflict
    #    (resource is None), so the vault ownership guard is the only defense: it
    #    refuses, and the founder's secret is NOT overwritten.
    _login("coadmin")
    seized = _connect("u-orphan", secret="coadmin-secret")
    assert seized["error"] == "credential_ownership_transfer_unsupported"
    recs = _http_records(udir)
    assert len(recs) == 1 and recs[0]["token"] == "founder-secret"  # untouched
    assert ledger._get_connection_resource(conn_id) is None  # still no connection

    # 3. Original owner retries (create now succeeds): the orphan heals into a
    #    usable connection + grant, and the stored secret is the owner's.
    _login("founder")
    healed = _connect("u-orphan", secret="founder-secret-v2")
    assert healed["status"] == "provisioned"
    assert healed["connection_id"] == conn_id
    assert ledger._get_connection_resource(conn_id) is not None
    assert ledger.get_grant(grant_id) is not None
    recs = _http_records(udir)
    assert len(recs) == 1 and recs[0]["token"] == "founder-secret-v2"


# --------------------------------------------------------------------------- #
# Redaction + no advertised handle.
# --------------------------------------------------------------------------- #


def test_response_and_logs_carry_no_secret(base: Path, caplog: pytest.LogCaptureFixture) -> None:
    _make_universe(base, "u-clean", admin="founder")
    _login("founder")
    secret = "sk-SUPER-SECRET-do-not-echo"
    with caplog.at_level("DEBUG"):
        result = _connect("u-clean", secret=secret)
    assert result["status"] == "provisioned"
    assert secret not in json.dumps(result)
    assert secret not in caplog.text


def test_connect_http_adds_no_advertised_handle(base: Path) -> None:
    import importlib

    from scripts.mcp_public_canary import CANONICAL_HANDLES
    from tinyassets import universe_server as us

    importlib.reload(us)
    try:
        advertised = {t.name for t in asyncio.run(us.mcp.list_tools(run_middleware=True))}
        assert advertised == set(CANONICAL_HANDLES)
        assert "connect_http" not in advertised
    finally:
        importlib.reload(us)
