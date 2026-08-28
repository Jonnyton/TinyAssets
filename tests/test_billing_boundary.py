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


def test_billing_is_off_without_webhook_authority(monkeypatch):
    """Do not take payment when the resulting entitlement cannot be authorized."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    assert billing_enabled() is False


def test_billing_is_enabled_only_with_both_secrets(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    assert billing_enabled() is True


def test_calls_fail_soft_rather_than_crashing_when_billing_is_off(monkeypatch):
    """A missing processor must be a clear refusal, never an unhandled error."""
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with pytest.raises(BillingUnavailable):
        create_checkout_session(
            universe_id="u-1",
            success_url="https://x/ok",
            cancel_url="https://x/no",
            attempt_anchor=1_700_000_000.5,
        )


# --- webhook verification ----------------------------------------------------

SECRET = "whsec_test_secret"
PRICE_ID = "price_tinyassets_monthly"


def _plan_price(*, price_id: str = PRICE_ID, **overrides):
    price = {
        "id": price_id,
        "lookup_key": "tinyassets_paid_monthly",
        "unit_amount": 2_000,
        "currency": "usd",
        "recurring": {
            "interval": "month",
            "interval_count": 1,
            "usage_type": "licensed",
        },
    }
    price.update(overrides)
    return price


def _subscription_object(
    *,
    universe_id: str = "u-1",
    status: str = "active",
    secret: str = SECRET,
    price: dict | None = None,
) -> dict:
    from tinyassets.billing.stripe_adapter import _entitlement_claim

    selected_price = price or _plan_price()
    return {
        "id": "sub_tinyassets",
        "status": status,
        "metadata": {
            "universe_id": universe_id,
            "tinyassets_entitlement_version": "1",
            "tinyassets_entitlement_claim": _entitlement_claim(
                universe_id, selected_price["id"], secret=secret
            ),
        },
        "items": {"data": [{"quantity": 1, "price": selected_price}]},
    }


def _subscription_event(
    status: str = "active", *, kind: str = "customer.subscription.updated", **kwargs
) -> dict:
    return {"type": kind, "data": {"object": _subscription_object(status=status, **kwargs)}}


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
    event = _subscription_event(status)
    assert subscription_state_from_event(event, secret=SECRET) == ("u-1", expected)


def test_deletion_always_returns_the_universe_to_free():
    event = _subscription_event("active", kind="customer.subscription.deleted")
    assert subscription_state_from_event(event, secret=SECRET) == ("u-1", "free")


def test_an_unrelated_event_moves_no_tier():
    """A payment on its own does not entitle — the subscription status decides."""
    assert subscription_state_from_event({"type": "invoice.paid", "data": {}}) is None


def test_an_event_without_a_universe_is_ignored():
    event = _subscription_event(universe_id="")
    assert subscription_state_from_event(event, secret=SECRET) is None


def test_an_authentic_but_unclaimed_subscription_cannot_move_a_tier():
    """Stripe provenance alone does not authorize arbitrary metadata as entitlement."""
    obj = _subscription_object()
    obj["metadata"].pop("tinyassets_entitlement_claim")
    event = {"type": "customer.subscription.updated", "data": {"object": obj}}
    assert subscription_state_from_event(event, secret=SECRET) is None


def test_an_entitlement_claim_cannot_be_moved_to_another_universe():
    obj = _subscription_object(universe_id="u-1")
    obj["metadata"]["universe_id"] = "u-2"
    event = {"type": "customer.subscription.updated", "data": {"object": obj}}
    assert subscription_state_from_event(event, secret=SECRET) is None


@pytest.mark.parametrize(
    "price",
    [
        _plan_price(lookup_key="some_other_plan"),
        _plan_price(unit_amount=1),
        _plan_price(currency="eur"),
        _plan_price(recurring={"interval": "year", "interval_count": 1}),
    ],
)
def test_a_claimed_subscription_for_the_wrong_plan_cannot_move_a_tier(price):
    event = _subscription_event(price=price)
    assert subscription_state_from_event(event, secret=SECRET) is None


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


def test_price_lookup_rejects_a_misconfigured_plan(monkeypatch):
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(
        stripe_adapter,
        "_get",
        lambda *_a, **_k: {"data": [_plan_price(unit_amount=1)]},
    )
    with pytest.raises(stripe_adapter.BillingUnavailable, match="not the \\$20"):
        stripe_adapter.resolve_price_id()


def test_checkout_refuses_a_second_subscription_for_one_universe(monkeypatch):
    """Two completed sessions would bill the same universe twice."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(
        stripe_adapter, "find_active_subscription", lambda _u: "sub_existing"
    )

    with pytest.raises(stripe_adapter.AlreadySubscribed) as caught:
        stripe_adapter.create_checkout_session(
            universe_id="u-1",
            success_url="https://x/ok",
            cancel_url="https://x/no",
            attempt_anchor=1_700_000_000.5,
        )
    assert caught.value.subscription_id == "sub_existing"


