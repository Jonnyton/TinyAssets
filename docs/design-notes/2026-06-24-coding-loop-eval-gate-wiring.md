# Design note: wire the coding-loop eval gate (output + trajectory)

**Filed:** 2026-06-24 · **Status:** PROPOSAL — needs navigator design + opposite-provider review before any build (research-gate per AGENTS.md §"Project Skills"). **Do not implement from this note as-is.**
**Basis:** `docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md` (G1); verification sweep 2026-06-24.

## The precise gap (verified, not assumed)

The vibe-coding whitepaper's thesis: *generation is solved; the remaining work is specification and verification.* It splits verification into **tests** (deterministic), **output-eval** (is the result correct?), and **trajectory-eval** (was the path/tool-calls sound?), with the rule "set the bar at the eval, not the demo."

A reality audit found this repo is **split by lane**:

- **Prose lane (fantasy-author):** bar IS at the eval. `domains/fantasy_daemon/phases/commit.py` runs a `StructuralEvaluator` + an LLM-as-judge `read_editorial` (a *different* model from the writer), and the accept/revert/second-draft verdict is gated by them. Real, running, gating.
- **Coding / community-patch lane (what AGENTS.md's verification norms are actually about):** bar is at the **demo**. All three eval components exist but are **disconnected**:
  1. `workflow/coding_packet_rubric.py` — `validate_coding_packet_rubric` (KEEP ≥ 9.0, child-output evidence, anti-overclaim contradiction checks). Imported by **exactly one file: its own test**. The governing doc `loop-outcome-rubric-v0.md` is `Status: proposal`, Phase 1 only.
  2. `workflow/evaluation/scenario_runner.py` + `scenario_dispatchers/mcp_call.py` — a genuine `AcceptanceScenario` harness (rubric fields: `evaluator_chain`, `pass_threshold.min_score`, `cost_budget`, `artifact_requirements`). But **no dispatcher is registered** and **no scenario instances exist as data**, so `run_scenario` returns `skip → no_dispatcher_registered` in production.
  3. `workflow/evaluation/process.py` — `evaluate_scene_process` IS a trajectory evaluator (scores `trace_handoff`, `tool_use`, `retrieval_choices`, `grounding_quality`, `stopping_behavior`) and IS called from `commit.py`. But the result is **logged, never enforced** — the verdict is computed before it from structural+editorial only.

So: the machinery is built and unit-tested; it is the **Phase-2 connections** that are missing. This is a wiring gap, not a greenfield build — which is exactly why it's high-leverage.

## Proposed minimal-but-real first slice (for navigator to refine)

Three connections, each independently shippable, smallest first:

**S1 — Register one runnable AcceptanceScenario in CI (output-eval).**
- Register `scenario_dispatchers.mcp_call` at universe startup (the dispatcher already exists; nothing reads it).
- Author 3–5 `AcceptanceScenario` instances as data (`evals/scenarios/*.json` or a registry module), e.g. `target_surface="mcp_call"`, `candidate_ref="goals.propose"`, with `pass_threshold={"min_score":0.9,"score_aggregation":"min"}` and an `evaluator_chain` asserting: response `status != error`, the Goal record exists, the binding handle is present.
- Add a `run_acceptance_suite()` entrypoint (mirror `scripts/proofs/daemon_memory_quality_eval.py`) and run it in CI. This is the "bar at the eval" beachhead.

**S2 — Wire `coding_packet_rubric` into `release_safety_gate` (output-eval, Phase 2).**
- `release_safety_gate` lives in `workflow/api/auto_ship_actions.py` (+ `extensions.py`). Feed `validate_coding_packet_rubric` into it so a patch with KEEP < 9.0 / missing child-output evidence / overclaim contradiction cannot auto-ship. This is the rubric doc's own unrealized Phase 2.

**S3 — Feed trajectory failures into the coding verdict (trajectory-eval enforcement).**
- The prose loop's `process.py` pattern, ported to the coding lane: a `tool_use` / `grounding_quality` trajectory failure should be able to force a re-draft or block, instead of only being written to audit notes.

## Why this is gated, not done here

- It changes **accept/auto-ship behavior** — owner sign-off territory (`Hard Rule 4`, autonomous defaults; storage/public-surface verification invariant).
- Defining the **pass bar** (min_score, which checks block vs warn) is a host/owner call, not an engineering default.
- Per the project's research-gate rule, a finding like this needs **opposite-provider review** (Codex/Cursor) re-checking sources + Workflow context before build, push, or rollout.

## Routing

1. `idea-refine` → navigator owns the design (PLAN.md Evaluator module).
2. Opposite-provider review (name the reviewer in STATUS.md) returns `approve` / `adapt` before S1 builds.
3. S1 → S2 → S3 as separate STATUS Work rows with explicit Files/Depends. S1 has no behavior-change risk (additive CI eval) and should go first.

## What is NOT proposed

- No new eval *framework* — the framework exists; this only connects it.
- No change to the prose lane (already correct).
- No model-routing / cost-tiering (separate, host-gated, conflicts with the always-latest norm).
