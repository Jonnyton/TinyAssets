# P0 - Public-site privacy, dependencies, and CI secret exposure

**Filed:** 2026-07-27 | **Verified:** 2026-07-27 | **Severity:** P0

> Migrated verbatim from `STATUS.md` on 2026-08-25 when the board was retired.
> Source dates preserved. Premise re-verified against `origin/main` @ `8cbf9769`.

## Source (verbatim)

Public-site privacy/deps/CI: private/operator reads; React 1C/1H, Svelte 7H, design 2H; same-repo
PRs can request 19 secrets.

## Reading

Three distinct problems filed as one row:

1. **Privacy** - the public site performs private/operator reads.
2. **Dependencies** - React 1 critical / 1 high, Svelte 7 high, design 2 high.
3. **CI** - a same-repo pull request can request **19 secrets**. This is the sharpest of the three:
   any contributor able to open a same-repo PR reaches the secret set.

## Note on scope

Item 3 overlaps the merge-attribution and `pr-scope-guard` work. `scripts/drain_review_gate.py`
(kept in the 2026-08-25 harness reset) enforces exact-head review receipts on sensitive-file PRs
including `.github/workflows/`, which narrows but does not close the secret-request surface.
