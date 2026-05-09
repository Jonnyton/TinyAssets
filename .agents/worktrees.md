# Worktree Inventory

Cross-provider append-only log of worktree create/remove events. Run
`python scripts/worktree_status.py` to see current local state.

GitHub alignment:

- A worktree is the local checkout for one Git branch.
- A branch folds back through a GitHub PR, normally draft while blocked or
  under review and ready only when verification gates pass.
- `STATUS.md` owns claims and file collision boundaries; GitHub owns branch,
  commit, PR, and merge history.
- A branch is not memory. `_PURPOSE.md`, this inventory, `STATUS.md`,
  idea files, and draft PR bodies are the durable memory layer.
- Lane state is one of: Active lane, Parked draft lane, Idea/reference only,
  Abandoned/swept.

Format for future entries:

```text
## YYYY-MM-DD HH:MM - <create|remove|sweep> <slug>

- Provider: <provider/session>
- Branch: <branch>
- Lane state: <Active lane | Parked draft lane | Idea/reference only | Abandoned/swept>
- Worktree: <path>
- STATUS/Issue/PR: <row, issue, or PR URL>
- PLAN refs: <relevant PLAN.md modules reviewed>
- Purpose: <one-line>
- _PURPOSE.md: <path or "missing - retrofit before pickup">
- Memory refs: <prior provider memory/artifact paths>
- Related implications: <STATUS rows, pipeline rows, reports, design notes>
- Idea feed refs: <bottom-of-lane ideas/INBOX.md captures to remember, not build authority>
- Ship/abandon: <PR URL, merge SHA, or abandon reason>
```

---

## 2026-05-07 19:50 - create loop-watch-skip-receipts

- Provider: codex-gpt5-desktop
- Branch: codex/loop-watch-skip-receipts
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-loop-watch-skip-receipts
- STATUS/Issue/PR: STATUS row "Community loop watch false-red alignment"
- PLAN refs: Forever Rule uptime; community loop health watch
- Purpose: align community_loop_watch with writer skip semantics and direct schedule evidence lookup.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-loop-watch-skip-receipts\_PURPOSE.md
- Memory refs: Cowork checker note for PR #594; PR #597 receipt-chain landing
- Related implications: live watch run 25533591057, stale-gate issue flood at 2026-05-08T02:39Z
- Idea feed refs: none
- Ship/abandon: PR pending, abandon if a newer loop-health PR covers both mismatches

---

## Initial Seed - 2026-05-02

Generated from `git worktree list --porcelain` during the worktree discipline
handoff. Existing worktrees do not all have `_PURPOSE.md` yet; retrofit on
next touch. Do not bulk edit another provider's active worktree metadata.

### Current Checkout

```text
Workflow                              cursor/claim-check-session-d
```

### Claude-Team / Convention Worktrees

```text
wf-bug045                            fix/bug-045-invoke-branch-spec-plumbing
wf-cohit-prevention                  chore/check-primitive-exists-script
wf-conventions                       chore/agent-memory-ownership-convention
wf-daemon-registry-doc               chore/daemon-registry-design-note
wf-graph-compiler-fix                fix/graph-compiler-event-sink
wf-slice1-sweep                      verify/slice1-sweep
wf-validate-branch-s1                fix/bug-044-validate-branch-stage-1
wf-worktree-discipline               chore/worktree-discipline-convention
wf-worktree-status-script            chore/worktree-status-script
```

### Codex-Owned Worktrees

Codex writes or confirms `_PURPOSE.md` for these on next touch.

