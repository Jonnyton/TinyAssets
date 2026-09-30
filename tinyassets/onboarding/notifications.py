"""The app's notification routes: register a device, list them, turn them off.

This is the registration the requests system has been missing since it existed
-- its own docstring named it ("a phone *notification* additionally needs
device registration, which does not exist yet"). With these routes the
delivery surface built in `tinyassets/owner_notifications.py` stops being dark.

The owner is always the AUTHENTICATED subject
-------------------------------------------
Every handler takes the subject from the resolved request identity and passes
it explicitly to the store, which has no other way to be told whose device a
row is. No body field names a subject, a universe or a destination. The store
enforces the same rule again (`owner_devices`), so neither layer is trusting
the other's word for it.

A token is write-only across this surface
-----------------------------------------
``POST /app/devices`` accepts a token; ``GET /app/devices`` never returns one.
A read that returned token material would be replayable as a send.

The service worker is the one public route here
-----------------------------------------------
A browser fetches a service worker with NO bearer -- `register()` is a plain
same-origin fetch -- so `/app/sw.js` has to be reachable unauthenticated or
web push can never be set up. It is a static script that carries no secret:
the VAPID *public* key is handed to `pushManager.subscribe` by the
already-authenticated page, not baked in here. That is the same carve-out, for
the same stated reason, that `/app` and `/app/token` already have.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: A registration body is three short fields. Bounded so registration cannot be
#: used as storage; the store bounds the token again.
MAX_BODY_BYTES = 8192

#: Served at ``/app/sw.js``. Handles a push event and a notification click, and
#: nothing else -- it holds no key, no token and no identity, so it is safe to
#: serve unauthenticated. `data.request_id` is what makes the click land on the
#: right request; a `clear` message cancels by the same tag instead of showing.
SERVICE_WORKER = """\
// TinyAssets web push. Served unauthenticated on purpose: a browser fetches a
// service worker with no bearer. It carries no key and no identity.
self.addEventListener('activate', function (event) {
  event.waitUntil(clients.claim());
});
self.addEventListener('push', function (event) {
  if (!event.data) return;
  var payload;
  try { payload = event.data.json(); } catch (e) { return; }
  var data = payload.data || {};
  var tag = data.request_id || 'tinyassets';
  if (payload.silent || data.kind === 'clear') {
    // The owner answered somewhere else: take this notification down rather
    // than showing anything.
    event.waitUntil(self.registration.getNotifications({tag: tag}).then(
      function (open) { open.forEach(function (n) { n.close(); }); }
    ));
    return;
  }
  event.waitUntil(self.registration.showNotification(payload.title || '', {
    body: payload.body || '',
    tag: tag,
    renotify: false,
    data: data
  }));
});

