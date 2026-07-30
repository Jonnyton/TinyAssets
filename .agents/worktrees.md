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

---

## 2026-07-27 - create preview-boundary-bootstrap

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/preview-boundary-bootstrap-20260727
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-preview-boundary-bootstrap-20260727
- STATUS/Issue/PR: STATUS.md `Bootstrap hosted-preview trust boundary` row; bootstrap PR pending
- Purpose: land the trusted default-branch preview boundary before rebasing #1812.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-preview-boundary-bootstrap-20260727\_PURPOSE.md
- Review gate: tests/builds + actionlint/zizmor + exact-head independent reviews + Claude Opus 5
- Ship/abandon: narrow main PR; merge before #1812/#1815/#1818 restack

---

## 2026-06-04 00:00 - create wiki-bug-sync-structured-first

- Provider: codex-gpt5
- Branch: patch-loop/wiki-bug-sync-structured-first
- Lane state: Active lane
- Worktree: /app
- STATUS/Issue/PR: request to update `scripts/wiki_bug_sync.py` structuredContent parsing
- PLAN refs: community loop intake sync; MCP structured payload parsing
- Purpose: reuse `_extract_structured_tool_payload` precedence for wiki list/read responses and add regression coverage.
- _PURPOSE.md: missing - retrofit before pickup
- Memory refs: none
- Related implications: `scripts/wiki_bug_sync.py`; `tests/test_wiki_bug_sync.py`
- Idea feed refs: none
- Ship/abandon: draft PR to Jonnyton/TinyAssets pending review

---

## 2026-05-27 12:00 - create pr139-universe-state

- Provider: codex-gpt5-desktop
- Branch: codex/pr139-universe-state
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-pr139-universe-state
- STATUS/Issue/PR: wiki PR-139; pages/notes/pr-139-in-flight-slice-2-universe-state-codex-2026-05-27.md
- PLAN refs: Module: Engine & Domains; Reference: State & Artifacts
- Purpose: PR-139 slice 2, additive domain-neutral universe-state substrate.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-pr139-universe-state\_PURPOSE.md
- Memory refs: drafts/notes/souled-universe-parent.md; pages/notes/pr-139-in-flight-slice-1-codex-2026-05-27.md
- Related implications: PR-139 build-order step 2; merged resolver contract PR #1089 at 71c8d5f6
- Idea feed refs: none
- Ship/abandon: PR pending; abandon if parent invariants change or another lane owns the same universe-state files

---

## 2026-05-12 21:08 - create pr828-skill-sync-refactor

- Provider: codex
- Branch: codex/pr828-skill-sync-refactor
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-pr828-skill-sync-refactor
- STATUS/Issue/PR: GitHub issue #826; closed PR #828; PR #837
- PLAN refs: Scoping Rules; Harness And Coordination; Retrieval And Memory; State And Artifacts
- Purpose: replace rejected PR #828 design-note output with loop writer routing, prompt, and guardrail fixes.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-pr828-skill-sync-refactor\_PURPOSE.md
- Memory refs: pages/notes/cowork-checker-key-pr828-reject-plus-writer-prompt-gap-2026-05-12.md; pages/notes/codex-response-cowork-writer-prompt-gap-pr097-status-and-pr633-ready-2026-05-12.md
- Related implications: pages/patch-requests/pr-106-pr-116-skills-should-sync-between-host-project-folder-loop-r.md
- Idea feed refs: none
- Ship/abandon: PR pending; abandon if equivalent design-note auto-promote and skill-loading guardrails land first

---

## 2026-05-11 16:15 - create wiki-delete-page

- Provider: codex-gpt5-desktop
- Branch: codex/wiki-delete-page
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-wiki-delete-page
- STATUS/Issue/PR: host-directed cleanup after misframed PR-106..115 pages
- PLAN refs: wiki as coordination surface; 6+5 primitive framing
- Purpose: expose safe wiki page deletion so mistaken brain pages can be removed instead of preserved.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-wiki-delete-page\_PURPOSE.md
- Memory refs: pages/notes/handoff-to-codex-pages-as-state-architectural-decision-2026-05-11.md
- Related implications: retracted PR-106..115 pages; closed GitHub PRs #809/#810/#812-#819
- Idea feed refs: none
- Ship/abandon: PR pending; abandon if equivalent safe wiki delete lands first

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
- Worktree: C:\Users\Jonathan\Projects\TinyAssets
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
- Purpose: prefer `TINYASSETS_PUSH_TOKEN` for Codex PR creation so pull_request
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

## Independent Checker Routing - 2026-05-09

- 2026-05-09 create `../wf-independent-checker-routing` on
  `codex/independent-checker-routing` by codex-gpt5-desktop.
- Source: live #720 recruiter-readiness stall; host asked to make the
  independent-checker self-heal gap real instead of a session workaround.
- Purpose: extend merge-readiness / loop-watch observability so mixed-provenance
  PRs with ineligible executor sessions route to an independent checker lane.
- Ship condition: focused tests pass, PR opened for Cowork/Claude review, no
  merge/approval behavior added.

## Checker Worker Dispatch - 2026-05-09

- 2026-05-09 create `../wf-checker-worker-dispatch` on
  `codex/checker-worker-dispatch` by codex-gpt5-desktop.
- Source: host clarified #720 must be fixed by the loop doing checker work, not
  by operators manually filling the checker role.
- Purpose: add an automatic checker-worker dispatch/receipt slice above the
  #728 independent-checker observability state.
- Ship condition: focused tests pass, PR opened for Cowork/Claude review, #720
  can route to a checker worker without manual session assignment.

## Checkpoint Retention - 2026-05-12

- 2026-05-12 create `../wf-checkpoint-retention` on
  `codex/checkpoint-retention` by codex-gpt5-desktop.
- Source: production disk triage found `concordance/checkpoints.db` at ~6.5 GiB
  with 2,915 retained checkpoints and no free-list space.
- Purpose: cap LangGraph checkpoint retention and surface active-universe
  checkpoint DB size in storage status before it becomes a disk-full outage.
- Ship condition: focused tests pass, ruff passes, PR opened for Claude/Cowork
  review.

## PR #975 Tools-Allowed Repair - 2026-05-24

- 2026-05-24 create `../wf-pr975-tools-allowed-repair` on
  `codex/pr975-tools-allowed-repair` by codex-gpt5-desktop-checker-pr975.
- Source: `outputs/pr-inventory-2026-05-23/checker-batches-2026-05-24.md`
  repair lane for dirty/conflicted PR #975 / GH issue #974.
- Purpose: port the #975 runtime MCP affordance onto current main without
  touching unrelated checker/repair lanes.
- Ship condition: focused branch-runner/API tests pass and PR/handoff goes to
  Claude-family checker because original writer family is Codex.

## BUG-106 Wiki Read Truncation - 2026-05-27

- 2026-05-27 create `../wf-bug106-wiki-read-truncation` on
  `codex/bug106-wiki-read-truncation` by codex-gpt5-desktop.
- Source: live wiki BUG-106 filed from the souled-universe draft review:
  `wiki read` returns partial large documents without an in-band marker.
- Purpose: make wiki read truncation unmistakable and actionable for connector
  users.
- Ship condition: focused wiki read tests pass, PR opened for Claude-family
  checker review.

## PR-139 Resolver Contract - 2026-05-27

- 2026-05-27 create `../wf-pr139-resolver-contract` on
  `codex/pr139-resolver-contract` by codex-gpt5-desktop.
- Source: live wiki PR-139 souled-universe consolidation program; dispatcher
  request failed from provider exhaustion before creating a GitHub lane.
- Purpose: implement build-order step 1 only: frozen resolver decision contract,
  fixture shape, and tests.
- Ship condition: focused resolution contract tests pass, branch pushed, PR
  opened for opposite-family checker review.

## #961 Branch Authoring Receipts - 2026-05-27

- 2026-05-27 create `../wf-pr961-branch-authoring-receipts` on
  `codex/pr961-branch-authoring-receipts` by codex-gpt5-desktop.
- Source: GH #961 asks for faster online Branch authoring with approvals,
  scoped trust sessions, and batch receipts.
- Purpose: ship the safe runtime slice: structured receipts on existing
  `build_branch` / `patch_branch`, without changing authorization semantics.
- PR: #1093.
- Ship condition: focused composite-action tests pass, mirror parity passes,
  PR opened for checker review.

## PR-139 Soul From Premise - 2026-05-27

- 2026-05-27 create `../wf-pr139-soul` on `codex/pr139-soul` by
  codex-gpt5-desktop.
- Source: live wiki PR-139 souled-universe consolidation program; host key
  now approved for all PR-139 slices.
- Purpose: implement build-order step 3 only: generalize `soul.md` from the
  current premise mechanism.
- Ship condition: focused soul/premise tests pass, branch pushed, PR opened
  for opposite-family checker review.

## PR-139 Permission Consolidation - 2026-05-27

- 2026-05-27 create `../wf-pr139-permission` on `codex/pr139-permission` by
  codex-gpt5-desktop.
- Source: live wiki PR-139 souled-universe consolidation program; slice 4
  coordination marker filed in the live wiki.
- Purpose: implement build-order step 4 only: CHILD-3 permission consolidation
  through a test-universe `.can(action, scope, context)` path, resolver-decision
  fixture handle, and legacy `is_host` equivalence evidence.
- Ship condition: focused permission/auth/universe tests pass, branch pushed,
  PR opened for opposite-family checker review.

## P0 Canary StructuredContent Parser - 2026-05-27

- 2026-05-27 create `../wf-p0-canary-structured-content` on
  `codex/p0-canary-structured-content` by codex-gpt5-desktop.
- Source: public MCP uptime canary run 26557828602 failed because the live
  tool result text is a preview and the JSON payload is in `structuredContent`.
- Purpose: fix the canary parser to accept current structured MCP tool
  payloads while preserving text-JSON fallback.
- Ship condition: focused canary tests pass, local live canary passes, branch
  pushed, PR opened for checker/host review.

## P0 Wiki Bug Sync StructuredContent Parser - 2026-05-28

- 2026-05-28 create `../wf-wiki-bug-sync-structured-content` on
  `codex/wiki-bug-sync-structured-content` by codex-gpt5-desktop.
- Source: community loop watch issue #1118 red; `wiki-bug-sync.yml` run
  26605636623 crashed because `scripts/wiki_bug_sync.py` parsed text only while
  MCP list payload now lives in `structuredContent`.
- Purpose: port the structuredContent/text-fallback parser pattern from #1125
  into the intake sync script and prove it with regression coverage.
