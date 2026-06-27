---
title: Engine primitive substrate — what the engine guarantees the tool surface depends on
date: 2026-04-26
author: navigator
status: active
companion:
  - docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md (PRIMARY — user-facing tool surface; this doc is the substrate-layer answer to the same question)
  - project_minimal_primitives_principle (the rule applied at this layer too)
  - PLAN.md (canonical architecture; this note crystallizes its substrate primitives)
  - AGENTS.md "Engine and Domains" section
load-bearing-question: What is the irreducible set of engine operations that domain skills + the MCP tool surface depend on, such that any future feature can be composed on top without growing the substrate?
audience: future contributors, skill authors, engine-internal devs
---

# Engine primitive substrate

## §0 — Frame

The primary primitive-set proposal (`2026-04-26-minimal-primitive-set-proposal.md`) answers "what's the fewest set of TOOLS the user composes?" — that's the user-facing answer. This companion answers a related but distinct question:

> **What's the fewest set of ENGINE operations that domain skills + the tool surface compose on top of, such that any future feature is composable from the same substrate?**

Different audience: tool surface = chatbot UX; engine substrate = developer/contributor design. Different design pressure: tool surface optimizes for user cognition (5 verbs); engine substrate optimizes for compositional power (do anything domain skills need). They share one principle (`project_minimal_primitives_principle` — fewest building blocks that compose everything imaginable) applied at two layers.

**Per AGENTS.md "Engine and Domains" + PLAN.md §"Engine And Domains":** the engine is goal-agnostic. Domain skills (fantasy_daemon, allied-ap accounting, scientific computing) live in `domains/<domain>/` and depend ONLY on engine substrate. If a domain needs something the substrate doesn't provide, ONE OF: (a) the substrate gains a primitive (rare — irreducibility test required), (b) the domain extends the substrate locally (acceptable — domain code), (c) the domain composes from existing substrate (preferred).

This note answers: what's the substrate that lets the domain layer NEVER need to reach into engine internals?

---

## §1 — The proposed irreducible 8 (engine substrate)

After auditing the codebase + tracing what domain skills + the 7 current MCP tools actually call into:

| # | Substrate primitive | What it owns | Why irreducible |
|---|---|---|---|
| **E1** | **Graph compile + execute** | Build a `StateGraph` from typed-state nodes + edges + reducers; compile with checkpointer; run to completion or interrupt. | TinyAssets IS LangGraph's StateGraph at heart. Domain skills declare nodes; engine compiles + runs. Can't be smaller — this is the core abstraction. |
| **E2** | **Typed state + reducer** | TypedDict state shapes; `Annotated[list, operator.add]` reducers; per-key state aggregation. | Hard Rule per AGENTS.md. Without typed state the graph compile is meaningless. |
| **E3** | **Persistent checkpoint** | SqliteSaver-backed checkpoint at every step; thread-scoped; resumable. | Without this, no run survives daemon restart, no human-in-loop interrupt works, no observability of historical runs. The persistence layer IS the leverage browser-only users get from the platform. |
| **E4** | **Provider routing** | Provider abstraction (Claude / Codex / OpenAI / Gemini / Groq / Ollama); per-call routing; fallback chain; cost accounting. | TinyAssets' promise to domain skills: "you say 'call provider', engine picks the right one." Domain skills MUST NOT hardcode a provider. |
| **E5** | **Retrieval (hybrid)** | HippoRAG + LanceDB + RAPTOR + agentic search router. Domain-agnostic interface; domain provides the corpus. | Long-horizon work needs context retrieval. Without this primitive, every domain reinvents memory + retrieval. |
| **E6** | **Evaluator** | First-class typed `Evaluator` registration + invocation. User-callable per `project_platform_responsibility_model`. Returns score + rationale; never auto-runs as gate. | The platform's scalability advantage browser-only users can't replicate alone (per primary doc §2). Substrate primitive that the user-facing `evaluate` tool wraps. |
| **E7** | **Catalog (branch / node / goal / bid)** | Git-native YAML catalog; CRUD for `BranchDefinition`, node registrations, `Goal`, `NodeBid`. The shared-knowledge layer's persistence. | `commons` and `workflow` tool primitives ride on top. Without catalog, no cross-user collaboration, no fork, no remix. |
| **E8** | **Dispatcher (request → claim → run)** | The general-purpose request queue + claim pattern. Bug-investigation, paid-market, goal-pool, scheduled-runs all use it. | Per `project_bug_investigation_general_dispatch`: same primitive supports all request types. Without dispatcher, every request type reinvents queue + claim + retry. |

**That's it. Eight.** Every current platform feature + every domain skill operation composes from these 8.

