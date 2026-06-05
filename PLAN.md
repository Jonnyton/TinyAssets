# Workflow — Plan

How the system should work and why. Architecture, principles, and the working theory of every module. PLAN.md is the reference everyone — humans, the auto-change loop, user chatbots — consults before building, so that the applicable module's shape is known before code is written.

For live state, see STATUS.md. For how to work on the project, see AGENTS.md. **Changes here require user approval.**

---

## Project Thesis

**Workflow is a global goals engine.** Humanity declares shared Goals — research breakthroughs, novels, prosecutions, cures, open datasets — and a legion of diverse AI-augmented workflows pursues each Goal in parallel. Branches evolve, cross-pollinate, and get ranked by how far their outputs advance up each Goal's real-world outcome-gate ladder. The value is the evolving ecology of many workflows chasing the same outcomes and learning from each other.

Fantasy writing is the first playful benchmark domain — a deliberate stress test for what design principles produce truly intelligent, iterative, self-improving agent workflows that many people can shape together. Future domains (research, journalism, scientific meta-analysis, legal, screenplay) inherit the engine, not the topology.

The real abstraction is an open workflow playground, multiplayer daemon platform, and long-horizon agent research lab. The system should maintain explicit state across many cycles; search and manage memory across multiple backends; use tools instead of one giant prompt; separate generation from evaluation from environmental truth; learn through durable artifacts, not hidden chat; coordinate across timescales, users, and daemons; let users conversationally design and reshape state architecture; connect to tracked real-world outcomes, not only text output; and evolve itself as models and community practice improve.

The system should get simpler as models improve. Every scaffold is temporary unless evals prove it still earns its keep.

---

## Scoping Rules

These five rules govern what features, primitives, and architecture get built — and what does not. They run in scoping cadence: irreducibility test first, then composition test, then privacy specialization, then architectural placement, then runtime tier targeting. Any new feature, design note, or audit recommendation must clear all five before it is shippable as platform code. Cross-provider readers (Codex, Cursor, OSS contributors): read these before proposing a new tool, action, evaluator, or primitive. Depth and worked examples live in lead memory files; PLAN.md carries the rule + why + how-to-apply only.

### 1. Minimal primitives — fewest building blocks that compose to everything

**Rule:** The platform's tool surface is a small, fixed set of fundamental primitives. Every proposed new tool answers: "is this a primitive (irreducible building block) or a convenience (composable from existing primitives)?" Conveniences don't ship. Treat tool count as a budget that should shrink, not grow.

**Why:** Every new tool taxes user cognition, chatbot tool-list metadata (more confusion + hallucination surface), maintenance cost, documentation burden, and discovery friction. The natural reflex when a user wants X is "let's add X." This rule overrides that with: "what minimal primitive(s) does the user need to compose X themselves?" Per host directive 2026-04-26.

**How to apply:** Before adding a tool, verb, action, EvaluatorKind, or any primitive: (1) is this fundamentally NEW capability, or convenience over existing capability? (2) Could you build THIS from a smaller combination of existing primitives? If yes, don't ship it — document the composition pattern instead. (3) Two primitives that overlap are one too many. (4) The decision rule for "convenience that's so useful it should ship": would a competent chatbot reliably compose this from primitives in <5 reasoning steps? If yes → community-build, no platform ship. If no (composition is fragile, requires nondeterministic reasoning, or hits a structural gap) → THAT gap is the actual primitive worth shipping. See `composition-patterns` wiki page for a cataloged set of chatbot-built compositions over the canonical primitive surface.

Depth: lead memory `project_minimal_primitives_principle.md`.

### 2. Community-build over platform-build

**Rule:** When a feature is proposed, the FIRST question is "could the community evolve this?" — not "should we build this?" Platform-build is the fallback, not the default. Imagine the implementation; sketch how a chatbot would compose it from existing primitives + wiki rubrics + remix material; if that sketch works, don't ship platform code.

**Why:** Workflow's product soul is users + chatbots evolving the system through wiki + remix + autoresearch. Platform-shipped primitives are scarce, intentional, and expensive — they crowd out community evolution and lock users into our taste. Community-buildable features compound: every new primitive composition becomes a remixable artifact other users discover and extend. Platform-shipped features are frozen at ship date; community-evolved features iterate continuously across thousands of remixes.

**How to apply:** Imagine the implementation first. Then ask: could the user's chatbot easily compose this from existing primitives (workflow nodes, evaluators, branches, gates, autoresearch, wiki content)? If yes → don't ship as platform primitive; surface the community-build path in the design note + idea triage. If no (structural gap) → identify the gap precisely, ship the smallest primitive that closes it, not the policy. Platform-build is justified only when the gap is structurally impossible to compose around, OR the platform-shipped version unblocks 10x more community evolution than it crowds out.

Depth: lead memory `project_community_build_over_platform_build.md`.

### 3. Privacy + threat-model patterns are community-build

**Rule:** Privacy mode is a special case of rule 2. Do NOT ship privacy as platform primitives (sensitivity_tier flags, private_output/ trees, server-side response redactors, threat-model presets, pre-baked HIPAA/SOC2 modes). The chatbot composes privacy patterns per user request, using existing primitives + community-evolved best practices.

**Why:** Per host directive 2026-04-26: for well-known sensitive categories (invoices, medical, legal, financial, PII), the chatbot uses community-evolved best practices — wiki pages, remixable node compositions, soul-policy templates. For complex/novel sensitive workflows, the community is BETTER at evolving patterns than the platform — they meet the user in their own vocabulary, with their own judgment about what matters. Platform-built privacy features ship a frozen taxonomy; user threat models are open-ended.

**How to apply:** When a sensitive-workflow request comes in (privacy mode, redaction, threat-model preset), the FIRST response is "the chatbot composes this from existing primitives + community best practices." Design-note recommendation: a how-to-compose guide, plus a pointer to community-evolved templates. Platform action ONLY if a primitive is structurally missing — and then ship the smallest primitive, not the policy. The platform DOES still own primitive enforcement boundaries: `WORKFLOW_UPLOAD_WHITELIST`, local-LLM-only routing, file-path enforcement at write time, MCP approval surface. Those are primitives, not policies.

Depth: lead memory `project_privacy_via_community_composition.md`.

### 4. Commons-first architecture

**Rule:** Private data lives on host machines; public data lives in the platform commons. Three parts: (a) when a user builds a private branch / canon / universe, the data lives on a host; the platform/server **never stores** private content. (b) Platform-stored data is the open-source community commons — public-by-definition. (c) Community designs published to the commons become the tool surface for next users via discovery + similarity + remix; the platform doesn't build features, the community evolves them.

**Why:** Per host directive 2026-04-27. Security architecture, not security policy — privacy is enforced by the platform never having the data. Identity alignment — Workflow is open-source community first, the platform's data space is for the community. Resource alignment — storage / serving / moderation costs of private data fall on the host. And the commons + remix engine is what makes minimal-primitives + community-build viable at scale: the platform ships discovery/similarity/ranking/attribution primitives; community ships features.

