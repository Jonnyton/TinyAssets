"""Signed control-plane client for daemon host-pool operations.

Every operation uses a short-lived daemon bearer token plus an Ed25519
proof-of-possession signature over the exact method, path (including query),
body hash, timestamp, and replay nonce.  There is no administrative credential
or unsigned fallback path.

The transport remains stdlib-only and injectable for focused tests.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from tinyassets.runtime.daemon_auth import DaemonAuthSession


class HostPoolError(Exception):
    """Raised when a host_pool REST call fails.

    ``status`` is the HTTP code (0 if the request never completed, e.g.
    DNS / TLS / socket error). ``body`` is the response body or the
    underlying error message.
    """

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"host_pool control-plane error (status={status}): {body[:200]}")
        self.status = status
        self.body = body


@dataclass
class HostPoolRow:
    """Typed view of a ``public.host_pool`` row.

    Matches the schema at
    ``prototype/full-platform-v0/migrations/001_core_tables.sql``.
    """

    host_id: str
    owner_user_id: str
    provider: str
    capability_id: str
    visibility: str
    price_floor: float | None
    max_concurrent: int
    always_active: bool
    version: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> HostPoolRow:
        return cls(
            host_id=data["host_id"],
            owner_user_id=data["owner_user_id"],
            provider=data["provider"],
            capability_id=data["capability_id"],
            visibility=data["visibility"],
            price_floor=data.get("price_floor"),
            max_concurrent=int(data.get("max_concurrent", 1)),
            always_active=bool(data.get("always_active", False)),
            version=int(data.get("version", 1)),
        )


class _HttpClient(Protocol):
    """Injection seam so tests can swap in an in-memory transport."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, str]: ...


class _UrllibClient:
    """Real stdlib client. One instance per HostPoolClient."""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout: float,
    ) -> tuple[int, str]:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = str(exc)
            return exc.code, body_text
        except urllib.error.URLError as exc:
            raise HostPoolError(0, f"unreachable: {exc.reason}") from exc
        except (TimeoutError, ssl.SSLError, OSError) as exc:
            raise HostPoolError(0, f"transport error: {exc!r}") from exc