### §1.1 — How current code maps to E1-E8

| Substrate primitive | Canonical implementation modules |
|---|---|
| E1 Graph compile + execute | `tinyassets/graph_compiler.py` (2126 LOC), `tinyassets/branches.py` (BranchDefinition models), `tinyassets/runs.py` (run orchestration), domain `graphs/*.py` |
| E2 Typed state + reducer | `tinyassets/branches.py` (state field schemas), domain `state/*.py` modules (e.g. `domains/fantasy_daemon/state/scene_state.py`) |
| E3 Persistent checkpoint | `tinyassets/checkpointing/sqlite_saver.py`, `tinyassets/storage/__init__.py` (SQLite resolution) |
| E4 Provider routing | `tinyassets/providers/router.py`, individual `tinyassets/providers/*.py` modules |
| E5 Retrieval | `tinyassets/retrieval/router.py`, `tinyassets/retrieval/agentic_search.py`, `tinyassets/knowledge/*` (HippoRAG + KG), `tinyassets/memory/*` (RAPTOR + scoping) |
| E6 Evaluator | `tinyassets/evaluation/*` (structural / process / editorial), `tinyassets/api/evaluation.py` (dispatch) |
| E7 Catalog | `tinyassets/catalog/*`, `tinyassets/branches.py` (model layer), `tinyassets/api/branches.py` (CRUD via MCP) |
| E8 Dispatcher | `tinyassets/dispatcher.py`, `tinyassets/scheduler.py`, `tinyassets/branch_tasks.py`, `tinyassets/bid/*`, `tinyassets/producers/*` |

**Total LOC enclosed by these 8 primitives: roughly the entire `tinyassets/` engine tree (~64k LOC).** Per `project_engine_domain_api_separation`: ~45 engine routes + 6 domain routes = 51 total entry points. The 8 substrates organize that 51.

### §1.2 — What's NOT in the 8

Things that LOOK substrate but are actually compositions:

