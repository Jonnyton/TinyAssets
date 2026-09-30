"""Capability-URL connections — the secret is a path segment, held in the vault.

Requirement source:
``openspec/changes/capability-url-connections/specs/http-connections-and-outbound-authority/spec.md``.

THE live failure, 2026-09-30 (free account universe
``u-01ky3zh1arr8qth8jee7zx63pq``, turn ``d75a6cb6447e4434b8b0d6aecf706475``): a
universe was handed a friend's ``https://tinyassets.io/mcp/hooks/<secret>`` link
to send bug reports to. It asked for an "API Token or Bearer Token" that does not
exist, hit ``auth_scheme must be one of basic, bearer, header, oauth1a``, and
settled on ``bearer`` with the secret hardcoded into ``path_template`` — stored
in the clear in the grant, projected to the owner and to any remix — while the
pasted value went out as a useless ``Authorization`` header.

Every case here would FAIL if its guard were removed. The two that carry the
design are:

* ``test_wire_request_carries_the_substituted_secret`` — the real transport path
  through a loopback stub records the path the receiver actually saw; and
* ``test_allowlist_refuses_a_node_supplied_value_in_the_secret_position`` — the
  reserved placeholder's pattern is the LITERAL token, which is what makes the
  egress boundary decidable with no secret material in the URL.

A neutral example host is used wherever the platform's own is not the point: the
primitive names no service, and ``url_secret`` is exactly as channel-agnostic as
``bearer``.
"""

from __future__ import annotations

import http.server
import json
import socket
import ssl
import threading
from pathlib import Path
from typing import Any

import pytest

from tinyassets.api.http_connection import (
    URL_SECRET_FIELD_NAME,
    embedded_secret_refusal,
    extract_url_secret,
    looks_like_embedded_secret,
)
from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
from tinyassets.storage.outbound_connections import (
    _URL_SECRET_SCHEME,
    ConnectionSecretBundle,
    SsrfValidationError,
    _build_http_secret_bundle,
    _parse_allowed_endpoints,
    _ssrf_auth_headers,
    _SsrfHardenedHttpDriver,
    _substitute_url_secret,
    _TrustedNetworkDriver,
    url_secret_token,
    validate_url_secret_binding,
    validate_url_secret_value,
)

#: A real-shaped capability secret: `secrets.token_urlsafe(32)` is what
#: `storage/webhook_hooks.mint` produces, so this is the exact shape the
#: platform's own `/mcp/hooks/<token>` receiver hands out.
HOOK_SECRET = "MRL8k3nZ-Ht9xWq2vB7pC4dF6gJ0sYaT1uK5wQ9eXmZ7b0"
HOOK_HOST = "hooks.example.com"
HOOK_TEMPLATE = "/mcp/hooks/{secret}"
HOOK_URL = f"https://{HOOK_HOST}/mcp/hooks/{HOOK_SECRET}"

#: Slack's secret is three segments, which is why `{secret+}` exists.
SLACK_SECRET = "T024BE7LD/B01ABCDEF/nOpQrStUvWxYz0123456789A"
SLACK_HOST = "hooks.slack.example"
SLACK_TEMPLATE = "/services/{secret+}"


def _endpoints(
    host: str = HOOK_HOST, template: str = HOOK_TEMPLATE, methods: Any = ("POST",)
) -> list[dict[str, Any]]:
    return [{"host": host, "path_template": template, "methods": list(methods)}]


