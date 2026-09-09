# Engine Run Admissions

> As-built (2026-08-30, changes `run-rate-cap-counts-writes` #2704, `engine-writes-count-toward-total` #2712, `sandboxed-code-node` #2719/#2723): the engine's per-universe run-admission ledger — what an engine-triggered run costs and how it is settled. Design rationale in the archived change's `design.md`. Live proof 2026-08-30: heartbeat periods settle as `read` rows; a one-line README job with retries (runs `c1cd14f98b6e4af8` → `3f86d7b9fde04bff`, `d773d4d006ae45a8`, `b77089dfa3c14d9e`, `631bd6d61473416f`) completed without meeting the cap.

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
`write` admissions in the window have reached the write cap (300 per 3600 s)
OR its admissions of any kind have reached the total cap (900 per 3600 s);
it SHALL refuse an `engine` admission at the total cap without a separate
engine-mutation ceiling or a reserved share for the same universe's runs; and
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

- **WHEN** a universe has 900 admissions of any kind in the rolling hour
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
- **THEN** the job's writes are admitted against an untouched 300-write budget

#### Scenario: Engine mutations can use the owner's total allowance

- **WHEN** a universe has 600 engine edits in its rolling hour and no other admissions
- **THEN** edit 601 is admitted, and engine edits can fill the existing total of 900
- **AND** the next admission of either kind refuses at the total cap, while another universe remains independent

#### Scenario: Mixed kinds compete atomically for the total

- **WHEN** engine edits and run submissions race for the final total admission with write capacity remaining
- **THEN** exactly one receives a recorded ticket and all others refuse at the total cap

#### Scenario: Edit usage does not permanently pause an automation

- **WHEN** engine edits exhaust the total allowance and a scheduled run becomes due
- **THEN** that period records `run_rate_limited` without launching or pausing the automation
- **AND** a later due period can be admitted after the old charges expire

#### Scenario: A read that arrived first does not hide a write
- **WHEN** a terminal status settles `read` while an adapter is still running and that adapter then delivers a PUT
- **THEN** the later `write` settlement promotes the admission row to `write`

#### Scenario: A write that fired before a failure stays a write
- **WHEN** `create_branch` (POST) delivered and then `write_readme` was refused, failing the run
- **THEN** the run's admission settles as `write`, and no later `read` settlement changes it

#### Scenario: A run that failed before any effect settles as a read
- **WHEN** a run fails at its first node before any effect fires
- **THEN** its admission settles as `read`

The settlement rule that every sink other than a GET/HEAD
`authenticated_external_call` settles a run as a write SHALL have exactly one
exception: a `workspace` `checkout` (which is charged as a `workspace` job)
SHALL settle the run's external-write admission as a read. A `workspace` `push`
settles as a write; `discard` is a workspace job and SHALL NOT be classified as
a read. All other clauses of this requirement are unchanged.

#### Scenario: a checkout does not spend the external-write budget
- **WHEN** a run checks out a repository, reads and runs it, and writes nothing externally
- **THEN** its admission settles as `read` and one `workspace` job is charged

### Requirement: Workspace jobs are admitted and settled through their own ledger kind with the maximum charge reserved before the wire

The engine SHALL reserve the runtime-controlled maximum transport byte charge
before workspace network activity, keeping existing per-universe rolling-byte,
lease, pool, retained-storage and lock checks. It SHALL reconcile downward only
from trustworthy measurement, retaining the maximum for an unknown or interrupted
transfer. Workspace job-count rows SHALL remain observations and SHALL NOT
independently refuse work based on jobs per hour. No caller-supplied packet
ceiling SHALL decide quota consumption.

Push and discard SHALL preserve their deterministic operation identity and
idempotent reservations. A zero-byte discard SHALL NOT be refused merely because
earlier workspace starts exhausted the retired jobs count. Generic execution and
effect admission remain separate existing controls. Workspace transfer bytes
SHALL remain separate from generic delivered-result byte accounting; workspace
effect nodes still consume the generic effect-node dispatch count.

#### Scenario: More than ten light operations
- **WHEN** eleven authorized workspace operations have sufficient actual resource capacity
- **THEN** the eleventh is admitted without an independent jobs-per-hour refusal and the observational count records eleven

#### Scenario: A retried push does not duplicate its reservation
- **WHEN** the same identified push reservation is requested again
- **THEN** its existing reservation is returned without adding another workspace job/byte record

#### Scenario: The hourly workspace bytes are exhausted
- **WHEN** a new checkout's runtime-controlled reservation would exceed the existing transfer window
- **THEN** it is refused before transport with workspace_quota_exceeded and the actual byte constraint

#### Scenario: Two checkouts compete for remaining bytes
- **WHEN** two checkouts concurrently request more combined bytes than remain
- **THEN** only a fitting reservation commits and the other is refused atomically

#### Scenario: Cleanup after ten starts
- **WHEN** more than ten jobs are recorded and an authorized zero-byte discard is requested
- **THEN** the observational jobs total does not block cleanup

#### Scenario: Unknown transfer remains conservative
- **WHEN** checkout fails and no trustworthy transfer measurement exists
- **THEN** its existing maximum byte reservation remains; a deleted or small local tree is not proof of zero transferred bytes

#### Scenario: a large checkout is not an HTTP budget event
- **WHEN** a run checks out a 3 GiB repository
- **THEN** the run's generic delivered-result byte budget is unchanged and the workspace ledger records the bytes, while the node still consumes one generic effect dispatch

### Requirement: Unresolved required inputs are refused before run admission
The engine SHALL preflight the exact authorized Branch target before creating or
admitting a run, and SHALL refuse a submission when any statically mandatory node
input is not supplied, defaulted, or guaranteed by an earlier completed superstep.

#### Scenario: Invalid initial state creates no activity
- **WHEN** a caller submits a valid authorized Branch target with one or more unresolved required inputs
- **THEN** the engine returns `failure_class=missing_required_inputs` without a run id and creates no run row, queue item, admission or billing record, provider call, or effect

#### Scenario: Supplied and defaulted inputs admit normally
- **WHEN** every required initial input is present in `inputs_json` or has a declared schema default
- **THEN** the existing run admission and execution path proceeds unchanged

#### Scenario: Declared optional input remains optional
- **WHEN** a node allowlists an input but does not mandatorily dereference it, or code reads it through an optional default
- **THEN** absence of that key does not block run admission

#### Scenario: Authorization precedes contract disclosure
- **WHEN** a caller is not authorized to run or read a private Branch target
- **THEN** the existing authority-safe not-found or refusal result is returned without disclosing missing keys or schema guidance

### Requirement: Outbound volume is bounded by usage budgets, not by graph shape

The engine SHALL check the current effect-chain dispatch count and delivered-result
byte total before entering another node's effect dispatch, with current defaults
5,000 dispatches and 256 MiB per root run. It SHALL check the universe's recorded
rolling-hour totals against 5,000 dispatches and 2 GiB before dispatch when that
ledger is readable. The count unit SHALL be one node with effects, not each sink
inside that node; workspace nodes SHALL consume this generic count as well as
their workspace-specific accounting. Nodes without effects SHALL not consume it.

Delivered results SHALL contribute reported request_bytes and response_bytes;
an absent integer size SHALL use the corresponding 8 MiB request / 5 MiB response
fallback. Workspace transfer bytes SHALL remain in workspace accounting because
ordinary workspace results do not report delivered=True. The authenticated-call
adapter SHALL report integer request_bytes and response_bytes on delivered results.

A crossed pre-dispatch threshold SHALL fail the node as effect_budget_exhausted,
naming current usage, budget and window; later nodes SHALL not proceed through
that failed chain. These are checks of recorded usage, not atomic pre-wire byte
reservations: an already-admitted dispatch can cross the byte threshold before
a later check, and concurrent runs can consult the same hourly observation.
The existing hourly meter SHALL record after dispatch and tolerate read/write
ledger failures while preserving per-run guards. It SHALL NOT be described as a
transactionally exact global byte cap, a wired commercial tier, or an exact
per-network-request count. These limitations are inputs to the replacement
resource-policy design, not claims of stronger enforcement than shipped.

#### Scenario: The per-run dispatch threshold refuses the next node
- **WHEN** the chain has recorded 5,000 dispatched effect nodes
- **THEN** the next effect node is refused before its adapters run with effect_budget_exhausted and the dispatch count and limit

#### Scenario: Workspace nodes share the generic dispatch count
- **WHEN** a workspace effect node completes without a delivered=True result
- **THEN** it consumes one generic dispatch and no generic delivered-result byte charge, while its workspace accounting remains separate

#### Scenario: The hourly byte observation reaches its threshold
- **WHEN** a readable universe ledger already records at least 2 GiB in its rolling hour
- **THEN** the next effect dispatch is refused with the hourly usage/window explanation

#### Scenario: An admitted response crosses a byte threshold
- **WHEN** recorded bytes are below the threshold before a bounded transport and its result crosses that threshold
- **THEN** the result is recorded and the next dispatch is refused; the meter does not retroactively claim a pre-wire reservation

#### Scenario: An unavailable hourly meter does not invent exact enforcement
- **WHEN** the hourly ledger cannot be read
- **THEN** existing per-run guards still apply but the hourly observation is not asserted to be a transactionally enforced cap
