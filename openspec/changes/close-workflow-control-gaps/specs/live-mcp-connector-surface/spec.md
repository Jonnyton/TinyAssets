## ADDED Requirements

### Requirement: Owned workflow lifecycle is reachable through graph handles
The graph handles SHALL expose owned workflow editing, exact persisted output
inspection, accurate node failure status, and cancellation without new top-level
tools or extra provider authority. Served selection SHALL remain pinned to its
universe and enforce the existing record ACL before content or mutation.

#### Scenario: Agent follows workflow edit guidance
- **WHEN** an authorized agent uses the operation and payload taught by the edit guidance
- **THEN** a valid owned-node content edit succeeds and reads back without rebuilding the workflow
- **AND** invalid or unauthorized edits refuse without changing the definition

#### Scenario: Code produces ordinary values
- **WHEN** an owned run produces Unicode text, numbers or structured state output
- **THEN** the agent can discover the output fields and retrieve their exact values through read_graph
- **AND** bounded responses explicitly provide continuation rather than silently dropping data

#### Scenario: Another universe's run identifier is supplied
- **WHEN** a pinned served agent selects a run outside its universe for run inspection, output or cancellation
- **THEN** it refuses without disclosing run content or mutating the run, even if broader public read access exists

#### Scenario: Code fails in a parallel workflow
- **WHEN** one code node raises while a sibling is active or complete
- **THEN** the failing node is recorded as failed with its own graph identity and original failure reason
- **AND** no sibling is falsely labeled as the failing node

#### Scenario: Owner cancels queued or running work
- **WHEN** the agent requests cancellation of its queued or running run through run_graph
- **THEN** the existing runner receives the request without another run admission or provider launch
- **AND** request acknowledgement remains distinct from observed terminal cancellation

#### Scenario: Cancel is repeated after completion
- **WHEN** the selected run is already terminal
- **THEN** the actual terminal status is returned without a new cancellation record or false cancelled claim

#### Scenario: Workspace cleanup follows a real ancestor
- **WHEN** discard names this run's held workspace created by a graph ancestor with no HTTP result
- **THEN** absence from the HTTP response map does not refuse the authorized discard
- **AND** a parallel non-ancestor workspace remains inaccessible and actual cleanup settlement is preserved
