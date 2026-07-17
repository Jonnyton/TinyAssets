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

## Addendum (2026-07-16, Codex r16 REJECT rework): real adapter, not the fake

Codex r16 returned **REJECT**: the layer was built + tested against a *permissive
fake* GitHub client and did not work against the real one. The rework closes that
gap end-to-end. Root-cause fix first: a **shared contract** — the fake and the
live `HttpGitHubApi` implement the SAME `github_native.GitHubApi` read surface AND
the SAME `run_call` executor, and `tests/test_github_api_contract.py` runs the
SAME behavioural assertions against BOTH (the real client driven by a recorded
HTTP transport that exercises real request construction, pagination, id
resolution, and head binding). No production path may depend on behaviour only
the fake provides, and production wires the real client (`github_client_from_vault`
+ the daemon caller below).

Per-finding resolutions:

1. **Manual merge is durably queued + drained (was neither).** The chat verb now
   ENQUEUES a head-bound row on a `manual_merge_outbox`; a real daemon worker
   (`runs.execute_pending_manual_merges`) drains it with the credentialed client
   and confirms merged only after a GitHub re-read. **Live daemon caller:**
   `runs.run_review_recovery_for_universe` builds a per-destination client from
   the vault and is invoked each cycle from `fantasy_daemon.__main__._dispatcher_startup`.
2. **Server-side founder handle is a real vault lookup.** `permissions.current_github_handle`
   resolves the connected owner login from the per-universe credential vault
   (`credential_vault.resolve_github_login`, reading the GitHub `vcs` record's
   `account_login`), fail-closed to `""` when unconnected/ambiguous. No monkeypatch
   in its integration test.
3. **Crash reconciliation is owner-bound + real.** `HttpGitHubApi.list_pull_reviews`
   is implemented (paginated); `_review_already_on_github` now requires the
   reviewer `user_login` to equal the RESOLVED connected owner (an empty owner
   never reconciles) plus the commit + state — an attacker's approval at the same
   commit is rejected.
4. **Revocation resolves the EXACT review id (was `/reviews/0/`).** The dismiss
   worker resolves the owner's approval id via `list_pull_reviews` (owner login +
   reviewed head) before dismissing; no standing approval → the goal is already
   met (marked done). **Dismissal authority (chosen path):** the dismissal runs
   under the **owner USER token** (an authorized dismisser on a protected branch),
   NOT the App's minimal installation scope — so it can actually succeed without
   an `Administration` grant. `github_http.run_call` routes `dismiss_review` to
   `PURPOSE_USER_REVIEW`.
5. **Merge confirmation is head-bound.** `execute_manual_merge` refuses to confirm
   a merged PR whose live/post-merge head != the reviewed head (`head_replaced_merge`),
   and the idempotency receipt identity includes the head (`manual_merge:{pr}:{head}`),
   so head B merging can't ride head A's confirmation.
6. **Preference tightening is atomic.** `review_queue.tighten_merge_preference`
   commits the binding revision bump, the pending-timer cancellation, and the
   GitHub revocation enqueue in ONE transaction — a crash after rebinding can no
   longer leave already-enabled auto-merge without a durable revocation.

Bundle e2e: the integration test is split into a pre-runner REFUSAL case
(provider/runner absent → the sandbox-required nodes refuse at `investigate`,
fail-closed) and a runner-enabled continuation case (only exercised when a real
isolated executor is present). Production stays fail-closed.

## Addendum (2026-07-16, Codex r17 REJECT rework): platform-enforced gates

r17 rejected because each round exposed the next unbuilt layer — the real GitHub
App **auth lifecycle** was never built (static tokens, no refresh) and the merge
trusted local state. This round builds the non-credential gates; the credential
lifecycle (#2) is HELD to land as **vault-broker consumption**, not reinvented
token handling (a static-token/self-refresh path now would be a Rule-11 dual-path).

- **#1 Merge requires a CONFIRMED owner review ON GitHub.** `execute_manual_merge`
  now refuses (`owner_review_unconfirmed`) unless GitHub holds an APPROVED review
  by the connected owner at the exact reviewed head — read via `list_pull_reviews`,
  NEVER local `WORKFLOW_APPROVED`. So even an unprotected repo can't merge without
  a real owner approval. An **independent** durable `review_effect_outbox` (+
  `execute_pending_review_effects` worker) submits the owner's review with the
  owner USER token regardless of any run suspension — the enqueue happens in the
  approve/reshape/reject verbs.
- **#3 Autonomous is reachable in prod.** `run_review_recovery_for_universe` now
  builds a per-destination ruleset-read **VERIFIER** client
  (`verifier_client_from_vault`), resolves the App bypass-actor id
  (`resolve_github_app_actor_id`) + owner, and INVOKES `fire_due_not_before_timers`
  each cycle. `fire_due_not_before_timers` resolves the merge client, verifier,
  owner, and App-actor per destination; no verifier ⇒ the gate fails closed and
  the timer stays due.
- **#4 App-authored-PR invariant.** `get_pull` now carries `author_login` /
  `author_type`; the merge gate + the review-effect worker reject a PR authored by
  the connected owner (self-approval is impossible on GitHub) or a non-App human /
  PAT (`author_type != "Bot"`) — `pr_author_invalid` before any merge or doomed
  self-review.
- **#5 Idempotent schema migration.** `initialize_review_queue_db` runs
  `_apply_column_migrations` (ALTER-in the `revocation_outbox.expected_head_sha` /
  `founder_handle` columns) so a DB on the preceding schema upgrades forward
  instead of raising `OperationalError` on the first new-column insert.
- **#6 head-binding + parity.** Merge/reconcile require `head == expected_head`;
  the receipt id includes the head; the exact owner review id is resolved for
  dismissal. The 4 MCP dispatch/docstring parity failures were pre-existing
  UPSTREAM drift (gates conformance-pack actions in a parser-blind format, a stale
  hand-maintained `_wiki_dispatch_keys` mirror vs `wiki.WIKI_ACTIONS`, a
  glued-to-prose `cosign_bug`, an undocumented `goals.archive_consultation`) —
  fixed honestly (documented the real actions; the test now derives wiki keys from
  the authoritative dict).

**HELD for the vault freeze (#2):** the App ID / private-key / installation-id
record shape + installation-token and user-token refresh land as consumption of
the vault broker (`github_client_from_vault` / `verifier_client_from_vault` swap
their `StaticTokenProvider` for the refreshing broker provider). Until then the
Codex re-gate is HELD — the recovery workers already fail closed without live
credentials.
