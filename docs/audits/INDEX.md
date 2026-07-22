# Audits Index

Audits are **event records**: what was true when someone looked. They are not living documents and are not retrofitted with lifecycle status (`docs/conventions.md` § *Frontmatter `status:` field*). This index exists so they stay findable — `docs/conventions.md` requires every durable note to be linked from at least one index page.

**Read the date first.** AGENTS.md § *Truth And Freshness*: *“audit docs decay too — before dispatching prescriptions from an audit older than ~24h, run a freshness check.”* Every entry below is dated in its filename; treat the finding as `historical:` until re-verified.

Each line's text is that audit's own H1 or frontmatter title, verbatim or lightly trimmed — a title, not a verified summary of the body. 88 top-level audits + 14 in `user-chat-intelligence/` = 102 total, generated against `0bc841aa`.

## Cross-family review gates

Opposite-provider verdicts (`approve` / `adapt` / `reject`) required by AGENTS.md § *Project Skills* before research-derived work ships. Seven 2026-07-01/02 entries are raw verdict dumps with no heading; their descriptors below come from the opening verdict line.

- [`2026-07-19-spec-baseline-codex-review.md`](2026-07-19-spec-baseline-codex-review.md) — Codex cross-family review — spec-out-existing-platform baseline
- [`2026-07-02-universe-intelligence-relay-codex-review.md`](2026-07-02-universe-intelligence-relay-codex-review.md) — Codex opposite-provider review — Universe Intelligence + Relay reshape
- [`2026-07-02-soul-edit-learn-path-codex-review.md`](2026-07-02-soul-edit-learn-path-codex-review.md) — `VERDICT: adapt` — omitted-`universe_id` routing leaked another founder's serial home outside `get_status`; OKF reserved files still modeled as concept docs
- [`2026-07-02-multi-tenant-isolation-proof-codex-review.md`](2026-07-02-multi-tenant-isolation-proof-codex-review.md) — Codex review — multi-tenant concurrency/isolation proof
- [`2026-07-01-slice3-followups-resolution-codex-review.md`](2026-07-01-slice3-followups-resolution-codex-review.md) — `VERDICT: adapt` — `switch_universe` still wrote the root `.active_universe` marker for authenticated MCP callers
- [`2026-07-01-require-auth-challenge-codex-review.md`](2026-07-01-require-auth-challenge-codex-review.md) — `VERDICT: adapt` — `WWW-Authenticate` `resource_metadata` URL pointed outside the only proxied path (`tinyassets.io/mcp*`)
- [`2026-07-01-prm-scopes-and-routing-codex-review.md`](2026-07-01-prm-scopes-and-routing-codex-review.md) — `VERDICT: adapt` — `/mcp/.well-known/oauth-authorization-server` returned 404, leaving direct-discovery MCP clients without the AuthKit proxy fallback
- [`2026-07-01-personification-recs-codex-review.md`](2026-07-01-personification-recs-codex-review.md) — `VERDICT: adapt` — default MCP routing still reads and mutates root-global `.active_universe`, violating the universe-creation spec
- [`2026-07-01-founder-capabilities-authz-model-codex-review.md`](2026-07-01-founder-capabilities-authz-model-codex-review.md) — (no verdict line) — OKF conformance wrong for reserved files (`index.md` / `log.md` treated as concept docs); branch stale vs `origin/main`
- [`2026-07-01-daemon-scoped-acl-exemption-codex-review.md`](2026-07-01-daemon-scoped-acl-exemption-codex-review.md) — `VERDICT: adapt` — first-contact `get_status()` created a universe outside `_dispatch_with_ledger` (no ledger entry); stale `founder_home` rows not repaired
- [`2026-06-30-okf-soul-baseline-review.md`](2026-06-30-okf-soul-baseline-review.md) — OKF soul-baseline source review (Claude, reviewer of Codex finding)
- [`2026-06-30-founder-identity-slice4-codex-review.md`](2026-06-30-founder-identity-slice4-codex-review.md) — Codex opposite-provider review — founder-identity slice 4 (creation contract)
- [`2026-06-30-founder-identity-slice3-codex-acl-review.md`](2026-06-30-founder-identity-slice3-codex-acl-review.md) — Codex opposite-provider review — founder-identity ACL (reconcile + slice 3)
- [`2026-06-25-universe-personification-codex-review.md`](2026-06-25-universe-personification-codex-review.md) — Codex review — universe-personification
- [`2026-06-24-brain-okf-canonical-codex-review.md`](2026-06-24-brain-okf-canonical-codex-review.md) — Codex review — brain-okf-canonical-store (OKF-canonical brain store)
- [`2026-06-10-tiny-first-principles-codex-review.md`](2026-06-10-tiny-first-principles-codex-review.md) — Codex review - Tiny first-principles companions
- [`2026-06-02-in-node-enqueue-adapt-rereview.md`](2026-06-02-in-node-enqueue-adapt-rereview.md) — In-node enqueue verb — ADAPT re-review brief (Codex, round 2)
- [`2026-05-30-in-node-enqueue-codex-review.md`](2026-05-30-in-node-enqueue-codex-review.md) — Codex review gate — in-node paced enqueue verb
- [`2026-05-02-provider-context-feed-claude-review.md`](2026-05-02-provider-context-feed-claude-review.md) — Provider Context Feed + Worktree Discipline — Claude Review
- [`2026-05-02-origin-quantum-claude-review.md`](2026-05-02-origin-quantum-claude-review.md) — Origin Quantum Optional Capability Pack — Claude-family review
- [`2026-05-02-opentraces-claude-review.md`](2026-05-02-opentraces-claude-review.md) — OpenTraces Private Trace Commons — Claude-family review
- [`2026-05-02-experience-pool-claude-review.md`](2026-05-02-experience-pool-claude-review.md) — ExperiencePool + GroupEvolutionRun — Claude-family review
- [`2026-05-02-agencybench-claude-review.md`](2026-05-02-agencybench-claude-review.md) — AgencyBench Acceptance Scenario Packs — Claude-family review