def test_finding_a_subscription_pages_past_the_first_hundred(monkeypatch):
    """Cancel searched only page one, so a later subscriber could not cancel."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    target = _subscription_object()
    target["id"] = "sub_target"
    pages = [
        {"data": [{"id": f"sub_{i}", "metadata": {}} for i in range(100)],
         "has_more": True},
        {"data": [target],
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


def _capture_checkout(monkeypatch, *, anchor: float, universe_id: str = "u-1"):
    """Run create_checkout_session against a stub Stripe and return what it sent."""
    import urllib.parse

    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(stripe_adapter, "find_active_subscription", lambda _u: None)
    monkeypatch.setattr(stripe_adapter, "resolve_price_id", lambda: "price_x")

    seen: dict = {}

    class _Resp:
        def read(self):
            return b'{"id":"cs_1","url":"https://checkout"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(request, timeout=None):
        seen["key"] = request.get_header("Idempotency-key")
        seen["params"] = dict(
            urllib.parse.parse_qsl(request.data.decode("utf-8"))
        )
        return _Resp()

    monkeypatch.setattr(stripe_adapter.urllib.request, "urlopen", _urlopen)
    stripe_adapter.create_checkout_session(
        universe_id=universe_id,
        success_url="https://x/ok",
        cancel_url="https://x/no",
        attempt_anchor=anchor,
    )
    return seen


def test_checkout_sends_an_idempotency_key(monkeypatch):
    """A lost response must not turn a retry into a second subscription."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
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
        seen["body"] = request.data.decode("utf-8")
        return _Resp()

    monkeypatch.setattr(stripe_adapter.urllib.request, "urlopen", _urlopen)
    stripe_adapter.create_checkout_session(
        universe_id="u-1",
            success_url="https://x/ok",
            cancel_url="https://x/no",
            attempt_anchor=1_700_000_000.5,
    )
    assert seen["key"], "no idempotency key sent"
    assert seen["key"].startswith("checkout:")
    assert "tinyassets_entitlement_version" in seen["body"]
    assert "tinyassets_entitlement_claim" in seen["body"]


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
    assert claim_checkout(tmp_path, now=now) == now
    assert claim_checkout(tmp_path, now=now) is None
    release_checkout_claim(tmp_path)
    assert claim_checkout(tmp_path, now=now) == now


def test_an_abandoned_checkout_does_not_lock_the_universe_forever(tmp_path):
    import time

    from tinyassets.storage.subscription_state import claim_checkout

    now = time.time()
    assert claim_checkout(tmp_path, now=now, ttl_seconds=60) == now
    assert claim_checkout(tmp_path, now=now + 30, ttl_seconds=60) is None
    assert claim_checkout(tmp_path, now=now + 120, ttl_seconds=60) == now + 120


# --- 2026-08-28 billing review follow-ups ------------------------------------


@pytest.mark.parametrize("payment_status", ["unpaid", "no_payment_required", ""])
def test_a_completed_session_does_not_entitle_until_it_is_paid(payment_status):
    """Stripe emits checkout.session.completed for unpaid sessions too."""
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "u-1",
                "mode": "subscription",
                "payment_status": payment_status,
            }
        },
    }
    assert subscription_state_from_event(event) is None


