# ASI-Evolve Architecture Implications For Workflow

Freshness stamp: 2026-05-02. Local Workflow snapshot was inspected from
`C:\Users\Jonathan\Projects\Workflow` on branch `cursor/claim-check-session-d`
with an already-dirty worktree. ASI-Evolve was cloned read-only from
`https://github.com/GAIR-NLP/ASI-Evolve` at commit
`fb8a67e552e25cf8b7144d4e7f1a17f665055130` (2026-04-17). This is a design
study, not an accepted PLAN.md change.

## Sources Used

- ASI-Evolve paper: https://arxiv.org/abs/2603.29640
- ASI-Evolve repo: https://github.com/GAIR-NLP/ASI-Evolve
- Google DeepMind AlphaEvolve overview:
  https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
- OpenEvolve repo:
  https://github.com/algorithmicsuperintelligence/openevolve
- The AI Scientist paper:
  https://arxiv.org/abs/2408.06292
- The AI Scientist repo:
  https://github.com/SakanaAI/AI-Scientist
- Agent Laboratory paper:
  https://arxiv.org/abs/2501.04227
- Workflow local docs: `PLAN.md`, `STATUS.md`,
  `docs/design-notes/2026-04-18-full-platform-architecture.md`
- Workflow local code: `workflow/`, `fantasy_daemon/`, `pyproject.toml`

## Executive Judgment

ASI-Evolve validates a pattern Workflow already wants: a durable
learn/design/experiment/analyze loop with explicit prior knowledge, explicit
candidate lineage, locked evaluators, and analyzer-written lessons. The
important conclusion is not "import ASI-Evolve". Its repo is small,
single-operator, file-local, and research-pipeline oriented. Workflow is
multiplayer, MCP-first, uptime-bound, privacy-aware, and distributed across
hosts. Direct grafting would duplicate our runtime and weaken our invariants.

The correct move is to absorb ASI-Evolve's invariants into Workflow's native
primitives:

1. Treat `Evaluator` as the first-class truth anchor.
2. Treat optimization as a run type, not a separate daemon stack.
3. Split memory into reusable cognition and per-experiment lineage.
4. Lock mutation scope and harness scope separately.
5. Store analyzer lessons as typed artifacts that future runs can sample.
6. Prefer quality-diversity search over "one best workflow" convergence.
7. Make distributed evaluation and budget accounting native from the start.

Workflow's PLAN already anticipates this in §32 node autoresearch and §33
evaluation layers. ASI-Evolve mainly sharpens the implementation shape.

## How ASI-Evolve Works

ASI-Evolve's core loop:

```text
cognition/prior knowledge
    -> Researcher proposes a candidate
    -> Engineer writes/runs candidate against evaluator
    -> Analyzer distills reusable lesson
    -> Database stores node, score, lineage, analysis
    -> Sampler chooses future parents
```

The paper frames this as learn -> design -> experiment -> analyze. The repo
implements that with:

- `main.py`: CLI bootstrapping and run arguments.
- `pipeline/main.py`: orchestration, state resume, sequential/threaded runs.
- `pipeline/researcher/researcher.py`: candidate generation by search/replace
  diffs or full rewrite.
- `pipeline/engineer/engineer.py`: materializes candidate code, runs a bash
  evaluator, parses `results.json`, optionally applies an LLM judge.
- `pipeline/analyzer/analyzer.py`: turns result data into a natural-language
  lesson.
- `database/`: persistent node store, FAISS similarity, samplers.
- `cognition/`: persistent prior-knowledge store with embeddings.
- `experiments/`: self-contained problem directories with baseline, evaluator,
  prompts, and cognition seeding.
- `skills/evolve/`: a single-agent abstraction of the same loop. This is more
  operationally mature than the repo pipeline because it forces preflight,
  writable scope, timeout, evaluator confirmation, and run spec persistence.

The ASI paper reports results across architecture search, data curation, and
RL algorithm design. The most transferable idea is not any specific model
architecture; it is the control loop and the separation of candidate mutation
from evaluator truth.

## Workflow System Map

