"""HTTP admission for Slack app events.

This is the missing door in front of an otherwise complete chain:
`app_event_ingress` authenticates and deduplicates, and the authority modules
downstream of it decide what an admitted event may do. Until this module existed
nothing called any of them from a running server.

Two properties carry the whole design:

* **The raw bytes are sacred.** Slack signs `v0:{timestamp}:{body}`, so the body
  is read once and handed to the verifier untouched. Parsing happens inside the
  verifier, *after* the HMAC check.
* **Absent configuration disables the route.** A missing secret must never
  degrade into an empty-key HMAC, which would still verify and would look
  exactly like a passing test.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from tinyassets.app_event_ingress import (
    AppEventAuthenticationError,
    AppEventEnvelopeError,
    SlackAppEventBoundary,
    SlackRequestVerifier,
)
from tinyassets.storage.app_events import AppEventAdmissionStore

SIGNING_SECRET_ENV = "TINYASSETS_SLACK_SIGNING_SECRET"
API_APP_ID_ENV = "TINYASSETS_SLACK_API_APP_ID"

#: Hard ceiling on bytes buffered from an *unauthenticated* request.
#: `SlackRequestVerifier` enforces its own 1 MiB limit, but only after it has
#: been handed a complete body — so an unbounded read would let anyone POST an
#: arbitrarily large payload and exhaust memory before a single byte is
#: authenticated. Slack's own event payloads are far below this.
MAX_UNAUTHENTICATED_BODY_BYTES = 1_048_576

#: Every refusal returns this exact text. "Not configured", "bad signature", and
#: "unknown app id" must be indistinguishable from outside, so the endpoint can
#: never be used to probe which apps are installed.
REFUSAL_BODY = "unauthorized"


def _clean(value: object) -> str:
    """Return a usable configuration string, or ``""`` if there isn't one."""
    if not isinstance(value, str):
        return ""
    return value.strip()


def resolve_boundary(
    base_path: object,
    *,
    env: Mapping[str, str] | None = None,
) -> SlackAppEventBoundary | None:
    """Build the admission boundary, or return ``None`` when unconfigured.

    Returning ``None`` is the fail-closed signal: the caller refuses every
    request rather than constructing a verifier with a weak key. There is
    deliberately no default, no fallback, and no request-supplied input here.
    """
    source = os.environ if env is None else env
    signing_secret = _clean(source.get(SIGNING_SECRET_ENV))
    api_app_id = _clean(source.get(API_APP_ID_ENV))
    if not signing_secret or not api_app_id:
        return None
    try:
        verifier = SlackRequestVerifier(
            signing_secret=signing_secret,
            expected_api_app_id=api_app_id,
        )
    except (TypeError, ValueError):
        # Malformed configuration is refused, never coerced into something
        # that happens to construct.
        return None
    return SlackAppEventBoundary(
        verifier=verifier,
        store=AppEventAdmissionStore(base_path),
    )


def _challenge_response(raw_body: bytes) -> str | None:
    """Return the challenge value if these bytes are a URL-verification handshake.

    Only reached after the signature has already been verified, so this parses
    bytes Slack authenticated. A body that claims to be a handshake is treated
    strictly as one — it never admits an event, even if it also carries
    ``event``/``event_id`` fields.
    """
    try:
        envelope: Any = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(envelope, dict):
        return None
    if envelope.get("type") != "url_verification":
        return None
    challenge = envelope.get("challenge")
    if not isinstance(challenge, str) or not challenge:
        return None
    return challenge


class BodyTooLarge(Exception):
    """The peer sent more bytes than we will buffer before authenticating."""


async def read_bounded_body(request: Any, *, limit: int = MAX_UNAUTHENTICATED_BODY_BYTES) -> bytes:
    """Buffer at most ``limit`` bytes from an unauthenticated request.

    Two gates, because either alone is bypassable: a declared ``Content-Length``
    is refused up front, and the stream itself is counted as it arrives so a
    chunked body (which declares no length) cannot slip past.
    """
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > limit:
                raise BodyTooLarge
        except ValueError:
            raise BodyTooLarge from None

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise BodyTooLarge
        chunks.append(chunk)
    return b"".join(chunks)


class IngressOutcome:
    """What the handler should send back, decided without touching HTTP."""

    __slots__ = ("status", "body", "admitted", "replay")

    def __init__(
        self,
        status: int,
        body: str,
        *,
        admitted: bool = False,
        replay: bool = False,
    ) -> None:
        self.status = status
        self.body = body
        self.admitted = admitted
        self.replay = replay


def handle_slack_request(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    boundary: SlackAppEventBoundary | None,
) -> IngressOutcome:
    """Authenticate, then either answer the handshake or admit the event.

    Kept transport-free so the ordering that matters — verify *before* branching
    — can be tested without a server.
    """
    if boundary is None:
        return IngressOutcome(401, REFUSAL_BODY)

    try:
        boundary.verifier.authenticate(raw_body=raw_body, headers=headers)
    except AppEventAuthenticationError:
        return IngressOutcome(401, REFUSAL_BODY)
    except AppEventEnvelopeError:
        # The signature held but the envelope is not an ``event_callback``.
        # The handshake lives here, and it is reachable only because the HMAC
        # already passed — an unsigned request never gets this far.
        challenge = _challenge_response(raw_body)
        if challenge is not None:
            return IngressOutcome(200, challenge)
        return IngressOutcome(401, REFUSAL_BODY)

    try:
        result = boundary.admit(raw_body=raw_body, headers=headers)
    except (AppEventAuthenticationError, AppEventEnvelopeError):
        return IngressOutcome(401, REFUSAL_BODY)

    return IngressOutcome(200, "", admitted=True, replay=result.replay)
