"""The chat transport's side of the authenticated ingress.

This is what lets the Slack agent stop mounting the production volume. Instead
of reading universe state itself — routing, replay admission, founder
recognition, `converse`, the reply post — it signs a description of the event
and the daemon does all of it.

The agent therefore holds no universe data, no vault access and no bot token;
only the socket-level app token and this shared secret.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from tinyassets.app_ingress_http import (
    HMAC_ENV,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    IngressAuthError,
    load_key,
    sign,
)

logger = logging.getLogger(__name__)

#: Where the daemon serves the ingress. Container-network address, never public.
URL_ENV = "TINYASSETS_APP_INGRESS_URL"
DEFAULT_URL = "http://daemon:8002/app-events"

#: One agent turn runs a CLI subprocess, so the daemon holds the connection for
#: as long as the universe takes to think. Generous, but finite: a hung request
#: must not wedge the pump forever.
DEFAULT_TIMEOUT_SECONDS = 300.0


class AppIngressError(Exception):
    """The delivery did not happen. The caller's failure notice should fire."""


@dataclass(frozen=True, slots=True)
class IngressResult:
    handled: bool
    provider_receipt_ref: str = ""


def ingress_url(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    return (source.get(URL_ENV) or DEFAULT_URL).strip()


def build_ingress_client(
    *,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    urlopen: Callable[..., Any] | None = None,
    now: Callable[[], float] = time.time,
) -> Callable[..., IngressResult]:
    """Return ``deliver(**fields) -> IngressResult``.

    Raises :class:`IngressAuthError` at BUILD time when the key is missing, so a
    misconfigured agent fails at startup rather than silently dropping every
    message it is sent.
    """
    key = load_key(env)
    url = ingress_url(env)
    _open = urlopen if urlopen is not None else urllib.request.urlopen

    def _deliver(**fields: str) -> IngressResult:
        body = json.dumps(fields, sort_keys=True).encode("utf-8")
        timestamp = str(int(now()))
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                SIGNATURE_HEADER: sign(body, timestamp, key),
                TIMESTAMP_HEADER: timestamp,
            },
        )
        try:
            with _open(request, timeout=timeout) as response:
                status = int(getattr(response, "status", 0) or 0)
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Deliberately does not log the response body: the daemon answers
            # every auth failure identically, and echoing it into the agent's
            # logs would be the one place the distinction leaks.
            raise AppIngressError(f"app ingress refused the delivery: {exc.code}") from exc
        except Exception as exc:  # noqa: BLE001
            raise AppIngressError("app ingress was unreachable") from exc

        if status != 200 or not isinstance(payload, dict):
            raise AppIngressError("app ingress returned an unusable response")
        return IngressResult(
            handled=bool(payload.get("handled")),
            provider_receipt_ref=str(payload.get("provider_receipt_ref") or ""),
        )

    return _deliver


def fetch_app_token(
    *,
    universe_id: str,
    connection_id: str,
    env: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    urlopen: Callable[..., Any] | None = None,
    now: Callable[[], float] = time.time,
) -> str:
    """The Socket Mode app-level token for one connection.

    The only credential the transport needs, and the reason it no longer mounts
    the production volume. The bot token stays server-side because the daemon
    posts replies itself.

    Raises :class:`AppIngressError` rather than returning "" on failure: a
    transport that starts with no socket credential should die at startup, not
    sit connected to nothing.
    """
    key = load_key(env)
    url = ingress_url(env).replace("/app-events", "/app-credentials")
    _open = urlopen if urlopen is not None else urllib.request.urlopen

    body = json.dumps(
        {"universe_id": universe_id, "connection_id": connection_id},
        sort_keys=True,
    ).encode("utf-8")
    timestamp = str(int(now()))
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            SIGNATURE_HEADER: sign(body, timestamp, key),
            TIMESTAMP_HEADER: timestamp,
        },
    )
    try:
        with _open(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AppIngressError(
            f"app ingress refused the credential request: {exc.code}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise AppIngressError("app ingress was unreachable") from exc

    token = str((payload or {}).get("app_token") or "")
    if not token:
        raise AppIngressError("app ingress returned no app token")
    return token


__all__ = [
    "AppIngressError",
    "IngressAuthError",
    "IngressResult",
    "HMAC_ENV",
    "build_ingress_client",
    "fetch_app_token",
    "ingress_url",
]
