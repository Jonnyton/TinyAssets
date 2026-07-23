## Context

Permission consolidation intentionally replaced identity-derived `host_request`
admission with the capability-era `operator_request` label. The producer
changed, but the BranchTask validator, dispatcher weights/enabled/status maps,
cloud wakeup, stuck-work classification, generated mirrors, and tests did not.
A verified reproduction on 2026-07-22 returned `status=pending`, a positive
priority weight, an empty `branch_task_id`, and “yours is next” while persisting
one request and zero tasks.

The handler derives priority from process-global environment variables, writes
`requests.json` without a lock, separately appends `branch_tasks.json`, and
swallows the second failure. Two JSON files cannot form an atomic accepted-
write boundary. More importantly, putting v2 fields in the existing task file
cannot isolate mixed versions: a v1 binary ignores the unknown tier during
selection but its claim primitive can still mutate any known task ID.

The project already has a canonical `user_requests` table in the shared
`.tinyassets.db`. The target hosted architecture has a Postgres
`request_inbox` plus narrow claim RPC. This change therefore defines one
backend-neutral protocol-v2 admission aggregate and an isolated queue epoch:
SQLite is the current one-control-plane bridge; Postgres preserves the same
constraints in the hosted target.

## Goals / Non-Goals

**Goals:**

- Make an authenticated exact-universe priority grant produce one auditable,
  durable, pickable operator task.
- Keep host/runtime identity, credentials, execution capacity, and payment
  authority separate from user/operator authority.
- Atomically create the canonical Request, admission receipt, and v2
  BranchTask in one transactional control-plane commit.
- Make protocol-v2 tasks inaccessible to v1 claim code while allowing v2
  workers to drain both epochs.
- Preserve deterministic scoring, single-winner claim/lease semantics,
  zero-host durability, and BYOC-or-market boundaries.
- Make the public result idempotent, complete, and free of false FIFO claims.

**Non-Goals:**

- Grant provider credentials, quota, hardware, execution leases, or payment
  authority.
- Redesign general dispatcher fairness or promise starvation freedom.
- Reclassify or rewrite historical v1 tasks.
- Export operational request text into OKF, Git, commons, or public mirrors.
- Implement runtime changes while overlapping PR/file claims remain active.

## Decisions

### 1. Priority authority is one request-local composed verdict

New priority admission requires the authenticated tenant and subject from
request context, ordinary `submit_request` action authorization, `write` or
`admin` ACL on the exact universe, a requested weight greater than zero, and an
active `submit_priority_request` grant for that subject and universe. The
ordinary submit leg follows the canonical fine-grained-action-or-coarse-effect
rule. The priority grant is a separate elevation modifier: coarse effects, ACL
admin alone, wildcard grants, host identity, environment variables, and
caller-supplied evidence cannot satisfy that leg.

A trusted capability-administration service issues and revokes the priority
grant. The issuer must hold exact-universe `admin` ACL plus the
`grant_capabilities` action scope. Each row stores subject, universe, issuer,
issued time, optional expiry, revoked time, and a monotonically increasing
generation. Repeated revoke is idempotent; regrant creates a higher generation.
Expiry is exclusive: a grant is inactive at or after `expires_at`.

Every replay authenticates and re-checks ordinary submit authorization plus
current write/admin ACL before idempotency lookup. ACL loss returns the ordinary
non-enumerating `universe_access_denied` response with no stored IDs. Revoking
only the priority grant after commit is prospective: with ACL intact,
same-key/same-body replay returns the historical result; a new key/body cannot
use the revoked or expired grant. Positive weight without an active grant
returns `priority_authorization_required` with zero persistence; weight zero is
an explicit ordinary opt-out even for a grant holder.

### 2. Operator is a real top-band tier; host remains historical

`operator_request` is valid, enabled, reported `live`, and has default base
weight `100`, equal to historical `host_request`. `owner_queued=80`,
`user_request=60`, `paid_bid=50`, `goal_pool=40`, and `opportunistic=10`
retain their defaults and enablement rules.

