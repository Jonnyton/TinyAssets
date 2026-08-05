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

#: Slack issues 32-hex-character signing secrets.
#:
#: An earlier version of this check used a length floor of 16 alone. A reviewer
#: broke it three ways in one pass — `"0" * 16`, two visible characters padded
#: with spaces, and two visible characters padded with U+200B zero-width spaces
#: all cleared it. **Length is not entropy.** So the check is now shape-based as
#: well: printable ASCII only (no whitespace, no invisibles), full Slack length,
#: and enough distinct characters that a padded or repeated value cannot pass.
MIN_SIGNING_SECRET_LENGTH = 32

#: A random 32-char hex string averages ~14 distinct characters. 12 keeps the
#: false-reject rate on genuine secrets very low while refusing the patterned
#: hex a reviewer used to clear a floor of 10 (`"0123456789" * 3 + "01"`). If a
#: real secret ever did trip this it fails CLOSED, which is the safe direction.
MIN_SIGNING_SECRET_DISTINCT_CHARS = 12

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


def is_strong_signing_secret(secret: str) -> bool:
    """Reject secrets that are long enough to look fine but trivial to guess.

    Reviewer counterexamples this must refuse, each of which cleared the
    previous version of this check:

    * ``"0" * 16`` — length is not entropy
    * ``"x" + " " * 14 + "x"`` — whitespace padding inflates a length count
    * ``"x" + "\\u200b" * 14 + "x"`` — so do zero-width characters
    * ``"0123456789" * 3 + "01"`` — valid hex, 32 chars, only 10 distinct

    The rule that finally holds is the *real* Slack shape (exactly 32 lowercase
    hex characters) plus a distinct-character floor, because shape alone still
    admits patterned hex and a floor alone still admits non-Slack junk.
    """
    if not isinstance(secret, str) or len(secret) != MIN_SIGNING_SECRET_LENGTH:
        return False
    # Slack signing secrets are exactly 32 lowercase hex characters. Requiring
    # the real shape is stronger than any generic "looks random" heuristic:
    # anything else is a misconfiguration by definition, not a preference. It
    # also subsumes the earlier printable-ASCII rule, since whitespace and
    # zero-width characters are not hex digits.
    if any(character not in "0123456789abcdef" for character in secret):
        return False
    # Shape alone is not enough — `"0123456789" * 3 + "01"` is valid hex with
    # only 10 distinct characters, which a reviewer got past a distinct-count
    # floor of 10. A genuine random 32-hex secret averages ~14 distinct.
    return len(set(secret)) >= MIN_SIGNING_SECRET_DISTINCT_CHARS


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
    if not is_strong_signing_secret(signing_secret):
        # A weak secret still constructs a valid HMAC and still "verifies" —
        # it is guessable, not merely unusual.
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


def _challenge_response(
    raw_body: bytes,
    *,
    expected_api_app_id: str,
    allowed_team_ids: frozenset[str],
) -> str | None:
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
    # Reject a MISMATCHED app id, but do not require one.
    #
    # Slack's genuine handshake body is only `{token, challenge, type}` — it
    # carries no `api_app_id`. Requiring one would make the Request URL
    # unsaveable in Slack and kill this endpoint on arrival, which is the exact
    # failure D3 exists to prevent. But a reviewer echoed `ORG-BYPASS` through a
    # handshake declaring `api_app_id: A_OTHER`, so a *present* value that
    # disagrees with ours is refused. Absent (the real shape) still passes.
    claimed_app_id = _clean(envelope.get("api_app_id"))
    if claimed_app_id and claimed_app_id != expected_api_app_id:
        return None
    # Same rule for the workspace. Slack's genuine handshake carries no team_id
    # either, so one cannot be required — but a reviewer got `CHAL` echoed back
    # through handshakes declaring `team_id: T_ATTACKER`, so a *present* team
    # that is not on the allow-list is refused.
    claimed_team_id = _clean(envelope.get("team_id"))
    if claimed_team_id and claimed_team_id not in allowed_team_ids:
        return None
    # An Enterprise Grid install is org-scoped, and the only authorisation this
    # deployment has is a per-workspace allow-list — so there is nothing here
    # that could vouch for one. A reviewer got `CHAL` echoed through a handshake
    # carrying only `enterprise_id`, which no team check can catch precisely
    # because it names no team. Refuse it rather than answer unauthorised.
    if _clean(envelope.get("enterprise_id")):
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