- Ship condition: focused tests pass, branch pushed, PR opened, GitHub
  `wiki-bug-sync.yml` dispatch succeeds, community loop watch recovers or
  residual non-intake blockers are documented.

## Codex Tiny Spec Review - 2026-06-10

- 2026-06-10 create `../wf-codex-tiny-review` on `codex/tiny-spec-review` by
  codex-gpt5-desktop.
- Source: PR #1303 landed the host-ratified Tiny first-principles spec plus
  Brain v2 and primitive-basis companions; STATUS.md has a pending Codex
  review gate for those companions.
- Purpose: write the Codex approve/adapt review artifact that unblocks or
  scopes context-engine build and vocabulary lock.
- Ship condition: artifact under `docs/audits/`, STATUS row retired/updated,
  branch pushed, PR opened.

## Prod Codex Auth Data Volume - 2026-06-17

- 2026-06-17 create `../wf-prod-codex-auth-data-volume` on
  `codex/prod-codex-auth-data-volume` by codex-gpt5-desktop.
- Source: host-directed production outage fix; Codex OAuth auth was tied to
  ephemeral container home and went stale after idle windows.
- Purpose: persist subscription-backed Codex auth at shared `/data/.codex`,
  make `get_status` honor `CODEX_HOME`, and add weekly SSH keepalive.
- Ship condition: focused tests pass, PR merged to main, deploy-prod green,
  live `get_status` sees Codex auth, trivial LLM node succeeds, keepalive
  dispatch green.

## BUG-126 Daemon Control - 2026-06-20

- 2026-06-20 create `../wf-bug126-daemon-control` on
  `codex/bug126-daemon-control` by codex-gpt5-desktop.
- Source: live wiki BUG-126; host handoff says existing branch was only the
  old watchdog commit and the actual daemon control fix was not written.
- Purpose: let connector `daemon_get`, `daemon_summon`, and `daemon_restart`
  accept top-level `daemon_id`, so a specific daemon can be inspected,
  revived, or restarted without host shell access.
- Ship condition: focused universe API tests pass, plugin mirror parity passes,
  branch pushed, PR opened for checker review.

## 4 Runtimes Up Deploy Config - 2026-06-20

- 2026-06-20 create `../wf-four-runtimes-up` on `codex/four-runtimes-up` by
  codex-gpt5-desktop.
- Source: host-directed split from PR-177; fleet runtime activation ships before
  goal_pool/marketplace economy work.
- Purpose: run 2 Codex + 2 Claude pinned workers from the two subscription auth
  homes already approved by #1330, with Codex auth refresh serialized.
- Ship condition: focused tests pass, branch pushed, PR opened, then deploy
  brings runtime_count to 4 while goal_pool remains a follow-on.
- 2026-07-21 CREATE wf-paid-market-wave2-spec branch=codex/paid-market-track-e-wave2-spec base=origin/main@a69dd70a provider=codex-gpt5-desktop (Track E Wave 2 transport OpenSpec proposal)
- 2026-06-24 CREATE wf-branch-lifecycle-automation branch=worktree-branch-lifecycle-automation base=origin/main provider=claude-code (branch lifecycle automation — design note + L0-L4)

## 2026-07-22 12:41 - create collapse-mcp-spec-reconcile

- Provider: codex-gpt5-desktop-2
- Branch: codex/collapse-mcp-spec-reconcile
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-collapse-mcp-spec-reconcile
- STATUS/Issue/PR: Reconcile obsolete five-handle OpenSpec; PR after strict validation and independent review
- PLAN refs: API and MCP Interface; Distribution and Discoverability
- Purpose: retire the obsolete five-handle change without corrupting seven-handle canonical truth and preserve real residuals as successor changes
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-collapse-mcp-spec-reconcile\_PURPOSE.md
- Memory refs: PR #1594 audit; PR #1595 catalog repair
- Related implications: external directory acceptance; live-mcp-connector-surface; PR #1561 legacy stdio fence is a separate runtime lane
- Idea feed refs: none
- Ship/abandon: merge reviewed spec-only PR, or abandon if a current overlapping lane is found

## 2026-07-22 - remove collapse-mcp-spec-reconcile

- Provider: codex-gpt5-desktop-2
- Branch: codex/collapse-mcp-spec-reconcile
- Lane state: Abandoned/swept
- Worktree: C:\Users\Jonathan\Projects\wf-collapse-mcp-spec-reconcile
- STATUS/Issue/PR: reviewed spec-only PR; STATUS claim retired in landing diff
- PLAN refs: API and MCP Interface; Distribution and Discoverability
- Purpose: archive obsolete five-handle proposal without syncing and preserve residual work as two narrow successor changes
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-collapse-mcp-spec-reconcile\_PURPOSE.md
- Memory refs: independent Codex whole-lane APPROVE 2026-07-22
- Related implications: external directory acceptance; PR #1522 folds into manifest successor; PRs #1561 and #1553 remain separate
- Idea feed refs: none
- Ship/abandon: ship after GitHub checks; local worktree may be removed after merge
## 2026-07-22 13:00 - create test-identity-reset-spec

- Provider: codex-gpt5-desktop-2
- Branch: codex/test-identity-reset-spec-reconcile
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-test-identity-reset-spec
- STATUS/Issue/PR: R2-2 repeatable test identity; spec-only reconciliation before any runtime salvage
- PLAN refs: full PLAN review; Providers, API & MCP Interface, Constraints, State & Artifacts
- Purpose: make the active reset/identity OpenSpec truthful, narrow, and safe without reusing stale all-eleven-task work
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-test-identity-reset-spec\_PURPOSE.md
- Memory refs: conformance triage from PR #1597 lane; stale PR #1560 and commit 375b0155 read-only
- Related implications: universe-visibility and provider-status own the moved isolation/evidence concerns
- Idea feed refs: none
- Ship/abandon: reviewed spec-only PR; implementation remains a later separately claimed lane

## 2026-07-23 - create backfill-graph-run-coordination-contracts

- Provider: codex-gpt56-spec-5
- Branch: codex/backfill-graph-run-coordination
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-backfill-graph-run-coordination
- STATUS/Issue/PR: Backfill graph-run coordination contracts
- PLAN refs: Engine & Domains; API & MCP Interface; State & Artifacts
- Purpose: backfill shipped run evidence receipts and installation/data-root-local teammate mailbox behavior missed by the full-coverage audit
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-backfill-graph-run-coordination\_PURPOSE.md
- Memory refs: 2026-07-22 full-coverage audit and grounding batches; three focused Codex semantic reviews
- Related implications: active distributed-execution remains read-only; full-coverage audit must stop claiming these two stores were canonical
- Idea feed refs: none
- Ship/abandon: ship reviewed spec-only backfill; runtime remains unchanged

## 2026-07-22 - remove test-identity-reset-spec

- Provider: codex-gpt5-desktop-2
- Branch: codex/test-identity-reset-spec-reconcile
- Lane state: Abandoned/swept
- Worktree: C:\Users\Jonathan\Projects\wf-test-identity-reset-spec
- STATUS/Issue/PR: R2-2 spec reconciliation approved; temporary claim retired in landing diff
- PLAN refs: full PLAN; Daemon Platform, Providers, API & MCP Interface, State & Artifacts
- Purpose: make test identity, operator reset, privacy, crash safety, and requester compute authority truthful before implementation
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-test-identity-reset-spec\_PURPOSE.md
- Memory refs: three independent Codex APPROVE verdicts, 2026-07-22
- Related implications: #1560 superseded; 2.3 stays with visibility/identity; provider evidence stays with #1570
- Idea feed refs: none
- Ship/abandon: ship reviewed spec-only PR; implementation remains separately claimable after merge
## 2026-07-22 13:30 - create connector-manifest-products

- Provider: codex-gpt5-desktop-2
- Branch: codex/connector-manifest-product-split
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-connector-manifest-products
- STATUS/Issue/PR: Split connector-manifest product contracts; corrective spec-only PR
- PLAN refs: API & MCP Interface; Distribution & Discoverability
- Purpose: separate remote OAuth seven, local MCPB seven, and remote directory-five product/auth contracts while sharing catalog names
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-connector-manifest-products\_PURPOSE.md
- Memory refs: post-#1597 reciprocal review ADAPT
- Related implications: manifest successor blocks retire-legacy-live-mcp-tools; external directory acceptance stays host-owned
- Idea feed refs: none
- Ship/abandon: reviewed corrective spec-only PR

## 2026-07-22 - remove connector-manifest-products

- Provider: codex-gpt5-desktop-2
- Branch: codex/connector-manifest-product-split
- Lane state: Abandoned/swept
- Worktree: C:\Users\Jonathan\Projects\wf-connector-manifest-products
- STATUS/Issue/PR: three-product distribution spec approved; temporary claim retired in landing diff
- PLAN refs: API & MCP Interface; Distribution & Discoverability
- Purpose: separate remote OAuth seven, local MCPB stdio seven-name, and remote directory-five contracts and acceptance
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-connector-manifest-products\_PURPOSE.md
- Memory refs: three independent Codex APPROVE verdicts, 2026-07-22
- Related implications: local actorless `converse` blocks legacy retirement until authority/redesign and host migration proof; external directory acceptance remains host-owned
- Idea feed refs: none
- Ship/abandon: ship reviewed spec-only PR; implementation remains separately claimable after merge

## 2026-07-22 - create sandbox-runner-spec-backfill

- Provider: codex-gpt56-spec
- Branch: codex/sandbox-runner-spec-backfill
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-sandbox-runner-spec-backfill
- STATUS/Issue/PR: Backfill shipped per-job sandbox runner seam
- PLAN refs: Daemon Platform; distributed-execution active change
- Purpose: canonicalize the landed fail-closed `runner/v1` seam without claiming a backend or production confinement
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-sandbox-runner-spec-backfill\_PURPOSE.md
- Memory refs: two independent 2026-07-22 owner/evidence audits
- Related implications: PR #1485 landed code; PR #1475 and active distributed-execution remain read-only future owners
- Idea feed refs: none
- Ship/abandon: sync/archive after strict validation, focused tests, and independent review

## 2026-07-22 - retire sandbox-runner-spec-backfill

