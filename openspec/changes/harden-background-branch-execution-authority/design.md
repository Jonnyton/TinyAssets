## Context

TinyAssets has at least twelve ways for branch work to outlive, detach from, or
re-enter after the request that originally authorized it:

1. cron/interval schedules;
2. event subscriptions;
3. a daemon's recurring `soul.md` loop;
4. async live/version root runs and selector/leaderboard/market delegates;
5. authenticated Request admission that persists a `BranchTask`;
6. goal-pool or paid-market producers that materialize durable tasks;
7. claimed `BranchTask` rows;
8. branch work enqueued by an approved source node;
9. live or frozen `invoke_branch` child execution, including async and retry;
10. interrupted-run resume and startup recovery;
11. the default compiled `branches/universe_cycle.yaml` daemon stream.

Historical wiki `file_bug` forwarding into `bug_investigation` queue work is
not a twelfth issuance root. `retire-cheat-loop` makes current filing
side-effect-free and owns the authority-safe locked migration of legacy rows
and receipts; this change may inventory that retired class only to exclude it
from binding, backfill, bounded drain, revival, and execution.

The current paths preserve scheduling and queue state but not target authority.
`tinyassets.scheduler` accepts an `owner_actor` string from the action payload;
the daemon later executes with `UNIVERSE_SERVER_USER`; a queue claim proves only
possession of a row; epoch-1 graph enqueue permits public targets because it has
no durable request principal; and a governed soul edit can change the loop
branch without rotating any execution grant. These mechanisms cannot safely
run private work after the request ends and cannot distinguish the principal
who authorized the work from the daemon or worker that executes it.

This change is the target-authority counterpart to
`harden-background-provider-execution-authority`. A target attempt must be
valid before provider-work authority can be issued, but neither authority
domain substitutes for the other. It also composes with branch ACLs, daemon
identity, the epoch-2 queue/admission contract, distributed B2 grants, and
provider-attempt receipts.

The connector actions remain the first-class product surface. The design adds
no Agent Village or web-app dependency.

`PLAN.md` currently describes one file-locked claimer while the epoch-2
OpenSpec program requires transactional claiming. The live coordination board
correctly treats that as unresolved. This change can specify the authority
contract, build models and dark/test adapters, and close call sites, but it
cannot choose or activate the fleet scheduling/claim mutation authority until
a host-approved PLAN reconciliation names the owner.

## Goals / Non-Goals

**Goals:**

- represent unattended branch authorization as durable server-owned state;
- revalidate current principal, universe, branch, trigger, daemon, and
  revocation state before every logical attempt;
- pin each admitted attempt to an exact branch snapshot and execution audience;
- make schedule/subscription and soul-loop changes recoverable across crashes;
- close request-admission, producer, built-in-cycle,
  direct-child, and resume authority seams;
- attenuate authority for graph-enqueued children without weakening existing
  universe, lineage, depth, budget, or concurrency limits;
- make one logical trigger produce at most one target attempt under concurrent
  hosts;
- migrate legacy work without trusting actor strings, environment, visibility,
  or queue possession; and
- preserve explicit provenance for both authorizer and executor.

**Non-Goals:**

- changing the canonical account, universe ACL, branch authorship, or daemon
  ownership models;
- granting provider, credential, outbound-effect, payment, moderation, or B2
  authority;
- making a trigger row, queue row, daemon identity, worker lease, or receipt ID
  into a bearer capability;
- synchronous execution from graph enqueue;
- redefining the demand-side change's IANA timezone, DST, period-identity, or
  declared missed-tick policy;
- allowing branch-authored code to inherit all rights of its authorizing
  principal;
- choosing the final PostgreSQL-versus-local control-plane deployment shape;
- designing the deferred Agent Village or any replacement web interface.

## Decisions

### 1. Durable binding and single-attempt target claim are distinct

The authority service owns two primary records:

| Record | Purpose | Not authority by itself |
|---|---|---|
| `BackgroundBranchBinding` | Durable authorization intent for one work source, principal, universe, branch target, operation, and bounded delegation | binding ID, schedule/subscription/soul/task row |
| `BackgroundBranchAttempt` | One revalidated execution attempt pinned to an exact target snapshot and executor audience | attempt ID, queue claim, daemon/worker ID |

