# Design note: wire the coding-loop eval gate (output + trajectory)

**Filed:** 2026-06-24 · **Status:** PROPOSAL — Codex opposite-provider review returned **ADAPT** (2026-06-24, via `mcp__codex__codex`; see §"Codex review" at the end). Inline corrections folded in below. Still needs navigator design before build. **Do not implement as-is — apply the adaptations.**
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

**Rubric dimensions (whitepaper p44 — grounds every `evaluator_chain`):** an eval
without an explicit rubric measures nothing. Score these five, the same way test
coverage gates a deploy: **task success**, **tool-use quality**, **trajectory
compliance**, **hallucination**, and **response quality**. The S1 asserts below
are the `task success` slice; the others are added as the suite grows.

Three connections, each independently shippable, smallest first:

**S1 — Register one runnable AcceptanceScenario in CI (output-eval).**
- **CORRECTED by review:** keep dispatcher registration **CI / suite-local**, NOT at universe startup — startup registration mutates runtime registry state and is therefore *not* the zero-behavior-change beachhead it was billed as. The dispatcher (`scenario_dispatchers/mcp_call.py:217` `register()`) also needs an injected `action_handler` + callable evaluators (`mcp_call.py:39-45`), so scenario *data* alone is insufficient.
- Author 3–5 `AcceptanceScenario` instances as data (`evals/scenarios/*.json` or a registry module), e.g. `target_surface="mcp_call"`, `candidate_ref="goals.propose"`, with `pass_threshold={"min_score":0.9,"score_aggregation":"min"}` and an `evaluator_chain` asserting: response `status != error`, the Goal record exists, the binding handle is present.
- Add a `run_acceptance_suite()` entrypoint (mirror `scripts/proofs/daemon_memory_quality_eval.py`) run in CI with a temp data dir. This is the "bar at the eval" beachhead.

