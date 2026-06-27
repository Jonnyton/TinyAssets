---
title: Methods-prose evaluator — REFRAMED community-build (was: first-class platform evaluator)
date: 2026-04-27
author: navigator
status: REFRAMED community-build per host directive 2026-04-26
status_detail: platform will NOT ship methods-prose evaluator subtypes as primitives; chatbot composes correctness checks from the existing Evaluator surface + wiki-published rubrics. Pre-reframe content preserved below as historical context.
type: design-note
companion:
  - tinyassets/evaluation/__init__.py (existing Evaluator Protocol — the user-callable primitive surface)
  - .claude/agent-memory/lead/project_community_build_over_platform_build.md
  - .claude/agent-memory/lead/project_privacy_via_community_composition.md (sibling case — same reframe pattern)
  - .claude/agent-memory/lead/project_minimal_primitives_principle.md
  - .claude/agent-memory/user/personas/priya_ramaswamy/sessions.md (Priya signal #2 — provenance)
  - ideas/INBOX.md 2026-04-27 entry — Methods-prose evaluator class
  - project_evaluation_layers_unifying_frame (host 2026-04-19 unification doctrine)
load-bearing-question: Does this make the user's chatbot better at serving the user's real goal?
audience: lead, host, future dev/spec author
---

# Methods-prose evaluator — REFRAMED community-build

## Reframe (2026-04-26 host directive — supersedes the proposal below)

**Status: this note no longer proposes a platform feature.** Per host directive 2026-04-26 (community-build over platform-build) the platform will **not** ship methods-prose evaluator subtypes as primitives. There is no upcoming spec, no `EvaluatorKind` extension, no reference implementation, and no v1/v2 rollout to land.

What ships instead:

- **The existing `Evaluator` Protocol at `tinyassets/evaluation/__init__.py:60`** is the user-callable primitive. It already has `EvaluatorKind = "custom"` and the inputs/outputs needed for prose correctness checks (run state, artifact paths, package manifest, generated text).
- **The chatbot composes prose-correctness checks for the user** by chaining existing primitives: read run state → diff against drafted prose → call existing custom evaluator(s) → present mismatch report. No new platform code.
- **Community-published rubrics on the wiki** — e.g. "methods-section reproducibility check for ecology MaxEnt sweeps" — give chatbots a recipe to pull, parameterize, and run. Discovery + remix is the feature engine, not platform-shipped subtypes.

Why the reframe: per `project_community_build_over_platform_build`, when proposing a feature we now ask FIRST "could the user's chatbot easily compose this from existing primitives?" — and for methods-prose verification the answer is yes (the chatbot already has run state, package manifest, drafted prose, and a `kind="custom"` Evaluator surface to invoke). Per `project_minimal_primitives_principle`, tool count is a budget that shrinks toward irreducible building blocks; named prose-* subtypes would expand the primitive surface for capability the existing surface already covers. Per `project_privacy_via_community_composition`, this is the same pattern as the privacy-modes reframe: platform owns the enforcement primitives, community evolves the recipes.

The original 2026-04-27 §1 chain-break (Priya's reviewer-2 risk) is still a real chain-break — but the **platform** chain is unbroken once the chatbot composes the check. The chain-break framing in the proposal below misdiagnosed a community-recipe gap as a platform-primitive gap.

The earlier in-line REFRAME (2026-04-27 host directive Q1=b + Q6=b — user-callable primitives, never auto-run gates) is consistent with this directive but did not go far enough; it kept the platform-primitive shape and only reshaped the invocation surface. The 2026-04-26 directive supersedes both: don't ship the primitive at all.

**STATUS Concern row** filed 2026-04-26 ("Methods-prose evaluator REFRAMED community-build") tracks this reframe. The Concern can be deleted once this note's header lands; the reframe IS the resolution.

---

## Pre-reframe design (historical)

The remainder of this note is the original platform-primitive proposal, preserved verbatim so future readers can see why the platform-build framing was rejected. Do not implement from this section. If a future host directive re-opens platform-primitive prose evaluators, start a fresh design note that grounds itself in the current commons-first / community-build doctrine rather than reviving this one.

---

## TL;DR

Priya signal #2 (2026-04-20) surfaced a chain-break: when the chatbot generates publication-grade methods prose ("Sensitivity sweeps were performed using `maxnet` v0.1.4 with kernels {linear, quadratic, hinge} × regmult {0.5, 1.0, 2.0}, evaluated by 5-fold spatial cross-validation, mean AUC ranked..."), nothing on the platform verifies the prose is correct. This is a **cross-layer chain-break (pitch-vs-product gap):** the platform's positioning ("evaluator-driven workflows") promises correctness verification at every step, but methods-section prose has no first-class evaluator.

This note proposes adding **methods-prose evaluator subtypes** to the existing `Evaluator` Protocol at `tinyassets/evaluation/__init__.py:60` — NOT a parallel system. The Protocol's `EvaluatorKind` literal already includes `"custom"`; this note recommends extending it with named subtypes (`prose-citation`, `prose-versions`, `prose-completeness`, `prose-reproducibility`) and shipping reference implementations.

**Recommendation: APPROVE in principle, scope tightly for v1.** Ship two of the four subtypes (versions + reproducibility) — they have clean deterministic signals. Defer the other two (citation + completeness) to v2 because they require external API integration (citation) or LLM judgment (completeness) without obvious bounded cost. Concrete path: spec → 2 dev tasks → ~2 weeks wall-time.

---

## 1. Problem statement (3-layer chain-break framing)

**System → Chatbot → User.** Load-bearing question: does this make the chatbot better at serving the user's real goal?

### The user's real goal

Priya is a postdoctoral ecologist running a 14-species × 15-MaxEnt-config sensitivity sweep for a peer-reviewed journal submission (Methods in Ecology and Evolution). Reviewer 2 will read her methods section and reject the paper if the prose is incorrect. Her real goal: **a methods paragraph that survives peer review.**

Her artifacts at session end (per `priya_ramaswamy/sessions.md` Session 1):
1. `western_ghats_sensitivity_sweep_ranked.csv` — empirical results.
2. `sensitivity_sweep_repro.py` — reproducibility script.
3. `workflow_node_definition.json` — node-spec for audit.
4. **A methods paragraph** the chatbot drafted for her acknowledgements section.

Items 1-3 have evaluator coverage today (CSV correctness checks, repro-script-runs validation, node-spec validity). **Item 4 has no evaluator.** If the chatbot wrote "we used MaxEnt v3.4.1" but actually invoked `maxnet` v0.1.4, reviewer 2 catches it and the paper is rejected on a methods misstatement. Today, no system gate prevents this.

### The chatbot's job

The chatbot draws on the run state, node-spec, package manifests, and user context to produce the methods prose. It has all the data — it just doesn't have a verifier that says "your prose claims `maxnet v0.1.4` but the run actually used `maxnet v0.1.5` per pip-freeze; correct the prose before delivering."

### The system gap

Today there is no `Evaluator` of `kind="prose-versions"` (or any prose-correctness kind) the chatbot can run after generating the paragraph. The chatbot can self-audit by re-reading the run state, but self-audit is not the same as a deterministic evaluator the user can trust.

**Chain-break diagnosis:** Cross-layer (interface 2 + pitch-vs-product gap).
- Interface 2 (chain-complete-but-upstream-broken): the chatbot can write the prose; the user can read it; the system has no evaluator gate between them.
- Pitch-vs-product: platform pitches "evaluator-driven workflows"; methods prose for academic users is a high-stakes evaluator-shaped need with no evaluator.

---

## 2. Design space — four methods-prose evaluator subtypes

Per task description, scope four subtypes:

### (a) `prose-versions` — library-version accuracy

**Verifies:** Every "library X version Y" claim in the prose maps to an actually-invoked package version.

**Signal source:** Deterministic — `pip freeze` of the run's environment, the node's `dependencies` field, the run's resolved environment manifest. No LLM needed.

**Evidence shape:** `{claimed_version: "maxnet v0.1.4", actual_version: "maxnet v0.1.5", source: "pip-freeze"}` per claim.

**Verdict logic:** any mismatch → `verdict="fail"`, `score=-1.0`. Match → `verdict="pass"`, `score=1.0`. No claim found → `verdict="skip"`.

**Cost:** Cheap. Single `pip-list`-equivalent read; substring-match prose claims against the manifest.

**Implementation difficulty: LOW.** Recommended for v1.

### (b) `prose-citation` — citation correctness

**Verifies:** Every cited paper exists, year + first-author match, DOI resolves.

**Signal source:** External API (Crossref, Semantic Scholar, OpenAlex). Requires network egress + rate-limiting + API-key handling.

**Evidence shape:** `{cited: "Phillips et al. 2017", resolved_doi: "10.1111/ecog.03049", crossref_status: "found", first_author_match: true, year_match: true}` per citation.

**Verdict logic:** all citations resolve cleanly → `pass`. Any 404 / mismatch → `fail`. Network unavailable → `skip` (degrade, don't block).

**Cost:** Bounded by citation count (Priya's prose has ~3 citations); ~100ms per Crossref lookup. Cacheable.

**Implementation difficulty: MEDIUM.** Defer to v2 — needs an external-API contract decision (which provider? what's the rate-limit strategy? cost?). Adds a new dependency surface.

### (c) `prose-completeness` — methodological-step completeness

**Verifies:** Every algorithm-config decision named in the run (CV folds, hyperparameter ranges, evaluation metric, random seed) is mentioned in the prose.

**Signal source:** LLM judge OR rubric-function comparing prose tokens against run-state field names. Hybrid is cheapest.

**Evidence shape:** `{run_field: "cv_folds=5", prose_mention: "5-fold spatial cross-validation", matched: true}` per field.

**Verdict logic:** all required fields mentioned → `pass`. Missing one → `fail` with the missing-field name. Threshold tuneable per node.

**Cost:** Either cheap (rubric: keyword match) or moderate (LLM: ~500 tokens per check). Hybrid: rubric first, LLM fallback for prose with semantic match needs ("five-fold" vs "5-fold" vs "5-fold spatial CV" all map to same config).

**Implementation difficulty: MEDIUM-HIGH.** Defer to v2 — needs domain-aware mapping table (which run fields are "required to mention" varies per node). Could ship with a per-node opt-in list of required-mention fields.

### (d) `prose-reproducibility` — reproducibility-claim verifiability

**Verifies:** Every "reproducible by re-running X" prose claim maps to a concrete `run_branch` call signature that actually exists on the platform.

**Signal source:** Deterministic — parse prose for repro-script-name claims, verify each named script exists in the run's output dir AND has a documented `run_branch` invocation that regenerates it.

**Evidence shape:** `{claimed_repro_script: "sensitivity_sweep_repro.py", file_exists: true, runs_cleanly: true, regenerates_outputs: true}` per claim.

**Verdict logic:** all repro claims map to actual artifacts AND artifacts run cleanly → `pass`. Missing artifact → `fail`. Artifact runs but mismatches output → `fail`. Network unavailable for cloud-only invocation → `skip`.

**Cost:** Moderate — running the repro script is the most expensive subcheck. Can be opt-in via `verify_runs=true` flag; default to file-existence + signature check only.

**Implementation difficulty: LOW-MEDIUM.** Recommended for v1 — the file-existence + signature check is cheap; the actual run-verification is a flag-gated bonus. Reproducibility is also Priya's **highest-stake** signal (her PRIYA-W6 win was "repro script runs locally and matches"). This is the surface where the platform delivers Q21 Real World Effect Engine value.

---

## 3. Decision required

### Option 1: Ship all four subtypes for v1 (FULL)

- 4 new evaluator implementations + tests.
- Adds 1 external-API integration (Crossref/Semantic Scholar for citation).
- Adds 1 LLM-judge dependency (completeness).
- Wall-time: ~6-8 weeks.
- Cost: highest — external API + LLM judge per check.
- Risk: scope creep + external-dependency drift (citation API rate-limits change; LLM judge accuracy depends on model version).

### Option 2: Ship two deterministic subtypes for v1 (RECOMMENDED)

- `prose-versions` + `prose-reproducibility` — both deterministic, cheap, high-stakes.
- 2 new evaluator implementations + tests.
- Wall-time: ~2 weeks.
- Cost: zero — runs locally on existing data.
- Risk: low — no external dependencies.
- Captures Priya's two highest-stake correctness needs (PRIYA-W6 reproducibility, PRIYA-W4 metric-match-requires-version-accuracy).
- v2 adds citation + completeness when external-API contracts are scoped separately.

### Option 3: Concede this stays human-review for v1 (SKIP)

- No new evaluators.
- Document the gap in `pages/concepts/` so chatbots warn Priya: "I drafted this prose; you must verify versions + citations before submission."
- Wall-time: ~1 day (concept page).
- Risk: trust-break on Priya's first published-paper attempt; she walks if reviewer 2 catches a methods misstatement.
- This option is honest but accepts the chain-break as permanent.

### Recommendation: Option 2

**Rationale:**

1. **The platform already has the substrate.** `Evaluator` Protocol exists at `tinyassets/evaluation/__init__.py:60`; `EvaluatorKind` includes `"custom"`. Adding two new kinds is mechanical.
2. **Priya's two highest-stake signals are version-accuracy + reproducibility.** PRIYA-W4 ("AUC matches to within 5-fold CV variance") and PRIYA-W6 ("repro script runs locally and matches") are both v1 wins for these subtypes.
3. **Citation + completeness need separate scope decisions.** Citation needs an external-API contract; completeness needs a domain-aware required-mention table. Neither is unsolvable — they just need their own design notes when the host wants to scope them.
4. **Chain-break framing.** Option 2 closes the chain at the highest-stake surface (versions + reproducibility) without committing to external dependencies the platform doesn't yet need.
5. **Q21 Real World Effect Engine alignment.** Reproducibility verification IS Q21 — it's the surface where "real paper, real artifact, real reviewer response" lands.

---

## 4. Concrete implementation outline (if Option 2 approved)

### 4.1 New evaluator subtypes

In `tinyassets/evaluation/__init__.py`:

```python
EvaluatorKind = Literal[
    "structural", "editorial", "process", "numeric", "custom",
    "prose-versions", "prose-reproducibility",  # NEW
]
```

### 4.2 New evaluator modules

```
tinyassets/evaluation/prose_versions.py    # ~150 LOC
tinyassets/evaluation/prose_reproducibility.py  # ~200 LOC
tests/test_prose_versions_evaluator.py    # ~30 tests
tests/test_prose_reproducibility_evaluator.py  # ~25 tests
```

### 4.3 Public surface (added to `workflow.evaluation.__init__`)

```python
from workflow.evaluation.prose_versions import (
    ProseVersionsEvaluator,
    ProseVersionMismatch,
)
from workflow.evaluation.prose_reproducibility import (
    ProseReproducibilityEvaluator,
    ReproClaim,
)
```

### 4.4 Chatbot integration

**Step 1 (default behavior):** When the chatbot drafts methods prose AND the run produced artifacts (CSV + repro script), automatically run `ProseVersionsEvaluator` + `ProseReproducibilityEvaluator` against the prose + run-state. Surface results in the chatbot's response: "Drafted your methods paragraph. Verifications: ✓ all 3 library-version claims match installed packages. ✓ repro script `sensitivity_sweep_repro.py` exists and signature matches the run."

**Step 2 (opt-in via `verify_runs=true`):** For the repro evaluator, also actually run the script in a sandboxed environment + diff outputs.

**Step 3 (failure path):** Either evaluator returning `fail` blocks the chatbot from delivering the prose without an explicit "I checked this and it's still right" override from the user. Trust-graduation surface — Priya sees the platform caught a real error, not a generated word salad.

### 4.5 Chatbot prompt update

Add to `control_station` prompt (per `project_evaluation_layers_unifying_frame`): "When you generate prose claims about library versions or reproducibility, run the appropriate `prose-versions` / `prose-reproducibility` evaluator before delivering. If the evaluator returns `fail`, correct the prose using the `details.evidence` field."

---

## 5. Decision asks for the lead

1. **Approve Option 2 (ship 2 of 4 subtypes for v1)?** Recommended. If yes, I'll write a tight spec at `docs/specs/methods-prose-evaluator-v1.md` and propose 2 dev tasks (one per subtype).
2. **Approve `prose-versions` + `prose-reproducibility` as the v1 pair?** Both are deterministic + high-stakes. Alternative: pair `prose-versions` with `prose-completeness` (rubric-only sub-mode, no LLM) if you want completeness over reproducibility — but reproducibility is the Q21 surface.
3. **Approve adding `"prose-versions"` and `"prose-reproducibility"` to `EvaluatorKind` literal?** This is the substrate change — needs lead sign-off because it touches the Protocol layer.
4. **Approve auto-invocation default?** §4.4 step 1: chatbot auto-runs the evaluator when the run produced artifacts. Alternative: opt-in only (chatbot asks user "run methods-prose checks?"). Auto-invocation is the chatbot-leverage win — fewer friction-prompts to the user.
5. **Defer or schedule v2 (citation + completeness)?** Not blocking. Capture in `ideas/PIPELINE.md` for next-quarter triage.
6. **Persona-replay regression test.** Recommend a test that replays Priya Session 1's prose-generation step against the new evaluators — ensures we'd actually catch the "v0.1.4 vs v0.1.5" class of error.

---

## 6. Risks + mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Evaluator false-positive (claims mismatch when prose is fine — e.g., "MaxEnt" prose, `maxnet` package) | MEDIUM | Build a known-aliases table (`maxnet ↔ MaxEnt`, `sklearn ↔ scikit-learn`); ship empty + grow per-domain. |
| Evaluator false-negative (misses a real error) | LOW | Deterministic check on package-manifest substring is hard to false-negative when manifest is correct. |
| External-domain users hate the auto-invocation | LOW | Opt-out flag at node level; chatbot respects user preference per `project_user_prefs_chatbot_native`. |
| Repro script run takes too long (e.g., Priya's 8-min sweep) | HIGH | Default to file-existence + signature check; full run-verification is `verify_runs=true` opt-in. |
| Adds LLM cost to chatbot turns | LOW | Both v1 subtypes are deterministic. Zero LLM cost. |
| Domain-coupling creep — these evaluators live in `workflow.evaluation` (engine-tier) but reference scientific-computing concepts | LOW | The evaluators are domain-agnostic mechanically — they verify "claim X matches reality Y" regardless of Priya being an ecologist or Devin being an ML engineer. The domain knowledge (which tokens map to what packages) lives in the per-node aliases table, which is per-domain. |

---

## 7. Cross-references

- `project_evaluation_layers_unifying_frame` — host 2026-04-19 unification doctrine. This note instantiates that frame for one new substrate (prose).
- `priya_ramaswamy/sessions.md` Session 1 + Session 2 — the source signals.
- `priya_ramaswamy/wins.md` PRIYA-W4 + PRIYA-W6 — the wins this evaluator pair preserves at scale.
- `priya_ramaswamy/grievances.md` PRIYA-R1 (vocabulary gap) — adjacent but separate concern; not solved here.
- `tinyassets/evaluation/__init__.py:60` — existing `Evaluator` Protocol that this note extends.
- `tinyassets/evaluation/structural.py` — existing reference implementation pattern to mirror.
- `ideas/INBOX.md` 2026-04-27 entry — capture row that this note responds to.
- `project_real_world_effect_engine` — Q21 product-soul check; reproducibility evaluator IS the Q21 surface for academic users.

---

## 8. Acceptance criteria (if approved)

The note is ready to graduate to a spec when the lead answers questions 1-4 in §5. The spec will include:

- Exact `EvalResult.details` schemas for both subtypes.
- Concrete signature for each evaluator class.
- Chatbot-side trigger logic + prompt-update text.
- Test fixtures including the Priya Session 1 persona-replay regression.
- Per-domain alias-table starting set (Python: `numpy`, `pandas`, `scikit-learn`, `scikit-learn-intelex`, `xgboost`, `lightgbm`, `maxnet`/`MaxEnt`; R: `dismo`, `randomForest`, `glmnet`).

Spec lands → 2 dev tasks → ~2 weeks wall-time → v1 ships → Priya Session 3 (planned, anticipated) is the live validation.
