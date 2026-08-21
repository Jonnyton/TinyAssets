"""Wire-request spec for every channel that routes through the ONE adapter.

Channel-agnostic-outbound (design.md D6). The legacy bespoke ``slack_transport`` and
``twitter_post`` modules are GONE and there is no feature flag / legacy fallback, so
these tests are no longer flag-ON/OFF differentials against a live oracle. They pin
the SURVIVING invariant — the NORMALIZED WIRE REQUEST each channel puts on the wire
through the real ``_SsrfHardenedHttpDriver`` — as the connection path's spec, asserted
UNCONDITIONALLY: endpoint, method, body, and non-auth headers exact; auth material
structurally equivalent (deterministic Bearer, or OAuth 1.0a modulo nonce/timestamp).

For OAuth 1.0a the algorithm's executable oracle is kept VERBATIM in this file (the
signer was lifted verbatim from the deleted ``twitter_post._oauth_header``), so the
in-child signer is still differential-tested against a byte-identical reference.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.server
import json
import socket
import ssl
import threading
import urllib.parse

import pytest

from tinyassets.effectors import outbound_channel_adapter
from tinyassets.effectors.outbound_channel_adapter import (
    GITHUB_API_BASE,
    github_add_labels_request,
    github_allowed_endpoints,
    github_contents_read_request,
    github_git_blob_request,
    github_git_commit_read_request,
    github_git_commit_request,
    github_git_ref_create_request,
    github_git_ref_read_request,
    github_git_tree_request,
    github_pull_request_create_request,
    slack_http_request,
    twitter_http_request,
)
from tinyassets.storage import outbound_connections
from tinyassets.storage.outbound_connections import (
    ConnectionSecretBundle,
    OutboundEndpoint,
    SsrfValidationError,
    _enforce_endpoint_allowlist,
    _oauth1a_authorization,
    _parse_canonical_https_url,
    _SsrfHardenedHttpDriver,
)


# --------------------------------------------------------------------------- #
# A loopback stub that records the request the connection path sends.
# --------------------------------------------------------------------------- #
class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.recorded.append(  # type: ignore[attr-defined]
            {
                "method": self.command,
                "path": self.path,
                "body": body,
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }
        )
        payload = self.server.response_body  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def stub():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.recorded = []  # type: ignore[attr-defined]
    server.response_body = (  # type: ignore[attr-defined]
        b'{"ok": true, "ts": "1700000000.000100", "channel": "C123", "data": {"id": "1"}}'
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


class _PassThroughTLS:
    def __init__(self):
        self.verify_mode = ssl.CERT_NONE
        self.check_hostname = False

    def wrap_socket(self, sock, server_hostname=None):  # noqa: ANN001
        return sock


def _run_through_general_driver(stub, *, host, request, bundle, auth_scheme):
    """Send ``request`` through the REAL SSRF-hardened driver to the loopback stub."""
    port = stub.server_address[1]

    def open_socket(_address, timeout, _src):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
    )
    path = request["url"].split(host, 1)[1]  # the path after the host
    driver(
        bundle=bundle,
        auth_scheme=auth_scheme,
        method="POST",
        url=f"https://{host}:{port}{path}",
        headers=request["headers"],
        body=request["body"],
        allowed_endpoints=(OutboundEndpoint(host, path, ("POST",)),),
    )
    return stub.recorded[-1]


# --------------------------------------------------------------------------- #
# SLACK — bearer token, spaced JSON body. Asserted unconditionally (no oracle).
# --------------------------------------------------------------------------- #
def test_slack_connection_path_wire_request(stub):
    token = "xoxb-test-bot-token"
    migrated = _run_through_general_driver(
        stub,
        host="slack.com",
        request=slack_http_request(
            channel="C123", text="hello world", thread_ts="1700000000.000001"
        ),
        bundle=ConnectionSecretBundle(token=token),
        auth_scheme="bearer",
    )

    assert migrated["method"] == "POST"
    assert migrated["path"] == "/api/chat.postMessage"
    # Slack's spaced json.dumps default separators — reproduced by the builder.
    expected_body = json.dumps(
        {"channel": "C123", "text": "hello world", "thread_ts": "1700000000.000001"}
    ).encode("utf-8")
    assert migrated["body"] == expected_body
    assert migrated["headers"]["content-type"] == "application/json; charset=utf-8"
    # Bearer auth is deterministic: byte-identical Authorization, driver-applied.
    assert migrated["headers"]["authorization"] == f"Bearer {token}"


# --------------------------------------------------------------------------- #
# TWITTER — OAuth 1.0a signature + compact JSON body.
# --------------------------------------------------------------------------- #
def _percent(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~-._")


def _reference_oauth1a(*, method, url, api_key, api_secret, access_token, access_token_secret):
    """VERBATIM OAuth 1.0a oracle (was ``twitter_post._oauth_header``).

    Kept in the test suite as the executable spec the in-child signer
    (``_oauth1a_authorization``) is differential-tested against — the deleted
    effector can no longer serve as the live oracle, so its algorithm lives here.
    """
    import secrets as _secrets
    import time as _time

    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": _secrets.token_urlsafe(24),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(_time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }
    parsed = urllib.parse.urlparse(url)
    base_url = urllib.parse.urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
    )
    query_params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    signature_params = {**query_params, **oauth_params}
    encoded_pairs = [
        f"{_percent(key)}={_percent(value)}"
        for key, value in sorted(signature_params.items())
    ]
    normalized = "&".join(encoded_pairs)
    base_string = "&".join([method.upper(), _percent(base_url), _percent(normalized)])
    signing_key = f"{_percent(api_secret)}&{_percent(access_token_secret)}"
    digest = hmac.new(
        signing_key.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha1
    ).digest()
    oauth_params["oauth_signature"] = base64.b64encode(digest).decode("ascii")
    rendered = ", ".join(
        f'{_percent(key)}="{_percent(value)}"'
        for key, value in sorted(oauth_params.items())
    )
    return f"OAuth {rendered}"


def _pin_oauth(monkeypatch):
    # Pin nonce + timestamp so the signatures are directly byte-comparable
    # (normalizing exactly the two fields D6 allows to vary).
    import secrets as _secrets
    import time as _time

    monkeypatch.setattr(_secrets, "token_urlsafe", lambda _n=24: "PINNED-NONCE-VALUE")
    monkeypatch.setattr(_time, "time", lambda: 1_700_000_000.0)


def test_twitter_oauth1a_signature_matches_the_verbatim_reference(monkeypatch):
    # With a pinned nonce/timestamp, the in-child signer yields a byte-identical
    # Authorization to the verbatim reference algorithm (auth-material parity, D6).
    _pin_oauth(monkeypatch)
    url = "https://api.x.com/2/tweets"
    reference_header = _reference_oauth1a(
        method="POST",
        url=url,
        api_key="ck-consumer-key",
        api_secret="cs-consumer-secret",
        access_token="at-access-token",
        access_token_secret="ats-access-token-secret",
    )
    migrated_header = _oauth1a_authorization(
        ConnectionSecretBundle(
            api_key="ck-consumer-key",
            api_secret="cs-consumer-secret",
            access_token="at-access-token",
            access_token_secret="ats-access-token-secret",
        ),
        method="POST",
        url=url,
    )
    assert migrated_header == reference_header
    assert migrated_header.startswith("OAuth ")
    assert 'oauth_nonce="PINNED-NONCE-VALUE"' in migrated_header
    assert 'oauth_timestamp="1700000000"' in migrated_header


def test_twitter_connection_path_wire_request(stub):
    # Distinctive, non-colliding secret values (short tokens like "at" would
    # substring-match the stub's JSON and trip the response scrub — a test artifact,
    # not a real leak; real OAuth secrets are long random strings).
    oauth_bundle = ConnectionSecretBundle(
        api_key="consumer-key-9f3ac1",
        api_secret="consumer-secret-9f3ac1",
        access_token="access-token-9f3ac1",
        access_token_secret="access-token-secret-9f3ac1",
    )
    migrated = _run_through_general_driver(
        stub,
        host="api.x.com",
        request=twitter_http_request(text="hello x"),
        bundle=oauth_bundle,
        auth_scheme="oauth1a",
    )

    assert migrated["method"] == "POST"
    assert migrated["path"] == "/2/tweets"
    # Compact JSON body, reproduced by the builder.
    assert migrated["body"] == json.dumps({"text": "hello x"}, separators=(",", ":")).encode()
    assert migrated["headers"]["accept"] == "application/json"
    assert migrated["headers"]["content-type"] == "application/json"
    assert migrated["headers"]["user-agent"] == "tinyassets-twitter-post-effector/1.0"
    # OAuth 1.0a Authorization signed in the driver (nonce/timestamp differ live;
    # byte-identical signer is proven in the dedicated auth-parity test above).
    assert migrated["headers"]["authorization"].startswith("OAuth ")


# --------------------------------------------------------------------------- #
# GITHUB — multi-call PR transaction, bearer token, spaced JSON body.
#
# github_pr routes _github_api_request / _git_data_api through the ONE SSRF-hardened
# driver UNCONDITIONALLY (no flag). These tests drive github_pr's REAL request
# construction end-to-end against a stateful loopback GitHub (the driver is pointed
# at the loopback socket via injected seams) and compare every recorded wire request
# to the corresponding standalone builder driven through the SAME real driver + the
# REAL GITHUB_ALLOWED_ENDPOINTS.
# --------------------------------------------------------------------------- #
_GH_TOKEN = "ghs_testcapabilitytoken_notinresponses"
_GH_OWNER_REPO = "octocat/hello-world"
_GH_BASE_BRANCH = "main"
_GH_HEAD_BRANCH = "tinyassets/cloud-branch"
_GH_COMMIT_MESSAGE = "test commit message"
_GH_CHANGE_PATH = "docs/x.md"  # non-tinyassets/ path -> no plugin-mirror blob
_GH_CHANGE_CONTENT = "hello\n"
# Fixed shas the stub vends at each step; distinct so a mismatch is unambiguous.
_GH_BASE_COMMIT_SHA = "a" * 40
_GH_BASE_TREE_SHA = "b" * 40
_GH_BLOB_SHA = "c" * 40
_GH_NEW_TREE_SHA = "d" * 40
_GH_NEW_COMMIT_SHA = "e" * 40


def _github_route(method: str, path: str) -> object:
    """Return the JSON github_pr expects at each PR-flow step (stateful stub)."""
    concrete = path.split("?", 1)[0]
    if method == "GET" and concrete.endswith("/pulls"):
        # read_for_commit (GET /repos/o/r/commits/{sha}/pulls) expects a LIST.
        return [{"number": 7, "html_url": "https://github.example/o/r/pull/7"}]
    if method == "GET" and "/git/ref/heads/" in concrete:
        return {"object": {"sha": _GH_BASE_COMMIT_SHA}}
    if method == "GET" and "/git/commits/" in concrete:
        return {"tree": {"sha": _GH_BASE_TREE_SHA}}
    if method == "GET" and "/contents/" in concrete:
        return {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(b"file body\n").decode("ascii"),
        }
    if method == "POST" and concrete.endswith("/git/blobs"):
        return {"sha": _GH_BLOB_SHA}
    if method == "POST" and concrete.endswith("/git/trees"):
        return {"sha": _GH_NEW_TREE_SHA}
    if method == "POST" and concrete.endswith("/git/commits"):
        return {"sha": _GH_NEW_COMMIT_SHA}
    if method == "POST" and concrete.endswith("/git/refs"):
        return {"ref": "refs/heads/x", "object": {"sha": _GH_NEW_COMMIT_SHA}}
    if method == "POST" and concrete.endswith("/pulls"):
        return {"html_url": "https://github.example/o/r/pull/1", "number": 1}
    if method == "POST" and concrete.endswith("/labels"):
        return [{"name": "x"}]
    return {}


class _GitHubRecordingHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):
        return

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.recorded.append(  # type: ignore[attr-defined]
            {
                "method": self.command,
                "path": self.path,
                "body": body,
                "headers": {k.lower(): v for k, v in self.headers.items()},
            }
        )
        payload = json.dumps(_github_route(self.command, self.path)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        self._handle()

    def do_POST(self):  # noqa: N802
        self._handle()


@pytest.fixture
def github_stub():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _GitHubRecordingHandler)
    server.recorded = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


class _GitHubStatusHandler(http.server.BaseHTTPRequestHandler):
    """Like the recorder, but returns ``server.status_for(method, path)`` — used to
    force a 4xx on a chosen step so the error-shape mapping is proven.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):
        return

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.recorded.append(  # type: ignore[attr-defined]
            {"method": self.command, "path": self.path, "body": body,
             "headers": {k.lower(): v for k, v in self.headers.items()}}
        )
        status = self.server.status_for(self.command, self.path)  # type: ignore[attr-defined]
        if status >= 400:
            # A FIXED error body so the driver's replace-decode yields a stable detail.
            payload = b'{"message":"Resource not accessible by integration"}'
        else:
            payload = json.dumps(_github_route(self.command, self.path)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        self._handle()

    def do_POST(self):  # noqa: N802
        self._handle()


@pytest.fixture
def github_stub_status():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _GitHubStatusHandler)
    server.recorded = []  # type: ignore[attr-defined]
    server.status_for = lambda _m, _p: 200  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _install_loopback_driver(monkeypatch, port):
    """Point github_pr's UNCONDITIONAL driver at the loopback stub.

    ``github_send_via_connection`` / the broker read build ``_SsrfHardenedHttpDriver()``
    with production defaults (real DNS/TLS). Replace that constructor in BOTH modules
    with a factory that injects the test seams (loopback socket, pass-through TLS,
    port-443 allowlist), so the real driver + real allowlist run against the stub.
    """

    def open_socket(_address, timeout, _src):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    def factory():
        return _SsrfHardenedHttpDriver(
            resolver=lambda _h, _p: ["127.0.0.1"],
            validator=lambda addr: addr,
            open_socket=open_socket,
            ssl_context=_PassThroughTLS(),
            allowed_ports=frozenset({443}),
        )

    monkeypatch.setattr(outbound_channel_adapter, "_SsrfHardenedHttpDriver", factory)
    monkeypatch.setattr(outbound_connections, "_SsrfHardenedHttpDriver", factory)