## Incidents, outages, and diagnostics

Postmortems and root-cause traces. `2026-04-20-public-mcp-outage-postmortem.md` is cited directly by AGENTS.md Hard Rule 11.

- [`2026-07-15-workflow-data-volume-audit.md`](2026-07-15-workflow-data-volume-audit.md) — Audit: old `workflow-data` docker volume (19 GB) — 2026-07-15
- [`2026-04-26-restart-loop-correlation.md`](2026-04-26-restart-loop-correlation.md) — Watchdog restart-loop correlation audit
- [`2026-04-25-etc-workflow-env-mode-flip.md`](2026-04-25-etc-workflow-env-mode-flip.md) — Audit: /etc/tinyassets/env mode-flip root cause
- [`2026-04-23-p0-auto-recovery-trace.md`](2026-04-23-p0-auto-recovery-trace.md) — P0 auto-recovery trace — 2026-04-23 disk-full pattern
- [`2026-04-20-public-mcp-outage-postmortem.md`](2026-04-20-public-mcp-outage-postmortem.md) — Public MCP Outage Postmortem — 2026-04-19
- [`2026-04-19-sporemarch-c16-s3-diagnostic.md`](2026-04-19-sporemarch-c16-s3-diagnostic.md) — Sporemarch C16-S3 Revise-Loop Plateau — Diagnostic

## Architecture, refactor, and rename sweeps

- [`2026-06-24-fantasy-architecture-residue-audit.md`](2026-06-24-fantasy-architecture-residue-audit.md) — Fantasy-architecture residue audit (de-privileging plan)
- [`2026-04-28-internal-scoping-threads-abc.md`](2026-04-28-internal-scoping-threads-abc.md) — Internal-scoping Threads A/B/C — Phase 6 + fantasy_author_original deletion + R7 closure
- [`2026-04-27-project-wide-shim-audit.md`](2026-04-27-project-wide-shim-audit.md) — Project-wide shim audit (2026-04-27)
- [`2026-04-26-legacy-branding-comprehensive-sweep.md`](2026-04-26-legacy-branding-comprehensive-sweep.md) — Legacy branding comprehensive sweep — every artifact teaching old vocabulary
- [`2026-04-26-architecture-edges-sweep.md`](2026-04-26-architecture-edges-sweep.md) — Architecture edges sweep — refactor + retire candidates ("button up the edges")
- [`2026-04-25-universe-server-decomposition.md`](2026-04-25-universe-server-decomposition.md) — universe_server.py Decomposition — Phase 1 Audit
- [`2026-04-25-fantasy-shim-import-audit.md`](2026-04-25-fantasy-shim-import-audit.md) — Fantasy Shim Import Audit — Phase 0
- [`2026-04-25-engine-domain-api-separation.md`](2026-04-25-engine-domain-api-separation.md) — Engine/Domain API Separation — Phase 1 Audit
- [`2026-04-25-audit-summary-for-host-review.md`](2026-04-25-audit-summary-for-host-review.md) — Audit Summary for Host Review — Engine/Domain Separation + universe_server Decomposition
- [`2026-04-19-schema-migration-followups.md`](2026-04-19-schema-migration-followups.md) — Schema-Migration Follow-Ups Audit
- [`2026-04-19-project-folder-spaghetti.md`](2026-04-19-project-folder-spaghetti.md) — Project-Folder Spaghetti Audit
- [`2026-04-19-modularity-audit-integration.md`](2026-04-19-modularity-audit-integration.md) — Modularity Audit Integration
- [`2026-04-18-universe-server-directive-relocation-plan.md`](2026-04-18-universe-server-directive-relocation-plan.md) — #15 Mitigation Scope — `tinyassets/universe_server.py` Directive Relocation
- [`2026-04-18-rename-tree-consistency-audit.md`](2026-04-18-rename-tree-consistency-audit.md) — Rename Phase 1 Part 2 — Tree Consistency Audit