def test_a_paid_session_waits_for_the_authorized_subscription_event():
    """Expectation changed: payment proves money landed, not which plan we created."""
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "u-1",
                "mode": "subscription",
                "payment_status": "paid",
            }
        },
    }
    assert subscription_state_from_event(event, secret=SECRET) is None


@pytest.mark.parametrize("status", ["trialing", "past_due", "unpaid", "active"])
def test_cancel_finds_every_billable_status_not_only_active(monkeypatch, status):
    """trialing is treated as PAID, and past_due/unpaid still bill.

    Searching only status=active made cancel report "no subscription" while the
    customer kept being charged.
    """
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    subscription = _subscription_object(status=status)
    subscription["id"] = "sub_t"
    monkeypatch.setattr(
        stripe_adapter,
        "_get",
        lambda *_a, **_k: {
            "data": [subscription],
            "has_more": False,
        },
    )
    assert stripe_adapter.find_active_subscription("u-1") == "sub_t"


@pytest.mark.parametrize("status", ["canceled", "incomplete_expired"])
def test_a_terminal_subscription_is_not_offered_for_cancellation(monkeypatch, status):
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    subscription = _subscription_object(status=status)
    subscription["id"] = "sub_x"
    monkeypatch.setattr(
        stripe_adapter,
        "_get",
        lambda *_a, **_k: {
            "data": [subscription],
            "has_more": False,
        },
    )
    assert stripe_adapter.find_active_subscription("u-1") is None


def test_cancel_ignores_an_unclaimed_subscription(monkeypatch):
    """Cancellation uses the same service-created plan authority as entitlement."""
    from tinyassets.billing import stripe_adapter

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    subscription = _subscription_object()
    subscription["metadata"].pop("tinyassets_entitlement_claim")
    monkeypatch.setattr(
        stripe_adapter,
        "_get",
        lambda *_a, **_k: {"data": [subscription], "has_more": False},
    )
    assert stripe_adapter.find_active_subscription("u-1") is None


def test_webhook_refuses_a_declared_oversize_before_streaming(monkeypatch):
    import asyncio

    from tinyassets import onboarding

    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)

    class _Request:
        headers = {"content-length": "262145"}
        streamed = False

        async def stream(self):
            self.streamed = True
            yield b"should not be read"

    request = _Request()
    response = asyncio.run(onboarding._handle_billing_webhook(request))
    assert response.status_code == 413
    assert request.streamed is False


def test_webhook_bounds_an_undeclared_chunked_body(monkeypatch):
    import asyncio

    from tinyassets import onboarding

    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)

    class _Request:
        headers = {}

        async def stream(self):
            yield b"x" * 262_144
            yield b"y"

    response = asyncio.run(onboarding._handle_billing_webhook(_Request()))
    assert response.status_code == 413


def test_the_claim_outlives_the_session_it_guards():
    """The invariant the old constants only APPEARED to state.

    They asserted that two of our own numbers matched each other, which says nothing
    about how long Stripe keeps a session payable. Nothing sent `expires_at`, so
    Stripe applied its 24-hour default and the session outlived its guard by nearly a
    day. What has to hold is that the claim is the LONGER of the two.
    """
    from tinyassets.storage.subscription_state import (
        CHECKOUT_SESSION_SECONDS,
        CHECKOUT_WINDOW_SECONDS,
    )

    assert CHECKOUT_WINDOW_SECONDS > CHECKOUT_SESSION_SECONDS
    assert CHECKOUT_SESSION_SECONDS >= 1800, "Stripe rejects expires_at under 30 min"


def test_no_metering_machinery_is_exported():
    """Dead metering code implies a capability this branch does not have."""
    import tinyassets.billing as billing

    assert not hasattr(billing, "report_effect_usage")
    source = (
        REPO / "tinyassets" / "billing" / "stripe_adapter.py"
    ).read_text(encoding="utf-8")
    assert "meter_events" not in source


