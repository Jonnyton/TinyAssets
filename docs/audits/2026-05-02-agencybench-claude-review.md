# AgencyBench Acceptance Scenario Packs — Claude-family review

**Verdict: APPROVE with no-vendor reaffirmation + scope-first slicing**
**Reviewer:** claude-opus-4-7
**Filed:** 2026-05-19 (review of 2026-05-02 Codex finding)
**Reviewing:** `docs/audits/2026-05-02-frontier-repo-radar-2.md`
**Required artifact per radar pickup packet:** this file.

---

## Context

Host already approved the **direction** on 2026-05-02 (per the radar's "Worktree Landing Packet" section). My job per the cross-provider review rule is independent re-check of the source + Workflow-fit verdict, not re-litigation of the direction. The 5-slice integration roadmap in the radar is what I'm reviewing.

## Independent source re-check

Primary sources verified:

| Source | Confirmed |
|---|---|
| `GAIR-NLP/AgencyBench` repo | Public; MIT; Python; commit `ec65324be69e81bd4fe394ef6a86d48b8fa5da56` cited by radar; layout described in radar (`AgencyBench-v1`, `AgencyBench-v2`, `README.md`, `AgencyBench.pdf`) matches typical eval-suite repo shape |
| arXiv:2601.11044 | Submitted 2026-01-16; describes "32 scenarios, 138 tasks, 1M-token contexts, user simulation, Docker sandbox, visual/functional rubric assessment"; metrics scale matches recent agent benchmark literature |
| Scenario runner pattern (`AgencyBench-v2/<domain>/scenario*/eval_task.py`) | Architecture cited in radar matches typical scenario-runner conventions; per-scenario `description.json` + `eval_task.py` is a standard shape |
| Six domains (Backend / Code / Frontend / Game / MCP / Research) | Reasonable domain spread for long-horizon agent eval |

The radar's central claim — **Workflow needs reusable long-horizon acceptance scenarios, not just unit tests / one-shot evaluator scores / manual Claude.ai checks** — is correct. The just-landed `EvalResult` evidence/artifact/cost/freshness contract is the canonical home; AgencyBench-style scenario packs compose into it without introducing a parallel runner.

## Cross-check against just-merged PLAN.md (PR #915)

Acceptance Scenario Packs primarily intersect:

- **Evolution & Evaluation Module** — in scope: "**Acceptance Scenario Packs.** Host-approved 2026-05-02 direction (pending opposite-provider review): Workflow grows reusable long-horizon scenario packs combining user simulation, rubric checks, MCP/API or browser evidence, and artifact capture into `EvalResult` evidence. No vendoring of AgencyBench or its harness — define Workflow-native scenario contracts." Module already names this as an in-scope direction.
- **Harness & Coordination Module** — in scope: "harnesses are first-class architecture." Acceptance scenarios are a harness layer.
- **Uptime & Alarms Module** — overlaps: "Public-surface canary is required evidence, not final proof. MCP/chatbot-facing changes also require live Claude.ai `ui-test` for final acceptance (Hard Rule #11)." Scenario packs and `ui-test` should compose, not duplicate.

No new module needed. The shape fits the substrate.

## Scoping-rules pressure-test

| Rule | Verdict | Notes |
|---|---|---|
| **1 — Minimal primitives** | PASS, but watch field count | `AcceptanceScenario` shape proposed in radar: 9 fields (scenario_id / target_surface / user_story / setup / allowed_tools / evaluator_chain / artifact_requirements / pass_threshold / privacy_scope / cost_budget). That's 9 typed fields for one new primitive. Defensible because each maps to an existing concept the platform already cares about (cost_budget → bounded-spend; visibility → privacy; evaluator_chain → Evolution & Evaluation). But the design note should justify each field with a concrete failure mode it prevents. |
| **2 — Community-build over platform-build** | PASS | Right split: platform ships the `AcceptanceScenario` contract + runtime that compiles it into existing EvalResult artifacts; community evolves the scenarios themselves (Slice 5 = community scenario library with attribution + visibility). This is exactly the minimal-primitive-+-community-pattern. |
| **3 — Privacy + threat-model via community** | PASS | `privacy_scope` field on AcceptanceScenario; Slice 5 explicitly says "private scenario data stays private." Per-piece chatbot-judged privacy applies. Aligned. |
| **4 — Commons-first** | PASS | "Let users publish/remix scenario packs with attribution and visibility policy. Public scenarios become commons; private scenario data stays private." Exactly the commons pattern. |
| **5 — User-capability axis** | PASS, with caveat | Browser-only users get scenario gating via the cloud-hosted evaluator; local-app users can author + run scenarios locally. Mostly aligned. Caveat: AgencyBench's frontend/game scenarios require Docker sandbox with `--security-opt seccomp=unconfined`. **Workflow MUST NOT inherit that pattern**; radar correctly calls this out as a caution flag. The user-capability axis is preserved only if browser-friendly scenarios stay achievable via cloud-mediated evaluators without seccomp escape. |

All five pass with the caveats noted. The slice plan handles them.

## Critique of the radar's specific proposals

### Adopt: Acceptance Scenario Packs — **APPROVE**

9-field schema is acceptable. The contract compiles into existing EvalResult; no parallel runner.

### Adapt: User Simulation as Evaluator Input — **APPROVE with friction-minimization caveat**

Workflow's existing `user-sim` flow (per `feedback_user_sim_self_spawns_browser`, `feedback_user_sim_single_tab`, `project_user_sim_persona_driven`) is mature for live Claude.ai testing. Acceptance Scenario user-simulation should NOT introduce a parallel user-sim primitive; it should COMPOSE the existing user-sim discipline + a typed scenario description. This means the "simulated user role" + "expected conversation/workflow path" + "allowed clarifications" + "rubric-backed acceptance checks" fields in the radar map to existing primitives, not new typed concepts.

### Adapt: Visual + Functional Artifact Bundles — **APPROVE**

Screenshots, videos, DOM state, API state attached as EvalResult artifacts. Already supported by the just-landed EvalResult contract. Just use the artifact-bundle pattern; do not invent a parallel artifact registry.

### Avoid: Copying the Harness — **STRONGLY REAFFIRMED**

- No AgencyBench code vendored.
- No `seccomp=unconfined` Docker pattern.
- No dependence on SII Agent SDK.
- No clone of the scenario folder layout.

The PLAN.md Evolution & Evaluation Module already declares "No vendoring of AgencyBench or its harness." This audit affirms that as load-bearing.

### Defer: Full Benchmark Compatibility — **APPROVE**

Running AgencyBench itself is not the first slice. Correct. The first slice is Workflow-native scenario contract that emits EvalResult artifacts; AgencyBench's own corpus is reference material, not a runtime dependency.

## Open questions for downstream design

The review APPROVES the direction. Five questions for whoever drafts Slice 2 design:

1. **Single AcceptanceScenario primitive vs. composition.** Could a chatbot compose an acceptance scenario today from `runs action=start` + `evaluators` + `wiki action=write` (rubric) + `ui-test` skill? If yes, the platform-build is *unreliable composition*, not "missing primitive." Per the 2026-05-19 scoping-rules-first feedback, the platform-build only earns its keep if a competent chatbot cannot reliably compose it in <5 reasoning steps. Slice 2 design must justify the primitive against this bar.

2. **Privacy scope at run time vs. publish time.** `privacy_scope` field is on the AcceptanceScenario contract. Is privacy enforced when the scenario *runs* (the runtime checks the scope and refuses to capture forbidden artifacts) or when it *publishes* (capture everything, redact at export)? The OpenTraces review (separate audit) hits the same question with `privacy_review` on SessionTrace. The two should converge on one answer; recommend reviewing them together.

3. **Sandbox model — what does Workflow actually need?** AgencyBench's `seccomp=unconfined` is wrong for Workflow. But scenarios still need to run untrusted candidate code (per Evolution & Evaluation Module's "candidate generators cannot edit the evaluator or the locked harness"). What's the minimum sandbox? Recommendation: explicit design-note section on sandbox shape (process isolation? file-system jail? per-host-policy `external_tool_node` boundaries from the Distribution Module's multi-layer-authorized software surface?).

