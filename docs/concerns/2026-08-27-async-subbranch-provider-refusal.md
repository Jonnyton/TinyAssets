# Async sub-branches are refused by the foreground provider session

**Filed:** 2026-08-27
**Severity:** P1 — live, user-facing, on code deployed today
**Shipped in:** PR #2559 (`41df0cf1`), deployed and serving

## The finding

`_ForegroundRunProviderSession.prepare()` opens with:

```python
if self._run_id:
    raise ProviderAuthorityHeldError(_HELD)
```

That guard is correct — one session must never serve two runs, because its
receipt and claim are minted against a single run id.

But `graph_compiler.py:2488` passes the **parent's already-prepared**
`provider_call` straight into `execute_branch_async` for an async sub-branch.
That reaches `prepare_foreground_run_provider` →
`_session_from_provider_call` returns the *same* session → `prepare()` →
`self._run_id` is already set → refusal. The child run is created directly as
FAILED before executing a single node.

Reproduced at the mechanism level: a session with `_run_id` set refuses a second
`prepare()` with `ProviderAuthorityHeldError`. **Not** reproduced end to end —
that needs real storage, universe, branch and run rows, and is the next step.

## Why it shipped

**No test exercises an async sub-branch through a provider session.** Every test
touching `execute_branch_async` was checked; none constructs a
`foreground_run_provider` session. The path has zero coverage.

**And no receipt was required.** `pr-scope-guard`'s `AUTHORITY_RE` listed only
`tinyassets/auth/`, `credential_vault.py`, and four `api/*.py` files. #2559
changed `foreground_run_provider.py`, `provider_work_authority.py` and
`providers/router.py` — none matched — so auto-merge took it once checks passed.
The cross-family review completed *after* the merge and deploy.

The regex is widened in the same change that files this. That closes the gate
for next time; it does not fix this.

## The fix, when someone takes it

A child run needs its **own** session, not the parent's. Relaxing the guard
would be wrong — mint a second session instead, inheriting only the constructor
inputs (base path, universe, principal, the underlying provider callable) and
never the parent's receipt, claim, or branch snapshot, so the child admits on
its own authority against its own run row.

`prepare_foreground_run_provider` is the right place: it already resolves the
session from the wrapper. The wrapper is a `UniverseBoundProviderCall`, so a
child wrapper needs the parent's `universe_context` and `operation`.

**Write the failing end-to-end test first.** An untested path is what produced
this, and a hand-applied fix to live authority code without one would repeat the
mistake at higher stakes.

## The other findings from the same review

Also unfixed, same PR, all rated Medium or Low and all now live:

- **`max_invocations` counts prompt-bearing node DEFINITIONS, not attempts**
  (`foreground_run_provider.py:195,302`). A loop executing one prompt four times
  gets one invocation; attempt two fails despite valid authority.
- **The explicit-mock bypass precedes admission and is selected by a mutable
  `__module__` string** (`:517`). A wrapper, decorator, or module move can
  silently convert a production call into an unreceipted provider path.
- **`_receipt` is published before `_claim`** while the unlocked fast path checks
  only `_receipt` (`:342,350,411`). Concurrent first calls can observe
  receipt-without-claim and spuriously fail. Reproduced deterministically by the
  reviewer; fails closed.
- **Broad exception wrapping masks** cancellation, author mismatch, unsupported
  role, policy widening and budget exhaustion as "Connect your provider"
  (`:159,345`), so callers cannot distinguish actionable denials.

## What the review cleared

Worth recording, because these were the questions worth asking:

- Snapshot pinning at `prepare()` is **safe**. Run status/cancellation, founder
  home, assignment, parent-binding revocation and custody are all re-read at
  admission or on every provider attempt, so pinning hides no revocation.
- Provider-free runs intentionally skip provider-only checks; `prepare()` still
  captures the digest and validates the run row.
- All eight canonical/plugin mirror pairs are byte-identical.
- Inventory closure is genuine: 49 expected, 49 observed, no duplicates and no
  bare `stream` entries.
