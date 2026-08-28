"""Stripe adapter — the only module that knows Stripe exists.

Deliberately stdlib-only. Adding the SDK would put a Stripe import one `pip install`
away from anywhere in the tree, and the boundary this package exists to hold is
easier to keep when there is nothing to accidentally import.

**Fail closed around money.** Billing is off unless both Stripe API and webhook
secrets are configured. A payment processor being unreachable must never grant an
entitlement or turn a normal free universe into an application crash.
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

#: Referenced by lookup key rather than a raw id, so the same code works against
#: test and live mode without an id-swap step.
PRICE_LOOKUP_KEY = "tinyassets_paid_monthly"
PLAN_UNIT_AMOUNT = 2_000
PLAN_CURRENCY = "usd"
PLAN_INTERVAL = "month"

_KEY_VAR = "STRIPE_SECRET_KEY"
_WEBHOOK_SECRET_VAR = "STRIPE_WEBHOOK_SECRET"

_ENTITLEMENT_VERSION = "1"
_ENTITLEMENT_VERSION_KEY = "tinyassets_entitlement_version"
_ENTITLEMENT_CLAIM_KEY = "tinyassets_entitlement_claim"

#: Stripe rejects a signature older than this; so do we, to stop replay.
_WEBHOOK_TOLERANCE_S = 300

#: Re-exported from the storage module so there is exactly ONE definition of how
#: long a checkout stays completable. Two constants that "must agree" is a comment,
#: not an invariant -- and this pair silently did not agree with Stripe's actual
#: behaviour at all (see CHECKOUT_SESSION_SECONDS).
from tinyassets.storage.subscription_state import (  # noqa: E402
    CHECKOUT_SESSION_SECONDS,
)


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


def _webhook_secret(secret: str = "") -> str:
    return (secret or os.environ.get(_WEBHOOK_SECRET_VAR) or "").strip()


def billing_enabled() -> bool:
    """True only when checkout and authoritative webhook handling can both work."""
    return bool(_secret_key() and _webhook_secret())


def _price_matches_plan(price: object) -> bool:
    """Whether a Stripe Price is exactly the advertised $20 USD monthly plan."""
    if not isinstance(price, dict):
        return False
    recurring = price.get("recurring")
    return bool(
        price.get("lookup_key") == PRICE_LOOKUP_KEY
        and price.get("unit_amount") == PLAN_UNIT_AMOUNT
        and str(price.get("currency") or "").lower() == PLAN_CURRENCY
        and isinstance(recurring, dict)
        and recurring.get("interval") == PLAN_INTERVAL
        and recurring.get("interval_count") == 1
        and recurring.get("usage_type") in (None, "licensed")
    )


def _entitlement_claim(universe_id: str, price_id: str, *, secret: str = "") -> str:
    """Sign authority that only our checkout creator may attach to metadata."""
    key = _webhook_secret(secret)
    if not key:
        raise BillingUnavailable("no Stripe webhook secret configured")
    message = "\0".join(
        (_ENTITLEMENT_VERSION, universe_id, PRICE_LOOKUP_KEY, price_id)
    ).encode("utf-8")
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _authorized_subscription_universe(obj: object, *, secret: str = "") -> str:
    """Return the bound universe only for a service-created subscription plan."""
    if not isinstance(obj, dict):
        return ""
    metadata = obj.get("metadata")
    items = obj.get("items")
    if not isinstance(metadata, dict) or not isinstance(items, dict):
        return ""
    item_data = items.get("data")
    if not isinstance(item_data, list) or len(item_data) != 1:
        return ""
    item = item_data[0]
    if not isinstance(item, dict) or item.get("quantity") != 1:
        return ""
    price = item.get("price")
    if not _price_matches_plan(price):
        return ""
    universe_id = str(metadata.get("universe_id") or "")
    price_id = str(price.get("id") or "")
    claim = str(metadata.get(_ENTITLEMENT_CLAIM_KEY) or "")
    if (
        not universe_id
        or not price_id
        or metadata.get(_ENTITLEMENT_VERSION_KEY) != _ENTITLEMENT_VERSION
        or not claim
    ):
        return ""
    try:
        expected = _entitlement_claim(universe_id, price_id, secret=secret)
    except BillingUnavailable:
        return ""
    return universe_id if hmac.compare_digest(expected, claim) else ""


def _post(
    path: str,
    fields: list[tuple[str, str]],
    *,
    timeout: float = 20.0,
    idempotency_key: str = "",
) -> dict:
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
    if idempotency_key:
        # Stripe deduplicates on this for 24h. Without it, a response lost in
        # transit turns a retry into a SECOND object — for checkout that means a
        # second subscription billing one universe twice, and our own duplicate
        # check cannot see it because a pending session is not yet a subscription
        # (Codex round 3, 3).
        request.add_unredirected_header("Idempotency-Key", idempotency_key)
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
    price = prices[0]
    if not _price_matches_plan(price):
        raise BillingUnavailable(
            f"active price {PRICE_LOOKUP_KEY!r} is not the $20 USD monthly plan"
        )
    return str(price["id"])


def create_checkout_session(
    *,
    universe_id: str,
    success_url: str,
    cancel_url: str,
    attempt_anchor: float,
) -> dict[str, str]:
    """Start a subscription. Returns the hosted checkout URL for the user.

    ``universe_id`` rides on ``client_reference_id`` and on subscription metadata so
    the webhook can map the resulting subscription back to a universe without us
    keeping a side table that could drift.

    ``attempt_anchor`` is the checkout claim's timestamp, and it identifies this
    attempt. Both the session's expiry and its idempotency key derive from it, which
    is what makes "retry of the same attempt" and "a genuinely new attempt" different
    requests to Stripe. It must be the value ``claim_checkout`` returned -- deriving
    either from the wall clock instead re-created one of two bugs: a retry seconds
    later changed ``expires_at`` and so conflicted with its own idempotency key, and
    a resubscribe inside the same bucket replayed the original completed session.
    """
    if not universe_id:
        raise ValueError("universe_id is required")
    # Idempotency at the product level: without this, two completed sessions
    # create two live subscriptions for one universe and the user is billed
    # twice (Codex REJECT 2026-08-28 C).
    existing = find_active_subscription(universe_id)
    if existing:
        raise AlreadySubscribed(existing)
    if attempt_anchor <= 0:
        raise ValueError("attempt_anchor is required")
    price_id = resolve_price_id()
    claim = _entitlement_claim(universe_id, price_id)
    session = _post(
        "checkout/sessions",
        [
            ("mode", "subscription"),
            # Bound how long this session stays completable. Sending nothing let
            # Stripe apply its 24-HOUR default, so the session outlived the claim
            # guarding it by nearly a day: after the claim expired a second session
            # could be created while the first was still payable, and completing both
            # billed one universe twice (Codex, 2026-08-28). Derived from the attempt
            # anchor, not the clock, so a retry sends byte-identical parameters under
            # the same idempotency key.
            ("expires_at", str(int(attempt_anchor + CHECKOUT_SESSION_SECONDS))),
            ("line_items[0][price]", price_id),
            ("line_items[0][quantity]", "1"),
            ("success_url", success_url),
            ("cancel_url", cancel_url),
            ("client_reference_id", universe_id),
            ("subscription_data[metadata][universe_id]", universe_id),
            (
                f"subscription_data[metadata][{_ENTITLEMENT_VERSION_KEY}]",
                _ENTITLEMENT_VERSION,
            ),
            (
                f"subscription_data[metadata][{_ENTITLEMENT_CLAIM_KEY}]",
                claim,
            ),
        ],
        # Keyed on the ATTEMPT, so a retry after a lost response returns the same
        # session and a new attempt gets a new one. A wall-clock bucket did neither
        # reliably: resubscribing inside the same bucket replayed the original
        # COMPLETED session (Stripe keeps idempotency results ~24h), handing the user
        # a dead checkout URL, while two attempts straddling a boundary each got
        # their own still-completable session.
        idempotency_key=(
            "checkout:"
            + hashlib.sha256(
                f"{universe_id}:{attempt_anchor!r}".encode()
            ).hexdigest()
        ),
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
    if not _webhook_secret():
        raise BillingUnavailable("no Stripe webhook secret configured")
    starting_after = ""
    for _page in range(20):  # bounded, but far past the single page it had
        # `all`, not `active`. trialing is treated as PAID here, and past_due /
        # unpaid still bill — searching only `active` made cancel report "no
        # subscription" while billing continued (Codex 2026-08-28).
        path = "subscriptions?status=all&limit=100"
        if starting_after:
            path += f"&starting_after={starting_after}"
        found = _get(path)
        data = found.get("data") or []
        for sub in data:
            if _authorized_subscription_universe(sub) != universe_id:
                continue
            # Terminal states are not cancellable and must not mask a live one.
            if str(sub.get("status") or "") in ("canceled", "incomplete_expired"):
                continue
            return str(sub["id"])
        if not found.get("has_more") or not data:
            return None
        starting_after = str(data[-1]["id"])
    # Ran out of pages while Stripe still says there are more. Returning None here
    # would read as "no subscription" and silently refuse a legitimate cancel, so
    # fail loudly instead (Codex REJECT round 2 C).
    raise BillingUnavailable(
        "could not scan all active subscriptions; cancel not attempted"
    )




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


def subscription_state_from_event(
    event: dict, *, secret: str = ""
) -> tuple[str, str] | None:
    """Map a Stripe event to ``(universe_id, tier)``, or None if irrelevant.

    Only subscription lifecycle events move a tier. Anything else — including a
    successful payment on its own — is ignored, because the subscription's own
    status is the single fact that decides entitlement.
    """
    kind = str(event.get("type") or "")
    obj = (event.get("data") or {}).get("object") or {}

    # A Checkout Session does not carry the complete subscription item/price
    # authority needed here. Even a paid completion is therefore non-authoritative;
    # the service-claimed customer.subscription event decides entitlement.
    if kind == "checkout.session.completed":
        return None

    if kind.startswith("customer.subscription."):
        universe_id = _authorized_subscription_universe(obj, secret=secret)
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
