"""The real transports, at the HTTP layer, with only the socket replaced.

These drive ``tinyassets.notify.fcm`` and ``tinyassets.notify.webpush``
themselves -- built by the real ``resolve_transports`` from real (throwaway)
keys -- and assert the bytes they would put on the wire. The stand-in is
``urlopen`` and nothing above it, because a harness stub is where proof leaks:
faking the transport function would have proved only that the test's own
function was called, not that a correctly shaped FCM request is ever built.

Keys are generated per test. Nothing here reads a credential from the
environment except the two documented variables, and no key is committed.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tinyassets.notify import (
    OUTCOME_SENT,
    Notification,
    TransportFailed,
    TransportGone,
    resolve_transports,
)

PROJECT = "tinyassets-test"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = f"https://fcm.googleapis.com/v1/projects/{PROJECT}/messages:send"
PUSH_ENDPOINT = "https://push.example.com/send/abc123"


# --- harness ------------------------------------------------------------------


class _Response:
    def __init__(self, body: bytes = b"{}") -> None:
        self._body = body

    def read(self, _n: int = -1) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


class _Wire:
    """Records every request and answers from a scripted queue."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []
        self.answers: dict[str, list] = {}

    def answer(self, url: str, *answers) -> None:
        """Set what this URL answers, REPLACING any earlier script.

        Replacing rather than appending, so a test that overrides the token
        exchange gets its override on the first call -- appending would have
        served the fixture's success first and quietly proved nothing.
        """
        self.answers[url] = list(answers)

    def __call__(self, request, timeout=None):  # noqa: ANN001
        self.requests.append(request)
        queue = self.answers.get(request.full_url)
        if not queue:
            return _Response()
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def sent_to(self, url: str) -> list[urllib.request.Request]:
        return [r for r in self.requests if r.full_url == url]

    def body_of(self, url: str, index: int = 0) -> dict:
        return json.loads(self.sent_to(url)[index].data.decode("utf-8"))


def _http_error(code: int, body: bytes = b"{}") -> urllib.error.HTTPError:
    import io

    return urllib.error.HTTPError(
        SEND_URL, code, "err", {}, io.BytesIO(body),
    )


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> _Wire:
    w = _Wire()
    w.answer(TOKEN_URL, _Response(
        json.dumps({"access_token": "ya29.test", "expires_in": 3600}).encode()
    ))
    monkeypatch.setattr(urllib.request, "urlopen", w)
    return w


@pytest.fixture
def service_account(monkeypatch: pytest.MonkeyPatch) -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    document = {
        "type": "service_account", "project_id": PROJECT,
        "client_email": "push@tinyassets-test.iam.gserviceaccount.com",
        "private_key": pem,
    }
    monkeypatch.setenv(
        "TINYASSETS_FCM_SERVICE_ACCOUNT_JSON", json.dumps(document),
    )
    return document


