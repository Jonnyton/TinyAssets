## MODIFIED Requirements

### Requirement: Dispatcher selection is a stateless deterministic function invoked at cycle boundaries
The branch-task dispatcher (`tinyassets.dispatcher`) SHALL select the next task
with a pure, stateless function that reads eligible candidates from persisted
queue epochs 1 and 2, keeps only `pending` tasks whose trigger-source tier and
hard worker predicates are enabled, scores each by a deterministic
`tier_weight + recency_decay + user_boost` formula, and returns the single
highest-scoring task (ties broken by oldest `queued_at`) or `None` when nothing
is eligible. It SHALL be invoked exactly at graph-cycle boundaries—once at
daemon startup and once between cycle-wrapper returns—and SHALL NOT run its own
timer or continuous polling loop. The selector SHALL only read the queues and
SHALL never claim, quarantine, or mutate them. Deferred market and goal-
affinity terms SHALL contribute zero until their coefficients are configured,
without reshaping the score. Soul affinity SHALL remain the canonical bounded,
advisory, fail-open score term; only an explicit directed-daemon mismatch is a
hard soul/routing rejection. `operator_request` SHALL be valid only in epoch 2,
enabled, reported `live`, and use default base weight `100`, equal to
historical v1 `host_request`; defaults for `owner_queued=80`,
`user_request=60`, `paid_bid=50`, `goal_pool=40`, and `opportunistic=10`
remain unchanged.

#### Scenario: highest-scoring eligible task wins across epochs
- **WHEN** a v2 worker selects over pending and non-pending v1/v2 tasks
- **THEN** it returns the eligible tier-enabled task with the highest score
- **AND** ties are broken by oldest `queued_at`

#### Scenario: no eligible task yields None
- **WHEN** both epochs are empty or every pending task has a disabled tier or failed hard predicate
- **THEN** `select_next_task` returns `None`

#### Scenario: selection never mutates either epoch
- **WHEN** selection returns a task
- **THEN** that task remains pending in its source epoch
- **AND** no candidate, quarantine, claim, or lease row is changed

#### Scenario: soul affinity remains advisory and fail-open
- **WHEN** soul evidence is unavailable or produces a lower bounded affinity score without an explicit directed-daemon mismatch
- **THEN** the task remains eligible with the canonical advisory score behavior
- **AND** affinity alone does not reject capacity

#### Scenario: default tier bands remain deterministic
- **WHEN** eligible zero-modifier tasks share the same `queued_at`
- **THEN** operator and historical host tasks share base score `100`, followed by owner `80`, user `60`, paid `50`, goal `40`, and opportunistic `10`
- **AND** stable oldest-first ordering resolves equal scores

## ADDED Requirements

### Requirement: One transaction commits the Request, admission, and protocol-v2 BranchTask
Every protocol-v2 request admission SHALL atomically create the canonical
Request in the existing Request store, one one-to-one authorization/idempotency
admission, one epoch-2 BranchTask, and one committed admission event in the
deployment's transactional control-plane store. The admission SHALL bind
opaque random admission/request/task IDs, tenant, authenticated actor,
universe, keyed idempotency-key hash, RFC 8785 body digest/version, sanitized
authority receipt, trigger source, accepted weight, policy/grant generation,
timestamps, and public result fields. Unique constraints SHALL cover each
Request/task link and `(tenant_id, actor_id, universe_id,
idempotency_key_hash)`. A commit SHALL make the complete aggregate runnable;
a crash or error before commit SHALL persist none of it.

The local bridge SHALL use the one always-on shared `.tinyassets.db`; host trays
SHALL NOT create competing admission truth. The hosted target SHALL preserve
the same logical aggregate and constraints in Postgres. In that backend one
`request_inbox` row SHALL implement both the Request payload and BranchTask
lifecycle, carry stable unique `request_id` and `branch_task_id`, and transition
through the existing narrow row-lock claim RPC; sibling admission receipt/event
rows SHALL reference both IDs in the same transaction. It SHALL NOT create a
second hosted dispatcher or a second competing task row. Operational request
text SHALL remain owner-scoped and SHALL NOT be exported to OKF, Git, commons,
or public mirrors.

#### Scenario: successful admission is one atomic aggregate
- **WHEN** an authorized request commits
- **THEN** exactly one canonical Request, one admission, one epoch-2 BranchTask, and one committed event become durable together
- **AND** the response contains their non-empty persisted IDs

#### Scenario: precommit crash leaves no half-pair
- **WHEN** authority read, idempotency lookup, ID allocation, Request insert, admission insert, task insert, or commit fails
- **THEN** the transaction rolls back without a runnable Request or task
- **AND** no response says pending, scheduled, accepted, or next

#### Scenario: response loss after commit replays safely
- **WHEN** result serialization or delivery fails after commit
- **THEN** the task remains runnable and same-key/same-body replay reconstructs the original result
- **AND** no second Request, task, mutation-ledger entry, or executable effect is created

