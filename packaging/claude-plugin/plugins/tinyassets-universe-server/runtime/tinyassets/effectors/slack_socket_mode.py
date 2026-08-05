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
import re
import traceback
from collections import OrderedDict
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
    #: Top-level on the frame, NOT inside `payload` — a `disconnect` frame has
    #: no payload at all. Reading it from the wrong place made every disconnect
    #: look like a hard close.
    reason: str = ""

    @property
    def needs_ack(self) -> bool:
        return bool(self.envelope_id)


def parse_envelope(raw: str | bytes) -> SocketEnvelope | None:
    """Normalise one socket frame, or return ``None`` if it is not usable.

    Returns ``None`` rather than raising: a malformed frame from Slack must not
    take down a long-lived connection that is otherwise healthy.

    A frame we cannot *interpret* still yields an envelope, with ``type`` set to
    the empty string, as long as it is a JSON object. That is deliberate: the
    ``envelope_id`` is what lets us acknowledge, and discarding the whole frame
    because its ``type`` was unrecognised threw away a usable acknowledgement id
    and left Slack redelivering a frame we were never going to understand.
    """
    try:
        decoded = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception:  # noqa: BLE001 - see below; the contract is "never raise"
        # Broad on purpose. The obvious catch is (UnicodeDecodeError,
        # JSONDecodeError), and it was — until a review fed in syntactically
        # VALID json nested 20,000 levels deep, which raises RecursionError
        # from the parser. That is not a decode error, so it escaped, and
        # because parsing happens before the pump's guarded block it ended the
        # connection. Enumerating what a parser can raise on hostile input is a
        # losing game; this function's contract is that it returns None.
        return None
    if not isinstance(decoded, dict):
        return None
    envelope_type = decoded.get("type")
    if not isinstance(envelope_type, str):
        envelope_type = ""
    envelope_id = decoded.get("envelope_id")
    payload = decoded.get("payload")
    attempt = decoded.get("retry_attempt")
    reason = decoded.get("reason")
    return SocketEnvelope(
        type=envelope_type,
        envelope_id=envelope_id if isinstance(envelope_id, str) else "",
        payload=payload if isinstance(payload, Mapping) else {},
        retry_attempt=attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else 0,
        reason=reason if isinstance(reason, str) else "",
    )


def event_of(envelope: SocketEnvelope) -> Mapping[str, Any] | None:
    """The inner Slack event, or ``None`` when this frame carries no event.

    The returned mapping carries a normalised ``team_id`` copied from the
    envelope payload. That field is load-bearing and it is *only* on the
    payload: Slack puts the authenticated workspace on the outer envelope,
    while the inner event carries `team` inconsistently and not at all for some
    types. A consumer that has to answer "which workspace is this?" would
    otherwise have to choose between an absent field and a fail-open default.

    The payload's value always wins over any `team_id` on the event, because
    the payload is the part Slack authenticated.
    """
    if envelope.type != ENVELOPE_EVENTS_API:
        return None
    payload = envelope.payload
    if payload.get("type") != "event_callback":
        return None
    event = payload.get("event")
    if not isinstance(event, Mapping):
        return None
    team_id = payload.get("team_id")
    if not isinstance(team_id, str) or not team_id.strip():
        return event
    normalised = dict(event)
    normalised["team_id"] = team_id.strip()
    return normalised


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
    # `app_id` and `bot_profile` are the markers a cross-family review used to
    # break the original three checks: it built a message carrying neither
    # `bot_id` nor `user` — just `app_id` + `bot_profile` — and reached the
    # handler. Any app-authored message is a loop risk, not only our own: two
    # agents in one channel answering each other spend both users' budgets
    # until someone notices the bill.
    if event.get("app_id"):
        return True
    if isinstance(event.get("bot_profile"), Mapping):
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
    event_type = event.get("type")
    # The isinstance check is not decoration. `x in frozenset` raises TypeError
    # for an unhashable x, so a frame carrying `"type": ["app_mention"]` used to
    # crash here — and because this filter runs before the handler's try block,
    # that TypeError escaped `pump` and killed the whole socket. One malformed
    # frame silently ended the agent.
    if not isinstance(event_type, str) or event_type not in CONVERSATIONAL_EVENT_TYPES:
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


