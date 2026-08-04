"""Outbound connection resources, per-universe grants, and scoped proxies."""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing
import re
import sqlite3
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


def _run_proxy_worker(
    channel: Any,
    dispatch_factory: str,
    dispatch_config: dict[str, Any],
    grant_id: str,
    scopes: tuple[str, ...],
) -> None:
    """Run the trusted dispatcher in a separate spawned process."""
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