def _parsed(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
    return _parse_allowed_endpoints(_endpoints(*args, **kwargs))


# --------------------------------------------------------------------------- #
# Auth / universe harness (same shape as test_http_connection_provisioning).
# --------------------------------------------------------------------------- #
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
    from tinyassets.auth.middleware import clear_identity

    set_provider(DevAuthProvider())
    clear_identity()


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


def _make_universe(base: Path, uid: str, *, admin: str = "") -> Path:
    from tinyassets.daemon_server import grant_universe_access

    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    if admin:
        grant_universe_access(
            base, universe_id=uid, actor_id=admin, permission="admin", granted_by=admin
        )
    return udir


def _connect(
    uid: str,
    *,
    destination: str = "bug-reports",
    secret: str = HOOK_URL,
    endpoints: Any = None,
    auth_scheme: str | None = _URL_SECRET_SCHEME,
    access: str | None = None,
) -> dict[str, Any]:
    from tinyassets.api.http_connection import connect_http

    doc: dict[str, Any] = {
        "destination": destination,
        "secret": secret,
        "allowed_endpoints": _endpoints() if endpoints is None else endpoints,
    }
    if auth_scheme is not None:
        doc["auth_scheme"] = auth_scheme
    if access is not None:
        doc["access"] = access
    return connect_http(universe_id=uid, payload=json.dumps(doc))


def _http_records(udir: Path) -> list[dict[str, Any]]:
    from tinyassets.credential_vault import load_credential_vault

    return [
        r for r in load_credential_vault(udir) if r.get("credential_type") == "http"
    ]


# --------------------------------------------------------------------------- #
# 1. The endpoint grammar: the reserved placeholder and its literal pattern.
# --------------------------------------------------------------------------- #
def test_reserved_placeholder_takes_the_literal_token_as_its_pattern() -> None:
    """THE security property (design D2).

    Every other ``{param}`` must declare a value pattern that admits a
    node-supplied segment. The reserved one is patterned as the ESCAPED LITERAL
    TOKEN, so the stored endpoint matches the concrete path ``/mcp/hooks/{secret}``
    and nothing else — which is how the allowlist can be evaluated with no secret
    material present at all.
    """
    endpoint = _parsed()[0]
    assert dict(endpoint.param_patterns) == {"secret": r"\{secret\}"}
    rest = _parsed(SLACK_HOST, SLACK_TEMPLATE)[0]
    assert dict(rest.param_patterns) == {"secret": r"\{secret\+\}"}


def test_a_caller_declared_pattern_for_the_reserved_name_is_refused() -> None:
    """A permissive pattern here would re-admit exactly the node-supplied
    segment the reserved placeholder exists to exclude."""
    with pytest.raises(SsrfValidationError) as exc:
        _parse_allowed_endpoints(
            [
                {
                    "host": HOOK_HOST,
                    "path_template": HOOK_TEMPLATE,
                    "methods": ["POST"],
                    "param_patterns": {"secret": ".*"},
                }
            ]
        )
    assert "param_patterns" in str(exc.value)


def test_url_secret_token_recognizes_both_spellings_and_nothing_else() -> None:
    assert url_secret_token(_parsed()[0]) == "{secret}"
    assert url_secret_token(_parsed(SLACK_HOST, SLACK_TEMPLATE)[0]) == "{secret+}"
    ordinary = _parse_allowed_endpoints(
        [
            {
                "host": HOOK_HOST,
                "path_template": "/repos/o/r/contents/{path+}",
                "methods": ["GET"],
                "param_patterns": {"path": "[A-Za-z0-9._/-]{1,200}"},
            }
        ]
    )
    assert url_secret_token(ordinary[0]) == ""


# --------------------------------------------------------------------------- #
# 2. The scheme <-> placeholder binding, both directions, three checkpoints.
# --------------------------------------------------------------------------- #
def test_binding_refuses_a_header_scheme_that_carries_the_placeholder() -> None:
    """The live failure's inverse: a `{secret}` template on a header scheme puts
    the literal token in the path AND the real credential in a header."""
    with pytest.raises(SsrfValidationError) as exc:
        validate_url_secret_binding("bearer", _parsed())
    assert _URL_SECRET_SCHEME in str(exc.value)


def test_binding_refuses_url_secret_without_a_placeholder() -> None:
    plain = _parse_allowed_endpoints(
        [{"host": HOOK_HOST, "path_template": "/mcp/hooks/x", "methods": ["POST"]}]
    )
    with pytest.raises(SsrfValidationError):
        validate_url_secret_binding(_URL_SECRET_SCHEME, plain)


def test_binding_refuses_a_mixed_connection() -> None:
    """Not "at least one endpoint": a mixed connection has endpoints reachable
    without the secret, and the owner's grant sentence could not say which."""
    mixed = _parse_allowed_endpoints(
        _endpoints()
        + [{"host": HOOK_HOST, "path_template": "/status", "methods": ["GET"]}]
    )
    with pytest.raises(SsrfValidationError):
        validate_url_secret_binding(_URL_SECRET_SCHEME, mixed)


def test_binding_refuses_a_redirect_following_capability_endpoint() -> None:
    """A 3xx off a capability URL hands the secret path to the next origin, and
    the redirect chain's re-match cannot match a substituted path anyway — so
    refuse it loudly rather than behave as no-follow in silence."""
    following = _parse_allowed_endpoints(
        [
            {
                "host": HOOK_HOST,
                "path_template": HOOK_TEMPLATE,
                "methods": ["GET"],
                "redirect_mode": "public_https_get",
            }
        ]
    )
    with pytest.raises(SsrfValidationError) as exc:
        validate_url_secret_binding(_URL_SECRET_SCHEME, following)
    assert "redirect" in str(exc.value)


def test_create_connection_enforces_the_binding_at_the_storage_boundary(
    base: Path,
) -> None:
    """Every issuer assembles its own payload, so the rule lives where they all
    pass — the same reason `validate_git_scopes` is there."""
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(
        base / "outbound.db", verify_authenticated_principal=lambda: "founder"
    )
    with pytest.raises(SsrfValidationError):
        ledger.create_connection(
            connection_id="c-1",
            owner_user_id="founder",
            connection_class="http",
            scopes=("POST",),
            provider="http",
            destination="bug-reports",
            credential_ref="vault://http/bug-reports",
            connection_type="http",
            auth_scheme="bearer",  # a header scheme with a {secret} template
            allowed_endpoints=_endpoints(),
        )


def test_create_connection_refuses_a_full_capability_url(base: Path) -> None:
    from tinyassets.storage.outbound_connections import ACCESS_FULL, ConnectionLedger

    ledger = ConnectionLedger(
        base / "outbound.db", verify_authenticated_principal=lambda: "founder"
    )
    with pytest.raises(SsrfValidationError) as exc:
        ledger.create_connection(
            connection_id="c-2",
            owner_user_id="founder",
            connection_class="http",
            scopes=("POST",),
            provider="http",
            destination="bug-reports",
            credential_ref="vault://http/bug-reports",
            connection_type="http",
            auth_scheme=_URL_SECRET_SCHEME,
            allowed_endpoints=_endpoints(),
            access_mode=ACCESS_FULL,
        )
    assert "full" in str(exc.value)


def test_set_access_mode_cannot_promote_a_capability_url_to_full(base: Path) -> None:
    """The refusal is a SQL predicate, so a concurrent redeposit cannot slip
    between a read and the write."""
    from tinyassets.storage.outbound_connections import (
        ACCESS_EXACT,
        ACCESS_FULL,
        ConnectionLedger,
    )

    ledger = ConnectionLedger(
        base / "outbound.db", verify_authenticated_principal=lambda: "founder"
    )
    ledger.create_connection(
        connection_id="c-3",
        owner_user_id="founder",
        connection_class="http",
        scopes=("POST",),
        provider="http",
        destination="bug-reports",
        credential_ref="vault://http/bug-reports",
        connection_type="http",
        auth_scheme=_URL_SECRET_SCHEME,
        allowed_endpoints=_endpoints(),
    )
    endpoints_json, scopes_json = ledger.policy_json("c-3")
    assert (
        ledger.set_access_mode(
            connection_id="c-3",
            access_mode=ACCESS_FULL,
            expected_mode=ACCESS_EXACT,
            expected_endpoints_json=endpoints_json,
            expected_scopes_json=scopes_json,
        )
        is False
    )
    assert ledger.access_mode("c-3") == ACCESS_EXACT


def test_dispatch_refuses_a_row_mutated_out_of_the_scheme() -> None:
    """The TOCTOU closure. The broker re-reads the row per call, so a row
    mutated from `url_secret` to `bearer` must be refused BEFORE a bundle
    exists — otherwise the placeholder goes out literally in the path and the
    secret segment goes out in an Authorization header.
    """
    driver = _TrustedNetworkDriver(
        {"allow_test_fixtures": False, "allow_http_connections": True}, Path(".")
    )
    with pytest.raises(SsrfValidationError) as exc:
        driver(
            connection_type="http",
            auth_scheme="bearer",
            allowed_endpoints=_parsed(),
            credential=HOOK_SECRET,
            verb="POST",
            provider="http",
            destination="bug-reports",
            request={"url": f"https://{HOOK_HOST}{HOOK_TEMPLATE}"},
        )
    assert _URL_SECRET_SCHEME in str(exc.value)


# --------------------------------------------------------------------------- #
# 3. The stored segment's grammar (what makes verbatim substitution safe).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value",
    [
        "has/a/slash",
        "has%2fan%2fencoded%2fslash",
        "..",
        "short",           # under 8 characters
        "has a space here",
        "has\nnewline0000",
        "",
        "tab\t0000000000",
    ],
)
def test_segment_grammar_refuses_anything_that_could_carry_structure(
    value: str,
) -> None:
    with pytest.raises(SsrfValidationError):
        validate_url_secret_value(value, "{secret}")


