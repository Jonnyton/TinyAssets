## Context

Run persistence currently starts in `tinyassets.runs._prepare_run`. Both
live-definition and immutable-version asynchronous execution reach
`_execute_branch_core`, which freezes the Branch snapshot and then immediately
calls `_prepare_run`. Missing state is discovered later by compiled nodes, after
the run row and pending events exist.

The preflight must understand graph topology without executing user code. Branches
may fork, join, and loop, so "some predecessor writes this key" is insufficient:
the producer must be guaranteed to run before the consumer on every possible
route. Public handlers must also preserve their existing authorization order so a
new diagnostic cannot disclose a private Branch contract.

## Goals / Non-Goals

**Goals:**

- Refuse unresolved declared node inputs before `_prepare_run`.
- Share one analysis and error contract across live-definition and immutable-
  version execution.
- Count caller values, schema defaults, and topology-guaranteed predecessor
  outputs as available.
- Return deterministic, agent-actionable guidance while producing no durable or
  external activity.

**Non-Goals:**

- Validate input values against schema types.
- Predict conditional-router outcomes or execute nodes during preflight.
- Repair or mutate a user's Branch, infer missing values, or add authority.
- Change runtime handling for outputs a node declares but then fails to emit.
- Add a new run target or MCP handle.

## Decisions

### 1. Use bounded superstep-frontier analysis over the frozen Branch snapshot

The analyzer models LangGraph's execution barrier: ordinary fan-out activates all
children in the next superstep and merges all sibling outputs, while a conditional
edge activates exactly one declared target. It explores possible active-node
frontiers independently for each required key and tracks whether that key has been
produced by a completed earlier superstep. Caller inputs and non-`None` canonical
or legacy defaults start available. A consumer reached while its key is unavailable
makes the submission unresolved. Repeated frontier/availability states terminate
legal loops, and direct `START` activation prevents a later loop output from being
mistaken for a first-entry value.

Exploration is capped at 4,096 distinct states/frontiers per key. Crossing the cap
fails conservatively as unresolved rather than letting user-authored topology turn
preflight into an admission-layer denial of service.

Alternatives considered: accepting any ancestor producer creates false negatives
at conditional joins; intersecting predecessor outputs incorrectly rejects a valid
parallel diamond where one sibling produces state merged at the barrier; checking
only the entry node misses later consumers; compiling/invoking speculatively can
call user code or providers.

### 2. Raise a typed pre-admission exception from shared execution code

`_execute_branch_core` freezes the definition, runs the analyzer, and raises
`MissingRequiredInputs` before `_prepare_run`. The synchronous live/version paths
perform the same check immediately before their `_prepare_run` call. This makes
the persistence boundary enforce the invariant for MCP, triggers, and internal
callers rather than relying only on presentation handlers.

The exception carries sorted missing keys and guidance derived only from the
already-authorized frozen schema. Public run handlers serialize it as
`failure_class=missing_required_inputs`, `missing_input_keys`, `input_guidance`,
`suggested_action`, and `actionable_by=chatbot`, and omit `run_id`.

Alternative considered: checking only in `tinyassets/api/runs.py` is simpler but
lets scheduler, trigger, and future callers bypass the invariant.

### 3. Keep authority and immutable-target ordering unchanged

The live-definition handler continues to resolve and authorize the Branch before
loading its contract. The version handler continues through its existing immutable
version resolution. Preflight occurs only after the authorized target is loaded
and frozen, and that same object is passed to execution, avoiding a live-definition
time-of-check/time-of-use gap.

### 4. Guidance is descriptive, not coercive

For each missing key, guidance includes its declared type (or `any`), optional
description, and a JSON-compatible example shape (`""`, `0`, `false`, `[]`, `{}`,
or `null`). Presence in caller inputs satisfies preflight even for falsey values;
runtime semantics remain responsible for value interpretation.

## Risks / Trade-offs

- **[Conditional paths can be over-conservative]** → Require inputs for every
  possible route unless graph topology guarantees a producer; document that an
  owner can provide a default when a route-specific value is optional.
- **[Malformed topology could confuse analysis]** → Run existing Branch validation
  first and fail loudly; the analyzer never tries to repair invalid graphs.
- **[Declared output may not be emitted at runtime]** → Preserve the existing
  runtime failure; preflight proves only the declared contract, not implementation
  correctness.
- **[A direct internal caller may now receive an exception]** → Use a dedicated
  exception with stable fields and cover synchronous, asynchronous, trigger, and
  version callers in tests.

## Migration Plan

No storage migration is required. Deploy the new preflight and response mapping,
run focused tests plus the public handle canary, then obtain rendered proof from a
bound agent using an owner-controlled disposable Branch. Rollback is a code revert;
no data cleanup is needed because refusals create no rows.

## Open Questions

None.