```text
wf-arc-b-phase3                      codex/arc-b-phase3
wf-codex-runtime-proof               codex/codex-runtime-proof
wf-connect-copy                      codex/mcp-rollout-acceptance
wf-daemon-souls                      codex/daemon-soul-summon-live
wf-daemon-souls-main                 codex/daemon-soul-summon-live-main
wf-directory-rollout                 codex/librechat-no-login-pack-v2
wf-directory-submissions             codex/directory-submission-boundaries
wf-directory-write-fix               codex/openai-write-proof-docs
wf-f2-spec-retire                    codex/status-loop-ownership
wf-host-discovery-live               codex/host-discoverability-live
wf-hostless-byok-impl                codex/daemon-memory-governor
wf-old-session-consolidation         codex/old-session-consolidation
wf-openai-app-draft-boundary         codex/openai-app-draft-boundary
wf-openai-form-state                 codex/openai-form-state
wf-openai-proof-assets               codex/openai-proof-assets
wf-openai-submission-prep            codex/openai-submission-prep
wf-provider-compliance-conventions   codex/provider-compliance-conventions
wf-reversible-approval-conventions   codex/reversible-approval-conventions
```

### Anomalies For Host / Owner Review

These do not conform to the new `../wf-<purpose-slug>` convention or have
unclear ownership. Keep, rename, or sweep only after owner/host review.

```text
Workflow/.claude/worktrees/agent-a54683e4  worktree-agent-a54683e4
Workflow/origin/main                       codex/bug037-publish-version-topology
Workflow-bug037-live2                      codex/browser-only-scorched-tanks-pwa
Workflow-scorched-pwa-live                 codex/scorched-tanks-browser-pwa-live-main
wf-ci-smoke-8e9de0c                        detached
wf-main-live                               main
wf-review-96                               detached
wf-review-100                              detached
wf-review-104                              detached
wf-review-105                              detached
wf-review-106                              detached
wf-review-107                              detached
wf-review-108                              detached
```

Notes:

- `Workflow/origin/main` is nested inside the main checkout and should not be a
  pattern for future worktrees.
- `Workflow-bug037-live2` and `Workflow-scorched-pwa-live` are sibling-prefix
  variants; new work uses `wf-*`.
- Detached `wf-review-NNN` worktrees need `_PURPOSE.md` with PR number and
  close/merge cleanup condition if retained.

## Sweep - 2026-05-02 Respawn Readiness

- Provider: codex-gpt5-desktop
- Branch: cursor/claim-check-session-d
- Worktree: C:\Users\Jonathan\Projects\Workflow
- STATUS/Issue/PR: Provider-context feed lifecycle scanner row.
- PLAN refs: Harness And Coordination; State And Artifacts; Providers.
- Purpose: Make new sessions see active worktree implications before claiming.
- _PURPOSE.md: retrofitted for `wf-worktree-discipline` and
  `wf-worktree-status-script`.
- Memory refs:
  `.claude/agent-memory/navigator/2026-05-02-worktree-discipline-design.md`.
- Related implications:
  `docs/audits/2026-05-02-provider-context-feed-frontier-research.md`.
- Idea feed refs: `ideas/PIPELINE.md`; `ideas/INBOX.md` bottom-of-lane ideas.
- Ship/abandon: Needs opposite-provider review before provider-context feed land.

## Cross-Refs

- `AGENTS.md` -> "GitHub-Aligned Worktree Discipline".
- `scripts/worktree_status.py` -> current-state scanner.
- `scripts/claim_check.py` -> STATUS.md file-collision scanner.
- `scripts/provider_context_feed.py` -> lifecycle feed for provider memories,
  loose ideas, research artifacts, automation notes, and worktree handoffs at
  claim/plan/build/review/foldback/memory-write checkpoints.
- Claude design memory:
  `.claude/agent-memory/navigator/2026-05-02-worktree-discipline-design.md`.

## Existing Main Entry - 2026-05-02

- 2026-05-02 create `../wf-provider-identity-bridge` on
  `codex/provider-identity-bridge` by codex-gpt5-desktop-identity-rollout;
  STATUS row: Provider identity bridge; PR expected ready after docs checks.

## OpenAI Submission Hardening - 2026-05-02

- 2026-05-02 create `../wf-openai-submission-hardening` on
  `codex/openai-submission-hardening` by
  codex-gpt5-desktop-openai-submission.