Workflow's thesis is broader than ASI-Evolve: a global goals engine where many
branches pursue shared real-world outcomes. The current codebase already
contains most of the pieces needed for a safer ASI-style platform:

- `workflow/api/`: MCP control surfaces.
- `workflow/runs.py`: durable branch run orchestration.
- `workflow/graph_compiler.py`: materializes branch definitions into LangGraph.
- `workflow/branches.py`: typed branch/node/edge definitions.
- `workflow/evaluation/`: deterministic, process, and editorial evaluation.
- `workflow/retrieval/`, `workflow/memory/`, `workflow/knowledge/`,
  `workflow/api/wiki.py`: evidence and memory substrate.
- `workflow/storage/`, `workflow/catalog/`, `workflow/daemon_server.py`:
  durable state and catalog operations.
- `workflow/host_pool/`, `workflow/branch_tasks.py`, `workflow/dispatcher.py`:
  distributed work claiming and scheduling.
- `workflow/providers/`: model/provider routing and failure semantics.
- `workflow/payments/`, `workflow/gates/`, `workflow/outcomes/`: paid market
  and real-world outcome evidence.
- `fantasy_daemon/`: legacy/reference domain that exercises the engine.

The key gap is not absence of primitives. The gap is a unified optimization
run contract that binds them together.

## Module-By-Module: Workflow

