# A Stripe 4xx reads as our billing being down

**Severity:** P2 · **Found:** 2026-08-28 (Codex, reviewing the checkout-lifecycle fix)
**Surface:** `tinyassets/billing/stripe_adapter.py` — the `HTTPError` handler in `_post`

## What happens

Every `urllib.error.HTTPError` from Stripe becomes `BillingUnavailable`, regardless of
status. A 400 `invalid_request_error` (a wrong price id, a malformed parameter, an
idempotency key reused with different parameters) is indistinguishable from Stripe
actually being down.

That class then becomes a 503 at the route, and — until the concern in
`2026-08-28-worker-swallows-every-origin-5xx-body.md` is fixed — the edge Worker
overwrites even that with "tunnel origin returned 5xx". A configuration mistake we made
is reported to the user, and to whoever reads the logs, as infrastructure sickness three
layers from the truth.

## Why it is not simply a widening of the existing fix

The `HTTPError` handler is deliberately careful about one thing and should stay that way:
it does **not** surface Stripe's message, because Stripe quotes request parameters back
and those include customer and subscription identifiers (Codex REJECT 2026-08-28 D). The
fix is to split the *class*, not to start returning Stripe's prose:

- 4xx (except 429) → a distinct `BillingMisconfigured`, surfaced as a 500 — it is our bug,
  and it should page us rather than look like weather.
- 429 and 5xx → `BillingUnavailable`, which is what that class was always meant to mean.

The detail stays log-only in both cases.

## Why it was not fixed in the same change

The checkout-lifecycle PR is already load-bearing on money handling: session expiry,
claim TTL, idempotency identity, and the webhook release condition. Splitting an exception
class touches every Stripe call path, not just checkout, and deserves its own diff and its
own review round rather than riding along.
