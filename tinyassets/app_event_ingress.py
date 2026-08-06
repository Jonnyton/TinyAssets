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
_SOCKET_MODE_SEAL = object()


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


@dataclass(frozen=True, slots=True, init=False)
class SocketModeAppEvent:
    """Evidence that Slack delivered this envelope on *this app's own* socket.

    Deliberately NOT an :class:`AuthenticatedAppEvent`. That type's seal attests
    a specific fact — "these exact HTTP bytes carried Slack's v0 signature at
    this timestamp" — and :mod:`tinyassets.app_conversation_authority` mints
    signed thread-custody grants on it. Socket Mode has no request signature and
    no request bytes at all; its authenticity is that the WebSocket was opened
    with this app's own app-level token, so Slack delivers only this app's
    events over it.

    That is sufficient to *identify a principal*, which is what founder
    recognition needs. It is not the same attestation, so this type must never
    be accepted where the request seal is required — enforced by explicit
    ``is_authenticated_app_event`` checks in the custody-grant and reply paths,
    not merely by type annotations.

    Two workspace fields, because they are genuinely different questions:

    ``team_id``
        The *delivery* workspace — where this app is installed.
    ``actor_team_id``
        The *sender's own* workspace. Under Slack Connect a guest from another
        workspace posts into a shared channel, and Slack user ids are unique
        only within a workspace. Keying a principal on the delivery workspace
        alone would let a foreign ``U123`` collide with a local ``U123``.
    """

    provider: str
    installation_id: str
    external_event_id: str
    event_type: str
    api_app_id: str
    team_id: str
    actor_team_id: str
    external_sender_id: str
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
        actor_team_id: str,
        external_sender_id: str,
        payload: Mapping[str, Any],
        _seal: object,
    ) -> None:
        if _seal is not _SOCKET_MODE_SEAL:
            raise TypeError("SocketModeAppEvent may only be created by the socket admitter")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "installation_id", installation_id)
        object.__setattr__(self, "external_event_id", external_event_id)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "api_app_id", api_app_id)
        object.__setattr__(self, "team_id", team_id)
        object.__setattr__(self, "actor_team_id", actor_team_id)
        object.__setattr__(self, "external_sender_id", external_sender_id)
        object.__setattr__(self, "payload", _freeze_json(payload))
        object.__setattr__(self, "_seal", _seal)


def is_socket_mode_app_event(value: object) -> bool:
    """Return whether ``value`` carries this process's socket-admitter seal."""

    return isinstance(value, SocketModeAppEvent) and value._seal is _SOCKET_MODE_SEAL


def is_admissible_principal_event(value: object) -> bool:
    """Return whether ``value`` may be used to *identify an external principal*.

    Strictly weaker than :func:`is_authenticated_app_event`. Identifying who
    sent something and attesting the exact bytes they sent are different
    guarantees; only the former is needed to recognise a founder.
    """

    return is_authenticated_app_event(value) or is_socket_mode_app_event(value)


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


@dataclass(frozen=True)
class SocketModeBoundaryResult:
    event: SocketModeAppEvent
    receipt: AppEventAdmissionReceipt
    replay: bool


class SlackSocketModeBoundary:
    """Admit a Socket Mode envelope: identity, then the durable replay ledger.

    Takes the envelope *payload* — the part Slack authenticated — rather than a
    transport object, so this module stays free of effector imports.

    Replay admission is durable on purpose. The socket layer's in-memory
    dedupe covers one process lifetime, and Slack redelivers an envelope that
    was not acked. A restart between delivery and redelivery would therefore
    reopen the window, and on the founder path "handled twice" means a second
    durable learning commit into the founder's own soul.
    """

    def __init__(
        self,
        *,
        expected_api_app_id: str,
        store: AppEventAdmissionStore,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.expected_api_app_id = _identifier(expected_api_app_id, "expected_api_app_id")
        self.store = store
        self.clock = clock

    def admit(self, *, payload: Mapping[str, Any]) -> SocketModeBoundaryResult:
        event = self._normalize(payload)
        stored = self.store.admit(
            provider=event.provider,
            installation_id=event.installation_id,
            external_event_id=event.external_event_id,
            event_type=event.event_type,
            # Socket Mode has no signed request timestamp. Admission time is the
            # honest value: it is what this ledger actually witnessed.
            request_timestamp=max(1, int(self.clock())),
            body_sha256=_payload_digest(payload),
        )
        return SocketModeBoundaryResult(
            event=event,
            receipt=stored.receipt,
            replay=stored.replay,
        )

    def _normalize(self, payload: Mapping[str, Any]) -> SocketModeAppEvent:
        if not isinstance(payload, Mapping):
            raise AppEventEnvelopeError("Socket Mode payload must be an object")
        if payload.get("type") != "event_callback":
            raise AppEventEnvelopeError("Socket Mode payload is not an event_callback")

        api_app_id = _envelope_identifier(payload.get("api_app_id"), "api_app_id")
        if api_app_id != self.expected_api_app_id:
            # Defence in depth: one socket only ever carries one app's events.
            raise AppEventEnvelopeError("Socket Mode event targets another app")
        team_id = _envelope_identifier(payload.get("team_id"), "team_id")
        external_event_id = _envelope_identifier(payload.get("event_id"), "event_id")
        inner = payload.get("event")
        if not isinstance(inner, Mapping):
            raise AppEventEnvelopeError("Socket Mode event payload must be an object")
        event_type = _envelope_identifier(inner.get("type"), "event.type")
        sender = inner.get("user", "")
        external_sender_id = "" if sender == "" else _envelope_identifier(sender, "event.user")

        return SocketModeAppEvent(
            provider="slack",
            installation_id=f"{api_app_id}:{team_id}",
            external_event_id=external_event_id,
            event_type=event_type,
            api_app_id=api_app_id,
            team_id=team_id,
            actor_team_id=_actor_team(inner, delivery_team=team_id),
            external_sender_id=external_sender_id,
            payload=inner,
            _seal=_SOCKET_MODE_SEAL,
        )


#: Slack names the sender's home workspace on Connect-delivered messages. The
#: order matters only in that both mean the same thing; whichever is present
#: wins over the delivery workspace.
_ACTOR_ORIGIN_FIELDS = ("user_team", "source_team")


def _actor_team(inner: Mapping[str, Any], *, delivery_team: str) -> str:
    """The sender's own workspace, falling back to the delivery workspace.

    The fallback is correct for an ordinary message: Slack omits ``user_team``
    when the sender is a member of the delivering workspace, which is exactly
    when the two are the same. It is documented rather than silent because it
    is the one path where a Connect guest could be keyed to the delivery
    workspace, and founder authority additionally requires the two to match.
    """
    for name in _ACTOR_ORIGIN_FIELDS:
        value = inner.get(name)
        if isinstance(value, str) and value.strip():
            return _envelope_identifier(value.strip(), name)
    return delivery_team


def _payload_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"


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