| Module | Current role | ASI-Evolve implication |
|---|---|---|
| `workflow/api/universe.py` | Broad MCP action dispatcher for universes, requests, daemon lifecycle, uploads, bids, and active state. | Should expose one coarse "optimize node/branch" entry point eventually, not many low-level ASI-style knobs. Chat surface remains control station. |
| `workflow/api/runs.py` | Run execution, run snapshots, stream/wait/cancel/resume, routing evidence. | Best home for user-visible optimization run lifecycle. `optimization_run` should probably be a specialized run mode, not a separate pipeline. |
| `workflow/api/evaluation.py` | Judge runs, compare runs, suggest edits, node versions, rollback. | Closest current surface to ASI's evaluator. Needs a normalized `EvaluatorResult` shape before optimization depends on it. |
| `workflow/api/branches.py` | Branch authoring and node CRUD. | Mutation scope should attach to branch/node definitions here: editable field paths, allowed operations, locked harness refs. |
| `workflow/api/market.py` | Goals, gates, escrow, provenance, outcomes. | Outcome gates can become long-horizon evaluators. This is Workflow's advantage over ASI: real-world effect, not just local benchmark score. |
| `workflow/api/wiki.py` | Project/user wiki, search, bug filing, promotion. | Should act as part of the cognition base, but only for reusable external/domain insight. Per-run lessons belong in optimization lineage, not wiki by default. |
| `workflow/api/runtime_ops.py` | Memory, dry-inspect, messaging, schedules/subscriptions. | Dry-inspect can become preflight for candidate mutation. Scheduling can run overnight optimization jobs. |
| `workflow/api/status.py` | Runtime status and policy evidence. | Must report effective evaluator/provider/host availability for any optimization run. No phantom capacity. |
| `workflow/universe_server.py` | MCP server shell mounting extracted APIs. | Should stay a routing shell. Do not rebuild ASI's pipeline here. |
| `workflow/mcp_server.py` | Older stdio file-interface MCP surface. | Avoid adding new optimization behavior here except compatibility routing. Canonical adapter should own it. |
| `workflow/runs.py` | SQLite-backed run/event/judgment/lineage execution engine. | ASI's experiment database maps here most directly. Add candidate records, parent ids, score vectors, and analyzer lessons either here or in a sibling runtime module. |
| `workflow/graph_compiler.py` | BranchDefinition -> LangGraph compiler, prompt/source/opaque nodes, timeouts, retries, child branch invocation. | This is Workflow's richer candidate execution engine. ASI evolves code strings; Workflow can evolve node concepts, prompts, graph topology, and evaluator chains. |
| `workflow/branches.py` | Branch/node/edge/state models and validation. | Add or reference optimization metadata: `optimization_spec_ref`, `editable_surface`, `test_harness_ref`, metric direction, merge policy. PLAN §32 already names this. |
| `workflow/branch_versions.py` | Branch versioning and rollback. | Needed for merge-back: every accepted candidate should become normal versioned branch/node history. |
| `workflow/branch_tasks.py` | Durable queue with claim/cancel/recover. | ASI's thread pool should become distributed BranchTask/host-pool claiming. |
| `workflow/dispatcher.py` | Scores and selects pending BranchTasks. | Can schedule optimization candidates by expected value, budget, and host capacity. Avoid hardcoded "best score only" scheduling. |
| `workflow/scheduler.py` | Cron/event branch invocation. | Useful for nightly or budgeted optimization runs; must emit resumable artifacts. |
| `workflow/daemon_server.py` | Multiplayer SQLite substrate: authors, branches, snapshots, requests, votes, runtime instances. | Contains many tables ASI lacks. Optimization should reuse authorship/provenance/snapshot concepts instead of inventing parallel identity. |
| `workflow/storage/__init__.py` | Data-dir/wikidir/db path policy, utilization, env probes. | Optimization will create many artifacts; storage pressure and caps must be designed in before large candidate runs. |
| `workflow/catalog/backend.py` | Git/SQLite catalog backend protocol. | Accepted candidates should write through catalog/version backend; rejected candidates stay in run lineage unless promoted. |
| `workflow/checkpointing/sqlite_saver.py` | LangGraph checkpointing with WAL and retention. | Resume/replay is a must for long optimization. ASI has simple state resume; Workflow should provide stronger restart semantics. |
| `workflow/runtime_singletons.py` | Non-serializable runtime singleton management. | Any optimizer must respect singleton rules, especially LanceDB and provider routers. |
| `workflow/evaluation/structural.py` | Cheap deterministic checks. | First stage of evaluator chains. ASI's `eval_script` is too monolithic; Workflow should support cheap filter -> expensive judge -> human/backstop. |
| `workflow/evaluation/process.py` | Trace/process evaluation. | Maps to ASI analyzer feedback and OpenEvolve artifact side-channel. Make trace warnings first-class feedback to next candidate. |
| `workflow/evaluation/editorial.py` | Natural-language critique from another model. | Good expensive evaluator stage, but not sufficient alone. Needs structured output and calibration against trusted examples. |
| `workflow/retrieval/router.py` | Routes evidence across KG/vector/hierarchical summaries/scopes. | Better cognition router than ASI's simple FAISS store. Use it to seed candidate design, but keep scope/privacy gates strict. |
| `workflow/retrieval/vector_store.py` | LanceDB singleton vector storage. | Could back candidate similarity/dedup, but watch storage pressure. ASI uses FAISS per experiment; Workflow should centralize. |
| `workflow/knowledge/knowledge_graph.py` | SQLite + igraph knowledge graph. | Stronger than ASI cognition for causal/lineage insights if analyzer lessons are typed. |
| `workflow/memory/manager.py` | Three-tier memory interface. | Split run-local lessons from durable project/domain memory. Do not let failed experiment chatter pollute global memory. |
| `workflow/memory/tools.py` | Agent-controlled memory tools. | Candidate designers can query memory, but writes should go through analyzer/gate policy. |
| `workflow/learning/*` | Criteria, style, craft-card learning. | Similar to ASI analyzer lessons. These should be generalized into typed reusable lessons per domain. |
| `workflow/planning/*` | HTN and domain expansion. | Optimization can evolve plans/topologies, not only code. Needs evaluator lock to prevent plan gaming. |
| `workflow/constraints/*` | ASP/symbolic constraints. | Good for hard evaluator constraints and mutation guards. Generated candidates should fail loudly on constraint substrate absence. |
| `workflow/providers/router.py` | Fallback chains, quota, role routing. | ASI assumes one OpenAI-compatible endpoint. Workflow should route researcher/engineer/analyzer/evaluator roles independently and expose effective chain evidence. |
| `workflow/host_pool/*` | Supabase host pool client and host heartbeat/registration. | Turns ASI's local workers into market/host-distributed candidates. This is one of Workflow's main differentiators. |
| `workflow/payments/*`, `workflow/bid/*` | Paid request, escrow, settlement mechanics. | Optimization can be paid work: users buy 100/1000 candidate evaluations; hosts bid on execution. Settlement evaluator must be separate from candidate generator. |
| `workflow/gates/*`, `workflow/outcomes/*` | Outcome ladder and evidence. | ASI's numeric score should be only one gate. Workflow can optimize for real-world outcomes and verified badges. |
| `workflow/desktop/*` | Tray/launcher/dashboard. | Tier-2 host UX should show optimization queue, resource cost, and contribution outcomes, not just daemon status. |
| `workflow/discovery.py`, `workflow/registry.py`, `workflow/domain_registry.py` | Domain registration and trusted opaque callables. | Domain-specific evaluators and mutation surfaces should plug in here. |
| `workflow/ingestion/*` | Upload and media extraction. | Inputs for cognition and evaluators. User uploads remain authoritative and must not be summarized as "lessons" without provenance. |
| `workflow/context/*` | Compaction and guardrails. | Candidate generation prompts need compaction, but evaluator and run specs must remain external artifacts. |
| `fantasy_daemon/api.py`, `fantasy_daemon/__main__.py` | Legacy/reference domain surfaces; large root modules remain. | Good stress domain, not where optimization primitives should live. Use it to test domain adaptation after engine-level primitives exist. |

