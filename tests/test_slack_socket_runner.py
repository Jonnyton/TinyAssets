"""The reconnect half of Socket Mode.

The failures these guard against are all the same shape: a daemon that is *up*,
reports nothing wrong, and answers no one. A cached socket URL, a permanent auth
error retried forever, or a swallowed cancellation each produce exactly that.
"""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest

from tinyassets.effectors.slack_socket_mode import SocketModeError
from tinyassets.effectors.slack_socket_runner import (
    INITIAL_BACKOFF_SECONDS,
    SocketModePermanentError,
    classify_open_failure,
    run_socket_forever,
)

APP_TOKEN = "xapp-1-A00000000-0000000000000-abcdef"
BOT_USER_ID = "U0BOT"


def _event_frame(text: str = "hello", user: str = "U0HUMAN") -> str:
    """A frame in the shape Slack documents for Socket Mode."""
    return json.dumps(
        {
            "envelope_id": f"env-{text}",
            "type": "events_api",
            "payload": {
                "type": "event_callback",
                "event": {"type": "app_mention", "user": user, "text": text},
            },
        }
    )


class _FakeSocket:
    """Yields a fixed list of frames, then closes."""

    def __init__(self, frames: list[str]) -> None:
        self._frames = list(frames)
        self.sent: list[str] = []

    async def __aiter__(self):
        for frame in self._frames:
            yield frame

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


class _FakeConnector:
    """Records every URL dialled, so 'did it re-open?' is directly assertable."""

    def __init__(self, sockets: list[object]) -> None:
        self._sockets = list(sockets)
        self.urls: list[str] = []

    def __call__(self, url: str):
        self.urls.append(url)
        socket = self._sockets.pop(0) if self._sockets else _FakeSocket([])

        @contextlib.asynccontextmanager
        async def _cm():
            if isinstance(socket, Exception):
                raise socket
            yield socket

        return _cm()


async def _no_sleep(_seconds: float) -> None:
    return None


async def _handle_nothing(_event) -> None:
    return None


@pytest.mark.asyncio
async def test_a_bot_token_is_refused_before_any_network_call() -> None:
    """A bot token cannot open a socket; failing here beats a confusing Slack error."""
    calls: list[str] = []

    def _opener(token: str):
        calls.append(token)
        return {"ok": True, "url": "wss://example.invalid/link"}

    with pytest.raises(SocketModeError):
        await run_socket_forever(
            "xoxb-not-an-app-token",
            bot_user_id=BOT_USER_ID,
            handle=_handle_nothing,
            opener=_opener,
            connector=_FakeConnector([]),
            max_cycles=1,
            sleep=_no_sleep,
        )

    assert calls == []


@pytest.mark.asyncio
async def test_each_reconnect_opens_a_fresh_socket_url() -> None:
    """Slack's socket URL is single-use.

    Caching it produces a runner that works exactly once and then silently
    stops answering — the failure this whole test file exists for.
    """
    urls = ["wss://example.invalid/one", "wss://example.invalid/two"]
    opened: list[str] = []

    def _opener(_token: str):
        url = urls[len(opened) % len(urls)]
        opened.append(url)
        return {"ok": True, "url": url}

    connector = _FakeConnector([_FakeSocket([]), _FakeSocket([])])

    await run_socket_forever(
        APP_TOKEN,
        bot_user_id=BOT_USER_ID,
        handle=_handle_nothing,
        opener=_opener,
        connector=connector,
        max_cycles=2,
        sleep=_no_sleep,
    )

    assert len(opened) == 2, "reconnect must call apps.connections.open again"
    assert connector.urls == ["wss://example.invalid/one", "wss://example.invalid/two"]


@pytest.mark.asyncio
async def test_a_permanent_refusal_stops_instead_of_spinning() -> None:
    """A revoked token will never work. Retrying it forever is a dead daemon."""
    attempts: list[str] = []

    def _opener(token: str):
        attempts.append(token)
        return {"ok": False, "error": "token_revoked"}

    with pytest.raises(SocketModePermanentError):
        await run_socket_forever(
            APP_TOKEN,
            bot_user_id=BOT_USER_ID,
            handle=_handle_nothing,
            opener=_opener,
            connector=_FakeConnector([]),
            max_cycles=50,
            sleep=_no_sleep,
        )

    assert len(attempts) == 1, "a permanent refusal must not be retried at all"


@pytest.mark.asyncio
async def test_an_unknown_refusal_is_treated_as_transient() -> None:
    """An unrecognised code costs a bounded retry; the reverse kills a live runner."""
    attempts: list[str] = []

    def _opener(token: str):
        attempts.append(token)
        return {"ok": False, "error": "some_code_slack_added_later"}

    handled = await run_socket_forever(
        APP_TOKEN,
        bot_user_id=BOT_USER_ID,
        handle=_handle_nothing,
        opener=_opener,
        connector=_FakeConnector([]),
        max_cycles=3,
        sleep=_no_sleep,
    )

    assert handled == 0
    assert len(attempts) == 3, "an unknown code should retry, not abort"


@pytest.mark.asyncio
async def test_a_dial_failure_reconnects_rather_than_dying() -> None:
    """The socket dropping is normal; it must not end the runner."""

    def _opener(_token: str):
        return {"ok": True, "url": "wss://example.invalid/link"}

    connector = _FakeConnector(
        [OSError("connection reset"), _FakeSocket([_event_frame("after-drop")])]
    )
    seen: list[str] = []

    async def _handle(event) -> None:
        seen.append(event["text"])

    handled = await run_socket_forever(
        APP_TOKEN,
        bot_user_id=BOT_USER_ID,
        handle=_handle,
        opener=_opener,
        connector=connector,
        max_cycles=2,
        sleep=_no_sleep,
    )

    assert handled == 1
    assert seen == ["after-drop"]


