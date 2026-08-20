"""The authenticated wire in front of `deliver_app_event`.

`deliver_app_event` trusts every field it is given, so these tests are the
proof that only the real transport can supply them.
"""

from __future__ import annotations

import base64
import json

import pytest

from tinyassets import app_ingress_http as http

KEY_BYTES = b"k" * 32
KEY_B64 = base64.b64encode(KEY_BYTES).decode("ascii")
ENV = {http.HMAC_ENV: KEY_B64}
NOW = 1_700_000_000.0

BODY = {
    "provider": "slack",
    "api_app_id": "A0WIRE00001",
    "workspace_id": "T0WIRE00001",
    "actor_team_id": "T0WIRE00001",
    "external_sender_id": "U0WIRE00001",
    "channel_id": "C0WIRE00001",
    "event_id": "Ev-wire-1",
    "event_type": "app_mention",
    "text": "<@U0BOT> hello",
    "thread_ts": "",
}


class _Result:
    handled = True
    provider_receipt_ref = "slack:C0WIRE00001:1700000000.000100"


def _spy():
    calls = []

    def _deliver(**kwargs):
        calls.append(kwargs)
        return _Result()

    return _deliver, calls


def _signed(body: bytes | None = None, *, timestamp: str = str(int(NOW))):
    raw = body if body is not None else json.dumps(BODY).encode("utf-8")
    return raw, {
        http.SIGNATURE_HEADER: http.sign(raw, timestamp, KEY_BYTES),
        http.TIMESTAMP_HEADER: timestamp,
    }


def test_a_correctly_signed_request_is_delivered():
    raw, headers = _signed()
    deliver, calls = _spy()

    status, payload = http.handle_request(
        body=raw, headers=headers, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 200
    assert payload == {
        "handled": True,
        "provider_receipt_ref": "slack:C0WIRE00001:1700000000.000100",
    }
    assert calls[0]["external_sender_id"] == "U0WIRE00001"


def test_signed_delivery_marks_only_the_current_app_transport_request():
    raw, headers = _signed()
    seen: list[bool] = []

    def _deliver(**_kwargs):
        seen.append(http.authenticated_app_transport())
        return _Result()

    assert http.authenticated_app_transport() is False
    status, _ = http.handle_request(
        body=raw,
        headers=headers,
        env=ENV,
        now=NOW,
        deliver=_deliver,
    )

    assert status == 200
    assert seen == [True]
    assert http.authenticated_app_transport() is False


def test_an_unsigned_request_never_reaches_delivery():
    raw = json.dumps(BODY).encode("utf-8")
    deliver, calls = _spy()

    status, payload = http.handle_request(
        body=raw, headers={}, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 401
    assert calls == []


def test_a_wrong_signature_never_reaches_delivery():
    raw, headers = _signed()
    headers[http.SIGNATURE_HEADER] = "0" * 64
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=headers, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 401
    assert calls == []


def test_a_tampered_body_invalidates_the_signature():
    """The signature covers the body, so claims cannot be edited in flight."""
    raw, headers = _signed()
    tampered = dict(BODY)
    tampered["external_sender_id"] = "U0ATTACKER1"
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=json.dumps(tampered).encode("utf-8"),
        headers=headers,
        env=ENV,
        now=NOW,
        deliver=deliver,
    )

    assert status == 401
    assert calls == []


def test_a_captured_request_expires():
    """Replay is bounded by a window rather than being possible forever."""
    raw, headers = _signed()
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw,
        headers=headers,
        env=ENV,
        now=NOW + http.MAX_SKEW_SECONDS + 1,
        deliver=deliver,
    )

    assert status == 401
    assert calls == []


def test_a_re_dated_replay_is_refused():
    """Re-stamping a captured signature must not extend its life.

    This is why the timestamp is inside the signed message rather than beside
    it: with the body signed alone, swapping the header would work forever.
    """
    raw, headers = _signed()
    headers[http.TIMESTAMP_HEADER] = str(int(NOW + http.MAX_SKEW_SECONDS + 10))
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw,
        headers=headers,
        env=ENV,
        now=NOW + http.MAX_SKEW_SECONDS + 10,
        deliver=deliver,
    )

    assert status == 401
    assert calls == []


