# Slice 3 CORE — cross-family review log (Codex)

Reviewer: Codex (opposite family). Read-only, adversarial.

## Round 1 (core, seams injected) → VERDICT: adapt

Codex ran standalone reproductions and found the CORE cannot yet claim its
invariants. Fix ALL before landing the core (they must land WITH or BEFORE the
record-wire; the core is not trustworthy as-is):

1. **CRITICAL — concurrent ticks double-post.** Two ticks both read `pending`, both
   call the adapter, both `mark_delivered`. The mark txn runs AFTER the side effect
   and its zero-row result is ignored. A crash between post and mark also duplicates.
   → Fix: CLAIM the entry atomically BEFORE posting (`pending → in_flight` under
   BEGIN IMMEDIATE; a 0-row claim means another tick owns it → skip). Give the
   adapter an explicit `action-result:{run_id}:{revision}` idempotency key as the
   crash-safety backstop.
2. **CRITICAL — summary can leak internal data.** `compose_summary` interpolates
   `failed_phase`/`terminal_phase`/`public_result_ref`/`result_url` unvalidated; a
   `failed_phase="node_internal_42 token=xoxb-…"` emitted the token. → Fix: sanitize
   — restrict to a strict safe pattern + length cap, or drop free-text phase and
   only emit a result ref matching an allowlist (URL / `PR #\d+`).
3. **CRITICAL — non-throwing transport failure silently "delivered".** An adapter
   returning `None` posted nothing yet was marked delivered. → Fix: validate the
   receipt; a falsy receipt = HOLD (not delivered), like an exception.
4. **Required — `cancelled`/`interrupted` stuck forever.** `_TERMINAL` = only
   completed/failed, so those terminal runs stay pending and re-count as
   `skipped_running` every tick. → Fix: treat all non-completed terminal statuses as
   "didn't finish" (honest, no success) and deliver once.
5. **Required — pagination starvation.** `list_pending` returns the oldest 200; 200
   older still-running entries hide a newer completed one forever. → Fix: cursor-page
   through ALL pending (created_at/rowid cursor), not just the first page.
6. **Required — content-free not enforced at the storage boundary.** No secret
   columns exist, but `app_binding_ref="xoxb-…"` persists verbatim. → Fix: cap field
   lengths + constrain to id-like values (defense-in-depth vs a caller bug).
7. **Required — tests self-confirming.** Add concurrency, cancellation, receipt-
   validation, pagination-starvation, and adversarial summary-safety cases.

STATUS: fixes NOT yet applied (Slice 2 is the landing priority this session; the
Slice 3 record-wire is a deferred cross-boundary change —
`docs/audits/2026-08-19-slice3-record-wiring-seam.md`). Apply these with the wire.

VERDICT (round 1): adapt: require run-and-terminal-revision adapter idempotency,
prevent concurrent claims, validate receipts and public summary fields, and handle
terminal-status and queue-starvation cases.