## Module-By-Module: ASI-Evolve

| Module | What it does | What Workflow should learn |
|---|---|---|
| `main.py` | Small CLI wrapper. Bootstraps repo as package `Evolve`, parses experiment/steps/sample/eval args, runs `Pipeline`. | Keep CLI thin. Workflow's equivalent should call existing API/run primitives, not duplicate orchestration. |
| `config.yaml` | Central defaults: provider, model params, agents enabled, retries, parallel workers, judge ratio, cognition, database, sampler. | Use explicit run spec. Avoid ambient config drift; status should expose effective config. |
| `pipeline/main.py` | Orchestrates steps, resumes state, samples parents, retrieves cognition, runs researcher/engineer/analyzer, stores node, updates best snapshot. | This is the core pattern to absorb. But Workflow should replace local threads with durable distributed task rows. |
| `pipeline/base.py` | Shared LLM/prompt/log setup for agents. | Workflow already has providers/router and should keep role-specific routing rather than a single LLM client. |
| `pipeline/researcher/researcher.py` | Generates candidate code by search/replace diff against a sampled parent, falling back to full rewrite. | "Patch vs rewrite vs fresh branch" should be an explicit candidate design choice with approved mutation paths. |
| `pipeline/engineer/engineer.py` | Writes candidate to `steps/<n>/code`, runs `bash eval.sh`, parses `results.json`, optional LLM judge. | Preserve materialized candidate artifacts. Add sandboxing, timeout invariants, structured evaluator results, and OS portability. |
| `pipeline/analyzer/analyzer.py` | Produces `analysis` text from code/results/best sampled node. | Analyzer lessons should become typed data: hypothesis, mechanism, evidence, failed assumptions, applicability, confidence. |
| `pipeline/manager/manager.py` | Optional prompt generation/management. | Workflow should let users vibe-code optimization specs/evaluators, but lock them before runs. |
| `database/database.py` | JSON node store with embeddings, sampler hooks, max-size eviction, FAISS save/load. | Equivalent should be `optimization_runs`/candidate tables plus vector/dedup indexes, not ad hoc JSON. |
| `database/faiss_index.py` | Embedding index for node similarity. | Workflow has LanceDB singleton; use one backend policy and avoid per-run connection recreation. |
| `database/embedding.py` | Sentence-transformers wrapper. | Keep embedding provider pluggable and startup-probed. Missing embeddings must fail or mark degraded clearly. |
| `database/algorithms/ucb1.py` | Exploration/exploitation parent selection. | Useful default when a direction exists. Add score normalization and visit counts to candidate store. |
| `database/algorithms/random.py` | Uniform exploration. | Useful for early scouting and anti-local-minimum runs. |
| `database/algorithms/greedy.py` | Top-score exploitation. | Should be rare; risks premature convergence and contradicts Workflow's diverse-ecology principle if overused. |
| `database/algorithms/island.py` | Island evolution, archive, migration, optional feature maps/MAP-Elites-style bins. | Highest-value search idea for Workflow: maintain diversity across solution families, not just best scalar score. |
| `cognition/cognition.py` | Prior knowledge store with FAISS retrieval. | Workflow should model cognition as approved reusable insight, not per-round transcript memory. |
| `utils/structures.py` | `Node`, `CognitionItem`, config/LLM response dataclasses. | Good minimal schema, but Workflow needs richer typed provenance, privacy, authorship, cost, and temporal fields. |
| `utils/diff.py` | Search/replace diff extraction and application. | Useful but too brittle as the only patch mechanism. Workflow should prefer structured patches/JSON-pointer mutation for node concepts. |
| `utils/llm.py` | OpenAI-compatible client, tag parsing, retries. | Workflow's no-SDK primary-writer rule means use provider subprocesses where required. Keep tag/JSON parsing robust. |
| `utils/prompt.py` and `utils/prompts/*.jinja2` | Template rendering for agents. | Optimization specs should be artifacts, not hidden prompt strings. Prompt templates should be versioned. |
| `utils/logger.py` | Console/file/W&B logging and stats. | Workflow should log run events into existing run/event tables and public/host-visible traces. |
| `utils/best_snapshot.py` | Maintains best candidate snapshot. | Merge-back should be versioned and provenance-linked; best snapshots are review material, not automatically truth. |
| `experiments/circle_packing_demo/*` | Runnable example with baseline, evaluator, cognition seed, prompts. | Workflow needs one tiny, deterministic reference optimizer test before production-scale node optimization. |
| `skills/evolve/SKILL.md` | Single-agent version with preflight, run spec, mutation scope, timeout, explicit sampling, cognition/database wrappers. | This is the most immediately reusable operational pattern. Its preflight gates match Workflow's safety needs better than `pipeline/main.py`. |
| `skills/evolve/scripts/evolve_core/*` | Vendored database/cognition/sampling/CLI wrappers for skill runs. | Do not vendor directly. Use as a design reference for Workflow-native CLI/API helpers. |