def _run_github_through_driver(github_stub, request: dict) -> dict:
    """Send a builder request through the REAL SSRF driver + REAL allowlist."""
    port = github_stub.server_address[1]

    def open_socket(_address, timeout, _src):
        return socket.create_connection(("127.0.0.1", port), timeout=timeout)

    driver = _SsrfHardenedHttpDriver(
        resolver=lambda _h, _p: ["127.0.0.1"],
        validator=lambda addr: addr,
        open_socket=open_socket,
        ssl_context=_PassThroughTLS(),
        allowed_ports=frozenset({port}),
    )
    tail = request["url"].split("api.github.com", 1)[1]  # /path?query
    driver(
        bundle=ConnectionSecretBundle(token=_GH_TOKEN),
        auth_scheme="bearer",
        method=request["method"],
        url=f"https://api.github.com:{port}{tail}",
        headers=request["headers"],
        body=request["body"],
        allowed_endpoints=github_allowed_endpoints(_GH_OWNER_REPO),
    )
    return github_stub.recorded[-1]


def _assert_github_wire_identical(migrated: dict, oracle: dict) -> None:
    assert migrated["method"] == oracle["method"]
    assert migrated["path"] == oracle["path"]
    assert migrated["body"] == oracle["body"]  # byte-identical spaced JSON / empty
    for header in ("accept", "content-type", "user-agent", "x-github-api-version"):
        assert migrated["headers"][header] == oracle["headers"][header]
    # Bearer auth is deterministic: byte-identical Authorization, driver-applied.
    assert migrated["headers"]["authorization"] == oracle["headers"]["authorization"]
    assert migrated["headers"]["authorization"] == f"Bearer {_GH_TOKEN}"