def test_segment_grammar_accepts_the_real_shapes() -> None:
    assert validate_url_secret_value(HOOK_SECRET, "{secret}") == HOOK_SECRET
    assert validate_url_secret_value(SLACK_SECRET, "{secret+}") == SLACK_SECRET


def test_a_multi_segment_value_needs_the_rest_spelling() -> None:
    with pytest.raises(SsrfValidationError):
        validate_url_secret_value(SLACK_SECRET, "{secret}")


def test_the_bundle_builder_refuses_a_corrupted_vault_record() -> None:
    """The one choke point every dispatch passes through, so a record mutated
    outside the deposit door fails closed rather than reaching a socket."""
    with pytest.raises(SsrfValidationError):
        _build_http_secret_bundle(_URL_SECRET_SCHEME, "../../admin")
    bundle = _build_http_secret_bundle(_URL_SECRET_SCHEME, HOOK_SECRET)
    assert bundle.secret_values() == (HOOK_SECRET,)


def test_the_scheme_emits_no_auth_header() -> None:
    """The live failure sent the pasted value as `Authorization: Bearer`, which
    hands the credential to a second reader for nothing."""
    assert (
        _ssrf_auth_headers(
            _URL_SECRET_SCHEME, ConnectionSecretBundle(token=HOOK_SECRET)
        )
        == {}
    )


# --------------------------------------------------------------------------- #
# 4. Substitution happens AFTER the allowlist, and only on the path.
# --------------------------------------------------------------------------- #
def _canonical(path_qs: str) -> Any:
    from tinyassets.storage.outbound_connections import _CanonicalOutboundUrl

    return _CanonicalOutboundUrl(
        hostname=HOOK_HOST, port=443, path_qs=path_qs, is_ip_literal=False
    )


