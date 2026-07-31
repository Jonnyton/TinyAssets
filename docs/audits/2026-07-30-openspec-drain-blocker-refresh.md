# OpenSpec drain blocker refresh

Date: 2026-07-30 America/Los_Angeles  
Provider: `drain-20260730-171757-db5ee6`  
Base: `origin/main` at `29ec497d5a4add0e36e27a81ad1a588615a5fdd7`

## Scope

Recheck every blocked OpenSpec delivery row in `STATUS.md` against current
main, OpenSpec progress, named GitHub pull requests, and bounded registered
worktree evidence. Remove only dependency labels disproved by current
evidence. Do not infer that a landed contract, dark store, or partial recovery
satisfies a separately named runtime, deployment, review, host, or rendered
acceptance gate.

## Admission evidence

- Before promotion, exact `claim_check.py --provider
  drain-20260730-171757-db5ee6 --status-ref origin/main --json` reported
  `claimable=0`, `in_flight=0`, and `stale=0`.
- The global `scripts/worktree_status.py` diagnostic exceeded its required
  90-second cap. The audit continued only from this clean current-main
  worktree using the exact claim check, OpenSpec CLI, GitHub, the bounded
  `git worktree list --porcelain` registry, and provider-context feed.
- The recovery row was then claimed as
  `claimed:drain-20260730-171757-db5ee6` and committed before the broad audit.

## Current evidence

- `python scripts/openspec_flow.py audit` reported 34 active changes, 378
  completed tasks, 826 remaining tasks, no pre-existing delivery WIP, and no
  complete-but-unarchived change. All STATUS-linked finish-first changes remain
  incomplete.
- The closest finish-first changes remain materially incomplete:
  `test-identity-and-reset` 6/9, relay 28/33, branch access 31/41,
  build-forward 5/19, provider receipts 1/15, universe creation 11/32,
  retire legacy 2/27, public read 5/35, retire cheat 9/39, connector manifests
  18/49, PostgreSQL 7/43, secret custody 5/42, demand-side 0/49, and
  plan-gated targets 8/58.
- Background branch authority advanced from 1/77 in the earlier audit to 8/77.
  PRs #1965 and #1966 landed the dark store and its foldback, but transition
  PR #1968 is still an open draft. The background authority, receipt, and
  sibling-runtime dependencies therefore remain unsatisfied rather than stale.
- PR #1792 (production-load evidence) and PR #1819 (retirement snapshot) remain
  open drafts. Runtime-qualified references to landed #1753 and #1784 remain
  valid because their separately named runtime and handoff requirements remain.
- The bounded worktree registry and provider-context feed show current
  background-transition, requester, secret-custody, branch-access, relay, and
  other named lanes. Their existence is coordination evidence, not proof that
  their acceptance contracts landed.

## Row-by-row disposition

| STATUS rows | Disposition |
|---|---|
| Canonical absolute guarantees; branch/run/evaluation/adjacent/outcome authority | Keep: their named audits, helpers, sibling runtimes, and retirement gates remain incomplete. |
| Requester-host and connector requester activation | Keep: secret custody, host binding, daemon/desktop identity, and paid/distributed transport remain incomplete. |
| Cheat-loop retirement, production proof, and alarm sink | Keep: #1819, rendered/organic proof, live receipts, packaging, sync/archive, and retirement prerequisites remain. |
| Public-read completeness and manifest edge | Keep: remaining substrate, pagination/evidence, manifest, browser, and host gates remain; the manifest edge is still host-owned. |
| Runtime-fiction, hyperparameter science, and PLAN-gated targets | Keep: their named design/review/owner gates remain unsatisfied. |
| Provider constraints, receipts, credential custody, and universe integration | Keep: successor, authority, receipt, connector/host, reset/log, and release gates remain. |
| Wiki backfill and first-contact onboarding | Keep: canonical-store/owner and opposite-provider review gates remain. |
| Relay survivors, test identity, and build-forward | Keep: explicit unchecked tasks and live/host/design acceptance remain. |
| PostgreSQL, market delivery, and universe-root migration | Keep: open #1792, host infrastructure/approval, transactional, domain-owner, and data-loss review gates remain. |
| OpenAI submission hardening | Keep: the clean rendered ChatGPT proof is still absent. |
| Host-action, host-decision, and monitoring rows | Keep host-owned; they are not autonomous drain candidates. |

## Result

No dependency label is disproved by current evidence, so no existing STATUS
row is edited. This is a valid exhaustion result, not a claim that the
underlying delivery debt is complete. The only promoted recovery task is this
freshness audit itself; it changes coordination evidence, not product behavior,
OpenSpec task state, architecture, production state, or host gates.

## Verification

The acceptance probe failed before this artifact existed. After the edit it
must find this exact base SHA plus `claimable=0` and `stale=0`. The exact claim
check must report this provider as the sole owned in-flight row, with no other
claimable or stale row, and `git diff --check` must pass.
