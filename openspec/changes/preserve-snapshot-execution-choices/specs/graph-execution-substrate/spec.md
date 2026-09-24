## ADDED Requirements

### Requirement: Immutable snapshots preserve branch execution choices

New immutable branch snapshots SHALL retain non-null branch-level default_llm_policy and concurrency_budget and include them in content identity. Previously stored snapshots MUST remain unchanged; unset fields MUST retain the prior absent-key snapshot form.

#### Scenario: Chosen execution settings survive publication

- **WHEN** an owner freezes a branch with a default model policy and concurrency budget
- **THEN** loading that version preserves both choices and changing either choice produces a distinct content identity

#### Scenario: Legacy snapshots remain immutable

- **WHEN** an old snapshot lacks these settings or a new branch leaves them unset
- **THEN** the old row is not rewritten, no choice is inferred from the current mutable branch, and new unset snapshots preserve the previous absent-key hash form

### Requirement: Branch execution choices are stored and authorable

Branch definitions SHALL persist an optional branch-level default model policy and an optional branch-level concurrency budget. The storage columns MUST be additive and nullable, NULL meaning unset — no value inferred, no existing row rewritten or backfilled. An owner SHALL be able to set, change and clear each choice through the existing authorized branch build and patch surface, with no new top-level MCP tool and no new field name; clearing MUST be indistinguishable from never having set the choice, in the stored row, the read receipt and the immutable snapshot.

#### Scenario: An owner sets a workflow-wide choice and reads it back

- **WHEN** an owner builds or patches a branch with a default model policy and a concurrency budget
- **THEN** both values are stored, returned by a later read of that branch, described on the authoring surface so they are discoverable, and echoed by the receipt that applied them

#### Scenario: Clearing returns the branch to unset

- **WHEN** an owner clears either choice
- **THEN** the branch behaves exactly as a branch that never set it, and its snapshot keeps the absent-key form

#### Scenario: A pre-existing branch is unaffected

- **WHEN** a branch definition stored before the choices existed is loaded, read or forked
- **THEN** both choices read as unset, the stored row is not rewritten, and no value is inferred from any other branch or version

### Requirement: Execution-choice validation matches the execution contract

This composes with the as-built "Branch validation is the compile gate" (`openspec/specs/graph-execution-substrate/spec.md:51`) and does not replace it: the same `validate()` return path carries these non-topology field errors, so build, patch and compile inherit one check.

An authored concurrency budget SHALL be accepted only as a positive integer, with booleans refused rather than coerced, matching the contract already enforced on the per-run override; values that the compiler would silently reinterpret or crash on MUST be refused at authoring time with an actionable message. Validation MUST NOT impose a structural ceiling on the budget. An authored default model policy SHALL be validated by the same policy-shape check used for node-level policies, preserving its forward-compatible treatment of unknown keys: an unknown key inside a policy is stored, not refused. Fields the check already knows to be invalid SHALL produce an explicit error rather than a stored value. Beyond that, the requirement is observability, not detection: a receipt that applies an execution choice MUST report the choices actually stored, so an author can read back what is in effect and see when a submitted field produced no stored value. It is NOT required to identify an unrecognized key inside a forward-compatible policy.

#### Scenario: A meaningless budget is refused at authoring time

- **WHEN** an owner submits a concurrency budget that is zero, negative, a boolean, or not an integer
- **THEN** authoring refuses with an explanatory error instead of storing a value the run would silently reinterpret or fail on later

#### Scenario: A fork keeps the parent's choices

- **WHEN** an owner forks a branch whose parent carries either execution choice
- **THEN** the fork inherits both choices unless its own specification overrides them
