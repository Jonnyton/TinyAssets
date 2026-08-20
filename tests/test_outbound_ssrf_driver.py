"""Adversarial tests for the general SSRF-hardened outbound HTTP driver.

Scope: channel-agnostic-outbound design.md D3/D4/D5, SLICE 1 (DARK). These
tests exercise the *mechanism* (`_SsrfHardenedHttpDriver` + its strict transport
helpers) directly. Each case would FAIL if the corresponding guard were removed:
they assert refusal on a hostile input or scrubbing of a leaked secret, not just
that the happy path works.

The driver exposes injectable seams (resolver / address validator / socket
opener / TLS context) whose DEFAULTS are the secure production implementations.
The security-critical default classifier (`_classify_global_address`) is tested
on its own; the live-socket integration cases inject a permissive validator and
a loopback socket so the real request/response/pinning/read/scrub path runs
against a local stub server (a loopback address can never pass `is_global`, so
there is no other way to exercise the transport end-to-end).
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import ssl
import threading
import time

import pytest

from tinyassets.storage.outbound_connections import (
    ConnectionSecretBundle,
    ProxyRequestError,
    SsrfValidationError,
    _classify_global_address,
    _default_ssl_context,
    _parse_canonical_https_url,
    _sanitize_child_environment,
    _SsrfHardenedHttpDriver,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class _PassThroughTLS:
    """A TLS context that returns the plain socket unwrapped.

    Lets the integration cases speak plain HTTP to a local stub through the real
    `_PinnedHTTPSConnection` without generating a certificate, while still
    proving the SNI/hostname value the driver *would* verify against.
    """

    def __init__(self) -> None:
        self.verify_mode = ssl.CERT_NONE
        self.check_hostname = False
        self.captured_server_hostname: str | None = None

    def wrap_socket(self, sock, server_hostname=None):  # noqa: ANN001
        self.captured_server_hostname = server_hostname
        return sock


class _FakeSock:
    """A socket whose peer address is controllable (peer-validation tests)."""

    def __init__(self, peer: str) -> None:
        self._peer = peer
        self.closed = False

    def getpeername(self):
        return (self._peer, 443)

    def close(self):
        self.closed = True


class _StopDial(Exception):
    """Raised by an injected opener to halt before any real network I/O."""


def _never_dial(*_args, **_kwargs):
    raise AssertionError("the transport must not open a socket for this input")


class _StubHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):  # silence the test server
        return

    def _serve(self):
        stub = self.server.stub  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        stub["received"] = {
            "path": self.path,
            "headers": {k.lower(): v for k, v in self.headers.items()},
            "body": raw,
        }
        payload = stub["body"]
        self.send_response(stub["status"])
        for name, value in stub.get("extra_headers", ()):  # type: ignore[union-attr]
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _serve
    do_POST = _serve


@pytest.fixture
def stub_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.stub = {  # type: ignore[attr-defined]
        "status": 200,
        "body": b"ok",
        "extra_headers": (),
        "received": None,
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _local_driver(server, **overrides):
    """A driver that dials `server` over loopback while pretending it pinned a
    public address; records resolver + open_socket calls for assertions."""
    port = server.server_address[1]
    calls = {"resolver": 0, "open_socket": []}

    def resolver(_host, _port):
        calls["resolver"] += 1
        return ["127.0.0.1"]

    def open_socket(address, timeout, _source_address):
        calls["open_socket"].append(address)
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    context = _PassThroughTLS()
    kwargs = dict(
        resolver=resolver,
        validator=lambda addr: addr,  # permissive: allow the loopback pin
        open_socket=open_socket,
        ssl_context=context,
        allowed_ports=frozenset({port}),
    )
    kwargs.update(overrides)
    return _SsrfHardenedHttpDriver(**kwargs), calls, context, port


# --------------------------------------------------------------------------- #
# Positive path — a normal public https call succeeds through the pinned path
# --------------------------------------------------------------------------- #
def test_positive_public_https_call_succeeds_through_the_pinned_path(stub_server):
    stub_server.stub.update(status=200, body=b'{"ok": true}')
    driver, calls, context, port = _local_driver(stub_server)

    result = driver(
        bundle=ConnectionSecretBundle(token="s3cr3t-bot-token"),
        auth_scheme="bearer",
        method="POST",
        url=f"https://public.example:{port}/api/send",
        headers={"Content-Type": "application/json"},
        body={"text": "hi"},
    )

    assert result["status"] == 200
    assert result["body"] == '{"ok": true}'
    # Resolved exactly once and pinned to the validated address (no re-resolve).
    assert calls["resolver"] == 1
    assert calls["open_socket"] == [("127.0.0.1", port)]
    # SNI / certificate verification targets the ORIGINAL hostname, not the pin.
    assert context.captured_server_hostname == "public.example"
    # The auth header the server saw came from the bundle, applied in-driver.
    received = stub_server.stub["received"]
    assert received["headers"]["authorization"] == "Bearer s3cr3t-bot-token"
    assert received["path"] == "/api/send"
    assert received["body"] == b'{"text":"hi"}'
    # The credential never rides back out in the returned object.
    assert "s3cr3t-bot-token" not in json.dumps(result)


def test_ambient_env_proxy_is_ignored(stub_server, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
    stub_server.stub.update(status=200, body=b"ok")
    driver, calls, _context, port = _local_driver(stub_server)

    result = driver(
        bundle=ConnectionSecretBundle(token="bearer-tok-not-in-any-response"),
        auth_scheme="bearer",
        method="GET",
        url=f"https://public.example:{port}/x",
    )

    assert result["status"] == 200
    # Straight to the pinned socket — the env proxy was never consulted.
    assert calls["open_socket"] == [("127.0.0.1", port)]


# --------------------------------------------------------------------------- #
# URL canonicalization refusals
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "url",
    [
        "http://public.example/x",  # non-https scheme (metadata via http too)
        "ftp://public.example/x",  # other scheme
        "https://user:pass@public.example/x",  # userinfo
        "https://public.example/x#frag",  # fragment
        "https://public.example/a/../b",  # dot-segment
        "https://public.example/./b",  # single-dot segment
        "https://public.example/%252e%252e/x",  # double-encoding
        "https://public.example\\@evil.example/x",  # backslash
        "https://public.example /x",  # embedded whitespace
        "https://public.example:8443/x",  # unexpected port (default allows 443)
        "https://2130706433/x",  # decimal IP literal
        "https://0x7f000001/x",  # hex IP literal
        "https://0177.0.0.1/x",  # octal-ish dotted literal
        "https://localhost/x",  # single-label host (no real TLD)
        "https://public.example/public/%2e%2e/admin",  # encoded dot-seg (Codex)
        "https://public.example/public/.%2e/admin",  # mixed encoded dot-seg
        "https://public.example/public/%2e%2e%2fadmin",  # encoded dot + slash
        "https://public.example/%2E%2E/admin",  # uppercase encoded dot-seg
    ],
)
def test_noncanonical_or_unsafe_urls_are_refused(url):
    driver = _SsrfHardenedHttpDriver(open_socket=_never_dial)
    with pytest.raises(SsrfValidationError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url=url,
        )


# --------------------------------------------------------------------------- #
# Address classification refusals (literal hosts that pass parse, fail classify)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.169.254/latest/meta-data/",  # link-local metadata
        "https://[::ffff:169.254.169.254]/x",  # IPv4-mapped IPv6 metadata
        "https://127.0.0.1/x",  # loopback
        "https://[::1]/x",  # IPv6 loopback
        "https://10.0.0.5/x",  # private
        "https://192.168.1.1/x",  # private
        "https://172.16.9.9/x",  # private
        "https://0.0.0.0/x",  # unspecified
        "https://100.64.0.1/x",  # shared / CGNAT
        "https://[fec0::1]/x",  # deprecated IPv6 site-local (Codex-found)
        "https://[64:ff9b::c0a8:1]/x",  # NAT64 embedding 192.168.0.1 (Codex-found)
    ],
)
def test_nonglobal_ip_literals_are_refused(url):
    driver = _SsrfHardenedHttpDriver(open_socket=_never_dial)
    with pytest.raises(SsrfValidationError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url=url,
        )


def test_classifier_unwraps_ipv4_mapped_ipv6():
    with pytest.raises(SsrfValidationError):
        _classify_global_address("::ffff:169.254.169.254")
    with pytest.raises(SsrfValidationError):
        _classify_global_address("::ffff:127.0.0.1")
    # A genuine public address passes.
    assert _classify_global_address("93.184.216.34") == "93.184.216.34"


# --------------------------------------------------------------------------- #
# DNS resolution / rebinding / pinning
# --------------------------------------------------------------------------- #
def test_resolver_returning_private_ip_is_refused_before_connect():
    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["10.0.0.5"],
        open_socket=_never_dial,
        ssl_context=_PassThroughTLS(),
    )
    with pytest.raises(SsrfValidationError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url="https://public.example/x",
        )


def test_all_resolved_addresses_are_validated_not_just_first():
    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["93.184.216.34", "10.0.0.5"],
        open_socket=_never_dial,
        ssl_context=_PassThroughTLS(),
    )
    with pytest.raises(SsrfValidationError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url="https://public.example/x",
        )


def test_pins_first_validated_address_and_never_reresolves():
    resolver_calls: list[str] = []
    dialed: list[tuple[str, int]] = []

    def resolver(host, _port):
        resolver_calls.append(host)
        # A rebinding resolver would hand back a private IP on a *second* call.
        # Pinning means we never call it twice, so the private answer is unused.
        return ["93.184.216.34"] if len(resolver_calls) == 1 else ["10.0.0.5"]

    def open_socket(address, _timeout, _source_address):
        dialed.append(address)
        raise _StopDial

    driver = _SsrfHardenedHttpDriver(
        resolver=resolver,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
    )
    with pytest.raises(ProxyRequestError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url="https://public.example/x",
        )

    assert resolver_calls == ["public.example"]  # resolved exactly once
    assert dialed == [("93.184.216.34", 443)]  # dialed the FIRST validated addr


def test_connected_peer_mismatch_is_rejected():
    fake = _FakeSock("10.0.0.5")  # rerouted to a private address after the pin

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["93.184.216.34"],
        validator=lambda addr: addr,  # permit the public pin
        open_socket=lambda *_a: fake,
        ssl_context=_PassThroughTLS(),
    )
    with pytest.raises(ProxyRequestError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url="https://public.example/x",
        )
    assert fake.closed


# --------------------------------------------------------------------------- #
# Caller-supplied sensitive headers are refused (auth is applied in-driver only)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_header",
    [
        {"Authorization": "Bearer attacker"},
        {"authorization": "Bearer attacker"},
        {"Host": "evil.example"},
        {"Cookie": "sid=1"},
        {"Proxy-Authorization": "Basic x"},
        {"Proxy-Connection": "keep-alive"},
        {"X-Evil": "line1\r\nInjected: 1"},  # header CR/LF injection
        {"Content-Length": "0"},  # request-smuggling framing header (Codex-found)
        {"Transfer-Encoding": "chunked"},  # request-smuggling framing header
        {"Connection": "close"},  # hop-by-hop header
    ],
)
def test_caller_supplied_sensitive_or_malformed_headers_are_refused(bad_header):
    driver = _SsrfHardenedHttpDriver(open_socket=_never_dial)
    with pytest.raises(SsrfValidationError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url="https://public.example/x",
            headers=bad_header,
        )


@pytest.mark.parametrize("scheme", ["bearer", "header"])
def test_auth_value_with_obs_fold_crlf_is_refused(scheme):
    # A bundle secret carrying CR/LF (obs-fold) would emit a folded header line
    # http.client accepts verbatim, re-opening request smuggling (Codex-found).
    driver = _SsrfHardenedHttpDriver(open_socket=_never_dial)
    with pytest.raises(SsrfValidationError):
        driver(
            bundle=ConnectionSecretBundle(token="secret\r\n Content-Length: 0"),
            auth_scheme=scheme,
            header_name="X-Api-Key",
            method="POST",
            url="https://public.example/x",
            body=b"GET /admin HTTP/1.1\r\nHost: internal\r\n\r\n",
        )


@pytest.mark.parametrize(
    "header_name",
    [
        "Content-Length",  # framing → request smuggling (Codex-found)
        "Transfer-Encoding",
        "Connection",
        "Host",
        "Cookie",
        "Proxy-Authorization",
    ],
)
def test_custom_auth_header_name_cannot_bypass_the_header_policy(header_name):
    # `auth_scheme="header"` must apply the SAME framing/sensitive/proxy policy
    # to its header name, or it is a back door around `_validated_request_headers`.
    driver = _SsrfHardenedHttpDriver(open_socket=_never_dial)
    with pytest.raises(SsrfValidationError):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="header",
            header_name=header_name,
            method="POST",
            url="https://public.example/x",
            body=b"GET /admin HTTP/1.1\r\nHost: internal\r\n\r\n",
        )


# --------------------------------------------------------------------------- #
# Response bounds
# --------------------------------------------------------------------------- #
def test_oversized_response_is_refused(stub_server):
    stub_server.stub.update(status=200, body=b"x" * 4096)
    driver, _calls, _context, port = _local_driver(stub_server, max_body_bytes=1024)
    with pytest.raises(SsrfValidationError, match="size bound"):
        driver(
            bundle=ConnectionSecretBundle(token="t"),
            auth_scheme="bearer",
            method="GET",
            url=f"https://public.example:{port}/big",
        )


def test_redirect_is_not_followed_and_returned_as_is(stub_server):
    stub_server.stub.update(
        status=302,
        body=b"",
        extra_headers=(("Location", "http://169.254.169.254/latest/meta-data/"),),
    )
    driver, calls, _context, port = _local_driver(stub_server)

    result = driver(
        bundle=ConnectionSecretBundle(token="bearer-tok-not-in-any-response"),
        auth_scheme="bearer",
        method="GET",
        url=f"https://public.example:{port}/r",
    )

    assert result["status"] == 302
    assert result["headers"]["location"] == "http://169.254.169.254/latest/meta-data/"
    # Exactly one socket opened — the redirect target was never dialed.
    assert len(calls["open_socket"]) == 1


# --------------------------------------------------------------------------- #
# Credential-blindness: the whole typed bundle is scrubbed from the response
# --------------------------------------------------------------------------- #
def test_response_echoing_the_injected_secret_is_scrubbed(stub_server):
    secret = "xoxb-super-secret-value"
    stub_server.stub.update(status=200, body=f"echo {secret}".encode())
    driver, _calls, _context, port = _local_driver(stub_server)

    with pytest.raises(ProxyRequestError) as raised:
        driver(
            bundle=ConnectionSecretBundle(token=secret),
            auth_scheme="bearer",
            method="GET",
            url=f"https://public.example:{port}/x",
        )
    assert secret not in str(raised.value)
    assert "unsafe destination response" in str(raised.value)


def test_basic_auth_base64_echo_is_scrubbed(stub_server):
    # A Basic credential goes on the wire as base64(user:pass), which matches no
    # raw bundle member; an adversarial destination could echo that blob and a
    # caller could reverse it. The wire-value scrub must catch it (Codex-found).
    import base64

    username, password = "admin", "s3cr3t-password-value"
    blob = base64.b64encode(f"{username}:{password}".encode()).decode()
    stub_server.stub.update(status=200, body=f"you sent {blob}".encode())
    driver, _calls, _context, port = _local_driver(stub_server)

    with pytest.raises(ProxyRequestError, match="unsafe destination response") as raised:
        driver(
            bundle=ConnectionSecretBundle(username=username, password=password),
            auth_scheme="basic",
            method="GET",
            url=f"https://public.example:{port}/x",
        )
    assert blob not in str(raised.value)


def test_exception_context_does_not_leak_the_secret():
    # A destination that replies with a non-HTTP line containing the token makes
    # http.client raise BadStatusLine(<that line>). The sanitized ProxyRequestError
    # must not carry it on __context__/__cause__ (the slack_transport.py:89 class).
    token = "xoxb-CONTEXT-LEAK-must-not-appear"
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve():
        try:
            conn, _ = listener.accept()
            try:
                conn.recv(65535)
                conn.sendall(f"{token} NOT-HTTP\r\n\r\n".encode())
            finally:
                conn.close()
        finally:
            listener.close()

    threading.Thread(target=serve, daemon=True).start()

    def open_socket(_address, timeout, _source_address):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
    )
    with pytest.raises(ProxyRequestError) as raised:
        driver(
            bundle=ConnectionSecretBundle(token=token),
            auth_scheme="bearer",
            method="GET",
            url=f"https://public.example:{port}/x",
        )

    exc: BaseException | None = raised.value
    seen: set[int] = set()
    pieces: list[str] = []
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        pieces.append(str(exc))
        pieces.append(repr(exc))
        exc = exc.__context__ or exc.__cause__
    assert all(token not in piece for piece in pieces)
    assert raised.value.__context__ is None


def test_declassify_scans_every_bundle_member_not_just_one(stub_server):
    bot_token = "xoxb-bot-token"
    app_token = "xapp-app-level-token"
    # The response echoes the APP token, which was NOT the header sent — the
    # whole-bundle scan still catches it (design.md D4).
    stub_server.stub.update(status=200, body=f"leak {app_token}".encode())
    driver, _calls, _context, port = _local_driver(stub_server)

    with pytest.raises(ProxyRequestError, match="unsafe destination response"):
        driver(
            bundle=ConnectionSecretBundle(bot_token=bot_token, app_token=app_token),
            auth_scheme="none",
            method="GET",
            url=f"https://public.example:{port}/x",
        )


# --------------------------------------------------------------------------- #
# The secure defaults
# --------------------------------------------------------------------------- #
def test_default_ssl_context_verifies_certificate_and_hostname():
    context = _default_ssl_context()
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_parse_accepts_a_normal_canonical_url():
    parsed = _parse_canonical_https_url(
        "https://api.example.com/v2/tweets?x=1",
        allowed_ports=frozenset({443}),
    )
    assert parsed.hostname == "api.example.com"
    assert parsed.port == 443
    assert parsed.path_qs == "/v2/tweets?x=1"
    assert parsed.is_ip_literal is False


def test_parse_allows_encoded_space_but_not_encoded_dot_or_slash():
    # A legitimate %20 path must still parse (Codex acceptance criterion for the
    # encoded-dot-segment fix — reject %2e/%2f only, not all percent-encoding).
    parsed = _parse_canonical_https_url(
        "https://api.example.com/a%20b/c",
        allowed_ports=frozenset({443}),
    )
    assert parsed.path_qs == "/a%20b/c"


# --------------------------------------------------------------------------- #
# FIX 1 — TLS key-logging credential leak (SSLKEYLOGFILE)
# --------------------------------------------------------------------------- #
def test_ssl_context_disables_keylog_even_with_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path / "tls.keys"))
    context = _default_ssl_context()
    assert context.keylog_filename is None


def test_child_environment_sanitization_drops_keylog_and_proxies(monkeypatch):
    monkeypatch.setenv("SSLKEYLOGFILE", "C:/temp/tls.keys")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
    _sanitize_child_environment()
    assert "SSLKEYLOGFILE" not in os.environ
    assert "HTTPS_PROXY" not in os.environ
    assert "HTTP_PROXY" not in os.environ
    assert "ALL_PROXY" not in os.environ


# --------------------------------------------------------------------------- #
# FIX 2 — total wall-clock deadline (slowloris / drip-feed)
# --------------------------------------------------------------------------- #
def test_slow_drip_body_aborts_at_the_total_deadline():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve():
        try:
            conn, _ = listener.accept()
            try:
                conn.recv(65535)
                # Claim a 100-byte body, then drip one byte at a time forever.
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n")
                while not stop.is_set():
                    try:
                        conn.sendall(b"x")
                    except OSError:
                        break
                    time.sleep(0.05)
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
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
        timeout=0.2,
        max_total_seconds=0.4,
    )
    started = time.monotonic()
    try:
        with pytest.raises(SsrfValidationError, match="total deadline"):
            driver(
                bundle=ConnectionSecretBundle(token="drip-token-not-in-response"),
                auth_scheme="bearer",
                method="GET",
                url=f"https://public.example:{port}/x",
            )
        elapsed = time.monotonic() - started
        assert elapsed < 3.0  # aborted at the deadline, did not hang
    finally:
        stop.set()


def _serve_drip(first_chunk: bytes):
    """Listener that sends ``first_chunk`` then drips 1 byte / 50 ms forever.

    Reproduces a slow-drip in whichever http.client parse phase ``first_chunk``
    leaves unterminated. Returns ``(port, stop_event)``.
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve():
        try:
            conn, _ = listener.accept()
            try:
                conn.recv(65535)
                conn.sendall(first_chunk)
                while not stop.is_set():
                    try:
                        conn.sendall(b"x")
                    except OSError:
                        break
                    time.sleep(0.05)
            finally:
                conn.close()
        except OSError:
            pass
        finally:
            listener.close()

    threading.Thread(target=serve, daemon=True).start()
    return port, stop