#: Slack error codes are lowercase snake_case identifiers. Anything else in that
#: field is not a code we recognise, and echoing it verbatim is how upstream
#: text — including a token an error message quoted back — reaches our logs.
_ERROR_CODE_PATTERN = re.compile(r"\A[a-z][a-z0-9_]{0,63}\Z")


def _scrubbed(exc: BaseException, token: str) -> SocketModeError:
    """The same error, minus its diagnostic if the token is anywhere in it.

    This is not a general secret scrubber, which would be a denylist and would
    not work. It checks for one specific string we are holding, across the whole
    rendered chain — so it either preserves a diagnostic we have *verified* is
    clean, or drops it. There is no third outcome where a token slips through
    because the pattern did not match.
    """
    if not token:
        return SocketModeError(str(exc))
    rendered = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )
    if token in rendered:
        return SocketModeError("could not reach slack to open a socket")
    return SocketModeError(str(exc))


def _safe_error_code(value: object) -> str:
    """Pass through a real Slack error code; refuse anything else.

    An allow-list, not a scrub. A denylist here would have to anticipate every
    shape a secret can take, and the set of valid Slack codes is small and
    well-shaped, so matching what we accept is both simpler and tighter.
    """
    if isinstance(value, str) and _ERROR_CODE_PATTERN.match(value):
        return value
    return ""


class Opener(Protocol):
    """Performs the `apps.connections.open` call. Injected so tests need no network."""

    def __call__(self, app_token: str) -> Mapping[str, Any]: ...


def open_socket_url(app_token: str, *, opener: Opener) -> str:
    """Exchange an app-level token for a single-use WSS URL.

    The token is sent in the Authorization header and never returned, logged, or
    placed in an exception — this function's output is a URL the caller will
    dial, and nothing else.

    Holding that guarantee takes two things that are easy to miss, and this
    function previously did neither:

    * ``from None``, not ``from exc``. An HTTP library routinely puts the
      request headers in its exception message, and ``raise ... from exc`` keeps
      that cause attached — so ``exc_info=True`` writes the whole ``Bearer
      xapp-…`` line into the log. Chaining is a leak here, not a courtesy.
    * A **sanitised** error code. Slack's ``error`` field is upstream text; a
      response of ``{"ok": false, "error": "invalid xapp-…"}`` interpolated
      straight into the message re-introduces the leak from the other side.
    """
    if not is_app_token(app_token):
        raise SocketModeError("slack app-level token is missing or not an xapp- token")
    try:
        response = opener(app_token)
    except SocketModeError as exc:
        # An opener that raises our own error type is *probably* one of ours
        # and already sanitised — but "probably ours" is not a security
        # property, and a review reproduced a token surviving this passthrough.
        # Keep the diagnostic only when we can see the token is not in it.
        raise _scrubbed(exc, app_token) from None
    except Exception:  # noqa: BLE001 - drop the cause: it may carry the token
        raise SocketModeError("could not reach slack to open a socket") from None
    if not isinstance(response, Mapping) or not response.get("ok"):
        code = ""
        if isinstance(response, Mapping):
            code = _safe_error_code(response.get("error"))
        raise SocketModeError(f"slack refused the socket: {code or 'unknown_error'}")
    url = response.get("url")
    if not isinstance(url, str) or not url.startswith("wss://"):
        raise SocketModeError("slack returned no socket url")
    return url


def _is_disconnect_warning(envelope: SocketEnvelope) -> bool:
    """True for Slack's advance notice, false for "closing now".

    Slack sends ``reason: "warning"`` about ten seconds ahead of the actual
    close. Treating that as "stop reading" discards whatever is still in
    flight; treating a real disconnect as a warning would spin on a dead
    socket, so the two must stay distinguishable.
    """
    return envelope.reason == "warning"


def ack_frame(envelope: SocketEnvelope) -> str:
    """The acknowledgement Slack expects for one envelope.

    Every events_api envelope must be acked or Slack redelivers it. The ack is
    sent BEFORE the turn runs — an agent turn is far slower than the redelivery
    window, and coupling them would turn one message into several.
    """
    return json.dumps({"envelope_id": envelope.envelope_id})


#: Called with the inner Slack event once it has passed every guard.
Handler = Callable[[Mapping[str, Any]], Awaitable[None]]

