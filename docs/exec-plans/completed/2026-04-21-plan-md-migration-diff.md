---
title: PLAN.md migration diff — full-platform architecture note
date: 2026-04-21
author: navigator
status: APPLIED — 2026-04-21 (lead ratified; all 5 changes written to PLAN.md)
source: docs/design-notes/2026-04-18-full-platform-architecture.md
---

# PLAN.md migration diff

What changes if `docs/design-notes/2026-04-18-full-platform-architecture.md`
is migrated into PLAN.md. Proposed changes only — no PLAN.md edits until
lead ratifies.

---

## Orientation: how current PLAN.md stands

PLAN.md (290 lines / ~28KB, verified 2026-04-21) is more current than the
STATUS.md concern implies. Prior sessions absorbed many sections from the
full-platform note already:

- Three-tier user model captured (Design Decisions + Multi-User section)
- GitHub demoted to export sink captured (Design Decisions line 89–90, flagged Q1 pending)
- Entry-point-based domain discovery captured (Distribution §, line 223)
- Privacy per-piece, chatbot-judged captured (Multi-User Evolutionary Design, line 277)
- Self-auditing tools pattern captured (Cross-Cutting Principles, line 33 + Design Decisions, line 103)
- Evaluation as platform-wide primitive captured (Evaluation section, line 183)
- Module layout target shape captured (Module Layout section, lines 49–68)
- Engine/domain seam captured (Engine And Domains section, lines 245–254)
- God-module decomposition tracked in Open Tensions (lines 289)

**Net:** most §2–§4 and §13–§33 material is already in PLAN.md at principle level.
The gaps are architectural specifics that belong as durable design decisions,
not implementation detail.

---

## Proposed changes

### Change 1 — Resolve Q1 (GitHub demoted) in Design Decisions

**Current PLAN.md text (lines 89–90):**
> - **GitHub as canonical shared state — under host review (Q1 in `docs/design-notes/2026-04-18-full-platform-architecture.md`).** ...

**Proposed replacement:**
> - **GitHub is an export sink, not the canonical store.** Canonical state lives in Postgres (Supabase-hosted at launch). GitHub receives a periodic flat-YAML export of public goals/branches/nodes; contributions via GitHub PR are accepted via a round-trip YAML → webhook → Postgres import path. This is a one-way-door decision (§4 of `docs/design-notes/2026-04-18-full-platform-architecture.md`) — reverting after users are collaborating in realtime requires data migration. Host approved this direction 2026-04-18.
> - **Local-first execution, git-native sync (current).** The DO Droplet self-host migration (2026-04-20) is the bridge state. Postgres-canonical replaces local-first when the control-plane backend ships.

**Why:** Q1 is resolved in the design note (§4.1 is explicit: "canonical store = Supabase Postgres"). Leaving it as "under host review" in PLAN.md creates false uncertainty for any session reading PLAN.md as design truth.

---

### Change 2 — Add real-time strategy decision

**Current PLAN.md:** nothing in System Shape or Multiplayer Daemon Platform about real-time mechanism.

**Proposed addition** (append to Multiplayer Daemon Platform section):

> **Real-time strategy — versioned rows + row-level broadcast, NOT CRDT.** User collaboration is coarse-grained: users edit *different* nodes concurrently, or edit the same node with last-write-wins + update-since-you-viewed conflicts. Comments are append-only. This does not require character-by-character CRDT (Google-Docs-style). Versioned Postgres rows + Supabase Realtime WebSocket broadcast + presence channels covers the requirement at a fraction of CRDT's complexity. CRDT adoption is an escalation path for any specific artifact that needs it later, not a baseline requirement. (Decision rationale: `docs/design-notes/2026-04-18-full-platform-architecture.md §2.2`.)

**Why:** This is a load-bearing architectural decision — adopting CRDT later would be expensive. Capturing it in PLAN.md prevents a future session from proposing CRDT without understanding the prior reasoning.

---

### Change 3 — Add backend stack selection to System Shape

**Current PLAN.md System Shape section:** ASCII diagram shows generic "FastAPI + TinyAssets Server (MCP) control plane" without naming the storage backend.

**Proposed addition** (append to System Shape section):

