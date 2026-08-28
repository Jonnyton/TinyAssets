Implemented directly in the owned files:

- Added service-generated entitlement claims and exact $20 USD monthly-plan validation.
- Checkout events no longer grant entitlement; authoritative subscription events do.
- Cancellation ignores foreign/unclaimed subscriptions.
- Billing requires both API and webhook secrets.
- Webhook bodies are bounded while streaming.
- Kept metering, quotas, enforcement, and Stripe SDK imports absent.
- Confirmed assumptions against Stripe’s [Checkout metadata](https://docs.stripe.com/api/checkout/sessions/create) and [Subscription object](https://docs.stripe.com/api/subscriptions/object) documentation.

Verified:

- Ruff: passed.
- Focused pytest: 76 passed.
- `git diff --check`: passed.
- No commit created.

I would now approve this surface for landing and deployment.

BUILDER-VERDICT: APPROVE
[exit 0]
