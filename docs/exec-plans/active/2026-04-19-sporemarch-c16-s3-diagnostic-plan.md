# Sporemarch C16-S3 Score-Plateau Diagnostic — Execution Plan

**Date:** 2026-04-19
**Author:** navigator
**Status:** Pre-staged diagnostic plan. Dispatch-ready when Sporemarch resumes post-Fix-E migration.
**Trigger:** Mission 26 #B4 finding — `sporemarch-B1-C16-S3` stuck in 30+ evaluate→SECOND_DRAFT→rewrite cycles, 04-17 04:20–05:10 UTC, scores locked 0.69-0.71 with downward drift. Different bug from concern 1 (overshoot), same universe, same blocker shape.
**Scope:** Diagnostic data needs + failure-mode taxonomy + user-sim debug mission + per-hypothesis fix shapes.
**Effort to ship the diagnostic:** 0 (this doc is the diagnostic spec). Effort to *act on* it depends on which hypothesis the data confirms.

---

## 1. Why pre-stage this now

#B4 will reappear the moment Sporemarch resumes post-Fix-E migration. Three predictable scenarios:

1. **Daemon resumes; same C16-S3 plateau.** Migration didn't touch the score-plateau bug; it'll re-fire on first dispatch cycle.
2. **Daemon resumes; advances past C16-S3.** The Fix-E DB cleanup removed orphan facts that may have been polluting evaluator context; with cleaner grounding, evaluator passes the draft.
3. **Daemon resumes; new plateau on a different scene.** The plateau pattern is structural to the evaluator/revise loop, not scene-specific.

We don't know which scenario fires until the migration applies and the daemon resumes. Pre-staging the diagnostic means **whichever scenario fires, the response is dispatch-ready** — no re-investigation required.

---

## 2. Diagnostic data the chatbot + daemon need to surface

The chatbot needs structured evidence to characterize *which* failure mode is firing. Today, only top-line evaluator scores are user-visible. That's not enough to discriminate between the four hypotheses in §3.

**Chatbot-side needs (via MCP):**

| Field | Source | Purpose |
|---|---|---|
| Last-N evaluator decisions for the stuck scene (score, verdict, criteria-breakdown if available) | `get_recent_events(tag="evaluator")` (acfeeeb landed `get_recent_events` 2026-04-19) | Which axes of the rubric are scoring low; is one criterion repeatedly the bottleneck. |
| Last-N revise cycle events (revert reason, draft length, prior-draft-id) | `get_recent_events(tag="revise")` or `get_recent_events(tag="revert")` | Are revisions actually changing the draft, or is the daemon producing semantically-equivalent rewrites. |
| Dispatch-guard events for the stuck scene | `get_recent_events(tag="dispatch_guard")` (per #B5 closure) | Is dispatch-guard firing on the loop, and if so what verdict (allowed/blocked/cooled-down). |
| RC-3 chapter-level revert-streak counter state | `get_recent_events(tag="rc3")` or `query_world` against control state | Is the RC-3 gate (`abb4d58`) seeing the streak? It's chapter-scoped; if streak <3, the gate hasn't fired. If streak ≥3, gate fired but daemon didn't escape. |
| Evaluator-criterion text for this scene | `query_world(query_type="criteria")` if available; otherwise daemon-side log read | If evaluator is using criteria that are mismatched to the scene's intent, surfaces which criterion. |

**Daemon-side needs (logged or surfaceable via MCP):**

| Diagnostic | Mechanism | Hypothesis it discriminates |
|---|---|---|
| Score *delta* between consecutive drafts (not just absolute score) | New surface; could fold into evaluator-event structured data | If delta is consistently zero or near-zero across many cycles, daemon isn't producing meaningful new content (revert-loop without progress). |
| Evaluator-criterion *which-fails* breakdown | Likely already in evaluator output but not exposed via MCP | Discriminates score-ceiling (one criterion repeatedly fails) from evaluator-brittleness (different criteria fail each cycle, suggesting noisy evaluator). |
| Time-since-last-accepted-draft | Activity log | Calibration signal — is the daemon stuck for hours vs minutes. |

**Verdict on chatbot surface:** dev shipped `get_recent_events` with tag-prefix filtering at `acfeeeb`. The pre-existing `get_recent_events(tag="dispatch_guard")` was the only specifically-needed verb for #B5. For #B4 diagnostic, **`get_recent_events(tag="evaluator")` and `get_recent_events(tag="revise")`** are the new tag-routes that need verification — if the daemon doesn't currently *emit* events under those tags, the verb will return empty and the diagnostic is blocked at the daemon emission layer, not the MCP layer.

**Pre-flight check for the dev who picks up #52:** verify `get_recent_events(tag="evaluator")` returns non-empty rows before the user-sim mission runs. If empty, daemon doesn't emit evaluator events into the activity log; first dev sub-task is to add those emissions (small change, ~30-60 min). Otherwise the user-sim mission has nothing to inspect.

---

## 3. Failure-mode taxonomy

Four hypotheses, each with a distinct evidence signature. Listed in order of estimated probability based on Mission 26 evidence:

### 3.1 H1 — Evaluator score-ceiling (most likely)

**Hypothesis:** The evaluator's scoring rubric has a hard ceiling around ~0.70 for this scene's content. The daemon's revisions are producing genuinely-different drafts but the rubric simply doesn't score above that threshold for the scene's structural shape (e.g., the scene needs a constraint the daemon can't satisfy without architectural change — POV switch, structural reframe, etc.).

