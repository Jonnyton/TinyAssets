"""Provider-neutral Realtime voice session broker for the shared app.

Realtime is an auxiliary speech transport, never a TinyAssets writer. A
universe opts in by binding an existing generic HTTP connection through a small
``voice-connection.json`` manifest. The remote bridge implements the public
TinyAssets voice protocol and may be backed by any service or local resource;
this module contains no service-specific endpoint, model, credential name, or
wire-event vocabulary. SDP signaling stays on the authenticated same-origin
route, so no temporary bearer or remote HTTP URL is exposed to the browser.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

VOICE_BINDING_FILENAME = "voice-connection.json"
VOICE_PROTOCOL = "tinyassets.voice.v1"
VOICE_DISCLOSURE_VERSION = 3
VOICE_SESSION_MAX_SECONDS = 30 * 60
VOICE_SESSION_WINDOW_SECONDS = 60.0
VOICE_SESSIONS_PER_WINDOW = 10
_MAX_BINDING_BYTES = 16 * 1024
_MAX_SERVICE_NAME_CHARS = 80
_MAX_URL_CHARS = 2048
_MAX_SDP_CHARS = 64 * 1024
_TRUTHY = {"1", "true", "yes", "on"}
_REF_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,190}$")
_session_buckets: dict[str, tuple[float, int]] = {}

ProxyFactory = Callable[[Path, str, "VoiceBinding"], Any]


class RealtimeVoiceError(RuntimeError):
    """A stable, secret-free failure suitable for the app boundary."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class VoiceBinding:
    """Validated, non-secret reference to one universe-owned voice bridge."""

    connection_id: str
    grant_id: str
    session_url: str
    service_name: str
    privacy_url: str


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def realtime_voice_enabled() -> bool:
    """True only when the app and both outbound kill switches are enabled."""

    return (
        _truthy("TINYASSETS_REALTIME_VOICE_ENABLED")
        and _truthy("TINYASSETS_ALLOW_REALTIME_VOICE_API")
        and _truthy("TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED")
    )


def public_voice_config() -> dict[str, Any]:
    """Non-secret configuration injected into the shared browser client."""

    return {
        "enabled": realtime_voice_enabled(),
        "protocol": VOICE_PROTOCOL,
        "disclosure_version": VOICE_DISCLOSURE_VERSION,
        "max_session_seconds": VOICE_SESSION_MAX_SECONDS,
    }


def _https_url(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text or len(text) > _MAX_URL_CHARS:
        raise RealtimeVoiceError("voice_binding_invalid", 409)
    parts = urlsplit(text)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise RealtimeVoiceError("voice_binding_invalid", 409)
    try:
        _ = parts.port
    except ValueError as exc:
        raise RealtimeVoiceError("voice_binding_invalid", 409) from exc
    return text


def load_voice_binding(universe_dir: str | Path) -> VoiceBinding:
    """Load a bounded, non-symlinked universe voice binding or fail loudly."""

    path = Path(universe_dir) / VOICE_BINDING_FILENAME
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > _MAX_BINDING_BYTES
        ):
            raise RealtimeVoiceError("voice_compatible_resource_required", 409)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except RealtimeVoiceError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RealtimeVoiceError("voice_binding_invalid", 409) from exc
    if not isinstance(payload, dict) or payload.get("schema") != VOICE_PROTOCOL:
        raise RealtimeVoiceError("voice_binding_invalid", 409)
    required = {"schema", "connection_id", "grant_id", "session_url", "service_name"}
    allowed = required | {"privacy_url"}
    if not required.issubset(payload) or not set(payload).issubset(allowed):
        raise RealtimeVoiceError("voice_binding_invalid", 409)

    connection_id = payload.get("connection_id")
    grant_id = payload.get("grant_id")
    if (
        not isinstance(connection_id, str)
        or not _REF_RE.fullmatch(connection_id)
        or not isinstance(grant_id, str)
        or not _REF_RE.fullmatch(grant_id)
    ):
        raise RealtimeVoiceError("voice_binding_invalid", 409)
    service_name = payload.get("service_name")
    if (
        not isinstance(service_name, str)
        or not 1 <= len(service_name.strip()) <= _MAX_SERVICE_NAME_CHARS
        or any(ord(char) < 32 for char in service_name)
    ):
        raise RealtimeVoiceError("voice_binding_invalid", 409)
    privacy = payload.get("privacy_url")
    privacy_url = "" if privacy is None or privacy == "" else _https_url(privacy)
    return VoiceBinding(
        connection_id=connection_id,
        grant_id=grant_id,
        session_url=_https_url(payload.get("session_url")),
        service_name=service_name.strip(),
        privacy_url=privacy_url,
    )


