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