def _drip_driver(port):
    def open_socket(_address, timeout, _source_address):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    return _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
        timeout=0.2,
        max_total_seconds=0.4,
    )


def test_header_drip_aborts_at_the_total_deadline():
    # An UNTERMINATED header (Codex-found): status line + a header name, then a
    # byte-drip that never sends the CRLFCRLF. http.client parses headers via
    # makefile -> recv_into, so the socket-layer _DeadlineSocket must abort this
    # phase too — not only the body loop.
    port, stop = _serve_drip(b"HTTP/1.1 200 OK\r\nX-Drip: ")
    started = time.monotonic()
    try:
        with pytest.raises(SsrfValidationError, match="total deadline"):
            _drip_driver(port)(
                bundle=ConnectionSecretBundle(token="drip-token-not-in-response"),
                auth_scheme="bearer",
                method="GET",
                url=f"https://public.example:{port}/x",
            )
        assert time.monotonic() - started < 3.0  # aborted at the deadline, not hung
    finally:
        stop.set()


def test_chunked_trailer_drip_aborts_at_the_total_deadline():
    # A complete body but an UNTERMINATED chunked trailer (Codex-found: pre-fix
    # this returned a late SUCCESS). The trailer parse must also honor the deadline
    # and the request must FAIL closed — never a hang, never a false success.
    port, stop = _serve_drip(
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\n0\r\nX-Drip: "
    )
    started = time.monotonic()
    try:
        with pytest.raises(SsrfValidationError, match="total deadline"):
            _drip_driver(port)(
                bundle=ConnectionSecretBundle(token="drip-token-not-in-response"),
                auth_scheme="bearer",
                method="GET",
                url=f"https://public.example:{port}/x",
            )
        assert time.monotonic() - started < 3.0
    finally:
        stop.set()


