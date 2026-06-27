# Daemon Task Economy + Universe/Branch Coherence — Design Memo

**Status:** design memo, not a spec. Planner + explorer collaboration, 2026-04-14.
**Audience:** host (for direction + open-question resolution), then dev (for implementation spec derivation once host lands decisions).
**Scope:** two coupled questions — (1) how Universe and Branch relate in a unified mental model; (2) how a single daemon services simultaneous request classes without operator babysitting.
**Non-scope:** implementation code, schema migrations, MCP tool surface. Those follow once the model is settled.

**Doctrine applied throughout:** the product is the user's *power to design, inspect, steer, and evolve workflows*. Every design decision below is checked against "does this expand user control?" If a proposal only makes the daemon smarter without giving the user more visibility or steering, it's rejected.

---

## 1. Current state — what the code actually does today

Four primitives exist in the code. They are each real and each load-bearing, but they do not form a single coherent model — they were built at different times for different purposes and never reconciled.

### 1.1 The four primitives

**Universe.** A filesystem subtree under `output/<universe_id>/` holding `notes.json`, `work_targets.json`, `hard_priorities.json`, `PROGRAM.md` (premise), `activity.log`, `status.json`, `canon/`, `output/book-*`, per-universe DBs (`story.db`, `checkpoints.db`). Universe is not an ID-keyed object — it's a *path binding*. `tinyassets/runtime.py:39-51` holds module-level singletons (`memory_manager`, `knowledge_graph`, `vector_store`, `raptor_tree`, `embed_fn`, `universe_config`) set by `DaemonController.start()` and bound to exactly one universe per process. Switching universes requires `runtime.reset()` + a new process; violating this was the root cause of the 2026-04 Ashwater cross-universe leak (documented in `runtime.py` module docstring).

**BranchDefinition** (`tinyassets/branches.py:338`). Portable graph topology dataclass. Fields: `branch_def_id`, `name`, `author`, `domain_id`, `goal_id` (nullable, empty-string default at `tinyassets/branches.py:364`), `tags`, `version`, `parent_def_id`, `graph_nodes`, `edges`, `conditional_edges`, `entry_point`, `node_defs`, `state_schema`, `published`, `stats`. Validates reachability and cycle-has-exit (`tinyassets/branches.py:511-629`). Persists to `branches/<slug>.yaml` at the repo root. Does **not** know about universes — no `universe_id` field anywhere.

**Goal.** Not a typed class anywhere in `tinyassets/`. Goals are YAML dicts on disk at `goals/<slug>.yaml` (`tinyassets/storage/layout.py:68`). Accessed via `goals` MCP tool (`tinyassets/universe_server.py:6504`) with propose/update/bind/list/get/search/leaderboard/common_nodes actions. `Branch.goal_id` is a string FK; empty string = unbound.

**WorkTarget** (`tinyassets/work_targets.py:123`). The materialized "unit of intentional work." Fields: `target_id`, `title`, `home_target_id`, `role` (`notes`|`publishable`), `publish_stage` (`none`|`provisional`|`committed`), `lifecycle` (`active`|`paused`|`dormant`|`complete`|`superseded`|`marked_for_discard`|`discarded`), `current_intent`, `tags`, `artifact_refs`, `note_refs`, `linked_target_ids`, `timeline_refs`, `lineage_refs`, `selection_reason`, `metadata`, timestamps. Persists to `<universe>/work_targets.json`. Sibling `HardPriorityItem` (`tinyassets/work_targets.py:180`) in `hard_priorities.json` represents foundation-level hard blocks (e.g. unsynthesized uploads). **No `origin` / `actor` / `source` field** — the model has no idea whether a target came from a user request, a host request, a seed, or auto-generation.

### 1.2 The "branch" name collision — three different meanings

The word "branch" refers to three disjoint concepts in this repo:

1. **`BranchDefinition`** — a portable workflow topology (above). `branches/<slug>.yaml`.
2. **Git-style per-universe fork branches** — SQL table `branches` in the TinyAssets daemon DB (`tinyassets/author_server.py:195` table schema, `:829` `ensure_default_branch`, `:900` `list_universe_forks`). Every universe gets a `free-roam` branch auto-created; `branch_heads` points to a snapshot. Intended for future universe-internal variant history. The former `universe action=list_branches` MCP action + `output/<uid>/branches.json` stub were removed during the rename cleanup (2026-04-14) — the `list_branches` name now belongs exclusively to `extensions` (BranchDefinition catalog).
3. **LangGraph conditional edges** — the internal graph-library term for routing. Not user-visible.

`#1` and `#2` share the name and nothing else. `#2` is universe-scoped SQL state; `#1` is a repo-global YAML file. `list_branches` over MCP returns `#2` (or the default stub); `run_branch` over MCP executes `#1`. The name collision is an active UX hazard.

### 1.3 Two execution models running side by side, never crossing

**Model A — Long-running domain daemon (trusted path).** `DaemonController` (`fantasy_author/__main__.py:118`) takes a `universe_path`, binds the runtime singletons, compiles `build_universe_graph()` (`domains/fantasy_author/graphs/universe.py:432`) with SqliteSaver, and invokes the graph in a loop. The graph is **hand-wired Python** using `langgraph.graph.StateGraph` directly — not a `BranchDefinition`. Topology: `foundation_priority_review → (hard-block?) → dispatch_execution | authorial_priority_review → dispatch_execution → (run_book | worldbuild | reflect | idle) → universe_cycle → (cycle | END)`. Phases are trusted Python imports from `domains/fantasy_author/phases/` with unrestricted access to `workflow.runtime`, filesystem, subprocesses, provider routers.

**Model B — Transient BranchDefinition runs (sandboxed path).** `extensions.run_branch` MCP action → `tinyassets/runs.py:execute_branch_async` → `tinyassets/graph_compiler.compile_branch` → background executor → `.runs.db`. The compiler enforces sandbox + approval: `UnapprovedNodeError` (`tinyassets/graph_compiler.py:41`, raised at `:328`) rejects any node whose `source_code` is user-authored and not explicitly approved. Runs **do not know about universes**: signature is `execute_branch_async(base_path, branch, inputs, run_name, actor, provider_call)`. Grepped: zero `universe_id` / `universe_path` references in `tinyassets/runs.py`. Branch runs don't read notes, work_targets, KG, vector store, or any universe-scoped resource.

