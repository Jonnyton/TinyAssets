## ADDED Requirements

### Requirement: Typed Filing Has No Privileged Automation Side Effect

The `file_bug` typed-filing action SHALL atomically create the requested wiki
filing and return filing metadata without creating a task-trigger receipt,
resolving an investigation handler, enqueueing a BranchTask, starting a run, or
appending an investigation section. It SHALL NOT attach automatic fast-lane,
carrier-review, navigator-triage, daemon-pickup, or other dispatcher-facing
route claims. Its response SHALL NOT expose the retired `investigation` or
`trigger` blocks or describe the filing as sent to a hidden pipeline. It SHALL
NOT derive or store an effort class, attention class, dispatch lane,
pickup-signal weight, triage policy, checker family, or product authority
boundary. Ordinary submitted filing fields and per-kind duplicate detection
remain without implying task, route, receipt, queue, review, or execution.

#### Scenario: Filing succeeds without task state

- **WHEN** an authorized caller files a valid typed page
- **THEN** the page is created and the response reports the filing result
- **AND** no trigger receipt, branch task, run, or investigation section is
  created

#### Scenario: Filing metadata cannot imply an automatic route

- **WHEN** a valid filing contains fields or text that the retired effort classifier treated as merge-instant or ghost-risk
- **THEN** the result makes no automatic fast-lane, carrier-review, navigator-triage, daemon-pickup, or queue claim
- **AND** the page/response contains no derived effort/attention/dispatch/checker product policy

#### Scenario: Obsolete environment configuration has no effect

- **WHEN** a process environment still contains
  `TINYASSETS_BUG_INVESTIGATION_GOAL_ID` or
  `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID`
- **THEN** `file_bug` does not read either value or initiate automation
- **AND** current deployment/configuration surfaces do not advertise those keys

## REMOVED Requirements

### Requirement: Trigger receipts use one mutable per-attempt row attempted before enqueue

**Reason**: The receipt is created only to support the retired hidden
filed-page auto-trigger. Retaining its special store and response surface would
preserve product-specific automation scaffolding.

**Migration**: User-authored workflows use the platform's generic request,
execution, and receipt/evidence mechanisms appropriate to their primitives.
Typed wiki filing no longer creates a trigger attempt.