- Provider: codex-gpt56-spec
- Branch: codex/sandbox-runner-spec-backfill
- Lane state: Review-ready; claim retired in landing diff
- Worktree: C:\Users\Jonathan\Projects\wf-sandbox-runner-spec-backfill
- STATUS/Issue/PR: PR #1629; temporary backfill claim removed after canonical sync/archive
- PLAN refs: Daemon Platform; distributed-execution active change
- Purpose: canonicalize the landed fail-closed `runner/v1` seam without claiming a backend or production confinement
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-sandbox-runner-spec-backfill\_PURPOSE.md
- Memory refs: `openspec/changes/archive/2026-07-23-backfill-per-job-sandbox-runner-seam/reviews/2026-07-23-independent-review.md`
- Related implications: active distributed-execution owner must reclassify its proposal as extending the new canonical base
- Idea feed refs: none
- Ship/abandon: reviewed and archived; retain worktree until PR #1629 lands

## 2026-07-22 - create sandbox-availability-spec-backfill

- Provider: codex-gpt56-spec-2
- Branch: codex/sandbox-availability-spec-backfill
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-sandbox-availability-spec-backfill
- STATUS/Issue/PR: Backfill sandbox availability and fail-loud execution contracts
- PLAN refs: Providers; Graph Execution; Uptime and Alarms
- Purpose: canonicalize shipped bwrap probing/caching and loud execution failure without claiming real confinement
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-sandbox-availability-spec-backfill\_PURPOSE.md
- Memory refs: post-PR #1629 reverse-coverage audit
- Related implications: PR #1573 and active distributed-execution remain future/read-only; PR #1626 did not canonicalize sandbox-status wording
- Idea feed refs: none
- Ship/abandon: sync/archive after strict validation, focused evidence, and independent review

## 2026-07-23 - retire sandbox-availability-spec-backfill

- Provider: codex-gpt56-spec-2
- Branch: codex/sandbox-availability-spec-backfill
- Lane state: Reviewed and archived; retirement staged in PR #1632
- Worktree: C:\Users\Jonathan\Projects\wf-sandbox-availability-spec-backfill
- STATUS/Issue/PR: PR #1632; landing diff removes the active claim
- PLAN refs: Providers; Graph Execution; Uptime and Alarms
- Purpose: fold seven shipped sandbox contracts into five canonical owners
- _PURPOSE.md: retained locally until the PR merges
- Memory refs: three independent APPROVE verdicts in the archived review record
- Related implications: credential-vault and hyperparameter importance remain shipped-coverage residuals
- Idea feed refs: none
- Ship/abandon: remove the physical worktree only after PR #1632 lands

## 2026-07-22 - create hyperparameter-importance-spec

- Provider: codex-gpt56-spec-2
- Branch: codex/hyperparameter-importance-spec-backfill
- Lane state: Active lane
- Worktree: C:\Users\Jonathan\Projects\wf-hyperparameter-importance-spec
- STATUS/Issue/PR: PR #1633 — Backfill shipped hyperparameter-importance evaluator
- PLAN refs: Evaluation; Outcomes
- Purpose: canonicalize the shipped fail-soft RF/Spearman evaluator and correct the legacy audit so the incompatible future science-domain target remains distinct
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-hyperparameter-importance-spec\_PURPOSE.md
- Memory refs: post-PR #1632 full-coverage residual audit
- Related implications: canonical evaluation-runtime owner; PR #1627 remains read-only; the future science-domain node/fixture target keeps a separate successor
- Idea feed refs: none
- Ship/abandon: sync/archive after strict validation, focused evidence, and independent review

## 2026-07-23 - retire hyperparameter-importance-spec

- Provider: codex-gpt56-spec-2
- Branch: codex/hyperparameter-importance-spec-backfill
- Lane state: Reviewed and archived; retirement staged in PR #1633
- Worktree: C:\Users\Jonathan\Projects\wf-hyperparameter-importance-spec
- STATUS/Issue/PR: PR #1633 approved; landing diff retires the temporary shipped-backfill claim
- PLAN refs: Evaluation; Outcomes
- Purpose: canonicalize the shipped generic evaluator while preserving the future science node/fixtures as a distinct target
- _PURPOSE.md: retained locally until PR #1633 merges
- Memory refs: archived independent review at `openspec/changes/archive/2026-07-23-backfill-hyperparameter-importance-shipped-contracts/reviews/2026-07-23-independent-review.md`
- Related implications: credential-vault is the only remaining shipped-coverage residual; five target-owner groups remain
- Idea feed refs: none
- Ship/abandon: remove the physical worktree only after PR #1633 lands

## 2026-07-23 - create credential-backfill-coordination

- Provider: codex-gpt56-spec-5
- Branch: codex/credential-backfill-coordination
- Lane state: Active coordination-only correction
- Worktree: C:\Users\Jonathan\Projects\wf-credential-backfill-coordination
- STATUS/Issue/PR: `Backfill remaining credential-vault shipped contracts`; PR after review
- PLAN refs: Brain; Providers; State & Artifacts
- Purpose: replace the stale #1606 canonical-owner dependency with the landed #1607 owner and current semantic/file blockers
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-credential-backfill-coordination\_PURPOSE.md
- Memory refs: PRs #1606, #1607, #1626; full-coverage audit
- Related implications: fail-closed provider auth overlay; R2-1a/R2-1b
- Idea feed refs: none
- Ship/abandon: land only the coordination correction; no OpenSpec or runtime edits

## 2026-07-23 - create uptime-alarm-concurrency-proof-coord

- Provider: codex-gpt56-spec-5
- Branch: codex/uptime-alarm-concurrency-proof-coord
- Lane state: Blocked coordination lane
- Worktree: C:\Users\Jonathan\Projects\wf-uptime-alarm-concurrency-proof-coord
- STATUS/Issue/PR: `Prove uptime alarm §14 concurrency after #1638/#1639`; coordination PR after review
- PLAN refs: Uptime & Alarms; Cross-Cutting Principles
- Purpose: restore the mandatory queued-trigger and incident-order concurrency proof omitted from #1638
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-uptime-alarm-concurrency-proof-coord\_PURPOSE.md
- Memory refs: PRs #1638/#1639; post-merge independent ADAPT review
- Related implications: active wiki-canary OAuth-challenge lane owns overlapping uptime files
- Idea feed refs: none
- Ship/abandon: publish the pending row now; build only after the active owner releases the workflow/spec

## 2026-07-23 - create mcpb-catalog-parity

- Provider: codex-gpt5-desktop
- Branch: codex/mcpb-catalog-parity
- Lane state: Active implementation lane
- Worktree: C:\Users\Jonathan\Projects\wf-mcpb-catalog-parity
- STATUS/Issue/PR: `MCPB staged catalog parity`; PR after independent review
- PLAN refs: Distribution & Discoverability; API & MCP Interface
- Purpose: make MCPB manifest tool metadata equal the staged middleware’s canonical seven-handle catalog and make packaging fail closed on future drift
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-mcpb-catalog-parity\_PURPOSE.md
- Memory refs: PR #1600; archived `collapse-live-mcp-surface-to-5-handles`
- Related implications: `reconcile-external-connector-manifests` tasks 1.1 and 2.1–2.5
- Idea feed refs: none
- Ship/abandon: land only the deterministic MCPB parity slice; defer Polsia handoff, directory acceptance, and host-rendered proof

## 2026-07-23 - create uptime-proof-p0-blocker-coord

- Provider: codex-gpt5-desktop
- Branch: codex/uptime-proof-p0-blocker-coord
- Lane state: Coordination-only dependency correction
- Worktree: C:\Users\Jonathan\Projects\wf-uptime-proof-blocker-coord2
- STATUS/Issue/PR: `Prove uptime alarm §14 concurrency after #1638/#1639`; PR after focused review
- PLAN refs: Uptime & Alarms; Cross-Cutting Principles
- Purpose: preserve the active P0-triage lane’s canonical uptime-spec ownership after #1641/#1642 released the prior wiki-canary blocker
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-uptime-proof-blocker-coord2\_PURPOSE.md
- Memory refs: PRs #1640–#1643; local `codex/fix-p0-triage-failure-escalation` claim
- Related implications: exact-script concurrency proof design prepared; implementation waits for canonical spec release
- Idea feed refs: none
- Ship/abandon: publish only the dependency edge; remove it when the P0-triage lane lands and releases the spec

## 2026-07-23 - create archive-1574-research

- Provider: codex-gpt5-desktop
- Branch: docs/archive-1574-research
- Lane state: Active archival documentation lane
- Worktree: C:\Users\Jonathan\Projects\wf-1574-research-archive
- STATUS/Issue/PR: `Archive PR #1574 research without design-truth foldback`; parent review before push
- PLAN refs: Scoping Rules; Commons-first architecture; Providers; no PLAN edits authorized
- Purpose: preserve nine dated research/review artifacts and gated idea pointers without landing stale PLAN or coordination truth from draft PR #1574
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-1574-research-archive\_PURPOSE.md
- Memory refs: draft PR #1574; current-main paid-market source-context approval
- Related implications: `paid-market-live-price-discovery`; R2-1a/R2-1b; target-spec PLAN host decision
- Idea feed refs: compute/model/task/fabrication markets; Zapier-equivalent automation; concurrency/scale; organizational universes; regulated-industry profiles
- Ship/abandon: local commit only until parent review; land docs, refreshed pointers, and task reflection, never #1574 PLAN/runtime/OpenSpec/stale coordination edits

## 2026-07-23 - create supersede-pr1574-references

- Provider: codex-gpt5-desktop
- Branch: docs/supersede-pr1574-references
- Lane state: Active reference-freshness cleanup
- Worktree: C:\Users\Jonathan\Projects\wf-supersede-pr1574-references
- STATUS/Issue/PR: supersede stale #1574 references after archival successor #1648
- PLAN refs: Providers; paid-market target remains host-PLAN gated
- Purpose: point active paid-market context at durable archived research, remove #1574 as a live dependency, and preserve the source review as dated evidence
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-supersede-pr1574-references\_PURPOSE.md
- Memory refs: PRs #1574/#1648; paid-market source-context review
- Related implications: `paid-market-live-price-discovery`; `paid-market-track-e-wave-2-transport`; target-spec PLAN conflict
- Idea feed refs: archived compute/model/task/fabrication market research
- Ship/abandon: land reference-only edits, then close #1574 as superseded

## 2026-07-23 - create provider-attempt-receipts

- Provider: codex-provider-receipts
- Branch: codex/provider-attempt-receipts
- Lane state: Active spec-only lane; apply blocked
- Worktree: C:\Users\Jonathan\Projects\wf-provider-attempt-receipts
- STATUS/Issue/PR: `R2-1b provider-attempt receipts (spec only)`; local commit pending root review
- PLAN refs: Providers; Cross-Cutting Principles; State & Artifacts; Brain
- Purpose: specify result-local provider-attempt evidence for reply and learning calls without runtime or canonical-spec edits
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-provider-attempt-receipts\_PURPOSE.md
- Memory refs: `.claude/agent-memory/dev-2/reference_plan_md_provider_invariants.md`; PR #1606; R2-1a STATUS row
- Related implications: fail-closed provider auth overlay; credential-vault backfill; both `converse` writer calls
- Idea feed refs: none
- Ship/abandon: strict-validate and commit locally; apply waits for #1606/R2-1a, and no push/PR occurs before root review

