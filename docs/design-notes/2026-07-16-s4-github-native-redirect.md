# S4 redirect: GitHub-authoritative owner review/merge

**Date:** 2026-07-16
**Status:** Host-approved build authority (Phase 1 lands the shape; GitHub calls
are Phase-2 execution).
**Supersedes:** the TinyAssets-authoritative S4 review-queue design (local
approval tokens, policy-generation signatures, merge-claim leases, and the
`_github_required_checks_passed` branch-protection reconstruction).

## Finding source and verification

- **Finding (Codex research):** the prior-art report
  [`docs/research/2026-07-16-github-native-review-merge-prior-art.md`](../research/2026-07-16-github-native-review-merge-prior-art.md)
  §1 concludes that S4 was building a second, partially-synchronized PR
  transaction system beside GitHub's — which is why review after review kept
  finding races. GitHub already owns the PR head, reviews, rulesets, checks,
  mergeability, and the atomic merge operation.
- **Claude-family verification:** approve. The GitHub-native mapping is sound and
  every primitive cited (PR reviews API with `event=APPROVE`+`commit_id`, App as
  PR author so the owner cannot self-approve, `CODEOWNERS * @owner` + a
  required-code-owner-review ruleset with stale-approval dismissal and
  latest-push approval, merge API with expected head SHA, GraphQL
  `enablePullRequestAutoMerge`) is real and documented.
  **One stale claim corrected:** the report's §2 flags the "unsafe Codex bypass
  fallback" as if it were live; that fallback is already attestation-gated on S3,
  so it is not an open S4 hole — noted so a future reader does not re-open it as
  a new finding.
- **Host decision (2026-07-16):** redirect S4 to GitHub-native /
  GitHub-authoritative. GitHub is the source of truth for review and merge state;
  TinyAssets is a chat projection + workflow coordinator.

## Design contract

GitHub is authoritative. TinyAssets keeps ONLY:

- Chat identity / session authorization.
- Job ↔ PR ↔ universe/run linkage.
- `reshape` durable resume (outbox + `draft_patch` resume identity).
- Merge **preference** as product config: `manual` | `auto` | `not_before`.
- ONE durable `not_before` timer scheduler.
- A reconciliation / projection cache of GitHub PR state.
- Workflow terminal outcomes + explanatory notes.

Execution model (Phase-2 wires real auth; Phase-1 lands the shape):

- The **platform** (GitHub App; PAT fallback) AUTHORS the patch PR, so the owner
  cannot self-approve.
- The owner's chat approval becomes a **real GitHub PR review**:
  `POST /pulls/{n}/reviews` with `event=APPROVE`, `commit_id=<head_sha>`,
  authenticated with the owner's GitHub App **user** access token (attributed to
  the owner).
- Repo gate = a ruleset requiring PR + code-owner review + stale-approval
  dismissal + latest-push approval, plus `CODEOWNERS * @owner` (protected).
- **Manual** merge = merge API with expected head SHA.
- **Auto** = GraphQL `enablePullRequestAutoMerge`.
- **Timer** = durable `not_before`; when it fires, enable auto-merge.
- A TinyAssets-side preference tightening **disables auto-merge** and, if renewed
  consent is required, dismisses/supersedes the prior review.

Setup verification **fails closed**: before treating a repo as review-gated,
verify the required-review ruleset is actually active, `CODEOWNERS` is present,
and the App is not a ruleset bypass actor. If any is absent, `auto`/`timer`
**REFUSE** with a structured error telling the owner exactly what to configure;
`manual` stays available with an explicit unprotected-repo warning. Merge success
is reported only after re-reading GitHub state (GitHub UI actions are legitimate
state changes).

## Keep

- `reshape` durable resume: the outbox row + the `draft_patch` resume identity
  (`universe_id` / `branch_def_id` / `run_id` / owner notes).
- S1's packet contract: the `review_queue` payload block stays advisory
  (`request_ref` + `verify_verdict`); trust identities come from the run context.
- The 45ba8cd0 salvage: consent universe_id isolation, the bundle-e2e contract,
  and the reshape honesty wording (which already matches this design).
- Owner-gating on the chat verbs; per-universe tenant isolation.

## Delete

- `merge_approvals` table + approval-token minting / expiry / consumption.
- `policy_generation` signatures and the monotonic binding `generation` CAS
  (the parked WIP items 1/2/6 at f13c69a8 — the races they fixed no longer
  exist once GitHub owns the transaction).
- Local `approved → merging → merged` authority, merge-claim leases,
  `merge_claimed_at`, `claim_for_merge` CAS, stale-claim recovery.
- `_github_required_checks_passed` (classic branch-protection reconstruction) —
  GitHub enforces its own aggregate rulesets atomically at merge. This also kills
  the `Administration: read` requirement; steady-state permissions reduce to
  `Contents: write` + `Pull requests: write`.
- `review_queue` as a state machine → reduced to a PR projection/binding keyed
  by PR number.

## Risks

- **Rules not installed.** Without a required-review rule, an API caller with
  `Contents: write` can merge. Mitigation: setup verification fails closed for
  `auto`/`timer`; `manual` warns explicitly.
- **CODEOWNERS coverage.** `CODEOWNERS` must cover every path and itself be
  protected; partial coverage leaves ungated paths.
- **Bypass actors.** The App must not be a ruleset bypass actor; verification
  checks this.
- **UI-side state changes.** GitHub UI edits are legitimate state changes;
  TinyAssets must reread GitHub state (webhook or immediate re-read) before
  reporting success.
- **Approval freshness.** GitHub does not expire an otherwise-valid approval
  after 24h. If freshness is a real product requirement, keep that ONE explicit
  constraint rather than the general token machinery. (Carried as an open
  product question, not built in Phase 1.)

## Phase boundary

Phase 1 (this slice) lands the SHAPE only: the projection store, the chat verbs
recording owner intent + the exact GitHub call each will make, the preference
config, the timer scaffold, and the setup-verification logic — all tested
against a faked GitHub API with no live network, and every response text honest
about the Phase-2 dependency. Phase 2 wires real GitHub App auth + live calls.

## Addendum (2026-07-16, Codex r13 host decision): manual default / autonomous opt-in

The fail-closed gate must read `bypass_actors`, which GitHub returns ONLY to a
ruleset-WRITE caller — but the App's steady-state scope is `Contents:write` +
`Pull requests:write` + `Metadata:read`, which can't see it. That made `auto` /
`not_before` always fail closed. Resolution (host-decided):

- **MANUAL merge is the default and needs no elevated read.** The owner reviews
  every PR and GitHub's native ruleset enforcement runs at merge — the owner is
  in the loop each time, so the platform never pre-reads `bypass_actors` for
  manual. Works with the minimal App scope.
- **AUTONOMOUS merge (`auto`/`not_before`) is an explicit OPT-IN** requiring a
  separate, narrowly-scoped **verifier identity** — the owner's ruleset-read
  token (`github_auth` purpose `ruleset_verify`; `github_http.verifier_client`)
  used ONLY for the gate read, never for merging. Without it, autonomous fails
  closed (`autonomous_requires_verifier`); manual stays available. The App's
  merge identity stays minimal — no `Administration` grant.

Also landed this round: the run-lifecycle state machine is now real, not a
status flip — the owner decision moves the suspension to a durable `decided`
(resume-pending) outbox state, a runtime consumer EXECUTES the directive (submit
the GitHub review + drive the merge path / re-enter draft_patch / terminal
reject) and only then completes the run + acks the suspension; idempotent startup
replay recovers a decision made just before a crash.