def test_github_git_data_sequence_matches_the_builders(github_stub, monkeypatch):
    # Drive github_pr's REAL materialize sequence through the driver against the stub,
    # then compare every recorded wire request to the matching standalone builder.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    _install_loopback_driver(monkeypatch, port)

    result = github_pr._materialize_branch(
        changes_json={_GH_CHANGE_PATH: _GH_CHANGE_CONTENT},
        destination=_GH_OWNER_REPO,
        base_branch=_GH_BASE_BRANCH,
        head_branch=_GH_HEAD_BRANCH,
        commit_message=_GH_COMMIT_MESSAGE,
        capability_token=_GH_TOKEN,
        publish_ref=True,
    )
    # The happy path completed => exactly the six git-data calls fired, in order.
    assert result.get("materialized") is True, result
    recorded = github_stub.recorded
    assert len(recorded) == 6, [r["method"] + " " + r["path"] for r in recorded]

    (ref_read, commit_read, blob, tree, commit, ref_create) = recorded

    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_git_ref_read_request(owner_repo=_GH_OWNER_REPO, branch=_GH_BASE_BRANCH),
        ),
        ref_read,
    )
    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_git_commit_read_request(
                owner_repo=_GH_OWNER_REPO, sha=_GH_BASE_COMMIT_SHA
            ),
        ),
        commit_read,
    )
    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_git_blob_request(
                owner_repo=_GH_OWNER_REPO, content=_GH_CHANGE_CONTENT
            ),
        ),
        blob,
    )
    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_git_tree_request(
                owner_repo=_GH_OWNER_REPO,
                base_tree=_GH_BASE_TREE_SHA,
                # github_pr's tree-entry key order (github_pr.py:1482).
                tree=[
                    {
                        "path": _GH_CHANGE_PATH,
                        "mode": "100644",
                        "type": "blob",
                        "sha": _GH_BLOB_SHA,
                    }
                ],
            ),
        ),
        tree,
    )
    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_git_commit_request(
                owner_repo=_GH_OWNER_REPO,
                message=_GH_COMMIT_MESSAGE,
                tree=_GH_NEW_TREE_SHA,
                parents=[_GH_BASE_COMMIT_SHA],
            ),
        ),
        commit,
    )
    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_git_ref_create_request(
                owner_repo=_GH_OWNER_REPO,
                ref=f"refs/heads/{_GH_HEAD_BRANCH}",
                sha=_GH_NEW_COMMIT_SHA,
            ),
        ),
        ref_create,
    )


