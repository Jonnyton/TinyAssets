# Acceptance Scenario Packs — Slice 1 design

**Status:** Slice 1 design (per Claude review APPROVE verdict + host pre-approved direction 2026-05-02).
**Authority:** `docs/audits/2026-05-02-agencybench-claude-review.md` (verdict: APPROVE with no-vendor reaffirmation + scope-first slicing).
**Radar source:** `docs/audits/2026-05-02-frontier-repo-radar-2.md` (AgencyBench frontier finding).
**Touches:** Evolution & Evaluation Module (primary), Harness & Coordination Module (composes with ui-test), Goals & Gates Module (composes with outcome ladder), Brain Module (cost + attribution refs).
**Date:** 2026-05-20.

---

## What's IN scope

A new typed surface — `AcceptanceScenario` — that compiles into existing `EvalResult` artifacts via a small runtime. The scenario describes a long-horizon acceptance check (a real-shape user-like task with user simulation, rubric assertions, artifact capture); the runtime executes it and emits standard `EvalResult` evidence. No new evaluator primitive; no parallel runner.

Slice 1 ships design + spec only. No runtime code. No scenario-pack vendoring.

## What's OUT of scope

Per the audit verdict's REAFFIRMS:

- ❌ No AgencyBench code vendored. Not its SII Agent SDK, not its scenario folder layout, not its corpus.
- ❌ No `seccomp=unconfined` Docker pattern.
- ❌ No new `EvaluatorKind`. Scenarios emit existing `EvalResult` artifacts.
- ❌ No replacement of `ui-test` as the final acceptance proof per Hard Rule #11. Scenarios are pre-launch harness; `ui-test` is post-deploy clean-use proof. They compose; neither replaces the other.
- ❌ No automatic public scenario upload. Community scenario library (Slice 5) is per-piece visibility per Goal owner.
- ❌ No parallel user-sim implementation. Existing user-sim discipline (per `feedback_user_sim_*` memories) composes; the scenario adds a typed envelope, not a new runner.

## The `AcceptanceScenario` primitive

After the audit's question 1 pressure-test — "could a chatbot compose this from existing primitives in <5 reasoning steps?" — the honest answer is: **mostly yes, but not reliably across surfaces.** A chatbot can run a single MCP-call scenario by composing `runs action=start` + `evaluators` + a manual rubric check. Where the composition breaks down:

- Long-horizon sessions with multiple subtasks need a single durable identity (`scenario_id`) that ties evidence across sub-runs.
- Visual-artifact bundles (screenshots + DOM + API state) need a consistent capture contract or every scenario reinvents it.
- Cost budgets are necessary because long-horizon scenarios are expensive; without a typed cap the chatbot has no place to enforce stop conditions.
- Reproducibility across providers (Claude vs ChatGPT vs Cursor) needs a setup contract; ad-hoc per-scenario setup drifts.

The minimum primitive that closes the structural gap: ONE typed contract with the 9 fields below + a thin runtime that executes the contract against the existing user-sim discipline + emits standard `EvalResult` artifacts.

Slice 1 ships the contract; runtime is Slice 2.

## The 9 fields (justified per audit question 1)

| Field | Justifies what failure mode |
|---|---|
| `scenario_id` | A single durable identity that ties evidence + cost + provenance across multiple sub-runs. Without it: ad-hoc IDs scatter across `output/`, and cross-run aggregation is brittle. |
| `target_surface` | Names what the scenario is testing — `mcp_call`, `ui_test_mission`, `branch_run`, `external_effect`, `session_trace_summary`. Without it: dispatch logic can't route the scenario to the right runtime + evaluator chain. |
| `user_story` | Free-text narrative of what a real user would do. Drives the user-simulation prompt. Without it: scenarios devolve into unit tests that don't resemble real user behavior. |
| `setup` | Pre-conditions the scenario assumes (universe state, branch fixtures, available evaluators). Without it: scenarios drift; the same scenario passes/fails depending on environment. |
| `allowed_tools` | Tool allowlist the candidate agent may use. Without it: scenarios can't enforce "this candidate is restricted to MCP only" or "no external network calls." |
| `evaluator_chain` | Ordered list of evaluator IDs the scenario runs against the candidate's output. Without it: scenario verdict is opinion not evidence. |
| `artifact_requirements` | List of artifact kinds the candidate MUST produce (screenshot, DOM snapshot, packet, file). Without it: the evidence bundle is incomplete and `EvalResult.artifacts` becomes inconsistent across runs. |
| `pass_threshold` | Threshold the evaluator chain's score must clear for the scenario to PASS. Without it: PASS/FAIL is ambiguous. |
| `cost_budget` | Token / wall-time / provider-spend cap. Without it: long-horizon scenarios run unbounded. Composes with the bounded autonomous spend principle (Brain Module). |

