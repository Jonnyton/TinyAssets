"""Provider-authenticated, authority-neutral external app event admission."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable

from tinyassets.storage.app_events import (
    AppEventAdmissionReceipt,
    AppEventAdmissionStore,
)

_SLACK_SIGNATURE = re.compile(r"v0=[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9._-]+\Z")
_AUTHENTICATION_SEAL = object()


class AppEventAuthenticationError(PermissionError):
    """The provider did not authenticate the exact request bytes."""


class AppEventEnvelopeError(ValueError):
    """An authenticated request did not contain an admissible event."""


@dataclass(frozen=True, slots=True, init=False)
class AuthenticatedAppEvent:
    """Transient provider evidence; this is not TinyAssets user authority."""

    provider: str
    installation_id: str
    external_event_id: str
    event_type: str
    api_app_id: str
    team_id: str
    external_sender_id: str
    request_timestamp: int
    body_sha256: str
    payload: Mapping[str, Any] = field(repr=False, compare=False)
    _seal: object = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        provider: str,
        installation_id: str,
        external_event_id: str,
        event_type: str,
        api_app_id: str,
        team_id: str,
        external_sender_id: str,
        request_timestamp: int,
        body_sha256: str,
        payload: Mapping[str, Any],
        _seal: object,
    ) -> None:
        if _seal is not _AUTHENTICATION_SEAL:
            raise TypeError("AuthenticatedAppEvent may only be created by a verifier")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "installation_id", installation_id)
        object.__setattr__(self, "external_event_id", external_event_id)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "api_app_id", api_app_id)
        object.__setattr__(self, "team_id", team_id)
        object.__setattr__(self, "external_sender_id", external_sender_id)
        object.__setattr__(self, "request_timestamp", request_timestamp)
        object.__setattr__(self, "body_sha256", body_sha256)
        object.__setattr__(self, "payload", _freeze_json(payload))
        object.__setattr__(self, "_seal", _seal)


def is_authenticated_app_event(value: object) -> bool:
    """Return whether ``value`` carries this process's verifier seal."""

    return isinstance(value, AuthenticatedAppEvent) and value._seal is _AUTHENTICATION_SEAL


@dataclass(frozen=True)
class AppEventBoundaryResult:
    event: AuthenticatedAppEvent
    receipt: AppEventAdmissionReceipt
    replay: bool


