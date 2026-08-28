"""Stripe adapter — the only module that knows Stripe exists.

Deliberately stdlib-only. Adding the SDK would put a Stripe import one `pip install`
away from anywhere in the tree, and the boundary this package exists to hold is
easier to keep when there is nothing to accidentally import.

**Fail soft, always.** No key configured means billing is off — but metering keeps
running and limits keep enforcing, because the ledger is ours. A payment processor
being unreachable must never decide whether a universe may act.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

_log = logging.getLogger(__name__)

_API = "https://api.stripe.com/v1"

#: Referenced by lookup key and event name rather than raw ids, so the same code
#: works against test and live mode without an id-swap step.
PRICE_LOOKUP_KEY = "tinyassets_paid_monthly"
EFFECT_METER_EVENT = "tinyassets_effect"

_KEY_VAR = "STRIPE_SECRET_KEY"
_WEBHOOK_SECRET_VAR = "STRIPE_WEBHOOK_SECRET"

#: Stripe rejects a signature older than this; so do we, to stop replay.
_WEBHOOK_TOLERANCE_S = 300


def _basic_auth(key: str) -> str:
    """Stripe basic auth: the secret key as username, empty password."""
    return "Basic " + base64.b64encode(f"{key}:".encode()).decode("ascii")


class AlreadySubscribed(RuntimeError):
    """This universe already has an active subscription."""

    def __init__(self, subscription_id: str) -> None:
        super().__init__("universe already has an active subscription")
        self.subscription_id = subscription_id


class BillingUnavailable(RuntimeError):
    """Billing is not configured, or Stripe could not be reached."""


def _secret_key() -> str:
    return (os.environ.get(_KEY_VAR) or "").strip()


def billing_enabled() -> bool:
    """True when a key is configured. Everything still works when this is False."""
    return bool(_secret_key())


def _post(path: str, fields: list[tuple[str, str]], *, timeout: float = 20.0) -> dict:
    key = _secret_key()
    if not key:
        raise BillingUnavailable("no Stripe key configured")
    body = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"{_API}/{path.lstrip('/')}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Basic auth: key as username, empty password, per Stripe.
    request.add_unredirected_header("Authorization", _basic_auth(key))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do NOT surface Stripe's message. It can quote request parameters back,
        # and those include customer and subscription identifiers — an avoidable
        # disclosure surface once this string is returned to a browser
        # (Codex REJECT 2026-08-28 D). Log the detail, return only the class.
        try:
            detail = json.loads(exc.read().decode("utf-8"))["error"]["message"]
        except Exception:
            detail = ""
        _log.warning(
            "stripe rejected %s: HTTP %s %s", path, exc.code, detail or "(no message)"
        )
        raise BillingUnavailable(
            f"Stripe rejected the request (HTTP {exc.code})"
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BillingUnavailable(
            f"Stripe unreachable: {type(exc).__name__}"
        ) from None


def _get(path: str, *, timeout: float = 20.0) -> dict:
    key = _secret_key()
    if not key:
        raise BillingUnavailable("no Stripe key configured")
    request = urllib.request.Request(f"{_API}/{path.lstrip('/')}", method="GET")
    request.add_unredirected_header("Authorization", _basic_auth(key))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BillingUnavailable(f"Stripe rejected the request: HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BillingUnavailable(f"Stripe unreachable: {type(exc).__name__}") from None


def resolve_price_id() -> str:
    """Find the $20/month price by lookup key, so no raw id is hardcoded."""
    found = _get(f"prices?lookup_keys[]={PRICE_LOOKUP_KEY}&active=true&limit=1")
    prices = found.get("data") or []
    if not prices:
        raise BillingUnavailable(
            f"no active price with lookup key {PRICE_LOOKUP_KEY!r}"
        )
    return str(prices[0]["id"])


def create_checkout_session(
    *, universe_id: str, success_url: str, cancel_url: str
) -> dict[str, str]:
    """Start a subscription. Returns the hosted checkout URL for the user.

    ``universe_id`` rides on ``client_reference_id`` and on subscription metadata so
    the webhook can map the resulting subscription back to a universe without us
    keeping a side table that could drift.
    """
    if not universe_id:
        raise ValueError("universe_id is required")
    # Idempotency at the product level: without this, two completed sessions
    # create two live subscriptions for one universe and the user is billed
    # twice (Codex REJECT 2026-08-28 C).
    existing = find_active_subscription(universe_id)
    if existing:
        raise AlreadySubscribed(existing)
    session = _post(
        "checkout/sessions",
        [
            ("mode", "subscription"),
            ("line_items[0][price]", resolve_price_id()),
            ("line_items[0][quantity]", "1"),
            ("success_url", success_url),
            ("cancel_url", cancel_url),
            ("client_reference_id", universe_id),
            ("subscription_data[metadata][universe_id]", universe_id),
        ],
    )
    return {"id": str(session["id"]), "url": str(session["url"])}


def cancel_subscription(subscription_id: str, *, immediately: bool = False) -> dict:
    """Cancel a subscription.

    Defaults to cancelling at period end — the user paid for the period and should
    keep it. ``immediately`` is for tests and for an explicit "cancel now" request.
    """
    if not subscription_id:
        raise ValueError("subscription_id is required")
    if immediately:
        return _post(f"subscriptions/{subscription_id}/cancel", [])
    return _post(
        f"subscriptions/{subscription_id}", [("cancel_at_period_end", "true")]
    )


def find_active_subscription(universe_id: str) -> str | None:
    """The universe's active subscription id, or None. Used by the cancel path."""
    starting_after = ""
    for _page in range(20):  # bounded, but far past the single page it had
        path = "subscriptions?status=active&limit=100"
        if starting_after:
            path += f"&starting_after={starting_after}"
        found = _get(path)
        data = found.get("data") or []
        for sub in data:
            meta = sub.get("metadata") or {}
            if meta.get("universe_id") == universe_id:
                return str(sub["id"])
        if not found.get("has_more") or not data:
            return None
        starting_after = str(data[-1]["id"])
    return None


