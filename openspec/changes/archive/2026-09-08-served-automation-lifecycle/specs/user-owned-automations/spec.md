## ADDED Requirements

### Requirement: Served agents can reach the owner's automation lifecycle
The served graph tools SHALL expose automation list/get/create/pause/resume/delete
using the same owner-scoped adapter as the canonical connector, with bound actor,
pinned universe and existing authorization, revision and creation preflight.
No operation SHALL require exposing a raw credential or editing a workflow.

#### Scenario: Inspect an attached automation
- **WHEN** a bound served agent reads its universe's automations or selects one by ID
- **THEN** it receives the existing projected state and revision, without another universe's record

#### Scenario: Owner pauses or retires an automation
- **WHEN** the bound owner requests pause or delete with the current revision
- **THEN** the existing handler changes only that automation and readback reflects the result
- **AND** the receipt does not claim that an already-running job has stopped

#### Scenario: Retired automation no longer prevents branch deletion
- **WHEN** an owner retires an automation through the served route
- **THEN** the existing dependency query no longer lists that automation as a blocker
- **AND** unrelated branch dependencies remain authoritative

#### Scenario: No execution budget or ready provider is needed to stop a trigger
- **WHEN** the owner can authenticate and control the row but new execution is unavailable
- **THEN** pause/delete still reach their existing owner-scoped control handler

#### Scenario: Stale or foreign control request
- **WHEN** a control request has a stale revision or selects another universe's automation
- **THEN** the existing revision conflict or uniform not-found refusal is returned and no row changes

#### Scenario: Create or resume intentional recurring work
- **WHEN** the bound agent requests create or resume
- **THEN** existing ownership, creation preflight where applicable, store limits and runtime execution authority remain in force
- **AND** create uses fail-closed engine admission rather than bypassing execution safeguards

#### Scenario: Unsupported action or malformed payload
- **WHEN** an unsupported operation or malformed create payload is submitted
- **THEN** a structured refusal is returned without falling through to another action

#### Scenario: Documentation and dispatch agree
- **WHEN** the served tool description teaches an automation target and operation
- **THEN** that pair is accepted by the routing layer or has an explicit truthful refusal, never a hidden missing-tool path
