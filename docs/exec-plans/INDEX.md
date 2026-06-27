# Execution Plans Index

Execution plans are for ideas that are too large or risky for a single board
row but should still be driven to a shipped outcome.

## Active

- [active/README.md](active/README.md)
- [active/2026-04-09-runtime-fiction-memory-graph.md](active/2026-04-09-runtime-fiction-memory-graph.md) — Runtime fiction memory graph: scene packets, typed entities, temporal/promise/relationship/epistemic ledgers. Multi-month plan.
- [active/2026-04-19-daemon-economy-first-draft.md](active/2026-04-19-daemon-economy-first-draft.md) — Foundation scoping for the daemon economy: minimum surface where a tier-1 user posts a paid request and a tier-2 daemon claims+fulfills it end-to-end.
- [active/2026-04-19-entry-point-discovery.md](active/2026-04-19-entry-point-discovery.md) — R10 — replace `tinyassets/discovery.py` filesystem scan with `importlib.metadata.entry_points(group="workflow.domains")`. Gated on Phase 5 (R8) compat-shim removal.
- [active/2026-04-19-rename-end-state.md](active/2026-04-19-rename-end-state.md) — Author→Daemon rename **end-state spec** (Path A, atomic). Foundation classification per host's Foundation-vs-Feature rule. Supersedes the abandoned A1-D2 ladder.
- [active/2026-04-19-sporemarch-c16-s3-diagnostic-plan.md](active/2026-04-19-sporemarch-c16-s3-diagnostic-plan.md) — Pre-staged diagnostic for the C16-S3 score-plateau. Dispatch-ready when Sporemarch resumes post-Fix-E migration.
- [active/2026-04-20-selfhost-uptime-migration.md](active/2026-04-20-selfhost-uptime-migration.md) — Move MCP + tunnel origin off the host machine (cloud provider) so full uptime no longer depends on host's computer. Post-P0 host directive 2026-04-19.
- [active/2026-04-20-track-e-paid-market-wave-1.md](active/2026-04-20-track-e-paid-market-wave-1.md) — Track E Wave 1: first-draft paid-market flow on top of Track A schema (commit `98055aa`) + Track D Wave 1 host_pool client (commit `72e86a2`).
- [active/2026-04-25-file-bug-wiring.md](active/2026-04-25-file-bug-wiring.md) — `file_bug` → `bug_investigation` 3-trigger contract (forward + startup-backfill + safety-net). Helper landed; forward call site UNWIRED (verifier-2 territory); backfill + safety-net unwired.
- [active/2026-04-30-live-community-reiteration-loop.md](active/2026-04-30-live-community-reiteration-loop.md) — Wire wiki bugs -> community branches -> patch packets -> PRs -> CI/deploy -> live observation, without redesigning user-made branches.
- [active/2026-04-26-decomp-arc-c-prep.md](active/2026-04-26-decomp-arc-c-prep.md) — Arc C prep: env-var deprecation alias deletion (UNIVERSE_SERVER_BASE, WIKI_PATH). STATUS Work #24. Arc B complete; execution remains blocked on #18 shared-file locks.
- [active/2026-04-26-engine-domain-coupling-inventory.md](active/2026-04-26-engine-domain-coupling-inventory.md) — Read-only inventory of every `tinyassets/` import that reaches into `domains.fantasy_*`. Input for Task #11/#28/#29 host-review queue.
- [active/2026-04-27-autonomous-backlog-queue.md](active/2026-04-27-autonomous-backlog-queue.md) — Continuous docs/spec backlog burn-down queue for claim-safe work while core locks remain active.
- [active/2026-04-27-hyperparameter-importance-implementation-cards.md](active/2026-04-27-hyperparameter-importance-implementation-cards.md) — Hyperparameter-importance implementation cards, ready when the science-domain lane opens.
- [active/2026-04-27-memory-scope-stage-2c-flip-prep.md](active/2026-04-27-memory-scope-stage-2c-flip-prep.md) — Memory-scope Stage 2c flip checklist; date-gated until the 30-day clean watch ends on 2026-05-16.
- [active/2026-04-27-post-18-recency-continue-implementation-cards.md](active/2026-04-27-post-18-recency-continue-implementation-cards.md) — Post-#18 cards for `run_branch resume_from=<run_id>`; Recency remains retired as a platform primitive.
- [active/2026-04-27-runtime-fiction-memory-graph-restart-cards.md](active/2026-04-27-runtime-fiction-memory-graph-restart-cards.md) — Restart cards for the runtime fiction memory graph thin slice.
- [active/2026-04-27-step-11plus-retarget-sweep-roi.md](active/2026-04-27-step-11plus-retarget-sweep-roi.md) — ROI analysis for the post-Step-11 retarget sweep (audit's "~100-LOC routing shell" target). Host decision pending.
- [active/2026-05-01-host-discoverability-and-onboarding-rollout.md](active/2026-05-01-host-discoverability-and-onboarding-rollout.md) — Host discoverability and customer onboarding rollout across directories, MCP registry, no-chatbot-login users, IDE agents, and long-tail MCP hosts.

## Completed

- [completed/README.md](completed/README.md)
- [completed/2026-04-15-author-to-daemon-rename.md](completed/2026-04-15-author-to-daemon-rename.md) — Original 5-phase rename plan with shim-based back-compat. **Superseded** by `active/2026-04-19-rename-end-state.md` (Path A, atomic) per host's Foundation-vs-Feature rule.
- [completed/2026-04-16-memory-scope-stage-2b.md](completed/2026-04-16-memory-scope-stage-2b.md) — Stage 2b 1/2/3 all shipped (commits `5944ca1`, `d053468`, `e25bd3b`). STATUS now tracks Stage 2c flag flip.
- [completed/2026-04-17-author-rename-phase0-audit.md](completed/2026-04-17-author-rename-phase0-audit.md) — Phase 0 preflight DONE (commit `07b75d8`). Companion to the parent rename plan.
- [completed/2026-04-18-uptime-phase-1a-static-landing.md](completed/2026-04-18-uptime-phase-1a-static-landing.md) — Superseded by `docs/design-notes/2026-04-18-full-platform-architecture.md` (host rejected phased rollout for single-build).
- [completed/2026-04-19-author-to-daemon-rename-status.md](completed/2026-04-19-author-to-daemon-rename-status.md) — Phase 1+ delta audit + A1-D2 dispatch ladder. **Superseded** by `active/2026-04-19-rename-end-state.md` (ladder explicitly abandoned per Foundation rule).
- [completed/2026-04-19-bid-package-promotion.md](completed/2026-04-19-bid-package-promotion.md) — R2 dispatch sequence; bid surface promoted to `tinyassets/bid/` package (commit 3b83798).
- [completed/2026-04-19-compat-naming-cleanup.md](completed/2026-04-19-compat-naming-cleanup.md) — R3 dispatch sequence; `tinyassets/compat.py` deleted (commit d7a455e).
- [completed/2026-04-19-r7a-phase7-to-catalog.md](completed/2026-04-19-r7a-phase7-to-catalog.md) — R7a — Phase 7 storage moved to `tinyassets/catalog/`. Shipped (`tinyassets/catalog/{__init__,backend,layout,serializer}.py` exist).
- [completed/2026-04-19-refactor-dispatch-sequence.md](completed/2026-04-19-refactor-dispatch-sequence.md) — R-ladder dispatch plan (R1-R13). **Superseded** by post-decomp Arc B/C/Phase 6 framing in STATUS Work table; multiple Rs landed (R1 STEERING removal, R4 layer-3 rename, R5 universe_server decomp, R7 storage split).
- [completed/2026-04-19-steering-md-removal.md](completed/2026-04-19-steering-md-removal.md) — STEERING.md deleted from repo root. Three of four directives migrated to AGENTS.md / PLAN.md; replaced functionally by `notes.json`.
- [completed/2026-04-19-storage-package-split.md](completed/2026-04-19-storage-package-split.md) — R7 — `daemon_server.py` split into `tinyassets/storage/` package (accounts.py, caps.py, rotation.py, etc.). Shipped.
- [completed/2026-04-19-track-a-schema-auth-rls.md](completed/2026-04-19-track-a-schema-auth-rls.md) — Track A daemon-economy schema + auth + RLS (commits 98055aa + 029a5ec).
- [completed/2026-04-20-wiki-file-bug-test-draft.md](completed/2026-04-20-wiki-file-bug-test-draft.md) — Pre-drafted test file for Task #3. `tests/test_wiki_file_bug.py` exists (in canonical tree).
- [completed/2026-04-21-plan-md-migration-diff.md](completed/2026-04-21-plan-md-migration-diff.md) — APPLIED 2026-04-21; all 5 changes written to PLAN.md.
- [completed/2026-04-26-decomp-step-1-prep.md](completed/2026-04-26-decomp-step-1-prep.md) — universe_server.py decomp Step 1 prep (Steps 1-11 LANDED per STATUS).
- [completed/2026-04-26-decomp-step-2-prep.md](completed/2026-04-26-decomp-step-2-prep.md) — Step 2 prep.
- [completed/2026-04-26-decomp-step-3-prep.md](completed/2026-04-26-decomp-step-3-prep.md) — Step 3 prep.
- [completed/2026-04-26-decomp-step-4-prep.md](completed/2026-04-26-decomp-step-4-prep.md) — Step 4 prep.
- [completed/2026-04-26-decomp-step-5-prep.md](completed/2026-04-26-decomp-step-5-prep.md) — Step 5 prep.
- [completed/2026-04-26-decomp-step-6-prep.md](completed/2026-04-26-decomp-step-6-prep.md) — Step 6 prep.
- [completed/2026-04-26-decomp-step-7-prep.md](completed/2026-04-26-decomp-step-7-prep.md) — Step 7 prep.
- [completed/2026-04-26-decomp-step-8-prep.md](completed/2026-04-26-decomp-step-8-prep.md) — Step 8 prep.
- [completed/2026-04-26-decomp-step-9-prep.md](completed/2026-04-26-decomp-step-9-prep.md) — Step 9 prep.
- [completed/2026-04-26-decomp-step-10-prep.md](completed/2026-04-26-decomp-step-10-prep.md) — Step 10 prep.
- [completed/2026-04-26-decomp-step-11-prep.md](completed/2026-04-26-decomp-step-11-prep.md) — Step 11 prep (universe_server.py 14012 → 1771 LOC).

- [completed/2026-04-26-decomp-arc-b-prep.md](completed/2026-04-26-decomp-arc-b-prep.md) — Arc B prep: Author→Daemon rename infrastructure deletion. Completed via `0cbdea9`, `c967272`, `1ae48ef`, and `b049f0d`.
- [completed/2026-04-27-arc-b-phase-3-dispatch-card.md](completed/2026-04-27-arc-b-phase-3-dispatch-card.md) — Arc B Phase 3 deletion card. Historical dispatch record; deletion landed in `1ae48ef`.

## Legacy Planning References

- [ARCHITECTURE_PLAN.md](../../ARCHITECTURE_PLAN.md)
- [RESTRUCTURE_PLAN.md](../../RESTRUCTURE_PLAN.md)
- [BUILD_PREP.md](../../BUILD_PREP.md)
- [IMPLEMENTATION_SUMMARY_PHASE_3.md](../../IMPLEMENTATION_SUMMARY_PHASE_3.md)
- [PHASE_3_5_6_IMPLEMENTATION.md](../../PHASE_3_5_6_IMPLEMENTATION.md)
- [IMPORT_COMPATIBILITY.md](../../IMPORT_COMPATIBILITY.md)
