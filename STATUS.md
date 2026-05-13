# Status

Live steering only. **Budget 4 KB / 60 lines.** Concerns/Work = one line each; landed rows are deleted; Forever rule = 24/7 uptime with zero hosts online.

## Concerns

- **[P0 filed:2026-04-23]** Revert-loop daemon PAUSED; auto-recovery outran pruner. Trace: `docs/audits/2026-04-23-p0-auto-recovery-trace.md`.
- [filed:2026-04-22 verified:2026-04-25] `/etc/workflow/env` mode flip: Fix A landed bc079a0; host installer review pending.
- [filed:2026-04-20 verified:2026-04-27] `test_node_eval` roundtrip flake: Fix B landed 16d4823; watch ≥30d.
- [filed:2026-04-18 verified:2026-04-28] `add_canon_from_path` sensitivity: host Qs reframed by commons-first audit F3.
- [filed:2026-04-24] Task #9 host Qs: GH Actions GROQ/GEMINI/XAI secrets + rotation e2e after deploy step.
- [filed:2026-04-28] Claude card matcher cleanup conflicts with legacy connector fallback test.
- **[P1 filed:2026-04-30]** Castles II run `28479d8ddfb44488` failed `provider_exhausted` at discovery; blocks branch-run proof (BUG-038).

## Work

Path: #18 cleared 2026-05-02 -> Arc C cleared -> Phase 6 db rename cleared. universe_server.py: 14012 -> 972 LOC live in main.

Run `python scripts/claim_check.py --provider <name>` before claiming. Claim by setting Status to `claimed:<name>`.

