## MODIFIED Requirements

### Requirement: State fields accumulate per their declared reducer
The compiler SHALL synthesize the run's state type as a `TypedDict` (Hard Rule #5) whose per-field merge behavior follows each `state_schema` field's declared `reducer`: `append` maps to `Annotated[list, operator.add]`, `merge` maps to `Annotated[dict, <shallow merger>]` under a single-writer contract, and any other value (including unset) is last-write-wins overwrite. For every merge-reduced field, compilation SHALL reject a graph with more than one node that declares the field through `output_keys` or `output_mapping`, and node execution SHALL fail closed if a node writes that field without declaring it. With exactly one declared writer, the merger SHALL remain a shallow, right-biased `dict.update`: right-hand top-level keys overwrite matching left-hand keys, left-only keys remain, and nested values are replaced wholesale rather than deep-merged.

#### Scenario: an append field concatenates contributions
- **WHEN** two nodes each write a list to a state field declared `reducer="append"`
- **THEN** the field's value is the concatenation of both contributions via `operator.add`

#### Scenario: an unreduced field is overwritten
- **WHEN** a field has no recognized reducer and two nodes write it
- **THEN** the last write wins and the earlier value is discarded

#### Scenario: multiple declared merge writers fail compilation
- **WHEN** more than one graph node declares the same `reducer="merge"` field in `output_keys` or `output_mapping`
- **THEN** `compile_branch` raises `CompilerError` because a merge-reduced field requires a single writer

#### Scenario: an undeclared merge write fails closed at runtime
- **WHEN** a compiled node returns a value for a `reducer="merge"` field absent from that node's `output_keys` and `output_mapping`
- **THEN** node execution raises `CompilerError` instead of applying the undeclared write

#### Scenario: one declared merge writer shallow-merges right-biased
- **WHEN** the sole declared writer updates a merge-reduced dict containing overlapping top-level keys, left-only keys, and a nested value
- **THEN** the resulting dict preserves left-only keys and uses the writer's values for overlapping keys
- **AND** the writer's nested value replaces the prior nested value wholesale rather than being deep-merged
