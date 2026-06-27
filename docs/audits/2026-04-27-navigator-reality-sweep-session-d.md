---
title: Navigator reality sweep — workflow-2026-04-27d
date: 2026-04-27
author: navigator (claude-code, session d)
status: complete
audience: lead, dev, dev-2, host
load-bearing-question: Does STATUS.md reflect actual repo + provider state right now?
---

# Navigator Reality Sweep — Session d

Reconciles STATUS.md against on-disk + git state at session start `2026-04-27` (lead session d). Cross-provider context: Codex (`codex-gpt5-desktop`) and Cursor (`cursor-gpt55`) have been working concurrently; many artifacts ship outside Claude Code's visibility.

## 1. Landed since last STATUS.md write

Last STATUS.md write was bundled into commit `c9de18e` (2026-04-27 23:30 -0700, "docs: backlog burn-down execution packs", `Made-with: Cursor`). Recent history:

| sha | time | author tag | summary |
|-----|------|------------|---------|
| `c9de18e` | 23:30 | Cursor | STATUS.md, PLAN.md, deploy/cloudflare-worker docs, audits, .agents/activity.log — bulk docs hygiene + PLAN.md additions |
| `8e9de0c` | 23:21 | (Codex/CI) | CI: pass sentinel to docker smoke container |
| `020d8bf` | 23:18 | Codex | chore: add JSON claim-check output |
| `010d0bc` | 23:16 | Codex | docs: promote future backlog slices (recency+continue specs, contributors, INBOX/PIPELINE updates) |
| `dbc8a91` | 23:05 | Codex | docs: codify instruction audit follow-ups |
| `ee6a190` | 23:02 | Codex | docs: document prospective claim checks |
| `5d135ba` | 23:01 | Codex | chore: add prospective claim file check (claim_check `--check-files`) |
| `dbeed86` | 22:57 | Claude | docs: land 22 Claude-team backlog artifacts (5934 LOC: nav audits, design notes, decomp prep) |
| `ab832f4` | 22:48 | Codex | docs: tighten parallel claim coordination |
| `36d3598` | 22:47 | Cursor/Codex | docs: remove shipped-phase labels from live modules (10 files) |
| `68546ce` | 22:45 | Codex | docs: update navigator MCP terminology |
| `b096987` | 22:45 | Codex | chore: add multi-provider claim checker (`scripts/claim_check.py`) |
| `116a657` | 21:54 | Claude (lead) | wiki.py BUG-003 + BUG-018 canonical-resolution fix (verifier SHIP) |
| `584dc39` | 21:54 | Claude (lead) | exec-plan retirement (9 plans → completed/) |

Provider attribution is read off explicit `Made-with:` trailers and commit-message conventions; uncertainty in CI commits.

## 2. In-flight by other providers

| row | claimer | files (declared) | activity since claim |
|-----|---------|------------------|----------------------|
| #18 retarget sweep | dev (Claude session prior) | `tinyassets/universe_server.py` + 5 api/* + plugin mirror + ~53 tests | none in last commits — WIP preserved in worktree per prior session-wrap (87 files modified, 972 LOC residual). Awaiting resume next dev session. |
| #23 Arc B phase 2 | dev (Claude session prior) | `tinyassets/_rename_compat.py`, `tinyassets/fantasy_author/`, `tinyassets/fantasy_daemon/`, `tests/`, `tinyassets/api/runs.py` | **Files cell partially phantom** — `tinyassets/fantasy_author/` and `tinyassets/fantasy_daemon/` directories no longer exist; tree is at `domains/fantasy_*/` (post-Arc-B-phase-1 in `0cbdea9`). Real lock is `_rename_compat.py` + `tests/` + `tinyassets/api/runs.py`. |
| Autonomous burn-down | codex-gpt5-desktop | `docs/exec-plans/active/2026-04-27-autonomous-backlog-queue.md`, `docs/notes/2026-04-27-backlog-user-sim-bundle.md`, `ideas/PIPELINE.md`, `ideas/INBOX.md` | actively producing (last touch 23:28). 18 untracked artifacts on disk authored by codex tonight 23:14-23:28; codex appears to be queue-ing them for a Cursor commit pass. |
| Public endpoint docs hygiene | cursor-gpt55 | deploy/cloudflare-worker/README.md, docs/ops/{acceptance-probe-catalog, day-of-cutover, launch-readiness-checklist}.md, several audits, design-note, specs (many) | live: `c9de18e` "Made-with: Cursor" 23:30 included partial sweep of these files. Continuing. |
| Mission 10 retest | user | (host watches browser) | not in flight — placeholder for next user-sim run. |

### 18 untracked artifacts — provenance + state

