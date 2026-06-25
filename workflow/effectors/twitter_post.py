"""X/Twitter post external-write effector for PR-173.

Consumes ``external_write_packet`` values whose sink is ``twitter_post`` and
posts them through X API v2 using OAuth 1.0a user-context credentials. This
adapter is intentionally standalone rather than sharing GitHub PR adapter code:
twitter posting has a separate authority, credential, idempotency, and evidence
shape.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workflow.effectors.authority import DENIED as SOUL_AUTHORITY_DENIED
from workflow.effectors.authority import resolve_soul_effect_authority

logger = logging.getLogger(__name__)

EXTERNAL_WRITE_SINK_TWITTER_POST = "twitter_post"

_DRY_RUN_ENV = "WORKFLOW_EXTERNAL_WRITE_DRY_RUN"
_DEFAULT_HANDLE = "@kwisatzh4derach"
_TWEETS_URL = "https://api.x.com/2/tweets"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class TwitterCredentials:
    api_key: str
    api_secret: str
    access_token: str
    access_token_secret: str
    source: str


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _parse_packet(value: Any) -> dict[str, Any] | None:
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
    if packet.get("sink") != EXTERNAL_WRITE_SINK_TWITTER_POST:
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


def _destination(packet: dict[str, Any]) -> str:
    value = packet.get("destination")
    if isinstance(value, str):
        return value.strip()
    return ""


def _payload(packet: dict[str, Any]) -> dict[str, Any]:
    value = packet.get("payload")
    return value if isinstance(value, dict) else {}


def _text(packet: dict[str, Any]) -> str:
    value = _payload(packet).get("text")
    if isinstance(value, str):
        return value.strip()
    return ""


def _optional_tweet_id(packet: dict[str, Any], key: str) -> str:
    value = _payload(packet).get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_handle(value: str) -> str:
    raw = value.strip()
    if raw.lower() in {"", "x:self", "self", "@self"}:
        return _DEFAULT_HANDLE
    if raw.lower().startswith("x:"):
        raw = raw.split(":", 1)[1].strip()
    if raw.startswith("https://x.com/") or raw.startswith("https://twitter.com/"):
        raw = raw.rstrip("/").rsplit("/", 1)[-1]
    if not raw.startswith("@"):
        raw = f"@{raw}"
    return raw


def _authorized_handle(packet: dict[str, Any]) -> str:
    """Account/handle the post will use — DERIVED FROM ``destination`` only.

    Authority, consent, and credential resolution all key off the
    authorized ``destination``. The account actually posted-from is bound
    to that same destination, never to an arbitrary payload-supplied
    handle. A packet whose payload names a *different* account is rejected
    upstream by :func:`_packet_handle_override` rather than silently
    honored, so authority+consent can never cover one account while the
    real write lands on another.
    """
    destination = _destination(packet)
    if destination:
        return _normalize_handle(destination)
    return _DEFAULT_HANDLE


def _packet_handle_override(packet: dict[str, Any]) -> str:
    """Return any payload/packet-supplied handle, normalized; "" if none.

    Unlike :func:`_authorized_handle` this does NOT fall back to
    ``destination`` — it surfaces only an explicit caller-supplied handle so
    the effector can detect (and reject) a handle that disagrees with the
    authorized destination.
    """
    payload = _payload(packet)
    for key in ("sink_handle", "handle", "account_handle"):
        value = payload.get(key) or packet.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_handle(value)
    return ""


def _env_suffix(value: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lstrip("@")).strip("_")
    return suffix.upper()


def _credential_prefixes(*, handle: str, destination: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for label, value in (("handle", handle), ("destination", destination)):
        suffix = _env_suffix(value)
        if suffix:
            candidates.append((label, f"TWITTER_{suffix}_"))
    candidates.append(("default", "TWITTER_"))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for label, prefix in candidates:
        if prefix in seen:
            continue
        seen.add(prefix)
        unique.append((label, prefix))
    return unique


def _resolve_credentials(*, handle: str, destination: str) -> TwitterCredentials | None:
    """Resolve per-handle credentials, falling back to default Twitter env.

    Supported forms:
    - ``TWITTER_<HANDLE>_API_KEY`` etc. for per-handle accounts.
    - ``TWITTER_<DESTINATION>_API_KEY`` etc. for destination aliases.
    - ``TWITTER_API_KEY`` etc. for the first/default account.
    """
    for label, prefix in _credential_prefixes(handle=handle, destination=destination):
        api_key = os.environ.get(f"{prefix}API_KEY", "").strip()
        api_secret = os.environ.get(f"{prefix}API_SECRET", "").strip()
        access_token = os.environ.get(f"{prefix}ACCESS_TOKEN", "").strip()
        access_secret = os.environ.get(f"{prefix}ACCESS_TOKEN_SECRET", "").strip()
        if api_key and api_secret and access_token and access_secret:
            return TwitterCredentials(
                api_key=api_key,
                api_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_secret,
                source=label,
            )
    return None


def _universe_dir(base_path: str | Path | None) -> Path | None:
    if base_path is None:
        return None
    try:
        return Path(base_path)
    except (TypeError, ValueError):
        return None


def _check_consent(universe_dir: Path | None, destination: str) -> bool:
    if universe_dir is None or not destination:
        return False
    try:
        from workflow.storage.effector_consents import is_consent_active

        return is_consent_active(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            destination=destination,
        )
    except Exception:
        logger.exception("twitter_post consent lookup crashed")
        return False


def _derive_idempotency_hint(
    *,
    packet: dict[str, Any],
    run_id: str,
    handle: str,
    text: str,
) -> str:
    raw = packet.get("idempotency_hint") or packet.get("idempotency_key")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    payload = _payload(packet)
    source_run_id = payload.get("source_run_id") or packet.get("source_run_id") or run_id
    seed = f"{source_run_id}|{EXTERNAL_WRITE_SINK_TWITTER_POST}|{handle}|{text}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _try_reserve(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    run_id: str,
) -> dict[str, Any]:
    if universe_dir is None or not idempotency_hint:
        return {"status": "no_hint"}
    from workflow.storage.external_write_receipts import try_reserve_receipt

    return try_reserve_receipt(
        universe_dir,
        idempotency_hint=idempotency_hint,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        run_id=run_id or "",
    )


def _finalize_receipt(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    evidence: dict[str, Any],
    run_id: str,
) -> bool:
    if universe_dir is None or not idempotency_hint:
        return False
    try:
        from workflow.storage.external_write_receipts import finalize_receipt

        return finalize_receipt(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            evidence=evidence,
            run_id=run_id or "",
        )
    except Exception:
        logger.exception("failed to finalize twitter_post receipt")
        return False


def _release_reservation(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    run_id: str,
) -> None:
    if universe_dir is None or not idempotency_hint:
        return
    try:
        from workflow.storage.external_write_receipts import release_reservation

        release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            run_id=run_id or "",
            mark_failed=True,
        )
    except Exception:
        logger.exception("failed to release twitter_post reservation")


def _is_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return any(token in msg for token in ("locked", "busy", "deadlock", "timeout"))


def _percent(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~-._")


def _oauth_header(
    *,
    method: str,
    url: str,
    credentials: TwitterCredentials,
) -> str:
    oauth_params = {
        "oauth_consumer_key": credentials.api_key,
        "oauth_nonce": secrets.token_urlsafe(24),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": credentials.access_token,
        "oauth_version": "1.0",
    }
    parsed = urllib.parse.urlparse(url)
    base_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    query_params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    signature_params = {**query_params, **oauth_params}
    encoded_pairs = [
        f"{_percent(key)}={_percent(value)}"
        for key, value in sorted(signature_params.items())
    ]
    normalized = "&".join(encoded_pairs)
    base_string = "&".join([
        method.upper(),
        _percent(base_url),
        _percent(normalized),
    ])
    signing_key = (
        f"{_percent(credentials.api_secret)}&"
        f"{_percent(credentials.access_token_secret)}"
    )
    digest = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    rendered = ", ".join(
        f'{_percent(key)}="{_percent(value)}"'
        for key, value in sorted(oauth_params.items())
    )
    return f"OAuth {rendered}"


def _post_tweet(
    *,
    text: str,
    reply_to_tweet_id: str,
    quote_tweet_id: str,
    credentials: TwitterCredentials,
) -> dict[str, Any]:
    body: dict[str, Any] = {"text": text}
    if reply_to_tweet_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
    if quote_tweet_id:
        body["quote_tweet_id"] = quote_tweet_id
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        _TWEETS_URL,
        data=data,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": _oauth_header(
                method="POST",
                url=_TWEETS_URL,
                credentials=credentials,
            ),
            "Content-Type": "application/json",
            "User-Agent": "workflow-twitter-post-effector/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500]
        return {
            "error": f"X API HTTP {exc.code}: {body_text}",
            "error_kind": "x_api_http_error",
            "http_status": exc.code,
        }
    except urllib.error.URLError as exc:
        return {
            "error": f"X API request failed: {exc}",
            "error_kind": "x_api_request_failed",
        }
    except TimeoutError as exc:
        return {
            "error": f"X API request timed out: {exc}",
            "error_kind": "x_api_request_failed",
        }
    except ValueError as exc:
        return {
            "error": f"X API returned invalid JSON: {exc}",
            "error_kind": "x_api_invalid_json",
        }


def _post_id(response: dict[str, Any]) -> str:
    data = response.get("data")
    if isinstance(data, dict):
        value = data.get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = response.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _post_url(handle: str, post_id: str) -> str:
    screen_name = handle.strip().lstrip("@")
    return f"https://x.com/{screen_name}/status/{post_id}"


def _would_post_evidence(
    *,
    reason: str,
    packet: dict[str, Any],
    destination: str,
    handle: str,
    text: str,
    matched_key: str | None,
    idempotency_hint: str | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "dry_run": True,
        "phase": "phase_2",
        "reason": reason,
        "destination": destination,
        "sink_handle": handle,
        "would_post": {
            "text": text,
            "reply_to_tweet_id": _optional_tweet_id(packet, "reply_to_tweet_id"),
            "quote_tweet_id": _optional_tweet_id(packet, "quote_tweet_id"),
        },
        "matched_output_key": matched_key,
        "intent": packet,
    }
    if idempotency_hint:
        evidence["idempotency_hint"] = idempotency_hint
    return evidence


def run_twitter_post_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Run one ``twitter_post`` external-write packet.

    The effector never raises to the run-completion path; every refusal,
    duplicate, or external API failure is returned as structured evidence.
    """
    matched_key, packet = _find_packet(output_keys=output_keys, run_state=run_state)
    if packet is None:
        return {
            "error": (
                f"node '{node_id}' declared effects=["
                f"{EXTERNAL_WRITE_SINK_TWITTER_POST}] but no output_key held "
                "a parseable twitter_post external_write_packet"
            ),
            "error_kind": "no_matching_packet",
        }

    destination = _destination(packet)
    # SECURITY INVARIANT: the account actually posted-from is bound to the
    # authorized ``destination``, never to an arbitrary payload handle.
    # Authority, consent, and credential resolution all key off this same
    # destination-derived handle.
    handle = _authorized_handle(packet)
    override_handle = _packet_handle_override(packet)
    text = _text(packet)
    universe_dir = _universe_dir(base_path)
    idempotency_hint = _derive_idempotency_hint(
        packet=packet,
        run_id=run_id,
        handle=handle,
        text=text,
    )

    if not destination:
        return {
            "error": "packet.destination is required for twitter_post",
            "error_kind": "invalid_destination",
            "phase": "phase_2",
            "matched_output_key": matched_key,
        }
    if override_handle and override_handle != handle:
        # The payload named an account that does not match the account the
        # authorized destination resolves to. Authority + consent only cover
        # the destination-derived account, so honoring this override would
        # post from an account that was never authorized. Reject, never post.
        return {
            "error": (
                "packet payload handle resolves to a different account than "
                "the authorized destination; refusing twitter_post to avoid "
                "posting from an unauthorized account"
            ),
            "error_kind": "handle_authority_mismatch",
            "phase": "phase_2",
            "destination": destination,
            "authorized_handle": handle,
            "requested_handle": override_handle,
            "matched_output_key": matched_key,
        }
    if not text:
        return {
            "error": "packet.payload.text is required for twitter_post",
            "error_kind": "invalid_payload",
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
        }

    if _env_truthy(_DRY_RUN_ENV):
        evidence = _would_post_evidence(
            reason="operator_kill_switch_active",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )
        evidence["kill_switch_env"] = _DRY_RUN_ENV
        return evidence

    authority = resolve_soul_effect_authority(
        universe_dir,
        EXTERNAL_WRITE_SINK_TWITTER_POST,
        destination,
    )
    if authority == SOUL_AUTHORITY_DENIED:
        return _would_post_evidence(
            reason="soul_not_authorized",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )

    if not _check_consent(universe_dir, destination):
        evidence = _would_post_evidence(
            reason="missing_consent",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )
        evidence["hint"] = (
            "Call extensions action=grant_effector_consent "
            f"sink={EXTERNAL_WRITE_SINK_TWITTER_POST} "
            f"destination={destination} before dispatching twitter_post effects."
        )
        return evidence

    credentials = _resolve_credentials(handle=handle, destination=destination)
    if credentials is None:
        evidence = _would_post_evidence(
            reason="missing_credentials",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )
        evidence["hint"] = (
            "Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, "
            "and TWITTER_ACCESS_TOKEN_SECRET for the default handle, or the "
            "same names prefixed with TWITTER_<HANDLE>_ for per-handle routing."
        )
        return evidence

    try:
        reservation = _try_reserve(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
    except sqlite3.OperationalError as exc:
        return {
            "error": (
                "receipt store unavailable; refusing twitter_post to avoid "
                f"duplicate posts: {exc}"
            ),
            "error_kind": (
                "receipt_store_locked"
                if _is_lock_error(exc) else "receipt_store_error"
            ),
            "phase": "phase_2",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
        }

    status = reservation.get("status")
    if status == "duplicate":
        recorded = reservation.get("row") or {}
        return {
            "idempotency_dedup_hit": True,
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
            "evidence": recorded.get("evidence") or {},
            "recorded_run_id": recorded.get("run_id"),
            "recorded_at": recorded.get("created_at"),
            "idempotency_hint": idempotency_hint,
        }
    if status == "in_flight":
        held = reservation.get("row") or {}
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "concurrent_in_flight",
            "destination": destination,
            "sink_handle": handle,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
            "held_by_run_id": held.get("run_id"),
            "reservation_created_at": held.get("created_at"),
            "intent": packet,
        }
    if status not in (
        "reserved",
        "reserved_after_stale",
        "reserved_after_failed",
        "no_hint",
    ):
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "reservation_unknown_state",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "reservation_status": str(status),
            "matched_output_key": matched_key,
            "intent": packet,
        }

    response = _post_tweet(
        text=text,
        reply_to_tweet_id=_optional_tweet_id(packet, "reply_to_tweet_id"),
        quote_tweet_id=_optional_tweet_id(packet, "quote_tweet_id"),
        credentials=credentials,
    )
    if "error" in response:
        _release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
        response.setdefault("phase", "phase_2")
        response.setdefault("destination", destination)
        response.setdefault("sink_handle", handle)
        response.setdefault("idempotency_hint", idempotency_hint)
        response.setdefault("reservation_released", True)
        response.setdefault("matched_output_key", matched_key)
        return response

    post_id = _post_id(response)
    if not post_id:
        _release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
        return {
            "error": "X API response did not contain data.id",
            "error_kind": "x_api_invalid_response",
            "phase": "phase_2",
            "destination": destination,
            "sink_handle": handle,
            "idempotency_hint": idempotency_hint,
            "reservation_released": True,
            "matched_output_key": matched_key,
        }

    evidence: dict[str, Any] = {
        "phase": "phase_2",
        "destination": destination,
        "sink_handle": handle,
        "post_id": post_id,
        "post_url": _post_url(handle, post_id),
        "matched_output_key": matched_key,
        "idempotency_hint": idempotency_hint,
        "credential_source": credentials.source,
        "recorded_at": time.time(),
    }
    if status in ("reserved_after_stale", "reserved_after_failed"):
        evidence["reservation_origin"] = status
    if not _finalize_receipt(
        universe_dir,
        idempotency_hint=idempotency_hint,
        evidence=evidence,
        run_id=run_id,
    ):
        evidence["receipt_finalize_failed"] = True
    return evidence


__all__ = [
    "EXTERNAL_WRITE_SINK_TWITTER_POST",
    "run_twitter_post_effector",
]
