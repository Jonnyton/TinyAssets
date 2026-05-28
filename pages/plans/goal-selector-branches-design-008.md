---
title: Goal selector branches
type: plan
status: working-draft
source_issue: 995
wiki_source_path: pages/design-proposals/design-008-goal-selection-logic-should-be-user-buildable-bind-a-selecto.md
created: 2026-05-21
tags: [goals, selection, leaderboard, user-buildable, substrate]
---

# Goal selector branches

## Purpose

Goal selection policy should be user-buildable. The platform may ship a
reference selector that preserves today's `quality_leaderboard` behavior, but
the weights that define "best" belong in a selector Branch bound to a Goal, not
as permanent substrate taste.

This page captures DESIGN-008 as a brain-plan record instead of a
`docs/design-notes/proposed/` draft. It keeps the design aligned with PLAN.md's
scoping rules: ship the smallest substrate gap that lets communities evolve
selection logic themselves.

## Current State

`workflow/api/quality_leaderboard.py` computes:

```text
score = 3.0 * normalized_judgment_score
      + 1.5 * log1p(completed_run_count)
      + 2.0 * log1p(fork_count)
      + 2.0 * recency_decay
      + 1.0 * has_gate_rung
      + 1.5 * safe_to_publish
      - 1.0 * log1p(failed_run_count)
```

`recommended_parent_for_fork` returns the top entry from that same fixed
ranking. The formula is disclosed in API output, but every Goal still inherits
the same platform-chosen weights.

## Design Position

Treat selector logic as a Workflow artifact:

- A selector is a published Branch version that reads a bounded selector input
  packet and emits an ordered list of candidate Branches with rationale.
- A Goal may bind one selector via `goals.selector_branch_version_id`.
- `recommended_parent_for_fork` resolves the Goal's selector. If no selector is
  bound, it falls back to the reference selector that mirrors today's formula.
- The selector input packet is built from existing primitive signals only:
  branch metadata, run counts, judgment summaries, fork counts, gate claims,
  publication-safety signal, and recency.
- Selector Branches compete for the selector slot through the same Goal,
  gate, and canonical-selection primitives used by ordinary Branches.

The platform owns the binding and invocation contract. Communities own the
selection policy.

## Slice 1: Selector Binding Contract

Add the substrate field and write action without changing ranking behavior:

1. Add nullable `goals.selector_branch_version_id`.
2. Add `goals action=set_selector goal_id=<id> branch_version_id=<published-version-or-empty>`.
3. Use the same authority rule as `set_canonical`: Goal author or host-level
   actor may bind or unset the selector.
4. Validate that the selector target is a published Branch version.
5. Return the selector id from `goals action=get` so chatbots can explain which
   selection policy is active.

Acceptance:

- Existing Goals with no selector keep using today's `quality_leaderboard`
  ranking.
- Unauthorized actors receive a structured rejection matching
  `set_canonical` style.
- Unpublished or missing Branch versions are rejected.

## Slice 2: Reference Selector Parity

Materialize today's formula as the default reference selector:

1. Define the selector input packet schema from the existing leaderboard
   signals.
2. Define the selector output schema:
   `[{branch_def_id, score, rationale, signal_summary}]`.
3. Keep the in-platform formula as the fallback implementation until the
   reference Branch can be invoked reliably through the normal branch runtime.
4. Add parity tests proving fallback output and reference-selector output rank
   the same fixture candidates.

Acceptance:

- `recommended_parent_for_fork` gives the same answer as before when no custom
  selector is bound.
- The API response names the selector source: `reference_formula`,
  `bound_selector`, or `fallback_reference_formula`.
- Selector failures do not break parent discovery; they fall back with a
  visible warning.

## Slice 3: Bound Selector Routing

Route parent recommendation through the bound selector:

1. Build the selector input packet from the same visibility-filtered candidate
   set that `quality_leaderboard` uses today.
2. Invoke the published selector Branch version.
3. Validate output against the selector output schema before trusting it.
4. Drop candidate ids that are not in the visibility-filtered input set.
5. Preserve deterministic fallback to the reference selector on invalid output,
   runtime failure, or timeout.

Acceptance:

- A Goal-bound selector can reorder candidates without modifying platform
  Python constants.
- Private or unauthorized Branches cannot be surfaced by selector output.
- Invalid selector output is reported as fallback metadata, not exposed as a
  broken recommendation.

## Non-Goals

- Do not add per-domain platform formulas.
- Do not let selector Branches read arbitrary private content.
- Do not replace `quality_leaderboard` immediately; it remains the visible
  reference implementation and fallback.
- Do not auto-promote a selector to canonical-selector status without the same
  authority and review gates used for other Goal-level bindings.

## Open Checks Before Runtime Work

- Confirm the published-Branch invocation primitive can run a selector without
  mutating the target Branch.
- Decide whether selector execution belongs in the same timeout and budget
  envelope as `recommended_parent_for_fork`.
- Decide whether selector Branches need an explicit capability tag, or whether
  schema validation at invocation time is enough for v1.

## References

- Issue #995 / DESIGN-008
- PLAN.md: Scoping Rules
- PLAN.md: Module: Goals & Gates
- PLAN.md: Module: Evolution & Evaluation
- `workflow/api/quality_leaderboard.py`