## Cross-System Lessons From Online Research

AlphaEvolve, OpenEvolve, ASI-Evolve, AI Scientist, and Agent Laboratory point to
the same basic truth: autonomous research works best when the system can cheaply
generate many candidates, run an evaluator, preserve the full trail, and feed
structured failures into later attempts.

The differences matter:

- AlphaEvolve emphasizes automated evaluators, model diversity, and codebase
  evolution for objectively measurable algorithmic tasks.
- OpenEvolve adds useful engineering patterns: artifacts side-channel,
  deterministic seeds, MAP-Elites visualization, prompt/meta-evolution, and
  explicit common pitfalls.
- ASI-Evolve adds a cognition base and analyzer that distills lessons back into
  future rounds.
- AI Scientist covers the whole paper-generation pipeline, but its own repo
  warns about executing LLM-written code and needing containment. That warning
  is directly relevant to Workflow node execution.
- Agent Laboratory highlights human feedback at stage boundaries. This supports
  Workflow's merge-policy design: auto-merge clear wins, review close calls.

The best synthesis for Workflow is not "fully autonomous science agent". It is
"evaluation-driven workflow evolution with explicit human/daemon merge policy".

## Best Implications For Workflow

### 1. Ship a native `OptimizationRun` primitive

Use Workflow's existing run/event substrate. Do not introduce an ASI pipeline
that bypasses `workflow/runs.py`, branch versions, provider routing, host-pool
claiming, or MCP evidence.

Minimum shape:

```text
OptimizationRun
  run_id
  target_kind: node | branch | evaluator
  target_ref
  baseline_ref
  optimization_spec_ref
  editable_surface
  evaluator_chain_ref
  search_policy
  budget
  merge_policy
  status
```

### 2. Normalize `EvaluatorResult`

PLAN §33 already names this. Make it concrete before large optimization work.

```text
EvaluatorResult
  score
  score_vector
  verdict
  rationale
  evidence
  artifacts
  evaluator_id
  cost
  ran_at
  freshness
```