# --- 2026-08-28 live subscribe/cancel run: refusals reported as outages -------
#
# Found by driving the real webapp: subscribe worked, cancel worked, and then an
# immediate resubscribe told the user "Billing unavailable: tunnel origin returned
# 5xx". Two defects stacked -- the route answered a deliberate refusal with 503, and
# the claim guarding the finished checkout was still held.


@pytest.mark.parametrize(
    ("out", "expected"),
    [
        ({"url": "https://checkout.stripe.com/c/pay/cs_test_x"}, 200),
        ({"error": "already_subscribed"}, 409),
        ({"error": "checkout_already_in_progress"}, 409),
        ({"error": "no_home_universe"}, 409),
        ({"error": "billing_unavailable", "detail": "no key"}, 503),
    ],
)
def test_a_refusal_is_not_reported_as_a_service_outage(out, expected):
    """Only billing actually being unavailable may answer 5xx.

    This is not cosmetic. The Cloudflare Worker in front of production replaces the
    BODY of any origin 5xx with its own bad_gateway JSON, so a refusal sent as 503
    reaches the browser with our reason stripped out and the tunnel blamed.
    """
    from tinyassets.onboarding import _checkout_status

    assert _checkout_status(out) == expected


def test_an_unclassified_checkout_error_is_a_500_not_a_plausible_refusal():
    """An error string nobody classified is a bug here, and must read as one."""
    from tinyassets.onboarding import _checkout_status

    assert _checkout_status({"error": "something_new"}) == 500


def test_every_checkout_error_the_route_can_return_is_classified():
    """The table is only load-bearing if it actually covers the route.

    Greps the route body for the error strings it can return, so adding a new one
    without classifying it fails here instead of reaching a user as a 500.
    """
    from tinyassets.onboarding import _CHECKOUT_STATUS

    source = (REPO / "tinyassets" / "onboarding" / "__init__.py").read_text(
        encoding="utf-8"
    )
    body = source.split("async def _handle_billing_checkout")[1].split(
        "async def _handle_billing_cancel"
    )[0]
    returned = set(re.findall(r'"error":\s*"([a-z_]+)"', body))
    assert returned, "the grep found nothing - the anchor moved"
    assert returned <= set(_CHECKOUT_STATUS), (
        f"unclassified checkout errors: {sorted(returned - set(_CHECKOUT_STATUS))}"
    )


def test_the_user_facing_copy_covers_every_refusal_the_route_classifies():
    """A classified refusal with no message falls back to 'Billing unavailable'."""
    from tinyassets.onboarding import _CHECKOUT_STATUS

    page = (REPO / "tinyassets" / "onboarding" / "app.html").read_text(
        encoding="utf-8"
    )
    block = page.split("const CHECKOUT_REFUSALS = {")[1].split("};")[0]
    named = set(re.findall(r"^\s*([a-z_]+):", block, re.M))
    refusals = {k for k, v in _CHECKOUT_STATUS.items() if v < 500}
    assert refusals <= named, f"no message for: {sorted(refusals - named)}"


def test_a_resolved_checkout_releases_its_claim_immediately(tmp_path, monkeypatch):
    """The live lockout: subscribe, cancel, and resubscribe is refused for 15 min.

    The claim exists to stop two concurrent clicks becoming two subscriptions. A
    Stripe subscription event is Stripe telling us that checkout resolved, so the
    claim has done its job by then -- `AlreadySubscribed` guards afterwards.
    """
    import asyncio
    import json as _json

    import tinyassets.api.helpers as helpers
    from tinyassets import onboarding
    from tinyassets.storage.subscription_state import (
        claim_checkout,
        get_tier,
        state_db_path,
    )

    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)

    universe = "u-claim-release"
    universe_dir = tmp_path / universe
    universe_dir.mkdir()
    assert claim_checkout(universe_dir, now=time.time()) is not None
    assert claim_checkout(universe_dir, now=time.time()) is None, "claim is held"

    payload = _json.dumps(_subscription_event(universe_id=universe)).encode()
    timestamp = int(time.time())

    class _Request:
        headers = {
            "content-length": str(len(payload)),
            "stripe-signature": _sign(payload, timestamp),
        }

        async def stream(self):
            yield payload

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    response = asyncio.run(onboarding._handle_billing_webhook(_Request()))
    assert response.status_code == 200

    assert get_tier(universe_dir) == "paid", "the event must still move the tier"
    assert state_db_path(universe_dir).exists()
    assert claim_checkout(universe_dir, now=time.time()) is not None, (
        "a resolved checkout must not keep its claim to the TTL"
    )