- STATUS row: OpenAI app submission hardening.
- Purpose: refresh official OpenAI requirements, audit `/mcp-directory`
  source/tool hints, and refactor packet/docs before final submit approval.
- Ship condition: submission packet is truthful and focused checks pass;
  final OpenAI submit remains action-time host approval.

## OpenAI Live Proof - 2026-05-02

- 2026-05-02 reuse `../wf-openai-submission-hardening` on
  `codex/openai-live-proof` by codex-gpt5-desktop-openai-submission after
  PR #183 merged.
- STATUS row: Directory submissions + first-use evidence.
- Purpose: record live deploy/redaction proof and narrow remaining OpenAI
  submission blockers.
- Ship condition: STATUS/docs show PR #183 deploy proof; ChatGPT web/mobile
  proof and final submit approval remain open.

## OpenAI Postdeploy Proof - 2026-05-02

- 2026-05-02 reuse `../wf-openai-submission-hardening` on
  `codex/openai-postdeploy-proof` by codex-gpt5-desktop-openai-submission
  after PR #184 deployed.
- STATUS row: Directory submissions + first-use evidence.
- Purpose: record strict live redaction proof after deploy run `25260784025`.
- Ship condition: STATUS/docs show strict `/mcp-directory` proof; ChatGPT
  web/mobile proof and final submit approval remain open.

## OpenAI ChatGPT Write Proof - 2026-05-02

- 2026-05-02 reuse `../wf-openai-submission-hardening` on
  `codex/openai-chatgpt-write-proof` by
  codex-gpt5-desktop-openai-submission.
- STATUS row: Directory submissions + first-use evidence.
- Purpose: record clean ChatGPT web read/write proof after strict redaction
  deploy.
- Ship condition: STATUS/docs show ChatGPT web proof and direct MCP
  verification for goal `20e2339c82e3`; mobile/final-submit approval remain
  open.

## OpenAI Onboarding Readiness Consolidation - 2026-05-02

- 2026-05-02 reuse `../wf-openai-submission-hardening` on
  `codex/onboarding-readiness-consolidation` by
  codex-gpt5-desktop-openai-submission.
- STATUS row: Directory submissions/onboarding readiness.
- Purpose: consolidate OpenAI/Claude onboarding gaps after ChatGPT web proof
  and re-audit the ChatGPT Apps packet before submission.
- Ship condition: docs/STATUS name only true remaining blockers; validation
  gates are fresh; final OpenAI submit remains action-time host approval.
- Landed: PR #193 merged on 2026-05-02 as `72b2e1d`.

## OpenAI Host-Action Foldback - 2026-05-02

- 2026-05-02 reuse `../wf-openai-submission-hardening` on
  `codex/onboarding-host-action-cleanup` by
  codex-gpt5-desktop-openai-submission after PR #193 merged.
- STATUS row: OpenAI/Claude directory submission host actions.
- Purpose: move remaining OpenAI submit blockers out of claimed provider work
  and into explicit host-action state.
- Ship condition: STATUS row no longer claims provider ownership for mobile,
  legal/publisher/assets, or final-submit approval.

## Onboarding Submission Closeout - 2026-05-02

- 2026-05-02 create `../wf-onboarding-closeout` on
  `codex/onboarding-close-gaps` by
  codex-gpt5-desktop-onboarding-closeout.
- STATUS row: OpenAI/Claude directory submission closeout.
- Purpose: close repo-side OpenAI/Claude onboarding submission gaps and
  isolate unavoidable action-time host approvals.
- Ship condition: submission assets/runbook/proofs are current; only external
  mobile/legal/publisher/final-submit actions remain.
- 2026-05-02 foldback: PR #197 merged as
  `b1fb7456afee465292b0186b8a11d12b8123c6dc`; deploy-site run
  `25262123905` passed; STATUS now points only at host actions. Local
  worktree ready to remove after this foldback lands.