@pytest.mark.parametrize(
    "env",
    [
        {},
        {http.HMAC_ENV: ""},
        {http.HMAC_ENV: "not-base64!!"},
        {http.HMAC_ENV: base64.b64encode(b"short").decode("ascii")},
    ],
    ids=["unset", "empty", "malformed", "too-short"],
)
def test_a_daemon_without_a_usable_key_is_closed_not_open(env):
    """No key must mean no ingress — never an unauthenticated one."""
    raw, headers = _signed()
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=headers, env=env, now=NOW, deliver=deliver
    )

    assert status == 401
    assert calls == []


def test_an_unset_key_cannot_be_exploited_by_signing_with_the_empty_key():
    """The attack a missing key actually enables.

    Signing with the GOOD key and asserting 401 proves nothing here — it fails
    on signature mismatch whether or not the key guard exists. The real attacker
    signs with the key the deployment would otherwise fall back to, and that key
    is `b""`, which they know. Without the presence guard this returns 200.
    """
    raw = json.dumps(BODY).encode("utf-8")
    ts = str(int(NOW))
    headers = {
        http.SIGNATURE_HEADER: http.sign(raw, ts, b""),
        http.TIMESTAMP_HEADER: ts,
    }
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=headers, env={}, now=NOW, deliver=deliver
    )

    assert status == 401
    assert calls == []


def test_a_too_short_key_cannot_be_exploited_by_signing_with_it():
    """A guessable key must be refused for being guessable, not by luck.

    Same shape as above: the length guard is only load-bearing against someone
    who signs with the weak key, so that is what this signs with.
    """
    short = b"short"
    raw = json.dumps(BODY).encode("utf-8")
    ts = str(int(NOW))
    headers = {
        http.SIGNATURE_HEADER: http.sign(raw, ts, short),
        http.TIMESTAMP_HEADER: ts,
    }
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw,
        headers=headers,
        env={http.HMAC_ENV: base64.b64encode(short).decode("ascii")},
        now=NOW,
        deliver=deliver,
    )

    assert status == 401
    assert calls == []


def test_every_auth_failure_looks_identical_to_the_caller():
    """A caller must not be able to probe which part of auth it failed."""
    raw, headers = _signed()
    bad_sig = dict(headers)
    bad_sig[http.SIGNATURE_HEADER] = "0" * 64
    stale = dict(headers)

    seen = {
        json.dumps(
            http.handle_request(
                body=raw, headers={}, env=ENV, now=NOW, deliver=_spy()[0]
            )
        ),
        json.dumps(
            http.handle_request(
                body=raw, headers=bad_sig, env=ENV, now=NOW, deliver=_spy()[0]
            )
        ),
        json.dumps(
            http.handle_request(
                body=raw,
                headers=stale,
                env=ENV,
                now=NOW + 10_000,
                deliver=_spy()[0],
            )
        ),
        json.dumps(
            http.handle_request(
                body=raw, headers=headers, env={}, now=NOW, deliver=_spy()[0]
            )
        ),
    }

    assert len(seen) == 1, f"auth failures are distinguishable: {seen}"


def test_undeclared_fields_cannot_reach_delivery():
    """An allowlist, so a new keyword on `deliver_app_event` is not remotely settable.

    `converse` and `transport` are test-injection seams; reaching them from the
    wire would let a caller replace the universe's own voice.
    """
    hostile = dict(BODY)
    hostile["converse"] = "not a callable but it must not arrive"
    hostile["fallback_universe_id"] = "u-victim"
    raw, headers = _signed(json.dumps(hostile).encode("utf-8"))
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=headers, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 200
    assert "converse" not in calls[0]
    assert "transport" not in calls[0]
    assert "fallback_universe_id" not in calls[0]
    assert set(calls[0]) == set(http._ACCEPTED_FIELDS)


def test_an_oversized_body_is_refused_before_parsing():
    raw = b"x" * (http.MAX_BODY_BYTES + 1)
    _, headers = _signed(raw)
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=headers, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 401
    assert calls == []


def test_a_malformed_body_is_a_400_not_a_crash():
    raw, headers = _signed(b"{not json")
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=headers, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 400
    assert calls == []


def test_a_non_string_field_is_rejected():
    hostile = dict(BODY)
    hostile["text"] = {"nested": "object"}
    raw, headers = _signed(json.dumps(hostile).encode("utf-8"))
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=headers, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 400
    assert calls == []


