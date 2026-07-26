## Why

The `graph-execution-substrate` spec still describes multi-writer `merge` fields as an accepted order-sensitive limitation, but commit `6b28cf89` / PR #1480 already made merge-reduced fields single-writer and fail-closed. The as-built spec must describe the enforcement that now protects graph execution from non-convergent fan-in.

## What Changes

- Replace the reducer requirement with the current contract while preserving `append` and unreduced-field behavior.
- Specify compile-time rejection when multiple nodes declare the same merge-reduced field as output.
- Specify runtime rejection when a node writes a merge-reduced field it did not declare.
- Retain the single-writer shallow, right-biased merge semantics, including wholesale replacement of nested values.
- Make no runtime or test changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `graph-execution-substrate`: Reconcile the state reducer requirement with the landed single-writer merge enforcement.

## Impact

Only the OpenSpec artifacts and the canonical `graph-execution-substrate` specification change. Runtime code and regression tests from `6b28cf89` remain untouched.