def _binding_authorized(
    universe_dir: Path, owner_user_id: str, binding: VoiceBinding
) -> bool:
    from tinyassets.storage.outbound_connections import (
        ConnectionLedger,
        _enforce_endpoint_allowlist,
        _parse_canonical_https_url,
    )

    db_path = universe_dir.parent / "outbound.db"
    if db_path.is_symlink() or not db_path.is_file():
        return False
    ledger = ConnectionLedger(db_path)
    grant = ledger.get_grant(binding.grant_id)
    view = ledger.get_connection_view(binding.connection_id)
    authorized = bool(
        grant is not None
        and view is not None
        and grant.revoked_at is None
        and view.revoked_at is None
        and grant.connection_id == binding.connection_id
        and grant.owner_user_id == owner_user_id
        and view.owner_user_id == owner_user_id
        and grant.universe_id == universe_dir.name
        and view.connection_type == "http"
        and "POST" in view.scopes
    )
    if not authorized:
        return False
    try:
        canonical = _parse_canonical_https_url(
            binding.session_url, allowed_ports=frozenset({443})
        )
        _enforce_endpoint_allowlist(
            canonical,
            "POST",
            view.allowed_endpoints,
            view.access_mode,
        )
    except Exception:
        return False
    return True


def voice_capability(
    universe_dir: str | Path | None, owner_user_id: str = ""
) -> dict[str, Any]:
    """Return a secret-free view of one universe's bound voice capability."""

    if not realtime_voice_enabled():
        return {"available": False, "state": "disabled", "reason": "voice_disabled"}
    if universe_dir is None or not owner_user_id:
        return {
            "available": False,
            "state": "locked",
            "reason": "no_home_universe",
        }
    try:
        universe = Path(universe_dir).resolve()
        binding = load_voice_binding(universe)
        authorized = _binding_authorized(universe, owner_user_id, binding)
    except RealtimeVoiceError as exc:
        return {"available": False, "state": "locked", "reason": exc.code}
    except Exception:
        return {
            "available": False,
            "state": "locked",
            "reason": "voice_binding_invalid",
        }
    if not authorized:
        return {
            "available": False,
            "state": "locked",
            "reason": "voice_compatible_resource_required",
        }
    return {
        "available": True,
        "state": "ready",
        "resource": "user_bound_voice_connection",
        "service_name": binding.service_name,
        "privacy_url": binding.privacy_url,
    }


def allow_voice_session(user_id: str, *, now: float | None = None) -> bool:
    """Bound accidental/replayed session creation for one authenticated owner."""

    moment = time.monotonic() if now is None else now
    start, count = _session_buckets.get(user_id, (moment, 0))
    if moment - start >= VOICE_SESSION_WINDOW_SECONDS:
        start, count = moment, 0
    if count >= VOICE_SESSIONS_PER_WINDOW:
        return False
    _session_buckets[user_id] = (start, count + 1)
    return True


def session_request(offer_sdp: str) -> dict[str, Any]:
    """Provider-neutral bridge contract; the browser cannot widen it."""

    return {
        "protocol": VOICE_PROTOCOL,
        "offer_sdp": offer_sdp,
        "session": {
            "instructions": (
                "Act only as the speech interface for this universe. For each "
                "completed utterance, invoke converse exactly once. Speak only "
                "the returned tool result and add nothing."
            ),
            "turn_detection": {
                "mode": "semantic",
                "eagerness": "medium",
                "interrupt_output": True,
            },
            "tool": {
                "name": "converse",
                "description": (
                    "Send the founder's complete spoken turn to their universe."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"],
                    "additionalProperties": False,
                },
            },
            "output": {
                "mode": "audio",
                "source": "tool_result",
                "verbatim": True,
            },
        },
    }


def _default_proxy_factory(
    universe_dir: Path, owner_user_id: str, binding: VoiceBinding
) -> Any:
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(
        universe_dir.parent / "outbound.db",
        verify_authenticated_principal=lambda: owner_user_id,
    )
    return ledger.resolve_exact_scoped_proxy(
        universe_id=universe_dir.name,
        grant_id=binding.grant_id,
        connection_id=binding.connection_id,
    )


