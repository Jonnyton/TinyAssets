## Context

Batch A established canonical owners for previously unspecced shipped surfaces.
The remaining core-runtime gaps are not new capabilities: they extend three
existing owners created by the 2026-07-19 baseline. Current source implements
the behavior, but the canonical requirements stop before soul-affinity reads,
the fantasy-domain review topology, Goal protocol/discovery/claim surfaces, and
the persistent outcome-event registry.

This reconciliation is documentation-only. Code and focused tests establish
as-built truth. Where a test expectation contradicts current authorization code,
the spec records current code behavior and the discrepancy remains a test-drift
observation rather than a false requirement.

## Goals / Non-Goals

**Goals:**

- Extend the existing capability owners with strict requirements for every
  verified gap in this Batch B slice.
- Preserve the distinction between deterministic queue selection, advisory
  soul affinity, and future model-driven soul choice.
- Specify generic work-target persistence separately from fantasy-domain review
  and handoff behavior.
- Distinguish selector-driven quality ranking, deterministic gate ranking, and
  fixed archive-parent ranking.
- Keep persistent outcome records separate from explicitly invoked evaluator
  results and verification.

**Non-Goals:**

- Change runtime, APIs, storage, authorization, tests, or feature flags.
- Claim that Goal protocol metadata executes prerequisites, advances itself, or
  performs rollback.
- Claim semantic node similarity, user-buildable archive ranking, automatic
  bonus expiry, branch-scoped bonuses, or model-driven soul selection.
- Duplicate daemon identity, mini-Brain, generic evaluator, paid-market
  settlement, or gate-event verification requirements owned elsewhere.
- Repair known stale test expectations in this spec-only lane.

## Decisions

### 1. Modify existing capability owners instead of creating new ones

Soul-guided selection and work-target review extend
`daemon-runtime-and-dispatch`; protocols, convergence discovery, ladders,
claims, ranking, and bonus attachment extend `shared-goals-and-convergence`;
persistent outcome records extend `evaluation-outcomes-and-attribution`.

Alternative considered: new narrow capabilities for each cluster. That would
fragment concepts already named by the canonical baseline and create the same
ownership ambiguity corrected during Batch A review.

### 2. Keep soul guidance advisory and state its inert default

The dispatcher requirement will preserve normal queue filters and selection,
then describe the bounded read-only affinity term. It will state that the
default empty active-daemon ID and zero coefficient produce no soul boost, that
directed work is not excluded without an active daemon binding, and that lookup
failures retain ordinary eligibility.

Alternative considered: describe PLAN's future soul decision node. No shipped
runtime exposes candidate work to a model or persists a soul-choice receipt, so
that would be forward-state fiction.

### 3. Separate generic target storage from fantasy review topology

One requirement owns the generic target record and guarded helper transitions.
Fantasy-specific requirements explicitly name foundation review, authorial
heuristic selection, producer merge behavior, artifacts, and execution handoff.
The spec records that arbitrary enum-like strings can persist and that current
producer merging does not universally filter paused/discarded targets.

Alternative considered: present the fantasy loop as the generic engine review
contract. That would overstate portability and hide a known candidate-filtering
limitation.

### 4. Make ranking surfaces distinct

The existing selector-driven Goal leaderboard requirement will be narrowed to
the quality metric. New requirements separately own the deterministic highest-
rung outcome leaderboard and the fixed archive-consultation heuristic.
Common-node discovery remains exact `node_id` equality, not semantic search.

Alternative considered: call all three surfaces one leaderboard contract. They
use different authority, inputs, and ranking policies and cannot share one
truthful requirement.

### 5. Treat protocol rollback and gate verdicts as data unless executed

Goal protocols persist ordered step metadata, including prerequisite and
rollback fields, but no runtime interprets those fields. Bonus release accepts
a caller-supplied bounded verdict string; it does not invoke an evaluator. Both
limitations become normative so stored intent cannot be mistaken for enforced
behavior.

Alternative considered: infer execution from field names. Persisted metadata
is not behavior proof.

### 6. Keep outcome recording probe-free and unverified by default

The `extensions` outcome registry stores run-linked evidence without validating
run existence, invoking a prober, or producing `EvalResult`. Generic adapters
remain owned by `evaluation-runtime-and-scenarios`; gate-event attestation and
verification remain under the existing evaluation/outcomes requirements.

