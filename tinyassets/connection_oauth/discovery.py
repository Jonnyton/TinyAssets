"""Whether a provider offers OAuth for a connection, found from standards, not code.

Founder, 2026-09-24: "Our generic connector should prefer OAuth when the
provider allows for what the request is trying to accomplish, as that is less
actions for the user." There is no table of providers here. The answer comes
from, in order:

1. **Connection data** the user or their agent supplied (``oauth`` on the
   ``connect`` ask): authorize URL, token URL, scopes and a public client id or a
   registration URL. No network is needed.
2. **Standard discovery** against the connection's own host(s):

   * RFC 9728 protected-resource metadata (``/.well-known/oauth-protected-resource``)
     names the authorization server(s) for the API;
   * RFC 8414 authorization-server metadata
     (``/.well-known/oauth-authorization-server``), then OpenID Connect discovery
     (``/.well-known/openid-configuration``), describe that server.

An offer exists only when the server covers the request: the authorization-code
grant with PKCE S256 for a public client, every requested scope (when the server
lists its scopes), and a client (the supplied id, or RFC 7591 dynamic
registration). Anything short of that is a reason, and the ask falls back to
key paste.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from tinyassets.connection_oauth.transport import OAuthError, request_json, validate_https_url

#: Network discovery on or off. On in production. The test suite injects False
#: (``tests/conftest.py``) so no test reaches a real host, and a test that
#: exercises discovery turns it back on against its own local fake server.
DISCOVERY_ENABLED = True

_SCOPE_RE = re.compile(r"[\x21\x23-\x5B\x5D-\x7E]{1,128}\Z")
_CLIENT_ID_RE = re.compile(r"[\x21-\x7E]{1,256}\Z")
_MAX_SCOPES = 32
_MAX_ISSUERS = 2
_REQUEST_KEYS = frozenset({
    "issuer", "authorize_url", "token_url", "client_id", "registration_url", "scopes",
})


@dataclass(frozen=True)
class ServerMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    scopes_supported: tuple[str, ...] | None
    code_challenge_methods: tuple[str, ...]
    grant_types: tuple[str, ...]
    response_types: tuple[str, ...]


def _strings(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise OAuthError("invalid_authorization_server_metadata")
    return tuple(value)


def validate_scopes(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split()
    if not isinstance(value, list) or len(value) > _MAX_SCOPES:
        raise ValueError(f"oauth.scopes must be a list of at most {_MAX_SCOPES} scope names")
    out: list[str] = []
    for scope in value:
        if not isinstance(scope, str) or not _SCOPE_RE.match(scope):
            raise ValueError("each oauth scope must be 1-128 printable characters, no spaces")
        if scope not in out:
            out.append(scope)
    return out


def validate_request(raw: Any) -> dict[str, Any]:
    """The ``oauth`` object a ``connect`` ask may carry: data, never code.

    Absent means "discover it". Present, it may name an ``issuer`` to discover
    from, or the endpoints themselves (both URLs, plus a public ``client_id`` or
    a ``registration_url``), and the ``scopes`` the requested use needs.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("oauth must be an object")
    unknown = set(raw) - _REQUEST_KEYS
    if unknown:
        raise ValueError("oauth has unknown fields: " + ", ".join(sorted(unknown))
                         + " (a client secret never goes through an ask)")
    out: dict[str, Any] = {}
    for key in ("issuer", "authorize_url", "token_url", "registration_url"):
        if raw.get(key) in (None, ""):
            continue
        try:
            out[key] = validate_https_url(raw[key])
        except OAuthError:
            raise ValueError(f"oauth.{key} must be a plain https:// URL with no query") from None
    client_id = raw.get("client_id")
    if client_id not in (None, ""):
        if not isinstance(client_id, str) or not _CLIENT_ID_RE.match(client_id):
            raise ValueError("oauth.client_id must be 1-256 printable characters")
        out["client_id"] = client_id
    out["scopes"] = validate_scopes(raw.get("scopes"))
    endpoints = [k for k in ("authorize_url", "token_url") if k in out]
    if len(endpoints) == 1:
        raise ValueError("oauth needs both authorize_url and token_url, or neither")
    if endpoints and not (out.get("client_id") or out.get("registration_url")):
        raise ValueError("oauth endpoints need a public client_id or a registration_url")
    return out


def _metadata_urls(issuer: str) -> list[str]:
    """RFC 8414 §3.1 inserts the well-known segment; OpenID appends it."""
    parts = urlsplit(issuer)
    path = parts.path.rstrip("/")
    origin = (parts.scheme, parts.netloc)
    return [
        urlunsplit((*origin, "/.well-known/oauth-authorization-server" + path, "", "")),
        urlunsplit((*origin, path + "/.well-known/openid-configuration", "", "")),
    ]