Grepped all of `domains/`: **zero hits for `execute_branch` / `execute_branch_async` / `run_branch`.** The two models have no code path between them.

**The split is not accidental — it's a security boundary.** User-authored Branch node code is untrusted (arbitrary Python from forks + uploads); the compiler sandbox exists specifically to contain it. Fantasy phases import freely from `workflow.*` because they are vetted repo code. Unifying the daemon loop onto `compile_branch` requires either (a) a "trusted-domain" carve-out that exempts registered domain branches from sandboxing, or (b) wrapping the fantasy `StateGraph` as a single opaque system-node that a Branch can invoke. Either is a migration cost, not a relabel.

### 1.4 How the daemon picks its next work today

Inside Model A, the selection pipeline is:

1. **`foundation_priority_review`** (`domains/fantasy_author/phases/foundation_priority_review.py`) reads `hard_priorities.json`. Any active hard block (`kind="synthesize_source"` etc.) routes to `dispatch_execution` with `current_task=worldbuild`. No hard block → routes to authorial review.
2. **`authorial_priority_review`** (`domains/fantasy_author/phases/authorial_priority_review.py:17`) calls `choose_authorial_targets(universe_path, premise=premise)` (`tinyassets/work_targets.py:678`). Ranks selectable targets by a fixed scoring tuple: `(active+role, stage, -updated_at)` — publishable role and active lifecycle outrank notes/dormant; committed publish_stage outranks provisional outranks none; newer updated_at breaks ties. Returns the top-ranked WorkTarget or `None`. If `None`, the graph routes to `_idle_node`.
3. **`dispatch_execution`** (`domains/fantasy_author/phases/dispatch_execution.py:70`) keyword-matches the selected intent against `"reflect"`, `"synth"`/`"worldbuild"`/`"reconcile"`/`"compare"` to choose `reflect` | `worldbuild`; otherwise `run_book` (or `worldbuild` if target is notes-role). Emits an execution envelope with `execution_id`, `execution_scope` (book/chapter/scene numbers inferred by `infer_execution_scope` at `tinyassets/work_targets.py:700`).
4. **Phase nodes** (`run_book`, `worldbuild`, `reflect`) execute the chosen task. `run_book` compiles a fantasy book subgraph; `worldbuild` runs world-synthesis; `reflect` runs a reflection pass.
5. **`universe_cycle`** (`domains/fantasy_author/phases/universe_cycle.py:30`) does end-of-cycle maintenance, evicts memory, checks the **cycle-level no-op streak guardrail** (`_MAX_CYCLE_NOOP_STREAK = 5` at `universe_cycle.py:27` — stops the daemon after 5 cycles of no forward progress, writes a self-pause note). Then either cycles back to foundation review or ends.

### 1.5 External-origin work is not wired