**Evidence signature:**
- Score variance across cycles is small (0.69-0.71, consistent with rubric noise floor).
- Drafts ARE meaningfully different (large delta in prose between cycles).
- Different criteria fail each cycle (rubric is hitting different ceilings on different drafts, no single criterion bottleneck).
- Revert-streak counter has fired (streak ≥3) but daemon doesn't escape.

**Fix shape if confirmed:** **Score-ceiling escape hatch.** When evaluator has rejected ≥N (say 5) drafts of the same scene with score in a narrow band (say 0.05 of each other), daemon escalates to a *restructure* action — produces a draft from a different POV, or recasts the scene's structural role, or splits/merges the scene. Per AGENTS.md "Bad decisions are data" principle, the failure mode is a signal the scene's spec needs revision, not just more rewrites.

**Dev-day estimate:** ~1-1.5 days. New action `force_restructure(scene_id, hint=...)` + RC-3-equivalent gate detection (already exists at chapter level via `abb4d58`; needs scene-scope variant) + plumbing through the dispatcher.

### 3.2 H2 — Revert-gate over-firing (second-most-likely)

**Hypothesis:** RC-3 gate (chapter-level revert-streak accumulator) is correctly seeing the streak and trying to halt-to-consolidate, but the consolidation action isn't producing a meaningfully-different next draft — it's recursing into the same revise loop after one consolidation cycle.

**Evidence signature:**
- RC-3 gate fired (streak ≥3 events visible in activity log).
- After consolidation, next draft scores in the same 0.69-0.71 band.
- Drafts pre- and post-consolidation are *not* meaningfully different (same scene, same structure, minor edits).
- Score delta between cycles is small.

**Fix shape if confirmed:** **Stronger consolidation directive.** The RC-3 halt currently just re-prompts with consolidate-context. Strengthen to: "produce a draft that materially differs from the prior N — different opening, different POV emphasis, or different beat structure. If you cannot, surface this scene as needing structural revision and pause." Failure-loud (per Hard Rule 8 in AGENTS.md) instead of failure-quiet.

**Dev-day estimate:** ~0.5 day. Prompt engineering on the RC-3 consolidation action + a "max-cycles-before-pause" hard ceiling.

### 3.3 H3 — Evaluator-criterion drift (less likely but plausible)