def test_header_names_are_case_insensitive():
    """HTTP header case is not guaranteed by any client."""
    raw, headers = _signed()
    upper = {k.upper(): v for k, v in headers.items()}
    deliver, calls = _spy()

    status, _ = http.handle_request(
        body=raw, headers=upper, env=ENV, now=NOW, deliver=deliver
    )

    assert status == 200
    assert len(calls) == 1


# ── the app-token handover (10.2c) ───────────────────────────────────────────


def _cred_body(universe_id="u-cred-1", connection_id="slack-main"):
    return json.dumps(
        {"universe_id": universe_id, "connection_id": connection_id}
    ).encode("utf-8")


def _cred_headers(raw, timestamp=str(int(NOW))):
    return {
        http.SIGNATURE_HEADER: http.sign(raw, timestamp, KEY_BYTES),
        http.TIMESTAMP_HEADER: timestamp,
    }


def test_a_signed_transport_gets_the_app_token():
    raw = _cred_body()
    seen = []

    def _resolve(uid, cid):
        seen.append((uid, cid))
        return "xapp-1-A0TEST-secret"

    status, payload = http.handle_credentials_request(
        body=raw, headers=_cred_headers(raw), env=ENV, now=NOW, resolve=_resolve
    )

    assert status == 200
    assert payload == {"app_token": "xapp-1-A0TEST-secret"}
    assert seen == [("u-cred-1", "slack-main")]


def test_an_unsigned_caller_gets_no_credential():
    """The whole point: this hands out a secret, so auth is the gate."""
    raw = _cred_body()
    called = []

    status, payload = http.handle_credentials_request(
        body=raw,
        headers={},
        env=ENV,
        now=NOW,
        resolve=lambda u, c: called.append((u, c)) or "xapp-leak",
    )

    assert status == 401
    assert payload == {"error": "unauthenticated"}
    assert called == [], "the vault was consulted for an unauthenticated caller"


def test_a_tampered_universe_id_invalidates_the_signature():
    """Otherwise a captured request could be re-aimed at another universe."""
    raw = _cred_body()
    headers = _cred_headers(raw)
    called = []

    status, _ = http.handle_credentials_request(
        body=_cred_body(universe_id="u-someone-else"),
        headers=headers,
        env=ENV,
        now=NOW,
        resolve=lambda u, c: called.append(u) or "xapp-leak",
    )

    assert status == 401
    assert called == []


def test_a_missing_credential_is_404_not_an_empty_success():
    """The transport must be able to tell "not deposited" from "bad signature"."""
    raw = _cred_body()

    status, payload = http.handle_credentials_request(
        body=raw, headers=_cred_headers(raw), env=ENV, now=NOW, resolve=lambda u, c: ""
    )

    assert status == 404
    assert "app_token" not in payload


def test_the_credential_route_needs_both_ids():
    """A universe-only request must not be answered with some default connection."""
    raw = json.dumps({"universe_id": "u-cred-1"}).encode("utf-8")
    called = []

    status, _ = http.handle_credentials_request(
        body=raw,
        headers=_cred_headers(raw),
        env=ENV,
        now=NOW,
        resolve=lambda u, c: called.append(u) or "xapp-leak",
    )

    assert status == 400
    assert called == []


def test_a_stale_credential_request_expires():
    raw = _cred_body()
    called = []

    status, _ = http.handle_credentials_request(
        body=raw,
        headers=_cred_headers(raw),
        env=ENV,
        now=NOW + http.MAX_SKEW_SECONDS + 1,
        resolve=lambda u, c: called.append(u) or "xapp-leak",
    )

    assert status == 401
    assert called == []


# ---------------------------------------------------------------------------
# Slice 2: the async /app-events route OFFLOADS the deliver turn to a bounded
# per-conversation worker (it must not block the event loop) and acks fast.
# ---------------------------------------------------------------------------