@pytest.fixture
def vapid(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    monkeypatch.setenv("TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY", pem)
    monkeypatch.setenv("TINYASSETS_WEBPUSH_VAPID_SUBJECT", "mailto:ops@example.com")


def _subscription() -> dict:
    """A subscription with a real P-256 public key, as a browser mints."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    client = ec.generate_private_key(ec.SECP256R1())
    public = client.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return {
        "endpoint": PUSH_ENDPOINT,
        "keys": {"p256dh": b64(public), "auth": b64(b"0123456789abcdef")},
    }


def _note(**kw) -> Notification:
    return Notification(
        title=kw.pop("title", "Alice's universe"),
        body=kw.pop("body", "TODO: Today"),
        data=kw.pop("data", {"kind": "request", "request_id": "req_abc",
                             "universe_id": "u-alice"}),
        **kw,
    )


# --- FCM ----------------------------------------------------------------------


def test_resolve_transports_builds_android_from_the_configured_credential(
    service_account, wire,
):
    assert set(resolve_transports()) == {"android"}


def test_a_send_builds_the_v1_request_for_the_credentials_own_project(
    service_account, wire,
):
    transport = resolve_transports()["android"]

    assert transport({"token": "device-token-1"}, _note()) == OUTCOME_SENT

    [sent] = wire.sent_to(SEND_URL)
    assert sent.get_header("Authorization") == "Bearer ya29.test"
    message = wire.body_of(SEND_URL)["message"]
    assert message["token"] == "device-token-1"
    # Data only: the app builds the notification (so it can carry an inline
    # Reply), and a `notification` block would be shown by the system without
    # ever reaching the app's code.
    assert "notification" not in message
    assert "notification" not in message["android"]
    assert message["data"]["title"] == "Alice's universe"
    assert message["data"]["body"] == "TODO: Today"
    # The app tags the notification with this id, which is what lets a clear
    # cancel that exact notification and stops one request stacking.
    assert message["data"]["request_id"] == "req_abc"
    assert message["android"]["priority"] == "high"


def test_the_endpoint_cannot_be_influenced_by_the_device_or_the_body(
    service_account, wire,
):
    transport = resolve_transports()["android"]

    transport(
        {"token": "device-token-1", "endpoint": "https://evil.example.com/x"},
        _note(data={"request_id": "req_abc", "endpoint": "https://evil.example.com"}),
    )

    assert [r.full_url for r in wire.requests] == [TOKEN_URL, SEND_URL]


def test_the_recipient_tag_comes_from_the_device_row_never_from_content(
    service_account, wire,
):
    transport = resolve_transports()["android"]

    transport(
        {"token": "device-token-1", "recipient": "rALICE"},
        _note(data={"request_id": "req_abc", "recipient": "rMALLORY"}),
    )

    assert wire.body_of(SEND_URL)["message"]["data"]["recipient"] == "rALICE"


def test_a_silent_clear_carries_no_notification_block(service_account, wire):
    transport = resolve_transports()["android"]

    transport(
        {"token": "device-token-1"},
        Notification(title="", body="", silent=True,
                     data={"kind": "clear", "request_id": "req_abc"}),
    )

    message = wire.body_of(SEND_URL)["message"]
    assert "notification" not in message
    assert message["data"] == {"kind": "clear", "request_id": "req_abc"}
    assert message["android"] == {"priority": "normal"}


def test_the_access_token_is_exchanged_once_for_several_sends(
    service_account, wire,
):
    transport = resolve_transports()["android"]

    transport({"token": "a"}, _note())
    transport({"token": "b"}, _note())

    assert len(wire.sent_to(TOKEN_URL)) == 1
    assert len(wire.sent_to(SEND_URL)) == 2


@pytest.mark.parametrize("code", [400, 404])
def test_an_unregistered_token_is_gone(service_account, wire, code):
    transport = resolve_transports()["android"]
    wire.answer(SEND_URL, _http_error(code, json.dumps({
        "error": {"status": "NOT_FOUND",
                  "details": [{"errorCode": "UNREGISTERED"}]},
    }).encode()))

    with pytest.raises(TransportGone):
        transport({"token": "dead"}, _note())


def test_a_transient_server_error_is_not_gone(service_account, wire):
    """A 503 must not retire a live device."""
    transport = resolve_transports()["android"]
    wire.answer(SEND_URL, _http_error(503))

    with pytest.raises(TransportFailed) as caught:
        transport({"token": "alive"}, _note())
    assert caught.value.cls == "unavailable"


def test_a_4xx_without_a_gone_code_is_refused_not_gone(service_account, wire):
    transport = resolve_transports()["android"]
    wire.answer(SEND_URL, _http_error(403, json.dumps({
        "error": {"status": "PERMISSION_DENIED"},
    }).encode()))

    with pytest.raises(TransportFailed) as caught:
        transport({"token": "alive"}, _note())
    assert caught.value.cls == "refused"


def test_an_fcm_error_body_is_never_forwarded_as_text(service_account, wire):
    transport = resolve_transports()["android"]
    wire.answer(SEND_URL, _http_error(403, json.dumps({
        "error": {"message": "key ya29.SUPER-SECRET rejected",
                  "status": "PERMISSION_DENIED"},
    }).encode()))

    with pytest.raises(TransportFailed) as caught:
        transport({"token": "alive"}, _note())
    assert "SUPER-SECRET" not in str(caught.value)


def test_a_rejected_token_exchange_is_a_bounded_refusal(service_account, wire):
    transport = resolve_transports()["android"]
    wire.answer(TOKEN_URL, urllib.error.HTTPError(
        TOKEN_URL, 401, "unauthorized", {}, None,
    ))

    with pytest.raises(TransportFailed) as caught:
        transport({"token": "alive"}, _note())
    assert caught.value.cls == "refused"
    assert wire.sent_to(SEND_URL) == []


@pytest.mark.parametrize("raw", [
    "not json",
    "[]",
    json.dumps({"project_id": "p", "client_email": "e@x"}),  # no private_key
    json.dumps({"client_email": "e@x", "private_key": "k"}),  # no project_id
])
def test_a_malformed_credential_leaves_android_unconfigured(
    monkeypatch, wire, raw,
):
    """A configuration fault says so once and stays off; it must not raise into
    whatever raised the request."""
    monkeypatch.setenv("TINYASSETS_FCM_SERVICE_ACCOUNT_JSON", raw)

    assert "android" not in resolve_transports()


def test_nothing_configured_resolves_to_nothing(monkeypatch):
    for var in (
        "TINYASSETS_FCM_SERVICE_ACCOUNT_JSON",
        "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY",
    ):
        monkeypatch.delenv(var, raising=False)

    assert resolve_transports() == {}


# --- web push -----------------------------------------------------------------


def test_web_push_is_available_with_no_third_party_project(vapid, wire):
    """The whole chain is provable before any messaging project exists."""
    assert set(resolve_transports()) == {"web"}


def test_a_web_send_is_vapid_signed_and_encrypted(vapid, wire):
    transport = resolve_transports()["web"]
    wire.answer(PUSH_ENDPOINT, _Response(b""))

    assert transport({"token": json.dumps(_subscription())}, _note()) == OUTCOME_SENT

    [sent] = wire.sent_to(PUSH_ENDPOINT)
    authorization = sent.get_header("Authorization")
    assert authorization.startswith("vapid t=")
    assert ", k=" in authorization
    assert sent.get_header("Content-encoding") == "aes128gcm"
    # The body is ciphertext: the words are not on the wire in the clear.
    assert b"TODO: Today" not in sent.data
    assert b"Alice's universe" not in sent.data


def test_a_dropped_web_subscription_is_gone(vapid, wire):
    transport = resolve_transports()["web"]
    wire.answer(PUSH_ENDPOINT, urllib.error.HTTPError(
        PUSH_ENDPOINT, 410, "gone", {}, None,
    ))

    with pytest.raises(TransportGone):
        transport({"token": json.dumps(_subscription())}, _note())


def test_a_web_push_outage_is_not_gone(vapid, wire):
    transport = resolve_transports()["web"]
    wire.answer(PUSH_ENDPOINT, urllib.error.HTTPError(
        PUSH_ENDPOINT, 500, "boom", {}, None,
    ))

    with pytest.raises(TransportFailed) as caught:
        transport({"token": json.dumps(_subscription())}, _note())
    assert caught.value.cls == "unavailable"


@pytest.mark.parametrize("subscription", [
    {"endpoint": "http://push.example.com/x", "keys": {"p256dh": "k", "auth": "a"}},
    {"endpoint": PUSH_ENDPOINT, "keys": {"p256dh": "k"}},
    {"endpoint": PUSH_ENDPOINT},
    {"keys": {"p256dh": "k", "auth": "a"}},
])
def test_a_malformed_subscription_is_refused_before_any_request(
    vapid, wire, subscription,
):
    transport = resolve_transports()["web"]

    with pytest.raises(TransportFailed):
        transport({"token": json.dumps(subscription)}, _note())
    assert wire.sent_to(PUSH_ENDPOINT) == []


def test_a_body_beyond_one_record_is_refused_rather_than_truncated(vapid, wire):
    """Silently cutting an encrypted body would ship half a sentence to a lock
    screen. The composer bounds it; this is the guard behind that."""
    transport = resolve_transports()["web"]

    with pytest.raises(TransportFailed):
        transport(
            {"token": json.dumps(_subscription())},
            _note(body="x" * 5000),
        )
    assert wire.sent_to(PUSH_ENDPOINT) == []


@pytest.mark.parametrize("subject", ["", "ops@example.com", "tel:123"])
def test_a_vapid_subject_that_is_not_a_contact_leaves_web_unconfigured(
    monkeypatch, subject,
):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setenv("TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY", key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii"))
    monkeypatch.setenv("TINYASSETS_WEBPUSH_VAPID_SUBJECT", subject)

    assert "web" not in resolve_transports()


def test_a_key_that_is_not_a_pem_leaves_web_unconfigured(monkeypatch):
    monkeypatch.setenv("TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY", "not-a-key")
    monkeypatch.setenv("TINYASSETS_WEBPUSH_VAPID_SUBJECT", "mailto:ops@example.com")

    assert "web" not in resolve_transports()


def test_the_key_script_output_configures_the_transport_it_is_for(
    monkeypatch, wire,
):
    """The generator and the reader have to agree. A script that prints a key
    the transport cannot load is a stale pointer in the docstring that names
    it, so this asserts the round trip rather than the key's shape."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        from webpush_keys import generate
    finally:
        sys.path.pop(0)

    for name, value in generate("mailto:ops@example.com").items():
        monkeypatch.setenv(name, value)

    transports = resolve_transports()
    assert "web" in transports
    wire.answer(PUSH_ENDPOINT, _Response(b""))
    assert transports["web"](
        {"token": json.dumps(_subscription())}, _note(),
    ) == OUTCOME_SENT


def test_the_printed_key_lines_load_from_an_env_file(
    monkeypatch, wire, capsys,
):
    """Production reads these from /etc/tinyassets/env, one line per variable.
    A multi-line PEM cannot live there, so the script prints each value on one
    line and the reader accepts the escaped newlines. This drives the PRINTED
    text, which is what an operator pastes, not the generator's return value."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        from webpush_keys import main
    finally:
        sys.path.pop(0)

    assert main(["--subject", "https://tinyassets.io"]) == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines()
             if ln and not ln.startswith("#")]
    assert len(lines) == 3, lines
    for line in lines:
        name, _, value = line.partition("=")
        assert "\n" not in value
        monkeypatch.setenv(name, value)

    from tinyassets.onboarding.notifications import _vapid_public

    assert _vapid_public() == os.environ["TINYASSETS_WEBPUSH_VAPID_PUBLIC_KEY"]
    transports = resolve_transports()
    assert "web" in transports
    wire.answer(PUSH_ENDPOINT, _Response(b""))
    assert transports["web"](
        {"token": json.dumps(_subscription())}, _note(),
    ) == OUTCOME_SENT


def test_the_key_script_refuses_a_subject_a_push_service_cannot_contact():
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        from webpush_keys import generate
    finally:
        sys.path.pop(0)

    with pytest.raises(ValueError, match="mailto:"):
        generate("ops@example.com")


# --- and the two together, through dispatch -----------------------------------


def test_dispatch_reaches_both_platforms_with_their_own_transport(
    tmp_path: Path, monkeypatch, service_account, vapid, wire,
):
    """One owner, two kinds of device, one request: each goes out over the
    transport for its own platform, through the real resolution."""
    from tinyassets.api import visibility as vis
    from tinyassets.daemon_server import (
        claim_founder_home,
        ensure_universe_registered,
        grant_universe_access,
        set_universe_display_name,
    )
    from tinyassets.owner_notifications import notify_request_raised
    from tinyassets.storage import owner_devices as devices

    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    owner, uid = "workos|alice-wire", "u-alice-wire"
    udir = base / uid
    udir.mkdir(parents=True)
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner,
    )
    claim_founder_home(base, owner, uid)
    vis.set_universe_visibility(uid, "private", source="default")
    set_universe_display_name(base, universe_id=uid, display_name="Alice's universe")
    devices.register_device(
        base, owner_user_id=owner, platform="android", token="android-token",
    )
    devices.register_device(
        base, owner_user_id=owner, platform="web", token=_subscription(),
    )
    wire.answer(PUSH_ENDPOINT, _Response(b""))

    result = notify_request_raised(
        base, universe_id=uid, raised_by=owner,
        request={"request_id": "req_both", "kind": "TODO", "title": "Today"},
    )

    assert result["sent"] == 2
    assert len(wire.sent_to(SEND_URL)) == 1
    assert len(wire.sent_to(PUSH_ENDPOINT)) == 1
    assert wire.body_of(SEND_URL)["message"]["data"]["title"] == (
        "Alice's universe asks"
    )