| Task | Files | Depends | Status |
|------|-------|---------|--------|
| PR #837 / PR #828 skill-sync refactor — replace rejected design-note route with project-design brain-page/skill-loading loop guardrails; refs issue #826 + Cowork reject note. | `.github/workflows/auto-fix-bug.yml`, `scripts/provider_context_feed.py`, `tests/test_auto_fix_workflow.py`, `tests/test_provider_context_feed.py`, `pages/concepts/skill-sync-via-brain-pages.md`, `.agents/worktrees.md` | - | dev-ready |
| Phase 3 merge-readiness classifier — read-only `RiskClassedMergeReadiness` / `MergeExecutorState` first slice; no merge/approval/close/rebase mutations. | `scripts/merge_readiness.py`, `tests/test_merge_readiness.py` | PR #617 landed; Phase 0-4 consensus notes | claimed:codex-gpt5-desktop ACTIVE 2026-05-08 |
| Community loop watch false-red alignment — live run 25533591057 still red after stale-gate batch because label floods hide schedule runs and `complete`/`await-primitive-layer` skip issues count stale. | `scripts/community_loop_watch.py`, `tests/test_community_loop_watch.py` | PR #594/#597 landed | claimed:codex-gpt5-desktop ACTIVE 2026-05-07 |
| BUG-068 Phase A loop self-learning — blocked-patterns brain page + pre-claim read/evidence convention; opposite-family review needed. | `workflow/daemon_wiki.py`, `workflow/daemon_memory.py`, `tests/test_daemon_wiki.py`, docs/spec notes | BUG-049 for closed-loop trigger proof | dev-ready |
| Scorched exact-original proof - mount guard green; needs rights-cleared Kickstart + input/sound/tank-hit acceptance. | WebSite/site/static/play/scorched-tanks/licensed/kickstart-a500-1.3.rom (deployment-only; do not commit ROM) | rights-cleared Kickstart | host-action |
| OpenAI/Claude directory submission host actions - dashboard `/mcp-directory` green, domain verified, Claude UI read proof captured; ChatGPT DEV still `/mcp` as of 2026-05-02T15:37; needs directory-safe web/mobile proof after re-register, logo/publisher/legal/mature approvals, Claude form submit, final submit. | OpenAI Apps dashboard; ChatGPT dev/mobile app; Claude directory form | action-time approval for uploads/legal/final submit/custom MCP warning | host-action |
| Community loop ALIVE end-to-end 2026-05-02 — BUG-050 first successful run post-#205 claim-grace; PR #198 (auto-ship canary v0 spec) + #206 (daemon-liveness watchdog spec) design-only, ready. Next: loop-content fix (BUG-051) + auto-ship canary build-out. | docs/milestones/auto-ship-canary-v0.md, docs/specs/daemon-liveness-watchdog.md | PR #198, #206 | review/landd, .agents/uptime.log, MCP live branches fd5c66b1d87d/e019229850f9 | deploy of `d897177` | claimed:codex-loop-uptime-chatgpt |
| Daemon soul followups - flagship core routing + host review/editor. | workflow/daemon_{registry,wiki,memory}.py, workflow/dispatcher.py, workflow/api/universe.py, fantasy_daemon/api.py, tests/ | - | dev-ready |
| Enable Actions PR creation for auto-fix - repo has read-only workflow perms; permission flip needs action-time confirmation. | GitHub repo settings | PR #100/#104 show branch push works | host-action |
| R7 closure pass — items 6+7 obviated; 1-5 cover Arc B/C; 8 by #25. | docs/exec-plans/active/2026-04-19-rename-end-state.md | #25 | nav-then-dev |
| #28 domain extraction host questions — #29 decomposition is done; remaining Qs are tool shape, upload-policy placement, registration hook. | `docs/audits/2026-04-25-engine-domain-api-separation.md` | rename locks | host-review |
| Wiki #32 — loop-owned cleanup: lowercase BUG-003/023 rm + BUG-018 old-canonical cleanup. | wiki droplet + MCP | loop dev | claimed:loop-dev |
| Loop action: `rm pages/bugs/bug-003-...md` + `rm pages/bugs/bug-023-...md` (lowercase duplicates) | wiki droplet | Wiki #32 | claimed:loop-dev |
| Loop action: BUG-018 cleanup — fix old canonical before promoting/merging cleaned slug. | wiki droplet + MCP | Wiki #32 | claimed:loop-dev |
| Arch audit residual — R7 `daemon_server.py` storage split + `catalog/backend.py` service-layer inversion remain. | `docs/design-notes/2026-04-{24-architecture-audit,25-arch-audit-5-r7-split-scoping}.md` | Arc B | host-review |
| Layer-3 design session | `docs/design-notes/2026-04-23-layer-3-design-session-*.md` | host schedules | half-day |
| Fire DR drill #3 via workflow_dispatch | `.github/workflows/dr-drill.yml` | - | host or lead-with-PAT |
| Mission 10 retest | user-sim | host watches browser | claimed:user |
| Host-action: re-register `Workflow DEV` ChatGPT connector to `/mcp-directory`; verified 2026-05-02T15:37 current ChatGPT DEV points to `/mcp` and exposes legacy `get_status`. | ChatGPT Apps settings | custom MCP warning approval | host-action |
| Memory-scope Stage 2c flag — watch started 2026-04-16; earliest flip 2026-05-16. | `docs/exec-plans/active/2026-04-27-memory-scope-stage-2c-flip-prep.md` | date gate | monitoring |
| Provider/DO key exposure audit — no concrete tokens found 2026-05-01; remaining DO refs are GH secret names for DR/P0 workflows. | `deploy/*`, `.github/workflows/{dr-drill,p0-outage-triage}.yml` | host decision | host-decision |
| Site cert flip — GitHub Pages still says "certificate does not exist yet"; CF edge green via MCP canaries + in-app smoke. | - | - | monitoring |

## Next

1. **Current uptime priority 2026-05-02 22:10Z:** Community patch loop ALIVE end-to-end. Substrate stack PASS: FEAT-004 trigger receipts + FEAT-006 provider diagnostics + BUG-009 dispatcher pickup + #205 claim-grace + BUG-045A child spawn. First successful end-to-end run BUG-050 (parent dee755 + child 1cdbd3) at 21:55-21:59. Bottleneck moved from substrate to loop-content (BUG-051: stale caution language in coding_packet/release_gate prompts) + auto-ship policy authoring (PR #198 spec). PR #198 + #206 are design-only, ready to land.

2. **Five Scoping Rules now in PLAN.md** (2026-04-28): minimal-primitives / community-build-over-platform / privacy-via-community-composition / commons-first-architecture / user-capability-axis. Cross-provider source. Depth in lead memory.
3. **Decision pile awaiting host:** Tomas + A.1 unpack §7 + Phase 6 db rename + parked Q D.
4. **No-shims-ever**, platform responsibility model, and public-surface probes after DNS/tunnel/Worker/connector changes are active.