The binding contains, at minimum:

- opaque binding ID, schema version, status, generation, and digest;
- canonical authorizing principal/account ID;
- universe ID, exact branch definition ID, and operation;
- source kind and source identity: schedule, subscription, pinned soul, root
  run, request admission, producer subscription/contract, resumed run, direct
  child or parent attempt;
- current source revision/digest and revocation generation;
- target mode (`live_at_attempt` or `pinned_version`);
- permitted executor class and optional daemon/runtime binding;
- expiry, maximum attempts, and remaining depth/count/cost envelopes where
  applicable; and
- an explicit child-delegation policy.

The attempt contains, at minimum:

- opaque attempt ID and deterministic logical-attempt key;
- binding ID, binding digest, and generation;
- principal, universe, branch definition, exact branch version/content digest,
  and operation;
- source trigger/task/soul identity and generation;
- daemon/runtime/worker audience plus claim generation and lease state;
- parent/origin lineage and inherited limits;
- state, timestamps, terminal reason, and audit correlation IDs; and
- references to separately required B2, provider-work, and provider-attempt
  evidence where those domains apply.

Serialized IDs and digests are references, not bearer authority. Only the
server-owned authority service can resolve or transition these records.

Collapsing the binding into a schedule or `BranchTask` was rejected because
those records contain caller-influenced data, have different lifecycles, and
cross process/storage boundaries. Reusing `ProviderWorkBinding` was rejected
because a branch target may be valid while provider use is forbidden, and vice
versa.

### 2. Bindings have closed server-owned issuance roots

A binding can be issued or rotated only by one of these transitions:

- **Authenticated schedule/subscription create:** the handler derives the
  canonical request principal, authorizes the universe and exact branch, and
  creates the trigger plus binding. `owner_actor` is ignored as authority and
  is not persisted as identity truth.
- **Authenticated trigger reauthorization:** pause/unpause, replacement, or
  recreation derives the current request principal and rotates the binding
  after fresh target checks. Admin control can pause or revoke but cannot
  silently become the authorizing principal.
- **Authenticated Request admission:** the request/admission/task transaction
  derives the canonical request principal, resolves the exact loop/branch
  target, and commits one source binding with the Request, admission, and
  protocol task. The admission verdict narrows or rejects this transition but
  is not itself target authority.
- **Goal/market producer subscription or contract:** authenticated goal
  subscription creates a bounded same-universe target delegation; an accepted
  paid-market contract supplies its separately authenticated requester and
  target scope. Producer emission may derive one exact task binding only from
  that durable source generation. Pool YAML, `posted_by`, producer identity,
  and the fresh-install anonymous maintenance subscription cannot authorize
  execution; ambiguous/default subscriptions hold until a founder
  reauthorizes them through the connector. Market-derived producer work
  remains held until `paid-market-track-e-wave-2-transport` defines and lands
  the accepted execution-contract generation this root consumes.
- **Wiki filing is excluded:** `file_bug` commits filing metadata only and
  creates no background binding, attempt, task, queue entry, or trigger receipt.
  Historical `bug_investigation` rows and receipts are retirement inputs owned
  by `retire-cheat-loop` task 2.5; no principal or content evidence can convert
  them into a background issuance root.
- **Universe creation or governed soul edit:** an authenticated principal that
  can administer the universe and run the declared branch creates or rotates
  the loop binding. A governed edit that preserves the normalized loop target
  may carry the existing scope to the new pinned soul digest. A target change
  requires fresh authenticated authorization or an existing binding whose
  explicit delegation names that exact new target.
- **Authorized root run:** request-local target authorization MUST create a
  root binding with a bounded child-delegation policy for work enqueued by that
  run.
- **Authorized run resume:** an initial run binding may issue one fenced resume
  binding/attempt for the exact persisted branch version and checkpoint after
  canonical resume-principal, run ownership, ACL, cancellation, and generation
  revalidation. Startup recovery can mark a run interrupted and fence stale
  work but cannot mint resume authority.
- **Authorized parent attempt:** the service may derive an exact child binding
  for enqueue or live/frozen direct invocation only within the parent's
  universe, lineage, remaining depth/count/cost/retry limits, and explicit
  target policy. Branch-authored `child_actor` is rejected at validation and
  cannot select execution identity.