## 2026-07-23 - create disk-watch-remediation-continuity

- Provider: codex-gpt5-desktop-disk
- Branch: fix/disk-watch-remediation-continuity
- Lane state: Active OpenSpec + TDD uptime repair
- Worktree: C:\Users\Jonathan\Projects\wf-disk-watch-remediation
- STATUS/Issue/PR: P1 disk-watch stop-on-pressure seam; PR pending
- PLAN refs: Uptime & Alarms
- Purpose: keep the intentional disk-pressure alert failure visible while guaranteeing later transcript rotation and disposable-host reclamation commands are attempted in order
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-disk-watch-remediation\_PURPOSE.md
- Memory refs: canonical `uptime-and-alarms` disk-pressure stop-seam requirement
- Related implications: P0 disk-full triage; deploy unit installation convergence
- Idea feed refs: none
- Ship/abandon: land one reviewed OpenSpec/TDD repair with focused tests; no host-install claim without live evidence

## 2026-07-23 - refresh operator-request-trigger-spec

- Provider: codex-refresh-operator-spec
- Branch: codex/operator-request-trigger-spec
- Lane state: Planning-only draft PR; refreshed locally for root review
- Worktree: C:\Users\Jonathan\Projects\wf-operator-request-trigger-spec
- STATUS/Issue/PR: live P1 `operator_request` concern; draft PR #1628; no spec-only Work claim
- PLAN refs: Daemon Platform; API & MCP Interface; Uptime & Alarms
- Purpose: rebase the reviewed admission contract without implying that runtime is fixed
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-operator-request-trigger-spec\_PURPOSE.md
- Memory refs: `docs/audits/2026-07-22-openspec-full-coverage-audit.md`; PR #1628 review record
- Related implications: rebase audit found only STATUS/worktree coordination conflicts; runtime P1 remains live
- Idea feed refs: none
- Ship/abandon: root review before push; merge as planning authority only, then claim exact runtime/test files in a separate lane after blockers clear

## 2026-07-23 - create deploy-rollback-receipt-truth

- Provider: codex-gpt5-desktop-rollback
- Branch: fix/deploy-rollback-receipt-truth
- Lane state: Active OpenSpec + TDD uptime repair
- Worktree: C:\Users\Jonathan\Projects\wf-deploy-rollback-receipt
- STATUS/Issue/PR: P1 rollback-scope truth residual; PR pending
- PLAN refs: Uptime & Alarms; API & MCP Interface release-state contract
- Purpose: ensure deploy failures and rollbacks publish terminal machine-readable truth instead of leaving a stale success receipt or unconditional “rolled back” claim
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-deploy-rollback-receipt\_PURPOSE.md
- Memory refs: `audit/audit-release-chain` P2-10; current `deploy-prod.yml`
- Related implications: release reconcile; `get_status.release_state`; P0 image-pull recovery; DR evidence
- Idea feed refs: none
- Ship/abandon: land one reviewed OpenSpec/TDD repair; do not claim live rollout until workflow evidence exists

## 2026-07-23 - ready deploy-rollback-receipt-truth

- Provider: codex-gpt5-desktop-rollback
- Branch: fix/deploy-rollback-receipt-truth
- Lane state: OpenSpec archived; repository implementation independently approved; PR-ready
- Worktree: C:\Users\Jonathan\Projects\wf-deploy-rollback-receipt
- STATUS/Issue/PR: implementation row retired; P1 live-failure-exercise watch retained; PR pending
- Verification: 240 focused checks; pinned actionlint 1.7.7; strict OpenSpec 42/42; three independent approvals
- Ship/abandon: merge through PR; do not claim operational proof until both production-safe failure exercises pass

## 2026-07-23 - create finish-node-enqueue

- Provider: codex-gpt5-desktop-enqueue
- Branch: codex/finish-node-enqueue
- Lane state: Active OpenSpec + concurrency-proof lane
- Worktree: C:\Users\Jonathan\Projects\wf-finish-node-enqueue
- STATUS/Issue/PR: `Prove shared in-node enqueue caps`; PR pending
- PLAN refs: Module Engine & Domains; Module Daemon Platform; §14 concurrency/load-test proof
- Purpose: backfill the approved live enqueue contract and prove exact shared-cap behavior under contention
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-finish-node-enqueue\_PURPOSE.md
- Memory refs: `docs/audits/2026-05-30-in-node-enqueue-codex-review.md`; `docs/audits/2026-06-02-in-node-enqueue-adapt-rereview.md`
- Related implications: production flag is already on; no runtime behavior change unless the proof exposes a defect
- Idea feed refs: none
- Ship/abandon: merge through a reviewed PR after strict OpenSpec and focused concurrency evidence

## 2026-07-23 - broaden finish-node-enqueue

- Provider: codex-gpt5-desktop-enqueue
- Branch: codex/finish-node-enqueue
- Lane state: Active OpenSpec + TDD production repair
- Worktree: C:\Users\Jonathan\Projects\wf-finish-node-enqueue
- STATUS/Issue/PR: broadened claimed row; PR pending
- Purpose: repair stable-root and lifetime-lineage bypasses exposed by the cap proof, then prove thread/process boundaries
- Related implications: production activation is proven; the previous no-runtime-change assumption no longer holds
- Ship/abandon: independent review is mandatory before merge because this now changes live queue admission

## 2026-07-23 - ready finish-node-enqueue

- Provider: codex-gpt5-desktop-enqueue
- Branch: codex/finish-node-enqueue
- Lane state: OpenSpec archived; implementation independently approved; PR-ready
- Worktree: C:\Users\Jonathan\Projects\wf-finish-node-enqueue
- STATUS/Issue/PR: claimed until merge; PR #1672
- Verification: 47 focused post-archive checks; security review observed 120 related passes; strict OpenSpec 41/41; mirror parity; concurrency/storage and security/spec APPROVE
- Post-fix live use: none yet; production-clean use must wait for deploy and observation
- Ship/abandon: make PR ready after CI and final verifier approval; retire STATUS row only after merge

## 2026-07-23 - landed finish-node-enqueue

- Provider: codex-gpt5-desktop-enqueue
- Branch: codex/finish-node-enqueue
- Lane state: merged as PR #1672 at `7778eebf`; implementation claim retired
- Worktree: C:\Users\Jonathan\Projects\wf-finish-node-enqueue
- STATUS/Issue/PR: only the post-deploy organic-use watch remains
- Verification: GitHub policy, package/import probe, and build-smoke passed; auto-merge completed
- Ship/abandon: observe production use after deployment; do not infer clean use from repository proof

## 2026-07-24 - created distributed-execution-current-main-design

- Provider: codex-gpt5-desktop
- Branch: codex/distributed-execution-current-main-design
- Lane state: landed via PR #1699 (`978649fe`)
- Worktree: C:\Users\Jonathan\Projects\wf-distributed-execution-current-main
- STATUS/Issue/PR: merged; coordination row retired
- Scope: complete distributed-execution design and publish a current-main extraction manifest; no runtime or live authority activation
- Review gate: independent security/design review now; opposite-provider review before live apply/deploy
- Memory/implications: PR #1475 handoff; PRs #1472/#1477/#1479/#1481/#1487/#1491; `docs/exec-plans/active/2026-07-18-distributed-execution-platform.md`
- Ship/abandon: ship when OpenSpec is strict-valid and current-main staged authority boundaries are independently approved; abandon only for a newer explicit successor

## 2026-07-24 - created distributed-execution-d0

- Provider: codex-gpt5-desktop
- Branch: codex/distributed-execution-d0
- Lane state: landed via PR #1701 (`aa328495`)
- Worktree: C:\Users\Jonathan\Projects\wf-distributed-execution-d0
- STATUS/Issue/PR: merged; coordination retirement follows on current main
- Scope: implement the dark fake/test-only signed-authority spine from `distributed-execution` tasks 1.1-1.16; no production wiring
- Review gate: focused TDD plus independent security/diff review; opposite-provider review remains required before any real-provider path
- Memory/implications: PR #1699; #1697 non-promotion invariant; stale PR extraction sources named in the OpenSpec design
- Ship/abandon: ship only with the D0 focused path, mutation proof, full strict OpenSpec validation, and zero production imports/routes/adapters

## 2026-07-24 - retire distributed-execution-d0

- Provider: codex-gpt5-desktop
- Branch: codex/retire-distributed-execution-d0
- Lane state: current-main coordination follow-up
- Worktree: C:\Users\Jonathan\Projects\wf-retire-distributed-execution-d0
- STATUS/Issue/PR: retire merged #1701 row and mark D0 tasks landed
- Scope: coordination/docs only; no runtime behavior
- Review gate: strict OpenSpec validation and exact coordination diff
- Ship/abandon: land immediately after current-main checks; no deployment

## 2026-07-24 - created retire-mcp-directory

- Provider: codex-gpt56-mcp-retirement
- Branch: codex/retire-mcp-directory
- Lane state: merged; production proof moved to the canonical `/mcp` STATUS watch
- Worktree: C:\Users\Jonathan\Projects\wf-retire-mcp-directory
- STATUS/Issue/PR: PR #1718 merged as `60f7f9f1`, based on merged PR #1688
- Scope: remove `/mcp-directory*` runtime/catalog/discovery/edge routing, generated mirrors, maintained registrations/guidance, and prove ordinary 404
- Review gate: red-first app/edge tests, provider-free canonical health, strict OpenSpec, independent architecture/security/diff review
- Memory/implications: PR #1688; PR #1522 provenance; source-derived canonical hardening remains separately opposite-provider-gated
- Ship/abandon: landed; retain the worktree only until the coordination closeout and production probes are recorded

## 2026-07-24 - fix MCP retirement proof

- Provider: codex-gpt56-mcp-proof-fix
- Branch: codex/fix-mcp-retirement-proof
- Lane state: PR open; independently approved; production contract green
- Worktree: C:\Users\Jonathan\Projects\wf-fix-mcp-retirement-proof
- STATUS/Issue/PR: PR #1722; Opus 5 final reject follow-up to merged PR #1718
- Scope: Cloudflare-safe retirement probe, correct deploy ownership, exact-seven canary, as-built spec truth, stale operator guidance
- Review gate: focused red/green tests, strict OpenSpec, workflow checks, independent diff review, then live rerun
- Memory/implications: PR #1718 review artifact; canonical hardening tasks remain separately open
- Ship/abandon: ship through PR #1722; both owning deploy lanes and direct live probes now prove their part

