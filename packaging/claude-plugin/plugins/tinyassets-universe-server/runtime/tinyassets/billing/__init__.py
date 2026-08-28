"""Billing adapter boundary.

Everything Stripe-shaped lives under this package and nowhere else. This slice owns
only a flat subscription and cancellation path; usage metering, quotas, and
enforcement are deliberately absent. Two consequences are deliberate:

* Stripe being absent or unreachable cannot accidentally grant paid entitlement.
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
