# Daemon Task Economy — Rollout Plan

**Status:** executable — derived from greenlit memo `docs/planning/daemon_task_economy.md` (host approval 2026-04-14).
**Audience:** dev claiming sequential phases.
**Owner:** planner (this file); dev (per-phase implementation).

Each phase ships independently behind a feature flag where it mutates behavior that could surprise hosts. "If we stop here" spells out the UX win delivered by that phase alone — a partial rollout is still a real improvement, not a half-finished feature.

**Universal doctrine:** every phase must expand the user's power to design, inspect, steer, or evolve their workflow. Daemon gets smarter only in service of user-facing legibility.

---

## Phase order + dependency graph

```text
A (naming/stubs)  ──┬──▶ C (producer interface) ─▶ D (fantasy-as-Branch) ─▶ E (dispatcher)
                    │                                                        │
B (wire requests) ──┘                                                        │
                                                                             ▼
                                            F (Goal subscription) ─▶ G (paid weights) ─▶ H (dashboard)
```

A and B run in parallel (disjoint files). Everything else is sequential.

---

## Phase A — Kill dead stubs + disambiguation naming

**Goal:** clear the semantic fog so §3's three-axes model is not papered-over in names. Explorer's §1 identified **three** disjoint "branch" concepts in the repo — rename the non-user-facing ones.