## Convergence pair-reads

Implementation-vs-design pair reads from the 2026-04-25 task set; each checks a landed implementation against the design note it claims to satisfy.

- [`2026-04-25-pair-59-resolve-canonical-convergence.md`](2026-04-25-pair-59-resolve-canonical-convergence.md) — Pair Convergence: #59 resolve_canonical ↔ #47 fallback chain + authority + #53 route-back + canonical_bindings table
- [`2026-04-25-pair-58-named-checkpoint-convergence.md`](2026-04-25-pair-58-named-checkpoint-convergence.md) — Pair Convergence: #58 named-checkpoint design ↔ #53 verdict + TypedPatchNotes + #56 sub-branch + graph_compiler + caused_regression metadata
- [`2026-04-25-pair-57-surgical-rollback-convergence.md`](2026-04-25-pair-57-surgical-rollback-convergence.md) — Pair Convergence: #57 surgical rollback design ↔ attribution-layer-specs + canary infrastructure
- [`2026-04-25-pair-55-external-pr-bridge-convergence.md`](2026-04-25-pair-55-external-pr-bridge-convergence.md) — Pair Convergence: #55 external-PR bridge ↔ #52 file_bug routing + CONTRIBUTORS.md + #48 ledger + canary spec + anti-spam invariants
- [`2026-04-25-pair-54-vs-56-convergence.md`](2026-04-25-pair-54-vs-56-convergence.md) — Pair Convergence: #54 (runner version-id bridge) ↔ #56 (run_branch surface audit)
- [`2026-04-25-pair-50-vs-56-convergence.md`](2026-04-25-pair-50-vs-56-convergence.md) — Pair Convergence: #50 (sub-branch invocation audit) ↔ #56 (BUG-005 design proposal)
- [`2026-04-25-impl-71-72-75-vs-48-convergence.md`](2026-04-25-impl-71-72-75-vs-48-convergence.md) — Implementation Pair-Read: #71 + #72 + #75 ↔ #48 contribution-ledger design
- [`2026-04-25-impl-54-65a-65b-vs-56-convergence.md`](2026-04-25-impl-54-65a-65b-vs-56-convergence.md) — Implementation Pair-Read: #65a + #65b ↔ #54 runner-version-id-bridge design

## Coordination surface and instruction files

Audits of `STATUS.md`, `AGENTS.md`, and the instruction-file set. `2026-04-28-status-md-coordination-gap.md` is the source of the `[filed: verified:]` Concern-row stamp convention.

- [`2026-04-28-status-md-coordination-gap.md`](2026-04-28-status-md-coordination-gap.md) — STATUS.md coordination gap — how 4 ChatGPT P1s went stale
- [`2026-04-28-status-md-concerns-staleness-pass.md`](2026-04-28-status-md-concerns-staleness-pass.md) — STATUS.md Concerns — 4-day staleness pass (per coordination-gap §5 Rule 1)
- [`2026-04-28-rows-6-7-8-community-build-obviation-addendum.md`](2026-04-28-rows-6-7-8-community-build-obviation-addendum.md) — STATUS Concerns rows 6/7/8 — community-build obviation pass (addendum to staleness audit)
- [`2026-04-28-project-instruction-files-cross-check.md`](2026-04-28-project-instruction-files-cross-check.md) — Project-instruction-files cross-check — AGENTS / CLAUDE / LAUNCH_PROMPT / CLAUDE_LEAD_OPS
- [`2026-04-28-agents-md-rule-addition-drafts.md`](2026-04-28-agents-md-rule-addition-drafts.md) — AGENTS.md rule-addition drafts (4 candidates from cross-check audit)
- [`2026-04-19-open-flag-consolidation.md`](2026-04-19-open-flag-consolidation.md) — OPEN-Flag Consolidation — 2026-04-19 Audit
- [`2026-04-19-concerns-post-session.md`](2026-04-19-concerns-post-session.md) — STATUS.md Concerns — Post-Session Re-Triage
- [`2026-04-19-concern-triage.md`](2026-04-19-concern-triage.md) — STATUS.md Concerns — Triage