def report_effect_usage(*, stripe_customer_id: str, count: int) -> dict:
    """Report metered effects. Reads OUR ledger's number and sends it upward."""
    if count <= 0:
        return {"reported": 0}
    _post(
        "billing/meter_events",
        [
            ("event_name", EFFECT_METER_EVENT),
            ("payload[stripe_customer_id]", stripe_customer_id),
            ("payload[value]", str(count)),
        ],
    )
    return {"reported": count}


def verify_webhook_signature(
    payload: bytes, signature_header: str, *, now: float, secret: str = ""
) -> bool:
    """Verify Stripe's `Stripe-Signature`. Constant-time, with replay rejection.

    An unverified webhook must never be able to change a universe's tier — that
    would let anyone who can reach the endpoint grant themselves the paid tier.
    """
    key = (secret or os.environ.get(_WEBHOOK_SECRET_VAR) or "").strip()
    if not key or not signature_header:
        return False
    timestamp = ""
    signatures: list[str] = []
    for part in signature_header.split(","):
        name, _, value = part.strip().partition("=")
        if name == "t":
            timestamp = value
        elif name == "v1":
            signatures.append(value)
    if not timestamp or not signatures:
        return False
    try:
        age = now - float(timestamp)
    except ValueError:
        return False
    if age > _WEBHOOK_TOLERANCE_S or age < -_WEBHOOK_TOLERANCE_S:
        return False
    expected = hmac.new(
        key.encode("utf-8"),
        f"{timestamp}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


def subscription_state_from_event(event: dict) -> tuple[str, str] | None:
    """Map a Stripe event to ``(universe_id, tier)``, or None if irrelevant.

    Only subscription lifecycle events move a tier. Anything else — including a
    successful payment on its own — is ignored, because the subscription's own
    status is the single fact that decides entitlement.
    """
    kind = str(event.get("type") or "")
    obj = (event.get("data") or {}).get("object") or {}

    if kind == "checkout.session.completed":
        universe_id = str(obj.get("client_reference_id") or "")
        if universe_id and obj.get("mode") == "subscription":
            return universe_id, "paid"
        return None

    if kind.startswith("customer.subscription."):
        universe_id = str((obj.get("metadata") or {}).get("universe_id") or "")
        if not universe_id:
            return None
        status = str(obj.get("status") or "")
        # `active` and `trialing` entitle; everything else (canceled, unpaid,
        # past_due, incomplete_expired) returns the universe to free.
        tier = "paid" if status in ("active", "trialing") else "free"
        if kind == "customer.subscription.deleted":
            tier = "free"
        return universe_id, tier

    return None
