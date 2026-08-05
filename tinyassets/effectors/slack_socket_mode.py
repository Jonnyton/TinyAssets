"""Slack Socket Mode transport — an outbound WebSocket, no public endpoint.

Socket Mode is how a self-hosted agent talks to Slack without exposing anything
to the internet. The daemon dials *out* to Slack over WSS and receives events on
that socket, so there is no inbound HTTP surface at all.

That absence is the entire point, and it removes a large class of problem rather
than defending against it:

* **No public endpoint** — nothing unauthenticated can reach this code. The HTTP
  ingress this replaces had to defend a publicly reachable URL whose only trust
  anchor was an HMAC, which is where its whole security surface came from.
* **No signature verification** — the socket is authenticated once, by an
  app-level token, at connect time. There is no per-request signature to forge,
  no timestamp window, no header-smuggling shape.
* **No 3-second acknowledgement race** — Socket Mode acks are per envelope over
  an already-open socket, not an HTTP response Slack will retry on.
* **Works on a free Slack plan and behind a firewall**, which is why this is the
  transport a user can actually reach.

The remaining risks are the ones inherent to answering messages at all, and each
guard below names the one it exists for.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol

logger = logging.getLogger(__name__)

#: Slack's Socket Mode connection-open endpoint. Takes an app-level token
#: (``xapp-``), returns a single-use WSS URL.
CONNECTIONS_OPEN_URL = "https://slack.com/api/apps.connections.open"

#: App-level tokens start with this; bot tokens (``xoxb-``) and user tokens
#: (``xoxp-``) are different credentials and cannot open a socket.
APP_TOKEN_PREFIX = "xapp-"

#: Envelope types Slack sends over the socket. `hello` and `disconnect` are
#: lifecycle frames, not events, and must not be treated as conversation.
ENVELOPE_EVENTS_API = "events_api"
ENVELOPE_HELLO = "hello"
ENVELOPE_DISCONNECT = "disconnect"

#: Only these are conversation. Anything else Slack delivers is an occurrence.
CONVERSATIONAL_EVENT_TYPES = frozenset({"app_mention", "message"})


class SocketModeError(RuntimeError):
    """The socket could not be opened or the frame was unusable.

    Carries no token and no message text — it crosses log boundaries.
    """


def is_app_token(token: object) -> bool:
    """True only for an app-level token.

    A bot token opens no socket, and passing one here fails with a confusing
    Slack error rather than an obvious one. Check the shape we require.
    """
    return isinstance(token, str) and token.startswith(APP_TOKEN_PREFIX)


@dataclass(frozen=True, slots=True)
class SocketEnvelope:
    """One frame off the socket, normalised.

    ``envelope_id`` is empty for lifecycle frames, which take no acknowledgement.
    """

    type: str
    envelope_id: str
    payload: Mapping[str, Any]
    retry_attempt: int = 0

    @property
    def needs_ack(self) -> bool:
        return bool(self.envelope_id)


def parse_envelope(raw: str | bytes) -> SocketEnvelope | None:
    """Normalise one socket frame, or return ``None`` if it is not usable.

    Returns ``None`` rather than raising: a malformed frame from Slack must not
    take down a long-lived connection that is otherwise healthy.
    """
    try:
        decoded = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict):
        return None
    envelope_type = decoded.get("type")
    if not isinstance(envelope_type, str) or not envelope_type:
        return None
    envelope_id = decoded.get("envelope_id")
    payload = decoded.get("payload")
    attempt = decoded.get("retry_attempt")
    return SocketEnvelope(
        type=envelope_type,
        envelope_id=envelope_id if isinstance(envelope_id, str) else "",
        payload=payload if isinstance(payload, Mapping) else {},
        retry_attempt=attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else 0,
    )


def event_of(envelope: SocketEnvelope) -> Mapping[str, Any] | None:
    """The inner Slack event, or ``None`` when this frame carries no event."""
    if envelope.type != ENVELOPE_EVENTS_API:
        return None
    payload = envelope.payload
    if payload.get("type") != "event_callback":
        return None
    event = payload.get("event")
    return event if isinstance(event, Mapping) else None


def is_self_authored(event: Mapping[str, Any], bot_user_id: str) -> bool:
    """True if we — or any app — wrote this message.

    Three markers, because no one of them is sufficient. `bot_id` and the
    `bot_message` subtype cover a reply sent with a bot token. The author check
    covers the case they both miss: a reply sent with a *user* token, which is
    indistinguishable from a human message except by its author id.

    Without this the agent answers its own posts forever, spending the user's
    provider budget each round. OpenClaw solves it the same way — it "drops
    user-scope message events authored by the resolved human identity".
    """
    if event.get("bot_id"):
        return True
    if event.get("subtype") == "bot_message":
        return True
    author = event.get("user")
    return (
        isinstance(author, str)
        and bool(author.strip())
        and bool(bot_user_id)
        and author.strip() == bot_user_id
    )


def is_conversational(event: Mapping[str, Any]) -> bool:
    """A plain message or a mention — never a subtyped occurrence.

    A subtype means Slack is describing something that happened (a file was
    shared, someone joined, a message was edited) rather than someone talking to
    us. Answering those spends a provider call per occurrence.
    """
    if event.get("type") not in CONVERSATIONAL_EVENT_TYPES:
        return False
    return not event.get("subtype")


def reply_thread_ts(event: Mapping[str, Any]) -> str:
    """The thread to answer in, or "" for a top-level message.

    Prefers the thread the question was asked in; falls back to the message's
    own ``ts`` so a reply opens a thread rather than flattening the channel.
    """
    for key in ("thread_ts", "ts"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class Opener(Protocol):
    """Performs the `apps.connections.open` call. Injected so tests need no network."""

    def __call__(self, app_token: str) -> Mapping[str, Any]: ...


def open_socket_url(app_token: str, *, opener: Opener) -> str:
    """Exchange an app-level token for a single-use WSS URL.

    The token is sent in the Authorization header and never returned, logged, or
    placed in an exception — this function's output is a URL the caller will
    dial, and nothing else.
    """
    if not is_app_token(app_token):
        raise SocketModeError("slack app-level token is missing or not an xapp- token")
    try:
        response = opener(app_token)
    except Exception as exc:  # noqa: BLE001 - normalise, never leak the token
        raise SocketModeError("could not reach slack to open a socket") from exc
    if not isinstance(response, Mapping) or not response.get("ok"):
        code = ""
        if isinstance(response, Mapping):
            code = str(response.get("error") or "")
        raise SocketModeError(f"slack refused the socket: {code or 'unknown_error'}")
    url = response.get("url")
    if not isinstance(url, str) or not url.startswith("wss://"):
        raise SocketModeError("slack returned no socket url")
    return url


def ack_frame(envelope: SocketEnvelope) -> str:
    """The acknowledgement Slack expects for one envelope.

    Every events_api envelope must be acked or Slack redelivers it. The ack is
    sent BEFORE the turn runs — an agent turn is far slower than the redelivery
    window, and coupling them would turn one message into several.
    """
    return json.dumps({"envelope_id": envelope.envelope_id})


#: Called with the inner Slack event once it has passed every guard.
Handler = Callable[[Mapping[str, Any]], Awaitable[None]]


async def pump(
    connection: Any,
    *,
    bot_user_id: str,
    handle: Handler,
) -> int:
    """Read frames until the socket closes. Returns how many events were handled.

    Ordering is deliberate and each step is load-bearing:

    1. parse — a malformed frame is skipped, never fatal to the connection
    2. **ack** — before any work, so a slow turn cannot cause redelivery
    3. filter — lifecycle frames, self-authored messages, subtyped occurrences
    4. handle — and a handler failure never kills the socket

    Returns a count rather than nothing so a caller can assert the loop did
    work, instead of a test passing on a socket that yielded nothing.
    """
    handled = 0
    async for raw in connection:
        envelope = parse_envelope(raw)
        if envelope is None:
            continue

        if envelope.needs_ack:
            try:
                await connection.send(ack_frame(envelope))
            except Exception:  # noqa: BLE001 - a failed ack is not fatal
                logger.warning("slack socket: ack failed for one envelope")

        if envelope.type == ENVELOPE_DISCONNECT:
            # Slack asks us to reconnect (refresh, or it is cycling the socket).
            logger.info("slack socket: disconnect requested")
            break
        if envelope.type != ENVELOPE_EVENTS_API:
            continue

        event = event_of(envelope)
        if event is None:
            continue
        if is_self_authored(event, bot_user_id):
            # The loop guard. Our own reply arrives back as a message event.
            continue
        if not is_conversational(event):
            continue

        try:
            await handle(event)
            handled += 1
        except Exception:  # noqa: BLE001 - one bad turn must not drop the socket
            logger.warning("slack socket: handler failed for one event", exc_info=True)
    return handled