**Hypothesis:** The evaluator's criteria for this scene are inconsistent across cycles — the rubric pulls from a set of criteria that vary with each evaluation (e.g., randomly-selected slice of all applicable criteria). Daemon "passes" criteria-set A but fails criteria-set B on the next cycle, oscillating without convergence possible.

**Evidence signature:**
- Different criteria fire FAILED on consecutive cycles (criterion A fails on cycle 1, criterion B fails on cycle 2, criterion A passes on cycle 3 etc.).
- Score variance is small but criterion-set varies.
- No structural change in drafts would resolve all criteria simultaneously.

**Fix shape if confirmed:** **Pin criteria for in-flight scenes.** Once an evaluator first evaluates a scene, the criterion set used should remain stable across all subsequent revise cycles for that scene — otherwise the daemon is chasing a moving target. Audit `tinyassets/evaluation/` for criteria selection logic; add a per-scene criterion-pin cache.

**Dev-day estimate:** ~1 day. Criterion-pin cache + per-scene reset-on-accept logic.

### 3.4 H4 — Evaluator brittleness (least likely)

**Hypothesis:** Evaluator scoring has high noise floor — the same draft re-evaluated produces different scores (small variance). The 0.69-0.71 band is genuinely just noise around the same draft quality, and the daemon is responding to noise as if it were signal.

**Evidence signature:**
- Score variance across re-evaluations of the *same draft* is in the same range as variance across genuinely-different drafts (0.05-ish).
- This requires a controlled experiment: re-evaluate the *same draft* N times and measure score variance.

**Fix shape if confirmed:** **Evaluator-temperature lowering OR multi-eval averaging.** Either lower the evaluator LLM's temperature to reduce stochasticity, or evaluate each draft 3 times and use the median score (mitigates outliers). Per PLAN.md "Generator, evaluator, and ground truth stay separate" — but the evaluator should be *consistent*, even if separate.

**Dev-day estimate:** ~0.5 day. Add temperature param to evaluator config + optional multi-eval averaging mode.

---

## 4. Dispatchable debug mission for user-sim

Persona-free, operator voice. ~5-prompt budget. Goal: discriminate between H1-H4 by collecting structured evidence.

```
MISSION: #B4 Sporemarch C16-S3 plateau diagnostic
PRECONDITION: Sporemarch daemon resumed post-Fix-E. C16-S3 is the active
work target. Either currently in a revise cycle OR has logged ≥10 revise
cycles in last activity_log_line_count.

PROMPT 1 — Last-10 evaluator decisions for the stuck scene
"Use the workflow connector. For sporemarch universe, scene
sporemarch-B1-C16-S3, return the last 10 evaluator events via
get_recent_events with tag='evaluator'. Include score, verdict,
which criteria fired FAILED if available, and the draft_id
referenced. Output as a table I can inspect."

EXPECTED:
- If H1 (score-ceiling): scores cluster tightly in 0.69-0.71, varied
  draft_ids, varied criteria failing.
- If H2 (revert-gate over-firing): RC-3 events visible alongside
  evaluator events; consolidation actions appear but don't change
  score band.
- If H3 (criterion drift): different criteria fire FAILED across
  consecutive cycles even when draft_ids are similar.
- If H4 (brittleness): same draft_id appears with different scores
  (re-evaluations producing different verdicts).
- If get_recent_events(tag='evaluator') returns empty: daemon doesn't
  emit evaluator events; STOP, escalate to dev for emission gap.

PROMPT 2 — Cross-reference with revise + dispatch-guard tags
"Same universe, same scene. Get last 10 events with tag='revise'
and last 10 with tag='dispatch_guard'. Show interleaved
chronologically with evaluator events from prompt 1. Look for
RC-3 gate fires, dispatch-guard halts, restart cycles."

EXPECTED:
- Discriminates H2 (RC-3 fired but didn't escape) from H1 (RC-3 may
  not have fired at all if threshold not met).

PROMPT 3 — Draft-content comparison
"For the most recent 3 revise cycles on this scene, retrieve each
draft's prose (or the first 500 chars if too long) and compute
text-overlap. Are revisions producing meaningfully different
prose, or near-identical drafts?"

EXPECTED:
- High overlap → H2 (consolidation not changing draft) or H3
  (criterion drift causing oscillation around stable draft).
- Low overlap with stable scores → H1 (real different drafts hitting
  same ceiling).

PROMPT 4 — Criterion pinning check
"For sporemarch-B1-C16-S3, list all criteria the evaluator has
ever scored. Group by 'criterion appeared in N of last M evaluations'.
A criterion that appears in <80% of evaluations indicates criterion
drift across cycles."

EXPECTED:
- If criteria appear in 100% of evaluations → H1 or H4 (criterion set
  stable; problem is elsewhere).
- If criteria appear in 50-80% range → H3 confirmed.

PROMPT 5 — Re-evaluation variance test (only if H4 still in play)
"Trigger 3 re-evaluations of the most recent draft (no rewrites
between). Report each evaluator score. Variance under 0.02 → noise
floor low → H4 unlikely. Variance over 0.05 → H4 confirmed."

EXPECTED:
- Conclusive on H4. Note: requires evaluator be re-runnable on a
  fixed draft via an MCP action; if that's not currently exposed,
  STOP and escalate to dev.

REPORT: per-hypothesis verdict (CONFIRMED / DISCONFIRMED / NEEDS-MORE-DATA),
recommended fix per §3 of the diagnostic doc.
```

