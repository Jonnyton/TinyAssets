## ADDED Requirements

### Requirement: Authenticated private feedback
The app SHALL accept bug reports, patch requests and ideas from authenticated users only, store their text verbatim, and return a durable ticket ID after commit. The server SHALL derive ownership from the current principal. The reporter and explicitly configured reviewer SHALL be the only readers.

#### Scenario: Retry after a lost response
- WHEN the same reporter retries identical content with the same idempotency key
- THEN the service returns the same ticket without an additional ticket or history entry.

#### Scenario: Cross-account read
- WHEN a different non-reviewer requests a ticket ID
- THEN the service returns not found without exposing the report.

### Requirement: Review and follow-up
The service SHALL support revision-checked reviewer status changes, reporter replies, history, JSON export, deletion, and account-deletion erasure. User content and tool receipts SHALL remain untrusted and SHALL NOT authorize execution.

#### Scenario: Concurrent status update
- WHEN two reviewers update the same revision
- THEN exactly one succeeds and the other receives a conflict.

#### Scenario: Reviewer not configured
- WHEN intake has no configured reviewer
- THEN submission fails with a configuration error and persists nothing.

### Requirement: Bounded admission and output
The service SHALL bound HTTP input, per-principal submissions, ticket history and graph output. Reads SHALL NOT initialize storage.

#### Scenario: Concurrent repeated submit
- WHEN multiple requests carry one idempotency key and payload
- THEN exactly one creates a ticket.