@pytest.mark.asyncio
async def test_events_are_handled_and_acked_across_the_run() -> None:
    """End-to-end through the runner, not just the pump."""
    socket = _FakeSocket([_event_frame("first"), _event_frame("second")])

    def _opener(_token: str):
        return {"ok": True, "url": "wss://example.invalid/link"}

    seen: list[str] = []

    async def _handle(event) -> None:
        seen.append(event["text"])

    handled = await run_socket_forever(
        APP_TOKEN,
        bot_user_id=BOT_USER_ID,
        handle=_handle,
        opener=_opener,
        connector=_FakeConnector([socket]),
        max_cycles=1,
        sleep=_no_sleep,
    )

    assert handled == 2
    assert seen == ["first", "second"]
    assert [json.loads(s)["envelope_id"] for s in socket.sent] == [
        "env-first",
        "env-second",
    ]


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed_by_the_retry_guard() -> None:
    """The broad reconnect `except` must not turn shutdown into a retry loop.

    A runner that ignores cancellation cannot be stopped, which makes graceful
    daemon shutdown impossible and leaves the socket held.
    """

    def _opener(_token: str):
        return {"ok": True, "url": "wss://example.invalid/link"}

    class _CancellingConnector:
        def __call__(self, _url: str):
            @contextlib.asynccontextmanager
            async def _cm():
                raise asyncio.CancelledError
                yield  # pragma: no cover

            return _cm()

    with pytest.raises(asyncio.CancelledError):
        await run_socket_forever(
            APP_TOKEN,
            bot_user_id=BOT_USER_ID,
            handle=_handle_nothing,
            opener=_opener,
            connector=_CancellingConnector(),
            max_cycles=10,
            sleep=_no_sleep,
        )


@pytest.mark.asyncio
async def test_backoff_resets_after_a_connection_succeeds() -> None:
    """Otherwise a socket that dropped once inherits an old failure's penalty."""
    delays: list[float] = []

    async def _record_sleep(seconds: float) -> None:
        delays.append(seconds)

    def _opener(_token: str):
        return {"ok": True, "url": "wss://example.invalid/link"}

    # fail, fail, succeed, fail -> the post-success delay must be small again
    connector = _FakeConnector(
        [
            OSError("drop"),
            OSError("drop"),
            _FakeSocket([]),
            OSError("drop"),
        ]
    )

    await run_socket_forever(
        APP_TOKEN,
        bot_user_id=BOT_USER_ID,
        handle=_handle_nothing,
        opener=_opener,
        connector=connector,
        max_cycles=4,
        sleep=_record_sleep,
    )

    failure_delays = [d for d in delays if d > 0]
    assert failure_delays, "failures must back off"
    # Jitter is uniform in [0, backoff], so assert the CEILING moved back down:
    # the last failure's delay cannot exceed the initial backoff bound.
    assert failure_delays[-1] <= INITIAL_BACKOFF_SECONDS


@pytest.mark.asyncio
async def test_the_app_token_never_reaches_an_error_message() -> None:
    """These errors cross log boundaries; a leaked xapp- token is a live key."""

    def _opener(_token: str):
        return {"ok": False, "error": "invalid_auth"}

    with pytest.raises(SocketModePermanentError) as caught:
        await run_socket_forever(
            APP_TOKEN,
            bot_user_id=BOT_USER_ID,
            handle=_handle_nothing,
            opener=_opener,
            connector=_FakeConnector([]),
            max_cycles=1,
            sleep=_no_sleep,
        )

    assert APP_TOKEN not in str(caught.value)
    assert "xapp-" not in str(caught.value)


def test_classify_open_failure_passes_a_successful_response() -> None:
    classify_open_failure({"ok": True, "url": "wss://example.invalid/link"})


def test_classify_open_failure_raises_only_for_known_permanent_codes() -> None:
    with pytest.raises(SocketModePermanentError):
        classify_open_failure({"ok": False, "error": "invalid_auth"})
    # transient / unknown must NOT raise here — the runner retries those
    classify_open_failure({"ok": False, "error": "ratelimited"})
    classify_open_failure({"ok": False, "error": ""})


@pytest.mark.asyncio
async def test_the_network_seams_are_actually_substitutable(monkeypatch) -> None:
    """Both seams must resolve at CALL time, not bind at def time.

    They were default arguments, which bind the function object when the module
    is imported — so a test that monkeypatched the module attribute silently
    kept the real one and made a live call to Slack with a fake token. A seam
    that cannot be substituted is not a seam, and here it was a test suite
    quietly depending on the network.
    """
    opened = []

    def _fake_opener(_token, **_kw):
        opened.append("opener")
        return {"ok": True, "url": "wss://example.invalid/link"}

    @contextlib.asynccontextmanager
    async def _fake_connector(_url):
        opened.append("connector")
        yield _FakeSocket([])

    monkeypatch.setattr(
        "tinyassets.effectors.slack_socket_runner.http_opener", _fake_opener
    )
    monkeypatch.setattr(
        "tinyassets.effectors.slack_socket_runner.websockets_connector",
        _fake_connector,
    )

    await run_socket_forever(
        APP_TOKEN,
        bot_user_id=BOT_USER_ID,
        handle=_handle_nothing,
        max_cycles=1,
        sleep=_no_sleep,
    )

    assert opened == ["opener", "connector"], "neither real seam may be reached"