#: Called when a handler raised. The event is delivered but unanswered, so this
#: is the hook that tells the *user* rather than only the log.
FailureHandler = Callable[[Mapping[str, Any], BaseException], Awaitable[None]]


@dataclass(slots=True)
class PumpStats:
    """A running count that survives the connection dying.

    `pump` also returns its count, which is enough for a direct caller. It is
    not enough for the runner: a dropped socket raises out of the async
    iteration, so the return value — and every event that connection had
    already handled — is lost with it. Since dropping is the *normal* path
    (Slack cycles sockets routinely), the total silently under-reported by
    roughly one connection's traffic every time.
    """

    handled: int = 0


def delivery_key(envelope: SocketEnvelope) -> str:
    """A stable identity for one delivery, for deduplication.

    Slack's ``event_id`` is stable across redeliveries of the same event, which
    is exactly what is needed: ``envelope_id`` alone is not enough, because a
    retry can arrive under a fresh envelope. Falls back to the envelope id when
    the payload carries no event id.
    """
    event_id = envelope.payload.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        return f"event:{event_id.strip()}"
    return f"envelope:{envelope.envelope_id}" if envelope.envelope_id else ""


class SeenDeliveries:
    """A bounded set of recently-handled delivery keys.

    Exists because acknowledging is not guaranteed to reach Slack. If the ack
    send fails — which the pump tolerates so a blip cannot kill the socket —
    Slack redelivers, and without this the agent answers the same question
    twice and bills the user twice for it. A review reproduced exactly that.

    Bounded, and evicting oldest-first, because an unbounded set on a
    long-running daemon is a slow memory leak.
    """

    __slots__ = ("_capacity", "_seen")

    def __init__(self, capacity: int = 2048) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._seen: OrderedDict[str, None] = OrderedDict()

    def add_if_new(self, key: str) -> bool:
        """Record ``key``; return whether this is the first time we saw it.

        An empty key is always "new" — we cannot identify the delivery, and
        refusing to handle unidentifiable events would drop real messages.
        """
        if not key:
            return True
        if key in self._seen:
            self._seen.move_to_end(key)
            return False
        self._seen[key] = None
        if len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return True

    def __len__(self) -> int:
        return len(self._seen)


async def pump(
    connection: Any,
    *,
    bot_user_id: str,
    handle: Handler,
    seen: SeenDeliveries | None = None,
    on_failure: FailureHandler | None = None,
    stats: PumpStats | None = None,
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
    deliveries = seen if seen is not None else SeenDeliveries()
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
            if _is_disconnect_warning(envelope):
                # Slack warns roughly ten seconds before it actually closes.
                # Breaking here abandoned frames still in flight, unacked and
                # unanswered. Keep draining; the socket closing ends the loop.
                logger.info("slack socket: disconnect warning, draining")
                continue
            logger.info("slack socket: disconnect requested")
            break
        if envelope.type != ENVELOPE_EVENTS_API:
            continue

        try:
            event = event_of(envelope)
            if event is None:
                continue
            if is_self_authored(event, bot_user_id):
                # The loop guard. Our own reply arrives back as a message event.
                continue
            if not is_conversational(event):
                continue
            if not deliveries.add_if_new(delivery_key(envelope)):
                # A redelivery. Slack resends whenever it did not see our ack,
                # including when the ack send itself failed above.
                logger.info("slack socket: skipping a redelivered event")
                continue
            try:
                await handle(event)
            except Exception as exc:  # noqa: BLE001 - report, do not drop silently
                # The ack already went out, so Slack will not retry: without
                # this branch the user's message is simply lost, and the only
                # trace is a log line nobody is reading.
                if on_failure is not None:
                    try:
                        await on_failure(event, exc)
                    except Exception:  # noqa: BLE001
                        logger.warning("slack socket: failure notice also failed")
                raise
            handled += 1
            if stats is not None:
                stats.handled += 1
        except Exception:  # noqa: BLE001 - one bad frame must not drop the socket
            # The filters are inside this block deliberately. They read
            # attacker-shaped JSON, and an exception from *any* of them used to
            # escape and end a long-lived connection. A socket that dies on one
            # frame is the worst failure mode here: the process stays up and
            # answers nobody, with nothing a user would look at reporting it.
            logger.warning("slack socket: dropped one frame", exc_info=True)
    return handled