## OpenAI Domain Verification - 2026-05-02

- 2026-05-02 create `../wf-openai-domain-verification` on
  `codex/openai-domain-verification` by
  codex-gpt5-desktop-openai-domain.
- STATUS row: OpenAI/Claude directory submission host actions.
- Purpose: publish OpenAI Apps domain-verification challenge for
  `tinyassets.io` and record the updated submission gate.
- Ship condition: challenge file is live and dashboard Verify Domain succeeds
  after action-time approval.
- 2026-05-02 reuse same worktree on
  `codex/onboarding-browser-proof-foldback` after PR #204 merged.
- Purpose: fold back live challenge proof and Claude.ai rendered read proof.
- Ship condition: STATUS/docs leave only true host action gates.
- 2026-05-02 reuse same worktree on
  `codex/openai-domain-verified-foldback` after host approved Verify Domain.
- Purpose: fold back OpenAI dashboard `Domain verified` proof.
- Ship condition: STATUS/docs remove Verify Domain from remaining host gates.

## OpenAI Submission Closeout - 2026-05-02

- 2026-05-02 create `../wf-openai-submission-closeout` on
  `codex/openai-submission-closeout` by codex-gpt5-desktop-onboarding.
- STATUS row: OpenAI/Claude directory submission host actions.
- Purpose: fold back the latest OpenAI Apps dashboard audit and local
  onboarding worktree cleanup.
- Ship condition: STATUS/docs name exact remaining host approvals and the
  dashboard field values ready for action-time approval.
- Cleanup performed before this lane: swept local clean merged onboarding
  worktrees for PRs #133, #135, #137, #139, #141, #143, #145, #154, and #159;
  remote GitHub branches were intentionally left untouched.

## 2026-05-02 15:12 - sweep merged local worktrees

- Provider: codex-gpt5-desktop
- Branch: `codex/status-loop-ownership`
- Lane state: Abandoned/swept
- Worktree: `C:\Users\Jonathan\Projects\wf-f2-spec-retire`
- STATUS/Issue/PR: STATUS row "Worktree backlog sweep"
- PLAN refs: Harness And Coordination
- Purpose: remove clean local worktrees whose branches had zero commits not
  reachable from `origin/main`, plus clean detached review worktrees.
- _PURPOSE.md: local ignored purpose file updated for this sweep.
- Memory refs: `.claude/agents/navigator.md`
- Related implications: GitHub/worktree discipline in `AGENTS.md`
- Idea feed refs: none
- Ship/abandon: removed 11 clean merged local branch worktrees and deleted
  their local branches: `codex/bug037-publish-version-topology`,
  `codex/arc-b-phase3`, `codex/bug-011-run-lease-phase-a`,
  `codex/chatgpt-goals-action-alias`, `codex/codex-runtime-proof`,
  `codex/daemon-soul-summon-live-main`,
  `codex/host-discoverability-live`, `codex/daemon-memory-governor`,
  `codex/old-session-consolidation`,
  `codex/provider-context-main-push`, and
  `codex/provider-identity-bridge`. Removed 8 clean detached review worktrees:
  `wf-ci-smoke-8e9de0c`, `wf-review-100`, `wf-review-104`,
  `wf-review-105`, `wf-review-106`, `wf-review-107`, `wf-review-108`,
  and `wf-review-96`. Left dirty, active, live-main, loop-owned, and unique
  clean branches intact.
- Additional local sweep: removed five clean stale worktrees with useful
  payload already folded back or extracted: `wf-cohit-prevention`,
  `wf-bug045`, `wf-provider-compliance-conventions`, and
  `wf-reversible-approval-conventions` were `git cherry` patch-equivalent to
  `origin/main`; `wf-agents-envvars` was extracted into `ff66420`. Deleted
  only local branches/worktrees; remote refs were left intact.

## 2026-05-02 - graph compiler failed-event foldback

