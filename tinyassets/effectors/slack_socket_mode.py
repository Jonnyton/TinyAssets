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

Two findings from review are accepted rather than fixed, and stated here so
nobody has to rediscover that the decision was deliberate:

* **A credential is reachable via `exc.__traceback__.tb_frame.f_locals`.** True,
  and true of every Python function that holds a secret in a local or a
  parameter. The exception chain is scrubbed (see `open_socket_url`), but frame
  locals are a property of the language, not of this module; removing the
  exposure would mean never binding a token to a name. Anything walking frame
  locals already has in-process execution, at which point the vault is readable
  directly.
* **Acknowledgement is head-of-line blocked behind each turn.** The pump awaits
  the handler before reading the next frame, so a slow turn delays the ack of
  the frames behind it and can provoke redelivery. `asyncio.to_thread` keeps the
  event loop free but does not make the pump concurrent. The fix is to dispatch
  turns as tasks with a bounded pool, which is a real design change — it needs
  per-conversation ordering guarantees so two messages in one thread cannot be
  answered out of order. Deferred, not overlooked.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol

from tinyassets.effectors.slack_errors import safe_error_code

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


#: Slack app ids: `A` then uppercase alphanumerics.
_APP_ID = re.compile(r"\AA[A-Z0-9]{6,}\Z")


def app_id_from_token(app_token: str) -> str:
    """The Slack app id embedded in an app-level token, or "".

    App-level tokens are `xapp-1-<APP_ID>-<issued>-<secret>`, so the app this
    socket belongs to is derivable without extra configuration. That matters:
    the api_app_id check is worthless if nothing sets it, and asking an operator
    to look up and paste an app id is a step that gets skipped or mistyped.

    Returns "" rather than guessing when the shape does not match — the check is
    then simply not applied, which is the same position as before it existed.
    """
    if not isinstance(app_token, str):
        return ""
    parts = app_token.split("-")
    if len(parts) < 3:
        return ""
    candidate = parts[2].strip()
    return candidate if _APP_ID.match(candidate) else ""


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
    normalised = dict(event)
    # Same treatment as team_id: the authenticated value is on the payload, and
    # an absent one must not leave an inner value standing in for it. A socket
    # only carries one app's events, so this is defence in depth rather than the
    # primary control — but the code should not have to rely on that to be safe.
    api_app_id = payload.get("api_app_id")
    if isinstance(api_app_id, str) and api_app_id.strip():
        normalised["api_app_id"] = api_app_id.strip()
    else:
        normalised.pop("api_app_id", None)
    team_id = payload.get("team_id")
    if isinstance(team_id, str) and team_id.strip():
        normalised["team_id"] = team_id.strip()
    else:
        # STRIP it, do not leave the inner value in place. Returning the event
        # unchanged here was a fail-open: an attacker-authored inner
        # `"team_id"` survived and every downstream consumer read it as the
        # authenticated workspace. A review used exactly that to route an
        # unattributable envelope into another universe. Absent must mean
        # absent, so the field is either the payload's or it is not there.
        normalised.pop("team_id", None)
    # Same treatment again, for the same reason: `event_id` is the key the
    # durable replay ledger dedupes on, so an inner value must never be able to
    # stand in for the authenticated one. An attacker-chosen id would otherwise
    # let a founder turn be replayed under a fresh key, or collide with a real
    # one to suppress somebody else's message.
    event_id = payload.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        normalised["event_id"] = event_id.strip()
    else:
        normalised.pop("event_id", None)
    normalised["actor_team_id"] = _actor_team_id(event, normalised.get("team_id"))
    return normalised


#: Fields Slack sets to the AUTHOR's own workspace when a message crosses
#: workspaces (Slack Connect / shared channels). Checked in this order.
_ACTOR_ORIGIN_FIELDS = ("user_team", "source_team")


def _actor_team_id(event: Mapping[str, Any], delivery_team: object) -> str:
    """The workspace the SENDER belongs to — not the one that delivered this.

    These differ in a Slack Connect channel, and conflating them is an identity
    collision rather than a cosmetic slip: Slack guarantees a user id is unique
    only *within* its own workspace, so a member of a foreign workspace may
    legitimately hold the same id as someone here. A cross-family review used
    exactly that — a foreign `U_COLLIDE` arriving on our delivery team resolves
    as our `U_COLLIDE` — so anything deciding *who* this is must key on the
    origin workspace.

    Falls back to the delivery team only when Slack supplies no origin field,
    which is the ordinary same-workspace case. That fallback is the one
    assumption carrying the Connect case: it holds exactly as far as "Slack
    omits these fields only when the author is local", so a caller elevating
    authority on the result should treat it as an assumption, not a proof.
    """
    for field in _ACTOR_ORIGIN_FIELDS:
        value = event.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return delivery_team if isinstance(delivery_team, str) else ""


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
    """The thread to answer in, or "" for a top-level (flat) reply.

    A DM is a 1:1 stream and must read as ONE continuous conversation, not a new
    thread per message — the founder called the per-message threading out as "not
    the same conversation thread of replies... it should feel like one." So:

    * If the message was posted INTO an existing thread, answer in that thread
      (respect where the person is talking).
    * A DM (Slack channel id starts with ``D``) answers FLAT — top-level — so the
      exchange is one running conversation.
    * In a shared channel, open a thread off the message so a reply does not
      flatten everyone else's channel (the original behaviour, kept).
    """
    ts = str(event.get("ts") or "").strip()
    thread_ts = str(event.get("thread_ts") or "").strip()
    # Posted into an existing thread (a real parent, not this message itself).
    if thread_ts and thread_ts != ts:
        return thread_ts
    channel = str(event.get("channel") or "")
    if channel.startswith("D"):
        return ""  # DM: flat, one continuous conversation
    return ts  # shared channel: open a thread off this message


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
    response = None
    failed = False
    try:
        response = opener(app_token)
    except Exception:  # noqa: BLE001 - see below
        # The opener's message is discarded entirely, not scrubbed. Scrubbing
        # meant substring-matching the token, and a review walked it straight
        # past: a percent-encoded or line-split token does not match, and a
        # truncated one still identifies. An allow-list on free-form upstream
        # text is not achievable, so no upstream text survives.
        #
        # The `raise` is OUTSIDE this handler deliberately, and that is the
        # whole point. `raise ... from None` clears __cause__ but leaves
        # __context__ pointing at the original token-bearing exception —
        # invisible to the default traceback, fully readable via
        # `exc.__context__`. Only raising once the handler has exited leaves no
        # chain at all. Verified: from-None-inside leaks, clearing the
        # attribute then raising leaks, raising outside does not.
        failed = True
    if failed:
        raise SocketModeError("could not reach slack to open a socket")
    if not isinstance(response, Mapping) or not response.get("ok"):
        code = ""
        if isinstance(response, Mapping):
            code = safe_error_code(response.get("error"))
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
            # Deliberately NOT exc_info=True. The handler runs a provider
            # turn, a vault read and an HTTP post, so its exception message is
            # arbitrary upstream text — a review raised one containing a bot
            # token and read it straight out of the log, right after the
            # user-facing notice had been carefully sanitised. The type name is
            # the diagnostic; the message is not ours to publish.
            logger.warning(
                "slack socket: dropped one frame (%s)",
                type(sys.exc_info()[1]).__name__,
            )
    return handled