---

## 5. Sequencing recommendations

- **Pre-flight (dev or nav):** verify `get_recent_events(tag="evaluator")` and `tag="revise"` return non-empty rows. If empty, file a small dev task to add daemon-side emissions (~30-60 min) before the diagnostic mission runs.
- **Mission timing:** dispatch the diagnostic mission *after* Sporemarch resumes post-Fix-E AND after C16-S3 has logged ≥10 revise cycles. Earlier produces too little data to discriminate.
- **Hypothesis prioritization for dev:** H1 (score-ceiling) is most likely; H2 (revert-gate) second. If diagnostic confirms H1, dev should ship the score-ceiling escape hatch (§3.1) before further user-sim missions on Sporemarch — otherwise every Sporemarch mission rediscovers the same plateau.
- **If migration scenario 2 fires** (Fix-E cleanup + cleaner grounding lets daemon escape C16-S3), this whole diagnostic becomes hypothetical — but worth keeping for the next score-plateau occurrence (the pattern recurs across universes, per Mission 8's earlier C15 oscillation).

---

## 6. What this doc does NOT decide

- Which hypothesis is correct — that's the diagnostic mission's job.
- Whether to ship the fix shapes pre-emptively without diagnostic — recommend NOT; per PLAN.md "Bad decisions are data," fix the right hypothesis, not all four.
- Whether to harden the evaluator generally — that's a much larger architectural conversation tied to PLAN.md Evaluation principle and the §33 evaluation-layers unification work.

---

## 7. Summary for dispatcher

- **0 dev-time to ship this doc** — it's the diagnostic spec.
- **~30-60 min dev pre-flight** if `get_recent_events(tag="evaluator"|"revise")` returns empty (add daemon-side emissions).
- **5-prompt user-sim mission** discriminates between 4 hypotheses.
- **Per-hypothesis fix shapes pre-scoped** with dev-day estimates (~0.5-1.5 days each).
- **Dispatch-ready** when Sporemarch resumes post-Fix-E migration. Asymmetric bet: 15 min nav cost; if scenario 1 or 3 fires, zero-latency response. If scenario 2 fires, doc preserved for the next plateau occurrence.

When dev picks up #52 (#B4 score-plateau diagnostic), this doc is the entry point. Mission script in §4 is dispatch-ready user-sim copy.
