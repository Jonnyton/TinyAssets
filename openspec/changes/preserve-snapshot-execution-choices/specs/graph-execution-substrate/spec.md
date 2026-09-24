## ADDED Requirements

### Requirement: Immutable snapshots preserve branch execution choices

New immutable branch snapshots SHALL retain non-null branch-level default_llm_policy and concurrency_budget and include them in content identity. Previously stored snapshots MUST remain unchanged; unset fields MUST retain the prior absent-key snapshot form.

#### Scenario: Chosen execution settings survive publication

- **WHEN** an owner freezes a branch with a default model policy and concurrency budget
- **THEN** loading that version preserves both choices and changing either choice produces a distinct content identity

#### Scenario: Legacy snapshots remain immutable

- **WHEN** an old snapshot lacks these settings or a new branch leaves them unset
- **THEN** the old row is not rewritten, no choice is inferred from the current mutable branch, and new unset snapshots preserve the previous absent-key hash form
