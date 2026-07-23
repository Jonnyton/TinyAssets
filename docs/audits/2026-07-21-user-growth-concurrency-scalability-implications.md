# User Growth and Concurrent-User Scalability Implications

**Archival status (2026-07-23):** Historical research evidence, current only as
of `0bc841aa` plus the separately noted `92dd60c5` check. Re-check every code,
spec, deployment, capacity, and operational prescription against current
`origin/main` before using it. The Claude verdict remains **ADAPT**, not approval
or build authority.

**Status:** Codex initial research; architecture and capacity audit only. No
runtime build is authorized. Current implementation claims are based on
`0bc841aa` in the research worktree on 2026-07-21, with the subsequent
`origin/main` credential-isolation fix `92dd60c5` reviewed separately. External
platform claims were checked against the official sources linked below. The
required Claude review returned **ADAPT**; its provider-route corrections are
folded in and the durable review is adjacent to this report. This remains
planning research, not implementation authority.

**Research constraint (2026-07-21; pending PLAN ratification):** TinyAssets does
not provide execution compute or model quota. Every user run uses
requester-authorized BYOC/BYOM or an explicitly accepted market offer.
Founder/maintainer Claude and OpenAI subscriptions, rate limits, credentials,
hardware, and billing are owner-scoped and MUST NOT be used by other users or
as a fallback.

## Executive answer

**Does the architecture scale to user growth and concurrent users?**

| Layer | Answer today | Why |
|---|---|---|
| Product/domain model | **Yes, conceptually** | Tenant/owner boundaries, immutable versions, leases, gates, receipts, daemon capacity, and commons artifacts are the right units |
| Target control/data-plane design | **Yes, conditionally** | Stateless edge + transactional authority + durable queue + sharded coordination + BYOC/market executors is a clean horizontal shape |
| Current public deployment | **No** | An auto-scaling Cloudflare proxy feeds one MCP origin/process and one shared local volume; no edge rate limiting or origin failover |
| Current storage/runtime | **No** | Correctness relies on process locks, file locks, SQLite/files, process singletons, and in-memory event state that cannot span replicas |
| Thousands-concurrent proof | **No evidence yet** | The target design contains §14 scenarios, but the repository has not demonstrated the complete concurrent-user/load envelope |

The right conclusion is neither “rewrite it all” nor “it already scales.” The
domain shape is good. The current deployment is a single-host proving ground.
Before growth, authoritative multi-user state must move behind a horizontally
reachable transaction boundary, asynchronous work must enter a durable queue,
coordination must shard by its natural entity, and execution must stay on
requester BYOC/BYOM or an accepted market host.

The market helps scale **execution supply**; it does not scale the control plane
by itself. More hosts cannot repair one hot MCP origin, one filesystem queue,
one global scheduler, or an unbounded tenant.

## What “concurrent users” actually means

Daily active users are not a capacity model. TinyAssets must measure separate
concurrency classes because they stress different resources:

| Concurrency class | Dominant pressure |
|---|---|
| MCP handshakes and read calls | gateway connections, auth/JWT verification, serialization, storage reads |
| Long-lived SSE streams | open connections, reconnect storms, durable cursor recovery |
| Concurrent authors on different universes | tenant-indexed writes and broadcast fan-out |
| Concurrent authors on one hot universe/node | optimistic conflicts, ordering, merge/fork UX |
| Webhook/poll event bursts | ingress admission, queue backlog, dedupe, payload storage |
| Simultaneous graph runs | task creation, checkpoints, run-event volume, provider/host capacity |
| Daemon fleet claims and heartbeats | matching shards, leases, fencing, liveness churn |
| Market bids/claims/settlements | transactional hot rows, escrow/capacity conservation, fairness |
| Commons discovery spikes | cache/index/materialized-view reads, not transactional writes |
| Autoresearch/fan-out | budget reservation, bounded expansion, executor availability, result aggregation |

Capacity planning must state the mix: users connected, calls per user, write
ratio, stream duration, workflow fan-out, event burstiness, daemon count,
provider latency, payload size, and hot-key distribution.

## Current deployment reality

### Edge scales; the origin does not

`deploy/cloudflare-worker/worker.js` is a streaming pass-through for `/mcp`.
Cloudflare Workers can scale request handling globally, and the proxy correctly
preserves SSE bodies and MCP headers. But its README explicitly records:

- no rate limiting in the Worker;
- one tunnel origin;
- no caching for per-session MCP traffic; and
- multi-region failover as future work.

