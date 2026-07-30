---
title: 0xCodez agentic-pro patterns — TinyAssets implications
date: 2026-07-25
initial_provider: claude-code-opus5
required_reviewer_provider: codex
review_status: >
  ADAPT (codex, 2026-07-25, against commits 1d8c9fc5 then cb248b8c) — findings
  folded, logged as R1-R6 in section 11.2 and R7-R8 in section 11.3. Build
  authority is per-candidate only: see the Status column of section 9. One
  candidate withdrawn (premise refuted), one fold-in, one design-only, one
  later-content-experiment; two adapt with stated preconditions. GAP-9 has no
  candidate and no authority, and its owed review round is a SECURITY review.
review_verdict: adapt
review_rounds: >
  round 1 = code-claim fact-check (4 confirmed / 3 refuted, section 11.1);
  round 2 = skill section 8 opposite-provider research review (section 11.2);
  round 3 = opposite-provider re-review of the round-2 fold (section 11.3,
  adapt on one GAP-9 residual; its replacement claims independently
  re-confirmed 3 of 3 under refute-by-default)
artifact_kind: external-research-implications
source_reachability: reachable via public mirrors (X itself login-walled)
recovery_freshness: >
  2026-07-30 against origin/main 1c86b073; primary-source links and the four
  load-bearing current-code findings were rechecked before recovery publication.
load-bearing-question: >
  Can a hardcore pro agentic engineer express 0xCodez's four taught disciplines
  (loop engineering, graph engineering, self-improving agents, build-your-own-LLM)
  on TinyAssets' primitives — and would they choose to, over building it themselves?
---

# 0xCodez agentic-pro patterns — TinyAssets implications

## Recovery freshness note — 2026-07-30

This artifact was recovered from the stranded
`claude/o5-agentic-pro-research` branch onto `origin/main`
`1c86b073c86903a771fbcc4f7c3e3bcb1e03c6e7`. Its original analysis is dated
2026-07-25 and is preserved as the reviewed historical record. Current-main
verification changes one load-bearing classification:

| Finding | 2026-07-30 current-main classification |
|---|---|
| GAP-1 Half A — `control_station` described hidden legacy tools | **Resolved by PR #1794** (`46ff5c5c`). `tinyassets/api/prompts.py` now enumerates exactly the seven canonical handles, explicitly refuses hidden legacy calls, and states unsupported creation honestly. `tests/test_goals_discoverability.py` and `tests/test_mcp_instruction_surfaces.py` carry drift coverage. |
| GAP-1 Half B — no canonical workflow-create route | **Still current.** `write_graph target="branch"` still dispatches only `patch_branch` for an existing `branch_id`; the reconciled prompt now exposes this limitation instead of contradicting `tools/list`. |
| GAP-9 — ordinary prompt nodes lack model-directed tool use | **Still current.** `NodeDefinition.tools_allowed` remains wired only through `_build_node_mcp_invoker` inside approved `source_code`; opaque nodes/effects remain author-wired composition, not model-selected tool calls. The no-candidate/security-review boundary still applies. |
| GAP-2 prerequisite — schedule ownership is client-supplied | **Still current.** `tinyassets/api/runtime_ops.py` still reads `owner_actor` from request kwargs for create/list/remove/pause paths. Do not canonically expose it before server-bound authority lands. |
| GAP-8 residual — in-process full-builtins execution | **Still current.** `graph_compiler.py` still executes approved source in process; the upstream `tinyassets.extensions.admin` gate also remains. The withdrawn self-approval claim stays withdrawn. |

The official Anthropic articles and arXiv records cited in §§2/5 were
re-reached on 2026-07-30. The 0xCodez/X material remains mirror-dependent, so
it remains a demand-language sample with zero technical authority. Statements
below such as “today,” “still owed,” and line-number citations describe the
2026-07-25 checkout unless this recovery note overrides them.

This recovery creates no new implementation authority. Section 9 remains
per-candidate, except that the Half-A prompt-reconciliation row is now resolved.

> **BUILD AUTHORITY IS PER-CANDIDATE — read §9's Status column before acting.**
> The skill §8 opposite-provider review ran on 2026-07-25 and returned
> **`adapt`** (initial provider `claude-code-opus5`; reviewer `codex`). That
> unblocks the *gate*, not the *scope*: of the six candidates, one is
> **withdrawn** (its premise was refuted), one is a **fold-in** to an existing
> lane, one is **design-only with no implementation authority**, one is a
> **later content experiment rather than a runtime change**, and the two
> remaining are **`adapt`** with preconditions that must be met first
> (creation semantics; server-bound schedule ownership). GAP-9, added *by* the
> review, has **no candidate and no authority** — it needs its own review round,
> and per §11.3 R8 that round is a **security** review: both of its candidate
> shapes move a security boundary, including the one previously described as
> mechanical.
>
> **Three** rounds of cross-provider verification are logged in §11, and
> **refuted claims are preserved rather than deleted** (§11.1 R-round: 4
> confirmed / 3 refuted; §11.2 R1–R6; §11.3 R7–R8). Two corrections matter most:
> **R1 — the GAP-8 self-approval claim is withdrawn** (`approve_source_code` is
> gated upstream by the `tinyassets.extensions.admin` action scope), and **R7 —
> GAP-9 is agent-node *tool parity*, not "the graph cannot reach the outside
> world"**; platform-authored opaque nodes and declared effects already compose
> a repo→diff→PR path with no `source_code`. Do not build against either
> withdrawn version; both are preserved in §8 and §11.2–11.3 for the record only.

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
   with **two** genuine structural gaps and one correctly out-of-scope item
   (own-model training). The two structural gaps are parallel
   runtime-cardinality fan-out (GAP-3) and — added on Codex research review,
   §11.2 R2, **scoped on re-review, §11.3 R7** — **ordinary nodes are not
   tool-using agents** (GAP-9): a prompt-template node is text-in/text-out,
   `tools_allowed` is honored only inside approved `source_code`
   (`graph_compiler.py:1793`), and even there the alias set is selected
   goals/gates reads, wiki reads, and paced enqueue. This is **not** the claim
   that a graph cannot reach the outside world — platform-authored **opaque
   nodes** (`read_repo_files`, `search_repo_files`, `validate_patch`) and
   **declared effects** (`github_pull_request`, `wiki_write_back`) already
   compose a repo→diff→PR path with no `source_code` at all. The gap is that
   every one of those reaches is **wired by the author, chosen by nobody at
   run time**. The official Anthropic primary defines the foundational building
   block as an *augmented* LLM — retrieval, tools, memory, with the model
   choosing the call — so a graph of pre-wired platform verbs is not at parity
   with the taught agent node, however good its state contracts are. On the
   *live user surface*: mostly **no**, not because the primitives are missing
   but because the two surfaces disagree about what the connector is. That half
   is a **surface-coherence** problem — a much cheaper class of fix than a
   missing primitive, and exactly the class the minimal-primitives principle
   arbitrates.
2. **"Would the hardcore pro actually want to use us?"** — Today, no. They would
   load the prompt, be told to call `extensions`, find no such tool, and leave.
   The draw we *do* have (MIT licence, remixable commons with real lineage, an
   attribution/provenance ledger, a paid-work market) is real but invisible
   behind a surface that contradicts itself in the first thirty seconds.

