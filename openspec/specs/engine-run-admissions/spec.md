# Engine Run Admissions

> As-built (2026-09-30, change `two-dimension-usage-limits`): the run-settlement
> ledger. It records whether each run only read or also wrote, for the effect
> boundary. It counts nothing against the account and refuses nothing: account
> usage is two numbers -- cloud storage and concurrent seats (`universe-seats`).
> History: the rolling-window run caps it used to enforce (`run-rate-cap-counts-writes`
> #2704, `engine-writes-count-toward-total` #2712) are deleted.

## Purpose

Settle each run as a read or a write, so the effect boundary knows what a run did.
## Requirements
### Requirement: Run admission retains settlement identity without rate limits

Every admitted run SHALL receive a settlement ticket without any hourly, daily,
write-count or total-count refusal. Tickets SHALL bind only their own run.
A write settlement SHALL remain final against later read settlements; a settlement
that arrives before attachment SHALL apply when the ticket is attached. A
tampered, missing or locked settlement store SHALL record nothing and SHALL NOT
refuse the run. Engine edits (`write_graph`, `remix`, `write_brain`, automation
and webhook creation, model setup) SHALL NOT be recorded here at all. Rows SHALL
be pruned once they can no longer be settled. Concurrent account seats SHALL be
acquired by executors, never by this bookkeeping.

#### Scenario: Prior runs do not refuse new work
- **WHEN** an account has already completed many runs
- **THEN** another run is admitted and waits for concurrency at its worker

#### Scenario: An unusable ledger refuses nothing
- **WHEN** the settlement store is a symlink, unreadable or locked
- **THEN** the run starts anyway, with no settlement recorded

#### Scenario: Settlement arrives before attachment
- **WHEN** the worker finishes before its ticket is attached
- **THEN** attaching the ticket applies that run's existing settlement

### Requirement: Workspace jobs are admitted and settled through their own ledger kind with the maximum charge reserved before the wire

The engine SHALL reserve the runtime-controlled maximum transport byte charge
before workspace network activity, keeping existing
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
5,000 dispatches and 256 MiB per root run. The count unit SHALL be one node with effects, not each sink
inside that node; workspace nodes SHALL consume this generic count as well as
their workspace-specific accounting. Nodes without effects SHALL not consume it.

Delivered results SHALL contribute reported request_bytes and response_bytes;
an absent integer size SHALL use the corresponding 8 MiB request / 5 MiB response
fallback. Workspace transfer bytes SHALL remain in workspace accounting because
ordinary workspace results do not report delivered=True. The authenticated-call
adapter SHALL report integer request_bytes and response_bytes on delivered results.

A crossed pre-dispatch threshold SHALL fail the node as effect_budget_exhausted,
naming current execution usage and bound; later nodes SHALL not proceed through
that failed chain. These are checks of recorded usage, not atomic pre-wire byte
reservations: an already-admitted dispatch can cross the byte threshold before
a later check, without any account rate meter.

#### Scenario: The per-run dispatch threshold refuses the next node
- **WHEN** the chain has recorded 5,000 dispatched effect nodes
- **THEN** the next effect node is refused before its adapters run with effect_budget_exhausted and the dispatch count and limit

#### Scenario: Workspace nodes share the generic dispatch count
- **WHEN** a workspace effect node completes without a delivered=True result
- **THEN** it consumes one generic dispatch and no generic delivered-result byte charge, while its workspace accounting remains separate

#### Scenario: An admitted response crosses a byte threshold
- **WHEN** recorded bytes are below the threshold before a bounded transport and its result crosses that threshold
- **THEN** the result is recorded and the next dispatch is refused; the meter does not retroactively claim a pre-wire reservation

