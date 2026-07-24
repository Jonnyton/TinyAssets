## MODIFIED Requirements

### Requirement: Queue garbage collection archives only old terminal tasks

The branch-task garbage collector SHALL, under the queue file lock, move only
terminal tasks whose string-valued `queued_at` parses before the configured
cutoff into the archive. It MUST retain pending, running, recent terminal,
missing/empty-date, and terminal rows whose string date raises `ValueError` in
`datetime.fromisoformat`; a truthy non-string date currently raises `TypeError`
and aborts collection. It SHALL replace the archive atomically before rewriting
the live queue. Because archived origin rows remain authoritative input to
lifetime lineage admission, an existing blank, whitespace-only, unreadable,
invalid-JSON, or non-list archive MUST fail collection without replacing the
archive or rewriting the live queue. A missing archive SHALL mean empty
history. A repeated collection after an archive-first/live-second interruption
SHALL not duplicate an identified task already present in the archive.

#### Scenario: Active and recent tasks survive collection

- **WHEN** garbage collection sees old pending or running tasks and a recent terminal task
- **THEN** all of those rows remain in the live queue

#### Scenario: Old terminal work moves to the archive

- **WHEN** a terminal task has a parseable `queued_at` before the cutoff
- **THEN** it is appended to the archive and removed from the live queue

#### Scenario: Interrupted collection converges without archive duplication

- **WHEN** an identified terminal task is already archived but remains in the live queue after an interrupted collection
- **THEN** a later collection removes the live copy without appending a second archived copy

#### Scenario: Corrupt prior archive blocks collection instead of erasing lineage truth

- **WHEN** old terminal rows are eligible for collection while the existing archive cannot be read as a JSON list
- **THEN** collection raises without replacing the archive or removing rows from the live queue

#### Scenario: Blank prior archive is corrupt history

- **WHEN** old terminal rows are eligible for collection while the existing archive is empty or whitespace-only
- **THEN** collection raises without treating that file as a missing empty archive

## ADDED Requirements

### Requirement: Claimed-task execution binds enqueue authority to the physical queue universe
The epoch-1 dispatcher SHALL derive the trusted enqueue universe from the canonical physical universe directory whose queue supplied the claimed row. Before branch execution it MUST compare that value with the row's persisted `universe_id` and fail without starting a run when they differ. After a match, only the physical queue universe SHALL be passed into graph enqueue context; mutable task metadata MUST NOT redirect descendant writes.

#### Scenario: Mismatched persisted universe fails before execution
- **WHEN** a task stored in universe A's queue declares universe B in its persisted row
- **THEN** direct branch execution is refused before a run starts and no descendant is appended to either universe

#### Scenario: Matching row uses the physical universe
- **WHEN** a claimed row's persisted universe matches the physical queue directory
- **THEN** graph execution receives that physical universe as its trusted enqueue context
