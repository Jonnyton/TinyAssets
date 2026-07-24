## MODIFIED Requirements

### Requirement: Queue garbage collection archives only old terminal tasks

The branch-task garbage collector SHALL, under the queue file lock, move only
terminal tasks whose string-valued `queued_at` parses before the configured
cutoff into the archive. It MUST retain pending, running, recent terminal,
missing/empty-date, and terminal rows whose string date raises `ValueError` in
`datetime.fromisoformat`; a truthy non-string date currently raises `TypeError`
and aborts collection. It SHALL replace the archive atomically before rewriting
the live queue. Because archived origin rows remain authoritative input to
lifetime lineage admission, an unreadable, invalid-JSON, or non-list archive
MUST fail collection without replacing the archive or rewriting the live
queue. A repeated collection after an archive-first/live-second interruption
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
