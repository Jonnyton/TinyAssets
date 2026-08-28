"""Billing adapter boundary.

Everything Stripe-shaped lives under this package and nowhere else. Metering writes
to our own ledger unconditionally; this package reads that ledger and reports
upward. Two consequences that are deliberate:

* Enforcement never depends on a third party being reachable — if Stripe is down,
  usage is still metered and limits are still enforced.
* The processor stays swappable, because no caller outside here knows it exists.

`tests/test_billing_boundary.py` asserts that property rather than trusting it.
"""

from tinyassets.billing.stripe_adapter import (
    BillingUnavailable,
    billing_enabled,
    cancel_subscription,
    create_checkout_session,
    subscription_state_from_event,
)

__all__ = [
    "BillingUnavailable",
    "billing_enabled",
    "cancel_subscription",
    "create_checkout_session",
    "subscription_state_from_event",
]