# --- Codex round 1 on the fix above: the claim did not bound what it guarded --


def test_the_session_is_given_an_expiry_inside_its_claim(monkeypatch):
    """Sending no expires_at let Stripe apply its 24-HOUR default.

    The claim then expired 23h45m before the session it guarded stopped being
    payable, so a second session could be created alongside a still-completable
    first, and completing both billed one universe twice.
    """
    from tinyassets.storage.subscription_state import CHECKOUT_WINDOW_SECONDS

    anchor = 1_700_000_000.0
    sent = _capture_checkout(monkeypatch, anchor=anchor)

    expires_at = int(sent["params"]["expires_at"])
    assert expires_at > anchor, "an expiry in the past would be rejected"
    assert expires_at - anchor >= 1800, "Stripe rejects expires_at under 30 minutes"
    assert expires_at - anchor < CHECKOUT_WINDOW_SECONDS, (
        "the session must stop being payable BEFORE its claim lapses"
    )


def test_the_idempotency_key_identifies_the_attempt_not_the_clock(monkeypatch):
    """A wall-clock bucket replayed a COMPLETED session on resubscribe.

    Stripe keeps idempotency results for ~24h, so subscribing, cancelling, and
    resubscribing inside one bucket returned the original finished session -- a dead
    checkout URL. Two different attempts must be two different requests.
    """
    first = _capture_checkout(monkeypatch, anchor=1_700_000_000.0)
    same = _capture_checkout(monkeypatch, anchor=1_700_000_000.0)
    later = _capture_checkout(monkeypatch, anchor=1_700_000_001.0)

    assert first["key"] == same["key"], "a retry of one attempt must deduplicate"
    assert first["key"] != later["key"], "a new attempt must not replay the old one"


def test_a_retry_of_one_attempt_sends_identical_parameters(monkeypatch):
    """Stripe errors on a reused idempotency key with changed parameters.

    Deriving expires_at from the clock rather than the anchor would make every retry
    a parameter mismatch -- the retry path the key exists for would be the one that
    breaks.
    """
    first = _capture_checkout(monkeypatch, anchor=1_700_000_000.0)
    retry = _capture_checkout(monkeypatch, anchor=1_700_000_000.0)

    assert first["params"] == retry["params"]


def test_a_stale_event_cannot_release_a_live_claim(tmp_path, monkeypatch):
    """A redelivered old event must not unlock a checkout pending right now.

    Driven THROUGH the webhook, not against apply_tier_event: the release decision
    lives in the route, so a test that never calls the route cannot catch it being
    made unconditional.
    """
    import asyncio
    import json as _json

    import tinyassets.api.helpers as helpers
    from tinyassets import onboarding
    from tinyassets.storage.subscription_state import apply_tier_event, claim_checkout

    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    universe = "u-stale"
    universe_dir = tmp_path / universe
    universe_dir.mkdir()
    # A newer cancellation has already been applied.
    assert apply_tier_event(universe_dir, tier="free", event_created=2_000.0) is True
    now = time.time()
    assert claim_checkout(universe_dir, now=now) is not None, "a checkout is pending"

    # An OLDER 'active' is now redelivered. It is stale, so it entitles nothing --
    # and it must not release the claim protecting the session pending right now.
    event = _subscription_event("active", universe_id=universe)
    event["created"] = 1_000
    payload = _json.dumps(event).encode()

    class _Request:
        headers = {
            "content-length": str(len(payload)),
            "stripe-signature": _sign(payload, int(now)),
        }

        async def stream(self):
            yield payload

    response = asyncio.run(onboarding._handle_billing_webhook(_Request()))
    assert response.status_code == 200
    assert claim_checkout(universe_dir, now=now) is None, "the live claim must survive"


