"""Outbound connection resources, per-universe grants, and scoped proxies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import io
import ipaddress
import json
import math
import multiprocessing
import os
import re
import secrets
import socket
import sqlite3
import ssl
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from tinyassets.storage.workspace_authority import is_git_scope, validate_git_scopes

AuthenticatedPrincipalVerifier = Callable[[], str]


@dataclass(frozen=True)
class OutboundEndpoint:
    """One allowlisted egress target for an ``http`` connection (design.md D2/D3).

    ``host`` is an exact hostname (lower-cased), ``path_template`` a ``/``-rooted
    template, ``methods`` the HTTP verbs permitted. The allowlist is the REAL
    confidentiality/egress boundary — a caller-supplied URL that does not match
    one of these is refused before any socket is opened.

    A ``{param}`` segment does NOT match "any non-empty segment": every
    placeholder MUST carry a declared value pattern in ``param_patterns`` (name →
    anchored regex the whole segment must full-match), so a tenant/target/id in a
    path segment cannot silently address a different account (Codex FIX 3).
    ``allowed_query`` names the ONLY query parameters permitted — an undeclared
    query parameter is REFUSED, never dropped — and ``query_patterns`` optionally
    constrains a declared query value. ``required_query`` names query parameters
    that MUST be present EXACTLY ONCE (a subset of ``allowed_query``), so an
    endpoint whose semantics depend on a validated parameter (github's contents
    ``?ref=`` — Codex FIX: "require exactly one validated ref query") cannot be
    called without it or with a duplicate. ``param_patterns``/``query_patterns``
    are stored as sorted ``(name, regex)`` pairs so the dataclass stays hashable.
    """

    host: str
    path_template: str
    methods: tuple[str, ...]
    param_patterns: tuple[tuple[str, str], ...] = ()
    allowed_query: tuple[str, ...] = ()
    query_patterns: tuple[tuple[str, str], ...] = ()
    required_query: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "path_template": self.path_template,
            "methods": list(self.methods),
            "param_patterns": {name: pat for name, pat in self.param_patterns},
            "allowed_query": list(self.allowed_query),
            "query_patterns": {name: pat for name, pat in self.query_patterns},
            "required_query": list(self.required_query),
        }


@dataclass(frozen=True, repr=False)
class ConnectionResource:
    """Credential-BEARING connection record — for trusted server-internal use.

    Carries ``credential_ref`` (the vault reference) and MUST NOT be returned to
    an adapter/graph/CRUD/list/evidence surface — those use :class:`ConnectionView`
    (no ``credential_ref``). Redaction is made STRUCTURAL, not conventional
    (Codex): ``__repr__`` masks ``credential_ref`` so stringifying/logging a
    resource (into an exception, evidence dict, or log line) never reveals it,
    while the attribute stays reachable for the broker child and the internal
    ownership/conflict checks that must compare it explicitly.
    """

    connection_id: str
    owner_user_id: str
    connection_class: str
    scopes: tuple[str, ...]
    provider: str
    destination: str
    credential_ref: str
    revoked_at: float | None
    #: The channel-type registry key (design.md D2). Empty for legacy
    #: github/slack connections that predate the descriptor; "http" selects the
    #: general SSRF-hardened driver.
    connection_type: str = ""
    #: How the child applies the credential (design.md D5): "bearer" | "basic" |
    #: "header" | "none". Empty for legacy connections.
    auth_scheme: str = ""
    #: The per-connection egress allowlist (design.md D3). Empty ⇒ no call.
    allowed_endpoints: tuple[OutboundEndpoint, ...] = ()

    def __repr__(self) -> str:
        return (
            "ConnectionResource("
            f"connection_id={self.connection_id!r}, "
            f"owner_user_id={self.owner_user_id!r}, "
            f"connection_class={self.connection_class!r}, "
            f"scopes={self.scopes!r}, "
            f"provider={self.provider!r}, "
            f"destination={self.destination!r}, "
            "credential_ref='***redacted***', "
            f"revoked_at={self.revoked_at!r}, "
            f"connection_type={self.connection_type!r}, "
            f"auth_scheme={self.auth_scheme!r}, "
            f"allowed_endpoints={self.allowed_endpoints!r})"
        )

    def to_view(self) -> ConnectionView:
        """The ONLY shape any caller/CRUD/list/evidence path may see (design.md D2).

        ``credential_ref`` — the vault reference — is deliberately dropped so no
        projection can leak it.
        """
        return ConnectionView(
            connection_id=self.connection_id,
            owner_user_id=self.owner_user_id,
            connection_class=self.connection_class,
            scopes=self.scopes,
            provider=self.provider,
            connection_type=self.connection_type,
            auth_scheme=self.auth_scheme,
            allowed_endpoints=self.allowed_endpoints,
            destination=self.destination,
            revoked_at=self.revoked_at,
        )


@dataclass(frozen=True)
class ConnectionView:
    """Redacted connection projection — carries NO ``credential_ref``/secret.

    Everything a caller/CRUD/list/evidence path may see EXCEPT the vault
    ``credential_ref``: there is no such field, so ``vars()``/``asdict()``/repr
    cannot expose it (Codex FIX 3, structural redaction). ``provider`` is not a
    secret and is included so existing owner projections keep working.
    """

    connection_id: str
    owner_user_id: str
    connection_class: str
    scopes: tuple[str, ...]
    provider: str
    connection_type: str
    auth_scheme: str
    allowed_endpoints: tuple[OutboundEndpoint, ...]
    destination: str
    revoked_at: float | None

    def as_dict(self) -> dict[str, object]:
        return {
            "connection_id": self.connection_id,
            "owner_user_id": self.owner_user_id,
            "connection_class": self.connection_class,
            "scopes": list(self.scopes),
            "provider": self.provider,
            "connection_type": self.connection_type,
            "auth_scheme": self.auth_scheme,
            "allowed_endpoints": [ep.as_dict() for ep in self.allowed_endpoints],
            "destination": self.destination,
            "revoked_at": self.revoked_at,
        }


@dataclass(frozen=True)
class ConnectionGrant:
    grant_id: str
    connection_id: str
    owner_user_id: str
    universe_id: str
    granted_at: float
    revoked_at: float | None
    unprompted_action_cap: ActionCap | None


@dataclass(frozen=True)
class ActionCap:
    name: str
    maximum: float
    unit: str

    def __post_init__(self) -> None:
        _required("cap name", self.name)
        _required("cap unit", self.unit)
        if not math.isfinite(self.maximum):
            raise ValueError("cap maximum must be finite")
        if self.maximum < 0:
            raise ValueError("cap maximum must be non-negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "maximum": self.maximum,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class CapDecision:
    status: str
    cap: ActionCap | None
    action_value: float
    action_unit: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "cap": self.cap.as_dict() if self.cap is not None else None,
            "action_value": self.action_value,
            "action_unit": self.action_unit,
            "authorization_axis": "unprompted_action",
        }


@dataclass(frozen=True)
class ConnectorArtifact:
    artifact_id: str
    owner_user_id: str
    connector_definition: dict[str, Any]
    mcp_client_config: dict[str, Any]
    parent_artifact_id: str | None
    attribution: tuple[str, ...]
    created_at: float


class GrantResolutionError(RuntimeError):
    """No single current grant can authorize the requested connection."""


class ProxyRequestError(RuntimeError):
    """A scoped proxy request failed without exposing destination internals."""


class AmbiguousProxyOutcome(RuntimeError):
    """The destination may have applied the request before transport failed."""


class SsrfValidationError(ProxyRequestError):
    """A general outbound HTTP request was refused by the strict egress guard.

    Subclasses ``ProxyRequestError`` so it flows through the broker's existing
    secret-free error hygiene (``_adapter_safe_proxy_error`` reduces it to a
    fixed string across the process boundary). Its own messages are FIXED —
    they never echo the offending URL, header, or address, because those can
    themselves carry credential material (e.g. ``https://user:pass@host``).
    """


_MAX_PROXY_FRAME_BYTES = 16 * 1024 * 1024


def _adapter_safe_proxy_error(exc: BaseException) -> str:
    """Return the only error text allowed across the adapter process boundary."""
    if isinstance(exc, AmbiguousProxyOutcome):
        return "destination outcome ambiguous"
    if isinstance(exc, GrantResolutionError):
        return "outbound connection grant unavailable"
    if isinstance(exc, PermissionError):
        return "outbound request not permitted"
    return "outbound request failed"


def _send_message(channel: Any, value: object) -> None:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProxyRequestError(
            "outbound proxy messages must use the redacted JSON contract"
        ) from exc
    if len(payload) > _MAX_PROXY_FRAME_BYTES:
        raise ProxyRequestError("outbound proxy message exceeds the size limit")
    channel.send_bytes(payload)


def _receive_message(channel: Any) -> object:
    try:
        payload = channel.recv_bytes(_MAX_PROXY_FRAME_BYTES)
        return json.loads(payload.decode("utf-8"))
    except (EOFError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProxyRequestError("outbound proxy received an invalid message") from exc


def _load_dispatch_factory(
    factory_reference: str,
    config: dict[str, Any],
) -> Callable[[str, str, object], Any]:
    factory = _TRUSTED_DISPATCH_FACTORIES.get(factory_reference)
    if factory is None:
        raise ValueError("dispatch factory is not in the trusted registry")
    dispatch = factory(config)
    if not callable(dispatch):
        raise TypeError("dispatch factory must return a callable")
    return dispatch


#: Environment variables the spawned broker child must never carry: TLS
#: key-logging (would leak the outbound TLS session key, defeating
#: credential-blindness) and ambient proxy routing (an SSRF/exfil vector the
#: transport disables structurally; dropping it here also keeps any other TLS
#: context created in the child — e.g. the GitHub read driver's plain urlopen —
#: from honoring an ambient proxy or logging keys). The child is a spawned
#: process, so this pop never touches the parent's environment.
_SSRF_CHILD_ENV_DENYLIST = (
    "SSLKEYLOGFILE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "FTP_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "ftp_proxy",
    "no_proxy",
)


def _sanitize_child_environment() -> None:
    for name in _SSRF_CHILD_ENV_DENYLIST:
        os.environ.pop(name, None)


#: Default-OFF flag gating the general ``http`` connection path. Until a
#: deployment sets this truthy, an ``http`` connection fails closed even if one
#: is created — nothing routes through the general driver by default.
_OUTBOUND_HTTP_FLAG = "TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED"

#: Handshake budget for the spawned broker child, and the var that overrides it.
_PROXY_STARTUP_TIMEOUT_VAR = "TINYASSETS_OUTBOUND_PROXY_STARTUP_TIMEOUT_S"
#: Measured: the broker module is pure-stdlib and a fresh interpreter imports it
#: in ~0.13s, so this is ~100x headroom, not a guess. Kept well under the cap
#: because the wait occupies a run-executor thread.
_DEFAULT_PROXY_STARTUP_TIMEOUT_S = 15.0
_MAX_PROXY_STARTUP_TIMEOUT_S = 120.0

#: The only connection_type values a connection may be created with. Empty is the
#: legacy/untyped github/slack shape; "http" is the general typed connection. Any
#: other value is refused at creation AND fails closed at dispatch (FIX 1).
_KNOWN_CONNECTION_TYPES = frozenset({"", "http"})

#: Auth schemes an ``http`` connection may declare. ``oauth1a`` (Twitter) signs
#: with the four OAuth secrets carried in the bundle; the rest use one token.
_SUPPORTED_HTTP_AUTH_SCHEMES = frozenset(
    {"none", "bearer", "basic", "header", "oauth1a"}
)

#: The ONLY credential_ref scheme an ``http`` connection may reference. Binding
#: the credential's scheme to the connection type is what stops a confused-deputy
#: exfil (an http connection referencing a `workos-pipes://github/...` token and
#: POSTing it to an attacker's endpoint) — Codex FIX 1.
_HTTP_CREDENTIAL_REF_PREFIX = "vault://http/"


def _validate_connection_credential_scheme(
    connection_type: str, credential_ref: str
) -> None:
    """Enforce the type<->credential-scheme biconditional (creation AND dispatch).

    An ``http`` connection may reference ONLY a ``vault://http/`` credential, and
    a non-http (legacy) connection may NEVER reference one. Applying the SAME rule
    at DISPATCH to the freshly re-read row — not only at creation — closes the
    connection-row mutation TOCTOU: a proxy started for one type whose row is
    later mutated to a different type/scheme (e.g. legacy-github -> http with an
    attacker allowlist) is refused before any credential is resolved, so no
    foreign-scheme token can be vended to the current-type driver (Codex FIX 1,
    TOCTOU).
    """
    ctype = (connection_type or "").strip().lower()
    is_http_ref = (credential_ref or "").strip().startswith(_HTTP_CREDENTIAL_REF_PREFIX)
    if ctype == "http" and not is_http_ref:
        raise SsrfValidationError(
            "an http connection credential_ref must be a vault://http/ reference"
        )
    if ctype != "http" and is_http_ref:
        raise SsrfValidationError(
            "a non-http connection must not use a vault://http/ credential_ref"
        )


def _outbound_http_enabled() -> bool:
    return os.environ.get(_OUTBOUND_HTTP_FLAG, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _proxy_startup_timeout_seconds() -> float:
    """Seconds to wait for the spawned broker child's ready handshake.

    The child is a ``spawn`` process, so it pays a FULL cold re-import of the
    package chain before it can answer. The original 5s budget was measured
    against nothing, and a cold container under load can exceed it — which
    surfaced as a proxy that "failed to start" with no further detail. Tunable
    so a slow host can be corrected without a redeploy.
    """
    raw = os.environ.get(_PROXY_STARTUP_TIMEOUT_VAR, "").strip()
    if not raw:
        return _DEFAULT_PROXY_STARTUP_TIMEOUT_S
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        # An explicitly-set unusable value is a misconfiguration, and silently
        # swallowing it is what Hard Rule 8 forbids. It still must not take
        # egress down, so: say so loudly, then use the default (Codex FIX C).
        print(
            f"{_PROXY_STARTUP_TIMEOUT_VAR}={raw!r} is not a positive number; "
            f"using the {_DEFAULT_PROXY_STARTUP_TIMEOUT_S:g}s default",
            file=sys.stderr,
        )
        return _DEFAULT_PROXY_STARTUP_TIMEOUT_S
    # Cap the range. The startup blocks a run-executor thread, and the top-level
    # pool is small (4 workers), so an unbounded budget lets a handful of hung
    # startups stall all top-level graph progress for that long (Codex FIX C).
    if value > _MAX_PROXY_STARTUP_TIMEOUT_S:
        print(
            f"{_PROXY_STARTUP_TIMEOUT_VAR}={raw!r} exceeds the "
            f"{_MAX_PROXY_STARTUP_TIMEOUT_S:g}s cap; clamping",
            file=sys.stderr,
        )
        return _MAX_PROXY_STARTUP_TIMEOUT_S
    return value


def _describe_child_exit(exitcode: int | None) -> str:
    """Render a broker child's exit status for an operator-facing error."""
    if exitcode is None:
        return ""
    # A negative code is the signal that killed it — -9 is the OOM killer, which
    # is the difference between "misconfigured" and "the box is out of memory".
    if exitcode < 0:
        return f" (killed by signal {-exitcode})"
    return f" (exitcode {exitcode})"


def _verb_within_scopes(verb: object, scopes: Iterable[str]) -> bool:
    """Whether an HTTP verb is one this connection's scopes carry.

    Authorization here is a membership test against the ``scopes`` tuple, and
    that tuple now also holds git scopes (``git_read:owner/name``), which are a
    DIFFERENT KIND of authority: they say a credentialed git operation may run
    against one repository, not that an arbitrary HTTP request may be dispatched.
    Without this check a caller could pass ``verb="git_read:owner/name"``, match
    by membership, and reach the credentialed dispatcher through the HTTP path.
    """
    if not isinstance(verb, str) or not verb:
        return False
    if is_git_scope(verb):
        return False
    return verb in scopes


def _run_proxy_worker(
    channel: Any,
    dispatch_factory: str,
    dispatch_config: dict[str, Any],
    grant_id: str,
    scopes: tuple[str, ...],
) -> None:
    """Run the trusted dispatcher in a separate spawned process."""
    _sanitize_child_environment()
    try:
        dispatch = _load_dispatch_factory(dispatch_factory, dispatch_config)
    except Exception as exc:
        # Hard Rule 8. The startup path runs BEFORE any credential is resolved
        # (`_load_dispatch_factory` only builds the ledger/driver/audit objects),
        # so the failure carries no credential material. Only the exception CLASS
        # crosses the wire, which is enough to discriminate the real causes —
        # PermissionError (runtime_root mkdir), OperationalError (ledger open),
        # ImportError — which a fixed string never was.
        #
        # The traceback is OPERATOR-VISIBLE, NOT host-only: daemon stderr goes to
        # Docker's fluentd driver (deploy/compose.yml:24,:46) into Vector, which
        # forwards unredacted to Better Stack (deploy/vector-betterstack.yaml:10).
        # It reaches no MCP user, but it does reach a third-party log sink, and
        # exception messages here can carry absolute host paths. Do not widen this
        # to dump locals or the config dict (Codex FIX B).
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        _send_message(
            channel,
            {
                "op": "startup_failed",
                "message": "trusted proxy failed to start",
                "cause": type(exc).__name__,
            },
        )
        channel.close()
        return
    _send_message(channel, {"op": "ready"})
    try:
        while True:
            message = _receive_message(channel)
            if message == {"op": "close"}:
                return
            if not isinstance(message, dict) or message.get("op") != "request":
                _send_message(
                    channel,
                    {
                        "ok": False,
                        "error_type": "ProxyRequestError",
                        "message": "outbound proxy rejected an invalid request",
                    },
                )
                continue
            verb = message.get("verb")
            if not _verb_within_scopes(verb, scopes):
                _send_message(
                    channel,
                    {
                        "ok": False,
                        "error_type": "PermissionError",
                        "message": "verb is outside the granted connection scope",
                    },
                )
                continue
            try:
                result = dispatch(grant_id, verb, message.get("request"))
            except (
                AmbiguousProxyOutcome,
                GrantResolutionError,
                PermissionError,
                ProxyRequestError,
            ) as exc:
                _send_message(
                    channel,
                    {
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "message": _adapter_safe_proxy_error(exc),
                    },
                )
            except Exception:
                _send_message(
                    channel,
                    {
                        "ok": False,
                        "error_type": "ProxyRequestError",
                        "message": "outbound request failed",
                    },
                )
            else:
                _send_message(channel, {"ok": True, "result": result})
    except (OSError, ProxyRequestError):
        return
    finally:
        channel.close()


class _ProxyChannel:
    """Adapter-side transport; contains no dispatcher or credential material."""

    __slots__ = ("_channel", "_closed", "_lock", "_process")

    def __init__(self, channel: Any, process: Any) -> None:
        self._channel = channel
        self._closed = False
        self._lock = threading.Lock()
        self._process = process

    def request(self, verb: str, request: object) -> Any:
        with self._lock:
            if self._closed:
                raise ProxyRequestError("outbound proxy is closed")
            _send_message(
                self._channel,
                {"op": "request", "verb": verb, "request": request},
            )
            response = _receive_message(self._channel)
        if not isinstance(response, dict):
            raise ProxyRequestError("outbound proxy returned an invalid response")
        if response.get("ok") is True:
            return response.get("result")
        message = str(response.get("message") or "outbound request failed")
        error_type = response.get("error_type")
        if error_type == "PermissionError":
            raise PermissionError(message)
        if error_type == "GrantResolutionError":
            raise GrantResolutionError(message)
        if error_type == "AmbiguousProxyOutcome":
            raise AmbiguousProxyOutcome(message)
        raise ProxyRequestError(message)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            try:
                _send_message(self._channel, {"op": "close"})
            except (OSError, ProxyRequestError):
                pass
            self._channel.close()
        self._process.join(timeout=1.0)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)


