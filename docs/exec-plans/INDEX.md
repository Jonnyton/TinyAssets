# Execution Plans Index

Execution plans are for ideas that are too large or risky for a single board
row but should still be driven to a shipped outcome.

## Active

Liveness classified 2026-07-22 — see
[docs/audits/2026-07-22-exec-plan-liveness-triage.md](../audits/2026-07-22-exec-plan-liveness-triage.md).
Directory placement alone is not a liveness claim; the subheadings below are.

- [active/README.md](active/README.md)

### Verified active (`verified:2026-07-22`)

- [active/2026-07-18-distributed-execution-platform.md](active/2026-07-18-distributed-execution-platform.md) — Distributed patch-loop execution platform. `openspec/changes/distributed-execution` has 9 unchecked tasks; PRs #1505 + #1493 OPEN.
- [active/2026-04-27-memory-scope-stage-2c-flip-prep.md](active/2026-04-27-memory-scope-stage-2c-flip-prep.md) — Memory-scope Stage 2c flip checklist. STATUS.md still carries the `Memory-scope Stage 2c flag` row (`monitoring`).
- [active/2026-04-20-track-e-paid-market-wave-1.md](active/2026-04-20-track-e-paid-market-wave-1.md) — Track E Wave 1 paid-market flow. `request_inbox` is implemented in no `.py` file; STATUS carries an in-flight Wave 2 row.

### Historical provenance — frozen by design, do not edit

Each is named by its OpenSpec spec as *"Historical source of record (untouched)"*. Moving these
breaks the citing spec; see the triage audit's follow-up lane.

- [active/2026-07-08-token-architecture.md](active/2026-07-08-token-architecture.md) — → `openspec/specs/token-architecture/`
- [active/2026-07-08-track-e-price-index-and-capacity-forwards.md](active/2026-07-08-track-e-price-index-and-capacity-forwards.md) — → `openspec/specs/paid-market-price-index-and-forwards/`
- [active/2026-07-08-track-f-training-market.md](active/2026-07-08-track-f-training-market.md) — → `openspec/specs/paid-market-training/`
- [active/2026-07-08-track-g-data-commons.md](active/2026-07-08-track-g-data-commons.md) — → `openspec/specs/data-commons/`
- [active/2026-07-08-track-h-pooled-training-ownership.md](active/2026-07-08-track-h-pooled-training-ownership.md) — → `openspec/specs/pooled-training-ownership/`
- [active/2026-07-08-track-i-hardware-creation.md](active/2026-07-08-track-i-hardware-creation.md) — → `openspec/specs/hardware-creation/`
- [active/2026-07-09-boundary-layer-design.md](active/2026-07-09-boundary-layer-design.md) — → `openspec/specs/boundary-layer/`
- [active/2026-07-09-demand-side-design.md](active/2026-07-09-demand-side-design.md) — → `openspec/specs/demand-side/`

### Misfiled category — design notes / probe report, not execution plans

Belong under `docs/design-notes/` and `docs/audits/`. Referenced by
`docs/PAID-MARKET-START-HERE-2026-07-08.md`; moving needs that write-set too.

- [active/2026-07-08-production-mcp-sweep.md](active/2026-07-08-production-mcp-sweep.md) — Production MCP probe report (not a plan).
- [active/2026-07-09-brain-crawl-format.md](active/2026-07-09-brain-crawl-format.md) — Binding design note.
- [active/2026-07-09-commons-architecture.md](active/2026-07-09-commons-architecture.md) — Binding design note.
- [active/2026-07-09-cross-venue-routing.md](active/2026-07-09-cross-venue-routing.md) — Binding design note.
- [active/2026-07-09-discovery-flows.md](active/2026-07-09-discovery-flows.md) — Binding GTM design note.
- [active/2026-07-09-founder-universe-archetype.md](active/2026-07-09-founder-universe-archetype.md) — Binding design note + seeding plan.
- [active/2026-07-09-market-data-layer.md](active/2026-07-09-market-data-layer.md) — Binding design note.
- [active/2026-07-09-market-open-dynamics.md](active/2026-07-09-market-open-dynamics.md) — Binding amendment to Track E mechanics.
- [active/2026-07-09-self-marketing-archetype.md](active/2026-07-09-self-marketing-archetype.md) — Standing-goal archetype note.

### Unverifiable from the repo — liveness not established

Each row's settling evidence is named in the triage audit. Do **not** treat these as claimable
work without re-verifying the premise first.