def test_a_cancellation_does_not_release_a_pending_claim(tmp_path, monkeypatch):
    """Only an ENTITLING event means a checkout resolved.

    After a deletion there is no subscription left for AlreadySubscribed to refuse
    against, so the claim's TTL is the only thing preventing a second session.
    """
    import asyncio
    import json as _json

    import tinyassets.api.helpers as helpers
    from tinyassets import onboarding
    from tinyassets.storage.subscription_state import claim_checkout

    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

    universe = "u-pending"
    universe_dir = tmp_path / universe
    universe_dir.mkdir()
    now = time.time()
    assert claim_checkout(universe_dir, now=now) is not None

    event = _subscription_event(
        "active", kind="customer.subscription.deleted", universe_id=universe
    )
    event["created"] = int(now)
    payload = _json.dumps(event).encode()
    timestamp = int(now)

    class _Request:
        headers = {
            "content-length": str(len(payload)),
            "stripe-signature": _sign(payload, timestamp),
        }

        async def stream(self):
            yield payload

    assert asyncio.run(onboarding._handle_billing_webhook(_Request())).status_code == 200
    assert claim_checkout(universe_dir, now=now) is None, (
        "a cancellation must leave the claim guarding the pending session"
    )


# --- the return URLs we hand to Stripe ---------------------------------------


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({}, "https://tinyassets.io"),
        ({"origin": "https://tinyassets.io"}, "https://tinyassets.io"),
        ({"origin": "https://evil.example"}, "https://tinyassets.io"),
        ({"origin": "javascript:alert(1)"}, "https://tinyassets.io"),
        (
            {"origin": "https://local.test", "host": "local.test"},
            "https://local.test",
        ),
    ],
)
def test_checkout_return_urls_only_use_an_origin_we_serve(headers, expected):
    """These URLs leave our control the moment Stripe has them."""
    from tinyassets.onboarding import _checkout_return_origin

    class _Request:
        pass

    request = _Request()
    request.headers = headers
    assert _checkout_return_origin(request) == expected


def test_the_checkout_route_actually_applies_the_origin_allowlist(
    tmp_path, monkeypatch
):
    """Testing the helper alone passes while the route stops calling it.

    Mutation-checked: replacing the route's call with the old raw-header read leaves
    the helper's own test green, so this one drives the route and reads the URL that
    reached Stripe.
    """
    import asyncio

    import tinyassets.api.helpers as helpers
    from tinyassets import onboarding
    from tinyassets.billing import stripe_adapter

    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(onboarding, "_app_identity_required", lambda: None)
    monkeypatch.setattr(onboarding, "current_identity", lambda: None, raising=False)
    monkeypatch.setattr(onboarding, "_read_home", lambda _i: "u-origin")
    monkeypatch.setattr(helpers, "_universe_dir", lambda u: tmp_path / u)

    sent: dict = {}

    def _create(*, universe_id, success_url, cancel_url, attempt_anchor):
        sent["success"] = success_url
        sent["cancel"] = cancel_url
        return {"id": "cs_1", "url": "https://checkout.stripe.com/x"}

    monkeypatch.setattr(stripe_adapter, "create_checkout_session", _create)
    import tinyassets.billing as billing

    monkeypatch.setattr(billing, "create_checkout_session", _create)

    class _Request:
        headers = {"origin": "https://evil.example", "host": "tinyassets.io"}

    response = asyncio.run(onboarding._handle_billing_checkout(_Request()))
    assert response.status_code == 200
    assert sent["success"].startswith("https://tinyassets.io/"), sent
    assert "evil.example" not in sent["success"] + sent["cancel"]
