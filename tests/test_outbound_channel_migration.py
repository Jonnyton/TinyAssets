"""Differential parity: the general-primitive path vs each channel's ORACLE.

Channel-agnostic-outbound tracks 2 + 5. Per design.md D6, a migration is proven by
a SEMANTIC EQUIVALENCE MATRIX, not byte parity of the whole HTTP frame — but the
load-bearing column is the NORMALIZED WIRE REQUEST: endpoint, method, body, and
non-auth headers identical; auth material normalized (OAuth nonce/timestamp) but
structurally equivalent. These tests keep each original effector VERBATIM as the
oracle and assert the general-primitive path produces the same normalized request.
"""

from __future__ import annotations

import base64
import http.server
import json
import socket
import ssl
import threading

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
# A loopback stub that records the request both paths send.
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
# SLACK (track 2) — bearer token, spaced JSON body.
# --------------------------------------------------------------------------- #
def test_slack_migrated_wire_request_matches_the_oracle(stub, tmp_path):
    from tinyassets.app_reply_authority import ReplyDestination
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.effectors.slack_transport import build_slack_transport

    port = stub.server_address[1]
    token = "xoxb-test-bot-token"
    universe = tmp_path / "universe-1"
    write_credential_vault(
        universe,
        [{
            "credential_type": "social",
            "service": "slack",
            "destination": "slack-conn-1",
            "bot_token": token,
        }],
    )

    # ORACLE: the verbatim slack_transport effector, pointed at the stub.
    oracle_transport = build_slack_transport(
        universe, url=f"http://127.0.0.1:{port}/api/chat.postMessage"
    )
    oracle_transport(
        ReplyDestination(provider="slack", connection_id="slack-conn-1", address="C123"),
        "hello world",
        thread_ts="1700000000.000001",
    )
    oracle = stub.recorded[-1]

    # GENERAL PRIMITIVE: the same message as an http-connection request.
    migrated = _run_through_general_driver(
        stub,
        host="slack.com",
        request=slack_http_request(
            channel="C123", text="hello world", thread_ts="1700000000.000001"
        ),
        bundle=ConnectionSecretBundle(token=token),
        auth_scheme="bearer",
    )

    assert migrated["method"] == oracle["method"] == "POST"
    assert migrated["path"] == oracle["path"] == "/api/chat.postMessage"
    assert migrated["body"] == oracle["body"]  # byte-identical spaced JSON
    assert migrated["headers"]["content-type"] == oracle["headers"]["content-type"]
    # Bearer auth is deterministic: byte-identical Authorization.
    assert migrated["headers"]["authorization"] == oracle["headers"]["authorization"]
    assert migrated["headers"]["authorization"] == f"Bearer {token}"


# --------------------------------------------------------------------------- #
# TWITTER (track 5) — OAuth 1.0a signature + compact JSON body.
# --------------------------------------------------------------------------- #
def _pin_oauth(monkeypatch):
    # Pin nonce + timestamp in BOTH modules so the OAuth signatures are directly
    # byte-comparable (normalizing exactly the two fields D6 allows to vary).
    import secrets as _secrets
    import time as _time

    monkeypatch.setattr(_secrets, "token_urlsafe", lambda _n=24: "PINNED-NONCE-VALUE")
    monkeypatch.setattr(_time, "time", lambda: 1_700_000_000.0)


def test_twitter_oauth1a_signature_is_byte_identical_to_the_oracle(monkeypatch):
    # The primitive's oauth1a handler is lifted verbatim from twitter_post; with a
    # pinned nonce/timestamp, the SAME url + method + credentials yield a
    # byte-identical Authorization (auth-material parity, design.md D6).
    from tinyassets.effectors import twitter_post

    _pin_oauth(monkeypatch)
    creds = twitter_post.TwitterCredentials(
        api_key="ck-consumer-key",
        api_secret="cs-consumer-secret",
        access_token="at-access-token",
        access_token_secret="ats-access-token-secret",
        source="test",
    )
    url = "https://api.x.com/2/tweets"
    oracle_header = twitter_post._oauth_header(method="POST", url=url, credentials=creds)
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
    assert migrated_header == oracle_header
    assert migrated_header.startswith("OAuth ")