#### Scenario: hosted inbox co-locates the two logical roles
- **WHEN** the aggregate is committed in Postgres
- **THEN** one `request_inbox` row exposes stable Request and BranchTask IDs and owns execution lifecycle
- **AND** the narrow claim RPC transitions that row without a second dispatcher or task table

### Requirement: Request admission is scope-bound, body-bound, and durably idempotent
The public `idempotency_key` SHALL be stored only as a keyed hash and uniquely
scoped by server-derived tenant, actor, and universe. Reusing the same raw key
in another scope SHALL be independent and non-enumerable. The digest SHALL be
SHA-256 over RFC 8785 canonical JSON containing schema version, universe ID,
exact UTF-8 text, request type, branch ID, pickup incentive, directed daemon
ID/instruction, and requested priority weight. Same-scope/same-body replay
SHALL return the original IDs and `idempotent_replay=true`; changed-body reuse
SHALL return `idempotency_key_body_conflict` without mutation.

Live/nonterminal rows SHALL remain indefinitely. Full private Request and result
detail SHALL remain at least 30 days after terminal state; then it MAY compact
while retaining a minimal scoped key hash/body digest/ID/terminal-state
tombstone until universe deletion.

#### Scenario: a different actor or universe may use the same raw key
- **WHEN** another actor, tenant, or universe submits the same raw key
- **THEN** it occupies an independent namespace
- **AND** neither response reveals whether the other namespace exists

#### Scenario: changed-body reuse conflicts
- **WHEN** one namespace reuses its key with a different canonical body
- **THEN** it receives `idempotency_key_body_conflict`
- **AND** the original aggregate remains unchanged

#### Scenario: compaction preserves deduplication
- **WHEN** full terminal detail ages beyond 30 days and compacts
- **THEN** the minimal tombstone remains until universe deletion
- **AND** replay cannot create a duplicate effect

### Requirement: Queue epoch 2 excludes legacy claim code and preserves single-winner execution
Epoch-2 tasks SHALL live in a transactional namespace that v1 binaries cannot
open or mutate. V2 readers SHALL combine eligible candidates from v1 and v2;
v1 readers SHALL continue to access v1 only. A v2 worker SHALL advertise
server-derived `queue_protocol_version=2`, capability `operator_request_v1`,
build SHA, config hash, boot ID, worker ID, runtime instance ID, and universe in
durable runtime metadata plus a per-worker heartbeat with 90-second validity.
Selection SHALL require matching live evidence, and the conditional
pending-to-running transaction SHALL re-check it atomically with the claim.

Claim, lease, heartbeat, cancellation, recovery, and terminal transitions SHALL
retain BranchTask semantics in epoch 2. Operator priority SHALL NOT confer
provider, executor, payment, credential, quota, or result authority.
An epoch-2 BranchTask claim SHALL authorize only internal scheduling
reservation. Before any external or distributed execution begins, the selected
task SHALL hand off through the `distributed-execution` B2 authority boundary,
which authenticates the owner daemon and requires the signed
owner/daemon/job/capsule/lease/fence grant and fenced signed completion. An
admission row, operator receipt, worker heartbeat, or mutable queue claim SHALL
only narrow/reject that authority and SHALL NEVER substitute for it.

#### Scenario: a v1 worker cannot claim epoch-2 work
- **WHEN** a v1 worker sees ordinary v1 work and is also given an epoch-2 operator task ID
- **THEN** it may process compatible v1 work but cannot open or mutate epoch 2
- **AND** the operator task remains pending

#### Scenario: a false or stale descriptor fails at claim
- **WHEN** selection evidence is missing, older than 90 seconds, or mismatches worker/runtime/boot/build/config identity
- **THEN** the epoch-2 claim transaction leaves the task unchanged
- **AND** status reports `awaiting_compatible_capacity`

#### Scenario: two compatible workers produce one claim
- **WHEN** two eligible v2 workers race for one pending task
- **THEN** exactly one conditional transition reaches running
- **AND** the other observes already claimed without duplicate execution

#### Scenario: internal reservation cannot authorize distributed execution
- **WHEN** a worker wins the epoch-2 scheduling claim but lacks a valid B2 signed execution grant
- **THEN** no external execution lease or result authority is created
- **AND** the task remains subject to the distributed-execution refusal and fence contract

### Requirement: Invalid epoch-2 rows quarantine independently of pure selection
Schema constraints and the trusted insert path SHALL prevent normal
construction of invalid operator work. A separate transactional maintenance
step SHALL classify imported, corrupt, forged, or unsupported rows and move
them idempotently to an inert quarantine keyed by canonical-row digest. The
source row SHALL be disabled only in the same transaction that records its
quarantine receipt. Pure selection SHALL see only valid candidates and SHALL
never perform quarantine mutation.

Status SHALL distinguish valid work with no compatible worker as
`awaiting_compatible_capacity`, invalid work as
`invalid_operator_admission`/`quarantined`, and disabled valid work as
`policy_parked`. It SHALL expose counts, oldest age, reason counts, digests,
and IDs without private request text or authorization evidence.