Every public call therefore converges on `mcp.tinyassets.io`, then one
`tinyassets-daemon` container running `python -m tinyassets.universe_server`.
An elastic proxy in front of a singleton origin is not horizontal scaling.

### One shared host/volume is the authority

`deploy/compose.yml` mounts one `tinyassets-data` volume at `/data`. The main MCP
process and four cloud-worker containers share files, provider auth homes, and
file-locked task state. This can coordinate a few processes on one machine, but
the same volume and process locks are not a multi-region or multi-origin
authority.

The deployment comments explicitly rely on:

- `branch_tasks.claim_task` file locking;
- a serialized flock around a shared Codex auth home; and
- one daemon container plus fixed worker replicas.

This is a valid single-host implementation, not a concurrent-user platform
boundary.

### Process-local correctness seams block replicas

Examples already found in the Zapier/concurrency audit:

- `_HOME_MATERIALIZE_LOCK` in `tinyassets/api/status.py` says a thread lock is
  sufficient because the daemon is one Uvicorn process. Multiple origins can
  race unless creation is a storage-level unique/upsert transaction.
- `tinyassets/scheduler.py` has a process-global singleton, an in-memory event
  queue, and no production startup caller.
- event delivery marks before launch and can lose work; schedule fire records
  after launch and can duplicate work.
- filesystem task claims coordinate same-volume workers only.
- SQLite-backed surfaces ultimately serialize writers. SQLite WAL improves
  reader/writer overlap but officially permits one writer and requires all
  processes to share one host; it is unsuitable as shared network authority.
- several user/market APIs open SQLite connections per call, so write
  contention and `database is locked` behavior need direct measurement even on
  one host.
- declared node retry policy is not applied by graph execution.
- graph runs use a fixed top-level worker pool plus a separate child pool;
  executor saturation/admission and checkpoint contention are not load-proven.
- there is no tenant-fair run admission: one tenant can occupy the process-wide
  top-level slots, while branch concurrency can be unbounded when no budget is
  supplied.
- the three mounted FastMCP surfaces keep session ownership in process-local
  dictionaries with no configured idle expiry or durable event store; restart
  breaks sessions, abandoned sessions can accumulate, and replicas require
  sticky routing without solving restart recovery.
- universe, wiki, account, and directory list paths are unpaginated and perform
  full scans or per-row follow-up work, so catalog growth increases latency,
  payload size, and browser graph work linearly.
- WorkOS JWKS resolution and several file/SQLite/provider operations remain
  synchronous on request paths, creating event-loop and worker saturation risk.
- daemon task leases default to 1,800 seconds while worker heartbeats are much
  shorter, so a hard crash can leave user work unavailable for roughly thirty
  minutes unless independent lease renewal/reclaim is redesigned and tested.
- the paid market is pre-launch/file-Git backed; its pure matching and
  conservation tests do not prove concurrent live escrow or settlement.
- commons `discover_nodes` scale exists as detailed design but has no canonical
  OpenSpec, public implementation, or one-million-node load evidence.

Any correctness property held only by Python memory, a local file lock, or one
host's SQLite journal disappears when a load balancer adds a second origin.

### Canonical storage truth is unresolved

The full-platform target describes Postgres/Supabase as canonical public
authority and GitHub as an export sink. Another PLAN line leaves the choice
unresolved, while the active brain canonical-store change keeps file bundles
and Git snapshots authoritative for that data. This may ultimately be a valid
data-class split—public multi-user coordination in Postgres, private host brain
state in files—but it is not currently stated cleanly enough to scale safely.

Before migration, every state class needs one named authority: public catalog,
private instance content, run/checkpoint, task/lease, connection grant,
market/ledger, brain memory, and blob. Dual-write without a named winner creates
split-brain under concurrency.

### Compute isolation is not yet a scale-safe assumption

The production compose deliberately shares maintainer Codex and Claude auth
homes among its fixed cloud workers. That is acceptable only for the
maintainer's explicitly owner-scoped workloads. It cannot be the public-user
execution pool.

The audited research HEAD predates `origin/main` commit `92dd60c5`. That commit
closes one observed fail-open path after a live second-identity test showed
`converse` and `run_graph` consuming the host subscription. It does not by
itself prove the complete invariant: strict provider allowlists and auditable
provider/capacity receipts remain open, and the direct graph path needs a
focused regression proving that provider dispatch always receives the
requester's universe context.

The required Claude review made the residual gap concrete:

- `UniverseConfig.allowed_providers` is defined in `tinyassets/config.py` and
  enforced by `tinyassets/providers/router.py`, but repository search finds no
  production write path. The fail-closed allowlist is therefore dormant.