def test_twitter_migrated_wire_request_matches_the_oracle(stub, monkeypatch):
    # Wire request (method/path/body/non-auth headers) parity vs the verbatim
    # twitter_post._post_tweet oracle, both pointed at the loopback stub.
    from tinyassets.effectors import twitter_post

    port = stub.server_address[1]
    monkeypatch.setattr(
        twitter_post, "_TWEETS_URL", f"http://127.0.0.1:{port}/2/tweets"
    )
    # Distinctive, non-colliding secret values (short tokens like "at" would
    # substring-match the stub's JSON and trip the response scrub — a test
    # artifact, not a real leak; real OAuth secrets are long random strings).
    creds = twitter_post.TwitterCredentials(
        api_key="consumer-key-9f3ac1",
        api_secret="consumer-secret-9f3ac1",
        access_token="access-token-9f3ac1",
        access_token_secret="access-token-secret-9f3ac1",
        source="test",
    )
    twitter_post._post_tweet(
        text="hello x", reply_to_tweet_id="", quote_tweet_id="", credentials=creds
    )
    oracle = stub.recorded[-1]

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

    assert migrated["method"] == oracle["method"] == "POST"
    assert migrated["path"] == oracle["path"] == "/2/tweets"
    assert migrated["body"] == oracle["body"]  # byte-identical compact JSON
    for header in ("accept", "content-type", "user-agent"):
        assert migrated["headers"][header] == oracle["headers"][header]
    # Both carry an OAuth 1.0a Authorization (nonce/timestamp differ live; the
    # byte-identical signer is proven in the dedicated auth-parity test above).
    assert migrated["headers"]["authorization"].startswith("OAuth ")
    assert oracle["headers"]["authorization"].startswith("OAuth ")


# --------------------------------------------------------------------------- #
# GITHUB (track 3) — multi-call PR transaction, bearer token, spaced JSON body.
#
# The oracle is github_pr's OWN request construction, driven end-to-end against
# a stateful loopback GitHub so no expected request is ever hand-written:
#   * _materialize_branch        -> base-ref read, base-commit read, blob, tree,
#                                   commit, ref (the git-data write sequence).
#   * _invoke_github_api_pr_create -> PR create + labels.
#   * _fetch_file_at_ref         -> contents read.
# Each recorded wire request is compared to the corresponding builder driven
# through the REAL _SsrfHardenedHttpDriver with the REAL GITHUB_ALLOWED_ENDPOINTS.
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
    force a 4xx on a chosen step so the flag-ON/OFF error-shape mapping is proven.
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
            # A FIXED error body so flag-ON (driver replace-decode) and flag-OFF
            # (exc.read() replace-decode) yield byte-identical detail strings.
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


def test_github_git_data_sequence_matches_the_oracle(github_stub, monkeypatch):
    # Drive github_pr's REAL materialize sequence against the stub, then compare
    # every recorded wire request to the matching builder.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    monkeypatch.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")

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


def test_github_pr_create_and_labels_match_the_oracle(github_stub, monkeypatch):
    # github_pr's REAL PR-create builder; the stub returns html_url+number so the
    # labels call fires too.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    monkeypatch.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")

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


def test_github_contents_read_matches_the_oracle(github_stub, monkeypatch):
    # github_pr's REAL contents-read builder (_fetch_file_at_ref computes the
    # quoting + path, then calls _git_data_api). The GET is recorded before the
    # response is validated, so a plain stub response suffices.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    monkeypatch.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")

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
    # hello-world/* — every attempt at another repo is refused (Codex finding 2:
    # the slice-1 [\w.-]+ placeholders permitted ANY repo; that hole is closed).
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
    # The {path+}/{ref+} rest tails ALLOW real multi-segment inputs but resist
    # every traversal / encoded-separator / host-escape (slice 2A contract).
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


