## ADDED Requirements

### Requirement: Served owners can edit ordinary node configuration in place

The served `write_graph` branch patch surface SHALL permit an authorized owner to revise a node's description, phase, model preference, reasoning effort, input/output keys, timeout, retry policy and enabled state through the canonical staged updater, in addition to its existing content, policy, effect and workspace declarations. Editing SHALL preserve branch/node identity, unrelated fields and immutable previously admitted run definitions; it SHALL NOT confer execution or connection authority.

#### Scenario: Output mapping and timeout are repaired without rebuilding

- **WHEN** an owner patches an existing node's output keys with matching state-schema changes and lowers its timeout to a valid value
- **THEN** canonical readback shows those values on the same branch and node
- **AND** a subsequent admitted run uses the revised definition without altering a previously admitted snapshot

#### Scenario: Ordinary settings share canonical validation

- **WHEN** an owner updates any accepted configuration field with a valid canonical value
- **THEN** canonical persistence and served readback agree, and omitted fields stay unchanged

#### Scenario: Invalid batches and authority edits persist nothing

- **WHEN** a patch mixes valid changes with malformed configuration, a disallowed field, or an unauthorized target
- **THEN** the entire batch is refused without changing the stored branch
- **AND** author/approval/grant/tool authority, publication and invocation restrictions remain in force

#### Scenario: Configuration does not grant execution

- **WHEN** an owner saves valid execution configuration
- **THEN** the edit dispatches no work and creates no consent or connection grant
- **AND** subsequent execution remains subject to existing admission, budget, sandbox and per-dispatch authorization checks