Creation uses canonical request subject, ACL, branch, daemon, and run read
interfaces. Caller kwargs, stored actor labels, process environment, queue
claims, admission receipts, public visibility, and worker identity cannot
issue or widen a binding.

Public branch visibility remains relevant to target authorization but is not a
durable execution grant. It permits the service to issue a narrowly scoped
binding at an authorized root or child transition; it never lets a later worker
invent one.

### 3. Every attempt is issued just in time from fresh state

Before creating or claiming an attempt, the service revalidates:

- binding active, unexpired, unexhausted, not revoked, and digest/generation
  exact;
- canonical authorizing principal still exists and retains the required
  universe and branch access;
- universe ID and physical queue universe match;
- branch definition exists, is not tombstoned, and the requested live/pinned
  mode resolves to an allowed exact version;
- trigger/task/request/producer/soul/run source identity, revision, and
  cancellation state match;
- daemon/runtime/worker is eligible for the binding's executor class;
- parent/origin lineage and remaining attenuation limits are exact; and
- no active, terminal, or indeterminate attempt already owns the logical key.

Fresh resolution pins the branch version/content digest into the attempt.
Existing schedule behavior therefore follows the current live branch definition
at each fire while each individual attempt is immutable. A frozen trigger can
instead require its pinned version.

Any failed check creates no runnable attempt and performs no provider,
credential, payment, or outbound-effect access. The source is placed in a
typed `target_authority_held` state with a non-secret reason such as
`reauthorization_required`, `target_changed`, `principal_revoked`,
`source_generation_mismatch`, or `indeterminate_prior_attempt`.

### 4. Logical attempt keys close duplicate-fire and replay races

Each source supplies one deterministic key:

- schedule: schedule ID + schedule generation + due instant;
- subscription: subscription ID + generation + event ID;
- soul loop: universe ID + pinned soul version/digest + cycle ordinal;
- request admission: tenant + Request/admission/task IDs + body digest +
  admission generation;
- producer emission: producer kind + durable subscription/contract generation
  + source-item revision + subscriber universe;
- run resume: run ID + exact checkpoint/version + resume generation;
- claimed task: physical universe + branch task ID + task generation; and
- graph child: parent attempt + node execution/invocation ordinal + child
  ordinal + retry ordinal, for both enqueue and live/frozen direct invocation.

The authority store enforces a unique key and atomically creates or follows the
winner. Concurrent scheduler ticks, event delivery, daemon cycles, queue
workers, or replayed enqueue calls cannot create a second target attempt.
Terminal replay returns the same outcome projection; an indeterminate attempt
holds until reconciled.

The event-delivery record and target-attempt reservation commit together when
they share a transaction. Across stores, delivery first enters `prepared`,
the attempt is reserved, and recovery either commits the exact pair or holds
it; delivery is never marked complete before an attempt or explicit denial
record exists. “Exactly once” remains at-most-one admitted logical attempt, not
a promise that external execution succeeds exactly once.

### 5. Schedule and subscription ownership is request-derived

Public schedule/subscription actions continue to use the existing connector
handle and action names. Registration:

1. derives the authenticated request principal;
2. authorizes the universe and exact branch operation;
3. reserves the per-principal active limit;
4. writes the binding and trigger as one transaction or recoverable prepared
   pair; and
5. returns opaque source and binding-status references.

List, pause, unpause, unschedule, and unsubscribe derive the same request
principal. They disclose and mutate only owned rows unless current universe
admin authority permits control. Unauthorized and absent rows have the same
external response shape to avoid an existence oracle. Admin pause/revoke does
not transfer ownership.

Each fire revalidates current authority; creation-time success is not perpetual
permission. A paused, held, or revoked source creates no provider work.
The schedule-period identity produced by `demand-side-signals` is the due
instant component of the logical key. IANA timezone validation, DST
gap/overlap rules, and `skip`, `fire_once`, or `backfill_bounded(n)` decide
which period identities exist; this change binds authority to those identities
without minting replacements. `demand-side-signals` must sync first, and this
change's merged requirement must sync second so neither timing nor authority
clauses are lost.

### 6. Soul declaration and binding use a recoverable version transition

`soul.md` is governed content, and its `Loop branch` line is executable
configuration. The pinned soul version/content digest therefore participates
in the loop binding.

