## ADDED Requirements

### Requirement: ChatGPT Goal aliases normalize to the canonical Goal actions
The Goal dispatch surface SHALL accept exactly four compatibility action names—`list_workflow_goals`, `search_workflow_goals`, `get_workflow_goal`, and `propose_workflow_goal`—and normalize them respectively to `list`, `search`, `get`, and `propose` before handler dispatch. The available-action catalog SHALL include both canonical actions and these aliases, and an alias SHALL inherit the canonical handler's validation, authorization, attribution, and response behavior rather than define a second implementation.

#### Scenario: Read aliases dispatch canonical handlers
- **WHEN** a caller uses `list_workflow_goals`, `search_workflow_goals`, or `get_workflow_goal`
- **THEN** the request is handled as `list`, `search`, or `get` with the same arguments and result shape

#### Scenario: Propose alias retains write semantics
- **WHEN** a caller uses `propose_workflow_goal`
- **THEN** the request is handled as canonical `propose`, including its name validation, configured authorization mode, persistence, and best-effort contribution attribution

#### Scenario: Action discovery includes aliases
- **WHEN** an unknown Goal action requests the available-action catalog
- **THEN** the response includes the four compatibility aliases alongside canonical actions