Priority input must be a JSON number (not string or Boolean), finite, and in
the inclusive range `[0, 100]`. Zero, finite positive fractions such as
`1e-9`, values immediately below 100, and exactly 100 are accepted; negatives,
NaN, infinities, and over-cap values fail before persistence. The cap and
`operator-priority-v1` version are disclosed.

A verified directed assignment remains `owner_queued`. It retains a requested
positive bounded boost only with active priority authority; otherwise a
positive request fails rather than silently demoting. Weight zero is ordinary
and unboosted. Scoring remains additive, so boosted owner work can outscore an
unboosted operator task. This change does not claim lexicographic dominance or
starvation freedom.

No new writer emits `host_request`. Historical rows stay labeled v1 accepted
work. Customized configs must add an explicit operator weight; missing
operator weight never inherits the host setting.

### 3. One transaction owns Request, Admission, and v2 BranchTask

The backend-neutral `RequestAdmissionStore` owns four related logical records:

- existing canonical `user_requests` Request entity;
- one-to-one `request_admissions` authorization/idempotency row;
- `branch_tasks_v2` execution-intent row in queue epoch 2;
- append-only `request_admission_events` audit rows.

One `BEGIN IMMEDIATE` SQLite transaction (or one Postgres transaction) performs
the authority reads, scoped idempotency lookup, random ID allocation, Request
insert, admission insert, v2 task insert, `committed` event, and commit.
A crash before commit rolls the whole aggregate back; there is no durable
half-pair to repair. Result serialization/delivery after commit is not part of
the transaction and replay reconstructs the result from committed rows.

The admission row stores opaque random IDs, tenant/actor/universe, a keyed hash
of the public idempotency key, canonical-body digest/version, trigger source,
accepted weight, policy/grant generation, sanitized receipt, timestamps, and
stored public result fields. Constraints enforce one admission per Request and
task and uniqueness of `(tenant_id, actor_id, universe_id,
idempotency_key_hash)`. Random ID collisions retry inside a fresh transaction.
Raw idempotency keys and credentials are not stored.

SQLite is authoritative only for its one always-on control-plane deployment and
shared volume; host trays never mint competing ledgers. In the Postgres target,
one `request_inbox` row co-locates the logical Request payload and BranchTask
lifecycle, carries stable unique `request_id` and `branch_task_id`, and is
claimed through the existing narrow row-lock RPC. Sibling admission/event rows
reference both IDs in the same transaction. The hosted backend creates neither
a second task row nor a second dispatcher. None of this operational state is
OKF/knowledge truth.

### 4. Queue epoch 2 creates enforceable mixed-version isolation

Legacy `requests.json` and `branch_tasks.json` are queue epoch 1. New
MCP-facing request admissions create the canonical Request and task only in the
transactional epoch-2 store; they are not copied into the v1 executable queue.
V2 readers combine eligible v1 and v2 candidates for scoring and can drain
both. V1 binaries can open and claim only v1 files, so even possession of a v2
task ID cannot mutate epoch 2.

A v2 claim performs a conditional pending-to-running transition inside the
epoch-2 transaction and re-checks the worker’s server-derived protocol
descriptor under the same transaction. Claim, lease, heartbeat, cancellation,
recovery, and terminal transitions retain BranchTask semantics but use the v2
store rather than the v1 whole-file rewrite.

That claim is internal scheduling reservation only. External or distributed
execution must next pass the active `distributed-execution` B2 boundary and
present its signed owner/daemon/job/capsule/lease/fence grant. An operator
receipt, admission row, worker heartbeat, or mutable queue claim can narrow or
reject execution but can never provide positive execution/result authority.

Workers advertise `queue_protocol_version=2`, capability
`operator_request_v1`, build SHA, config hash, boot ID, worker ID, runtime
instance ID, and universe in durable runtime metadata and per-worker
heartbeats. The descriptor is derived from release/runtime state, never caller
input or auth capabilities, and is live for 90 seconds. Missing, expired,
mismatched, or untruthful evidence makes the worker ineligible at both
selection and claim.

### 5. Idempotency is scoped, body-bound, and durable

The public name is `idempotency_key` only. It is required for every canonical
`write_graph(target="request")` call, 16–128 ASCII bytes, and matches
`^[A-Za-z0-9._:-]+$`. The server derives tenant, actor, and universe from
authenticated context. Reusing a raw key in another actor/tenant/universe scope
is independent and reveals nothing about the other namespace.

