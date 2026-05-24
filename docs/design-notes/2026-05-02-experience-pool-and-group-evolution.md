# ExperiencePool + GroupEvolutionRun — Slice 1 design

**Status:** Slice 1 design (per Claude review APPROVE verdict).
**Authority:** `docs/audits/2026-05-02-experience-pool-claude-review.md` (verdict: APPROVE with scope discipline).
**Radar source:** `docs/audits/2026-05-02-frontier-project-radar.md` (GEA/EvoSkill frontier finding).
**Touches:** Evolution & Evaluation Module (primary), Brain Module (ExperienceLesson as memory_kind), Goals & Gates Module (composes with branch lineage).
**Date:** 2026-05-20.

---

## What's IN scope

Three concepts shipped as a sequenced slice plan:

1. **ExperienceLesson** — a new memory_kind in the existing Brain Module registry. The atom of group evolution: one typed lesson record per learned-thing-from-a-run. **Slice 1 ships the schema.**
2. **ExperiencePool** — a read-only aggregation view over typed lessons + existing artifacts (EvalResult, branch lineage, attribution). **Slice 1 ships the contract; Slice 2 ships the read-model code.**
3. **GroupEvolutionRun** — a dormant run-type spec that pressure-tests OptimizationRun's interface before that primitive is locked. **Slice 1 ships the dormant spec; no runtime execution.**

This matches the staged discipline the audit verdict approved: schema first, read-model second, dormant run-type spec third. No write paths for ExperiencePool in Slice 1; no runtime for GroupEvolutionRun ever in this lane.

## What's OUT of scope

Per the audit verdict's REAFFIRMS:

