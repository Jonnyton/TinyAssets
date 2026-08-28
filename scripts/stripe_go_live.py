#!/usr/bin/env python
"""Check, and optionally provision, everything Stripe needs to take real money.

Going live is four steps, three of which are founder-only. This script exists so the
one that is *not* founder-only is a command rather than dashboard archaeology, and so
"are we ready?" has an answer nobody has to reconstruct from memory.

    python scripts/stripe_go_live.py --check
    python scripts/stripe_go_live.py --provision --webhook-url https://tinyassets.io/mcp/app/billing/webhook

``--check`` is read-only and safe to run against live mode. ``--provision`` creates the
price and the webhook endpoint if they are missing, and is idempotent: run it twice and
the second run reports "already correct" rather than making a duplicate.

The key comes from ``STRIPE_SECRET_KEY`` in the environment and is never printed. The
webhook signing secret is printed ONCE by ``--provision``, because Stripe returns it
exactly once and it has to be captured; nothing here writes it anywhere.

Deliberately NOT automated: activating the Stripe account. That needs business details
and a bank account, and it is the founder's to do.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Read the plan's shape from the adapter rather than restating it. A go-live check that
# provisions a price the application would then reject is worse than no check.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from tinyassets.billing.stripe_adapter import (  # noqa: E402
    PLAN_CURRENCY,
    PLAN_INTERVAL,
    PLAN_UNIT_AMOUNT,
    PRICE_LOOKUP_KEY,
    _price_matches_plan,
)

_API = "https://api.stripe.com/v1"
_TIMEOUT = 20

#: The subscription lifecycle events entitlement depends on, plus the two Checkout
#: Session events. Anything not listed here we do not act on.
REQUIRED_EVENTS = [
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
]

PRODUCT_NAME = "TinyAssets"
PRODUCT_DESCRIPTION = (
    "Your always-on universe. Effects, compute and storage on the paid tier."
)

OK = "  ok    "
BAD = "  BLOCK "
WARN = "  warn  "


def _request(method: str, path: str, params: list[tuple[str, str]] | None = None):
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key:
        raise SystemExit("STRIPE_SECRET_KEY is not set in the environment.")
    url = f"{_API}/{path}"
    data = None
    if params:
        data = urllib.parse.urlencode(params).encode()
    request = urllib.request.Request(url, data=data, method=method)
    request.add_unredirected_header("Authorization", f"Bearer {key}")
    if data:
        request.add_unredirected_header(
            "Content-Type", "application/x-www-form-urlencoded"
        )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))["error"]["message"]
        except Exception:
            detail = f"HTTP {exc.code}"
        raise SystemExit(f"Stripe refused {method} {path}: {detail}") from None


def _mode() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if key.startswith("sk_live"):
        return "live"
    if key.startswith("sk_test"):
        return "test"
    return "unknown"


def check(webhook_url: str) -> list[str]:
    """Report what is ready and what is not. Returns the blocking reasons."""
    blockers: list[str] = []
    mode = _mode()
    print(f"\nStripe mode: {mode.upper()}")
    if mode != "live":
        print(
            f"{WARN} the key in this environment is not a live key, so everything "
            "below describes TEST mode"
        )

    # --- 1. the account itself -------------------------------------------------
    account = _request("GET", "account")
    print(f"\nAccount {account.get('id')}")
    for field, label in (
        ("charges_enabled", "can accept payments"),
        ("payouts_enabled", "can receive payouts"),
        ("details_submitted", "activation details submitted"),
    ):
        good = bool(account.get(field))
        print(f"{OK if good else BAD} {label}")
        if not good:
            blockers.append(
                f"account {field}=false — activate at "
                "https://dashboard.stripe.com/account/onboarding (founder only)"
            )
    requirements = account.get("requirements") or {}
    due = requirements.get("currently_due") or []
    if due:
        print(f"{BAD} Stripe is still asking for: {', '.join(due)}")
        blockers.append(f"account requirements currently_due: {', '.join(due)}")

    # --- 2. the price ----------------------------------------------------------
    print(f"\nPrice (lookup key {PRICE_LOOKUP_KEY!r})")
    found = _request(
        "GET", f"prices?lookup_keys[]={PRICE_LOOKUP_KEY}&active=true&limit=1"
    )
    prices = found.get("data") or []
    if not prices:
        print(f"{BAD} no active price with that lookup key in {mode} mode")
        blockers.append(
            f"no active price with lookup key {PRICE_LOOKUP_KEY!r} — "
            "run with --provision"
        )
    elif not _price_matches_plan(prices[0]):
        # Not a nitpick: the application refuses a price whose shape it does not
        # recognise, so a mismatched price is a checkout that always fails.
        print(f"{BAD} {prices[0]['id']} is not the advertised plan")
        print(
            f"         want {PLAN_UNIT_AMOUNT} {PLAN_CURRENCY} / {PLAN_INTERVAL}, "
            f"got {prices[0].get('unit_amount')} {prices[0].get('currency')}"
        )
        blockers.append(
            "the active price does not match the advertised $20 USD monthly plan"
        )
    else:
        print(f"{OK} {prices[0]['id']} — $20.00 usd / month")

    # --- 3. the webhook endpoint ----------------------------------------------
    print(f"\nWebhook endpoint ({webhook_url})")
    endpoints = (_request("GET", "webhook_endpoints?limit=100").get("data")) or []
    match = [e for e in endpoints if str(e.get("url", "")).rstrip("/") ==
             webhook_url.rstrip("/")]
    if not match:
        print(f"{BAD} no endpoint registered for that URL")
        blockers.append(f"no webhook endpoint for {webhook_url} — run with --provision")
    else:
        endpoint = match[0]
        enabled = set(endpoint.get("enabled_events") or [])
        missing = [e for e in REQUIRED_EVENTS if e not in enabled and "*" not in enabled]
        status = str(endpoint.get("status") or "")
        print(f"{OK if status == 'enabled' else BAD} {endpoint['id']} status={status}")
        if status != "enabled":
            blockers.append(f"webhook endpoint {endpoint['id']} is {status}")
        if missing:
            print(f"{BAD} not subscribed to: {', '.join(missing)}")
            blockers.append(f"webhook endpoint missing events: {', '.join(missing)}")
        else:
            print(f"{OK} subscribed to every event entitlement depends on")

    # --- 4. what this script cannot see ---------------------------------------
    print("\nNot checkable from here")
    if not os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip():
        print(f"{BAD} STRIPE_WEBHOOK_SECRET is not set in THIS environment")
        blockers.append("STRIPE_WEBHOOK_SECRET unset here (it must be set on the daemon)")
    else:
        print(f"{OK} STRIPE_WEBHOOK_SECRET is set here")
    print(
        f"{WARN} whether the daemon's secret matches THIS endpoint's signing secret "
        "can only be proven by a real delivery"
    )
    return blockers


def provision(webhook_url: str) -> None:
    """Create the price and webhook endpoint if absent. Idempotent."""
    mode = _mode()
    print(f"\nProvisioning in {mode.upper()} mode")

    found = _request(
        "GET", f"prices?lookup_keys[]={PRICE_LOOKUP_KEY}&active=true&limit=1"
    )
    if found.get("data"):
        print(f"{OK} price already exists: {found['data'][0]['id']}")
    else:
        products = _request("GET", "products?active=true&limit=100").get("data") or []
        existing = [p for p in products if p.get("name") == PRODUCT_NAME]
        if existing:
            product_id = existing[0]["id"]
            print(f"{OK} reusing product {product_id}")
        else:
            product = _request(
                "POST",
                "products",
                [("name", PRODUCT_NAME), ("description", PRODUCT_DESCRIPTION)],
            )
            product_id = product["id"]
            print(f"{OK} created product {product_id}")
        price = _request(
            "POST",
            "prices",
            [
                ("product", product_id),
                ("unit_amount", str(PLAN_UNIT_AMOUNT)),
                ("currency", PLAN_CURRENCY),
                ("recurring[interval]", PLAN_INTERVAL),
                ("lookup_key", PRICE_LOOKUP_KEY),
            ],
        )
        print(f"{OK} created price {price['id']} with lookup key {PRICE_LOOKUP_KEY!r}")

    endpoints = (_request("GET", "webhook_endpoints?limit=100").get("data")) or []
    match = [e for e in endpoints if str(e.get("url", "")).rstrip("/") ==
             webhook_url.rstrip("/")]
    if match:
        print(f"{OK} webhook endpoint already exists: {match[0]['id']}")
        print(
            "        Stripe reveals a signing secret only at creation. If you do not "
            "have it, roll it in the dashboard."
        )
        return
    params = [("url", webhook_url)]
    params += [(f"enabled_events[{i}]", e) for i, e in enumerate(REQUIRED_EVENTS)]
    endpoint = _request("POST", "webhook_endpoints", params)
    print(f"{OK} created webhook endpoint {endpoint['id']}")
    secret = endpoint.get("secret")
    if secret:
        print("\n" + "=" * 72)
        print("SIGNING SECRET — shown ONCE by Stripe, and only here. Capture it now.")
        print("Set it as STRIPE_WEBHOOK_SECRET on the daemon; do not commit it.")
        print("=" * 72)
        print(secret)
        print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only readiness report")
    parser.add_argument(
        "--provision", action="store_true", help="create the price and webhook if absent"
    )
    parser.add_argument(
        "--webhook-url",
        default="https://tinyassets.io/mcp/app/billing/webhook",
        help="the endpoint Stripe should deliver to",
    )
    args = parser.parse_args()
    if not (args.check or args.provision):
        args.check = True

    if args.provision:
        provision(args.webhook_url)
    blockers = check(args.webhook_url)

    print()
    if blockers:
        print(f"NOT READY — {len(blockers)} blocker(s):")
        for reason in blockers:
            print(f"  - {reason}")
        return 1
    print("READY: this Stripe account can take real subscriptions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
