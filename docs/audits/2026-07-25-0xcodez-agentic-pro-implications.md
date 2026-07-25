---
title: 0xCodez agentic-pro patterns — TinyAssets implications
date: 2026-07-25
initial_provider: claude-code-opus5
required_reviewer_provider: codex
review_status: PENDING — no build authority flows from this document
artifact_kind: external-research-implications
source_reachability: reachable via public mirrors (X itself login-walled)
load-bearing-question: >
  Can a hardcore pro agentic engineer express 0xCodez's four taught disciplines
  (loop engineering, graph engineering, self-improving agents, build-your-own-LLM)
  on TinyAssets' primitives — and would they choose to, over building it themselves?
---

# 0xCodez agentic-pro patterns — TinyAssets implications

> **NO BUILD AUTHORITY.** This is research. Nothing here is a licence to
> implement, push, roll out live, or advance acceptance tests. Per
> `AGENTS.md` §"Project Skills" and `.agents/skills/external-research-implications/SKILL.md`
> §8, a research-derived finding made by Claude requires an **opposite-provider
> (Codex) review** returning `approve` or `adapt` before any build work starts.
> Initial provider: `claude-code-opus5`. Required reviewer: `codex`.
> The Codex claim-refutation pass run alongside this draft (§11) is a
> *fact-check of the code claims*, **not** the §8 research review — that review
> is still owed.

---

## 1. Executive judgment

**The patterns 0xCodez teaches are almost entirely already built inside
TinyAssets — and the user surface tells the client to reach them through tools
the client cannot see.**

The substrate has a validated graph compiler with typed state reducers,
conditional routing, checkpointed resumable runs, child-branch invocation, a
cron scheduler, an event-subscription bus, a provenance-carrying knowledge graph
with entity resolution, a reflexion engine, per-node model/effort tiering, a
fork/remix lineage ledger, and skill snapshots that inherit across forks. Every
one of those is a named 0xCodez pattern.

But the connector ships **two mutually inconsistent surfaces**:

- `tools/list` advertises **seven handles** (`read_graph` / `write_graph` /
  `run_graph` / `read_page` / `write_page` / `converse` / `get_status`), on
  which a user **cannot create a graph, add a node, wire an edge, schedule a
  run, record a remix, or judge a run** — `write_graph target=branch` routes
  only to `patch_branch` (`universe_server.py:631-638`).
- The **`control_station` prompt** — which the server instructions tell every
  client to load early (`universe_server.py:202`) and which is registered and
  live (`:298`) — announces *"This connector exposes FIVE tools"*, names the
  five **deprecated** fat tools, and hands the model a complete intent→action
  routing table for authoring (`extensions action=build_branch`,
  `patch_branch`, `add_node`, `connect_nodes`, `set_entry_point`,
  `add_state_field`, `run_branch`, `goals action=propose/bind/leaderboard`)
  (`api/prompts.py:212-298`). It never mentions the seven handles.

Those five tools are stripped from `tools/list` by
`_DeprecatedToolVisibility.on_list_tools` (`universe_server.py:1986-1988`) but
remain dispatchable by name. So a signed-in client that *knows the name* can
still call them — while the model's tool schema, built from `tools/list`,
does not contain them. **The connector's own canonical behavioral prompt
instructs the model to call tools the model has not been given.** That is not a
missing capability; it is a surface incoherence that produces a confidently
wrong failure, and it is almost certainly the root cause of the STATUS row
*"rendered chat found stale commands, unknowable branch-ID prerequisite, and
missing starter branch."*

So the honest answers to the host's two headline questions:

1. **"Can our users do all these things?"** — On the *substrate*: mostly yes,
   with one genuine structural gap (parallel runtime-cardinality fan-out) and
   one correctly out-of-scope one (own-model training). On the *live user
   surface*: mostly **no**, not because the primitives are missing but because
   the two surfaces disagree about what the connector is. This is a
   **surface-coherence** problem — a much cheaper class of fix than a missing
   primitive, and exactly the class the minimal-primitives principle arbitrates.
2. **"Would the hardcore pro actually want to use us?"** — Today, no. They would
   load the prompt, be told to call `extensions`, find no such tool, and leave.
   The draw we *do* have (MIT licence, remixable commons with real lineage, an
   attribution/provenance ledger, a paid-work market) is real but invisible
   behind a surface that contradicts itself in the first thirty seconds.

**A security finding surfaced during cross-provider verification** (§8, GAP-8)
and is independent of the 0xCodez framing: `source_code` nodes `exec()` with
full `__builtins__`, and `approve_source_code` records approval from
`_current_actor()` with **no host-role and no author check**. It needs a
`STATUS.md` Concern row raised by whoever folds this back — this branch does not
edit `STATUS.md`, so the finding would otherwise stay invisible.

The strategic reframe: **0xCodez's audience is our exact target customer, and
they are graduating from "prompt an agent" to "author, verify, schedule, and
compound an agent system."** TinyAssets already *is* that system. The gap is
that we ship it with the authoring panel unbolted.

---

## 2. Source freshness stamp and canonicalization

**Fetched 2026-07-25.** `x.com/0xCodez` is login-walled to WebFetch, as the
host predicted. The account was canonicalized through public mirrors and
search-result excerpts, all of which corroborate each other.

| Source | URL | Reached | Date |
|---|---|---|---|
| Thread index (mirror) | https://threadnavigator.com/author/0xcodez/ | ✅ full | 2026-07-25 |
| Graph Engineering with Claude — 14 steps | https://threadnavigator.com/thread/2079165300625330317/ | ✅ full | posted 2026-07-23 |
| Agent Harness Engineering with Claude — 14 steps | https://threadnavigator.com/thread/2066867539305459732/ | ✅ full | posted 2026-07-14 |
| Graph Engineering workshop (2h, Anthropic engineer) | https://threadnavigator.com/thread/2081017726261199185/ | ✅ full | posted 2026-07-25 |
| "Loop Engineering" 11-page PDF thread | https://x.com/0xCodez/status/2069736449902027136 | ⚠️ excerpt only (mirror 404) | posted ~2026-06 |
| "Graph Engineering" 12-page PDF thread (KG pipeline) | https://x.com/0xCodez/status/2080250266851463209 | ⚠️ excerpt only (mirror 404) | posted 2026-07-24 |
| Build-your-own-LLM 5-stage pipeline (article mirror) | https://youmind.com/landing/x-viral-articles/build-llm-from-scratch-pipeline | ✅ full | — |
| Loop-engineering corroboration (independent) | https://hyper.ai/en/papers/Loop-Engineering-IEEE | ✅ | — |
| Graph-vs-loop framing (independent) | https://explainx.ai/blog/graph-engineering-ai-agents-multi-agent-organizations-2026 | ✅ | 2026 |
| Rattibha mirror | https://en.rattibha.com/0xCodez | ❌ HTTP 403 | — |

### What 0xCodez actually is (evidence, not vibes)

**0xCodez is a curator-explainer, not a shipper.** No GitHub repo, no library,
no framework, no benchmark is attributable to the account — a targeted repo
search surfaced only unrelated `awesome-harness-engineering` lists. The output
is a consistent format: take a primary artifact (an Anthropic engineer's PDF or
workshop, a Google/OpenAI/IBM course, a Karpathy lecture) and compress it into a
numbered 14-step breakdown with a memorable spine.

**This matters for how we weight it.** The *patterns* are not 0xCodez's — they
are Anthropic's, Google's, Karpathy's. What 0xCodez supplies is **the canonical
vocabulary the target customer now thinks in**, and a reliable read on what that
customer believes competence looks like this quarter. Treat the account as a
**demand signal with high fidelity and zero implementation authority**. Do not
cite it as a technical primary source; cite the artifacts it points at.

**License/adoption constraints:** none. Nothing to vendor, nothing to attribute,
no code to import. The entire integration surface is conceptual.

---

## 3. Module-by-module map of the outside system

The four disciplines, decomposed the way the skill requires.

### 3.1 Loop engineering — "you stop prompting the agent; you build the system that prompts it"

