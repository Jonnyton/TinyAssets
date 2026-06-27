# ExperienceLesson — minimal schema spec

**Status:** Slice 1 minimal schema (per `docs/design-notes/2026-05-02-experience-pool-and-group-evolution.md`).
**Authority:** Claude review APPROVE verdict (`docs/audits/2026-05-02-experience-pool-claude-review.md`).
**Date:** 2026-05-20.

---

## Purpose

Specify the `experience_lesson` memory_kind that ships in Slice 2 (per the design note's sequenced slice plan). Slice 1 ships the spec only; Slice 2 ships the memory_kind addition to the Brain Module's registry + a lifecycle test + a wiki composition-pattern page.

## Inheritance

An `experience_lesson` is a `daemon_brain_entries` row (existing table, no schema migration) where `memory_kind = "experience_lesson"`. The existing row schema covers identity, ownership, content, metadata, lineage, and promotion state. This spec defines the **content shape** (what goes in `content` + `metadata_json`) — not a new table.

Same pattern as `session_trace_summary` shipped in #933.

## Fields (in `metadata_json`)

| Field | Type | Required | Purpose |
|---|---|---|---|
| `source_run_id` | string | required | Lineage: which run produced this lesson. Format `run:<id>`. |
| `source_candidate_id` | string | optional | Sub-lineage: which specific candidate within that run. Format `candidate:<id>`. |
| `goal_id` | string | required | Which Goal this lesson belongs to. Drives cross-branch discovery. Format `goal:<id>`. |
| `branch_id` | string | required | Which Branch produced the lesson. Attribution + lineage. Format `branch:<def-id>`. |
| `lesson_kind` | enum | required | One of: `failure_mode`, `intervention`, `pattern`, `holdout_signal`, `outcome_link`. Constrains the shape of subsequent fields. |
| `failure_mode` | object | optional | When `lesson_kind=failure_mode`: `{"signature": "<short id>", "trigger": "<text>", "evidence_pattern": "<text>"}`. Cross-references the existing `failure_mode` memory_kind. |
| `intervention` | object | optional | When `lesson_kind=intervention`: `{"description": "<text>", "change_kind": "<add|remove|reorder|configure>", "applied_to": "<branch_def_id|node_id|evaluator_id>"}`. |
| `observed_delta` | string | required | What changed between before and after the lesson. Free-text 100-1000 chars OR structured JSON if `lesson_kind=holdout_signal` (see below). |
| `evidence_refs` | list[string] | required | URIs of supporting evidence. At least one required (no opinion-as-lesson). |
| `confidence` | float | optional | Lesson author's self-assessed confidence, 0.0-1.0. Lazy unless query patterns need it. |
| `held_out_scenario_refs` | list[string] | optional | When `lesson_kind=holdout_signal`: list of `scenario_id` refs the lesson was evaluated against. Composes with AcceptanceScenario substrate (#936). |

## Content field (the `content` column)

100-800 character narrative summary of what was learned. The narrative SHOULD:

- State the context (what was being attempted).
- State the observation (what was learned, in plain language).
- Reference the evidence (cite evidence_refs by URI).
- Note replicability (was this seen N times before? — if so, the lesson is stronger).

The narrative SHOULD NOT:

- Reproduce raw trace payloads.
- Reproduce sensitive content.
- Make claims unsupported by `evidence_refs`.

## lesson_kind variations (shape constraints)

| `lesson_kind` | Required additional fields | Example |
|---|---|---|
| `failure_mode` | `failure_mode` object | "Provider chain exhaustion when claude-code binary missing" |
| `intervention` | `intervention` object | "Add explicit placeholder-validation gate before simulator step" |
| `pattern` | None (free narrative) | "Branches that bind to small Goals (≤3 sub-rungs) merge 4x faster than larger Goals" |
| `holdout_signal` | `observed_delta` as structured JSON + `held_out_scenario_refs` | `{"scenarios_passed": 7, "scenarios_failed": 1, "regression_set": [...]}` |
| `outcome_link` | `evidence_refs` includes a real-world outcome URI | "Markovic publication arXiv:XXXX accepted; lineage traces to lesson XYZ" |

## Promotion state machine (existing — no change)

Per open-brain v2 slice A (#904), the existing state machine applies unchanged:

- candidate → accepted → promoted → superseded
- candidate → accepted → rejected
- candidate → rejected
- accepted → superseded
- promoted → superseded

Terminal states: `rejected`, `superseded`. From `promoted`, only `superseded` is reachable.

## Visibility-state interaction

Per the PrivateTraceCommons pattern (settled in #935): `visibility` and promotion `state` are orthogonal; no platform enforcement coupling them. Universes compose enforcement via gates per Goal.

For `experience_lesson` specifically:

- `visibility=host_private` (default): lesson stays host-side; universe's gate composition decides whether it can promote.
- `visibility=borrowable_role_context`: lesson readable across branches within the universe.
- `visibility=published`: lesson promoted to commons wiki; readable cross-universe; remixable.

The Goal's universe owner declares which visibility values are eligible for which states via the Goal scope manifest (per the external-write authority design landed in #914).

## Example records

### Example 1 — intervention lesson (Markovic)

```json
{
  "memory_kind": "experience_lesson",
  "content": "When the Markovic methodology check fails on patient placeholder consistency, the parent run usually returned a partial outcome and the simulator snapshot tar was missing. Adding an explicit placeholder-validation gate before the simulator step caught 3 prior false-passes in retrospective evaluation.",
  "metadata_json": {
    "source_run_id": "run:markovic-2026-05-15-abc",
    "source_candidate_id": "candidate:fingerprint_rd_v3.1",
    "goal_id": "goal:markovic-publication",
    "branch_id": "branch:markovic_fingerprint_rd_v3",
    "lesson_kind": "intervention",
    "intervention": {
      "description": "Add explicit placeholder-validation gate before simulator step",
      "change_kind": "add",
      "applied_to": "branch:markovic_fingerprint_rd_v3"
    },
    "observed_delta": "3 prior runs (run:markovic-2026-05-08-ghi, run:markovic-2026-05-12-def, run:markovic-2026-05-15-abc) that produced partial outcomes with missing simulator artifacts would have been caught at the validation gate. New gate produces FAILED early with typed failure_mode=patient_placeholder_inconsistent.",
    "evidence_refs": [
      "evalresult://run-markovic-2026-05-15-abc",
      "evalresult://run-markovic-2026-05-12-def",
      "evalresult://run-markovic-2026-05-08-ghi"
    ],
    "confidence": 0.8
  },
  "visibility": "borrowable_role_context",
  "promotion_state": "candidate"
}
```

### Example 2 — holdout signal (cross-Goal)

```json
{
  "memory_kind": "experience_lesson",
  "content": "Branch candidate Y outperformed baseline X by 12 percentage points across the held-out scenario set (7 pass / 1 fail vs. 4 pass / 4 fail). The single failure was scenario_id=scenario:cross-domain-edge-case, which baseline X also failed. Signal: Y's intervention generalizes within the held-out set.",
  "metadata_json": {
    "source_run_id": "run:experiment-2026-05-18-xyz",
    "goal_id": "goal:markovic-publication",
    "branch_id": "branch:fingerprint_rd_y_candidate",
    "lesson_kind": "holdout_signal",
    "observed_delta": "{\"scenarios_passed\": 7, \"scenarios_failed\": 1, \"baseline_passed\": 4, \"baseline_failed\": 4, \"regression_set\": []}",
    "evidence_refs": [
      "evalresult://run-experiment-2026-05-18-xyz"
    ],
    "held_out_scenario_refs": [
      "scenario:markovic-methodology-pass",
      "scenario:markovic-placeholder-validation",
      "scenario:markovic-simulator-roundtrip",
      "scenario:markovic-publication-package",
      "scenario:cross-domain-edge-case",
      "scenario:markovic-co-author-handoff",
      "scenario:markovic-arxiv-submission-dry-run",
      "scenario:markovic-retrospective-replay"
    ],
    "confidence": 0.7
  },
  "visibility": "borrowable_role_context",
  "promotion_state": "candidate"
}
```

## Acceptance checklist

Slice 1 (this PR) passes when:

- [ ] All 11 required/optional fields have a concrete purpose
- [ ] lesson_kind enum has 5 values with shape constraints per kind
- [ ] All 5 audit open questions have explicit resolutions (per design note)
- [ ] No new typed surface beyond the memory_kind addition (Slice 2)
- [ ] No new evaluator primitive
- [ ] No new merge/diversity policy enum
- [ ] EvalResult reused verbatim
- [ ] Held-out evaluation reuses AcceptanceScenario substrate
- [ ] Visibility-state matches PrivateTraceCommons pattern (no platform enforcement)

Slice 2 (memory_kind + test, future PR) passes when:

- [ ] `experience_lesson` appears in `tinyassets/daemon_brain.py::MEMORY_KIND_REGISTRY` with one-line description
- [ ] Plugin mirror parity ✓
- [ ] One lifecycle test in `tests/test_daemon_brain.py` covers the new kind through candidate → accepted → promoted
- [ ] Wiki composition-pattern page `pages/plans/composing-experience-pool-queries.md` exists in commons with a worked example
- [ ] No new MCP actions added
- [ ] No new SQL tables added

Slice 3+ (SkillOps trial, GroupEvolutionRun runtime, community library): each ships as separate PRs against its own slice plan.

## What is NOT in this spec

Out of scope per the audit verdict's REAFFIRMS:

- ❌ Separate `experience_lesson` table (use the existing `daemon_brain_entries` table)
- ❌ Separate `experience_pool` table (use wiki composition pattern)
- ❌ Typed `experience_pool action=summarize` MCP action (composition is enough)
- ❌ GroupEvolutionRun runtime (dormant spec only)
- ❌ Platform `merge_policy` enum (free-text per Goal)
- ❌ Platform `diversity_policy` enum (free-text per Goal)
- ❌ Parallel evidence shape (EvalResult reused verbatim)
- ❌ Held-out evaluation primitive separate from AcceptanceScenario (held-out sets are scenario packs)
- ❌ Platform-enforced visibility coupling (community composes gates per the PrivateTraceCommons pattern)

Future slices may revisit any of these IF concrete usage proves the composition pattern is insufficient. Default expectation per the APPROVE verdict's scope discipline: not needed.