@dataclass(frozen=True, slots=True)
class ScopedConnectionProxy:
    """Credential-blind adapter surface bound to one exact grant."""

    grant_id: str
    provider: str
    destination: str
    scopes: tuple[str, ...]
    _channel: _ProxyChannel = field(repr=False, compare=False)

    def request(self, verb: str, request: object) -> Any:
        if not _verb_within_scopes(verb, self.scopes):
            raise PermissionError(
                f"verb {verb!r} is outside the granted connection scope"
            )
        return self._channel.request(verb, request)

    def close(self) -> None:
        self._channel.close()


class CredentialBlindBroker:
    """Trusted daemon-side dispatcher; adapter-facing errors are secret-free."""

    __slots__ = ("_audit", "_ledger", "_network_request", "_resolve_credential")

    def __init__(
        self,
        ledger: ConnectionLedger,
        *,
        resolve_credential: Callable[[str], str],
        network_request: Callable[..., Any],
        audit: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._ledger = ledger
        self._resolve_credential = resolve_credential
        self._network_request = network_request
        self._audit = audit or (lambda _record: None)

    def dispatch(self, grant_id: str, verb: str, request: object) -> Any:
        resource = self._ledger._active_resource_for_grant(grant_id)
        if resource is None:
            raise GrantResolutionError("absent or revoked outbound connection grant")
        if not _verb_within_scopes(verb, resource.scopes):
            raise PermissionError(
                f"verb {verb!r} is outside the granted connection scope"
            )
        try:
            # Re-validate the CURRENT row's type<->credential-scheme match (the row
            # was just re-read and may have been mutated after proxy start), then
            # resolve the credential selecting the resolver by the CURRENT type —
            # not the type frozen at proxy start. Together these refuse a mutated
            # row before any foreign-scheme token can be vended (Codex FIX 1 TOCTOU).
            _validate_connection_credential_scheme(
                resource.connection_type, resource.credential_ref
            )
            credential = self._resolve_credential(
                resource.credential_ref, resource.connection_type
            )
        except Exception:
            self._record_error(resource, grant_id, verb, "credential unavailable")
            raise ProxyRequestError(
                "outbound request failed: credential unavailable"
            ) from None
        if not credential:
            self._record_error(resource, grant_id, verb, "credential unavailable")
            raise ProxyRequestError("outbound request failed: credential unavailable")
        try:
            response = self._network_request(
                credential=credential,
                provider=resource.provider,
                destination=resource.destination,
                connection_type=resource.connection_type,
                auth_scheme=resource.auth_scheme,
                allowed_endpoints=resource.allowed_endpoints,
                verb=verb,
                request=request,
            )
        except AmbiguousProxyOutcome:
            self._record_error(
                resource,
                grant_id,
                verb,
                "destination outcome ambiguous",
            )
            raise AmbiguousProxyOutcome("destination outcome ambiguous") from None
        except Exception:
            self._record_error(
                resource,
                grant_id,
                verb,
                "destination request failed",
            )
            raise ProxyRequestError(
                "outbound request failed at destination"
            ) from None
        if _contains_secret(response, credential):
            self._record_error(
                resource,
                grant_id,
                verb,
                "destination response contained credential material",
            )
            raise ProxyRequestError(
                "outbound request failed: unsafe destination response"
            )
        return response

    def _record_error(
        self,
        resource: ConnectionResource,
        grant_id: str,
        verb: str,
        reason: str,
    ) -> None:
        self._audit(
            {
                "event": "outbound_proxy_error",
                "grant_id": grant_id,
                "provider": resource.provider,
                "destination": resource.destination,
                "verb": verb,
                "reason": reason,
            }
        )


class _TestFixtureCredentialResolver:
    __slots__ = ("_allow_test_fixtures",)

    def __init__(self, *, allow_test_fixtures: bool) -> None:
        self._allow_test_fixtures = allow_test_fixtures

    def __call__(self, credential_ref: str) -> str:
        if not self._allow_test_fixtures:
            raise RuntimeError("credential reference has no trusted resolver")
        if credential_ref == "test-fixture://nonsecret":
            return "trusted-child-fixture"
        for prefix, fail in (
            ("test-vault-file:", False),
            ("test-vault-error:", True),
        ):
            if not credential_ref.startswith(prefix):
                continue
            path = Path(credential_ref.removeprefix(prefix))
            if not path.is_absolute() or not path.is_file():
                raise RuntimeError("trusted credential reference is unavailable")
            credential = path.read_text(encoding="utf-8")
            if fail:
                raise RuntimeError(
                    f"vault failed while loading {credential}"
                )
            return credential
        raise RuntimeError("credential reference has no trusted resolver")


class _GeneralVaultCredentialResolver:
    """Resolve a general (non-github) connection credential from the vault.

    NEVER parses the destination as a github repo (Codex FIX 4): the github
    resolver's ``__init__`` runs ``_github_repository_from_destination`` on the
    destination, which raises for a normal http host like ``api.example.com`` and
    crashed the broker at startup. An ``http`` connection's ``credential_ref``
    (``vault://http/<key>``) names a per-universe vault record; its secret is
    returned, or fail closed. A general typed-bundle resolver in
    ``credential_vault.py`` is task 1.8 (deferred); this reads the single value.
    """

    __slots__ = ("_universe_dir",)

    def __init__(self, *, universe_dir: str | Path) -> None:
        self._universe_dir = Path(universe_dir)

    def __call__(self, credential_ref: str) -> str:
        ref = (credential_ref or "").strip()
        prefix = "vault://http/"
        if not ref.startswith(prefix):
            raise RuntimeError("credential reference has no trusted resolver")
        record_key = ref[len(prefix):].strip()
        if not record_key:
            raise RuntimeError("credential reference is unavailable")
        from tinyassets.credential_vault import load_credential_vault

        for record in load_credential_vault(self._universe_dir):
            if str(record.get("credential_type") or "").strip().lower() != "http":
                continue
            if str(record.get("destination") or "").strip() != record_key:
                continue
            for key in ("token", "access_token", "secret", "api_key"):
                value = record.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            raise RuntimeError("credential reference is unavailable")
        raise RuntimeError("credential reference is unavailable")


class _TrustedCredentialResolver:
    """Select the correct credential resolver INSIDE the broker child.

    Constructing this must never crash (Codex FIX 4): the github resolver — whose
    ``__init__`` parses the destination as a repo — is built LAZILY, only on the
    explicit github path, so an ``http`` connection never touches it. An http
    connection resolves through the GENERAL vault path, never the repo parser.
    """

    __slots__ = (
        "_allow_test_fixtures",
        "_connection_type",
        "_destination",
        "_owner_user_id",
        "_provider",
        "_universe_dir",
    )

    def __init__(self, config: dict[str, Any]) -> None:
        self._provider = str(config["provider"])
        self._connection_type = str(config.get("connection_type", "") or "").strip().lower()
        self._allow_test_fixtures = bool(config["allow_test_fixtures"])
        self._universe_dir = config["universe_dir"]
        self._destination = str(config["destination"])
        self._owner_user_id = str(config["owner_user_id"])

    def __call__(self, credential_ref: str, connection_type: str | None = None) -> str:
        ref = credential_ref or ""
        # Select by the CURRENT connection_type the caller supplies (the broker
        # passes the freshly re-read row's type), falling back to the type frozen
        # at proxy start only when none is given — so a post-start row mutation
        # cannot force resolution through the wrong (stale) resolver (Codex FIX 1
        # TOCTOU).
        effective_type = (
            connection_type if connection_type is not None else self._connection_type
        )
        effective_type = (effective_type or "").strip().lower()
        # CONNECTION-TYPE-FIRST (Codex FIX 1 — confused-deputy exfiltration). An
        # http connection resolves its credential ONLY through the general vault
        # resolver — NEVER a scheme-specific (github/workos/slack) or fixture
        # resolver. This is what stops a forged/mismatched credential_ref (e.g.
        # `workos-pipes://github/victim` on an http connection) from vending a
        # FOREIGN token that the http driver would then POST to an attacker's
        # allowlisted endpoint. The general resolver accepts only vault://http/
        # refs and fails closed on anything else.
        # CONNECTION-TYPE-FIRST (Codex FIX 1 — confused-deputy exfiltration). An
        # http connection resolves its credential ONLY through the general vault
        # resolver (vault://http/<key>), which fails closed on anything else. This
        # is the single channel-agnostic egress credential path; there is no
        # scheme-specific (github/slack/workos) resolver — channels are user-built
        # nodes over the generic http connection, not platform code.
        if effective_type == "http":
            return _GeneralVaultCredentialResolver(
                universe_dir=self._universe_dir
            )(credential_ref)
        # Test-fixture refs resolve through the fixture resolver — a REAL gated
        # component, not a mock — for the test paths only.
        if (
            self._provider.startswith("test-fixture.")
            or ref == "test-fixture://nonsecret"
            or ref.startswith(("test-vault-file:", "test-vault-error:"))
        ):
            return _TestFixtureCredentialResolver(
                allow_test_fixtures=self._allow_test_fixtures
            )(credential_ref)
        raise RuntimeError("credential reference has no trusted resolver")


class _TestFixtureNetworkDriver:
    __slots__ = ("_allow_test_fixtures", "_path")

    def __init__(
        self,
        runtime_root: Path,
        *,
        allow_test_fixtures: bool,
    ) -> None:
        self._path = runtime_root / "network.jsonl"
        self._allow_test_fixtures = allow_test_fixtures

    def __call__(
        self,
        *,
        credential: str,
        provider: str,
        destination: str,
        verb: str,
        request: object,
    ) -> dict[str, object]:
        del credential
        outcomes = {
            "test-fixture.created": "created",
            "test-fixture.issue": "issue",
            "test-fixture.fail-once": "fail_once",
            "test-fixture.ambiguous": "ambiguous",
            "test-fixture.explode": "explode",
        }
        outcome = (
            outcomes.get(provider)
            if self._allow_test_fixtures
            else None
        )
        if outcome is None:
            raise ProxyRequestError(
                "provider has no trusted outbound transport"
            )
        prior = self._path.exists()
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "provider": provider,
                        "destination": destination,
                        "verb": verb,
                        "request": request,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
        if outcome == "explode":
            raise RuntimeError("destination request failed")
        if outcome == "fail_once" and not prior:
            raise RuntimeError("destination rejected once")
        if outcome == "ambiguous":
            raise AmbiguousProxyOutcome("connection dropped after send")
        if outcome == "created":
            return {"status": "created"}
        return {"issue_id": 17}


# ---------------------------------------------------------------------------
# General SSRF-hardened outbound HTTP driver
# (channel-agnostic-outbound, design.md D3/D4/D5 — SLICE 1, DARK)
#
# This is the credential-blind general ``_network_request`` driver. It lives
# inside the broker module so a later slice can select it by ``connection_type``
# from ``_TrustedNetworkDriver``. It is DARK in this slice: the dispatch in
# ``_TrustedNetworkDriver`` is UNCHANGED, no channel is migrated, and no default
# flag is flipped. Only the mechanism + its adversarial tests exist. Nothing
# routes through it yet.
# ---------------------------------------------------------------------------

#: Only https is ever dialed; http and every other scheme is refused.
_SSRF_ALLOWED_SCHEME = "https"
#: Default egress ports; a per-connection endpoint allowlist (a later slice)
#: narrows further. Empty-allowlist-permits-nothing lives at that layer.
_SSRF_DEFAULT_PORTS = frozenset({443})
#: Response bounds. Body size is capped DURING the read (streamed read of
#: cap+1 bytes). Header count/bytes are a POST-parse reject: http.client has
#: already buffered the headers when we check, bounded transiently by the
#: stdlib's own _MAXHEADERS=100 / _MAXLINE=65536 ceiling (~6.4 MiB), NOT a
#: during-read cap.
_SSRF_MAX_BODY_BYTES = 5 * 1024 * 1024
_SSRF_MAX_HEADER_COUNT = 100
_SSRF_MAX_HEADER_BYTES = 64 * 1024
_SSRF_TIMEOUT_SECONDS = 30.0
#: Total wall-clock budget across connect + send + body read, enforced with a
#: monotonic deadline so a slow-drip server cannot reset the per-operation
#: socket timeout indefinitely (slowloris + endless chunked trailers;
#: Codex-found). The body is read in bounded chunks, checking the deadline each
#: iteration and tightening the socket timeout to the remaining budget.
_SSRF_MAX_TOTAL_SECONDS = 30.0
_SSRF_READ_CHUNK = 65536
# RESIDUALS owed before this driver is ACTIVATED (it is dark; activation is
# gated behind the endpoint-allowlist slice):
#   - The monotonic wall-clock deadline (_SSRF_MAX_TOTAL_SECONDS) is enforced at
#     the SOCKET layer (_DeadlineSocket), so it uniformly covers the status line,
#     headers, body, and chunked trailers — every phase http.client reads through
#     recv_into — not just the body loop. A slow-drip in ANY phase aborts at the
#     deadline. Header/body byte counts are still capped separately.
#   - The response substring scrub (_declassify_response) is BEST-EFFORT only: a
#     destination that transforms, splits, or re-encodes the secret before
#     echoing it evades a substring scan. The real confidentiality boundary is
#     the per-connection endpoint allowlist PLUS fixed destination-specific
#     response projections (next slice) — once a connection is bound, arbitrary
#     destination headers/body must not cross the child boundary; only the typed,
#     projected fields may. Do not treat the scrub as that boundary.
#   - Network-/org-specific NAT64 prefixes are NOT caught by prefix
#     classification: RFC 6052 permits a deployment to carve a NAT64 prefix from
#     ordinary global-unicast space (e.g. 2001:db8:1::/96 -> 10.0.0.1), which
#     reads as global here. Activation needs deployment-aware prefix rejection or
#     an egress firewall denying translated private destinations.
#   - DNS resolution is NOT inside the total deadline: getaddrinfo runs before the
#     deadline is created and is a blocking OS call a deadline cannot interrupt
#     mid-flight. TCP connect + TLS handshake ARE now deadline-bounded (see
#     _PinnedHTTPSConnection.connect), and all post-handshake parsing is bounded by
#     _DeadlineSocket, so a slow-but-returning resolver only lets DNS time escape
#     the budget; a truly hanging resolver is bounded only by the OS. Fully bounding
#     DNS needs a threaded resolver with its own timeout — an activation-slice item.
# Decompression bound: the driver NEVER decompresses. It sends no
# Accept-Encoding and does not gunzip, so a `Content-Encoding: gzip` body is
# returned as raw bytes capped by _SSRF_MAX_BODY_BYTES — a zip bomb can never
# expand. Redirect bound: redirects are disabled structurally (no
# HTTPRedirectHandler is installed on the opener), so ZERO hops are ever
# followed; a 3xx is returned as-is. If a connection ever opts into redirects,
# the full scheme/host/DNS/peer check must re-run per hop with no cross-origin
# credential forwarding — deliberately not implemented while it is off.
#: Headers a caller may never set: auth is applied inside the child from the
#: typed bundle (D5); Host/proxy routing is owned by the transport, not the
#: packet. Any ``proxy-*`` header is also refused (prefix check below).
_SSRF_FORBIDDEN_REQUEST_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "host",
        "proxy-authorization",
        "proxy-connection",
    }
)
#: Framing / hop-by-hop headers a caller may never set. Letting a caller supply
#: its own Content-Length or Transfer-Encoding is request smuggling: the body
#: can carry a second pipelined request that the destination executes. The
#: transport computes framing itself.
_SSRF_FORBIDDEN_FRAMING_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "expect",
        "keep-alive",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)
