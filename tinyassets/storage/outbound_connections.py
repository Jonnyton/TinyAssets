"""Outbound connection resources, per-universe grants, and scoped proxies."""

from __future__ import annotations

import base64
import hashlib
import http.client
import io
import ipaddress
import json
import math
import multiprocessing
import os
import re
import socket
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

AuthenticatedPrincipalVerifier = Callable[[], str]


@dataclass(frozen=True)
class ConnectionResource:
    connection_id: str
    owner_user_id: str
    connection_class: str
    scopes: tuple[str, ...]
    provider: str
    destination: str
    credential_ref: str
    revoked_at: float | None


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
    except Exception:
        _send_message(
            channel,
            {"op": "startup_failed", "message": "trusted proxy failed to start"},
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
            if not isinstance(verb, str) or verb not in scopes:
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
        if verb not in self.scopes:
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
        if verb not in resource.scopes:
            raise PermissionError(
                f"verb {verb!r} is outside the granted connection scope"
            )
        try:
            credential = self._resolve_credential(resource.credential_ref)
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


class _ProductionVaultCredentialResolver:
    """Resolve one exact connection-ledger reference inside the broker child."""

    __slots__ = ("_destination", "_provider", "_repository", "_universe_dir")

    def __init__(
        self,
        *,
        universe_dir: str | Path,
        provider: str,
        destination: str,
    ) -> None:
        self._universe_dir = Path(universe_dir)
        self._provider = provider.strip().lower()
        self._destination = destination.strip().lower()
        self._repository = _github_repository_from_destination(self._destination)

    def __call__(self, credential_ref: str) -> str:
        if self._provider != "github":
            raise RuntimeError("credential reference has no trusted resolver")
        expected_reference = f"vault://github/{self._repository}"
        if credential_ref != expected_reference:
            raise RuntimeError("credential reference does not match the connection")
        from tinyassets.credential_vault import resolve_github_token

        credential = resolve_github_token(
            self._universe_dir,
            self._repository,
            purpose="write",
        )
        if not credential:
            raise RuntimeError("credential reference is unavailable")
        return credential


class _WorkOSPipesCredentialResolver:
    """Resolve an owner-bound Pipes reference only inside the broker child."""

    __slots__ = ("_owner_user_id", "_provider")

    def __init__(self, *, owner_user_id: str, provider: str) -> None:
        self._owner_user_id = owner_user_id.strip()
        self._provider = provider.strip().lower()

    def __call__(self, credential_ref: str) -> str:
        expected = f"workos-pipes://github/{self._owner_user_id}"
        if self._provider != "github" or credential_ref != expected:
            raise RuntimeError("credential reference does not match the connection")
        from tinyassets.workos_pipes import WorkOSPipesClient

        return WorkOSPipesClient().vend_credential(user_id=self._owner_user_id)


class _TrustedCredentialResolver:
    """Select fixture or production resolution without an adapter callback."""

    __slots__ = ("_fixture", "_production", "_pipes", "_provider")

    def __init__(self, config: dict[str, Any]) -> None:
        self._provider = str(config["provider"])
        self._fixture = _TestFixtureCredentialResolver(
            allow_test_fixtures=bool(config["allow_test_fixtures"]),
        )
        self._production = _ProductionVaultCredentialResolver(
            universe_dir=config["universe_dir"],
            provider=self._provider,
            destination=str(config["destination"]),
        )
        self._pipes = _WorkOSPipesCredentialResolver(
            owner_user_id=str(config["owner_user_id"]),
            provider=self._provider,
        )

    def __call__(self, credential_ref: str) -> str:
        if self._provider.startswith("test-fixture."):
            return self._fixture(credential_ref)
        if credential_ref.startswith("workos-pipes://"):
            return self._pipes(credential_ref)
        return self._production(credential_ref)


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


def _github_repository_from_destination(destination: str) -> str:
    normalized = destination.strip().lower().removeprefix("https://")
    normalized = normalized.removeprefix("http://").strip("/")
    normalized = normalized.removeprefix("github.com/")
    parts = normalized.split("/")
    if (
        len(parts) != 2
        or re.fullmatch(r"[\w.-]+/[\w.-]+", normalized) is None
        or any(part in {".", ".."} for part in parts)
    ):
        raise PermissionError("GitHub destination does not identify one repository")
    return normalized


class _ProductionGitHubNetworkDriver:
    """Trusted credential-bearing GitHub read transport for scoped proxies."""

    __slots__ = ()

    def __call__(
        self,
        *,
        credential: str,
        provider: str,
        destination: str,
        verb: str,
        request: object,
    ) -> Any:
        if provider != "github":
            raise PermissionError("provider verb has no trusted outbound transport")
        repository = _github_repository_from_destination(destination)
        if verb == "pull_requests:write":
            if not isinstance(request, dict):
                raise PermissionError("GitHub write request shape is not permitted")
            requested_repository = str(request.get("repository", "")).strip().lower()
            if requested_repository != repository:
                raise PermissionError("GitHub request repository is outside the grant")
            from tinyassets.effectors.github_pr import (
                _prepare_scoped_github_commit,
                _publish_scoped_github_pull_request,
            )

            operation = request.get("operation")
            if operation == "prepare_commit":
                return _prepare_scoped_github_commit(
                    request=request,
                    destination=repository,
                    capability_token=credential,
                )
            if operation == "publish_pull_request":
                return _publish_scoped_github_pull_request(
                    request=request,
                    destination=repository,
                    capability_token=credential,
                )
            raise PermissionError("GitHub write operation is not permitted")
        if verb != "pull_requests:read_for_commit":
            raise PermissionError("provider verb has no trusted outbound transport")
        if not isinstance(request, dict) or set(request) != {
            "repository",
            "intended_head_sha",
            "per_page",
        }:
            raise PermissionError("GitHub request shape is not permitted")
        requested_repository = str(request["repository"]).strip().lower()
        if requested_repository != repository:
            raise PermissionError("GitHub request repository is outside the grant")
        intended_head_sha = str(request["intended_head_sha"]).strip().lower()
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", intended_head_sha) is None:
            raise PermissionError("GitHub request commit is invalid")
        per_page = request["per_page"]
        if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= 100:
            raise PermissionError("GitHub request page size is invalid")
        path = (
            f"/repos/{repository}/commits/{intended_head_sha}/pulls?"
            + urllib.parse.urlencode({"per_page": per_page})
        )
        outbound = urllib.request.Request(
            f"https://api.github.com{path}",
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {credential}",
                "User-Agent": "tinyassets-outbound-broker/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(outbound, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ProxyRequestError("GitHub destination read failed") from exc
        if not isinstance(payload, list):
            raise ProxyRequestError("GitHub destination returned an invalid response")
        return payload


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


def _ssrf_auth_headers(
    auth_scheme: str,
    bundle: ConnectionSecretBundle,
    *,
    header_name: str = "",
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
    else:
        # oauth1a (Twitter) is intentionally NOT implemented in this dark slice;
        # it lands with the Twitter migration (tasks.md §4) by lifting the
        # existing signer verbatim into an ``oauth1a`` handler.
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
    # Percent-encoded dot/slash survives the raw dot-segment check but the origin
    # decodes it, so `/public/%2e%2e/admin` bypasses a path-template allowlist
    # (Codex-found). Reject encoded dots/slashes specifically — this leaves an
    # ordinary encoded space (%20) legal, so real paths still parse.
    lowered_path = path.lower()
    if "%2e" in lowered_path or "%2f" in lowered_path:
        raise SsrfValidationError(
            "outbound url path must not contain encoded dot-segments"
        )
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
    host_for_url = (
        f"[{canonical.hostname}]"
        if canonical.is_ip_literal and ":" in canonical.hostname
        else canonical.hostname
    )
    url = f"https://{host_for_url}"
    if canonical.port != 443:
        url += f":{canonical.port}"
    url += canonical.path_qs
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
        # leaves ``__context__`` populated (readable via ``exc.__context__`` —
        # the slack_transport.py:89 leak, where a URLError/BadStatusLine can
        # quote the reflected Authorization header). Raising here clears it.
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
    ) -> None:
        self._resolver = resolver or _default_dns_resolver
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
    ) -> dict[str, Any]:
        if not isinstance(bundle, ConnectionSecretBundle):
            raise SsrfValidationError("a typed connection secret bundle is required")
        verb = (method or "").strip().upper()
        if verb not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise SsrfValidationError("outbound method is not permitted")
        canonical = _parse_canonical_https_url(url, allowed_ports=self._allowed_ports)
        request_headers = _validated_request_headers(headers)
        auth_headers = _ssrf_auth_headers(auth_scheme, bundle, header_name=header_name)
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


class _TrustedNetworkDriver:
    """Select fixture or production transport entirely inside the broker."""

    __slots__ = ("_fixture", "_production")

    def __init__(self, config: dict[str, Any], runtime_root: Path) -> None:
        self._fixture = _TestFixtureNetworkDriver(
            runtime_root,
            allow_test_fixtures=bool(config["allow_test_fixtures"]),
        )
        self._production = _ProductionGitHubNetworkDriver()

    def __call__(self, **kwargs: Any) -> Any:
        provider = str(kwargs.get("provider", ""))
        if provider.startswith("test-fixture."):
            return self._fixture(**kwargs)
        return self._production(**kwargs)


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
    revoked_at      REAL
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
    ) -> ConnectionResource:
        resource = ConnectionResource(
            connection_id=_required("connection_id", connection_id),
            owner_user_id=_required("owner_user_id", owner_user_id),
            connection_class=_required("connection_class", connection_class),
            scopes=tuple(_required("scope", scope) for scope in scopes),
            provider=_required("provider", provider),
            destination=_required("destination", destination),
            credential_ref=_required("credential_ref", credential_ref),
            revoked_at=None,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO outbound_connections (
                    connection_id, owner_user_id, connection_class, scopes_json,
                    provider, destination, credential_ref, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    resource.connection_id,
                    resource.owner_user_id,
                    resource.connection_class,
                    json.dumps(resource.scopes),
                    resource.provider,
                    resource.destination,
                    resource.credential_ref,
                ),
            )
        return resource

    def get_connection(self, connection_id: str) -> ConnectionResource | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbound_connections WHERE connection_id = ?",
                (connection_id,),
            ).fetchone()
        if row is None:
            return None
        return ConnectionResource(
            connection_id=row["connection_id"],
            owner_user_id=row["owner_user_id"],
            connection_class=row["connection_class"],
            scopes=tuple(json.loads(row["scopes_json"])),
            provider=row["provider"],
            destination=row["destination"],
            credential_ref=row["credential_ref"],
            revoked_at=row["revoked_at"],
        )

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
        resource = self.get_connection(connection_id)
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
        return self._start_scoped_proxy(
            grant_id=row["grant_id"],
            universe_id=universe_id,
            provider=row["provider"],
            destination=row["destination"],
            scopes=tuple(json.loads(row["scopes_json"])),
            owner_user_id=row["owner_user_id"],
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
        resource = self.get_connection(_required("connection_id", connection_id))
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
    ) -> ScopedConnectionProxy:
        factory_reference = "credential_broker_v1"
        grant_runtime_id = hashlib.sha256(
            grant_id.encode("utf-8")
        ).hexdigest()
        factory_config = {
            "allow_test_fixtures": self._allow_test_fixtures,
            "ledger_db_path": str(self._db_path.resolve()),
            "universe_dir": str((self._db_path.parent / universe_id).resolve()),
            "provider": provider,
            "destination": destination,
            "owner_user_id": owner_user_id,
            "runtime_root": str(
                (
                    self._db_path.parent
                    / ".outbound-proxy"
                    / grant_runtime_id
                ).resolve()
            ),
        }
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
        worker.start()
        server_channel.close()
        if not client_channel.poll(5.0):
            client_channel.close()
            worker.terminate()
            worker.join(timeout=1.0)
            raise ProxyRequestError("outbound proxy failed to start")
        ready = _receive_message(client_channel)
        if ready != {"op": "ready"}:
            client_channel.close()
            worker.terminate()
            worker.join(timeout=1.0)
            raise ProxyRequestError("outbound proxy failed to start")
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
        return ConnectionResource(
            connection_id=row["connection_id"],
            owner_user_id=row["owner_user_id"],
            connection_class=row["connection_class"],
            scopes=tuple(json.loads(row["scopes_json"])),
            provider=row["provider"],
            destination=row["destination"],
            credential_ref=row["credential_ref"],
            revoked_at=row["revoked_at"],
        )

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