def test_github_pr_create_and_labels_match_the_builders(github_stub, monkeypatch):
    # github_pr's REAL PR-create path; the stub returns html_url+number so the
    # labels call fires too.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    _install_loopback_driver(monkeypatch, port)

    labels = ["cloud", "automation"]
    github_pr._invoke_github_api_pr_create(
        payload={
            "title": "Add a thing",
            "body": "PR body <!-- marker -->",
            "base_branch": _GH_BASE_BRANCH,
            "head_branch": _GH_HEAD_BRANCH,
            "labels": labels,
            "draft": True,
        },
        destination=_GH_OWNER_REPO,
        capability_token=_GH_TOKEN,
    )
    assert len(github_stub.recorded) == 2, github_stub.recorded
    pulls_oracle, labels_oracle = github_stub.recorded

    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_pull_request_create_request(
                owner_repo=_GH_OWNER_REPO,
                title="Add a thing",
                body="PR body <!-- marker -->",
                base_branch=_GH_BASE_BRANCH,
                head_branch=_GH_HEAD_BRANCH,
                draft=True,
            ),
        ),
        pulls_oracle,
    )
    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_add_labels_request(
                owner_repo=_GH_OWNER_REPO, pr_number=1, labels=labels
            ),
        ),
        labels_oracle,
    )