- `set_engine` persists `engine_source=self_hosted_endpoint` and
  `engine_endpoint` in `tinyassets/api/universe.py`, but the provider router
  never reads `engine_endpoint`; the advertised self-hosted BYOC route is not an
  executable route today.
- `ollama-local` is inert in the current container because Ollama is absent, but
  its mandatory fallback becomes live on the Tier-2/Tier-3 self-hosted installs
  that do have Ollama. It therefore still violates owner-scoped authority for a
  different user's work.

These are immediate truth/alignment blockers, not scale optimizations. A route
cannot be load-tested as isolated BYOC until configuration writes an enforceable
authority-bound allowlist, the endpoint is actually consumed, and receipts prove
which owner's compute/model access ran every attempt.

There is a current truth conflict to resolve. The canonical provider-routing
spec requires every role chain to terminate at a host-local model, while the
runtime fallback chain can reach host providers and subprocess environments
can inherit shared `CODEX_HOME`/`CLAUDE_CONFIG_DIR` when no universe-scoped auth
is supplied. That contradicts the host's 2026-07-21 boundary. The active R2-1
credential fail-closed lane plus an OpenSpec provider-routing alignment must
make absence of requester/market authority a held state, not host fallback.

Every execution on behalf of a user--interactive, scheduled, event-triggered,
autonomous, retried, resumed, child, or autoresearch--needs a complete authority
bundle. BYOC means requester-owned compute; BYOM means requester-owned gated
model/API access. They are independent dimensions, not interchangeable routes:

```text
compute_authority = requester_compute | accepted_market_compute_offer
model_authority = none_required | requester_model | accepted_market_model_offer
```

An accepted offer states which dimension(s) it covers. Open-weight model use
may set `model_authority=none_required`, but still requires compute authority.
Ordinary TinyAssets control-plane work is platform-operated; inference,
training, tuning, fabrication, and user task execution are not. The task, run,
attempt, lease, effect, receipt, and provider route must all carry the same
tenant and authority bundle. A missing, revoked, or exhausted required dimension
yields `pending/held`, never an environment-variable fallback or maintainer
subscription.

Capacity ownership also scopes operational state. Provider quotas, cooldowns,
failure scores, spend caps, and admission cannot be keyed only by provider name
in process-global memory; otherwise one tenant can throttle or reroute another.
Each completed or rejected run needs a receipt binding actor, universe,
provider/model, capacity owner or accepted market offer, spend/token cap, and
outcome.

## Clean scalable target

```text
Chatbot / MCP / webhook clients
              |
Stateless authenticated edge
  auth, schema, tenant, deadline, coarse rate limits
              |
Transactional state authority -------- Object/blob storage
  RLS/ownership, graph/run/task,         public artifacts or
  grants, leases, market, ledger,        owner-controlled private refs
  idempotency, outbox, receipts
              |
Durable at-least-once queues
  IDs and routing metadata, not private payloads/secrets
              |
Tenant-fair lease broker
         /                         \
requester-owned compute      accepted market host
and required model access    with declared compute/model coverage
```

This is a logical contract, not a mandatory vendor stack. Managed Postgres,
Supabase Realtime, Cloudflare Queues, and Durable Objects demonstrate useful
pieces, but TinyAssets should preserve a portable boundary.

### 1. Stateless edge

The public edge should authenticate, validate protocol/schema/size/deadline,
bind the tenant, apply abuse shedding, assign/validate `client_request_id`, and
route. It should not own workflow truth or execution.

MCP sessions are a transport concern, not a correctness store. The current
2025-11-25 MCP specification permits server session IDs; the current draft
frontier removes protocol-level sessions in favor of explicit durable handles.
TinyAssets can support present clients while keeping cross-call state in
explicit durable run/universe/task handles, which allows any healthy gateway
replica to serve the next call.

Disconnect is not cancellation. SSE recovery reads a durable event cursor;
explicit cancellation changes durable task/run state.

### 2. Transactional authority

A Postgres-compatible authority is the clean initial fit for public and
multi-user state:

- tenant/user identity, ownership, and grants;
- public concept catalog and immutable workflow versions;
- runs, tasks, leases, fences, attempts, receipts, and outbox;
- accepted offers, capacity locks, escrow, settlement, and disputes;
- durable schedules/subscriptions and event identities;
- exact admission/budget constraints.

Use tenant-bearing primary/secondary indexes, RLS, optimistic version columns,
and short transactions. Serverless/elastic gateways need transaction pooling;
long-lived services use bounded pools. Views and materialized rankings are
read projections, never settlement authority.

