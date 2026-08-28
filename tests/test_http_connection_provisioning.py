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


def test_connection_scope_is_the_endpoint_methods_not_a_type_token(base: Path) -> None:
    """REGRESSION (first end-to-end live channel test, 2026-08-24).

    An http connection's SCOPE must be the set of HTTP methods its endpoints
    permit — the ``verb`` the ``authenticated_external_call`` effector matches
    against (``verb in resource.scopes`` in both the ScopedConnectionProxy and the
    CredentialBlindBroker). ``connect_http`` used to hardcode the literal
    ``("http",)`` type token, which contains NO verb, so every outbound POST failed
    ``"verb 'POST' is outside the granted connection scope"`` and the whole http
    channel was dead on arrival. The effector's own test harness proves the working
    contract is method-scoped (``_setup(... scopes=("POST",))``); this pins that
    ``connect_http`` produces exactly that shape.
    """
    from tinyassets.api.http_connection import _ids

    _make_universe(base, "u-scope", admin="founder")
    _login("founder")

    result = _connect(
        "u-scope",
        endpoints=[
            {"host": "api.example.com", "path_template": "/v1/messages", "methods": ["POST"]},
            {"host": "api.example.com", "path_template": "/v1/files", "methods": ["get", "PUT"]},
        ],
    )
    assert result["status"] == "provisioned"

    conn_id, _grant_id = _ids(universe_id="u-scope", destination="webhook:acme")
    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert resource is not None
    # Sorted, uppercased, de-duped union of every endpoint's methods — the verbs the
    # effector accepts — and specifically NOT the ("http",) type token.
    assert tuple(resource.scopes) == ("GET", "POST", "PUT")
    assert "http" not in resource.scopes


def _seed_legacy_http_connection(
    base: Path,
    uid: str,
    *,
    endpoints: Any = None,
    old_secret: str = "old-secret",
    grant_universe: str | None = None,
) -> tuple[Path, str, str]:
    """Write a PRE-FIX http connection: the legacy ("http",) scope token + an old
    secret + a grant carrying the real ``_HTTP_ACTION_CAP`` (the shape a connection
    provisioned before the #2521 scope fix actually has)."""
    from tinyassets.api.http_connection import _HTTP_ACTION_CAP, _ids
    from tinyassets.credential_vault import write_credential_vault

    udir = _make_universe(base, uid, admin="founder")
    conn_id, grant_id = _ids(universe_id=uid, destination="webhook:acme")
    write_credential_vault(
        udir,
        [
            {
                "credential_type": "http",
                "service": "webhook:acme",
                "destination": "webhook:acme",
                "token": old_secret,
            }
        ],
        owner_user_id="founder",
        universe_id=uid,
    )
    ledger = _ledger(base, "founder")
    ledger.create_connection(
        connection_id=conn_id,
        owner_user_id="founder",
        connection_class="http",
        connection_type="http",
        auth_scheme="bearer",
        scopes=("http",),
        provider="http",
        destination="webhook:acme",
        credential_ref="vault://http/webhook:acme",
        allowed_endpoints=_EP if endpoints is None else endpoints,
    )
    ledger.grant_connection(
        grant_id=grant_id,
        connection_id=conn_id,
        owner_user_id="founder",
        universe_id=grant_universe or uid,
        unprompted_action_cap=_HTTP_ACTION_CAP,
    )
    assert tuple(ledger._get_connection_resource(conn_id).scopes) == ("http",)
    return udir, conn_id, grant_id


def test_legacy_http_scope_token_is_upgraded_in_place_not_stranded(base: Path) -> None:
    """REGRESSION (Codex ADAPT, #2521).

    A connection provisioned BEFORE the scope fix carries the legacy ("http",)
    token. Re-provisioning it with the SAME policy must UPGRADE its scope to the
    method union in place (a bounded, one-directional migration) and rotate the
    secret — NOT strand it behind ``connection_conflict``, which deterministic ids +
    the absence of a policy-update path would otherwise make unrecoverable.
    """
    udir, conn_id, _grant_id = _seed_legacy_http_connection(base, "u-legacy")
    _login("founder")

    result = _connect("u-legacy", secret="new-secret")  # SAME policy, rotated secret
    assert result["status"] == "provisioned"  # NOT connection_conflict — upgraded.

    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert tuple(resource.scopes) == ("POST",)  # upgraded from the ("http",) token
    assert _http_records(udir)[0]["token"] == "new-secret"  # secret rotated