def test_app_events_offloads_the_turn_and_acks_without_blocking(monkeypatch):
    import threading

    from starlette.testclient import TestClient

    monkeypatch.setenv(http.HMAC_ENV, KEY_B64)
    # Fresh executor so this test is isolated from module singleton state.
    monkeypatch.setattr(
        "tinyassets.app_ingress_workers._EXECUTOR", None, raising=False,
    )

    delivered = threading.Event()
    seen: dict = {}

    def _spy_deliver(**fields):
        # The turn runs on a WORKER thread — the authenticated-transport
        # ContextVar must be set there (Slice 2 sets it inside the worker fn).
        seen["ctx"] = http._authenticated_app_transport.get()
        seen["fields"] = fields
        delivered.set()
        return _Result()

    monkeypatch.setattr("tinyassets.app_ingress.deliver_app_event", _spy_deliver)

    app = http.create_app_ingress_app()
    client = TestClient(app)
    raw, headers = _signed(timestamp=str(int(__import__("time").time())))
    resp = client.post("/app-events", content=raw, headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"handled": True, "queued": True}   # fast ack, not the turn result
    assert delivered.wait(5)                                   # the turn ran on a worker
    assert seen["ctx"] is True                                 # ContextVar set in the worker
    assert seen["fields"]["external_sender_id"] == "U0WIRE00001"


def test_app_events_returns_503_without_awaiting_the_notice(monkeypatch):
    import threading

    from starlette.testclient import TestClient

    import tinyassets.app_ingress_http as h
    from tinyassets.app_ingress import OVERLOADED_NOTICE

    monkeypatch.setenv(http.HMAC_ENV, KEY_B64)
    # Fresh notifier for isolation.
    monkeypatch.setattr(h, "_NOTIFIER", None, raising=False)
    monkeypatch.setattr(h, "_NOTIFIER_INFLIGHT", 0, raising=False)

    class _FullExecutor:
        def submit(self, key, fn):
            return False  # backlog saturated

    monkeypatch.setattr(
        "tinyassets.app_ingress_workers.get_ingress_executor",
        lambda: _FullExecutor(),
    )
    ran = {"n": 0}
    monkeypatch.setattr(
        "tinyassets.app_ingress.deliver_app_event",
        lambda **k: ran.__setitem__("n", ran["n"] + 1),
    )
    # The notice BLOCKS. If the 503 awaited it, client.post would not return until
    # the notice finished — so proving the 503 comes back while the notice is STILL
    # blocked is a real decoupling proof (Codex: an instant spy would pass either
    # way). The bounded release keeps a regression from hanging CI forever.
    started = threading.Event()
    done = threading.Event()
    release = threading.Event()
    notices: list = []

    def _blocking_notice(**k):
        notices.append(k)
        started.set()
        release.wait(10)
        done.set()
        return _Result()

    monkeypatch.setattr("tinyassets.app_ingress.deliver_app_notice", _blocking_notice)

    app = http.create_app_ingress_app()
    client = TestClient(app)
    raw, headers = _signed(timestamp=str(int(__import__("time").time())))
    resp = client.post("/app-events", content=raw, headers=headers)

    assert resp.status_code == 503                            # returned...
    assert resp.json() == {"handled": False, "overloaded": True}
    assert ran["n"] == 0                                       # turn not run
    assert started.wait(5)                                    # the notice WAS scheduled
    assert not done.is_set()                                  # ...503 came back BEFORE it finished
    release.set()                                             # let the notice complete
    assert done.wait(5)
    assert notices[0]["notice"] == OVERLOADED_NOTICE
    assert notices[0]["channel_id"] == BODY["channel_id"]     # routed to the sender


def _spin(pred, timeout=5.0):
    import time as _t
    deadline = _t.monotonic() + timeout
    while _t.monotonic() < deadline:
        if pred():
            return True
        _t.sleep(0.005)
    return pred()


def test_the_notifier_drops_when_saturated_and_recovers(monkeypatch):
    import threading

    import tinyassets.app_ingress_http as h

    monkeypatch.setattr(h, "_NOTIFIER", None, raising=False)
    monkeypatch.setattr(h, "_NOTIFIER_INFLIGHT", 0, raising=False)

    release = threading.Event()

    def _blocking():
        release.wait(5)

    # Fill to the in-flight cap; every one is admitted.
    for _ in range(h._NOTIFIER_MAX_INFLIGHT):
        assert h._fire_best_effort_notice(_blocking) is True
    # The next is DROPPED (returns False) rather than queued unbounded.
    assert h._fire_best_effort_notice(_blocking) is False

    # Recovery: once the blocked notices drain, in-flight returns to 0 and a fresh
    # notice is admitted again — the drop is transient, not a permanent wedge.
    release.set()
    assert _spin(lambda: h._NOTIFIER_INFLIGHT == 0)
    assert h._fire_best_effort_notice(lambda: None) is True
    assert _spin(lambda: h._NOTIFIER_INFLIGHT == 0)