**Scope:**
- Delete `universe.branches.json` dead-stub code paths. `_action_list_branches` at `tinyassets/universe_server.py:1873` returns a hardcoded `[{"id":"main"}]` from a stub file nothing writes; retire the path.
- **Rename concept #2 (SQL `branches` table at `author_server.py:195 / :829` — git-style in-universe fork)** → `universe_fork` across SQL schema (backward-compatible migration), MCP tool params, docstrings, error messages, tests.
- **Concept #1 (`BranchDefinition`)** keeps the public-facing "Branch" name — it's the user-primitive in PLAN.md and the Multi-User Evolutionary Design section.
- **Concept #3 (LangGraph internal conditional edges)** — out of scope. That's LangGraph's term, not ours.
- `tinyassets/universe_server.py` surface: `list_branches` becomes ambiguous; split into `list_universe_forks` (concept #2) vs `list_branch_defs` (concept #1).

**Files:** `tinyassets/author_server.py`, `tinyassets/universe_server.py`, relevant `tests/test_community_branches_*.py`, any domain references.

**Depends on:** — (first phase).

**Feature flag:** none — pure rename + dead-code deletion, tests lock the contract.

**If we stop here:** users stop seeing "branch" mean two different things in the MCP surface. The documentation / chat affordances around registering Branches stop colliding with Phase 4 universe-fork semantics. Zero runtime behavior change, but a measurable chat-UX improvement (bot stops saying "branch" when it means "universe fork" and vice versa).

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase A:** kill `universe.branches.json` stub + `universe_fork` vs `branch_def` rename | `tinyassets/author_server.py`, `tinyassets/universe_server.py`, `tests/test_community_branches_*.py` | — | pending | Pure rename + dead-code delete. No feature flag. Test suite locks the contract. |

---

## Phase B — Wire `submit_request` producer path

**Goal:** requests landing in `requests.json` stop being a dead drop; they surface to the daemon.

**Scope:**
- Already in-flight as Task #18 (dev). Verify it lands: `requests.json` reads are wired into the daemon loop as a BranchTask producer with `origin=host_request` (or `user_request` once external submission is possible).
- In the context of the rollout plan, this phase's value is establishing the **producer pattern** — the shape that Phase C will generalize.

**Files:** per #18 — `tinyassets/universe_server.py`, relevant daemon loop.

**Depends on:** — (parallel to A).

**Feature flag:** none required for the plumbing; default behavior is "requests are read"; empty requests.json is a no-op.

**If we stop here:** users who submit requests via MCP `submit_request` stop getting silent-drop. That's the immediate UX win. Sets up every subsequent phase's producer shape.

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase B:** wire `submit_request` producer (rolls up #18) | `tinyassets/universe_server.py`, daemon loop | — | claimed:dev | #18. Producer pattern for Phase C. |

---

## Phase C — Pluggable WorkTarget producer interface + genericize `execution_kind`

**Goal:** the daemon no longer runs one hardcoded "authorial review" selection. It runs a **list of producers**, each producing candidate Tasks, merged + scored.

**Scope:**
- Define a `TaskProducer` protocol: `produce(universe, config) -> list[BranchTask]`. Implementations live in `tinyassets/producers/`.
- Convert `choose_authorial_targets` into `FantasyAuthorialProducer(TaskProducer)`. Move from `domains/fantasy_author/phases/` into a producer-shaped wrapper.
- Convert `foundation_priority_review` selection into `FoundationBlockerProducer(TaskProducer)`. Hard-blocker work becomes a special producer that pre-empts tier ordering.
- **Genericize `execution_kind`** — today `tinyassets/work_targets.py:49-51` exposes `EXECUTION_KIND_NOTES / BOOK / CHAPTER / SCENE`. BOOK/CHAPTER/SCENE leak fantasy into generic infrastructure. Replace with `execution_scope: str` (free-form) OR move the enum to `domains/fantasy_author/` and have the generic module accept any string. Recommend: move to domain — cheaper, safer.
- Add `origin` field on WorkTarget (§4.6 checklist item).
- Tests: a second trivial producer ("index-rebuild housekeeping") proves the interface isn't fantasy-shaped.

**Files:** `tinyassets/work_targets.py`, new `tinyassets/producers/__init__.py` + `tinyassets/producers/fantasy_*.py`, `domains/fantasy_author/phases/authorial_priority_review.py`, `domains/fantasy_author/phases/foundation_priority_review.py`, fantasy `__init__` (register producers), tests.

**Depends on:** A (naming settled before we scatter `branch_def` refs), B (producer pattern reference from `submit_request` wiring).

**Feature flag:** `TINYASSETS_PRODUCER_INTERFACE=on` (default on). If off, fall back to direct `choose_authorial_targets` call path. This is load-bearing — if the interface misbehaves, host can revert without a redeploy.

**If we stop here:** users can register their own TaskProducer (Python) and have the daemon pull candidate tasks from it. The fantasy daemon continues to work identically. The builder surface GAINS a Python-level extension point below the Branch level. **First time a user can extend the daemon's attention without writing a Branch.**

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase C:** pluggable `TaskProducer` interface + genericize `execution_kind` + `origin` field on WorkTarget | `tinyassets/work_targets.py`, new `tinyassets/producers/`, `domains/fantasy_author/phases/*priority_review.py`, tests | A, B | pending | Feature flag `TINYASSETS_PRODUCER_INTERFACE`. BOOK/CHAPTER/SCENE enum moves to fantasy domain. |

---

## Phase D — Fantasy universe-cycle graph as registered BranchDefinition

**Goal:** the fantasy daemon's autonomous graph becomes a regular Branch. Unifies the two execution paths (autonomous vs user-registered) through the same compiler + executor.

**Scope:**
- **Primary path: opaque-node wrapping (memo §3.4 option b).** Express the fantasy universe-cycle as a single-node `BranchDefinition(domain_id="fantasy_author", name="universe-cycle", ...)` whose one node invokes the existing `build_universe_graph()` StateGraph unchanged. No per-phase sandbox audit needed. Unification lands at the queue + inspection layer; per-phase legibility stays what it is today. Lower migration cost, ships the UX win sooner. **Implementation hint** (explorer): the single node's `NodeDefinition.approved` flag is set to `True` at registration time using the existing domain-trusted precedent at `tinyassets/universe_server.py:2577` (which already flips `approved=True` programmatically). No new approval mechanism required; `compile_branch` lets the approved node through without sandbox audit.
- **Deferred to future phase: trusted-domain carve-out (memo §3.4 option a).** A `trusted_domain` attribute on `BranchDefinition` that exempts domain-registered graphs from sandbox approval when `domain_id` matches a host's trusted-domain list. Unlocks per-phase inspection and per-phase user extensions. Revisit when a second domain lands OR when users actively want to extend fantasy at the phase level.
- `DaemonController` invokes via the unified executor path; the outer loop becomes "run this Branch forever" where "this Branch" is the registered single-node fantasy-cycle.
- **Risk:** breaking the autonomous loop is high-blast-radius. Feature-flag it: `TINYASSETS_UNIFIED_EXECUTION=off` by default. When off, fantasy uses the old `StateGraph` path directly. When on, it runs via the registered single-node Branch through `execute_branch`. Tests must pass under both settings; live-run at least one full user-sim mission on ON before flipping the default.

**Files:** `domains/fantasy_author/graphs/universe.py` (unchanged — just invoked by the wrapping node), new `domains/fantasy_author/branches/universe_cycle.yaml` (single-node Branch def), `domains/fantasy_author/__main__.py` (DaemonController wiring to invoke via registered Branch when flag on), tests. `tinyassets/branches.py` is NOT touched in Phase D — the `trusted_domain` attribute lands with option (a) when future demand materializes.

**Depends on:** C (producer interface — Phase D's universe-cycle Branch reads Tasks via producers, not via direct `choose_authorial_targets`).

**Feature flag:** `TINYASSETS_UNIFIED_EXECUTION=off` by default. Host opts in per-universe. Live tests under both settings for at least one full user-sim mission before flipping the default.

**If we stop here:** nothing changes for the user unless the flag is on. Under the flag, a user can inspect the fantasy daemon's running graph the same way they inspect their own Branches. **The builder surface and the autonomous surface have met.** This is the memo's load-bearing claim delivered.

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase D:** fantasy universe-cycle as registered Branch (opaque-node wrap) | `domains/fantasy_author/__main__.py`, new `domains/fantasy_author/branches/universe_cycle.yaml`, tests | C | pending | Feature flag `TINYASSETS_UNIFIED_EXECUTION` (default off). Single-node Branch wraps existing StateGraph unchanged — no per-phase sandbox audit. Trusted-domain carve-out deferred to future phase. High blast radius — live-test under both settings before flipping default. |

**Release notes (for the flag default flip):**

- **Body-less nodes now hard-fail at compile.** Phase D tightened `_build_node` so any `NodeDefinition` with empty `prompt_template` AND empty `source_code` AND no matching `(domain_id, node_id)` in the domain-trusted registry raises `CompilerError` instead of silently returning `_passthrough`. Low-probability impact on live user data — but if any user-registered Branches in the prod SQLite `branch_definitions` registry were accidentally saved with body-less nodes, they will fail to compile on load after the flag flips. Mitigation: the error message names the offending `(domain_id, node_id)` pair so host can add a body or delete the node. See `tinyassets/graph_compiler.py:_build_node` for the new error path.

---

## Phase E — Tier-aware `DaemonController` dispatcher

**Goal:** replace "run fantasy graph forever" with "walk tiers, pick Task, dispatch to executor."

**Scope:**
- `DaemonController` accepts `(universe_id, branch_def_id=<default>)` and dispatches any registered Branch.
- Implement the §4.1 fallthrough cascade in the controller. First iteration: tier on/off switches are config-only (host edits daemon config), no dashboard surface yet.
- BranchTasks route to `execute_branch_async`. NodeBids route to a new `execute_node_bid` (stub until Phase G, but the routing code exists).
- Existing fantasy daemon invocation stays identical (default `branch_def_id=fantasy_author/universe-cycle`).
- Writes `branch_tasks.json` per universe (§4.6 checklist item). Reads it via Phase B's producer pattern.

**Files:** `domains/fantasy_author/__main__.py` (DaemonController rewrite), new `tinyassets/dispatcher.py`, new `tinyassets/branch_tasks.py` (queue plumbing), tests.

**Depends on:** D (unified execution so the dispatcher has one path to route through).

**Feature flag:** inherits Phase D's flag. Tier enforcement goes live when `TINYASSETS_UNIFIED_EXECUTION=on`.

**If we stop here:** user can submit multiple BranchTasks via MCP to their daemon and see them run in tier + priority order. Queue is visible via an MCP inspection action. **First time user can see + steer a daemon queue.**

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase E:** tier-aware `DaemonController` + BranchTask queue | new `tinyassets/dispatcher.py`, new `tinyassets/branch_tasks.py`, `domains/fantasy_author/__main__.py`, tests | D | pending | Inherits `TINYASSETS_UNIFIED_EXECUTION` flag. Dispatcher + queue plumbing. NodeBid executor is stubbed. |

---

## Phase F — Goal subscription + pool producer

**Goal:** daemons can subscribe to Goals and pull cross-universe pool work when local queues are empty.

**Scope:**
- `subscribed_goals: list[str]` field on universe metadata (`rules.yaml`).
- New repo-root `goal_pool/<goal_slug>/` directory with YAML-per-BranchTask.
- `GoalPoolProducer(TaskProducer)` — for each subscribed Goal, reads the pool directory and emits BranchTasks with `origin=goal_pool`.
- MCP actions: `subscribe_goal(goal_id)`, `unsubscribe_goal(goal_id)`, `list_subscriptions`.
- Post-to-pool MCP action: `post_to_goal_pool(goal_id, branch_def_id, inputs, bid?)`.
- Default: on fresh install, daemon subscribes to a curated "maintenance" pool (index rebuilds, KG consolidations — the opportunistic tier materialized as public pool work anyone can pick up).

**Files:** `tinyassets/universe_server.py` (subscribe + post actions), new `tinyassets/producers/goal_pool.py`, new `goal_pool/` directory convention, tests.

**Depends on:** C (producer interface), E (dispatcher reading from producers).

**Feature flag:** `TINYASSETS_GOAL_POOL=off` by default. Host flips on when they want their daemon to touch external work.

**If we stop here:** a user's idle daemon starts doing useful maintenance across public Branches they've forked. Goal-pool submission is live. **First time the daemon leaves the universe boundary.** Still no monetary layer — that's Phase G.

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase F:** Goal subscription + pool producer | `tinyassets/universe_server.py`, new `tinyassets/producers/goal_pool.py`, `goal_pool/` dir, tests | C, E | pending | Feature flag `TINYASSETS_GOAL_POOL`. Default maintenance pool subscription. |

---

## Phase G — Paid-market priority weights + NodeBid executor

**Goal:** the priority scorer recognizes bids; the `execute_node_bid` stub becomes a real sandboxed single-node executor.

**Scope:**
- Implement `execute_node_bid(bid)` — sandboxed single-node run matching compile_branch's security model but narrower (one node, one LLM call).
- Add `bid`, `required_llm_type` to BranchTask AND NodeBid shapes (memo §3.2).
- Priority scorer (§4.3) accepts `bid_term(task.bid)`. Weight-coefficient `bid_weight` in daemon config.
- Repo-root `bids/` directory. `NodeBidProducer(TaskProducer)` reads it. MCP action: `submit_node_bid(node_def_id, required_llm_type, inputs, bid)`.
- **No real monetary integration.** Bids are token-denominated and accounted, but wallet/crypto integration is a later phase. This phase ships the priority-function slot so the market can grow into it.
- Ties to #56 outcome gates: NodeBid completion requires `evidence_url`. Sybil-prevention stub.

**Files:** new `tinyassets/node_bid.py`, new `tinyassets/executors/node_bid.py`, `tinyassets/producers/node_bid.py`, `tinyassets/dispatcher.py` (scorer), `bids/` dir convention, tests.

**Depends on:** E (dispatcher), F (producer pattern at pool scale). #56 spec should be in Phase 6.2+ at this point.

**Feature flag:** `TINYASSETS_PAID_MARKET=off` by default. Host opts in.

**If we stop here:** the priority scorer handles bids correctly in-process (host can manually submit zero-bid NodeBids and watch sort order). No external market yet. But the structural slot exists — the daemon will never need a scorer retrofit when the real market lands.

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase G:** NodeBid executor + paid priority weights | new `tinyassets/node_bid.py`, new `tinyassets/executors/node_bid.py`, `tinyassets/producers/node_bid.py`, dispatcher scorer, `bids/` dir, tests | E, F, #56 spec Phase 6.2+ | pending | Feature flag `TINYASSETS_PAID_MARKET`. No real wallet integration — priority slot only. |

---

## Phase H — Host dashboard + inspection surfaces

**Goal:** the per-tier on/off switches, earnings view, request inbox, and Task-queue inspection are all surfaced through the host dashboard and MCP inspection tools. The user can SEE what the daemon is doing and STEER it.

**Scope:**
- Dashboard: tier toggles (accept_external, accept_goal_pool, accept_paid, allow_opportunistic). Per-Goal subscribe list. Earnings table. Accepted vs declined bid list with reasons. Active Task + recent Task history.
- MCP inspection actions: `inspect_daemon_queue`, `inspect_tier_config`, `inspect_earnings` (gated by `TINYASSETS_PAID_MARKET`).
- Chatbot-side affordances: "pause tier X", "promote Task Y", "subscribe to Goal Z."
- UX-doctrine acceptance test: a user new to TinyAssets who runs a daemon for the first time should see the full tier ladder with explanatory text, and be able to toggle any tier in one click. No hidden state.

**Files:** dashboard surface (Qt or equivalent host-side), `tinyassets/universe_server.py` (new MCP inspect actions), tests.

**Depends on:** E, F, G (everything the dashboard surfaces must exist).

**Feature flag:** none — dashboard/MCP additions are purely additive.

**If we stop here:** the user has full visibility + steering over their daemon. This is the memo's UX-primary doctrine fully delivered — the product is workflow-building POWER, and the user can now design, inspect, and steer every tier of daemon activity. Paid market may still be behind its flag, but every non-market surface is live and legible.

**Work table row:**
| Task | Files | Depends | Status | Notes |
|---|---|---|---|---|
| **Phase H:** host dashboard + MCP inspect surfaces | host dashboard app, `tinyassets/universe_server.py` new inspect actions, tests | E, F, G | pending | No feature flag — purely additive. UX-primary delivery vehicle. |

---

## Cross-phase notes

- **Every phase must leave `tests/` strictly greener** — no test skips, no xfails added. If a phase requires test-shape changes, reviewer does whole-file pass before commit (per 2026-04-14 feedback memory).
- **Every feature flag defaults OFF except where explicitly noted** (Phase C's producer interface defaults on because it's the smallest-risk refactor and subsequent phases depend on it).
- **Flag lifecycle — when a restart is required.** Not every flag behaves the same at flip-time. Two classes:
  - **Registration-gate flags** are read once at module import in a `register_if_enabled()` side-effect. Flipping the env var on a live daemon has no effect until the process restarts. These are the flags that add producers/nodes to a registry at startup.
    - `TINYASSETS_GOAL_POOL` — `tinyassets/producers/goal_pool.py:334-355` (`register_if_enabled()` + module-level call). **Restart required.**
    - `TINYASSETS_PAID_MARKET` — `tinyassets/producers/node_bid.py:38-41, 207-228` (`paid_market_enabled()` + `register_if_enabled()` + module-level call). **Restart required.**
  - **Behavior-gate flags** are read at call time inside a helper. Flipping the env var takes effect on the next cycle — no restart.
    - `TINYASSETS_UNIFIED_EXECUTION` — `fantasy_author/__main__.py:126-129` (`_workflow_unified_execution_enabled()`, called from `_run_graph`). **No restart needed.** The `universe_cycle_wrapper` is registered unconditionally at `fantasy_author/branch_registrations.py:111`; the flag only routes between Branch-compile and direct paths.
    - `TINYASSETS_DISPATCHER_ENABLED` (Phase E) — read at call time. **No restart needed.**

  Operators flipping a default should know which class applies. Tests that `monkeypatch.setenv` a registration-gate flag must call `register_if_enabled()` explicitly or re-import the module — setting the env alone won't change the live registry.
- **No phase merges without user-sim validation** on at least one clean universe. Sporemarch / ashwater stress-tests follow.
- **#56 outcome gates** interacts with Phase G's NodeBid sybil-prevention. Track coordination in STATUS concerns.
- **Execution_kind genericization** (the BOOK/CHAPTER/SCENE leak) lives in Phase C; verify no STATUS concern or PLAN.md assumption contradicts.
- **PLAN.md updates** — this rollout introduces concepts (BranchTask, NodeBid, TaskProducer, Goal subscription) that belong in PLAN.md's Design Decisions. After Phase D lands, draft PLAN.md additions for host approval.

## What this rollout does NOT do

- **Wallet / crypto integration.** Phase G ships the priority-function slot, not the payment rails. The real market integration is a later phase with its own memo.
- **Multi-host federation.** A daemon on host A still can't pull Goal-pool work posted by host B unless the pool is git-synced. Git sync is Phase 7's job, not this rollout's.
- **Dynamic `subscribed_goals` from chat.** Phase F surfaces subscribe/unsubscribe via MCP but not via natural-language chat parsing. That's a later UX pass.
- **Moderation of pool work.** The memo and this rollout punt on spam / malicious pool postings. Phase 6.5 (outcome-gate adversarial validation) is the natural place for that.

---

## Reviewer + host audit checklist

Before claim on each phase:
- Phase's "if we stop here" readout must describe a real UX win, not just plumbing.
- Files column must not overlap any in-progress phase's Files column.
- Feature flag (if required) has a defined default, a host toggle surface, and a test that proves both paths work.
- Dependencies are explicitly listed — no invisible reads-from-main assumptions.

Once reviewer clears a phase, dev claims, lands, user-sim validates, next phase unblocks.