- **MCP tool surface** (`tinyassets/api/*`) — composition layer over E1-E8. Implements `workspace`, `workflow`, `run`, `evaluate`, `commons` per primary doc §2. NOT substrate.
- **HTTP API** (`fantasy_daemon/api.py`) — composition over E1-E8 via FastAPI; same shape as MCP surface, different wire protocol. NOT substrate.
- **Sandbox / isolation** (`tinyassets/sandbox/`, `tinyassets/node_sandbox.py`) — composition over E1 + E4 + node-software-capabilities concept. NOT substrate (it's an execution-policy layer).
- **Soul + identity + attribution** (`tinyassets/identity.py`, `tinyassets/attribution/`, `tinyassets/contribution_events.py`) — domain-of-collaboration concepts; ride atop E7 (catalog) + E2 (state). NOT substrate.
- **Evaluator KINDS / RUBRICS** — domain-specific evaluator types (`structural`, `editorial`, `process`, future `prose-versions`, `prose-reproducibility`) are CATALOG ENTRIES atop E6. The substrate is the Evaluator interface; specific kinds are content.
- **Daemon orchestration** (`tinyassets/daemon_server.py`, `tinyassets/cloud_worker.py`, `tinyassets/desktop/launcher.py`) — composition layer. Picks work from E8, runs E1, persists via E3, settles via E7. NOT substrate.

This list is just as important as the 8 primitives. Anything claiming to be substrate that's actually a composition shouldn't grow the substrate count.

---

## §2 — Substrate stability + collapse trajectory

### §2.1 — What changes when MCP roadmap features ship

The 8 substrate primitives don't change with MCP capability additions. What changes is the TOOL SURFACE LAYER's composition over them:

| MCP capability | Substrate that changes | What evolves |
|---|---|---|
| Resources | E7 (catalog) becomes browseable as MCP `resources` | Tool layer change, not substrate. |
| Prompts | Tool layer surfaces `branch_design_guide` etc as `prompts` | Tool layer change. |
| Sampling | E1 + E4 — server-initiated LLM call during graph execution | Substrate INTERPRETATION richer (provider router can be invoked mid-run by node), but primitive set unchanged. |
| Elicitation | E1 — node mid-execution can pause + ask user via MCP | Same — interpretation enriches, primitives unchanged. |

**The 8 substrate primitives are spec-stable.** Roadmap features add EXPRESSIVE POWER inside existing primitives, not new primitives.

### §2.2 — What changes when capability tier shifts

Per `project_user_capability_axis`, the gap between browser-only and local-app collapses over time. Substrate impact:

- **E1-E5** (graph, state, checkpoint, provider, retrieval) — TIER-INDEPENDENT. Same primitives serve both tiers. Browser users compose via cloud daemon claiming; local-app users compose via local daemon. Substrate doesn't see the difference.
- **E6** (evaluator) — same; user-callable from either tier.
- **E7** (catalog) — same; git-native catalog works equivalently for both (browser users via MCP, local-app via direct git).
- **E8** (dispatcher) — same; tier-agnostic.

**Substrate is tier-portable. Tool surface is the place where tier difference shows up** (`host` primitive only meaningful for local-app, etc.).

---

## §3 — Tool-surface ↔ substrate mapping

To prove the 5+2 tool primitive set composes ENTIRELY from the 8 substrates:

| Tool primitive (per primary doc) | Substrate composition |
|---|---|
| `workspace` | E7 (catalog: list universes / branches) + E3 (state: read checkpoints) + E2 (typed state inspection) |
| `workflow` | E7 (catalog CRUD) + E2 (declare typed state schema) + E1 (compile graph + register node) |
| `run` | E1 (execute graph) + E3 (checkpoint each step) + E4 (provider routing during run) + E8 (queue if dispatched) + E5 (retrieval inside nodes) |
| `evaluate` | E6 (evaluator interface) + E5 (retrieval for context) + E7 (gate-claim records) |
| `commons` | E7 (catalog of public branches / goals / bids / wiki) + E8 (request queue for cross-user dispatch) + attribution layer atop E7 |
| `host` (local-app) | E8 (claim incoming requests) + E7 (settle ledger entries) + E1 (run claimed work) |
| `upload` (local-app) | E7 (write to catalog) — that's it; just a file→catalog adapter |

**Every tool primitive composes from 1-5 substrates. No tool requires a new substrate.** This validates the 8 as sufficient.

If a future tool surface change required a 9th substrate, the irreducibility test should run: is this irreducible (a new fundamental capability) or composable from existing 8? If composable, don't add. If irreducible, the new tool gets its own design note + arc.

---

## §4 — Validation: domain skill compositions

Per AGENTS.md: domain skills depend ONLY on substrate, never on engine internals. Walk through each domain's substrate dependency:

### §4.1 — `domains/fantasy_daemon/`

- Declares nodes (`phases/orient.py`, `phases/draft.py`, etc.) — uses E2 (typed state) + E1 (graph node interface) + E4 (provider for prose generation)
- Declares evaluators (`eval/criteria.py`) — uses E6
- Stores world state (`state/world_state_db.py`) — uses E3 (SQLite checkpoint shape)
- Retrieves canon (`phases/_provider_stub.py` calls into knowledge layer) — uses E5

**Substrate footprint: E1, E2, E3, E4, E5, E6.** Doesn't use E7 directly (catalog is engine-side); doesn't use E8 directly. Pure composition over 6/8 substrates.

### §4.2 — Hypothetical `domains/allied_ap/` (Maya's accounting domain)

Per primary doc §6.4 + Maya's persona:
- Declare invoice extraction nodes — E2 + E1 + E4 (provider for OCR/extraction)
- Declare CSV-format transformer node — E2 + E1
- Declare Sage-50-import evaluator — E6 (does the CSV match Sage schema?)
- Store vendor → vendor-ID mapping (cross-month consistency) — E3
- Wiki-share extraction patterns with other AP teams — E7 (catalog) + E5 (retrieval if patterns are searchable)

**Substrate footprint: E1, E2, E3, E4, E5, E6, E7.** No new substrate needed.

### §4.3 — Hypothetical `domains/scientific_computing/` (Priya's domain)

- Declare MaxEnt / BIOCLIM / RF nodes — E1 + E2 + E4
- Sensitivity-sweep dispatch — E8 (request queue for parallel fits)
- AUC / repro-eval — E6
- Methods-paragraph generation — E1 + E4 (composition of LLM nodes)
- Repro-script artifact bundling — E3 (state contains paths) + E7 (catalog tracks artifact URLs)

**Substrate footprint: all 8.** Worth noting: Priya's domain is the highest substrate-utilization persona — exercises the full surface. That's a design validation: ANY domain demanding scientific rigor uses every substrate.

### §4.4 — Hypothetical `domains/customer_support/` (e.g. ticket auto-triage)

- Declare classify + route + draft-reply nodes — E1 + E2 + E4
- Customer-history retrieval — E5
- Reply-quality evaluator — E6
- Persistent ticket state across days — E3
- Cross-team shared classification rubrics — E7 (commons-side catalog)

**Substrate footprint: 7/8** (skips E8 unless tickets get queued cross-team).

**Net result: every realistic domain composes from the 8 substrates with no extension to the engine.** That's the test of irreducibility — if a domain needed primitive #9, the substrate is incomplete. None do.

---

## §5 — What this means for future scoping

When a contributor proposes a new feature, two questions:

1. **Is this a substrate change** (modifies one of E1-E8) or a composition (adds a tool / spec / domain skill atop)? If composition, no substrate review needed; just the tool/domain review.
2. **If substrate change:** does it modify one of the 8 (acceptable — substrate evolves) or propose a 9th primitive (high bar — irreducibility test required)?

**Examples of substrate changes that are acceptable:**
- Add a new provider to E4's router (just registering a backend). Not a new primitive; expands an existing one.
- Add a new retrieval algorithm to E5 (e.g. semantic-similarity-via-graph). Same primitive, expanded coverage.
- Add a new evaluator interface mode to E6 (e.g. streaming evaluation). Same primitive.

**Examples of substrate changes that propose a 9th and need scrutiny:**
- "We need a real-time message bus" — is this irreducible, or composable from E8 (dispatcher) + E3 (state)?
- "We need a global event log" — is this irreducible, or composable from E7 (catalog) + E3?
- "We need a content-moderation primitive" — almost certainly composable from E6 (evaluator) + community rubrics.

The 8 are the bar. Adding to it means demonstrating composition from existing 8 fails.

---

## §6 — Recommendations for engine design discipline

1. **Domain skills don't reach into `tinyassets/<engine-internal>/` directly.** They depend only on the public surface of E1-E8. Per `project_engine_domain_api_separation`, this is already a stated principle; this note crystallizes the substrate that makes it concrete.

2. **The 8 substrate modules have stable public APIs.** Any breaking change to E1-E8's public surface is a major version bump for the platform. Domain skills depend on this contract.

3. **Composition layers (MCP tool surface, HTTP API, sandbox, daemon orchestration) are NOT substrate.** They evolve faster. Tool-surface consolidation per primary doc §5 is a composition-layer change, not a substrate change.

4. **Substrate audit cadence:** every quarter, sweep new substrate proposals and confirm none have crept in disguised as compositions. The shim audits already do this for shim debt; this would be the parallel for substrate growth.

5. **Future substrate evolution candidates** (acceptable per §5):
   - E1: support distributed graph execution (multi-node graph spans multiple machines via dispatcher).
   - E5: integrate `MemOS` / `LightRAG` patterns from `docs/design-notes/2026-04-09-memory-graph-research-brief.md` if benchmarks support adoption.
   - E6: add streaming-evaluator mode when MCP sampling lands.
   - E8: add scheduled-trigger primitive (cron-style) — currently this is a separate `tinyassets/scheduler.py` that subscribes to E8; could merge.

These are evolutionary refinements, not new primitives.

---

## §7 — Decision asks for the lead → host

1. **Confirm the 8 substrate primitives** as the engine's irreducible set? Useful as a stated contract for future contributors.
2. **Confirm the substrate-vs-composition distinction** as a design discipline? Adds a review gate when someone proposes substrate changes.
3. **Should this be canonicalized in PLAN.md** as a §"Substrate primitives" section, or stay as a design note? Recommend canonicalize — the 8-primitive contract is design truth per AGENTS.md.
4. **Substrate-audit cadence** — quarterly per recommendation? Lower frequency? Event-driven only?

---

## §8 — Cross-references

- **PRIMARY:** `docs/design-notes/2026-04-26-minimal-primitive-set-proposal.md` — the user-facing tool surface (5+2). This note is the substrate that the tool surface composes on top of.
- `project_minimal_primitives_principle` — the rule applied at both layers (this is the engine-layer application).
- `project_engine_domain_api_separation` (memory) — the principle this note crystallizes.
- AGENTS.md "Engine and Domains" section
- PLAN.md §"Engine And Domains"
- `docs/audits/2026-04-25-engine-domain-api-separation.md` — engine/domain seam audit (~45 engine + 6 domain routes)
- `docs/design-notes/2026-04-26-fantasy-daemon-unpack-arc.md` — A.1 unpack arc that ratifies this seam
- `docs/design-notes/2026-04-09-memory-graph-research-brief.md` — E5 retrieval substrate evolution
- `tinyassets/graph_compiler.py` (E1), `tinyassets/checkpointing/` (E3), `tinyassets/providers/` (E4), `tinyassets/retrieval/` + `tinyassets/knowledge/` + `tinyassets/memory/` (E5), `tinyassets/evaluation/` (E6), `tinyassets/catalog/` (E7), `tinyassets/dispatcher.py` + `tinyassets/scheduler.py` + `tinyassets/branch_tasks.py` (E8) — canonical homes for the 8 substrates