All authored by `codex-gpt5-desktop` per frontmatter `author:` field and queue manifest in `docs/exec-plans/active/2026-04-27-autonomous-backlog-queue.md`. None are dev-ready in the "claim and start coding" sense — they are pre-implementation artifacts (specs, fixture packs, implementation cards, runbooks, policy notes). All link back to triaged INBOX entries and PIPELINE rows.

| file | type | purpose | gating |
|------|------|---------|--------|
| `docs/exec-plans/active/2026-04-27-autonomous-backlog-queue.md` | exec-plan | Codex's own queue manifest (item 11 = next) | self-paced |
| `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md` | exec-plan | 5-card implementation breakdown for `extensions action=my_recent_runs` + `goals action=my_recent` + `extensions action=continue_branch` | blocked by #18 lock on `tinyassets/api/runs.py` |
| `docs/exec-plans/active/2026-04-27-hyperparameter-importance-implementation-cards.md` | exec-plan | domain-skill cards | module-lane blocked |
| `docs/exec-plans/active/2026-04-27-runtime-fiction-memory-graph-restart-cards.md` | exec-plan | restart-cards thin slice for Tomás-style fiction graph | needs scope decision (fiction-domain skill) |
| `docs/specs/2026-04-27-recency-continue-fixture-pack.md` | spec | fixture pack for cards above | post-#18 |
| `docs/specs/2026-04-27-hyperparameter-importance-evaluator-node.md` | spec | inputs/outputs/errors/tests frozen | module-lane |
| `docs/specs/2026-04-27-hyperparameter-importance-fixture-pack.md` | spec | companion fixtures | module-lane |
| `docs/specs/2026-04-27-runtime-memory-graph-minimal-schema-v1.md` | spec | 4-entity-type schema (world_truth/event/epistemic_claim/narrative_debt) | needs host nod for v1 entity set |
| `docs/notes/2026-04-27-runtime-memory-graph-contradiction-policy.md` | note | proposed v1 contradiction handling (proposed_conflict + narrative_debt) | needs host nod, paired with schema spec |
| `docs/notes/2026-04-27-methods-prose-rubric-starter-pack.md` | note | content-ready wiki rubric for methods-prose evaluator (REFRAMED to community-build) | content ready, awaits Task #16-style wiki promote |
| `docs/notes/2026-04-27-cross-algorithm-parity-wiki-template.md` | note | RF-vs-MaxEnt seed + template | content ready, wiki-publish |
| `docs/notes/2026-04-27-cross-algorithm-parity-publication-checklist.md` | note | publication checklist | content ready |
| `docs/notes/2026-04-27-trust-graduation-query-pack.md` | note | SQL/dashboard pack for `pct_skip_dry_inspect_on_session_n` | observability-lane blocked |
| `docs/notes/2026-04-27-contributors-maintenance-runbook.md` | note | hygiene runbook for CONTRIBUTORS.md | OPS — could land after `dbc8a91` |
| `docs/notes/2026-04-27-agent-teams-post-uptime-scoping-checklist.md` | note | post-uptime entry-gates checklist for the agent-teams-on-Workflow scope | uptime-track gating |
| `docs/notes/2026-04-27-backlog-user-sim-bundle.md` | note | user-sim verification bundle for promoted backlog | content-ready |
| `docs/design-notes/2026-04-27-trust-graduation-observability-metric.md` | design-note | event-contract + metric definition | proposed |
| `tests/test_provider_allowlist.py` | test | Q6.3 `allowed_providers` allowlist primitive | **anomaly — see §6** |

### Anomaly: `tests/test_provider_allowlist.py`

Authored 2026-04-27 22:48; references `workflow.config.UniverseConfig` `allowed_providers` field and `ProviderRouter` filtering — **the implementation does not exist yet** (Q6.3 design note `docs/design-notes/2026-04-27-q63-third-party-provider-privacy.md` is still in the host-decision pile per STATUS Concern row). Codex appears to have written tests-first ahead of approval. Flag for lead: this test file will fail until Q6.3 ships, and `tests/` is in dev's #18 lock-set for retarget. Recommend either keep untracked until Q6.3 is greenlit + dispatched, or skip-mark with `pytest.skip("blocked on Q6.3 allowed_providers impl")`.

## 3. Stale claims to reap

`claim_check.py` reports STALE = 0. Independent verification:

- **#18 dev claim** — last commit on its lock-set (`tinyassets/api/branches.py` `65abde1`, `extensions.py` `d662249`, `engine_helpers.py` `ade38bc`) was 2026-04-27 morning/midday session. Lead's prior session-wrap explicitly preserves WIP in worktree pending dev resume. NOT stale yet (24h not exceeded; lead intent documented).
- **#23 Arc B phase 2** — last `tinyassets/_rename_compat.py` activity was 2026-04-25. Approaching staleness boundary (~50h). However, dev's #18 lock blocks this row from being touched in parallel anyway; reap would not unblock anything. Recommend leaving claimed until #18 lands.
- **Codex burn-down** — actively touching files within the last hour. Live.
- **Cursor docs hygiene** — `c9de18e` 23:30 commit IS the activity. Live.
- **Mission 10 retest (user)** — placeholder, not active claim. Skip.