def test_the_notifier_scheduling_failure_is_leak_free_and_non_raising(monkeypatch):
    import tinyassets.app_ingress_http as h

    monkeypatch.setattr(h, "_NOTIFIER_INFLIGHT", 0, raising=False)

    class _RejectingPool:
        def submit(self, fn):
            raise RuntimeError("cannot schedule (no thread / shutting down)")

    monkeypatch.setattr(h, "_NOTIFIER", _RejectingPool(), raising=False)

    # A scheduling failure must NOT raise (the 503 path depends on it), must return
    # False, and must NOT leak a permit — else repeated failures permanently consume
    # all permits and silently drop every future notice (Codex #3).
    for _ in range(20):
        assert h._fire_best_effort_notice(lambda: None) is False
        assert h._NOTIFIER_INFLIGHT == 0


def test_the_notifier_permit_release_is_idempotent_after_partial_enqueue(monkeypatch):
    import tinyassets.app_ingress_http as h

    monkeypatch.setattr(h, "_NOTIFIER_INFLIGHT", 0, raising=False)

    class _PartialEnqueuePool:
        # Mimics CPython: `submit` ENQUEUES the work item (which later RUNS and
        # releases the permit via `_wrapped`'s finally) and THEN thread creation
        # raises (which our except path also handles). Both must not double-release.
        def submit(self, wrapped):
            wrapped()  # the queued work item runs later -> releases the permit
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(h, "_NOTIFIER", _PartialEnqueuePool(), raising=False)

    # Released EXACTLY ONCE despite both paths firing — not -1 (Codex round-4 #1).
    assert h._fire_best_effort_notice(lambda: None) is False
    assert h._NOTIFIER_INFLIGHT == 0
    # Repeatable: the counter never drifts below 0, so the cap stays enforceable.
    for _ in range(20):
        assert h._fire_best_effort_notice(lambda: None) is False
        assert h._NOTIFIER_INFLIGHT == 0


def test_app_events_surfaces_an_escaped_turn_failure_to_the_user(monkeypatch):
    import threading

    from starlette.testclient import TestClient

    monkeypatch.setenv(http.HMAC_ENV, KEY_B64)
    monkeypatch.setattr(
        "tinyassets.app_ingress_workers._EXECUTOR", None, raising=False,
    )

    posted = threading.Event()
    notices: list = []

    def _boom(**fields):
        # A delivery that escapes its OWN failure notice (a routing/post fault),
        # not an ordinary in-turn failure.
        raise RuntimeError("delivery escaped")

    def _spy_notice(**k):
        notices.append(k)
        posted.set()
        return _Result()

    monkeypatch.setattr("tinyassets.app_ingress.deliver_app_event", _boom)
    monkeypatch.setattr("tinyassets.app_ingress.deliver_app_notice", _spy_notice)

    app = http.create_app_ingress_app()
    client = TestClient(app)
    raw, headers = _signed(timestamp=str(int(__import__("time").time())))
    resp = client.post("/app-events", content=raw, headers=headers)

    # The ack is still fast (the turn is offloaded); the escape is surfaced on the
    # worker, not swallowed with only a log line.
    assert resp.status_code == 200
    assert posted.wait(5)
    assert len(notices) == 1
    assert notices[0]["channel_id"] == BODY["channel_id"]
    assert notices[0]["notice"]  # a non-empty honest notice, not silence


def test_app_events_still_401s_a_bad_signature_synchronously(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setenv(http.HMAC_ENV, KEY_B64)
    monkeypatch.setattr(
        "tinyassets.app_ingress_workers._EXECUTOR", None, raising=False,
    )
    ran = {"n": 0}
    monkeypatch.setattr(
        "tinyassets.app_ingress.deliver_app_event",
        lambda **k: ran.__setitem__("n", ran["n"] + 1),
    )

    app = http.create_app_ingress_app()
    client = TestClient(app)
    raw = json.dumps(BODY).encode("utf-8")
    resp = client.post(
        "/app-events", content=raw,
        headers={http.SIGNATURE_HEADER: "deadbeef", http.TIMESTAMP_HEADER: "0"},
    )
    assert resp.status_code == 401
    assert ran["n"] == 0  # auth still gates BEFORE any offload
