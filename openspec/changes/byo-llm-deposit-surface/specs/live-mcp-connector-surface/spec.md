# Live MCP connector surface

## ADDED Requirements

### Requirement: BYO-LLM subscription deposit is a connection operation, not a new handle

The connector SHALL accept an LLM subscription deposit as an operation under the
existing `write_graph` handle — `write_graph target=connection
operation=connect_llm` — and SHALL NOT introduce a new advertised MCP tool handle
for it. The canonical advertised handle set SHALL remain exactly the pinned set
asserted by the public canary, so a deposit-surface deployment cannot regress the
handle catalog. The `connect_llm` operation SHALL dispatch to the owner-scoped
deposit handler and SHALL leave the existing `connection` operations
(`connect`/`reconcile`/`list`) unchanged.

#### Scenario: connect_llm is served without changing the advertised handles

- **WHEN** the deposit surface is deployed and the public canary asserts the
  advertised handle set
- **THEN** the canonical handle set is unchanged and the canary passes
- **AND** `write_graph target=connection operation=connect_llm` is reachable as an
  operation of the existing `write_graph` handle

#### Scenario: An unknown connection operation is still rejected

- **WHEN** a caller invokes `write_graph target=connection` with an operation that
  is neither an LLM deposit nor an existing GitHub connection action
- **THEN** the server returns an unknown-operation error and writes nothing