## 2026-07-24 - fix deploy receipt summary quoting

- Provider: codex-gpt56-deploy-summary
- Branch: fix/deploy-summary-quoting
- Lane state: PR open; awaiting Opus 5 review and required checks
- Worktree: C:\Users\Jonathan\Projects\wf-deploy-summary-quoting
- STATUS/Issue/PR: production Deploy prod run 30141691915; PR #1725
- Scope: fix the post-deploy receipt Summary literal-escape SyntaxError
- Review gate: focused RED/GREEN test, workflow suite, actionlint, independent Opus 5 review
- Memory/implications: receipt validation/publication succeeded; Summary rendering alone failed
- Ship/abandon: publish reviewed PR to main; do not deploy from this lane

## 2026-07-24 - epoch-2 claimed-request materialization

- Provider: codex-gpt5-desktop-operator
- Branch: codex/operator-epoch2-consumer
- Lane state: active implementation
- Worktree: C:\Users\Jonathan\Projects\wf-operator-epoch2-consumer
- STATUS/Issue/PR: STATUS 5.7 row; no PR yet
- Scope: live-claim-only canonical v2 Request materialization and restart observation; no v2 claim activation or v1 projection
- Review gate: focused red/green tests, adjoining suite, strict OpenSpec, mirror/import checks, independent Opus 5 exact-head review
- Memory/implications: 5.8 remains blocked by PLAN's file-lock versus transactional-claim conflict
- Ship/abandon: publish reviewed prerequisite PR; keep EPOCH2_QUEUE_CONSUMER_READY false

## 2026-07-24 23:10 - create wiki-discovery-scope

- Provider: codex-gpt56-wiki-scope
- Branch: codex/wiki-discovery-scope
- Lane state: Merged as PR #1745 at `fdfde5f1bd74ff74bd808e02bf453721db38a1fb`; proof moved to `wf-wiki-discovery-proof`
- Worktree: C:\Users\Jonathan\Projects\wf-wiki-discovery-scope
- STATUS/Issue/PR: R2-4a wiki discovery scoping; #1550 closed source-only
- PLAN refs: Module API & MCP Interface; composable primitive and visibility principles
- Purpose: default user discovery excludes coordination history without resurrecting the retired directory server.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-wiki-discovery-scope\_PURPOSE.md
- Memory refs: docs/audits/2026-07-21-wiki-discovery-contamination.md; PR #1550
- Related implications: universe-visibility; canonical /mcp acceptance; universe-creation owns the public read_page seam
- Idea feed refs: none
- Ship/abandon: ship current-main OpenSpec/TDD successor through a reviewed PR; abandon if the behavior is already satisfied

## 2026-07-24 23:10 - create secret-custody-spec

- Provider: codex-gpt56-secret-custody
- Branch: codex/secret-custody-spec
- Lane state: Active review/spec-only lane
- Worktree: C:\Users\Jonathan\Projects\wf-secret-custody-spec
- STATUS/Issue/PR: Retire MCP provider-secret deposit
- PLAN refs: Module Providers; Module API & MCP Interface; full-platform control-plane/BYOC boundaries
- Purpose: replace raw MCP provider-secret deposit with requester-controlled OS custody and opaque authority references.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-secret-custody-spec\_PURPOSE.md
- Memory refs: docs/audits/2026-07-24-first-contact-authority-opus5-verdict.md; PRs #1592, #1691, #1736
- Related implications: Slice A0; provider-attempt receipts; universe-creation; complete-independent-full-platform-targets
- Idea feed refs: #1469 remains optional source-only encrypted server custody unless separately approved
- Ship/abandon: Opus APPROVE/ADAPT gates a strict spec PR; runtime remains blocked on listed owners

## 2026-07-25 - verify deployed wiki discovery

- Provider: codex-gpt56-wiki-proof with Claude Opus 5 browser peer
- Branch: codex/wiki-discovery-proof
- Lane state: Active post-merge proof
- Worktree: C:\Users\Jonathan\Projects\wf-wiki-discovery-proof
- STATUS/Issue/PR: Verify deployed wiki discovery; PR #1745 merged
- PLAN refs: Module API & MCP Interface; canonical `/mcp`; visibility principles
- Purpose: prove deployed source, exact-seven surface, rendered connector behavior, and organic use/watch
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-wiki-discovery-proof\_PURPOSE.md
- Memory refs: archived `2026-07-25-scope-wiki-discovery`; PR #1745
- Review gate: ui-test through real chatbot + independent evidence review
- Ship/abandon: publish proof/task foldback only; no runtime changes
- Foldback: proof complete and independently approved; PR #1747 merged

## 2026-07-25 - bind authenticated host principal to account

- Provider: codex-gpt56-host-principal with Claude Opus 5 opposite review
- Branch: codex/host-principal-binding
- Lane state: landed; PR #1753 merged at `d454a5c5`; runtime remains separately gated
- Worktree: C:\Users\Jonathan\Projects\wf-host-principal-binding
- STATUS/Issue/PR: STATUS row retired; PR #1753 merged
- PLAN refs: Identity; Host Pool; Providers; zero-maintainer-authority invariant
- Purpose: preserve the stable server account-to-host authority and add the unowned subject-pinned `bound`-not-`online` tray contract without creating a competing identity primitive
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-host-principal-binding\_PURPOSE.md
- Memory refs: draft PR #1746 owner-resolution ADAPT; PR #1736
- Review gate: exact-head Opus 5 and independent Codex approved; counterparty owner acceptance remains before runtime
- Ship/abandon: current-main spec/audit PR only; runtime files remain unclaimed

## 2026-07-25 - reconcile engine execution admission and isolation

- Provider: codex-gpt5-desktop-full-product with Claude Opus 5 opposite review
- Branch: `feat/converse-os-sandbox` via local `codex/reconcile-engine-os-sandbox-final-20260725`
- Lane state: landed as PR #1573 / `c1f0d404`; spec/audit only, with no runtime or backend authority
- Worktree: C:\Users\Jonathan\Projects\wf-engine-os-sandbox-final
- STATUS/Issue/PR: PR #1573 merged; STATUS work row retired; P0 runtime concern remains
- PLAN refs: Execution substrate; Provider routing; Distributed execution; zero-maintainer-authority invariant
- Purpose: replace the obsolete Bubblewrap-only false-attestation contract with backend-neutral, non-downgradeable execution admission composed with #1784
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-engine-os-sandbox-final\_PURPOSE.md
- Memory refs: #1784; runner/v1; exact Opus 5 APPROVE; 2026-07-25 sandbox audit
- Review gate: passed — exact-head Opus 5 plus independent security/domain/diff approvals; 53/53 strict OpenSpec
- Ship/abandon: merged in place; runtime/backends remain unclaimed and require owner-specific lanes

## 2026-07-24 23:15 - repurpose release-reconcile-event

- Provider: codex-gpt5-desktop-release-reconcile
- Branch: codex/release-reconcile-event
- Lane state: PRs #1749/#1750 landed; live foldback complete
- Worktree: C:\Users\Jonathan\Projects\wf-operator-epoch2-consumer
- STATUS/Issue/PR: #1749 implementation + #1750 CI cleanup merged; drift/failure-cap monitoring remains
- PLAN refs: Uptime & Alarms; release/deploy reconciliation
- Purpose: trigger release reconciliation after successful Docker smoke completion while retaining the cron backstop and non-cancelling concurrency.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-operator-epoch2-consumer\_PURPOSE.md
- Memory refs: wf-openspec-uptime-backfill; release terminal truth and deploy rollback receipts
- Related implications: Docker build smoke; build-image/deploy-prod chain; release-state honesty
- Idea feed refs: none
- Ship/abandon: ship through OpenSpec, Section-14 concurrency proof, actionlint, Opus 5 review, and a short-lived PR; abandon if current main already has an equivalent event trigger
- Foldback: OpenSpec archived; Opus 5 approved; #1750 repaired post-merge CI; main smoke #30152319997 woke successful workflow_run reconcile #30152436780

## 2026-07-25 - repurpose secure-agent-village

- Provider: codex-gpt5-desktop-village-security
- Branch: codex/secure-agent-village
- Lane state: PR #1760 landed; containment foldback complete
- Worktree: C:\Users\Jonathan\Projects\wf-operator-epoch2-consumer
- STATUS/Issue/PR: #1760 merged; active row retired
- PLAN refs: API & MCP Interface; chatbot + connector is canonical, Agent Village deferred
- Purpose: minimum containment of the already-shipped unsafe surface; no continuing Village product lane.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-operator-epoch2-consumer\_PURPOSE.md
- Memory refs: PR #1489 recovery and clean-checkout proof
- Related implications: local-app capability axis; host-private coordination state; explicit write actions
- Idea feed refs: none
- Ship/abandon: strict OpenSpec change, exact HTTP/browser contract tests, security review, and short-lived PR; abandon only if current main already enforces equivalent authentication
- Foldback: OpenSpec archived; Opus 5 approved; #1760 merged; all checks green; connector-first priority recorded

## 2026-07-25 - harden-production-load-evidence

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/harden-production-load-evidence
- Lane state: claimed; spec-only promotion
- Worktree: C:\Users\Jonathan\Projects\wf-full-product-next
- STATUS/Issue/PR: STATUS Work row; PR pending
- PLAN refs: §14 concurrency/load proof; API & MCP connector-first principle
- Purpose: define the shared production-load evidence protocol without owning capability scenarios, thresholds, or `tests/load/`.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-full-product-next\_PURPOSE.md
- Memory refs: none
- Related implications: 2026-07-21 user-growth concurrency/scalability audit; April Track J pre-draft
- Idea feed refs: ideas/INBOX.md §14 production-load harness entry
- Ship/abandon: ship a strict-valid target OpenSpec after Opus 5 artifact review; abandon if the draft cannot keep protocol ownership disjoint from capability owners