**How to apply:** Before adding ANY platform feature, ask: "Could a user compose this from existing primitives + community remix?" If yes, the answer is to make discovery / similarity / remix work well, not to ship the feature. All platform-stored data is public-by-definition — no `is_private` flag on platform records (those records don't exist). Private branches don't have rows in platform metadata; the chatbot composes "this is private, keep it on host" without the platform's knowledge. Async availability is acceptable — private content is gated on a host being online; users-with-access who arrive when no host is online wait or get a graceful "no host online" signal. Anti-patterns: storing private data with platform-side encryption (still platform-resident), soft-private branches (a "private" flag breaks the architecture), discovery surfaces that bias toward platform-built content (commons content is equal first-class).

Depth: lead memory `project_commons_first_architecture.md`.

### 5. User capability axis — browser-only vs local-app, across providers

**Rule:** Workflow has two basic user shapes for product-design purposes: **browser-only** (phone or computer; chats through web client — Claude.ai web, ChatGPT web; no local file system or code execution) and **local-app** (computer with chat-client app + computer-use access — Claude Code, ChatGPT desktop with computer-use; local file system, local code execution, daemon hosting). Orthogonal axis: MCP host provider. Claude and ChatGPT are P0 launch/discoverability gates, not the market boundary. Any user-facing chatbot, IDE agent, local model shell, enterprise agent builder, or custom app that can connect to a Workflow MCP server is part of the customer model; non-P0 hosts get explicit matrix-scoped support and caveats instead of being treated as invisible long tail.

**Why:** "Use Claude.ai instead" or "use Claude Code instead" is an anti-pattern. A real user is on whatever client they chose, and the platform reaches them there. Bugs that work on one provider but not another are P1 product bugs, not "use the other one." Don't second-class browser-only users — compensate via cleverness (host the daemon for them, publish results to shareable URLs, stream long outputs, save state to universe, compose chains that produce tangible deliverables, use platform scalability advantages like parallelism + retries + evaluators that no single browser session could do alone).

**How to apply:** Every feature design names its target capability tier and host coverage. Local-app: daemon hosting, file system I/O, local program invocation, autoresearch overnight, multi-tenant tray, OSS-clone-and-extend. Browser-only: cloud-mediated equivalents for everything actionable. Launch parity: test on both Claude and ChatGPT before claiming a public chatbot feature ships. Matrix parity: for any other host, say exactly which host was verified and what caveat remains. A primitive earns its keep MORE if it works equivalently across both capability tiers and many MCP hosts; a primitive that only helps local-app users or one provider is a much higher bar to ship. Hopeful future: the gap collapses (Claude.ai gaining computer-use, ChatGPT gaining MCP local-file capabilities, browser sandboxing improving) — primitives should compose the same way regardless of capability tier; tier just determines leverage paths, not feature existence.

Depth: lead memory `project_user_capability_axis.md`; host matrix `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md`. Refines `project_user_tiers` (which is about install friction); both lenses are valid.

---

## Canonical Vocabulary

**Status: canonical as of 2026-05-10.** Workflow's foundational substrate vocabulary is six work concepts plus five permissioned MCP handles. Coding sessions should use this vocabulary when naming architecture, docs, tool metadata, and future design notes unless a narrower domain term is explicitly needed.

The six base concepts describe durable work at the graph layer:

| Concept | Meaning |
|---|---|
| `Node` | A typed unit of work, judgment, transformation, or evidence capture. |
| `Edge` | A declared transition between nodes, including conditional routing and review paths. |
| `State` | The durable typed record a graph reads, writes, reduces, checkpoints, and resumes. |
| `Scope` | The authority and context boundary for a work item: user, branch, goal, daemon, host, commons, or other bounded surface. |
| `Run` | An execution attempt with inputs, outputs, provider traces, checkpoints, and evidence. |
| `Trigger` | The event or schedule that asks Workflow to start, resume, replay, or route work. |

The five MCP handles describe the small permissioned control surface agents use to inspect and act on those concepts:

| Handle | Authority |
|---|---|
| `read.graph` | Inspect graph structure, state summaries, lineage, runs, and public metadata. |
| `write.graph` | Propose or mutate graph definitions, state, scopes, edges, and work artifacts under the caller's authority. |
| `run.graph` | Start, resume, cancel, replay, or otherwise control graph execution within the caller's scope and confirmation policy. |
| `read.page` | Read wiki, commons, docs, request, and explanation pages that contextualize the graph. |
| `write.page` | Draft or update wiki, commons, docs, request, and explanation pages through the same reviewable artifact path. |

These names are substrate vocabulary, not a mandate that every runtime function or MCP tool be named exactly this way. Concrete tool names may remain client-shaped for compatibility, but they should map back to one or more of these handles in docs, permission checks, and tool descriptions. The older 8-engine-primitive framing in `docs/design-notes/2026-04-26-engine-primitive-substrate.md` remains a useful historical pressure test over implementation modules; it is no longer the canonical primitive count for project architecture. The canonical source for the promotion rationale is `docs/design-notes/proposed/2026-05-10-promote-work-substrate-vocabulary.md`.

---

## Cross-Cutting Principles

These principles apply to every module. They do not own a module each; they constrain how modules behave.

**Agentic hybrid search is memory.** Durable memory is a policy over multiple stores (KG traversal, vector similarity, hierarchical summaries, notes, world-state, direct tool calls). No single backend owns truth. Routing matters more than any one store.

**Context is a managed working set.** Prompts are lossy projections over durable state. The goal is not "pack more context" but "give the model the smallest high-signal working set for the current step."

**Workflow state transitions are the core abstraction.** Orient, plan, draft, commit, learn, reflect, worldbuild, task selection. If the state model is wrong, the system feels smart locally and breaks over long runs.

**Every scaffold is a falsifiable hypothesis.** Counters, thresholds, phase gates, routing rules all encode a claim about model weakness. Prove the simpler approach fails before adding; prove removing hurts before defending. When a stronger model lands, re-test the harness. Trend toward less prescriptive control.

**Harness design is part of the cognition stack.** Initializers, traces, browser harnesses, replayable tests, dashboards, status files, artifact stores materially change what the system can do.

**Tools are the agent-computer interface.** Tool shape is architecture — names, parameters, return schemas, failure semantics. Prefer a smaller number of reliable composable tools over many overlapping ones. **Trust-critical tools include their own caveats** (the self-auditing-tools pattern, see `docs/design-notes/2026-04-19-self-auditing-tools.md`); structured evidence + structured caveats lets the chatbot compose trustworthy narratives without the system having to police its honesty.

**Generator, evaluator, and ground truth stay separate.** Self-evaluation bias is real. Keep them as separate channels, often separate model families. The evaluator needs a different failure profile, not a better creator.

**State lives on multiple timescales.** Scene = short-horizon action. Chapter = medium-horizon consolidation. Book = longer-horizon recovery and planning. Universe = global maintenance, synthesis, strategy. The hierarchy exists because timescales differ, not because fiction has chapters.

**Learning is write-back compression.** Agents improve by promoting stable lessons into reusable artifacts (notes, style rules, facts, summaries, revised tools and prompts), not by hoarding transcripts.

**Evals grade process and outcome.** Final quality isn't enough. Inspect retrieval choices, tool usage, stopping behavior, handoff quality, grounding, artifacts. When a run fails, traces should explain why.

**Module shape is part of the architecture.** A flat namespace of 35 modules at `workflow/` root signals "no opinion about boundaries." A god-module of 10k lines signals "boundaries deferred indefinitely." Both are forms of architectural debt. The Module Map below codifies the target shape; the per-module sections that follow codify what each owns.

**Cleanup operations against scene-attributed data must scope across all DBs that hold scene-attributed rows.** Generalizes the Fix E lesson (task #49): a cleanup path that prunes one DB but not its sibling leaves orphan derivatives that masquerade as canon on the next retrieval cycle. When a new DELETE or mutation operates on rows keyed to scene_id (or any cross-store attribution), scope it against both `knowledge.db` and `story.db` from the start, or explicitly document the opt-out with reason. Per the migration-audit follow-up at `docs/audits/2026-04-19-schema-migration-followups.md`.

---

## How to Use This PLAN

PLAN.md is the working theory of what each module is and how it works. **Everyone references it before building** — human contributors, the auto-change loop, the user chatbots, the agent teams. If your work doesn't fit one of the modules below, that gap is the design conversation.

**Skill anchors.** Each named project skill ties into one PLAN.md surface; invoke the skill before or during module work, not after:

| Skill | When to invoke | What it does for PLAN.md |
|---|---|---|
| `improve-codebase-architecture` | Before refactoring a module; when a module feels spaghettified; when planning a decomposition | Module audit against this PLAN.md; surfaces drift between described shape and current code |
| `auto-iterate` | Every time a behavioral failure recurs across sessions (the same mistake twice = ratchet) | Adds the next prevention layer (doc → script → hook → gate); each ratchet records the trigger in the module it touched |
| `spec-driven-development` | Before writing code for any feature that spans >1 file or >30 minutes | Produces the spec; this PLAN.md is the PLAN-phase artifact for any spec that touches platform shape |
| `planning-and-task-breakdown` | After a spec exists; when work needs to be broken into ordered tasks | Decomposes; module Substrate fields tell you what code paths are in scope |
| `incremental-implementation` | During execution of any multi-file change | Thin vertical slices; the open-brain v2 A/B/C/D series is the exemplar |
| `domain-model` | When a proposal feels fuzzy or names overload existing concepts | Challenges against the Canonical Vocabulary above + the relevant module |
| `ubiquitous-language` | When terminology drifts (aliases, overloaded words) | Hardens PLAN.md as the canonical name source |
| `api-and-interface-design` | When designing a new MCP action, module boundary, or contract | Maps to the API & MCP Interface Module |
| `code-simplification` | After a feature is working but feels heavier than it should | No new abstractions before reducing existing ones |
| `zoom-out` | Before any non-trivial code change | Build the high-level map first; required first step inside `improve-codebase-architecture` |

**Auto-iteration of the modular skill.** The `improve-codebase-architecture` skill self-iterates against this PLAN.md via three lightweight mechanisms:

1. **Per-module audit stamps.** Each module section carries a `_Last audited: YYYY-MM-DD_` line. The skill updates the stamp on every audit pass; `scripts/plan_module_audit.py` lists stale modules.
2. **Drift detection.** The same script compares each module's Substrate field against the code paths actually present in the repo and flags mismatches.
3. **Recurrence ratchet.** When the same architectural smell is found in two consecutive audits of any module, the auto-iterate ladder fires — adds the next prevention layer (doc → script → hook → gate).

PLAN.md itself stays clean — the audit machinery lives in the skill + the script. PLAN.md only carries the stamp and the module shape.

---

## Module Map

The codebase target shape, with each PLAN.md module mapped to its primary code package(s). Where the current state diverges from this target, the gap is in-flight work — not architectural disagreement. Anchored by the spaghetti audit at `docs/audits/2026-04-19-project-folder-spaghetti.md`.

`workflow/` is the engine package. Domain packages (`fantasy_daemon/`, future `research_daemon/`, etc.) consume from it.

| PLAN.md Module | Primary code package(s) |
|---|---|
| Engine & Domains | `workflow/`, `domains/<name>/` |
| Daemon Platform | `workflow/identity.py`, `workflow/discovery.py`, `workflow/branch_tasks.py`, `workflow/runtime/` |
| **Brain** | `workflow/memory/`, `workflow/retrieval/`, `workflow/knowledge/`, `workflow/storage/__init__.py` (memory_kinds), `workflow/learning/` |
| Goals & Gates | `workflow/storage/goals_gates.py`, `workflow/api/market.py` (goals + gates actions) |
| Evolution & Evaluation | `workflow/evaluation/`, `workflow/learning/`, autoresearch surface |
| Providers | `workflow/providers/` |
| API & MCP Interface | `workflow/api/` (mounted submodules per cluster), `workflow/servers/` |
| Distribution & Discoverability | `packaging/`, `workflow/directory_server.py`, MCP registry |
| Harness & Coordination | `AGENTS.md`, `STATUS.md`, `scripts/claim_check.py`, `scripts/worktree_status.py`, `scripts/provider_context_feed.py`, `.agents/`, `.claude/agents/` |
| Uptime & Alarms | `deploy/`, `.github/workflows/uptime-canary.yml`, `.github/workflows/p0-outage-triage.yml`, `scripts/uptime_canary.py` |
| Constraints | `workflow/constraints/`, `data/world_rules.lp` |

Engine subpackage target shape (the durable commitment — anything new must fit one of these or earn its root spot with a one-line explanation):

| Subpackage | Responsibility |
|---|---|
| `workflow/api/` | MCP tool surfaces. Mounted submodules per capability cluster (FastMCP `mount()`). **No god-modules.** |
| `workflow/storage/` | Schema + bounded-context storage layers. Shared `_connect()` + migrations in `__init__.py`. |
| `workflow/runtime/` | Run scheduling primitives — runs, work_targets, dispatcher, branch_tasks, subscriptions, producers, executors. |
| `workflow/bid/` | Per-node paid-market mechanics — node_bid, bid_execution_log, bid_ledger, settlements. |
| `workflow/servers/` | Entry-point shells. Routes to `api/` submodules. **Not the place action logic lives.** |

Existing subpackages already conforming: `auth/`, `catalog/`, `checkpointing/`, `constraints/`, `context/`, `evaluation/`, `ingestion/`, `knowledge/`, `learning/`, `memory/`, `planning/`, `providers/`, `retrieval/`, `desktop/`, `testing/`, `utils/`. Correctly-flat root modules (small typed surfaces with no clear sibling): `protocols.py`, `exceptions.py`, `notes.py`, `packets.py`, `config.py`, `identity.py`, `discovery.py`, `singleton_lock.py`, `domain_registry.py`, `registry.py`, `preferences.py`, `compat.py` (post-Phase-5).

**Migration policy.** When a flat module crosses ~500 LOC OR overlaps a sibling's responsibility, it gets a subpackage. New work goes into the target shape; legacy gets refactored opportunistically (the spaghetti audit ranks priority order).

---

## Module Shape

Every module section below follows the same shape so PLAN.md reads as reference:

- **Purpose.** One sentence — what the module exists for.
- **In scope.** What this module owns.
- **Out of scope.** What it does NOT own (pointing to siblings).
- **Principles.** The constraints that govern this module.
- **Substrate.** Concrete code paths and current shape.
- **Open evolution.** What is still being figured out.
- _Last audited: YYYY-MM-DD_

---

## Module: Engine & Domains

**Purpose:** `workflow/` is reusable infrastructure that any domain can adopt; `domains/*` own their graph topology and import what they need.

**In scope:** Engine-shared primitives (state, edges, runs, triggers), the engine/domain seam, domain registration, scene/chapter/book/universe timescale hierarchy as a generic shape.

**Out of scope:** Domain-specific graph topology (lives under `domains/<name>/`); paid-market mechanics (Daemon Platform); evaluation logic (Evolution & Evaluation).

**Principles:**
- *Extract infrastructure first, prove topology second.* A second domain pressures the engine to prove it's actually domain-agnostic — fantasy is the benchmark, not the trunk.
- *Engine = `workflow/`. Domains = `domains/<name>/`.* The engine-vs-domain seam is named. Once the separation lands, every action lives in exactly one of: shared engine API (`workflow/api/`) or a domain API (`domains/<name>/api/`). No third location.
- *State transitions are the core abstraction.* Orient → plan → draft → commit → learn → reflect → worldbuild → task selection. If the state model is wrong, the system feels smart locally and breaks over long runs.
- *Scene Loop is a state-transition pattern, not a fiction-specific concept.* Orient → plan → draft → commit is useful only if each step adds value; flatten the loop when a stronger model + better tools can do equivalent work in fewer steps.

**Substrate:** `workflow/` (engine package), `domains/fantasy_daemon/` (only live domain today), `workflow/domain_registry.py`, `workflow/registry.py`, `workflow/protocols.py`. Pending engine/domain API separation: `docs/design-notes/2026-04-17-engine-domain-api-separation.md`. Fantasy domain keeps scene/chapter/book/universe names in its own graph; shared `workflow/` infrastructure uses domain-agnostic names.

**Open evolution:** Second domain adoption (research_daemon, journalism_daemon) is the unblocking proof that the engine is domain-agnostic. Until then, every "engine" decision risks fantasy-shaped bias.

_Last audited: 2026-05-19_

---

## Module: Daemon Platform

**Purpose:** A multi-tenant workflow platform where many users and daemons collaborate without collapsing into one shared chat or one hidden runtime.

**In scope:** Daemon identity (souls, fingerprints, forks), runtime instance allocation, host pool registry, soul eligibility per node/gate, soul-guided dispatch, capacity-bounded fleet sizing, file-locked claim across cloud + host executors.

**Out of scope:** What a daemon *knows* (Brain); what a daemon *evaluates* (Evolution & Evaluation); goal/gate ladder definitions (Goals & Gates); MCP tool surface (API & MCP Interface).

**Principles:**
- *Separate identity from runtime.* Daemons are public, forkable, summonable agent identities defined by soul files; runtime instances are resource allocations bound to providers, models, and executor hosts. Every `(user, daemon, executor)` tuple is independently addressable; today's N=1 is the degenerate case.
- *Daemon-driven.* Let the daemon make creative and structural decisions whenever the model can reliably do so. Hardcoded thresholds and stage gates are scaffolding — test each by removing it. When the daemon decides badly, improve goals/context/tools/evals rather than layering recipes.
- *Always ready for the next user and daemon fleet.* Multi-tenant from the first build. Storage, authorization, queues, budgets, audits, daemon bindings, and runtime activations carry tenant/owner boundaries.
- *Zero daemons required for authoring.* Node/branch/goal creation, editing, forking, and collaboration work with no daemon running anywhere. Daemon hosting is opt-in for execution work. Load-bearing requirement — any architecture where authoring depends on a running daemon violates it.
- *Host fleets are capacity-bounded, not product-capped.* A host may summon as many daemons as they can afford and operate, including multiple daemons on the same provider. Second-and-later same-provider summons show warning-only subscription/rate-limit guidance; no platform subscription gate.
- *Soul eligibility.* Nodes and gates may declare whether daemon souls are allowed, forbidden, required, replaced, or combined with a temporary node/gate header. They may declare domain requirements (scientific, legal, artistic, local-model-only). Claim-time verification checks soul fingerprint + required claims/proofs before execution.
- *Soul-guided dispatch.* A soul-bearing daemon returns to a decision step listing eligible work + soul policy + domain requirements + required capability + offer. The daemon may choose money, interests, reputation, public-good impact, or refusal per its soul. Soulless daemons use the default platform dispatcher.
- *Two coexisting executors, one file-locked claim.* Cloud-side `cloud_worker` (identity `cloud-droplet`) + opt-in host-tray (identity `host`); both call `branch_tasks.claim_task`; file-lock sidecar guarantees no double-claim.

**Substrate:** `workflow/identity.py`, `workflow/discovery.py`, `workflow/branch_tasks.py`, `workflow/runtime/`, `workflow/singleton_lock.py`. Soul/fork machinery currently lives in the `author_definitions` substrate transitioning to a domain-agnostic daemon registry (content provenance retains `author_id` + `author_kind` discriminator). Host pool registry: `docs/design-notes/2026-04-18-full-platform-architecture.md §5`. Soul-guided dispatch read path landed via open-brain v2 slice B 2026-05-19.

**Open evolution:** Cross-host node-execution hopping is not supported (cross-host software donation IS, see Distribution). N-of-M multi-actor approval as a generic primitive (founder vote, treasury multisig, scientific publication co-signature) is unscoped.

_Last audited: 2026-05-19_

---

## Module: Brain

**Purpose:** The platform's memory + identity + authority substrate. The Brain holds what each universe / branch / daemon / contributor knows, what they've agreed to, and what they're eligible to do. Every other module consults the Brain before deciding.

**In scope:**
- Tiered memory across multiple stores (KG, vector, hierarchical summaries, world-state, notes, direct tool calls).
- The `memory_kinds` typed catalog — canon fact, attribution snapshot, soul fingerprint, gate-evidence, contributor weight, etc.
- Promotion state machine: candidate → accepted → promoted → rejected → superseded. No memory becomes load-bearing without earning promotion.
- Soul-guided dispatch *read path* — what work is a daemon eligible to claim?
- Treasury status *read path* — bounded budget + spend visibility.
- Bounded autonomous spend guardrails — per-Goal / per-daemon / per-cycle caps.
- Authority-condition policy (per `docs/design-notes/proposed/2026-05-19-external-write-authority-and-rewards.md`) — Brain conditions every external-write authority decision on past-decision memory.
- Attribution graph snapshot at the moment a reward releases — authoritative for payout.

**Out of scope:** Treasury *write path* (future Treasury Module); goal/gate ladder definitions (Goals & Gates); provider routing (Providers); evaluation logic (Evolution & Evaluation); MCP surface (API & MCP Interface).

**Principles:**
- *No single backend owns truth.* Routing across stores is the policy; routing matters more than any one backend.
- *Memory interface is query semantics, not tier names.* The public interface feels like faceted search, not "core/episodic/archival" tier addressing.
- *Generator, evaluator, and Brain stay separate.* Self-evaluation bias is real; the Brain is read-only to its own evaluations.
- *Learning is write-back compression.* Stable lessons get promoted into the typed catalog; transcripts are not memory.
- *Brain conditions every authority decision.* Permissive by default — Brain logs and hints. Per-Goal opt-in to strict mode where Brain may refuse to authorize a contradicting write.

**Substrate:** `workflow/memory/`, `workflow/retrieval/`, `workflow/knowledge/`, `workflow/learning/`, `workflow/storage/__init__.py` (memory_kinds + promotion state). Open-brain v2 slices landed 2026-05-19: A=memory_kinds registry, B=soul-guided dispatch read, C=treasury status read, D=bounded autonomous spend. Companion artifacts on main: #903 amendment-verdict carrier, #870 wiki-bug body inclusion, #866 dedup safety net.

**Open evolution:** Authority-condition strict-mode rollout (per the 2026-05-19 design note open questions). Brain's role in N-of-M multi-actor approval state. Brain ↔ Evolution feedback — which Brain-snapshotted attributions feed back into evaluator training signal? Cross-universe Brain federation (shared scientific corpus across Goals).

_Last audited: 2026-05-19_

---

## Module: Goals & Gates

**Purpose:** A Goal is a named pursuit ("research-paper", "fantasy-novel"); a Branch is one concrete take; many Branches bind to one Goal. Gates are the outcome ladder that turns Goal progress into a truth signal.

**In scope:**
- Goal as first-class object: `goals` table, `Branch.goal_id`, per-Goal browsing.
- Work-target registry (the unit of intentional work — uploads, canon repair, world notes, plans, scenes). Foundation review hard-blocks on unsynthesized uploads only; authorial review may choose any justified move once hard blockers clear. Targets carry role (notes/publishable), publish stage, lifecycle, tags, artifact refs.
- Outcome-gate ladders per Goal (draft → peer feedback → submission → acceptance → publication → citations → breakthrough for research; ladder shape varies per Goal).
- Rung-claim recommendations on branch tasks.
- `archive_consultation` parent-rank surface (quality + outcome + diversity).
- Per-Goal leaderboards, cross-branch node library.
- Outcome gates: rung claims are the trigger that fires external writes via the authority + idempotency model in the Brain (see 2026-05-19 design note).

**Out of scope:** Brain memory (Brain); evaluation logic (Evolution & Evaluation); external-write execution (the *trigger* is here; the *execution* is policed by Brain + connector registration).

**Principles:**
- *Goal is first-class above Branch.* Many Branches bind to one Goal. "Simultaneously pursue the same Goal via different Branches" is the default collaboration pattern.
- *Outcome gates — real-world impact is the truth signal.* Leaderboards rank on outcome progression, not draft polish.
- *Tags stay loose; role and lifecycle stay guarded.* Publishable-vs-notes role, publish stage, and true discard are explicit state transitions; `marked_for_discard` is not the same as `discarded`.
- *Two review gates, one target registry.* Foundation review hard-blocks; authorial review chooses.
- *Diverse-by-default.* 100 different research-paper workflows from 100 users is a feature, not duplication. Consolidation into "the best" workflow is an anti-pattern.

**Substrate:** `workflow/storage/goals_gates.py`, `workflow/api/market.py` (goals actions: propose, update, bind, list, get, search, leaderboard, common_nodes, archive_consultation, set_canonical). `BranchTask.rung_claim_recommendations` field landed via PR #899.

**Open evolution:** Parent-rank scoring formula as an evolvable workflow node (see follow-up #913) — formula competes via autoresearch, not as a fixed platform constant. Tracking of outcome gates (self-report first, automated later via DOI / court-docket / sales / awards). Per-piece privacy: concept-public default, instance-private when user data involved, chatbot-judged per piece (refines earlier branch-private framing).

_Last audited: 2026-05-19_

---

## Module: Evolution & Evaluation

**Purpose:** Improve workflow quality through feedback, not brittle gates. Optimization is a native run type, not a sidecar.

**In scope:** Layered evaluation (deterministic checks + editorial reader + environment-grounded artifacts + traces); the `Evaluator` primitive that unifies fantasy judges, autoresearch metrics, moderation rubrics, real-world outcomes, and discovery ranking; `OptimizationRun` surface; `EvalResult` schema; acceptance scenario packs; quality-diversity search; lineage; attribution; community remix.

**Out of scope:** Goal/gate ladder definitions (Goals & Gates); provider routing for evaluator runs (Providers); MCP action surface (API & MCP Interface).

**Principles:**
- *Layered evaluation.* Deterministic checks for provable failures; an editorial reader for natural-language critique; environment-grounded artifacts + traces for verification. One strong independent reader beats a committee of shallow scorers.
- *Evals grade process and outcome.* Inspect retrieval choices, tool usage, stopping behavior, handoff quality, grounding, artifacts. When a run fails, traces should explain why.
- *Evaluation is platform-wide, not fantasy-specific.* Fantasy judges, autoresearch metrics, moderation rubrics, real-world outcomes, and discovery ranking are instantiations of one `Evaluator` primitive.
- *Native optimization, not an ASI-Evolve clone.* Workflow adopts the ASI-Evolve / AlphaEvolve lesson as an engine-native pattern: users ask through any MCP-connected chatbot; the platform runs bounded evaluator-driven optimization over nodes, branches, evaluators, prompts, policies, topology; accepted changes land through normal versioned/provenance-aware branch history. Do not vendor or parallel-run a separate ASI pipeline.
- *Community model.* Branches, nodes, evaluators, and lessons are remixable public commons when privacy policy permits. The platform preserves many competing solution families rather than collapsing to one "best" workflow.
- *Safety model.* Candidate generators cannot edit the evaluator or the locked harness they are being judged by. Optimization runs declare editable surface, evaluator chain, budget, stop conditions, merge policy, provenance, and visibility up front. Private instance data must not be promoted into reusable cognition unless privacy layer permits.
- *Acceptance Scenario Packs.* Host-approved 2026-05-02 direction (pending opposite-provider review): Workflow grows reusable long-horizon scenario packs combining user simulation, rubric checks, MCP/API or browser evidence, and artifact capture into `EvalResult` evidence. No vendoring of AgencyBench or its harness — define Workflow-native scenario contracts.

**Substrate:** `workflow/evaluation/`, `workflow/learning/`. `EvalResult` evidence/artifact/cost/freshness contract landed 2026-05-02. Canonical rationale: `docs/audits/2026-05-02-asi-evolve-architecture-implications.md`; integration design: `docs/design-notes/2026-05-02-community-evolvable-optimization-integration.md`.

**Open evolution:** `OptimizationRun` substrate spec (review-blocked on opposite-provider verdicts for ExperiencePool + GroupEvolutionRun, Acceptance Scenario Packs, Private Trace Commons, Origin Quantum Q0/Q1 — see STATUS Work table). Quality-diversity vs. linear ranking — the parent-rank formula divergence in Goals & Gates is a special case of this same evolvable-formula question.

_Last audited: 2026-05-19_

---

## Module: Providers

**Purpose:** Pick the best provider per role and preserve role separation without hiding failure.

**In scope:** Provider registry, fallback chains, parallel diversity, the writer-pin override (`WORKFLOW_PIN_WRITER`), local-LLM endpoint binding (`OLLAMA_HOST`, `ANTHROPIC_BASE_URL`), provider-specific config.

**Out of scope:** What a provider is asked to do (the requesting module); evaluation of provider output (Evolution & Evaluation).

**Principles:**
- *Error loudly when the remaining provider can't produce acceptable work.* Fake success is worse than failure. (Hard Rule #8.)
- *Fallback chain correctness is a first-class invariant.* Every provider named in a fallback chain must be either registered AND reachable at startup, or explicitly excluded with a logged reason. Phantom chain entries are a bug. A chain that reads `[claude-code, codex, gemini-free, ...]` but whose first entry's CLI binary is absent silently degrades the whole chain; operators reading config see one chain, the runtime iterates a different one. Register-and-probe at startup; emit structured evidence of the effective chain via `get_status`; refuse to advertise unreachable providers. (Corroborated by BUG-025 + 2026-04-21 prod-LLM-binding incident + 2026-04-23 revert-loop P0.)
- *Required files must be probed at startup and fail loud if missing.* When code declares a required on-disk artifact (ASP rule files, schema definitions, seeded fixtures, vendored configs), startup must probe for it and refuse to start if absent — not log a WARNING and continue with an empty fallback. Silent substrate-degradation from missing artifacts produces runs that report success while behaving as no-ops; that violates Hard Rule #8 at an earlier lifecycle phase. (Corroborated by BUG-026: `data/world_rules.lp` absent silently reduced the ASP constraint engine to a no-op.)

**Substrate:** `workflow/providers/`. Required-files probe lives at startup; chain probe emits via `get_status`.

**Open evolution:** Auth-parity work for non-Claude/ChatGPT providers in the MCP-host customer matrix.

_Last audited: 2026-05-19_

---

## Module: API & MCP Interface

**Purpose:** Let users steer through natural conversation and MCP tooling without letting any chat surface become the author.

**In scope:** MCP tool surfaces, FastMCP `mount()` topology, tool/prompt discoverability metadata, control-station prompt, server shells.

**Out of scope:** Action implementations behind the surface (each module owns its actions); the control plane wiring (Daemon Platform); discoverability outside MCP (Distribution & Discoverability).

**Principles:**
- *Any MCP-compatible client is a control station, not a creator.* The daemon does the creative work. If a chat surface writes story content itself, that indicates a missing daemon path.
- *Tools publish explicit titles, tags, and behavior hints.* The daemon exposes a small number of coarse-grained tools; discoverability metadata is part of the interface contract.
- *Trust-critical tools are self-auditing.* Tools that touch privacy, cost, routing, scope, or moderation expose structured evidence + structured caveats; the chatbot composes the user-facing narrative on top. Caveats are part of the tool's contract. (See `docs/design-notes/2026-04-19-self-auditing-tools.md`.)
- *Release state is a status contract.* `get_status.release_state` reads the deploy-published receipt that ties the live daemon to source SHA, image tag/digest, build/deploy runs, config hash, canary status, deployment time, rollback target, and actor metadata. Missing receipts surface as caveats, not probe failures.
- *Module shape rule.* API surfaces live in `workflow/api/` as mounted submodules per capability cluster. Server shells in `workflow/servers/` route to them. **No god-modules.**

**Substrate:** `workflow/api/` (helpers, wiki, status, runs, evaluation, runtime_ops, market, branches), `workflow/servers/` (workflow_server, daemon_server, mcp_server). Universe-server decomposition is in-flight per `docs/audits/2026-04-25-universe-server-decomposition.md` — universe_server.py is down from 14k peak to 972 LOC live in main.

**Open evolution:** Final cluster extraction completion. ChatGPT-host first-response UX caveat (large MCP responses → "something went wrong"; see memory `project_chatgpt_response_too_large_failure.md`) — SUMMARY-by-default response shape with `verbose=true` opt-in is unscoped.

_Last audited: 2026-05-28_

---

## Module: Distribution & Discoverability

**Purpose:** Installable and discoverable across standard MCP surfaces, Anthropic packaging, and future packaging without changing the portable core.

**In scope:** MCPB packages, Claude Code / Cowork plugins, registry metadata, ChatGPT app submission, MCP-directory tooling, the per-host customer matrix, install-readiness invariants, software-surface authorization (declarative + multi-layer).

**Out of scope:** What the daemon does once installed (other modules); auth at the MCP edge (API & MCP Interface).

**Principles:**
- *Keep the core portable; add platform wrappers around it.* MCPB packages, Claude Code plugins, registry metadata, and future `.cnw.zip` packaging are distribution layers over the same daemon and tool surface, not replacement architectures.
- *MCP host coverage is matrix-driven.* Claude and ChatGPT are P0 launch gates, but every MCP-capable host is a possible customer surface. Caveats + acceptance proofs live in `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md`.
- *Install-readiness is continuous.* Main is a downloadable release at all times. Every change preserves flawless first-install — packaging auto-builds via CI (import probe + plugin drift check), user-facing copy is branded and unambiguous, broken install is a production bug.
- *Discovery via entry points, not filesystem scan.* Domain discovery uses `importlib.metadata.entry_points(group="workflow.domains")`. Filesystem scan of `domains/*/skill.py` is a dev-mode fallback for editable worktrees only. Compat aliases stay out of discovery — compat lives in import shims, not in the domain registry contract.
- *Software surface is declarative and multi-layer-authorized.* Nodes declare `required_capabilities`. Per-host capability registry resolves what's installed. Missing software auto-installs (host-policy gated). Daemons can invoke arbitrary local software via a dedicated `external_tool_node` type that bypasses the Python sandbox but layers security: bundled handler signatures, binary signature verification, universe-level allow-list, per-software host approval, subprocess isolation. Any single layer fails, the others hold. Cross-host software donation supported; cross-host node-execution hopping is not.

**Substrate:** `packaging/`, `workflow/directory_server.py`, MCP Registry surface, ChatGPT app submission packet, no-login deployment packs for Open WebUI / LibreChat.

**Open evolution:** First-user evidence after no-dev-mode acceptance proofs land. ChatGPT-mobile proof.

_Last audited: 2026-05-19_

---

## Module: Harness & Coordination

**Purpose:** Make the system operable, testable, replayable, and improvable across both product runtime and AI-to-AI development. Harness is first-class architecture.

**In scope:** Three Living Files (AGENTS.md / PLAN.md / STATUS.md); the GitHub-shaped lane spine (STATUS row → branch → worktree → PR/draft PR); provider-context feed; agent roles (verifier, navigator, dev, user-sim, lead); claim discipline; cross-provider drift detection.

**Out of scope:** What individual roles produce (other modules); skill content (`.agents/skills/`, `.claude/skills/` — content is per-skill, the harness orchestrates invocation).

**Principles:**
- *Harness design is part of the cognition stack.* Browser harnesses, builder automation, traces, regression tests, dashboards, role-based agent coordination materially improve system intelligence by making behavior legible and correctable.
- *Three Living Files separate process truth, design truth, and live state.* AGENTS.md = how to work. PLAN.md = how the system works. STATUS.md = what's happening now. Each is updated immediately when its slice of truth changes.
- *GitHub/worktree coordination spine.* Buildable work flows through: STATUS Work row + purpose-named branch + sibling `../wf-<slug>` worktree + PR / draft PR. Relevant PLAN.md modules are the project understanding each lane reviews at planning, build, review, and fold-back. `ideas/INBOX.md` is a loose idea feed; entries park at the bottom of a lane as "Idea feed refs" — not design truth or build authority.
- *Provider-context feed.* Provider-specific memory and automation are INPUTS to the GitHub/worktree spine, not separate planning authorities. `scripts/provider_context_feed.py` scans Claude/Codex/Cursor/shared memory + ideas + research + automation + worktree handoff surfaces at claim/plan/build/review/foldback/memory-write checkpoints. Hidden provider context cannot bypass community-visible project state.
- *Roles are architectural capabilities.* Each provider implements them through its available harness rather than one universal team mechanism. Verifier/navigator/dev/user-sim are not Claude-Code-specific.

**Substrate:** `AGENTS.md`, `STATUS.md`, `PLAN.md`, `scripts/claim_check.py`, `scripts/worktree_status.py`, `scripts/provider_context_feed.py`, `scripts/check_cross_provider_drift.py`, `.agents/`, `.claude/agents/`, `.claude/hooks/`.

**Open evolution:** Continued auto-iteration of the harness itself — see `improve-codebase-architecture` + `auto-iterate` skills.

_Last audited: 2026-05-19_

---

## Module: Uptime & Alarms

**Purpose:** The complete system — MCP surface + node execution + collaboration surfaces + paid-market + moderation — stays up 24/7 with zero hosts online. The host machine being asleep for 24h must not extend any outage window past the pager's escalation ladder.

**In scope:** Self-heal layers, alarm ladder, DR drill, canonical canary, loop-uptime-maintenance escape.

**Out of scope:** Application-level bugs (other modules); deploy mechanics (Distribution).

**Principles:**
- *Defense in depth, and the alarm path itself is host-independent.* Every self-heal layer assumes the layers below it will fail; the alarm ladder assumes every self-heal layer will fail. None run on a host machine.
- *Three self-heal layers, each catches a different class.* 1. Container restart (`systemd Restart=always` + `workflow-watchdog.timer`) — transient crashes, OOM recovery, hung-but-not-crashed. 2. GHA `p0-outage-triage.yml` auto-repair — six classes covered (OOM, disk-full, image-pull, watchdog-hot-loop, tunnel-token-manual, env-unreadable). 3. Deploy-side invariants — `deploy-prod.yml` asserts `/etc/workflow/env` is readable by the daemon user post-mutation and post-restart, then publishes `/data/release-state.json` for live status reconciliation.
- *Alarm ladder, host-phone-independent.* Pushover paging from GHA `alarm-sink` at threshold-cross (2 consecutive reds ≈ 10 min outage), `priority=2` + vibrate-tier initial, escalating re-page at 1h / 4h / 24h if `p0-outage` issue stays open with no human comment. Probe-without-paging is not an alarm path (2026-04-21 lesson).
- *DR validated end-to-end.* Weekly drill provisions a fresh VM, bootstraps, restores `/etc/workflow/env` + data volume from offsite, starts daemon, asserts canary-green within SLA. Decoupled restore + start, exit-code propagation, SSH-tunnel probe; no host keystrokes bridge any step.
- *Loop-uptime-maintenance is the authorized escape.* Skill at `.agents/skills/loop-uptime-maintenance/SKILL.md` handles failure classes not yet graduated to layers 1-3. Entry condition: the loop is too broken to self-heal via its own loop. Success metric: usage trends to zero — every incident graduates a failure class out of the skill into layers 1-3.
- *Public-surface canary is required evidence, not final proof.* MCP/chatbot-facing changes also require live Claude.ai `ui-test` for final acceptance (Hard Rule #11).

**Substrate:** `deploy/`, `.github/workflows/uptime-canary.yml`, `.github/workflows/p0-outage-triage.yml`, `.github/workflows/deploy-prod.yml`, `.github/workflows/dr-drill.yml`, `scripts/uptime_canary.py`, `scripts/mcp_public_canary.py`. Acceptance probe catalog: `docs/ops/acceptance-probe-catalog.md`.

**Open evolution:** Validation of the testable assumption — if the host's phone is off for 24h, a secondary paging path (email / desktop / secondary device) still fires at the 4h escalation tick.

_Last audited: 2026-05-28_

---

## Module: Constraints

**Purpose:** Formally verify world rules only where symbolic checking clearly adds value.

**In scope:** Neurosymbolic constraint engine (ASP rules), universe-specific rule packs, constraint evaluation as `Evaluator` primitive instantiation.

**Out of scope:** General quality evaluation (Evolution & Evaluation); domain topology (Engine & Domains).

**Principles:**
- *Neurosymbolic methods are optional leverage.* Universe-specific rules are the only version likely to earn ongoing complexity; generic boilerplate constraints are not enough.
- *Required-files probe applies.* `data/world_rules.lp` (or equivalent) must be probed at startup — silent absence reducing the engine to a no-op violates Hard Rule #8.

**Substrate:** `workflow/constraints/`, `data/world_rules.lp` (universe-specific rule packs).

**Open evolution:** Second universe's rule pack as the test that constraint engine is domain-agnostic.

_Last audited: 2026-05-19_

---

## Reference: System Shape

```text
Users / Hosts
    <->
MCP-compatible clients / Host dashboard
    <->
FastAPI + Workflow Server (MCP) control plane
    <->
Daemon (LangGraph)
    |
    +-----------+---------------+---------------+
    |           |               |               |
State/Artifacts Search/Tools  Evaluation    Providers
    |
Harness / Traces / Tests / Coordination
```

The daemon writes autonomously. MCP clients and the host dashboard are the user-facing interfaces. Communication is file- and artifact-based: daemon writes to disk, API/MCP expose state and actions, harness inspects artifacts and traces.

**Backend stack (target):** Supabase — Postgres (catalog + ledger + inbox), Realtime broadcast (presence + change broadcast), Auth (GitHub OAuth + sessions), Row-Level Security (visibility + sensitivity at DB layer), Storage (S3-compatible canon uploads). One stack covers five concerns otherwise requiring separate glue. Postgres exit path is self-hostable without application rewrite. Decision: `docs/design-notes/2026-04-18-full-platform-architecture.md §3.2`.

**Auth + identity:** GitHub OAuth as the single identity primitive at launch, covering all three tiers without account stitching. OAuth 2.1 + PKCE at the MCP edge (MCP spec 2025-11-25 mandate). Session tokens scoped per user; RLS enforces per-user visibility at the DB layer. Native accounts (email/passkey) added when >~15% of sign-up attempts bounce. Decision: `docs/design-notes/2026-04-18-full-platform-architecture.md §7`.

**Real-time strategy — versioned rows + broadcast, NOT CRDT.** User collaboration is coarse-grained: users edit different nodes concurrently, or edit the same node with last-write-wins + update-since-you-viewed conflicts. Comments are append-only. Versioned Postgres rows + Supabase Realtime + presence channels covers this at a fraction of CRDT's complexity. CRDT is an escalation path for any specific artifact needing it later, not a baseline. Decision: `docs/design-notes/2026-04-18-full-platform-architecture.md §2.2`.

**Single canonical public entry point.** The daemon surface has exactly one public URL: `https://tinyassets.io/mcp`. Debug/diagnostic access is via Cloudflare Worker observability + tunnel logs, NOT a second public DNS record. The Worker requires a `mcp.tinyassets.io` hostname for internal tunnel-routing subrequests; this record is retained as Access-gated internal plumbing, not a second public surface. Host directive 2026-04-20; runbook: `docs/ops/dns-tunnel-single-entry-cutover.md`.

---

## Reference: State & Artifacts

Strong agents run on explicit typed state and external artifacts, not hidden chat memory. If state shapes drift or artifacts become untrustworthy, the system looks smart locally and fails over time.

**Live state stays thin.** Identity, intent, control flags, and artifact handles. Rich context, prior outputs, and durable memory belong in saved artifacts and registries. Persist each step immediately; the next node may cache the just-finished result locally, but saved refs are authoritative.

**Durable artifacts outlive context windows.** Plans, notes, checkpoints, logs, learned heuristics, subagent outputs belong in external storage.

**Scene commits emit structured packets.** Every accepted scene writes a validated JSON packet (facts, promises, entities, POV, deltas) beside the prose. Packets are the backbone for timelines, promise tracking, continuity, typed retrieval.

---

## Reference: Full-Platform Architecture

**Status: integrated.** The architectural commitments — multi-tenant multiplayer platform, Postgres-canonical catalog with GitHub as export sink, versioned-rows real-time strategy, opt-in daemon hosting, paid-market on top of a free authoring substrate, full uptime with zero hosts online, three user tiers, evaluation-as-platform-primitive, node discovery + remix surface — are the durable canonical architecture, distributed across the modules above.

**Single source of detail:** `docs/design-notes/2026-04-18-full-platform-architecture.md` (~3000 LOC) carries the full reasoning, tradeoff analysis, scale-audit numbers, and host-decision lineage. PLAN.md modules are the principle-level reference; the design note is the integrated detail. Citation chain: PLAN.md module principle → design-note section → host-decision lineage. No layer skipped.

**Durable coordination proposal:** `docs/design-proposals/design-001-durable-coordination-architecture-where-workflow-s-structura.md` explains how Workflow's structural graph vocabulary supports resumable, multi-actor coordination over time.

**Phased rollout — explicitly rejected.** The earlier "Phase 1 thin relay → Phase 2 state migration → Phase 3 paid failover" plan was rejected 2026-04-18 because (a) authoring must work with zero daemons running, which Phase 1 ships 0% of, and (b) building the final shape in one push avoids three throwaway migrations that each require re-teaching users + re-cutting Claude.ai connectors. The single-build target ("weeks not months") is canonical sequencing. Historical phased plan retained as superseded context only.

---

## Design Decisions

ADR-style index of decisions that don't fit cleanly inside one module.

- **Universe = single consistent reality.** Alternative realities are separate universes. Data isolation between universes is the only hard boundary.
- **Upload provenance.** Each upload is tagged ("published book", "rough notes") and the writer weights canon sources accordingly.
- **Unified notes.** All feedback is timestamped, attributed notes on files. One system, one format, one durable store per universe.
- **Writer self-indexes.** The writer produces entity and fact data when it commits. No separate extraction role is the end state.
- **Editorial feedback, not scoring.** Natural-language notes about what works, what's concerning, and whether a concern is provably wrong. No numeric rubric in the core loop.
- **Graph hierarchy is scaffolding.** Structure should emerge from the daemon's choices wherever possible, not fixed counters.
- **Workflow Server, not single-user daemon.** Control plane runs in the cloud (currently DO Droplet, formerly a host laptop); many named users connect through MCP clients.
- **Multi-tenant by design, single-tenant today as N=1.** Every daemon-related design must scale from `(user, daemon)` to `(N users, M daemons per user)` without rewrite. Any architecture that would require a migration to multi-user is rejected. Memory `project_daemons_are_multi_tenant_by_design.md`.
- **Workflow-first, domain-agnostic identity.** Fantasy authoring is an early benchmark domain, not the trunk.
- **MCP clients + local host dashboard.** MCP is the shared collaborative surface; host operational controls live in a local dashboard.
- **Daemons are the public agent identity.** Summonable, forkable, defined by durable soul files. Soul changes create new forks rather than overwriting.
- **Daemon identity is platform-wide, not domain-specific authoring.** Migrate or rename the current `author_definitions` substrate into the general daemon registry. Content provenance retains `author_id` + `author_kind` discriminator.
- **Branch-first collaboration.** Branches are first-class, long-lived, public-forkable. Reconciliation optional, no fixed mainline.
- **Swarm runtime.** No universe-wide single active daemon. Runtime capacity and daemon identity are separate resources.
- **GitHub is an export sink, not the canonical store.** Canonical state lives in Postgres (Supabase-hosted at launch). GitHub receives a periodic flat-YAML export of public goals/branches/nodes; contributions via GitHub PR are accepted via a round-trip YAML → webhook → Postgres import path. One-way-door decision (host-approved 2026-04-18).
- **Local-first execution, git-native sync (bridge state).** DO Droplet self-host is the current bridge. Postgres-canonical replaces local-first when the control-plane backend ships.
- **User-controllable state architecture.** Users should eventually inspect, steer, and redesign workflow/state structure conversationally.
- **Multi-host is the destination.** Local-host is important, but end-state is a network of hosts contributing model capacity to shared projects.
- **The system must evolve itself.** Stagnation is the worst failure mode.
- **Context is tools, not pre-assembly.** The writer should query through tools. Pre-assembly is transitional.
- **Bad decisions are data.** When the daemon decides poorly, improve goals/tools/state/evals. Don't reflexively add rules.
- **Human control belongs at irreversible boundaries.** Bounded loops for autonomy; pause/stop/takeover/confirmation at the edge.
- **Engine is infrastructure, not topology.** `workflow/` is a shared library plus optional profiles. Each domain owns its own graph.
- **Currency naming + test rail.** Real currency reference is `Destiny (tiny)` with symbol `tiny`. Current paid-market tests use `test tiny` on Base Sepolia only. Mainnet Destiny/tiny settlement, staking, DAO voting, and treasury flows are deferred. See `docs/design-notes/2026-04-29-token-naming-and-test-currency.md`.

---

## Open Tensions

- **Tool-driven context is the target; pre-assembly is transitional.** If the writer is mostly fed pre-assembled blobs, this architecture is not finished.
- **Structural scaffolding should shrink** as models improve — hard maxima and routing thresholds only survive if evals prove they help.
- **Hybrid memory must become one policy.** Retrieval and memory may be separate implementations but should behave like one coherent decision system from the daemon's perspective (Brain Module is the convergence point).
- **State contract mismatches are bugs.** TypedDicts, node outputs, and downstream consumers must agree.
- **God-module decomposition is in-flight, not done.** `workflow/universe_server.py` is down from 14k peak to 972 LOC live in main; remaining cluster extractions sequenced per `docs/audits/2026-04-25-universe-server-decomposition.md`.
- **Postgres-canonical vs GitHub-canonical is the largest unresolved architectural decision.** Until host answers, two design shapes coexist in this document. Decision should land soon to avoid further documentation divergence.
- **External-write authority + idempotency + reward release.** Per the 2026-05-19 design note draft, the holistic model is awaiting host steering on 6 open questions before implementation begins.
- **Per-Goal strict-mode rollout for Brain authority-condition policy.** Permissive by default; strict-mode opt-in is unscoped.