Do not partition per customer initially. PostgreSQL warns that too many
partitions add planning/memory cost. Measure first; likely first partitions are
time buckets for append-only events/receipts, then a bounded tenant hash only if
measured access patterns require it.

### 3. Transactional outbox plus durable queue

The database transaction writes authoritative task/event state and an outbox
row. A publisher sends an ID-only envelope to a durable queue and marks the
outbox delivered; a reconciler closes either crash window.

Queue delivery is at-least-once and unordered. That is the honest scalable
default. Workers claim by durable task ID plus lease/fence, deduplicate, and
acknowledge only after durable state/receipt. Delays, bounded retries,
visibility timeouts, and a user-visible dead-letter/`needs_review` path absorb
backpressure without holding an MCP request open.

Queue order never defines workflow order. Graph dependencies and durable state
do.

### 4. Shard by the atom of coordination

Cloudflare's Durable Object guidance captures the general rule: one logical
coordination entity per actor/object, never one global singleton. TinyAssets can
implement the same rule with database transactions, actors, or both.

| Surface | Initial coordination/shard key |
|---|---|
| Collaboration ordering/conflict | `universe_id` or `branch_id` |
| External event dedupe | `(tenant_id, subscription_id, source_event_id)` |
| User request idempotency | `(tenant_id, client_request_id)` |
| Workflow step/effect | `(run_id, step_id, effect_kind)` |
| Dispatch discovery | `(capability_class, privacy_class, trust_class, region?)` |
| Fair scheduling/admission | `tenant_id` |
| Market capacity/settlement | `accepted_offer_id`, with discovery grouped by market key |
| Realtime collaboration | per-universe channels |
| Daemon request push | per-capability channels |
| Commons search/ranking | asynchronous indexed/materialized projection |

A single hot universe or market key still has a finite serial coordination
rate. That is correct: conflicting writes cannot all be simultaneous. Scale the
system across many keys, and handle a hot key with optimistic CAS, bounded
queues, fork/merge, batching, and truthful overload—not unsafe parallel writes.

Durable Objects may later coordinate a measured hot room/tenant. Do not make
them mandatory or create one global object. Their official limit remains
single-threaded per object; horizontal scale comes from many objects.

### 5. Tenant-fair lease broker and BYOC/market data plane

Executors connect outbound and request work only when they have a free slot.
Untrusted hosts never receive raw queue credentials. A broker returns a
short-lived, task-scoped lease containing only authorized artifact references,
capability/privacy/trust requirements, and the execution authority.

- Requester-owned compute and any required gated model access can run only on
  that requester's authorized routes.
- Market work can run only on a host covered by the accepted offer.
- Provider substitution is allowed only when already authorized by the
  requester or offer policy.
- Private content stays on an authorized host or owner-controlled transfer/CAS;
  public queues/realtime carry opaque IDs and bounded metadata.
- Host disappearance requeues only within the same authority envelope.
- If no compatible capacity exists, the queue remains truthful; the platform
  never consumes founder quota.

Scale comes from more independent hosts and fair admission, not a central
platform model account.

### 6. Realtime is notification, not authority

Use per-universe and per-capability channels. Broadcast says “state changed”;
clients re-read authoritative state after reconnect. Presence is ephemeral and
may optimize collaboration/host liveness, but it must not settle money, grant a
lease, or prove a workflow effect.

Supabase's current official limits show why budgets must be explicit: plan
limits cap concurrent connections, joins, messages/second, and payload sizes,
and clients can be disconnected under excess throughput. Its cluster can scale
far beyond one project limit, but a purchased quota is not a TinyAssets SLO.

## Admission, fairness, and noisy-neighbor isolation

Backpressure should be layered:

1. **Edge:** approximate per-tenant/user/route limits, IP only a secondary abuse
   signal.
2. **Transactional admission:** exact outstanding-job, queued-byte, fan-out,
   grant, accepted-offer capacity, budget, escrow, and privacy constraints.
3. **Queue:** separate coarse workload/trust classes, bounded consumer
   concurrency, retry delay, backlog/oldest-age alarms, DLQ.
4. **Lease broker:** dispatch only into a reported free slot; tenant-aware fair
   scheduling prevents a whale from monopolizing supply.
5. **Provider/destination:** per-grant and per-upstream token buckets, respect
   `Retry-After`, circuit-break repeated failure.
6. **User-visible truth:** distinguish `queued`, `no_authorized_executor`,
   `capacity_unavailable`, `admission_rejected`, and `needs_review`.

