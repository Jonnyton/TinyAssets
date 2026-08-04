# app-outbound-adapter Specification

## Purpose
TBD - created by archiving change app-outbound-adapter. Update Purpose after archive.
## Requirements
### Requirement: Deliver only a current authorized response
The adapter SHALL accept delivery only for an `AppReplyAuthorization` whose response digest matches the supplied private response body and whose destination is the exact destination already authorized by the custody and mapping gates.

#### Scenario: Body substitution is rejected before transport
- **WHEN** a caller supplies response text whose canonical digest differs from the authorization
- **THEN** delivery fails before invoking the transport and no receipt is written

### Requirement: Keep transport credentials outside the adapter contract
The adapter SHALL invoke a server-owned transport callback with only the authorized destination and response body; it SHALL accept no caller-supplied credential, URL, token, or provider override.

#### Scenario: Exact Slack destination reaches the server-owned transport
- **WHEN** a valid authorization targets Slack and the body digest matches
- **THEN** the callback receives that exact destination and body once
- **AND** the returned receipt contains no body or credential material

### Requirement: Make delivery idempotent and receipts content-redacted
The adapter SHALL reserve a deterministic authorization idempotency key, persist only redacted receipt metadata, and return the original receipt on an exact replay without invoking transport again.

#### Scenario: Retry after a lost response does not send twice
- **WHEN** the same authorization and body are delivered twice
- **THEN** the second call is marked as a replay and the transport invocation count remains one

### Requirement: Fail closed on transport failure
The adapter SHALL convert transport failures into a bounded adapter error and a redacted failed receipt; it SHALL not return exception text, response content, credentials, or an unbounded retry instruction.

#### Scenario: Transport failure does not leak secrets
- **WHEN** the server-owned callback raises an exception containing a secret
- **THEN** delivery raises the adapter error and persisted evidence contains only a fixed failure class