self.addEventListener('notificationclick', function (event) {
  var data = (event.notification && event.notification.data) || {};
  event.notification.close();
  var target = '/app' + (data.request_id ? '?request=' + encodeURIComponent(
    data.request_id) : '');
  if (data.request_id && data.item_id) target += '&item=' + encodeURIComponent(data.item_id);
  event.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true})
    .then(function (windows) {
      for (var i = 0; i < windows.length; i++) {
        var url = new URL(windows[i].url);
        if (url.origin === self.location.origin && url.pathname === '/app'
            && 'focus' in windows[i]) {
          return windows[i].navigate(target).then(function (client) {
            return client ? client.focus() : clients.openWindow(target);
          }).catch(function () {
            return clients.openWindow(target);
          });
        }
      }
      return clients.openWindow(target);
    }));
});
"""


async def _body(request: Any) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("body is too large")
    try:
        document = json.loads(raw or b"{}")
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("body must be JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("body must be a JSON object")
    return document


def _subject() -> str:
    from tinyassets.auth.middleware import current_identity_or_none

    identity = current_identity_or_none()
    return (getattr(identity, "user_id", "") or "").strip() if identity else ""


async def handle_service_worker(request: Any) -> Any:
    """The web-push service worker. Public, static, secret-free."""
    from starlette.responses import PlainTextResponse, Response

    from tinyassets.onboarding import onboarding_enabled

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    if request.method == "HEAD":
        return Response(status_code=200, media_type="application/javascript")
    return Response(
        SERVICE_WORKER,
        media_type="application/javascript",
        # Scope has to cover /app; the header is what allows that from /app/sw.js.
        headers={"Service-Worker-Allowed": "/app", "Cache-Control": "no-cache"},
    )


async def handle_devices(request: Any) -> Any:
    """``GET`` the caller's own devices; ``POST`` registers or retires one."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.onboarding import _app_identity_required, onboarding_enabled

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    owner = _subject()
    if not owner:
        return JSONResponse({"error": "authentication_required"}, status_code=401)

    from tinyassets.api.helpers import _base_path
    from tinyassets.storage import owner_devices as devices

    if request.method == "GET":
        listed = await run_in_threadpool(
            devices.list_devices, _base_path(), owner_user_id=owner,
        )
        enabled = await run_in_threadpool(
            devices.notifications_enabled, _base_path(), owner_user_id=owner,
        )
        return JSONResponse({"devices": listed, "notifications_enabled": enabled})

    try:
        document = await _body(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    if document.get("operation") == "retire":
        device_id = str(document.get("device_id") or "").strip()
        retired = await run_in_threadpool(
            devices.retire_device, _base_path(),
            owner_user_id=owner, device_id=device_id, reason="owner",
        )
        # Not found and not-yours are the same answer, so this cannot be used
        # to probe which device ids exist.
        return JSONResponse({"retired": bool(retired)})

    try:
        result = await run_in_threadpool(
            devices.register_device, _base_path(),
            owner_user_id=owner,
            platform=str(document.get("platform") or ""),
            token=document.get("token"),
            label=str(document.get("label") or ""),
        )
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception:  # noqa: BLE001 - a store fault is not the caller's fault
        logger.warning("app: device registration failed", exc_info=True)
        return JSONResponse(
            {"error": "device_registration_unavailable"}, status_code=503,
        )
    return JSONResponse({"device_id": result["device_id"],
                         "platform": result["platform"]})


async def handle_notify_settings(request: Any) -> Any:
    """``GET``/``POST`` the owner's own notifications on/off switch."""
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse, PlainTextResponse

    from tinyassets.onboarding import _app_identity_required, onboarding_enabled

    if not onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404)
    denied = _app_identity_required()
    if denied is not None:
        return denied
    owner = _subject()
    if not owner:
        return JSONResponse({"error": "authentication_required"}, status_code=401)

    from tinyassets.api.helpers import _base_path
    from tinyassets.storage import owner_devices as devices

    if request.method == "GET":
        enabled = await run_in_threadpool(
            devices.notifications_enabled, _base_path(), owner_user_id=owner,
        )
        return JSONResponse({"enabled": enabled, "vapid_public_key": _vapid_public()})

    try:
        document = await _body(request)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if not isinstance(document.get("enabled"), bool):
        return JSONResponse({"error": "enabled must be true or false"},
                            status_code=400)
    await run_in_threadpool(
        devices.set_notifications_enabled, _base_path(),
        owner_user_id=owner, enabled=document["enabled"],
    )
    return JSONResponse({"enabled": document["enabled"]})


def _vapid_public() -> str:
    """The web-push application server key the BROWSER needs, or "".

    Public by design -- it is what `pushManager.subscribe` sends to the push
    service. Derived from the configured private key rather than read from a
    second variable, so the two cannot drift; "" when web push is unconfigured,
    which the client reads as "do not offer this".
    """
    import base64
    import os

    pem = (os.environ.get("TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY") or "").strip()
    if not pem:
        return ""
    try:
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
        raw = key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    except Exception:  # noqa: BLE001 - a key we cannot load offers nothing
        logger.error("app: VAPID key is not usable; web push stays off")
        return ""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


__all__ = [
    "SERVICE_WORKER",
    "handle_devices",
    "handle_notify_settings",
    "handle_service_worker",
]
