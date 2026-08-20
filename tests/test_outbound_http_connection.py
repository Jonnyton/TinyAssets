"""Connection descriptor, endpoint allowlist, and redacted-view tests.

Scope: channel-agnostic-outbound activation slice — the ``http`` connection
descriptor (design.md D2), the per-connection endpoint allowlist (D3), and the
``ConnectionView`` redaction that keeps ``credential_ref`` out of every caller
projection. These exercise the STORAGE + validation seams; the live transport
and its SSRF hardening are covered in ``test_outbound_ssrf_driver.py``.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3

import pytest

from tinyassets.storage.outbound_connections import (
    ConnectionLedger,
    ConnectionView,
    OutboundEndpoint,
    SsrfValidationError,
    _parse_allowed_endpoints,
    _validate_endpoint,
)


def _http_endpoints():
    return [
        {"host": "api.example.com", "path_template": "/v1/messages", "methods": ["POST"]},
        {
            "host": "api.example.com",
            "path_template": "/v1/threads/{id}",
            "methods": ["GET"],
            # Every {param} MUST declare a value pattern (FIX 3).
            "param_patterns": {"id": r"[A-Za-z0-9_-]+"},
        },
    ]


def _create_http_connection(ledger, *, credential_ref="vault://http/SECRET-REF-VALUE"):
    return ledger.create_connection(
        connection_id="conn-http",
        owner_user_id="user-1",
        connection_class="outbound-http",
        scopes=("POST", "GET"),
        provider="http",
        destination="api.example.com",
        credential_ref=credential_ref,
        connection_type="http",
        auth_scheme="bearer",
        allowed_endpoints=_http_endpoints(),
    )


# --------------------------------------------------------------------------- #
# Descriptor persistence + round-trip
# --------------------------------------------------------------------------- #
def test_http_descriptor_persists_and_round_trips(tmp_path):
    db_path = tmp_path / "boundary.db"
    ledger = ConnectionLedger(db_path)
    created = _create_http_connection(ledger)

    assert created.connection_type == "http"
    assert created.auth_scheme == "bearer"
    assert created.allowed_endpoints == (
        OutboundEndpoint("api.example.com", "/v1/messages", ("POST",)),
        OutboundEndpoint(
            "api.example.com",
            "/v1/threads/{id}",
            ("GET",),
            param_patterns=(("id", r"[A-Za-z0-9_-]+"),),
        ),
    )

    reopened = ConnectionLedger(db_path)
    assert reopened.get_connection("conn-http") == created


def test_legacy_connection_reads_back_as_empty_descriptor(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    legacy = ledger.create_connection(
        connection_id="conn-legacy",
        owner_user_id="user-1",
        connection_class="pull-request-writer",
        scopes=("pull_requests:write",),
        provider="github",
        destination="github.com/acme/widgets",
        credential_ref="vault://github/acme/widgets",
    )
    assert legacy.connection_type == ""
    assert legacy.auth_scheme == ""
    assert legacy.allowed_endpoints == ()
    assert ledger.get_connection("conn-legacy") == legacy


def test_alter_migration_backfills_descriptor_columns_on_old_db(tmp_path):
    # Simulate a pre-descriptor DB: a connections table WITHOUT the new columns.
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as raw:
        raw.execute(
            """
            CREATE TABLE outbound_connections (
                connection_id   TEXT PRIMARY KEY,
                owner_user_id   TEXT NOT NULL,
                connection_class TEXT NOT NULL,
                scopes_json     TEXT NOT NULL,
                provider        TEXT NOT NULL,
                destination     TEXT NOT NULL,
                credential_ref  TEXT NOT NULL,
                revoked_at      REAL
            )
            """
        )
        raw.execute(
            "INSERT INTO outbound_connections VALUES (?,?,?,?,?,?,?,NULL)",
            (
                "conn-old",
                "user-1",
                "pull-request-writer",
                json.dumps(["pull_requests:write"]),
                "github",
                "github.com/acme/widgets",
                "vault://github/acme/widgets",
            ),
        )

    # Opening the ledger runs the ALTER migration; the old row reads back clean.
    ledger = ConnectionLedger(db_path)
    resource = ledger.get_connection("conn-old")
    assert resource is not None
    assert resource.connection_type == ""
    assert resource.allowed_endpoints == ()


# --------------------------------------------------------------------------- #
# ConnectionView redaction — credential_ref never leaks
# --------------------------------------------------------------------------- #
def test_connection_view_hides_credential_ref(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    _create_http_connection(ledger, credential_ref="vault://http/SECRET-REF-VALUE")

    view = ledger.get_connection_view("conn-http")
    assert isinstance(view, ConnectionView)
    assert not hasattr(view, "credential_ref")
    # No serialization of the view (dict, repr, or json) exposes the secret ref.
    blob = json.dumps(view.as_dict()) + repr(view)
    assert "SECRET-REF-VALUE" not in blob
    # The non-secret descriptor is present for CRUD callers.
    assert view.connection_type == "http"
    assert view.allowed_endpoints[0].host == "api.example.com"


def test_list_connection_views_are_all_redacted(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    _create_http_connection(ledger, credential_ref="vault://http/LIST-SECRET-REF")

    views = ledger.list_connection_views(owner_user_id="user-1")
    assert len(views) == 1
    assert all(isinstance(v, ConnectionView) for v in views)
    blob = json.dumps([v.as_dict() for v in views]) + repr(views)
    assert "LIST-SECRET-REF" not in blob


# --------------------------------------------------------------------------- #
# create_connection validation for the http type
# --------------------------------------------------------------------------- #
def test_http_connection_requires_an_allowlist(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    with pytest.raises(SsrfValidationError, match="at least one allowed endpoint"):
        ledger.create_connection(
            connection_id="conn-http",
            owner_user_id="user-1",
            connection_class="outbound-http",
            scopes=("POST",),
            provider="http",
            destination="api.example.com",
            credential_ref="vault://http/ref",
            connection_type="http",
            auth_scheme="bearer",
            allowed_endpoints=[],
        )


def test_http_connection_rejects_unsupported_auth_scheme(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    with pytest.raises(SsrfValidationError, match="auth scheme is not supported"):
        ledger.create_connection(
            connection_id="conn-http",
            owner_user_id="user-1",
            connection_class="outbound-http",
            scopes=("POST",),
            provider="http",
            destination="api.example.com",
            credential_ref="vault://http/ref",
            connection_type="http",
            auth_scheme="digest",  # not a supported http auth scheme
            allowed_endpoints=_http_endpoints(),
        )


# --------------------------------------------------------------------------- #
# Endpoint validation rejects unsafe descriptors at authoring time
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "endpoint",
    [
        {"host": "api.example.com", "path_template": "/a/../b", "methods": ["GET"]},
        {"host": "api.example.com", "path_template": "/a/%2e%2e/b", "methods": ["GET"]},
        {"host": "api.example.com", "path_template": "/a/%5c/b", "methods": ["GET"]},  # FIX 2
        {"host": "api.example.com", "path_template": "/a/%255c/b", "methods": ["GET"]},  # FIX 2
        {"host": "api.example.com", "path_template": "relative/x", "methods": ["GET"]},
        {"host": "10.0.0.5", "path_template": "/x", "methods": ["GET"]},  # IP literal host
        {"host": "localhost", "path_template": "/x", "methods": ["GET"]},  # single label
        {"host": "api.example.com", "path_template": "/x", "methods": ["TRACE"]},  # bad verb
        {"host": "api.example.com", "path_template": "/x", "methods": []},  # no verb
        {"host": "", "path_template": "/x", "methods": ["GET"]},  # empty host
        # FIX 3: a placeholder with no declared pattern.
        {"host": "api.example.com", "path_template": "/v1/{id}", "methods": ["GET"]},
        # FIX 3: a stray param_pattern that names no placeholder.
        {
            "host": "api.example.com",
            "path_template": "/v1/{id}",
            "methods": ["GET"],
            "param_patterns": {"id": "x", "other": "y"},
        },
        # FIX 3: an uncompilable declared pattern.
        {
            "host": "api.example.com",
            "path_template": "/v1/{id}",
            "methods": ["GET"],
            "param_patterns": {"id": "("},
        },
        # FIX 3: a query_pattern for a name not in allowed_query.
        {
            "host": "api.example.com",
            "path_template": "/x",
            "methods": ["GET"],
            "query_patterns": {"mode": "safe"},
        },
    ],
)
def test_unsafe_endpoint_descriptors_are_rejected(endpoint):
    with pytest.raises(SsrfValidationError):
        _validate_endpoint(endpoint)


def test_valid_endpoint_with_param_and_query_rules_round_trips():
    endpoint = _validate_endpoint(
        {
            "host": "api.example.com",
            "path_template": "/v1/accounts/{account_id}/secrets",
            "methods": ["get"],
            "param_patterns": {"account_id": "self"},
            "allowed_query": ["mode", "mode"],  # de-duped
            "query_patterns": {"mode": "safe"},
        }
    )
    assert endpoint.param_patterns == (("account_id", "self"),)
    assert endpoint.allowed_query == ("mode",)
    assert endpoint.query_patterns == (("mode", "safe"),)


# --------------------------------------------------------------------------- #
# FIX 1 — unknown connection_type rejected at creation
# --------------------------------------------------------------------------- #
def test_unknown_connection_type_rejected_at_creation(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    with pytest.raises(SsrfValidationError, match="connection_type is not supported"):
        ledger.create_connection(
            connection_id="conn-bogus",
            owner_user_id="user-1",
            connection_class="cc",
            scopes=("POST",),
            provider="github",
            destination="github.com/acme/widgets",
            credential_ref="vault://x",
            connection_type="htpt",  # typo — must be refused, not stored
            auth_scheme="bearer",
            allowed_endpoints=[],
        )


@pytest.mark.parametrize(
    "foreign_ref",
    [
        "workos-pipes://github/victim-user",  # the exact confused-deputy repro
        "vault://github/acme/widgets",
        "vault://slack/some-conn",
        "test-vault-file:/etc/passwd",
    ],
)
def test_http_connection_rejects_foreign_scheme_credential_ref(tmp_path, foreign_ref):
    # Codex FIX 1 (creation side): an http connection may reference ONLY a
    # vault://http/ credential — a github/workos/slack ref is refused at creation
    # so it can never later vend a foreign token to the http driver.
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    with pytest.raises(SsrfValidationError, match="vault://http"):
        ledger.create_connection(
            connection_id="conn-http",
            owner_user_id="user-1",
            connection_class="outbound-http",
            scopes=("POST",),
            provider="github",  # attacker-chosen provider
            destination="attacker.example",
            credential_ref=foreign_ref,
            connection_type="http",
            auth_scheme="bearer",
            allowed_endpoints=[
                {"host": "attacker.example", "path_template": "/collect", "methods": ["POST"]},
            ],
        )


def test_creation_rejects_http_placeholder_without_declared_pattern(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    with pytest.raises(SsrfValidationError, match="declare exactly the path placeholders"):
        ledger.create_connection(
            connection_id="conn-http",
            owner_user_id="user-1",
            connection_class="outbound-http",
            scopes=("GET",),
            provider="http",
            destination="api.example.com",
            credential_ref="vault://http/ref",
            connection_type="http",
            auth_scheme="bearer",
            allowed_endpoints=[
                {"host": "api.example.com", "path_template": "/v1/{id}", "methods": ["GET"]},
            ],
        )


# --------------------------------------------------------------------------- #
# Structural redaction — get_connection/create return a view with NO
# credential_ref field at all (Codex FIX 3)
# --------------------------------------------------------------------------- #
def test_get_connection_and_create_return_redacted_views_without_credential_ref(tmp_path):
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    created = _create_http_connection(ledger, credential_ref="vault://http/REDACT-SECRET-REF")
    fetched = ledger.get_connection("conn-http")
    for projection in (created, fetched):
        # Redaction is STRUCTURAL: no attribute, no vars() key, no asdict() key,
        # nothing in repr/str/as_dict reveals the credential reference.
        assert isinstance(projection, ConnectionView)
        assert not hasattr(projection, "credential_ref")
        assert "credential_ref" not in vars(projection)
        assert "credential_ref" not in dataclasses.asdict(projection)
        blob = repr(projection) + str(projection) + json.dumps(projection.as_dict())
        assert "REDACT-SECRET-REF" not in blob
    # The trusted-internal credential-bearing read still exposes the ref (broker
    # child + ownership checks need it), and even it masks the ref in its repr.
    resource = ledger._get_connection_resource("conn-http")
    assert resource.credential_ref == "vault://http/REDACT-SECRET-REF"
    assert "REDACT-SECRET-REF" not in repr(resource)
    assert "***redacted***" in repr(resource)


def test_valid_endpoint_normalizes_host_and_methods():
    endpoint = _validate_endpoint(
        {"host": "API.Example.COM", "path_template": "/v1/x", "methods": ["get", "post", "get"]}
    )
    assert endpoint.host == "api.example.com"  # lower-cased
    assert endpoint.methods == ("GET", "POST")  # upper-cased, de-duped


def test_parse_allowed_endpoints_from_stored_json_string():
    stored = json.dumps(_http_endpoints())
    parsed = _parse_allowed_endpoints(stored)
    assert parsed[0] == OutboundEndpoint("api.example.com", "/v1/messages", ("POST",))
    assert _parse_allowed_endpoints("") == ()
    assert _parse_allowed_endpoints(None) == ()