#: STANDARDIZED special-use IPv6 ranges ``ipaddress.is_global`` does not
#: consistently reject across CPython versions, checked on the ORIGINAL address
#: before transition unwrapping. This blocks only the fixed IANA/RFC prefixes.
#: It does NOT close org-specific NAT64 prefixes carved from ordinary
#: global-unicast space (RFC 6052) — e.g. a deployment's own
#: ``2001:db8:.../96`` NAT64 that maps to an internal v4. That is a
#: deployment-aware egress-policy concern for the endpoint-allowlist slice, not
#: something structurally decidable here (Codex-noted).
_SSRF_EXTRA_BLOCKED_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64 well-known prefix
    ipaddress.ip_network("64:ff9b:1::/48"),  # NAT64 local-use prefix
    ipaddress.ip_network("::/96"),  # deprecated IPv4-compatible IPv6
)
#: A strict DNS hostname with a real alphabetic TLD. Rejects ``localhost``,
#: all-numeric hosts, ``0x..``/octal spellings, and other unusual IP-literal
#: forms that ``ipaddress`` will not parse as an address.
_SSRF_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)
#: Control chars / whitespace / backslash anywhere in the raw URL is refused.
_SSRF_FORBIDDEN_URL_CHARS = re.compile(r"[\x00-\x20\x7f-\x9f\\]")
#: Control chars (but NOT space) in a header name/value — CR/LF injection guard.
_SSRF_FORBIDDEN_HEADER_CHARS = re.compile(r"[\x00-\x1f\x7f]")
#: HTTP methods a connection may declare and a caller may invoke.
_SSRF_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
#: An allowlist path-template placeholder segment (``{name}``). It matches EXACTLY
#: one non-empty, non-traversal path segment when the concrete URL is checked.
_SSRF_ENDPOINT_PLACEHOLDER_RE = re.compile(r"^\{[a-z0-9_]+\}$")
#: A literal path-template segment: ordinary URL-path characters only. Encoded
#: dot/slash and dot-segments are rejected separately so a template cannot smuggle
#: traversal, and the concrete URL is already dot-segment-free (canonical parse).
_SSRF_ENDPOINT_LITERAL_RE = re.compile(r"^[A-Za-z0-9._~%!$&'()*+,;=:@-]*$")
#: DNS resolution runs in a worker thread bounded by this timeout so a hanging
#: ``getaddrinfo`` (a blocking OS call the request deadline cannot interrupt
#: mid-flight) is abandoned rather than escaping the budget (residual #3). Kept
#: at/under the per-op + total request budget.
_SSRF_DNS_TIMEOUT_SECONDS = 5.0
#: One percent-encoded octet. Used to reject any encoding of a path separator or
#: dot-segment that an origin would decode AFTER our allowlist match — `%2e` (.),
#: `%2f` (/), `%5c` (\), plus control (<0x20, except the legal `%20` space) and
#: high/overlong bytes (>=0x7f — overlong-UTF-8 forms of separators always use
#: high lead/continuation bytes). `%25` (double-encoding) is rejected separately.
_SSRF_PERCENT_ENC_RE = re.compile(r"%([0-9A-Fa-f]{2})")
_SSRF_UNSAFE_ENCODED_BYTES = frozenset({0x2E, 0x2F, 0x5C})
#: A permitted query-parameter NAME in an endpoint allowlist declaration.
_SSRF_QUERY_NAME_RE = re.compile(r"^[A-Za-z0-9_.\[\]-]{1,64}$")
#: A concrete path segment / query value longer than this is refused before the
#: declared regex runs — bounds catastrophic-backtracking exposure on a
#: user-declared pattern (per-universe self-inflicted at worst, but capped).
_SSRF_MAX_MATCH_SEGMENT = 512
#: A declared param/query value pattern longer than this is rejected at authoring.
_SSRF_MAX_PATTERN_LEN = 256
#: A multi-segment ("rest") placeholder — ``{name+}`` — permitted ONLY as the
#: FINAL template segment and at most once. It captures one OR MORE concrete path
#: segments (github contents sub-paths, slash-bearing branch refs) as a single
#: value. The captured tail is split on literal ``/``; each segment is rejected if
#: empty / ``.`` / ``..`` / over-long, the whole tail is bounded (segments + total
#: length), and the ``/``-joined tail must full-match the endpoint's declared
#: pattern for that rest-param. Encoded separators (%2e/%2f/%5c), ``%25``,
#: controls, and overlong bytes are ALREADY rejected on the concrete URL by
#: ``_parse_canonical_https_url`` -> ``_reject_unsafe_encoded_path`` before any
#: match, and the canonical path is already literal-dot-segment-free — so a
#: rest-tail cannot smuggle a traversal an origin would decode later. The declared
#: rest-pattern is the endpoint-specific tightening (repo-relative path for
#: contents; git ref-name shape for branches) on top of those invariants.
_SSRF_ENDPOINT_REST_PLACEHOLDER_RE = re.compile(r"^\{[a-z0-9_]+\+\}$")
#: A concrete rest-tail may span at most this many segments / this many chars.
_SSRF_MAX_REST_SEGMENTS = 40
_SSRF_MAX_REST_TAIL_LEN = 1024
#: Bounds on the raw query string parsed at allowlist time. Without these a
#: duplicate-field flood (``?ref=a&ref=a&...``) forces ``parse_qsl`` to build a
#: huge list before the exactly-once/undeclared checks can reject it — a cheap
#: memory/CPU amplifier on the egress path (Codex). ``max_num_fields`` makes
#: ``parse_qsl`` itself fail closed past the bound.
_SSRF_MAX_QUERY_LEN = 4096
_SSRF_MAX_QUERY_FIELDS = 32


class ConnectionSecretBundle:
    """A typed, per-connection-type set of named secret values (design.md D2).

    Constructed only inside the broker child from resolved credential material;
    it never crosses the process boundary and never appears in a packet. It
    exists so the driver can (a) build the auth header from the correct named
    value and (b) declassify a response against *every* secret it holds, not a
    single string (Slack keeps a bot token and a separate app token; Twitter
    carries four OAuth values).
    """

    __slots__ = ("_values",)

    def __init__(self, **values: str) -> None:
        cleaned: dict[str, str] = {}
        for name, value in values.items():
            if not isinstance(value, str):
                raise TypeError("bundle secret values must be strings")
            if value:
                cleaned[name] = value
        self._values = cleaned

    def get(self, name: str) -> str:
        value = self._values.get(name, "")
        if not value:
            raise SsrfValidationError("connection secret bundle is missing a value")
        return value

    def secret_values(self) -> tuple[str, ...]:
        return tuple(self._values.values())


def _reject_forbidden_header_name(name: str) -> None:
    """Refuse any sensitive, framing/hop-by-hop, or ``proxy-*`` header name.

    The SINGLE policy for both caller-supplied headers and a custom auth header
    name — a custom name must not be a back door around the framing denylist
    (``auth_scheme="header", header_name="Content-Length"`` was a smuggling
    vector, Codex-found).
    """
    low = name.strip().lower()
    if (
        not low
        or low in _SSRF_FORBIDDEN_REQUEST_HEADERS
        or low in _SSRF_FORBIDDEN_FRAMING_HEADERS
        or low.startswith("proxy-")
    ):
        raise SsrfValidationError("header name is not permitted")


def _oauth1a_percent(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~-._")


def _oauth1a_authorization(
    bundle: ConnectionSecretBundle, *, method: str, url: str
) -> str:
    """OAuth 1.0a HMAC-SHA1 ``Authorization`` built INSIDE the child (Twitter).

    The algorithm is the standard OAuth 1.0a HMAC-SHA1 signer (its byte-identical
    reference oracle is pinned in ``tests/test_outbound_channel_migration.py``), but
    it reads the four OAuth secrets from the typed ``ConnectionSecretBundle`` — the
    auth material is applied where the credential already legitimately lives, never
    at the adapter. The bundle is ``{api_key, api_secret, access_token,
    access_token_secret}``; a missing member fails closed via ``bundle.get``.
    """
    oauth_params = {
        "oauth_consumer_key": bundle.get("api_key"),
        "oauth_nonce": secrets.token_urlsafe(24),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": bundle.get("access_token"),
        "oauth_version": "1.0",
    }
    parsed = urllib.parse.urlparse(url)
    base_url = urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
    )
    query_params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    signature_params = {**query_params, **oauth_params}
    encoded_pairs = [
        f"{_oauth1a_percent(key)}={_oauth1a_percent(value)}"
        for key, value in sorted(signature_params.items())
    ]
    normalized = "&".join(encoded_pairs)
    base_string = "&".join([
        method.upper(),
        _oauth1a_percent(base_url),
        _oauth1a_percent(normalized),
    ])
    signing_key = (
        f"{_oauth1a_percent(bundle.get('api_secret'))}&"
        f"{_oauth1a_percent(bundle.get('access_token_secret'))}"
    )
    digest = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    rendered = ", ".join(
        f'{_oauth1a_percent(key)}="{_oauth1a_percent(value)}"'
        for key, value in sorted(oauth_params.items())
    )
    return f"OAuth {rendered}"


def _ssrf_auth_headers(
    auth_scheme: str,
    bundle: ConnectionSecretBundle,
    *,
    header_name: str = "",
    method: str = "",
    url: str = "",
) -> dict[str, str]:
    """Build the auth header(s) INSIDE the child from the typed bundle (D5)."""
    scheme = (auth_scheme or "none").strip().lower()
    if scheme == "none":
        result: dict[str, str] = {}
    elif scheme == "bearer":
        result = {"Authorization": f"Bearer {bundle.get('token')}"}
    elif scheme == "basic":
        raw = f"{bundle.get('username')}:{bundle.get('password')}".encode("utf-8")
        result = {"Authorization": "Basic " + base64.b64encode(raw).decode("ascii")}
    elif scheme == "header":
        name = (header_name or "").strip()
        if not name or _SSRF_FORBIDDEN_HEADER_CHARS.search(name):
            raise SsrfValidationError("custom auth header name is not permitted")
        _reject_forbidden_header_name(name)
        result = {name: bundle.get("token")}
    elif scheme == "oauth1a":
        # OAuth 1.0a (Twitter): the signature is over the request method + URL, so
        # they are threaded in from the driver. Signed entirely in the child.
        result = {
            "Authorization": _oauth1a_authorization(bundle, method=method, url=url)
        }
    else:
        raise SsrfValidationError("auth scheme is not supported")
    # Validate the auth-DERIVED values too, not just caller headers: a bundle
    # token carrying CR/LF (obs-fold) would otherwise emit a folded header line
    # http.client accepts verbatim, re-opening request smuggling (Codex-found).
    for value in result.values():
        if _SSRF_FORBIDDEN_HEADER_CHARS.search(value):
            raise SsrfValidationError("auth header value contains forbidden characters")
    return result


@dataclass(frozen=True, slots=True)
class _CanonicalOutboundUrl:
    hostname: str
    port: int
    path_qs: str
    is_ip_literal: bool


def _canonical_request_url(canonical: _CanonicalOutboundUrl) -> str:
    """The exact https URL the driver puts on the wire (also what oauth1a signs)."""
    host_for_url = (
        f"[{canonical.hostname}]"
        if canonical.is_ip_literal and ":" in canonical.hostname
        else canonical.hostname
    )
    url = f"https://{host_for_url}"
    if canonical.port != 443:
        url += f":{canonical.port}"
    return url + canonical.path_qs