Hard per-tenant bounds are needed for active MCP streams, outstanding tasks,
workflow depth/fan-out, schedules, event rate, payload/blob bytes, connection
grants, host leases, market exposure, and unprompted action/spend.

The scheduler must optimize fairness, not just FIFO or highest price. Track per-
tenant wait-time and throughput distributions, dominant-tenant share,
starvation, and priority inversion.

## Failure semantics under concurrency

| Failure | Required behavior |
|---|---|
| Duplicate MCP POST | Return existing run/task by tenant-scoped client request ID |
| Queue duplicate | Claim by task ID + lease epoch; dedupe state/effect |
| Worker crash before effect | Lease expires and becomes eligible within the same authority envelope |
| Crash/timeout after effect | Reconcile through provider idempotency/status; otherwise `unknown/needs_review`, never blind retry |
| Slow/partitioned worker acts after lease expiry | Every state transition presents the current epoch; reserve a deterministic effect idempotency key under a live fence immediately before the effect; stale epochs cannot issue or commit; a replacement reconciles an unknown prior attempt before retrying |
| Database serialization/deadlock | Bounded jittered retry of the whole transaction; no external effect inside transaction |
| Gateway/SSE disconnect | Resume from durable cursor; do not cancel implicitly |
| Provider `429`/outage | Delay/circuit-break that authorized route; substitute only if pre-authorized |
| Host disappears | Requeue to an authority-compatible host or wait; host-specific offer needs new acceptance |
| Queue backlog near retention | Stop admission and recreate delivery from canonical outbox/task state |
| Realtime loss | Re-read canonical state; notification loss never loses work |
| Hot tenant/universe | Enforce bounds/CAS/fork/queue; other tenants remain within SLO |
| Missing BYOC/market authority | `no_authorized_executor`; zero founder credential/quota use |

## Existing §14 targets versus proof

The full-platform architecture already recognized that all earlier testing was
one daemon plus one universe on one laptop. Its §14/§25/§32 target scenarios
include:

- 1,000 concurrent Tier-1 subscribers on one hot universe, no missed events,
  broadcast lag under two seconds;
- 500 daemons during 1,000 requests in five minutes, claim/dispatch p99 under
  three seconds and no lost requests;
- 200 concurrent cascade readers with no lock thrash;
- 1,000 presence heartbeats/minute without churn;
- 100 requests fan-out by ten (1,000 claims), p99 under three seconds;
- 100 autoresearch requests × 100 runs (10,000 iteration rows), with no claim,
  dedupe, or budget race; and
- automated recovery/failover rehearsals.

Those are design targets, not current evidence. Track J's k6/synthetic-fleet/
Supabase load harness is not implemented in current CI. The present repo and
deployment do not justify a “thousands concurrent” claim until an isolated
staging stack runs the complete proof and publishes raw results, environment,
versions, resource sizes, date, and failure distribution.

### Fresh repository evidence

On 2026-07-21 at `0bc841aa`, a focused local concurrency/race set including
the slow two-clone bid race produced **114 passed** on Windows/Python 3.14.3.
A broader relevant run produced **146 passed, 11 failed**; the failures were
dispatcher submission/list/cancel tests hitting `universe_loop_not_declared`,
consistent with fixture drift but not separately root-caused in this research
lane. This is useful correctness evidence, not a capacity envelope.

Reproduction commands (same worktree; no environment overrides):

```powershell
python -m pytest -q tests/test_multi_tenant_isolation.py tests/test_node_enqueue_concurrency.py tests/test_concurrency_budget.py tests/test_scheduler.py tests/test_scheduler_edge_cases.py tests/test_match_scale.py tests/test_dispatcher_queue.py::test_file_lock_race tests/test_dispatcher_queue.py::test_branch_tasks_json_survives_controller_lifecycle tests/test_node_bid_claim_stress.py
python -m pytest -q tests/test_multi_tenant_isolation.py tests/test_node_enqueue_concurrency.py tests/test_concurrency_budget.py tests/test_scheduler.py tests/test_scheduler_edge_cases.py tests/test_match_scale.py tests/test_dispatcher_queue.py
```

No CI workflow currently runs Track J, k6, a synthetic daemon fleet, or a
Postgres/Supabase load environment. Existing CI covers packaging, fresh-clone
smoke, Worker unit behavior, and uptime canaries. The public MCP latency probe
records elapsed time but has no gating threshold.

Other proof mismatches relevant to scale remain:

