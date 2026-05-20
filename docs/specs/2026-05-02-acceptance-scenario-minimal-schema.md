# AcceptanceScenario — minimal schema spec

**Status:** Slice 1 minimal schema (per `docs/design-notes/2026-05-02-acceptance-scenario-packs.md`).
**Authority:** Claude review APPROVE verdict (`docs/audits/2026-05-02-agencybench-claude-review.md`).
**Date:** 2026-05-20.

---

## Purpose

Specify the data shape for an `AcceptanceScenario` — a typed contract that compiles into existing `EvalResult` evidence via a thin runtime (Slice 2). Slice 1 ships the contract only.

## Inheritance / storage

An `AcceptanceScenario` is a new typed record, NOT a memory_kind. Each scenario has a stable identity and is reusable across runs. Storage location is decided in Slice 2 design (candidate: `workflow/storage/acceptance_scenarios.py` table with the existing `_connect()` pattern, OR a `pages/scenarios/` wiki-page-backed surface). This spec defines the **contract shape**; Slice 2 picks the storage.

## Fields

| Field | Type | Required | Purpose |
|---|---|---|---|
| `scenario_id` | string | required | Stable identifier, format `scenario:<slug>`. Immutable; updates create a new scenario with `supersedes_id` pointing at the prior version. |
| `target_surface` | enum | required | One of: `mcp_call`, `ui_test_mission`, `branch_run`, `external_effect`, `session_trace_summary`. Drives dispatch to the right runtime + evaluator chain. |
| `user_story` | string | required | 200–2000 character narrative of what a real user would do. Drives the user-simulation prompt. |
| `setup` | list[object] | optional | Pre-scenario actions the runner executes (list of MCP tool calls, e.g. `[{"action": "goals action=propose", "args": {...}}, ...]`). Slice 2 picks the exact schema; this spec only locks the field name + intent. |
| `allowed_tools` | list[string] | required | Tool allowlist. List of MCP tool names the candidate may invoke. Refusal at the runtime is an EvalResult `failure_mode: "tool_not_allowed"`. |
| `evaluator_chain` | list[string] | required | Ordered list of evaluator IDs the runner invokes against the candidate's output. Each evaluator emits an evaluator-specific `EvalResult` artifact; aggregation rules are Slice 2. |
| `artifact_requirements` | list[object] | required | List of required artifact descriptors: `{"kind": "<screenshot|dom|packet|file>", "scope": "<final|every_step|on_failure>", "redact_pattern": "<optional-regex>"}`. Missing required artifact marks scenario FAILED. |
| `pass_threshold` | object | required | Threshold spec: `{"min_score": <float>, "score_aggregation": "<min|mean|weighted>", "weights": {"<evaluator-id>": <float>, ...}}`. Score above threshold = PASS; at or below = FAIL. |
| `cost_budget` | object | required | Bounded spend cap: `{"max_tokens": <int>, "max_wall_time_seconds": <int>, "max_provider_cost_usd": <float|null>}`. Runner hard-kills on over-budget per Brain Module bounded-spend principle. |
| `privacy_scope` | enum | required | One of: `scenario_internal` (artifacts stay host-only; never even candidates for any wiki), `universe_only` (eligible for universe wiki promotion only), `commons_publishable` (eligible for cross-universe commons promotion). |
| `idempotency_key_constructor` | string | required | Stable hash recipe for a scenario run, per the external-write authority design (#914). Format: deterministic string template referencing scenario_id + target_surface + setup hash + attempt window. Required at scenario-registration time; runtime refuses to dispatch without it. |
| `supersedes_id` | string | optional | Set when a new scenario version replaces an older one. Old scenario stays as historical reference; new scenario is the active version. Matches the memory promotion supersede pattern. |

## Example scenario record (concrete: Goal proposal MCP test)

```json
{
  "scenario_id": "scenario:goals-propose-happy-path-v1",
  "target_surface": "mcp_call",
  "user_story": "A new user opens their MCP-connected chatbot, asks 'I want to start a fantasy novel project,' and expects the chatbot to propose a new Goal record bound to a fantasy_novel category and return the goal_id so they can keep referring to it in conversation.",
  "setup": [
    {"action": "universe action=ensure_exists", "args": {"universe_id": "scenario-test-universe"}}
  ],
  "allowed_tools": [
    "goals",
    "universe"
  ],
  "evaluator_chain": [
    "evaluator:goal-record-shape-check",
    "evaluator:user-narrative-clarity-check"
  ],
  "artifact_requirements": [
    {"kind": "packet", "scope": "final", "redact_pattern": null},
    {"kind": "trace", "scope": "every_step", "redact_pattern": null}
  ],
  "pass_threshold": {
    "min_score": 0.75,
    "score_aggregation": "weighted",
    "weights": {
      "evaluator:goal-record-shape-check": 0.7,
      "evaluator:user-narrative-clarity-check": 0.3
    }
  },
  "cost_budget": {
    "max_tokens": 8000,
    "max_wall_time_seconds": 120,
    "max_provider_cost_usd": 0.50
  },
  "privacy_scope": "commons_publishable",
  "idempotency_key_constructor": "sha256({scenario_id}|{target_surface}|{setup_hash}|{date_hour})"
}
```

## Visibility-state interaction

Scenarios don't transition through promotion states themselves; they're stable typed records. **Scenario runs** (the EvalResult artifacts they produce) DO carry visibility tags inherited from the scenario's `privacy_scope`. Per the PrivateTraceCommons lane (visibility tag, no platform enforcement): if a universe wants `scenario_internal` runs to never produce commons-readable artifacts, the universe owner wires that as a gate composition.

The same Scoping-Rule-2 discipline applies: platform ships the privacy_scope tag; universe ships the enforcement.

## Cross-link to PLAN.md modules

- **Evolution & Evaluation Module** (primary): scenarios compile into the existing `EvalResult` contract. Per PLAN.md "**Acceptance Scenario Packs.** Host-approved 2026-05-02 direction (pending opposite-provider review)" — the audit (#928) is that review.
- **Harness & Coordination Module**: scenarios with `target_surface=ui_test_mission` compose with the existing user-sim discipline; no parallel implementation.
- **Goals & Gates Module**: future Slice 4 wires scenario-pack requirements into the rung-claim flow.
- **Brain Module**: `cost_budget` aligns with bounded-spend; scenario run results may produce `session_trace_summary` memories.

## Acceptance checklist

Slice 1 (this PR) passes when:

- [ ] All 11 required fields have a concrete failure-mode justification (per design note table)
- [ ] All 5 audit open questions have explicit resolutions (per design note)
- [ ] Example scenario record validates against the field types
- [ ] No new evaluator primitive; no new sandbox primitive; no new gating primitive
- [ ] No AgencyBench code referenced or vendored
- [ ] ui-test composability preserved per Hard Rule #11
- [ ] `privacy_scope` enum + tag-only-no-enforcement matches the PrivateTraceCommons lane's pattern

Slice 2 (runtime, future PR) passes when:

- [ ] A `workflow/evaluation/scenario_runner.py` module exists with a `run_scenario(scenario, candidate_ref) -> EvalResult` function
- [ ] The runner dispatches to existing primitives (user-sim for ui_test_mission, run_branch for branch_run, MCP tool call for mcp_call) — no parallel implementation
- [ ] Cost budget enforcement hard-kills on over-budget
- [ ] At least one end-to-end scenario from registration to EvalResult is exercised by a test
- [ ] Plugin mirror parity holds if `workflow/evaluation/` is touched

Slice 3+ (concrete scenarios + community library + optimization gate): each ships as separate PRs against their own slice plans.

## What is NOT in this spec

Out of scope per the audit verdict's REAFFIRMS:

- ❌ AgencyBench corpus or scenario folder layout
- ❌ SII Agent SDK
- ❌ `seccomp=unconfined` Docker pattern
- ❌ New `EvaluatorKind`
- ❌ Replacement of `ui-test` as final acceptance proof
- ❌ Automatic public scenario upload
- ❌ Parallel user-sim implementation
- ❌ Hidden-reasoning capture in scenario artifacts
- ❌ Platform-enforced visibility coupling (community composes via gates, per the same pattern as PrivateTraceCommons / #935)
