# What account deletion still does not do, after three review rounds

**Filed:** 2026-09-02, at the `AGENTS.md` three-round cap on PR #2774.
**Verified:** yes — every item below is a Codex round-3 finding I read, reproduced
or accepted, and then chose not to fix. Rounds:
`output/codex-review-2773.md` (9 findings), `output/codex-review-2773-r2.md`
(P0 + 6 P1), `output/codex-review-2774-r3.md` (7 P1 + 1 P2).
**Severity:** P2 — the shipped path deletes the user's data, refuses rather than
touching anyone else's, and reports honestly when a step does not finish. What
remains is durability and completeness at the margins, on a product with one
real user.

## Fixed across the three rounds

Account deletion exists in-app and at `/account`; the row set is derived from the
live schema instead of a list; `created_by` is not a deletion key; foreign data
and live work refuse the deletion; every store at the data root is swept, blobs
included; the fence is written before staging and keyed by a digest; every
targeted table is counted before anything is deleted; audit rows are redacted;
non-terminal billing and identity outcomes are unfinished work with a durable
receipt; the Android shell cannot reach checkout; and the public copy matches
what the code does.

## What is left, and why I stopped

1. **No automatic retry, and no resumable journal.** Round 2 asked for one;
   round 3 restated it. Today an unfinished phase writes a content-free receipt
   under `.account-deletions/` and the app tells the user, but nothing retries.
   If Stripe is unreachable at exactly the wrong moment, a subscription keeps
   charging until a host reads the receipt. `pending_deletions()` lists them and
   `docs/host-actions.md` says to check. **A retry worker is the real fix.**
2. **No global deletion fence over writers.** The tombstone stops first contact
   re-founding the account, and it is now written before anything is staged, but
   a token already issued stays valid at this daemon until it expires, and a
   writer that never calls first contact is not checked. Closing it properly
   means a fence consulted by the auth path, plus draining in-flight work under
   the maintenance barrier — which is the shape `scoped_reset` uses offline and
   cannot be taken while the service holds its shared lease.
3. **Ownership is refused, not anonymised.** Where another person's rows sit in
   the universe, deletion blocks instead of detaching them. That is right for a
   platform whose one invariant is not touching another user's data, and it is
   unreachable for a normal single user, but it means an edge case ends at
   `legal@tinyassets.io` rather than in the app. GDPR-style erasure would prefer
   anonymising the deleted person's attribution in rows that are legitimately
   retained; we redact `action_records` and nothing else.
4. **Blockers are not literally the operator path's function.** They reuse its
   queries and its state constants, not `_inspect_database` itself, because that
   function's dependent-row rule is deliberately different for a reset. Round 3
   is right that they can drift. A shared, parameterised analysis in
   `scoped_reset` would fix it and is the natural next change.
5. **"Not shared" in the Play data-safety form rests on unverified contracts.**
   The runbook now records which exclusion each recipient relies on, but nobody
   has confirmed the WorkOS, Stripe and hosting data-processing terms are in
   force for this account. That is a founder check before submission, listed in
   `docs/ops/google-play-launch.md` §6.

## Why not a fourth round

`AGENTS.md`: three rounds, then escalate — the published evidence is that defect
counts across repeated audit rounds are non-monotonic, and that fixing round N's
findings creates round N+1's. This lane matches the pattern: round 2's P0 was
introduced by round 1's fix, and round 3's findings are mostly about code round 2
introduced. Items 1 and 2 are each a real change with their own design, not a
patch to this one, so they belong in their own lane with their own review.