def test_substitution_replaces_the_placeholder_verbatim() -> None:
    out = _substitute_url_secret(
        _canonical(HOOK_TEMPLATE),
        auth_scheme=_URL_SECRET_SCHEME,
        bundle=ConnectionSecretBundle(token=HOOK_SECRET),
    )
    assert out.path_qs == f"/mcp/hooks/{HOOK_SECRET}"
    assert out.hostname == HOOK_HOST  # the host is never touched: the DNS pin holds


def test_substitution_leaves_the_query_string_alone() -> None:
    """The secret of a capability URL is in the PATH. A placeholder in the query
    was validated against `query_patterns`, and splicing a credential there
    would put it somewhere the owner's grant never described."""
    out = _substitute_url_secret(
        _canonical(f"{HOOK_TEMPLATE}?note=%7Bsecret%7D"),
        auth_scheme=_URL_SECRET_SCHEME,
        bundle=ConnectionSecretBundle(token=HOOK_SECRET),
    )
    assert out.path_qs == f"/mcp/hooks/{HOOK_SECRET}?note=%7Bsecret%7D"


def test_substitution_refuses_a_url_secret_request_that_names_no_placeholder() -> None:
    with pytest.raises(SsrfValidationError):
        _substitute_url_secret(
            _canonical("/mcp/hooks/whatever"),
            auth_scheme=_URL_SECRET_SCHEME,
            bundle=ConnectionSecretBundle(token=HOOK_SECRET),
        )


def test_substitution_refuses_a_placeholder_under_another_scheme() -> None:
    with pytest.raises(SsrfValidationError):
        _substitute_url_secret(
            _canonical(HOOK_TEMPLATE),
            auth_scheme="bearer",
            bundle=ConnectionSecretBundle(token=HOOK_SECRET),
        )


def test_substitution_refuses_a_repeated_placeholder() -> None:
    with pytest.raises(SsrfValidationError):
        _substitute_url_secret(
            _canonical("/mcp/hooks/{secret}/{secret}"),
            auth_scheme=_URL_SECRET_SCHEME,
            bundle=ConnectionSecretBundle(token=HOOK_SECRET),
        )


def test_substitution_is_a_no_op_for_every_other_scheme() -> None:
    plain = _canonical("/v1/messages")
    assert (
        _substitute_url_secret(
            plain, auth_scheme="bearer", bundle=ConnectionSecretBundle(token="t")
        )
        is plain
    )


# --------------------------------------------------------------------------- #
# 5. The wire. A loopback stub records what the receiver actually saw.
# --------------------------------------------------------------------------- #
class _PassThroughTLS:
    def __init__(self) -> None:
        self.verify_mode = ssl.CERT_NONE
        self.check_hostname = False

    def wrap_socket(self, sock, server_hostname=None):  # noqa: ANN001
        return sock


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args: Any) -> None:
        return

    def _serve(self) -> None:
        stub = self.server.stub  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        stub["received"] = {
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": self.rfile.read(length) if length else b"",
        }
        payload = stub["body"]
        self.send_response(stub["status"])
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _serve
    do_POST = _serve


@pytest.fixture
def stub_server() -> Any:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.stub = {"status": 200, "body": b"ok", "received": None}  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _local_driver(server: Any) -> tuple[Any, int]:
    port = server.server_address[1]

    def open_socket(_address, timeout, _source_address):  # noqa: ANN001
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
    )
    return driver, port


def test_wire_request_carries_the_substituted_secret(stub_server: Any) -> None:
    """THE end-to-end proof, at the HTTP layer only.

    MUTATION CHECK: delete the `_substitute_url_secret` call from
    `_SsrfHardenedHttpDriver.__call__` and this fails — the receiver sees the
    literal `{secret}`. Weaken the reserved pattern to `.*` and
    `test_allowlist_refuses_a_node_supplied_value_in_the_secret_position` fails.
    """
    driver, port = _local_driver(stub_server)
    host = f"public.example:{port}"
    endpoints = _parse_allowed_endpoints(
        [
            {
                "host": "public.example",
                "path_template": HOOK_TEMPLATE,
                "methods": ["POST"],
            }
        ]
    )

    result = driver(
        bundle=ConnectionSecretBundle(token=HOOK_SECRET),
        auth_scheme=_URL_SECRET_SCHEME,
        method="POST",
        url=f"https://{host}{HOOK_TEMPLATE}",
        headers={"Content-Type": "application/json"},
        body={"text": "a bug report"},
        allowed_endpoints=endpoints,
    )

    assert result["status"] == 200
    received = stub_server.stub["received"]
    # The receiver saw the REAL capability URL...
    assert received["path"] == f"/mcp/hooks/{HOOK_SECRET}"
    # ...and no Authorization header, because there is nothing to put in one.
    assert "authorization" not in received["headers"]
    assert received["body"] == b'{"text":"a bug report"}'
    # ...and the secret does not ride back out in the returned object.
    assert HOOK_SECRET not in json.dumps(result)