The body digest is SHA-256 over RFC 8785 canonical JSON containing schema
version, universe ID, exact UTF-8 text, request type, branch ID, pickup
incentive, directed daemon ID/instruction, and requested priority weight. Text
is not Unicode-normalized after boundary validation. Unknown request-target
fields are rejected. Same-scope/same-body replay returns the original pair with
`idempotent_replay=true`; changed-body reuse returns
`idempotency_key_body_conflict` and changes nothing.

Live and nonterminal admissions remain indefinitely. Full Request/result detail
remains at least 30 days after terminal state. Then private text, result detail,
and audit detail may compact, but a minimal scoped key hash/body digest/ID/
terminal-state tombstone remains until universe deletion so an old retry cannot
create another effect. A committed replay does not append a second mutation-
ledger entry; it may append a separate access-audit event.

### 6. Invalid v2 rows quarantine without poisoning selection

Schema constraints and the trusted insert path prevent ordinary forgery.
Import, corruption, or unsupported future-protocol rows are classified as
`invalid_operator_admission`, `unsupported_protocol`, or incomplete. A
separate transactional maintenance step—not the pure selector—moves invalid
rows into `branch_tasks_v2_quarantine` keyed by canonical-row digest and records
reason plus first/last seen. The source row is disabled only in the same
transaction that preserves its quarantine receipt.

Valid work with no compatible worker is `awaiting_compatible_capacity`.
Malformed work is `invalid/quarantined`; a disabled configured tier is
`policy_parked`. Status reports counts, oldest age, reasons, digests, and IDs,
not private request text or authorization evidence. One invalid row cannot
block selection or claim of valid rows in either epoch.

### 7. The canonical MCP result is honest and rank-free

`write_graph(target="request")` accepts `idempotency_key` and numeric
`priority_weight`, rejects unknown request-target fields, and routes through
the transactional boundary. `/mcp-directory` implements the same protocol
rather than silently diverging. The handle-level `idempotentHint` stays false
because other `write_graph` targets are not idempotent.

A success result contains exactly:

- `universe_id`, `admission_id`, `admission_state="committed"`;
- non-empty `request_id` and `branch_task_id`;
- `request_status="pending"` and actual `trigger_source`;
- `accepted_priority_weight`, `priority_weight_cap=100`, and
  `priority_policy_version="operator-priority-v1"`;
- `idempotent_replay` and `directed_daemon_id` (empty when not directed).

It omits `queue_position`, `ahead_of_yours`, `what_happens_next`, raw grants,
evidence handles, and any promise that work is next. Dispatcher rank is
daemon-relative and race-sensitive, so the admission surface exposes none.

### 8. Writer activation is a two-key per-universe gate

Effective v2 writing requires both a deployment kill switch and an atomically
published per-universe cutover manifest. The manifest moves
`disabled -> readers_only -> canary -> enabled -> rollback` and records rollout
ID, queue epoch, required worker capability, allowed reader/server build SHAs,
canary universes, config hash, owner, activation time, expiry, and evidence.
The writer reads both gates on every admission rather than caching startup
state. Canary admits only allowlisted universes. Rollback or kill-switch off
stops new v2 writes within 60 seconds while v2 readers continue draining.

`TINYASSETS_OPERATOR_REQUEST_WRITES` defaults off. Weight zero is an ordinary
opt-out and does not require this elevation gate. A composed verdict that would
accept positive priority while the operator gate is off returns
`operator_priority_unavailable` with no persistence and is never silently
demoted; positive weight without active authority instead returns
`priority_authorization_required`. Before final v2 cutover, ordinary v1
submission may remain available; after a universe reaches `enabled`, every
canonical request write uses epoch 2 and no public v1 request writer remains.

Pinned safe v1 executors may coexist because storage epochs isolate them. An
unknown or partially upgraded online worker blocks `canary -> enabled`; no
online worker does not block zero-host admission. Legacy submission-server
writers may not remain behind the public route after cutover.

### 9. Activation carries the literal §14 proof