Changing the soul uses a prepare/apply/commit protocol:

1. validate the governed edit with compare-and-swap and calculate the proposed
   normalized loop target and content digest;
2. authorize and prepare a candidate binding for that exact target and digest,
   or prepare a carry-forward when the target is unchanged;
3. atomically write the soul edit/snapshot under the existing universe lock;
4. commit the candidate and revoke the old binding; and
5. publish the new loop generation.

Execution accepts only an active binding whose soul version/digest and loop
target match the current pinned soul. A crash after prepare but before soul
write aborts the candidate. A crash after soul write but before commit is
recovered by exact digest comparison; the matching candidate is committed,
the old digest aborts it, and any third state quarantines the loop for manual
reauthorization. No code falls back to `PROGRAM.md`,
`UNIVERSE_SERVER_USER`, or the previous binding after a mismatch.

Edits that do not change the normalized loop target can carry the same narrow
target scope to the new digest; they do not inherit broader principal rights.
A changed target cannot be inferred from the learning source or daemon actor.

The default compiled `branches/universe_cycle.yaml` stream is not a permanent
infrastructure-authority exception. Before enforcement it must be materialized
as an ordinary registered Branch version, declared in governed `soul.md`, and
bound through authenticated universe creation or provable founder/admin
migration. A legacy universe without that proof enters
`reauthorization_required`; the daemon cannot keep streaming the built-in
branch outside `execute_branch` or run provenance.

### 7. Graph child authority is transferred, never copied

The run context receives a non-serializable child-delegation object derived
from its active root/parent binding. For each enqueue or live/frozen direct
child invocation, the service resolves the requested target and atomically
creates an exact child binding while debiting the parent's remaining
depth/count/cost/retry envelope. Every initial invocation and retry has a
stable ordinal and exact attempt; async mode does not weaken the gate.
Concurrent children cannot receive more authority in aggregate than remains.

The default policy permits only same-universe public targets within existing
run-wide, global-active, lifetime-lineage, and depth caps. A private target
requires an explicit exact-target allowlist created by the authenticated root
or parent binding. Branch definitions carrying `child_actor` fail validation
after enforcement rather than selecting or relabeling execution identity.
Unknown/dynamic targets outside the policy fail before queue append or direct
child execution.

The queue record carries only the opaque binding reference/digest and trusted
lineage. It cannot carry a principal, ACL verdict, or serialized capability.
The epoch-1 file-backed queue never nests an authority transaction inside its
file lock: child authority is prepared first, queue append commits under the
queue lock, and reconciliation activates the exact pair before pickability.
Only a future epoch-2 store that owns both rows may use one transaction.
A conclusive queue-cap or append refusal aborts the prepared child and returns
its reserved envelope exactly once to the still-active parent generation, so
the existing exact successful-enqueue invariant is preserved. Proven unused
authority after a conclusive child close may likewise return once; an
indeterminate boundary or stale parent generation expires rather than being
double-credited.

Epoch-1 remains public-only until its file-backed task shape and reconciliation
path carry these references without weakening existing guards. Epoch-2 cannot
activate until every dark-era row is either linked to provable canonical
authority, drained under the old public-only path before enforcement, or held.

### 8. Queue claim, target attempt, and execution authorities compose

A branch-task queue claim is only a scheduling reservation. The worker first
snapshots and verifies its current queue lease/generation under the queue lock,
releases that lock, then atomically claims the exact
`BackgroundBranchAttempt` bound to that snapshot, physical universe, task
generation, and daemon/runtime/worker audience. It rechecks the unchanged
lease/generation under the queue lock before branch resolution. If recheck
fails before an irreversible boundary, it releases the target claim
automatically; an indeterminate release holds the row.

A missing, revoked, exhausted, unauthorized, or indeterminate attempt moves the
row by fenced transition into non-pickable `target_authority_held`. An audience
or lease mismatch from a provably dead/invalidated predecessor instead
advances the attempt-claim generation and autonomously reclaims the same
attempt when every irreversible boundary is conclusively absent or closed. A
generation-checked recovery-proven transition may revive the same held row to
`pending`; authenticated reauthorization is required only when the binding or
target authority itself must rotate. Neither path appends replacement work.