#### Scenario: one invalid row does not poison valid work
- **WHEN** epoch 2 contains one forged row and one valid eligible row
- **THEN** maintenance quarantines the forged row once by digest
- **AND** selection and claim can continue with the valid row

#### Scenario: quarantine failure cannot lose or execute the row
- **WHEN** quarantine persistence fails
- **THEN** the source remains inert and health is red
- **AND** it is neither deleted nor made selectable

### Requirement: Operator work is honest with zero compatible capacity
A committed operator task SHALL remain visible and pending when no compatible
worker is online and SHALL invoke no provider, model, platform-maintainer
credential, quota, hardware, host, or market purchase merely because it is
queued. When compatible capacity appears it SHALL enter the ordinary epoch-2
single-winner claim and lifecycle path.

#### Scenario: zero-capacity admission remains honest
- **WHEN** operator work commits with no compatible worker online
- **THEN** it is visible as `awaiting_compatible_capacity`
- **AND** no compute, model, credential, quota, host, or payment path is invoked

#### Scenario: explicit worker predicates preserve pending work
- **WHEN** capacity fails request-type, served-LLM, directed-daemon, protocol, or quarantine predicates
- **THEN** it does not claim, fail, or consume the task
- **AND** later compatible capacity may claim it

### Requirement: Operator activation is two-key, mixed-version, and section-14 gated
Effective v2 writing SHALL require both a deployment kill switch and an atomic
per-universe cutover manifest, checked on every admission. Manifest states SHALL
be `disabled`, `readers_only`, `canary`, `enabled`, and `rollback`, with rollout
ID, queue epoch, required capability, allowed reader/server build SHAs, canary
universe set, config hash, owner, activation/expiry times, and evidence.
`TINYASSETS_OPERATOR_REQUEST_WRITES` SHALL default off. Weight zero is an
ordinary opt-out and does not require this priority-elevation gate. A composed
verdict that would accept positive priority while the gate is off SHALL return
`operator_priority_unavailable` with zero persistence and no silent demotion.
Positive weight without active priority authority SHALL instead return
`priority_authorization_required` before cutover evaluation. Rollback SHALL
stop new priority-elevated writes within 60 seconds while v2 readers continue
draining.

Pinned safe v1 executors MAY coexist on isolated epoch 1. Unknown or partially
upgraded online workers SHALL block `canary -> enabled`; no online worker SHALL
NOT block zero-host admission. Historical host rows SHALL remain v1 and SHALL
NOT be relabeled. A customized host weight SHALL NOT become an operator weight
without explicit reviewed configuration.

The canonical §14 run SHALL warm for 60 seconds then keep 500 daemons
concurrently alive for the full 300-second measurement: 400 compatible v2 and
100 pinned safe v1. It SHALL preseed 100 historical host rows; admit exactly
1,000 unique requests (500 operator, 300 ordinary, 200 directed) over five
minutes; add 10% concurrent same-key replays plus conflicts outside that count;
run 100 status clients at one read/second; and inject invalid v2 fixtures.
Every one of the 1,000 canonical requests SHALL have compatible capacity
continuously available; every directed request SHALL name a live compatible v2
daemon. Dispatch latency from `committed_at` to durable claim SHALL be computed
over all 1,000 committed requests and have p99 below three seconds. Any
unclaimed canonical request SHALL fail the run rather than leave the denominator.

Pass SHALL require exactly 1,000 aggregates and zero loss, duplicate live
claims, invalid-row execution, unauthorized/legacy v2 claims, corruption, or
deadlock. Raw evidence SHALL recompute counts and percentiles and record exact
commands, seed, releases/config/manifest, topology/mount, clock sync,
p50/p95/p99/max, lock/transaction timing, throughput, store/file growth, write
amplification, CPU, memory, disk/fsync, handles, network, and process count.
Peak CPU, memory, and disk SHALL each retain at least 20% headroom. Admission
and claim-operation latency SHALL be reported separately and remain within 20%
of a same-environment readers-only baseline; they are not §14 targets.

#### Scenario: literal section-14 storm passes
- **WHEN** the production-shaped canonical run holds all 500 daemons for all 300 measured seconds and admits 1,000 unique requests
- **THEN** all 1,000 have compatible capacity, all 200 directed requests name live v2 daemons, all 1,000 reach durable claim, and full-denominator dispatch p99 is below three seconds
- **AND** independently recomputable evidence proves the population, duration, latency, resource headroom, zero-loss/isolation invariants, and raw counts

#### Scenario: mixed-version recovery is measured separately
- **WHEN** a second instrumented run rolls v2 workers and disconnects/reconnects v1 workers
- **THEN** epoch isolation and single-winner recovery remain correct
- **AND** this run is not substituted for the canonical 500-daemon steady-window result

#### Scenario: zero-capacity recovery does not spend platform compute
- **WHEN** all workers stop, operator work commits, and v2 capacity later returns
- **THEN** no provider/model/credential/quota/payment/hardware path runs while capacity is absent
- **AND** restored capacity produces single-winner claims with p99 below three seconds measured from capacity availability