## Primitive and surface design audits

- [`2026-04-25-sub-branch-invocation-audit.md`](2026-04-25-sub-branch-invocation-audit.md) — Sub-Branch Invocation Primitive Audit
- [`2026-04-25-run-branch-surface-audit.md`](2026-04-25-run-branch-surface-audit.md) — `run_branch` Surface Audit
- [`2026-04-25-canonical-primitive-audit.md`](2026-04-25-canonical-primitive-audit.md) — Canonical-Branch-for-Goal Primitive Audit
- [`2026-04-25-audit-69-storage-auth-solo.md`](2026-04-25-audit-69-storage-auth-solo.md) — Solo Audit — #69 Storage-Layer Authority Refactor
- [`2026-04-25-audit-53-gate-route-back-solo.md`](2026-04-25-audit-53-gate-route-back-solo.md) — Solo Audit — #53 Gate-Route-Back Verdict Extension

## MCP / chatbot surface audits

- [`2026-04-28-get-status-key-level-audit.md`](2026-04-28-get-status-key-level-audit.md) — `get_status` key-level audit
- [`2026-04-25-mcp-tool-description-clarity.md`](2026-04-25-mcp-tool-description-clarity.md) — MCP tool description clarity audit — chatbot cold-read pass
- [`2026-04-25-mcp-response-size-audit.md`](2026-04-25-mcp-response-size-audit.md) — MCP Response Size Audit — build_branch / patch_branch
- [`2026-04-25-chatgpt-update-node-approval-bug.md`](2026-04-25-chatgpt-update-node-approval-bug.md) — ChatGPT Connector — Update Node Approval Bug Scoping

## Principle and strategy implication sweeps

- [`2026-04-28-commons-first-tool-surface-audit.md`](2026-04-28-commons-first-tool-surface-audit.md) — Commons-first tool-surface audit — running the 5 foundational principles against the live primitive set
- [`2026-04-27-navigator-reality-sweep-session-d.md`](2026-04-27-navigator-reality-sweep-session-d.md) — Navigator reality sweep — workflow-2026-04-27d
- [`2026-04-27-commons-first-architecture-implications.md`](2026-04-27-commons-first-architecture-implications.md) — Commons-first architecture — project-wide implications sweep
- [`2026-04-26-user-capability-axis-implications.md`](2026-04-26-user-capability-axis-implications.md) — User-capability-axis principle — implications across the project
- [`2026-04-23-navigator-full-corpus-synthesis.md`](2026-04-23-navigator-full-corpus-synthesis.md) — Navigator full-corpus synthesis — sequencing + substrate + host-independence

## External research and frontier radar

Outputs of the `external-research-implications` skill.

- [`2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md`](2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md) — Adoption audit + tracker: "New SDLC with Vibe Coding" + "Claude Code in large codebases"
- [`2026-05-02-provider-context-feed-frontier-research.md`](2026-05-02-provider-context-feed-frontier-research.md) — Provider Context Feed Frontier Research
- [`2026-05-02-frontier-repo-radar-3.md`](2026-05-02-frontier-repo-radar-3.md) — Frontier Repo Radar 3: OpenTraces
- [`2026-05-02-frontier-repo-radar-2.md`](2026-05-02-frontier-repo-radar-2.md) — Frontier Repo Radar 2: AgencyBench
- [`2026-05-02-frontier-project-radar.md`](2026-05-02-frontier-project-radar.md) — Frontier Project Radar
- [`2026-05-02-asi-evolve-architecture-implications.md`](2026-05-02-asi-evolve-architecture-implications.md) — ASI-Evolve Architecture Implications For Workflow

## Test, coverage, and acceptance-probe audits

