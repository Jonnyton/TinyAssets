## Context

The baseline `graph-execution-substrate` specification documented `_dict_merge` as an accepted non-convergent fan-in limitation. Commit `6b28cf89` / PR #1480 retained that shallow right-biased reducer but constrained it to one declared writer: compilation rejects multiple declared writers, and wrapped node execution rejects undeclared merge-field writes. The landed regression suite proves those two guards and stable single-writer execution.

## Goals / Non-Goals

**Goals:**

- Make the canonical reducer requirement match the landed compiler and runtime guards.
- Preserve the existing `append`, unreduced overwrite, and shallow single-writer merge contracts.
- Express the replacement as one complete `MODIFIED` requirement so syncing is deterministic and preserves unrelated requirements.

**Non-Goals:**

- Change runtime code, tests, reducer data structures, or graph APIs.
- Make merge commutative, convergent, or deep.
- Alter any requirement outside the state-reducer block.

## Decisions

1. **Replace the complete reducer requirement.** The delta repeats the requirement and all of its scenarios under `MODIFIED Requirements`, because the old multi-writer scenario is no longer valid and OpenSpec modification semantics require full replacement.
2. **Specify both enforcement boundaries.** Static output declarations provide the compile-time single-writer proof; a runtime guard closes the gap when node code returns a merge field absent from its declarations.
3. **Keep the shallow reducer semantics explicit.** With one declared writer, `_dict_merge` remains a right-biased top-level union. Nested values are replaced wholesale, not recursively merged.

Alternatives considered: describing only the new guards as an added requirement would leave the contradictory multi-writer scenario canonical; defining a convergent lattice or deep merge would invent behavior not present in the landed implementation.

## Risks / Trade-offs

- **Specification accidentally drops append or unreduced behavior** → Retain both scenarios in the full modified requirement.
- **Sync overwrites unrelated graph requirements** → Merge only the named reducer block and verify a second sync is a no-op.
- **Declared outputs differ from actual writes** → Preserve the runtime fail-closed scenario alongside compile-time validation.

## Migration Plan

Sync the modified requirement into the existing `graph-execution-substrate` spec, run strict validation and the three landed reducer-law tests, verify sync idempotence, then archive the completed change. No deployment or rollback is required because runtime behavior is unchanged.

## Open Questions

None.
