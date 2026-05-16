# Workflow — Plan

How the system should work and why. Architecture, principles, and design decisions — high-level only. Implementation detail lives in the code.

For live state, see STATUS.md. For how to work on the project, see AGENTS.md. Changes here require user approval.

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

## Canonical Work Substrate Vocabulary

**Status: canonical as of 2026-05-10.** Workflow's foundational substrate
vocabulary is six work concepts plus five permissioned MCP handles. Coding
sessions should use this vocabulary when naming architecture, docs, tool
metadata, and future design notes unless a narrower domain term is explicitly
needed.

The six base concepts describe durable work at the graph layer:

| Concept | Meaning |
|---|---|
| `Node` | A typed unit of work, judgment, transformation, or evidence capture. |
| `Edge` | A declared transition between nodes, including conditional routing and review paths. |
| `State` | The durable typed record a graph reads, writes, reduces, checkpoints, and resumes. |
| `Scope` | The authority and context boundary for a work item: user, branch, goal, daemon, host, commons, or other bounded surface. |
| `Run` | An execution attempt with inputs, outputs, provider traces, checkpoints, and evidence. |
| `Trigger` | The event or schedule that asks Workflow to start, resume, replay, or route work. |

The five MCP handles describe the small permissioned control surface agents use
to inspect and act on those concepts:

| Handle | Authority |
|---|---|
| `read.graph` | Inspect graph structure, state summaries, lineage, runs, and public metadata. |
| `write.graph` | Propose or mutate graph definitions, state, scopes, edges, and work artifacts under the caller's authority. |
| `run.graph` | Start, resume, cancel, replay, or otherwise control graph execution within the caller's scope and confirmation policy. |
| `read.page` | Read wiki, commons, docs, request, and explanation pages that contextualize the graph. |
| `write.page` | Draft or update wiki, commons, docs, request, and explanation pages through the same reviewable artifact path. |

These names are substrate vocabulary, not a mandate that every runtime function
or MCP tool be named exactly this way. Concrete tool names may remain
client-shaped for compatibility, but they should map back to one or more of
these handles in docs, permission checks, and tool descriptions. The older
8-engine-primitive framing in
`docs/design-notes/2026-04-26-engine-primitive-substrate.md` remains a useful
historical pressure test over implementation modules; it is no longer the
canonical primitive count for project architecture. The canonical source for
the promotion rationale is
`docs/design-notes/proposed/2026-05-10-promote-work-substrate-vocabulary.md`.

---

## Cross-Cutting Principles

## Brain Module

Workflow's Brain module is the composition layer for retrieval, memory, and durable state. It subsumes the older "Retrieval And Memory" and "State And Artifacts" framings into one discipline: every agent step should know what to read, what state to trust, what artifact to update, and what prior art to consult before it invents a new pattern.

Reference implementations worth studying before changing Brain-shaped systems include OB1-style operator memory and the Karpathy LLM Wiki pattern: small, inspectable pages that compress lessons into reusable working context instead of burying them in transcripts. Workflow should apply the same consult-prior-art habit to public commons pages, branch state, notes, and run artifacts.

Design implications:

- Brain is a policy over existing primitives (`read.page`, `write.page`, `read.graph`, `write.graph`, `run.graph`), not a new monolithic tool.
- Retrieval, memory, notes, state, artifacts, and wiki pages are one working set with different trust and freshness properties.
- Before adding a Brain primitive, first show why current graph/page primitives cannot compose the behavior.
- Every Brain write-back should be reviewable, attributable, and reusable by future daemons.

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

**Module shape is part of the architecture.** A flat namespace of 35 modules at `workflow/` root signals "no opinion about boundaries." A god-module of 10k lines signals "boundaries deferred indefinitely." Both are forms of architectural debt. The Module Layout section below codifies the target shape.