- PLAN describes a weekly DR drill, while the current DR workflow is manual;
- the daemon runtime spec says at-most-once event delivery but titles its
  scenario exactly-once;
- no canonical OpenSpec currently defines p95/p99, throughput, concurrent
  sessions, backpressure, or a verified capacity envelope.

## Unapproved 10k-DAU workload hypothesis

The existing full-platform design estimates roughly 2,000 simultaneous Tier-1
users plus 400 online daemons at 10k DAU. The following is an **unapproved
workload hypothesis**, not a current capability, approved SLO, or derived
capacity result. The concurrency counts inherit or extend the full-platform
design scenarios; the proposed latency/throughput values are deliberately
testable starting hypotheses. Revise them after the current-system baseline:

| Surface | Unapproved gate hypothesis |
|---|---|
| Chatbot MCP | 2,500 concurrent clients; 100 control-plane tool calls/s steady and 250/s burst; p95 read ≤750 ms, p99 ≤2 s; explicit overload, zero tenant leakage; model execution excluded |
| Realtime/hot universe | 1,000 subscribers; p99 lag ≤2 s; 50 conflicting writers produce explicit CAS conflicts, never lost writes |
| Webhook ingress | 100 events/s steady, 500/s one-minute burst; p99 durable ack ≤1 s; zero loss; deterministic dedupe; bounded payload and per-tenant quota |
| Graph control plane | 200 active and 1,000 queued runs; dispatch p99 ≤3 s; cancellation observed ≤5 s; queues bounded; execution authority mandatory |
| Scheduler | 10,000 active schedules, 1,000 due/minute; two-replica crash matrix; one durable dispatch identity per occurrence; p99 skew ≤30 s |
| Daemon leases | 500 online daemons, 1,000 simultaneous claims; p99 claim ≤3 s; one fenced winner; hard-kill reclaim ≤120 s |
| Storage | 2,500 readers, 500 reads/s and 100 writes/s; 500 concurrent universe births; 50 hot-row editors; no lost/cross-tenant write |
| Paid market | 1,000 requests/5 min, 1,000 claim attempts, 100 concurrent settlements; exact conservation; zero double capacity/escrow/settlement |
| Commons discovery | Seed 1 million nodes; 200 queries/s, 1,000 concurrent callers; 20-result/≤40 KiB response; p95 ≤500 ms; no private-field leak |

Basis is explicit so none of these numbers can masquerade as measurement:

| Surface | Basis |
|---|---|
| Chatbot MCP | Extends the design's roughly 2,000 connected users; rates and latency are proposed for baseline calibration |
| Realtime/hot universe | Subscriber/lag target inherited from section 14; conflicting-writer mix proposed |
| Webhook ingress | New proposed workload because no current ingress implementation/evidence exists |
| Graph control plane | Dispatch latency/fan-out informed by section 14; active/queued/cancel mix proposed |
| Scheduler | New proposed workload for the unproven scheduler surface |
| Daemon leases | Daemon/claim/latency inherited from section 14; reclaim target proposed |
| Storage | Connected-user scale inherited; transaction mix proposed |
| Paid market | Request/daemon load inherited from section 14; settlement concurrency proposed |
| Commons discovery | One-million-node/response shape inherited; caller/rate/latency proposed |

Each scenario runs steady state, a 2× burst, and failure injection. If baseline
measurements show these budgets are unrealistic or wasteful, change the budget
before changing architecture. Vendor limits are guardrails, not acceptance.

## Required capacity and isolation test suite

### Baseline packet

Every test pins commit/image/config, gateway replicas, database/queue/realtime
tiers, region, connection pools, payload distribution, workflow graph, daemon
mix, BYOC/market simulators, and observability sampling. It reports p50/p95/p99,
error/timeout/retry rate, saturation, queue age, lock wait, and per-tenant
fairness. Averages are insufficient.

No load test uses founder Claude/OpenAI credentials. Provider execution uses
deterministic fakes, requester-scoped test accounts, or explicitly budgeted
market sandboxes. After the test, credential/provider receipts must prove zero
cross-tenant or founder-resource use.

### Scenarios

1. **MCP connection storm:** handshakes, read calls, writes, SSE streams,
   disconnect/reconnect, duplicate POST, and explicit cancellation across many
   tenants. Thresholds must be approved; measure origin and pool saturation.
2. **Hot-universe collaboration:** the existing 1,000-subscriber target plus 50
   conflicting writers; assert no silent lost update and bounded conflict UX.
