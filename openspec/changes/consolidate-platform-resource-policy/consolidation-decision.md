# Decision-ready consolidation recommendation

Current completion scope is extended by the September 8 owner directive in
[goal-completion-contract.md](goal-completion-contract.md): full deployed limits
simplification plus five app-reported capability gaps, with explicit rendered
webapp-agent confirmation that the gaps are closed. The historical design-only
statements below describe the recommendation stage, not a withdrawal of the
owner's subsequent implementation/deployment authorization.

2026-09-08 PDT / September 9 UTC. **Design only; not approved runtime policy.**
The workspace-start cap removal and storage sampler are shipped. Neither is the
requested end state. This pass changes no code, PLAN, ledger, threshold, workflow,
test run or production state. It does not reopen the sampler or its reviews.

## Recommended end state

One per-universe resource policy, presented as three dimensions, with one
authoritative decision at each real dependency boundary:

1. **Concurrent use:** work currently holding a real scarce resource. Admission
   waits/refuses for actual capacity, and completion/cancellation/crash recovery
   releases it. Sleeping, queued or completed work is not a live allocation.
   An exclusive repository/generation lock protects data; it is not a second
   customer concurrency allowance. Nested provider work retains progress headroom.
2. **Activity over time:** a consistent rolling fair-use envelope for work the
   platform actually admits, independent of how the user divides it into nodes
   and runs. Keep operations, held time and transferred bytes in their native
   units; do not add them or invent weighted credits. Count a real dependency
   activation once at its existing identity/authority boundary, not again for
   every parent graph, wrapper and receipt read. A new physical retry may consume
   resources; replaying an existing receipt or refusing before launch does not
   prove a new physical activation. This needs coverage/settlement proof, not
   renaming current mixed counters to "actions".
3. **Retained space:** attributable data still present, plus separately identified
   pending allocations. It does not reset hourly and deletion must actually free
   the bytes before capacity is returned. Traffic already transferred is a
   different resource. Partial observations are not admission authority.

Three dimensions do **not** mean three universal scalar constants. A provider
process and a git transfer cannot safely be summed as equal memory consumers.
Native dependency guards remain beneath the policy, but arbitrary graph-shape and
duplicated category allowances are retired as their coverage is replaced. The
observable difference must be fewer policy refusals, not a reorganized dashboard.

Keep the existing universe scope initially. No cross-universe account pooling,
pricing or new storage authority is implied. User-selected providers and their
owner-authorized invocation/token/cost bounds stay separate from platform capacity;
available TinyAssets capacity never grants more upstream spending authority.

## What source establishes, and what it does not

Verified with scoped `docview.py lines` and `rg -n` reads of the shipped source.
These are source-contract proofs, not new performance or concurrency experiments.

| Control | Evidence | Classification / disposition |
|---|---|---|
| Scope, credentials, receipt generation/expiry and delegated provider bounds | `storage/provider_work_authority.py:780-814` requires exact binding, identity and budget containment | Authority invariant. Never consolidate this into a platform usage allowance or infer unlimited provider entitlement. |
| Provider live counter and nested reserve | `provider_admission.py:117-166` acquires under a condition; outer calls leave child headroom | Real resource/deadlock safeguard. The mechanism is technical; six total/one reserved is sizing, not proven optimal current capacity. Process-local is not host-global. |
| Workspace locks and byte reservations | `workspace_pool.py::_acquire_lock`, `admit`, `reconcile_bytes`; `effectors/workspace.py::_pool_db` | Ownership/data integrity and real resource protection. Same-run reentrancy and universe-local DBs prevent claiming a global concurrency allowance today. Keep until the actual shared scope is enforced. |
| Engine mutation subcap | `engine_admissions.py:183-194, 229-235` derives two-thirds of total specifically to reserve admissions for runs in the same universe | Product/workflow-allocation policy. It partitions one universe's finite allowance between its own strategies; it is not an independent memory, network or disk boundary. Candidate for actual retirement. |
| Write-run and total admission caps | `engine_admissions.py:66-68, 219-242` counts rows, with current 300/900 values | Coarse activity/abuse policy, not measurements of compute cost. Atomic admission is technical; category ceilings are choices. Keep the total and write bound for the first narrow retirement below. |
| Per-node command/RPC counts and per-run RPC count | `node_sandbox.py:125,145,221`; `effectors/__init__.py:314,682` | Workflow-shape-sensitive safety proxies. Splitting work across nodes/runs changes the budget outcome without changing the underlying command. Do not call the chosen counts physical capacity. Retire only after the actual execution boundary is bounded across the whole workload. |
| RPC reply/read/output buffer bounds, memory watchdog and OS resource limits | `node_sandbox.py:128,146-157,221-242` | Technical protection against unbounded protocol/process resources. A 1 MiB reply bound does not prove users cannot process larger files inside their code. Streaming/chunked access is an engineering solution, not a request to remove all buffer bounds. |
| Per-run and hourly effect count/byte guards | `effectors/__init__.py:332-380,771-793` and `engine_admissions.py:436-486` | Mixed: actual traffic dimension plus count/horizon policy. Node count is not sink count; checks and post-effect charges are not one atomic reservation. Preserve until covered; do not promote their fail-open readout to sole authority. |
| Existing usage reservations | `storage/usage_ledger.py:102-179` uses stable keys and pre-effect transactions; `usage_policy.py:194-211` documents settlement/coverage gaps | Reusable accounting mechanism, not an enabled unified policy. Keep dark; closing the documented gaps is necessary before it replaces an existing guard. Do not enable the 100-effect free-tier gate as a shortcut. |
| Existing compute seconds | `storage/usage_ledger.py:195-218` records/clamps worker-held duration | Not CPU seconds or provider token consumption. Do not relabel it as either. A resource decision must name what is actually occupied or measured. |