def test_github_contents_read_matches_the_builder(github_stub, monkeypatch):
    # github_pr's REAL contents-read path (_fetch_file_at_ref computes the quoting +
    # path, then calls _git_data_api). The GET is recorded before the response is
    # validated, so a plain stub response suffices.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    _install_loopback_driver(monkeypatch, port)

    github_pr._fetch_file_at_ref(
        owner_repo=_GH_OWNER_REPO,
        path="README.md",
        ref=_GH_BASE_BRANCH,
        capability_token=_GH_TOKEN,
    )
    oracle = github_stub.recorded[-1]

    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_contents_read_request(
                owner_repo=_GH_OWNER_REPO, path="README.md", ref=_GH_BASE_BRANCH
            ),
        ),
        oracle,
    )


def test_github_contents_read_subdir_wire_and_result(github_stub, monkeypatch):
    # Contents read of a SUBDIRECTORY file routes through the {path+} rest tail
    # (slice 2A). Wire request + parsed result asserted unconditionally.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    _install_loopback_driver(monkeypatch, port)

    contents, err = github_pr._fetch_file_at_ref(
        owner_repo=_GH_OWNER_REPO,
        path="src/pkg/module.py",
        ref=_GH_BASE_BRANCH,
        capability_token=_GH_TOKEN,
    )
    assert err is None and contents == "file body\n"
    assert len(github_stub.recorded) == 1
    req = github_stub.recorded[0]
    assert req["path"] == "/repos/octocat/hello-world/contents/src/pkg/module.py?ref=main"
    _assert_github_wire_identical(
        _run_github_through_driver(
            github_stub,
            github_contents_read_request(
                owner_repo=_GH_OWNER_REPO, path="src/pkg/module.py", ref=_GH_BASE_BRANCH
            ),
        ),
        req,
    )