The `artifacts` field is important. OpenEvolve's previous execution feedback
pattern is exactly what lets later generations learn from stderr, warnings,
profiling, and human/LLM comments.

### 3. Freeze evaluator and mutation scope before running

ASI's strongest operational invariant is also in Workflow PLAN §32: separate:

- the optimization spec,
- the editable candidate surface,
- the evaluator/test harness.

The generator must not edit the evaluator it is trying to satisfy. The first
Workflow implementation should enforce this structurally with write scopes and
hashes, not socially with prompt text.

### 4. Store analyzer lessons as typed facts

ASI stores `analysis` as text. Workflow can do better:

```text
OptimizationLesson
  candidate_id
  parent_ids
  hypothesis
  changed_mechanism
  metric_delta
  failure_mode
  reusable_principle
  applicability_scope
  confidence
  evidence_refs
```

These can feed retrieval, KG, discovery ranking, and future branch remix.

### 5. Add quality-diversity search, not just top-score search

Workflow's product thesis is "diverse evolving public workflows", so MAP-Elites
and island search fit better than greedy search. We should preserve alternative
families even when they are not current best.

For Workflow, feature dimensions should include:

- score/performance,
- cost,
- runtime,
- complexity,
- reliability,
- evaluator confidence,
- privacy/sensitivity class,
- branch lineage/family,
- domain-specific metrics.

### 6. Make distributed evaluation native

ASI-Evolve uses local threads. Workflow should use:

- BranchTask queue or a new optimization task queue,
- host-pool claiming,
- `SELECT FOR UPDATE SKIP LOCKED` in the future Postgres control plane,
- candidate hash dedup,
- cost and wall-clock budget enforcement,
- restart-safe status transitions.

This is where Workflow can exceed ASI rather than imitate it.

### 7. Use provider diversity deliberately

AlphaEvolve uses different model strengths for breadth and depth. Workflow
already has provider routing. Recommended role split:

- cheap/broad proposer,
- deeper proposer for top candidates,
- deterministic evaluator first,
- independent editorial/evaluator provider,
- analyzer provider selected for synthesis quality.

Provider status must be reported as effective runtime evidence; phantom
fallbacks caused prior Workflow incidents.

### 8. Make merge-back conservative

A candidate passing the evaluator is not automatically globally better.

Recommended policies:

- `human_review_always` for public/high-risk nodes,
- `human_review_if_delta_below` for ordinary nodes,
- `auto_accept_if_improves_by` only for deterministic, low-risk metrics,
- holdout evaluator or replay set before merge,
- rollback-ready version history.

### 9. Treat real-world outcomes as the higher evaluator layer

ASI optimizes local scores. Workflow's advantage is outcome gates:

```text
candidate improves benchmark
  -> node/branch version improves real workflow output
  -> user adopts output
  -> external outcome is verified
```

Discovery and leaderboards should not overfit to local eval wins. Real-world
effect stays the north star.

### 10. Build a tiny reference optimizer first

Before optimizing arbitrary nodes, create a deterministic toy target similar to
ASI's circle-packing demo, but Workflow-native. Good candidates:

- optimize a small prompt node against fixed golden examples,
- optimize a simple code node against unit tests,
- optimize a branch routing heuristic against synthetic traces.

The first proof should verify:

- locked evaluator,
- editable surface enforcement,
- candidate storage,
- parent sampling,
- analyzer lesson storage,
- merge-back/rollback,
- resume after interruption,
- cost/budget accounting.

## What Not To Copy

- Do not copy ASI's file-local JSON database as a production store.
- Do not copy the bash-only evaluator interface as the only execution path.
- Do not let the candidate writer edit evaluator scripts.
- Do not rely on one scalar `score` for public discovery or merge decisions.
- Do not store all lessons in global memory.
- Do not use local thread pools as the platform concurrency model.
- Do not auto-merge public nodes from noisy LLM-judge metrics.
- Do not treat generated code execution as safe without sandbox/timeout/network
  policy.

## Recommended Implementation Roadmap

This is ordered by leverage and collision risk, not by excitement.

### Slice 0: Decision

Accept or reject this design stance:

