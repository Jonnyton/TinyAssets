# The checkout claim is a timestamp, not a lease on a session

**Severity:** P2 · **Filed:** 2026-08-28 (Codex rounds 1 and 2, reviewing #2610)
**Surface:** `tinyassets/storage/subscription_state.py`, `tinyassets/billing/stripe_adapter.py`

The claim guarding a checkout stores *when* it was taken and nothing else. It does not
know **which Stripe Checkout Session it is guarding**, and three separate defects all
reduce to that one gap. Codex recommended the same structural fix in two consecutive
review rounds; #2610 narrowed each symptom without closing the cause.

## What the missing correlation costs

**1. A lost response creates a second session.** If Stripe creates the session and the
response is lost in transit, the route treats it as `BillingUnavailable` and *releases the
claim*. The retry gets a new anchor, therefore a new idempotency key, therefore a second
session. The idempotency key only protects a retry that reuses the same anchor — and no
code path does. (#2610 removed the comment that wrongly claimed otherwise.)

**2. A delayed event for an old subscription releases a live claim.** #2610 gates the
release on `applied and tier == paid`, which closes the ordering case but not this one:

1. Subscription A's last locally applied event is at `t=100`.
2. Stripe generates an authorized paid update for A at `t=190`; delivery is delayed.
3. A is deleted at `t=200`; that webhook is also delayed.
4. Checkout B starts — `find_active_subscription` sees A as canceled and skips it. B has
   a live claim and an open session.
5. A's delayed `t=190` event arrives. Local state is still at `100`, so `apply_tier_event`
   returns True and the tier is paid.
6. `applied and paid` deletes **B's** claim.
7. Checkout C can now start alongside B's still-open session.

The entitlement claim signs universe and price, but carries no attempt or session
identity, so the webhook cannot tell that this event is not about B.

**3. Abandonment locks the user out for ~37 minutes.** The claim must outlive the session
it guards, so lengthening the session to close the double-billing hole lengthened the
lockout with it. A user who deliberately clicks Stripe's cancel link is told to wait.

## The fix, in one sentence

Persist the Checkout Session id with the claim and make it a **lease on that session**
rather than a bare timestamp. Then:

- A repeat click returns the existing open session's URL instead of a 409 — no lockout.
- An explicit "start over" calls Stripe's session-expire endpoint on **that** session,
  confirms it, and only then rotates the claim.
- The webhook releases by comparing the session/attempt identity it is holding, never
  `DELETE WHERE key = 'checkout_claim_at'`.
- A lost response is recoverable, because the anchor survives the failure.

Stripe exposes an explicit expire endpoint for exactly this; the current timestamp-only
state cannot target it.

## Why it is a separate change

It alters storage shape and touches money, which `AGENTS.md` names as spec-before-code.
It also needs the checkout route to hold a Stripe object id, which is the first piece of
Stripe-side state we would persist — a design decision, not a patch. #2610 was a bug fix
to landed code and is strictly better than what it replaced; this is the redesign that
makes the remaining races impossible rather than narrow.

---

## Design, as adapted after review round 3 (2026-08-28)

Codex reviewed the design and returned **DISAGREE_CONCERN**: directionally right, not
safe to build as written. This is round 3, so per `AGENTS.md` there is no round 4 — the
design is recorded here in adapted form and the residual risk is stated rather than
reviewed again.

**Confirmed correct.** Settling by exact stored `cs_…` id does close the wrong-claim
release. No extra HMAC is needed to *delete* an attempt: the signature establishes Stripe
provenance, `livemode` must match, exact id comparison establishes object identity, and
deletion grants no entitlement. Returning the stored URL for an open session is also
correct — Stripe documents `url` as present while the session is active, with no separate
single-use lifecycle.

**Four things the design was missing.**

1. **Persist the creation inputs, not just an anchor.** Stripe replays an idempotent
   request only for *identical parameters*, and ours are not attempt-stable: the return
   URLs come from the current request Origin, the price id is re-resolved per call, the
   entitlement claim is recomputed from the current key, and the Stripe mode can change
   under us. Store the normalized inputs themselves — price id, return URLs, requested
   expiry, metadata and claim version, Stripe mode and account — not a hash. A hash
   detects drift but cannot reconstruct the request.

2. **The webhook can arrive before we record the session id.** Stripe can deliver
   `checkout.session.completed` before `record_checkout_session` runs, and the handler
   would 200 with nothing to match. Close it by putting a versioned, authenticated
   attempt id in the *Checkout Session* metadata, so a terminal event can bind to an
   attempt that has no session id yet.

3. **Identity must not be a timestamp.** Use a random `attempt_id` with `created_at` as a
   separate field. Deriving both expiry and identity from one anchor is what makes a
   retry minutes later send an `expires_at` too close to now for Stripe to accept.

4. **Migrate the legacy claim, do not ignore it.** A fresh `checkout_claim_at` must keep
   blocking until its original expiry; once stale, delete it and create the new attempt
   atomically; a corrupt value fails closed. Do **not** convert a fresh legacy claim into
   a retryable attempt — its original inputs were never stored, so an identical replay
   cannot be guaranteed. A one-time remaining-TTL lockout beats a second live
   subscription.

**Defer start-over.** Returning the stored open URL already closes the lockout. An
explicit "start over" adds a fresh money race: Stripe refuses to expire a non-open
session, and `complete` does not mean funds settled, so beginning again there can produce
two subscriptions once async processing finishes. If built later it must branch on the
*retrieved* status — `expired` → settle and begin; `complete` → settle but do not begin;
`open` → retry expire; unknown → fail closed.

**Simplification worth taking.** Drop the three-state enum. One record: absent means no
attempt, present without a session id means starting, present with one means open.
`settled` contradicts deletion anyway.

**Not reachable without state.** Stripe offers no way to recover the session id after a
lost response except replaying the request, so this lease cannot be made stateless.