- Provider: codex-gpt5-desktop
- Branch: `codex/status-loop-ownership`
- Lane state: Swept after foldback
- Worktree removed: `C:\Users\Jonathan\Projects\wf-graph-compiler-fix`
- Local branch deleted: `fix/graph-compiler-event-sink`
- STATUS/Issue/PR: STATUS row "Fold stale graph compiler failed-event branch"
- Source commit: `d2884fe7eaee4918538da6e3e574bd57507536ed`
- Purpose: preserve terminal failed node events when provider calls raise.
- Ship condition: regression + adjacent run-event tests pass, plugin mirror
  rebuilt, row removed in the landing commit.
- Remote branch deleted after post-push PR/ref check found no PR:
  `origin/fix/graph-compiler-event-sink`.

## 2026-05-02 - merged deploy worktree sweep

- Provider: codex-gpt5-desktop
- Branch: `codex/status-loop-ownership`
- Lane state: Swept after merge confirmation
- Worktrees removed: `C:\Users\Jonathan\Projects\wf-deploy-prod-fallback`,
  `C:\Users\Jonathan\Projects\wf-bwrap-compose-security`
- Local branches deleted: `fix/deploy-prod-latest-fallback`,
  `fix/compose-bwrap-security`
- Remote branches deleted: `origin/fix/deploy-prod-latest-fallback`,
  `origin/fix/compose-bwrap-security`
- STATUS/Issue/PR: STATUS row "Sweep merged deploy/bwrap worktrees"; PR #172
  and PR #180 were already merged.
- Evidence: `git cherry -v origin/main` marked both branch commits with `-`,
  and `gh pr list --head ... --state all` showed merged PRs.
- Purpose: remove stale branch/worktree clutter after useful deploy hardening
  was already on `main`.
- Ship condition: local worktrees gone, local + remote refs deleted, row
  removed in closeout commit.

## OpenAI Final Readiness - 2026-05-02

- 2026-05-02 create `../wf-openai-final-readiness` on
  `codex/openai-final-readiness` by codex-openai-final-readiness.
- STATUS row: OpenAI/Claude directory submission host actions.
- Purpose: close repo-side OpenAI/Claude onboarding submission evidence gaps
  before final host review.
- Ship condition: directory-safe source and live MCP evidence are current; only
  real mobile, legal/publisher, upload, Claude form, and final submit approvals
  remain action-time gates.

## Auto-Ship PR Creation - 2026-05-03

- 2026-05-03 create `../wf-auto-ship-pr-create` on
  `codex/auto-ship-pr-create` by codex-gpt5-desktop.
- STATUS row: Auto-ship #3 loop-created PR action.
- Purpose: implement feature-flagged PR creation from an existing
  `auto-change/*` branch, with no auto-merge.
- Ship condition: flag defaults off; disabled path records/returns
  `pr_create_disabled`; enabled path opens PR and updates
  `auto_ship_attempts` to `opened` + `pr_url`; targeted tests, ruff,
  plugin mirror, and diff-check pass.
- Memory refs: `.agents/activity.log` 2026-05-03T23:25Z, PR #243.

## Issue 245 Patch-Request Framing Bridge - 2026-05-04

- 2026-05-04 create `../wf-bridge-245-patch-request-framing` on
  `codex/bridge-245-patch-request-framing` by codex-gpt5-desktop.
- Source: `origin/auto-change/issue-245-codex-25294660657`, GitHub issue #245.
- Purpose: manually bridge the loop-created BUG-056 patch/feature/design
  request framing fix while #248 auto-PR creation is not yet merged.
- Ship condition: scoped diff excludes stale `.agents` deletions, plugin mirror
  rebuilt, focused tests pass, PR opened for Cowork/Codex review.

## Issue 244 Autonomy Roadmap Bridge - 2026-05-04

- 2026-05-04 create `../wf-bridge-244-autonomy-roadmap` on
  `codex/bridge-244-autonomy-roadmap` by codex-gpt5-desktop.