def _reject_unsafe_encoded_path(path: str) -> None:
    """Refuse any percent-encoding that decodes to a hidden separator (FIX 2).

    A raw dot-segment is caught by the caller; this catches the *encoded* forms
    an origin would decode AFTER the allowlist template matches — `%2e` (.),
    `%2f` (/), and `%5c`/`%5C` (\\, a Windows/IIS separator missed pre-fix), plus
    overlong-UTF-8 spellings of those (which always use high bytes >=0x7f) and
    encoded control chars. `%20` (space) stays legal so real paths still parse;
    `%25` (double-encoding) is rejected by the caller before this runs.
    """
    for match in _SSRF_PERCENT_ENC_RE.finditer(path):
        byte = int(match.group(1), 16)
        if byte in _SSRF_UNSAFE_ENCODED_BYTES or byte < 0x20 or byte >= 0x7F:
            raise SsrfValidationError(
                "outbound url path contains an unsafe encoded byte"
            )


def _parse_canonical_https_url(
    url: str,
    *,
    allowed_ports: frozenset[int],
) -> _CanonicalOutboundUrl:
    """Parse exactly ONE absolute, canonical https URL or fail closed (D3.1)."""
    if not isinstance(url, str) or not url:
        raise SsrfValidationError("outbound url is required")
    if _SSRF_FORBIDDEN_URL_CHARS.search(url):
        raise SsrfValidationError("outbound url contains forbidden characters")
    if "%25" in url:
        # An encoded percent sign is a double-encoding canonicalization smell.
        raise SsrfValidationError("outbound url must not be double-encoded")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != _SSRF_ALLOWED_SCHEME:
        raise SsrfValidationError("outbound url scheme must be https")
    if (
        parsed.username is not None
        or parsed.password is not None
        or "@" in parsed.netloc
    ):
        raise SsrfValidationError("outbound url must not carry userinfo")
    if parsed.fragment:
        raise SsrfValidationError("outbound url must not carry a fragment")
    host = parsed.hostname
    if not host:
        raise SsrfValidationError("outbound url host is required")
    if "%" in host:
        raise SsrfValidationError("outbound url host must not be percent-encoded")
    try:
        port = parsed.port
    except ValueError:
        raise SsrfValidationError("outbound url port is invalid") from None
    port = 443 if port is None else port
    if port not in allowed_ports:
        raise SsrfValidationError("outbound url port is not permitted")
    path = parsed.path or "/"
    if any(segment in (".", "..") for segment in path.split("/")):
        raise SsrfValidationError("outbound url path must not contain dot-segments")
    _reject_unsafe_encoded_path(path)
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False
    if not is_ip_literal and not _SSRF_HOSTNAME_RE.match(host):
        raise SsrfValidationError("outbound url host is not a permitted hostname")
    path_qs = f"{path}?{parsed.query}" if parsed.query else path
    return _CanonicalOutboundUrl(
        hostname=host,
        port=port,
        path_qs=path_qs,
        is_ip_literal=is_ip_literal,
    )


def _validate_endpoint_methods(methods: Any) -> tuple[str, ...]:
    if isinstance(methods, str) or not isinstance(methods, (list, tuple)):
        raise SsrfValidationError("endpoint methods must be a list")
    seen: list[str] = []
    for method in methods:
        verb = str(method).strip().upper()
        if verb not in _SSRF_ALLOWED_METHODS:
            raise SsrfValidationError("endpoint method is not permitted")
        if verb not in seen:
            seen.append(verb)
    if not seen:
        raise SsrfValidationError("endpoint must permit at least one method")
    return tuple(seen)


def _placeholder_names(path_template: str) -> list[str]:
    return [
        segment[1:-1]
        for segment in path_template.split("/")
        if _SSRF_ENDPOINT_PLACEHOLDER_RE.match(segment)
    ]


def _rest_placeholder_name(path_template: str) -> str | None:
    """The name of the final ``{name+}`` rest placeholder, or ``None``.

    A rest placeholder is permitted ONLY as the final segment and at most once —
    ``_validate_path_template`` enforces that at authoring, so at match time this
    trusts the stored template. ``{name+}`` strips to ``name`` (drop ``{`` and
    ``+}``).
    """
    segments = path_template.split("/")
    last = segments[-1] if segments else ""
    if _SSRF_ENDPOINT_REST_PLACEHOLDER_RE.match(last):
        return last[1:-2]
    return None


def _validate_path_template(path_template: Any) -> str:
    """Validate a stored allowlist path template (traversal-free, ``/``-rooted)."""
    if not isinstance(path_template, str) or not path_template.startswith("/"):
        raise SsrfValidationError("endpoint path_template must be an absolute path")
    if _SSRF_FORBIDDEN_URL_CHARS.search(path_template):
        raise SsrfValidationError("endpoint path_template contains forbidden characters")
    if "%25" in path_template:
        raise SsrfValidationError("endpoint path_template must not be double-encoded")
    # Same encoded-separator guard the concrete URL gets (FIX 2): reject
    # %2e/%2f/%5c and overlong/control encodings a stored template could smuggle.
    _reject_unsafe_encoded_path(path_template)
    segments = path_template.split("/")[1:]
    for index, segment in enumerate(segments):
        if segment in (".", ".."):
            raise SsrfValidationError("endpoint path_template must not contain dot-segments")
        if _SSRF_ENDPOINT_PLACEHOLDER_RE.match(segment):
            continue
        if _SSRF_ENDPOINT_REST_PLACEHOLDER_RE.match(segment):
            # A multi-segment tail is only sound as the FINAL segment — anywhere
            # else it would swallow later fixed segments and defeat the
            # destination pin (`/repos/<owner>/<repo>/...`).
            if index != len(segments) - 1:
                raise SsrfValidationError(
                    "endpoint rest placeholder must be the final path segment"
                )
            continue
        if not _SSRF_ENDPOINT_LITERAL_RE.match(segment):
            raise SsrfValidationError("endpoint path_template segment is not permitted")
    return path_template


def _compile_declared_pattern(pattern: Any) -> str:
    """Validate one declared value pattern (compiles, bounded), return its text."""
    if not isinstance(pattern, str) or not pattern:
        raise SsrfValidationError("endpoint value pattern must be a non-empty string")
    if len(pattern) > _SSRF_MAX_PATTERN_LEN:
        raise SsrfValidationError("endpoint value pattern is too long")
    try:
        re.compile(pattern)
    except re.error:
        raise SsrfValidationError("endpoint value pattern is invalid") from None
    return pattern


def _validate_param_patterns(
    path_template: str, raw: Any
) -> tuple[tuple[str, str], ...]:
    """Every ``{param}`` / ``{param+}`` MUST declare a value pattern; no strays (FIX 3)."""
    placeholders = _placeholder_names(path_template)
    rest_name = _rest_placeholder_name(path_template)
    all_names = placeholders + ([rest_name] if rest_name else [])
    if len(set(all_names)) != len(all_names):
        raise SsrfValidationError("endpoint path_template has duplicate placeholders")
    placeholder_set = set(all_names)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise SsrfValidationError("endpoint param_patterns must be an object")
    declared = {str(name) for name in raw}
    if declared != placeholder_set:
        raise SsrfValidationError(
            "endpoint param_patterns must declare exactly the path placeholders"
        )
    return tuple(
        (name, _compile_declared_pattern(raw[name]))
        for name in sorted(placeholder_set)
    )


def _validate_query_rules(
    allowed_raw: Any, patterns_raw: Any, required_raw: Any
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], tuple[str, ...]]:
    """Declared query names + optional value patterns + required names.

    ``required_query`` names must be a subset of ``allowed_query`` and are each
    enforced present EXACTLY ONCE at match time (Codex FIX: exactly-one ref).
    Undeclared names are refused; declared names may be pattern-constrained.
    """
    if allowed_raw is None:
        allowed_raw = []
    if isinstance(allowed_raw, str) or not isinstance(allowed_raw, (list, tuple)):
        raise SsrfValidationError("endpoint allowed_query must be a list")
    allowed: list[str] = []
    for name in allowed_raw:
        text = str(name).strip()
        if not _SSRF_QUERY_NAME_RE.match(text):
            raise SsrfValidationError("endpoint allowed_query name is not permitted")
        if text not in allowed:
            allowed.append(text)
    if patterns_raw is None:
        patterns_raw = {}
    if not isinstance(patterns_raw, dict):
        raise SsrfValidationError("endpoint query_patterns must be an object")
    patterns: list[tuple[str, str]] = []
    for name, pattern in patterns_raw.items():
        text = str(name).strip()
        if text not in allowed:
            raise SsrfValidationError(
                "endpoint query_patterns names must be in allowed_query"
            )
        patterns.append((text, _compile_declared_pattern(pattern)))
    if required_raw is None:
        required_raw = []
    if isinstance(required_raw, str) or not isinstance(required_raw, (list, tuple)):
        raise SsrfValidationError("endpoint required_query must be a list")
    required: list[str] = []
    for name in required_raw:
        text = str(name).strip()
        if text not in allowed:
            raise SsrfValidationError(
                "endpoint required_query names must be in allowed_query"
            )
        if text not in required:
            required.append(text)
    return tuple(allowed), tuple(sorted(patterns)), tuple(sorted(required))


def _validate_endpoint(raw: Any) -> OutboundEndpoint:
    """Coerce+validate one stored/authored allowlist endpoint, or fail closed."""
    if isinstance(raw, OutboundEndpoint):
        raw = raw.as_dict()
    if not isinstance(raw, dict):
        raise SsrfValidationError("endpoint must be an object")
    host = str(raw.get("host", "")).strip().lower()
    if not host or "%" in host or not _SSRF_HOSTNAME_RE.match(host):
        # Allowlist hosts are real DNS hostnames only — never IP literals, never
        # single-label names — matching the transport's own hostname policy.
        raise SsrfValidationError("endpoint host is not a permitted hostname")
    path_template = _validate_path_template(raw.get("path_template"))
    allowed_query, query_patterns, required_query = _validate_query_rules(
        raw.get("allowed_query"), raw.get("query_patterns"), raw.get("required_query")
    )
    return OutboundEndpoint(
        host=host,
        path_template=path_template,
        methods=_validate_endpoint_methods(raw.get("methods")),
        param_patterns=_validate_param_patterns(path_template, raw.get("param_patterns")),
        allowed_query=allowed_query,
        query_patterns=query_patterns,
        required_query=required_query,
    )


def _parse_allowed_endpoints(raw: Any) -> tuple[OutboundEndpoint, ...]:
    """Parse the allowlist from create input or stored JSON; each is validated."""
    if raw is None or raw == "":
        return ()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            raise SsrfValidationError("stored endpoint allowlist is invalid") from None
    if isinstance(raw, (list, tuple)):
        return tuple(_validate_endpoint(item) for item in raw)
    raise SsrfValidationError("endpoint allowlist must be a list")


def _segment_matches_pattern(segment: str, pattern: str) -> bool:
    """Full-match one concrete segment/value against a declared pattern, bounded."""
    if not segment or segment in (".", ".."):
        return False
    if len(segment) > _SSRF_MAX_MATCH_SEGMENT:
        return False
    return re.fullmatch(pattern, segment) is not None


def _fixed_segments_match(
    concrete: list[str], pattern: list[str], param_patterns: dict[str, str]
) -> bool:
    """Match a run of concrete segments against fixed/``{param}`` template segments.

    Each ``{param}`` must full-match its DECLARED single-segment pattern; a
    placeholder with no declared pattern fails closed (an over-broad "any
    non-empty segment" match is exactly the FIX 3 bypass). Literals must be
    byte-equal. Lengths must already be equal.
    """
    for got, want in zip(concrete, pattern):
        if _SSRF_ENDPOINT_PLACEHOLDER_RE.match(want):
            declared = param_patterns.get(want[1:-1])
            if declared is None or not _segment_matches_pattern(got, declared):
                return False
            continue
        if got != want:
            return False
    return True


def _path_matches_template(
    path: str, template: str, param_patterns: dict[str, str]
) -> bool:
    """Segment-wise match; each ``{param}``/``{param+}`` full-matches its pattern.

    Fixed-arity templates require equal segment counts. A template ending in a
    ``{name+}`` rest placeholder matches its fixed prefix segment-for-segment,
    then captures the REMAINING concrete segments (>=1) as the rest-tail — each
    tail segment rejected if empty / ``.`` / ``..`` / over-long, the whole tail
    bounded, and the ``/``-joined tail full-matched against the rest-param's
    DECLARED endpoint-specific pattern. The concrete URL is already canonical,
    literal-dot-segment-free, and stripped of encoded separators (%2e/%2f/%5c)
    upstream, so the rest-tail cannot smuggle a decoded traversal.
    """
    concrete = path.split("/")
    pattern = template.split("/")
    rest_name = _rest_placeholder_name(template)
    if rest_name is None:
        if len(concrete) != len(pattern):
            return False
        return _fixed_segments_match(concrete, pattern, param_patterns)

    prefix = pattern[:-1]
    # The rest placeholder captures one OR MORE segments.
    if len(concrete) < len(prefix) + 1:
        return False
    if not _fixed_segments_match(concrete[: len(prefix)], prefix, param_patterns):
        return False
    tail_segments = concrete[len(prefix):]
    if len(tail_segments) > _SSRF_MAX_REST_SEGMENTS:
        return False
    for seg in tail_segments:
        if not seg or seg in (".", "..") or len(seg) > _SSRF_MAX_MATCH_SEGMENT:
            return False
    tail = "/".join(tail_segments)
    if len(tail) > _SSRF_MAX_REST_TAIL_LEN:
        return False
    declared = param_patterns.get(rest_name)
    if declared is None:
        return False
    return re.fullmatch(declared, tail) is not None


def _query_permitted(query_items: list[tuple[str, str]], endpoint: OutboundEndpoint) -> bool:
    """Refuse any query parameter not DECLARED in the endpoint (FIX 3).

    Queries are no longer discarded before matching: an undeclared parameter (or
    a declared one whose value fails its pattern) refuses the whole request, so a
    tenant/target/operation cannot ride in a query string to escape the
    connection's destination. A ``required_query`` name must additionally appear
    EXACTLY ONCE (Codex FIX: exactly-one validated ref) — zero occurrences or a
    duplicate refuses the request.
    """
    allowed = set(endpoint.allowed_query)
    patterns = dict(endpoint.query_patterns)
    counts: dict[str, int] = {}
    for name, value in query_items:
        if name not in allowed:
            return False
        declared = patterns.get(name)
        if declared is not None and not _segment_matches_pattern(value, declared):
            return False
        counts[name] = counts.get(name, 0) + 1
    for required in endpoint.required_query:
        if counts.get(required, 0) != 1:
            return False
    return True


def _enforce_endpoint_allowlist(
    canonical: _CanonicalOutboundUrl,
    method: str,
    endpoints: tuple[OutboundEndpoint, ...],
) -> None:
    """Refuse any host/method/path/query not on the connection allowlist (design.md D3).

    This is the real egress boundary: an EMPTY allowlist permits nothing, and a
    URL whose host, method, path, OR query does not match a declared endpoint is
    refused before any socket is opened.
    """
    if not endpoints:
        raise SsrfValidationError("connection has no permitted endpoints")
    host = canonical.hostname.strip().lower()
    verb = (method or "").strip().upper()
    raw_path, _, raw_query = canonical.path_qs.partition("?")
    if len(raw_query) > _SSRF_MAX_QUERY_LEN:
        raise SsrfValidationError("outbound url query is too long")
    try:
        query_items = (
            urllib.parse.parse_qsl(
                raw_query,
                keep_blank_values=True,
                max_num_fields=_SSRF_MAX_QUERY_FIELDS,
            )
            if raw_query
            else []
        )
    except ValueError:
        # parse_qsl raises when the field count exceeds the bound; treat a
        # flood as a refused request rather than an unbounded parse.
        raise SsrfValidationError("outbound url query has too many fields") from None
    for endpoint in endpoints:
        if endpoint.host != host:
            continue
        if verb not in endpoint.methods:
            continue
        if not _path_matches_template(
            raw_path, endpoint.path_template, dict(endpoint.param_patterns)
        ):
            continue
        if not _query_permitted(query_items, endpoint):
            continue
        return
    raise SsrfValidationError("outbound endpoint is not on the connection allowlist")


