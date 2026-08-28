"""The billing adapter boundary, fail-soft posture, and webhook verification."""

from __future__ import annotations

import hashlib
import hmac
import pathlib
import re
import time

import pytest

from tinyassets.billing import (
    BillingUnavailable,
    billing_enabled,
    create_checkout_session,
    subscription_state_from_event,
)
from tinyassets.billing.stripe_adapter import verify_webhook_signature

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_nothing_outside_the_billing_package_knows_stripe_exists():
    """The boundary that keeps the processor swappable and metering independent."""
    offenders = []
    pattern = re.compile(r"^\s*(?:import\s+stripe|from\s+stripe\b)", re.MULTILINE)
    for path in (REPO / "tinyassets").rglob("*.py"):
        if "billing" in path.parts:
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], f"Stripe imported outside the adapter: {offenders}"


def test_the_adapter_itself_uses_no_stripe_sdk():
    """Stdlib only — an SDK would put a stripe import one install away everywhere."""
    source = (REPO / "tinyassets" / "billing" / "stripe_adapter.py").read_text(
        encoding="utf-8"
    )
    assert not re.search(r"^\s*(?:import\s+stripe|from\s+stripe\b)", source, re.M)


def test_billing_is_off_without_a_key_and_says_so(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert billing_enabled() is False


def test_calls_fail_soft_rather_than_crashing_when_billing_is_off(monkeypatch):
    """A missing processor must be a clear refusal, never an unhandled error."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(BillingUnavailable):
        create_checkout_session(
            universe_id="u-1", success_url="https://x/ok", cancel_url="https://x/no"
        )


# --- webhook verification ----------------------------------------------------

SECRET = "whsec_test_secret"


def _sign(payload: bytes, timestamp: int, secret: str = SECRET) -> str:
    mac = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={mac}"


def test_a_valid_signature_verifies():
    payload = b'{"type":"customer.subscription.deleted"}'
    now = time.time()
    header = _sign(payload, int(now))
    assert verify_webhook_signature(payload, header, now=now, secret=SECRET) is True


def test_a_forged_signature_is_rejected():
    """Otherwise anyone reaching the endpoint could grant themselves the paid tier."""
    payload = b'{"type":"checkout.session.completed"}'
    now = time.time()
    forged = f"t={int(now)},v1={'0' * 64}"
    assert verify_webhook_signature(payload, forged, now=now, secret=SECRET) is False


def test_a_tampered_payload_is_rejected():
    now = time.time()
    header = _sign(b'{"amount":1}', int(now))
    assert (
        verify_webhook_signature(b'{"amount":9999}', header, now=now, secret=SECRET)
        is False
    )


def test_a_replayed_signature_is_rejected():
    """A captured webhook must not be replayable hours later."""
    payload = b'{"type":"checkout.session.completed"}'
    signed_at = time.time() - 3600
    header = _sign(payload, int(signed_at))
    assert (
        verify_webhook_signature(payload, header, now=time.time(), secret=SECRET)
        is False
    )


@pytest.mark.parametrize("header", ["", "garbage", "t=,v1=", "v1=abc", "t=abc,v1=def"])
def test_a_malformed_signature_header_is_rejected(header):
    assert (
        verify_webhook_signature(b"{}", header, now=time.time(), secret=SECRET) is False
    )


def test_verification_fails_closed_without_a_configured_secret(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    payload = b"{}"
    header = _sign(payload, int(time.time()))
    assert verify_webhook_signature(payload, header, now=time.time()) is False


# --- event -> tier mapping ---------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("active", "paid"),
        ("trialing", "paid"),
        ("past_due", "free"),
        ("canceled", "free"),
        ("unpaid", "free"),
        ("incomplete_expired", "free"),
    ],
)
def test_only_an_entitling_status_yields_the_paid_tier(status, expected):
    event = {
        "type": "customer.subscription.updated",
        "data": {"object": {"metadata": {"universe_id": "u-1"}, "status": status}},
    }
    assert subscription_state_from_event(event) == ("u-1", expected)


def test_deletion_always_returns_the_universe_to_free():
    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"universe_id": "u-1"}, "status": "active"}},
    }
    assert subscription_state_from_event(event) == ("u-1", "free")


def test_an_unrelated_event_moves_no_tier():
    """A payment on its own does not entitle — the subscription status decides."""
    assert subscription_state_from_event({"type": "invoice.paid", "data": {}}) is None


def test_an_event_without_a_universe_is_ignored():
    event = {
        "type": "customer.subscription.updated",
        "data": {"object": {"metadata": {}, "status": "active"}},
    }
    assert subscription_state_from_event(event) is None


# --- Codex REJECT 2026-08-28 follow-ups --------------------------------------


def test_a_stripe_error_message_is_not_returned_to_the_caller(monkeypatch):
    """Stripe quotes request params back, including customer identifiers."""
    import io
    import urllib.error

    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")

    body = (
        b'{"error":{"message":"No such customer: cus_SECRET123 for '
        b'subscription sub_PRIVATE456"}}'
    )

    def _raise(*a, **k):
        raise urllib.error.HTTPError(
            "https://api.stripe.com/v1/x", 400, "Bad Request", {}, io.BytesIO(body)
        )

    monkeypatch.setattr(stripe_adapter.urllib.request, "urlopen", _raise)

    with pytest.raises(stripe_adapter.BillingUnavailable) as caught:
        stripe_adapter._post("customers", [])

    message = str(caught.value)
    assert "cus_SECRET123" not in message
    assert "sub_PRIVATE456" not in message
    assert "400" in message


def test_checkout_refuses_a_second_subscription_for_one_universe(monkeypatch):
    """Two completed sessions would bill the same universe twice."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(
        stripe_adapter, "find_active_subscription", lambda _u: "sub_existing"
    )

    with pytest.raises(stripe_adapter.AlreadySubscribed) as caught:
        stripe_adapter.create_checkout_session(
            universe_id="u-1", success_url="https://x/ok", cancel_url="https://x/no"
        )
    assert caught.value.subscription_id == "sub_existing"


