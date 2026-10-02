"""Streamed upstream responses (S6, I14): the driver's open_stream and the broker's stream.

The driver tests run the real pinned transport against a local stub server
that dribbles a chunked body, through the same seams the request/close tests
use (a loopback socket, a pass-through TLS context). The broker tests use the
real ledger and an injected network driver.
"""

from __future__ import annotations

import http.server
import socket
import threading
import time

import pytest

from tests.test_outbound_ssrf_driver import _PassThroughTLS
from tinyassets.storage.outbound_connections import (
    BrokerStream,
    ConnectionLedger,
    ConnectionSecretBundle,
    CredentialBlindBroker,
    OutboundDeadlineExceeded,
    ProxyRequestError,
    SsrfValidationError,
    UpstreamStream,
    _SsrfHardenedHttpDriver,
)

SECRET = "s3cr3t-bot-token"


class _Dribble(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        return

    def do_POST(self):  # noqa: N802 - http.server API
        stub = self.server.stub  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.send_response(stub.get("status", 200), stub.get("reason"))
        for name, value in stub.get("headers", ()):
            self.send_header(name, value)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for piece in stub["pieces"]:
            if piece is None:
                time.sleep(stub.get("pause", 0.3))
                continue
            self.wfile.write(f"{len(piece):x}\r\n".encode() + piece + b"\r\n")
            self.wfile.flush()
        if not stub.get("hang"):
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        else:
            time.sleep(5)


@pytest.fixture
def dribble():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Dribble)
    server.stub = {"pieces": [b"data: one\n\n"]}  # type: ignore[attr-defined]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _driver(server, **overrides):
    port = server.server_address[1]

    def open_socket(address, timeout, _source):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    kwargs = dict(resolver=lambda *_: ["127.0.0.1"], validator=lambda addr: addr,
                  open_socket=open_socket, ssl_context=_PassThroughTLS(),
                  allowed_ports=frozenset({port}))
    kwargs.update(overrides)
    return _SsrfHardenedHttpDriver(**kwargs), port


def _open(server, **overrides):
    stream_kwargs = {k: overrides.pop(k) for k in ("idle_s", "reply_budget_s") if k in overrides}
    driver, port = _driver(server, **overrides)
    return driver.open_stream(
        bundle=ConnectionSecretBundle(token=SECRET), auth_scheme="bearer", method="POST",
        url=f"https://models.example:{port}/v1/chat", headers={"Content-Type": "application/json"},
        body={"stream": True}, **stream_kwargs,
    )


def _drain(stream):
    out = bytearray()
    while chunk := stream.read(65536):
        out += chunk
    return bytes(out)


def test_the_first_bytes_arrive_before_the_upstream_finishes(dribble):
    dribble.stub.update(pieces=[b"data: first\n\n", None, None, b"data: last\n\n"], pause=0.4)
    started = time.monotonic()
    stream = _open(dribble)
    first = stream.read(65536)
    first_at = time.monotonic() - started
    rest = _drain(stream)
    assert first == b"data: first\n\n" and rest == b"data: last\n\n"
    assert first_at < 0.6 < time.monotonic() - started
    assert stream.status == 200 and stream.read(10) == b""


def test_silence_longer_than_the_idle_bound_is_a_deadline(dribble):
    dribble.stub.update(pieces=[b"x", None], pause=3, hang=True)
    stream = _open(dribble, idle_s=0.5)
    assert stream.read(10) == b"x"
    with pytest.raises(OutboundDeadlineExceeded):
        stream.read(10)


def test_the_body_bound_is_cumulative(dribble):
    dribble.stub.update(pieces=[b"a" * 600, b"b" * 600])
    stream = _open(dribble, max_body_bytes=1000)
    with pytest.raises(SsrfValidationError):
        _drain(stream)


def test_a_header_echoing_the_credential_is_refused_before_a_stream_exists(dribble):
    dribble.stub.update(headers=[("X-Echo", f"Bearer {SECRET}")])
    with pytest.raises(ProxyRequestError):
        _open(dribble)


