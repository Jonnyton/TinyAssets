## Context

The Windows OpenSpec drain demonstrates bounded claims, isolated worktrees,
review, CI, and foldback, but its controller and health disappear with the host
PC. PLAN requires recurring host-independent workflows to live in the user's
cloud universe as ordinary compositions, requires user-owned compute before
market compute, and forbids a privileged product-specific automation loop.

This change turns the host-approved design in
`docs/design-notes/2026-07-29-main-account-cloud-spec-drain.md` into an
end-to-end delivery contract. It does not claim that all prerequisites already
exist. Background authority, requester-owned provider resolution, schedule
continuation, Branch access/versioning, and GitHub effect authority remain with
their owning OpenSpec lanes and must be current-main behavior before activation.

The custody assumption is explicit: the private universe may hold this
automation's definition, activation, checkpoints, coordination metadata,
receipts, and health. Those records must be exportable. The repository remains
in GitHub, and this change does not decide custody for unrelated user content.

## Goals / Non-Goals

**Goals:**

- Run one bounded repository-to-accepted-spec delivery slice at a time from a
  requester's private cloud universe while every user device is off, with
  Jonathan's OpenSpec drain as the first acceptance fixture.
- Let an ordinary user supply a repository plus a spec or patch request through
  the chatbot, create/import/remix the Branch composition, bind private
  authority, and activate it without a maintainer-only setup step.
- Use only requester-owned provider and destination-scoped GitHub authority.
- Preserve current-main admission, isolated branch/worktree, independent
  review, CI, merge verification, and OpenSpec foldback.
- Make ownership complete from a phone chatbot: inspect, control, repair,
  version, activate, and roll back the ordinary Branch composition.
- Use a rendered connector conversation as final user-surface acceptance after
  the generic input, execution, authority, and output boundaries are live.
- Prove restart recovery, no duplicate claims, useful 24-hour progress, and
  single-active tray-to-cloud cutover.

**Non-Goals:**

- A new scheduler service, top-level MCP handle, drain-specific server
  subsystem, or privileged maintainer automation path.
- Market-compute fallback, parallel lane execution, or multi-repository
  generalization in the MVP.
- Tenant repository commands, shell, CI emulation, or external tool execution
  before production confinement is available.
- Dependency-wave scheduling, backlog-refinery automation, or
  reprioritization in this first change.
- Bypassing GitHub review, CI, branch protection, or OpenSpec sync/archive.
- Depositing raw provider or GitHub secrets through chat.
- Treating the local tray, a local test, or a mocked cloud run as cloud
  acceptance.

## Decisions

### 1. The drain is an ordinary private Branch composition

The durable definition is a versioned Branch in the requester's universe,
bound to a standing Goal and persisted Trigger. Principal, universe,
repository, accepted spec, Branch version, evaluator policy, provider route,
and destination are data-bound inputs. Jonathan's values instantiate the first
fixture and do not appear as runtime constants.

The published definition contains immutable references and policy only.
Activation, epoch-2 task, background attempt, provider invocation, evaluation,
effect, and GitHub/OpenSpec state remain with their existing owners. A
chatbot-facing projection reads those records and generations without copying
them into a second writable packet state or advancing their lifecycle.

This keeps policy user-owned and remixable. Moving the current supervisor
script to GitHub Actions was rejected because that would create a second,
repository-specific scheduler. Keeping the tray primary was rejected because
host shutdown remains an outage.

### 2. The first deployable slice is BYOC, single-flight, and PR-only

The minimum useful vertical slice freezes one `AcceptanceScenario`, executes a
typed deterministic baseline containing no tenant code, resolves
requester-owned provider authority in the cloud, fires one persisted
invocation, admits and leases one current-head candidate, produces at most one
PR through the outbound-boundary owner, and writes one terminal receipt. It has
no market fallback and no direct merge effect.

This is the shortest slice that proves the hard boundaries together. A
read-only demo would not prove provider authority or useful progress; a
multi-lane version would add concurrency before single-flight correctness is
known.

Activation is gated on current-main prerequisites:

- request-scoped/background execution carries the real user, universe, Branch,
  and immutable version authority;
- the cloud executor resolves a user-owned provider binding and fails closed
  without maintainer, host, or market substitution;
- the frozen evaluator chain, input digests, privacy scope, expected evidence,
  and budgets are immutable for the attempt, while shell/repository commands
  fail closed with `sandbox_unavailable`;
- persisted trigger/continuation and collision-safe claim leasing survive
  worker restart;
