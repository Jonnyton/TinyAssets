## MODIFIED Requirements

### Requirement: Engine run admissions are charged as writes and settled by what fired

Because effects fire at node time, a run MAY fire a write and then fail or be
cancelled. On every terminal status the runtime SHALL settle the run's
admission from the effect chain's record of what fired — a fired write
settles as `write` (final) even when the run ends `failed`, `cancelled` or
`interrupted`; a run whose chain fired nothing settles as `read`. Settlement
SHALL have exactly one owner per run (the chain, via the terminal status
write); the "failed run fired nothing" shortcut SHALL apply only to runs that
had no chain. A `write` settlement SHALL be final in both directions: it
SHALL promote an admission a `read` settlement reclassified earlier, and a
later `read` SHALL change nothing. The clause "a run that failed or was
cancelled … fires nothing" is withdrawn. All other clauses of this
requirement are unchanged.

#### Scenario: A read that arrived first does not hide a write
- **WHEN** a terminal status settles `read` while an adapter is still running and that adapter then delivers a PUT
- **THEN** the later `write` settlement promotes the admission row to `write`

#### Scenario: A write that fired before a failure stays a write
- **WHEN** `create_branch` (POST) delivered and then `write_readme` was refused, failing the run
- **THEN** the run's admission settles as `write`, and no later `read` settlement changes it

#### Scenario: A run that failed before any effect settles as a read
- **WHEN** a run fails at its first node before any effect fires
- **THEN** its admission settles as `read`