**S2 — Wire `coding_packet_rubric` into the auto-ship gate (output-eval, Phase 2).**
- **CORRECTED by review:** there is no `release_safety_gate` function (the first-pass audit's grep matched prose, not a def). The real structural gate is `workflow.auto_ship.validate_ship_request` (`workflow/auto_ship.py:271`), reached via `_action_validate_ship_packet` (`workflow/api/auto_ship_actions.py:110` → `:165`). It **already** enforces child score < 9 (`auto_ship.py:377-392`) and required fields incl. `stable_evidence_handle` (`:71-78`). Only the rubric-**only** checks are missing — `child_candidate_patch_packet`, `release_evidence_bundle_complete`, contradictory-child-claim detection (`coding_packet_rubric.py:181,209,239`).
- Add just those missing checks, and update the **plugin mirror** copy (`packaging/claude-plugin/.../coding_packet_rubric.py:116`, per the mirror-parity rule). **Update packet producers + `tests/test_auto_ship.py:26-41` FIRST** — today's passing packets lack the rubric-only fields, so naive composition would flip valid packets to blocked.

**S3 — Feed trajectory failures into the coding verdict (trajectory-eval enforcement).**
- The prose loop's `process.py` pattern, ported to the coding lane: a `tool_use` / `grounding_quality` trajectory failure should be able to force a re-draft or block, instead of only being written to audit notes.
- **CORRECTED by review:** do NOT reuse `workflow/evaluation/process.py` directly — it is scene-loop specific (scene IDs, beats, `story_search`, `canon_breach`: `process.py:142-158,195-205,285`). Define a **coding-specific trajectory schema + thresholds + false-positive behavior** first, then gate. Lowest-confidence slice; do it last.

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

## Codex review (2026-06-24) — verdict: ADAPT

Independent opposite-provider review dispatched via `mcp__codex__codex` (read-only). Thread `019efd40-e343-7970-9c14-b3ca3e3803ff`. The diagnosis held up; the wiring details did not. Confirmed accurate: `validate_coding_packet_rubric` imported only by its test; `run_scenario` returns `no_dispatcher_registered`; zero `AcceptanceScenario` data instances; `process.py` trajectory eval computed-but-not-gating (`commit.py:162` verdict precedes `:222` eval). Corrected (folded into S1–S3 above):

1. **S2 wiring point was wrong** — no `release_safety_gate`; use `auto_ship.validate_ship_request` (`auto_ship.py:271`), which already covers part of the rubric. Add only the rubric-only checks + the plugin mirror; update producers/tests first or valid packets flip to blocked.
2. **S1 is not zero-behavior-change** if the dispatcher registers at startup — keep it CI/suite-local; it also needs an injected action-handler + evaluators, not just data.
3. **S3 can't reuse the scene evaluator** — define a coding-specific trajectory schema + thresholds before gating.

Gate status: build remains blocked pending navigator design that incorporates these three adaptations.

## S2 — warn-only mode landed (2026-06-25)

The safe half of S2 is on main: the coding-packet rubric is wired into
`validate_ship_request` (`workflow/auto_ship.py`) behind
`WORKFLOW_AUTO_SHIP_RUBRIC_MODE` (default **`warn`**). Warn mode computes the
rubric and attaches `rubric_warnings` to the decision dict but **never changes
pass/block behavior**, and the call is **fail-open** (a rubric exception yields
no warnings and never breaks the envelope gate). The enforce set is scoped to
the two genuinely-new, non-overlapping checks: `release_evidence_bundle_incomplete`
+ `child_run_not_completed_for_keep`. Tested warn/off/enforce (75 passed) +
Codex-reviewed **SHIP** — the FIX-NEEDED double-reporting of
`child_output_evidence_missing` / `contradictory_child_claim` was resolved by
narrowing the enforce set (those two need de-overlap logic before rejoining).
Plugin mirror rebuilt. **Zero production block-behavior change.**

### Turnkey enforce-flip (host-gated watched rollout)
1. **Producers first** (so valid packets don't flip to blocked under enforce) —
   and set each field **only where it is truthfully determinable**, never blindly
   (code-read 2026-06-25):
   - `child_run_status="completed"` IS truthful at the child-attachment producer
     `attach_existing_child_run` (`workflow/runs.py:~1330`, which already sets
     `selected_child_status="attached_completed"`). Add it there (+ receipt/return
     mirrors + plugin mirror), and verify it actually flows into the assembled
     ship packet the gate sees.
   - `release_evidence_bundle_complete` is a **release-assembly** claim (the
     bundle = diff + rollback + gate result + attached child evidence), NOT a
     child-attachment fact. It must be set by the ship-packet builder — the
     out-of-repo loop-content `release_safety_gate` prompt — and only once the
     full bundle is assembled. **Do NOT hardcode it `True` at child-attachment**:
     that asserts completeness before the bundle exists, the exact "fluent-but-
     wrong" claim the rubric guards against. Coordinate via the loop-content lane.
   This is why the producer migration is **navigator + loop-content design, not a
   mechanical field-add** — and why warn-only (already landed) is the safe state
   until that design lands.
2. **Tests**: once producers populate the fields, update `_valid_packet` in
   `tests/test_auto_ship.py` to carry them so enforce-mode tests reflect the
   new floor.
3. **Watched warn period**: leave the flag unset (`warn`); query the auto-ship
   ledger for decisions carrying `rubric_warnings` to measure the real failure
   rate (reuse `WORKFLOW_AUTO_SHIP_OBSERVATION_WINDOW_SECONDS`).
4. **Host flip**: once the warn rate is acceptable and opposite-provider review
   re-confirms, set `WORKFLOW_AUTO_SHIP_RUBRIC_MODE=enforce`. `off` is the
   instant kill-switch.
5. **Widen later**: re-add `child_output_evidence_missing` (the
   `child_candidate_patch_packet` half only) + `contradictory_child_claim`
   with envelope-overlap suppression.

## S3 — coding-lane trajectory evaluator (pure scorer landed 2026-06-25)

The third verification leg from the whitepaper — *was the execution **path**
sound?* — now has a coding-lane implementation, addressing the Codex ADAPT
point (don't reuse the scene evaluator; define a coding-specific schema +
thresholds + false-positive behavior first). **What landed is pure and
unwired** (`workflow/evaluation/coding_process.py`, imported only by its test) —
zero behavior change, the same harmless beachhead state `coding_packet_rubric.py`
itself started in. Gating is deferred (host-gated, like the enforce flip).

### Grounding (verified against code, not assumed)
The coding lane emits **no `quality_trace`** (that is prose-lane only). Its path
data is assembled from a run record + `run_events` + `provider_calls` +
`child_failures` + `__system__` telemetry, all keyed by `run_id`
(`workflow/runs.py`). So this is genuinely new, not a port. Real signals scored:
`recursion_limit_applied` (runs.py ~2328), `provider_calls[].attempts/degraded`
(~2223), `failure_class` from `_classify_failure` (~4006) + `ACTIONABLE_BY`,
`child_failures[].failure_class` (`ChildFailure`, ~1953), receipt-waiting gate
(~2410), `run_events` node statuses (~2178).

### Schema
`evaluate_coding_trajectory(trajectory) -> CodingTrajectoryEvaluation`, kind
`process` (mirrors `process.py`). Five weighted dimensions, each returning
`applicable` / `passed` / `score` / `observation`:

| Dimension | Weight | Signal | Heaviest because / lightest because |
|---|---|---|---|
| `terminal_health` | 0.25 | `run_status` + `failure_class` | clean terminal vs infra-failure path |
| `child_integrity` | 0.25 | `child_failures`, receipt-waiting | child evidence grounds any coding KEEP |
| `provider_efficiency` | 0.20 | `provider_calls[].attempts/degraded` | excessive retries / degraded = unhealthy path |
| `recursion_discipline` | 0.15 | `recursion_limit_applied` (+empty output) | negative signal; absence is good |
| `node_progression` | 0.15 | `run_events` statuses | lightest: `step_index` is an opaque cursor |

### False-positive behavior (the Codex-required piece)
1. **Only positive evidence deducts.** A signal that is simply absent makes its
   check `applicable=False` and is **excluded from the aggregate** — never a
   failure. (Thin gate-time packets therefore don't manufacture failures.)
2. **`< 2` applicable checks → `skip`** (inconclusive), surfaced via the
   reserved `EvalResult` not-applicable score `-1.0`. Warn mode emits nothing,
   and any future enforce mode never blocks, on insufficient data.
3. **A conclusive eval `fail`s via either path:** (a) a *critical* applicable
   check fails — `terminal_health` or `child_integrity`, the two `.25`-weight
   ground-truth dims — in which case it fails regardless of aggregate (so a hard
   terminal failure or a broken child run can't be offset by clean modifier
   checks); or (b) a *non-critical* applicable check fails **and** the weighted
   aggregate is below `pass_threshold` (default 0.8). `>= pass_threshold` passes
   for non-critical failures, matching the rubric's `>= 9.0` KEEP convention.

### Separate axis — no double-report with the output rubric (S2 lesson)
This scores **path quality** (a number); `validate_coding_packet_rubric` scores
**claim validity** (block rules). Signals they share (`recursion_limit_applied`,
child attachment) are *quality deductions* here, not re-emitted block rules.
When this is later wired into the ship gate it must surface on its own
`trajectory_warnings` channel, **distinct from `rubric_warnings`** — exactly the
de-overlap the S2 enforce-set narrowing taught us. Two source normalizers exist:
`coding_trajectory_from_packet` (thin, gate-time) and `coding_trajectory_from_run`
(rich, post-run from run record + events).

### Wiring plan — warn + enforce LANDED 2026-06-25 (Codex SHIP)
Same warn→enforce ladder as S2, on a separate channel:
1. **Warn-only — LANDED.** `validate_ship_request` computes
   `evaluate_coding_trajectory(coding_trajectory_from_packet(packet))` behind
   `WORKFLOW_AUTO_SHIP_TRAJECTORY_MODE` (default `warn`; `off` skips). It attaches
   `trajectory_warnings` to BOTH decision dicts and NEVER touches `violations`;
   one record per failing applicable check, emitted only when the eval is
   conclusive AND verdict==`fail` (= what enforce blocks, so the warn rate
   measures the real prospective block-rate). Fail-open. Ledger: additive
   `trajectory_warnings_json` column (forward-compat) populated by
   `attempt_from_decision`. **Zero block-behavior change** (Codex-verified).
2. **Watched period — ready.** `summarize_trajectory_warnings(universe_path)`
   aggregates `{total_attempts, attempts_with_warnings, check_counts}` (counts by
   `check`, mirrors `summarize_rubric_warnings`) to measure the real path-failure
   rate before any gating discussion.
3. **Enforce PATH — LANDED 2026-06-25 (Codex SHIP, thread `019f00f9`).**
   `WORKFLOW_AUTO_SHIP_TRAJECTORY_MODE=enforce` promotes a CONCLUSIVE path-quality
   FAIL to ONE blocking violation `{rule_id: trajectory_path_unsound}` on its own
   channel (mirrors §6.4 rubric enforce; distinct axis from the output rubric, so
   no same-rule double-report). Default `warn`; invalid → `warn`; `off` is the
   kill switch — so **zero block-behavior change until a host flips it.** Now at
   off/warn/enforce parity with S2.
4. **Host FLIP — DONE 2026-06-25 (host-approved).** `enforce` is live + durable
   on the droplet (verified; see Gate status). Env audited; the gate is the
   on-demand `validate_ship_packet` MCP action — **not exercised by the
   autonomous loop** (no `.ship_attempts` ledger on the droplet, confirmed
   2026-06-26), so enforce currently blocks nothing and accumulates no warn data.
   **Post-flip monitoring (still open, but gated on the gate being exercised):**
   if/when `validate_ship_packet` starts being called and `summarize_trajectory_warnings`
   shows `child_integrity` is dominated by thin-packet / receipt artifacts rather
   than real bad paths, wire the richer run-event-backed `coding_trajectory_from_run`
   source (already built + tested in `coding_process.py`, just unwired). Wiring it
   now would be speculative — no data, no current effect — so it stays ready, not
   built into the gate path.

### Gate status
Pure scorer + 31 tests SHIP'd (Codex, thread `019f0022`). Warn-only gate wiring +
ledger observability SHIP'd next (zero block-behavior change). **Enforce path
LANDED 2026-06-25** (Codex SHIP, thread `019f00f9`, no blocking findings) — S3 at
full off/warn/enforce parity with S2. **ENFORCE FLIP LIVE + verified 2026-06-25**
(host-approved, overriding the warn-period gate): the running droplet daemon has
`WORKFLOW_AUTO_SHIP_{RUBRIC,TRAJECTORY}_MODE=enforce` (`docker exec ... printenv`),
durable in systemd's `/opt/workflow/compose.yml`, daemon `healthy`, loopback +
public canary green; repo config flipped to match (`deploy/compose.yml` +
`workflow-env.template`, 3836d073). Because the gate is the on-demand
`validate_ship_packet` MCP action (not an autonomous-loop gate), enforce blocks
only explicit ship-validation calls and cannot wedge the loop. Watch (flip-time
item (a) above): the run-event-backed source is still worth wiring if
`child_integrity` proves thin-packet-noisy — track via `summarize_trajectory_warnings`.