def test_slow_connect_aborts_at_the_total_deadline():
    # A slow TCP connect happens BEFORE _DeadlineSocket is installed; it must still
    # be bounded by the total deadline (Codex-found: 29s connect + 5s TLS beats a
    # 30s deadline). The post-connect deadline check in connect() closes this.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def slow_open_socket(_address, _timeout, _source_address):
        time.sleep(0.5)  # a slow connect, longer than the 0.3s total deadline
        return socket.create_connection(("127.0.0.1", port), timeout=1.0)

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=slow_open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
        timeout=1.0,
        max_total_seconds=0.3,
    )
    try:
        with pytest.raises(SsrfValidationError, match="total deadline"):
            driver(
                bundle=ConnectionSecretBundle(token="tok-not-in-response"),
                auth_scheme="bearer",
                method="GET",
                url=f"https://public.example:{port}/x",
            )
    finally:
        listener.close()


def test_fast_response_succeeds_within_a_short_deadline(stub_server):
    stub_server.stub.update(status=200, body=b'{"ok": true}')
    driver, _calls, _context, port = _local_driver(stub_server, max_total_seconds=0.5)
    result = driver(
        bundle=ConnectionSecretBundle(token="fast-token-not-in-response"),
        auth_scheme="bearer",
        method="GET",
        url=f"https://public.example:{port}/x",
    )
    assert result["status"] == 200
    assert result["body"] == '{"ok": true}'