- Source: `origin/auto-change/issue-244-codex-25294779205`, GitHub issue #244.
- Purpose: manually bridge the loop-created autonomy roadmap/config branch while
  #248 auto-PR creation is not yet merged.
- Ship condition: scoped diff excludes stale `.agents` deletions, focused config
  test passes, PR opened for Cowork/Codex review.

## Auto-Ship Dispatch Ledger Kwargs - 2026-05-04

- 2026-05-04 create `../wf-autoship-dispatch-ledger-kwargs` on
  `codex/autoship-dispatch-ledger-kwargs` by codex-gpt5-desktop.
- Source: `.agents/activity.log` 2026-05-04T07:15Z Cowork observation 2.
- Purpose: fix `extensions action=validate_ship_packet record_in_ledger=true`
  so MCP/chatbot-triggered auto-ship attempts can write ledger rows.
- Ship condition: regression test, targeted auto-ship tests, plugin mirror,
  ruff, and diff-check pass; PR opened for Cowork review.

## Loop Self-Clear Fix - 2026-05-05

- 2026-05-05 create `../wf-loop-self-clear-fix` on
  `codex/loop-self-clear-fix` by codex-gpt5-desktop.
- Source: host liveness incident; issue #343 repeatedly retried while older
  pending auto-change requests waited.
- Purpose: make terminal no-PR writer failures add reviewed/failure labels so
  scheduled discovery can advance to the next queue item.
- Ship condition: static workflow tests, ruff, diff-check, PR opened for
  Cowork/Claude review; recovery verified by a later writer run advancing past
  the repeated issue.

## Wiki Patch Action - 2026-05-05

- 2026-05-05 create `../wf-wiki-patch-action` on
  `codex/wiki-patch-action` by codex-gpt5-desktop.
- Source: loop liveness incident: issue #347 blocked because `wiki read`
  truncates long pages while `wiki write` requires full replacement.
- Purpose: add a safe exact-match partial-patch wiki action with optional
  content-hash guard so long pages can be edited server-side.
- Ship condition: focused wiki tests, ruff, plugin mirror build, diff-check,
  and PR opened for Claude/Cowork review.

## Auto-Fix PR Token - 2026-05-05

- 2026-05-05 create `../wf-auto-fix-pr-token` on
  `codex/auto-fix-pr-token` by codex-gpt5-desktop.
- Source: post-#395 proof opened PR #397, but the PR had no status checks
  because it was created through the default Actions token.
- Purpose: prefer `WORKFLOW_PUSH_TOKEN` for Codex PR creation so pull_request
  checks fire on loop-created PRs.
- Ship condition: workflow static tests, actionlint, diff-check, PR opened for
  Claude/Cowork review.

## Branch-Push Retry Priority - 2026-05-05

- 2026-05-05 create `../wf-branch-push-terminal-retry` on
  `codex/branch-push-terminal-retry` by codex-gpt5-desktop.
- Source: after PR #398 landed, issue #87 stayed `branch_push_blocked` while
  normal old pending issues were selected first.
- Purpose: prioritize retryable `auto-fix-branch-push-blocked` issues across all
  auto labels before normal queue discovery.
- Ship condition: focused workflow tests, ruff, diff-check, PR opened for
  Claude/Cowork review.

## Merge Readiness View - 2026-05-08

- 2026-05-08 create `../wf-merge-readiness-view` on
  `codex/merge-readiness-view` by codex-gpt5-desktop.
- Source: new-day Codex/Cowork/host Phase 0-4 consensus after the 13h
  operator-asleep stall and PR #617 merge.
- Purpose: add the first read-only Phase 3 classifier for
  `RiskClassedMergeReadiness` / `MergeExecutorState` so queue routing is
  observable before any merge automation.
- Ship condition: focused tests, no PR mutation behavior, draft PR opened for
  Claude/Cowork review.