def test_wire_request_carries_a_multi_segment_secret(stub_server: Any) -> None:
    driver, port = _local_driver(stub_server)
    endpoints = _parse_allowed_endpoints(
        [
            {
                "host": "public.example",
                "path_template": SLACK_TEMPLATE,
                "methods": ["POST"],
            }
        ]
    )

    driver(
        bundle=ConnectionSecretBundle(token=SLACK_SECRET),
        auth_scheme=_URL_SECRET_SCHEME,
        method="POST",
        url=f"https://public.example:{port}{SLACK_TEMPLATE}",
        body={"text": "hi"},
        allowed_endpoints=endpoints,
    )

    assert stub_server.stub["received"]["path"] == f"/services/{SLACK_SECRET}"


def test_allowlist_refuses_a_node_supplied_value_in_the_secret_position() -> None:
    """The reserved pattern is the literal token, so a node cannot address the
    secret's position with a value of its own — not even the real secret."""
    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: pytest.fail("must refuse before resolving"),
        validator=lambda addr: addr,
        open_socket=lambda *_a, **_k: pytest.fail("must refuse before dialing"),
        ssl_context=_PassThroughTLS(),
    )
    for path in (
        f"/mcp/hooks/{HOOK_SECRET}",   # the real secret, hardcoded by the node
        "/mcp/hooks/guessed-value-01",
        "/mcp/hooks/{other}",
    ):
        with pytest.raises(SsrfValidationError):
            driver(
                bundle=ConnectionSecretBundle(token=HOOK_SECRET),
                auth_scheme=_URL_SECRET_SCHEME,
                method="POST",
                url=f"https://{HOOK_HOST}{path}",
                allowed_endpoints=_parsed(),
            )


def test_a_failing_far_side_that_echoes_the_url_fails_closed(
    stub_server: Any,
) -> None:
    """A 500 whose body quotes the request URL is the realistic leak: without
    the segment in the bundle, that body would be returned verbatim and land in
    the run's `external_write_errors` preview.

    Because the segment IS a bundle member, `_declassify_response` catches the
    echo and the call fails closed with fixed text instead. MUTATION CHECK:
    return `ConnectionSecretBundle()` from `_build_http_secret_bundle` for this
    scheme and the call succeeds with the secret in the body.
    """
    from tinyassets.storage.outbound_connections import ProxyRequestError

    driver, port = _local_driver(stub_server)
    stub_server.stub.update(
        status=500, body=f"failed calling /mcp/hooks/{HOOK_SECRET}".encode()
    )
    endpoints = _parse_allowed_endpoints(
        [
            {
                "host": "public.example",
                "path_template": HOOK_TEMPLATE,
                "methods": ["POST"],
            }
        ]
    )

    with pytest.raises(ProxyRequestError) as exc:
        driver(
            bundle=ConnectionSecretBundle(token=HOOK_SECRET),
            auth_scheme=_URL_SECRET_SCHEME,
            method="POST",
            url=f"https://public.example:{port}{HOOK_TEMPLATE}",
            body={"text": "x"},
            allowed_endpoints=endpoints,
        )
    assert HOOK_SECRET not in str(exc.value)


def test_a_failing_far_side_that_does_not_echo_is_returned_as_is(
    stub_server: Any,
) -> None:
    """The ordinary failure still reaches the owner: a 500 is evidence, and a
    capability URL must not turn every far-side error into a refusal."""
    driver, port = _local_driver(stub_server)
    stub_server.stub.update(status=500, body=b"internal error")
    endpoints = _parse_allowed_endpoints(
        [
            {
                "host": "public.example",
                "path_template": HOOK_TEMPLATE,
                "methods": ["POST"],
            }
        ]
    )

    result = driver(
        bundle=ConnectionSecretBundle(token=HOOK_SECRET),
        auth_scheme=_URL_SECRET_SCHEME,
        method="POST",
        url=f"https://public.example:{port}{HOOK_TEMPLATE}",
        body={"text": "x"},
        allowed_endpoints=endpoints,
    )
    assert result["status"] == 500
    assert HOOK_SECRET not in json.dumps(result)


# --------------------------------------------------------------------------- #
# 6. The pasted link: the platform extracts the secret.
# --------------------------------------------------------------------------- #
def test_a_pasted_link_yields_the_segment() -> None:
    assert extract_url_secret(HOOK_URL, _parsed()) == (HOOK_SECRET, "")


def test_a_pasted_link_with_a_trailing_slash_is_tolerated() -> None:
    """Zapier and Make show one in their own UI; the template does not carry it."""
    assert extract_url_secret(HOOK_URL + "/", _parsed()) == (HOOK_SECRET, "")


def test_a_pasted_slack_link_yields_all_three_segments() -> None:
    parsed = _parsed(SLACK_HOST, SLACK_TEMPLATE)
    assert extract_url_secret(
        f"https://{SLACK_HOST}/services/{SLACK_SECRET}", parsed
    ) == (SLACK_SECRET, "")


def test_a_bare_segment_is_still_accepted() -> None:
    assert extract_url_secret(HOOK_SECRET, _parsed()) == (HOOK_SECRET, "")


