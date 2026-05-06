# OptimizationRun (Slice 2) — Rule-1 Atomization Gate

> **HISTORICAL — as-of 2026-05-02.** This note captures navigator framing as of 2026-05-02. The "Slice 1 commit-flow note" section below references work-in-progress state from that date (uncommitted Slice 1 files, "When Codex pushes...", "Recommendation for Codex...") that has since changed. **Future agents must revalidate current branch / Slice state in `STATUS.md` and recent activity logs before acting on any recommendations in this note.** Per Codex's HOLD on PR #548 — cross-AI artifact-safety review.

Pre-spec gate set by Claude Code navigator on 2026-05-02 ahead of Codex's
OptimizationRun draft. Goal: minimize new primitives by reusing existing
ids and concepts wherever possible, per Scoping Rule 1 (minimal primitives,
PLAN.md §"Scoping Rules").

Source memo (Claude Code internal): `.claude/agent-memory/navigator/2026-05-02-optimizationrun-rule1-prereview.md`.
Reproduced here in full for cross-provider visibility.

## Headline framing

**OptimizationRun = parametric Run with a fitness target, funded by a
Capacity Grant.** Three existing concepts (RunOutcome + Evaluator + the
new capacity-grant / executor-backend split from
`docs/design-notes/2026-05-01-hostless-byok-cloud-daemon-capacity.md`)
compose to give the 4th feature. **No new tier. No new spend primitive.
No parallel lifecycle FSM.**

The user-facing brand stays `autoresearch` per
`project_autoresearch_brand_recognition`; `OptimizationRun` is the
engine-internal type name. Slice 2 spec must name the brand-vs-engine
split explicitly.

## Must-ship vs reuse — bar set on the audit's 10-field shape

| Candidate field | Verdict | Why |
|---|---|---|
| `run_id` | **REUSE** | RunOutcome's id space — this is a *kind* of run, not a separate id space |
| `target_kind` | **MUST-SHIP** | enum (node / branch / evaluator) |
| `target_ref` | **MUST-SHIP** | references existing ids; no separate type needed |
| `baseline_ref` | **MUST-SHIP** | no existing field for "the thing being improved" |
| `optimization_spec_ref` | **MUST-SHIP** | the `program.md` of the 3-file autoresearch pattern |
| `editable_surface` | **MUST-SHIP** | typed write-scope; closes a structural gap |
| `evaluator_chain_ref` | **REUSE** | reuse Evaluator id from Slice 1 |
| `search_policy` | **MUST-SHIP** | enum + typed params |
| `budget` | **REUSE → `capacity_grant_ref`** | NOT raw cents/tokens; the grant carries the budget |
| `merge_policy` | **MUST-SHIP** | enum |
| `status` | **REUSE** | RunOutcome.status |

**Net: 6 must-ship + 5 reuses out of the 10 audit fields.**

## Anti-patterns to flag in the spec

The Slice 2 draft will be reviewed against these. Each is a "if you see
this, push back hard" line for the navigator review:

1. New id space for `run_id` instead of reusing RunOutcome's.
2. Raw budget fields (cents / tokens / etc.) instead of `capacity_grant_ref`.
3. New evaluator-chain dataclass instead of reusing the Evaluator id.
4. **`OptimizationCandidate` as a separate primitive with its own table.**
   Most likely to drift this way. Pressure-test hard: a candidate is
   most likely a child Run (parametric variant) rather than its own
   primitive. Tables are forever; convenience types should compose.
5. Free-form code blob for `search_policy` instead of enum + typed params.
6. Lifecycle FSM that doesn't compose with `RunOutcome.status`.
7. Inlined `optimization_spec` content in the row instead of `_ref` to
   the spec artifact.

## Capacity-grant alignment check

OptimizationRun's `budget` reuse is `capacity_grant_ref`. That makes
OptimizationRun a *consumer* of the capacity-grant substrate, not a
parallel primitive. When a user kicks off an OptimizationRun:

- The grant says how much spend / which providers / which executor
  backends are eligible.
- The OptimizationRun's `editable_surface` says what it's allowed to
  rewrite.
- The `evaluator_chain_ref` (Slice 1) says how candidate runs get scored.
- Each candidate is a Run executed under the grant; results aggregate
  into the OptimizationRun's overall outcome.

That composition is the architecture. Any field that doesn't fit one
of those four roles is a candidate for the convenience-vs-primitive
pressure-test.

## Brand alignment

User-facing verb is `autoresearch` per `project_autoresearch_brand_recognition`
(karpathy reference, instant user excitement). MCP-facing surface uses
`autoresearch_node` / `autoresearch_branch`. Engine-internal type is
`OptimizationRun`. Slice 2 spec must name this split explicitly so the
chatbot, the MCP descriptions, and the engine code don't drift on
terminology.

## Slice 1 commit-flow note

Slice 1 (`workflow/evaluation/schema.py` + `tests/test_evaluator_result_schema.py`
+ `__init__.py` + `process.py` changes) is currently uncommitted in the
cursor checkout's working tree. When Codex pushes, verifier on the
Claude side will run a wider regression sweep against
`origin/main + Slice 1` (~6+ evaluation/judge/evaluator/run test files)
to catch any score-range-validator blast radius — the `__post_init__`
range check on `EvalResult.score` is the only behavioral (non-additive)
bit of Slice 1 and warrants a broader sweep than the 3-file targeted run.

Recommendation for Codex: sweep the same files on your side before
pushing, then verifier broadens post-push as second eye.
