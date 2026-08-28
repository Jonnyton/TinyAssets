"""The ONE generic outbound channel primitive (Pipedream model).

The PLATFORM knows NOTHING about any specific channel. There is no per-service
code here — no hard-coded hostname, no per-channel auth-header assembly, no
per-service branch. A universe adds ANY outbound integration — even an API this
platform has never heard of — with ZERO platform changes, by:

  1. Creating an ``http`` outbound connection (the Pipedream "connected
     account"): a vault ``credential_ref`` + an ``auth_scheme``
     (bearer/basic/header/oauth1a/none) + a per-endpoint egress allowlist
     (host + path_template + methods, including the ``{name+}`` multi-segment
     tail). See ``storage/outbound_connections.ConnectionLedger``.
  2. Granting that connection to the universe (``grant_effector_consent`` /
     ``grant_connection``).
  3. Emitting an ``authenticated_external_call`` packet from a node that
     DESCRIBES the actual API request.

The packet is fully user-specified; the platform validates SHAPE, not channel:

    {
      "sink": "authenticated_external_call",
      "connection_id": "<the http connection to use>",
      "grant_id":      "<the grant binding that connection to THIS universe>",
      "verb":          "<the connection scope string — for http, the HTTP method>",
      "request": {
        "method":  "POST",           # optional; must equal ``verb`` if present
        "host":    "api.example.com", # optional; falls back to the connection's
                                      #   single allowlisted host
        "path":    "/v1/messages",    # request path (matched by the allowlist)
        "query":   {"k": "v"},        # optional; validated by the allowlist
        "headers": {"X-Extra": "1"},  # optional NON-auth headers
        "header_name": "X-Api-Key",   # optional; only for the "header" auth scheme
        "body":    {...} | "..."      # optional; dict/list json-encoded by worker
      }
    }

CREDENTIAL-BLINDNESS. This effector NEVER resolves or sees the credential. It
resolves an exact scoped proxy under the universe's own authority and hands the
wire request to ``proxy.request(verb, request)``. The credential is applied
INSIDE the spawned broker worker (``_run_proxy_worker`` +
``_SsrfHardenedHttpDriver``); the secret never exists in this process. The
effector returns the worker's sanitized ``{status, reason, headers, body}`` as
evidence, or a secret-free error dict — it NEVER raises to the run-completion
path.

ISOLATION. ``universe_id`` is derived from server-owned run context
(``base_path``), never the packet. A packet may only name a grant that is bound
to the universe RUNNING the graph: the effector refuses any grant whose
``universe_id`` does not match, so a copied/remixed graph cannot borrow another
universe's connections. The authenticated principal is the grant's OWN stored
owner — read from the trusted grant row, gated by that universe match — never a
payload-supplied identity.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from pathlib import Path
from typing import Any

from tinyassets.effectors.authority import DENIED as SOUL_AUTHORITY_DENIED
from tinyassets.effectors.authority import resolve_soul_effect_authority

logger = logging.getLogger(__name__)

#: The one generic sink. A node that declares ``effects=[…this…]`` and emits a
#: matching packet routes here regardless of which external service it targets.
EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL = "authenticated_external_call"


# --------------------------------------------------------------------------- #
# Packet reading (shape only — no channel knowledge)
# --------------------------------------------------------------------------- #
def _parse_packet(value: Any) -> dict[str, Any] | None:
    """Return the packet dict iff ``value`` is a matching packet, else None."""
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (TypeError, ValueError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None
    if packet.get("sink") != EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL:
        return None
    return packet


def _find_packet(
    *,
    output_keys: list[str],
    run_state: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    for key in output_keys or []:
        if not isinstance(key, str) or key not in run_state:
            continue
        packet = _parse_packet(run_state.get(key))
        if packet is not None:
            return key, packet
    return None, None


def _str_field(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    return value.strip() if isinstance(value, str) else ""


# --------------------------------------------------------------------------- #
# Run-context resolution (server-owned; never from the packet)
# --------------------------------------------------------------------------- #
def _universe_id(base_path: str | Path | None) -> str:
    """The universe whose authority this run binds to — from ``base_path`` only.

    ``runs.py`` passes the universe DIR as ``base_path`` (``data_root/<uid>``), so
    the trailing component IS the universe id. Never taken from the packet.
    """
    if base_path is None:
        return ""
    try:
        return Path(base_path).name.strip()
    except (TypeError, ValueError):
        return ""


def _ledger_db_path(base_path: str | Path | None) -> Path | None:
    """The outbound ledger DB lives at the DATA ROOT (``base_path.parent``)."""
    if base_path is None:
        return None
    try:
        return Path(base_path).parent / "outbound.db"
    except (TypeError, ValueError):
        return None


def _check_consent(universe_dir: Path, destination: str) -> bool:
    """Whether an active effector-consent grant exists for this destination.

    A connection grant proves the universe MAY use the connection; a live
    external effect additionally requires the owner's explicit effector consent
    for the destination. Fail closed (return False) on empty destination or any
    lookup failure — a live call must never proceed on a crashed consent check.
    """
    if not destination:
        return False
    try:
        from tinyassets.storage.effector_consents import is_consent_active

        return is_consent_active(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
            destination=destination,
        )
    except Exception:
        logger.exception("authenticated_external_call consent lookup crashed")
        return False


# --------------------------------------------------------------------------- #
# Wire-request assembly (generic; the allowlist in the worker is the boundary)
# --------------------------------------------------------------------------- #
def _resolve_host(request: dict[str, Any], connection_view: Any) -> tuple[str, str]:
    """Return ``(host, error_kind)``; ``error_kind`` empty on success.

    Host precedence: an explicit ``request.host`` (the user fully specifies the
    call), else the connection's single allowlisted host. A connection spanning
    multiple hosts with no explicit ``host`` is ambiguous and refused — the user
    must say which. The worker's allowlist re-validates whatever host is used.
    """
    explicit = _str_field(request, "host")
    if explicit:
        return explicit, ""
    hosts = {
        ep.host
        for ep in getattr(connection_view, "allowed_endpoints", ()) or ()
        if getattr(ep, "host", "")
    }
    if len(hosts) == 1:
        return next(iter(hosts)), ""
    if not hosts:
        return "", "no_allowlisted_host"
    return "", "host_ambiguous"


def _build_url(request: dict[str, Any], host: str) -> tuple[str, str]:
    """Return ``(url, error_kind)``. Accepts an absolute ``url`` or ``host``+``path``.

    Query params come from a ``query`` mapping (never smuggled inside ``path`` when
    a ``query`` is also supplied). The URL is built here but the real egress
    boundary is the per-connection allowlist enforced inside the worker.
    """
    absolute = _str_field(request, "url")
    if absolute:
        return absolute, ""
    path = request.get("path")
    if not isinstance(path, str) or not path:
        return "", "missing_path"
    if not path.startswith("/"):
        return "", "invalid_path"
    query = request.get("query")
    query_string = ""
    if query is not None:
        if not isinstance(query, dict):
            return "", "invalid_query"
        if "?" in path:
            return "", "query_in_path_conflict"
        query_string = urllib.parse.urlencode(
            {str(k): str(v) for k, v in query.items()}
        )
    url = f"https://{host}{path}"
    if query_string:
        url = f"{url}?{query_string}"
    return url, ""


# --------------------------------------------------------------------------- #
# Proxy seam — the ONLY place the ledger is touched. Kept small + named so the
# credential-blind spawned-worker path is the default and tests can substitute
# an in-process loopback broker for wire-request assertions (the child re-imports
# with production SSRF seams, so a monkeypatch cannot cross the spawn boundary —
# exactly why the project splits "credential-blindness through the real worker"
# from "successful wire-request assertion via an injected driver").
# --------------------------------------------------------------------------- #
def _read_connection_context(
    *, db_path: Path, grant_id: str, connection_id: str, universe_id: str
) -> tuple[Any, Any, str]:
    """Return ``(grant, connection_view, error_kind)`` — plain reads, no principal.

    Enforces the isolation gate: the grant must exist, be active, and be bound to
    the RUNNING universe. ``error_kind`` empty on success.
    """
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(db_path)
    grant = ledger.get_grant(grant_id)
    if grant is None:
        return None, None, "unknown_grant"
    if getattr(grant, "revoked_at", None) is not None:
        return None, None, "revoked_grant"
    if getattr(grant, "universe_id", "") != universe_id:
        # The isolation boundary: a packet cannot select a grant from a
        # different universe than the one running this graph.
        return None, None, "grant_not_for_universe"
    if getattr(grant, "connection_id", "") != connection_id:
        return None, None, "grant_connection_mismatch"
    view = ledger.get_connection_view(connection_id)
    if view is None:
        return None, None, "unknown_connection"
    return grant, view, ""


def _open_connection_proxy(
    *,
    db_path: Path,
    universe_id: str,
    grant_id: str,
    connection_id: str,
    owner_user_id: str,
) -> Any:
    """Resolve the exact scoped, credential-blind proxy under universe authority.

    The authenticated principal is the grant's OWN stored owner (trusted grant
    row), gated upstream by the universe match. ``resolve_exact_scoped_proxy``
    spawns the broker worker; the credential is resolved and applied inside it.
    """
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(
        db_path,
        verify_authenticated_principal=lambda: owner_user_id,
    )
    return ledger.resolve_exact_scoped_proxy(
        universe_id=universe_id,
        grant_id=grant_id,
        connection_id=connection_id,
    )


# --------------------------------------------------------------------------- #
# The effector
# --------------------------------------------------------------------------- #
def run_authenticated_external_call_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Dispatch one ``authenticated_external_call`` packet. NEVER raises.

    Every refusal or failure is returned as a secret-free evidence dict with an
    ``error_kind``. Success returns the worker's sanitized response plus a small
    amount of non-secret metadata.
    """
    del dry_run  # gate orchestration owns the dry-run decision; kept for compat
    try:
        return _run(
            node_id=node_id,
            output_keys=output_keys,
            run_state=run_state,
            base_path=base_path,
            run_id=run_id,
        )
    except Exception as exc:  # defensive — never raise from the completion path
        logger.exception(
            "authenticated_external_call effector crashed for node %s", node_id
        )
        return {
            "error": f"effector crashed: {exc}",
            "error_kind": "effector_crashed",
        }