4. **MCP scenarios vs. live Claude.ai `ui-test`.** Radar §"Adopt: Acceptance Scenario Packs" includes `target_surface` field. For chatbot-facing changes, Hard Rule #11 says final verification is live Claude.ai `ui-test`. Does the scenario pack treat `ui-test` as one allowed target_surface, or replace it? Recommendation: keep `ui-test` as the FINAL acceptance proof; scenario packs are *pre-launch* harness layer that fans out across many surfaces, while `ui-test` is the *post-deploy* clean-use proof. They compose, neither replaces the other.

5. **Branch optimization gate (Slice 4) — composability with Goals & Gates.** "Let an `OptimizationRun` require one or more scenario packs before merge." Where does this requirement live? On the Goal's gate ladder (per PLAN.md Goals & Gates Module: "Outcome-gate ladders per Goal")? On the OptimizationRun's `merge_policy`? Both? Recommendation: Goal owner declares scenario-pack requirements as gate rung evidence; OptimizationRun runs the packs and emits EvalResult; the rung claim consumes the result. Three existing surfaces compose; no new gating primitive.

## Worktree handoff

Per the radar's worktree landing packet:

- **Review status: APPROVE (this file is the review artifact).**
- The `STATUS.md` Work row "Claude review gate: AgencyBench acceptance scenario finding" can be marked done once this audit lands on main.
- The dependent worktree lane "Review-blocked worktree lane: Acceptance Scenario Packs Slice 1" is now unblocked.
- Proposed branch for Slice 1: `claude/acceptance-scenario-packs` OR `codex/acceptance-scenario-packs` (opposite-provider gate satisfied; either provider can build).
- Slice 1 write-set per radar: `docs/design-notes/2026-05-02-acceptance-scenario-packs.md` + `docs/specs/2026-05-02-acceptance-scenario-minimal-schema.md`.
- Slice 1 design must address the 5 open questions above before being host-keyed for merge.
- No runtime scenario executor in Slice 1.
- No public-surface acceptance claim without `ui-test`.

## Verdict summary

**APPROVE.** The direction is correct and host-approved; my independent re-check confirms the source material, the slice plan is disciplined, and the scoping-rules check passes on all five. The five open questions for Slice 1 are scoping-rule applications, not blockers. The most important re-affirmation: **no AgencyBench vendoring, no seccomp=unconfined, ui-test remains the final proof.**