- Branch access and immutable version operations enforce owner authority;
- the outbound-boundary owner enforces an exact repository destination grant,
  secret custody, idempotent receipts, remote reconciliation, and normal PR
  policy;
- canonical connector actions can inspect and control the resulting state.

### 3. Activation, claims, and external effects use separate durable identities

Host decision 2026-07-29: epoch-2 transactional claiming is the sole live
mutation authority in the approved target. As built, epoch 2 remains
dark/inactive and epoch-1 file locking remains the live bridge until task 4.1
implements and proves the server-authoritative cutover. Migration closes
epoch-1 admission and drains or fences already-admitted work before activation;
afterward epoch 1 is compatibility-reconciliation-only and cannot admit new
work or mutate this automation. Cutover is fail-closed and the two authorities
are never dual-active.

Every invocation reads the exact current destination head, follows the
canonical repository/spec admission policy, and acquires one durable task
claim before building. One server-authoritative activation record is keyed by
`(universe_id, automation_id)` and carries a monotonically increasing epoch,
active executor class, immutable Branch version, lease identity, and state.
Activation, version rebind, stop, cutover, and rollback use compare-and-swap
transitions. Every claim validates the exact current epoch, executor, and
version. Concurrent cloud versions, alternate activation identities, and stale
or partitioned tray attempts cannot claim by minting a new local identity.

Concurrent or recovered invocations reuse the automation activation and
logical claim identities; provider invocation authority remains independently
reserved by its owner and is never inferred from queue possession.

The persisted Trigger is the generic cadence owner, not provider, queue, or
effect authority. Each bounded slice has an immutable trigger ordinal and
frozen definition digest. A SQLite compare-and-swap lease admits exactly one
worker; lease expiry may advance only that trigger's generation. Settlement
atomically records one immutable typed terminal receipt, marks the claimed
trigger emitted, and—only while the exact cloud activation remains current—
creates the next pending trigger. Replaying settlement returns the same
receipt and successor. Pause or stop still records already-committed evidence
but creates no successor. This makes crash recovery explicit without turning
the repository workflow into a privileged scheduler.

The outbound-boundary owner supplies the GitHub effect's system-derived
idempotency identity tied to the claim, repository destination, intended head,
and effect kind. The exact tuple is
`(universe_id, automation_id, claim_id, repository, intended_head_sha,
effect_kind)`. Recovery has three exhaustive outcomes:

1. if the exact remote effect exists, attach it and finalize the existing
   receipt without another mutation;
2. if authoritative destination inspection proves the effect absent and the
   same reservation is retry-eligible, retry at most once under that same
   reservation;
3. if remote state is ambiguous, mismatched, or cannot be reconciled, record a
   blocker and perform no mutation.

A receipt proves what was attempted and observed, but GitHub remains
the fresh external source for PR, checks, protected head, and merge state.
TinyAssets remains authoritative for activation, budgets, evaluation, and
receipts. Foldback combines both before it begins.

Using one identity for activation, local admission, and remote effects was
rejected: the three state machines fail and recover at different boundaries.

One evaluation retry is allowed in the same preserved task workspace. It keeps
the logical definition and outbound effect identity, receives bounded failure
context, and mints fresh target-attempt and provider-invocation generations
with fresh bounded budgets. A second failure terminates with a durable replan
input. Dependency waves and backlog-refinery admission wait for a later delta.

### 4. Control is owner-authorized and respects irreversible boundaries

Existing `read_graph`, `write_graph`, `run_graph`, and `get_status` handles
expose the automation definition, active immutable version, current claim,
last useful progress, terminal receipts, provider authority source, budgets,
retry state, and blocker. The server derives the principal from authenticated
request context and resolves ownership server-side; caller-supplied
`owner_actor` is never authority. Owner-authorized actions pause, resume, or
stop future slices. Reprioritization is deferred to an epoch-2 queue-policy
delta.

Pause and stop do not pretend to cancel an external effect already committed to
GitHub. They prevent the next slice and record the in-flight boundary. This
matches PLAN's rule that human control belongs at irreversible boundaries.

### 5. Repair and evolution publish immutable versions

Jonathan edits the ordinary Branch definition, inspects the complete diff,
dry-tests it without external writes, publishes a new immutable version, and
explicitly rebinds activation. Rollback rebinds a previously published version;
it never mutates history in place.

Operator-only patching was rejected because it would make the cloud loop
nominally user-owned but practically dependent on a computer or maintainer.

### 6. Cutover and health are cloud-authoritative