def _run(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None,
    run_id: str,
) -> dict[str, Any]:
    matched_key, packet = _find_packet(output_keys=output_keys, run_state=run_state)
    if packet is None:
        return {
            "error": (
                f"node '{node_id}' declared effects=["
                f"{EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL}] but no output_key held "
                "a parseable authenticated_external_call packet"
            ),
            "error_kind": "no_matching_packet",
        }

    connection_id = _str_field(packet, "connection_id")
    grant_id = _str_field(packet, "grant_id")
    if not connection_id:
        return {"error": "packet.connection_id is required", "error_kind": "invalid_packet"}
    if not grant_id:
        return {"error": "packet.grant_id is required", "error_kind": "invalid_packet"}

    request = packet.get("request")
    if not isinstance(request, dict):
        return {"error": "packet.request must be a mapping", "error_kind": "invalid_packet"}

    # verb = the connection scope. For http connections this IS the HTTP method
    # (the worker uses it as the method). Accept either the top-level verb or
    # request.method; if both are present they must agree.
    verb = _str_field(packet, "verb")
    request_method = _str_field(request, "method")
    if not verb:
        verb = request_method
    if not verb:
        return {"error": "packet.verb is required", "error_kind": "invalid_packet"}
    if request_method and request_method.upper() != verb.upper():
        return {
            "error": "request.method does not match verb",
            "error_kind": "method_mismatch",
            "verb": verb,
            "requested_method": request_method,
        }

    universe_id = _universe_id(base_path)
    db_path = _ledger_db_path(base_path)
    if not universe_id or db_path is None:
        # No trusted universe context ⇒ fail closed (never borrow a default).
        return {
            "error": "no universe authority is bound to this run",
            "error_kind": "no_universe_authority",
            "matched_output_key": matched_key,
        }

    grant, view, gate_error = _read_connection_context(
        db_path=db_path,
        grant_id=grant_id,
        connection_id=connection_id,
        universe_id=universe_id,
    )
    if gate_error:
        return {
            "error": f"connection authority refused: {gate_error}",
            "error_kind": gate_error,
            "matched_output_key": matched_key,
            "connection_id": connection_id,
            "grant_id": grant_id,
            "universe_id": universe_id,
        }

    # Authorization gates — parity with every prior per-channel effector. The
    # connection grant above proves the universe MAY use this connection, but a
    # LIVE external effect additionally requires: (1) the running universe's soul
    # to not DENY the (sink, destination), and (2) an active effector-consent
    # grant for the destination. A connection grant ALONE is not sufficient to
    # fire an effect — fail closed on either gate. The destination is the
    # connection's own configured destination (a stable, server-owned value,
    # never taken from the packet).
    universe_dir = Path(base_path)
    destination = str(getattr(view, "destination", "") or "").strip()
    authority = resolve_soul_effect_authority(
        universe_dir,
        EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        destination,
    )
    if authority == SOUL_AUTHORITY_DENIED:
        return {
            "dry_run": True,
            "reason": "soul_authority_denied",
            "error_kind": "soul_authority_denied",
            "destination": destination,
            "connection_id": connection_id,
            "matched_output_key": matched_key,
        }
    if not _check_consent(universe_dir, destination):
        return {
            "dry_run": True,
            "reason": "missing_consent",
            "error_kind": "missing_consent",
            "destination": destination,
            "connection_id": connection_id,
            "matched_output_key": matched_key,
            "hint": (
                "A live authenticated_external_call requires an active effector-"
                "consent grant for this connection's destination; grant it through "
                "the internal consent surface before the effect can fire."
            ),
        }

    host, host_error = _resolve_host(request, view)
    if host_error:
        return {
            "error": f"could not resolve request host: {host_error}",
            "error_kind": host_error,
            "matched_output_key": matched_key,
            "connection_id": connection_id,
        }

    url, url_error = _build_url(request, host)
    if url_error:
        return {
            "error": f"could not build request url: {url_error}",
            "error_kind": url_error,
            "matched_output_key": matched_key,
            "connection_id": connection_id,
        }

    wire_request: dict[str, Any] = {"url": url}
    headers = request.get("headers")
    if headers is not None:
        wire_request["headers"] = headers
    if "body" in request:
        wire_request["body"] = request.get("body")
    header_name = _str_field(request, "header_name")
    if header_name:
        wire_request["header_name"] = header_name

    # QUOTA — pre-flight, on the path production actually uses. This effector is
    # dispatched straight from run_effects_for_branch and calls proxy.request()
    # itself; it never passes through execute_replay_safe_effect, so gating that
    # helper left THE primary channel-agnostic write primitive unmetered
    # (Codex REJECT 2026-08-28 A). run_id:node_id identifies one effect within a
    # run and is stable across a replay of the same node.
    from tinyassets.storage.outbound_connections import AmbiguousProxyOutcome
    from tinyassets.storage.usage_ledger import get_tier
    from tinyassets.usage_policy import (
        release_effect_quota,
        reserve_effect_quota,
        settle_effect_quota,
    )

    _quota_key = f"{run_id}:{node_id}"
    _refusal = reserve_effect_quota(
        base_path,
        sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        effect_key=_quota_key,
        tier=get_tier(base_path),
    )
    if _refusal is not None:
        return {
            "error": "usage limit reached",
            "error_kind": "usage_limit_reached",
            "dimension": _refusal.dimension,
            "tier": _refusal.tier,
            "detail": _refusal.message(),
            "matched_output_key": matched_key,
        }

    proxy = None
    try:
        proxy = _open_connection_proxy(
            db_path=db_path,
            universe_id=universe_id,
            grant_id=grant_id,
            connection_id=connection_id,
            owner_user_id=getattr(grant, "owner_user_id", ""),
        )
        response = proxy.request(verb, wire_request)
    except Exception as exc:
        # Refund ONLY when we know nothing reached the world. An ambiguous outcome
        # means the destination may already have applied the request — refunding it
        # would let an effect that DID land be retried for free, which is the
        # opposite of what a cap is for. Ambiguity keeps its slot; reconciliation
        # settles or releases it once the truth is known (Codex REJECT round 2 A).
        if not isinstance(exc, AmbiguousProxyOutcome):
            release_effect_quota(
                base_path,
                sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
                effect_key=_quota_key,
            )
        # Secret-free by construction: the proxy/broker raise only sanitized,
        # credential-free errors across the governed boundary.
        return {
            "error": f"outbound request failed: {type(exc).__name__}",
            "error_kind": "outbound_request_failed",
            "detail": str(exc),
            "matched_output_key": matched_key,
            "connection_id": connection_id,
            "grant_id": grant_id,
            "verb": verb,
            "url": url,
        }
    finally:
        if proxy is not None:
            try:
                proxy.close()
            except Exception:  # pragma: no cover — best-effort teardown
                logger.debug("proxy close failed for node %s", node_id, exc_info=True)

    # Reached the world: spend the reserved slot. Transition-sensitive, so a
    # replay of the same run:node settles nothing further.
    settle_effect_quota(
        base_path,
        sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
        effect_key=_quota_key,
    )
    return {
        "delivered": True,
        "response": response,
        "matched_output_key": matched_key,
        "connection_id": connection_id,
        "grant_id": grant_id,
        "verb": verb,
        "url": url,
    }


__all__ = [
    "EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL",
    "run_authenticated_external_call_effector",
]
