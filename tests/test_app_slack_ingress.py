"""Tests for the Slack app-event HTTP admission path.

Weighted toward the properties that make a publicly reachable, HMAC-only
endpoint safe: absent configuration refuses even a *correct* signature, the
handshake branch is not an unauthenticated echo, and every refusal looks alike.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from tinyassets.app_slack_ingress import (
    API_APP_ID_ENV,
    MIN_SIGNING_SECRET_DISTINCT_CHARS,
    MIN_SIGNING_SECRET_LENGTH,
    REFUSAL_BODY,
    SIGNING_SECRET_ENV,
    TEAM_IDS_ENV,
    handle_slack_request,
    resolve_allowed_team_ids,
    resolve_boundary,
)

ALLOWED = frozenset({"T0BN5LK57FT"})

SECRET = "9f2c41ab7d05e6839c1b4a7e2d508f6a"
APP_ID = "A0BN1Q98MTQ"
TEAM_ID = "T0BN5LK57FT"


def _signed(body: bytes, *, secret: str = SECRET, timestamp: int | None = None):
    ts = str(int(time.time()) if timestamp is None else timestamp)
    digest = hmac.new(
        secret.encode("utf-8"),
        b"v0:" + ts.encode("ascii") + b":" + body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "x-slack-request-timestamp": ts,
        "x-slack-signature": f"v0={digest}",
    }


def _event_body(event_id: str = "Ev00000001", *, user: str = "U0123") -> bytes:
    return json.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": TEAM_ID,
            "event_id": event_id,
            "event": {"type": "app_mention", "user": user, "text": "hi"},
        }
    ).encode("utf-8")


def _handshake_body(challenge: str = "3eZbrw1aB") -> bytes:
    return json.dumps({"type": "url_verification", "challenge": challenge}).encode("utf-8")


@pytest.fixture
def configured(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(SIGNING_SECRET_ENV, SECRET)
    monkeypatch.setenv(API_APP_ID_ENV, APP_ID)
    return resolve_boundary(tmp_path)


def _receipt_count(boundary) -> int:
    with boundary.store.connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM app_event_admissions").fetchone()[0]


# --- configuration is fail-closed --------------------------------------------


@pytest.mark.parametrize(
    "secret,app_id",
    [
        (None, APP_ID),
        (SECRET, None),
        ("", APP_ID),
        (SECRET, ""),
        ("   ", APP_ID),
        (SECRET, "  "),
    ],
)
def test_missing_or_blank_configuration_yields_no_boundary(
    tmp_path: Path, monkeypatch, secret, app_id
):
    monkeypatch.delenv(SIGNING_SECRET_ENV, raising=False)
    monkeypatch.delenv(API_APP_ID_ENV, raising=False)
    if secret is not None:
        monkeypatch.setenv(SIGNING_SECRET_ENV, secret)
    if app_id is not None:
        monkeypatch.setenv(API_APP_ID_ENV, app_id)

    assert resolve_boundary(tmp_path) is None


def test_unconfigured_server_refuses_a_correctly_signed_event(tmp_path: Path):
    """The fail-open canary.

    A signature that would verify under *some* key must still be refused when
    the server holds no key. If this ever passes with 200, the endpoint has
    started trusting an empty or defaulted secret.
    """
    body = _event_body()
    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=None, allowed_team_ids=ALLOWED
    )

    assert outcome.status == 401
    assert outcome.admitted is False


def test_refusals_are_indistinguishable(configured):
    """No oracle: every rejection reason looks identical from outside.

    Compares (status, body) rather than body alone. The body-only version of
    this test stayed green while a status-code oracle would have been wide
    open — a reviewer's counterexample, not a hypothetical.
    """
    good = _event_body()
    forged = dict(_signed(good))
    forged["x-slack-signature"] = "v0=" + "0" * 64
    other_app = _event_body_for_other_app()
    unlisted = _event_body_for_team("T_ATTACKER")

    def refusal(**kwargs):
        outcome = handle_slack_request(**kwargs)
        return (outcome.status, outcome.body)

    observed = {
        # not configured
        refusal(raw_body=good, headers=_signed(good), boundary=None,
                allowed_team_ids=ALLOWED),
        # forged signature
        refusal(raw_body=good, headers=forged, boundary=configured,
                allowed_team_ids=ALLOWED),
        # signed with the wrong key
        refusal(raw_body=good, headers=_signed(good, secret="a-different-key"),
                boundary=configured, allowed_team_ids=ALLOWED),
        # correct key, wrong app
        refusal(raw_body=other_app, headers=_signed(other_app),
                boundary=configured, allowed_team_ids=ALLOWED),
        # correct key and app, workspace not on the allow-list
        refusal(raw_body=unlisted, headers=_signed(unlisted),
                boundary=configured, allowed_team_ids=ALLOWED),
    }
    assert observed == {(401, REFUSAL_BODY)}, (
        "every refusal must agree on status AND body; "
        f"observed variants: {sorted(observed)}"
    )


def _event_body_for_other_app() -> bytes:
    return json.dumps(
        {
            "type": "event_callback",
            "api_app_id": "A999OTHER",
            "team_id": TEAM_ID,
            "event_id": "Ev00000099",
            "event": {"type": "app_mention", "user": "U0123", "text": "hi"},
        }
    ).encode("utf-8")


# --- admission ---------------------------------------------------------------


def test_signed_event_is_admitted_once(configured):
    body = _event_body()
    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured, allowed_team_ids=ALLOWED
    )

    assert outcome.status == 200
    assert outcome.admitted is True
    assert outcome.replay is False
    assert _receipt_count(configured) == 1


def test_redelivery_is_acknowledged_as_replay(configured):
    body = _event_body()
    handle_slack_request(
        raw_body=body,
        headers=_signed(body),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )
    again = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured, allowed_team_ids=ALLOWED
    )

    assert again.status == 200
    assert again.replay is True
    assert _receipt_count(configured) == 1, "redelivery must not create a second receipt"


@pytest.mark.parametrize("mutation", ["forged", "tampered", "stale", "wrong_app"])
def test_untrusted_requests_admit_nothing(configured, mutation):
    body = _event_body()
    headers = dict(_signed(body))

    if mutation == "forged":
        headers["x-slack-signature"] = "v0=" + "1" * 64
    elif mutation == "tampered":
        body = body.replace(b'"hi"', b'"gimme the keys"')
    elif mutation == "stale":
        old = int(time.time()) - 4000
        headers = dict(_signed(body, timestamp=old))
    elif mutation == "wrong_app":
        body = _event_body_for_other_app()
        headers = dict(_signed(body))

    outcome = handle_slack_request(
        raw_body=body, headers=headers, boundary=configured, allowed_team_ids=ALLOWED
    )

    assert outcome.status == 401
    assert outcome.admitted is False
    assert _receipt_count(configured) == 0


# --- the URL verification handshake ------------------------------------------


def test_signed_handshake_echoes_only_the_challenge(configured):
    body = _handshake_body("abc123XYZ")
    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured, allowed_team_ids=ALLOWED
    )

    assert outcome.status == 200
    assert outcome.body == "abc123XYZ"
    assert outcome.admitted is False
    assert _receipt_count(configured) == 0, "a handshake is not an event"


def test_unsigned_handshake_echoes_nothing(configured):
    """The handshake must not become an unauthenticated echo oracle."""
    body = _handshake_body("leak-me")
    outcome = handle_slack_request(
        raw_body=body,
        headers=_signed(body, secret="not-the-server-key"),
        boundary=configured, allowed_team_ids=ALLOWED,
    )

    assert outcome.status == 401
    assert "leak-me" not in outcome.body


def test_handshake_shape_cannot_smuggle_an_event(configured):
    """A body claiming both shapes is a handshake and admits nothing."""
    body = json.dumps(
        {
            "type": "url_verification",
            "challenge": "chal",
            "api_app_id": APP_ID,
            "team_id": TEAM_ID,
            "event_id": "Ev00000042",
            "event": {"type": "app_mention", "user": "U0123", "text": "hi"},
        }
    ).encode("utf-8")

    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured, allowed_team_ids=ALLOWED
    )

    assert outcome.body == "chal"
    assert outcome.admitted is False
    assert _receipt_count(configured) == 0


# --- byte fidelity -----------------------------------------------------------


def test_non_ascii_and_odd_whitespace_still_verify(configured):
    """Proves nothing in the path re-serialises the body.

    A JSON round-trip would normalise the spacing and re-encode the emoji,
    changing the bytes the HMAC covers and breaking verification.
    """
    body = (
        '{"type":"event_callback",  "api_app_id":"'
        + APP_ID
        + '","team_id":"'
        + TEAM_ID
        + '","event_id":"Ev0000ABC","event":{"type":"app_mention",'
        '"user":"U0123","text":"hej åäö \U0001f680"}}'
    ).encode("utf-8")

    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured, allowed_team_ids=ALLOWED
    )

    assert outcome.status == 200
    assert outcome.admitted is True


# --- unauthenticated resource bounds -----------------------------------------


class _FakeRequest:
    """Minimal stand-in for a Starlette request body stream."""

    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None):
        self._chunks = chunks
        self.headers = headers or {}

    async def stream(self):
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_declared_oversize_body_is_refused_without_reading():
    """A huge Content-Length is refused before a single chunk is buffered."""
    from tinyassets.app_slack_ingress import (
        MAX_UNAUTHENTICATED_BODY_BYTES,
        BodyTooLarge,
        read_bounded_body,
    )

    request = _FakeRequest(
        [b"x"], {"content-length": str(MAX_UNAUTHENTICATED_BODY_BYTES + 1)}
    )
    with pytest.raises(BodyTooLarge):
        await read_bounded_body(request)


@pytest.mark.asyncio
async def test_chunked_body_without_content_length_is_still_capped():
    """The declared-length gate alone is bypassable — chunked declares nothing."""
    from tinyassets.app_slack_ingress import BodyTooLarge, read_bounded_body

    # No content-length header at all, streamed past the limit.
    request = _FakeRequest([b"x" * 40, b"y" * 40], {})
    with pytest.raises(BodyTooLarge):
        await read_bounded_body(request, limit=50)


@pytest.mark.asyncio
async def test_body_within_the_limit_is_returned_byte_exact():
    from tinyassets.app_slack_ingress import read_bounded_body

    request = _FakeRequest([b'{"a":', b' 1}'], {"content-length": "8"})
    assert await read_bounded_body(request, limit=50) == b'{"a": 1}'


@pytest.mark.asyncio
async def test_malformed_content_length_is_refused():
    from tinyassets.app_slack_ingress import BodyTooLarge, read_bounded_body

    request = _FakeRequest([b"{}"], {"content-length": "not-a-number"})
    with pytest.raises(BodyTooLarge):
        await read_bounded_body(request)


def test_unconfigured_boundary_is_never_invoked():
    """`None` boundary must short-circuit, not merely produce a 401 later."""

    class _Recorder:
        def __init__(self):
            self.calls = 0

        def admit(self, **_kwargs):
            self.calls += 1
            raise AssertionError("boundary must not be reached")

    recorder = _Recorder()
    body = _event_body()
    outcome = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=None, allowed_team_ids=ALLOWED
    )

    assert outcome.status == 401
    assert recorder.calls == 0


def _event_body_for_team(team_id: str, event_id: str = "Ev0000TEAM") -> bytes:
    return json.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": team_id,
            "event_id": event_id,
            "event": {"type": "app_mention", "user": "U_ATTACKER", "text": "x"},
        }
    ).encode("utf-8")


# --- the workspace allow-list ------------------------------------------------
#
# The signing secret is per-APP, not per-workspace: every install signs with the
# same key. A valid signature therefore proves which app is talking, never which
# workspace. Reviewer-demonstrated exploit before this gate existed:
#   {'unlisted_team_status': 200, 'admitted': True}


def test_unlisted_workspace_is_refused_despite_a_valid_signature(configured):
    body = _event_body_for_team("T_ATTACKER")
    outcome = handle_slack_request(
        raw_body=body,
        headers=_signed(body),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )

    assert outcome.status == 401
    assert outcome.admitted is False
    assert _receipt_count(configured) == 0, "an unlisted workspace must not write a ledger row"


def test_listed_workspace_is_admitted(configured):
    """The accept direction — an allow-list that rejects everything is not a gate."""
    body = _event_body_for_team("T0BN5LK57FT", event_id="Ev0000OK")
    outcome = handle_slack_request(
        raw_body=body,
        headers=_signed(body),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )

    assert outcome.status == 200
    assert outcome.admitted is True


def test_empty_allow_list_admits_nobody(configured):
    """Unconfigured allow-list is fail-closed, not fail-open."""
    body = _event_body()
    outcome = handle_slack_request(
        raw_body=body,
        headers=_signed(body),
        boundary=configured,
        allowed_team_ids=frozenset(),
    )
    assert outcome.status == 401

    # and omitting the argument entirely must not mean "allow all"
    omitted = handle_slack_request(
        raw_body=body, headers=_signed(body), boundary=configured
    )
    assert omitted.status == 401


def test_allow_list_parsing(monkeypatch):
    monkeypatch.setenv(TEAM_IDS_ENV, " T111 , T222 ,, ")
    assert resolve_allowed_team_ids() == frozenset({"T111", "T222"})

    monkeypatch.delenv(TEAM_IDS_ENV, raising=False)
    assert resolve_allowed_team_ids() == frozenset()


# --- signing-secret strength -------------------------------------------------


@pytest.mark.parametrize("weak", ["0", "changeme", "x" * (MIN_SIGNING_SECRET_LENGTH - 1)])
def test_weak_signing_secret_is_refused(tmp_path: Path, weak: str):
    """A 1-char secret still produces a verifying HMAC — reviewer-demonstrated.

    Slack issues 32 hex chars; anything materially shorter is a truncated paste
    or a placeholder, and it is brute-forceable.
    """
    assert (
        resolve_boundary(
            tmp_path, env={SIGNING_SECRET_ENV: weak, API_APP_ID_ENV: APP_ID}
        )
        is None
    )


def test_slack_length_secret_is_accepted(tmp_path: Path):
    """The accept direction, using a real-shaped Slack secret (32 hex chars)."""
    real_shape = "0123456789abcdef0123456789abcdef"
    assert (
        resolve_boundary(
            tmp_path, env={SIGNING_SECRET_ENV: real_shape, API_APP_ID_ENV: APP_ID}
        )
        is not None
    )


# --- replay-conflict is not an oracle ----------------------------------------


def test_event_id_reuse_with_different_content_is_acknowledged_not_admitted(configured):
    """Same event_id, different body: acknowledged, and never admitted.

    Two rounds of review shaped this. An unhandled conflict surfaced as 502 —
    an obvious oracle. Refusing it with 401 was still an oracle, just a subtler
    one: a known event_id answered 401 while an unused one answered 200, so
    membership was readable from the status alone. It now answers exactly like
    a fresh delivery, which is also what Slack needs — the delivery is terminal
    either way and must not be retried.
    """
    first = _event_body_for_team("T0BN5LK57FT", event_id="Ev0000DUP")
    handle_slack_request(
        raw_body=first,
        headers=_signed(first),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )

    colliding = json.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": "T0BN5LK57FT",
            "event_id": "Ev0000DUP",
            "event": {"type": "app_mention", "user": "U_ATTACKER", "text": "different"},
        }
    ).encode("utf-8")

    outcome = handle_slack_request(
        raw_body=colliding,
        headers=_signed(colliding),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )

    assert (outcome.status, outcome.body) == (200, "")
    assert outcome.admitted is False, "a conflicting body must never be admitted"
    assert _receipt_count(configured) == 1, "the colliding event must not add a row"


def test_real_slack_handshake_shape_still_works(configured):
    """Slack's genuine handshake is {token, challenge, type} — no api_app_id.

    Regression guard: a fix for the mismatched-app-id echo briefly REQUIRED
    api_app_id, which would have made the Request URL unsaveable in Slack and
    killed the endpoint on arrival. Absent must stay valid.
    """
    body = json.dumps(
        {
            "token": "Jhj5dZrVaK7ZwHHjRyZWjbDl",
            "challenge": "3eZbrw1aBm2rZgRNFrufIbFAqTyBRCiDLxWlbwZeUiVXxOTAcJ",
            "type": "url_verification",
        }
    ).encode("utf-8")

    outcome = handle_slack_request(
        raw_body=body,
        headers=_signed(body),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )

    assert outcome.status == 200
    assert outcome.body == "3eZbrw1aBm2rZgRNFrufIbFAqTyBRCiDLxWlbwZeUiVXxOTAcJ"


def test_handshake_claiming_another_app_is_refused(configured):
    """Reviewer's counterexample: echoed `ORG-BYPASS` under api_app_id A_OTHER."""
    body = json.dumps(
        {
            "type": "url_verification",
            "challenge": "ORG-BYPASS",
            "api_app_id": "A_OTHER",
            "enterprise_id": "E_ATTACKER",
        }
    ).encode("utf-8")

    outcome = handle_slack_request(
        raw_body=body,
        headers=_signed(body),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )

    assert outcome.status == 401
    assert "ORG-BYPASS" not in outcome.body