Two additional fields the audit's question 2 raised:

- `privacy_scope` — enum (`scenario_internal` / `universe_only` / `commons_publishable`). Drives whether the run's evidence stays host-only, lands in universe wiki, or eligible for commons promotion. Composes with the just-shipped session_trace_summary visibility model.
- `idempotency_key_constructor` — deterministic key shape for the scenario run (per the external-write authority design, #914). Without it: re-running the same scenario can't collapse retries.

Total: 11 fields. The original radar's 9 + privacy + idempotency, both required by other 2026-05 design landings.

## Five open question resolutions

### Q1 — Composability vs primitive (justified above)

The 11-field contract closes a structural gap (cross-run identity + artifact capture contract + cost cap + reproducibility) that chatbot composition does not reliably handle in <5 reasoning steps for long-horizon scenarios. Single-MCP-call scenarios COULD compose without this primitive, but the platform-build earns its keep at the multi-subtask + visual-artifact horizon.

### Q2 — Privacy at run time vs publish time

**Both, but at different layers.**

- Run-time enforcement: `privacy_scope` controls what artifacts the runtime CAPTURES. A `scenario_internal` scenario refuses to write artifacts to commons-readable paths. Enforced at the capture-emit boundary.
- Publish-time enforcement: per-piece chatbot-judged privacy (per `project_privacy_per_piece_chatbot_judged`) reviews evidence before it leaves the host. Composes with the session_trace_summary review lifecycle.

Aligned with the OpenTraces lane (PrivateTraceCommons) so the two converge: scenarios produce session_trace_summary memories that themselves carry visibility tags; the universe's gate composition handles enforcement.

### Q3 — Sandbox model

**The minimum sandbox is the existing `external_tool_node` multi-layer-authorized surface** (per PLAN.md Distribution Module): bundled handler signatures + binary signature verification + universe-level allow-list + per-software host approval + subprocess isolation. NO `seccomp=unconfined`. NO new sandbox primitive.

Scenarios that need browser automation reuse the existing `ui-test` Chrome path (one tab, persona-driven; per `feedback_user_sim_single_tab` and `feedback_user_sim_self_spawns_browser`). Scenarios that need a Docker sandbox are out of Slice 1; they require a separate design discussion + an `external_tool_node` capability registration.

The principle: candidate code runs inside whatever the universe's host policy allows; the platform does not ship a "scenario sandbox" of its own.

### Q4 — MCP scenarios vs live Claude.ai ui-test

**Compose, neither replaces the other.** Acceptance scenarios are the pre-launch harness layer; ui-test is the post-deploy clean-use proof. Concretely:

- During development: scenarios run against staging / sandboxed connectors / mock surfaces. Fast, repeatable, cheap. Multiple scenarios fan out across many surfaces.
- After deploy: ui-test (live Claude.ai chat with the production MCP connector) confirms real-user behavior matches scenario predictions. Slow, expensive, single-shot.

Hard Rule #11 stays in force: chatbot-facing changes require live Claude.ai `ui-test` for final acceptance. The scenario pack DOES NOT bypass this. A scenario can be the PR's primary acceptance proof IF AND ONLY IF its `target_surface` is not chatbot-facing OR the corresponding live ui-test has also been captured.

### Q5 — Branch optimization gate composability with Goals & Gates

**Decompose across three existing surfaces; no new gating primitive.**

- Goals & Gates owns the outcome ladder. Goal owner declares scenario-pack requirements as gate rung evidence ("rung R3 = 'all scenario X passes'").
- An `OptimizationRun` (future spec) runs candidate scenarios and emits EvalResult artifacts per the existing contract.
- The rung claim mechanism (existing in workflow/api/market.py per #899) consumes the EvalResult evidence and advances or refuses the rung claim.

Three existing surfaces compose. No new "branch optimization gate" primitive. The scenario pack is the evidence; the gate is the rung; the dispatch is the standard rung-claim flow.

## What Slice 2+ ships (preview)

Slice 1 (this PR): design + spec.

Slice 2: runtime. A `workflow/evaluation/scenario_runner.py` that takes an `AcceptanceScenario` contract + a candidate target_surface and produces a standard `EvalResult` artifact. The runner is thin — it dispatches to existing primitives (user-sim for ui_test_mission, run_branch for branch_run, MCP tool calls for mcp_call) and bundles their output as the scenario's evidence.

Slice 3: one concrete scenario shipped end-to-end. Recommendation: a small MCP scenario for an existing `goals` action (e.g., `goals action=propose` correctly creates a Goal record + binds the chatbot's request). Smallest possible real test of the full contract.

Slice 4: optimization gate. Wire scenario-pack requirements into the Goals & Gates rung-claim flow per Q5 above.

Slice 5: community scenario library. Per-Goal visibility for scenario packs; commons-promotable; remixable.

## Cross-frame consistency

All 5 scoping rules pass:

- **Rule 1 (minimal primitives):** ONE typed contract (11 fields) + a thin runtime in Slice 2. No new evaluator primitive. No new gate primitive. No parallel runner.
- **Rule 2 (community-build):** Scenarios are community-evolved per Goal. Platform ships the envelope; community ships the scenarios. The first concrete scenario in Slice 3 is a worked example, not a frozen taxonomy.
- **Rule 3 (privacy via community):** `privacy_scope` is a small enum (3 values) that the universe's gate composition can act on; no platform privacy taxonomy.
- **Rule 4 (commons-first):** Public scenarios become commons (Slice 5); private scenario data stays host-side; cross-universe remix via wiki.
- **Rule 5 (user-capability-axis):** ui-test composability covers browser-only; local-app users get full sandbox flexibility via `external_tool_node`.

## Composes with prior session work

- #904 (open-brain v2 slice A) — `cost_budget` field aligns with Brain Module bounded-spend principle
- #906 (open-brain v2 slice C) — `cost_estimate` tracking reuses the cost-ledger READ surface
- #914 (external-write authority) — `idempotency_key_constructor` field matches the strict-idempotency contract
- #915 (PLAN.md restructure) — Evolution & Evaluation Module is the authoritative reference
- #928 (4 audits) — APPROVE verdict from AgencyBench audit is the design authority
- #931 / #933 / #935 (PrivateTraceCommons) — `privacy_scope` aligns with session_trace_summary visibility model

## What this PR does NOT change

- `workflow/evaluation/process.py` — unchanged. The existing evaluator process continues to run unchanged.
- `EvalResult` schema — unchanged. Scenarios emit existing artifacts; no schema migration.
- `ui-test` skill — unchanged. Slice 4 may compose with it, but no changes to the skill itself.

## Open follow-ups for Slice 2 design

These are intentionally NOT resolved in Slice 1; Slice 2 design pass will resolve them based on concrete implementation contact:

1. **`evaluator_chain` ordering semantics** — is it strict ordered (fail-fast on first evaluator that fails) or aggregate (run all evaluators, combine scores)? Recommend aggregate-by-default with `fail_fast=true` opt-in.
2. **`artifact_requirements` enforcement strictness** — does a missing required artifact MARK the scenario FAILED or just emit a warning? Recommend FAILED with explicit error message.
3. **`setup` execution model** — does the platform run setup, or is it documentation that the scenario author provides for human readers? Slice 2 will pick one; recommend explicit-setup-action approach where setup is a list of MCP tool calls the runner executes pre-scenario.
4. **`cost_budget` enforcement** — hard kill on over-budget vs soft-warning + record? Recommend hard kill matching the Brain Module bounded-spend principle.
5. **Scenario versioning** — does updating a scenario create a new `scenario_id` (immutable per-version) or modify in place? Recommend immutable + supersedes_id chain matching the memory promotion pattern.

## Verification (Slice 1 acceptance check)

- [ ] All 11 fields in the spec map to a concrete failure mode they prevent
- [ ] The audit's 5 open questions are explicitly answered in the design
- [ ] No new evaluator primitive; no new sandbox primitive; no new gating primitive
- [ ] ui-test composability preserved per Hard Rule #11
- [ ] Cross-link from Evolution & Evaluation Module section of PLAN.md to this design (small PLAN.md amendment in a future PR or this one — either works)
- [ ] No AgencyBench code vendored
