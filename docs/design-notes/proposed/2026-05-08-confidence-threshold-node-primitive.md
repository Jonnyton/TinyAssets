---
title: Confidence Threshold Node Primitive
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-PATCH
github_issue: 441
wiki_source: pages/patch-requests/pr-039-confidence-threshold-node-primitive-auto-process-when-sure-a.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#scene-loop
  - PLAN.md#evaluation
  - PLAN.md#community-evolvable-optimization
---

# Confidence Threshold Node Primitive

## 1. Recommendation Summary

Do not add a dedicated `confidence_threshold_node` runtime primitive as the
first response to this request. The requested behavior -- auto-process when
sure, ask the user when uncertain, and learn from the answer -- is mostly a
composition of existing Workflow concepts:

- an evaluator returns a typed judgment with evidence;
- a branch or node declares an automation policy for that judgment;
- uncertain cases pause for user-visible clarification or review;
- the user's answer becomes a durable lesson or branch patch with provenance.

The smallest useful project change is to record the design boundary before
runtime code lands. A platform primitive is only justified if existing
evaluator results cannot express the confidence signal and the user-answer
feedback cannot be captured as ordinary branch/node evolution. If that gap is
confirmed, ship a generic "decision gate over evaluator result" contract, not
a hardcoded confidence-threshold node type.

This follows the minimal-primitives rule: thresholds and routing recipes are
scaffolding unless they prove they unlock a reusable primitive that communities
cannot compose reliably.

## 2. Classification

Request type: project design / feature-shaping patch.

The filing asks for a new node primitive rather than a bug fix. It changes how
Workflow should model uncertain automation, user clarification, and learning.
That is architectural surface area, so this branch intentionally leaves runtime
files unchanged.

## 3. Composable Behavior

The requested behavior decomposes into four reusable pieces.

### Evaluator Output

The upstream node produces a candidate result. An evaluator then returns a
typed result:

```yaml
status: pass | fail | uncertain
confidence: 0.0..1.0
reason: short user-readable rationale
evidence_refs:
  - artifact://...
recommended_next: auto_continue | ask_user | reject | run_more_evidence
```

The confidence number is advisory evidence, not the sole control signal. The
important primitive is the typed evaluator result plus evidence. A threshold
without evidence encourages brittle automation.

### Decision Policy

A branch, node, or run may attach a policy that maps evaluator output to a
next step:

```yaml
on_evaluator_result:
  pass:
    min_confidence: 0.85
    action: auto_continue
  uncertain:
    action: ask_user
    prompt_ref: prompts/clarify-requirement.md
  fail:
    action: stop_for_review
```

This policy should live with the workflow artifact that owns the risk. It
should not be baked into a universal node type, because acceptable confidence
depends on domain, stakes, model, cost, and user preference.

### User Clarification

When policy chooses `ask_user`, the run records a blocked state with:

- the candidate output;
- the evaluator result and evidence;
- the exact question shown to the user;
- the user's answer;
- the resulting branch/node patch or continuation decision.

For chatbot users, this should surface as a normal clarification turn in the
MCP client. For local daemon hosts, it may appear as a tray notification or
pending-review queue. The contract is the same: no hidden auto-merge while the
policy says user input is required.

### Learning From Answers

The user answer should become a durable learning artifact only after it is
typed and scoped:

- If the answer corrects one branch's behavior, save it as a branch or node
  patch with provenance.
- If it reveals a reusable rule, save it as a lesson candidate that evaluators
  or community templates can consume.
- If it contradicts earlier lessons, preserve both with context instead of
  silently overwriting the older rule.

This avoids turning every clarification into global memory. User answers are
training signal, but their scope must be explicit.

## 4. What Not To Ship

Do not ship these as v1 platform code:

- a universal `confidence_threshold_node` type;
- a single global default threshold;
- automatic learning into daemon memory without provenance and scope;
- a chatbot-visible convenience action whose only job is "run if confident";
- hidden continuation after uncertainty without a user-visible blocked state.

Those options hardcode policy instead of strengthening primitives.

## 5. Smallest Runtime Follow-Up If Approved

If implementation is later approved, scope it as a generic evaluator-decision
gate:

1. Extend or confirm the evaluator result contract can carry `confidence`,
   `status`, `reason`, and `evidence_refs`.
2. Add a declarative policy field on the owning artifact, not a new standalone
   node type.
3. Persist a pending clarification record when policy chooses `ask_user`.
4. Convert the user's answer into an explicit branch/node patch, lesson
   candidate, or continuation event.
5. Add tests for auto-continue, ask-user, fail/stop, provenance capture, and
   conflicting lesson handling.

This follow-up should touch the runtime only after the evaluator and
clarification contracts are verified against existing code and current MCP
client behavior.

## 6. Open Questions

1. Which existing evaluator result shape is canonical today, and does it
   already carry confidence-like evidence?
2. Where should pending clarification records live in the current storage
   model: run state, branch activity, node activity, or a dedicated review
   queue?
3. Does chatbot-surface clarification need a new MCP response shape, or can it
   reuse existing blocked/pending state?
4. What is the minimum provenance required before a user answer can become a
   reusable lesson?
5. Which domains, if any, require a default "never auto-continue on confidence
   alone" policy because mistakes are high-risk?

## References

- `PLAN.md` Scoping Rules
- `PLAN.md` Scene Loop
- `PLAN.md` Evaluation
- `PLAN.md` Community Evolvable Optimization
