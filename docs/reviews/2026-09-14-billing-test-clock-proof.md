# Test-only repair after native-picker CI

September14 2026. PR3843 CI34896562120 / required job104152476867 finished
FAILURE at21:35UTC: 17863passes,54skips,15failures,2collection errors; six new
failures all report an expired synthetic checkout in test_billing_boundary.py.
The other nine failures/two errors match the existing main baseline.

## Cause and scope

The test module captured time.time() during collection, twice. Its checkout
expiry was anchor+2100seconds, while production correctly requires at least
1800seconds remaining. Collection/pre-test delay exceeding300seconds makes
six unrelated assertions fail before reaching their subject.

At the prior reviewed dd343a9b and current main d895905e, test_billing_boundary.py
has identical blob fe5b8d8946635d12da2751683d77a21ed9d154eb; stripe_adapter.py
has identical blob ae4e041b040e5c68e0a2c907e502c4de2543b112. Neither is changed
by the native-picker implementation. This is a latent timing-sensitive test
fixture, not a reason to weaken production checkout expiry.

Repair: an explicit function-scoped checkout_anchor fixture initializes each
attempt when its test starts. All retries within that test retain the SAME
anchor, keeping existing idempotency/parameter equality assertions intact.
Add a negative case proving an actually aged attempt still raises the existing
BillingUnavailable refusal. No runtime, billing behavior, quarantine or gate
changes. Stripe requests remain stubbed; no live account or payment operations.

## Verification (local Windows, September14)

- Before: pytest collection hook aged the module anchor600seconds; exact six CI
  failure identities reproduced,100passed/6failed in3.04s.
- After: `python -m pytest -q tests/test_billing_boundary.py --tb=short`:
  107passed/0skipped in2.92s, including the real aged-attempt refusal.
- A separate collection hook advances the process-local time.time by600seconds
  after collection. The initial106-case correction passed all106 in2.86s;
  final107-case delayed-clock and Linux results are recorded on the PR before
  landing. This does not change the system clock.
- `python -m ruff check tests/test_billing_boundary.py` and `git diff --check` pass.
- Local Linux oracle initially unavailable because Docker Desktop was stopped;
  normal installed Docker Desktop start requested. No Linux pass inferred.

The previous Fable approval remains evidence for unchanged native-picker runtime,
not approval of this test correction. One narrowly scoped additional review was
requested from the owner; none dispatched without that approval. Auto-merge is
disabled until the updated head is reviewed and CI passes. No deployment claim.