**No reaping needed this sweep.**

## 4. STATUS.md edits to apply

Concrete patches the lead can apply:

### 4.a Concerns

| Concern | Edit | Reason |
|---------|------|--------|
| `[filed:2026-04-23] P0 revert-loop` | **Verify or downgrade.** Trace doc `docs/audits/2026-04-23-p0-auto-recovery-trace.md` is from filing day; commits `964bc8d` (storage observability + Lane 4 revert-loop canary, 2026-04-23) and `8aed818` (Storage layer bundle, 2026-04-24) likely landed mitigation. Add `verified:YYYY-MM-DD` once host or dev confirms daemon resume; if unresolved, keep but stamp current verification date. Currently 5 days unverified — at risk of stale-certainty per AGENTS.md "Contradictions must be downgraded immediately." |
| `[filed:2026-04-19] modularity audit flags universe_server, discovery, daemon_server` | **Edit:** strike `universe_server` per prior session note — Steps 1-11 LANDED (last `d662249` extensions extraction). Discovery + daemon_server seams remain. Reframe to `[filed:2026-04-19 verified:2026-04-27] Modularity audit: discovery + daemon_server seams remain (universe_server decomp landed Steps 1-11).` |
| `[filed:2026-04-24] Task #9 host Qs about GROQ/GEMINI/XAI in GH Actions secrets` | No edit — still pending host. Add `verified:2026-04-27` if still relevant. |
| `[filed:2026-04-28] Claude card matcher cleanup conflicts with tests/test_claude_chat_inline_dismiss.py` | **Add resolution path or clarify.** This is a pure-engineering note that should either move to a PIPELINE row or get a one-line proposed-fix sentence. Currently has no actor. |

### 4.b Work table

| Row | Edit | Reason |
|-----|------|--------|
| `#23 Arc B phase 2` Files cell | Replace `tinyassets/fantasy_author/, tinyassets/fantasy_daemon/` with `domains/fantasy_author/, domains/fantasy_daemon/` (or strip the directory references entirely if Arc B phase 2 only touches `_rename_compat.py` + `tinyassets/api/runs.py` + tests/ — see prep doc `docs/exec-plans/active/2026-04-26-decomp-arc-b-prep.md`). | The `tinyassets/fantasy_*/` paths don't exist; collision warnings on those paths are spurious. |
| Wiki #32 row | Update post-`116a657` deploy state. The row says "wiki.py fix LIVE in prod (116a657 deployed 05:04Z)" which appears to be from a prior cursor — verify via tinyassets canary or `mcp_probe.py` that 116a657 is actually live in prod (commit timestamp is 21:54 PDT 2026-04-27, not 05:04). If yes, the only outstanding items are 2 host `rm`s + BUG-018 promote. If no, raise as deploy-lag. | Stale timestamp suggests cursor copy-paste from prior session. |
| `Phase 6` row Files cell | Includes `tests/` — this overlaps every dev row. Tighten to specific test files (e.g., `tests/test_storage_db_path.py` NEW + 2-3 specific migration tests) before Phase 6 dispatches. | claim_check flags `files-overlap:tests/` as blocker. Real overlap is narrow. |
| `Claude.ai injection mitigation` row | Files cell `tinyassets/universe_server.py, tinyassets/prompts/` overlaps #18 lock. After #18 lands, the prompt-discipline edits move to the new locations (`tinyassets/api/universe.py` + extracted control_station prompt). Either defer this row's dispatch, or pre-rewrite Files cell now. | Will collide with dev's #18 sweep. |
| `R7 closure pass` | Already correctly tagged `nav-then-dev` blocked on `#25`. No change needed but note: current STATUS.md does not list a `#25` row by that ID — the dependency is to "Phase 6" / "Arc C #24". Either update R7's Depends to `#24` or rename. | ID mismatch. |

### 4.c Path line

The "Path:" line (line ~30) reads `#18 retarget sweep (live) → Arc B phase 2 → Arc C → Phase 6 db rename. universe_server.py: 14012 → 972 LOC live in main.` — accurate. Keep.

## 5. Newly dev-ready tasks

These are tasks that became dispatch-ready because (a) their gating commit landed or (b) Codex surfaced execution-ready artifacts:

