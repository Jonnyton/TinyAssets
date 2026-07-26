## MODIFIED Requirements

### Requirement: The per-job runner exposes a versioned typed seam with a strict JSON-object payload

`tinyassets.sandbox_runner` SHALL define protocol `runner/v1`, request schema
`runner-job/v1`, and result schema `runner-result/v1`, with frozen typed carrier
dataclasses for requests, capability reports, enforcement receipts, and
results. A request wire object SHALL contain schema version, job ID,
idempotency key, owner scope, capability, derived actions, payload, workspace
reference, and credential-grant reference. The payload SHALL be detached
through strict JSON serialization, reject non-finite values and
non-JSON-serializable Python values, and be a JSON object. Actions SHALL be
derived from the immutable capability mapping rather than accepted from the
caller.

The supported capability/action pairs SHALL be:
`source_exec` → `source_exec`; `repo_read` → `list, read`; `repo_exec` →
`list, read, exec`; and `coding` → `list, read, write, exec`. The result status
vocabulary SHALL be exactly `succeeded`, `failed`, and `cancelled`.
The `job_id`, `idempotency_key`, `owner_scope`, `workspace_ref`, and
`credential_grant_ref` fields are carried through without runtime type,
nonempty, or JSON validation; their dataclass annotations are not an
authentication or shape check. The capability is instead dereferenced through
the enum and immutable action mapping.

This nine-field runner seam does not contain universe, selected provider, host,
or assignment-generation fields and SHALL NOT be treated as the validator for
a provider credential binding. The shipped capability set does not become
credential-bearing merely because the carrier field exists. Before any future
provider invocation is converted to `runner/v1`, its owner-accepted adapter
SHALL first validate the authority required by its fulfillment class.
Requester-owned local invocation SHALL use
`constrain-set-engine-provider-authority`'s exported
`ProviderAssignmentAdmission`, frozen
`ProviderInvocation -> ProviderLaunchHandle` barrier, and exact opaque binding.
Accepted-market remote execution SHALL use its owner-accepted production B2
authority contract. The current D0 path is fake-only/production-denied and
SHALL NOT be required or accepted as ordinary requester-provider authority.
Only an owning adapter MAY copy an already-validated non-secret locator into
`credential_grant_ref`. The field SHALL remain a locator rather than a bearer
grant, and an empty capability ceiling SHALL NOT stand in for missing
authority.

#### Scenario: Capability determines the wire action list
- **WHEN** a `coding` request is serialized
- **THEN** its sorted actions are exactly `exec`, `list`, `read`, and `write`
- **AND** the wire object contains the nine landed request fields

#### Scenario: Non-JSON request data is refused before dispatch
- **WHEN** the payload contains a callable, another non-JSON-serializable value, or a non-finite number, or the payload is not an object
- **THEN** serialization raises `SandboxRequestError`
- **AND** no backend dispatch occurs

#### Scenario: runner carrier does not validate provider authority
- **WHEN** a current shipped runner request carries an empty or non-empty `credential_grant_ref`
- **THEN** `SandboxRunner` preserves the canonical nine-field carrier behavior and does not infer universe, provider, host, assignment generation, or execution authority
- **AND** the field confers no provider credential or dispatch authority

#### Scenario: requester-owned local invocation uses provider assignment admission
- **WHEN** an accepted requester-owned local invocation is later routed through `runner/v1`
- **THEN** its provider-authority-owned adapter validates the frozen invocation and exact binding under shared `ProviderAssignmentAdmission` before constructing or dispatching the runner request
- **AND** fake-only D0 is neither required nor accepted as provider authority

#### Scenario: accepted-market execution waits for production B2 authority
- **WHEN** an accepted-market remote invocation would be routed through `runner/v1`
- **THEN** it remains held until the distributed-execution owner accepts a production B2 authority composition
- **AND** neither an opaque locator nor a fake-only/production-denied D0 record authorizes backend or provider dispatch
