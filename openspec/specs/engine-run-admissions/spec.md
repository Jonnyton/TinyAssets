# Engine Run Admissions

> As-built (2026-08-30, changes `run-rate-cap-counts-writes` #2704 and `engine-writes-count-toward-total` #2712): the engine's per-universe run-admission ledger — what an engine-triggered run costs and how it is settled. Design rationale in the archived change's `design.md`. Live proof 2026-08-30: heartbeat periods settle as `read` rows; a one-line README job with retries (runs `c1cd14f98b6e4af8` → `3f86d7b9fde04bff`, `d773d4d006ae45a8`, `b77089dfa3c14d9e`, `631bd6d61473416f`) completed without meeting the cap.

## Purpose

Bound how often an engine-triggered run can fire an already-approved effect (Codex gate #5) without charging the write budget for runs that provably wrote nothing.

## Requirements

### Requirement: Engine run admissions are charged as writes and settled by what fired

The engine SHALL admit every engine-triggered run and every scheduled
automation run through one per-universe rolling ledger
(`<data_dir>/.engine_run_admissions.db`), charging each as kind `write`
atomically at admission time, with schema inspection and migration inside
the same immediate transaction. The engine SHALL admit every durable engine
write (`write_graph`, remix, brain write) through the same ledger as kind
`engine`. The engine SHALL refuse a run admission when the universe's
`write` admissions in the window have reached the write cap (20 per 3600 s)
OR its admissions of any kind have reached the total cap (60 per 3600 s);
it SHALL refuse an `engine` admission when the universe's `engine`
admissions in the window have reached the engine cap (40 per 3600 s, two
thirds of the total, so runs always keep at least 20) OR the total cap; and
SHALL say which cap refused. An `engine` row SHALL never be bound to a run
or reclassified. A refusal caused by an unusable or untrusted ledger SHALL
say so and SHALL NOT be reported as a quota. Rows outside the window SHALL
be pruned on the next admission. Admission SHALL return a
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
other verb, or an unnamed verb SHALL settle it as `write`, and a `write`
settlement SHALL be final: a later `read` settlement for the same run SHALL
change nothing. A settlement that arrives before the bind SHALL be kept and
applied at bind time. Settlement rows SHALL expire two hours after they are
written, pruned on every settle and every admission. Every engine surface's
refusal SHALL name the cap that refused. The ledger
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
- **THEN** settlement changes no admission; when a ledger already exists it
  may leave a settlement row that expires within two hours; no ledger is
  created for it

#### Scenario: A write that later fails stays a write

- **WHEN** an admitted run's `PUT` effect fired and its status is then
  rewritten to `failed` (provider-authority release failed)
- **THEN** the admission stays `write`

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

#### Scenario: Branch authoring does not spend the effect budget

- **WHEN** a universe's engine has made 30 `write_graph` calls in the rolling
  hour and then runs a job that writes externally
- **THEN** the job's writes are admitted against an untouched 20-write budget

#### Scenario: A burst of engine writes cannot starve runs

- **WHEN** a universe's engine has made 40 `write_graph` calls in the rolling
  hour (failed validations included - they charged their admission)
- **THEN** the 41st is refused by the engine cap while runs are still admitted
  until 60 admissions of any kind exist