class SlackRequestVerifier:
    """Verify Slack's v0 signature before decoding the Events API envelope."""

    def __init__(
        self,
        *,
        signing_secret: str | bytes,
        expected_api_app_id: str,
        clock: Callable[[], float] | None = None,
        max_body_bytes: int = 1_048_576,
        max_age_seconds: int = 300,
    ) -> None:
        if isinstance(signing_secret, str):
            secret = signing_secret.encode("utf-8")
        elif isinstance(signing_secret, bytes):
            secret = signing_secret
        else:
            raise TypeError("signing_secret must be str or bytes")
        if not secret:
            raise ValueError("signing_secret must be non-empty")
        self._signing_secret = bytes(secret)
        self.expected_api_app_id = _identifier(
            expected_api_app_id,
            "expected_api_app_id",
        )
        self._clock = clock or time.time
        if not isinstance(max_body_bytes, int) or isinstance(max_body_bytes, bool):
            raise ValueError("max_body_bytes must be an integer")
        if not 1 <= max_body_bytes <= 16 * 1024 * 1024:
            raise ValueError("max_body_bytes must be between 1 and 16777216")
        if not isinstance(max_age_seconds, int) or isinstance(max_age_seconds, bool):
            raise ValueError("max_age_seconds must be an integer")
        if not 1 <= max_age_seconds <= 300:
            raise ValueError("max_age_seconds must be between 1 and 300")
        self.max_body_bytes = max_body_bytes
        self.max_age_seconds = max_age_seconds

    def authenticate(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> AuthenticatedAppEvent:
        if not isinstance(raw_body, bytes):
            raise AppEventAuthenticationError("raw request body must be immutable bytes")
        if not raw_body or len(raw_body) > self.max_body_bytes:
            raise AppEventAuthenticationError("raw request body is empty or exceeds the limit")
        if not isinstance(headers, Mapping):
            raise AppEventAuthenticationError("request headers are required")

        timestamp_text = _single_header(headers, "x-slack-request-timestamp")
        signature = _single_header(headers, "x-slack-signature")
        if not timestamp_text.isascii() or not timestamp_text.isdigit():
            raise AppEventAuthenticationError("Slack request timestamp is malformed")
        if len(timestamp_text) > 20:
            raise AppEventAuthenticationError("Slack request timestamp is malformed")
        request_timestamp = int(timestamp_text)
        try:
            now = float(self._clock())
        except (TypeError, ValueError, OverflowError) as exc:
            raise AppEventAuthenticationError("boundary clock is invalid") from exc
        if (
            not math.isfinite(now)
            or request_timestamp <= 0
            or abs(now - request_timestamp) > self.max_age_seconds
        ):
            raise AppEventAuthenticationError("Slack request timestamp is stale")
        if _SLACK_SIGNATURE.fullmatch(signature) is None:
            raise AppEventAuthenticationError("Slack request signature is malformed")

        signed = b"v0:" + timestamp_text.encode("ascii") + b":" + raw_body
        expected = (
            "v0="
            + hmac.new(
                self._signing_secret,
                signed,
                hashlib.sha256,
            ).hexdigest()
        )
        if not hmac.compare_digest(expected, signature):
            raise AppEventAuthenticationError("Slack request signature does not match")

        return self._normalize_authenticated_envelope(
            raw_body=raw_body,
            request_timestamp=request_timestamp,
        )

    def _normalize_authenticated_envelope(
        self,
        *,
        raw_body: bytes,
        request_timestamp: int,
    ) -> AuthenticatedAppEvent:
        try:
            envelope = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppEventEnvelopeError("Slack event envelope is not valid JSON") from exc
        if not isinstance(envelope, dict):
            raise AppEventEnvelopeError("Slack event envelope must be an object")
        if envelope.get("type") != "event_callback":
            raise AppEventEnvelopeError("Slack envelope is not an event_callback")

        api_app_id = _envelope_identifier(envelope.get("api_app_id"), "api_app_id")
        if api_app_id != self.expected_api_app_id:
            raise AppEventEnvelopeError("Slack event targets another app")
        team_id = _envelope_identifier(envelope.get("team_id"), "team_id")
        external_event_id = _envelope_identifier(envelope.get("event_id"), "event_id")
        payload = envelope.get("event")
        if not isinstance(payload, dict):
            raise AppEventEnvelopeError("Slack event payload must be an object")
        event_type = _envelope_identifier(payload.get("type"), "event.type")
        sender = payload.get("user", "")
        if sender == "":
            external_sender_id = ""
        else:
            external_sender_id = _envelope_identifier(sender, "event.user")

        return AuthenticatedAppEvent(
            provider="slack",
            installation_id=f"{api_app_id}:{team_id}",
            external_event_id=external_event_id,
            event_type=event_type,
            api_app_id=api_app_id,
            team_id=team_id,
            external_sender_id=external_sender_id,
            request_timestamp=request_timestamp,
            body_sha256=f"sha256:{hashlib.sha256(raw_body).hexdigest()}",
            payload=payload,
            _seal=_AUTHENTICATION_SEAL,
        )


class SlackAppEventBoundary:
    """Compose provider authentication with the durable replay ledger."""

    def __init__(
        self,
        *,
        verifier: SlackRequestVerifier,
        store: AppEventAdmissionStore,
    ) -> None:
        self.verifier = verifier
        self.store = store

    def admit(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
    ) -> AppEventBoundaryResult:
        event = self.verifier.authenticate(raw_body=raw_body, headers=headers)
        stored = self.store.admit(
            provider=event.provider,
            installation_id=event.installation_id,
            external_event_id=event.external_event_id,
            event_type=event.event_type,
            request_timestamp=event.request_timestamp,
            body_sha256=event.body_sha256,
        )
        return AppEventBoundaryResult(
            event=event,
            receipt=stored.receipt,
            replay=stored.replay,
        )


def _single_header(headers: Mapping[str, str], expected_name: str) -> str:
    values = [
        value
        for name, value in headers.items()
        if isinstance(name, str) and name.casefold() == expected_name
    ]
    if len(values) != 1 or not isinstance(values[0], str) or not values[0]:
        raise AppEventAuthenticationError(f"exactly one {expected_name} header is required")
    return values[0]


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a non-empty identifier")
    if len(value) > 128 or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name} is malformed")
    return value


def _envelope_identifier(value: object, name: str) -> str:
    try:
        return _identifier(value, name)
    except ValueError as exc:
        raise AppEventEnvelopeError(str(exc)) from exc


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(nested) for key, nested in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_json(item) for item in value)
    return value