def fetch_server_metadata(issuer: str) -> ServerMetadata:
    issuer = validate_https_url(issuer)
    for url in _metadata_urls(issuer):
        status, doc = request_json("GET", url)
        if status != 200 or not isinstance(doc, dict):
            continue
        # RFC 8414 §3.3 / OIDC Discovery §4.3: the document must name the very
        # issuer it was fetched for, or it is someone else's metadata.
        if doc.get("issuer") != issuer and doc.get("issuer") != issuer.rstrip("/"):
            raise OAuthError("authorization_server_issuer_mismatch")
        try:
            authorize = validate_https_url(doc.get("authorization_endpoint"))
            token = validate_https_url(doc.get("token_endpoint"))
        except OAuthError:
            raise OAuthError("invalid_authorization_server_metadata") from None
        registration = doc.get("registration_endpoint") or ""
        if registration:
            try:
                registration = validate_https_url(registration)
            except OAuthError:
                registration = ""
        return ServerMetadata(
            issuer=issuer, authorization_endpoint=authorize, token_endpoint=token,
            registration_endpoint=registration,
            scopes_supported=_strings(doc.get("scopes_supported")),
            code_challenge_methods=_strings(doc.get("code_challenge_methods_supported")) or (),
            # RFC 8414 §2 defaults when omitted.
            grant_types=_strings(doc.get("grant_types_supported"))
            or ("authorization_code", "implicit"),
            response_types=_strings(doc.get("response_types_supported")) or (),
        )
    raise OAuthError("no_authorization_server_metadata")


def protected_resource_issuers(host: str) -> list[str]:
    """RFC 9728: the authorization servers an API names for itself."""
    resource = f"https://{host}"
    status, doc = request_json("GET", resource + "/.well-known/oauth-protected-resource")
    if status != 200 or not isinstance(doc, dict):
        return []
    # §3.3: the metadata must be about the resource it was fetched from.
    named = doc.get("resource")
    if not isinstance(named, str) or urlsplit(named).netloc.lower() != host.lower():
        return []
    servers = doc.get("authorization_servers")
    if not isinstance(servers, list):
        return []
    out = []
    for server in servers[:_MAX_ISSUERS]:
        try:
            out.append(validate_https_url(server))
        except OAuthError:
            continue
    return out


def _metadata_for(hosts: list[str], issuer: str) -> ServerMetadata:
    if issuer:
        return fetch_server_metadata(issuer)
    last: OAuthError = OAuthError("no_authorization_server_metadata")
    for host in hosts[:_MAX_ISSUERS]:
        candidates = protected_resource_issuers(host) or [f"https://{host}"]
        for candidate in candidates:
            try:
                return fetch_server_metadata(candidate)
            except OAuthError as exc:
                last = exc
    raise last


def _covers(metadata: ServerMetadata, scopes: list[str]) -> str:
    """Empty when the server covers the requested use, else the reason."""
    if "S256" not in metadata.code_challenge_methods:
        return "pkce_not_offered"
    if "code" not in metadata.response_types:
        return "authorization_code_not_offered"
    if "authorization_code" not in metadata.grant_types:
        return "authorization_code_not_offered"
    if metadata.scopes_supported is not None and not set(scopes) <= set(metadata.scopes_supported):
        return "scopes_not_offered"
    return ""


def resolve_offer(requested: dict[str, Any], hosts: list[str]) -> tuple[dict[str, Any] | None, str]:
    """``(offer, "")`` when OAuth covers this connection, else ``(None, reason)``.

    The offer is recorded on the ask, so what the owner is shown is exactly what
    the sign-in uses.
    """
    scopes = list(requested.get("scopes") or [])
    if requested.get("authorize_url"):
        return {
            "issuer": requested.get("issuer", ""),
            "authorize_url": requested["authorize_url"],
            "token_url": requested["token_url"],
            "client_id": requested.get("client_id", ""),
            "registration_url": requested.get("registration_url", ""),
            "scopes": scopes,
            "source": "supplied",
        }, ""
    if not DISCOVERY_ENABLED:
        return None, "discovery_unavailable"
    try:
        metadata = _metadata_for(hosts, requested.get("issuer", ""))
    except OAuthError as exc:
        return None, exc.code
    reason = _covers(metadata, scopes)
    if reason:
        return None, reason
    client_id = requested.get("client_id", "")
    registration = requested.get("registration_url") or metadata.registration_endpoint
    if not client_id and not registration:
        return None, "no_public_client"
    return {
        "issuer": metadata.issuer,
        "authorize_url": metadata.authorization_endpoint,
        "token_url": metadata.token_endpoint,
        "client_id": client_id,
        "registration_url": "" if client_id else registration,
        "scopes": scopes,
        "source": "discovered",
    }, ""


def register_public_client(registration_url: str, *, redirect_uri: str,
                           scopes: list[str]) -> str:
    """RFC 7591 dynamic registration of a PUBLIC client; returns its id.

    A server that insists on a confidential client (issues a secret) is
    refused: a client secret would have nowhere safe to live in a browser flow.
    """
    body: dict[str, Any] = {
        "redirect_uris": [redirect_uri],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "client_name": "TinyAssets",
    }
    if scopes:
        body["scope"] = " ".join(scopes)
    status, doc = request_json("POST", registration_url, json_body=body)
    if status not in (200, 201) or not isinstance(doc, dict):
        from tinyassets.connection_oauth.transport import server_error_detail

        raise OAuthError("client_registration_failed", server_error_detail(status, doc),
                         status=status)
    client_id = doc.get("client_id")
    if not isinstance(client_id, str) or not _CLIENT_ID_RE.match(client_id):
        raise OAuthError("client_registration_failed", "no client_id in the response")
    method = doc.get("token_endpoint_auth_method", "none")
    if doc.get("client_secret") or method != "none":
        raise OAuthError("confidential_client_refused",
                         "the server registered a confidential client")
    return client_id
