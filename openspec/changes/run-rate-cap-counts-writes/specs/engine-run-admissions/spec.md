## ADDED Requirements

### Requirement: Engine run admissions are charged as writes and settled by what fired

The engine SHALL admit every engine-triggered run and every engine write
(`write_graph`, remix, brain write) through one per-universe rolling ledger
(`<data_dir>/.engine_run_admissions.db`), charging each admission as kind
`write` atomically at admission time. The engine SHALL refuse an admission
when the universe's `write` admissions in the window have reached the write
cap (20 per 3600 s) OR its admissions of any kind have reached the total cap
(120 per 3600 s). `run_graph` SHALL bind the admission to the run it starts.
When the run's effects have fired, the dispatcher SHALL reclassify the run's
admission as `read` if and only if every effect that ran was a `GET`/`HEAD`
`authenticated_external_call` (a refused-before-the-wire packet counts by the
verb it declared; no effect at all counts as read); any other sink, verb, or
an unnamed verb SHALL leave it `write`. The ledger SHALL be refused (fail
closed) when it is a symlink or resolves outside its data dir. Older ledgers
SHALL be migrated additively, their rows counting as writes.

#### Scenario: A GitHub job's reads do not spend the write budget

- **WHEN** a universe's engine runs a branch whose only effects are `GET`
  calls (read the ref, read the file) and the run completes
- **THEN** its admission is reclassified as `read` and the universe's write
  budget is unchanged by that run

#### Scenario: A write is charged before it runs and stays charged

- **WHEN** the engine admits a run and the run fires a `PUT` or `POST`
  authenticated call, or any other sink
- **THEN** the admission was counted at admission time and remains kind
  `write` after settlement

#### Scenario: A loop of read-only runs is still bounded

- **WHEN** a universe has 120 admissions of any kind in the rolling hour
- **THEN** the next engine run is refused even if no write budget was spent

#### Scenario: A branch cannot be pre-classified as read-only

- **WHEN** a run is admitted
- **THEN** it is charged as a write regardless of the branch's shape, because
  the verb an effect uses is decided by the packet the run produces

#### Scenario: A run that never ran through the engine has no admission

- **WHEN** a browser or scheduled run's effects fire
- **THEN** settlement finds no admission row and changes nothing; the ledger
  is not created for it