@pytest.mark.parametrize(
    "pasted",
    [
        f"https://evil.example.com/mcp/hooks/{HOOK_SECRET}",          # wrong host
        f"https://{HOOK_HOST}/other/path/{HOOK_SECRET}",              # undeclared path
        f"https://{HOOK_HOST}/mcp/hooks/{HOOK_SECRET}?x=1",           # a query
        f"https://{HOOK_HOST}/mcp/hooks/{HOOK_SECRET}#frag",          # a fragment
        f"https://u:p@{HOOK_HOST}/mcp/hooks/{HOOK_SECRET}",           # userinfo
        f"http://{HOOK_HOST}/mcp/hooks/{HOOK_SECRET}",                # not https
        f"https://{HOOK_HOST}/mcp/hooks/{HOOK_SECRET}/deeper",        # extra segment
        f"https://{HOOK_HOST}/mcp/hooks/short",                       # too short
    ],
)
def test_a_mismatched_link_is_refused_without_echoing_it(pasted: str) -> None:
    value, error = extract_url_secret(pasted, _parsed())
    assert value == ""
    assert error
    # A refusal names the declared TEMPLATE, never the pasted value: repeating
    # it would put the secret in the very error the owner reads aloud.
    assert HOOK_SECRET not in error
    assert HOOK_TEMPLATE in error or "8-512" in error or "1-8 path" in error


def test_an_ambiguous_link_is_refused_rather_than_guessed() -> None:
    """Two carriers that capture DIFFERENT values: which one holds the secret
    would be a guess, and guessing wrong stores half a credential.

    The realistic shape is a Discord-style webhook declared both ways — the
    id+token tail, and the token alone behind a fixed id.
    """
    parsed = _parse_allowed_endpoints(
        [
            {
                "host": "discord.example",
                "path_template": "/api/webhooks/{secret+}",
                "methods": ["POST"],
            },
            {
                "host": "discord.example",
                "path_template": "/api/webhooks/1234567890123/{secret}",
                "methods": ["POST"],
            },
        ]
    )
    value, error = extract_url_secret(
        "https://discord.example/api/webhooks/1234567890123/tOkEn0123456789abcdef",
        parsed,
    )
    assert value == ""
    assert "more than one" in error


def test_two_carriers_that_agree_are_not_ambiguous() -> None:
    """Agreement is not a guess. Both templates capture the same segment, so
    there is exactly one candidate credential and the deposit proceeds."""
    parsed = _parse_allowed_endpoints(
        _endpoints()
        + [
            {
                "host": HOOK_HOST,
                "path_template": "/mcp/hooks/{secret+}",
                "methods": ["POST"],
            }
        ]
    )
    assert extract_url_secret(HOOK_URL, parsed) == (HOOK_SECRET, "")


def test_a_bare_segment_with_several_carriers_asks_for_the_whole_link() -> None:
    parsed = _parse_allowed_endpoints(
        _endpoints()
        + [{"host": "other.example", "path_template": HOOK_TEMPLATE, "methods": ["POST"]}]
    )
    value, error = extract_url_secret(HOOK_SECRET, parsed)
    assert value == ""
    assert "whole link" in error


# --------------------------------------------------------------------------- #
# 7. A hardcoded secret in path_template is refused when authored.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "segment",
    [
        HOOK_SECRET,
        "MRL8k3nZ-Ht9xWq2vB7pC4dF6gJ0sYaT1u",
        "nOpQrStUvWxYz0123456789A",                      # a Slack webhook token
        "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",  # an opaque public id
    ],
)
def test_a_high_entropy_fixed_segment_reads_as_a_secret(segment: str) -> None:
    assert looks_like_embedded_secret(segment) is True


@pytest.mark.parametrize(
    "segment",
    [
        "completions", "messages", "v1", "2", "pulls", "contents", "git", "refs",
        "heads", "spreadsheets", "chat", "repos", "services", "webhooks",
        "incoming-webhook", "api", "oauth", "tweets", "conversations.history",
        "batch_annotate_images", "v1beta2", "2010-04-01", "2024-11-05",
    ],
)
def test_an_ordinary_api_path_segment_is_not_a_secret(segment: str) -> None:
    """The refusal must not fire on real paths. Anything here that tripped it
    would block a legitimate connection at ask time."""
    assert looks_like_embedded_secret(segment) is False


def test_the_refusal_names_both_repairs() -> None:
    """Whichever it is — a credential or a public id — the fix is a placeholder,
    so the error is actionable both ways."""
    refusal = embedded_secret_refusal(
        [{"host": HOOK_HOST, "path_template": f"/mcp/hooks/{HOOK_SECRET}"}]
    )
    assert refusal is not None
    detail = refusal["detail"]
    assert _URL_SECRET_SCHEME in detail
    assert "{secret}" in detail
    assert "param_patterns" in detail


def test_a_placeholder_segment_is_never_flagged() -> None:
    assert embedded_secret_refusal(
        [{"host": HOOK_HOST, "path_template": HOOK_TEMPLATE}]
    ) is None
    assert embedded_secret_refusal(
        [{"host": HOOK_HOST, "path_template": "/repos/o/r/contents/{path+}"}]
    ) is None


