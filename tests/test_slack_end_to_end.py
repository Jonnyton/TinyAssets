"""The assembled agent against a faithful Socket Mode server.

This is the closest thing to a real Slack test that does not require
credentials. It is not a substitute for one, and it is not claimed as one — but
it exists to make the remaining gap as small as possible, so that what is left
untested is Slack's *identity* rather than Slack's *protocol*.

What is real here: the vault, credential resolution and type checks, the socket
runner and its reconnect logic, `websockets` client framing over loopback TCP,
the pump, envelope parsing, the loop guard, deduplication, the binding
resolver, the tier decision, and a genuine HTTP POST carrying a real
Authorization header to a `chat.postMessage` stand-in.

What is simulated: Slack's side of the wire — but following the documented
lifecycle rather than a convenient one. That includes the parts most likely to
be got wrong and least likely to be exercised by a happy-path fake:

  hello -> event -> ack -> disconnect(warning) -> more events -> close
        -> reconnect on a FRESH url -> redelivery of an already-acked event

What is stubbed: `converse`, because a provider call costs money and proves
nothing about the plumbing.
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tinyassets.credential_vault import write_credential_vault
from tinyassets.effectors import slack_agent_service as service
from tinyassets.effectors import slack_socket_runner as runner
from tinyassets.effectors import slack_transport

pytest.importorskip("websockets")

TEAM = "T0BN5LK57FT"
APP = "A0BN1Q98MTQ"
BOT_USER = "U08BOT0001"
HUMAN = "U07HUM0001"
UNIVERSE = "u-e2e"
CONNECTION = "slack-main"
APP_TOKEN = f"xapp-1-{APP}-1234567890123-exampleonly"
BOT_TOKEN = "xoxb-EXAMPLE-NOT-A-REAL-TOKEN"


def _event_envelope(envelope_id, text, *, event_id=None, retry_attempt=0):
    """Slack's documented Socket Mode envelope, including the fields a
    convenient fake tends to omit."""
    return json.dumps(
        {
            "envelope_id": envelope_id,
            "type": "events_api",
            "accepts_response_payload": False,
            "retry_attempt": retry_attempt,
            "retry_reason": "" if not retry_attempt else "timeout",
            "payload": {
                "token": "deprecated-verification-token",
                "team_id": TEAM,
                "api_app_id": APP,
                "type": "event_callback",
                "event_id": event_id or f"Ev-{envelope_id}",
                "event_time": 1700000000,
                "event": {
                    "type": "app_mention",
                    "user": HUMAN,
                    "text": f"<@{BOT_USER}> {text}",
                    "ts": "1700000000.000100",
                    "channel": "C0123",
                    "event_ts": "1700000000.000100",
                },
            },
        }
    )


def _self_authored_envelope(envelope_id):
    """Our own reply coming back — the shape that used to slip the loop guard."""
    return json.dumps(
        {
            "envelope_id": envelope_id,
            "type": "events_api",
            "payload": {
                "team_id": TEAM,
                "api_app_id": APP,
                "type": "event_callback",
                "event_id": f"Ev-{envelope_id}",
                "event": {
                    "type": "message",
                    "app_id": APP,
                    "bot_profile": {"id": "B08BOT0001", "app_id": APP},
                    "text": "an answer the agent itself posted",
                    "channel": "C0123",
                    "ts": "1700000000.000300",
                },
            },
        }
    )


class _PostMessage(BaseHTTPRequestHandler):
    posts: list[dict] = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _PostMessage.posts.append(
            {"body": body, "auth": self.headers.get("Authorization", "")}
        )
        payload = json.dumps(
            {"ok": True, "ts": "1700000000.000900", "channel": body.get("channel")}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_a):
        pass


@pytest.mark.asyncio
async def test_the_documented_socket_lifecycle_end_to_end(tmp_path, monkeypatch):
    """One agent, two connections, a warning disconnect, and a redelivery."""
    from websockets.asyncio.server import serve

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / UNIVERSE
    udir.mkdir()
    write_credential_vault(
        udir,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": CONNECTION,
                "bot_token": BOT_TOKEN,
                "app_token": APP_TOKEN,
            }
        ],
    )

    _PostMessage.posts = []
    http = HTTPServer(("127.0.0.1", 0), _PostMessage)
    threading.Thread(target=http.serve_forever, daemon=True).start()

    acks: list[str] = []
    connections = 0

    async def _slack(connection):
        nonlocal connections
        connections += 1
        await connection.send(
            json.dumps(
                {
                    "type": "hello",
                    "num_connections": 1,
                    "connection_info": {"app_id": APP},
                }
            )
        )
        if connections == 1:
            await connection.send(_event_envelope("E-1", "first question"))
            acks.append(await connection.recv())
            # Our own reply arriving back. Must be acked and never answered.
            await connection.send(_self_authored_envelope("E-self"))
            acks.append(await connection.recv())
            # Slack's ~10s warning: frames after it must still be handled.
            await connection.send(
                json.dumps({"type": "disconnect", "reason": "warning"})
            )
            await connection.send(_event_envelope("E-2", "second question"))
            acks.append(await connection.recv())
            await connection.close()
            return
        # Second connection: Slack redelivers an event it never saw acked.
        await connection.send(
            _event_envelope("E-3", "first question", event_id="Ev-E-1", retry_attempt=1)
        )
        acks.append(await connection.recv())
        await connection.close()

    async with serve(_slack, "127.0.0.1", 0) as ws:
        port = ws.sockets[0].getsockname()[1]
        opened: list[str] = []

        def _opener(_token):
            opened.append("open")
            return {"ok": True, "url": f"wss://slack.invalid/link/{len(opened)}"}

        real_connect = runner.websockets_connector
        monkeypatch.setattr(runner, "http_opener", _opener)
        monkeypatch.setattr(
            runner,
            "websockets_connector",
            lambda _u: real_connect(f"ws://127.0.0.1:{port}"),
        )

        real_transport = slack_transport.build_slack_transport
        monkeypatch.setattr(
            service,
            "build_slack_transport",
            lambda d, **kw: real_transport(
                d, url=f"http://127.0.0.1:{http.server_address[1]}/api/chat.postMessage"
            ),
        )

        turns: list[str] = []

        def _converse(universe_id, message, *, actor_id="", founder_grant=None,
                      conversation_history=None):
            who = "founder" if founder_grant is not None else "not-founder"
            turns.append(f"{universe_id}|{who}|{actor_id}|{message}")
            return f"answering: {message}"

        config = service.SlackAgentConfig(
            universe_id=UNIVERSE,
            connection_id=CONNECTION,
            team_id=TEAM,
            bot_user_id=BOT_USER,
            api_app_id=APP,
        )
        handled = await asyncio.wait_for(
            service.run_slack_agent(config, max_cycles=2, converse=_converse),
            timeout=30,
        )

    http.shutdown()

    # Two real questions answered; the self-authored message and the
    # redelivery must not have become turns.
    assert handled == 2, f"expected 2 handled, got {handled}"
    assert [t.split("|")[-1] for t in turns] == ["first question", "second question"]

    # The recognition outcome and identity that reached the provider. This
    # sender has no founder mapping, so the platform hands the engine no grant
    # and the turn runs at the external floor.
    assert all(f"|not-founder|slack:{TEAM}:{HUMAN}|" in t for t in turns)

    # Every envelope acknowledged, including the ones never answered.
    assert [json.loads(a)["envelope_id"] for a in acks] == [
        "E-1",
        "E-self",
        "E-2",
        "E-3",
    ]

    # Reconnect used a FRESH apps.connections.open call.
    assert len(opened) == 2

    # Two replies, threaded, posted with the bot token.
    assert len(_PostMessage.posts) == 2
    for post in _PostMessage.posts:
        assert post["body"]["channel"] == "C0123"
        assert post["body"]["thread_ts"] == "1700000000.000100"
        assert post["auth"].startswith("Bearer xoxb-")
    assert [p["body"]["text"] for p in _PostMessage.posts] == [
        "answering: first question",
        "answering: second question",
    ]


@pytest.mark.asyncio
async def test_a_missing_credential_stops_before_any_socket_opens(
    tmp_path, monkeypatch
):
    """The "up but answering nobody" shape, end to end: the service must refuse
    to start rather than connect successfully and fail at first reply."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    (tmp_path / UNIVERSE).mkdir()
    write_credential_vault(
        tmp_path / UNIVERSE,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": CONNECTION,
                "app_token": APP_TOKEN,  # no bot token
            }
        ],
    )
    opened = []
    monkeypatch.setattr(runner, "http_opener", lambda _t: opened.append(1) or {})

    config = service.SlackAgentConfig(
        universe_id=UNIVERSE,
        connection_id=CONNECTION,
        team_id=TEAM,
        bot_user_id=BOT_USER,
    )

    with pytest.raises(service.SlackAgentConfigError):
        await service.run_slack_agent(config, max_cycles=1)

    assert opened == [], "it must not even reach Slack"