def _decoy_verifier() -> SlackRequestVerifier:
    """A throwaway verifier over a random key, used only to equalise timing."""
    global _DECOY
    if _DECOY is None:
        _DECOY = SlackRequestVerifier(
            signing_secret=hashlib.sha256(os.urandom(32)).hexdigest(),
            expected_api_app_id="A00000000000",
        )
    return _DECOY


_DECOY: SlackRequestVerifier | None = None


def _burn_equivalent_work(raw_body: bytes, headers: Mapping[str, str]) -> None:
    """Run the *real* authentication path against a decoy key, discarding it.

    An earlier version hashed the body directly. That equalised only one shape:
    a reviewer measured a 767x timing ratio on the configured-but-missing-headers
    path, because header validation rejects before any hashing happens and the
    hand-rolled burn did not reproduce that. Running the genuine code path is
    the only version that tracks it — whatever the verifier does, the decoy does
    too, including its early exits.
    """
    try:
        _decoy_verifier().authenticate(raw_body=raw_body, headers=headers)
    except (AppEventAuthenticationError, AppEventEnvelopeError):
        pass


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
    allowed = frozenset() if allowed_team_ids is None else allowed_team_ids

    if boundary is None or not allowed:
        # No key, or no workspace authorised to talk to us: nothing can be
        # admitted and nothing — not even a handshake — should be answered.
        _burn_equivalent_work(raw_body, headers)
        return IngressOutcome(401, REFUSAL_BODY)

    try:
        event = boundary.verifier.authenticate(raw_body=raw_body, headers=headers)
    except AppEventAuthenticationError:
        return IngressOutcome(401, REFUSAL_BODY)
    except AppEventEnvelopeError:
        # The signature held but the envelope is not an ``event_callback``.
        # The handshake lives here, and it is reachable only because the HMAC
        # already passed — an unsigned request never gets this far.
        #
        # It cannot be team-gated: Slack's handshake body carries no team_id at
        # all. What it CAN be gated on is that the deployment has authorised at
        # least one workspace (checked above), so a server that is configured
        # but not yet authorised to serve anybody answers nothing. Beyond that,
        # the echo returns only the caller's own challenge value, so a
        # secret-holder learns nothing they did not already send.
        challenge = _challenge_response(
            raw_body,
            expected_api_app_id=boundary.verifier.expected_api_app_id,
            allowed_team_ids=allowed,
        )
        if challenge is not None:
            return IngressOutcome(200, challenge)
        return IngressOutcome(401, REFUSAL_BODY)

    # A valid signature proves the *app*, not the *workspace*: every install of
    # the app signs with the same secret. Without this check an attacker who
    # installs the app in a workspace they control delivers perfectly signed
    # events under a team_id of their choosing — and each one writes a
    # permanent ledger row.
    if event.team_id not in allowed:
        return IngressOutcome(401, REFUSAL_BODY)

    try:
        result = boundary.admit(raw_body=raw_body, headers=headers)
    except (AppEventAuthenticationError, AppEventEnvelopeError):
        return IngressOutcome(401, REFUSAL_BODY)
    except AppEventReplayConflict:
        # Same event_id, different body: acknowledged, never admitted.
        #
        # A previous version returned 401 here. That still leaked the ledger:
        # a known event_id answered 401 while an unused one answered 200, so a
        # valid signer could enumerate membership by watching the status. Both
        # now answer 200 with an identical empty body, which is also what Slack
        # wants — the delivery is terminal either way and must not be retried.
        return IngressOutcome(200, "")

    return IngressOutcome(200, "", admitted=True, replay=result.replay)
