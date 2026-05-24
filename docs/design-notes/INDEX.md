# Design Notes Index

## 2026-05-03

- [Multi-User Workflow Operating Model](2026-05-03-multi-user-workflow-operating-model.md) - **status: research.** Repository-side preservation of wiki proposal `pages/plans/multi-user-workflow-operating-model.md` / Issue #236. Captures isolation, fairness, leases, budgets, typed records, and federation-by-reference invariants for future multi-user specs; not yet canonical `PLAN.md` truth.

## 2026-04-18

- [Full Platform Architecture — No Phases, Single-Build Target](2026-04-18-full-platform-architecture.md) - **status: integrated-into-PLAN (2026-04-28).** Architectural commitments are canonical via `PLAN.md §"Full-Platform Architecture (Canonical)"`; this design note is the integrated detail surface (full reasoning + scale-audit + host-decision lineage). Host directive 2026-04-18: thousands-concurrent users, full node CRUD with zero daemons hosted, multi-user near-real-time collaboration, opt-in daemon hosting. Recommends Supabase (Postgres + Realtime + Auth + RLS + Storage), GitHub demoted to export sink, versioned rows + broadcast + presence (not CRDT), GitHub OAuth at launch. ~7-9 dev-days with two devs. 8 host Qs §11, most importantly Q1 Postgres-canonical commit.
- [Persistent Uptime Architecture — Control Plane + Data Plane](2026-04-18-persistent-uptime-architecture.md) - **SUPERSEDED 2026-04-18 by full-platform-architecture.md.** Retained as historical: phased rollout (Phase 1 thin relay → Phase 2 state migration → Phase 3 paid failover) rejected by host in favor of single-build collaborative backend.
- [NodeScope Unification — `node_scope.py` + `scoping.py`](2026-04-18-nodescope-unification.md) - 2a loader (tuple, 1 import site) vs 2b runtime (list, 14+ import sites). Keep `scoping.py` canonical; re-home 2a loader to produce `scoping.NodeScope` directly. Drop parallel `NodeScopeEntry` / local `SliceSpec` / local `ExternalSource`. ~0.5 dev-day, readers unchanged. Sequence 1–2 weeks AFTER 2c flag flip stabilizes; do not bundle.
- [Private Universes: Payload-Redacted Enforcement Under Claude.ai Chat](2026-04-18-privacy-modes-for-sensitive-workflows.md) - Chat is Claude.ai webchat (hard constraint). Tool response body is the only enforcement surface. `sensitivity_tier: public \| internal \| confidential` per-universe flag; `private_output/` tree; daemon pinned to `ollama-local`; §8 per-action redaction table (counts/opaque-IDs only, content actions REJECT with "local-only" hint); §9 tool-description nudges teach the Claude.ai agent not to infer content or accept pasted sensitive text; §7.5 universe-name aliasing for metadata mitigation. Non-retroactive. ~3–4 dev-day MVP. Allied AP path = Claude.ai chat + redacted responses + local CSV view.
- [Mission 10 Bug Scoping — Fix-Ready Pointers](2026-04-18-mission10-bug-scoping.md) - Pointers for tasks #15/#16/#17. Bug 1 (list_canon iterdir misses `canon/sources/`). Bug 2 (`DashboardMetrics.seed_from_db` line 91 sets `_evaluated=total` not `evaluated`). Bug 3 (`phase` from status.json + `staleness` from activity.log — need reconciled `phase_human` + pending_signals + time_in_phase). All in `workflow/universe_server.py` + `workflow/desktop/dashboard.py`; zero collision with rename zones.
- [Scene-Scoped KG Cleanup — `seeded_scene` Schema Expansion](2026-04-18-scene-scoped-kg-cleanup.md) - `facts.seeded_scene` exists; `entities`/`edges` don't. Fix E can only clean facts today (53 of 156 drift rows in echoes). Adds symmetric columns via additive migration; ~140 lines + tests; sequence AFTER #17 lands, before Fix E grows other dependents.
- [`add_canon_from_path` — MCP Sensitivity Metadata Research](2026-04-18-add-canon-from-path-sensitivity.md) - MCP has no shipped `sensitiveHint`; Claude Desktop approvals are tool-level not action-level. Recommendation: extract `add_canon_from_path` as its own `@mcp.tool` in the #11 MCP split + keep whitelist as real guard + set `destructiveHint` for forward-compat.

## 2026-04-17

- [Engine/Domain API Separation — ROI-First Proposal](2026-04-17-engine-domain-api-separation.md) - Task #11 split into two tracks. REST: do not extract (~1 dev-day cleanup only); MCP: yes extract via FastMCP `mcp.mount()` pattern, 3–4 dev-days after Author→Daemon rename. 7 fantasy actions move to mounted `fantasy` tool.

## 2026-04-15

- [Memory Scope — Tiered Multi-Domain Rethink](2026-04-15-memory-scope-tiered.md) - Supersedes Stage-2 proposal in `2026-04-14-memory-scope-defense-in-depth.md`. 5-tier scope (node/branch/goal/user/universe), private-universe ACL, multi-domain (fantasy/science/archaeology/corporate).
- [Node Software Capabilities — First-Class Plug-and-Play](2026-04-15-node-software-capabilities.md) - Nodes declare required software (Unreal, Ollama, etc.); host registry resolves; multi-layer security (bundled handlers → signatures → universe allow-list → bid approval → sandbox). MVP: Unreal headless builds, host-side detection, ask-approval default.

## 2026-04-14

- [Memory-Scope Defense-in-Depth](2026-04-14-memory-scope-defense-in-depth.md) - Row-level universe_id tagging for KG + vector rows as a second layer behind per-universe DB paths. Stage 1 landed; Stage 2 superseded by 2026-04-15 rethink.

## 2026-04-09

- [Seed Retrofit Overlay](2026-04-09-seed-retrofit-overlay.md) - Additive overlay that backfills the newer seed-era repo hubs, idea pipeline, execution-plan surfaces, and human-readable knowledge docs without moving current Workflow artifacts.
- [Runtime Fiction Memory Graph](2026-04-09-runtime-fiction-memory-graph.md) - Target design for turning long-run fiction memory from loose notes and prose leaves into typed world truth, event, epistemic, and narrative-debt ledgers with generated human-readable views.

## 2026-03-31

- [Science-First Architecture Refactor](2026-03-31-science-first-refactor.md) — Research synthesis for every major subsystem choice (HippoRAG, ASP, HTN, DOME, Letta memory, hybrid retrieval). Includes cross-session hybrid retrieval convergence findings.

## Build Preparation

- [BUILD_PREP.md](../../BUILD_PREP.md) — One-shot build session reference with MVP-first phase ordering, per-module gotchas, golden test strategy, and file-by-file implementation order.