@pytest.mark.asyncio
async def test_an_event_from_another_workspace_is_acked_and_ignored(
    tmp_path, monkeypatch
):
    """End to end over a real socket, not just at the resolver."""
    from websockets.asyncio.server import serve

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / UNIVERSE
    udir.mkdir()
    write_credential_vault(
        udir,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": CONNECTION,
                "bot_token": BOT_TOKEN,
                "app_token": APP_TOKEN,
            }
        ],
    )

    frame = json.loads(_event_envelope("E-x", "hello"))
    frame["payload"]["team_id"] = "T_SOMEONE_ELSE"
    acks = []

    async def _slack(connection):
        await connection.send(json.dumps(frame))
        acks.append(await connection.recv())
        await connection.close()

    async with serve(_slack, "127.0.0.1", 0) as ws:
        port = ws.sockets[0].getsockname()[1]
        real_connect = runner.websockets_connector
        monkeypatch.setattr(
            runner, "http_opener", lambda _t: {"ok": True, "url": "wss://slack.invalid/x"}
        )
        monkeypatch.setattr(
            runner,
            "websockets_connector",
            lambda _u: real_connect(f"ws://127.0.0.1:{port}"),
        )
        turns = []
        posts = []
        monkeypatch.setattr(
            service,
            "build_slack_transport",
            lambda *_a, **_kw: lambda *a, **kw: posts.append(a),
        )

        config = service.SlackAgentConfig(
            universe_id=UNIVERSE,
            connection_id=CONNECTION,
            team_id=TEAM,
            bot_user_id=BOT_USER,
        )
        await asyncio.wait_for(
            service.run_slack_agent(
                config,
                max_cycles=1,
                converse=lambda *a, **k: turns.append(a) or "never",
            ),
            timeout=20,
        )

    assert turns == [], "no provider call for an unbound workspace"
    assert posts == [], "and nothing said back"
    assert len(acks) == 1, "but still acknowledged, so Slack stops resending"
