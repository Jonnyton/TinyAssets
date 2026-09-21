## ADDED Requirements

### Requirement: Served owners can edit existing effect and workspace declarations

The served write_graph branch patch surface SHALL allow an authorized author to
add effect-bearing nodes and replace or clear an existing node's effects and
workspace declarations using the same admitted effect grammar as served creation.
Omitted declarations SHALL remain unchanged. The edit SHALL grant no connection,
consent, provider, filesystem or execution authority and SHALL dispatch no effect.
Source-review provenance SHALL retain its existing source-bound semantics, never
become an execution gate or be accepted from caller-supplied approval metadata.
Existing ownership, runtime consent, resource, sandbox and workspace ancestor/lease
checks SHALL remain effective. There SHALL be no per-branch effect-node count cap.

#### Scenario: Owner revises an existing effect without rebuilding

- **WHEN** an authorized author patches an existing node to use an admitted sink
- **THEN** the original branch identity is retained and readback shows the declaration
- **AND** clearing effects with an empty array or null removes the declaration
- **AND** an unrelated edit leaves the declaration unchanged

#### Scenario: Owner adds an effect-bearing node

- **WHEN** an author adds a node with a declaration accepted by served creation
- **THEN** the existing branch gains the node without a graph-size refusal
- **AND** caller-supplied approval and author fields are stripped as on creation

#### Scenario: Workspace declaration is an ancestor reference not a grant

- **WHEN** the owner changes or clears the workspace declaration
- **THEN** canonical string/null semantics apply and the result persists on the same node
- **AND** execution still refuses a missing or non-ancestor workspace or invalid lease

#### Scenario: Invalid batch or foreign edit persists nothing

- **WHEN** a patch contains a malformed declaration, unadmitted sink, repeated sink,
  forbidden authority field, or targets another author's branch
- **THEN** it refuses without changing the persisted branch or firing an effect

#### Scenario: Declaration does not bypass consent

- **WHEN** a successfully edited node later tries an external operation without its required consent
- **THEN** the runtime refuses under the same authority rules as a newly created node
- **AND** the edit has neither minted a grant nor made the operation authorized
