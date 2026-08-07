"""The pump against a REAL WebSocket, not a stand-in.

Every other test in this feature drives a fake socket object that I wrote to
match my own assumptions. That proves the decision logic and proves nothing
about whether `websockets`' connection actually behaves the way the pump
expects — async iteration yielding frames, `send` taking a str. If that
assumption were wrong, all 87 tests would still pass and nothing would work.

So this test stands up a real `websockets` server on localhost, dials it with
the real client, and runs the real pump over it. No Slack, no credentials, no
network beyond the loopback interface.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tinyassets.effectors.slack_socket_mode import pump
from tinyassets.effectors.slack_socket_runner import websockets_connector

pytest.importorskip("websockets")

BOT_USER = "U08BOT0001"


def _envelope(envelope_id: str, text: str, user: str = "U07HUM0001") -> str:
    return json.dumps(
        {
            "type": "events_api",
            "envelope_id": envelope_id,
            "payload": {
                "type": "event_callback",
                "team_id": "T0BN5LK57FT",
                "event_id": f"Ev-{envelope_id}",
                "event": {
                    "type": "app_mention",
                    "user": user,
                    "text": text,
                    "channel": "C0123",
                    "ts": "1700000000.000100",
                },
            },
        }
    )


@pytest.mark.asyncio
async def test_the_pump_works_over_a_real_websocket():
    """Frames in, acks out, over an actual socket."""
    from websockets.asyncio.server import serve

    acks: list[str] = []
    done = asyncio.Event()

    async def _handler(connection):
        # Slack's side: greet, send two events, read the acks, then close.
        await connection.send(json.dumps({"type": "hello", "num_connections": 1}))
        await connection.send(_envelope("E-1", "first question"))
        await connection.send(_envelope("E-2", "second question"))
        try:
            for _ in range(2):
                acks.append(await connection.recv())
        finally:
            done.set()
            await connection.close()

    async with serve(_handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        seen: list[str] = []

        async def _handle(event):
            seen.append(event["text"])

        async with websockets_connector(f"ws://127.0.0.1:{port}") as connection:
            handled = await asyncio.wait_for(
                pump(connection, bot_user_id=BOT_USER, handle=_handle),
                timeout=10,
            )

        await asyncio.wait_for(done.wait(), timeout=10)

    assert handled == 2, "both events were handled over a real socket"
    assert seen == ["first question", "second question"]
    assert [json.loads(a)["envelope_id"] for a in acks] == ["E-1", "E-2"]


@pytest.mark.asyncio
async def test_the_loop_guard_holds_over_a_real_websocket():
    """The guard that stops an unbounded self-reply loop, on a real connection."""
    from websockets.asyncio.server import serve

    async def _handler(connection):
        # Our own reply coming back, in the shape that used to slip through.
        await connection.send(
            json.dumps(
                {
                    "type": "events_api",
                    "envelope_id": "E-self",
                    "payload": {
                        "type": "event_callback",
                        "team_id": "T0BN5LK57FT",
                        "event_id": "Ev-self",
                        "event": {
                            "type": "message",
                            "app_id": "A_SELF",
                            "bot_profile": {"id": "B_SELF"},
                            "text": "my own answer",
                            "channel": "C0123",
                            "ts": "1700000000.000200",
                        },
                    },
                }
            )
        )
        await connection.recv()  # the ack
        await connection.close()

    async with serve(_handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        seen: list[str] = []

        async def _handle(event):
            seen.append(event.get("text", ""))

        async with websockets_connector(f"ws://127.0.0.1:{port}") as connection:
            handled = await asyncio.wait_for(
                pump(connection, bot_user_id=BOT_USER, handle=_handle),
                timeout=10,
            )

    assert handled == 0, "our own message must never come back to the handler"
    assert seen == []


@pytest.mark.asyncio
async def test_the_runner_survives_a_real_dropped_connection():
    """A network drop is not a crash — it is a reconnect.

    An abruptly aborted socket raises `ConnectionClosedError` out of the async
    iteration itself, which `pump` does not catch (it guards frame *processing*,
    not the connection). That exception is the runner's signal to reconnect, so
    the property worth testing is not "pump returns quietly" — it is that the
    runner recovers and keeps answering. Which is what this asserts, against a
    genuinely aborted TCP connection rather than a fake raising on cue.
    """
    from websockets.asyncio.server import serve

    from tinyassets.effectors.slack_socket_runner import run_socket_forever

    connections = 0

    async def _handler(connection):
        nonlocal connections
        connections += 1
        if connections == 1:
            await connection.send(_envelope("E-1", "before the drop"))
            await connection.recv()
            # Slam it shut with no close handshake, the way a real network fails.
            connection.transport.abort()
            return
        await connection.send(_envelope("E-2", "after the reconnect"))
        await connection.recv()
        await connection.close()

    async with serve(_handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        seen: list[str] = []

        async def _handle(event):
            seen.append(event["text"])

        async def _no_sleep(_seconds):
            return None

        # The opener returns a `wss://` url because `open_socket_url` requires
        # one, and that check stays — a plaintext socket carrying workspace
        # traffic would be a real downgrade, and relaxing a live guard so a test
        # can use loopback is backwards. The connector is the injected seam, so
        # it dials the actual local server. Everything below the URL is real:
        # real TCP, real WebSocket framing, real abort, real reconnect.
        def _dial_local(_url):
            return websockets_connector(f"ws://127.0.0.1:{port}")

        handled = await asyncio.wait_for(
            run_socket_forever(
                "xapp-EXAMPLE-NOT-A-REAL-TOKEN",
                bot_user_id=BOT_USER,
                handle=_handle,
                opener=lambda _t: {"ok": True, "url": "wss://slack.invalid/link"},
                connector=_dial_local,
                max_cycles=2,
                sleep=_no_sleep,
            ),
            timeout=15,
        )

    assert connections == 2, "the runner dialled again after the drop"
    assert handled == 2
    assert seen == ["before the drop", "after the reconnect"]