- [active/2026-04-09-runtime-fiction-memory-graph.md](active/2026-04-09-runtime-fiction-memory-graph.md) — Multi-month ladder; partially built (`tinyassets/packets.py` exists).
- [active/2026-04-27-runtime-fiction-memory-graph-restart-cards.md](active/2026-04-27-runtime-fiction-memory-graph-restart-cards.md) — Restart cards for the same ladder.
- [active/2026-04-25-file-bug-wiring.md](active/2026-04-25-file-bug-wiring.md) — **Premise contradicted**: the plan says the forward call site is UNWIRED, but `tinyassets/api/wiki.py:2207` calls it. Triggers 2/3 unconfirmed.
- [active/2026-04-27-post-18-recency-continue-implementation-cards.md](active/2026-04-27-post-18-recency-continue-implementation-cards.md) — `resume_from` code landed (`extensions.py:288`, `runs.py:591`); live MCP verification unproven.
- [active/2026-04-19-sporemarch-c16-s3-diagnostic-plan.md](active/2026-04-19-sporemarch-c16-s3-diagnostic-plan.md) — Conditional on Sporemarch resuming; trigger never fired.
- [active/2026-04-27-hyperparameter-importance-implementation-cards.md](active/2026-04-27-hyperparameter-importance-implementation-cards.md) — Conditional on the science-domain lane opening; never opened.
- [active/2026-04-19-daemon-economy-first-draft.md](active/2026-04-19-daemon-economy-first-draft.md) — Substantively overtaken by Tracks E–I, but no doc declares the supersession.
- [active/2026-04-26-engine-domain-coupling-inventory.md](active/2026-04-26-engine-domain-coupling-inventory.md) — Self-declared read-only inventory; input to a host-review queue.
- [active/2026-04-27-step-11plus-retarget-sweep-roi.md](active/2026-04-27-step-11plus-retarget-sweep-roi.md) — Self-declared read-only ROI analysis; host decision pending.
- [active/2026-04-27-autonomous-backlog-queue.md](active/2026-04-27-autonomous-backlog-queue.md) — Codex working-process doc, not a deliverable plan.
- [active/2026-05-01-host-discoverability-and-onboarding-rollout.md](active/2026-05-01-host-discoverability-and-onboarding-rollout.md) — Seed plan; STATUS carries related but not identical `host-action` rows.

## Completed

- [completed/README.md](completed/README.md)
- [completed/2026-04-15-author-to-daemon-rename.md](completed/2026-04-15-author-to-daemon-rename.md) — Original 5-phase rename plan with shim-based back-compat. **Superseded** by `completed/2026-04-19-rename-end-state.md` (Path A, atomic) per host's Foundation-vs-Feature rule.
- [completed/2026-04-16-memory-scope-stage-2b.md](completed/2026-04-16-memory-scope-stage-2b.md) — Stage 2b 1/2/3 all shipped (commits `5944ca1`, `d053468`, `e25bd3b`). STATUS now tracks Stage 2c flag flip.
- [completed/2026-04-17-author-rename-phase0-audit.md](completed/2026-04-17-author-rename-phase0-audit.md) — Phase 0 preflight DONE (commit `07b75d8`). Companion to the parent rename plan.
- [completed/2026-04-18-uptime-phase-1a-static-landing.md](completed/2026-04-18-uptime-phase-1a-static-landing.md) — Superseded by `docs/design-notes/2026-04-18-full-platform-architecture.md` (host rejected phased rollout for single-build).
- [completed/2026-04-19-author-to-daemon-rename-status.md](completed/2026-04-19-author-to-daemon-rename-status.md) — Phase 1+ delta audit + A1-D2 dispatch ladder. **Superseded** by `completed/2026-04-19-rename-end-state.md` (ladder explicitly abandoned per Foundation rule).
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

- [completed/2026-04-19-entry-point-discovery.md](completed/2026-04-19-entry-point-discovery.md) — R10 entry-point discovery. LANDED: `tinyassets/discovery.py:55` uses `importlib.metadata.entry_points`; filesystem scan kept as documented dev fallback.
- [completed/2026-04-19-rename-end-state.md](completed/2026-04-19-rename-end-state.md) — Author→Daemon rename end-state spec. LANDED: `_rename_compat.py` + `domains/fantasy_author/` absent repo-wide.
- [completed/2026-04-20-selfhost-uptime-migration.md](completed/2026-04-20-selfhost-uptime-migration.md) — Move MCP + tunnel origin off the host machine. LANDED: production runs off-host via `deploy/compose.yml` + `deploy-prod.yml`.
- [completed/2026-04-26-decomp-arc-c-prep.md](completed/2026-04-26-decomp-arc-c-prep.md) — Arc C env-var alias deletion. LANDED: no bare `UNIVERSE_SERVER_BASE`/`WIKI_PATH` reader survives; STATUS row #24 already removed.
- [completed/2026-06-27-tinyassets-hard-rename.md](completed/2026-06-27-tinyassets-hard-rename.md) — TinyAssets hard rename. LANDED: `origin` is `Jonnyton/TinyAssets`.
- [completed/2026-07-02-universe-intelligence-relay-build.md](completed/2026-07-02-universe-intelligence-relay-build.md) — Universe-intelligence relay reshape, M1. LANDED via `b91a6b07` (PR #1437), deployed live 2026-07-15.

## Legacy Planning References

- [ARCHITECTURE_PLAN.md](../../ARCHITECTURE_PLAN.md)
- [RESTRUCTURE_PLAN.md](../../RESTRUCTURE_PLAN.md)
- [BUILD_PREP.md](../../BUILD_PREP.md)
- [IMPLEMENTATION_SUMMARY_PHASE_3.md](../../IMPLEMENTATION_SUMMARY_PHASE_3.md)
- [PHASE_3_5_6_IMPLEMENTATION.md](../../PHASE_3_5_6_IMPLEMENTATION.md)
- [IMPORT_COMPATIBILITY.md](../../IMPORT_COMPATIBILITY.md)
