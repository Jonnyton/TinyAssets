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

import hashlib
import hmac
import json
import os
from typing import Any, Mapping

from tinyassets.app_event_ingress import (
    AppEventAuthenticationError,
    AppEventEnvelopeError,
    SlackAppEventBoundary,
    SlackRequestVerifier,
)
from tinyassets.storage.app_events import AppEventAdmissionStore, AppEventReplayConflict

SIGNING_SECRET_ENV = "TINYASSETS_SLACK_SIGNING_SECRET"
API_APP_ID_ENV = "TINYASSETS_SLACK_API_APP_ID"
TEAM_IDS_ENV = "TINYASSETS_SLACK_TEAM_IDS"

#: Slack issues 32-hex-character signing secrets. Anything materially shorter is
#: a misconfiguration (`changeme`, a truncated paste, a placeholder `0`), not a
#: deliberate choice — and a short key is brute-forceable, which turns the sole
#: trust anchor of a public endpoint into a guessing game. Refuse rather than
#: run with it. Deliberately below 32 so a future Slack format change degrades
#: to "still refuses the obviously-broken values" instead of refusing everything.
MIN_SIGNING_SECRET_LENGTH = 16

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


def resolve_allowed_team_ids(env: Mapping[str, str] | None = None) -> frozenset[str]:
    """Workspaces permitted to deliver events. Empty means none.

    The signing secret is per-*app*, not per-workspace: every workspace where
    the app is installed signs with the same key. So `api_app_id` alone does not
    identify who is talking — an attacker who installs the app in a workspace
    they control produces perfectly valid signatures. This allow-list is what
    makes the sender's identity meaningful.
    """
    source = os.environ if env is None else env
    raw = _clean(source.get(TEAM_IDS_ENV))
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


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
    if len(signing_secret) < MIN_SIGNING_SECRET_LENGTH:
        # A one-character secret still constructs a valid HMAC and still
        # "verifies" — it is brute-forceable, not merely weak.
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


def _burn_equivalent_work(raw_body: bytes) -> None:
    """Do the same HMAC an authenticated path would, and discard it.

    Without this, an unconfigured server answers instantly while a configured
    one hashes the body — so timing a few large forged requests tells an
    attacker whether the endpoint is armed. Cheap to equalise, so equalise it.
    """
    hmac.new(b"\x00" * 32, b"v0:0:" + raw_body, hashlib.sha256).hexdigest()


def handle_slack_request(
    *,
    raw_body: bytes,
    headers: Mapping[str, str],
    boundary: SlackAppEventBoundary | None,
    allowed_team_ids: frozenset[str] | None = None,
) -> IngressOutcome:
    """Authenticate, then either answer the handshake or admit the event.

    Kept transport-free so the ordering that matters — verify *before* branching
    — can be tested without a server.
    """
    if boundary is None:
        _burn_equivalent_work(raw_body)
        return IngressOutcome(401, REFUSAL_BODY)

    try:
        event = boundary.verifier.authenticate(raw_body=raw_body, headers=headers)
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

    # A valid signature proves the *app*, not the *workspace*: every install of
    # the app signs with the same secret. Without this check an attacker who
    # installs the app in a workspace they control delivers perfectly signed
    # events under a team_id of their choosing — and each one writes a
    # permanent ledger row.
    allowed = frozenset() if allowed_team_ids is None else allowed_team_ids
    if event.team_id not in allowed:
        return IngressOutcome(401, REFUSAL_BODY)

    try:
        result = boundary.admit(raw_body=raw_body, headers=headers)
    except (AppEventAuthenticationError, AppEventEnvelopeError):
        return IngressOutcome(401, REFUSAL_BODY)
    except AppEventReplayConflict:
        # Same event_id, different body. Surfacing this as a distinct status
        # would let a valid signer probe which event_ids the ledger holds, and
        # turn a collision into an error oracle. It is refused like anything
        # else untrusted.
        return IngressOutcome(401, REFUSAL_BODY)

    return IngressOutcome(200, "", admitted=True, replay=result.replay)