3. **Webhook burst:** duplicate, reordered, oversized, invalid-signature, and
   valid events; assert persistence-before-ack, dedupe, backlog recovery, and
   tenant isolation.
4. **Daemon claim storm:** existing 500-daemon target plus churn, expired
   leases, reconnect, and one malicious/slow host.
5. **Noisy neighbor:** one tenant consumes its full queue/fan-out/rate/budget
   allowance while ordinary tenants remain inside their accepted SLO.
6. **Market conservation:** concurrent bid/accept/capacity-lock/settlement and
   duplicate callbacks; assert no double-sell, overdraw, or cross-tenant access.
7. **Crash matrix:** kill gateway, publisher, consumer, broker, executor, and
   database connections before/after each durable boundary.
8. **Provider pressure:** `429`, long latency, partial stream, quota exhaustion,
   and provider outage; assert per-authority circuit-break and no founder
   fallback.
9. **Backlog and recovery:** pause consumers, grow queue, resume, exercise DLQ
   and reconciliation without message loss or retry avalanche.
10. **Storage growth:** large append-only run/event/receipt history, RLS-indexed
    reads, vacuum/WAL/partition behavior, export/deletion, and blob quotas.
11. **No-host mode:** zero executors online while authoring/discovery remain
    healthy and executable work truthfully queues/holds.
12. **Multi-origin failover:** add/remove gateway replicas and fail the primary
    origin; no process-local lock/session may affect correctness.
13. **Mixed-tenant authority isolation:** mix requester-owned compute, gated
    model grants, open-weight models, and accepted market routes while forging
    task/offer/lease IDs and revoking or exhausting grants. Inspect subprocess
    environments, logs, receipts, and billing identities; assert zero
    cross-tenant access and zero founder/maintainer resource use.
14. **Moderation and abuse under load:** flood reports, reconnects, malicious
    payloads, and auth/rate-limit bypass attempts while ordinary tenants remain
    inside the accepted SLO. Assert bounded queues, preserved evidence,
    enforceable moderation state, and no privilege or tenant-boundary bypass.

### Measurements that decide scale work

- MCP arrival/concurrency per tenant/tool, time-to-first-event, stream count,
  reconnect/resume, duplicate rate;
- database pool usage, query/transaction latency, lock wait,
  serialization/deadlock retry, hot rows/indexes, RLS cost, WAL/vacuum lag;
- queue ingress/egress, oldest age, backlog bytes/count, retries, duplicates,
  lease expiry, DLQ;
- per-tenant throughput/wait distribution, starvation and dominant share;
- capacity by capability/privacy/trust class, lease churn, host loss, provider
  latency/429, BYOC availability;
- effect reconciliation, reservation-versus-actual cost, settlement latency,
  duplicate-prevention;
- realtime connection/message/join quota, lag, reconnect storm, cursor resume;
- privacy/credential leakage across queue envelopes, logs, traces, artifacts,
  subprocess environments, and receipts.

Measure before optimizing. A new cache, partition, Durable Object, broker, or
queue shard requires a trace showing the bottleneck and a before/after result.

## User-growth operating envelope

Growth should be managed by explicit capacity states, not DAU milestones:

- **green:** all SLOs have margin; oldest queue age and provider capacity are
  stable;
- **yellow:** a quota/pool/queue/hot key approaches a configured ceiling;
  reduce fan-out, shed low-priority admission, or add authorized market supply;
- **red:** new executable work is rejected/held before durability or privacy is
  compromised; authoring/read surfaces remain available;
- **unknown:** missing telemetry or unrun load proof is itself non-green.

Each deployment publishes the maximum *verified* envelope: concurrent MCP
clients, streams, write rate, event burst, active runs, daemon claims, market
transactions, payload size, and tested fault conditions. Marketing and chatbot
status must not claim more.

User growth changes economics but not authority. If requester/market capacity
lags demand, price and wait time rise and jobs queue. The platform may help
discover supply; it does not donate founder quota.

## Adopt / adapt / avoid

### Adopt

- stateless authenticated edge and explicit durable handles;
- transactional public-state authority with tenant RLS/indexes;
- transactional outbox plus at-least-once durable queue;
- capacity-driven outbound executor pulls with leases/fences;
- per-universe/per-capability channels and entity-level coordination;
- tenant-fair admission, quotas, backpressure, DLQ, and truthful states;
- append-only receipts and separate expiring private payloads;
- published load envelopes and capacity dashboards.

### Adapt

- Supabase/Postgres/Realtime as an initial portable implementation, not a
  permanent vendor dependency or an unmeasured promise;
