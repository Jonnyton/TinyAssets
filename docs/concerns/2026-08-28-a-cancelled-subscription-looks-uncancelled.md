# A cancelled subscription looks uncancelled on reload

**Severity:** P2 · **Found:** 2026-08-28, driving the live subscribe/cancel flow as a user
**Surface:** `/mcp/app/billing/status` + the plan chip in `tinyassets/onboarding/app.html`

## What happens

Cancelling works. At the moment of cancelling, the user is told the truth:

> Your subscription will end at the close of the current period. You keep the paid tier
> until then.

That message is transient. **Reload the page and every trace of it is gone.** The chip
reads `Paid plan`, exactly as it did before, and clicking it offers to cancel a
subscription that is already cancelled.

So a user who cancels, closes the tab, and comes back has no way to tell whether their
cancellation took. The available action is to cancel again — which is harmless (Stripe
treats it as idempotent) but reads as "the first one didn't work."

## Why

`_handle_billing_status` returns `{"tier", "billing_enabled", "enforced"}` and nothing
else. Tier is the correct model for *entitlement* — the user IS still paid until the
period ends — but it cannot express *"paid, and ending on the 27th"*, which is the state
they are actually in. `renderPlan` therefore has only two words available to it.

## Why the obvious fix is wrong

Calling `find_active_subscription` from the status route would put a Stripe round-trip on
every page load and every status poll. Status is polled; billing reads are not free and
Stripe being slow would then make the app feel slow.

## Suggested fix

The webhook already receives `customer.subscription.updated` carrying
`cancel_at_period_end` and `current_period_end`. Persist those two alongside the tier in
`subscription_state` — the same place, written by the same authority, with no extra
network call — and let the chip render `Paid · ends 27 Sep`. The cancel confirm should
then not offer to re-cancel an already-cancelled subscription.

This is a small increment on storage that already exists, not a new subsystem. It was
deliberately left out of the fix for the two *defects* found in the same run
(PR #2608) so that a bug fix and a behaviour addition would not land as one change.

## Reproduce

1. Subscribe through the webapp.
2. Cancel through the webapp; read the confirmation message.
3. Reload `/mcp/app`. The chip says `Paid plan`; nothing indicates a pending cancellation.