- ❌ No separate local-only self-evolution harness.
- ❌ No optimization against one fixed validation set without holdouts.
- ❌ No promotion of private failures into public reusable lessons without per-piece privacy review (composes with PrivateTraceCommons lane #931/#933/#935).
- ❌ No EvoSkill `.claude`-first layout copy (Workflow is cross-provider; canonical is `.agents/skills/`).
- ❌ No DGM isolated-coding-agent focus.
- ❌ No conflating benchmark progress with real-world outcome progress.
- ❌ No GroupEvolutionRun runtime execution in Slice 1 — dormant spec only.
- ❌ No new platform "merge policy" enum (community-evolved per Goal; see Q3 resolution below).

## ExperienceLesson — the atom

Per the audit's open question 1: ExperienceLesson SHOULD ship as a new memory_kind in the existing Brain Module registry, NOT as a separate typed surface. Same pattern as `session_trace_summary` (landed via #933). The recommendation: start as a memory_kind; promote to a separate surface only if real query patterns demand it.

This composes:

- With the existing `daemon_brain_entries` table (no schema migration).
- With the existing promotion state machine (candidate → accepted → promoted → superseded).
- With the existing memory_kinds registry (just adds one entry).
- With the existing visibility tags (per the community-composes-enforcement pattern from PrivateTraceCommons).

### 10-field shape (in `metadata_json`)

| Field | Required | Purpose |
|---|---|---|
| `source_run_id` | required | Which run produced this lesson. Lineage. |
| `source_candidate_id` | optional | Which specific candidate within that run. Sub-lineage. |
| `goal_id` | required | Which Goal this lesson belongs to. Drives cross-branch discovery. |
| `branch_id` | required | Which Branch produced the lesson. Attribution + lineage. |
| `lesson_kind` | required | Enum: `failure_mode` (something broke; here's the trigger), `intervention` (a change that worked), `pattern` (a recurring structure observation), `holdout_signal` (held-out evaluation result), `outcome_link` (real-world outcome tied to evidence). |
| `failure_mode` | optional | If `lesson_kind=failure_mode`, the structured failure signature (matches the existing `failure_mode` memory_kind for cross-reference). |
| `intervention` | optional | If `lesson_kind=intervention`, the structured description of what was changed. |
| `observed_delta` | required | What changed between before and after the lesson. Free-text or structured per lesson_kind. Required so a lesson without a delta is rejected. |
| `evidence_refs` | required | URIs of supporting evidence: `evalresult://<id>`, `output://<path>`, `wiki://bug-NNN`. Required so lessons without evidence are rejected (no opinion-as-lesson). |
| `confidence` | optional | Float 0.0-1.0. Lesson author's self-assessed confidence. Lazy unless query patterns need it. |

Stored in `metadata_json` of a `daemon_brain_entries` row where `memory_kind=experience_lesson`. The `content` column carries a 100-800 character narrative summary of what was learned, similar to `session_trace_summary`.

### Example record

```json
{
  "memory_kind": "experience_lesson",
  "content": "When the Markovic methodology check fails on patient placeholder consistency, the parent run usually returned a partial outcome and the simulator snapshot tar was missing. Adding an explicit placeholder-validation gate before the simulator step caught 3 prior false-passes.",
  "metadata_json": {
    "source_run_id": "run:markovic-2026-05-15-abc",
    "source_candidate_id": "candidate:fingerprint_rd_v3.1",
    "goal_id": "goal:markovic-publication",
    "branch_id": "branch:markovic_fingerprint_rd_v3",
    "lesson_kind": "intervention",
    "intervention": "Add explicit placeholder-validation gate before simulator step",
    "observed_delta": "3 prior runs that produced partial outcomes with missing simulator artifacts would have been caught at the validation gate. New gate produces FAILED early with typed failure_mode=patient_placeholder_inconsistent.",
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

## ExperiencePool — the aggregation

Per the audit's open question 2: **does the platform need a typed `experience_pool action=summarize` action, or is wiki-based composition enough?**

Slice 1 answer: **composition is enough at the read-only level for Slice 1. Ship a wiki composition pattern, NOT a new action.** The aggregation is computable from existing primitives:

- `brain action=query memory_kind=experience_lesson + filter:{goal_id, branch_id}` — gets the lessons
- `branches action=list goal_id=...` — gets bound branches
- `goals action=get goal_id=...` — gets gate ladder + outcome refs
- `wiki action=search query=...` — gets cross-references

A chatbot composes "what has this branch family learned?" from these in <5 reasoning steps. Per Scoping Rule 2, don't ship the action; ship the wiki composition pattern as a worked example.

Slice 2 evaluates whether real usage proves this unreliable. If the composition takes >5 reasoning steps consistently, Slice 2 may promote a typed `experience_pool` aggregator. Default expectation: not needed.

### What Slice 1 ships for ExperiencePool

- The `experience_lesson` memory_kind is the storage substrate.
- A wiki composition-pattern page (`pages/plans/composing-experience-pool-queries.md`) documents the aggregation pattern.
- A worked example: "what has the Markovic branch family learned in the last 30 days?" walked end-to-end from raw `brain action=query` to a synthesized digest.

No new platform code beyond the memory_kind addition.

## GroupEvolutionRun — the dormant spec

Per the audit's open question 5 (held-out evaluation set provenance): GroupEvolutionRun is the right surface to spec dormantly because it pressure-tests OptimizationRun's interface before that primitive is locked. The spec lives here; no runtime ships in this lane.

### 7-field shape (dormant; subject to OptimizationRun refinement)

| Field | Purpose |
|---|---|
| `group_evolution_run_id` | Stable identity, format `gevorun:<slug>`. |
| `goal_id` | Which Goal this run advances. |
| `parent_branch_refs` | List of starting branches that share lessons. Diversity-seed set. |
| `experience_pool_ref` | Composed pool definition (which lessons to draw from — by goal_id + filter set). |
| `evaluator_chain_ref` | Reference to the locked evaluator chain. Per Evolution & Evaluation safety model: candidate generators cannot edit this. |
| `diversity_policy` | Free-text per Goal (per Q3 resolution below). |
| `merge_policy` | Free-text per Goal (per Q3 resolution below). |

### Why dormant

Three reasons:

1. **No runtime user pull yet.** Per `project_real_world_effect_engine`, ship runtimes when users ask. No chatbot is asking for a multi-candidate group-evolution run today.
2. **OptimizationRun substrate not yet locked.** The audit's Q4 (EvalResult coupling discipline) requires GroupEvolutionRun to reuse OptimizationRun's contract verbatim. Until that substrate exists, GroupEvolutionRun is a placeholder.
3. **Pressure-test value.** Having the dormant spec lets the OptimizationRun design pass say "does my interface support GroupEvolutionRun's needs?" without committing to a runtime.

If/when a runtime is needed, it should ship as a separate slice with its own design discussion + opposite-provider review.

## Five open question resolutions

### Q1 — ExperienceLesson as memory_kind vs separate surface

**Memory_kind.** Recommendation from the audit is to start as a memory_kind, promote to separate surface only if real query patterns demand it. Matches the just-shipped `session_trace_summary` pattern (#933). One new line in `MEMORY_KIND_REGISTRY`; no new tables; no schema migration. If real usage shows query patterns the existing memory query interface doesn't serve well, Slice 2+ promotes to a typed surface.

### Q2 — Aggregation read model composability

**Composition is enough at Slice 1.** Ship the wiki composition pattern as a worked example; do NOT ship a typed `experience_pool action=summarize` action. Per Scoping Rule 2. Slice 2 may revisit if real usage proves composition unreliable.

### Q3 — merge_policy + diversity_policy variations

**Free-text per Goal, not platform enum.** Per `feedback_design_questions_apply_scoping_rules_first`: open-ended variations are community-build candidates. The audit's open question hints at this directly: "open-ended variations like 'merge policy' are community-build candidates. Recommend free-text annotation + community-evolved patterns rather than a frozen enum."

GroupEvolutionRun's `merge_policy` and `diversity_policy` fields are free-text strings the Goal owner declares. Community evolves the patterns in commons wiki pages. No platform enum; no platform enforcement.

### Q4 — EvalResult coupling discipline

**Reuse EvalResult verbatim. No parallel evidence shapes.**

ExperienceLesson's `evidence_refs` carry URIs that point at existing EvalResult IDs. GroupEvolutionRun (when it has a runtime, post-Slice 1) emits standard EvalResult per the existing contract — no parallel "group eval result" type.

This is the same Rule 1 discipline from the Origin Quantum review (DEFER verdict #928): quantum results map to existing EvalResult. ExperiencePool does the same.

### Q5 — Held-out evaluation set provenance

**Held-out sets are scenario packs.** This composes with the AcceptanceScenario lane (#936 / 560643a):

- The held-out set for a Goal's learning is a set of `AcceptanceScenario` records the Goal owner declares.
- ExperienceLesson with `lesson_kind=holdout_signal` reports per-scenario PASS/FAIL outcomes from a held-out run.
- The provenance question reduces to: "which scenarios are held-out vs in-training?" — answered by the Goal owner via the scenario records themselves (not a new platform field).

Reuse the just-merged AcceptanceScenario substrate; no new "held-out set" primitive.

## Cross-frame consistency

All 5 scoping rules pass:

- **Rule 1 (minimal primitives):** ONE new memory_kind value + ONE dormant spec (no runtime) + ONE wiki composition pattern. Three concepts but only one shipped runtime element (the memory_kind).
- **Rule 2 (community-build):** Aggregation is wiki composition; `merge_policy` and `diversity_policy` are free-text community-evolved per Goal; lesson clustering / failure-mining heuristics are community-evolved.
- **Rule 3 (privacy via community):** Lessons carry visibility tags (same as session_trace_summary); community composes enforcement gates per Goal.
- **Rule 4 (commons-first):** Promoted lessons become commons; private lessons stay host-side; cross-Goal lesson remix via wiki.
- **Rule 5 (user-capability-axis):** Lesson capture works browser-only the same as local-app (the lesson is a memory write, not a local-file operation).

## What Slice 1 ships (concretely)

- This design note.
- `docs/specs/2026-05-02-experience-pool-minimal-schema.md` (the spec).
- The `experience_lesson` memory_kind addition is **NOT** in Slice 1 code — Slice 2 ships that, following the same pattern as `session_trace_summary` (#931 spec + #933 implementation).
- A wiki composition-pattern page (`pages/plans/composing-experience-pool-queries.md`) will be published as a follow-up after Slice 1 lands.

## Slice 2+ preview

Slice 2: implementation. Adds `experience_lesson` to `MEMORY_KIND_REGISTRY` (canonical + plugin mirror). Adds one lifecycle test on the new kind. Publishes the wiki composition-pattern page. Mirror parity ✓. ~15 LOC + 1 test + 1 wiki page. Tiny.

Slice 3: SkillOps trial. Apply EvoSkill-style failure mining to ONE existing project skill: identify recurring failures via memory_kind=failure_mode queries, propose a skill edit with held-out validation criteria (using AcceptanceScenario records as the held-out set), run validation, keep or reject the edit with evidence. Multi-slice; needs its own design pass.

Slice 4: GroupEvolutionRun runtime. Only ships when a real user pull surfaces (not today).

Slice 5: Community lesson library. Per-Goal visibility on lessons; commons promotable; remixable. Per the same pattern as PrivateTraceCommons community library (eventual future slice).

## Composes with prior session work

- #904 (open-brain v2 slice A) — memory_kinds registry pattern reused verbatim
- #915 (PLAN.md restructure) — Evolution & Evaluation Module is the authoritative reference
- #928 (4 audits) — APPROVE verdict from GEA/EvoSkill audit is the design authority
- #931/#933/#935 (PrivateTraceCommons) — visibility-tag-no-enforcement pattern + memory_kind-as-storage pattern reused verbatim
- #936 (AcceptanceScenario Slice 1) — held-out evaluation set provenance composes with AcceptanceScenario records

## Verification (Slice 1 acceptance check)

- [ ] 10-field ExperienceLesson shape justified by failure-mode prevention
- [ ] 7-field GroupEvolutionRun shape marked dormant; no runtime committed
- [ ] All 5 audit open questions explicitly answered
- [ ] No new typed surface beyond the memory_kind
- [ ] No new evaluator primitive
- [ ] No new merge/diversity policy enum (community-evolved free-text)
- [ ] EvalResult reused verbatim, no parallel evidence shape
- [ ] Held-out evaluation provenance reuses AcceptanceScenario substrate
- [ ] Cross-link to Evolution & Evaluation Module section of PLAN.md