> **Backend stack (target):** Supabase (Postgres catalog + Realtime broadcast + Auth + S3-compatible storage). Supabase is selected because one stack covers five concerns otherwise requiring separate glue (DB, realtime, auth, RLS, object store), Postgres exit path is self-hostable without application rewrite, and Python client is first-class. Rejected alternatives: Convex (TypeScript lock-in), Firebase (pay-per-read unpredictable, no Postgres), custom realtime on small VPS (negative ROI at current scale). (Decision rationale: `docs/design-notes/2026-04-18-full-platform-architecture.md §3.2`.)

**Why:** Stack selection is a design decision, not an implementation detail. Future contributors need to understand why we chose Supabase before proposing a Firebase integration or building a custom realtime service.

---

### Change 4 — Add auth strategy to System Shape

**Current PLAN.md:** "Private chats, public actions" is captured (Design Decisions line 85) but the auth mechanism is absent.

**Proposed addition** (append to System Shape section, after backend stack):

> **Auth + identity:** GitHub OAuth as the single identity primitive at launch (covers all three tiers — chatbot user, daemon host, OSS contributor — without account stitching). OAuth 2.1 + PKCE at the MCP edge (MCP spec 2025-11-25 mandate). Session tokens scoped per user; RLS enforces per-user visibility at the DB layer, not application layer. Native accounts (email/passkey) added when > ~15% of sign-up attempts bounce at the GitHub wall. (Design rationale: `docs/design-notes/2026-04-18-full-platform-architecture.md §7`.)

**Why:** Auth strategy constrains several downstream decisions (tier migration, RLS policy shape, MCP connector OAuth flow). Belongs in PLAN.md as a durable design decision.

---

### Change 5 — Update Multiplayer Daemon Platform section (thin → richer)

**Current PLAN.md Multiplayer Daemon Platform section (4 lines):** captures goal and principle but not the host-pool registry or daemon visibility model.

**Proposed addition** (append to the section):

> **Host pool registry:** every daemon host declares capabilities (node types, LLM models, price), visibility (`self` / `network` / `paid`), and heartbeat state. The control plane holds this registry; daemons are execution-tier, not control-plane. Zero daemons required for node/branch/goal authoring — daemon hosting is opt-in at any time after signing up. (See `docs/design-notes/2026-04-18-full-platform-architecture.md §5` for the full dispatch flow and multi-spawn policy.)

**Why:** The "zero daemons required for authoring" principle (requirement 2 from §1 of the note, the core reason the phased plan was rejected) is not currently explicit in PLAN.md. It's a high-stakes architectural constraint.

---

## What does NOT migrate

The following sections of the full-platform note are implementation-detail,
operational, or domain-specific — they belong in design notes or exec plans,
not in PLAN.md:

| Section | Why not PLAN.md |
|---|---|
| §5 Host's near-term Allied AP path | Operational, host-specific |
| §5 Tray UX details | Implementation detail (Distribution section covers principle) |
| §8 Moderation rate-limit numbers | Tactical; policy, not architecture |
| §9 Cost envelope + dollar figures | Operational; changes with scale |
| §10 Build sequencing steps | Exec plan territory, not design truth |
| §11 Host decisions requested | Resolved decisions absorbed above; open ones stay in STATUS.md |
| §13.1–13.4 Onboarding per tier | Copy/UX, not architecture |
| §14 Scale audit numbers | Research evidence; links to note are sufficient |
| §15–§33 Implementation details per feature | Feature-level detail; each has its own design note |

---

## Pre-conditions before PLAN.md edits

1. **Lead ratifies this diff.** Changes 1–5 are the scope.
2. **Navigator reads current PLAN.md lines 107–128 (System Shape)** immediately
   before editing to catch any interim changes not reflected here.
3. **Changes are additive or replacement of Q1-caveat language.** No section
   deletions — the goal is to bring PLAN.md current, not to compress it.

---

## Size impact

Current: 290 lines / ~28KB. Expected after these 5 changes: ~310 lines / ~30KB.
Within PLAN.md's 18KB reference target? No — PLAN.md is already 28KB, above the
AGENTS.md guideline. However AGENTS.md says the "design reference (18 KB)" as a
descriptive note, not a hard cap. These changes add ~20 lines of durable decisions
that prevent future architectural mistakes. The ROI justifies the size.
