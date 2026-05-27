# Authority Resolver Contract v1

Source: live wiki PR-139, CHILD-4 build-order step 1.

This spec freezes the decision payload shape that later PR-139 slices may
consume before a resolver runtime exists. It is intentionally a contract, not a
policy engine.

## Version

- Decision schema: `resolver-decision-v1`
- Contract/runtime placeholder: `authority-resolver-contract-v1`
- Fixture pack: `tests/fixtures/resolution/resolver_decision_v1.json`
- Python contract: `workflow.resolution`

Schema changes require a new schema version, fixture updates, and a
compatibility/deprecation note. A consumer must not silently treat a future
schema as v1.

## Inputs

`ResolverInput` contains:

- `question`: the authority or evidence question being resolved.
- `scope`: universe-first resource boundary.
- `conflict_type`: typed conflict label.
- `citations`: evidence handles with source role, surface type, reference, and
  claim text.

Unknown source roles or surface types are accepted at the input boundary so the
resolver can produce an auditable fail-closed decision.

## Decision Payload

`ResolverDecision` contains:

- `schema_version`: exactly `resolver-decision-v1`.
- `status`: one of `resolved`, `unresolved`, `needs-human-decision`.
- `confidence`: float from `0.0` to `1.0`.
- `evidence_handles`: cited handles preserved in the decision.
- `source_role_map`: map from evidence handle to the resolved source-role label.
- `resolver_version`: resolver or contract version.
- `reason`: concise audit reason.

`unresolved` is a structural status. No universe setting, authority weight, or
configuration may remove it from the contract.

## Taxonomy Guard

Known surface types in v1:

- `merged`
- `running`
- `proposed`
- `compiled`
- `released`
- `worktree-head`
- `worktree-snapshot`
- `local-snapshot`

Unknown surface types fail closed as `unresolved`; they do not receive guessed
precedence. New surface types enter through brain/wiki convention and host gate
when security implications exist.

Known source roles in v1 are intentionally small and may be expanded by a later
contract version. Unknown source roles fail closed as `unresolved`.

Known source-role labels in v1:

- `claimant`
- `reviewer`
- `operator`
- `runtime-observation`
- `evidence-source`
- `merged-code`
- `running-system`
- `proposed-change`
- `compiled-artifact`
- `released-artifact`
- `worktree-snapshot`

## Required Fixture Cases

The v1 fixture pack must include:

- Constructed real conflict returning `unresolved`.
- Surface mismatch where claims are reframed under typed surfaces and preserved.
- Unknown surface type returning `unresolved`.

Later resolver runtime work must keep these cases passing before it can consume
the contract for permission or tag-matrix behavior.