def test_github_read_for_commit_routes_through_driver(github_stub, monkeypatch):
    # The broker's OWN read_for_commit path (outbound_connections): it routes through
    # the SSRF driver + destination-bound allowlist UNCONDITIONALLY and returns the
    # parsed PR list, sending the broker's exact wire request (broker User-Agent, NO
    # Content-Type — read_for_commit sends no body).
    port = github_stub.server_address[1]
    driver = outbound_connections._ProductionGitHubNetworkDriver()
    _install_loopback_driver(monkeypatch, port)
    payload = driver(
        credential=_GH_TOKEN,
        provider="github",
        destination=_GH_OWNER_REPO,
        verb="pull_requests:read_for_commit",
        request={
            "repository": _GH_OWNER_REPO,
            "intended_head_sha": "a" * 40,
            "per_page": 30,
        },
    )
    assert isinstance(payload, list)
    assert len(github_stub.recorded) == 1
    req = github_stub.recorded[-1]
    assert req["method"] == "GET"
    assert req["path"].endswith(f"/commits/{'a' * 40}/pulls?per_page=30")
    assert req["path"].startswith(f"/repos/{_GH_OWNER_REPO}/commits/")
    assert req["headers"]["authorization"] == f"Bearer {_GH_TOKEN}"
    assert req["headers"]["user-agent"] == "tinyassets-outbound-broker/1.0"
    assert req["headers"]["accept"] == "application/vnd.github+json"
    # read_for_commit sends no body, so no Content-Type — the driver must not add one.
    assert "content-type" not in req["headers"]


def test_github_error_shape_preserves_bug111_scope_upgrade(github_stub_status, monkeypatch):
    # A 403 on the base-ref lookup maps back to _git_data_api's (parsed, error) shape
    # and preserves BUG-111's 401/403/404 scope upgrade (github_contents_write_denied).
    from tinyassets.effectors import github_pr

    github_stub_status.status_for = lambda method, path: (  # type: ignore[attr-defined]
        403 if "/git/ref/heads/" in path else 200
    )
    port = github_stub_status.server_address[1]
    _install_loopback_driver(monkeypatch, port)
    result = github_pr._materialize_branch(
        changes_json={_GH_CHANGE_PATH: _GH_CHANGE_CONTENT},
        destination=_GH_OWNER_REPO,
        base_branch=_GH_BASE_BRANCH,
        head_branch=_GH_HEAD_BRANCH,
        commit_message=_GH_COMMIT_MESSAGE,
        capability_token=_GH_TOKEN,
        publish_ref=True,
    )
    assert result["error_kind"] == "github_contents_write_denied"