@pytest.mark.parametrize(
    "weak,label",
    [
        ("0" * 32, "repeated single character"),
        ("x" + " " * 30 + "x", "whitespace padding"),
        ("x" + "\u200b" * 30 + "x", "zero-width padding"),
        ("ab" * 16, "only two distinct characters"),
        ("changeme" * 4, "repeated placeholder word"),
    ],
)
def test_long_but_guessable_secrets_are_refused(tmp_path: Path, weak: str, label: str):
    """Length is not entropy — every one of these cleared a bare length floor."""
    assert len(weak) >= MIN_SIGNING_SECRET_LENGTH, "must be long enough to prove the point"
    assert (
        resolve_boundary(
            tmp_path, env={SIGNING_SECRET_ENV: weak, API_APP_ID_ENV: APP_ID}
        )
        is None
    ), f"{label} must be refused"


def test_invisible_padding_is_refused_even_with_enough_distinct_characters(tmp_path: Path):
    """Isolates the printable-ASCII gate.

    Mutation-probe finding: removing that gate left the suite green, because
    every existing weak-secret case had only two distinct characters and was
    caught by the distinct-character floor instead. This secret clears BOTH the
    length and distinct floors and is rejected solely for containing invisibles
    — so the ASCII gate is the only thing standing between it and acceptance.
    """
    sneaky = "abcdefghij" + "\u200b" * 22  # 32 chars, 11 distinct
    assert len(sneaky) >= MIN_SIGNING_SECRET_LENGTH
    assert len(set(sneaky)) >= MIN_SIGNING_SECRET_DISTINCT_CHARS

    assert (
        resolve_boundary(
            tmp_path, env={SIGNING_SECRET_ENV: sneaky, API_APP_ID_ENV: APP_ID}
        )
        is None
    )