## 2026-07-25 - fold back harden-production-load-evidence

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/harden-production-load-evidence-foldback
- Lane state: foldback after PR #1775
- Worktree: C:\Users\Jonathan\Projects\wf-full-product-next-foldback
- STATUS/Issue/PR: #1775 merged at `c94575c9`; completed authoring row retired
- PLAN refs: §14 concurrency/load proof; API & MCP connector-first principle
- Purpose: mark proposal validation/landing complete while leaving implementation tasks and the isolated `/mcp` host decision active
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-full-product-next-foldback\_PURPOSE.md
- Memory refs: none
- Related implications: final Opus 5 APPROVE in `docs/audits/2026-07-25-section14-production-load-evidence-opus5-review.md`
- Idea feed refs: retired into active OpenSpec `harden-production-load-evidence`
- Foldback: target change remains active and unsynced; no runtime or `tests/load/` implementation claimed

## 2026-07-25 - full-product-vision-completion-audit

- Provider: codex-gpt56-full-vision
- Branch: codex/full-product-vision-audit-20260725
- Lane state: landed as PR #1779 / `b1acc2bc`
- Worktree: C:\Users\Jonathan\Projects\wf-full-product-vision-audit
- STATUS/Issue/PR: merged PR #1779; STATUS Work row retired
- PLAN refs: full product architecture; §14 concurrency/load proof; API & MCP connector-first principle
- Purpose: map the host's complete product vision to current design, implementation, and acceptance evidence without claiming active runtime files.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-full-product-vision-audit\_PURPOSE.md
- Memory refs: Handoff #1582; historical 2026-07-21 implications reports
- Related implications: compute/LLM market; Zapier automation; scalability; organization brains; regulated-industry profiles
- Idea feed refs: ideas/PIPELINE.md promoted research; ideas/INBOX.md organization and assurance successors
- Ship/abandon: shipped after exact-head Opus approval and 51/51 strict validation; no implementation authority or runtime edits
- Foldback: gaps promoted through separate OpenSpec/STATUS claims only

## 2026-07-25 - harden-branch-access-authority

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/harden-branch-access-authority
- Lane state: claimed; spec-only promotion
- Worktree: C:\Users\Jonathan\Projects\wf-connector-first-next
- STATUS/Issue/PR: STATUS Work rows; PR pending
- PLAN refs: API & MCP Interface; connector users are first-class
- Purpose: specify one authenticated-subject branch authority boundary across reads, projections, reuse, lineage, mutation, and deletion
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-connector-first-next\_PURPOSE.md
- Memory refs: none
- Related implications: active universe-visibility predicates stay owner-local; run-branch access is a named sibling lane
- Idea feed refs: none
- Ship/abandon: ship strict-valid target OpenSpec after Opus 5 artifact review; no runtime or test edits while claimed elsewhere

## 2026-07-25 - reconcile-provider-authority

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/reconcile-provider-authority
- Lane state: landed in main as #1784 / `620fed5a`; supersedes draft PR #1691
- Worktree: C:\Users\Jonathan\Projects\wf-reconcile-provider-authority
- STATUS/Issue/PR: merged PR #1784; STATUS Work row retired
- PLAN refs: Provider Integration; §14 concurrency/load proof; connector users are first-class
- Purpose: replace the unmintable requester seal and circular sibling gates with request-scoped transport evidence, sink-bound authority, and one-way interfaces.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-reconcile-provider-authority\_PURPOSE.md
- Memory refs: draft PR #1691 is source-only
- Related implications: #1746 secret custody; universe creation; provider-attempt receipts; future requester-host activation
- Idea feed refs: none
- Ship/abandon: shipped after strict 51/51 validation, exact-revision Opus 5 approval, and published sibling handoffs

## 2026-07-25 - provider-authority-foldback

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/provider-authority-foldback
- Lane state: claimed; merged-lane coordination cleanup only
- Worktree: C:\Users\Jonathan\Projects\wf-provider-authority-foldback
- STATUS/Issue/PR: retire #1784 Work row; close superseded draft PR #1691; follow-up PR
- PLAN refs: Provider Integration; §14 concurrency/load proof
- Purpose: mark task 1.35, retire the landed STATUS claim, and preserve the target active/unsynced.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-provider-authority-foldback\_PURPOSE.md
- Memory refs: #1784 exact-head Opus approval
- Related implications: #1746 secret custody; provider-attempt receipts; provider-authority successors
- Idea feed refs: none
- Ship/abandon: merge only if no other foldback already performed all cleanup

## 2026-07-25 - background-provider-authority

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/provider-authority-successors
- Lane state: claimed; OpenSpec planning only
- Worktree: C:\Users\Jonathan\Projects\wf-provider-authority-successors
- STATUS/Issue/PR: split provider-authority successor bundle; claim background receipt contract
- PLAN refs: Daemon Platform; Providers; API & MCP Interface; Uptime & Alarms
- Purpose: specify durable provider work authority across post-response task/thread/process bridges without runtime edits.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-provider-authority-successors\_PURPOSE.md
- Memory refs: #1784 / merge 620fed5a / exact-head Opus approval
- Related implications: run/background branch authority; provider-attempt receipts; outbound boundary
- Idea feed refs: none
- Ship/abandon: planning PR after exact current-main Opus review; no Village/web dependency

## 2026-07-26 - refresh PostgreSQL transactional control-plane authority

- Provider: codex-gpt5-desktop-full-product; Claude Opus 5 opposite review approved
- Branch: codex/postgres-control-plane-exact-main-20260726
- Lane state: host-approved; landing current-main target OpenSpec/audit refresh only
- Worktree: C:\Users\Jonathan\Projects\wf-postgres-control-plane-exact
- STATUS/Issue/PR: draft PR #1802; stale stacked draft PR #1670 closed as superseded
- PLAN refs: per-domain canonical store; full-platform zero-host architecture; §14 load proof
- Purpose: preserve PostgreSQL authority for catalog/ledger/inbox/market while reconciling current identity, custody, migration, load, market, and execution owners
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-postgres-control-plane-exact\_PURPOSE.md
- Memory refs: PR #1670; PR #1761 PLAN foldback; PRs #1775/#1784/#1797/#1798/#1573/#1800
- Review gate: passed at semantic SHA `bc5fdcbb` — exact current-main Opus 5 plus three independent architecture/spec/verification approvals; host accepted the reconciled target boundary 2026-07-26
- Ship/abandon: target-only OpenSpec/audit publication; no SQL, runtime, baseline inventory, migration, cutover, sync, archive, deploy, or production authority

## 2026-07-26 - background-provider-authority foldback

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/provider-authority-successors-foldback
- Lane state: foldback after PR #1803 merged
- Worktree: C:\Users\Jonathan\Projects\wf-provider-authority-successors
- STATUS/Issue/PR: retire the landed planning claim; target stays active with 33 runtime tasks
- PLAN refs: Daemon Platform; Providers; API & MCP Interface; Uptime & Alarms
- Purpose: preserve the approved implementation handoff without treating planning as runtime completion.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-provider-authority-successors\_PURPOSE.md
- Memory refs: #1784 / merge `620fed5a`; #1803 / merge `58371486`
- Related implications: background branch authority; run authority; provider-attempt receipts; outbound boundary
- Ship/abandon: merge coordination-only foldback, then release this worktree lane

## 2026-07-26 - background-branch-execution-authority

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/background-branch-authority-spec
- Lane state: claimed; OpenSpec planning only
- Worktree: C:\Users\Jonathan\Projects\wf-provider-authority-successors
- STATUS/Issue/PR: split target specification from blocked runtime implementation
- PLAN refs: Daemon Platform; Multi-User Evolutionary Design; API & MCP Interface; Uptime & Alarms
- Purpose: bind scheduled, autonomous, and post-response branch execution to server-owned target authority while keeping valid private loops live.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-provider-authority-successors\_PURPOSE.md
- Memory refs: #1784 / merge `620fed5a`; #1803 / merge `58371486`
- Related implications: harden-branch-access-authority; universe-creation; retire-legacy; provider-attempt receipts
- Ship/abandon: planning PR only after exact current-main Opus review; no runtime or Village/web dependency

## 2026-07-26 - retire privileged cheat/community patch loop

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/retire-cheat-loop-current-20260726
- Lane state: target merged as PR #1810; implementation gates remain in the safe-waves lane
- Worktree: C:\Users\Jonathan\Projects\wf-retire-cheat-loop-current
- STATUS/Issue/PR: host-directed retirement; merged PR #1810
- PLAN refs: user-authored/remixable automations; generic Goal/graph/wiki/effect/evaluation primitives; complete-system uptime
- Purpose: remove privileged platform-owned auto-triage/auto-ship/repair/routing and patch-loop product branding while preserving generic primitives users can compose, copy, and remix
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-retire-cheat-loop-current\_PURPOSE.md
- Memory refs: host directive 2026-07-26; semantic target 8ef99451; current-main reconciliation 3fabd2e1; merge 0d50a2d4
- Review gate: exact Claude Opus 5 APPROVE plus independent architecture/spec/live-migration APPROVEs
- Ship/abandon: target landed; collision-free runtime deletion remains separately gated; no reinterpretation of queued privileged rows as generic user automations

## 2026-07-26 - retire cheat-loop collision-safe waves

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/retire-cheat-loop-safe-waves
- Lane state: claimed; current-main site/announcement/helper wave approved at `c84cb833`
- Worktree: C:\Users\Jonathan\Projects\wf-retire-cheat-loop-safe-waves
- STATUS/Issue/PR: open draft implementation PR #1812 against `main`
- PLAN refs: user-authored/remixable automations; public website surface; complete-system uptime
- Purpose: remove retired product presentation and callers from production React, rollback Svelte, and deployment guidance without touching runtime/queue or external GitHub state
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-retire-cheat-loop-safe-waves\_PURPOSE.md
- Memory refs: target merge 0d50a2d4; safe-wave commits 5e8e5e39/594a9287/255e83cf; current-main exact approval c84cb833
- Review gate: current-main Opus 5 APPROVE plus three pre-merge exact APPROVEs over byte-identical implementation; rendered connector and post-fix clean-use remain later acceptance gates
- Ship/abandon: keep PR #1812 draft and gate any merge on task 3.5's final announcement-run drain; do not deploy or authorize runtime/external-state retirement
- Update 2026-07-26: draft PR #1812 published and green; announcement/helper deletion committed; exact Opus 5 + three independent reviewers APPROVE `9e08a28c`; tasks 3.5/5.2/5.3 and rendered/clean-use gates remain open
- Update 2026-07-26: parent #1810 folded in; React/Svelte builds, 58/58 strict OpenSpec, active-source scans, and exact current-main reviews pass at `c84cb833`
- Update 2026-07-27: current-main exact head `c5a13216` has final Codex/Opus 5 APPROVE, 59/59 strict OpenSpec, green 282-test Linux CI, and pre-credential preview receipt `30327788528`; #1812 is ready for promotion before #1815/#1818 restack.