Cloud activation uses the server-authoritative CAS/epoch fence shared with the
tray drain. Cutover advances the record from a stopped tray epoch to one cloud
epoch. Rollback first stops that cloud epoch and then advances to a tray epoch.
Every claim validates the current record, so a stale or partitioned executor
cannot continue from cached state.

Cloud health is derived from typed receipts and checkpoints, not tray color or
process liveness. It reports last useful progress, current claim, retry time,
blocker, authority source, budget state, and a no-progress alarm. Repeated
retries without a useful state transition remain unhealthy.

Until cutover, the temporary tray drain remains the active fallback. If its
coordination-only refinery worker discovers that an older open pull request
already owns the exact assigned target, the supervisor suppresses that target
for the entire bounded run and immediately considers the next candidate.
Suppression requires the exact terminal-marker PR URL, exact repository, a PR
head branch equal to the assigned target or its canonical `-aNNN` attempt lane,
fresh open state, and a creation time before the run start. Prefix-colliding,
missing, unrelated, closed, merged, malformed, or
same-run PR evidence remains a real failure. The exact refinery assignment is
persisted before dispatch, and restart recovery reruns the same verification
before consuming a result left behind by a crash; failed recovery verification
consumes the `FAILED` result through ordinary failure accounting before any new
dispatch. This prevents a correct duplicate-lane refusal from consuming the
two-strike failure budget while avoiding false progress or broad open-PR trust.

## Risks / Trade-offs

- **[Prerequisite lanes expose incompatible authority shapes]** → Recheck their
  current-main specs and implementations before any runtime edit; adapt this
  change through reviewed deltas rather than adding a parallel authority model.
- **[A worker crashes after a remote effect but before local finalization]** →
  Attach/finalize an exact match, retry once only after conclusive absence under
  the same reservation, and block without mutation on ambiguous reconciliation.
- **[Tenant repository code reaches control-plane secrets]** → Admit only typed
  deterministic no-tenant-code evaluators; fail closed with
  `sandbox_unavailable` until the distributed-execution owner proves
  confinement, secret absence, resource limits, cleanup, and fenced evidence.
- **[GitHub reconciliation is still unsupported]** → Keep activation dark until
  `outbound-boundary-layer` ships exact remote lookup and crash-after-effect
  reconciliation or explicitly owns a reviewed narrow adapter.
- **[Missed schedules create bursts or silent stalls]** → Use one explicitly
  declared bounded continuation policy from the scheduler owner and expose the
  applied policy in health.
- **[Pause races an irreversible effect]** → Fence future slices and surface the
  committed boundary; do not claim retroactive cancellation.
- **[A broad GitHub grant escapes the repository]** → Require an exact
  TinyAssets repository destination, purpose, and effect class, with no raw
  credential in Branch-visible state.
- **[A green loop makes no useful progress]** → Separate liveness from useful
  progress and alarm on the latter.
- **[Twenty-four-hour proof is slow]** → Use focused restart/concurrency tests
  before cutover, but retain the real PC-off duration as the final acceptance
  gate.

## Migration Plan

1. Obtain independent opposite-provider review of this change and verify every
   prerequisite against current main.
2. Implement and test the generic immutable definition and read-only
   operational projection behind an inactive private Branch version.
3. Land epoch-2 activation, background Branch/provider authority, typed
   no-tenant-code evaluation, and outbound GitHub reconciliation prerequisites;
   keep activation dark while any remain unavailable.
4. Dry-test through the live connector with external effects disabled, then
   publish the immutable version and exact authority bindings.
5. Stop and fence the local tray drain; activate exactly one cloud version.
6. Run restart, collision, effect-reconciliation, phone-control, and 24-hour
   PC-off acceptance.
7. If acceptance fails, stop cloud first and re-enable the tray only after the
   cloud fence is observed inactive. Preserve receipts and checkpoints for
   diagnosis.
8. After acceptance, leave the tray drain disabled and complete OpenSpec
   sync/archive foldback.

## Open Questions

- Which current-main requester-owned provider binding is the first one proven
  safe for cloud consumption without raw-secret chat deposit?
- Does the landed scheduler owner supply the required bounded continuation
  policy, or must this composition use standing-Goal event re-enqueueing?
- Which existing canonical-handle actions provide the complete Branch
  definition diff, dry-test, version bind, and rollback flow at implementation
  time?

These are prerequisite-selection questions. They may choose among existing
owners but may not expand this change into a new provider, scheduler, or MCP
surface.
