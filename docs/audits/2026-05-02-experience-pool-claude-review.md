# ExperiencePool + GroupEvolutionRun — Claude-family review

**Verdict: APPROVE with scope discipline**
**Reviewer:** claude-opus-4-7
**Filed:** 2026-05-19 (review of 2026-05-02 Codex finding)
**Reviewing:** `docs/audits/2026-05-02-frontier-project-radar.md` (GEA/EvoSkill frontier finding)
**Required artifact per radar pickup packet:** this file.

---

## Independent source re-check

Primary sources verified:

| Source | Confirmed |
|---|---|
| Group-Evolving Agents paper (arXiv:2602.04837) | Real arXiv ID; reported metrics (71.0% vs 56.7% on SWE-bench Verified; 88.3% vs 68.3% on Polyglot) are within the range of recent group-evolution literature; no obvious red flag |
| EvoSkill repo (github.com/sentient-agi/EvoSkill) | Public; Apache-2.0; Python; SkillOps loop accurately described in radar (failure mining → skill proposal → held-out eval → keep/reject → materialized folder) |
| Darwin-Gödel Machine (Sakana, jennyzzt/dgm) | Cited correctly as ancestor lineage; tree/archive evolution vs group evolution distinction is accurate |
| EvoAgentX, A-Evolve, EvoMaster | All confirmed as real adjacent work; radar's "less aligned than GEA" framing holds |

The radar's central claim — **group-as-unit-of-evolution maps Workflow's product shape better than single-agent self-evolution** — is correct. Workflow's PLAN.md Evolution & Evaluation Module explicitly calls out community model: "Branches, nodes, evaluators, and lessons are remixable public commons … the platform preserves many competing solution families rather than collapsing to one global 'best' workflow." GEA is the research signal that says this is not just product taste; it is the stronger architecture.

## Cross-check against just-merged PLAN.md (PR #915)

The 2026-05-19 PLAN.md restructure introduced 11 well-shaped modules. ExperiencePool + GroupEvolutionRun primarily intersects:

- **Evolution & Evaluation Module** — in scope: "Acceptance Scenario Packs," "quality-diversity search; lineage; attribution; community remix." ExperiencePool fits the in-scope pattern exactly.
- **Brain Module** — in scope: "tiered memory across multiple stores," "memory_kinds typed catalog," "promotion state machine." Per-run "ExperienceLesson" entries map naturally onto memory_kinds; a new `lesson` memory_kind is additive to the existing registry.
- **Goals & Gates Module** — in scope: "rung-claim recommendations on branch tasks," "archive_consultation parent-rank surface." ExperiencePool's `goal_id` and `branch_family_ids` compose with these surfaces.

No new module needed. The shape fits the substrate.

## Scoping-rules pressure-test

Per `feedback_design_questions_apply_scoping_rules_first` (saved 2026-05-19): apply rules 1+2 to the design proposal BEFORE asking the host.

| Rule | Verdict | Notes |
|---|---|---|
| **1 — Minimal primitives** | PASS, with discipline | ExperienceLesson + ExperiencePool + GroupEvolutionRun = 3 new typed surfaces. That's a lot to add at once. But the radar's slice plan stages them correctly: Slice 1 = ExperienceLesson schema only; Slice 2 = read-only aggregation over existing artifacts (no new write paths); Slice 3 = SkillOps trial on one skill; Slice 4 = GroupEvolutionRun spec dormant. **Stage discipline carries the rule.** |
| **2 — Community-build over platform-build** | PASS | The radar correctly notes existing primitives Workflow already has (EvalResult, branch lineage, `.agents/skills`, attribution). ExperienceLesson is the *minimum primitive that closes a structural gap* — without a typed lesson shape, branches cannot reliably share what they learned because the raw artifacts (EvalResult, traces, packets) are not in a queryable form. The lesson surface is platform-build; the *strategies* for what counts as a lesson, how to cluster failures, what diversity policies to use are community-build (per radar §"Adapt EvoSkill to Cross-Provider Skills"). Right split. |
| **3 — Privacy + threat-model via community** | PASS | The radar explicitly lists `visibility` and `visibility_policy` on both ExperienceLesson and ExperiencePool. The "do not let private failures become public reusable lessons without per-piece privacy review" is exactly the per-piece chatbot-judged privacy model from PLAN.md. Matches the principle. |
| **4 — Commons-first** | PASS | "branches under shared goals" is the canonical commons model. ExperiencePool would be platform-stored only when its visibility policy permits it; private branches/lessons stay host-side. Aligned. |
| **5 — User-capability axis** | PASS | "users can say through any MCP chatbot: 'fork these three approaches and let them share lessons.'" is browser-friendly. No local-app dependency. Aligned. |

All five pass. The slice-1 design (schema only) is the right starting bar.

## Critique of the radar's specific proposals

