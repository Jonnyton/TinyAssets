"""The authenticated wire in front of :func:`deliver_app_event`.

``deliver_app_event`` takes every field on trust — which workspace, which
sender, which sender's own team. That is only safe if the caller is provably
the real chat transport, and this module is that proof.

Why a separate port, not a path on the public app
-------------------------------------------------
The daemon's Starlette app is the origin the Cloudflare tunnel points at, and
production runs the tunnel in **token mode**, so its ingress rules live in the
Cloudflare dashboard rather than in this repo. Probing the live host shows every
non-``/mcp`` path returning 404, but that is not proof of path isolation: a 404
from the app itself and a 404 from a tunnel that refuses to forward are
indistinguishable from outside.

Mounting an unauthenticated-by-design internal route on an app whose public
exposure cannot be read from the repo is not a risk worth taking for the
convenience of reusing a port. This app is served separately and bound to the
container network only.

Why HMAC and not a bearer token
-------------------------------
A bearer token is replayable by anything that observes one request. The
signature here covers the body and a timestamp, so a captured request cannot be
re-sent after the skew window and cannot be edited at all — which matters
because the body is exactly the set of identity claims the daemon then trusts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

#: Shared secret, canonical single-line standard base64 of >=32 random bytes —
#: the same encoding the other daemon secrets use. Held by the daemon and the
#: chat transport, nothing else.
HMAC_ENV = "TINYASSETS_APP_INGRESS_HMAC_KEY"

#: Domain separation, so a signature minted for this purpose can never be
#: replayed against another HMAC surface that happens to share the key.
_PURPOSE = b"tinyassets-app-ingress-v1"

#: How far a request's timestamp may be from ours, in seconds. Bounds replay to
#: a window rather than forever. Symmetric, because a transport whose clock runs
#: fast is a real operational condition, not an attack.
MAX_SKEW_SECONDS = 300

#: Refuse anything larger unread. The real payload is a chat message plus a
#: handful of ids; a megabyte of it is not a legitimate caller.
MAX_BODY_BYTES = 128 * 1024

SIGNATURE_HEADER = "x-tinyassets-ingress-signature"
TIMESTAMP_HEADER = "x-tinyassets-ingress-timestamp"

#: Exactly the fields `deliver_app_event` accepts from a caller. An allowlist
#: rather than `**body`: without it, adding a test-only injection parameter to
#: `deliver_app_event` would silently become remotely settable.
_ACCEPTED_FIELDS = (
    "provider",
    "api_app_id",
    "workspace_id",
    "actor_team_id",
    "external_sender_id",
    "channel_id",
    "event_id",
    "event_type",
    "text",
    "thread_ts",
)


class IngressAuthError(Exception):
    """Authentication failed. The reason belongs in the log, not the response."""


def load_key(env: Mapping[str, str] | None = None) -> bytes:
    """The shared secret, or raise.

    Fails closed: an unset or malformed key means the route refuses every
    request rather than serving an unauthenticated one. A daemon deployed
    without the secret must not quietly become an open ingress.
    """
    raw = (env if env is not None else os.environ).get(HMAC_ENV, "")
    if not raw or not raw.strip():
        raise IngressAuthError("app ingress key is not configured")
    try:
        key = base64.b64decode(raw.strip(), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise IngressAuthError("app ingress key is not valid base64") from exc
    if len(key) < 32:
        raise IngressAuthError("app ingress key is too short")
    return key


def sign(body: bytes, timestamp: str, key: bytes) -> str:
    """The expected signature for one request.

    Binds the timestamp to the body: signing them separately, or signing only
    the body, would let a captured signature be re-dated indefinitely.
    """
    digest = hashlib.sha256(body).hexdigest().encode("ascii")
    message = b"%s:%s:%s" % (_PURPOSE, timestamp.encode("ascii"), digest)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def verify(
    *,
    body: bytes,
    signature: str,
    timestamp: str,
    key: bytes,
    now: float | None = None,
) -> None:
    """Raise :class:`IngressAuthError` unless this request is authentic and fresh."""
    if len(body) > MAX_BODY_BYTES:
        raise IngressAuthError("app ingress body is too large")
    try:
        sent_at = float(timestamp)
    except (TypeError, ValueError) as exc:
        raise IngressAuthError("app ingress timestamp is not a number") from exc
    current = time.time() if now is None else now
    if abs(current - sent_at) > MAX_SKEW_SECONDS:
        raise IngressAuthError("app ingress timestamp is outside the skew window")
    expected = sign(body, timestamp, key)
    # compare_digest, not `==`: a byte-at-a-time comparison leaks the prefix
    # length of a correct guess, which is enough to forge one byte at a time.
    if not hmac.compare_digest(expected, signature or ""):
        raise IngressAuthError("app ingress signature does not match")


def _accepted(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Only the declared fields, each a string. Anything else is dropped."""
    out: dict[str, Any] = {}
    for name in _ACCEPTED_FIELDS:
        value = payload.get(name, "")
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        out[name] = value
    return out


