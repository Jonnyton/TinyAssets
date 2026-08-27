# Four unfixed authority gaps in the foreground run provider

**Filed:** 2026-08-27
**Re-verified:** 2026-08-27 against `814b4f06` — all four still present; every
line number in the source below had rotted and is corrected under
*Re-verification*, per this directory's convention.
**Severity:** P2 — all live, none is a refusal-to-run.

This file was filed as *"Async sub-branches are refused by the foreground
provider session"*. **That P1 is fixed and deployed** — PR #2586, merge
`44c4e205`, which is the sha `scripts/deployed_sha.py --assert-contains`
reports production serving. `prepare_foreground_run_provider` now mints a
sibling session when the wrapper's session is bound to a different run, built
from `constructor_inputs()` only and inheriting no receipt or claim; the guard
that stops one session serving two runs is untouched.

The file is narrowed to the rest of that review, which was never fixed. It is
open because these four are individually live, not because the P1 is.

## Source (verbatim)

The four findings as originally recorded, unedited — line numbers included, and
wrong now. See *Re-verification*.

> Also unfixed, same PR, all rated Medium or Low and all now live:
>
> - **`max_invocations` counts prompt-bearing node DEFINITIONS, not attempts**
>   (`foreground_run_provider.py:195,302`). A loop executing one prompt four times
>   gets one invocation; attempt two fails despite valid authority.
> - **The explicit-mock bypass precedes admission and is selected by a mutable
>   `__module__` string** (`:517`). A wrapper, decorator, or module move can
>   silently convert a production call into an unreceipted provider path.
> - **`_receipt` is published before `_claim`** while the unlocked fast path checks
>   only `_receipt` (`:342,350,411`). Concurrent first calls can observe
>   receipt-without-claim and spuriously fail. Reproduced deterministically by the
>   reviewer; fails closed.
> - **Broad exception wrapping masks** cancellation, author mismatch, unsupported
>   role, policy widening and budget exhaustion as "Connect your provider"
>   (`:159,345`), so callers cannot distinguish actionable denials.

## Re-verification — 2026-08-27, `814b4f06`

The premises all hold. Only the citations moved; `foreground_run_provider.py`
grew by the #2586 sibling-session fix.

| Finding | Was | Now | Evidence at the new line |
|---|---|---|---|
| `max_invocations` counts definitions | `:195,302` | **`:321`** | `max_invocations=len(nodes)` |
| Mock bypass keyed on `__module__` | `:517` | **`:536`** | `getattr(self._provider_call, "__module__", "") != "tinyassets.providers.call"` |
| Receipt before claim | `:342,350,411` | **`:362-363`**, fast path **`:369-370`** | `self._receipt = receipt` then `self._claim = claim`; `_ensure_admitted` returns on `_receipt is not None` *before* taking the lock |
| Denials masked | `:159,345` | **`:365-367`**, message at **`:30`** | `except Exception as exc: raise ProviderAuthorityHeldError(_HELD) from exc` |

Two notes the re-check adds:

- **Receipt-before-claim survived the #2586 edit.** The two assignments are now
  adjacent, which reads as fixed and is not: adjacency is not atomicity, and
  `_ensure_admitted`'s early return still tests only `_receipt`, outside the
  lock. This is the one most likely to be waved off as already handled.
- **Finding 4 lands on the user, not just on callers.** Every masked cause
  surfaces as *"Connect your provider before running this universe"*, so a user
  who has connected one is told to do the thing they already did. Related:
  [[exceptions-carry-more-than-their-message]].

## Why they shipped, which is the part worth keeping

**No test exercised an async sub-branch through a provider session** — every
test touching `execute_branch_async` was checked and none constructed a
`foreground_run_provider` session. **And no receipt was required:**
`pr-scope-guard`'s `AUTHORITY_RE` listed only `tinyassets/auth/`,
`credential_vault.py` and four `api/*.py` files, so a PR changing
`foreground_run_provider.py`, `provider_work_authority.py` and
`providers/router.py` matched nothing, and auto-merge took it once checks
passed. The cross-family review completed *after* the merge and deploy.

The regex was widened in the change that first filed this. That closes the gate
for the next one; it did not fix these four.

## What the same review positively cleared

Recorded because they were the right questions, and re-asking them is waste:

- Snapshot pinning at `prepare()` is **safe**. Run status/cancellation, founder
  home, assignment, parent-binding revocation and custody are all re-read at
  admission or on every provider attempt, so pinning hides no revocation.
- Provider-free runs intentionally skip provider-only checks; `prepare()` still
  captures the digest and validates the run row.
- All eight canonical/plugin mirror pairs are byte-identical.
- Inventory closure is genuine: 49 expected, 49 observed, no duplicates, no
  bare `stream` entries.

## Resolving this file

Fix all four and delete it. Fixing a subset means editing this file down rather
than annotating it.
