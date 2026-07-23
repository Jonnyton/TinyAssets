## ADDED Requirements

### Requirement: Canonical request writes expose one body-bound idempotent admission schema
`write_graph(target="request")` SHALL require one public field named
`idempotency_key`, 16–128 ASCII characters matching
`^[A-Za-z0-9._:-]+$`, and SHALL accept `graph_id`, `text`, `request_type`,
`branch_id`, `pickup_incentive`, `directed_daemon_id`,
`directed_daemon_instruction`, and `priority_weight`. Priority weight SHALL be
a JSON number rather than a string or Boolean, finite, and in inclusive range
`[0, 100]`. Actor, tenant, universe authority, trigger tier, and evidence SHALL
be server-derived. Unknown request-target fields, caller-supplied tiers or
evidence, NaN, infinities, negatives, and over-cap weights SHALL be rejected
before persistence. Weight zero SHALL be an explicit ordinary opt-out. A
positive weight without active exact-universe priority authority SHALL return
`priority_authorization_required` with zero persistence rather than silently
demoting the request.

The public directory implementation SHALL expose the same request-admission
schema and behavior as the main connector. The handle-level
`idempotentHint` SHALL remain false because other `write_graph` targets are not
idempotent.

#### Scenario: valid numeric boundaries are accepted
- **WHEN** otherwise valid request writes use priority weights `0`, `1e-9`, a finite value immediately below `100`, or exactly `100`
- **THEN** the value passes numeric-shape/range validation
- **AND** authority policy determines whether it is accepted as priority

#### Scenario: zero is ordinary even with a priority grant
- **WHEN** an authorized caller submits weight zero
- **THEN** the result uses `user_request` with accepted weight zero, or `owner_queued` when validly directed
- **AND** the operator writer gate is not required

#### Scenario: positive weight without active priority authority fails
- **WHEN** an ordinarily authorized caller requests positive weight without an active exact-universe priority grant
- **THEN** the result contains `error="priority_authorization_required"` with zero persistence
- **AND** it is not silently admitted as ordinary work

#### Scenario: invalid input fails before admission
- **WHEN** the key is missing/malformed, a request field is unknown, or weight is Boolean, string, NaN, infinite, negative, or above `100`
- **THEN** the result is a validation error with zero Request/admission/task persistence
- **AND** it exposes no authority evidence

#### Scenario: directory and main connector remain request-compatible
- **WHEN** the same authenticated request is sent through the main connector and `/mcp-directory`
- **THEN** both enforce the same fields, authorization, idempotency, and result contract
- **AND** neither surface silently demotes or uses a legacy request writer

### Requirement: Successful request-admission results are complete, exact, and rank-free
A committed canonical request write SHALL return exactly
`universe_id`, `admission_id`, `admission_state`, `request_id`,
`branch_task_id`, `request_status`, `trigger_source`,
`accepted_priority_weight`, `priority_weight_cap`,
`priority_policy_version`, `idempotent_replay`, and
`directed_daemon_id`. `admission_state` SHALL be `committed`,
`request_status` SHALL be `pending`, both IDs SHALL be non-empty, the cap SHALL
be `100`, and the policy version SHALL be `operator-priority-v1`.

The result SHALL omit `queue_position`, `ahead_of_yours`,
`what_happens_next`, raw grants, evidence handles, and any assertion that work
is next. A failed admission SHALL NOT use pending/scheduled/accepted language.
The existing faithful structured/text result-envelope requirement remains
unchanged.

#### Scenario: committed result is honest and complete
- **WHEN** request admission commits
- **THEN** the result contains exactly the authoritative fields and values above
- **AND** it contains no FIFO position, dispatcher rank, or scheduling promise

#### Scenario: changed-body reuse conflicts without mutation
- **WHEN** one actor/universe scope reuses an idempotency key with a different canonical body
- **THEN** the result contains `error="idempotency_key_body_conflict"`
- **AND** no Request, task, admission, mutation-ledger row, or executable effect is created

#### Scenario: ACL-lost replay reveals nothing
- **WHEN** current ordinary authorization fails before replay lookup
- **THEN** the result contains `error="universe_access_denied"`
- **AND** it omits stored IDs, digest, receipt, replay status, and key-existence evidence

#### Scenario: operator writer unavailability never silently demotes
- **WHEN** the composed verdict would accept priority elevation but the operator writer gate is off
- **THEN** the result contains `error="operator_priority_unavailable"` with zero persistence
- **AND** the request is not silently rewritten as user or historical host work