def test_github_pr_create_http_error_shape(github_stub_status, monkeypatch):
    # A 422 on the PR-create POST exercises _github_api_request's SYNTHESIZED
    # urllib.error.HTTPError (the driver returns status/body; the caller catches
    # HTTPError + reads exc.code). It maps to a github_api_error result naming 422.
    from tinyassets.effectors import github_pr

    github_stub_status.status_for = lambda method, path: (  # type: ignore[attr-defined]
        422 if path.endswith("/pulls") else 200
    )
    port = github_stub_status.server_address[1]
    _install_loopback_driver(monkeypatch, port)
    result = github_pr._invoke_github_api_pr_create(
        payload={
            "title": "Add a thing",
            "body": "PR body",
            "base_branch": _GH_BASE_BRANCH,
            "head_branch": _GH_HEAD_BRANCH,
            "labels": [],
            "draft": True,
        },
        destination=_GH_OWNER_REPO,
        capability_token=_GH_TOKEN,
    )
    assert result["error_kind"] == "github_api_error"
    assert "422" in result["error"]


def test_github_pr_create_refusal_marked_ambiguous(monkeypatch):
    # A driver refusal (SsrfValidationError/ProxyRequestError) maps to
    # urllib.error.URLError so _invoke_github_api_pr_create marks the outcome
    # ambiguous — the same branch a real network loss takes.
    from tinyassets.effectors import github_pr

    def factory():
        def _boom(**_kwargs):
            raise outbound_connections.ProxyRequestError("destination unreachable")
        return _boom

    monkeypatch.setattr(outbound_channel_adapter, "_SsrfHardenedHttpDriver", factory)
    result = github_pr._invoke_github_api_pr_create(
        payload={
            "title": "Add a thing",
            "body": "PR body",
            "base_branch": _GH_BASE_BRANCH,
            "head_branch": _GH_HEAD_BRANCH,
            "labels": [],
            "draft": True,
        },
        destination=_GH_OWNER_REPO,
        capability_token=_GH_TOKEN,
    )
    assert result["error_kind"] == "github_api_error"
    assert result.get("outcome_ambiguous") is True


def test_github_allowlist_is_storage_valid_and_covers_the_pr_flow():
    # Built through the storage validator, so every entry is one create_connection
    # would accept; assert the full api.github.com PR-flow surface is present with
    # DESTINATION-BOUND literal owner/repo (Codex finding 2) + the SSRF-safe rest
    # tails for subdir contents and slash-bearing branch refs (slice 2A).
    eps = github_allowed_endpoints(_GH_OWNER_REPO)
    assert all(isinstance(ep, OutboundEndpoint) for ep in eps)
    assert all(ep.host == "api.github.com" for ep in eps)
    templates = {(ep.path_template, ep.methods) for ep in eps}
    base = f"/repos/{_GH_OWNER_REPO}"
    assert templates == {
        (f"{base}/pulls", ("POST",)),
        (f"{base}/issues/{{pr_number}}/labels", ("POST",)),
        (f"{base}/git/blobs", ("POST",)),
        (f"{base}/git/trees", ("POST",)),
        (f"{base}/git/commits", ("POST",)),
        (f"{base}/git/refs", ("POST",)),
        (f"{base}/git/ref/heads/{{ref+}}", ("GET",)),
        (f"{base}/git/commits/{{sha}}", ("GET",)),
        (f"{base}/contents/{{path+}}", ("GET",)),
        (f"{base}/commits/{{sha}}/pulls", ("GET",)),
    }
    # owner/repo are LITERALS — no {owner}/{repo} placeholder can expand to another
    # account. The two rest-tail endpoints declare their tightening pattern; the
    # contents endpoint requires exactly one validated ref.
    contents = next(e for e in eps if e.path_template.endswith("/contents/{path+}"))
    assert contents.required_query == ("ref",)
    assert dict(contents.query_patterns)["ref"]
    assert GITHUB_API_BASE == "https://api.github.com"


def test_github_allowlist_is_destination_bound_to_one_repo():
    # A token scoped to octocat/hello-world can ONLY egress to /repos/octocat/
    # hello-world/* — every attempt at another repo is refused (Codex finding 2).
    eps = github_allowed_endpoints(_GH_OWNER_REPO)

    def refused(method, url):
        try:
            canon = _parse_canonical_https_url(url, allowed_ports=frozenset({443}))
            _enforce_endpoint_allowlist(canon, method, eps)
            return False
        except SsrfValidationError:
            return True

    b = GITHUB_API_BASE
    assert not refused("POST", f"{b}/repos/{_GH_OWNER_REPO}/pulls")  # own repo OK
    assert refused("POST", f"{b}/repos/evil/repo/pulls")  # other repo REFUSED
    assert refused("POST", f"{b}/repos/octocat/other-repo/pulls")  # same owner, other repo
    assert refused("POST", f"{b}/repos/octocat/hello-world-evil/pulls")  # prefix trick