class HostPoolClient:
    """Proof-of-possession client for host-pool control-plane resources.

    Parameters
    ----------
    control_plane_url :
        HTTPS base URL of the TinyAssets control plane. Override via
        ``TINYASSETS_CONTROL_PLANE_URL``.
    auth :
        Enrolled daemon authentication session. Required; there is no unsigned
        or administrative-credential fallback.
    http :
        Injection seam — pass a custom ``_HttpClient`` in tests.
    timeout :
        Per-call HTTP timeout in seconds. Default 10s.
    """

    def __init__(
        self,
        control_plane_url: str | None = None,
        *,
        auth: DaemonAuthSession | None = None,
        http: _HttpClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        url = control_plane_url or os.environ.get("TINYASSETS_CONTROL_PLANE_URL", "").strip()
        if not url:
            raise HostPoolError(0, "TINYASSETS_CONTROL_PLANE_URL not configured")
        if not url.startswith("https://"):
            raise HostPoolError(0, "TINYASSETS_CONTROL_PLANE_URL must use HTTPS")
        if auth is None:
            raise HostPoolError(0, "enrolled daemon authentication is required")
        self._base = url.rstrip("/")
        self._auth = auth
        self._http = http or _UrllibClient()
        self._timeout = timeout

    # -- helpers ------------------------------------------------------------

    def _headers(
        self,
        method: str,
        path: str,
        body: bytes | None,
        *,
        prefer: str | None = None,
    ) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        headers.update(self._auth.sign_headers(method, path, body))
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> Any:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        signed_path = f"/v1/{path.lstrip('/')}{query}"
        url = f"{self._base}{signed_path}"
        encoded = (
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            if body is not None
            else None
        )
        status, text = self._http.request(
            method,
            url,
            self._headers(method, signed_path, encoded, prefer=prefer),
            encoded,
            self._timeout,
        )
        if status < 200 or status >= 300:
            raise HostPoolError(status, text)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise HostPoolError(status, f"invalid JSON: {exc}; body={text[:200]}") from exc

    # -- host_pool CRUD ----------------------------------------------------

    def register(
        self,
        *,
        provider: str,
        capability_id: str,
        visibility: str = "self",
        price_floor: float | None = None,
        max_concurrent: int = 1,
        always_active: bool = False,
    ) -> HostPoolRow:
        """Insert a row into ``host_pool``. Returns the new row.

        ``provider`` must be one of ``local|claude|codex|gemini``
        per schema CHECK. ``visibility`` must be one of
        ``self|network|paid``.
        """
        payload = {
            "provider": provider,
            "capability_id": capability_id,
            "visibility": visibility,
            "max_concurrent": max_concurrent,
            "always_active": always_active,
        }
        if price_floor is not None:
            payload["price_floor"] = price_floor
        rows = self._request(
            "POST",
            "host-pool",
            body=payload,
            prefer="return=representation",
        )
        if not isinstance(rows, list) or not rows:
            raise HostPoolError(0, f"register returned no row: {rows!r}")
        return HostPoolRow.from_api(rows[0])

    def heartbeat(self, host_id: str) -> None:
        """Bump ``updated_at`` on the host_pool row (bimodal heartbeat).

        Per design call 2026-04-20: DB updated_at is the load-bearing
        liveness signal pre-Realtime. Upgrade to Presence when Supabase
        Realtime Presence wires in; this call then drops to ~hourly OR
        retires entirely.

        Safe to call on a missing row — returns without error (the
        next register call can recreate). Callers that care about
        row-presence should use ``get`` first.
        """
        self._request(
            "PATCH",
            f"host-pool/{host_id}:heartbeat",
            body={"updated_at": "now()"},
        )

    def update_visibility(self, host_id: str, visibility: str) -> None:
        """Change a host's visibility. ``self|network|paid``."""
        self._request(
            "PATCH",
            f"host-pool/{host_id}",
            body={"visibility": visibility},
        )

    def update_capability(self, host_id: str, capability_id: str) -> None:
        """Change a host's declared capability."""
        self._request(
            "PATCH",
            f"host-pool/{host_id}",
            body={"capability_id": capability_id},
        )

    def deregister(self, host_id: str) -> None:
        """Remove a host_pool row (clean shutdown).

        Not strictly required — Presence-based liveness would mark the
        host offline within TTL. But explicit cleanup is cheap + keeps
        the pool small for queries that filter on ``updated_at``.
        """
        self._request(
            "DELETE",
            f"host-pool/{host_id}",
        )

    def get(self, host_id: str) -> HostPoolRow | None:
        rows = self._request(
            "GET",
            f"host-pool/{host_id}",
        )
        if not isinstance(rows, list) or not rows:
            return None
        return HostPoolRow.from_api(rows[0])

    # -- capabilities ------------------------------------------------------

    def ensure_capability(
        self, capability_id: str, *, node_type: str, llm_model: str,
        description: str | None = None,
    ) -> None:
        """Insert the capability row if absent; no-op if present.

        Per schema: first daemon registration auto-inserts capability
        rows it declares (``docs/exec-plans/active/2026-04-19-track-a-
        schema-auth-rls.md`` §7 OPEN resolution).
        """
        payload = {
            "capability_id": capability_id,
            "node_type": node_type,
            "llm_model": llm_model,
        }
        if description:
            payload["description"] = description
        # ON CONFLICT DO NOTHING via Prefer header.
        self._request(
            "POST",
            "capabilities",
            body=payload,
            prefer="resolution=ignore-duplicates",
        )

    # -- requests surface (bid polling) ------------------------------------

    def list_pending_requests(
        self,
        capability_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Read pending requests matching a capability.

        Returns raw dicts (not a dataclass) because the request shape
        has jsonb ``inputs`` + per-field nullability we don't fully
        model yet. Consumers can project what they need.

        Filters: ``state='pending'`` AND ``capability_id=<cap>`` AND
        ``visibility IN ('paid', 'public')``. Sorted by oldest first —
        FIFO fairness for the first-draft.
        """
        rows = self._request(
            "GET",
            "execution-requests",
            params={
                "state": "eq.pending",
                "capability_id": f"eq.{capability_id}",
                "visibility": "in.(paid,public)",
                "select": (
                    "request_id,requester_user_id,capability_id,"
                    "node_id,visibility,reserve_price,deadline,inputs,created_at"
                ),
                "order": "created_at.asc",
                "limit": str(limit),
            },
        )
        return list(rows) if isinstance(rows, list) else []