- Cloudflare Durable Objects as an optional measured hot-entity coordinator,
  not a global database or required primitive;
- Cloudflare Queues as delivery machinery, never workflow/economic truth;
- Temporal's durable-history, activity, heartbeat, worker-version, and fairness
  patterns only if home-grown workflow recovery becomes the measured dominant
  burden;
- existing file/SQLite stores as daemon-local private state and test fixtures,
  not shared control-plane authority.

### Avoid

- one MCP origin, scheduler, actor, queue, or Durable Object for the world;
- horizontally replicating code whose correctness is process-memory/file-lock
  based;
- shared/network SQLite;
- poll-all daemon dispatch;
- queue order as workflow order;
- per-tenant database partitions/queues before measurement;
- unbounded graph fan-out, streams, payloads, retries, or market exposure;
- secrets/private payloads in public queues, realtime, logs, or traces;
- automatic provider substitution outside the execution authority;
- any platform/founder compute, model quota, credential, or billing fallback;
- “exactly once” external-effect claims without provider proof/reconciliation;
- declaring scale from vendor marketing limits or one synthetic average.

## Recommended sequence

1. Treat the current deployment as single-origin/single-host and publish that
   truthful envelope.
2. Resolve the boundary-layer effect guarantee and scheduler delivery
   contradictions before introducing retry or replicas.
3. Align provider-routing OpenSpec with the host-approved PLAN boundary, land
   R2-1 fail-closed credentials, make execution authority mandatory, and prove
   no cross-tenant/founder provider fallback.
4. Establish the load harness and baseline the current system before selecting
   a storage/queue migration.
5. Move multi-user authority to transactional storage with unique/CAS
   invariants; keep blobs and private content in their proper stores.
6. Add transactional outbox, durable ingress/queue, and tenant-fair lease
   broker.
7. Make the MCP gateway horizontally replaceable: durable handles, pooled
   storage, no process-only correctness.
8. Shard realtime/dispatch by universe/capability and add admission/backpressure.
9. Run §14 plus the expanded fault/isolation suite; publish raw evidence.
10. Scale or partition only the measured bottleneck, then rerun the same packet.

## Source provenance

Primary TinyAssets evidence:

- `PLAN.md` Daemon Platform, Providers, API & MCP Interface, Uptime & Alarms;
- `docs/design-notes/2026-04-18-full-platform-architecture.md` §§2, 3, 5,
  14, 25, and 32;
- `deploy/compose.yml`;
- `deploy/cloudflare-worker/worker.js` and `README.md`;
- `tinyassets/universe_server.py`;
- `tinyassets/api/status.py`;
- `tinyassets/scheduler.py`;
- `tinyassets/branch_tasks.py`;
- `tinyassets/idempotency.py`;
- `openspec/specs/daemon-runtime-and-dispatch/spec.md`;
- `openspec/specs/graph-execution-substrate/spec.md`;
- `openspec/specs/boundary-layer/spec.md`;
- `openspec/specs/identity-auth-and-access-control/spec.md`;
- `openspec/specs/live-mcp-connector-surface/spec.md`.

Current official external references:

- Cloudflare Workers limits:
  <https://developers.cloudflare.com/workers/platform/limits/>
- Cloudflare Durable Object rules and limits:
  <https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/>
  and
  <https://developers.cloudflare.com/durable-objects/platform/limits/>
- Cloudflare Queues delivery, batching/retries, and pull leases:
  <https://developers.cloudflare.com/queues/reference/delivery-guarantees/>,
  <https://developers.cloudflare.com/queues/configuration/batching-retries/>,
  and
  <https://developers.cloudflare.com/queues/configuration/pull-consumers/>
- SQLite WAL concurrency:
  <https://sqlite.org/wal.html>
- PostgreSQL MVCC, serialization retry, row security, and partitioning:
  <https://www.postgresql.org/docs/current/mvcc-intro.html>,
  <https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html>,
  <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>, and
  <https://www.postgresql.org/docs/current/ddl-partitioning.html>
- Supabase connection pooling, Realtime limits, RLS performance, and production
  load-testing guidance:
  <https://supabase.com/docs/guides/database/connecting-to-postgres>,
  <https://supabase.com/docs/guides/realtime/limits>,
  <https://supabase.com/docs/guides/database/postgres/row-level-security>, and
  <https://supabase.com/docs/guides/deployment/going-into-prod>
- MCP Streamable HTTP, authorization, and current draft sessionless direction:
  <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>,
  <https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization>,
  and
  <https://modelcontextprotocol.io/specification/draft/changelog>.