def test_github_allowlist_rest_tails_and_traversal_defenses():
    # The {path+}/{ref+} rest tails ALLOW real multi-segment inputs but resist every
    # traversal / encoded-separator / host-escape (slice 2A contract).
    eps = github_allowed_endpoints(_GH_OWNER_REPO)

    def allowed(method, url):
        try:
            canon = _parse_canonical_https_url(url, allowed_ports=frozenset({443}))
            _enforce_endpoint_allowlist(canon, method, eps)
            return True
        except SsrfValidationError:
            return False

    b = GITHUB_API_BASE
    base = f"{b}/repos/{_GH_OWNER_REPO}"
    sha = "a" * 40
    # ALLOWED: subdir contents, slash-bearing + plain branch refs, %20 space.
    assert allowed("GET", f"{base}/contents/src/pkg/module.py?ref=main")
    assert allowed("GET", f"{base}/contents/README.md?ref=main")
    assert allowed("GET", f"{base}/contents/my%20file.md?ref=main")
    assert allowed("GET", f"{base}/git/ref/heads/main")
    assert allowed("GET", f"{base}/git/ref/heads/tinyassets/cloud-{'a' * 24}")
    assert allowed("GET", f"{base}/git/ref/heads/feat/x")
    assert allowed("GET", f"{base}/commits/{sha}/pulls?per_page=30")
    # REFUSED: traversal (literal + every encoded separator), host escape, empty
    # tail, over-deep tail, undeclared / duplicate / missing-required query.
    assert not allowed("GET", f"{base}/contents/../etc/passwd?ref=main")
    assert not allowed("GET", f"{base}/contents/%2e%2e/secret?ref=main")
    assert not allowed("GET", f"{base}/contents/a%2fb?ref=main")
    assert not allowed("GET", f"{base}/contents/a%5cb?ref=main")
    assert not allowed("GET", f"{base}/contents/src/pkg/module.py")  # missing ref
    assert not allowed("GET", f"{base}/contents/x?ref=main&foo=bar")  # undeclared
    assert not allowed("GET", f"{base}/contents/x?ref=a&ref=b")  # duplicate ref
    assert not allowed("GET", f"{base}/git/ref/heads/")  # empty tail
    deep = "/".join(["seg"] * 41)  # > _SSRF_MAX_REST_SEGMENTS
    assert not allowed("GET", f"{base}/contents/{deep}?ref=main")
    assert not allowed("GET", f"{base}/commits/{sha}/pulls")  # missing per_page
    assert not allowed("GET", f"{base}/commits/{sha}/pulls?per_page=101")  # >100
    assert not allowed("PUT", f"{base}/contents/x?ref=main")  # wrong method


def test_github_allowlist_bounds_query_field_flood():
    # A duplicate-field flood is refused BEFORE building an unbounded parse list
    # (Codex: bound query parsing). > _SSRF_MAX_QUERY_FIELDS ref= fields.
    eps = github_allowed_endpoints(_GH_OWNER_REPO)
    flood = "&".join(["ref=main"] * 64)
    url = f"{GITHUB_API_BASE}/repos/{_GH_OWNER_REPO}/contents/x?{flood}"
    canon = _parse_canonical_https_url(url, allowed_ports=frozenset({443}))
    with pytest.raises(SsrfValidationError):
        _enforce_endpoint_allowlist(canon, "GET", eps)


def test_github_allowlist_refuses_non_ascii_repo():
    # The destination validator uses Unicode \w; the allowlist compares ASCII
    # literals. A non-ASCII owner/repo fails closed with a clear error (Codex).
    with pytest.raises(SsrfValidationError):
        github_allowed_endpoints("café/repo")