def _response_document(response: Any) -> tuple[int, dict[str, Any]]:
    if not isinstance(response, dict):
        raise RealtimeVoiceError("voice_resource_bad_response", 502)
    status = response.get("status", 200)
    if not isinstance(status, int) or isinstance(status, bool):
        raise RealtimeVoiceError("voice_resource_bad_response", 502)
    raw = response.get("body", response)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RealtimeVoiceError("voice_resource_bad_response", 502) from exc
    if not isinstance(raw, dict):
        raise RealtimeVoiceError("voice_resource_bad_response", 502)
    return status, raw


async def create_voice_session(
    universe_dir: str | Path,
    owner_user_id: str,
    offer_sdp: str,
    *,
    proxy_factory: ProxyFactory = _default_proxy_factory,
) -> dict[str, Any]:
    """Exchange one bounded browser SDP offer through the bound voice bridge."""

    if not realtime_voice_enabled():
        raise RealtimeVoiceError("voice_disabled", 404)
    if (
        not isinstance(offer_sdp, str)
        or not 1 <= len(offer_sdp) <= _MAX_SDP_CHARS
        or not offer_sdp.startswith("v=0")
        or "\x00" in offer_sdp
    ):
        raise RealtimeVoiceError("voice_session_offer_invalid", 400)
    universe = Path(universe_dir).resolve()
    binding = load_voice_binding(universe)
    if not _binding_authorized(universe, owner_user_id, binding):
        raise RealtimeVoiceError("voice_compatible_resource_required", 409)

    from starlette.concurrency import run_in_threadpool

    def request_session() -> Any:
        proxy = None
        try:
            proxy = proxy_factory(universe, owner_user_id, binding)
            return proxy.request(
                "POST",
                {
                    "url": binding.session_url,
                    "headers": {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    "body": session_request(offer_sdp),
                },
            )
        finally:
            if proxy is not None:
                try:
                    proxy.close()
                except Exception:
                    pass

    try:
        response = await run_in_threadpool(request_session)
    except RealtimeVoiceError:
        raise
    except Exception as exc:
        raise RealtimeVoiceError("voice_resource_unreachable", 502) from exc

    status, payload = _response_document(response)
    if status == 429:
        raise RealtimeVoiceError("voice_resource_rate_limited", 503)
    if status in {401, 403}:
        raise RealtimeVoiceError("voice_resource_rejected", 409)
    if not 200 <= status < 300:
        raise RealtimeVoiceError("voice_resource_failed", 502)
    if payload.get("protocol") != VOICE_PROTOCOL:
        raise RealtimeVoiceError("voice_resource_bad_response", 502)
    answer_sdp = payload.get("answer_sdp")
    if (
        not isinstance(answer_sdp, str)
        or not 1 <= len(answer_sdp) <= _MAX_SDP_CHARS
        or not answer_sdp.startswith("v=0")
        or "\x00" in answer_sdp
    ):
        raise RealtimeVoiceError("voice_resource_bad_response", 502)
    try:
        expires_at = int(payload.get("expires_at") or 0)
        requested_limit = int(payload.get("max_session_seconds") or 0)
    except (TypeError, ValueError) as exc:
        raise RealtimeVoiceError("voice_resource_bad_response", 502) from exc
    session_limit = max(
        60,
        min(
            requested_limit or VOICE_SESSION_MAX_SECONDS,
            VOICE_SESSION_MAX_SECONDS,
        ),
    )
    return {
        "protocol": VOICE_PROTOCOL,
        "answer_sdp": answer_sdp,
        "expires_at": expires_at,
        "max_session_seconds": session_limit,
    }


__all__ = [
    "VOICE_BINDING_FILENAME",
    "VOICE_DISCLOSURE_VERSION",
    "VOICE_SESSIONS_PER_WINDOW",
    "VOICE_SESSION_WINDOW_SECONDS",
    "VOICE_PROTOCOL",
    "RealtimeVoiceError",
    "VoiceBinding",
    "allow_voice_session",
    "create_voice_session",
    "load_voice_binding",
    "public_voice_config",
    "realtime_voice_enabled",
    "session_request",
    "voice_capability",
]