Held rows do not count against the global active `pending` + `running` queue
cap. They continue to count exactly once against the lifetime-lineage cap
because that cap is a non-refundable growth budget, including archived
terminal descendants. Reauthorization of the same row consumes no additional
lineage unit. Cancellation or archival cannot refund a lifetime unit, which
prevents repeated hold/cancel cycles from bypassing the growth bound while
allowing unrelated lineages and global queue capacity to proceed.

Where distributed execution applies, the worker additionally needs a current
B2 execution grant. Where a branch can reach a provider sink, it additionally
needs a `ProviderWorkAuthorityReceipt` and later a provider-attempt receipt.
All records cross-reference immutable IDs/digests for audit, but no record can
mint or replace another.

The order is:

1. queue-lock snapshot of current task/claim/lease generation, then release;
2. target-attempt claim transaction bound to that snapshot;
3. queue-lock revalidation, then release; on mismatch, release/fence the target
   claim before continuing;
4. B2 claim where applicable;
5. provider-work issuance where applicable;
6. exact branch execution; and
7. independent terminal settlement of each authority domain.

No authority transaction nests the queue file lock, provider-assignment lock,
credential lock, or external-effect transaction. Recovery uses generation-bound
non-authorizing proofs and compare-and-swap; lease expiry alone does not prove
the prior executor dead.

### 9. Provenance separates authorizer from executor

Run and audit records persist:

- `authorized_by_principal`;
- background binding and attempt IDs/digests/generations;
- trigger/task/soul source and logical-attempt key;
- universe, exact branch version/content digest, and lineage;
- executing daemon/runtime/worker identity;
- current status and terminal/hold reason; and
- B2/provider/effect receipt references when applicable.

The run actor is derived from the canonical authorizing principal and execution
context, never from `UNIVERSE_SERVER_USER`. User-visible history can explain
“authorized by” and “executed by” separately without exposing bearer material
or credentials.

### 10. The authority store is one interface and live placement is PLAN-gated

`BackgroundBranchAuthorityStore` is the sole interface for bindings, attempts,
claims, generations, and recovery transitions. It requires atomic insert,
compare-and-swap, uniqueness, bounded query, and transaction primitives.
Scheduler, soul, queue, daemon, and worker code call the interface; they do not
open its tables directly.

Local tests and dark inventory may use a non-live adapter colocated with the
current runs SQLite database. That adapter cannot become the fleet mutation
authority merely because it is convenient. Live schedule/task claim storage
and transaction boundaries remain blocked until the host-approved PLAN
reconciliation resolves file-locked versus epoch-2 transactional claiming and
the owning capability assigns one mutation authority. The behavioral contract
does not depend on a local file path, PostgreSQL table name, or one
always-online host.

Choosing “put the grant in `BranchTask` JSON” was rejected because copied JSON
would become a bearer. Choosing one global process-local registry was rejected
because zero-host restart recovery and multi-host claims require durable shared
truth.

### 11. Failure, concurrency, and live-surface proof gate activation

The implementation must prove:

- concurrent duplicate schedule ticks and event emissions issue one attempt;
- concurrent child enqueues cannot overspend parent or shared growth caps;
- branch ACL, branch version, soul version, binding generation, trigger
  generation, and daemon eligibility changes fence stale workers;
- crashes at every prepared/commit boundary converge without guessed authority;
- multi-host claim/reclaim never overlaps execution after a generation fence;
- legacy ambiguous rows remain held;
- dark-to-enforced rollout drains or holds every pre-authority queue row; and
- connector-created work survives restart and executes through the live
  chatbot surface with correct authorizer/executor provenance.

Unit and focused integration tests are supporting evidence. Final activation
also requires the project §14 concurrency/load proof, public canary checks, a
rendered chatbot conversation through the installed connector, and fresh
post-fix real-user evidence or an explicit `STATUS.md` watch item.

## Risks / Trade-offs

- **[More durable state and joins]** → Keep trigger/task rows lightweight,
  expose one bounded authority-store interface, and index logical keys,
  binding generations, and active attempts.
- **[Cross-store crash windows]** → Use prepared pairs, exact digests, monotonic
  generations, idempotent recovery, and fail-closed quarantine for third
  states.
- **[Revocation can hold previously valid automation]** → Surface typed
  non-secret hold reasons and provide authenticated reauthorization through
  existing connector actions.