**Cleanup operations against scene-attributed data must scope across all DBs that hold scene-attributed rows.** Generalizes the Fix E lesson (task #49): a cleanup path that prunes one DB but not its sibling leaves orphan derivatives that masquerade as canon on the next retrieval cycle. When a new DELETE or mutation operates on rows keyed to scene_id (or any cross-store attribution), scope it against both `knowledge.db` and `story.db` from the start, or explicitly document the opt-out with reason. Per the migration-audit follow-up at `docs/audits/2026-04-19-schema-migration-followups.md`.

---

## Module Layout (target shape)

The canonical subpackage layout the codebase is moving toward. Rooted in the spaghetti audit at `docs/audits/2026-04-19-project-folder-spaghetti.md`. Where the current state diverges from this target, the gap is in-flight work (rename end-state collapse + post-rename cleanup), not architectural disagreement.

`workflow/` is the engine package. Domain packages (`fantasy_daemon/`, future `research_daemon/`, etc.) consume from it. The engine layout follows five canonical subpackages plus a small set of correctly-flat modules:

| Subpackage | Responsibility |
|---|---|
| `workflow/api/` | MCP tool surfaces. Mounted submodules per capability cluster. Landed today (2026-04-26): `api/helpers.py`, `api/wiki.py`, `api/status.py`. In-flight per `docs/audits/2026-04-25-universe-server-decomposition.md` 8-step plan: `api/runs.py`, `api/evaluation.py`, `api/runtime_ops.py`, `api/market.py`, `api/branches.py`. Per FastMCP `mount()` pattern. **No god-modules.** |
| `workflow/storage/` | Schema + bounded-context storage layers (`storage/accounts.py`, `storage/universes_branches.py`, `storage/requests_votes.py`, `storage/notes_work_targets.py`, `storage/goals_gates.py`). Shared `_connect()` + migrations in `__init__.py`. |
| `workflow/runtime/` | Run scheduling primitives. Consolidates `runs.py`, `work_targets.py`, `dispatcher.py`, `branch_tasks.py`, `subscriptions.py`, plus existing `producers/` + `executors/` subpackages. `runtime/__init__.py` re-exports the public API. |
| `workflow/bid/` | Per-node paid-market mechanics. Consolidates `node_bid.py`, `bid_execution_log.py`, `bid_ledger.py`, `settlements.py`. |
| `workflow/servers/` | Entry-point shells. The integration layer that mounts `api/` submodules. Hosts `workflow_server.py` (post-layer-3 rename), `daemon_server.py`, `mcp_server.py`. **Acts as routing surface, not the place action logic lives.** |

Existing subpackages that already conform: `auth/`, `catalog/`, `checkpointing/`, `constraints/`, `context/`, `evaluation/`, `ingestion/`, `knowledge/`, `learning/`, `memory/`, `planning/`, `providers/`, `retrieval/`, `desktop/`, `testing/`, `utils/`.

Correctly-flat modules at root (small typed surfaces with no clear sibling): `protocols.py`, `exceptions.py`, `notes.py`, `packets.py`, `config.py`, `identity.py`, `discovery.py`, `singleton_lock.py`, `domain_registry.py`, `registry.py`, `preferences.py`, `compat.py` (post-Phase-5), `__init__.py`, `__main__.py`, `docview.py`.

**Migration policy.** When a flat module crosses ~500 LOC OR overlaps a sibling's responsibility, it gets a subpackage. New work goes into the target shape; legacy gets refactored opportunistically (the spaghetti audit ranks the priority order). The five subpackages above are the durable commitment — anything new must fit one of them or earn its place at the root with a one-line explanation in this section.

---

## Design Decisions

- **Universe = single consistent reality.** Alternative realities are separate universes. Data isolation between universes is the only hard boundary.
- **Upload provenance.** Each upload is tagged ("published book", "rough notes") and the writer weights canon sources accordingly.
- **Unified notes.** All feedback is timestamped, attributed notes on files. One system, one format, one durable store per universe. (Replaces the obsolete `STEERING.md` directive surface.)
- **Writer self-indexes.** The writer produces entity and fact data when it commits. No separate extraction role is the end state.
- **Editorial feedback, not scoring.** Natural-language notes about what works, what's concerning, and whether a concern is provably wrong. No numeric rubric in the core loop.
- **Graph hierarchy is scaffolding.** Structure should emerge from the daemon's choices wherever possible, not fixed counters.
- **Two review gates, one target registry.** Foundation review hard-blocks on unsynthesized uploads; authorial review may choose any justified work.
- **Workflow Server, not single-user daemon.** The control plane runs in the cloud (currently the DO Droplet, formerly a host laptop); many named users connect through MCP clients. (Renamed from "Universe Server" — the platform-name rebrand. The MCP namespace is currently `workflow-universe-server` pending the layer-3 plugin-dir rename per `docs/design-notes/2026-04-19-universe-to-workflow-server-rename.md`.)
- **Multi-tenant by design, single-tenant today as N=1.** Every daemon-related design — dispatcher, claim-lock, identity, heartbeat, host pool registry, cloud-worker supervisor — must scale from `(user, daemon)` to `(N users, M daemons per user)` without rewrite. Today's live system is one user + a small handful of daemons; that is the degenerate case of the general shape, not its target. Any architecture that would require a migration to multi-user is rejected. (Host directive 2026-04-22; memory `project_daemons_are_multi_tenant_by_design.md`.)
- **Workflow-first, domain-agnostic identity.** Fantasy authoring is an early benchmark domain, not the trunk.
- **Open workflow playground.** Open-source, social, remixable, viral enough to spread. Playful surface, serious utility.
- **MCP clients + local host dashboard.** MCP is the shared collaborative surface; host operational controls live in a local dashboard.
- **Two coexisting executors, one file-locked claim.** Node execution runs on the cloud-side `cloud_worker` supervisor (distinct identity `cloud-droplet`) *and* on any host-side tray (identity `host`). Both call `branch_tasks.claim_task`; the file-lock sidecar guarantees no double-claim. The cloud worker closes the "MCP reachable but nothing executes" gap — `last_activity_canary` is the proof signal. Host-tray remains valid for users who want local-model runs with their own keys. (Cloud-worker shipped in 4d1265c; supervises `fantasy_daemon` subprocess, inherits `/etc/workflow/env`.) Per-universe dashboards are orthogonal to executor identity.
- **Private chats, public actions.** Conversations stay private; any universe-affecting action is publicly attributable.
- **Daemons are the public agent identity.** Summonable, forkable, defined by durable soul files. Soul changes create new forks rather than overwriting. ("Author" → "daemon" rename in flight; agent-runtime concept is `daemon_id`, content-authorship concept stays `author_id` + `author_kind` discriminator. See `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` §1.5.)
- **Daemon identity is platform-wide, not domain-specific authoring.** The current `author_definitions` / soul-hash / runtime-instance substrate is transitional: preserve the useful soul, fork, fingerprint, and runtime concepts, but migrate or rename it into the general daemon registry rather than entrenching a fantasy-author-specific author model. Content provenance still uses `author_id` + `author_kind`; daemon soul identity is runtime identity, eligibility identity, and personality/policy.
- **Branch-first collaboration.** Branches are first-class, long-lived, public-forkable. Reconciliation optional, no fixed mainline.
- **Swarm runtime.** No universe-wide single active daemon. Runtime capacity and daemon identity are separate resources.
- **Host daemon fleets are capacity-bounded, not product-capped.** The one-daemon host posture was a development/testing throttle, not product design. A host may summon as many daemons as they can afford and operate, including multiple daemons on the same provider. Second-and-later same-provider summons show warning-only subscription/rate-limit guidance with an estimated required provider plan; they do not enforce a platform subscription gate. Target scale is many hosts, potentially thousands, each running as many soul-bearing or soulless daemons as their provider capacity supports.
- **GitHub is an export sink, not the canonical store.** Canonical state lives in Postgres (Supabase-hosted at launch). GitHub receives a periodic flat-YAML export of public goals/branches/nodes; contributions via GitHub PR are accepted via a round-trip YAML → webhook → Postgres import path. One-way-door decision (host-approved 2026-04-18, `docs/design-notes/2026-04-18-full-platform-architecture.md §4`) — reverting after realtime collaboration is active requires data migration.
- **Local-first execution, git-native sync (bridge state).** The DO Droplet self-host migration (2026-04-20) is the current bridge. Postgres-canonical replaces local-first when the control-plane backend ships.
- **User-controllable state architecture.** Users should eventually inspect, steer, and redesign workflow/state structure conversationally.
- **Multi-host is the destination.** Local-host is important, but end-state is a network of hosts contributing model capacity to shared projects.
- **The system must evolve itself.** Stagnation is the worst failure mode. Workflow, memory policy, retrieval, evaluation, naming should all learn from research and outcomes over time.
- **Native optimization, not an ASI-Evolve clone.** Workflow adopts the ASI-Evolve/AlphaEvolve lesson as an engine-native pattern: users ask through any MCP-connected chatbot, the platform runs bounded evaluator-driven optimization over nodes, branches, evaluators, prompts, policies, and topology, and accepted changes land through normal versioned/provenance-aware branch history. Do not vendor or parallel-run a separate ASI pipeline that bypasses MCP, branch lineage, host-pool claiming, evaluator chains, privacy gates, or real-world outcome gates. Canonical rationale: `docs/audits/2026-05-02-asi-evolve-architecture-implications.md`; integration design: `docs/design-notes/2026-05-02-community-evolvable-optimization-integration.md`.
- **Work targets are the unit of intentional work.** Any locus the daemon may work on next — uploads, canon repair, world notes, plans, scenes.
- **Tags stay loose; role and lifecycle stay guarded.** Publishable-vs-notes role, publish stage, and true discard are explicit state transitions.
- **Context is tools, not pre-assembly.** The writer should query through tools. Pre-assembly is a transitional compromise.
- **Bad decisions are data.** When the daemon decides poorly, improve goals/tools/state/evals. Don't reflexively add rules.
- **Scene commits emit structured packets.** Every accepted scene writes a validated JSON packet (facts, promises, entities, POV, deltas) beside the prose. Packets are the backbone for timelines, promise tracking, continuity, typed retrieval.
- **Durable artifacts outlive context windows.** Plans, notes, checkpoints, logs, learned heuristics, subagent outputs belong in external storage.
- **Human control belongs at irreversible boundaries.** Bounded loops for autonomy; pause/stop/takeover/confirmation at the edge.
- **Engine is infrastructure, not topology.** `workflow/` is a shared library plus optional profiles. Each domain owns its own graph. The engine is judged by whether a *second* domain can adopt it without engine changes — fantasy is the benchmark, not the trunk.
- **Memory interface is query semantics, not tier names.** Three tiers (core/episodic/archival) is conceptual; the public interface feels like faceted search, not tier addressing.
- **Trust-critical tools are self-auditing.** Tools that touch privacy, cost, routing, scope, or moderation expose structured evidence + structured caveats; the chatbot composes the user-facing narrative on top of the evidence. The chatbot cannot rubber-stamp because the caveats are part of the tool's contract. (See `docs/design-notes/2026-04-19-self-auditing-tools.md` for the pattern + 5 instantiations: memory-scope, provider routing, privacy decisions, autoresearch fulfillment, moderation.)

---

## System Shape

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

The daemon writes autonomously. MCP clients and the host dashboard are the user-facing interfaces. Communication is file- and artifact-based: daemon writes to disk, API/MCP expose state and actions, harness inspects artifacts and traces. AGENTS.md, PLAN.md, STATUS.md, notes.json, checkpoints, logs, tests are part of the same design philosophy.

**Backend stack (target):** Supabase — Postgres (catalog + ledger + inbox), Realtime broadcast (presence + change broadcast), Auth (GitHub OAuth + sessions), Row-Level Security (visibility + sensitivity at DB layer), Storage (S3-compatible canon uploads). One stack covers five concerns otherwise requiring separate glue. Postgres exit path is self-hostable without application rewrite. Rejected: Convex (TypeScript lock-in), Firebase (pay-per-read unpredictable, no Postgres), custom realtime on small VPS (negative ROI at current scale). (Decision rationale: `docs/design-notes/2026-04-18-full-platform-architecture.md §3.2`.)

**Auth + identity:** GitHub OAuth as the single identity primitive at launch, covering all three tiers without account stitching. OAuth 2.1 + PKCE at the MCP edge (MCP spec 2025-11-25 mandate). Session tokens scoped per user; RLS enforces per-user visibility at the DB layer. Native accounts (email/passkey) added when >~15% of sign-up attempts bounce at the GitHub wall. (Decision rationale: `docs/design-notes/2026-04-18-full-platform-architecture.md §7`.)

**Real-time strategy — versioned rows + broadcast, NOT CRDT.** User collaboration is coarse-grained: users edit different nodes concurrently, or edit the same node with last-write-wins + update-since-you-viewed conflicts. Comments are append-only. Versioned Postgres rows + Supabase Realtime + presence channels covers this at a fraction of CRDT's complexity. CRDT is an escalation path for any specific artifact needing it later, not a baseline requirement. (Decision rationale: `docs/design-notes/2026-04-18-full-platform-architecture.md §2.2`.)

**Single canonical public entry point.** The daemon surface has exactly one public URL: `https://tinyassets.io/mcp`. Debug/diagnostic access is via Cloudflare Worker observability + tunnel logs, NOT a second public DNS record. Tradeoff explicitly accepted: losing the cheap dual-probe URL localization trick in exchange for a smaller attack surface and zero ambiguity about what users should connect to. The 2026-04-19 P0 outage (`api.tinyassets.io` appearing then disappearing) is additional evidence against multiple public entry points. Implementation caveat: the Cloudflare Worker requires a `mcp.tinyassets.io` hostname for internal tunnel-routing subrequests; this record is retained as Access-gated internal plumbing, not a second public surface. The principle is "one URL users connect to"; the implementation allows an Access-protected internal record that is functionally unreachable from the public internet. (Host directive 2026-04-20; options analysis: `docs/design-notes/2026-04-20-single-entry-execution-options.md`; cutover runbook: `docs/ops/dns-tunnel-single-entry-cutover.md`.)

---

## Full-Platform Architecture (Canonical)

**Status: integrated.** The architectural commitments below — multi-tenant multiplayer platform, Postgres-canonical catalog with GitHub as export sink, versioned-rows real-time strategy, opt-in daemon hosting, paid-market on top of a free authoring substrate, full uptime with zero hosts online, three user tiers, evaluation-as-platform-primitive, node discovery + remix surface — are the durable canonical architecture. They are not a future proposal.

**Single source of detail:** `docs/design-notes/2026-04-18-full-platform-architecture.md` (~3000 LOC) carries the full reasoning, tradeoff analysis, scale-audit numbers, and host-decision lineage. PLAN.md is the principle-level reference; the design note is the integrated detail. Future readers consult both — PLAN.md to understand WHY each principle holds, the design note to understand HOW each principle was reached.

**Phased rollout — explicitly rejected.** The earlier "Phase 1 thin relay → Phase 2 state migration → Phase 3 paid failover" plan was rejected by host on 2026-04-18 on the grounds that (a) authoring must work with zero daemons running, which Phase 1 ships 0% of, and (b) building the final shape in one push avoids three throwaway migrations that each require re-teaching users + re-cutting Claude.ai connectors. The single-build target ("weeks not months") is the canonical sequencing model. The historical phased plan (`docs/design-notes/2026-04-18-persistent-uptime-architecture.md`) is retained as superseded historical context only.

**Where the design note lives in PLAN.md:** the principles below already cite specific sections of the design note as decision rationale — Supabase stack (§3.2), GitHub OAuth at MCP edge (§7), versioned-rows over CRDT (§2.2), host-pool registry (§5), zero-daemons-for-authoring (§1), per-piece privacy (§17). When in doubt about an architectural commitment, the citation chain is: PLAN.md principle → design-note section → host-decision lineage. No layer is skipped.

---

## Multiplayer Daemon Platform

**Goal:** A multi-tenant workflow platform where many users and daemons collaborate without collapsing into one shared chat or one hidden runtime.

**Principle:** Separate identity from runtime. Daemons are public, forkable, summonable agent identities defined by soul files; runtime instances are resource allocations bound to providers, models, and executor hosts. Every `(user, daemon, executor)` tuple is independently addressable; today's degenerate case is N=1 of the general shape. Host fleet size is an operating-cost decision, not a platform cap: hosts can run many daemons, including many on one provider, with warning-only provider-plan/rate-limit estimates for additional same-provider daemons.

**Always ready for the next user and daemon fleet.** A host-only or private-alpha rollout is an exposure gate, not a single-user architecture. Storage, authorization, queues, budgets, audits, daemon bindings, and runtime activations carry tenant/owner boundaries from the first build so more users and more daemons can join by changing exposure and capacity limits, not by redesigning the substrate.

**Soul eligibility.** Nodes and gates may declare whether daemon souls are allowed, forbidden, required, replaced by a node/gate-provided soul, or combined with a temporary node/gate header. They may also declare domain requirements for eligible souls, such as scientific, legal, artistic, local-model-only, or other community-defined qualifications. Claim-time verification checks the daemon soul fingerprint and required claims/proofs before execution; prompt composition then applies the accepted host soul, provided soul, or temporary header according to the node/gate policy.

**Soul-guided dispatch.** After a daemon finishes a node or gate, a soul-bearing daemon returns to a decision step that lists all work it is eligible to claim, including node/gate soul policy, domain requirements, required provider/capability, and any offer. The daemon may choose highest money, specific interests, reputation, public-good impact, or refusal to work on soul-incompatible nodes according to its soul. Soulless daemons use the default platform dispatcher policy.

Defaults: cloud control plane with named accounts; private per-user MCP sessions; shared tool contract; per-universe dashboards; public attributable actions; public read + public fork; no fixed mainline; long-lived branch coexistence; admin-gated runtime capacity; user votes for daemon forks; multi-host execution from day one (cloud-droplet + opt-in host-tray coexist via file-locked claim).

**Zero daemons required for authoring.** Node/branch/goal creation, editing, forking, and collaboration work with no daemon running anywhere. Daemon hosting is opt-in for execution work. This is a load-bearing requirement — any architecture where authoring depends on a running daemon violates it. (The phased plan was rejected on this basis; see `docs/design-notes/2026-04-18-full-platform-architecture.md §1`.)

**Host pool registry.** Every daemon host declares capabilities (node types, LLM models, price), visibility (`self` / `network` / `paid`), and heartbeat state to the control plane. Daemons are execution-tier, not control-plane. The control plane dispatches paid work to hosts and settles via the ledger; daemons poll outbound. (Decision rationale: `docs/design-notes/2026-04-18-full-platform-architecture.md §5`.)

---

## State And Artifacts

**Goal:** Make long-horizon reasoning legible, durable, and inspectable.

**Principle:** Strong agents run on explicit typed state and external artifacts, not hidden chat memory. If state shapes drift or artifacts become untrustworthy, the system looks smart locally and fails over time.

---

## Daemon-Driven

**Goal:** Let the daemon make creative and structural decisions whenever the model can reliably do so.

**Principle:** Hardcoded thresholds and stage gates are scaffolding. Test each by removing it. When the daemon makes a bad decision, improve the goal/context/tools/evals rather than layering on recipes.

---

## Scene Loop

**Goal:** Produce one unit of work that is grounded, coherent, ambitious, and improves through external feedback.

**Principle:** Orient → plan → draft → commit is useful only if each step adds value. If a stronger model with better tools can do equivalent work in fewer steps, flatten the loop.

---

## Work Targets And Review Gates

**Goal:** Let the daemon choose the next most justified locus of work.

**Principle:** One unified work-target registry. Foundation review hard-blocks on unsynthesized uploads only; authorial review may choose any justified move once hard blockers are clear. Targets carry role (notes | publishable), publish stage, lifecycle, tags, and artifact refs. notes → publishable must pass through provisional first. `marked_for_discard` is not the same as `discarded` — true discard is a later review decision, recoverable.

---

## Retrieval And Memory

**Goal:** Ground every decision in the best available evidence without flooding the model with irrelevant context.

**Principle:** Retrieval and memory are one system with multiple backends (KG, vector, hierarchical summaries, world-state DB, notes, direct tool calls). The routing policy matters more than any individual backend.

---

## Evaluation

**Goal:** Improve quality through feedback, not brittle gates.

**Principle:** Layered — deterministic checks for provable failures, an editorial reader for natural-language critique, environment-grounded artifacts and traces for verification. One strong independent reader beats a committee of shallow scorers. **Evaluation is platform-wide, not fantasy-specific** — the §33 unifying frame (`docs/design-notes/2026-04-15-evaluation-layers.md` if landed; otherwise the §33 framing in the full-platform note) treats fantasy judges, autoresearch metrics, moderation rubrics, real-world outcomes, and discovery ranking as instantiations of one `Evaluator` primitive.

**Accepted direction: Acceptance Scenario Packs.** Host approved the AgencyBench-derived direction on 2026-05-02: Workflow should grow reusable long-horizon scenario packs that combine user simulation, rubric checks, MCP/API or browser evidence, and artifact capture into `EvalResult` evidence. Do not vendor AgencyBench or its harness; define Workflow-native scenario contracts after the required opposite-provider research review. Canonical rationale: `docs/audits/2026-05-02-frontier-repo-radar-2.md`.

---

## Community Evolvable Optimization

**Goal:** Make every useful piece of the platform improvable by users and daemons without requiring the project maintainers to be online.

**Principle:** Optimization is a native run type, not a sidecar research script. A user with any MCP-connected chatbot should be able to say "improve this branch overnight under this budget and ask before merging"; Workflow then creates versioned candidates, runs locked evaluators, records typed lessons, preserves lineage, and proposes or applies changes according to the user's merge policy.

**User model:** The primary user is not a Python researcher running a local experiment. The primary user is a person steering through Claude.ai, ChatGPT, Open WebUI, LibreChat, a local IDE, or any future MCP client. Chat remains the control station. The daemon and host network do the work. Users can redesign branches, evaluators, and optimization policy conversationally; the platform translates that into bounded specs, not hidden prompt magic.

**Community model:** Branches, nodes, evaluators, and lessons are remixable public commons when privacy policy permits. The platform should preserve many competing solution families rather than collapse to one global "best" workflow. Quality-diversity search, lineage, attribution, and real-world outcome gates are core to keeping the project alive and community-evolvable.

**Safety model:** Candidate generators cannot edit the evaluator or the locked harness they are being judged by. Optimization runs declare editable surface, evaluator chain, budget, stop conditions, merge policy, provenance, and visibility up front. Private instance data must not be promoted into reusable cognition unless the privacy layer explicitly permits it.

**Implementation stance:** First ship contracts: `EvaluatorResult`, `OptimizationRun`, typed analyzer lessons, and MCP-facing actions that compose existing `runs`, `branches`, `evaluation`, `host_pool`, and provenance primitives. Runtime refactors must strengthen those primitives instead of adding a parallel ASI-Evolve-style control plane.

---

## Constraints

**Goal:** Formally verify world rules only where symbolic checking clearly adds value.

**Principle:** Neurosymbolic methods are optional leverage. Universe-specific rules are the only version likely to earn ongoing complexity; generic boilerplate constraints are not enough.

---

## Providers

**Goal:** Keep the system running and preserve role separation without hiding failure.

**Principle:** Pick the best provider per role, then use fallback chains and parallel diversity where they improve resilience. Error loudly when the remaining provider can't produce acceptable work. Fake success is worse than failure.

**Principle (fallback chain correctness is a first-class invariant):** Every provider named in a fallback chain must be either registered AND reachable at startup, or explicitly excluded at startup with a logged reason. Phantom chain entries are a bug. A chain that reads `[claude-code, codex, gemini-free, ...]` but whose first entry's CLI binary is absent from the container silently degrades the whole chain — operators reading config see one chain; the runtime iterates a different one. Register-and-probe at startup; emit structured evidence of the effective chain via `get_status`; refuse to advertise unreachable providers as available. (Corroborated by BUG-025 + 2026-04-21 prod-LLM-binding incident; Gemini/Groq unregistered in prod fallback plus claude-code phantom registration together produced the 2026-04-23 revert-loop P0.)

**Principle (required files must be probed at startup and fail loud if missing):** When code declares a required on-disk artifact (ASP rule files, schema definitions, seeded fixtures, vendored configs), startup must probe for it and refuse to start if absent — not log a WARNING and continue with an empty fallback. Silent substrate-degradation from missing artifacts produces runs that report success while behaving as no-ops; that violates Hard Rule #8 (fail loudly, never silently) at an earlier lifecycle phase. Deploy-pipeline discipline extends to runtime file probes, not just image-layer contents. (Corroborated by BUG-026: `data/world_rules.lp` absent from container image silently reduced the ASP constraint engine to a no-op; BUG-027 proposes the general startup-probe invariant.)

---

## API And MCP Interface

**Goal:** Let the user steer through natural conversation and MCP tooling without letting any chat surface become the author.

**Principle:** Any MCP-compatible client is a control station, not a creator. The daemon does the creative work. If a chat surface writes story content itself, that indicates a missing daemon path.

**Shipping rule:** MCP tools and prompts publish explicit titles, tags, and behavior hints through the registered FastMCP surface — the daemon exposes a small number of coarse-grained tools, so discoverability metadata is part of the interface contract.

**Module shape rule:** API surfaces live in `workflow/api/` as mounted submodules per capability cluster (FastMCP `mount()` pattern). Server shells in `workflow/servers/` route to them. **No god-modules.** `workflow/universe_server.py` (12.4k LOC as of 2026-04-26, down from 14k peak) is in-flight refactor scope per `docs/audits/2026-04-25-universe-server-decomposition.md` — 3 of 8 steps landed (helpers, wiki, status); 5 remain (runs, evaluation, runtime_ops, market, branches).

---

## Distribution And Discoverability

**Goal:** Installable and discoverable across standard MCP surfaces, Anthropic packaging, and future Conway packaging without changing the portable core.

**Principle:** Keep the core portable; add platform wrappers around it. MCPB packages, Claude Code / Cowork plugins, registry metadata, and future `.cnw.zip` packaging are distribution layers over the same daemon and tool surface, not replacement architectures.

**Principle (MCP host coverage):** Discoverability work is matrix-driven. Claude and ChatGPT are P0 launch gates, but every MCP-capable host is a possible customer surface. The current host support list, caveats, and acceptance proofs live in `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md`.

**Principle (install-readiness is continuous):** Main is a downloadable release at all times. Every change preserves flawless first-install — packaging auto-builds via CI (import probe + plugin drift check), user-facing copy is branded and unambiguous, broken install is a production bug (not a latent issue). Viral spread can happen any day; optimize throughout, not as a pre-release phase.

**Principle (discovery via entry points, not filesystem scan):** Domain discovery uses `importlib.metadata.entry_points(group="workflow.domains")` per PyPA spec. Filesystem scan of `domains/*/skill.py` is a dev-mode fallback for editable worktrees only. Compat aliases stay out of discovery — compat lives in import shims, not in the domain registry contract. (See spaghetti audit hotspot #6.)

**Principle (software surface is declarative and multi-layer-authorized):** The daemon's software surface is declarative, host-registered, and multi-layer-authorized. Nodes declare `required_capabilities` as a first-class field. Per-host capability registry resolves what's installed. Missing software auto-installs (host-policy gated). Daemons can invoke arbitrary local software — graphics engines, games, LLMs — via a dedicated `external_tool_node` type that bypasses the Python sandbox but layers security: bundled handler signatures, binary signature verification, universe-level allow-list, per-software host approval, subprocess isolation. Any single layer fails, the others hold. Cross-host software donation (Host A cached installer → Host B on demand) is supported; cross-host node-execution hopping is not.

---

## Harness And Coordination

**Goal:** Make the system operable, testable, replayable, and improvable across both product runtime and AI-to-AI development.

**Principle:** Harnesses are first-class architecture. Browser harnesses, builder automation, traces, regression tests, dashboards, and role-based agent coordination materially improve system intelligence by making behavior legible and correctable. The same principle applies to the development process — the **Three Living Files** (AGENTS.md / PLAN.md / STATUS.md, see `AGENTS.md`) and the verifier/navigator/dev/user-sim roles separate process truth, design truth, live state, quality, direction, and live-mission validation. These roles are architectural capabilities; each provider implements them through its available harness rather than one universal team mechanism. That's not just process; it's part of the theory of durable agentic work.

**GitHub/worktree coordination spine:** Buildable work flows through GitHub-shaped lanes: a current `STATUS.md` Work row, a purpose-named branch, a sibling `../wf-<slug>` worktree, and a PR or draft PR as the fold-back object. Relevant `PLAN.md` modules are the project/module understanding that each lane must review during planning, build, review, and fold-back. `ideas/INBOX.md` is a loose idea feed; its entries can be parked at the bottom of a lane as "Idea feed refs" so they are not forgotten, but they are not design truth or build authority. `ideas/PIPELINE.md`, provider memories, audits, specs, and exec plans are context feeds that must be refactored into current STATUS/worktree/PR state before build. This keeps community ideas and external-research implications alive without turning old docs into parallel build queues.

**Provider-context feed:** Provider-specific memory and automation systems are inputs to the GitHub/worktree spine, not separate planning authorities. `scripts/provider_context_feed.py` scans Claude/Codex/Cursor/shared memory, idea, research, automation, and worktree handoff surfaces at claim, plan, build, review, fold-back, and memory-write checkpoints. Relevant findings are promoted into STATUS/worktree/PR lanes; irrelevant or stale findings are noted or ignored. This keeps hidden provider context from bypassing the community-visible project state.

---

## Live State Shape

**Goal:** Keep live state thin; durable artifacts are the source of truth.

**Principle:** Live state carries identity, intent, control flags, and artifact handles. Rich context, prior outputs, and durable memory belong in saved artifacts and registries. Persist each step immediately; the next node may cache the just-finished result locally, but saved refs are authoritative.

---

## Engine And Domains

**Goal:** `workflow/` is reusable infrastructure; `domains/*` own their graph topology and import what they need.

**Principle:** Extract infrastructure first, prove topology second. Skills (swappable phase implementations, domain tools, eval criteria, state extensions) remain valuable within a graph but don't dictate graph shape. A second domain pressures the engine to prove it's actually domain-agnostic.

**Module-shape commitment (refined):** Engine = `workflow/`. Domains = `domains/<name>/`. Currently fantasy_daemon is the only live domain; the pending engine/domain API separation work (`docs/design-notes/2026-04-17-engine-domain-api-separation.md`) extracts domain-specific MCP actions out of the engine shell into `domains/fantasy_daemon/api/` (or equivalent). The engine shell becomes a routing surface; domains register their actions on startup. The engine-vs-domain seam is *named* — once the separation lands, every action lives in exactly one of: shared engine API (`workflow/api/`) or a domain API (`domains/<name>/api/`). No third location.

Fantasy domain keeps scene/chapter/book/universe names in its own graph. Shared `workflow/` infrastructure uses domain-agnostic names.

---

## Multi-User Evolutionary Design

**Vision:** The world simultaneously pursues shared broad Goals — "research papers", "fantasy writing", "investigative journalism", "scientific meta-analysis", "screenplay production", and more. Each Goal is a first-class shared pursuit; the internet contributes Branches toward it in parallel. The result is not one correct workflow per Goal but a legion of diverse evolving public workflows, all chasing the same ultimate outcome, all improving each other.

**Goal is first-class above Branch.** A Goal is a named pursuit (`research-paper`, `fantasy-novel`). A Branch is one user's concrete take. Many Branches bind to one Goal. "Simultaneously pursue the same Goal via different Branches" is the default collaboration pattern, not forking one canonical Branch. Goals are extensible — any user can propose one; popular Goals accrete Branches, unpopular ones fade.

**Diverse-by-default.** 100 different research-paper workflows from 100 users is a feature, not duplication. Consolidation into "the best" workflow is an anti-pattern; the value is the ecology.

**Outcome gates — real-world impact is the truth signal.** Each Goal declares a ladder of real-world gates beyond the workflow's immediate output. Research papers: draft → peer feedback → submission → acceptance → publication → citations → breakthrough. Legal briefs: draft → attorney review → filing → survives dismissal → trial → conviction. Workflows succeed when outputs advance up the ladder, not when drafts merely look polished. Leaderboards rank on outcome progression. Tracking is self-report first, automated later (DOI, court-docket, sales, awards).

**Required surfaces (not yet built):**
- Goal as first-class object: `goals` table, `Branch.goal_id`, per-Goal browsing.
- Node identity across branches — forks preserve lineage so improvements flow between variants.
- Fork and invent as parallel first-class actions — "improve this one" and "try a different approach" both bind to the same Goal.
- Filter/search over the public Branch corpus per Goal.
- Per-Goal leaderboards (most-run, highest-judged, most-forked, highest-gate-progress).
- Aggregated social judgment signals per node/branch/Goal.
- Authorship + attribution lineage chains.
- Cross-Branch node library per Goal — patterns that work become shared primitives.

**Privacy default:** Per-piece, chatbot-judged. Concept-public by default; instance-private when user data is involved. Chatbot makes per-piece visibility decisions dynamically. (See `docs/design-notes/2026-04-18-full-platform-architecture.md` §17 + memory `project_privacy_per_piece_chatbot_judged.md`.) The earlier "public-by-default; users can mark a branch private for drafting" framing has been refined to per-piece granularity.

**Non-goals for now:** account system MVP scope under Q1; monetization scoped to 1% crypto fee on paid-market bids only; moderation = community-flagged with volunteer-mod review (Q10-host RESOLVED).

**Currency naming + test rail:** The real currency reference is `Destiny (tiny)` with symbol `tiny`. Current Workflow monetization and paid-market tests use `test tiny` on Base Sepolia only. Mainnet Destiny/tiny settlement, staking, DAO voting, and treasury flows are deferred until a later real-currency integration phase; current contract references are naming anchors, not active Workflow rails. See `docs/design-notes/2026-04-29-token-naming-and-test-currency.md`.

---

## Uptime And Alarm Path

**Goal:** The complete system — MCP surface + node execution + collaboration surfaces + paid-market + moderation — stays up 24/7 with zero hosts online. The host machine being asleep for 24h must not extend any outage window past the pager's escalation ladder.

**Principle:** Defense in depth *and* the alarm path itself is host-independent. Every self-heal layer assumes the layers below it will fail; the alarm ladder assumes every self-heal layer will fail. None run on a host machine.

**Three self-heal layers, each catches a different class:**

1. **Container restart (`systemd Restart=always` + `workflow-watchdog.timer`).** Catches transient crashes, OOM-recovery, and hung-but-not-crashed processes. Blind to filesystem-bricked states by design; those fall through to layer 2.
2. **GHA `p0-outage-triage.yml` auto-repair.** Triggered by the `p0-outage` issue label. Before attempting restart, inspects `journalctl` for known-class markers and applies the canonical repair. Six classes covered (5a6b645): OOM, disk-full, image-pull, watchdog-hot-loop, tunnel-token-manual, env-unreadable (the `ENV-UNREADABLE` marker shipped in a62ae30). Self-repair is encoded, not generalized — each class is a witnessed failure with a known remedy. New classes are added as they are witnessed.
3. **Deploy-side invariants.** `deploy-prod.yml` asserts `/etc/workflow/env` is readable by the daemon user immediately after every `sudo sed -i` mutation and independently post-restart (0217175). Prevents the 2026-04-21 perm-regression class at the source.

**Alarm ladder, host-phone-independent:** Pushover paging from the GHA `alarm-sink` step at threshold-cross (2 consecutive reds = ~10 min outage), `priority=2` + vibrate-tier for the initial page, escalating re-page at 1h / 4h / 24h if the `p0-outage` issue remains open with no human comment (19c2261). The probe (uptime-canary at 5-min GHA cron) is the signal source; Pushover is the delivery. Neither runs on a host. The 2026-04-21 P0 (~18h dark) exposed that probe-without-paging is not an alarm path — the canary had fired every tick for 18 hours; nothing paged.

**DR validated end-to-end 2026-04-22.** The drill provisions a fresh Debian VM, bootstraps via `hetzner-bootstrap.sh`, restores `/etc/workflow/env` from offsite (GH release backup assets), restores the data volume from offsite, starts the daemon, and asserts canonical canary-green within SLA. Decoupling of restore + start steps (a8fdb97) + owner-path sweep (9ef6c3d) + exit-code propagation (4f936fe) + SSH-tunnel probe (c50b6e8) together make the drill honest — no host keystrokes bridge any step. Weekly recurrence is the always-on regression check.

**Loop uptime maintenance skill (2026-05-03 add).** A fourth path lives at .agents/skills/loop-uptime-maintenance/SKILL.md — the discipline for handling failure classes not yet graduated to layers 1-3. Entry condition: the loop is too broken to self-heal via its own loop (dispatcher wedged, supervisor in restart loop, daemon subprocess wedged, MCP surface 502, filesystem-bricked state). Every application produces an incident log + substrate improvement + (usually) a PLAN.md update. Success metric is usage trending to zero — every incident graduates a failure class out of the skill into one of the three layers above. The skill is the authorized escape from the user-sim discipline when (and only when) the user-sim path is itself the broken thing.

**What is explicitly *not* in this layer:**
- On-box pagers (share host-fate with the daemon).
- Third-party uptime monitors (probe is not the gap; delivery is).
- "Restart will fix it" as a universal remedy (witnessed to fail when the fault is on the filesystem, not in memory).

**Testable assumption:** If the host's phone is off for 24h, a secondary paging path (email / desktop / secondary device subscribed to the Pushover channel) still fires at the 4h escalation tick. Unvalidated today; validation depends on host's secondary-device setup.

---

## Open Tensions

- **Tool-driven context is the target; pre-assembly is transitional.** If the writer is mostly fed pre-assembled blobs, this architecture is not finished.
- **Structural scaffolding should shrink** as models improve — hard maxima and routing thresholds only survive if evals prove they help.
- **Hybrid memory must become one policy.** Retrieval and memory may be separate implementations, but they should behave like one coherent decision system from the daemon's perspective.
- **State contract mismatches are bugs.** TypedDicts, node outputs, and downstream consumers must agree.
- **God-module decomposition is in-flight, not done.** `workflow/universe_server.py` (12.4k LOC, down from 14k peak; 3 of 8 audit-prescribed extractions landed 2026-04-26) and `workflow/daemon_server.py` (3.6k LOC) are the dominant violations of the Module Layout commitment above. Decomp is sequenced ahead of the rename Phase 5 collapse per the active session's ordering — see `docs/audits/2026-04-25-universe-server-decomposition.md` for the 8-step migration shape.
- **Postgres-canonical vs GitHub-canonical (Q1 in full-platform note) is the largest unresolved architectural decision.** Until host answers, two design shapes coexist in this document. The decision should land in the next few cycles to avoid further documentation divergence.