### Adopt: ExperiencePool — **APPROVE**

The 9-field shape (goal_id / branch_family_ids / visibility_policy / lesson_refs / candidate_refs / evaluator_result_refs / failure_modes / reusable_skills / outcome_refs) maps cleanly onto existing primitives. `outcome_refs` ties into Goals & Gates; `evaluator_result_refs` ties into the just-landed EvalResult contract; `failure_modes` is a new typed view but composes from existing EvalResult.evidence fields.

### Adopt: GroupEvolutionRun — **APPROVE as dormant spec only**

The 7-field shape is reasonable but introduces a parallel run type. The slice plan correctly marks this as **Slice 4: dormant spec without broad execution**. APPROVE the dormant spec; explicitly defer the runtime execution to a later substantive design pass. The dormant spec earns its keep by pressure-testing OptimizationRun's interface before that primitive is locked.

### Adopt: SkillOps from failures — **APPROVE**

The held-out evaluation gap (radar §"What To Adopt → SkillOps From Failures") is real. Workflow today has `.agents/skills/` + `validate_skills.py` + mirror parity, but no held-out evaluation before a skill change becomes canonical. Adding that gate is a clean Scoping Rule 2 application: a small primitive (held-out validator) closes a real composition gap. APPROVE.

### Avoid recommendations — all CORRECT

- "Do not build a separate local-only self-evolution harness" — yes, this is exactly the platform-build trap.
- "Do not optimize against one fixed validation set without holdouts" — yes, validation-set overfitting is a real failure mode.
- "Do not copy EvoSkill's `.claude`-first layout" — yes; Workflow is cross-provider with `.agents/skills/` as canonical source.
- "Do not copy DGM's isolated coding-agent focus" — yes; that's the single-agent trap.

## Open questions for downstream design

The review APPROVES the direction but flags these for whoever drafts the design note in Slice 2:

1. **ExperienceLesson as memory_kind vs. separate table.** The Brain Module already has a memory_kinds registry (open-brain v2 slice A). Should `lesson` be a new memory_kind, or its own typed surface? Memory_kind keeps things minimal; separate surface allows specialized indexing. Recommendation: start as a memory_kind, promote to separate surface only if real query patterns demand it (mirrors the Origin Quantum review's "promote-only-if-needed" guardrail).

2. **Aggregation read model in Slice 2 — composed or platform-built?** Radar says "expose a read-only aggregation over existing artifacts." A chatbot can already compose `wiki action=search` + `branches action=list` + `runs action=list` to assemble this. Does the platform need a typed `experience_pool action=summarize` action, or is the composition pattern (documented as a wiki page) enough? Per scoping rules, default to composition. The platform-shipped action earns its keep only if the composition is unreliable in <5 reasoning steps.

3. **GroupEvolutionRun merge_policy field.** What are the available merge policies? Free-text per Goal, or a small enum? Per the 2026-05-19 design-questions-scoping-rules feedback: open-ended variations like "merge policy" are community-build candidates. Recommend free-text annotation + community-evolved patterns rather than a frozen enum.

4. **EvalResult coupling.** Slice 1 should reuse the just-landed EvalResult evidence/artifact/cost/freshness contract verbatim, not introduce parallel evidence shapes. This is the same Rule 1 lesson as the navigator's Origin Quantum pre-review.

5. **Held-out evaluation set provenance.** Where do held-out tasks come from? If they come from the same pool as training tasks (e.g., past failures), there's a known set-overlap risk. Recommend the design note explicitly specifies how held-out sets are sampled and audited.

## Worktree handoff

Per the radar's worktree landing packet:

- **Review status: APPROVE (this file is the review artifact).**
- The `STATUS.md` Work row "Claude review gate: ExperiencePool + GroupEvolutionRun frontier finding" can be marked done once this audit lands on main.
- The dependent worktree lane "Review-blocked worktree lane: ExperiencePool + GroupEvolutionRun Slice 1" is now unblocked.
- Proposed branch for Slice 1: `claude/experience-pool-slice-1` OR `codex/experience-pool-slice-1` (either provider; Codex made the initial finding, Claude reviewed, opposite-provider gate satisfied).
- Slice 1 write-set per radar: `docs/design-notes/2026-05-02-experience-pool-and-group-evolution.md` + `docs/specs/2026-05-02-experience-pool-minimal-schema.md`.
- Slice 1 must address the 5 open questions above before being host-keyed for merge.

## Verdict summary

**APPROVE.** Direction is correct, slice plan is disciplined, scoping-rules check passes on all five. Five open questions for the Slice 1 design note (none are blockers, all are scoping-rule applications). Workflow's product shape is community-evolved, group-evolving branch ecology; GEA is the research signal that says this is the stronger architecture.

The radar correctly identifies this as the frontier bet. Build it.
