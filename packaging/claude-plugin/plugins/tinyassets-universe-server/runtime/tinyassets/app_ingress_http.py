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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

_authenticated_app_transport: ContextVar[bool] = ContextVar(
    "tinyassets_authenticated_app_transport",
    default=False,
)


def authenticated_app_transport() -> bool:
    """Whether the current delivery crossed the signed ingress boundary."""

    return _authenticated_app_transport.get()


# --- best-effort, BOUNDED user-notice sender --------------------------------
# Notices for conditions AROUND a turn (an overload refusal, a fault that escaped
# the turn's own notice) must never block the event loop, never tie up a turn
# worker, and never let an unreachable Slack amplify a request flood into thread-
# pool exhaustion (Codex #4). They run on a tiny dedicated pool with a hard
# in-flight cap; past the cap a notice is DROPPED with a log rather than queued
# unbounded — a best-effort courtesy, never a correctness dependency.
_NOTIFIER: ThreadPoolExecutor | None = None
_NOTIFIER_LOCK = threading.Lock()
_NOTIFIER_INFLIGHT = 0
_NOTIFIER_MAX_WORKERS = 2
_NOTIFIER_MAX_INFLIGHT = 8


def _fire_best_effort_notice(fn: Callable[[], Any]) -> bool:
    """Run ``fn`` (a notice post) off the loop, bounded + drop-on-saturation.

    Returns True if scheduled, False if dropped because the notifier is saturated.
    """
    global _NOTIFIER, _NOTIFIER_INFLIGHT
    with _NOTIFIER_LOCK:
        if _NOTIFIER_INFLIGHT >= _NOTIFIER_MAX_INFLIGHT:
            logger.warning("app ingress: dropping a user notice (notifier saturated)")
            return False
        if _NOTIFIER is None:
            _NOTIFIER = ThreadPoolExecutor(
                max_workers=_NOTIFIER_MAX_WORKERS,
                thread_name_prefix="ingress-notice",
            )
        _NOTIFIER_INFLIGHT += 1
        pool = _NOTIFIER

    # Release the reserved permit EXACTLY ONCE. `pool.submit` in CPython enqueues
    # the work item BEFORE it starts a worker thread, so a thread-creation failure
    # can both raise (our except path) AND later run `_wrapped` (its finally) — the
    # permit would be released twice, driving the counter negative and defeating
    # the cap (Codex round-4 #1). A shared, lock-guarded latch makes it idempotent.
    released = [False]

    def _release() -> None:
        global _NOTIFIER_INFLIGHT
        with _NOTIFIER_LOCK:
            if released[0]:
                return
            released[0] = True
            _NOTIFIER_INFLIGHT -= 1

    def _wrapped() -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001 - a notice is best-effort
            logger.exception("app ingress: best-effort notice failed")
        finally:
            _release()

    try:
        pool.submit(_wrapped)
    except Exception:  # noqa: BLE001 - scheduling failed (pool saturated / no thread)
        # Release the permit (idempotently — a partially-enqueued `_wrapped` may
        # still run and release it too) and DO NOT raise: the caller (the overload
        # path) must still return its 503 immediately (Codex #3/#4-r4).
        _release()
        logger.exception("app ingress: could not schedule a user notice")
        return False
    return True

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
    accepted = _authenticate_and_accept(
        body=body, headers=headers, env=env, now=now,
    )
    if isinstance(accepted, tuple):  # (status, error_payload)
        return accepted
    fields = accepted

    if deliver is None:
        from tinyassets.app_ingress import deliver_app_event as deliver

    transport_token = _authenticated_app_transport.set(True)
    try:
        result = deliver(**fields)
    finally:
        _authenticated_app_transport.reset(transport_token)
    return 200, {
        "handled": bool(getattr(result, "handled", False)),
        "provider_receipt_ref": str(getattr(result, "provider_receipt_ref", "")),
    }