- **MCP `submit_request`** (`tinyassets/universe_server.py:1305`) writes to `<universe>/requests.json` with message "The Author will consider it at the next review gate." **Grepped `domains/`: nothing reads `requests.json`.** Requests accumulate in a file the graph never consults. This is a dead channel. (Fix assigned as task #18.)
- **MCP `give_direction`** (`tinyassets/universe_server.py:1358`) writes to `notes.json` via `workflow.notes.add_note`. Notes *are* consumed — they surface in `inspect` output and are read by the writer via orient context. This channel works.
- **WorkTarget has no `origin`/`actor` field** — no way to record "this target was submitted by external user X" even if we wanted to. All production code paths create WorkTargets via `ensure_seed_targets` (universe-notes + book-1 from premise) or `sync_source_synthesis_priorities` (auto-generated from upload signals).

### 1.6 Daemon "runs forever" — how the code currently interprets it

The PLAN.md thesis calls for daemons that work continuously. The current code does **not** implement that. Stopping conditions wired today:

1. **`_MAX_CYCLE_NOOP_STREAK`** — 5 no-op cycles → self-pause (`universe_cycle.py:27`).
2. **`.pause` sentinel file** — `control_daemon` action=pause creates it (`universe_server.py:1777`); daemon checks at scene boundaries.
3. **`should_continue_universe`** (`domains/fantasy_author/graphs/universe.py:393`) — reads `health.stopped`; true → END.
4. **`_idle_node`** (`universe.py:407`) — authorial review returns no target → sets `health.stopped=True`, `idle_reason="no_user_task"` → END.
5. **External process signals** — SIGINT, API stop, cross-universe synthesis switch (`universe_cycle.py:264`).

Default behavior on empty queue is **stop, not pickup-work**. The daemon process stays alive (tray-managed); a new graph invocation starts only on external trigger.

### 1.7 What's generic vs fantasy-specific

Generic in `tinyassets/`: `BranchDefinition`, `WorkTarget` + storage + selection scorer, `HardPriorityItem`, `compile_branch`, `execute_branch_async`, `runtime` singletons, the universe-server MCP tool surface, `graph_compiler` with sandbox + approval.

Fantasy-specific in `domains/fantasy_author/`: the entire universe graph topology, `UniverseState` TypedDict, the `_determine_task` keyword router, `run_book` + book subgraph, all phase implementations, per-scene commit packets.

**One fantasy leak into generic code:** `tinyassets/work_targets.py:49-51` defines `EXECUTION_KIND_BOOK/CHAPTER/SCENE` constants and `infer_execution_scope` (`:700`) encodes book/chapter/scene regex detection. These belong in a domain, not in shared infrastructure — a visible seam for genericization work later.

### 1.8 Summary — what's missing for the three-axis model

- Goal is not a typed runtime object; only YAML and a string FK.
- Universe has no `goal_id` field; Goals-to-Universes is unmaterialized.
- BranchDefinition has no `universe_id` field; instantiation is implicit.
- WorkTarget has no `origin` / `trigger_source` field; external-origin is unrepresentable.
- No Task / queue abstraction spans the daemon + Branch runtime split.
- No Goal-pool storage, no subscription mechanism, no opportunistic-work tier.
- No node-scoped bid market; paid-request model (per memory: own-crypto, `(node_def_id, required_llm, price)` triples) has no data model yet.
- Daemon runs on a hand-wired `StateGraph`, not a BranchDefinition — the builder surface and the autonomous surface share nothing, and the split is a security boundary, not merely an oversight.

---

## 2. Tensions — why the system feels split today

Three tensions surface when a user tries to form a single mental model of the system:

### 2.1 "What does the daemon actually run?"

When a user registers a Branch via `extensions` and calls `run_branch`, they get a foreground graph execution (`tinyassets/runs.py:execute_branch_async`). When the fantasy daemon works autonomously, it doesn't `execute_branch` anything — it runs the fantasy universe-cycle graph, which selects a `WorkTarget` via authorial review, and dispatches the appropriate phase. These are two entirely separate execution paths sharing no code.

Consequence: "the daemon ran my workflow" and "my workflow ran" are different events. A user who designs a Branch has no way to say "daemon, please run this Branch autonomously next time you have capacity." The builder surface and the autonomous surface don't meet.

**UX cost:** the user's power to design Branches does not translate into power over the daemon's work. The two surfaces evolve independently.

### 2.2 "Who owns what?"

Universes own: canon, notes, rules, priorities, work targets, one running daemon, one filesystem tree. Branches own: topology, state schema, node defs, fork lineage. Goals own: intent, outcome ladder, bound branches.

None of these own each other cleanly:
- A Branch is universe-free in its dataclass, but operationally it gets a default `free-roam` branch per universe (`author_server.py:829`), which implies the opposite.
- A Goal has many Branches, but Branches run in Universes, so Goals-to-Universes is a many-to-many through Branches — and nothing materializes that relationship.
- A Universe contains WorkTargets, but a WorkTarget is fantasy-shaped; there's no general abstraction a research-paper Branch would use.

**UX cost:** the user has three primitives with unclear containment. "Where does my work live?" has no single answer.

### 2.3 "What's the daemon idling for?"

Today the fantasy daemon either works on its universe or sits idle until the user uploads or requests something. There is no concept of "the daemon has capacity, and the world has open work." No pool, no subscription, no pickup. The daemon's economy is closed at the universe boundary.

This contradicts the PLAN.md thesis — "a legion of diverse AI-augmented workflows pursues each Goal in parallel" — which requires daemons to pick up Goal-pool work across the shared corpus.

**UX cost:** the user cannot say "when my Branch is idle, help the research-papers Goal." The daemon-as-shared-resource vision is absent from the current code.

---

## 3. Proposed unified model — three orthogonal axes

After reviewing the code and the PLAN.md design decisions, the cleanest model is **not to merge Universe and Branch, but to recognize them as three orthogonal axes around a single runnable unit.** They already ARE orthogonal in the code; the fix is to make that explicit and let the daemon operate over the full product.

### 3.1 The three axes

| Axis | Asks | Scope | Persistence |
|---|---|---|---|
| **Goal** | *Why?* Intent / pursuit / outcome | Public, shared across users | `goals/<slug>.yaml` |
| **Branch** | *How?* TinyAssets topology / graph design | Public, forkable, Goal-bound | `branches/<slug>.yaml` |
| **Universe** | *Where?* Reality scope — isolated canon, facts, state, memory | Private to the host (usually) | `<universe>/` subtree |

**Key claim:** these three axes are each complete design primitives. They do not subsume each other. A Branch is not "inside" a Universe; it is a design artifact that CAN be instantiated into one or more Universes. A Goal is not "above" a Branch in containment terms; it is the intent layer Branches BIND to.

**Note on the existing operational coupling.** Today `author_server.py:829` creates a default "free-roam" branch per universe. That `branch` is the SQL-table sense (§1.2 concept #2) — a git-style in-universe fork — NOT a `BranchDefinition`. `BranchDefinition` and `Universe` are already orthogonal in dataclass terms (explorer confirmed: zero cross-references). This model formalizes that orthogonality and retires the name collision through the rollout plan.

### 3.2 Two runnable shapes: BranchTask and NodeBid

The daemon actually executes **two different shapes of work**, and they need different durable forms. Merging them into one Task row hides a real structural difference — bid-market work is node-scoped and cross-universe, while all other work is Branch-scoped and universe-bound.

#### BranchTask — whole-graph execution against a Universe

```text
BranchTask = (
  branch_task_id,
  goal_id,           # why (may be empty for universe-internal maintenance)
  branch_def_id,     # how — the full graph topology to run
  universe_id,       # where — bound reality scope
  inputs,            # state_schema initializer + optional work_target_ref
  trigger_source,    # owner_queued | host_request | user_request | opportunistic
  priority_weight,
  claimed_by,        # which daemon owns execution
  status,            # pending | running | succeeded | failed | cancelled
)
```

BranchTasks run a whole Branch graph from entry to terminal. They're universe-bound because the graph's state schema reads/writes universe-scoped resources (canon, notes, work_targets). Live in a per-universe queue.

#### NodeBid — single-node execution, cross-universe, bid-market

```text
NodeBid = (
  node_bid_id,
  node_def_id,        # which node function to run
  required_llm_type,  # hard filter — daemon must serve this model
  inputs,             # node's input dict, self-contained
  bid,                # price in project token — no floor
  submitted_by,
  status,             # open | claimed:<daemon_id> | succeeded | failed | expired
  evidence_url,       # populated on completion — ties to #56 outcome gates
)
```

NodeBids run one node, not a graph. They live in a **repo-root bid queue** (`bids/<id>.yaml` conceptually), not in any universe. A daemon pulls a NodeBid, spins up a throwaway context, runs the node with the required LLM, writes the output artifact, and populates `evidence_url`. Cross-universe by construction — **no `universe_id` field**; the bid doesn't know or care about any universe's canon. This keeps the bid market and the universe-isolation invariant strictly independent.

**Why the split is necessary, not cosmetic.** A BranchTask reads the universe's working state; a NodeBid reads only its own `inputs`. They have different storage locations, different security models (NodeBid must run in the sandboxed path because the submitter is untrusted; BranchTask may run trusted-domain code), different completion semantics (NodeBid is atomic + evidence-gated; BranchTask writes artifacts across multiple phases).

**Both feed the same daemon dispatcher.** See §4.2 — the dispatcher picks from tiered sources that include both shapes, then routes to the appropriate executor: `execute_branch_async` for BranchTask (universe-bound, can use trusted domain graph), `execute_node_bid` (new — sandboxed single-node executor) for NodeBid.

**WorkTarget survives as BranchTask-input.** A BranchTask can reference a WorkTarget via `inputs.work_target_ref`; the Branch's entry node reads it. WorkTarget stays universe-scoped. One WorkTarget can spawn many BranchTasks.

### 3.3 Why this preserves every current design decision

- Universe isolation (PLAN.md "Universe = single consistent reality") — unchanged. Tasks execute against a single universe_id; the runtime.py singleton binding still holds.
- Branch as forkable topology — unchanged. Branches still live at `branches/<slug>.yaml`, still Goal-bound.
- Goal as pursuit intent — unchanged. Goals still above Branches; outcome gates still ride on the Goal.
- WorkTarget as unit of intentional work — unchanged. Now referenced by Tasks rather than consumed directly by the universe-cycle graph.

### 3.4 What changes

- **The three-way `branch` name collision retires.** Concept #2 (SQL-table in-universe fork at `author_server.py:195 / :829`) is renamed `universe_fork` by the rollout plan. `BranchDefinition` keeps the public-facing "Branch" name. LangGraph's internal conditional edges are out of scope — they're LangGraph's term, not ours.
- **The fantasy universe-cycle graph becomes an inspectable Branch — aspirationally, via opaque-node wrapping.** The daemon's "autonomous loop" becomes "repeatedly run the fantasy universe-cycle Branch against this universe." Two bridging options per §1.3 and explorer's §5.1:
  - **(b) Opaque-node wrapping (preferred path).** The fantasy graph runs as a single-node Branch — one `BranchDefinition` whose sole node invokes the existing `build_universe_graph()` StateGraph. Preserves unification at the queue + inspection layer; does NOT force every fantasy phase through sandbox compilation. Lower migration cost, ships the UX win sooner.
  - **(a) Trusted-domain carve-out (future work).** `BranchDefinition` gains a `trusted_domain` flag that exempts domain-registered graphs from sandbox approval when `domain_id` matches the host's trusted-domain list. Unlocks per-phase inspection + per-phase user extensions. Higher migration cost — fantasy phases must be audited for compile compatibility.
  The rollout plan ships option (b); option (a) is future work when more domains arrive and per-phase inspection matters more.
- **One dispatcher per daemon, two executors.** Tiered selection (see §4) picks from a merged source list; BranchTasks route to `execute_branch_async` (universe-bound, may include trusted-domain graphs), NodeBids route to a new sandboxed single-node executor. Same dispatcher, different execution paths — reflects the real security + scope differences.

### 3.5 UX check

- User can see every Task the daemon has run, is running, or has queued — one inspection surface.
- User can promote/demote Task priorities, cancel queued Tasks, or pause a tier entirely.
- User can author a Branch, bind it to a Goal, and say "run this when idle" — the same input surface as building a workflow.
- User can see which Tasks came from their host, from connected users, from the Goal pool, from opportunistic scan — legibility of request provenance.

Passes the UX-primary doctrine: every new capability expands user inspection or steering power.

---

## 4. Proposed daemon task economy

### 4.1 Default behaviors — "leave daemon on → works forever"

The daemon's outer loop, in plain language:

```text
forever:
  if current_task is running: continue
  next_task = select_next_task(tiers, daemon_config)
  if next_task is None:
      sleep(idle_backoff)  # configurable, exponential up to N minutes
      continue
  execute(next_task)  # routes to execute_branch_async or execute_node_bid
```

**Note on what exists vs. what's forward-design.** Tier 2 (`host_request`) and tier 3 (`owner_queued`) have existing plumbing today — `submit_request` landing in `requests.json` (wired via task #18) and `choose_authorial_targets` respectively. Tiers 4-7 are **forward-design only** — no non-host user can submit work to a daemon today, no Goal-pool directory exists, no bid queue, no opportunistic producer. The cascade specifies where they land when they arrive (see rollout plan Phases E-G).

**The fallthrough cascade — concrete sequence.** `select_next_task` walks these sources in order; first non-empty wins:

1. **Current task** — if a BranchTask or NodeBid is mid-execution, continue it. (Stored: in-memory + checkpoint at `.langgraph_runs.db`.)
2. **host_request BranchTasks** — host-submitted, universe-bound. (Stored: per-universe `branch_tasks.json` or equivalent durable queue.)
3. **owner_queued BranchTasks** — WorkTargets promoted via authorial review. (Stored: derived from `work_targets.json`.)
4. **user_request BranchTasks** (gated: `accept_external_requests=true`) — non-host MCP clients. (Stored: same queue as host_request, filtered by submitter identity. **New feature — no current plumbing; see §4.4 schema asks.**)
5. **Subscribed Goal-pool BranchTasks** (gated: `accept_goal_pool=true`) — BranchTasks posted against Goals the daemon subscribes to. (Stored: repo-root `goal_pool/<goal_slug>/<branch_task_id>.yaml` or similar cross-universe path. **New feature.**)
6. **NodeBid queue** (gated: `accept_paid_bids=true`, LLM-filter) — bid-market single-node work. (Stored: repo-root `bids/<node_bid_id>.yaml`. **New feature.**)
7. **Opportunistic** — daemon-generated housekeeping (index rebuilds, canon consolidation). (Stored: generated inline, not persisted as a queue.)

If every gated-on source is empty AND opportunistic is disabled, the daemon idles with an exponential backoff. If opportunistic is enabled (default), the daemon always has work.

**The critical default:** `goal_pool` subscription is opt-in per Goal, but the daemon ships subscribed to a curated "maintenance pool" (index rebuilds, canon audits on public Branches the user has forked, knowledge-base consolidations). Out of the box, leaving the daemon on means it gets useful — just not world-facing — work.

`host_request` is always on; `user_request` (non-host) is opt-in via a host switch (`accept_external_requests: bool`). Each tier has its own on/off switch — "accept global pool: yes/no", "accept paid-bid work: yes/no", "allow opportunistic: yes/no". The host-dashboard view of these switches IS the control surface a user sees when they turn their daemon on for the first time.

### 4.2 Tiered selection with bid-weighted sorting

The daemon applies a **hard LLM-type filter** first (applicable to NodeBids; BranchTasks inherit it from their graph's declared provider chain), then a **tier × bid** scoring function.

**Hard filter.** A daemon can only consider work whose `required_llm_type` it can serve. This is structural — a daemon running Opus can't fulfill a NodeBid that requires a specific fine-tuned model. The filter happens before scoring; unmatched work is invisible to this daemon.

**Tier ordering** maps 1-to-1 with the default behavior cascade, high priority → low priority:

1. **host_request BranchTask** — host's own box, first priority.
2. **owner_queued BranchTask** — this universe's WorkTargets, scheduled by the user or by authorial review.
3. **user_request BranchTask** — non-host-submitted, gated.
4. **Goal-pool BranchTask** — cross-host, shared against subscribed Goals, gated.
5. **NodeBid** — cross-universe bid-market, LLM-filtered, bid-sorted, gated.
6. **opportunistic** — daemon-generated housekeeping. Always last; never empty.

Within a tier, work sorts by score. Host can reshape the ladder via dashboard; ordering is config, not code.

### 4.3 The priority function — concept, not code

Conceptually the daemon picks by:

```text
score(task) = tier_weight[task.trigger_source]
           + bid_term(task.bid)             # 0 if no bid; dominates within a tier when present
           + recency_decay(task.queued_at)
           + user_boost(task.priority_weight)
           + goal_affinity(task.goal_id, daemon.subscribed_goals)
           - cost_penalty(task.estimated_cost)
```

Explicit goals for the function:
- **Host requests can't be starved** by paid goal_pool work — tier_weight dominates bid. Even a big bid on a goal_pool Task sits below a zero-bid host_request.
- **Bid dominates within a tier.** Two goal_pool Tasks with the same LLM match sort by bid, high to low. A host who wants maximum earnings configures a high bid_term coefficient; a host who runs their daemon for their own projects configures a low one.
- **No bid floor.** A daemon with no higher-tier work AND no paid pool work still pulls zero-bid goal_pool Tasks. "Very cheap work is still work" — preserves the "leave daemon on → works forever" default even in a thin market.
- **Recency decay** prevents old queued tasks from being ignored forever, but doesn't invert tier ordering.
- **User boost** is a direct steering lever (user says "this first") — visible, overridable.
- **Goal affinity** means a daemon subscribed to `research-paper` Goal weights those tasks higher in the pool.
- **Cost penalty** lets the user say "don't spend 5 hours on a single Task without asking." For paid Tasks, cost_penalty compares against bid — a high bid buys through the cost gate.

All weights exposed in config, inspectable by the user, adjustable without a code change.

**Earnings dashboard implied.** If the daemon accepts paid work, the host needs a view of: accepted offers, earnings/hour, offers declined (and why — LLM mismatch, budget, lower than another open offer). This is a visibility surface, not a policy; lives in the host dashboard not the MCP tool.

**Outcome-gate sybil risk.** Paid claims need evidence that the Task actually ran and produced the right output. Ties to #56 outcome gates — the evidence_url of a gate claim doubles as the receipt of paid completion. Memo notes the coupling; follow-up gate design will work out the details.

### 4.4 Chatbot-does-it vs user-hosts-own-daemon — where the line falls

**The chatbot can do:**
- Submit a Task to any running daemon's queue (host or external).
- Inspect any queue / any Task / any Goal.
- Author or fork a Branch (design work).
- Steer: promote, demote, cancel, pause.
- Read outputs.

**The chatbot cannot do:**
- Execute a Branch against a universe. That requires a running daemon, which requires the runtime.py singleton binding — a host process.
- Hold long-horizon state for a Task. Chatbot chats end; daemons persist.

**So when does the user host their own daemon?**
- When they want a persistent reality (a Universe they return to).
- When they want work to happen while they're offline.
- When their Branch is expensive and they don't want to share execution cost with another host.
- When privacy matters — private Universes can only run on hosts the user controls.

**When is the chatbot enough?**
- One-shot Branch runs against an existing host's daemon.
- Designing Branches, forking, remixing.
- Browsing Goals, submitting requests.
- Watching a daemon's output without running one.

This line is load-bearing: *the chatbot is the designer; the daemon is the executor.* A user who only designs can live entirely in the chatbot. A user who wants persistence hosts a daemon. Clean split, and it maps onto hardware: chatbots are ephemeral, daemons are long-running.

**The one-shot vs keep-running test.** A sharper framing: if the work is one-shot — "answer this question now, once" — the user calls a chatbot directly; no daemon needed. If the work has to keep running, retry on failure, absorb feedback over days, OR if the user wants someone ELSE's hardware to do it (e.g. a cheaper GPU host, a specialist fine-tune they don't own), THAT'S what a daemon is for — whether self-hosted or paid-market-accessed. **The daemon is infrastructure for long-running OR market-mediated work.** Everything else is chatbot territory.

### 4.5 UX check

- User can see tier definitions and weights; they're not opaque.
- User can subscribe/unsubscribe to Goal pools with a one-line toggle per Goal.
- User can pause a whole tier (e.g. "stop taking user_request work tonight").
- User can trace any running Task back to its trigger_source and see who queued it.
- User can say "never do opportunistic work" and the daemon will idle honestly instead of inventing tasks.

Passes the doctrine. Nothing here hides what the daemon is doing.

### 4.6 What §4 asks of the existing data model

This section is a checklist for the dev-spec phase — what has to land before §4 can be implemented. None of these are design decisions; they're mechanical consequences of the cascade above.

- **New `origin` field on WorkTarget** — today `WorkTarget` has no source/actor/submitter field (confirmed via code read). Without it the dispatcher can't distinguish `host_request` vs `user_request` vs `opportunistic` entries sharing the same queue. Value set mirrors `trigger_source` in §3.2.
- **New `branch_tasks` durable queue (per universe)** — `work_targets.json` is fantasy-scoped and book/chapter/scene-shaped; BranchTasks need their own queue because they span domains and can reference any Branch-def. Sibling file: `branch_tasks.json` alongside `work_targets.json`.
- **New repo-root `goal_pool/` directory** — cross-host BranchTask postings against Goals. One YAML per posting. Empty by default.
- **New repo-root `bids/` directory** — NodeBid queue with YAML-per-bid. Integrates with outcome gates (evidence_url).
- **New universe-metadata field: `subscribed_goals`** — which Goals this universe's daemon will pull pool work from. Stored on `<universe>/rules.yaml` or equivalent.
- **New daemon config: per-tier on/off switches** — `accept_external_requests`, `accept_goal_pool`, `accept_paid_bids`, `allow_opportunistic`. Host-editable via dashboard.
- **New executor: `execute_node_bid`** — single-node sandboxed runner for NodeBids. Distinct from `execute_branch_async`.
- **Migrate `submit_request` output into `branch_tasks.json`** — the dead-drop bug (requests landing in `requests.json` but never read by the daemon) is being fixed separately. Once that lands, those requests become the natural seed for the `host_request` / `user_request` BranchTask queue — §4's job is to route them to the dispatcher with the right `origin` stamp, not to re-invent the submission surface.

None of these is blocking for the memo's design; all are implementation-time obligations. The list is here so the dev-spec phase knows exactly what to add.

---

## 5. Migration sketch — how fantasy maps into the unified model

### 5.1 Fantasy today (authoritative summary)

End-to-end loop, concrete enough to reconstruct:

**Process start.** A user (or the tray) invokes `python -m fantasy_author --universe output/<name>`. `fantasy_author/__main__.py` parses CLI args and instantiates `DaemonController(universe_path=...)` (`fantasy_author/__main__.py:118`). The controller resolves `story.db` and `checkpoints.db` under the universe path, guarding against CWD-relative paths that would cross universes (`__main__.py:148-166`).

**Runtime binding.** `DaemonController.start()` populates `tinyassets/runtime.py` module globals (`memory_manager`, `knowledge_graph`, `vector_store`, `raptor_tree`, `embed_fn`, `universe_config`) from the universe's config + DBs. After this point the process is bound to one universe until `runtime.reset()`; attempting to switch universes in-process would reintroduce the Ashwater-class cross-universe leak.

**Graph compile.** Controller imports `build_universe_graph()` (`domains/fantasy_author/graphs/universe.py:432`) which constructs an uncompiled `StateGraph(UniverseState)` with nodes `foundation_priority_review`, `authorial_priority_review`, `dispatch_execution`, `run_book`, `worldbuild`, `reflect`, `idle`, `universe_cycle`. Entry point is `foundation_priority_review` (`universe.py:453`). Conditional edges wire the review routing (`universe.py:456-463`) and task-dispatch routing (`universe.py:467-475`); unconditional edges feed each terminal task into `universe_cycle` (`universe.py:479-483`); a final conditional edge routes `universe_cycle` → `foundation_priority_review` (continue) or `END` (stop) via `should_continue_universe` (`universe.py:486-493`). The graph is compiled with a `SqliteSaver` checkpointer pointing at `checkpoints.db`.

**Invocation.** Controller calls `compiled_graph.invoke(initial_state)` with `initial_state` seeded from universe state (premise, workflow_instructions, `_universe_path`). Each node mutates partial state via dict returns; reducers in `UniverseState` (TypedDict with `Annotated[list, operator.add]` for `quality_trace` and `task_queue`) merge updates.

**Per-cycle flow.**
1. `foundation_priority_review` reads `<universe>/hard_priorities.json` via `tinyassets/work_targets.py:load_hard_priorities`. If an active `synthesize_source` priority exists, it emits `review_stage="foundation"`, `current_task="worldbuild"`, and routes (via `route_after_foundation_review`, `universe.py:362`) directly to `dispatch_execution`. Otherwise routes to `authorial_priority_review`.
2. `authorial_priority_review` (`domains/fantasy_author/phases/authorial_priority_review.py:17`) calls `choose_authorial_targets` (`tinyassets/work_targets.py:678`), which in turn calls `ensure_seed_targets` (creates `universe-notes` + `book-1` WorkTargets on first run from premise) and `list_selectable_targets` (filters out `discarded`/`superseded`). The ranker is `score()` at `work_targets.py:686`: tuple `(active_score + role_score, stage_score, -updated_at)`. Top result → `selected_target_id` + `selected_intent` (target's `current_intent`). Also captures two alternates. Writes a review artifact JSON to `<universe>/artifacts/reviews/`. Emits `current_task=None` (to be resolved by dispatch) or `"idle"` if no target.
3. `dispatch_execution` (`domains/fantasy_author/phases/dispatch_execution.py:16`) creates an `execution_id` (`exec-<hex>`), calls `infer_execution_scope` to resolve book/chapter/scene numbers, runs `_determine_task` keyword match against the intent to pick one of `run_book` | `worldbuild` | `reflect` | `idle`, writes an execution artifact to `<universe>/artifacts/executions/`, and emits `current_task`, `current_execution_id`, `current_execution_ref`.
4. The chosen phase node runs. `run_book` (in `universe.py` around `:285`) compiles and invokes the book subgraph (`build_book_graph()`); on compile/invoke failure it falls back to direct `run_chapter` calls (`universe.py:312-321`). `worldbuild` performs source-synthesis or world-reconciliation; `reflect` runs a reflection pass. Each returns partial state updates (`total_chapters`, `total_words`, `quality_trace`).
5. `universe_cycle` (`domains/fantasy_author/phases/universe_cycle.py:30`) updates health counters, calls `MemoryManager.evict_old_data` if bound, clears the completed execution envelope, and evaluates the **cycle no-op guardrail** (`_MAX_CYCLE_NOOP_STREAK = 5`). The guardrail compares `_prev_cycle_totals` against a fresh `_snapshot_progress_signals` (total_words, canon_facts_count, generated_files_len, signals_acted, notes_mtime); if none advanced, streak increments. At streak ≥ 5 it sets `health.stopped=True`, `idle_reason="universe_cycle_noop_streak"`, and writes a system note via `workflow.notes.add_note`. Also checks sibling universes for pending synthesis and, if found, sets `health.switch_to_universe=<other_uid>` so the controller can tear down + respawn.
6. `should_continue_universe` reads `health.stopped`. False → back to `foundation_priority_review` (next cycle). True → `END`. The `universe_cycle → foundation_priority_review` loop is not a validator-rejecting cycle — every node in the cycle reaches `END` through this conditional edge, which is why the fantasy graph (if re-expressed as a BranchDefinition) would pass `BranchDefinition.validate()`'s cycle-has-exit check at `tinyassets/branches.py:608-618`.

**Idle termination.** When `authorial_priority_review` finds no selectable targets, it sets `current_task="idle"`, which routes through `dispatch_execution` to `_idle_node` (`universe.py:407`). `_idle_node` sets `health.stopped=True` and `idle_reason="no_user_task"`, flows into `universe_cycle`, which exits via `END`. The process stays alive (tray-managed); a new `invoke` call starts only when something external (API, MCP tool, new upload) changes state.

**What the user sees.** `tinyassets/universe_server.py` exposes this loop through the `universe` MCP tool's `inspect` action (`universe_server.py:1167`), which reports `daemon.phase`, `daemon.is_paused`, `daemon.has_work`, active WorkTargets, recent notes, output files, recent activity, pending requests count. `status.json` is the bridge — the daemon throttled-writes it after every node completion (`fantasy_author/__main__.py:638-643`), and `inspect` reads it back. This is the user's single window into "what is my daemon doing." Everything else — the graph topology, the review scoring, the phase dispatch — is invisible from outside the Python process.

### 5.2 Fantasy under the unified model (planner draft — explorer to refine)

Concrete migration steps, in order:

1. **Register the fantasy universe-cycle graph as a Branch — via opaque-node wrapping.** Per §3.4 option (b) and §1.3, a single-node `BranchDefinition(domain_id="fantasy_author", name="universe-cycle", ...)` whose one node invokes the existing `build_universe_graph()` StateGraph. This is the primary approach: lower migration cost, no forced sandbox-compilation of every fantasy phase, unification happens at the queue/inspection layer rather than at the per-phase level. Option (a) — trusted-domain carve-out allowing full per-phase inspection — is future work when per-phase user extension matters more.
2. **WorkTarget becomes Task-input, not daemon-input.** `choose_authorial_targets` stays — but instead of being the daemon's only selector, it emits a Task with `trigger_source=owner_queued`, `branch_def_id=fantasy_author/universe-cycle`, `universe_id=<this>`, `inputs.work_target_ref=<target_id>`.
3. **DaemonController becomes a tier-aware loop.** Instead of "run universe graph forever," the controller walks tiers, picks Tasks, dispatches to the `execute_branch` path. Fantasy-specific code disappears from the outer loop — it moves to the Branch it executes.
4. **Default Goal subscription: the fantasy domain's Goals** (`fantasy-novel`, maybe `worldbuilding-notes`). Host can add or remove subscriptions.
5. **Opportunistic tier: canon audits, KG rebuilds, notes consolidation.** Existing maintenance passes become opportunistic Tasks generated by a background scan.

**What doesn't change:** work_targets.json stays. Universe path singletons stay. Review gates stay. State schema stays. Scene packet contract stays. This migration is additive at the edges, not a rewrite.

**What gets new power:** a user can register their own Branch — say, a "compare to canon" validator — bind it to the `fantasy-novel` Goal, and have the fantasy daemon run it opportunistically. The builder surface and the autonomous surface meet.

### 5.3 Validation: a research-paper walkthrough

A user creates a `research-paper` Goal. They author three Branches: `survey`, `experiment`, `writeup`. A second user forks `writeup` and makes a stricter variant. A third user creates a Universe called `my-dissertation` and subscribes their daemon to the Goal.

Under this model:
- The three Branches are shared. Anyone can fork. No universe binding.
- The dissertation Universe is private — the third user's reality scope.
- The daemon runs `survey` against `my-dissertation`, then `experiment`, then `writeup` (or the forked variant). Each run is a Task; the tier is `owner_queued`. The user queued them in order.
- When the daemon is idle, it pulls Goal-pool Tasks — maybe someone else submitted "help me find counterexamples to Claim X" as a user_request on the shared Goal. The daemon accepts if `accept_external_requests=true`.

Clean. Every concept earns its keep.

---

## 6. Open questions for host

Design choices that need host sign-off before implementation can scope:

### Q1. Is Universe default-private or default-public?

Today universes are host-local filesystems. In a shared-state world, some could be pushed to git. If a user registers a Universe under a Goal, should it be public by default (inviting collaboration) or private (explicit promotion required)? Recommend: **private by default**; explicit `publish_universe` action to make it visible. Matches PLAN.md "Privacy default: Public-by-default; users can mark a branch private for drafting" — but for reality scopes (where personal canon lives), default-private is safer.

**Resolved by implementation:** Universes stayed host-local filesystems through the shipped implementation; no `publish_universe` action shipped. Default is effectively private-by-filesystem-scope. Revisit when shared-state publishing surfaces.

### Q2. Paid-request market — confirming the model and its edges

Host has specified the model (2026-04-14): project-native cryptocurrency; requester submits (node, required_llm_type, bid); daemons filter by LLM type then sort by bid with no floor. Folded into §4.2-4.3. Remaining edges for host to rule on:

- **Escrow / settlement.** Is bid held in escrow at submission and released on completion, or paid on-completion trust-first? Recommend: **escrow**, to prevent requester-side fraud (submit a huge bid, cancel after daemon starts). Settlement on outcome-gate evidence (ties to #56).
- **Can a host accept ONLY paid work?** i.e. turn off zero-bid opportunistic. Recommend: **yes, per-tier pause switch**. "Accept goal_pool work: paid only" is a valid dashboard toggle.
- **Bid transparency.** Does the daemon see all open bids for a Task (to compete) or only the bid on the Task it's considering? Recommend: **see all**, so the bid-sort is meaningful. An open auction surface also makes the market legible to users.
- **Reputation / daemon identity.** Does a requester get to filter by daemon reputation (past completion rate, evidence-gated success)? Recommend: **yes, later** — not blocking for v1 paid market, but note the slot.

These aren't blockers for §3-4 adoption; they're the next memo when the paid market moves from "project memory" to "executable spec."

**Status:** still host-blocking. The NodeBid executor and priority weighting shipped in `cb7482f` without escrow, transparency, or reputation surfaces — the four edges above remain open design choices. Flag escrow for host before the paid-market default flip.

### Q3. Can a single daemon serve multiple Universes?

Today: one daemon = one universe (runtime.py singleton). Tomorrow: should one daemon be able to rotate across several of a user's Universes? If yes, the runtime singleton has to break; if no, "user hosts own daemon" scales per-universe. Recommend: **one daemon per Universe for now**, revisit when the singleton contract breaks for multi-tenancy. Simpler mental model for users.

**Resolved by implementation:** one-daemon-per-universe preserved through the tier-aware DaemonController (`29a71a7`) and dashboard (`3d7acb0`). Singleton contract unchanged.

### Q4. What's the "opportunistic tier" allowed to touch?

Opportunistic is the fallthrough that keeps daemons alive. If the daemon is truly idle, can it edit canon? Modify WorkTargets? Spawn new ones? Recommend: **read/verify/consolidate only**. No net-new content without a higher-tier Task. Otherwise the daemon invents work the user didn't ask for — bad for trust and bad for the UX doctrine.

**Resolved by implementation:** the tier system (`29a71a7`) and NodeBid executor (`cb7482f`) preserved the "no net-new content from opportunistic tier" contract — bids/pool-work are task-scoped, not free-form. Opportunistic surface remains read/verify/consolidate-only.

### Q5. Does `goal_pool` subscription require host approval per Task?

If a daemon subscribes to `fantasy-novel` and someone submits 200 Tasks to the Goal pool, does the daemon auto-accept or does each pull require the host to approve? Recommend: **auto-accept up to a daily Task count / cost budget the host sets; above that, require approval**. Default budget low enough that default behavior is "a few opportunistic pulls per day, user sees them in the queue."

**Resolved by implementation:** followed recommended default in `1d02903` — goal_pool producer auto-accepts within tier-budgeted cycle count. Per-Task approval deferred; revisit if dashboard usage surfaces a flood.

### Q6. Chatbot-held state — is there any persistence we're leaving on the table?

We said chatbots can't hold long-horizon state. But MCP sessions DO have a tool surface that could write to durable artifacts. Is there a class of work the chatbot should handle directly (quick design iteration, small synthesis tasks) without ever invoking a daemon? Recommend: **yes, but only for actions that write to durable artifacts the daemon can later consume** — Branch authoring, Goal creation, Task submission. Never direct content generation against a Universe; that always goes through a daemon.

**Resolved by implementation:** the TinyAssets MCP tool surface consistently restricts chatbot actions to artifact authoring (Branches, Goals, Task submission); content generation routes through the daemon. The "HARD RULE — NO SIMULATION" instruction at the MCP level enforces it.

### Q7. Can high-tier work starve lower tiers indefinitely?

The cascade walks tiers in priority order, first-non-empty-wins. This correctly prevents paid work from pre-empting the host's own queued work. But a busy host can indefinitely block paid / Goal-pool work from ever running on their daemon — tiers 4-7 only fire when tiers 1-3 empty. Two views:

- **View A: this is correct.** The host is providing the hardware; their priorities dominate. If a paid request must run, it belongs on a different host's daemon. The bid market finds a host with capacity naturally — tier starvation is a signal, not a bug.
- **View B: some fairness-interleaving is needed.** A weighted round-robin below a cost threshold (e.g. "once per 10 host tasks, run one paid/pool task if one matches") keeps paid work moving through networks where many hosts are always somewhat busy, avoiding a "tragedy of the commons" where no host ever runs paid work.

Recommend: **View A for v1** — simpler, honest, starvation is user-visible via the dashboard queue. Revisit if paid-market throughput becomes a real complaint; a fairness_interleave coefficient in the priority function is a cheap retrofit later.

**Resolved by implementation:** View A shipped in the tier cascade (`29a71a7`); NodeBid (`cb7482f`) respects the cascade without fairness-interleave. No starvation complaint surfaced. Retrofit slot preserved in the priority function.

---

## Status

All sections drafted and converged. §1 + §5.1 authored by explorer; §2, §3, §4, §5.2-5.3, §6 authored by planner. Memo is ready for reviewer audit and host approval on §6.

**Next steps:**
1. Reviewer audits for PLAN.md alignment and UX-doctrine adherence.
2. Host rules on the open questions in §6 — only Q2 (paid-market edges: escrow/transparency/reputation) remains host-blocking. Q1/Q3/Q4/Q5/Q6/Q7 resolved by implementation.
3. Rollout plan at `docs/exec-plans/daemon_task_economy_rollout.md` sequences the historical implementation batches; each work-table row is ready for dev to claim once host lands decisions.
4. Implementation specs derive into `docs/specs/` as batches start.
