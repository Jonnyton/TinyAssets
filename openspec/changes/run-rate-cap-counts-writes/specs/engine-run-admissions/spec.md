## ADDED Requirements

### Requirement: Engine run admissions are charged as writes and settled by what fired

The engine SHALL admit every engine-triggered run, every scheduled
automation run and every engine write (`write_graph`, remix, brain write)
through one per-universe rolling ledger
(`<data_dir>/.engine_run_admissions.db`), charging each admission as kind
`write` atomically at admission time, with schema inspection and migration
inside the same immediate transaction. The engine SHALL refuse an admission
when the universe's `write` admissions in the window have reached the write
cap (20 per 3600 s) OR its admissions of any kind have reached the total cap
(60 per 3600 s), and SHALL say which cap refused. Admission SHALL return a
ticket (the ledger row id), or the sentinel `ADMITTED_UNRECORDED` when a
tolerated ledger error admitted without a row (fail-open callers only);
`run_graph` and the automation runner SHALL bind a real ticket to the run
they start the moment its id exists. A ledger whose parent directory does
not exist yet SHALL be created there, never treated as "no cap"; its path
SHALL come from the canonical data-dir resolver, never the CWD.
When the run has finished, its admission SHALL be settled: reclassified as
`read` if and only if every effect that ran was a `GET`/`HEAD`
`authenticated_external_call` (a refused-before-the-wire packet counts by the
verb it declared), or no effect ran at all — including a run that failed or
was cancelled, which fires nothing; any other sink (known or unknown), any
other verb, or an unnamed verb SHALL leave it `write`. A settlement that
arrives before the bind SHALL be kept and applied at bind time. The ledger
SHALL be refused (fail closed) when it is a symlink or resolves outside its
data dir. Older ledgers SHALL be migrated additively, their rows counting as
writes.

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

- **WHEN** a universe has 60 admissions of any kind in the rolling hour
- **THEN** the next engine run is refused even if no write budget was spent

#### Scenario: Two first touches of a legacy ledger cannot both pass

- **WHEN** two admissions race on a ledger that still has the old schema and
  one write of budget left
- **THEN** exactly one is admitted and exactly one row is recorded

#### Scenario: A scheduled automation settles like a foreground run

- **WHEN** a scheduled automation's run fires only `GET` effects
- **THEN** its admission, bound to that run when it started, is reclassified
  as `read`

#### Scenario: A branch cannot be pre-classified as read-only

- **WHEN** a run is admitted
- **THEN** it is charged as a write regardless of the branch's shape, because
  the verb an effect uses is decided by the packet the run produces

#### Scenario: A run that was never admitted has no admission

- **WHEN** a browser-triggered run's effects fire
- **THEN** settlement finds no admission row and changes nothing; the ledger
  is not created for it

#### Scenario: A run that failed settles as a read

- **WHEN** an admitted run fails, is cancelled or times out before its
  effects could fire
- **THEN** its admission is reclassified as `read` when the terminal status
  is recorded

#### Scenario: A fast run that settles before its bind is not lost

- **WHEN** a run's settlement arrives before `run_graph` has bound the
  ticket to its id
- **THEN** the settlement is kept and applied when the bind happens

#### Scenario: An unknown sink is a write

- **WHEN** an admitted run's node names a sink the platform does not know
- **THEN** the admission stays `write`

#### Scenario: A verb that disagrees with the request method is a write

- **WHEN** a packet declares `verb: GET` and `request.method: PUT`
- **THEN** the adapter refuses it before the wire and the admission stays
  `write` (the declared verb says nothing about intent)