def test_configuration_state_is_not_timeable(configured):
    """Coarse guard on the configured-vs-unconfigured timing oracle.

    A reviewer measured a 767x ratio on the missing-headers path, because header
    validation rejects before any hashing and the original equaliser did not
    reproduce that. The bound is deliberately loose (25x) so ordinary scheduler
    noise cannot make this flaky while a regression of that magnitude still
    fails loudly.
    """
    import statistics

    # The leak needs a body large enough that hashing it dominates, and headers
    # valid enough to reach the hash. With missing headers BOTH paths exit early
    # and look identical — an earlier version of this test used that shape and
    # stayed green with the equaliser deleted.
    body = b'{"type":"event_callback","pad":"' + b"z" * 200_000 + b'"}'
    headers = _signed(body)

    def median_micros(boundary) -> float:
        samples = []
        for _ in range(40):
            start = time.perf_counter()
            handle_slack_request(
                raw_body=body,
                headers=headers,
                boundary=boundary,
                allowed_team_ids=ALLOWED,
            )
            samples.append(time.perf_counter() - start)
        return statistics.median(samples) * 1e6

    # Warm both paths so import/lazy-init cost is not attributed to one of them.
    median_micros(configured)
    median_micros(None)

    armed = median_micros(configured)
    dark = median_micros(None)
    ratio = max(armed, dark) / max(min(armed, dark), 1e-9)

    assert ratio < 25, (
        f"configured={armed:.2f}us dark={dark:.2f}us ratio={ratio:.1f} — "
        "configuration state is distinguishable by timing"
    )


