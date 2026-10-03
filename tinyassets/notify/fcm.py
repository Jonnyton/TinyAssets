"""Firebase Cloud Messaging HTTP v1, for the Android shell.

The credential is a service-account JSON supplied to the process and never to
a caller. It is exchanged for a short-lived access token by signing a JWT with
the account's own key (PyJWT + cryptography, both already declared
dependencies) -- no SDK, no extra dependency, and no long-lived bearer sitting
in a header the whole time.

Everything a caller could influence is absent by construction: the endpoint is
derived from the credential's own ``project_id``, the registration token comes
from the owner's device row, and the body comes from the server-composed
:class:`~tinyassets.notify.Notification`. The only thing read from the wire is
the HTTP status and FCM's own error code, and neither is forwarded as text.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from tinyassets.notify import (
    OUTCOME_REFUSED,
    OUTCOME_SENT,
    OUTCOME_UNAVAILABLE,
    Notification,
    TransportFailed,
    TransportGone,
)

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TIMEOUT_S = 10.0
#: Refresh a little before the hour is up, so a send never races expiry.
_TOKEN_SKEW_S = 300

#: FCM's own codes for "this registration is dead". Anything else is a
#: transport failure, so a transient 503 never retires a live device.
_GONE_CODES = frozenset({"UNREGISTERED", "NOT_FOUND", "INVALID_ARGUMENT"})


class _AccessToken:
    """One cached access token per credential, refreshed under a lock."""

    def __init__(self, credential: dict[str, Any]) -> None:
        self._credential = credential
        self._lock = threading.Lock()
        self._value = ""
        self._expires_at = 0.0

    def get(self) -> str:
        with self._lock:
            if self._value and time.time() < self._expires_at - _TOKEN_SKEW_S:
                return self._value
            self._value, self._expires_at = self._mint()
            return self._value

    def _mint(self) -> tuple[str, float]:
        import jwt

        now = int(time.time())
        assertion = jwt.encode(
            {
                "iss": self._credential["client_email"],
                "scope": _SCOPE,
                "aud": _TOKEN_URL,
                "iat": now,
                "exp": now + 3600,
            },
            self._credential["private_key"],
            algorithm="RS256",
        )
        body = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }).encode("utf-8")
        request = urllib.request.Request(
            _TOKEN_URL, data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                document = json.loads(response.read(64_000).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # A rejected assertion is a configuration fault; its response body
            # can echo the account address, so only the status is logged.
            logger.error("notify.fcm: token exchange refused (HTTP %s)", exc.code)
            raise TransportFailed(
                OUTCOME_REFUSED if exc.code in (400, 401, 403) else OUTCOME_UNAVAILABLE
            ) from None
        except Exception:  # noqa: BLE001 - network, DNS, TLS, malformed JSON
            logger.warning("notify.fcm: token exchange unavailable", exc_info=False)
            raise TransportFailed(OUTCOME_UNAVAILABLE) from None
        token = str(document.get("access_token") or "")
        if not token:
            raise TransportFailed(OUTCOME_REFUSED)
        lifetime = float(document.get("expires_in") or 3600)
        return token, time.time() + lifetime


def _message(device: dict, notification: Notification) -> dict[str, Any]:
    """The FCM v1 message: DATA ONLY, for every kind.

    The Android app builds the notification itself (``TinyAssetsMessagingService``)
    because the system tray cannot carry an inline Reply action, and a message
    carrying a ``notification`` block is displayed by the system without ever
    reaching the app's code. So the words travel as ``data.title`` /
    ``data.body`` -- server-composed, exactly the strings the web transport
    shows -- and a ``clear`` is the same shape with no words, which the app
    turns into a cancel of the notification tagged with the request id.

    ``priority`` is high for a visible notification (the owner is being asked
    something) and normal for a silent clear. Everything here is derived from
    ``notification``; nothing a caller supplies names a field.
    """
    data = {str(k): str(v) for k, v in notification.data.items()}
    # Whose message this is, from the device row the SERVER resolved -- never
    # from the notification's own data, so content cannot claim another owner.
    if device.get("recipient"):
        data["recipient"] = str(device["recipient"])
    if not notification.silent:
        data["title"] = notification.title
        data["body"] = notification.body
    return {
        "token": device["token"],
        "data": data,
        "android": {"priority": "normal" if notification.silent else "high"},
    }


def fcm_transport(env: dict[str, str]):
    """Build the Android transport, or raise ValueError on a bad credential."""
    raw = (env.get("TINYASSETS_FCM_SERVICE_ACCOUNT_JSON") or "").strip()
    try:
        credential = json.loads(raw)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("service account is not JSON") from exc
    if not isinstance(credential, dict):
        raise ValueError("service account is not an object")
    missing = [
        key for key in ("project_id", "client_email", "private_key")
        if not str(credential.get(key) or "").strip()
    ]
    if missing:
        raise ValueError("service account is missing " + ", ".join(missing))
    endpoint = (
        "https://fcm.googleapis.com/v1/projects/"
        f"{credential['project_id']}/messages:send"
    )
    access = _AccessToken(credential)

    def send(device: dict, notification: Notification) -> str:
        body = json.dumps({"message": _message(device, notification)}).encode("utf-8")
        request = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {access.get()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
                response.read(8192)
            return OUTCOME_SENT
        except urllib.error.HTTPError as exc:
            code = _error_code(exc)
            if exc.code in (400, 404) and code in _GONE_CODES:
                raise TransportGone(code) from None
            logger.warning("notify.fcm: send refused (HTTP %s)", exc.code)
            raise TransportFailed(
                OUTCOME_REFUSED if 400 <= exc.code < 500 else OUTCOME_UNAVAILABLE
            ) from None
        except Exception:  # noqa: BLE001 - network, DNS, TLS
            raise TransportFailed(OUTCOME_UNAVAILABLE) from None

    return send


def _error_code(exc: urllib.error.HTTPError) -> str:
    """FCM's own error enum, or "". Reads ONE field and never returns text."""
    try:
        document = json.loads(exc.read(16_000).decode("utf-8"))
    except Exception:  # noqa: BLE001 - a body we cannot parse names nothing
        return ""
    details = ((document.get("error") or {}).get("details") or [])
    for entry in details if isinstance(details, list) else []:
        if isinstance(entry, dict) and entry.get("errorCode"):
            return str(entry["errorCode"])[:40]
    status = (document.get("error") or {}).get("status")
    return str(status)[:40] if status else ""


__all__ = ["fcm_transport"]