**A security finding surfaced during cross-provider verification** (§8, GAP-8)
and is independent of the 0xCodez framing — **but half of it was wrong and has
been withdrawn** (Codex research review, §11.2 R1). What stands: `source_code`
nodes `exec()` with full `__builtins__`, in-process, with **no OS sandbox**,
fenced only by a substring denylist. That is the standing STATUS P1 "no OS
engine sandbox" concern, restated with its customer-facing consequence, not a
new finding. What is **withdrawn**: the claim that a merely signed-in user can
self-approve their own code. `approve_source_code` is gated upstream by
`_dispatch_scope_error("extensions", action)` (`api/extensions.py:399`) →
`tinyassets.extensions.admin` (`auth/provider.py:410-418`), and WorkOS
production founders receive `read`/`write`/`costly`/`submit_request`/`list` but
**not** `admin` (`auth/workos_provider.py:29-40`, asserted by
`tests/test_source_code_approval_action.py:118-124`). The missing handler-local
author check does not establish a production self-approval path. `STATUS.md` was
corrected accordingly on `origin/main` (#1758) after this artifact was first
committed; the residual is regression coverage, not a new guard.

The strategic reframe — **stated as a hypothesis to validate, not a conclusion
this evidence establishes** (Codex research review, §11.2 R4): 0xCodez's audience
is plausibly our exact target customer, and they are graduating from "prompt an
agent" to "author, verify, schedule, and compound an agent system." TinyAssets
already *is* that system on the substrate. The gap is that we ship it with the
authoring panel unbolted — and, per GAP-9, with the nodes themselves unable to
touch anything outside the graph.

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
are Anthropic's, Google's, Karpathy's. What 0xCodez supplies is **one fresh
demand-language signal** — a readable sample of how a segment of this audience
is currently phrasing competence. Treat the account as a **demand signal with
zero implementation authority**. Do not cite it as a technical primary source;
cite the artifacts it points at.

**Calibration (Codex research review, §11.2 R5).** An earlier draft called this
"the canonical vocabulary the target customer now thinks in" and said the market
is standardizing on it. That overstates the sample: the mirror showed only tens
to low hundreds of views on the relevant threads at fetch time, and the
authoritative ideas predate the wording — Anthropic's
[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
already describes parallelization, orchestrator-workers, evaluator-optimizer
loops, tools, memory, and programmatic workflows, and
[How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
documents parallel subagents and dynamic delegation. A targeted search surfaced
no official Anthropic primary for the mirror's specific "Graph Engineering,"
`parallel()`, `pipeline()`, `/workflows`, or `ultracode` product claims — those
are usable as curator/audience evidence, **not** as verified product facts. The
*decomposition* in §3.1 is separately corroborated by the
[Loop Engineering mirror](https://hyper.ai/en/papers/Loop-Engineering-IEEE) and
stands.

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
| Node = **augmented LLM** (retrieval + tools + memory) — the foundational building block in the Anthropic primary | `NodeDefinition.tools_allowed` exists (`branches.py:307`) but `_build_node_mcp_invoker` has **exactly one call site** (`graph_compiler.py:1793`), inside the approved-`source_code` exec path. A prompt-template node is text-in/text-out and never sees `tools_allowed`. The alias set itself is two goals reads, two gates reads, wiki **reads**, and paced `dispatch.enqueue` | `graph_compiler.py:1375-1404,1679-1708,1793-1807`; `branches.py:307` | **GAP-9 — below the taught baseline.** *Scoped §11.3 R7:* the graph is **not** toolless — platform-authored **opaque nodes** (`read_repo_files`, `search_repo_files`, `validate_patch`; `graph_compiler.py:2634-2646`) and **declared effects** (`github_pull_request`, `wiki_write_back`; `api/branches.py:1672-1683`) compose a repo→diff→PR path with no `source_code`. What is missing is **model-directed** tool use: the author pre-wires every opaque step, the model chooses nothing, and anything the platform did not pre-author (CI, issues, arbitrary APIs, web) still falls to the `source_code` hatch |
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
| **Discovery** (loop move 1) | `producers/` (`goal_pool`, `node_bid`, `branch_task`), `work_targets.py`, `idle_cycle.py`, `enrichment_signals.py` | module tree | **Daemon-internal only.** *Corrected per §11.2 R2:* this is the daemon producing its own tasks, **not** a user-authored node discovering work. *Scoped §11.3 R7:* a user's branch can discover through the **opaque** `search_repo_files`/`read_repo_files` nodes or wiki reads inside approved `source_code` — but in every case the author names the query, never the model. So this row depends on GAP-9, not just on the surface |
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
| Dynamic workflow script | `source_code` nodes — fail-closed on `approved` + `approved_source_hash == sha256(src)` + a substring denylist, then `exec()` **in-process with full `__builtins__`, no OS sandbox**. Approval is gated upstream by the `tinyassets.extensions.admin` action scope (*corrected per §11.2 R1* — an earlier draft claimed the handler was self-approvable; it is not) | `graph_compiler.py:1318-1372,1805-1807`; `api/extensions.py:399`; `auth/provider.py:410-418`; spec:77-92 | **GAP-8 — the standing OS-sandbox P1, restated with its commons consequence. Not a new authorization gap** |
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
`:1741-1745`), and `dispatch.enqueue` behind a fail-closed env gate — and even
*that* set is reachable only from an approved `source_code` node, because
`_build_node_mcp_invoker` has a single call site inside the exec path
(`:1793`). A prompt-template node has **no** tool access at all — no invoker, no
tool schema, no call loop. It can still be *wired next to* a platform-authored
opaque node or carry a declared effect (§8 GAP-9, "what already exists"), which
is composition by the author, not tool use by the model. See GAP-9.

---

## 5. Adjacent research

- **Loop engineering is independently corroborated, not one person's coinage**
  — attributed by the cited mirror to Steinberger, Cherny, and Osmani in June
  2026 ([hyper.ai](https://hyper.ai/en/papers/Loop-Engineering-IEEE)). This is
  enough to treat the phrase as recognizable adjacent vocabulary, not enough to
  claim market-wide standardization.
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
| 10 | **Discovery** — the loop finds its own work | ⚠️ producers/work_targets/idle_cycle are **daemon-internal**; a user's node discovers only via wiki reads inside approved `source_code` | ⚠️ | ❌ | **expressible-with-missing-primitives #9 *and* #20** — *corrected per §11.2 R2; the original row conflated daemon task production with user-authored node tool access* |
| 11 | Handoff / isolation between parallel agents | ✅ state-scoped isolation + checkpoint threads | ✅ | ❌ | **expressible-with-missing-primitive-#1** |
| 12 | Persistence across context death | ✅ checkpoints, notes, wiki, memory tiers | ✅ | ⚠️ `write_page` + `read_graph target=run` yes | **expressible-today (partially)** |
| 13 | Memory that compounds → graduates into skills | ✅ promotion/consolidation/reflexion; skills inherit across forks | ✅ `add_skill`/`update_skill` patch ops | ❌ | **expressible-with-missing-primitive-#1 (GAP-6 closes with it)** |
| 14 | Knowledge graph as shared agent memory (E/R/A/Q) | ✅ and stronger (provenance, HippoRAG, RAPTOR, Leiden, epistemic access) | ❌ no MCP path in or out | ❌ | **not-expressible as a platform KG — GAP-4 (composable as a commons pattern)** |
| 15 | Arbitrary code as an orchestration node | ✅ full-builtins `exec`, **no OS sandbox** | ⚠️ approval requires the `extensions.admin` scope (*corrected §11.2 R1 — not self-approvable*) | ❌ | **expressible-but-unsafe — GAP-8. The unsafety is the missing OS sandbox (standing P1), not a missing approval role** |
| 16 | Bring your own model / provider | ✅ credential vault + `set_engine` | ✅ (being retired) | ❌ | **expressible-with-missing-primitive — GAP-7 (owned elsewhere)** |
| 17 | Train / fine-tune your own LLM | ❌ nothing | ❌ | ❌ | **not-expressible — GAP-5 (correctly out of scope)** |
| 18 | Publish, fork, remix, and get attributed | ✅ full lineage + attribution ledger | ✅ `record_remix`/`get_provenance`/`fork_tree` | ⚠️ `read_graph target=branch` reads any public branch | **expressible-today (read); recording not discoverable** |
| 19 | Hire the work out / get paid | ✅ market + escrow + settlement | ✅ | ⚠️ `write_graph target=request` reachable; escrow not | **expressible-today (partially)** |
| 20 | **Node as a tool-using agent** — the *model* decides mid-reasoning to call a tool, picks the arguments, reads the result, continues | ⚠️ `tools_allowed` exists but is honored only inside approved `source_code` (`graph_compiler.py:1793`); alias set is goals/gates reads, wiki reads, paced enqueue (`:1375-1404`). Prompt-template nodes: nothing. *Author-wired* platform verbs do exist (opaque nodes + effects, `graph_compiler.py:2634-2646`) — that is composition, not model-directed tool use | ⚠️ author-wired opaque/effect composition for the verbs the platform pre-authored; anything else via the `source_code` escape hatch | ❌ | **not-expressible for an ordinary node — GAP-9.** *Added on Codex research review (§11.2 R2); scoped against the composition path on re-review (§11.3 R7); this row was missing from the original pass* |

**Summary:** of **20** patterns, **2 discoverable today**, 3 partially, **1
genuinely not-expressible and correctly so** (#17), **1 unreachable by any path**
(#14), **1 expressible-but-unsafe** (#15), **1 not expressible for an ordinary
node** (#20), and **11 blocked behind a surface that advertises the wrong
tools**.

Three things follow, and they point in different directions:

- **Eleven of twenty unblock from one fix** — making the advertised surface
  and the callable surface agree. That is still the highest-leverage item on
  this audit by a wide margin, and it is mostly not new code.
- **The substrate is strong but not uniformly ahead.** *Corrected on Codex
  research review (§11.2 R2).* The original claim was "at or ahead on **14 of
  19**." That aggregate counted #10 Discovery as substrate-parity — it is
  daemon-internal task production, not a user-authored node capability — and it
  omitted the augmented-LLM node baseline entirely. Removing #10 from the parity
  column and adding #20 as a non-parity row gives **13 of 20**. The direction of
  the original claim survives; its size does not.
- **Two of the three shortfalls are not presentation problems.** GAP-3 (parallel
  fan-out) and GAP-9 (node tool access) are real substrate work. Only the
  eleven-pattern block is a surface fix. An audit that says "we are losing on
  presentation, not on power" is now too generous by exactly those two gaps.

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
   denylist.** `exec(src, {"__builtins__": __builtins__, …})`
   (`graph_compiler.py:1805-1807`), fenced only by `if pattern in src` over
   `_DANGEROUS_PATTERNS` (`:1367-1372`). A security-literate buyer defeats a
   substring denylist in their head in ten seconds, and then will not run anyone
   else's forked graph — **which disables the commons, the one thing we're
   actually selling.** The STATUS P1 "no OS engine sandbox" concern is
   customer-facing, not internal. See GAP-8. *Corrected per §11.2 R1:* an earlier
   draft added "and approval is self-service." That is wrong — approval requires
   the `tinyassets.extensions.admin` scope, which production founders do not
   hold. The repellent is the sandbox, not the approval role, and it is the
   weaker of the two arguments for it.
5. **Ordinary nodes don't decide anything; the author pre-wires every reach
   outside the graph.** *Scoped on re-review (§11.3 R7) — the original wording,
   "cannot touch anything outside the graph," was false.* The graph **can**
   reach a repo, validate a diff, open a PR, or publish to the wiki, by wiring
   platform-authored **opaque nodes** and **declared effects**
   (`graph_compiler.py:2634-2646`; `api/branches.py:1672-1683`). What it cannot
   do is let the *model* choose the call: `tools_allowed` is honored only inside
   approved `source_code` (`graph_compiler.py:1793`), and the alias set there is
   selected goals/gates reads, wiki reads, and paced enqueue (`:1375-1404`).
   This buyer's mental model of "a node" is Anthropic's augmented LLM —
   retrieval, tools, memory — so a static, fully pre-wired chain reads to them as
   the *pre-agent* shape, and the first step the platform did not pre-author
   (CI, issues, an arbitrary API, the web) drops them straight into the same
   `source_code` hatch item 4 just told them not to trust. **This is the gap that
   makes items 4 and 6 load-bearing instead of theoretical.** See GAP-9. *Added
   on Codex research review (§11.2 R2).*
6. **No parallel dynamic fan-out.** The pro's default shape is
   `parallel(items.map(...))` where `items` came from the previous node. Ours
   requires the width at design time, or a sequential loop inside an approved
   `source_code` node — the same escape hatch, and it needs an admin to open it.
   They hit this on their first real graph.
7. **BYOC is being retired from the surface while the alternative isn't live.**
   `set_engine` deposits a BYO key into the per-universe vault
   (`api/universe.py:5674`) but is fat-tool-only, and the active
   `retire-mcp-provider-secret-deposit` lane removes the MCP deposit path. Net
   position from outside: "you can't bring your own model." For a buyer whose
   first question is *which model runs my node*, that is close to fatal.
   Whatever replaces it must land **before** the deposit path goes away, or the
   window where the honest answer is "you can't" becomes a permanent impression.
8. **Their loop already works.** `.claude/`, a cron, a worktree script, a
   verifier subagent — the harness is a weekend. We are not competing with
   nothing; we are competing with something they already own and trust. The only
   defensible pitch is what a *single* engineer structurally cannot build:
   **other people's verified, attributed, forkable graphs.** Not the runtime.
9. **Forced shapes.** Universe/branch/node/goal is our vocabulary, not theirs
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

**With GAP-1 closed, GAP-9 answered, GAP-2 shipped, GAP-8's sandbox residual
addressed, and reference graphs seeded: plausibly yes** — for the commons and the
ledger, never for the runtime. GAP-8 is load-bearing for that sentence, not
incidental: a commons whose whole value is running *other people's* graphs
cannot ship on full-builtins, in-process `exec` with no OS sandbox, regardless of
who signed the approval. GAP-9 is load-bearing in the other direction: a commons
of graphs that can only run the verbs the platform pre-authored, wired in a
fixed order by the graph's author, is a commons of **static pipelines** — the
forkable artifact this audience wants is one where the node itself decides. (The
sharper earlier phrasing, "graphs whose nodes cannot touch a repo, CI, or the
web," was corrected on re-review — repo reach exists via opaque nodes; §11.3 R7.)

**On "stop pitching the runtime, pitch the ledger" — reframed as a hypothesis
(Codex research review, §11.2 R4).** The first half is supported: graph
orchestration patterns are old, common, and available in tools this buyer may
already own, so runtime features alone are a weak differentiator. The ledger is
also real in the code. What this evidence does **not** show is that 0xCodez's
audience values that ledger, would switch for it, or treats it as the primary
purchase criterion — none of the sampled threads evaluates provenance markets,
attribution, remix economics, or paid work. The ledger is also not yet coherently
reachable from the canonical surface. So the defensible statement is:
**differentiate on a verified, attributed, forkable commons, and validate that
proposition with target users — do not claim the source proved it.** Pitching
*only* the ledger before authoring, tool-using nodes, security, and
discoverability are addressed would overrun both the evidence and the product.

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

Ranked by (unblocked patterns × customer-visibility) ÷ build cost. **Ranks were
revised on the Codex research review (§11.2 R2):** GAP-9 enters at rank 2 —
ahead of scheduling and fan-out, because both of those presume the nodes inside
the loop can *do* something — pushing GAP-2 to 3, GAP-3 to 4, and GAP-4 to 5.
GAP numbers are discovery order, not rank; read the ⭐ marker.

### GAP-1 — the advertised surface and the callable surface disagree ⭐ rank 1

*Blocks 11 of 20 patterns. Two halves: one is a doc fix, one is a missing route.*

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

### GAP-9 — ordinary nodes are not tool-using agents ⭐ rank 2

*Added on Codex research review (§11.2 R2). Missed entirely by the original pass,
which is why it carries the highest re-ranking. Numbered 9 by discovery order;
ranked 2 by impact.*

The taught unit — and the unit in the official Anthropic primary
([Building effective agents](https://www.anthropic.com/engineering/building-effective-agents))
— is an **augmented LLM**: retrieval, tools, memory, with the model choosing the
call. Ours is a prompt template with excellent typed I/O and no hands **of its
own** — the graph around it can be given hands by its author, which is a
different thing and is the distinction this section now turns on.

**Scoped on the Codex re-review of the fold (§11.3 R7).** The first version of
this section said the *only* way a graph could touch a repo was `source_code`.
That is false, and the false version made the gap look bigger and more diffuse
than it is. Two adjacent things have to be held apart, because only one of them
is missing.

#### What already exists — opaque-node + effect composition (NOT the gap)

The platform ships **host-authored node bodies a user can reference but not
supply**, and **declared external-write sinks that fire from run state**. Both
were verified in this checkout:

- **Opaque domain callables.** `read_repo_files` (`effectors/github_read.py:63-64,189,286-296`),
  `search_repo_files` (`effectors/github_search.py:72-73,242,315-323`), and
  `validate_patch` (`effectors/validate_patch.py:43-44,80,198-206`) register into
  the domain registry at import of `tinyassets.effectors`
  (`effectors/__init__.py:57-60`). The compiler resolves `(branch.domain_id,
  node.node_id)` and wraps the hit as a graph node (`graph_compiler.py:2634-2646`
  → `_build_opaque_node`, `:1875-1930`). The user names the node; the **platform
  owns the body**, which is why opaque nodes deliberately bypass
  `_validate_source_code` (`:1883-1885`) — there is no user code to approve.
- **Declared effects.** `effects` is a `NodeDefinition` attribute, accepted in
  `add_node` / `update_node` patch specs (`api/branches.py:1672-1683,1733`), and
  run at run completion off a documented packet shape (`runs.py:2658-2669` →
  `effectors/__init__.py`). Shipped sinks include `github_pull_request`
  (`effectors/github_pr.py:108`), `github_merge`, `wiki_write_back`,
  `twitter_post`. They are gated in depth — global kill-switch env → soul
  effect-authority (`effectors/authority.py`) → env capability map →
  per-destination consent — and **default to dry-run evidence** rather than a
  real write (`github_pr.py:112-114,1139-1320`).

So *read a repo → localize the files → validate a diff → open a PR* is
**composable today with no `source_code` node at all**. That is a real,
platform-trusted path, and the earlier absolute claim erased it.

Two limits on that path, both verified, neither of which is the gap:

1. **It is closed-world.** You get the verbs the platform wrote. Query CI, file
   an issue, hit an arbitrary external API, search the web — no opaque node, no
   sink. Those *do* fall back to `source_code`.
2. **It is domain-gated, and the gate is currently unreachable from patch ops.**
   `resolve_domain_callable` is an exact `(domain_id, node_id)` tuple lookup
   (`domain_registry.py:68-73`); those three effectors register under
   `DOMAIN_ID = "tinyassets"`, while `BranchDefinition.domain_id` **defaults to
   `"workflow"`** (`branches.py:858`; `api/branches.py:385,2090`) — and the
   effector docstrings themselves say "in the `workflow` domain"
   (`github_read.py:4-6`, `github_search.py:6-9`), contradicting their own
   constant. `_apply_patch_op` has no `set_domain` op (`api/branches.py:2332-2560`:
   node/edge/state/skill ops plus `set_name`/`set_description`/`set_tags`/
   `set_published`/`set_visibility`/`set_fork_from`/`set_goal`), so domain is
   fixed at create time — and create is not on the canonical surface (GAP-1
   Half B). *This is a separate, smaller defect than GAP-9; it is recorded here,
   not promoted to a gap of its own, and it is downstream of GAP-1 Half B.*

#### What is actually missing — model-directed tool use inside a node (the gap)

Composition is the **graph author** deciding, at authoring time, which platform
verb runs where, with arguments wired from state fields. The taught agent node
is the **model** deciding, mid-reasoning, that it needs a tool, choosing the
arguments, reading the result, and continuing. Neither an opaque node nor a
completion effect gives an LLM a tool schema or a call loop; the opaque node
runs whether or not any model wanted it, and the effect fires after the run is
over. That is the parity gap, and it is unaffected by how many opaque nodes
ship:

1. `NodeDefinition.tools_allowed` exists (`branches.py:307`), round-trips
   through the serializer (`catalog/serializer.py:224,265`), and is settable via
   patch ops (`api/branches.py:2039-2045`).
2. `_build_node_mcp_invoker` — the thing that reads `tools_allowed` and turns it
   into a callable — has **exactly one call site**, `graph_compiler.py:1793`,
   inside `_compile_source_code_node`. A prompt-template node never receives an
   invoker, so its `tools_allowed` is inert configuration.
3. Even inside `source_code`, `_NODE_MCP_ACTION_ALIASES` (`:1375-1404`) is two
   goals reads, two gates reads, five wiki **reads**, and `dispatch.enqueue`
   behind a fail-closed env gate. No repository, no CI, no issue tracker, no
   external API, no web.

**Consequence, restated precisely, and why it still outranks scheduling and
fan-out.** A pro's first real workflow is something like *read the failing CI
job → find the offending diff → draft a fix → open a PR*. The repo-read, the
diff validation, and the PR are composable from the opaque nodes and sinks
above; **the CI query is not, and none of it is decided by the model** — the
author has to pre-wire every step and every argument, which is exactly the
static workflow the taught material treats as the *pre-agent* shape. The moment
the user wants a step the platform did not pre-author, or wants the model to
choose, the only path is a `source_code` node plus an admin approval — the
escape hatch GAP-8 exists to warn about. Scheduling a loop (GAP-2) and widening
its fan-out (GAP-3) both presume the nodes inside the loop can decide something;
this gap is upstream of both.

**Smallest primitive — NOT determined, deliberately. Both shapes are
security-boundary changes (§11.3 R8).** The earlier version called shape (a)
"cheap; changes no security boundary." That was wrong and is the more dangerous
of the two errors in this section, because it is the sentence a future lane
would quote to skip a security review:

- *(a) Wire the existing invoker into the prompt path* so a prompt-template
  node's `tools_allowed` becomes a real tool schema. It adds **no alias to the
  registry** — and that is the only sense in which it is narrow. It changes
  **capability reachability**, which is the boundary itself. Today the invoker
  is constructed only after `_validate_source_code(node)` passes
  (`graph_compiler.py:1790` → `:1793`), i.e. only inside a body that carries
  `approved=True` **and** an `approved_source_hash` equal to sha256 of the
  effective source (`:1318-1365`), with the approval itself behind the
  `tinyassets.extensions.admin` scope (§11.2 R1). Prompt-template nodes compile
  with **no approval gate whatsoever** (`:2627-2633`) and their template is
  ordinary patchable text whose effective caller is a model reading run state.
  Shape (a) therefore moves the whole alias set — **including the
  side-effecting, env-gated `dispatch.enqueue`** (`:1397-1403`) — from
  *admin-approved, hash-bound code* to *unapproved, prompt-injection-reachable
  text*. Any candidate must state what replaces approval + hash-binding as the
  gate for that path.
- *(b) Widen `_NODE_MCP_ACTION_ALIASES`* beyond the current read-mostly set.
  Also a security-boundary decision: every alias added is a new capability
  reachable from an LLM-authored node, and the SSRF/egress residual in the
  standing reshape Concern applies directly.

The two differ in *which* boundary moves — (a) moves who may reach the existing
set, (b) moves what the set contains — not in whether one is a security change
and the other plumbing. **Neither is a plumbing task.**

- **T1/T2/T3: NOT RUN.** This gap arrived *from* the review, so it has not been
  through the project's own three tests with an opposite-provider verdict on the
  result. **It therefore grants no build authority of any kind** — including for
  shape (a), which merely *looks* cheap and is the exact profile of a change
  that smuggles a capability widening past a gate. It needs its own review
  round, and that round is a **security** review, not a scoping one.
- **Cross-check owed:** whether the deliberate narrowness is a recorded design
  decision rather than an omission. `graph_compiler.py:1380-1386` carries an
  explicit comment refusing in-node wiki *writes* ("a node that needs to publish
  goes through an effect, not `invoke_mcp_action`") — and the composition path
  above shows that referent is **real and shipped** (`wiki_write_back`,
  `effectors/wiki_write_back.py:24`), so the comment is a live routing decision,
  not aspirational. If the read-mostly boundary is likewise deliberate, GAP-9 is
  a *product-positioning* finding, not a defect — and the honest fix may be
  documenting the boundary rather than widening it. **Answer this before
  proposing anything.**

### GAP-2 — no scheduling / event subscription on the canonical surface ⭐ rank 3

*Blocks the loop discipline entirely. Without a timer there is no loop.*

**Smallest primitive:** `write_graph target=schedule` with a cron expression +
`branch_id`, and `read_graph target=schedules`. Backed by `register_schedule` /
`list_schedules` / `pause_schedule`, which already exist and run
(`scheduler.py:217,297,320`).

- **T1:** PRIMITIVE-GAP. A chatbot cannot compose a timer; there is no
  primitive that produces one.
- **T2:** ⚠️ **conditional fail until ownership is server-bound** — see the
  prerequisite below. The original "schedules are per-branch, per-author" pass
  was wrong: the author is whatever string the client sent.
- **T3:** ✅ **this is the browser-only user's only path to a loop** — a
  local-app user can cron it themselves. Highest T3 value of any proposal here.

**PREREQUISITE — server-bind schedule ownership before any exposure.** Found on
Codex research review (§11.2 R3) and independently verified against the code;
now also a STATUS P2 Concern on `origin/main` (#1758). The legacy scheduling
actions trust a **client-supplied** actor:

- `_action_schedule_branch` reads `owner_actor` straight out of `kwargs`,
  defaults it to the literal `"anonymous"`, and never calls `_current_actor()`,
  never checks that the caller can see or owns `branch_def_id`
  (`api/runtime_ops.py:350-392`).
- `_action_unschedule_branch` passes that same client string to
  `unregister_schedule(..., requesting_actor=owner_actor)` (`:398-411`) — so the
  authorization check is performed against a value the caller chose.
- `_action_list_schedules` accepts a blank owner filter and enumerates
  everything (`:414-423`).

The `extensions.admin` scope gates `pause_schedule` / `unpause_schedule` /
`unschedule_branch` (`auth/provider.py:410-418`), but `schedule_branch` and
`subscribe_branch` sit in the *costly* tier — so an ordinary authenticated
founder can register a schedule attributed to someone else. **Bind
`owner_actor` to `_current_actor()` server-side, scope list/pause/remove to the
authenticated actor or an explicit admin, and validate target-branch authority
— all before a canonical route exists.** This is a prerequisite to exposure, not
a later hardening pass: publishing `write_graph target=schedule` over the
current backend would promote a legacy-surface defect onto the canonical one.

- **Separable, not required for slice 1:** the runaway-schedule bound. Minimum
  interval and max-active are already implemented in `scheduler.py` and are
  reusable as-is; a **new** consecutive-failure counter with auto-pause is
  plausible operational hygiene ([arXiv 2607.01641] is the failure class) but it
  is *not* needed to prove the primitive and should be justified on its own
  rather than bundled into the first exposure slice. *Corrected per §11.2 R3 — an
  earlier draft said "do not ship the timer without the bound," which conflated
  the reusable existing bounds with new failure-policy state.*
- Deliberately excludes event subscriptions in slice 1 — cron is the
  irreducible half; subscriptions are a second, separately-justified finding.

### GAP-3 — no *parallel* dynamic (runtime-cardinality) fan-out ⭐ rank 4

*The pro's default shape. Narrowed by the Codex cross-check: a `source_code`
node `exec()`s with full builtins, so a runtime-N **sequential** map already
works inside one node. What is missing is the parallel form — and the
sequential escape hatch runs through GAP-8's unsandboxed `exec` and needs an
admin to open it, so it is not a safe answer or an available one.*

**Smallest primitive:** one field on `NodeDefinition` —
`fan_out_over: "<state_key>"` — meaning "run this node once per element of that
list state key, appending into the declared `append` reducer." Implemented over
LangGraph's `Send`, which the compiler does not currently use. It reuses the
reducer contract that already exists rather than inventing a barrier concept.

- **T1:** PRIMITIVE-GAP, and this one *looks* like a **genuine irreducibility
  finding** — no arrangement of static edges expresses an unknown-at-design-time
  width. **But the comparison is unfinished** (§11.2 R6), which is why §9 lists
  this as **design-only with no implementation authority**. An unfinished
  irreducibility test is not a passed one.
- **T2:** ✅ no storage-shape change.
- **T3:** ✅.
- **Risk:** the highest-risk proposal here. Fan-out width × concurrency ×
  recursion interacts with `ConcurrencyTracker`, the enqueue budget, and cost.
  Must land with a hard width cap, must respect `concurrency_budget`, and must
  be differential-tested against the static-edge path per `AGENTS.md`
  §Testing.
- **Cheaper alternative to price first:** `enqueue_branch_run` +
  `await_run_spec` approximates this asynchronously. **Do not presume
  equivalence** (§11.2 R6): `enqueue_branch_run` is paced asynchronous dispatch
  returning a *branch-task identity*, not a joined child-run result, so any
  claim that it substitutes for an in-graph dynamic map must supply the join
  and the barrier, not just the fan-out. If a design note shows the async shape
  is genuinely sufficient, GAP-3 drops to `Defer` and we save the riskiest
  change on the list. **Price this before scoping the `Send` work.**

### GAP-4 — knowledge graph is unreachable ⭐ rank 5

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

### GAP-8 — unsandboxed in-process code execution ⭐ security, largely already known

*Not a 0xCodez pattern. Surfaced by the Codex claim-refutation cross-check (§11
MISSED) while verifying GAP-3. **Rewritten after the Codex research review
(§11.2 R1) refuted half of it.** The original heading was "self-approvable
arbitrary code execution"; that framing is withdrawn.*

#### What stands

1. `source_code` nodes execute via `exec(src, {"__builtins__": __builtins__,
   "invoke_mcp_action": …})` — **full builtins, in-process, no OS sandbox**
   (`graph_compiler.py:1805-1807`).
2. The only content fence is a substring denylist, `if pattern in src` over
   `_DANGEROUS_PATTERNS` (`:1367-1372`) — trivially defeated by
   `getattr`/`__import__` string construction.

Those two are the **standing STATUS P1 "no OS engine sandbox" Concern**, not a
new finding. What this audit adds is the *commons* consequence: a platform whose
value proposition is running other people's forked graphs cannot rest its
isolation story on a substring match, whoever signed the approval. That makes
the P1 customer-facing rather than internal, and it is the correct thing to
carry forward from GAP-8.

#### What is withdrawn — the approval-authority claim

The original GAP-8 asserted that a merely signed-in user could self-approve
their own code, because `_ext_branch_approve_source_code` applies no
handler-local host-role or author check (`api/branches.py:514-531`). **The
handler observation is true and the conclusion drawn from it is false.** The
gate is upstream, one frame out:

| Link | Evidence | Verified |
|---|---|---|
| Every `extensions` action is scope-checked *before* dispatch | `_extensions_impl` calls `_dispatch_scope_error("extensions", action)` at `api/extensions.py:399`, before the `if action == …` chain | ✅ read in this checkout |
| `_dispatch_scope_error` raises through `require_action_scope` | `api/extensions.py:243-260` | ✅ |
| `approve_source_code` is an **admin** action | `_EXTENSIONS_ADMIN_ACTIONS` at `auth/provider.py:410-418` → `tinyassets.extensions.admin` | ✅ |
| Production founders do **not** hold `admin` | `_AUTHENTICATED_BASE_CAPABILITIES = ("read", "write", "costly", "submit_request", "list")`, with an explicit comment that `admin` "is NOT implicit; it stays RBAC-gated via the token's `permissions` claim" (`auth/workos_provider.py:29-40`) | ✅ |
| A test already asserts exactly this | `tests/test_source_code_approval_action.py:118-124` asserts `oauth_scope == "tinyassets.extensions.admin"` and `effect == "admin"` | ✅ |

So the anonymous *warning string* is a dev/optional-auth artifact — in that mode
scope enforcement is intentionally bypassed — not a production hole. A platform
admin approving another author's code is plausibly by design. **I concede the
refutation in full**; I traced each link above rather than accepting the
reviewer's citation, and the code says what the reviewer said it says. The
original claim's error was structural and worth naming: I read one handler and
concluded from the absence of a check *in that frame* that no check existed,
without walking one frame outward to the dispatcher. §12 Q3 had flagged
"does any production auth mode block it upstream?" as an unanswered severity
input — and the finding was nonetheless written up as though the answer were no.
That is the defect, not the missing grep.

#### Residual — regression coverage, not a new guard

The reviewer's own residual, adopted here as the replacement for the withdrawn
candidate: **prove that every dispatch path to `approve_source_code` reaches the
admin gate, and keep proving it.** The existing test asserts the *mapping*
(action → scope) but nothing asserts the *funnel* (that no route reaches the
handler without passing `_dispatch_scope_error`).

Today the funnel does hold, and I traced it rather than assuming it:
`_BRANCH_ACTIONS` is defined at `api/branches.py:3331` and has exactly one
runtime dispatch consumer, `api/extensions.py:458` — inside `_extensions_impl`,
59 lines *after* the `_dispatch_scope_error` call at `:399`. Its only other
references are the `action_scope_audit` surface (`auth/provider.py:488,536`) and
two parity tests. Every canonical route into `_extensions_impl`
(`universe_server.py:469,474,488,634,676,1435`) therefore passes the gate.

That is a property a newly added route can silently break with nothing going
red — which is the whole argument for the test. Note also that
`packaging/claude-plugin/.../runtime/tinyassets/` carries a full mirror of both
modules; the canonical-tree test plus the existing pre-commit mirror-parity
guardrail (`AGENTS.md` §Testing) is the right division of labor, not a second
test.

- **T1:** not a primitive question, and no longer an authorization question
  either — a **test-coverage** question.
- **Cost:** small. One test that enumerates callers/dispatch tables and asserts
  the gate is upstream of all of them.
- **Not displaced:** the OS sandbox remains the durable fix for the half that
  stands, and this coverage does nothing about it.

#### STATUS state

`STATUS.md` on `origin/main` already carries both corrections, filed after this
artifact's first commit — **no action owed from a folder-back**:

- #1757 filed GAP-8 as a P1 Concern as originally written.
- #1758 downgraded it to *"contradicted: GAP-8 self-approval refuted by Codex
  (extensions.admin scope gates it upstream, provider.py:410); residual =
  regression-cover every dispatch path reaches that gate. OS-sandbox P1
  unchanged"* — and filed the GAP-2 scheduler `owner_actor` defect as a separate
  P2.

The earlier instruction in §10 to "raise the Concern row" is therefore
**discharged**, and re-raising it would duplicate a corrected row.

### Deliberately not proposed

- A `graph_authoring` tool, a `parallel` verb, a `verify` verb, a `memory` verb,
  a `skill` verb, a `knowledge_graph` verb. All are compositions or convenience
  rollups; all fail T1; all grow a budget `PLAN.md:27` says must shrink.
- Un-hiding the legacy fat tools. That inverts the PR-178 canonical-surface
  decision, and hard rule #11's `--assert-handles` canary would go red. The fix
  is routes on the seven handles, not resurrecting the eleven.

---

## 9. OpenSpec change candidates

**This section proposed SIX candidates, not four, and they do not share a
status.** An earlier framing (and the lane report's Q3 summary) said "four
OpenSpec change candidates," which was a miscount that invited a blanket
approval across rows needing different dispositions — flagged by the Codex
research review (§11.2 R6) and corrected here. The design-first row and the
commons-seed row are not runtime changes at all, and one row is withdrawn
outright.

**Eight rows below:** the six reviewed candidates, each with the reviewer's
disposition in its own Status cell; plus the replacement for the withdrawn one;
plus an explicit *no-candidate* row for GAP-9, so its absence reads as a
decision rather than an oversight.

**No row grants implementation authority beyond what its own Status cell says.**

| Candidate | Status after review | Scope (one para) |
|---|---|---|
| `canonical-surface-prompt-reconciliation` | **RESOLVED — PR #1794 (`46ff5c5c`) landed after this artifact's source branch diverged. Do not create a competing change.** | `control_station` now describes the seven canonical handles, explicitly refuses hidden legacy calls, and has instruction-surface drift coverage. This closes GAP-1 Half A; it does not add the missing workflow-create route in Half B. |
| `canonical-surface-graph-authoring` | **ADAPT — creation semantics must be specified before scoping.** Approve the problem statement, not the scope as written. | Make `write_graph target=branch` with an empty `branch_id` create a branch from an ordered `changes_json` patch-op list. **The correction (§11.2 R6): create does *not* inherit patch's pre/post-snapshot and author-gate behavior "for free"** — patch operates on a branch that already exists and already has an owner, so every one of those properties must be *established*, not *inherited*. The change must specify, explicitly: (i) **blank-branch staging** — what object the ops apply to before the branch exists; (ii) **author binding** — the created branch's author bound server-side from the authenticated actor, never from a client field; (iii) **idempotency** — what a retried create does, so a client that times out mid-create does not produce two branches; (iv) **visibility and storage** — created private-by-default, host-resident private data preserved, and public/publish/remix semantics stated rather than assumed from "visibility exists"; (v) **validation** — whether a create may land structurally invalid and be repaired by later patches, or must validate atomically; (vi) **first version** — whether create publishes v1 or leaves the branch unversioned; (vii) **publication** — the explicit act that moves it into the commons. Covers node defs, edges, conditional edges, state fields with reducers, entry point, and `skills`. Explicitly does not un-hide the legacy fat tools and does not change `CANONICAL_HANDLES`. Closes GAP-1 Half B and GAP-6. Requires `--assert-handles` canary + rendered `ui-test` before acceptance. |
| ~~`source-code-approval-authority`~~ | **WITHDRAWN — premise refuted (§11.2 R1).** Not "deferred": the thing it proposed to add already exists. | Withdrawn in full. It proposed requiring a host/owner role in `_ext_branch_approve_source_code`; the `tinyassets.extensions.admin` action scope already supplies exactly that authority one frame upstream (`api/extensions.py:399` → `auth/provider.py:410-418`), and production founders do not hold it (`auth/workos_provider.py:29-40`). Building it would have duplicated an existing authority boundary and, worse, implied that boundary was absent. |
| `source-code-approval-gate-regression-coverage` | **REPLACEMENT for the withdrawn row — small, and the only thing GAP-8 actually owes.** Needs a proposal; needs no design round. | The reviewer's residual. Add regression coverage asserting that **every** dispatch path to `approve_source_code` passes `_dispatch_scope_error` before reaching the handler. The action→scope mapping is already tested (`tests/test_source_code_approval_action.py:118-124`); the *funnel* is not. It holds today — `_BRANCH_ACTIONS` (`api/branches.py:3331`) has exactly one runtime dispatch consumer, `api/extensions.py:458`, which sits 59 lines after the `_dispatch_scope_error` call at `:399` — which is precisely the kind of property a newly added route breaks silently, with nothing going red. Does not touch the OS-sandbox residual, which stays with the standing P1. |
| `canonical-surface-branch-scheduling` | **ADAPT — server-bind ownership first; that part is a prerequisite, not a later hardening pass.** | Add `write_graph target=schedule` (cron expr + `branch_id` + pause/unpause) and `read_graph target=schedules` over the shipped `tinyassets/scheduler.py` registry. **Blocking prerequisite (§11.2 R3, now STATUS P2 via #1758):** bind `owner_actor` to `_current_actor()` server-side, scope list/pause/remove to the authenticated actor or an explicit admin, and validate target-branch authority — the legacy actions today accept a client-supplied owner string, default it to `"anonymous"`, and check `unregister_schedule` authorization *against that same client-chosen value* (`api/runtime_ops.py:350-423`). Exposing the current backend canonically would promote a legacy-surface defect onto the user surface. **Separable, and not required for slice 1:** the existing min-interval and max-active bounds are reusable as-is; a *new* consecutive-failure counter with auto-pause is operational hygiene to justify on its own, not a gate on proving the primitive. Depends on `canonical-surface-graph-authoring` (scheduling a branch you cannot author is inert). Closes GAP-2. |
| `graph-runtime-fan-out-over-state` | **DESIGN-ONLY — explicitly no implementation authority.** The artifact leaves its own irreducibility comparison unfinished, so it cannot grant any. | Price whether `enqueue_branch_run` + `await_run_spec` already satisfies runtime-cardinality fan-out before committing to a `NodeDefinition.fan_out_over` field over LangGraph's `Send`. Note the asymmetry that makes this non-obvious: `enqueue_branch_run` is *paced asynchronous dispatch* returning a branch-task identity, **not** a joined child-run result, so it is not equivalent to an in-graph dynamic map/barrier without a join story. If the async path suffices, the change closes as `no new primitive` and documents the composition. If not, it specifies the field with a hard width cap, `concurrency_budget` participation, recursion/enqueue-budget interaction, and differential tests against the static-edge path per the hot-path-rewrite rule. Closes GAP-3. Highest technical risk on this list. |
| `commons-reference-graph-patterns` | **LATER CONTENT EXPERIMENT — not an OpenSpec runtime change, and never privileged platform policy.** | Publish reference branches as public, forkable, **ordinary attributed commons content**: diamond audit (split → parallel → reduce → synthesize), adversarial verifier gate, loop-until-dry discovery, and extract-resolve-assemble-query memory over `read_page`. **Correction (§11.2 R6): they get no privileged "canonical" status.** Preselected graphs blessed by the platform are exactly the prebuilt complexity the minimal-primitives rule exists to prevent, and blessing them pre-empts the commons ranking (`quality_leaderboard`, `recommended_parent_for_fork`) that is supposed to decide which patterns win. Seed them, attribute them, let them rank like anyone else's. Depends on `canonical-surface-graph-authoring`; **it does not depend on GAP-9** — *corrected as a consequence of §11.3 R7*, since all four patterns are expressible from `read_page`, opaque nodes, and declared effects. A reference graph that wants a verb the platform did not pre-author (CI, issues, arbitrary APIs, the web) does depend on GAP-9, and until GAP-9 is answered such a graph would have to ship as admin-approved `source_code` — which is a reason not to seed one, not a reason to widen the boundary. Closes GAP-4 the principle-correct way — a composition pattern, not a verb. |
| *(GAP-9 — node tool access)* | **NO CANDIDATE, BY DESIGN — and when one is written it is a SECURITY change, not a plumbing one (§11.3 R8).** Surfaced *by* the review, so it has never been through T1/T2/T3 with an opposite-provider verdict on the result. Its review round must be a **security review**; a scoping review does not discharge it. | Deliberately not written up as a candidate. §8 GAP-9 states two shapes — (a) wire the existing invoker into the prompt path, (b) widen `_NODE_MCP_ACTION_ALIASES` — and **both move a security boundary.** (a) adds no alias, but it relocates the entire alias set, including side-effecting env-gated `dispatch.enqueue` (`graph_compiler.py:1397-1403`), from *admin-approved, hash-bound `source_code`* (`:1790` → `:1793`; approval behind `tinyassets.extensions.admin`, §11.2 R1) to *prompt-template text that compiles with no approval gate at all* (`:2627-2633`) and whose caller is a model reading run state. Any candidate must therefore state what replaces approval + hash-binding as the gate, and must be scoped against the composition path that already exists (§8 GAP-9 "what already exists") so it does not re-propose reach the platform already has. It may also not be a defect: the in-node wiki-write refusal at `graph_compiler.py:1380-1386` reads as deliberate scoping — and its "goes through an effect" referent is shipped (`effectors/wiki_write_back.py:24`) — so if the read-mostly boundary is likewise deliberate, the honest output is documentation rather than widening. **Needs its own review round before any candidate is named.** |

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
yet — build is review-blocked and STATUS is at its 60-line budget).

**Review status: the skill §8 Codex research review is COMPLETE and returned
`adapt`** (2026-07-25, against commit `1d8c9fc5`). Its findings are folded
throughout this artifact and logged as R1–R6 in §11. Build authority now flows
**per §9 Status cell only** — three rows are fold-in / withdrawn / design-only,
and none of them is a licence to implement the others as originally scoped.

**Discharged — do not redo:**

1. ~~GAP-8 needs a `STATUS.md` Concern row.~~ **Filed and then corrected on
   `origin/main` without this branch: #1757 filed it as P1 as originally
   written; #1758 downgraded it to `contradicted:` after the Codex refutation
   and separately filed the GAP-2 scheduler `owner_actor` defect as a P2.** Both
   rows are live. Re-raising either would duplicate a corrected row. The §12 Q3
   severity inputs are answered (§11.2 R1) — the answer is that the upstream
   production gate exists.

**Still owed:**

1. ~~**GAP-1 Half A (`control_station` reconciliation) is still owed.**~~
   **Discharged by PR #1794 (`46ff5c5c`).** The current prompt names the seven
   canonical handles and carries drift coverage. Do not open a competing lane;
   GAP-1 Half B (workflow creation) remains separate.
2. **GAP-9 (node tool access) needs its own review round — a SECURITY review**
   (§11.3 R8) — before any candidate is named for it. It arrived from the
   review, so it has never been through T1/T2/T3 with a verdict on the result;
   and both of its candidate shapes move a security boundary, so a scoping
   review does not discharge it. Scope any future candidate against the
   opaque-node/effect composition path that already exists (§8 GAP-9) so it does
   not re-propose reach the platform already has.

**Overlap check before any lane is materialized:**

- `openspec/changes/repair-first-contact-onboarding/` — **same defect, different
  entry point** (rendered chat found stale commands, the missing starter branch,
  and an unknowable branch-ID prerequisite). GAP-1 Half A is very likely that
  lane's root cause. Do not open a competing lane; fold in or add a `Depends`
  edge.
- The standing "no OS engine sandbox" P1 Concern and the `#1485` fail-closed
  seam — **checked; GAP-8 is not new.** Its surviving half *is* the OS-sandbox
  P1. Its only genuinely new residual is regression coverage of the admin-gate
  funnel (§9, `source-code-approval-gate-regression-coverage`); the "missing
  approval role" residual claimed in the first draft does not exist (§11.2 R1).
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
| Depends | this artifact; **Codex research review returned `adapt` 2026-07-25 — satisfied (§11.2 R1–R6)**; overlap resolution with `repair-first-contact-onboarding`; **plus the §9 `adapt` conditions: creation semantics (i)–(vii) specified before scoping** |
| Write-set (STATUS Files cell) | `openspec/changes/canonical-surface-graph-authoring/`, `tinyassets/universe_server.py`, `tinyassets/api/branches.py`, `tests/` |
| Read deps to recheck | `scripts/mcp_public_canary.py:72`, `openspec/specs/live-mcp-connector-surface/spec.md`, `openspec/specs/graph-execution-substrate/spec.md` |
| PLAN modules to review | `PLAN.md:27` (minimal primitives), the five-permissioned-handles module |
| Memory refs | `enabling-primitives-not-prebuilt-complexity`, `universe-intelligence-relay-architecture`, `universe-engine-sandbox-p0`, `no-users-build-correct-shape`, `stale-backlog-rows-misdirect` |
| Related implications | `docs/audits/2026-04-28-commons-first-tool-surface-audit.md` (T1/T2/T3), `docs/audits/2026-04-26-user-capability-axis-implications.md`, `docs/audits/2026-07-21-zapier-automation-platform-implications.md` |
| First slice | The OpenSpec proposal only — no runtime code |
| Gates: pre-commit | `pytest` (targeted) + `ruff check` |
| Gates: pre-push | ~~Codex review `approve`/`adapt`~~ **satisfied** — verdict `adapt`, folded here, logged §11.2 R1–R6. Remaining pre-push gate: the §9 creation-semantics spec exists and has been read by the reviewing provider |
| Gates: pre-acceptance | `mcp_public_canary.py --assert-handles` (hard rule #11 — the handle set must be **unchanged**) **and** a rendered chatbot `ui-test` proving a user can author and run a graph end-to-end |
| Fold-back | Draft PR while review-blocked; ready PR only after gates; retire the row on land; sync delta specs + archive in the same lane |

---

## 11. Cross-provider verification of the code claims

**Two rounds ran, and they are different things.** Round 1 (§11.1) was a
*fact-check of code claims*, dispatched by the author while drafting. Round 2
(§11.2) is the **skill §8 opposite-provider research review** — the gate that
governs build authority. Both are logged; refuted claims are preserved in both.

### 11.1 Round 1 — code-claim fact-check (refute-by-default)

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

Promoted to **GAP-8** (§8) — **and the "approve code without a host-role check"
half of it was subsequently refuted by round 2 (§11.2 R1).** Quoted verbatim
above because that is the record; do not read it as current. Note what happened:
I recorded this as "independently verified," and what I actually verified was
the handler's *contents*, not the *reachability* of the handler. The quote is
accurate about `api/branches.py:514-520` and wrong about the system. A
cross-family reviewer's finding is a lead to run down, not a verdict to inherit
— the same standing rule this project applies to its own findings.

**Method note for future dispatches:** framing the ask as *refute-by-default*
with a hard output contract is what produced this. A "please review" framing
would very likely have returned agreement with all seven claims, three of which
were wrong. Consistent with the `codex-review-script-assumes-pr-review` and
`silent-failure-dispatch-and-tests` memory patterns.

> **Round 1 was a fact-check of code claims only.** It did **not** satisfy the
> skill §8 research review. That review has since been run — see below.

### 11.2 Round 2 — the skill §8 Codex research review (verdict: `adapt`)

**Run 2026-07-25 against commit `1d8c9fc5`; the 932-line artifact was read in
full.** This is the opposite-provider review the `external-research-implications`
skill §8 requires for a Claude-originated finding, and it re-checked the primary
sources *and* the TinyAssets code, not just the internal consistency of the
draft. **Verdict: `adapt`** — the surface, creation, scheduling, and fan-out
observations are directionally sound; GAP-8 was misdiagnosed; the candidate set
needs consolidated statuses; and a ranked gap was missing.

Same preservation rule as round 1: **refuted claims are kept here, not deleted.**

| # | Original claim | Verdict | What replaced it |
|---|---|---|---|
| **R1** | GAP-8: a merely signed-in user can self-approve their own `source_code`, because `_ext_branch_approve_source_code` applies no host-role and no author check (`api/branches.py:514-531`) | **REFUTED — conceded in full** | The gate is one frame upstream, not in the handler: `_extensions_impl` → `_dispatch_scope_error("extensions", action)` (`api/extensions.py:399`) → `_EXTENSIONS_ADMIN_ACTIONS` → `tinyassets.extensions.admin` (`auth/provider.py:410-418`); production founders hold `read`/`write`/`costly`/`submit_request`/`list` but **not** `admin` (`auth/workos_provider.py:29-40`), and `tests/test_source_code_approval_action.py:118-124` already asserts it. Each link re-verified in this checkout before conceding. The anonymous *warning string* is a dev/optional-auth artifact. **Rewrote §8 GAP-8; withdrew the `source-code-approval-authority` candidate; replaced it with the reviewer's residual (funnel regression coverage).** `STATUS.md` had already been corrected on `origin/main` by #1758. |
| **R2** | *(omission)* The ranked gap list runs GAP-1 → GAP-2 → GAP-3 → GAP-4, and the substrate is "at or ahead on 14 of 19" | **MISSED FINDING — accepted** | `NodeDefinition.tools_allowed` exists (`branches.py:307`) but `_build_node_mcp_invoker` has one call site, inside approved `source_code` (`graph_compiler.py:1793`) — prompt-template nodes are text-in/text-out with no tool access, and even the `source_code` alias set is selected goals/gates reads, wiki reads, and paced enqueue (`:1375-1404`). Against the Anthropic primary's *augmented LLM* baseline that is below parity. Verified independently. **Added as GAP-9, ranked 2 (ahead of scheduling and fan-out); added §6 pattern #20; corrected §6 #10 Discovery, which had conflated daemon-internal task production with user-authored node tool access; the parity claim drops from 14-of-19 to 13-of-20.** |
| **R3** | GAP-2: expose scheduling over the shipped registry, and "do not ship the timer without the bound" (min interval, max active, auto-pause on N failures) | **ADAPT — accepted** | The candidate missed a live authorization defect: `_action_schedule_branch` takes a **client-supplied** `owner_actor`, defaults it to `"anonymous"`, and never binds `_current_actor()` or checks branch authority (`api/runtime_ops.py:350-392`); `_action_unschedule_branch` then checks authorization *against that same client-chosen string* (`:398-411`); `list_schedules` accepts a blank owner filter (`:414-423`). Verified. **Server-binding is now a stated prerequisite to exposure.** Separately: the bound was over-bundled — min-interval/max-active already exist and are reusable, while a *new* consecutive-failure/auto-pause policy is separable and needs its own justification. Now also STATUS P2 via #1758. |
| **R4** | "Stop pitching the runtime, pitch the ledger" (§1, §7.3) | **ADAPT — accepted** | The first half is supported (orchestration patterns are commodity); the second is not established by this evidence — none of the sampled threads evaluates provenance markets, attribution, remix economics, or paid work, and the ledger is not yet coherently reachable from the canonical surface. **Reframed as a hypothesis to validate with target users, not a conclusion**, and noted that pitching only the ledger before authoring, node tool access, security, and discoverability would overrun the evidence. |
| **R5** | §2: 0xCodez supplies "the canonical vocabulary the target customer now thinks in," and the market is standardizing on it | **OVERSTATED — accepted** | The mirror showed only tens to low hundreds of views at fetch time, and the authoritative ideas predate the wording (Anthropic's *Building effective agents* and *How we built our multi-agent research system*). No official primary was found for the mirror's specific `parallel()` / `pipeline()` / `/workflows` / `ultracode` product claims — curator evidence, not verified product facts. **Downgraded to "one fresh demand-language signal" with the calibration stated inline in §2.** Scope note: §5's separate claim that *"loop engineering"* is a converged term rests on independent sourcing (Steinberger, Cherny, Osmani via the hyper.ai mirror), not on this account, and is unaffected. The "curator, not builder" classification and §3.1's five-move decomposition both stand. |
| **R6** | §9 presents "four OpenSpec change candidates," all `pending` | **AMBIGUOUS — accepted** | There were six rows sharing one status, which invited blanket approval across rows needing different dispositions. **Rewritten with per-row Status cells:** fold-in / adapt / withdrawn / replacement / adapt / design-only / later-content-experiment, plus an explicit no-candidate row for GAP-9. Two substantive scope corrections came with it: branch *create* does not inherit patch's snapshot and author-gate behavior for free (seven creation semantics now enumerated), and the four reference graphs must be ordinary attributed commons content, never privileged platform policy. |

**What this round cost, and why it was worth it.** Two of the six findings (R1,
R2) would each have produced wasted or misdirected build work: R1 an OpenSpec
change to add an authority boundary that already exists, and R2 a roadmap that
ships a scheduler and a fan-out primitive for nodes that cannot call anything.
R3 would have promoted a live authorization defect onto the canonical user
surface. **The pattern common to R1 and R3 is the same one:** reading a single
handler and drawing a conclusion about the system's authorization posture
without walking one frame outward — in R1 that produced a false positive (the
gate was upstream), in R3 a false negative (the gate was upstream but coarse).
The generalizable rule: *an authorization claim about a handler is not verified
until the dispatcher above it has been read.*

### 11.3 Round 3 — Codex re-review of the fold (verdict: `adapt`, one residual)

**Run 2026-07-25 against commit `cb248b8c`** — a focused read-only re-read of the
five fold areas. Four were confirmed clean: GAP-8 conceded and withdrawn
correctly with the OS-sandbox P1 intact; scheduler `owner_actor` correctly folded
as an exposure prerequisite with the failure-policy split preserved; §9's
per-row statuses correctly differentiated (`withdrawn` judged stronger and
clearer than the prior `reject as written`); and the ledger claim fairly
reframed as a target-user hypothesis. **The verdict was `adapt` on a single
residual, both halves of it inside GAP-9** — the section added *by* the previous
round, which is where the previous round had the least review exposure.

Same preservation rule: **the overreaching claims are kept here, not deleted.**

| # | Claim in the fold at `cb248b8c` | Verdict | What replaced it |
|---|---|---|---|
| **R7** | GAP-9: "The only way to make any of [read CI → find the diff → draft a fix → open a PR] happen is to write a `source_code` node and get an admin to approve it" (§8), restated in §1, §4, §6 #20, §7.2 #5, §7.3 | **TOO ABSOLUTE — accepted** | The compiler supports **platform-trusted opaque domain nodes**: `read_repo_files` (`effectors/github_read.py:63-64,286-296`), `search_repo_files` (`github_search.py:72-73,315-323`), `validate_patch` (`validate_patch.py:43-44,198-206`), registered at import (`effectors/__init__.py:57-60`) and resolved by `(domain_id, node_id)` at `graph_compiler.py:2634-2646` → `_build_opaque_node` (`:1875-1930`), which bypasses `_validate_source_code` precisely because the **platform owns the body** (`:1883-1885`). The write side is `effects` on a node, accepted in patch specs (`api/branches.py:1672-1683,1733`) and run at completion (`runs.py:2658-2669`) through gated sinks (`github_pr.py:108,1139-1320`). So repo→diff→PR **composes with no `source_code`**. **The gap was re-stated as agent-node *tool parity*: the model choosing a call mid-reasoning, versus the author pre-wiring a platform verb.** Verified independently, not accepted on the reviewer's word. Two limits recorded while verifying, neither promoted to a gap: the verb set is closed-world (no CI, issues, arbitrary API, web), and resolution is exact-match on a `domain_id` (`"tinyassets"`) that `BranchDefinition` does not default to (`"workflow"`, `branches.py:858`) and that **no patch op can set** (`_apply_patch_op`, `api/branches.py:2332-2560`) — so today the path is reachable only at create time, i.e. downstream of GAP-1 Half B. |
| **R8** | GAP-9 shape (a) — wire the existing invoker into the prompt path — is "cheap; changes no security boundary" | **REFUTED — conceded in full** | It adds no alias to the registry, and that is the *only* narrow thing about it. It changes **capability reachability**, which is the boundary. The invoker is built only after `_validate_source_code(node)` passes (`graph_compiler.py:1790` → `:1793`) — `approved=True` **plus** `approved_source_hash == sha256(effective source)` (`:1318-1365`), with approval itself behind `tinyassets.extensions.admin` (§11.2 R1). Prompt-template nodes compile with **no approval gate at all** (`:2627-2633`) from ordinary patchable text whose caller is a model reading run state. Shape (a) therefore moves the whole alias set — **including side-effecting, env-gated `dispatch.enqueue`** (`:1397-1403`) — from admin-approved hash-bound code to unapproved, prompt-injection-reachable text. **§8 now states both shapes as security-boundary changes and §9's no-candidate row requires a security review, not a scoping one.** |

**Independent re-check of the new claims (2026-07-25).** R7's replacement text
asserts three things the *reviewer did not supply* — the composition path as a
whole, the `domain_id` reachability precondition, and the approval-gate
asymmetry behind R8. Rather than ship them on my own reading, they went back to
Codex (`codex exec`, read-only, **refute-by-default**, "default to refuted if
uncertain", hard three-line output contract, lane-local out file).
**Result: 3 of 3 confirmed** — the opaque-node/effect path
(`graph_compiler.py:2634-2646`; `api/branches.py:1672-1733`;
`effectors/__init__.py:91-120`), the exact-tuple domain lookup with no patch-op
domain setter (`domain_registry.py:68-73`; `branches.py:858`;
`api/branches.py:2332-2555`, and it independently flagged the same
`"workflow"`-docstring/`"tinyassets"`-constant contradiction), and the
approval-gate asymmetry (`:1318-1365`, `:1790-1797` vs `:2627-2633`, with
`dispatch.enqueue` at `:1375-1404`). No claim in R7/R8 rests on single-provider
reading.

**Why this residual was the right one to catch.** R8 is the more dangerous of
the two: "changes no security boundary" is exactly the sentence a future lane
would quote to skip a review, and it sat inside a section whose own status is
*no candidate, needs a review round* — i.e. the safeguard was already there and
the prose was quietly undercutting it. R7 is the same failure mode as §11.2 R1
in a new costume: **a conclusion drawn from one execution path without checking
whether a sibling path exists.** In R1 the missed frame was one call *up* (the
dispatcher); here it was one branch *sideways* in the same dispatch function —
`_select_node_adapter` checks `source_code`, then `prompt_template`, then the
domain registry, and the audit had read the first two. The generalizable rule to
add to R1's: *before claiming a capability is absent, enumerate every branch of
the dispatcher that could supply it, not just the one you were reading.*

---

## 12. Open questions and verification gaps

1. **Was the narrow `write_graph` target set a deliberate product decision or an
   incomplete PR-178 fold?** This determines whether GAP-1 Half B is a bug or a
   direction change. PR #1794 has since reconciled `control_station` with the
   narrow canonical target set and now states that workflow creation is not
   exposed. That removes the stale-prompt evidence for “incomplete” but does not
   decide whether creation should exist. **Host decision remains.**
2. **Does GAP-1 duplicate `repair-first-contact-onboarding`?** Must be answered
   before any lane opens. Strong suspicion: the "stale commands" symptom in that
   row *is* the `control_station` drift.
3. ~~**GAP-8 severity inputs, unanswered.**~~ **ANSWERED — §11.2 R1.** (a) A
   signed-in non-author cannot reach the handler at all without the
   `tinyassets.extensions.admin` scope, which production founders do not hold;
   the branch-visibility sub-question is moot for the severity call, though it
   remains open for an admin acting across authors (plausibly by design).
   (b) **Yes** — `_dispatch_scope_error` at `api/extensions.py:399` blocks it
   upstream in every auth-enabled mode. (c) **Yes** — the surviving half *is*
   the standing OS-sandbox P1. The severity was filed (#1757) and then corrected
   to `contradicted:` (#1758). *Meta-lesson worth keeping: this question was
   written down as unanswered, and the finding was published anyway as though
   the answer were "no." An unanswered severity input should block the claim,
   not just annotate it.*
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
   this: if users run each other's forked graphs, full-builtins in-process
   `exec` behind a substring denylist is a commons-wide risk, not an
   engine-local one — **and the admin approval gate does not resolve it**, since
   an admin approving a graph is not the same as that graph being safe to run on
   someone else's host. Not analyzed here. *(Rephrased per §11.2 R1; the original
   said "self-approvable," which was the withdrawn claim.)*
7. **Unreached primary sources:** the two Anthropic PDFs (loop engineering,
   graph engineering) were read only through secondary excerpts; both mirror
   URLs 404'd. If a reviewer can reach them, re-verify §3.1 and §3.3 against the
   originals. **Round 2 did not reach them either** — the reviewer corroborated
   §3.1 through the same hyper.ai mirror, so this gap is unchanged.
8. **Is GAP-9's narrowness deliberate?** *(New — §11.2 R2; sharpened §11.3 R7.)*
   The in-node wiki-write refusal at `graph_compiler.py:1380-1386` is explicitly
   commented as a design choice ("a node that needs to publish goes through an
   effect") — and that effect is shipped (`effectors/wiki_write_back.py:24`), so
   the comment describes a live routing decision, not an intention. The whole
   opaque-node/effect layer points the same way: the platform's answer to "a node
   needs to do something in the world" has consistently been *a host-authored
   verb the author wires*, never *a tool the model calls*. If that is a recorded
   decision, GAP-9 is a product-positioning finding and the honest response is
   documenting the boundary; if it is an omission, it is a capability gap.
   **Answer before naming any candidate for it.** Nothing in the roadmap should
   assume the widening is approved — and per §11.3 R8 the widening is a security
   decision either way.
9. **Would this audience actually pay for the ledger?** *(New — §11.2 R4.)* §7.3's
   reframe makes this the load-bearing commercial question, and **no evidence in
   this study answers it** — none of the sampled threads evaluates provenance,
   attribution, remix economics, or paid work. Answerable only by talking to
   target users, not by more code reading or more source mirrors. Until it is
   answered, "differentiate on the commons" is a direction to test, not a
   strategy to build a roadmap around.
10. **Is the `"tinyassets"` vs `"workflow"` domain mismatch a live defect?**
    *(New — §11.3 R7.)* The three opaque effectors register under
    `DOMAIN_ID = "tinyassets"` while their own docstrings say "in the `workflow`
    domain" and `BranchDefinition.domain_id` defaults to `"workflow"`
    (`branches.py:858`); no patch op sets it. Either the constant is wrong, or
    the docstrings and default are — and the difference decides whether any
    patch-authored branch can reach `read_repo_files` at all. Not analyzed here
    beyond establishing the mismatch; it belongs to whoever scopes GAP-1 Half B,
    since create is where `domain_id` is set.

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