def test_event_id_membership_is_not_observable(configured):
    """The control the previous collision test omitted.

    A known event_id must not answer differently from an unused one. The
    earlier version compared only "conflict vs refusal" and so missed that
    known IDs returned 401 while unused IDs returned 200 — a valid signer could
    enumerate the ledger by watching the status code.
    """
    seeded = _event_body_for_team("T0BN5LK57FT", event_id="EvKNOWN")
    handle_slack_request(
        raw_body=seeded,
        headers=_signed(seeded),
        boundary=configured,
        allowed_team_ids=ALLOWED,
    )

    def probe(event_id: str, text: str):
        body = json.dumps(
            {
                "type": "event_callback",
                "api_app_id": APP_ID,
                "team_id": "T0BN5LK57FT",
                "event_id": event_id,
                "event": {"type": "app_mention", "user": "U1", "text": text},
            }
        ).encode("utf-8")
        outcome = handle_slack_request(
            raw_body=body,
            headers=_signed(body),
            boundary=configured,
            allowed_team_ids=ALLOWED,
        )
        return (outcome.status, outcome.body)

    known = probe("EvKNOWN", "different content")   # collides with the seed
    unused = probe("EvUNUSED", "different content")  # fresh id

    assert known == unused, (
        f"ledger membership is observable: known={known} unused={unused}"
    )