def test_finding_a_subscription_pages_past_the_first_hundred(monkeypatch):
    """Cancel searched only page one, so a later subscriber could not cancel."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    pages = [
        {"data": [{"id": f"sub_{i}", "metadata": {}} for i in range(100)],
         "has_more": True},
        {"data": [{"id": "sub_target", "metadata": {"universe_id": "u-1"}}],
         "has_more": False},
    ]
    calls = {"n": 0}

    def _get(_path, **_k):
        out = pages[min(calls["n"], len(pages) - 1)]
        calls["n"] += 1
        return out

    monkeypatch.setattr(stripe_adapter, "_get", _get)
    assert stripe_adapter.find_active_subscription("u-1") == "sub_target"
    assert calls["n"] == 2, "must have paged"


def test_exhausting_pagination_fails_loudly_instead_of_reporting_none(monkeypatch):
    """Returning None would read as 'no subscription' and refuse a real cancel."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(
        stripe_adapter,
        "_get",
        lambda *_a, **_k: {
            "data": [{"id": "sub_x", "metadata": {}}],
            "has_more": True,
        },
    )
    with pytest.raises(stripe_adapter.BillingUnavailable):
        stripe_adapter.find_active_subscription("u-1")


def test_checkout_sends_an_idempotency_key(monkeypatch):
    """A lost response must not turn a retry into a second subscription."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(stripe_adapter, "find_active_subscription", lambda _u: None)
    monkeypatch.setattr(stripe_adapter, "resolve_price_id", lambda: "price_x")

    seen = {}

    class _Resp:
        def read(self):
            return b'{"id":"cs_1","url":"https://checkout"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(request, timeout=None):
        seen["key"] = request.get_header("Idempotency-key")
        return _Resp()

    monkeypatch.setattr(stripe_adapter.urllib.request, "urlopen", _urlopen)
    stripe_adapter.create_checkout_session(
        universe_id="u-1", success_url="https://x/ok", cancel_url="https://x/no"
    )
    assert seen["key"], "no idempotency key sent"
    assert seen["key"].startswith("checkout:")


# --- subscription state (this branch's only durable state) -------------------


def test_a_stale_event_cannot_resurrect_a_cancelled_tier(tmp_path):
    """Stripe does not guarantee delivery order and retries deliveries."""
    from tinyassets.storage.subscription_state import apply_tier_event, get_tier

    assert apply_tier_event(tmp_path, tier="free", event_created=200.0) is True
    assert apply_tier_event(tmp_path, tier="paid", event_created=100.0) is False
    assert get_tier(tmp_path) == "free", "a stale event must not re-entitle"
    assert apply_tier_event(tmp_path, tier="paid", event_created=300.0) is True
    assert get_tier(tmp_path) == "paid"


def test_a_same_second_cancel_beats_a_same_second_activate(tmp_path):
    """Stripe timestamps are second-granularity, so ties are ordinary."""
    from tinyassets.storage.subscription_state import apply_tier_event, get_tier

    apply_tier_event(tmp_path, tier="free", event_created=500.0)
    assert apply_tier_event(tmp_path, tier="paid", event_created=500.0) is False
    assert get_tier(tmp_path) == "free"


def test_an_unreadable_state_db_reads_as_free_never_paid(tmp_path):
    """A database we cannot read must never silently grant the paid tier."""
    from tinyassets.storage.subscription_state import get_tier, state_db_path

    state_db_path(tmp_path).write_bytes(b"this is not a sqlite database")
    assert get_tier(tmp_path) == "free"


def test_two_concurrent_checkouts_cannot_both_start(tmp_path):
    import time

    from tinyassets.storage.subscription_state import (
        claim_checkout,
        release_checkout_claim,
    )

    now = time.time()
    assert claim_checkout(tmp_path, now=now) is True
    assert claim_checkout(tmp_path, now=now) is False
    release_checkout_claim(tmp_path)
    assert claim_checkout(tmp_path, now=now) is True


def test_an_abandoned_checkout_does_not_lock_the_universe_forever(tmp_path):
    import time

    from tinyassets.storage.subscription_state import claim_checkout

    now = time.time()
    assert claim_checkout(tmp_path, now=now, ttl_seconds=60) is True
    assert claim_checkout(tmp_path, now=now + 30, ttl_seconds=60) is False
    assert claim_checkout(tmp_path, now=now + 120, ttl_seconds=60) is True