The earlier audit's historical 32/64 call/command numbers are stale; current
source has 500 RPCs per node and 1,000 workspace commands per node. The node's
"host-wide slot" comment is also not proof of host-wide exclusion. This proposal
uses the actual mechanisms above, not those historical labels.

## Concrete route: retire constraints, do not add another readout

### First implementation candidate: retire the engine-mutation share

Remove the independent `engine_max = two-thirds(total_max)` refusal while retaining
the existing total 900 admission envelope, 300 write-run limit, exact authority,
current resource/transport guards, and category observations. Reuse the same
admissions rows; no new ledger or reinterpretation of historic rows. This removes
one real product-policy knob without pretending a new universal action unit is
already implemented. It lets an owner spend their existing total allowance on
their chosen mix instead of the platform reserving one-third for a workflow type.

Required proof before changing it: a category-mix admission matrix demonstrates
that aggregate admissions cannot exceed the unchanged total, external write runs
still meet their unchanged write bound, unauthorized work still refuses, and
every non-category resource refusal is unchanged. Check all `engine_max` callers
and coupled schema/status/refusal consumers; update them together. A source claim
that it protects another user's resource must identify that resource and a path
not already bounded by the surviving total/authority controls. Do not assume this
proof licenses removing the 300-write bound or any per-effect guard next.

This candidate changes admission behavior, so it needs its normal independent
shape/basic-safety and Linux/CI/delivery gates when implementation is authorized.
**It is a recommendation, not a completed safety proof or authorization to edit.**

### Then converge at the real boundaries

- **Concurrency:** make the existing lease/slot authority cover the actual
  shared-host contention domain and execution entry points before deriving one
  per-universe capacity envelope. Keep private ownership, reentrant resource locks
  and nested-call progress distinct. Do not implement this by summing read-only
  snapshots or moving one DB argument and assuming cross-store atomicity. The
  existing run lifecycle/outbox owns release and recovery; no new ledger is the
  default answer. This is an implementation/authority design, not a founder's
  choice of semaphore or SQLite technique.
- **Activity:** inventory the real launch/dispatch identities already provided by
  engine admissions, request/provider receipts and effect reservations. Give each
  boundary one preflight/settlement owner using those existing stores. Only after
  coverage, crash and retry semantics agree may older node/run count predicates
  be removed. Prove equal resource work receives equal treatment when regrouped
  across nodes/runs; prove receipt replays do not add phantom work and actual new
  attempts cannot evade resource charging. Do not add the current counters or
  transfer 900/5,000 numeric ceilings to a different unit by relabeling them.
- **Storage:** join attributable file ownership and existing allocation/release
  evidence at writer admission; a cached sampler cannot enforce writes. Preserve
  unknown-transfer reservations, quarantine/LOST allocations and actual deletion
  settlement. The real aggregate disk-bound gap stays in the existing workspace
  admission concern, not a newly opened hardening workstream here.

If these steps reveal a genuinely necessary schema/authority change, return with
that concrete conflict before implementing it. This design does not pre-authorize
a migration, a new global ledger or a PLAN change.

## Smallest founder decision, only before a retained-space allowance changes

**Recommendation:** mandatory platform-managed runtime/shared-service overhead is
the platform's responsibility, not deducted from a user's retained-data allowance.
Attributable universe data—including user-work outputs, checkpoints and provider
state created by their work—belongs to the universe's retained footprint. Unknown
attribution is neither a charge nor proof that space is free; host protection still
accounts for all physical bytes.

**Decision:** should unavoidable platform-managed overhead be excluded from the
user's retained-space allowance? Recommend **yes**. This is a product-responsibility
choice, not something the code can settle. Do not equate the whole `.runtime`
directory with that overhead; provenance, not folder name, decides the classification.

No founder decision is needed on lock implementation, transaction layout, scan
limits, cache duration or current per-universe scope. Do not ask for new quota
numbers before the unit/coverage and real capacity evidence are established.
The first engine-share retirement candidate does not depend on this storage
decision; nothing is implemented or blocked on a premature numeric choice here.

## Acceptance of the eventual system

The same authorized work can be split, combined, retried or resumed without new
shape-based refusals; actual concurrent use, throughput and retained allocations
remain bounded for other users and the host. The user can understand and recover
from the exhausted resource. Their provider authority is never widened. Existing
technical evidence must be followed by owner-held rendered acceptance. More
telemetry alone does not satisfy this outcome. No app prompt is authorized here.