| Task | Files | Why ready | Suggested provider |
|------|-------|-----------|--------------------|
| Land Codex's 18 untracked artifacts | (the 18 paths in §2) | Codex appears to be writing them for Cursor to commit. If Codex doesn't commit by next sweep, lead can ask Cursor to bundle. | cursor-gpt55 (precedent: `c9de18e` was a Cursor commit picking up Codex docs work) |
| Resolve `tests/test_provider_allowlist.py` anomaly | `tests/test_provider_allowlist.py` | Either skip-mark or remove until Q6.3 lands | dev (small, 5 min) |
| `#24 Arc C` env-var deprecation aliases | `tinyassets/storage/__init__.py` | `dev-ready` per row, blocked only by `#23`. After #23 phase 2 lands, this is single-file. | dev |
| Recency + continue_branch primitives (post-#18) | per implementation cards `docs/exec-plans/active/2026-04-27-post-18-recency-continue-implementation-cards.md` | Specs + fixtures + cards all frozen. Becomes immediately dev-ready the moment #18 lands. | dev |
| `run_branch resume_from=<run_id>` param | `tinyassets/api/runs.py`, `tests/` | F2 ACCEPTED 2026-04-28; single param add. Gated only by #18 lock. | dev (queue post-#18) |
| Methods-prose rubric wiki promote | wiki | Content ready in `docs/notes/2026-04-27-methods-prose-rubric-starter-pack.md`. Just needs post-#16-style promote. | navigator (small) |
| Cross-algorithm parity wiki publish | wiki | Template + checklist + RF-vs-MaxEnt seed all landed. | navigator (small) |
| CONTRIBUTORS maintenance runbook adoption | docs ops | Runbook landed 23:24. Lead can wire into AGENTS.md cross-ref or tooling. | trivial doc-only |

Nothing is "claim now and start coding" because every code-track row is gated by #18 in dev's lock-set. The dev queue post-#18 IS substantial: recency, continue_branch, resume_from, allowed_providers (Q6.3), Phase 6, hyperparameter_importance.

## 6. Concerns to downgrade or close

| Concern | Recommendation |
|---------|----------------|
| `[filed:2026-04-23] P0 revert-loop` | **Re-verify, do not delete.** Mitigations landed (`964bc8d` + `8aed818`). Either: (a) ask host whether daemon has been un-paused; (b) probe live daemon state via `mcp_probe.py status`. If running clean since mitigations, downgrade to monitoring. Currently 5 days without re-verification. |
| `[filed:2026-04-19] universe_server modularity audit` | **Edit per §4.a.** Strike `universe_server`; keep discovery + daemon_server seams. |
| `[filed:2026-04-25 verified:2026-04-28] BUG-034 ChatGPT connector approval bug` | **Keep.** Verifier date already current. Two tracks (platform + OpenAI escalation) remain open per row text. |
| `[filed:2026-04-28] Commons-first audit landed: 5 findings` | **No change.** Live; F1 ungated, others tracked. |
| `[filed:2026-04-28] Internal-scoping items moved off host queue` | **Could delete.** This is meta-coordination noise — once items moved, the row provides no live state. Move detail to `feedback_dont_ask_host_internal_scoping.md` if not already there, delete row. |
| `[filed:2026-04-28] Claude card matcher cleanup conflicts with tests/test_claude_chat_inline_dismiss.py` | **Convert to Work row** with Files = `tests/test_claude_chat_inline_dismiss.py`, Depends = none, owner unassigned. It's an actionable engineering item, not a Concern. |

## 7. Cross-references verified

- `wiki_sweep_cursor.md` last sweep tick states `45 promoted (was 45), 8 drafts (was 8)` with no deltas. No new wiki sweep run this session — cursor still valid.
- `116a657` wiki.py fix is verified in repo (`tinyassets/api/wiki.py:269` `_resolve_bugs_canonical`); canonical test file `tests/test_wiki_alias_corner_cases.py` exists.
- `BUG-034` STATUS line correctly references the ChatGPT connector approval bug; cross-ref "see BUG-034" present per AGENTS.md rule.
- `BUG-003` and `BUG-018` are still in host-action queue as documented.

## 8. Summary for lead

State is healthy; multi-provider concurrency is working as designed. Codex is producing pre-implementation artifacts faster than Cursor can commit them, which is fine. Dev's #18 lock is the binding constraint — at least 6 high-value rows queue behind it. Recommend lead:

1. Ask Cursor (or claim directly) to bundle-commit the 18 untracked artifacts so STATUS+disk align.
2. Apply the §4.a Concern edits (verify P0 + universe_server strike).
3. Apply the §4.b Files-cell tightenings on rows #23 and Phase 6.
4. Resolve the `test_provider_allowlist.py` ahead-of-impl anomaly (skip-mark or remove).
5. Hold dev queue ready: recency + continue_branch + resume_from are all spec-frozen and dispatch-ready the moment #18 lands.

No host blockers added by this sweep. Existing host pile (Q6.3 dispositions, Mark-branch canonical, primitive-set proposal §7, A.1 fantasy_daemon §7, Phase 6 §7) unchanged.