# --------------------------------------------------------------------------- #
# GITHUB slice 2B — flag-ON vs flag-OFF END-TO-END differential parity.
#
# Drive github_pr's OWN dispatch (the SAME operation) twice against the SAME
# stateful loopback: once flag-OFF (legacy raw urllib) and once flag-ON (through
# the REAL _SsrfHardenedHttpDriver + REAL github_allowed_endpoints). Assert BOTH
# the recorded wire requests AND the parsed results / error shapes are identical
# — that is the proof the DARK wiring is transparent.
# --------------------------------------------------------------------------- #
def _install_loopback_driver(monkeypatch, port):
    """Point the flag-ON path's driver at the loopback stub.

    ``github_send_via_connection`` builds ``_SsrfHardenedHttpDriver()`` with
    production defaults (real DNS/TLS). Replace that constructor in BOTH modules
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


def _run_materialize_capturing(github_stub, monkeypatch, *, flag_on):
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]
    github_stub.recorded.clear()
    with monkeypatch.context() as m:
        m.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")
        if flag_on:
            m.setenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", "1")
            _install_loopback_driver(m, port)
        else:
            m.delenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", raising=False)
        result = github_pr._materialize_branch(
            changes_json={_GH_CHANGE_PATH: _GH_CHANGE_CONTENT},
            destination=_GH_OWNER_REPO,
            base_branch=_GH_BASE_BRANCH,
            head_branch=_GH_HEAD_BRANCH,
            commit_message=_GH_COMMIT_MESSAGE,
            capability_token=_GH_TOKEN,
            publish_ref=True,
        )
    return result, list(github_stub.recorded)


def test_github_materialize_flag_on_off_wire_and_result_identical(github_stub, monkeypatch):
    off_result, off_reqs = _run_materialize_capturing(
        github_stub, monkeypatch, flag_on=False
    )
    on_result, on_reqs = _run_materialize_capturing(
        github_stub, monkeypatch, flag_on=True
    )
    assert off_result.get("materialized") is True, off_result
    # Same operation ⇒ same parsed result.
    assert on_result == off_result
    # Same wire requests, request-for-request (method/path/body/non-auth headers +
    # Bearer). Host/Accept-Encoding artifacts of the loopback are excluded by
    # _assert_github_wire_identical, which compares only the github header set.
    assert len(on_reqs) == len(off_reqs) == 6
    for on_req, off_req in zip(on_reqs, off_reqs):
        _assert_github_wire_identical(on_req, off_req)


def test_github_pr_create_flag_on_off_identical(github_stub, monkeypatch):
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]

    def run(flag_on):
        github_stub.recorded.clear()
        with monkeypatch.context() as m:
            m.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")
            if flag_on:
                m.setenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", "1")
                _install_loopback_driver(m, port)
            else:
                m.delenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", raising=False)
            result = github_pr._invoke_github_api_pr_create(
                payload={
                    "title": "Add a thing",
                    "body": "PR body <!-- marker -->",
                    "base_branch": _GH_BASE_BRANCH,
                    "head_branch": _GH_HEAD_BRANCH,
                    "labels": ["cloud", "automation"],
                    "draft": True,
                },
                destination=_GH_OWNER_REPO,
                capability_token=_GH_TOKEN,
            )
        return result, list(github_stub.recorded)

    off_result, off_reqs = run(False)
    on_result, on_reqs = run(True)
    assert on_result == off_result
    assert on_result.get("pr_number") == 1
    assert len(on_reqs) == len(off_reqs) == 2  # PR create + labels
    for on_req, off_req in zip(on_reqs, off_reqs):
        _assert_github_wire_identical(on_req, off_req)


def test_github_contents_read_flag_on_off_identical_subdir(github_stub, monkeypatch):
    # Contents read of a SUBDIRECTORY file — flag-ON routes it through the {path+}
    # rest tail (slice 2A), where slice-1 REFUSED it. Wire + result must match.
    from tinyassets.effectors import github_pr

    port = github_stub.server_address[1]

    def run(flag_on):
        github_stub.recorded.clear()
        with monkeypatch.context() as m:
            m.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")
            if flag_on:
                m.setenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", "1")
                _install_loopback_driver(m, port)
            else:
                m.delenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", raising=False)
            contents, err = github_pr._fetch_file_at_ref(
                owner_repo=_GH_OWNER_REPO,
                path="src/pkg/module.py",
                ref=_GH_BASE_BRANCH,
                capability_token=_GH_TOKEN,
            )
        return (contents, err), list(github_stub.recorded)

    off_result, off_reqs = run(False)
    on_result, on_reqs = run(True)
    assert on_result == off_result
    assert on_result[1] is None and on_result[0] == "file body\n"
    assert len(on_reqs) == len(off_reqs) == 1
    assert on_reqs[0]["path"] == "/repos/octocat/hello-world/contents/src/pkg/module.py?ref=main"
    _assert_github_wire_identical(on_reqs[0], off_reqs[0])


def test_github_error_shape_flag_on_off_identical(github_stub_status, monkeypatch):
    # A 403 on the base-ref lookup must yield the SAME error dict flag-ON and
    # flag-OFF — proving the driver's status/body maps back to _git_data_api's
    # (parsed, error) shape and preserves BUG-111's 401/403/404 scope upgrade.
    from tinyassets.effectors import github_pr

    github_stub_status.status_for = lambda method, path: (  # type: ignore[attr-defined]
        403 if "/git/ref/heads/" in path else 200
    )
    port = github_stub_status.server_address[1]

    def run(flag_on):
        github_stub_status.recorded.clear()
        with monkeypatch.context() as m:
            m.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")
            if flag_on:
                m.setenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", "1")
                _install_loopback_driver(m, port)
            else:
                m.delenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", raising=False)
            return github_pr._materialize_branch(
                changes_json={_GH_CHANGE_PATH: _GH_CHANGE_CONTENT},
                destination=_GH_OWNER_REPO,
                base_branch=_GH_BASE_BRANCH,
                head_branch=_GH_HEAD_BRANCH,
                commit_message=_GH_COMMIT_MESSAGE,
                capability_token=_GH_TOKEN,
                publish_ref=True,
            )

    off = run(False)
    on = run(True)
    assert off["error_kind"] == on["error_kind"] == "github_contents_write_denied"
    assert on == off


def test_github_pr_create_error_shape_flag_on_off_identical(github_stub_status, monkeypatch):
    # A 422 on the PR-create POST exercises _github_api_request's SYNTHESIZED
    # urllib.error.HTTPError on the flag-ON path (the driver returns status/body;
    # the caller expects to catch HTTPError + read exc.code/exc.read()). Flag-ON
    # and flag-OFF must map to the identical github_api_error result.
    from tinyassets.effectors import github_pr

    github_stub_status.status_for = lambda method, path: (  # type: ignore[attr-defined]
        422 if path.endswith("/pulls") else 200
    )
    port = github_stub_status.server_address[1]

    def run(flag_on):
        github_stub_status.recorded.clear()
        with monkeypatch.context() as m:
            m.setattr(github_pr, "_GITHUB_API", f"http://127.0.0.1:{port}")
            if flag_on:
                m.setenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", "1")
                _install_loopback_driver(m, port)
            else:
                m.delenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", raising=False)
            return github_pr._invoke_github_api_pr_create(
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

    off = run(False)
    on = run(True)
    assert off["error_kind"] == on["error_kind"] == "github_api_error"
    assert "422" in off["error"] and "422" in on["error"]
    assert on == off


def test_github_pr_create_refusal_marked_ambiguous_flag_on(github_stub, monkeypatch):
    # A driver refusal (SsrfValidationError/ProxyRequestError) on the flag-ON path
    # maps to urllib.error.URLError so _invoke_github_api_pr_create marks the
    # outcome ambiguous — the same branch a real network loss takes flag-OFF.
    from tinyassets.effectors import github_pr

    with monkeypatch.context() as m:
        m.setenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", "1")

        def factory():
            def _boom(**_kwargs):
                raise outbound_connections.ProxyRequestError("destination unreachable")
            return _boom

        m.setattr(outbound_channel_adapter, "_SsrfHardenedHttpDriver", factory)
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


def test_github_read_for_commit_flag_on_routes_through_driver(github_stub, monkeypatch):
    # The broker's OWN read_for_commit path (outbound_connections.py:978): flag-ON
    # routes through the SSRF driver + destination-bound allowlist and returns the
    # parsed PR list, sending the broker's exact wire request (broker User-Agent,
    # NO Content-Type — the flag-OFF legacy urllib path builds the same shape but
    # is left untouched and cannot be pointed at a loopback without a global
    # urlopen patch, so this asserts the flag-ON wiring is correct + faithful).
    port = github_stub.server_address[1]
    driver = outbound_connections._ProductionGitHubNetworkDriver()
    with monkeypatch.context() as m:
        m.setenv("TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION", "1")
        _install_loopback_driver(m, port)
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