On production-shaped OS/filesystem/storage and release builds, warm up for 60
seconds, then keep 500 daemons concurrently alive and polling for the full
300-second measured window: 400 v2-capable and 100 pinned safe v1. Preseed 100
historical v1 host rows. Admit exactly 1,000 unique accepted requests
(500 operator, 300 ordinary, 200 directed) uniformly during the window, add
10% concurrent same-key replays, changed-body/cross-scope conflicts outside the
accepted count, 100 status clients at one read/second, and invalid v2 fixtures.
Workers stop after durable claim and invoke no model/provider.

Every canonical request has compatible capacity continuously available; each
directed request names a live compatible v2 daemon. Dispatch latency is from
`committed_at` to durable winning claim across all 1,000 committed requests and
must have p99 below three seconds. Any unclaimed request fails the run.
Admission response and claim-operation latencies are reported separately and
must not regress more than 20% from a same-environment readers-only baseline;
they are not mislabeled §14 targets.

Pass requires exactly 1,000 admission pairs; zero loss, duplicate live claims,
invalid-row execution, unauthorized/legacy v2 claims, corruption, or deadlock;
and all invalid fixtures inert and quarantined by digest. Raw timestamped
evidence must recompute every count/percentile and record exact commands, seed,
SHAs/images/config/manifest, topology/mount, clock sync, p50/p95/p99/max,
lock wait/hold, throughput, store/file growth, write amplification, CPU,
aggregate memory, disk/fsync, open handles, network, and process count. Peak
CPU, memory, and disk each retain at least 20% headroom.

A separate instrumented recovery run performs rolling v2 restart and v1
disconnect/reconnect without pretending the canonical run held 500 throughout.
A zero-capacity phase stops all workers, admits operator work, proves no
provider/model/credential/quota/payment/hardware invocation, then restores v2
capacity and proves single-winner claims and p99 below three seconds measured
from capacity availability.

## Risks / Trade-offs

- **Epoch 2 adds a second transitional read path** — it is deliberate
  isolation, not a permanent fork; v2 drains v1 while all new public writes
  converge on the target transactional inbox.
- **SQLite is deployment-local** — only the always-on control plane owns it.
  The hosted target must migrate the same aggregate and constraints to
  Postgres; trays are consumers, never competing authorities.
- **A top tier can delay lower work** — cap/weight disclosure and load evidence
  bound this change; fairness remains a separate decision.
- **Historical host rows lack modern evidence** — inventory and drain them
  without relabeling.
- **Quarantine is intentionally noisy** — invalid work must stay visible and
  inert rather than be discarded or policy-parked.
- **Whole-file v1 performance may remain poor** — it cannot justify weakening
  §14; if merging v1 candidates breaks the gate, drain/shard/migrate v1 rather
  than reducing concurrency.
- **Generated mirrors can drift** — canonical files regenerate through
  `python packaging/claude-plugin/build_plugin.py`; parity is a gate.

## Migration Plan

1. Land the three capability contracts and inventory historical host rows,
   custom weights, v1 writers, and active worker build SHAs.
2. Resolve overlapping PRs, run collision checks, and claim exact storage,
   auth, public-surface, runtime, mirror, migration, and test files.
3. Pre-migrate the admission/event/v2-task/quarantine schema; add versioned
   grants, v2 readers/claim, worker descriptors, status, and cloud wakeup with
   both writer keys off.
4. Regenerate the plugin mirror and deploy the compatible reader/worker cohort.
5. Run authorization, idempotency, mixed-version, exact §14, recovery, and
   zero-capacity proofs; publish the reviewed cutover manifest.
6. Move canary universes then the enabled cohort to v2 public writes, run
   public MCP/rendered-chatbot verification, and watch post-fix real use.
7. Roll back by disabling writes within 60 seconds while retaining v2 drain.

## Resolved Decisions Requiring Inventory Evidence

- The cap is `100` under `operator-priority-v1`.
- Grant administration is exact-universe and requires both universe admin ACL
  and `grant_capabilities`.
- Queue epoch 2 is inaccessible to v1 claim code; v2 workers drain both epochs.
- Production inventory still decides how historical pending/running host rows
  and custom host weights are drained or retired; they cannot become operator
  evidence.