- **[Live branch schedules are mutable]** → Pin each attempt to the freshly
  resolved exact version so mutation affects only future attempts.
- **[Stricter migration interrupts legacy work]** → Inventory first, classify
  deterministically, preserve rows for reauthorization, and never delete
  ambiguous work.
- **[Authority domains increase operational complexity]** → Use explicit names,
  immutable cross-references, one lock order, and tests proving that no domain
  is promoted into another.
- **[Local SQLite cannot be the final fleet coordinator]** → Keep storage behind
  the same transactional interface required by the active control-plane
  change; activation waits for the deployment-appropriate implementation.

## Migration Plan

1. **Inventory and classify:** enumerate schedules, subscriptions, current and
   legacy soul/`PROGRAM.md` loops, live/archive branch tasks, graph enqueue
   and live/frozen invoke paths, Request admission, goal/market producers and
   their subscriptions/contracts, historical retired wiki `file_bug`
   forward-triggers, the
   compiled built-in universe cycle, resume/recovery, daemon dispatchers,
   cloud workers, `_current_actor`, and direct runtime call sites. Record whether
   canonical principal, ACL, target, physical universe, source generation, and
   executor evidence is provable. Actor/environment strings are diagnostic
   only. Historical wiki forwards are classified only for handoff to
   `retire-cheat-loop` task 2.5 and are never candidates for binding or drain.
2. **Resolve live ownership:** obtain host approval for the PLAN reconciliation
   that assigns one production scheduling/claim mutation authority. Model,
   interface, inventory, and dark/test work may proceed beforehand; live
   persistence integration and rollout may not.
3. **Introduce dark schemas:** add binding/attempt stores, typed hold states,
   source references, provenance projections, uniqueness constraints, and
   recovery scanners. In dark mode, compute classifications and would-allow/
   would-deny decisions without authorizing execution or changing legacy
   behavior.
4. **Enable new issuance roots:** authenticated schedule/subscription,
   Request/producer tasks, universe creation/soul edits, root/resumed runs, and
   child derivation write bindings. New rows remain non-live until their
   end-to-end target and provider gates pass. Wiki filing is permanently
   excluded and remains filing-only.
5. **Backfill only provable work:** create bindings only where canonical durable
   records independently prove principal, universe ACL, exact target, source,
   and generation. Never infer from `owner_actor`, public visibility,
   `UNIVERSE_SERVER_USER`, queue possession, or daemon/worker identity.
   Explicitly exclude every `bug_investigation` row and trigger receipt,
   regardless of evidence; preserve them for the retirement migration.
6. **Hold ambiguous legacy work:** pause or mark
   `reauthorization_required`; preserve source definitions and history.
   Authenticated unpause/recreate/redeclare rotates a new binding. Legacy
   `PROGRAM.md` fallback cannot execute unattended.
7. **Drain the transport boundary:** before enabling epoch-2 graph/queue
   execution, link every pre-authority row to provable state, drain it under
   the explicitly bounded old public-only path, or hold it. Record a zero-
   unclassified invariant. Retired `bug_investigation` work is outside this
   drain and follows only `retire-cheat-loop` task 2.5.
8. **Enforce by source class:** schedule/subscription (after
   `demand-side-signals` sync), Request/producer task, soul loop, run resume,
   claimed task, graph enqueue/direct child, then distributed worker. Each
   class requires focused concurrency/failure proof and call-site closure
   before activation.
9. **Activate live:** only after `retire-cheat-loop` has completed task 2.5,
   synced its filing-only/retirement requirements, and archived, run full
   OpenSpec/test/lint gates, §14 load/concurrency
   evidence, canaries, rendered connector `ui-test`, and post-fix real-user
   observation.
10. **Rollback:** stop new attempt issuance and claims, leave sources/tasks
   pending or held, retain generations and audit history, and revoke in-flight
   claims. Rollback never re-enables actor/environment/public/queue fallbacks
   and never downgrades to legacy authority.

## Open Questions

- Which capability and production store own live schedule/task claim
  transactions after the file-lock versus epoch-2 contradiction is reconciled?
  This requires host-approved `PLAN.md` resolution before live integration; it
  does not block interface, inventory, dark-mode, model, or test work.
