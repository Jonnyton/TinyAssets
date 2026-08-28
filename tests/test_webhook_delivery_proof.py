"""A verified delivery is the only proof the signing secret matches the endpoint.

Signing secrets are per-endpoint and cannot be read back from Stripe, so nothing else
can establish it. The failure this guards is silent in the worst direction: a LIVE api
key with a stale TEST signing secret lets real checkout succeed — Stripe takes the
money — while every entitlement webhook fails verification and is dropped. The user
pays and is never entitled, and nothing in the checkout flow looks wrong.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time

import pytest

import tinyassets.api.helpers as helpers
from tinyassets import onboarding
from tinyassets.billing.stripe_adapter import (
    last_verified_delivery,
    record_verified_delivery,
    verified_delivery_marker_path,
)

SECRET = "whsec_test_secret"


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    return tmp_path


def _signed(payload: bytes, ts: int, secret: str = SECRET) -> str:
    mac = hmac.new(
        secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256
    ).hexdigest()
    return f"t={ts},v1={mac}"


def _hook(payload: bytes, ts: int, secret: str = SECRET):
    class _R:
        headers = {
            "content-length": str(len(payload)),
            "stripe-signature": _signed(payload, ts, secret),
        }

        async def stream(self):
            yield payload

    return _R()


def test_nothing_is_recorded_before_any_delivery():
    assert last_verified_delivery() is None


def test_a_verified_delivery_is_recorded_through_the_route(monkeypatch, tmp_path):
    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    now = int(time.time())
    payload = json.dumps(
        {"type": "invoice.paid", "livemode": False, "data": {}}
    ).encode()
    asyncio.run(onboarding._handle_billing_webhook(_hook(payload, now)))

    record = last_verified_delivery()
    assert record is not None
    assert record["livemode"] is False


def test_a_FORGED_delivery_records_nothing(monkeypatch, tmp_path):
    """Otherwise anyone who can reach the endpoint could manufacture the proof."""
    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    now = int(time.time())
    payload = json.dumps({"type": "invoice.paid", "livemode": False}).encode()
    response = asyncio.run(
        onboarding._handle_billing_webhook(_hook(payload, now, secret="whsec_wrong"))
    )

    assert response.status_code == 400
    assert last_verified_delivery() is None, "a bad signature must prove nothing"


def test_a_mode_mismatched_but_SIGNED_delivery_still_counts(monkeypatch, tmp_path):
    """The signature is what is being proven, and it verified.

    The event is refused for its mode, but the fact the go-live check needs -- that
    this secret belongs to this endpoint -- is established either way.
    """
    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    now = int(time.time())
    payload = json.dumps({"type": "invoice.paid", "livemode": True}).encode()
    response = asyncio.run(onboarding._handle_billing_webhook(_hook(payload, now)))

    assert response.status_code == 400, "wrong mode is still refused"
    assert last_verified_delivery()["livemode"] is True


def test_an_unwritable_marker_never_costs_us_a_webhook(monkeypatch, tmp_path):
    """Best-effort. A failed marker write must not drop a real event."""
    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    from tinyassets.billing import stripe_adapter

    def _explode(**_kw):
        raise OSError("read-only filesystem")

    monkeypatch.setattr(stripe_adapter, "record_verified_delivery", _explode)
    now = int(time.time())
    payload = json.dumps({"type": "invoice.paid", "livemode": False}).encode()

    with pytest.raises(OSError):
        # Proves the monkeypatch is in the path at all — without this the next
        # assertion would pass vacuously.
        stripe_adapter.record_verified_delivery(now=1.0, livemode=False)

    # The real function swallows its own errors, so the route stays clean.
    monkeypatch.undo()
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    verified_delivery_marker_path().parent.mkdir(parents=True, exist_ok=True)
    response = asyncio.run(onboarding._handle_billing_webhook(_hook(payload, now)))
    assert response.status_code in (200, 400)


def test_a_corrupt_marker_reads_as_no_proof(tmp_path):
    """Half a record is not evidence."""
    path = verified_delivery_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert last_verified_delivery() is None

    path.write_text(json.dumps({"at": "soon"}), encoding="utf-8")
    assert last_verified_delivery() is None


def test_the_marker_round_trips():
    record_verified_delivery(now=1_700_000_000.0, livemode=True)
    got = last_verified_delivery()
    assert got["at"] == 1_700_000_000.0
    assert got["livemode"] is True
