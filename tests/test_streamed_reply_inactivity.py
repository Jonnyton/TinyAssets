"""A streamed model reply is judged by whether it keeps arriving, not by its length.

Founder, 2026-10-02: "if the model response is just slow your skipping it and
then that call is used up for the user". On a capped free tier every abandoned
reply is one of the day's requests. The broker now reads a streamed inference
reply with a per-read INACTIVITY window: a reply that keeps arriving runs past
the old whole-reply ceiling; one that goes silent is returned as far as it got,
marked ``stalled``; a slow drip still ends at the outer total.

Real sockets against the real driver; the times are scaled down.
"""

import socket
import threading
import time

import pytest

from tests.test_inference_reply_budget import (  # noqa: F401 - broker is a fixture
    INFERENCE_URL,
    _read_request,
    broker,
)
from tinyassets.storage.outbound_connections import (
    INFERENCE_IDLE_MIN_SECONDS,
    INFERENCE_MAX_SECONDS,
    INFERENCE_STREAM_MAX_SECONDS,
    ConnectionSecretBundle,
    CredentialBlindBroker,
    OutboundDeadlineExceeded,
    _SsrfHardenedHttpDriver,
)


class _PassThroughTLS:
    def wrap_socket(self, sock, server_hostname=None):
        return sock


def _event(n):
    return f'data: {{"choices":[{{"index":0,"delta":{{"content":"w{n} "}}}}]}}\n\n'.encode()


def _stream_server(*, events, gap_s, then_silent=False, drip=False):
    """A chunked SSE stream: ``events`` events ``gap_s`` apart, then the end,
    or silence (held open until teardown), or an endless drip."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def chunk(data):
        return f"{len(data):x}\r\n".encode() + data + b"\r\n"

    def serve():
        try:
            conn, _ = listener.accept()
            try:
                _read_request(conn)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                             b"Transfer-Encoding: chunked\r\n\r\n")
                n = 0
                while drip and not stop.wait(gap_s):
                    conn.sendall(chunk(b":\n"))
                for n in range(events):
                    if stop.wait(gap_s):
                        return
                    conn.sendall(chunk(_event(n)))
                if then_silent:
                    stop.wait(30)
                    return
                conn.sendall(chunk(b"data: [DONE]\n\n") + b"0\r\n\r\n")
            finally:
                conn.close()
        except OSError:
            pass
        finally:
            listener.close()

    threading.Thread(target=serve, daemon=True).start()

    def open_socket(_address, timeout, _source_address):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"], validator=lambda addr: addr,
        open_socket=open_socket, ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}), timeout=0.3, max_total_seconds=0.3,
    )
    return driver, port, stop


def _call(driver, port, **extra):
    return driver(
        bundle=ConnectionSecretBundle(token="stream-token-not-in-response"),
        auth_scheme="bearer", method="POST",
        url=f"https://public.example:{port}/v1/chat/completions", body={}, **extra,
    )


def test_a_stream_that_keeps_arriving_runs_past_the_old_whole_reply_budget():
    # 12 events 0.15s apart = ~1.8s, six times the 0.3s whole-reply budget; no
    # gap reaches the 0.5s inactivity window.
    driver, port, stop = _stream_server(events=12, gap_s=0.15)
    try:
        result = _call(driver, port, reply_budget_s=0.3, reply_stream=(0.5, 10.0))
        assert result["status"] == 200 and "stalled" not in result
        assert result["body"].count("data:") == 13
    finally:
        stop.set()


def test_the_same_slow_stream_without_the_window_still_ends_at_the_budget():
    """The control: without ``reply_stream`` nothing about the old bound changed."""
    driver, port, stop = _stream_server(events=12, gap_s=0.15)
    try:
        with pytest.raises(OutboundDeadlineExceeded):
            _call(driver, port, reply_budget_s=0.3)
    finally:
        stop.set()


def test_a_stream_that_goes_silent_returns_what_arrived_marked_stalled():
    driver, port, stop = _stream_server(events=3, gap_s=0.05, then_silent=True)
    started = time.monotonic()
    try:
        result = _call(driver, port, reply_budget_s=5.0, reply_stream=(0.5, 10.0))
        assert result["stalled"] is True and result["status"] == 200
        assert "w0 " in result["body"] and "w2 " in result["body"]
        assert time.monotonic() - started < 3.0
    finally:
        stop.set()


def test_a_drip_still_ends_at_the_outer_total():
    """Keep-alive bytes forever must not hold a connection forever."""
    driver, port, stop = _stream_server(events=0, gap_s=0.05, drip=True)
    started = time.monotonic()
    try:
        with pytest.raises(OutboundDeadlineExceeded):
            _call(driver, port, reply_budget_s=0.3, reply_stream=(0.5, 1.0))
        assert time.monotonic() - started < 4.0
    finally:
        stop.set()


@pytest.mark.parametrize("budget,idle,expected", [
    (None, 120, None),                       # no granted budget: no stream window
    (600.0, None, None),                     # not asked for
    (600.0, True, None),                     # a bool is not a number
    (600.0, float("nan"), None),
    (600.0, 0, None),
    (600.0, 1, (INFERENCE_IDLE_MIN_SECONDS, 3000.0)),
    (600.0, 120, (120.0, 3000.0)),
    (600.0, 10**9, (INFERENCE_MAX_SECONDS, 3000.0)),
])
def test_the_window_is_granted_only_with_the_budget_and_clamped(budget, idle, expected):
    assert CredentialBlindBroker._inference_stream(budget, 3000.0, idle) == expected


def test_the_outer_total_is_clamped():
    idle, total = CredentialBlindBroker._inference_stream(600.0, 10**12, 120)
    assert total == INFERENCE_STREAM_MAX_SECONDS


# --------------------------------------------------------------------------
# The broker grants the window only to a model source that got the budget.
# --------------------------------------------------------------------------

def _post(broker, grant, budget, idle, verb="POST"):  # noqa: F811
    instance, calls, _ = broker
    instance.dispatch(grant, verb, {"url": INFERENCE_URL, "body": {},
                                    "reply_budget_s": budget, "reply_idle_s": idle})
    return calls[-1]


def test_a_model_source_gets_its_inactivity_window(broker):  # noqa: F811
    call = _post(broker, "grant-model", 3000, 120)
    assert call["reply_stream"] == (120.0, 3000.0)
    assert call["reply_budget_s"] == INFERENCE_MAX_SECONDS
    assert "reply_idle_s" not in call["request"]


@pytest.mark.parametrize("grant,verb", [("grant-plain", "POST"), ("grant-model", "GET")])
def test_no_window_without_the_inference_budget(broker, grant, verb):  # noqa: F811
    call = _post(broker, grant, 3000, 120, verb)
    assert "reply_stream" not in call
    assert "reply_idle_s" not in call["request"]