Alternative considered: duplicate evaluator-adapter contracts here. Batch A
already made that ownership explicit and independently reviewed.

## Requirement Evidence

| Capability / requirement | Current source owner | Focused evidence |
|---|---|---|
| Daemon: bounded advisory soul guidance | `tinyassets/dispatcher.py` | `tests/test_dispatcher_queue.py` |
| Daemon: generic work-target records/transitions | `tinyassets/work_targets.py`, `tinyassets/daemon_server.py` | `tests/test_work_targets.py` |
| Daemon: fantasy foundation review | `domains/fantasy_daemon/phases/foundation_priority_review.py`, `tinyassets/work_targets.py` | `tests/test_work_targets.py`, `tests/test_graph_topology.py` |
| Daemon: fantasy authorial selection/handoff | `domains/fantasy_daemon/phases/authorial_priority_review.py`, `dispatch_execution.py`, producer registries | producer, request-materialization, and work-target tests |
| Goals: ordered protocol metadata | `tinyassets/api/market.py`, `tinyassets/daemon_server.py` | `tests/test_goals_ladder_shape.py` |
| Goals: exact common-node discovery | `tinyassets/api/market.py`, `tinyassets/daemon_server.py` | `tests/test_goals_surface.py`, `tests/test_node_reuse_discovery.py`, `tests/test_branch_visibility.py` |
| Goals: fixed archive consultation | `tinyassets/api/market.py`, `tinyassets/daemon_server.py` | `tests/test_goals_surface.py` |
| Goals: ladder definition lifecycle | `tinyassets/api/market.py`, `tinyassets/daemon_server.py` | `tests/test_outcome_gates.py`, current handler authorization branches |
| Goals: claim/retract/list/run-claim lifecycle | `tinyassets/api/market.py`, `tinyassets/daemon_server.py` | `tests/test_outcome_gate_claims.py`, `tests/test_gates_claim_from_branch_run.py`, `tests/test_branch_visibility.py` |
| Goals: deterministic outcome leaderboard | `tinyassets/api/market.py`, `tinyassets/daemon_server.py` | gate-claim and leaderboard tests |
| Goals: node-only bonus attachment | `tinyassets/api/market.py`, `tinyassets/gates/actions.py` | `tests/test_gate_bonuses_mcp.py` |
| Goals: single-winner bonus resolution | `tinyassets/gates/actions.py` | `tests/test_gate_bonus_release.py` |
| Goals: quality-selector ownership boundary | `tinyassets/api/market.py`, selector storage/dispatch helpers | `tests/test_goals_set_selector.py`, Goal leaderboard tests |
| Evaluation: persistent unverified outcome registry | `tinyassets/api/market.py`, `tinyassets/outcomes/schema.py` | `tests/test_outcome_mcp.py` |

## Risks / Trade-offs

- [Risk] Large gate-lifecycle text duplicates Evaluation or Paid Market. →
  Mitigation: specify state transitions and visibility here, reference admission
  and settlement owners, and state caller-supplied verdict limits.
- [Risk] Stale tests are mistaken for current authorization truth. → Mitigation:
  ground requirements in current handlers and record focused failures without
  silently changing code.
- [Risk] Work-target review is generalized beyond the fantasy domain. →
  Mitigation: name the fantasy cycle in every topology/selection requirement.
- [Risk] Soul affinity is interpreted as autonomous soul choice. → Mitigation:
  specify the zero-default coefficient, token-based formula, read-only nature,
  and absent durable receipt.
- [Trade-off] Documenting lifecycle bugs and stranded-bonus cases makes the
  contract less aspirational. → Honest limitations are required for canonical
  as-built truth and make later fixes explicit deltas.

## Migration Plan

1. Draft three delta specs against their exact existing canonical requirements.
2. Map every added/modified requirement to current code and focused tests.
3. Strict-validate the change and obtain independent grounding/ownership review.
4. Archive the change to sync canonical specs, then validate the complete tree
   and compare archived deltas with canonical results.
5. Land through the normal PR path and promote the next collision-free Batch B
   slice.

Rollback is a documentation revert; no runtime or data migration occurs.