def test_a_reason_phrase_echoing_the_credential_is_refused(dribble):
    dribble.stub.update(reason=SECRET)
    with pytest.raises(ProxyRequestError):
        _open(dribble)


def test_close_unblocks_a_read_waiting_in_another_thread(dribble):
    dribble.stub.update(pieces=[b"x", None], pause=5, hang=True)
    stream = _open(dribble)
    assert stream.read(10) == b"x"
    errors = []

    def reader():
        try:
            stream.read(10)
        except Exception as exc:  # noqa: BLE001 - the test inspects it
            errors.append(exc)

    thread = threading.Thread(target=reader)
    thread.start()
    time.sleep(0.3)
    stream.close()
    thread.join(3)
    assert not thread.is_alive()


# ── the broker's stream ─────────────────────────────────────────────────────


@pytest.fixture
def ledger(tmp_path):
    ledger = ConnectionLedger(tmp_path / "outbound.db",
                              verify_authenticated_principal=lambda: "owner")
    ledger.create_connection(
        connection_id="conn-model", owner_user_id="owner", connection_class="http",
        connection_type="http", auth_scheme="bearer", scopes=("POST",), provider="http",
        destination="compute:conn-model", credential_ref="vault://http/synthetic",
        allowed_endpoints=[{"host": "models.example.com", "path_template": "/v1/chat",
                            "methods": ["POST"]}],
    )
    ledger.grant_connection(grant_id="grant-model", connection_id="conn-model",
                            owner_user_id="owner", universe_id="universe")
    return ledger


def _broker(ledger, pieces, *, headers=None, credential="held-credential-xyz"):
    calls = []

    def network(**kwargs):
        calls.append(kwargs)
        assert kwargs["stream"] is True
        return UpstreamStream.complete(
            {"status": 200, "reason": "OK", "headers": headers or {},
             "body": b"".join(pieces)}, (),
        )

    return CredentialBlindBroker(ledger, resolve_credential=lambda *_: credential,
                                 network_request=network), calls


def _read_all(stream: BrokerStream) -> bytes:
    out = bytearray()
    while (chunk := stream.read(7)) is not None:
        out += chunk
    return bytes(out)


def test_the_broker_streams_a_clean_body_whole(ledger):
    broker, calls = _broker(ledger, [b"data: hello\n\n", b"data: [DONE]\n\n"])
    stream = broker.dispatch("grant-model", "POST",
                             {"url": "https://models.example.com/v1/chat", "body": {}},
                             stream=True)
    assert isinstance(stream, BrokerStream) and stream.status == 200
    assert _read_all(stream) == b"data: hello\n\ndata: [DONE]\n\n"
    assert len(calls) == 1


def test_the_broker_withholds_its_own_held_value_from_the_body(ledger):
    broker, _ = _broker(ledger, [b"data: leaked held-credential-xyz\n\n"])
    stream = broker.dispatch("grant-model", "POST",
                             {"url": "https://models.example.com/v1/chat", "body": {}},
                             stream=True)
    forwarded = bytearray()
    with pytest.raises(ProxyRequestError):
        while (chunk := stream.read(5)) is not None:
            forwarded += chunk
    assert b"held-credential-xyz" not in bytes(forwarded)
    assert len(forwarded) <= len(b"data: leaked ")


def test_the_broker_refuses_a_header_echoing_its_held_value(ledger):
    broker, _ = _broker(ledger, [b"ok"], headers={"x-echo": "held-credential-xyz"})
    with pytest.raises(ProxyRequestError):
        broker.dispatch("grant-model", "POST",
                        {"url": "https://models.example.com/v1/chat", "body": {}}, stream=True)


def test_request_close_dispatch_is_unchanged(ledger):
    calls = []

    def network(**kwargs):
        calls.append(kwargs)
        return {"status": 200, "body": "ok"}

    broker = CredentialBlindBroker(ledger, resolve_credential=lambda *_: "c",
                                   network_request=network)
    result = broker.dispatch("grant-model", "POST",
                             {"url": "https://models.example.com/v1/chat", "body": {}})
    assert result == {"status": 200, "body": "ok"} and "stream" not in calls[0]