def handle_request(
    *,
    body: bytes,
    headers: Mapping[str, str],
    env: Mapping[str, str] | None = None,
    now: float | None = None,
    deliver: Callable[..., Any] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Authenticate one request and deliver it. Returns ``(status, payload)``.

    Transport-agnostic on purpose so the security decisions are testable without
    standing up a server.

    Every authentication failure answers **401 with the same body**. A caller
    that can tell "no key configured" from "bad signature" from "stale
    timestamp" learns about the deployment; the specific reason is logged.
    """
    lowered = {str(k).lower(): v for k, v in headers.items()}
    try:
        key = load_key(env)
        verify(
            body=body,
            signature=str(lowered.get(SIGNATURE_HEADER, "")),
            timestamp=str(lowered.get(TIMESTAMP_HEADER, "")),
            key=key,
            now=now,
        )
    except IngressAuthError as exc:
        logger.warning("app ingress: refused (%s)", exc)
        return 401, {"error": "unauthenticated"}

    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("body must be a JSON object")
        fields = _accepted(payload)
    except Exception:  # noqa: BLE001
        logger.warning("app ingress: malformed body")
        return 400, {"error": "malformed"}

    if deliver is None:
        from tinyassets.app_ingress import deliver_app_event as deliver

    result = deliver(**fields)
    return 200, {
        "handled": bool(getattr(result, "handled", False)),
        "provider_receipt_ref": str(getattr(result, "provider_receipt_ref", "")),
    }


#: Where the internal listener binds.
#:
#: **This port must never appear in a compose ``ports:`` mapping.** The daemon
#: publishes 8001 as ``127.0.0.1:8001``, and the tunnel's dashboard ingress rule
#: resolves to that loopback-published port — so publishing this one would put
#: an internal route exactly where the public one already reaches. Unpublished,
#: it is reachable only as ``daemon:<port>`` on the container network.
BIND_HOST_ENV = "TINYASSETS_APP_INGRESS_HOST"
BIND_PORT_ENV = "TINYASSETS_APP_INGRESS_PORT"
DEFAULT_BIND_PORT = 8002


def should_serve(env: Mapping[str, str] | None = None) -> bool:
    """Whether to open the listener at all.

    No usable key means no listener, rather than a listener that refuses every
    request: a port that is not open cannot be probed, misconfigured later, or
    reached through a routing mistake.
    """
    try:
        load_key(env)
    except IngressAuthError:
        return False
    return True


def bind_target(env: Mapping[str, str] | None = None) -> tuple[str, int]:
    """``(host, port)`` for the internal listener."""
    source = env if env is not None else os.environ
    host = (source.get(BIND_HOST_ENV) or "0.0.0.0").strip()
    raw = (source.get(BIND_PORT_ENV) or "").strip()
    try:
        port = int(raw) if raw else DEFAULT_BIND_PORT
    except ValueError:
        raise IngressAuthError("app ingress port is not a number") from None
    if not 1 <= port <= 65535:
        raise IngressAuthError("app ingress port is out of range")
    return host, port


def serve_in_background(env: Mapping[str, str] | None = None) -> bool:
    """Start the ingress on its own port in a daemon thread.

    Returns whether it started. A daemon thread on purpose: this listener must
    never keep the process alive after the MCP server it accompanies has gone.
    """
    if not should_serve(env):
        logger.info("app ingress: no key configured, not serving")
        return False

    import threading

    import uvicorn

    host, port = bind_target(env)

    def _run() -> None:
        uvicorn.run(create_app_ingress_app(), host=host, port=port, log_level="warning")

    threading.Thread(target=_run, name="app-ingress", daemon=True).start()
    logger.info("app ingress: serving on %s:%d (container network only)", host, port)
    return True


def handle_credentials_request(
    *,
    body: bytes,
    headers: Mapping[str, str],
    env: Mapping[str, str] | None = None,
    now: float | None = None,
    resolve: Callable[..., str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """Hand the transport the ONE credential it cannot do without.

    A Socket Mode connection can only be opened by the app-level token
    (``xapp-``, scope ``connections:write``), and the transport is the thing
    holding the socket, so this token has to reach it. Everything else stays
    server-side: the bot token never leaves, because the daemon posts the reply
    itself (:func:`tinyassets.app_ingress.deliver_app_event`).

    That split is the whole reason the agent can stop mounting the production
    volume. It ends up holding one narrowly-scoped token instead of read access
    to every universe's vault.
    """
    lowered = {str(k).lower(): v for k, v in headers.items()}
    try:
        key = load_key(env)
        verify(
            body=body,
            signature=str(lowered.get(SIGNATURE_HEADER, "")),
            timestamp=str(lowered.get(TIMESTAMP_HEADER, "")),
            key=key,
            now=now,
        )
    except IngressAuthError as exc:
        logger.warning("app ingress credentials: refused (%s)", exc)
        return 401, {"error": "unauthenticated"}

    try:
        payload = json.loads(body.decode("utf-8"))
        universe_id = str(payload["universe_id"]).strip()
        connection_id = str(payload.get("connection_id") or "").strip()
        if not universe_id or not connection_id:
            raise ValueError("universe_id and connection_id are required")
    except Exception:  # noqa: BLE001
        return 400, {"error": "malformed"}

    if resolve is None:
        from tinyassets.api.helpers import _universe_dir
        from tinyassets.credential_vault import resolve_slack_app_token

        def resolve(uid: str, cid: str) -> str:
            return resolve_slack_app_token(_universe_dir(uid), cid)

    token = resolve(universe_id, connection_id)
    if not token:
        # Absent is not an error the caller can distinguish from unauthorised
        # by content, but it IS a different status: the transport must be able
        # to say "this universe has no socket credential" at startup rather
        # than retry a signature it got right.
        logger.info("app ingress credentials: no app token deposited")
        return 404, {"error": "no_credential"}
    return 200, {"app_token": token}


def create_app_ingress_app():
    """A Starlette app serving POST ``/app-events`` and nothing else.

    Bind this to the container network only — see the module docstring for why
    it is not a route on the public app.
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _app_events(request):
        body = await request.body()
        status, payload = handle_request(body=body, headers=dict(request.headers))
        return JSONResponse(payload, status_code=status)

    async def _app_credentials(request):
        body = await request.body()
        status, payload = handle_credentials_request(
            body=body, headers=dict(request.headers)
        )
        return JSONResponse(payload, status_code=status)

    return Starlette(
        routes=[
            Route("/app-events", _app_events, methods=["POST"]),
            Route("/app-credentials", _app_credentials, methods=["POST"]),
        ]
    )