def test_reading_a_stored_template_never_applies_the_refusal() -> None:
    """Putting the heuristic in `_validate_path_template` would make an
    already-deposited connection unreadable and unremovable, which is a
    data-loss bug wearing a security fix's name."""
    stored = _parse_allowed_endpoints(
        [
            {
                "host": HOOK_HOST,
                "path_template": f"/mcp/hooks/{HOOK_SECRET}",
                "methods": ["POST"],
            }
        ]
    )
    assert stored[0].path_template == f"/mcp/hooks/{HOOK_SECRET}"


# --------------------------------------------------------------------------- #
# 8. The deposit door, end to end.
# --------------------------------------------------------------------------- #
def test_deposit_stores_only_the_segment(base: Path) -> None:
    udir = _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    result = _connect("u-owner")

    assert result["status"] == "provisioned"
    assert result["auth_scheme"] == _URL_SECRET_SCHEME
    # THE property: the vault holds the segment, not the link.
    records = _http_records(udir)
    assert len(records) == 1
    assert records[0]["token"] == HOOK_SECRET
    # The grant holds the PLACEHOLDER, and the response holds neither.
    assert result["allowed_endpoints"][0]["path_template"] == HOOK_TEMPLATE
    assert HOOK_SECRET not in json.dumps(result)


def test_deposit_refuses_a_hardcoded_secret_in_the_template(base: Path) -> None:
    """The exact live 2026-09-30 shape."""
    _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    result = _connect(
        "u-owner",
        secret=HOOK_SECRET,
        auth_scheme="bearer",
        endpoints=_endpoints(template=f"/mcp/hooks/{HOOK_SECRET}"),
    )

    assert result["error"] == "connection_setup_invalid"
    assert _URL_SECRET_SCHEME in result["detail"]
    assert not _http_records(base / "u-owner")  # nothing written


def test_deposit_refuses_a_link_for_the_wrong_host(base: Path) -> None:
    udir = _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    result = _connect(
        "u-owner", secret=f"https://evil.example.com/mcp/hooks/{HOOK_SECRET}"
    )

    assert result["error"] == "connection_setup_invalid"
    assert HOOK_SECRET not in json.dumps(result)
    assert not _http_records(udir)


def test_deposit_refuses_full_access_on_a_capability_url(base: Path) -> None:
    udir = _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    result = _connect("u-owner", access="full", endpoints=_endpoints())

    assert result["error"] == "connection_setup_invalid"
    assert not _http_records(udir)


def test_deposit_refuses_a_placeholder_under_a_header_scheme(base: Path) -> None:
    udir = _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    result = _connect("u-owner", secret=HOOK_SECRET, auth_scheme="bearer")

    assert result["error"] == "connection_setup_invalid"
    assert _URL_SECRET_SCHEME in result["detail"]
    assert not _http_records(udir)


def test_rotation_extracts_from_the_new_link(base: Path) -> None:
    """A regenerated webhook is a new LINK, not a new code — so the rotation
    parses it the same way, or the vault ends up holding a whole URL and every
    later call doubles the path."""
    from tinyassets.api.http_connection import rotate_http

    udir = _make_universe(base, "u-owner", admin="founder")
    _login("founder")
    assert _connect("u-owner")["status"] == "provisioned"

    replacement = "ZZZ9y8x7-W6v5U4t3S2r1Q0pO9nM8lK7jI6hG5fE4dC3b"
    rotated = rotate_http(
        universe_id="u-owner",
        payload=json.dumps(
            {
                "destination": "bug-reports",
                "secret": f"https://{HOOK_HOST}/mcp/hooks/{replacement}",
            }
        ),
    )

    assert rotated["status"] == "rotated"
    assert [r["token"] for r in _http_records(udir)] == [replacement]


# --------------------------------------------------------------------------- #
# 9. The ask, and the sentence the owner reads.
# --------------------------------------------------------------------------- #
_ASK = {
    "kind": "API",
    "title": "The webhook link for your friend's bug tracker",
    "body": "So I can post the bug reports you asked me to collect.",
    "action": {
        "type": "connect_http",
        "destination": "bug-reports",
        "auth_scheme": _URL_SECRET_SCHEME,
        "endpoints": [
            {"host": HOOK_HOST, "path_template": HOOK_TEMPLATE, "methods": ["POST"]}
        ],
    },
    "fields": [
        {
            "name": URL_SECRET_FIELD_NAME,
            "type": "secret",
            "label": "Webhook URL",
            "help": "the whole link they gave you, starting https://",
        }
    ],
}


def _ask_request(uid: str, **over: Any) -> dict[str, Any]:
    from tinyassets.api.pending_requests import request_from_user

    return request_from_user(universe_id=uid, payload=json.dumps({**_ASK, **over}))


def test_the_ask_validates(base: Path) -> None:
    _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    raised = _ask_request("u-owner")

    assert raised.get("status") == "pending", raised
    assert not raised.get("error")


