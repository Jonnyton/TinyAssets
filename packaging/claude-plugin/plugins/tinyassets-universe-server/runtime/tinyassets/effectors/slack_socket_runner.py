"""The I/O half of Socket Mode: open a socket, hold it, reconnect forever.

`slack_socket_mode` is pure envelope logic with no I/O and no dependencies. This
module is the part that touches the network, kept separate so the decision logic
stays testable without a socket and without `websockets` installed.

Two things here are easy to get wrong and are the reason this module exists:

* **The socket URL is single-use.** Slack hands out a WSS URL that works for one
  connection. Every reconnect must call `apps.connections.open` again — caching
  the URL produces a runner that works once and then silently stops answering.
* **A permanent failure must not be retried.** A revoked or wrong-type token
  will never succeed, so retrying it forever is a daemon that looks alive and
  answers nothing. Those codes stop the runner loudly; only transient failures
  back off and retry.

Slack disconnects deliberately (it refreshes sockets, and asks before deploys),
so reconnecting is the *normal* path, not the error path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import urllib.error
import urllib.request
from typing import Any, AsyncContextManager, Callable, Mapping

from tinyassets.effectors.slack_socket_mode import (
    CONNECTIONS_OPEN_URL,
    Handler,
    SocketModeError,
    is_app_token,
    open_socket_url,
    pump,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 15.0

#: Slack refusals that will never succeed on retry. Spinning on one of these is
#: the silent-failure shape: a process that is up, connected to nothing, and
#: reporting no error anywhere a user would look.
PERMANENT_SLACK_ERRORS = frozenset(
    {
        "invalid_auth",
        "account_inactive",
        "token_revoked",
        "token_expired",
        "not_allowed_token_type",
        "no_permission",
        "missing_scope",
    }
)

#: Reconnect backoff bounds, in seconds. A refresh-driven reconnect does not
#: wait at all; only a *failure* backs off.
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0


class SocketModePermanentError(SocketModeError):
    """Slack refused in a way that retrying cannot fix.

    Separate from `SocketModeError` so a caller can tell "the network blipped"
    from "this token is wrong" — the first should retry, the second must not.
    """


def http_opener(
    app_token: str,
    *,
    url: str = CONNECTIONS_OPEN_URL,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> Mapping[str, Any]:
    """POST `apps.connections.open` and return the decoded response.

    Stdlib only, matching `effectors/slack_transport`: one POST does not justify
    a Slack SDK. The token goes in the Authorization header and is never placed
    in an exception — these errors cross log boundaries.
    """
    request = urllib.request.Request(  # noqa: S310 - fixed https Slack endpoint
        url,
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {app_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise SocketModeError(f"slack connections.open http {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SocketModeError("slack unreachable opening a socket") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SocketModeError("slack returned malformed JSON opening a socket") from exc
    if not isinstance(decoded, dict):
        raise SocketModeError("slack returned a non-object opening a socket")
    return decoded


def classify_open_failure(response: Mapping[str, Any]) -> None:
    """Raise the right error class for a refused `apps.connections.open`.

    Called before `open_socket_url` so a permanent refusal is distinguishable.
    A refusal we do not recognise is treated as transient — the safer error,
    since an unknown code that is actually permanent costs a bounded retry,
    while an unknown code treated as permanent kills a recoverable runner.
    """
    if response.get("ok"):
        return
    code = str(response.get("error") or "").strip()
    if code in PERMANENT_SLACK_ERRORS:
        raise SocketModePermanentError(
            f"slack refused the socket permanently: {code}"
        )


#: Dials a WSS URL. Returns an async context manager yielding a connection that
#: is async-iterable and has ``send``. Injected so tests need no network.
Connector = Callable[[str], AsyncContextManager[Any]]


def websockets_connector(url: str) -> AsyncContextManager[Any]:
    """The real dialer. Imported lazily so this module loads without the dep."""
    from websockets.asyncio.client import connect

    return connect(url, open_timeout=_DEFAULT_TIMEOUT_SECONDS)


async def run_socket_forever(
    app_token: str,
    *,
    bot_user_id: str,
    handle: Handler,
    opener: Callable[[str], Mapping[str, Any]] = http_opener,
    connector: Connector = websockets_connector,
    max_cycles: int | None = None,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> int:
    """Hold a Socket Mode connection open, reconnecting until told to stop.

    Returns the total number of events handled across every connection, so a
    caller (or a test) can assert the runner actually did work rather than
    passing on a loop that connected to nothing.

    ``max_cycles`` bounds the number of connect attempts; ``None`` means run
    until a permanent failure or cancellation. Tests use a small bound — an
    unbounded reconnect loop in a test suite is a hang, not a failure.

    Raises `SocketModePermanentError` when Slack refuses in a way retrying
    cannot fix. That is deliberately loud: the alternative is a process that
    stays up and answers nothing.
    """
    if not is_app_token(app_token):
        raise SocketModeError("slack app-level token is missing or not an xapp- token")

    handled = 0
    backoff = INITIAL_BACKOFF_SECONDS
    cycles = 0

    while max_cycles is None or cycles < max_cycles:
        cycles += 1
        try:
            response = opener(app_token)
            classify_open_failure(response)
            # Reuse the already-fetched response rather than calling Slack
            # twice; `open_socket_url` owns the ok/url validation.
            url = open_socket_url(app_token, opener=_replay(response))
        except SocketModePermanentError:
            raise
        except SocketModeError:
            # Transient: Slack unreachable, a 5xx, a malformed body. Back off.
            logger.warning("slack socket: could not open, retrying")
            await sleep(_jittered(backoff))
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            continue

        try:
            async with connector(url) as connection:
                # A connection that opens at all resets the backoff; otherwise
                # a long-lived socket that drops once inherits an hour-old
                # penalty from a failure that has since resolved.
                backoff = INITIAL_BACKOFF_SECONDS
                handled += await pump(
                    connection,
                    bot_user_id=bot_user_id,
                    handle=handle,
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - any dial/socket failure is retryable
            logger.warning("slack socket: connection dropped, reconnecting")
            await sleep(_jittered(backoff))
            backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            continue

        # A clean return from pump means Slack asked us to reconnect (it
        # refreshes sockets routinely). That is not a failure and waits only
        # long enough to avoid hammering if it repeats immediately.
        await sleep(0)

    return handled


def _replay(response: Mapping[str, Any]) -> Callable[[str], Mapping[str, Any]]:
    """An `Opener` that returns an already-fetched response.

    Lets `open_socket_url` stay the single owner of "is this response usable"
    without the runner paying for a second `apps.connections.open` call —
    which Slack rate-limits, and which would hand back a *different*
    single-use URL, leaving the first one dangling.
    """

    def _opener(_app_token: str) -> Mapping[str, Any]:
        return response

    return _opener


def _jittered(seconds: float) -> float:
    """Full jitter, so many daemons reconnecting do not synchronise.

    Without this every runner that lost a socket to the same Slack-side event
    retries in lockstep, which is how a recovery turns into a thundering herd.
    """
    return random.uniform(0.0, seconds)  # noqa: S311 - backoff jitter, not crypto