def _authenticate_and_accept(
    *,
    body: bytes,
    headers: Mapping[str, str],
    env: Mapping[str, str] | None = None,
    now: float | None = None,
) -> dict[str, Any] | tuple[int, dict[str, Any]]:
    """The FAST, synchronous half of ingress: HMAC-verify + parse the event.

    Returns the accepted ``fields`` dict on success, or a ``(status, payload)``
    error tuple (401 unauthenticated / 400 malformed). Split out (Slice 2) so the
    ingress can authenticate+parse on the event loop and then offload the SLOW
    ``deliver`` turn to a bounded worker instead of blocking the loop.
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
        return _accepted(payload)
    except Exception:  # noqa: BLE001
        logger.warning("app ingress: malformed body")
        return 400, {"error": "malformed"}


def _conversation_key(fields: Mapping[str, Any]) -> tuple[str, str, str]:
    """The per-conversation FIFO key: (workspace, channel, thread) (Slice 2).

    Turns for the same channel+thread execute in arrival order; different
    conversations run concurrently. A thread reply groups under its thread; a
    top-level message keys on the channel itself.
    """
    return (
        str(fields.get("workspace_id") or ""),
        str(fields.get("channel_id") or ""),
        str(fields.get("thread_ts") or fields.get("channel_id") or ""),
    )


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
        resolve = _resolve_socket_identity

    # A resolver may return the bare token (tests, and the original shape) or
    # the full identity mapping. Both are accepted so the security tests can
    # stay focused on auth without also standing up an identity fixture.
    result = resolve(universe_id, connection_id)
    if isinstance(result, dict):
        token = str(result.get("app_token") or "")
    else:
        token = str(result or "")
    if not token:
        # Absent is not an error the caller can distinguish from unauthorised
        # by content, but it IS a different status: the transport must be able
        # to say "this universe has no socket credential" at startup rather
        # than retry a signature it got right.
        logger.info("app ingress credentials: no app token deposited")
        return 404, {"error": "no_credential"}
    if not isinstance(result, dict):
        return 200, {"app_token": token}
    return 200, {
        "app_token": token,
        "team_id": str(result.get("team_id") or ""),
        "bot_user_id": str(result.get("bot_user_id") or ""),
        "api_app_id": str(result.get("api_app_id") or ""),
    }


def _resolve_socket_identity(universe_id: str, connection_id: str) -> dict[str, str]:
    """The app token plus who the transport is, resolved server-side.

    The identity is here rather than in the transport because the transport
    used to learn it by calling Slack's `auth.test` with the BOT token — the one
    credential this rework deliberately keeps on the server. Sending the bot
    token out just so the agent can ask Slack its own name would give back
    everything the move was for.
    """
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.credential_vault import resolve_slack_app_token, resolve_slack_token
    from tinyassets.effectors.slack_socket_mode import app_id_from_token
    from tinyassets.slack_agent_worker import _identify

    universe_dir = _universe_dir(universe_id)
    app_token = resolve_slack_app_token(universe_dir, connection_id)
    if not app_token:
        return {}
    bot_token = resolve_slack_token(universe_dir, connection_id)
    team_id, bot_user_id = _identify(bot_token) if bot_token else ("", "")
    return {
        "app_token": app_token,
        "team_id": team_id,
        "bot_user_id": bot_user_id,
        "api_app_id": app_id_from_token(app_token),
    }


def create_app_ingress_app():
    """A Starlette app serving POST ``/app-events`` and nothing else.

    Bind this to the container network only — see the module docstring for why
    it is not a route on the public app.
    """
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _app_events(request):
        # Slice 2: authenticate + parse on the event loop (fast, so 401/400 stay
        # synchronous), then OFFLOAD the slow deliver-turn to a bounded per-
        # conversation worker so one long turn never head-of-line-blocks another
        # conversation. The daemon posts the reply to Slack itself, so the turn
        # can run after this ack.
        body = await request.body()
        headers = dict(request.headers)
        accepted = _authenticate_and_accept(body=body, headers=headers)
        if isinstance(accepted, tuple):  # (status, error_payload) — 401 / 400
            return JSONResponse(accepted[1], status_code=accepted[0])
        fields = accepted

        def _run_turn() -> None:
            # ContextVars do NOT cross threads — set the authenticated-transport
            # marker INSIDE the worker, not on the event loop.
            from tinyassets.app_ingress import (
                _failure_notice,
                deliver_app_event,
                deliver_app_notice,
            )
            token = _authenticated_app_transport.set(True)
            try:
                deliver_app_event(**fields)
            except Exception as exc:  # noqa: BLE001
                # deliver_app_event owns its own honest notice AND posts at most
                # once per turn, swallowing post/record faults; so reaching here is
                # a genuine PRE-post fault (nothing was posted). Surface it (Codex
                # adapt #3) — off the worker via the bounded notifier so a down
                # Slack cannot tie up this turn slot, and never double-posting
                # (Codex #3: the only escapes left are pre-post).
                logger.exception("app ingress: turn escaped before any post")
                exc_for_notice = exc
                _fire_best_effort_notice(
                    lambda: deliver_app_notice(
                        **fields, notice=_failure_notice(exc_for_notice),
                    )
                )
            finally:
                _authenticated_app_transport.reset(token)

        from tinyassets.app_ingress_workers import get_ingress_executor
        admitted = get_ingress_executor().submit(
            _conversation_key(fields), _run_turn,
        )
        if not admitted:
            # Bounded backlog full — truthful overload, NOT a silent drop. Tell the
            # USER (Codex adapt #3): a 503 the transport swallows leaves the user on
            # silence. Fire the busy notice best-effort + bounded and return the 503
            # IMMEDIATELY (Codex #4) — never awaiting Slack, so an unreachable Slack
            # cannot stall ingress or exhaust the shared threadpool.
            logger.warning("app ingress: overloaded, refusing turn (backlog full)")
            from tinyassets.app_ingress import OVERLOADED_NOTICE, deliver_app_notice
            _fire_best_effort_notice(
                lambda: deliver_app_notice(**fields, notice=OVERLOADED_NOTICE)
            )
            return JSONResponse(
                {"handled": False, "overloaded": True}, status_code=503,
            )
        return JSONResponse({"handled": True, "queued": True}, status_code=200)

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