- [`2026-04-27-probe-catalog-state.md`](2026-04-27-probe-catalog-state.md) — Acceptance probe catalog — state audit + gap analysis
- [`2026-04-25-acceptance-probe-catalog-audit.md`](2026-04-25-acceptance-probe-catalog-audit.md) — Acceptance Probe Catalog Audit
- [`2026-04-19-test-coverage-gaps.md`](2026-04-19-test-coverage-gaps.md) — Test Coverage Gaps — 2026-04-19

## Agent-team operations

- [`2026-06-23-skills-refactor-audit.md`](2026-06-23-skills-refactor-audit.md) — Workflow Skills Audit — Refactor Prep
- [`2026-04-28-agent-memory-cross-drift-sweep.md`](2026-04-28-agent-memory-cross-drift-sweep.md) — Agent-memory cross-drift sweep — contradictions, gaps, duplicates, stale refs
- [`2026-04-25-despawn-chain-protocol.md`](2026-04-25-despawn-chain-protocol.md) — Despawn Chain Protocol — Faster Roster Swaps

## Docs coherence and repo hygiene

- [`2026-04-19-pitch-vs-product-alignment.md`](2026-04-19-pitch-vs-product-alignment.md) — Pitch-vs-Product Alignment Audit
- [`2026-04-19-dirty-tree-audit.md`](2026-04-19-dirty-tree-audit.md) — Dirty-Tree Audit — 2026-04-19
- [`2026-04-19-design-note-vs-specs-coherence.md`](2026-04-19-design-note-vs-specs-coherence.md) — Design-Note vs Specs Coherence Audit

## User-chat intelligence reports

Navigator-authored reports on simulated and live user sessions, written to `docs/audits/user-chat-intelligence/` per `.claude/agents/navigator.md`. Persona mission drafts and post-session findings.

- [`2026-05-01.md`](user-chat-intelligence/2026-05-01.md) — User-chat intelligence — 2026-05-01
- [`2026-04-24-competitor-trials-sweep.md`](user-chat-intelligence/2026-04-24-competitor-trials-sweep.md) — User-Chat Intelligence Report — 2026-04-24: Competitor Trials Sweep
- [`2026-04-23-pre-dispatch-sweep.md`](user-chat-intelligence/2026-04-23-pre-dispatch-sweep.md) — User-chat intelligence sweep — pre-dispatch review of 4 paste-ready mission drafts
- [`2026-04-20-mission-draft-priya.md`](user-chat-intelligence/2026-04-20-mission-draft-priya.md) — Mission draft — Priya first-live-session (post-BUG-001/002/003 deploy)
- [`2026-04-20-mission-draft-priya-mission3.md`](user-chat-intelligence/2026-04-20-mission-draft-priya-mission3.md) — Mission draft — Priya Mission 3 (paper revision submitted + peer-referral growth loop)
- [`2026-04-20-mission-draft-priya-mission2.md`](user-chat-intelligence/2026-04-20-mission-draft-priya-mission2.md) — Mission draft — Priya Mission 2 (post-sweep reviewer-2 follow-up + repro artifact stress)
- [`2026-04-20-mission-draft-maya.md`](user-chat-intelligence/2026-04-20-mission-draft-maya.md) — Mission draft — Maya Session 2 (vocab-discipline regression + month-end real-artifact advance)
- [`2026-04-20-mission-draft-devin-mission27.md`](user-chat-intelligence/2026-04-20-mission-draft-devin-mission27.md) — Mission draft — Devin Mission 27 (post-Session-2 trust-commitment probe + Task #13 stress)
- [`2026-04-20-do-cutover-acceptance.md`](user-chat-intelligence/2026-04-20-do-cutover-acceptance.md) — User-Chat Intelligence Report — DO Cutover Acceptance Test
- [`2026-04-19-p0-uptime-canary-probe.md`](user-chat-intelligence/2026-04-19-p0-uptime-canary-probe.md) — User-Chat Intelligence Report — P0 Uptime Canary Probe
- [`2026-04-19-mission26-sporemarch-echoes.md`](user-chat-intelligence/2026-04-19-mission26-sporemarch-echoes.md) — User-Chat Intelligence Report — Mission 26 (Sporemarch + Echoes)
- [`2026-04-19-initial.md`](user-chat-intelligence/2026-04-19-initial.md) — User-Chat Intelligence Report — Initial
- [`2026-04-19-devin-session1.md`](user-chat-intelligence/2026-04-19-devin-session1.md) — User-Chat Intelligence Report — Devin Session 1
- [`2026-04-19-devin-session-2.md`](user-chat-intelligence/2026-04-19-devin-session-2.md) — User-Chat Intelligence Report — Devin Session 2