def test_the_ask_refuses_a_hardcoded_secret_before_the_owner_sees_it(
    base: Path,
) -> None:
    _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    raised = _ask_request(
        "u-owner",
        action={
            **_ASK["action"],
            "auth_scheme": "bearer",
            "endpoints": [
                {
                    "host": HOOK_HOST,
                    "path_template": f"/mcp/hooks/{HOOK_SECRET}",
                    "methods": ["POST"],
                }
            ],
        },
    )

    assert raised.get("error")
    assert _URL_SECRET_SCHEME in json.dumps(raised)


def test_the_ask_requires_the_fixed_field_name(base: Path) -> None:
    """The deposit READS this name. A card that gets it wrong would be filled in
    by a person and then refused."""
    _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    raised = _ask_request(
        "u-owner",
        fields=[{"name": "token", "type": "secret", "label": "Webhook URL"}],
    )

    assert raised.get("error")
    assert URL_SECRET_FIELD_NAME in json.dumps(raised)


def test_the_ask_refuses_full_access(base: Path) -> None:
    _make_universe(base, "u-owner", admin="founder")
    _login("founder")

    raised = _ask_request(
        "u-owner",
        action={
            "type": "connect_http",
            "destination": "bug-reports",
            "auth_scheme": _URL_SECRET_SCHEME,
            "access": "full",
            "hosts": [HOOK_HOST],
        },
    )

    assert raised.get("error")


def test_answering_the_ask_stores_the_segment(base: Path) -> None:
    """End to end through the owner's own surface: the tab promised the template,
    the owner pasted the link, and only the code went to the vault."""
    from tinyassets.api.pending_requests import answer_request

    udir = _make_universe(base, "u-owner", admin="founder")
    _login("founder")
    raised = _ask_request("u-owner")
    assert raised.get("status") == "pending", raised

    answered = answer_request(
        universe_id="u-owner",
        payload=json.dumps(
            {
                "request_id": raised["request_id"],
                "values": {URL_SECRET_FIELD_NAME: HOOK_URL},
            }
        ),
    )

    assert answered.get("status") == "answered", answered
    assert [r["token"] for r in _http_records(udir)] == [HOOK_SECRET]
    # The receipt the owner reads back carries no part of the code.
    assert HOOK_SECRET not in json.dumps(answered)


def test_the_grant_sentence_explains_where_the_code_goes(base: Path) -> None:
    """The endpoint line shows `{secret}`, which without a word of explanation
    reads like a template the owner is meant to fill in."""
    from tinyassets.api.pending_requests import _grant_sentence

    sentence = _grant_sentence(
        {
            "kind": "API",
            "title": _ASK["title"],
            "body": _ASK["body"],
            "fields": _ASK["fields"],
            "action": {**_ASK["action"], "access": "exact", "scopes": []},
        }
    )

    assert "vault" in sentence
    assert HOOK_TEMPLATE in sentence


# --------------------------------------------------------------------------- #
# 10. The effector keeps a node-authored secret out of the run record.
# --------------------------------------------------------------------------- #
class _View:
    def __init__(self, scheme: str) -> None:
        self.auth_scheme = scheme


def test_the_effector_refuses_a_packet_that_hardcodes_the_code() -> None:
    """The allowlist in the child would refuse it anyway, but that refusal
    arrives AFTER this url is on the returned evidence and persisted with the
    run. Refusing here keeps it out of the record entirely."""
    from tinyassets.effectors.authenticated_external_call import (
        _capability_url_shape_error,
    )

    error = _capability_url_shape_error(
        f"https://{HOOK_HOST}/mcp/hooks/{HOOK_SECRET}", _View(_URL_SECRET_SCHEME)
    )
    assert error
    # The message must not echo the offending url -- that would put the code in
    # the very run record this exists to keep clean.
    assert HOOK_SECRET not in error


def test_the_effector_admits_the_placeholder_form() -> None:
    from tinyassets.effectors.authenticated_external_call import (
        _capability_url_shape_error,
    )

    for path in (HOOK_TEMPLATE, SLACK_TEMPLATE, f"{HOOK_TEMPLATE}?x=1"):
        assert (
            _capability_url_shape_error(
                f"https://{HOOK_HOST}{path}", _View(_URL_SECRET_SCHEME)
            )
            == ""
        )


def test_the_effector_guard_is_scoped_to_the_scheme() -> None:
    from tinyassets.effectors.authenticated_external_call import (
        _capability_url_shape_error,
    )

    assert (
        _capability_url_shape_error(
            f"https://{HOOK_HOST}/v1/messages", _View("bearer")
        )
        == ""
    )


# --------------------------------------------------------------------------- #
# 11. The served guidance teaches the shape (it is the only thing the agent
#     reads before composing a card).
# --------------------------------------------------------------------------- #
def test_the_connections_chapter_teaches_the_capability_url_shape() -> None:
    from tinyassets.engine_mcp_server import _WRITE_GRAPH_CONNECTIONS_CHAPTER as chapter

    assert _URL_SECRET_SCHEME in chapter
    assert "{secret}" in chapter
    assert "{secret+}" in chapter
    assert URL_SECRET_FIELD_NAME in chapter
    # The failure mode, named, so the agent recognises the link when it sees one.
    assert "webhook" in chapter.lower()