> Workflow will not vendor ASI-Evolve. Workflow will implement an ASI-style
> evaluator-driven optimization loop natively on top of `runs`, `branches`,
> `evaluation`, `host_pool`, and branch/version provenance.

If accepted, add it to PLAN.md. Until accepted, keep this report as analysis.

### Slice 1: `EvaluatorResult` schema and artifact side-channel

Files likely involved:

- `workflow/evaluation/`
- `workflow/api/evaluation.py`
- tests under `tests/test_evaluation.py` and related run/judgment tests

Goal: every evaluator can return score, verdict, rationale, evidence, artifacts,
cost, freshness, and evaluator id.

### Slice 2: Optimization run spec

Files likely involved:

- `workflow/branches.py`
- `workflow/runs.py`
- `workflow/api/runs.py`
- a design note or vetted spec section

Goal: represent optimization target, mutation scope, evaluator ref, search
policy, budget, and merge policy without executing candidates yet.

### Slice 3: Single-node local optimizer proof

Files likely involved:

- `workflow/runs.py`
- `workflow/api/evaluation.py`
- new runtime/helper module only if it fits the target layout
- focused tests

Goal: run 3-5 candidate variants against a deterministic evaluator and record
candidate lineage.

### Slice 4: Analyzer lessons

Files likely involved:

- `workflow/knowledge/`
- `workflow/memory/`
- `workflow/runs.py`

Goal: store typed `OptimizationLesson` entries and retrieve them in later
candidate generation.

### Slice 5: Quality-diversity sampler

Files likely involved:

- runtime/search helper module
- `workflow/runs.py`
- tests for UCB1/random/greedy/island behavior

Goal: preserve diverse candidate families and expose why each parent was chosen.

### Slice 6: Distributed host execution

Files likely involved:

- `workflow/host_pool/`
- `workflow/branch_tasks.py`
- `workflow/dispatcher.py`
- future Postgres control plane

Goal: scale candidates across hosts with claims, budget caps, dedup, and
restart-safe transitions.

## Highest-Risk Failure Modes

1. Metric gaming: the generator learns evaluator quirks rather than improving
   the node.
2. Evaluator drift: the evaluation layer changes mid-run, invalidating score
   comparisons.
3. Memory pollution: failed local run lessons become global doctrine.
4. Premature convergence: greedy sampling kills diversity and contradicts the
   ecology principle.
5. Public auto-merge harm: noisy evaluator merges a worse public node.
6. Sandbox escape or resource burn: generated code executes with too much
   system/network access.
7. Storage pressure: large candidate runs create unbounded artifacts.
8. Provider false-advertising: status says a role has fallback capacity when it
   does not.
9. Privacy leakage: private instance details become reusable cognition.
10. UI misframing: users think "AI research toy" instead of "real work gets
    better while I sleep".

## Immediate Product Implications

- This strengthens, not replaces, the Forever Rule. The uptime/distribution
  lane remains top priority; ASI-style optimization becomes a way to improve
  nodes and evaluators after the public surfaces are reachable.
- The node discovery/remix surface should show lineage, evaluator evidence, and
  real-world outcomes, not just "best score".
- Tier-2 host UX should eventually show optimization contribution: candidates
  evaluated, winning candidates produced, cost earned, real-world outcomes
  helped.
- Tier-1 chatbot UX should hide most mechanics. The user says: "improve this
  invoice processor overnight, do not spend over $10, ask me before merging."
- Tier-3 contributors should get deterministic local examples and tests so they
  can build samplers/evaluators without production credentials.

## Final Recommendation

The best system Workflow can make is not an ASI-Evolve clone. It is an
evaluation-driven, multiplayer, outcome-aware evolution substrate where:

- ASI-style loops optimize individual nodes, branches, evaluators, and workflow
  topologies;
- users and daemons publish many competing approaches under shared Goals;
- evaluators are composable, inspectable, and recursively optimizable with
  cycle guards;
- candidate runs are distributed across hosts with budgets and provenance;
- real-world outcomes sit above local metrics;
- merge-back is conservative and versioned.

In short: ASI-Evolve teaches the inner loop. Workflow's job is to build the
outer civilization around that loop.
