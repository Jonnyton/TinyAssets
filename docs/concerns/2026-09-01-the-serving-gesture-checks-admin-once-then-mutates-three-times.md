# The serving gesture checks admin once, then mutates three times

**Filed:** 2026-09-01, from Codex's review of #2760 (S1). Pre-existing since
the phone connect flow landed 2026-08-21; #2760 widened its use, so it is
recorded rather than left implicit.
**Severity:** P2 — a narrow revocation race on an authority path.

## The finding

`tinyassets/onboarding/serving.py` `ensure_founder_serving` re-checks the
caller's CURRENT admin ACL once (`_require_current_admin`), then performs
three mutations: create or reset the platform binding, `bind_serving_provider`,
`set_serving`. The lower layers verify the binding's creator and credential
custody, not the caller's current ACL. So an admin row revoked between the
check and the mutations still lets the principal create, re-point and enable
serving.

This is the "verify the binding in the destructive step" class: the check has
to live inside the mutation's own admission, not before it.

## Why it is not fixed in #2760

The fix belongs in `provider_serving_binding.py` (the ACL check inside the
serving admission lock), which is an authority path under the exact-head
receipt rule. #2760 composes the existing helper without touching it.

## Also from the same review, not a defect

Two first-time gestures could race (`_platform_binding` is check-then-create,
`agent_bindings` has no uniqueness constraint) and leave two bindings with
nothing serving. #2760 serializes the gesture per universe inside the daemon
process, with a deterministic two-thread test. A cross-process caller would
not be covered; none exists today.