def _classify_global_address(ip_text: str) -> str:
    """Return the address only if it is globally routable; else fail closed.

    Unwraps IPv4-mapped / 6to4 / Teredo IPv6 so an embedded private v4 cannot
    ride in as a "global" v6, and rejects loopback, link-local (incl. the cloud
    metadata address), private, ULA, shared/CGNAT, reserved, unspecified, and
    multicast (D3.2).
    """
    try:
        ip_obj = ipaddress.ip_address(ip_text)
    except ValueError:
        raise SsrfValidationError("resolved address is not a valid ip") from None
    for network in _SSRF_EXTRA_BLOCKED_NETWORKS:
        if ip_obj.version == network.version and ip_obj in network:
            raise SsrfValidationError("resolved address is not globally routable")
    if isinstance(ip_obj, ipaddress.IPv6Address):
        if ip_obj.ipv4_mapped is not None:
            ip_obj = ip_obj.ipv4_mapped
        elif ip_obj.sixtofour is not None:
            ip_obj = ip_obj.sixtofour
        elif ip_obj.teredo is not None:
            ip_obj = ip_obj.teredo[1]
    if (
        not ip_obj.is_global
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_private
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
        # IPv6-only; ``fec0::/10`` deprecated site-local reads as global on some
        # CPython versions (Codex-found). getattr keeps the IPv4 path working.
        or getattr(ip_obj, "is_site_local", False)
    ):
        raise SsrfValidationError("resolved address is not globally routable")
    return str(ip_obj)