Spine: **Schedule → Discover → Build → Verify → Persist → repeat.** Five moves
per turn ([thread](https://x.com/0xCodez/status/2069736449902027136),
[corroboration](https://hyper.ai/en/papers/Loop-Engineering-IEEE)):

| Move | What it means | Why it's load-bearing |
|---|---|---|
| **Discovery** | The loop finds its own work — failing CI, open issues, recent commits — rather than being handed a task list | Removes the human from the queue-filling seat; this is what makes it a *loop* and not a *script* |
| **Handoff** | Each finding gets an isolated git worktree so parallel agents don't collide | Isolation is what makes parallelism safe |
| **Verification** | A second agent, *told to assume the code is broken*, reviews the first — "the thing that can say no" | An agent grading its own output praises it; tuning an independent skeptic is far more tractable than making a generator self-critical |
| **Persistence** | Results written to disk, never left in a context window that gets flushed | Context death is the default failure mode |
| **Scheduling** | An automation wakes it on a timer | Without this you have a harness, not a loop |

The harness/loop/self-improvement ladder from the companion 14-step thread
([source](https://threadnavigator.com/thread/2066867539305459732/)):

- **Harness** = model + tools + permissions + initial context.
- **Loop** = automated scheduling that runs the harness repeatedly.
- **Self-improving system** = loop + memory that compounds.
- Components: `CLAUDE.md` for standing facts (<~500 tokens), `settings.json`
  for permissions/auto-approval, **subagents** for isolated review contexts,
  **skills** as reusable `SKILL.md` procedures, **hooks** for deterministic
  enforcement at fixed lifecycle points, **memory files** that preserve lessons
  between sessions, and — the top rung — **distilled insights graduating from
  memory into skills**.
- Named anti-patterns: default settings; bloating standing-context files with
  procedures; mixing enforcement into suggestions; and *"wrapping loops around
  weak foundations."*

### 3.2 Graph engineering — "a prompter asks a question; an architect draws a graph"

14 steps ([source](https://threadnavigator.com/thread/2079165300625330317/)):

- **Problem:** multi-step agents are written linearly; each step waits on the
  previous one; context and latency both blow up.
- **Nodes and edges:** a node is one unit of work (an agent call); an edge is a
  *data dependency*. The sharpest line in the whole corpus: **"'and then' is an
  edge only when the next step actually consumes the previous output."** Most
  apparent sequence is false sequence.
- **Contracts:** every node declares bounded inputs and *validated structured
  outputs* — composition is only reliable when the schema is enforced.
- **Fan-out / fan-in:** independent work runs concurrently via `parallel()`;
  results converge at a **barrier** only where a judgment needs the complete set.
- **Diamond pattern:** split → parallel → reduce → synthesize. The canonical
  topology, reused for audits, research, and reviews.
- **Conditional routing** on runtime classification.
- **Verifier nodes** that validate findings before they propagate downstream.
- **Cycles with convergence conditions** for unknown-scope discovery
  (loop-until-dry rather than loop-N-times).
- **Model tiering** per node to control cost.
- **Dynamic workflows**: the model writes a JavaScript orchestration script
  rather than spending conversational turns on coordination — coordination logic
  costs zero tokens.

The 2026-07-25 workshop thread adds the org-level framing and a claim worth
noting as a demand signal: *"80% of our engineers are using self-improving
loops. Now everyone is building agentic graphs."* Independent commentary frames
the progression as **prompt engineering → loop engineering → graph engineering**,
with a dual-graph split: a stable **org graph** (long-lived agents, permanent
domain ownership) over an ephemeral **work graph** (task nodes that split, merge,
and vanish) ([explainx](https://explainx.ai/blog/graph-engineering-ai-agents-multi-agent-organizations-2026)).

### 3.3 Graph-as-memory — Extract → Resolve → Assemble → Query → Repeat

The knowledge-graph half ([thread](https://x.com/0xCodez/status/2080250266851463209)).
Framing: *"your agents' memory dies with their context window; a knowledge graph
makes it permanent."*

| Stage | Mechanics as taught |
|---|---|
| **Extract** | A cheap model (Haiku) pulls entities and subject-predicate-object triples, one call per document. *"The Pydantic schema is the only training data."* |
| **Resolve** | A stronger model (Sonnet) clusters coreferent entities — "Edwin Aldrin" → "Buzz Aldrin", zero string overlap — using descriptions as context |
| **Assemble** | Canonical nodes, typed edges, **provenance on every triple** |
| **Query** | Serialize a subgraph so the model reasons over triples; **every answer cites a specific edge** |
| **Repeat** | Plug into a multi-agent system as *shared* memory: workers write, evaluators fact-check against it, loops persist overnight |

### 3.4 Build-your-own-LLM — five stages

([mirror](https://youmind.com/landing/x-viral-articles/build-llm-from-scratch-pipeline),
tracking Karpathy's lecture): data preparation + tokenization → pretraining
(next-token over trillions of tokens) → supervised fine-tuning → reward
modeling → RLHF. The thesis the account emphasizes: **data quality and systems
engineering dominate architecture.** The transformer is the least interesting
part.

---

## 4. Module-by-module TinyAssets comparison

Every row verified against code in this checkout at
`claude/o5-agentic-pro-research` (base `origin/main` 6cde7ef0), not from memory.

| Outside module | TinyAssets equivalent | Evidence | Assessment |
|---|---|---|---|
| Node = unit of work with contract | `NodeDefinition` — `input_keys`, `output_keys`, `strict_input_isolation`, `prompt_template`, `timeout_seconds`, `retry_policy` | `tinyassets/branches.py:263` | **Stronger than taught.** Contracts are dataclass-validated with lossless JSON round-trip and a compile gate |
| Edge = data dependency | `EdgeDefinition` + `ConditionalEdge`, compiled onto a LangGraph `StateGraph` | `tinyassets/branches.py:577,599`; `tinyassets/graph_compiler.py:2912-2933` | **Parity** |
| Validated structured output | JSON contract injection + coercion + `_extract_json_object` | `graph_compiler.py:836-960` | **Parity** |
| Fan-in / barrier / reducers | `state_schema` with declared reducers; `append` concatenates, single-writer `merge` shallow-merges right-biased, **undeclared merge writes fail closed** | `openspec/specs/graph-execution-substrate/spec.md:42-65`; `graph_compiler.py:400-455` | **Stronger than taught.** 0xCodez's `parallel()` has no writer-conflict discipline at all |
| Fan-out (static K) | Multiple outgoing edges from one node; LangGraph runs them in one superstep; `concurrency_budget` throttles | `branches.py:909`; `graph_compiler.py:112` (`ConcurrencyTracker`) | **Parity** for design-time K |
| Fan-out (runtime N) | No LangGraph `Send`; topology is static at compile time. **But** a `source_code` node `exec()`s with full `__builtins__`, so runtime-N mapping is expressible *sequentially inside one node* | grep `Send(`: zero hits; `graph_compiler.py:2912`, `:1805-1807` | **Partial — GAP-3. Sequential yes (gated), parallel no** |
| Diamond pattern | Composable from the above once N is fixed at design time | — | Expressible for static K |
| Conditional routing | `graph.add_conditional_edges` routed **by `path_map` label, not target node id**, with first-label fallback on unknown output | `graph_compiler.py:2933`; spec:66-76 | **Stronger.** Label-indirection survives node renames |
| Verifier node | Any node + conditional edge; plus `evaluation_criteria` per node, `judge_run` / `list_judgments` / `compare_runs`, and `tinyassets/evaluation/` (structural, process, editorial) | `branches.py:352`; `api/extensions.py:741` | **Substrate stronger; surface absent** |
| Cycles with convergence | Cycles permitted; **a cycle with no exit fails validation**; default recursion limit 100, per-run override | spec:34,101 | **Stronger.** The convergence condition is compile-enforced, not conventional |
| Model tiering | `model_hint`, `reasoning_effort`, `llm_policy` per node with branch-level `default_llm_policy` fallback | `branches.py:300-330,905`; `graph_compiler.py:2884` | **Stronger than taught** |
| Sub-agent / isolated context | `invoke_branch_spec` (live blocking/async), `invoke_branch_version_spec` (frozen at a version), `await_run_spec`, `attach_existing_child_run`, depth cap | `branches.py:366-393`; spec:140-287 | **Substantially stronger.** Frozen-version child invocation has no analogue in the taught material |
| **Discovery** (loop move 1) | `producers/` (`goal_pool`, `node_bid`, `branch_task`), `work_targets.py`, `idle_cycle.py`, `enrichment_signals.py` | module tree | **Substrate present; surface absent** |
| **Handoff** (loop move 2) | Per-run checkpoint threads, `strict_input_isolation`, `node_sandbox.py`, per-universe dirs | spec:93-100 | **Parity**, different isolation model (state-scoped, not worktree) |
| **Verification** (loop move 3) | `judge_run`, `evaluation/`, `NodeEvaluator` stats + transitions, `attest/verify/dispute_gate_event` | `node_eval.py:150`; `api/extensions.py:751` | **Stronger** — includes a dispute/retract path |
| **Persistence** (loop move 4) | `SqliteSaver` checkpointing, `notes.json`, wiki commons, `project_memory_*`, `memory/` (episodic, archival, consolidation, temporal, versioning) | `checkpointing/sqlite_saver.py:37`; `tinyassets/memory/` | **Substantially stronger** |
| **Scheduling** (loop move 5) | Real cron parser + scheduler thread + event-subscription bus: `CronSchedule`, `register_schedule`, `register_subscription`, `_fire_due_schedules`, pause/unpause | `tinyassets/scheduler.py:108,217,407,559` | **Parity in substrate; ABSENT on the user surface** |
| Skills as reusable procedure | `BranchDefinition.skills` snapshots, **inherited by forks** | `branches.py:865`; `api/branches.py:2134-2148` | **Stronger.** Skill inheritance across lineage is not in the taught material |
| Memory → skill graduation | `memory/promotion.py`, `memory/consolidation.py`, `learning/craft_cards.py`, `learning/criteria_discovery.py`, `memory/reflexion.py` | module tree; `memory/reflexion.py:31` | **Substrate present; no user-facing graduation verb** |
| Hooks / deterministic enforcement | Node `checkpoints` with cumulative budget validation; `gates/`, `gate_events/`; effector consent grants | `branches.py:349`; `api/extensions.py:759` | **Parity-plus** |
| KG **Extract** | `knowledge/entity_extraction.py::extract_from_prose` — entities, edges, facts from a typed schema | `entity_extraction.py:165` | **Parity** |
| KG **Resolve** | `AliasRegistry.register/resolve/register_from_entities` | `entity_extraction.py:80` | **Parity** |
| KG **Assemble** | `add_entity` / `add_edge` / `add_facts` with `provenance`, `confidence`, `hardness`, `horizon`, `seeded_scene` columns | `knowledge/knowledge_graph.py:309,407,497`; schema at `:222` | **Stronger.** Provenance *and* a truth-value typing axis (`FactWithContext`, `AGENTS.md` hard rule #6) |
| KG **Query** | `query_facts`, `hipporag_query`, `raptor_query`, Leiden communities, `get_epistemic_access` | `knowledge_graph.py:558,630,665,769` | **Substantially stronger** — HippoRAG + RAPTOR + community detection + epistemic access control |
| KG as *shared* multi-agent memory | Constructed in only two places: `memory/archival.py`, `retrieval/agentic_search.py`. **No MCP path in or out** | grep `KnowledgeGraph(` | **GAP-4 — built, unreachable** |
| Dynamic workflow script | `source_code` nodes — fail-closed on `approved` + `approved_source_hash == sha256(src)` + a substring denylist, then `exec()` **in-process with full `__builtins__`, no OS sandbox**; the approve handler applies **no host-role and no author check** | `graph_compiler.py:1318-1372,1805-1807`; `api/branches.py:514-531`; spec:77-92 | **GAP-8 — security, not a feature gap** |
| Build-your-own-LLM | Nothing. `providers/router.py` routes to external providers; no training, no dataset export, no eval-set export | module tree | **GAP-5 — not expressible, and correctly so** |
| Provenance / lineage / attribution | `fork_from`, `parent_def_id`, `record_remix`, `get_provenance`, `fork_tree`, `attribution/`, `contribution_events.py`, `quality_leaderboard`, `recommended_parent_for_fork` | `branches.py:868-870`; `api/market.py:898,1012`; `api/branches.py:3348` | **Unique. No analogue anywhere in the taught corpus** |
| Paid work market | `write_graph target=request` with `pickup_incentive`, `priority_weight`, `directed_daemon_id` — **reachable on the canonical surface**; `escrow_*` and settlement are not | `universe_server.py:611-630`; `api/extensions.py:749` | **Unique. Partially reachable** |

### 4.1 The surface boundary — the finding under the finding

The canonical user surface is seven handles
(`universe_server.py:426,511,660,702,771,941,1930`), asserted live by
`CANONICAL_HANDLES` in `scripts/mcp_public_canary.py:72` per hard rule #11.
Their targets:

- `read_graph` → status, graphs, graph, goals, goal, runs, run, **branch**
  (full graph + node configs — a real export path)
- `write_graph` → goal, request, **branch (patch only)**, universe
- `run_graph` → run an existing branch
- `read_page` / `write_page` → commons wiki + issue filing
- `converse` → relay to the universe intelligence
- `get_status` → read-only

`write_graph target=branch` routes to `patch_branch`
(`universe_server.py:631-638`) — **edit an existing branch**. There is no
`create` route. The full authoring catalog — `create_branch`, `add_node`,
`connect_nodes`, `set_entry_point`, `add_state_field`, `build_branch`,
`validate_branch`, `approve_source_code`, `schedule_branch`,
`subscribe_branch`, `record_remix`, `get_provenance`, `judge_run`,
`publish_version`, `fork_tree`, `project_memory_*`, `set_engine` — lives on the
fat tools listed in `_DEPRECATED_TOOL_NAMES` (`universe_server.py:1030`), which
`_DeprecatedToolVisibility.on_list_tools` removes from `tools/list`
(`universe_server.py:1986-1988`).

**The boundary is discoverability, not capability — and the two channels
disagree.** Corrected by Codex cross-check (§11, C2 REFUTED):

- `on_call_tool` keeps the hidden tools **fully callable** for signed-in
  callers; only anonymous callers are refused (`universe_server.py:2004-2011`).
  Authorization-wise the fat tools are live.
- The `control_station` prompt — registered at `universe_server.py:298`, and
  the server instructions at `:202` tell every client to *"Load the
  `control_station` prompt early — it is the canonical behavioral surface…the
  tool catalog"* — states **"This connector exposes FIVE tools (describe ALL
  when asked)"** and enumerates `universe`, `extensions`, `goals`, `wiki`,
  `community_change_context`, followed by a ~40-row intent→action routing table
  covering the entire authoring surface (`api/prompts.py:212-298`). The seven
  canonical handles appear nowhere in it.

Net effect on a real client: the model's tool schema is built from `tools/list`
(seven handles); its behavioral prompt instructs it to call `extensions
action=build_branch`. The model follows the prompt, finds no such tool, and
fails in a way that reads to the user as a broken product — or, worse,
hallucinates the call. **That is a sharper defect than "the capability is
hidden."**

This is the same defect as the STATUS row *"Repair first-contact branch/wiki
onboarding — rendered chat found stale commands, unknowable branch-ID
prerequisite, and missing starter branch."* A rendered chatbot session hit it
from the user side; this audit reaches it from the code side. **"Stale commands"
is `control_station` naming retired tools.** The onboarding lane
(`openspec/changes/repair-first-contact-onboarding/`) is the natural home for
the fix, and it should be scoped as *prompt/surface reconciliation*, not as
copy edits.

### 4.2 The relay is not an action-taker (as-built)

`converse` → `universe_intelligence.converse` runs **two LLM calls per turn** —
the first-person reply plus a learning-extraction pass — and `commit_learning`
writes the universe's private canon (`universe_intelligence.py:267-274,300-327,
398,432-441`; corrected by Codex, §11 C4). Both calls run with
`allowed_tools=("WebFetch",)` and an explicit denylist of everything else
including `mcp__*` (`:41-112`).

What that does **not** include is any action surface: no MCP tool access, no
branch authoring, no run, no schedule. So the "universe intelligence is the sole
action-taker" architecture recorded in memory
(`universe-intelligence-relay-architecture`) is **design intent, not as-built**.
It has a memory and a voice; it does not have hands. A user cannot route around
the authoring-surface incoherence by asking their universe to build the graph
for them. In-node MCP access is equally narrow:
`_NODE_MCP_ACTION_ALIASES` (`graph_compiler.py:1375-1404`) permits two goals
reads, two gates reads, wiki **reads only** (writes explicitly refused at
`:1741-1745`), and `dispatch.enqueue` behind a fail-closed env gate.

---

## 5. Adjacent research

- **Loop engineering is a converged term, not one person's coinage** — surfaced
  independently by Steinberger, Cherny, and Osmani in June 2026
  ([hyper.ai](https://hyper.ai/en/papers/Loop-Engineering-IEEE)). The market is
  standardizing on this vocabulary; we should read STATUS/PLAN against it rather
  than invent parallel terms.
- **Harness auto-evolution is now benchmarked.** *Agentic Harness Engineering*
  reports 84.7% pass@1 on Terminal-Bench 2 and lifts a fixed model 69.7 → 77.0%
  over 10 iterations purely by evolving the harness, with the frozen harness
  transferring to SWE-bench-Verified
  ([arXiv 2604.25850](https://arxiv.org/pdf/2604.25850),
  [repo](https://github.com/china-qijizhifeng/agentic-harness-engineering)).
  Direct evidence that **the harness, not the model, is the improvable unit** —
  which is precisely what a remixable-branch commons is a market for.
- **Experience Graphs** ([arXiv 2606.29823](https://arxiv.org/pdf/2606.29823))
  and **Harness Engineering for Self-Improvement**
  ([Lil'Log](https://lilianweng.github.io/posts/2026-07-04-harness/)) both argue
  the durable asset is the accumulated *experience graph*, not the model. Our
  run/outcome/attribution ledger is an experience graph with a lineage ledger
  attached; nobody in this literature has the attribution half.
- **Countervailing evidence:** *When Agents Do Not Stop*
  ([arXiv 2607.01641](https://arxiv.org/html/2607.01641v1)) documents infinite
  agentic loops as a live failure class. Our compile-time
  "cycle-with-no-exit fails validation" rule and recursion limit are the correct
  posture; any fan-out primitive we add must inherit the same bounding, and
  should be cited as a *feature* when we talk to this audience.

---

## 6. Question 1 — "Can our users do all these things?"

Verdicts are given across **three** layers, because the honest answer differs by
each and collapsing them is what makes this question hard to answer straight:
`substrate` = the code in this checkout; `dispatchable` = callable by a
signed-in client that knows the tool name; `discoverable` = reachable by a
chatbot from `tools/list` + the `control_station` prompt as a real user would
hit it.

| # | Pattern (0xCodez) | Substrate | Dispatchable | Discoverable | Verdict |
|---|---|---|---|---|---|
| 1 | Author a node/edge graph with typed contracts | ✅ | ✅ `build_branch` | ❌ prompt names a tool not in `tools/list` | **expressible-with-missing-primitive: a coherent authoring surface (GAP-1)** |
| 2 | Static fan-out → barrier → reduce (diamond) | ✅ edges + reducers | ✅ | ❌ (needs #1) | **expressible-with-missing-primitive-#1** |
| 3 | Dynamic fan-out over a runtime-sized list | ⚠️ sequential-in-node only (full-builtins `exec`); no parallel `Send` | ⚠️ needs approval | ❌ | **expressible-with-missing-primitive: parallel fan-out (GAP-3)** |
| 4 | Conditional routing on runtime classification | ✅ path_map labels | ✅ | ❌ (needs #1) | **expressible-with-missing-primitive-#1** |
| 5 | Verifier node / "the thing that can say no" | ✅ + `judge_run`, criteria, dispute path | ✅ | ❌ | **expressible-with-missing-primitive-#1** |
| 6 | Cycles with convergence conditions | ✅ compile-enforced exit + recursion cap | ✅ | ❌ (needs #1) | **expressible-with-missing-primitive-#1** |
| 7 | Model tiering per node | ✅ `model_hint`/`reasoning_effort`/`llm_policy` | ✅ | ❌ | **expressible-with-missing-primitive-#1** |
| 8 | Sub-agent with isolated context | ✅ live/frozen/await/attach child invocation | ✅ | ❌ | **expressible-with-missing-primitive-#1** |
| 9 | **Scheduling** — wake the loop on a timer | ✅ cron + subscriptions + pause | ✅ `schedule_branch` | ❌ no canonical verb | **expressible-with-missing-primitive: schedule on the canonical surface (GAP-2)** |
| 10 | **Discovery** — the loop finds its own work | ✅ producers, work_targets, idle_cycle | ✅ | ❌ | **expressible-with-missing-primitive-#9** (schedule + wiki-read node ≈ discovery) |
| 11 | Handoff / isolation between parallel agents | ✅ state-scoped isolation + checkpoint threads | ✅ | ❌ | **expressible-with-missing-primitive-#1** |
| 12 | Persistence across context death | ✅ checkpoints, notes, wiki, memory tiers | ✅ | ⚠️ `write_page` + `read_graph target=run` yes | **expressible-today (partially)** |
| 13 | Memory that compounds → graduates into skills | ✅ promotion/consolidation/reflexion; skills inherit across forks | ✅ `add_skill`/`update_skill` patch ops | ❌ | **expressible-with-missing-primitive-#1 (GAP-6 closes with it)** |
| 14 | Knowledge graph as shared agent memory (E/R/A/Q) | ✅ and stronger (provenance, HippoRAG, RAPTOR, Leiden, epistemic access) | ❌ no MCP path in or out | ❌ | **not-expressible as a platform KG — GAP-4 (composable as a commons pattern)** |
| 15 | Arbitrary code as an orchestration node | ✅ full-builtins `exec` | ⚠️ self-approvable — see GAP-8 | ❌ | **expressible-but-unsafe — GAP-8 is a security finding, not a feature request** |
| 16 | Bring your own model / provider | ✅ credential vault + `set_engine` | ✅ (being retired) | ❌ | **expressible-with-missing-primitive — GAP-7 (owned elsewhere)** |
| 17 | Train / fine-tune your own LLM | ❌ nothing | ❌ | ❌ | **not-expressible — GAP-5 (correctly out of scope)** |
| 18 | Publish, fork, remix, and get attributed | ✅ full lineage + attribution ledger | ✅ `record_remix`/`get_provenance`/`fork_tree` | ⚠️ `read_graph target=branch` reads any public branch | **expressible-today (read); recording not discoverable** |
| 19 | Hire the work out / get paid | ✅ market + escrow + settlement | ✅ | ⚠️ `write_graph target=request` reachable; escrow not | **expressible-today (partially)** |

**Summary:** of 19 patterns, **2 discoverable today**, 3 partially, **1 genuinely
not-expressible and correctly so** (#17), **1 unreachable by any path** (#14),
**1 expressible-but-unsafe** (#15), and **11 blocked behind a surface that
advertises the wrong tools**.

Two things follow, and they point in different directions:

- **Eleven of nineteen unblock from one fix** — making the advertised surface
  and the callable surface agree. That is the highest-leverage item on this
  audit by a wide margin, and it is mostly not new code.
- **The substrate is not the weak layer.** On raw capability TinyAssets is at or
  ahead of everything 0xCodez teaches on 14 of 19 patterns. We are losing on
  presentation, not on power.

---

## 7. Question 2 — would the hardcore pro actually use us?

Adversarially, assuming a customer who has read every 0xCodez thread, already
runs their own loop, and reflexively distrusts platforms.

### 7.1 The honest draw

1. **MIT licence, full source, proven fresh-clone install.** `LICENSE` is MIT;
   `openspec/specs/oss-clone-and-install/spec.md` describes a *scheduled*
   Tier-3 job that clones to a clean dir, `pip install -e .`, and runs smoke +
   import-graph gates. The anti-lock-in answer is not a promise, it is a nightly
   CI job. **This is our single strongest card with this buyer and we do not
   lead with it.**
2. **Provenance and attribution nobody else has.** Every competitor's answer to
   "who wrote this pattern and what did it derive from" is a README credit.
   Ours is `fork_from` / `parent_def_id` lineage, `record_remix`,
   `get_provenance` with depth-bounded ancestry, `fork_tree`,
   `contribution_events`, an attribution calculator, and
   `Co-Authored-By` emission on ship (hard rule #10). For an audience whose
   entire craft is *reusable procedure*, a ledger that says who authored the
   procedure is the thing they cannot build alone.
3. **A commons of runnable graphs, not blog posts.** 0xCodez's whole business is
   that these patterns circulate as *prose*. A diamond-pattern audit graph you
   can fork, run, and see the lineage of is categorically better than a
   14-tweet thread. `quality_leaderboard` + `recommended_parent_for_fork`
   means the commons can rank what actually works.
4. **Correctness properties they'd have to discover the hard way.** Compile-time
   orphan/cycle-exit validation; single-writer merge enforcement with
   fail-closed undeclared writes; label-indirected conditional routing; frozen
   child-branch versions; hash-bound code approval; a terminal status taxonomy;
   resumable checkpoints under owner/status/version guards. Every one of these
   is a bug this buyer has already shipped at least once.
5. **A market attached to the graph.** Nobody else lets you post the work and
   pay for it in the same object model.

### 7.2 The honest repellent — be adversarial

1. **The product contradicts itself in the first thirty seconds.** The prompt
   the client is told to load says there are five tools and routes every build
   intent through `extensions`; `tools/list` offers seven different ones and no
   `extensions`. The model follows the prompt and fails. Time-to-disqualification
   is under five minutes and the verdict is "broken," which is strictly worse
   than "limited." Everything in §7.1 is invisible behind this. **This is the
   whole ballgame; most of the rest of this list is downstream of it.**
2. **Hidden state they can't see or reason about.** The authoring verbs exist,
   are documented in an advertised prompt, and are dispatchable — but are
   stripped from `tools/list`. A pro who works this out (and they will; the
   source is MIT) reads it as a platform whose own docs disagree with its own
   API. That damages trust more than a missing feature does.
3. **The relay promises an agent and delivers a voice.** The connector
   instructions describe a personified intelligence that acts. As built it is
   two LLM calls with `WebFetch`, a private-canon write path, and **no action
   surface at all** (`universe_intelligence.py:41-112,267-274`). It can
   remember and it can talk; it cannot do. A pro tests this in one prompt.
4. **Arbitrary code runs in-process with full builtins behind a substring
   denylist — and approval is self-service.** `exec(src, {"__builtins__":
   __builtins__, …})` (`graph_compiler.py:1805-1807`), fenced only by
   `if pattern in src` over `_DANGEROUS_PATTERNS` (`:1367-1372`), and
   `approve_source_code` writes `approved=True` from `_current_actor()` with no
   host-role check and no author check — an anonymous actor gets a *warning
   string*, not a refusal (`api/branches.py:514-531`). A security-literate buyer
   defeats a substring denylist in their head in ten seconds, and then will not
   run anyone else's forked graph — **which disables the commons, the one thing
   we're actually selling.** The STATUS P1 "no OS engine sandbox" concern is
   customer-facing, not internal. See GAP-8.
5. **No parallel dynamic fan-out.** The pro's default shape is
   `parallel(items.map(...))` where `items` came from the previous node. Ours
   requires the width at design time, or a sequential loop inside an approved
   `source_code` node — which is exactly the escape hatch a security-conscious
   buyer won't take. They hit this on their first real graph.
6. **BYOC is being retired from the surface while the alternative isn't live.**
   `set_engine` deposits a BYO key into the per-universe vault
   (`api/universe.py:5674`) but is fat-tool-only, and the active
   `retire-mcp-provider-secret-deposit` lane removes the MCP deposit path. Net
   position from outside: "you can't bring your own model." For a buyer whose
   first question is *which model runs my node*, that is close to fatal.
   Whatever replaces it must land **before** the deposit path goes away, or the
   window where the honest answer is "you can't" becomes a permanent impression.
7. **Their loop already works.** `.claude/`, a cron, a worktree script, a
   verifier subagent — the harness is a weekend. We are not competing with
   nothing; we are competing with something they already own and trust. The only
   defensible pitch is what a *single* engineer structurally cannot build:
   **other people's verified, attributed, forkable graphs.** Not the runtime.
8. **Forced shapes.** Universe/branch/node/goal is our vocabulary, not theirs
   (agent/tool/graph/task). Onboarding auto-creates a universe and binds a
   founder before they've decided they want one. A pro reads mandatory ceremony
   as a tax.

### 7.3 Verdict

**Today: no.** Not because of lock-in — the MIT licence and the nightly
clone-install proof genuinely defuse that — but because the connector's own
canonical prompt points at tools the client was not given, so the first serious
attempt fails; and because the one thing they'd stay for (the commons) is empty
of the graphs they'd want, precisely because the authoring path is incoherent.
That is a bootstrap deadlock and it resolves in one direction: **make the
advertised surface true, give it a create route, then seed the commons with the
patterns this audience already believes in** (diamond audit, verifier gate,
loop-until-dry discovery, extract-resolve-assemble-query memory).

**With GAP-1 closed, GAP-2 shipped, GAP-8 fixed, and four seeded reference
graphs: plausibly yes** — for the commons and the ledger, never for the runtime.
GAP-8 is load-bearing for that sentence, not incidental: a commons whose whole
value is running *other people's* graphs cannot ship on self-approved,
full-builtins, in-process `exec`. **We should stop pitching the runtime and
start pitching the ledger.**

---

## 8. Question 3 — smallest enabling primitive per gap

Each proposal is run through the project's own three tests
(`docs/audits/2026-04-28-commons-first-tool-surface-audit.md:44-60`):
**T1 irreducibility** (composable in <5 chatbot reasoning steps → it's a
convenience, don't ship it), **T2 commons-first**, **T3 user-capability**
(browser-only parity). Per `PLAN.md:27`, tool count is a budget that should
shrink. **Nothing below adds a top-level handle.** Every proposal is a *target*
or *field* on an existing handle, except where an irreducibility finding is
explicitly claimed.

Ranked by (unblocked patterns × customer-visibility) ÷ build cost.

### GAP-1 — the advertised surface and the callable surface disagree ⭐ rank 1

*Blocks 11 of 19 patterns. Two halves: one is a doc fix, one is a missing route.*

**Half A — coherence (no new primitive at all, and this is the urgent half).**
`control_station` must describe the surface the client was actually given.
Today it announces five tools that `tools/list` does not contain
(`api/prompts.py:212-298` vs `universe_server.py:1986-1988`). Rewrite its tool
catalog and intent→action routing table against the seven canonical handles.
This is a prompt edit, it ships without touching the runtime, and it converts a
"broken product" first impression into an honest "limited surface" one.

**Half B — the missing route.** `write_graph target=branch` already carries
`changes_json`: an ordered, transactional, author-gated patch-op list. Make
**an empty `branch_id` mean "create"** — the same op list applied to an empty
branch. One route, zero new verbs, zero new concepts; transactional and
author-gate semantics come for free.

- **T1:** Half A is not a primitive question at all. Half B is a PRIMITIVE-GAP —
  no composition of the seven handles produces a new branch.
- **T2:** ✅ inherits `visibility`; public branches are already a global remix
  commons by design (`universe_server.py:481-488`).
- **T3:** ✅ pure MCP; browser-only parity.
- **Risk:** the patch-op vocabulary must cover node defs, edges, conditional
  edges, state fields, entry point, and `skills` or create is half-usable.
  `control_station` already advertises `add_skill`/`update_skill` ops, so the
  vocabulary is likely broader than `patch_branch`'s canonical route exposes —
  **verify the op set before scoping** (§12 Q4).
- **Sequencing:** Half A can land alone and should not wait for Half B. Shipping
  B without A leaves the prompt still pointing at retired tools.
- **Not this:** re-exposing `create_branch` + `add_node` + `connect_nodes` +
  `set_entry_point` + `add_state_field` as five canonical verbs. Tool-budget
  regression; each composes into one patch list; T1 fails them.
- **Also not this:** un-hiding the fat tools. That inverts PR-178 and would turn
  the hard-rule-#11 `--assert-handles` canary red.

### GAP-2 — no scheduling / event subscription on the canonical surface ⭐ rank 2

*Blocks the loop discipline entirely. Without a timer there is no loop.*

**Smallest primitive:** `write_graph target=schedule` with a cron expression +
`branch_id`, and `read_graph target=schedules`. Backed by `register_schedule` /
`list_schedules` / `pause_schedule`, which already exist and run
(`scheduler.py:217,297,320`).

- **T1:** PRIMITIVE-GAP. A chatbot cannot compose a timer; there is no
  primitive that produces one.
- **T2:** ✅ schedules are per-branch, per-author.
- **T3:** ✅ **this is the browser-only user's only path to a loop** — a
  local-app user can cron it themselves. Highest T3 value of any proposal here.
- **Risk:** runaway schedules. Bound as the compiler already bounds cycles
  (min interval, max active schedules, auto-pause on N consecutive failures)
  and cite [arXiv 2607.01641] as the reason. **Do not ship the timer without
  the bound.**
- Deliberately excludes event subscriptions in slice 1 — cron is the
  irreducible half; subscriptions are a second, separately-justified finding.

### GAP-3 — no *parallel* dynamic (runtime-cardinality) fan-out ⭐ rank 3

*The pro's default shape. Narrowed by the Codex cross-check: a `source_code`
node `exec()`s with full builtins, so a runtime-N **sequential** map already
works inside one node. What is missing is the parallel form — and the
sequential escape hatch runs through GAP-8, so it is not a safe answer.*

**Smallest primitive:** one field on `NodeDefinition` —
`fan_out_over: "<state_key>"` — meaning "run this node once per element of that
list state key, appending into the declared `append` reducer." Implemented over
LangGraph's `Send`, which the compiler does not currently use. It reuses the
reducer contract that already exists rather than inventing a barrier concept.

- **T1:** PRIMITIVE-GAP, and this one is a **genuine irreducibility finding** —
  no arrangement of static edges expresses an unknown-at-design-time width.
- **T2:** ✅ no storage-shape change.
- **T3:** ✅.
- **Risk:** the highest-risk proposal here. Fan-out width × concurrency ×
  recursion interacts with `ConcurrencyTracker`, the enqueue budget, and cost.
  Must land with a hard width cap, must respect `concurrency_budget`, and must
  be differential-tested against the static-edge path per `AGENTS.md`
  §Testing.
- **Cheaper alternative to price first:** `enqueue_branch_run` +
  `await_run_spec` already approximates this asynchronously. If a design note
  shows the async shape is sufficient, GAP-3 drops to `Defer` and we save the
  riskiest change on the list. **Price this before scoping the `Send` work.**

### GAP-4 — knowledge graph is unreachable ⭐ rank 4

*We have the best-in-class version of 0xCodez's flagship pattern and no door.*

**Smallest primitive:** **none — do not add a verb.** The irreducibility test
says a KG query is composable: a node already reads the wiki commons and writes
typed state. What's missing is not a primitive but a **commons pattern** — a
published reference branch implementing extract → resolve → assemble → query
over `read_page`, with provenance carried in state and every claim citing its
source page.

- **T1:** CONVENIENCE-COMPOSABLE → **document the composition, ship no verb.**
  This is the principle working correctly.
- **Standards emerge from the commons:** if that reference branch gets forked
  heavily and every fork reimplements the same resolve step, *that* is the
  irreducibility evidence for a future primitive. Not before.
- Depends on GAP-1 (you can't publish a reference branch you can't author) and
  on the `brain-okf-canonical-store` lane, which owns store shape.

### GAP-5 — no own-model training

**Proposal: none. `Avoid`.** Training is not a TinyAssets primitive and adding
it would violate every principle in `PLAN.md:27`. But 0xCodez's own thesis —
*data quality and systems engineering dominate architecture* — points at the
adjacent thing we **do** own: a TinyAssets user's runs, judgments, outcomes, and
attributed lineage are exactly the SFT/reward-model corpus that stage 3-4 needs.
The right response is **export, not training**: the user's own run/outcome
history, in their hands, to fine-tune wherever they like.

That belongs to the existing PLAN-gated portability/deletion target, is
privacy-load-bearing, and per skill §6 **must never start as automatic public
trace upload** — private-by-default with explicit review, or not at all. Record
as `Defer`; do not open a lane from this audit.

### GAP-6 — skills exist but cannot be attached or graduated by a user

*The top rung of 0xCodez's ladder — memory distilling into a shared skill — and
our version already inherits across forks, which his does not.*

**Smallest primitive:** none new. `BranchDefinition.skills` is a field on an
object that GAP-1 makes writable; a skill snapshot is a patch op. **GAP-6 closes
for free when GAP-1 lands, provided the patch-op vocabulary covers `skills`.**
Verify that during GAP-1 scoping.

- **T1:** CONVENIENCE-COMPOSABLE once GAP-1 exists.

### GAP-7 — BYOC being retired from the surface with no live replacement

**Proposal: none from this audit — a sequencing constraint instead.** The active
`retire-mcp-provider-secret-deposit` lane and `#1691`/R2-1a
(`set_engine` must constrain `allowed_providers`) already own this. What this
audit contributes is a customer-facing datum for that lane's decision record:
**"which model runs my node, and can I bring my own key" is a top-3 qualifying
question for the target buyer.** Any window where the answer is "you can't"
should be treated as a customer-visible outage, not an internal transition.
Route this observation into the existing lane; do not open a new one.

### GAP-8 — self-approvable arbitrary code execution ⭐ security, ranks above everything

*Not a 0xCodez pattern. Surfaced by the Codex cross-check (§11 MISSED) while
verifying GAP-3, and independently confirmed against the code. Recorded here
because it materially changes both the §7.2 answer and the commons thesis.*

Three facts compose:

1. `source_code` nodes execute via `exec(src, {"__builtins__": __builtins__,
   "invoke_mcp_action": …})` — **full builtins, in-process, no OS sandbox**
   (`graph_compiler.py:1805-1807`).
2. The only content fence is a substring denylist, `if pattern in src` over
   `_DANGEROUS_PATTERNS` (`:1367-1372`) — trivially defeated by
   `getattr`/`__import__` string construction.
3. `_ext_branch_approve_source_code` sets `approved=True`, `approved_by =
   _current_actor()`, and `approved_source_hash` **with no host-role check and
   no branch-author check** in the handler; an anonymous actor receives a
   *warning string in the response*, not a refusal (`api/branches.py:514-531`).
   `_BRANCH_WRITE_ACTIONS` gates this as an OAuth write **scope**
   (`auth/provider.py:553`) and for ledger logging (`branches.py:318`) — neither
   is a role.

The runtime docstring states *"host approval is the primary line of defense"*
(`graph_compiler.py:1318-1323`). The approval path does not implement a host
role, so the primary defense is a self-signed assertion and the secondary one is
a substring match.

**Smallest fix — a check, not a primitive:** require a host/owner role in
`_ext_branch_approve_source_code` before writing `approved`, and fail closed on
an anonymous actor instead of warning. That is a guard on an existing handler.
The OS sandbox (the standing STATUS P1) remains the durable fix and is not
displaced by this.

- **T1:** not a primitive question — a missing authorization check.
- **Verification owed before acting:** (a) whether a signed-in non-author can
  reach *another* author's branch through this handler — the handler shows no
  author gate but `get_branch_definition`'s visibility scoping was not traced;
  (b) whether any production auth mode already blocks it upstream. **Do not file
  a severity until both are answered.**
- **Cross-check against known-stale-row risk:** confirm this is not already
  covered by the `#1485` fail-closed-seam or the "no OS engine sandbox" Concern
  before opening anything. The residual claimed here is the *approval role*,
  which is narrower than either.
- **This branch does not edit `STATUS.md`.** Whoever folds this back must raise
  the Concern row, or the finding dies with this artifact.

### Deliberately not proposed

- A `graph_authoring` tool, a `parallel` verb, a `verify` verb, a `memory` verb,
  a `skill` verb, a `knowledge_graph` verb. All are compositions or convenience
  rollups; all fail T1; all grow a budget `PLAN.md:27` says must shrink.
- Un-hiding the legacy fat tools. That inverts the PR-178 canonical-surface
  decision, and hard rule #11's `--assert-handles` canary would go red. The fix
  is routes on the seven handles, not resurrecting the eleven.

---

## 9. OpenSpec change candidates

All `pending`. **None may be proposed, scoped, or implemented until the §8
Codex research review returns `approve` or `adapt`.**

| Candidate | Scope (one para) |
|---|---|
| `canonical-surface-prompt-reconciliation` | **Highest urgency, lowest cost, no runtime change.** Rewrite the `control_station` prompt's tool catalog and intent→action routing table so it describes the seven canonical handles instead of the five `tools/list`-stripped fat tools it names today (`api/prompts.py:212-298`). Includes an invariant test asserting the prompt names only tools present in `tools/list`, so the two surfaces cannot drift apart again — the drift, not the wording, is the defect. Almost certainly the root cause of the "stale commands" half of `repair-first-contact-onboarding`; check for overlap and fold rather than compete. Closes GAP-1 Half A. |
| `canonical-surface-graph-authoring` | Make `write_graph target=branch` with an empty `branch_id` create a branch from an ordered `changes_json` patch-op list, reusing the existing transactional, author-gated `patch_branch` machinery. Covers the op vocabulary needed for a usable create — node defs, edges, conditional edges, state fields with reducers, entry point, and `skills` — so a user can author a complete runnable graph without any new handle. Explicitly does not un-hide the legacy fat tools and does not change `CANONICAL_HANDLES`. Closes GAP-1 Half B and GAP-6; with the prompt fix, unblocks 11 of 19 audited patterns. Requires `--assert-handles` canary + rendered `ui-test` before acceptance. |
| `source-code-approval-authority` | Security, not a feature. Require a host/owner role in `_ext_branch_approve_source_code` before it writes `approved`/`approved_source_hash`, and fail closed on an anonymous actor rather than returning a warning string (`api/branches.py:514-531`). Scope-gates the path from "signed-in user" to "full-builtins in-process `exec`" (`graph_compiler.py:1805-1807`). Must first answer whether a non-author can reach another author's branch here, and whether production auth already blocks it upstream; must be checked against the existing `#1485` seam and the standing OS-sandbox Concern so it does not duplicate them. Closes GAP-8. Does not replace the OS sandbox. |
| `canonical-surface-branch-scheduling` | Add `write_graph target=schedule` (cron expr + `branch_id` + pause/unpause) and `read_graph target=schedules` over the shipped `tinyassets/scheduler.py` registry. Ships **with** its bounds, not after: minimum interval, max active schedules per author, and auto-pause after N consecutive failed runs, citing the infinite-agentic-loop failure class. This is the browser-only user's only path to a loop, so it is the highest user-capability-axis item on the list. Depends on `canonical-surface-graph-authoring` (scheduling a branch you cannot author is inert). Closes GAP-2. |
| `graph-runtime-fan-out-over-state` | Design-first change: price whether `enqueue_branch_run` + `await_run_spec` already satisfies runtime-cardinality fan-out before committing to a `NodeDefinition.fan_out_over` field over LangGraph's `Send`. If the async path suffices, the change closes as `no new primitive` and documents the composition. If not, it specifies the field with a hard width cap, `concurrency_budget` participation, recursion/enqueue-budget interaction, and differential tests against the static-edge path per the hot-path-rewrite rule. Closes GAP-3. Highest technical risk on this list. |
| `commons-reference-graph-patterns` | Not a code change — a commons seed. Publish four canonical reference branches as public, forkable, attributed graphs: diamond audit (split → parallel → reduce → synthesize), adversarial verifier gate, loop-until-dry discovery, and extract-resolve-assemble-query memory over `read_page`. These are the patterns the target audience already believes in, expressed as runnable artifacts instead of prose, and they are what makes the commons non-empty on the day authoring ships. Depends on `canonical-surface-graph-authoring`. Closes GAP-4 the principle-correct way — a composition pattern, not a verb. |

**Not proposed as changes:** GAP-5 (own-model training — `Avoid`; the export
half belongs to the existing PLAN-gated portability target) and GAP-7 (BYOC —
route the customer-facing sequencing datum into the existing
`retire-mcp-provider-secret-deposit` and `#1691`/R2-1a lanes).

---

## 10. Pickup packet + worktree landing packet

**Concept:** canonical-surface authoring + scheduling for agentic-pro users.
**Source artifact:** this file. **Source URLs:** §2.
**Initial provider:** `claude-code-opus5`. **Required reviewer:** `codex`.

**Applies when touching:** `tinyassets/universe_server.py` (the seven handles),
`tinyassets/api/branches.py` (`_BRANCH_ACTIONS`, patch-op vocabulary),
`tinyassets/scheduler.py`, `tinyassets/graph_compiler.py` (fan-out / `Send`),
`scripts/mcp_public_canary.py` (`CANONICAL_HANDLES`), or any first-contact /
onboarding surface. If you are working on any of these, read §4.1 first — the
surface boundary is the load-bearing fact.

**Next home:** `ideas/PIPELINE.md` Active Promotions (not a `STATUS.md` Work row
yet — build is review-blocked and STATUS is at its 60-line budget). **Exact next
action:** Codex research review per skill §8.

**Two things must not wait for that review:**

1. **GAP-8 needs a `STATUS.md` Concern row.** It is a security finding, not a
   research implication, and the review gate does not apply to raising a
   concern. This branch deliberately does not edit `STATUS.md` (it is not
   merging), so the finding is invisible until someone files it. Answer the §12
   Q3 severity inputs first.
2. **GAP-1 Half A (`control_station` reconciliation) is a prompt fix**, not a
   research-derived design. If the `repair-first-contact-onboarding` lane owns
   the "stale commands" symptom, this belongs there now.

**Overlap check before any lane is materialized:**

- `openspec/changes/repair-first-contact-onboarding/` — **same defect, different
  entry point** (rendered chat found stale commands, the missing starter branch,
  and an unknowable branch-ID prerequisite). GAP-1 Half A is very likely that
  lane's root cause. Do not open a competing lane; fold in or add a `Depends`
  edge.
- The standing "no OS engine sandbox" P1 Concern and the `#1485` fail-closed
  seam — GAP-8 must be checked against both before it is filed as new. Its
  residual is narrower than either: the missing *approval role*.
- `openspec/changes/brain-okf-canonical-store/` — owns store shape; GAP-4's
  reference branch must not presuppose a different one.
- `retire-mcp-provider-secret-deposit` + `#1691`/R2-1a — own GAP-7 entirely.
- PLAN store/private-data/primitive/privacy `host-decision` rows — gate the
  GAP-5 export half.

**Worktree landing packet** (reserved, **not materialized** — build is
review-blocked and the host scoped this session to research):

| Field | Value |
|---|---|
| Branch | `claude/canonical-surface-graph-authoring` |
| Worktree | `../wf-canonical-surface-graph-authoring` (via `python scripts/wt.py new`) |
| Base | `origin/main` |
| Depends | this artifact + a Codex review verdict of `approve`/`adapt`; overlap resolution with `repair-first-contact-onboarding` |
| Write-set (STATUS Files cell) | `openspec/changes/canonical-surface-graph-authoring/`, `tinyassets/universe_server.py`, `tinyassets/api/branches.py`, `tests/` |
| Read deps to recheck | `scripts/mcp_public_canary.py:72`, `openspec/specs/live-mcp-connector-surface/spec.md`, `openspec/specs/graph-execution-substrate/spec.md` |
| PLAN modules to review | `PLAN.md:27` (minimal primitives), the five-permissioned-handles module |
| Memory refs | `enabling-primitives-not-prebuilt-complexity`, `universe-intelligence-relay-architecture`, `universe-engine-sandbox-p0`, `no-users-build-correct-shape`, `stale-backlog-rows-misdirect` |
| Related implications | `docs/audits/2026-04-28-commons-first-tool-surface-audit.md` (T1/T2/T3), `docs/audits/2026-04-26-user-capability-axis-implications.md`, `docs/audits/2026-07-21-zapier-automation-platform-implications.md` |
| First slice | The OpenSpec proposal only — no runtime code |
| Gates: pre-commit | `pytest` (targeted) + `ruff check` |
| Gates: pre-push | Codex review `approve`/`adapt` recorded in a durable artifact |
| Gates: pre-acceptance | `mcp_public_canary.py --assert-handles` (hard rule #11 — the handle set must be **unchanged**) **and** a rendered chatbot `ui-test` proving a user can author and run a graph end-to-end |
| Fold-back | Draft PR while review-blocked; ready PR only after gates; retire the row on land; sync delta specs + archive in the same lane |

---

## 11. Cross-provider verification of the code claims

The seven load-bearing code claims in §4 were dispatched to Codex
(`codex exec`, read-only, this checkout) framed as **refute-by-default** with a
hard output contract, per the `codex-review-script-assumes-pr-review` and
`silent-failure-dispatch-and-tests` memory patterns.

**Result: 4 confirmed, 3 refuted.** All three refutations were independently
re-verified against the code by the author and **the analysis above was rewritten
to match** — §1, §4 (three rows), §4.1, §4.2, §6, §7.2, §8 (GAP-1, GAP-3, new
GAP-8), and §9 all changed as a result. The refuted claims are preserved here
rather than silently deleted, because the corrections are the most valuable
output of this audit.

| Claim | Verdict | Evidence |
|---|---|---|
| C1 — seven handles, no create route | **CONFIRMED** | `universe_server.py:402-410`, `:631-640` |
| C2 — authoring catalog undiscoverable | **REFUTED** | `on_call_tool` keeps hidden tools callable (`:1976-1988`); the advertised `control_station` prompt documents `extensions` and its full action surface (`api/prompts.py:212-236,249-298`). *Corrected: the boundary is `tools/list` vs. an advertised prompt that contradicts it — a worse defect than the original claim.* |
| C3 — runtime-N fan-out not expressible | **REFUTED** | Topology is static (`graph_compiler.py:2914-2933`), but `source_code` nodes exec with full builtins (`:1805-1810`), so sequential runtime-N mapping works inside one node. *Corrected: the gap is **parallel** fan-out.* |
| C4 — relay is one turn, `WebFetch` only, no writes | **REFUTED** | Two LLM calls — reply + learning extraction (`universe_intelligence.py:432-441`, `:267-274`) — and `commit_learning` writes private canon (`:300-327,398`). *Corrected: it has memory and a voice; the no-action-surface half of the claim stands.* |
| C5 — `source_code` fail-closed at runtime, in-process | **CONFIRMED** | inline authoring strips caller-supplied approval (`api/branches.py:1502-1504`); runtime verifies approval/hash/denylist (`graph_compiler.py:1318-1372`) then execs in-process (`:1805-1810`) |
| C6 — in-node MCP narrowly aliased | **CONFIRMED** | `graph_compiler.py:1375-1404`, rejection at `:1697-1708`, wiki writes blocked `:1737-1745`, enqueue fail-closed `:1407-1416` |
| C7 — scheduler built but unexposed | **CONFIRMED** | `scheduler.py:108-145,217-267,407-445,559-614`; canonical targets still limited at `universe_server.py:631-640` |

**Codex's MISSED finding**, quoted verbatim because it outranks everything the
seven claims were designed to test:

> *"The seven handles are a discoverability boundary, not a capability/security
> boundary: signed-in clients can call hidden fat tools, approve code without a
> host-role check (`tinyassets/api/branches.py:514-520`), then obtain full
> in-process Python execution."*

Independently verified and promoted to **GAP-8** (§8).

**Method note for future dispatches:** framing the ask as *refute-by-default*
with a hard output contract is what produced this. A "please review" framing
would very likely have returned agreement with all seven claims, three of which
were wrong. Consistent with the `codex-review-script-assumes-pr-review` and
`silent-failure-dispatch-and-tests` memory patterns.

> **This is a fact-check of code claims only.** It does **not** satisfy the
> skill §8 research review — that review must re-check the primary sources and
> the TinyAssets framing, and is still owed before any build work.

---

## 12. Open questions and verification gaps

1. **Was the narrow `write_graph` target set a deliberate product decision or an
   incomplete PR-178 fold?** This determines whether GAP-1 Half B is a bug or a
   direction change. `universe_server.py:402-412` reads like a migration in
   progress — and `control_station` was evidently never updated with it, which
   is evidence for "incomplete." **Host decision.**
2. **Does GAP-1 duplicate `repair-first-contact-onboarding`?** Must be answered
   before any lane opens. Strong suspicion: the "stale commands" symptom in that
   row *is* the `control_station` drift.
3. **GAP-8 severity inputs, unanswered:** (a) can a signed-in non-author reach
   another author's branch through `_ext_branch_approve_source_code`? The
   handler shows no author gate, but `get_branch_definition`'s visibility
   scoping was not traced. (b) Does any production auth mode block it upstream?
   (c) Is the residual already covered by `#1485` or the standing OS-sandbox
   Concern? **Answer all three before filing a severity.**
4. **Does the existing patch-op vocabulary cover node defs, edges, conditional
   edges, state fields, entry point, and skills?** GAP-1 Half B's scope and
   GAP-6's free closure both depend on it. `control_station` advertises
   `add_skill`/`update_skill`, so it is probably broader than the canonical
   route exposes — but `changes_json` op shapes were **not** enumerated in this
   pass.
5. **Is `enqueue_branch_run` + `await_run_spec` sufficient for parallel dynamic
   fan-out?** If yes, GAP-3 drops off and we avoid the riskiest change.
   Answerable by design analysis alone — do it before scoping any `Send` work.
6. **Does the OS-sandbox residual gate the commons itself?** GAP-8 sharpens
   this: if users run each other's forked graphs, self-approvable full-builtins
   `exec` is a commons-wide risk, not an engine-local one. Not analyzed here.
7. **Unreached primary sources:** the two Anthropic PDFs (loop engineering,
   graph engineering) were read only through secondary excerpts; both mirror
   URLs 404'd. If a reviewer can reach them, re-verify §3.1 and §3.3 against the
   originals.

---

## 13. Skill self-iteration

Two repeatable steps this study surfaced, proposed for
`.agents/skills/external-research-implications/SKILL.md` — **not yet applied**,
since editing the skill mid-study would change the process being followed:

1. **Canonicalize the source's *type*, not just its URL.** §2 established that
   0xCodez is a curator, not a builder — which changed how every downstream
   claim was weighted (demand signal, zero implementation authority) and
   redirected citation to the primary artifacts behind the threads. The skill's
   §2 covers "repo" and "paper" but has no branch for a **curator/influencer
   account**, where the correct move is to canonicalize *the audience's
   vocabulary* and chase the primaries. Worth adding.
2. **When the source is login-walled, record a mirror-reachability table.** §2's
   table (which mirror worked, which 404'd, which returned 403, and which claims
   rest on excerpt-only sources) is what lets a reviewer know exactly which
   findings are second-hand. The skill requires a freshness stamp but not a
   *reachability* stamp.

Applying these requires `scripts/sync-skills.ps1` + `validate_skills.py` per
skill §10, and is left to the follow-up lane so this research commit stays
scoped to the artifact.
