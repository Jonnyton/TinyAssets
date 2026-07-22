## ADDED Requirements

### Requirement: Existing write_graph handle creates and patches branches

`write_graph(target="branch")` SHALL expose the existing validated branch authoring path additively. With no `branch_id`, it SHALL accept `spec_json` and route to `build_branch`. With `branch_id`, it SHALL accept `changes_json` and preserve the existing `patch_branch` behavior. The router SHALL NOT implement a second branch schema.

#### Scenario: chatbot creates a branch in one call
- **WHEN** a caller supplies `target=branch`, no `branch_id`, and a valid `spec_json`
- **THEN** the existing `build_branch` handler validates and persists the branch
- **AND** the response carries the normal batch receipt

#### Scenario: existing branch patch remains compatible
- **WHEN** a caller supplies `target=branch`, `branch_id`, and `changes_json`
- **THEN** the existing `patch_branch` handler is invoked unchanged

#### Scenario: mixed create and patch payload is rejected
- **WHEN** a caller supplies `branch_id` and `spec_json` together
- **THEN** the response explains that create and patch payloads are mutually exclusive
- **AND** no branch state changes

### Requirement: Workflow definition schema is discoverable from the wiki

The shared commons SHALL contain a discovery-classified canonical workflow-definition schema page. The `write_graph.spec_json` field description SHALL name a `read_page` query that finds it.

#### Scenario: new user asks how to define a workflow
- **WHEN** a caller searches `read_page(query="workflow definition schema")`
- **THEN** the canonical schema page is returned in default discovery scope
- **AND** it includes a minimal valid `spec_json` example using START/END edges