## 2026-07-26 - close release-reconcile production drift watch

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/close-release-reconcile-watch-20260726
- Lane state: landed via PR #1816
- Worktree: C:\Users\Jonathan\Projects\wf-close-release-reconcile-watch
- STATUS/Issue/PR: resolved monitoring row retired in merged PR #1816
- PLAN refs: Uptime & Alarms; complete-system 24/7 uptime
- Purpose: preserve the first end-to-end drift-to-build-to-explicit-deploy convergence under the #1749/#1750 logic; drift detection itself predates it.
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-close-release-reconcile-watch\_PURPOSE.md
- Memory refs: PRs #1749/#1750; Actions runs #30188518485/#30188530692/#30188600783
- Review gate: Claude Opus 5 APPROVE after two correction passes; no runtime/workflow changes
- Ship/abandon: landed at `970c1d57`; no further release action

## 2026-07-27 - restack privileged loop uptime-skill retirement

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/restack-retire-loop-uptime-final-20260727
- Publish branch: codex/retire-loop-uptime-skill (PR #1815 force-with-lease target)
- Lane state: landed as PR #1815
- Build worktree: C:\Users\Jonathan\Projects\wf-restack-retire-loop-uptime-final-20260727
- STATUS/Issue/PR: PR #1815 merged to main as `d024e479`
- PLAN refs: user-buildable/remixable automations; generic uptime and alarms; no privileged platform loop
- Purpose: delete the active loop-uptime escape-hatch skill and catalog routes while retaining incident records only as historical non-skill evidence
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-restack-retire-loop-uptime-final-20260727\_PURPOSE.md
- Memory refs: base 18abe542; prior payload head 50192892; prepared review heads b71f1b70/fae3842b
- Review gate: skill sync/parity, active-surface scan, strict OpenSpec, independent exact-head review
- Ship/abandon: landed at `d024e479`; never reinterpret historical incidents as active instructions
- Host checkout obligation: after #1815 lands, safely reconcile primary checkout `0bc841aa` to merged main so the exact discovery-only `.agents`/`.claude` deletions cease to be uncommitted; do not restore the retired route or overwrite unrelated dirty files
- Update 2026-07-27: canonical skill/catalog and PLAN escape-path claim replayed; seven historical records moved out of active agent surfaces
- Update 2026-07-27: pre-review head 328a98e6 passed idempotent skill sync, drift/skill gates, zero active/runtime route scans, 59/59 strict OpenSpec, and fresh-session host-catalog proof; `test_validate_skills.py` retains only the two known main-baseline `zoom-out` fixture failures
- Update 2026-07-27: exact head a3c8cb7d received Codex and Claude Opus 5 APPROVE and landed through PR #1815 as `d024e479`

## 2026-07-27 - restack privileged loop soul retirement

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/restack-retire-loop-souls-final-20260727
- Publish branch: codex/retire-loop-souls (PR #1818 force-with-lease target)
- Lane state: landed as PR #1818
- Worktree: C:\Users\Jonathan\Projects\wf-restack-retire-loop-souls-final-20260727
- STATUS/Issue/PR: PR #1818 merged to main as `30c962c7`
- PLAN refs: user-buildable/remixable automations; generic soul/daemon machinery; no platform-owned loop-team defaults
- Purpose: delete the seven shipped loop-team soul documents without filtering user-authored workflows or claiming live snapshot/data retirement
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-restack-retire-loop-souls-final-20260727\_PURPOSE.md
- Memory refs: base d024e479; prior PR head a6376bfe; source deletion d311cf03 replayed as 29486b98
- Review gate: exact absence/reference scans, daemon-registry tests, strict OpenSpec, Codex and Claude Opus 5 exact-head review
- Ship/abandon: landed at `30c962c7`; keep OpenSpec task 5.3 open until canonical snapshot provenance/pagination, live-source disposition, stored-role, and synthetic-fixture proof are complete
- Remaining proof: source deletion is not production deregistration or generated-snapshot evidence
- Update 2026-07-27: exact head 6cc51c01 received Codex and Claude Opus 5 APPROVE and landed through PR #1818 as `30c962c7`

## 2026-07-27 - audit next privileged-loop retirement wave

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/audit-retire-cheat-runtime-next-20260727
- Lane state: landed as PR #1829
- Worktree: C:\Users\Jonathan\Projects\wf-audit-retire-cheat-runtime-next-20260727
- STATUS/Issue/PR: PR #1829 merged to main as `66006cf4`; existing migrator draft PR #1820 targets unmerged `codex/retire-loop-snapshots`
- PLAN refs: user-buildable/remixable automation; generic primitives survive; no privileged platform composition
- Purpose: map remaining runtime, workflow/live-state, snapshot/data, packaging, and validation residue to exact owners and choose the smallest collision-safe wave
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-audit-retire-cheat-runtime-next-20260727\_PURPOSE.md
- Memory refs: base 30c962c7; PRs #1812/#1815/#1818 landed; retire-cheat-loop OpenSpec
- Review gate: exact residue scan, claim-check owner map, strict OpenSpec, independent Codex/Claude architecture review before implementation
- Ship/abandon: publish the audit/foldback separately; implement only after an exact Files/Depends claim is clear
- Update 2026-07-27: exact-head Codex review required an ordering correction: 2.1 stop-writer -> dark authority store/reconciler -> locked 2.5 migration -> authority activation/foldback; stale broad claims must be revalidated/reaped or carved
- Update 2026-07-27: exact head `0a4bd6f3` received Codex and Claude Opus 5 APPROVE and landed through PR #1829 as `66006cf4`

## 2026-07-27 - restack cheat-loop GitHub-state inventory migrator

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/restack-retire-loop-github-state-20260727
- Lane state: landed as PR #1830
- Worktree: C:\Users\Jonathan\Projects\wf-restack-retire-loop-github-state-20260727
- STATUS/Issue/PR: PR #1830 merged to main as `52475559`; old draft PR #1820 closed as superseded with replacement link
- PLAN refs: user-buildable/remixable automation; retire only privileged GitHub residue; preserve generic effectors and explicit GitHub primitives
- Purpose: import only the fail-closed inventory/planning/verifier payload and exact 3.6/3.7 spec delta; exclude old snapshot/site/coordination ancestry
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-restack-retire-loop-github-state-20260727\_PURPOSE.md
- Memory refs: base 66006cf4; PR #1829 audit; source payload d40173a2; draft PR #1820
- Review gate: 46 focused tests, py_compile, strict OpenSpec, no-live-mutator inspection, exact-head Codex and Claude Opus 5 review
- Ship/abandon: keep tasks 3.6/3.7 unchecked; open against main, then close #1820 as superseded with replacement link; do not import or close sibling snapshot PR #1819
- Update 2026-07-27: PR #1830 opened against main at `fab12790`; #1820 closed as superseded; #1819 remains parked for the separate snapshot/task-5.3 lane
- Update 2026-07-28: exact head `d5b31a3f` received Codex security/spec and Claude Opus 5 APPROVE; PR #1830 merged as `52475559`

## 2026-07-28 - post-1830 cheat-loop retirement hardening

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/post1830-retire-next-20260728
- Lane state: landed as PR #1835 / main `328f2c64`
- Worktree: C:\Users\Jonathan\Projects\wf-post1830-retire-next-20260728
- STATUS/Issue/PR: PR #1835 merged; retirement claim continues as task 2.1
- PLAN refs: user-buildable/remixable automation; no privileged platform composition
- Purpose: reject inert peer-record/schema extensions while the no-live-mutator boundary remains dark
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-post1830-retire-next-20260728\_PURPOSE.md
- Memory refs: main `52475559`; PRs #1829/#1830; retire-cheat-loop OpenSpec
- Review gate: TDD, full focused suite, strict OpenSpec, independent Codex and Claude Opus 5 exact-head review
- Ship/abandon: no live GitHub mutation; tasks 3.6/3.7 stay unchecked; task 2.1 source/mirror/tests are clear after exact public-read/personification/outbound claim narrowing and landed control_station cleanup
- Update 2026-07-28: TDD proved three red bypasses, then 49/49 passed after exact label definition/association closure and rejecting label planned actions
- Update 2026-07-28: pushed current-main branch and opened draft PR #1835; exact-head Codex approved `b8d57e9f`, Claude Opus 5 required collector-contract coverage before ready
- Update 2026-07-28: review fix adds collector round-trip, exact scalar schemas, and PlanError container typing; 53/53 pass with 60/60 strict OpenSpec
- Update 2026-07-28: control_station's apparent task-2.1 conflict was three-dot squash ancestry; all five target blobs equal current main, independent carve-out recheck pending
- Update 2026-07-28: independent recheck confirmed all five blobs/index/worktree clean; narrowed three broad claims to release task-2.1 files
- Update 2026-07-28: Opus approved the collector/schema adaptation and requested only a non-blocking malformed-action error-contract cleanup before merge
- Update 2026-07-28: `cf48df9e` converts malformed non-empty label action arrays from raw traceback to PlanError; 54/54 pass
- Update 2026-07-28: exact head `7ecc82b1` received Codex and Claude Opus 5 APPROVE; PR #1835 merged as `328f2c64`

## 2026-07-28 - cheat-loop task 2.1 filing-only stop-writer

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/retire-cheat-stop-writer-20260728
- Lane state: PR #1836 merged as `35da9d4f`; repository stop-writer landed, runtime deploy/drain/fence proof pending
- Worktree: C:\Users\Jonathan\Projects\wf-retire-cheat-stop-writer-20260728
- STATUS/Issue/PR: PR #1836 merged; active privileged-loop runtime-proof claim
- PLAN refs: user-buildable/remixable automation; generic wiki filing and explicit workflow primitives survive
- Purpose: remove `file_bug` trigger receipt, enqueue, Investigation rendering, and response metadata while preserving ordinary filing
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-retire-cheat-stop-writer-20260728\_PURPOSE.md
- Memory refs: main `328f2c64`; PRs #1829/#1830/#1835; retire-cheat-loop task 2.1
- Review gate: RED 7 failures; GREEN 136 passed/1 skipped plus 85 related passed; Ruff/py_compile/diff-check/parity passed; nested Codex exact-head APPROVE; fresh Codex + Claude Opus 5 exact-head review still required
- Ship/abandon: repository merge is only the stop-writer image; task 2.1 stays unchecked until deployed and every old writer is drained/fenced
- Update 2026-07-28: exact head `e8755f08` received Codex and Claude Opus 5 APPROVE; PR #1836 merged as `35da9d4f`. Repository lane closed; production still ran old writer image at the last audit.

## 2026-07-28 - cheat-loop task 2.1 production deployment proof

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/retire-cheat-deploy-proof-20260728
- Lane state: draft PR #1839; repository candidate approved at `953f89db`; current-main integration, CI, and live deployment proof remain
- Worktree: C:\Users\Jonathan\Projects\wf-retire-cheat-deploy-proof-20260728
- STATUS/Issue/PR: draft PR #1839; task 2.1 operational continuation after merged PR #1836
- PLAN refs: user-buildable/remixable automation; no platform-owned cheat/community writer
- Purpose: build and deploy the filing-only image while proving every controlled writer, queued write-back, restart racer, and rollback path is fenced
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-retire-cheat-deploy-proof-20260728\_PURPOSE.md
- Memory refs: merge `35da9d4f`; retire-cheat-loop task 2.1; runtime residue audit production topology section
- Review gate: 201 focused tests plus Ruff/compile/YAML/bash/diff/OpenSpec green; workflow, security, simplification, and Claude Opus 5 exact-head APPROVEs; actionlint/CI, live deploy receipt, and rendered connector proof remain
- Ship/abandon: do not dispatch build/deploy until preflight evidence exists; task 2.1 remains unchecked on any uncertainty
- Update 2026-07-28: `953f89db` closes write-ahead, crash/cancellation,
  bounded-lock, residue, guarded-mutation, rollback, and terminal-truth gaps.
  The 1,735-line controller is explicitly transitional and must be deleted
  after task 2.5; no production action has run from this branch yet.
- Update 2026-07-28: Claude Opus 5 APPROVED repository head `2dcc1139`
  with no blocking findings and asked that controller deletion become a
  checkable obligation; OpenSpec task 2.5a now owns that deletion.

## 2026-07-27 - canonical public-read completeness

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/public-read-completeness-current
- Lane state: slice 0A local runtime approved; deploy/sync/live connector proof pending
- Worktree: C:\Users\Jonathan\Projects\wf-public-read-completeness-current
- STATUS/Issue/PR: Implement canonical public-read completeness; no public PR before the privacy deployment gate
- PLAN refs: canonical seven handles; Tier-1 chatbot-first surface; wiki discovery; shared goals; §14 load proof; Village deferred
- Purpose: close every public private-Goal read oracle, then define visibility-safe full-scope pagination and completeness receipts without adding an MCP handle
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-public-read-completeness-current\_PURPOSE.md
- Memory refs: PR #1812 blocker evidence; `docs/audits/2026-07-25-full-product-vision-completion-audit.md`
- Review gate: spec Opus 5 round 18 APPROVE; runtime Opus 5 round 8b APPROVE after every blocking finding was folded
- Ship/abandon: private deploy first, then sync/publish and rendered connector acceptance; never publish the live privacy gap ahead of deployment

## 2026-07-28 - harden GitHub retirement terminal oracle

- Provider: codex-gpt5-desktop-full-product
- Branch: codex/retire-github-terminal-oracle-final
- Lane state: exact semantic head `c95876fe` received Opus 5 APPROVE; publication pending
- Worktree: C:\Users\Jonathan\Projects\wf-retire-github-terminal-oracle-final
- STATUS/Issue/PR: same privileged-loop retirement claim; #1830/#1835/#1836 are the landed base
- PLAN refs: ordinary user-buildable uptime primitives; no hidden repair/mutation authority; Village deferred
- Purpose: reject full terminal REST pages as ambiguous while preserving #1830's closed receipt envelope and all other fail-closed guards
- _PURPOSE.md: C:\Users\Jonathan\Projects\wf-retire-github-terminal-oracle-final\_PURPOSE.md
- Memory refs: Opus 5 review rounds in the abandoned pre-#1830 worktree; PR #1830 / `52475559`
- Review gate: passed — 61 focused tests, Ruff, all 60 strict OpenSpec validations, 45 forgery probes, bounded mutation battery, exact semantic-head Opus 5 APPROVE
- Ship/abandon: land only the complementary oracle hardening; tasks 3.6/3.7 remain unchecked and no GitHub state may change
- Update 2026-07-28: pre-#1835 exact-current Opus 5 mutation review returned APPROVE after every request/page-size, digest, and archive guard then under review proved load-bearing
- Update 2026-07-28: moved the approved commit into a clean current-main worktree after #1835 overlapped the receipt-schema files; preserved both hardening waves
- Update 2026-07-28: exact-current Opus found a recovery-doc gap plus Unicode, multi-page-terminal, and stored-endpoint-scope proof gaps; all four adaptations are folded and 61/61 passes
- Update 2026-07-28: Opus rereview found two surviving test mutations plus a malformed-page traceback and stale approval wording; exact continuation, positive multi-page, and typed-failure regressions are folded
- Update 2026-07-28: next Opus pass found the stored anchor admitted `page`/`after`, continuation subguards and live round-trip were underpinned, and `None` was the needed malformed-page discriminator; adaptations in progress before #1836 restack
- Update 2026-07-28: all four implementation commits restacked on #1836; task 2.1 repository work is landed and its deploy/drain/fence proof remains the next runtime dependency
- Update 2026-07-28: exact #1836-based Opus review found no forgery or authority defect; three isolated regressions remain for chain digest, pagination key closure, and terminal ordinal before approval
- Update 2026-07-28: targeted Opus rerun killed the full requested 21-mutation battery plus the three added guards; count reconciliation, repository database-id type, and oracle literal were the final isolated survivors and now have direct regressions
- Update 2026-07-28: bounded Opus rerun killed all 34 requested mutations and rejected 11 concrete forgeries; expanded sweep found six deeper receipt-shape guards without isolated tests, now pinned in one final schema/completeness pass
- Update 2026-07-28: exact semantic head `c95876fe` received Opus 5 APPROVE; every named mutation died, all 45 concrete forgery probes were rejected, and no correctness or authority defect remained

## 2026-07-29 15:00 - create repair-synthesis-checklist

- Provider: `drain-20260729-145600-e75271`
- Branch: `drain/20260729-145600-e75271/repair-synthesis-checklist`
- Lane state: Active lane
- Worktree: `C:/Users/Jonathan/Projects/wf-drain-20260729-145600-e75271`
- STATUS/Issue/PR: `Repair stale synthesis-checklist assertion`; PR pending
- PLAN refs: no architectural change; test-only expectation repair
- Purpose: align one stale ledger assertion with canonical handle retirement
- _PURPOSE.md: `C:/Users/Jonathan/Projects/wf-drain-20260729-145600-e75271/_PURPOSE.md`

## 2026-07-29 17:25 - create independent-targets-handoff-5.2

- Provider: `drain-20260729-171925-6b1b07`
- Branch: `chore/drain-20260729-171925-6b1b07-recovery`
- Lane state: Active lane
- Worktree: `C:/Users/Jonathan/Projects/wf-drain-20260729-171925-6b1b07-recovery`
- STATUS/Issue/PR: `independent-full-platform-targets recovery slice 5.2`; PR pending
- PLAN refs: Daemon Platform; Security Model; External Effects and Handoffs
- Purpose: verify and fold back the already-implemented task 5.2 authority/evidence contract without entering deferred verification transport or disputes.
- _PURPOSE.md: `C:/Users/Jonathan/Projects/wf-drain-20260729-171925-6b1b07-recovery/_PURPOSE.md`
- Memory refs: task 5.2 landing note at `cf8a03f5`; PR #1876 boundary foldback
- Related implications: tasks 5.3 and 5.5-5.7 remain blocked and out of scope.
- Idea feed refs: none

## 2026-07-29 18:15 - land independent-targets-handoff-5.2

- Provider: `drain-20260729-171925-6b1b07`
- Branch: `chore/drain-20260729-171925-6b1b07-recovery`
- Lane state: Landed; local worktree retained through foldback merge
- Worktree: `C:/Users/Jonathan/Projects/wf-drain-20260729-171925-6b1b07-recovery`
- STATUS/Issue/PR: claim retired; implementation PR #1884 merged as `22bbb0a7`
- Verification: 82 focused tests passed; all 28 handoff mutations went red; strict OpenSpec validation passed on Windows, 2026-07-29

## 2026-07-29 18:25 - reopen independent-targets-handoff-5.2

- Provider: `drain-20260729-171925-6b1b07`
- Branch: `chore/drain-20260729-171925-6b1b07-recovery`
- Lane state: Active corrective lane; implementation PR #1884 and premature foldback PR #1886 merged
- Worktree: `C:/Users/Jonathan/Projects/wf-drain-20260729-171925-6b1b07-recovery`
- STATUS/Issue/PR: task 5.2 reopened locally after exact-`22bbb0a7` independent review found two High blockers and one Medium gap
- Pickup: add failing actor/run-authority, receipt-success replay, lifecycle-read, and positive-bound tests before repair; preserve plugin parity
- Recovery: `d3bcac92` independently approved; 130 focused tests pass, 28 mutations go red, strict OpenSpec 59/59, core/plugin parity clean; claim retires with PR #1888

## 2026-07-29 17:00 - land repair-synthesis-checklist

- Provider: `drain-20260729-145600-e75271`
- Branch: `drain/20260729-145600-e75271/repair-synthesis-checklist`
- Lane state: Landed; local worktree retained through foldback merge
- Worktree: `C:/Users/Jonathan/Projects/wf-drain-20260729-145600-e75271`
- STATUS/Issue/PR: `Repair stale synthesis-checklist assertion`; implementation PR #1881 merged as `9514f938`
- Verification: `python -m pytest tests/test_universe_server_ledger.py -q` — 20 passed on Windows, 2026-07-29

## 2026-07-29 20:45 - enforce drain review before merge

- Provider: `drain-20260729-194051-a81d12`
- Branch: `chore/drain-exhaustion-20260729-a81d12`
- Lane state: Draft PR #1896 open; STATUS claim retired in the branch pending merge
- Worktree: `C:/Users/Jonathan/Projects/wf-drain-exhaustion-20260729-a81d12`
- STATUS/Issue/PR: resolves the 2026-07-29 P1 review-order concern; draft PR #1896 awaiting final-head receipt and CI
- Purpose: require a current exact-head review receipt in both auto-enrollment and the already-required `policy` check
- Review: fresh-context fallback APPROVE at `9f0e868f`; final foldback-head review still required before ready-for-review
- Verification: 174 focused/full drain tests, Ruff, workflow parsing, and strict OpenSpec validation passed on Windows, 2026-07-29
- Publish/cleanup: one draft PR; retain worktree until GitHub merge and controller verification