def _default_dns_resolver(hostname: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for info in infos:
        addr = info[4][0]
        if addr not in seen:
            seen.add(addr)
            ordered.append(addr)
    return ordered


def _threaded_dns_resolve(
    hostname: str,
    port: int,
    *,
    base_resolver: Callable[[str, int], list[str]],
    timeout: float,
) -> list[str]:
    """Resolve ``hostname`` in a worker thread bounded by ``timeout`` (residual #3).

    ``getaddrinfo`` is a blocking OS call the request's monotonic deadline cannot
    interrupt once it is stuck, so a hostile/black-hole resolver could hang the
    child indefinitely BEFORE the deadline machinery (which starts at connect
    time) is armed. Running it in a daemon thread we abandon on timeout closes
    that: on timeout the thread is left to die with the process and the request
    FAILS CLOSED. The abandoned thread never mutates request state — its result
    is read only if it finished in time.
    """
    outcome: dict[str, Any] = {}
    done = threading.Event()

    def _work() -> None:
        try:
            outcome["addresses"] = base_resolver(hostname, port)
        except BaseException as exc:  # noqa: BLE001 - carried, re-raised on the caller thread
            outcome["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(
        target=_work,
        name="outbound-dns-resolve",
        daemon=True,
    )
    worker.start()
    if not done.wait(max(0.0, float(timeout))):
        # Abandon the hung getaddrinfo thread; fail closed within the budget.
        raise SsrfValidationError("outbound host resolution exceeded the deadline")
    error = outcome.get("error")
    if error is not None:
        if isinstance(error, SsrfValidationError):
            raise error
        raise SsrfValidationError("outbound host resolution failed") from None
    return list(outcome.get("addresses", []))


def _make_default_resolver(timeout: float) -> Callable[[str, int], list[str]]:
    """The production resolver: ``getaddrinfo`` wrapped in the threaded deadline."""

    def _resolver(hostname: str, port: int) -> list[str]:
        return _threaded_dns_resolve(
            hostname,
            port,
            base_resolver=_default_dns_resolver,
            timeout=timeout,
        )

    return _resolver


def _resolve_pinned_addresses(
    hostname: str,
    port: int,
    *,
    resolver: Callable[[str, int], list[str]],
    validator: Callable[[str], str],
) -> list[str]:
    """Resolve, validate EVERY A/AAAA result, and return pinnable addresses."""
    try:
        candidates = resolver(hostname, port)
    except SsrfValidationError:
        raise
    except Exception:
        raise SsrfValidationError("outbound host resolution failed") from None
    if not candidates:
        raise SsrfValidationError("outbound host did not resolve")
    # validator raises on the FIRST non-global result — reject the whole host.
    return [validator(addr) for addr in candidates]


def _normalize_ip(text: str) -> str:
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return text


def _default_open_socket(
    address: tuple[str, int],
    timeout: float | None,
    source_address: tuple[str, int] | None,
) -> socket.socket:
    return socket.create_connection(
        address,
        timeout=timeout,
        source_address=source_address,
    )


class _TotalDeadlineExceeded(Exception):
    """The request exceeded its monotonic wall-clock budget."""


def _looks_like_deadline_breach(exc: BaseException, deadline: float) -> bool:
    """True if a request failure is really a total-deadline breach.

    ``_DeadlineSocket`` closes a drip two ways: it raises ``_TotalDeadlineExceeded``
    when the budget is already spent, but as the deadline approaches it tightens the
    socket timeout to the tiny remaining budget, so the LAST read (e.g. during the
    status-line/header parse inside ``opener.open()``, which urllib does not wrap)
    surfaces as a ``TimeoutError`` right at the deadline. Both mean the same thing —
    detect either so a breach in ANY phase is labeled uniformly rather than as a
    generic destination failure.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, _TotalDeadlineExceeded):
            return True
        reason = getattr(cur, "reason", None)
        if isinstance(reason, _TotalDeadlineExceeded):
            return True
        cur = cur.__cause__ or cur.__context__
    return time.monotonic() >= deadline


class _DeadlineSocket:
    """A delegating socket proxy that enforces an absolute monotonic deadline on
    EVERY read and write.

    http.client parses the status line, headers, body, and chunked trailers by
    reading through ``sock.makefile("rb")`` -> ``recv_into`` inside stdlib loops
    that honor only the per-socket timeout. A drip that sends one byte before
    each timeout keeps those loops alive forever (Codex-found). Wrapping the
    connected socket so every ``recv_into``/``recv``/``send`` first checks the
    deadline — and tightens the socket timeout to the remaining budget — makes
    the total budget cover ALL phases uniformly, so a drip aborts at the
    deadline inside the stdlib parser too, not only in the body loop.
    """

    __slots__ = ("_deadline", "_per_op_timeout", "_sock")

    def __init__(self, sock: Any, *, deadline: float, per_op_timeout: float | None) -> None:
        self._sock = sock
        self._deadline = deadline
        self._per_op_timeout = per_op_timeout

    def _arm(self) -> None:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise _TotalDeadlineExceeded
        budget = remaining
        if self._per_op_timeout is not None and self._per_op_timeout > 0:
            budget = min(self._per_op_timeout, remaining)
        try:
            self._sock.settimeout(max(0.001, budget))
        except OSError:
            pass

    def recv_into(self, buffer: Any, *args: Any) -> int:
        self._arm()
        return self._sock.recv_into(buffer, *args)

    def recv(self, *args: Any) -> bytes:
        self._arm()
        return self._sock.recv(*args)

    def sendall(self, data: Any, *args: Any) -> None:
        self._arm()
        return self._sock.sendall(data, *args)

    def send(self, data: Any, *args: Any) -> int:
        self._arm()
        return self._sock.send(data, *args)

    def makefile(self, mode: str = "rb", buffering: int | None = None, **_kwargs: Any) -> Any:
        # Mirror socket.makefile, but bind SocketIO to THIS proxy so its reads go
        # through our deadline-armed recv_into rather than the raw socket's.
        raw = socket.SocketIO(self, "rb")
        self._sock._io_refs += 1
        if buffering is None:
            buffering = io.DEFAULT_BUFFER_SIZE
        if buffering == 0:
            return raw
        return io.BufferedReader(raw, buffering)

    def _decref_socketios(self) -> None:
        self._sock._decref_socketios()

    def settimeout(self, value: float | None) -> None:
        self._sock.settimeout(value)

    def gettimeout(self) -> float | None:
        return self._sock.gettimeout()

    def close(self) -> None:
        self._sock.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._sock, name)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to a PINNED validated address, keeping SNI/cert verification.

    Defeats DNS-rebinding/TOCTOU: the vetted address (already classified
    ``is_global``) is dialed directly, so there is no second resolution, and the
    connected peer is re-checked against the pin. TLS SNI and certificate
    hostname verification still run against the original hostname (``self.host``).
    The connected socket is wrapped in a ``_DeadlineSocket`` so the request's
    total wall-clock deadline covers status line + headers + body + trailers.
    """

    def __init__(
        self,
        host: str,
        *,
        pinned_address: str,
        open_socket: Callable[..., socket.socket],
        deadline: float,
        **kwargs: Any,
    ) -> None:
        super().__init__(host, **kwargs)
        self._pinned_address = pinned_address
        self._open_socket = open_socket
        self._deadline = deadline

    def connect(self) -> None:  # noqa: D102 - overrides http.client
        # Bound the TCP connect by the remaining TOTAL budget, not just the per-op
        # timeout: the deadline otherwise only covers post-handshake reads, so a
        # slow-connect + slow-TLS peer could push the request well past it
        # (Codex-found: 29s connect + 5s handshake beats a 30s deadline).
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise _TotalDeadlineExceeded
        connect_timeout = (
            remaining if self.timeout is None else min(self.timeout, remaining)
        )
        sock = self._open_socket(
            (self._pinned_address, self.port),
            connect_timeout,
            self.source_address,
        )
        try:
            peer = sock.getpeername()[0]
            if _normalize_ip(peer) != _normalize_ip(self._pinned_address):
                raise SsrfValidationError("connected peer is not the pinned address")
            # Bound the TLS handshake by the remaining budget too — the raw socket's
            # timeout governs the handshake reads before _DeadlineSocket is installed.
            remaining = self._deadline - time.monotonic()
            if remaining <= 0:
                raise _TotalDeadlineExceeded
            sock.settimeout(
                remaining if self.timeout is None else min(self.timeout, remaining)
            )
        except BaseException:
            try:
                sock.close()
            except Exception:
                pass
            raise
        tls = self._context.wrap_socket(sock, server_hostname=self.host)
        # Enforce the total deadline at the socket layer, covering every http.client
        # read phase (status line, headers, body, chunked trailers) — not just the
        # body loop, which cannot see the deadline while parsing runs in stdlib.
        self.sock = _DeadlineSocket(
            tls,
            deadline=self._deadline,
            per_op_timeout=self.timeout,
        )


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    """urllib HTTPS handler that drives the pinned connection above."""

    def __init__(
        self,
        *,
        context: Any,
        pinned_address: str,
        open_socket: Callable[..., socket.socket],
        deadline: float,
    ) -> None:
        super().__init__(context=context)
        self._pinned_address = pinned_address
        self._open_socket = open_socket
        self._deadline = deadline

    def https_open(self, req: Any) -> Any:
        return self.do_open(self._make_connection, req)

    def _make_connection(
        self,
        host: str,
        *,
        timeout: float | None = None,
        **_ignored: Any,
    ) -> _PinnedHTTPSConnection:
        return _PinnedHTTPSConnection(
            host,
            timeout=timeout,
            context=self._context,
            pinned_address=self._pinned_address,
            open_socket=self._open_socket,
            deadline=self._deadline,
        )


def _read_capped_body(response: Any, max_body_bytes: int) -> bytes | None:
    """Read the body in bounded chunks, enforcing only the size cap.

    The wall-clock deadline is enforced at the socket layer (``_DeadlineSocket``),
    which raises ``_TotalDeadlineExceeded`` from inside ``read1``'s recv if the
    budget is spent — so this loop only needs the size cap. ``read1`` returns
    after at most one underlying recv, so a huge body is cut at the cap without
    being fully read. Returns the bytes, or None on a size-bound violation.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = response.read1(min(_SSRF_READ_CHUNK, max_body_bytes + 1 - total))
        if not piece:
            break
        total += len(piece)
        if total > max_body_bytes:
            return None
        chunks.append(piece)
    return b"".join(chunks)


def _execute_pinned_https_request(
    *,
    method: str,
    canonical: _CanonicalOutboundUrl,
    pinned_address: str,
    headers: dict[str, str],
    body: bytes | None,
    ssl_context: Any,
    open_socket: Callable[..., socket.socket],
    timeout: float,
    max_total_seconds: float,
    max_body_bytes: int,
    max_header_count: int,
    max_header_bytes: int,
) -> dict[str, Any]:
    """Fire ONE request: no ambient proxies, no redirects, bounded response."""
    deadline = time.monotonic() + max_total_seconds
    url = _canonical_request_url(canonical)
    request = urllib.request.Request(url, data=body, method=method, headers=headers)

    opener = urllib.request.OpenerDirector()
    # Ambient/env proxies disabled (D3.5): an explicit empty proxy map, and the
    # opener is built by hand so no default env-proxy handler is ever installed.
    opener.add_handler(urllib.request.ProxyHandler({}))
    # No HTTPRedirectHandler and no HTTPErrorProcessor are added, so a 3xx is
    # returned as-is (never auto-followed) and non-2xx does not raise (D3.4).
    opener.add_handler(
        _PinnedHTTPSHandler(
            context=ssl_context,
            pinned_address=pinned_address,
            open_socket=open_socket,
            deadline=deadline,
        )
    )

    response = None
    deadline_exceeded = False
    try:
        # Cap connect + header phase at the smaller of the per-op timeout and the
        # remaining total budget; the socket-layer deadline (_DeadlineSocket)
        # additionally bounds the status-line + header parse against the total.
        response = opener.open(request, timeout=min(timeout, max_total_seconds))
    except _TotalDeadlineExceeded:
        deadline_exceeded = True
    except SsrfValidationError:
        raise
    except Exception as exc:
        # A deadline breach during the status-line/header parse surfaces as a
        # urllib-wrapped TimeoutError (opener.open does not re-wrap getresponse),
        # so the bare _TotalDeadlineExceeded above misses it — recognize it here
        # so every phase's breach is labeled as the deadline, not a generic fail.
        if _looks_like_deadline_breach(exc, deadline):
            deadline_exceeded = True
        else:
            response = None
    if deadline_exceeded:
        # Raised OUTSIDE the except block: a fixed, secret-free message with a
        # clean __context__.
        raise SsrfValidationError("outbound request exceeded the total deadline")
    if response is None:
        # Raised OUTSIDE the except block on purpose: `raise ... from None` still
        # leaves ``__context__`` populated (readable via ``exc.__context__`` — the
        # Authorization-echo leak class, where a URLError/BadStatusLine can quote
        # the reflected Authorization header). Raising here clears it.
        raise ProxyRequestError("outbound request failed at destination")

    # Collect the sanitized result (or a bound-violation reason) inside the
    # try, but raise only AFTER the block so no server-controlled exception can
    # ride out on ``__context__``.
    sanitized: dict[str, Any] | None = None
    bound_violation: str | None = None
    read_deadline_exceeded = False
    try:
        status = int(response.status)
        reason = str(getattr(response, "reason", "") or "")
        raw_headers = list(response.getheaders())
        if len(raw_headers) > max_header_count:
            bound_violation = "outbound response has too many headers"
        elif sum(len(str(k)) + len(str(v)) for k, v in raw_headers) > max_header_bytes:
            bound_violation = "outbound response headers exceed the bound"
        else:
            declared = response.getheader("Content-Length")
            declared_ok = True
            if declared is not None:
                try:
                    declared_ok = int(declared) <= max_body_bytes
                except (TypeError, ValueError):
                    declared_ok = True
            if not declared_ok:
                bound_violation = "outbound response exceeds the size bound"
            else:
                body_bytes = _read_capped_body(response, max_body_bytes)
                if body_bytes is None:
                    bound_violation = "outbound response exceeds the size bound"
                else:
                    sanitized = {
                        "status": status,
                        "reason": reason,
                        "headers": {
                            str(name).lower(): str(value)
                            for name, value in raw_headers
                        },
                        "body": body_bytes.decode("utf-8", errors="replace"),
                    }
    except _TotalDeadlineExceeded:
        read_deadline_exceeded = True
    except Exception as exc:
        # A deadline breach during the body / chunked-trailer read can also surface
        # as a TimeoutError from the tightened socket timeout — label it as the
        # deadline (fail-closed) rather than a generic destination failure, exactly
        # as the header-phase handler does.
        if _looks_like_deadline_breach(exc, deadline):
            read_deadline_exceeded = True
        else:
            sanitized = None
            bound_violation = None
    finally:
        try:
            response.close()
        except Exception:
            pass

    if read_deadline_exceeded:
        raise SsrfValidationError("outbound request exceeded the total deadline")
    if bound_violation is not None:
        raise SsrfValidationError(bound_violation)
    if sanitized is None:
        raise ProxyRequestError("outbound request failed at destination")
    return sanitized


def _validated_request_headers(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, dict):
        raise SsrfValidationError("request headers must be a mapping")
    validated: dict[str, str] = {}
    for name, value in headers.items():
        key = str(name).strip()
        _reject_forbidden_header_name(key)
        text = str(value)
        if _SSRF_FORBIDDEN_HEADER_CHARS.search(key) or _SSRF_FORBIDDEN_HEADER_CHARS.search(text):
            raise SsrfValidationError("request header contains forbidden characters")
        validated[key] = text
    return validated


def _encode_request_body(body: Any, headers: dict[str, str]) -> bytes | None:
    if body is None:
        return None
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    if isinstance(body, (dict, list)):
        headers.setdefault("Content-Type", "application/json")
        return json.dumps(body, separators=(",", ":")).encode("utf-8")
    raise SsrfValidationError("request body type is not permitted")


def _declassify_response(result: dict[str, Any], secrets: tuple[str, ...]) -> None:
    """Scan the WHOLE returned object for EVERY sensitive string (D4).

    ``secrets`` covers each raw bundle member AND the exact auth material placed
    on the wire — a ``Basic`` connection sends ``base64(user:pass)``, which no
    raw member matches, so an adversarial destination could echo that blob and a
    caller could reverse it (Codex-found). Scanning the wire value closes that.
    NOTE: substring scanning is a best-effort declassification net, not a
    complete confidentiality boundary against a fully adversarial destination
    that transforms the secret before echoing it — the per-connection endpoint
    allowlist (a later slice) is the real boundary that keeps traffic to trusted
    origins.
    """
    for secret in secrets:
        if secret and _contains_secret(result, secret):
            raise ProxyRequestError(
                "outbound request failed: unsafe destination response"
            )


def _default_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    # ssl.create_default_context() enables TLS pre-master-secret key logging when
    # SSLKEYLOGFILE is in the environment. A reader of that file could decrypt
    # the outbound TLS stream and recover the injected Authorization header —
    # defeating credential-blindness. Force it off regardless of the ambient env
    # (Codex-found). The broker child ALSO drops SSLKEYLOGFILE from its env so a
    # later-created context cannot re-enable it.
    context.keylog_filename = None
    return context


class _SsrfHardenedHttpDriver:
    """Credential-blind general HTTP driver (design.md D3/D4/D5).

    Applies the auth scheme from the injected typed bundle, performs ONE
    SSRF-hardened https call, and declassifies the response against every bundle
    member before returning a sanitized ``{status, reason, headers, body}``. It
    never returns the request's own auth material and raises only secret-free
    errors (with ``from None`` so no exception ``__context__`` can carry a
    secret). The resolver/validator/socket/context seams default to the secure
    production implementations; tests inject controlled ones.
    """

    __slots__ = (
        "_allowed_ports",
        "_max_body_bytes",
        "_max_header_bytes",
        "_max_header_count",
        "_max_total_seconds",
        "_open_socket",
        "_resolver",
        "_ssl_context",
        "_timeout",
        "_validator",
    )

    def __init__(
        self,
        *,
        resolver: Callable[[str, int], list[str]] | None = None,
        validator: Callable[[str], str] | None = None,
        open_socket: Callable[..., socket.socket] | None = None,
        ssl_context: Any = None,
        allowed_ports: frozenset[int] = _SSRF_DEFAULT_PORTS,
        timeout: float = _SSRF_TIMEOUT_SECONDS,
        max_total_seconds: float = _SSRF_MAX_TOTAL_SECONDS,
        max_body_bytes: int = _SSRF_MAX_BODY_BYTES,
        max_header_count: int = _SSRF_MAX_HEADER_COUNT,
        max_header_bytes: int = _SSRF_MAX_HEADER_BYTES,
        dns_timeout: float = _SSRF_DNS_TIMEOUT_SECONDS,
    ) -> None:
        # An injected resolver is used verbatim (tests drive controlled ones);
        # the production default wraps getaddrinfo in the threaded deadline so a
        # hanging resolver is abandoned instead of escaping the budget.
        self._resolver = resolver or _make_default_resolver(dns_timeout)
        self._validator = validator or _classify_global_address
        self._open_socket = open_socket or _default_open_socket
        self._ssl_context = ssl_context if ssl_context is not None else _default_ssl_context()
        self._allowed_ports = frozenset(allowed_ports)
        self._timeout = float(timeout)
        self._max_total_seconds = float(max_total_seconds)
        self._max_body_bytes = int(max_body_bytes)
        self._max_header_count = int(max_header_count)
        self._max_header_bytes = int(max_header_bytes)

    def __call__(
        self,
        *,
        bundle: ConnectionSecretBundle,
        auth_scheme: str,
        method: str,
        url: str,
        headers: Any = None,
        body: Any = None,
        header_name: str = "",
        allowed_endpoints: tuple[OutboundEndpoint, ...] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(bundle, ConnectionSecretBundle):
            raise SsrfValidationError("a typed connection secret bundle is required")
        verb = (method or "").strip().upper()
        if verb not in _SSRF_ALLOWED_METHODS:
            raise SsrfValidationError("outbound method is not permitted")
        canonical = _parse_canonical_https_url(url, allowed_ports=self._allowed_ports)
        # The per-connection endpoint allowlist is the real egress boundary
        # (design.md D3). When supplied, the concrete host/method/path must match
        # a declared endpoint BEFORE any resolution/socket. ``None`` means the
        # caller is exercising the raw transport (the driver's own adversarial
        # tests); every production call through _TrustedNetworkDriver passes a
        # non-empty allowlist, and an empty one refuses.
        if allowed_endpoints is not None:
            _enforce_endpoint_allowlist(canonical, verb, allowed_endpoints)
        request_headers = _validated_request_headers(headers)
        # oauth1a signs over the method + the exact request URL, so pass the
        # reconstructed URL (identical to the one _execute_pinned_https_request
        # sends). Other schemes ignore method/url.
        auth_headers = _ssrf_auth_headers(
            auth_scheme,
            bundle,
            header_name=header_name,
            method=verb,
            url=_canonical_request_url(canonical),
        )
        request_headers.update(auth_headers)
        # Everything to scrub from the response: raw bundle members AND the exact
        # auth values placed on the wire (e.g. the base64 blob of a Basic
        # credential, which matches no raw member).
        sensitive = list(bundle.secret_values())
        for header_value in auth_headers.values():
            sensitive.append(header_value)
            scheme_split = header_value.split(" ", 1)
            if len(scheme_split) == 2:
                sensitive.append(scheme_split[1])
        encoded_body = _encode_request_body(body, request_headers)
        if canonical.is_ip_literal:
            pinned = self._validator(canonical.hostname)
        else:
            pinned = _resolve_pinned_addresses(
                canonical.hostname,
                canonical.port,
                resolver=self._resolver,
                validator=self._validator,
            )[0]
        result = _execute_pinned_https_request(
            method=verb,
            canonical=canonical,
            pinned_address=pinned,
            headers=request_headers,
            body=encoded_body,
            ssl_context=self._ssl_context,
            open_socket=self._open_socket,
            timeout=self._timeout,
            max_total_seconds=self._max_total_seconds,
            max_body_bytes=self._max_body_bytes,
            max_header_count=self._max_header_count,
            max_header_bytes=self._max_header_bytes,
        )
        _declassify_response(result, tuple(sensitive))
        return result


_OAUTH1A_BUNDLE_KEYS = frozenset(
    {"api_key", "api_secret", "access_token", "access_token_secret"}
)


def _looks_like_oauth1a_bundle(credential: str) -> bool:
    """True iff ``credential`` is the deposited oauth1a encoding: a JSON object
    carrying the four OAuth 1.0a keys. Used to refuse re-interpreting that bundle
    under any OTHER scheme (the row-mutation leak). Never logs or returns values."""
    text = (credential or "").lstrip()
    if not text.startswith("{"):
        return False
    try:
        values = json.loads(text)
    except (TypeError, ValueError):
        return False
    return isinstance(values, dict) and _OAUTH1A_BUNDLE_KEYS.issubset(values.keys())


def _build_http_secret_bundle(auth_scheme: str, credential: str) -> ConnectionSecretBundle:
    """Build the typed bundle for an ``http`` connection INSIDE the child (D2/D5).

    The broker resolves ONE opaque credential string from the vault; this maps it
    to the named bundle shape the auth scheme needs. ``basic`` stores the pair as
    ``username:password`` and is split on the FIRST colon (a password may itself
    contain colons). ``bearer``/``header`` carry a single token. ``oauth1a``
    (Twitter) needs FOUR named values, so its single vault string is a JSON object
    ``{api_key, api_secret, access_token, access_token_secret}`` parsed here — see
    the SHAPE FINDING in the migration notes: a first-class multi-named-secret
    vault resolver (task 1.3) is the cleaner home for this than a JSON-in-one-slot
    encoding. The bundle never crosses the process boundary and is scrubbed from
    the response.
    """
    scheme = (auth_scheme or "none").strip().lower()
    # SCHEME <-> ENCODING BINDING (Codex ADAPT, PR #2525). The vault stores ONE
    # opaque string whose ENCODING is fixed by the scheme it was deposited under
    # (oauth1a = JSON object of the four OAuth values). This builder is the single
    # choke point every dispatch passes through, and it is handed the row's
    # CURRENT scheme — so a connection row mutated from oauth1a to bearer would
    # otherwise re-interpret the whole four-value bundle as a single token and
    # emit it verbatim as `Authorization: Bearer {json…}` to an allowlisted
    # endpoint, leaking all four secrets. Refuse, fail closed, any credential
    # whose encoding is recognisably that of a DIFFERENT scheme before a header
    # is ever built. (A mismatch can only arise from row mutation or a corrupted
    # deposit — never from a legitimate connect_http, which validates shape at
    # the door with the same rules.)
    if scheme != "oauth1a" and _looks_like_oauth1a_bundle(credential):
        raise SsrfValidationError(
            "credential encoding does not match the connection's auth scheme"
        )
    if scheme in ("bearer", "header"):
        return ConnectionSecretBundle(token=credential)
    if scheme == "basic":
        if ":" not in credential:
            raise SsrfValidationError("basic credential must be username:password")
        username, password = credential.split(":", 1)
        if not username or not password:
            raise SsrfValidationError("basic credential must be username:password")
        return ConnectionSecretBundle(username=username, password=password)
    if scheme == "oauth1a":
        try:
            values = json.loads(credential)
        except (TypeError, ValueError):
            raise SsrfValidationError(
                "oauth1a credential must be a JSON object of the four OAuth values"
            ) from None
        if not isinstance(values, dict):
            raise SsrfValidationError("oauth1a credential must be a JSON object")
        required = ("api_key", "api_secret", "access_token", "access_token_secret")
        if any(not isinstance(values.get(name), str) or not values.get(name) for name in required):
            raise SsrfValidationError("oauth1a credential is missing a required value")
        return ConnectionSecretBundle(**{name: values[name] for name in required})
    if scheme == "none":
        return ConnectionSecretBundle()
    raise SsrfValidationError("auth scheme is not supported")


class _TrustedNetworkDriver:
    """Select the fixture or general http transport inside the broker child.

    Routing is EXPLICIT and fails closed (Codex FIX 1). ``connection_type=="http"``
    → the general credential-blind SSRF-hardened driver (the single
    channel-agnostic egress, behind the ``allow_http_connections`` deployment
    flag); the EMPTY legacy type routes ONLY to the gated test fixture; ANY other
    (unknown/unsupported) type is REFUSED. There is no per-channel (github/slack/…)
    transport — channels are user-built graph nodes over the generic http
    connection, never platform code.
    """

    __slots__ = ("_allow_http", "_fixture", "_http")

    def __init__(self, config: dict[str, Any], runtime_root: Path) -> None:
        self._fixture = _TestFixtureNetworkDriver(
            runtime_root,
            allow_test_fixtures=bool(config["allow_test_fixtures"]),
        )
        self._allow_http = bool(config.get("allow_http_connections", False))
        self._http = _SsrfHardenedHttpDriver()

    def __call__(self, **kwargs: Any) -> Any:
        # Pop the descriptor fields so the fixture driver keeps its exact fixed
        # signature — only the http path consumes them.
        connection_type = str(kwargs.pop("connection_type", "") or "").strip().lower()
        auth_scheme = str(kwargs.pop("auth_scheme", "") or "")
        allowed_endpoints = kwargs.pop("allowed_endpoints", ()) or ()
        if connection_type == "http":
            return self._dispatch_http(
                auth_scheme=auth_scheme,
                allowed_endpoints=tuple(allowed_endpoints),
                credential=kwargs.get("credential", ""),
                verb=str(kwargs.get("verb", "")),
                request=kwargs.get("request"),
            )
        if connection_type == "":
            # Legacy untyped connections route ONLY to the gated test fixture —
            # never to any real network destination.
            provider = str(kwargs.get("provider", ""))
            if provider.startswith("test-fixture."):
                return self._fixture(**kwargs)
            raise ProxyRequestError("outbound provider has no trusted transport")
        # Unknown / unsupported connection_type: FAIL CLOSED.
        raise ProxyRequestError("outbound connection type is not supported")

    def _dispatch_http(
        self,
        *,
        auth_scheme: str,
        allowed_endpoints: tuple[OutboundEndpoint, ...],
        credential: str,
        verb: str,
        request: object,
    ) -> Any:
        if not self._allow_http:
            # Fail closed until a deployment enables the general http path.
            raise ProxyRequestError("outbound http connections are not enabled")
        if not allowed_endpoints:
            # No allowlist ⇒ no reachable destination (the real egress boundary).
            raise SsrfValidationError("connection has no permitted endpoints")
        if not isinstance(request, dict):
            raise SsrfValidationError("outbound http request shape is not permitted")
        bundle = _build_http_secret_bundle(auth_scheme, credential)
        return self._http(
            bundle=bundle,
            auth_scheme=auth_scheme,
            method=str(verb),
            url=request.get("url"),
            headers=request.get("headers"),
            body=request.get("body"),
            header_name=str(request.get("header_name", "") or ""),
            allowed_endpoints=allowed_endpoints,
        )


class _JsonlAuditWriter:
    __slots__ = ("_path",)

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def __call__(self, record: dict[str, object]) -> None:
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")


def _build_credential_broker_dispatch(
    config: dict[str, Any],
) -> Callable[[str, str, object], Any]:
    runtime_root = Path(config["runtime_root"])
    runtime_root.mkdir(parents=True, exist_ok=True)
    broker = CredentialBlindBroker(
        ConnectionLedger(config["ledger_db_path"]),
        resolve_credential=_TrustedCredentialResolver(config),
        network_request=_TrustedNetworkDriver(config, runtime_root),
        audit=_JsonlAuditWriter(str(runtime_root / "audit.jsonl")),
    )
    return broker.dispatch


_TRUSTED_DISPATCH_FACTORIES = {
    "credential_broker_v1": _build_credential_broker_dispatch,
}


def _contains_secret(value: object, secret: str) -> bool:
    if isinstance(value, str):
        return secret in value
    if isinstance(value, bytes):
        return secret.encode("utf-8") in value
    if isinstance(value, dict):
        return any(
            _contains_secret(key, secret) or _contains_secret(item, secret)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_secret(item, secret) for item in value)
    return False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbound_connections (
    connection_id   TEXT PRIMARY KEY,
    owner_user_id   TEXT NOT NULL,
    connection_class TEXT NOT NULL,
    scopes_json     TEXT NOT NULL,
    provider        TEXT NOT NULL,
    destination     TEXT NOT NULL,
    credential_ref  TEXT NOT NULL,
    revoked_at      REAL,
    connection_type TEXT NOT NULL DEFAULT '',
    auth_scheme     TEXT NOT NULL DEFAULT '',
    allowed_endpoints_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS outbound_connection_grants (
    grant_id        TEXT PRIMARY KEY,
    connection_id   TEXT NOT NULL REFERENCES outbound_connections(connection_id),
    owner_user_id   TEXT NOT NULL,
    universe_id     TEXT NOT NULL,
    granted_at      REAL NOT NULL,
    revoked_at      REAL,
    unprompted_action_cap_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbound_grant_resolution
    ON outbound_connection_grants(owner_user_id, universe_id, revoked_at);

CREATE TABLE IF NOT EXISTS outbound_connector_artifacts (
    artifact_id              TEXT PRIMARY KEY,
    owner_user_id            TEXT NOT NULL,
    connector_definition_json TEXT NOT NULL,
    mcp_client_config_json   TEXT NOT NULL,
    created_at               REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS outbound_connector_artifact_edges (
    parent_artifact_id TEXT NOT NULL
        REFERENCES outbound_connector_artifacts(artifact_id),
    child_artifact_id  TEXT NOT NULL UNIQUE
        REFERENCES outbound_connector_artifacts(artifact_id),
    remixed_by_user_id TEXT NOT NULL,
    created_at         REAL NOT NULL,
    PRIMARY KEY (parent_artifact_id, child_artifact_id),
    CHECK (parent_artifact_id <> child_artifact_id)
);
"""


def _required(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized


def _resource_from_row(row: sqlite3.Row) -> ConnectionResource:
    """Build a ``ConnectionResource`` from an ``outbound_connections`` row.

    The descriptor columns are read through ``.keys()`` guards so a row selected
    before the ALTER-migration ran (should not happen — every ledger __init__
    backfills them — but defensive) reads back as a legacy connection.
    """
    columns = set(row.keys())
    endpoints_raw = row["allowed_endpoints_json"] if "allowed_endpoints_json" in columns else "[]"
    return ConnectionResource(
        connection_id=row["connection_id"],
        owner_user_id=row["owner_user_id"],
        connection_class=row["connection_class"],
        scopes=tuple(json.loads(row["scopes_json"])),
        provider=row["provider"],
        destination=row["destination"],
        credential_ref=row["credential_ref"],
        revoked_at=row["revoked_at"],
        connection_type=(row["connection_type"] if "connection_type" in columns else "") or "",
        auth_scheme=(row["auth_scheme"] if "auth_scheme" in columns else "") or "",
        allowed_endpoints=_parse_allowed_endpoints(endpoints_raw),
    )


def _json_object(name: str, value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    _reject_secret_material(value)
    return json.loads(json.dumps(value, sort_keys=True))


def _reject_secret_material(value: object) -> None:
    secret_keys = {
        "api_key",
        "authorization",
        "credential",
        "password",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in secret_keys:
                raise ValueError("connector artifacts cannot contain credential material")
            _reject_secret_material(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_secret_material(item)


class ConnectionLedger:
    """SQLite ledger for user-owned connections and universe grants."""

    def __init__(
        self,
        db_path: str | Path,
        *,
        allow_test_fixtures: bool = False,
        verify_authenticated_principal: AuthenticatedPrincipalVerifier | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._allow_test_fixtures = allow_test_fixtures
        self._verify_authenticated_principal = verify_authenticated_principal
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            grant_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(outbound_connection_grants)"
                )
            }
            if "unprompted_action_cap_json" not in grant_columns:
                connection.execute(
                    "ALTER TABLE outbound_connection_grants "
                    "ADD COLUMN unprompted_action_cap_json TEXT"
                )
            # Backfill the channel descriptor columns onto pre-descriptor DBs.
            # Legacy rows read back as connection_type='' (routes to the existing
            # github/slack drivers) with an empty allowlist.
            connection_columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(outbound_connections)"
                )
            }
            for column, ddl in (
                ("connection_type", "TEXT NOT NULL DEFAULT ''"),
                ("auth_scheme", "TEXT NOT NULL DEFAULT ''"),
                ("allowed_endpoints_json", "TEXT NOT NULL DEFAULT '[]'"),
            ):
                if column not in connection_columns:
                    connection.execute(
                        f"ALTER TABLE outbound_connections ADD COLUMN {column} {ddl}"
                    )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def require_authenticated_principal_id(self) -> str:
        """Resolve the request principal through a trusted daemon verifier.

        The verifier is a required call-site capability for authority-bearing
        operations. It must be installed by the authenticated request boundary,
        must derive the current principal from server-owned context, and must
        never be constructed from universe/action payload fields.
        """
        verifier = self._verify_authenticated_principal
        if verifier is None:
            raise PermissionError(
                "authenticated principal verifier is required"
            )
        try:
            principal_id = verifier()
        except Exception:
            raise PermissionError(
                "authenticated principal verification failed"
            ) from None
        if not isinstance(principal_id, str):
            raise PermissionError("authenticated principal is required")
        principal_id = principal_id.strip()
        if not principal_id or principal_id == "anonymous":
            raise PermissionError("authenticated principal is required")
        return principal_id

    def create_connection(
        self,
        *,
        connection_id: str,
        owner_user_id: str,
        connection_class: str,
        scopes: tuple[str, ...],
        provider: str,
        destination: str,
        credential_ref: str,
        connection_type: str = "",
        auth_scheme: str = "",
        allowed_endpoints: Any = (),
    ) -> ConnectionView:
        endpoints = _parse_allowed_endpoints(allowed_endpoints)
        normalized_type = (connection_type or "").strip().lower()
        normalized_scheme = (auth_scheme or "").strip().lower()
        if normalized_type not in _KNOWN_CONNECTION_TYPES:
            # Reject unknown types at creation so a bogus type can never be stored
            # and later fall through to a hardcoded-destination driver (FIX 1).
            raise SsrfValidationError("connection_type is not supported")
        # The credential SCHEME must match the connection type — the SAME rule
        # dispatch re-checks against the current row (Codex FIX 1 + TOCTOU).
        _validate_connection_credential_scheme(normalized_type, credential_ref)
        if normalized_type == "http":
            # A general http connection is only safe with a declared allowlist
            # and a supported auth scheme (the bundle builder enforces the
            # per-scheme credential FORMAT later, inside the child).
            if not endpoints:
                raise SsrfValidationError(
                    "an http connection requires at least one allowed endpoint"
                )
            if normalized_scheme not in _SUPPORTED_HTTP_AUTH_SCHEMES:
                raise SsrfValidationError("auth scheme is not supported")
        # A git scope binds one repository on one host, so it may only ride on a
        # connection provably pointed at github.com. Checked HERE, at the storage
        # boundary: every issuer assembles its own scope tuple, and a rule that
        # lives in one of them is a rule the next one forgets.
        validate_git_scopes(
            scopes,
            hosts=[endpoint.host for endpoint in endpoints],
            provider=provider,
        )
        resource = ConnectionResource(
            connection_id=_required("connection_id", connection_id),
            owner_user_id=_required("owner_user_id", owner_user_id),
            connection_class=_required("connection_class", connection_class),
            scopes=tuple(_required("scope", scope) for scope in scopes),
            provider=_required("provider", provider),
            destination=_required("destination", destination),
            credential_ref=_required("credential_ref", credential_ref),
            revoked_at=None,
            connection_type=normalized_type,
            auth_scheme=normalized_scheme,
            allowed_endpoints=endpoints,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_connections (
                    connection_id, owner_user_id, connection_class, scopes_json,
                    provider, destination, credential_ref, revoked_at,
                    connection_type, auth_scheme, allowed_endpoints_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    resource.connection_id,
                    resource.owner_user_id,
                    resource.connection_class,
                    json.dumps(resource.scopes),
                    resource.provider,
                    resource.destination,
                    resource.credential_ref,
                    resource.connection_type,
                    resource.auth_scheme,
                    json.dumps([ep.as_dict() for ep in resource.allowed_endpoints]),
                ),
            )
        # Return the REDACTED view — no caller (not even the creator) gets
        # credential_ref back from the default read/create API (Codex FIX 3).
        return resource.to_view()

    def _upgrade_http_connection_scopes(
        self, *, connection_id: str, scopes: tuple[str, ...]
    ) -> None:
        """Bounded, one-directional migration of the legacy ("http",) scope token.

        connect_http originally stored an http connection's scope as the literal
        ("http",) type token, which the authenticated_external_call effector could
        never match against the packet HTTP verb (#2521). This rewrites such a row's
        scope to the concrete method-union. It is deliberately GUARDED by
        ``scopes_json = '["http"]'`` in the WHERE clause: it can ONLY ever replace
        the exact legacy token, so it can never silently widen, narrow, or alter a
        real method-scoped set — a row already carrying method scopes is untouched.
        """
        new_scopes = tuple(_required("scope", scope) for scope in scopes)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE outbound_connections
                SET scopes_json = ?
                WHERE connection_id = ? AND scopes_json = ?
                """,
                (json.dumps(list(new_scopes)), connection_id, json.dumps(["http"])),
            )

    def extend_http_connection_endpoints(
        self,
        *,
        connection_id: str,
        endpoints: Any,
        scopes: tuple[str, ...],
        expected_endpoints_json: str,
        expected_scopes_json: str,
    ) -> bool:
        """ADD endpoints to an existing http connection. Never remove or replace.

        A credential is deposited once and extended as the work needs it — the
        alternative was a fresh connection (and a fresh paste) per endpoint,
        because a deterministic id plus any policy difference read as a hard
        conflict.

        Two things keep this from being a widening primitive:

        * **Additive only.** The caller has already checked the new set is a
          superset; this re-checks nothing about intent but writes the union, so
          an endpoint another graph depends on cannot vanish here. Narrowing and
          removal stay unsupported (they are a different, destructive intent).
        * **CAS-guarded on BOTH columns it writes, always.** The UPDATE matches
          on the exact endpoint JSON AND the exact scopes JSON the caller read
          (both from one :meth:`policy_json` snapshot). Guarding endpoints alone
          let two scope-only widenings race: the first wrote scope B without
          touching the endpoints, so the second's CAS still matched and
          replaced B with A; an optional scopes guard let a caller skip it
          (Codex rounds 1-2 on the 2026-09-02 rail change).

        Returns True when the row was updated.
        """
        parsed = _parse_allowed_endpoints(endpoints)
        if not parsed:
            raise SsrfValidationError(
                "an http connection requires at least one allowed endpoint"
            )
        new_scopes = tuple(_required("scope", scope) for scope in scopes)
        validate_git_scopes(new_scopes, hosts=[endpoint.host for endpoint in parsed])
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbound_connections
                SET allowed_endpoints_json = ?, scopes_json = ?
                WHERE connection_id = ? AND allowed_endpoints_json = ?
                  AND scopes_json = ?
                """,
                (
                    json.dumps([ep.as_dict() for ep in parsed]),
                    json.dumps(list(new_scopes)),
                    connection_id,
                    expected_endpoints_json,
                    expected_scopes_json,
                ),
            )
            return cursor.rowcount > 0

    def policy_json(self, connection_id: str) -> tuple[str, str] | None:
        """The stored ``(allowed_endpoints_json, scopes_json)`` exactly as
        written, for a CAS-guarded extension to compare against. Reserialising
        the parsed policy happens to round-trip today; comparing the raw text
        cannot silently stop doing so."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT allowed_endpoints_json, scopes_json FROM outbound_connections "
                "WHERE connection_id = ?",
                (connection_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["allowed_endpoints_json"]), str(row["scopes_json"])

    def _get_connection_resource(
        self, connection_id: str
    ) -> ConnectionResource | None:
        """Credential-BEARING read for TRUSTED internal use only.

        Returns the full ``ConnectionResource`` including ``credential_ref``. The
        public ``get_connection`` returns a redacted :class:`ConnectionView`
        instead (Codex FIX 3); this method is the explicit, named seam the broker
        child and the internal ownership/conflict checks use when they must see
        the credential reference. Never expose its result to an adapter/graph/CRUD
        surface.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_connections WHERE connection_id = ?",
                (connection_id,),
            ).fetchone()
        if row is None:
            return None
        return _resource_from_row(row)

    def get_connection(self, connection_id: str) -> ConnectionView | None:
        """Redacted connection read — the default public projection (Codex FIX 3).

        Returns a :class:`ConnectionView` with NO ``credential_ref`` field — the
        redaction is structural, not a repr convention: the returned object has no
        attribute, ``vars()``, or ``asdict()`` key for the credential reference.
        Trusted internal code that needs the reference uses
        ``_get_connection_resource``.
        """
        resource = self._get_connection_resource(connection_id)
        return resource.to_view() if resource is not None else None

    def get_connection_view(self, connection_id: str) -> ConnectionView | None:
        """Explicit redacted-view accessor (same result as ``get_connection``)."""
        return self.get_connection(connection_id)

    def list_connection_views(
        self,
        *,
        owner_user_id: str,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[ConnectionView]:
        """List one owner's connections as redacted views (no credential_ref)."""
        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM outbound_connections
                 WHERE owner_user_id = ?
                   AND (? = 0 OR revoked_at IS NULL)
                 ORDER BY connection_id LIMIT ?
                """,
                (_required("owner_user_id", owner_user_id), int(active_only), limit),
            ).fetchall()
        return [_resource_from_row(row).to_view() for row in rows]

    def grant_connection(
        self,
        *,
        grant_id: str,
        connection_id: str,
        owner_user_id: str,
        universe_id: str,
        granted_at: float | None = None,
        unprompted_action_cap: ActionCap | None = None,
    ) -> ConnectionGrant:
        resource = self._get_connection_resource(connection_id)
        if resource is None:
            raise LookupError("connection resource does not exist")
        owner = _required("owner_user_id", owner_user_id)
        if resource.owner_user_id != owner:
            raise PermissionError("grant owner does not own connection resource")
        grant = ConnectionGrant(
            grant_id=_required("grant_id", grant_id),
            connection_id=resource.connection_id,
            owner_user_id=owner,
            universe_id=_required("universe_id", universe_id),
            granted_at=time.time() if granted_at is None else granted_at,
            revoked_at=None,
            unprompted_action_cap=unprompted_action_cap,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_connection_grants (
                    grant_id, connection_id, owner_user_id, universe_id,
                    granted_at, revoked_at, unprompted_action_cap_json
                ) VALUES (?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    grant.grant_id,
                    grant.connection_id,
                    grant.owner_user_id,
                    grant.universe_id,
                    grant.granted_at,
                    (
                        json.dumps(
                            grant.unprompted_action_cap.as_dict(),
                            sort_keys=True,
                        )
                        if grant.unprompted_action_cap is not None
                        else None
                    ),
                ),
            )
        return grant

    def get_grant(self, grant_id: str) -> ConnectionGrant | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_connection_grants WHERE grant_id = ?",
                (grant_id,),
            ).fetchone()
        if row is None:
            return None
        cap_payload = row["unprompted_action_cap_json"]
        cap = ActionCap(**json.loads(cap_payload)) if cap_payload else None
        return ConnectionGrant(
            grant_id=row["grant_id"],
            connection_id=row["connection_id"],
            owner_user_id=row["owner_user_id"],
            universe_id=row["universe_id"],
            granted_at=row["granted_at"],
            revoked_at=row["revoked_at"],
            unprompted_action_cap=cap,
        )

    def list_grants(
        self,
        *,
        owner_user_id: str,
        universe_id: str,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[ConnectionGrant]:
        """List grants for one exact owner/universe without connection secrets."""

        if limit < 1:
            raise ValueError("limit must be positive")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM outbound_connection_grants
                WHERE owner_user_id = ? AND universe_id = ?
                  AND (? = 0 OR revoked_at IS NULL)
                ORDER BY grant_id LIMIT ?
                """,
                (owner_user_id, universe_id, int(active_only), limit),
            ).fetchall()
        result: list[ConnectionGrant] = []
        for row in rows:
            cap_payload = row["unprompted_action_cap_json"]
            result.append(
                ConnectionGrant(
                    grant_id=row["grant_id"],
                    connection_id=row["connection_id"],
                    owner_user_id=row["owner_user_id"],
                    universe_id=row["universe_id"],
                    granted_at=row["granted_at"],
                    revoked_at=row["revoked_at"],
                    unprompted_action_cap=(
                        ActionCap(**json.loads(cap_payload)) if cap_payload else None
                    ),
                )
            )
        return result

    def revoke_grant(self, grant_id: str, *, revoked_at: float | None = None) -> bool:
        timestamp = time.time() if revoked_at is None else revoked_at
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbound_connection_grants
                   SET revoked_at = ?
                 WHERE grant_id = ?
                """,
                (timestamp, grant_id),
            )
        return cursor.rowcount > 0

    def revoke_connection(
        self,
        connection_id: str,
        *,
        revoked_at: float | None = None,
    ) -> bool:
        """Revoke a connection resource and thereby invalidate all of its grants."""
        timestamp = time.time() if revoked_at is None else revoked_at
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE outbound_connections
                   SET revoked_at = ?
                 WHERE connection_id = ?
                """,
                (timestamp, connection_id),
            )
        return cursor.rowcount > 0

    def delete_connection(self, connection_id: str) -> bool:
        """HARD-delete a connection and every grant on it. Returns True if a
        row went away.

        Not a revoke. ``revoke_connection`` stamps ``revoked_at``, and because
        a connection id is DETERMINISTIC on ``(universe_id, destination)``, a
        revoked row makes that destination unusable forever: every
        re-provision then trips the ``revoked_at is not None`` conflict, so a
        user who removes ``github`` could never deposit ``github`` again. That
        is documented in
        ``docs/concerns/2026-08-27-no-reachable-remove-for-http-connections.md``
        and it is why removal deletes rather than flags.

        Grants go first so no window exists where a grant outlives the
        connection it authorises. The caller is responsible for the VAULT
        record; this owns only the ledger rows.
        """
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM outbound_connection_grants WHERE connection_id = ?",
                (connection_id,),
            )
            cursor = connection.execute(
                "DELETE FROM outbound_connections WHERE connection_id = ?",
                (connection_id,),
            )
        return cursor.rowcount > 0

    def resolve_scoped_proxy(
        self,
        *,
        universe_id: str,
        connection_class: str,
    ) -> ScopedConnectionProxy:
        """Resolve exactly one current grant; absent/revoked/ambiguous fail closed."""
        owner_user_id = self.require_authenticated_principal_id()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT g.grant_id, g.revoked_at AS grant_revoked_at,
                       c.owner_user_id,
                       c.provider, c.destination, c.scopes_json,
                       c.connection_type,
                       c.revoked_at AS connection_revoked_at
                  FROM outbound_connection_grants AS g
                  JOIN outbound_connections AS c
                    ON c.connection_id = g.connection_id
                 WHERE g.owner_user_id = ?
                   AND g.universe_id = ?
                   AND c.owner_user_id = ?
                   AND c.connection_class = ?
                """,
                (
                    _required("owner_user_id", owner_user_id),
                    _required("universe_id", universe_id),
                    _required("owner_user_id", owner_user_id),
                    _required("connection_class", connection_class),
                ),
            ).fetchall()
        if not rows:
            raise GrantResolutionError("absent outbound connection grant")
        active = [
            row
            for row in rows
            if row["grant_revoked_at"] is None
            and row["connection_revoked_at"] is None
        ]
        if not active:
            raise GrantResolutionError("revoked outbound connection grant")
        if len(active) != 1:
            raise GrantResolutionError("ambiguous outbound connection grants")
        row = active[0]
        columns = set(row.keys())
        return self._start_scoped_proxy(
            grant_id=row["grant_id"],
            universe_id=universe_id,
            provider=row["provider"],
            destination=row["destination"],
            scopes=tuple(json.loads(row["scopes_json"])),
            owner_user_id=row["owner_user_id"],
            connection_type=(
                (row["connection_type"] if "connection_type" in columns else "") or ""
            ),
        )

    def resolve_exact_scoped_proxy(
        self,
        *,
        universe_id: str,
        grant_id: str,
        connection_id: str,
    ) -> ScopedConnectionProxy:
        """Resolve one named current grant and connection for the principal."""
        owner_user_id = self.require_authenticated_principal_id()
        grant = self.require_active_grant(_required("grant_id", grant_id))
        resource = self._get_connection_resource(_required("connection_id", connection_id))
        if resource is None:
            raise GrantResolutionError("absent outbound connection resource")
        exact = (
            grant.connection_id == resource.connection_id,
            grant.owner_user_id == owner_user_id,
            grant.universe_id == _required("universe_id", universe_id),
            resource.owner_user_id == owner_user_id,
            resource.revoked_at is None,
        )
        if not all(exact):
            raise GrantResolutionError("outbound connection grant identity mismatch")
        return self._start_scoped_proxy(
            grant_id=grant.grant_id,
            universe_id=grant.universe_id,
            provider=resource.provider,
            destination=resource.destination,
            scopes=resource.scopes,
            owner_user_id=resource.owner_user_id,
            connection_type=resource.connection_type,
        )

    def _start_scoped_proxy(
        self,
        *,
        grant_id: str,
        universe_id: str,
        provider: str,
        destination: str,
        scopes: tuple[str, ...],
        owner_user_id: str,
        connection_type: str = "",
    ) -> ScopedConnectionProxy:
        factory_reference = "credential_broker_v1"
        grant_runtime_id = hashlib.sha256(
            grant_id.encode("utf-8")
        ).hexdigest()
        factory_config = {
            "allow_test_fixtures": self._allow_test_fixtures,
            "allow_http_connections": _outbound_http_enabled(),
            "ledger_db_path": str(self._db_path.resolve()),
            "universe_dir": str((self._db_path.parent / universe_id).resolve()),
            "provider": provider,
            "destination": destination,
            "connection_type": (connection_type or "").strip().lower(),
            "owner_user_id": owner_user_id,
            "runtime_root": str(
                (
                    self._db_path.parent
                    / ".outbound-proxy"
                    / grant_runtime_id
                ).resolve()
            ),
        }
        # Resolve the budget BEFORE spawning: a validation failure here must not
        # leak an already-started child (Codex FIX C).
        timeout = _proxy_startup_timeout_seconds()
        context = multiprocessing.get_context("spawn")
        client_channel, server_channel = context.Pipe(duplex=True)
        worker = context.Process(
            target=_run_proxy_worker,
            args=(
                server_channel,
                factory_reference,
                factory_config,
                grant_id,
                scopes,
            ),
            daemon=True,
            name=f"outbound-proxy-{grant_id}",
        )
        try:
            worker.start()
        except Exception as exc:
            # A spawn that never starts used to bypass the diagnostic contract
            # entirely, surfacing as an unrelated error type (Codex FIX D).
            client_channel.close()
            server_channel.close()
            raise ProxyRequestError(
                f"outbound proxy could not be spawned: {type(exc).__name__}"
            ) from exc
        server_channel.close()

        def _abandon() -> int | None:
            """Tear the child down, reporting how it died if it died on its own.

            Reads ``exitcode`` BEFORE terminating: our own SIGTERM sets ``-15``,
            so terminating first would overwrite the child's real exit status and
            report every timeout as a process death (Codex FIX D).
            """
            # Read liveness BEFORE touching the channel. Closing our end breaks
            # the child's pipe, and a healthy-but-slow child then dies on the
            # broken pipe while trying to send "ready" — so an exitcode sampled
            # after the close can be a death the PARENT caused, which is the very
            # misattribution this helper exists to prevent.
            own_exit = worker.exitcode
            if own_exit is None and not worker.is_alive():
                # Already exited, just not reaped yet; is_alive() reaps it, so
                # the EOF path recovers the real code instead of losing it.
                own_exit = worker.exitcode
            client_channel.close()
            if own_exit is None:
                worker.terminate()
                worker.join(timeout=1.0)
            return own_exit

        _describe = _describe_child_exit

        if not client_channel.poll(timeout):
            exitcode = _abandon()
            if exitcode is None:
                raise ProxyRequestError(
                    "outbound proxy did not finish starting within "
                    f"{timeout:g}s"
                )
            raise ProxyRequestError(
                f"outbound proxy exited during startup{_describe(exitcode)}"
            )
        try:
            ready = _receive_message(client_channel)
        except ProxyRequestError:
            # On Linux a child that dies CLOSES the pipe, so poll() reports
            # readable and the read hits EOF. That is a child death, not a
            # malformed frame, and it was reaching the caller as an unrelated
            # generic message — the most likely production shape (Codex FIX D).
            exitcode = _abandon()
            raise ProxyRequestError(
                f"outbound proxy exited during startup{_describe(exitcode)}"
            ) from None
        if isinstance(ready, dict) and ready.get("op") == "startup_failed":
            cause = ready.get("cause")
            _abandon()
            detail = f": {cause}" if isinstance(cause, str) and cause else ""
            # The cause is the child's exception CLASS only; its full traceback is
            # on the daemon's stderr. Redacted by construction, still diagnostic.
            raise ProxyRequestError(
                f"outbound proxy failed to start{detail}"
            )
        if ready != {"op": "ready"}:
            _abandon()
            raise ProxyRequestError(
                "outbound proxy sent an unrecognized startup message"
            )
        return ScopedConnectionProxy(
            grant_id=grant_id,
            provider=provider,
            destination=destination,
            scopes=scopes,
            _channel=_ProxyChannel(client_channel, worker),
        )

    def _active_resource_for_grant(
        self, grant_id: str
    ) -> ConnectionResource | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT c.*
                  FROM outbound_connection_grants AS g
                  JOIN outbound_connections AS c
                    ON c.connection_id = g.connection_id
                 WHERE g.grant_id = ?
                   AND g.revoked_at IS NULL
                   AND c.revoked_at IS NULL
                   AND g.owner_user_id = c.owner_user_id
                """,
                (grant_id,),
            ).fetchone()
        if row is None:
            return None
        return _resource_from_row(row)

    def require_active_grant(self, grant_id: str) -> ConnectionGrant:
        """Return a grant only while both it and its connection are current."""
        grant = self.get_grant(grant_id)
        if grant is None:
            raise GrantResolutionError("absent outbound connection grant")
        if grant.revoked_at is not None:
            raise GrantResolutionError("revoked outbound connection grant")
        if self._active_resource_for_grant(grant_id) is None:
            raise GrantResolutionError("revoked outbound connection resource")
        return grant

    def evaluate_unprompted_action_cap(
        self,
        *,
        grant_id: str,
        action_value: float,
        action_unit: str,
    ) -> CapDecision:
        """Evaluate only the unprompted-action axis; tool/spend gates are separate."""
        if not math.isfinite(action_value):
            raise ValueError("action_value must be finite")
        if action_value < 0:
            raise ValueError("action_value must be non-negative")
        normalized_unit = _required("action_unit", action_unit)
        grant = self.require_active_grant(grant_id)
        cap = grant.unprompted_action_cap
        if cap is not None and normalized_unit != cap.unit:
            raise ValueError(
                f"action_unit {normalized_unit!r} does not match cap unit {cap.unit!r}"
            )
        status = (
            "held"
            if cap is not None and action_value > cap.maximum
            else "automatic"
        )
        return CapDecision(
            status=status,
            cap=cap,
            action_value=action_value,
            action_unit=normalized_unit,
        )

    def create_connector_artifact(
        self,
        *,
        artifact_id: str,
        owner_user_id: str,
        connector_definition: dict[str, Any],
        mcp_client_config: dict[str, Any],
        created_at: float | None = None,
    ) -> ConnectorArtifact:
        definition = _json_object("connector_definition", connector_definition)
        config = _json_object("mcp_client_config", mcp_client_config)
        timestamp = time.time() if created_at is None else created_at
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_connector_artifacts (
                    artifact_id, owner_user_id, connector_definition_json,
                    mcp_client_config_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    _required("artifact_id", artifact_id),
                    _required("owner_user_id", owner_user_id),
                    json.dumps(definition, sort_keys=True),
                    json.dumps(config, sort_keys=True),
                    timestamp,
                ),
            )
        artifact = self.get_connector_artifact(artifact_id)
        assert artifact is not None
        return artifact

    def remix_connector_artifact(
        self,
        *,
        parent_artifact_id: str,
        artifact_id: str,
        owner_user_id: str,
        connector_definition: dict[str, Any],
        mcp_client_config: dict[str, Any],
        created_at: float | None = None,
    ) -> ConnectorArtifact:
        parent = self.get_connector_artifact(parent_artifact_id)
        if parent is None:
            raise LookupError("parent connector artifact does not exist")
        timestamp = time.time() if created_at is None else created_at
        child = self.create_connector_artifact(
            artifact_id=artifact_id,
            owner_user_id=owner_user_id,
            connector_definition=connector_definition,
            mcp_client_config=mcp_client_config,
            created_at=timestamp,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO outbound_connector_artifact_edges (
                        parent_artifact_id, child_artifact_id,
                        remixed_by_user_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        parent.artifact_id,
                        child.artifact_id,
                        _required("owner_user_id", owner_user_id),
                        timestamp,
                    ),
                )
        except Exception:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM outbound_connector_artifacts WHERE artifact_id = ?",
                    (child.artifact_id,),
                )
            raise
        remixed = self.get_connector_artifact(child.artifact_id)
        assert remixed is not None
        return remixed

    def get_connector_artifact(
        self, artifact_id: str
    ) -> ConnectorArtifact | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artifact_id, owner_user_id, connector_definition_json,
                       mcp_client_config_json, created_at
                  FROM outbound_connector_artifacts
                 WHERE artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
            edge = connection.execute(
                """
                SELECT parent_artifact_id
                  FROM outbound_connector_artifact_edges
                 WHERE child_artifact_id = ?
                """,
                (artifact_id,),
            ).fetchone()
        if row is None:
            return None
        parent_id = edge["parent_artifact_id"] if edge is not None else None
        if parent_id is None:
            attribution = (row["owner_user_id"],)
        else:
            parent = self.get_connector_artifact(parent_id)
            if parent is None:
                raise RuntimeError("connector attribution parent is missing")
            attribution = parent.attribution + (row["owner_user_id"],)
        return ConnectorArtifact(
            artifact_id=row["artifact_id"],
            owner_user_id=row["owner_user_id"],
            connector_definition=json.loads(row["connector_definition_json"]),
            mcp_client_config=json.loads(row["mcp_client_config_json"]),
            parent_artifact_id=parent_id,
            attribution=attribution,
            created_at=row["created_at"],
        )


__all__ = [
    "ActionCap",
    "CapDecision",
    "ConnectionGrant",
    "ConnectionLedger",
    "ConnectionResource",
    "ConnectorArtifact",
    "CredentialBlindBroker",
    "GrantResolutionError",
    "ProxyRequestError",
    "ScopedConnectionProxy",
]