def test_legacy_upgrade_is_deferred_until_after_a_successful_deposit(
    base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed credential deposit must leave the legacy ("http",) scope UNTOUCHED —
    otherwise a failed rotation would activate the formerly-unusable connection with
    the stale, un-rotated secret (Codex ADAPT re-review: fail-open ordering)."""
    udir, conn_id, _grant_id = _seed_legacy_http_connection(base, "u-legacy-dep")
    _login("founder")

    def _boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("deposit exploded")

    # connect_http imports write_credential_vault fresh from the source module at
    # call time, so patch the SOURCE, not the api.http_connection namespace.
    monkeypatch.setattr(
        "tinyassets.credential_vault.write_credential_vault", _boom
    )
    result = _connect("u-legacy-dep", secret="new-secret")
    assert result["error"] == "deposit_failed"

    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert tuple(resource.scopes) == ("http",)  # NOT upgraded — still inert
    assert _http_records(udir)[0]["token"] == "old-secret"  # secret NOT rotated


def test_legacy_scope_untouched_on_grant_conflict(base: Path) -> None:
    """A grant-conflict refusal must leave the legacy ("http",) scope UNTOUCHED —
    the upgrade is deferred past the grant-conflict check."""
    udir, conn_id, _g = _seed_legacy_http_connection(
        base, "u-legacy-grant", grant_universe="u-OTHER-universe"
    )
    _login("founder")

    result = _connect("u-legacy-grant", secret="new-secret")
    assert result == {"error": "connection_conflict", "resource": "grant"}
    assert tuple(_ledger(base, "founder")._get_connection_resource(conn_id).scopes) == (
        "http",
    )
    assert _http_records(udir)[0]["token"] == "old-secret"  # nothing rotated


def test_legacy_row_with_changed_policy_conflicts_scope_untouched(base: Path) -> None:
    """A legacy row whose endpoint policy DIFFERS from the re-provision request is a
    genuine conflict (not an upgrade); the legacy scope stays untouched."""
    udir, conn_id, _g = _seed_legacy_http_connection(
        base,
        "u-legacy-policy",
        endpoints=[
            {"host": "api.example.com", "path_template": "/v1/other", "methods": ["POST"]}
        ],
    )
    _login("founder")

    # Default _EP is /v1/messages — a different endpoint set than seeded.
    result = _connect("u-legacy-policy", secret="new-secret")
    assert result == {"error": "connection_conflict", "resource": "connection"}
    assert tuple(_ledger(base, "founder")._get_connection_resource(conn_id).scopes) == (
        "http",
    )
    assert _http_records(udir)[0]["token"] == "old-secret"


def test_connections_list_includes_http_channel_connections(base: Path) -> None:
    """REGRESSION: read_graph target=connections (cloud_connections 'list') must list
    a universe's http CHANNEL connections, not just github pipes — channel-agnostically.

    The served agent needs to read back a connection's connection_id / grant_id /
    allowed host+path itself to build an authenticated_external_call node; without
    this it had to ask the owner to paste those ids by hand. Any deposited http
    destination appears identically — no per-service code.
    """
    from tinyassets.api.cloud_connections import cloud_connections
    from tinyassets.api.http_connection import _ids

    _make_universe(base, "u-list", admin="founder")
    _login("founder")
    _connect("u-list", destination="webhook:slack-like")  # generic http deposit
    conn_id, grant_id = _ids(universe_id="u-list", destination="webhook:slack-like")

    result = cloud_connections(action="list", universe_id="u-list")
    conns = result["connections"]
    http = [c for c in conns if c["connection_id"] == conn_id]
    assert len(http) == 1, f"http channel connection not listed: {conns}"
    row = http[0]
    assert row["grant_id"] == grant_id
    assert row["destination"] == "webhook:slack-like"
    assert row["connection_class"] == "http"
    # The redacted egress allow-list gives the agent the exact host/path to emit.
    assert row["allowed_endpoints"][0]["host"] == "api.example.com"
    assert "POST" in row["allowed_endpoints"][0]["methods"]
    # No secret ever surfaces in the listing.
    assert "sk-SECRET-token" not in json.dumps(result)
    assert "credential_ref" not in row and "vault://" not in json.dumps(result)


def test_connections_list_isolates_by_owner_not_just_universe(base: Path) -> None:
    """SECURITY (Codex ADAPT #2524): the connections list isolates by OWNER, not only
    by universe.

    Two ADMINS of the SAME universe each deposit a connection; each must see ONLY
    their own — never the other owner's. If the ``owner_user_id`` filter in
    ``list_grants`` were dropped, each would see BOTH connections and this fails
    (the include-http test only varied the universe, so it would have stayed green
    without that filter — this is the real cross-owner probe Codex asked for).
    """
    from tinyassets.api.cloud_connections import cloud_connections
    from tinyassets.daemon_server import grant_universe_access
    from tinyassets.storage.outbound_connections import ConnectionLedger

    _make_universe(base, "u-shared", admin="founder")
    grant_universe_access(
        base, universe_id="u-shared", actor_id="collab", permission="admin",
        granted_by="founder",
    )

    # Seed two connections in the SAME universe owned by DIFFERENT principals
    # directly at the ledger (the credential vault is single-owner-per-universe, so
    # two owners cannot both deposit via connect_http — but the list's isolation is a
    # property of the list_grants owner filter, which this exercises head-on).
    def _seed(owner: str, dest: str, conn_id: str, grant_id: str) -> None:
        ledger = ConnectionLedger(
            base / "outbound.db", verify_authenticated_principal=lambda: owner
        )
        ledger.create_connection(
            connection_id=conn_id, owner_user_id=owner, connection_class="http",
            connection_type="http", auth_scheme="bearer", scopes=("POST",),
            provider="http", destination=dest, credential_ref=f"vault://http/{dest}",
            allowed_endpoints=_EP,
        )
        ledger.grant_connection(
            grant_id=grant_id, connection_id=conn_id, owner_user_id=owner,
            universe_id="u-shared",
        )

    _seed("founder", "webhook:founders", "http_founder", "grant_founder")
    _seed("collab", "webhook:collabs", "http_collab", "grant_collab")

    # Collaborator sees ONLY their own connection, never the founder's. Removing the
    # owner_user_id filter from list_grants would surface "http_founder" here.
    _login("collab")
    theirs = cloud_connections(action="list", universe_id="u-shared")
    tids = {c["connection_id"] for c in theirs["connections"]}
    assert "http_collab" in tids, f"collab should see own connection: {theirs}"
    assert "http_founder" not in tids, f"cross-owner leak: collab saw founder's: {theirs}"

    # Symmetric: the founder sees only theirs, never the collaborator's.
    _login("founder")
    mine = cloud_connections(action="list", universe_id="u-shared")
    mids = {c["connection_id"] for c in mine["connections"]}
    assert "http_founder" in mids and "http_collab" not in mids


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
    """A scheme the broker cannot sign is refused at the door, nothing written.
    (``header`` is engine-signable but needs a per-connection header NAME the ledger
    does not persist yet, so it stays off the deposit door; ``none`` has nothing to
    deposit.)"""
    udir = _make_universe(base, "u-as", admin="founder")
    _login("founder")
    for bad in ("digest", "header", "none", "hmac"):
        result = _connect("u-as", auth_scheme=bad)
        assert result["error"] == "unsupported_auth_scheme", bad
        assert set(result["allowed_auth_schemes"]) == {"bearer", "basic", "oauth1a"}
    assert _http_records(udir) == []


def test_oauth1a_scheme_deposits_generically(base: Path) -> None:
    """GENERIC UNLOCK: ``auth_scheme=oauth1a`` is accepted at the deposit door.

    The engine already signs OAuth 1.0a end-to-end (``_build_http_secret_bundle``
    parses the four-value JSON, ``_oauth1a_authorization`` signs), but the door was
    bearer-only — which blocked X/Twitter posting and every other OAuth 1.0a API
    with no way around it. This is a scheme unlock, NOT a per-service path: the
    destination label is whatever the owner is connecting.
    """
    from tinyassets.api.http_connection import _ids

    udir = _make_universe(base, "u-o1", admin="founder")
    _login("founder")
    bundle = json.dumps({
        "api_key": "ck", "api_secret": "cs",
        "access_token": "at", "access_token_secret": "ats",
    })
    result = _connect(
        "u-o1", destination="x:my-account", secret=bundle, auth_scheme="oauth1a",
        endpoints=[{"host": "api.x.com", "path_template": "/2/tweets", "methods": ["POST"]}],
    )
    assert result["status"] == "provisioned", result
    assert result["auth_scheme"] == "oauth1a"
    assert "ats" not in json.dumps(result) and "cs" not in json.dumps(result)

    # Stored as ONE opaque string per connection (the broker parses it at request
    # time) and the connection row carries the scheme so the child signs correctly.
    conn_id, _g = _ids(universe_id="u-o1", destination="x:my-account")
    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert resource.auth_scheme == "oauth1a"
    assert _http_records(udir)[0]["token"] == bundle

    # Idempotent re-provision with the SAME scheme rotates; a DIFFERENT scheme for
    # the same destination is a policy change → conflict, nothing rotated.
    again = _connect(
        "u-o1", destination="x:my-account", secret=bundle.replace("ats", "ats2"),
        auth_scheme="oauth1a",
        endpoints=[{"host": "api.x.com", "path_template": "/2/tweets", "methods": ["POST"]}],
    )
    assert again["status"] == "provisioned"
    assert "ats2" in _http_records(udir)[0]["token"]
    clash = _connect(
        "u-o1", destination="x:my-account", secret="plain-bearer", auth_scheme="bearer",
        endpoints=[{"host": "api.x.com", "path_template": "/2/tweets", "methods": ["POST"]}],
    )
    assert clash == {"error": "connection_conflict", "resource": "connection"}
    assert "ats2" in _http_records(udir)[0]["token"]  # untouched


def test_oauth1a_malformed_bundle_rejected_before_any_write(base: Path) -> None:
    """The secret's SHAPE is validated at the door (mirroring the broker's parser)
    so a malformed multi-value credential fails BEFORE any write — never as a
    mysterious failed outbound call later. Error messages carry no secret material."""
    udir = _make_universe(base, "u-o2", admin="founder")
    _login("founder")
    cases = {
        "not-json-at-all": "must be a JSON object",
        json.dumps(["a", "b"]): "must be a JSON object",
        json.dumps({"api_key": "k", "api_secret": "s"}): "missing: access_token",
    }
    for bad, expect in cases.items():
        r = _connect("u-o2", secret=bad, auth_scheme="oauth1a")
        assert r["error"] == "connection_setup_invalid", (bad, r)
        assert expect in r["detail"], (bad, r)
        assert "k" != r["detail"] and bad not in r["detail"]  # no secret echoed
    assert _http_records(udir) == []  # nothing written by any refusal

    # basic: BOTH halves non-empty, mirroring the broker exactly (Codex ADAPT: the
    # door used to accept "user:", ":pw", ":" and write a credential dispatch would
    # then reject — malformed input must be refused at the door, never written).
    for bad in ("no-colon-here", "user:", ":pw", ":"):
        r = _connect("u-o2", secret=bad, auth_scheme="basic")
        assert r["error"] == "connection_setup_invalid", bad
        assert "username:password" in r["detail"], bad
        # No secret material echoed: the message is a CONSTANT that never embeds the
        # input. (A bare ":" input trivially "appears" inside the constant
        # "username:password", so check the constant, not substring-absence.)
        assert r["detail"] == "basic secret must be username:password (both non-empty)"
    assert _http_records(udir) == []
    ok = _connect("u-o2", secret="user:pa:ss", auth_scheme="basic")
    assert ok["status"] == "provisioned" and ok["auth_scheme"] == "basic"


def test_non_string_or_empty_auth_scheme_is_refused_not_defaulted(base: Path) -> None:
    """An EXPLICIT falsy / non-string auth_scheme is a malformed request and must be
    refused — not silently coerced to bearer (Codex ADAPT). Only an ABSENT key takes
    the bearer default."""
    from tinyassets.api.http_connection import connect_http

    udir = _make_universe(base, "u-o3", admin="founder")
    _login("founder")
    # `None` = an EXPLICIT `"auth_scheme": null` on the wire — refused, not treated
    # as absent (Codex ADAPT re-review: null used to provision a bearer credential).
    for bad in (None, "", "   ", 0, False, [], {"scheme": "bearer"}):
        doc = {"destination": "webhook:acme", "secret": "sk", "allowed_endpoints": _EP,
               "auth_scheme": bad}
        r = connect_http(universe_id="u-o3", payload=json.dumps(doc))
        assert r["error"] == "unsupported_auth_scheme", (bad, r)
    assert _http_records(udir) == []
    # Absent key → bearer default, as before.
    ok = _connect("u-o3")
    assert ok["status"] == "provisioned" and ok["auth_scheme"] == "bearer"


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
    silent reuse of the old connection under a rotated secret. Changing an
    existing connection's policy is UNSUPPORTED in Slice 1 (no revoke-then-
    reprovision path exists — revoke only stamps revoked_at); a policy change
    needs a new destination. ADDING endpoints is a different intent and now
    extends in place (see the extension tests below); REPLACING one still
    conflicts, because silently dropping an endpoint another graph depends on is
    the dangerous direction."""
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


def test_legacy_unowned_http_record_is_not_seizable(base: Path) -> None:
    """An http credential deposited BEFORE http ownership was recorded (a legacy /
    owner-less vault record with no owner row) must not be silently overwritten by
    an owned connect_http: the universe-wide guard cannot see an owner it never
    recorded, so the deposit fails closed and the legacy secret is preserved. A
    second admin cannot seize it; recovery needs a dedicated flow (Codex review)."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.daemon_server import grant_universe_access

    udir = _make_universe(base, "u-legacy", admin="founder")
    grant_universe_access(
        base, universe_id="u-legacy", actor_id="coadmin",
        permission="admin", granted_by="founder",
    )
    # Simulate a legacy deposit: an http vault record with NO owner row (owner-less).
    write_credential_vault(
        udir,
        [{
            "credential_type": "http",
            "service": "webhook:acme",
            "destination": "webhook:acme",
            "token": "legacy-secret",
        }],
    )

    # Neither a fresh admin nor the original founder may silently rewrite it.
    for actor in ("coadmin", "founder"):
        _login(actor)
        result = _connect("u-legacy", secret=f"{actor}-secret")
        assert result["error"] == "credential_ownership_transfer_unsupported", (
            actor, result,
        )
        recs = _http_records(udir)
        assert len(recs) == 1 and recs[0]["token"] == "legacy-secret"  # untouched


def test_unrelated_llm_deposit_cannot_claim_orphaned_http_slot(base: Path) -> None:
    """A second admin must not be able to seize a legacy unowned http credential
    by first depositing an UNRELATED owned credential (an LLM subscription). Owner
    rows are claimed only for the records a deposit actually TOUCHES, so an LLM
    deposit never assigns ownership of a pre-existing orphaned http slot — and the
    later connect_http is still refused (Codex re-review: the LLM-deposit-first
    seizure)."""
    import sqlite3 as _sqlite

    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.daemon_server import grant_universe_access
    from tinyassets.storage import db_path

    udir = _make_universe(base, "u-indirect", admin="founder")
    grant_universe_access(
        base, universe_id="u-indirect", actor_id="coadmin",
        permission="admin", granted_by="founder",
    )
    # Legacy orphan: an http vault record with NO owner row.
    write_credential_vault(
        udir,
        [{
            "credential_type": "http",
            "service": "webhook:acme",
            "destination": "webhook:acme",
            "token": "legacy-secret",
        }],
    )

    # coadmin deposits their OWN claude subscription. This must NOT silently claim
    # the orphaned http slot.
    write_credential_vault(
        udir,
        [{"credential_type": "llm_subscription", "service": "claude",
          "oauth_token": "coadmin-tok"}],
        owner_user_id="coadmin",
        universe_id="u-indirect",
    )
    conn = _sqlite.connect(db_path(base))
    try:
        rows = {
            (str(s), str(o))
            for s, o in conn.execute(
                "SELECT service, owner_user_id FROM llm_credential_deposit_owners "
                "WHERE universe_id = ?",
                ("u-indirect",),
            ).fetchall()
        }
    finally:
        conn.close()
    assert rows == {("claude", "coadmin")}  # http slot NOT claimed by the LLM deposit

    # coadmin now tries to seize the orphaned http credential — still refused.
    _login("coadmin")
    result = _connect("u-indirect", secret="coadmin-secret")
    assert result["error"] == "credential_ownership_transfer_unsupported"
    recs = _http_records(udir)
    assert len(recs) == 1 and recs[0]["token"] == "legacy-secret"  # untouched


def test_http_deposit_preserves_llm_serving_custody_rows(base: Path) -> None:
    """Generalizing owner-row keys to http must NOT wipe or corrupt the
    claude/codex ownership rows that gate serving custody. After a universe has
    both llm subscriptions AND an http connection, all three owner rows coexist —
    the http prune/insert leaves the subscription custody rows intact (Codex
    review: prove owner-row prune/insert preserves serving custody)."""
    import base64 as _b64mod
    import sqlite3 as _sqlite

    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.storage import db_path

    udir = _make_universe(base, "u-custody", admin="founder")
    codex_auth = _b64mod.b64encode(b'{"tokens":{"a":"b"}}').decode("ascii")
    write_credential_vault(
        udir,
        [
            {"credential_type": "llm_subscription", "service": "claude",
             "oauth_token": "tok"},
            {"credential_type": "llm_subscription", "service": "codex",
             "auth_json_b64": codex_auth},
        ],
        owner_user_id="founder",
        universe_id="u-custody",
    )

    _login("founder")
    assert _connect("u-custody", secret="sk-http")["status"] == "provisioned"

    conn = _sqlite.connect(db_path(base))
    try:
        rows = {
            (str(s), str(o))
            for s, o in conn.execute(
                "SELECT service, owner_user_id FROM llm_credential_deposit_owners "
                "WHERE universe_id = ?",
                ("u-custody",),
            ).fetchall()
        }
    finally:
        conn.close()
    # claude/codex serving-custody rows survive the http prune; http adds its own.
    assert rows == {
        ("claude", "founder"),
        ("codex", "founder"),
        ("http:webhook:acme", "founder"),
    }


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


# --------------------------------------------------------------------------- #
# Endpoint EXTENSION — a credential is deposited once and grows with the work.
# Founder 2026-08-27: "not for each action with that credential".
# --------------------------------------------------------------------------- #

_MORE = [
    {"host": "api.example.com", "path_template": "/v1/messages", "methods": ["POST"]},
    {"host": "api.example.com", "path_template": "/v1/threads", "methods": ["POST"]},
]


def test_adding_an_endpoint_extends_instead_of_conflicting(base: Path) -> None:
    """Before this, a deterministic id plus ANY policy difference was a hard
    conflict — so adding one endpoint meant a whole new connection under a new
    name, and another paste of the same key."""
    _make_universe(base, "u-ext", admin="founder")
    _login("founder")
    assert _connect("u-ext", secret="sk-v1")["status"] == "provisioned"

    out = _connect("u-ext", secret="sk-v1", endpoints=_MORE)

    assert out["status"] == "provisioned", out
    paths = sorted(e["path_template"] for e in out["allowed_endpoints"])
    assert paths == ["/v1/messages", "/v1/threads"]
    # The original endpoint survives — extension adds, it never replaces.
    from tinyassets.api.http_connection import _ids

    conn_id, _ = _ids(universe_id="u-ext", destination="webhook:acme")
    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert sorted(e.path_template for e in resource.allowed_endpoints) == [
        "/v1/messages", "/v1/threads",
    ]


def test_extension_widens_the_method_scope_with_it(base: Path) -> None:
    """The scope is the method union the effector matches a verb against, so it
    has to grow with the endpoints or the new one is unusable."""
    _make_universe(base, "u-ext2", admin="founder")
    _login("founder")
    _connect("u-ext2", secret="sk-v1")

    out = _connect("u-ext2", secret="sk-v1", endpoints=[
        {"host": "api.example.com", "path_template": "/v1/messages",
         "methods": ["POST"]},
        {"host": "api.example.com", "path_template": "/v1/files", "methods": ["PUT"]},
    ])

    assert out["status"] == "provisioned"
    from tinyassets.api.http_connection import _ids

    conn_id, _ = _ids(universe_id="u-ext2", destination="webhook:acme")
    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert sorted(resource.scopes) == ["POST", "PUT"]


def test_removing_an_endpoint_is_still_a_conflict(base: Path) -> None:
    """Only ADDITION is an extension. Dropping an endpoint another graph depends
    on is a different, destructive intent and must not happen by re-deposit."""
    _make_universe(base, "u-narrow", admin="founder")
    _login("founder")
    assert _connect("u-narrow", secret="sk-v1", endpoints=_MORE)["status"] == "provisioned"

    out = _connect("u-narrow", secret="sk-v2", endpoints=[_MORE[0]])

    assert out == {"error": "connection_conflict", "resource": "connection"}
    from tinyassets.api.http_connection import _ids

    conn_id, _ = _ids(universe_id="u-narrow", destination="webhook:acme")
    resource = _ledger(base, "founder")._get_connection_resource(conn_id)
    assert len(resource.allowed_endpoints) == 2, "nothing was dropped"


def test_extension_still_refuses_a_different_owner_or_scheme(base: Path) -> None:
    """Extension relaxes ONE field. Every other immutable check still holds."""
    from tinyassets.daemon_server import grant_universe_access

    _make_universe(base, "u-ext3", admin="founder")
    grant_universe_access(base, universe_id="u-ext3", actor_id="other",
                          permission="admin", granted_by="founder")
    _login("founder")
    _connect("u-ext3", secret="sk-v1")

    # A different auth scheme, even while adding endpoints, is not an extension.
    assert _connect("u-ext3", secret="u:p", endpoints=_MORE,
                    auth_scheme="basic")["error"] == "connection_conflict"
    # Nor is a different owner.
    _login("other")
    assert _connect("u-ext3", secret="sk-v1",
                    endpoints=_MORE)["error"] == "connection_conflict"


def test_an_unchanged_redeposit_is_still_idempotent(base: Path) -> None:
    """Extension must not turn the ordinary same-policy re-deposit into a write."""
    _make_universe(base, "u-same", admin="founder")
    _login("founder")
    first = _connect("u-same", secret="sk-v1")
    again = _connect("u-same", secret="sk-v2")

    assert again["status"] == "provisioned"
    assert again["connection_id"] == first["connection_id"]
    assert again["allowed_endpoints"] == first["allowed_endpoints"]


# --------------------------------------------------------------------------- #
# Removal — grant, row, AND secret. Anything less is not a removal.
# --------------------------------------------------------------------------- #


def _forget(uid: str, destination: str = "webhook:acme") -> Any:
    from tinyassets.api.http_connection import forget_http

    return forget_http(universe_id=uid,
                       payload=json.dumps({"destination": destination}))


def test_forgetting_removes_the_secret_not_just_the_grant(base: Path) -> None:
    """The vault could only add or replace — `_merge_single_record` has no branch
    that drops a record — so nothing could take a secret back out. Revoking the
    grant stopped it being USABLE while the material stayed on disk, and calling
    that "removed" would have been a lie."""
    udir = _make_universe(base, "u-forget", admin="founder")
    _login("founder")
    assert _connect("u-forget", secret="sk-SECRET-v1")["status"] == "provisioned"
    assert len(_http_records(udir)) == 1

    out = _forget("u-forget")

    assert out["status"] == "forgotten"
    assert out["secret_removed"] is True
    assert _http_records(udir) == [], "the secret must actually be gone"
    from tinyassets.api.http_connection import _ids

    conn_id, grant_id = _ids(universe_id="u-forget", destination="webhook:acme")
    ledger = _ledger(base, "founder")
    assert ledger._get_connection_resource(conn_id) is None
    assert ledger.get_grant(grant_id) is None


def test_a_forgotten_name_is_free_again(base: Path) -> None:
    """THE reason removal deletes rather than tombstones. revoke_connection
    stamps revoked_at and leaves the row, and ids are deterministic on
    (universe, destination) — so a tombstone would burn that name forever."""
    _make_universe(base, "u-reuse", admin="founder")
    _login("founder")
    _connect("u-reuse", secret="sk-v1")
    _forget("u-reuse")

    again = _connect("u-reuse", secret="sk-v2")

    assert again["status"] == "provisioned", again
    assert [e["path_template"] for e in again["allowed_endpoints"]] == ["/v1/messages"]


def test_a_second_forget_refuses_rather_than_deleting_whatever_is_there_now(
    base: Path,
) -> None:
    """Codex 2026-08-27: the first version claimed "idempotent, safe to retry",
    and it was destructive. Fail between the row deletion and the secret
    deletion, let the owner re-deposit, retry — and the retry deleted the NEW
    credential. Nothing in a stateless "forget destination X" call distinguishes
    a retry from a fresh request, and ids are deterministic so even the
    connection id matches. So a forget with no connection present is a refusal."""
    udir = _make_universe(base, "u-idem", admin="founder")
    _login("founder")
    _connect("u-idem", secret="sk-v1")

    assert _forget("u-idem")["secret_removed"] is True
    assert _forget("u-idem") == {"error": "not_found", "resource": "connection"}

    # The case that actually matters: a re-deposit after a forget must survive a
    # stale retry of that forget.
    assert _connect("u-idem", secret="sk-NEW")["status"] == "provisioned"
    assert _forget("u-idem")["secret_removed"] is True  # deliberate, not stale
    _connect("u-idem", secret="sk-NEWER")
    recs = _http_records(udir)
    assert len(recs) == 1 and recs[0]["token"] == "sk-NEWER"


def test_a_co_admin_cannot_forget_another_principals_credential(base: Path) -> None:
    from tinyassets.daemon_server import grant_universe_access

    udir = _make_universe(base, "u-fowner", admin="founder")
    grant_universe_access(base, universe_id="u-fowner", actor_id="coadmin",
                          permission="admin", granted_by="founder")
    _login("founder")
    _connect("u-fowner", secret="founder-secret")

    _login("coadmin")
    assert _forget("u-fowner") == {"error": "not_found", "resource": "connection"}
    _login("founder")
    assert len(_http_records(udir)) == 1, "the owner's secret survived"


def test_forgetting_needs_an_owner(base: Path) -> None:
    _make_universe(base, "u-fauth", admin="founder", write="writer")
    _login("writer")
    assert _forget("u-fauth") == {"error": "not_found", "resource": "connection"}
    _logout()
    assert _forget("u-fauth")["error"] == "authentication_required"


def test_forget_routes_through_write_graph(base: Path) -> None:
    import importlib

    from tinyassets import universe_server as us

    udir = _make_universe(base, "u-froute", admin="founder")
    _login("founder")
    _connect("u-froute", secret="sk-route")
    importlib.reload(us)
    try:
        raw = us.write_graph(target="connection", operation="forget_http",
                             graph_id="u-froute",
                             payload_json=json.dumps({"destination": "webhook:acme"}))
        assert json.loads(raw)["status"] == "forgotten"
        assert _http_records(udir) == []
    finally:
        importlib.reload(us)


def test_an_orphaned_secret_cannot_be_deleted_by_a_co_admin(base: Path) -> None:
    """Codex reproduction: orphan a credential (vault write succeeds, connection
    creation fails), then have a co-admin call forget. With no connection row
    there is no proof of ownership, so the first version deleted another
    principal's secret. An absent row is a refusal, not a licence."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.daemon_server import grant_universe_access

    udir = _make_universe(base, "u-orph", admin="founder")
    grant_universe_access(base, universe_id="u-orph", actor_id="coadmin",
                          permission="admin", granted_by="founder")
    # An orphan: vault record with no connection row.
    write_credential_vault(
        udir,
        [{"credential_type": "http", "service": "webhook:acme",
          "destination": "webhook:acme", "token": "sk-ORPHAN"}],
        owner_user_id="founder", universe_id="u-orph",
    )
    assert len(_http_records(udir)) == 1

    _login("coadmin")
    assert _forget("u-orph") == {"error": "not_found", "resource": "connection"}
    assert _http_records(udir)[0]["token"] == "sk-ORPHAN", "the orphan survived"


def test_the_ledger_delete_uses_the_verified_principal_not_an_argument(base: Path) -> None:
    """Codex: with verifier identity `mallory`, passing owner_user_id="alice"
    deleted Alice's rows. The owner now comes from the trusted verifier, so the
    invariant holds regardless of who calls it."""
    import inspect

    from tinyassets.storage.outbound_connections import ConnectionLedger

    for name in ("delete_connection", "delete_grant"):
        sig = inspect.signature(getattr(ConnectionLedger, name))
        assert "owner_user_id" not in sig.parameters, name
        src = inspect.getsource(getattr(ConnectionLedger, name))
        assert "require_authenticated_principal_id()" in src, name

    _make_universe(base, "u-verif", admin="founder")
    _login("founder")
    _connect("u-verif", secret="sk-v1")
    from tinyassets.api.http_connection import _ids

    conn_id, grant_id = _ids(universe_id="u-verif", destination="webhook:acme")
    # A ledger whose verifier says "mallory" cannot delete founder's rows.
    mallory = ConnectionLedger(base / "outbound.db",
                               verify_authenticated_principal=lambda: "mallory")
    assert mallory.delete_grant(grant_id=grant_id) is False
    assert mallory.delete_connection(connection_id=conn_id) is False
    assert _ledger(base, "founder")._get_connection_resource(conn_id) is not None
