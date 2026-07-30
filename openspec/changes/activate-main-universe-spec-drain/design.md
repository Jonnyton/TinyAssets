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

- Run one bounded OpenSpec delivery slice at a time from Jonathan's private
  cloud universe while every user device is off.
- Use only Jonathan-owned provider and destination-scoped GitHub authority.
- Preserve current-main admission, isolated branch/worktree, independent
  review, CI, merge verification, and OpenSpec foldback.
- Make ownership complete from a phone chatbot: inspect, control, repair,
  version, activate, and roll back the ordinary Branch composition.
- Prove restart recovery, no duplicate claims, useful 24-hour progress, and
  single-active tray-to-cloud cutover.

**Non-Goals:**

- A new scheduler service, top-level MCP handle, drain-specific server
  subsystem, or privileged maintainer automation path.
- Market-compute fallback, parallel lane execution, or multi-repository
  generalization in the MVP.
- Bypassing GitHub review, CI, branch protection, or OpenSpec sync/archive.
- Depositing raw provider or GitHub secrets through chat.
- Treating the local tray, a local test, or a mocked cloud run as cloud
  acceptance.

## Decisions

### 1. The drain is an ordinary private Branch composition

The durable definition is a versioned Branch in Jonathan's main universe,
bound to a standing Goal and persisted Trigger. Its graph composes selection,
claim, build, verification, review, publication, merge verification, foldback,
receipt, and continuation nodes from existing primitives.

This keeps policy user-owned and remixable. Moving the current supervisor
script to GitHub Actions was rejected because that would create a second,
repository-specific scheduler. Keeping the tray primary was rejected because
host shutdown remains an outage.

### 2. The first deployable slice is BYOC, single-flight, and PR-only

The minimum useful vertical slice resolves Jonathan-owned provider authority in
the cloud, fires one persisted invocation, admits and leases one current-main
candidate, produces at most one PR, and writes one terminal receipt. It has no
market fallback and no direct merge effect.

This is the shortest slice that proves the hard boundaries together. A
read-only demo would not prove provider authority or useful progress; a
multi-lane version would add concurrency before single-flight correctness is
known.

Activation is gated on current-main prerequisites:

- request-scoped/background execution carries the real user, universe, Branch,
  and immutable version authority;
- the cloud executor resolves a user-owned provider binding and fails closed
  without maintainer, host, or market substitution;
- persisted trigger/continuation and collision-safe claim leasing survive
  worker restart;
- Branch access and immutable version operations enforce owner authority;
- the GitHub adapter enforces an exact repository destination grant, secret
  custody, idempotent receipts, and normal PR policy;
- canonical connector actions can inspect and control the resulting state.

### 3. Activation, claims, and external effects use separate durable identities

Host decision 2026-07-29: epoch-2 transactional claiming is the sole live
mutation authority. Epoch-1 file locking is compatibility-drain-only during a
bounded migration and cannot admit new work or mutate this automation while
epoch 2 is active. Cutover is fail-closed and the two authorities are never
dual-active.

Every invocation reads exact current `origin/main`, follows the canonical
STATUS/OpenSpec admission policy, and acquires one durable task claim before
building. One server-authoritative activation record is keyed by
`(universe_id, automation_id)` and carries a monotonically increasing epoch,
active executor class, immutable Branch version, lease identity, and state.
Activation, version rebind, stop, cutover, and rollback use compare-and-swap
transitions. Every claim validates the exact current epoch, executor, and
version. Concurrent cloud versions, alternate activation identities, and stale
or partitioned tray attempts cannot claim by minting a new local identity.

Concurrent or recovered invocations reuse the automation activation and claim
identities; they do not mint an alternate provider identity.

The GitHub effect uses a system-derived idempotency identity tied to the claim,
repository destination, intended head, and effect kind. The exact tuple is
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
authoritative for PR, checks, and merge state. Foldback begins only after
independently verifying the merged PR on GitHub.

Using one identity for activation, local admission, and remote effects was
rejected: the three state machines fail and recover at different boundaries.

### 4. Control is owner-authorized and respects irreversible boundaries

Existing canonical handles expose the automation definition, active immutable
version, current claim, last useful progress, terminal receipts, provider
authority source, budgets, retry state, and blocker. Owner-authorized actions
pause, resume, or stop future slices.

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

## Risks / Trade-offs

- **[Prerequisite lanes expose incompatible authority shapes]** → Recheck their
  current-main specs and implementations before any runtime edit; adapt this
  change through reviewed deltas rather than adding a parallel authority model.
- **[A worker crashes after a remote effect but before local finalization]** →
  Attach/finalize an exact match, retry once only after conclusive absence under
  the same reservation, and block without mutation on ambiguous reconciliation.
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
2. Implement and test the BYOC single-flight PR-only slice behind an inactive
   private Branch version.
3. Dry-test through the live connector with external effects disabled, then
   publish the immutable version and exact authority bindings.
4. Stop and fence the local tray drain; activate exactly one cloud version.
5. Run restart, collision, effect-reconciliation, phone-control, and 24-hour
   PC-off acceptance.
6. If acceptance fails, stop cloud first and re-enable the tray only after the
   cloud fence is observed inactive. Preserve receipts and checkpoints for
   diagnosis.
7. After acceptance, leave the tray drain disabled and complete OpenSpec
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
