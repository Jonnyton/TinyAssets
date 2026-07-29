## Context

The shipped OpenSpec drain is a Windows watchdog/supervisor/worker stack. It
has useful delivery invariants—fresh `origin/main` admission, one claim, one
bounded slice, independent review, ordinary pull requests, and durable terminal
results—but its controller and health state disappear with the host.

TinyAssets already has or is actively specifying the generic pieces needed to
replace that controller: immutable Branch versions, owner-scoped authoring,
persisted triggers, background target and provider authority, scoped external
effects, checkpointed runs, and canonical chatbot handles. This change does not
take ownership of those pieces. It defines the activation envelope that proves
they compose into an ordinary user-owned cloud loop and preserves the
drain-specific delivery invariants.

The important unresolved boundary is provider authority. The current
requester-custody direction intentionally keeps raw provider secrets on a
requester-controlled executor. That is not, by itself, a cloud-usable authority
source when Jonathan's computer is off. This change refuses activation until a
separately owned contract supplies a Jonathan-owned provider binding usable by
the cloud executor without raw-secret chat ingress, maintainer quota, or market
fallback.

The approved architecture and user acceptance boundary live in
`docs/design-notes/2026-07-29-main-account-cloud-spec-drain.md`.

## Goals / Non-Goals

**Goals:**

- Instantiate the drain as a private, ordinary, immutable Branch version in
  Jonathan's main universe.
- Make readiness and activation a typed, fail-closed composition check rather
  than a deployment assumption.
- Preserve exactly one active drain controller across local-to-cloud cutover
  and rollback.
- Let Jonathan inspect, control, repair, version, publish, activate, and roll
  back the loop using only a phone chatbot and the live connector.
- Prove continuous useful progress, restart recovery, truthful blocking, and
  authority provenance while the computer remains off.

**Non-Goals:**

- Building a privileged repository patch service or a drain-specific scheduler.
- Adding a top-level MCP handle.
- Implementing provider custody, background authority, the generic authoring
  lifecycle, or the outbound boundary inside this change.
- Using market compute, maintainer credentials/quota, or concurrent drain lanes
  as an MVP fallback.
- Treating a local tray indicator as cloud health.

## Decisions

### 1. The drain is an ordinary Branch composition plus a typed activation

The drain definition uses the same versioned user-authoring lifecycle as other
Branches and composes Goal, Trigger, Gate, Run, and effect nodes. The only
drain-specific product artifact is its definition and policy data. A small
activation record binds an immutable Branch version to the authorities and
continuation policy required to run it unattended.

This is preferable to moving the Python supervisor into a cloud container or
GitHub Actions. Either alternative would create a privileged second runtime
whose control and evolution do not exercise the product contract.

### 2. Readiness is a closed manifest, not a best-effort probe

The activation record pins:

- the owner principal and main-universe identity;
- one immutable Branch version and definition hash;
- the standing Goal and persisted Trigger, including timezone and missed-fire
  policy;
- current background target and provider binding references;
- the Jonathan-owned provider assignment/binding generation;
- the exact TinyAssets GitHub destination grant, allowed effect classes,
  unprompted-action caps, and receipt policy;
- per-slice time, token/spend, retry, and no-progress budgets;
- the activation generation and controller-fence identity.

Activation rereads every referenced record and fails closed if one is absent,
stale, revoked, mismatched, or not implemented. A provider route identified as
maintainer-owned, market-supplied, or merely available in process environment
is ineligible. Readiness remains inspectable from the phone surface.

This avoids partially activating a loop whose scheduler works but whose
provider or GitHub authority silently degrades to a different owner.

### 3. A generation-fenced activation lease enforces single-active cutover

There is one logical drain-controller key for the TinyAssets repository. Cloud
activation uses compare-and-swap to acquire its next generation only after the
local bridge has been stopped and its final claim has either completed or
reached a safe terminal hold. Each cloud slice carries that generation.
Losing, replacing, pausing, or stopping the activation fences new slice and
effect admission; it does not pretend an already committed external effect was
rolled back.

Rollback first stops/fences the cloud generation, waits for its current
irreversible boundary to settle, and only then permits a prior cloud version or
the local bridge to acquire a new generation. The tray and cloud controller
never share an active generation.

An operating-system process lock is insufficient because it cannot coordinate
with a cloud worker after the PC is off.

### 4. Each trigger produces one durable logical slice attempt

The persisted Trigger issues a logical period/continuation identity. Duplicate
delivery reuses that identity and cannot create another claim. One slice:

1. refreshes and inspects exact current `origin/main`;
2. ranks and mechanically admits one currently claimable OpenSpec/STATUS lane;
3. creates or resumes one isolated Git branch;
4. performs one bounded implementation/foldback increment;
5. runs focused checks and independent opposite-provider review;
6. publishes through normal GitHub PR, CI, review, and branch protection;
7. records terminal progress/blocking/effect receipts before scheduling the
   next slice.

Worker death before an external effect resumes from checkpoint or retries the
same logical attempt. Ambiguous effect outcomes are held for destination
reconciliation. A terminal result must exist before the next slice becomes
eligible.

This keeps the useful local drain discipline while removing local worktree and
tray state as authority.

### 5. Phone ownership reuses the canonical handles

The live connector remains the only required user control surface:

- `read_graph` and `get_status` expose the active version, full definition,
  health, current claim, receipts, budgets, authority provenance, and blockers;
- existing owner-scoped authoring operations routed through the canonical graph
  handles create, inspect, diff, edit, dry-test, and publish immutable versions;
- existing schedule/run/control operations routed through the canonical handles
  pause, resume, stop, activate/rebind, and roll back owner-authorized state;
- `converse` may translate natural language into those operations but grants no
  authority by itself.

If an internal operation is missing, its owning generic capability must supply
it under the existing handle set before activation. This change does not add a
drain-only verb.

### 6. Health measures useful progress and truthful holds

Cloud health is derived from durable state: activation/lease generation, last
useful progress, current claim and phase, last terminal receipt, next eligible
retry, consecutive no-progress count, active Branch version, and target/provider
authority sources. A blocked prerequisite or exhausted admissible queue is
yellow/held with its reason; missing ownership, lost activation, stale progress,
or repeated delivery failure is red. A ticking scheduler without useful
progress is not green.

### 7. Cutover is an acceptance event, not merely deployment

The cloud loop may be deployed dark and dry-tested while the tray remains the
active bridge. Final cutover stops the tray, verifies no live local claim,
activates one cloud generation, and begins the acceptance window. Acceptance
requires:

- the computer off for the entire 24-hour window;
- useful progress and a deliberate cloud-worker restart recovery;
- rendered phone-chatbot inspection, pause/resume, edit/diff, dry-test,
  publish, activation, and rollback;
- concurrency/load proof for duplicate triggers, activation races, claim
  races, revocation, and worker loss;
- no maintainer, market, desktop, CLI, duplicate-claim, or review-bypass trace;
- post-fix clean-use evidence or an explicit watch item if no later user use is
  yet visible.

The local bridge is removed from startup only after this evidence passes.

## Risks / Trade-offs

- **[Provider authority has no cloud-usable Jonathan-owned route]** →
  activation remains `not_ready` and names the missing dependency; no fallback
  is allowed.
- **[Active prerequisite changes overlap or change shape]** → consume only
  their reviewed contracts, keep this lane's code boundary to composition and
  acceptance, and revalidate references at build/foldback checkpoints.
- **[A phone abstraction hides execution-affecting detail]** → the full
  definition and immutable diff remain available alongside summaries.
- **[A crash occurs around a GitHub mutation]** → use the outbound boundary's
  journal-before-fire identity and destination reconciliation; hold before
  firing anything else.
- **[The tray is stopped too early]** → dark deploy and dry-test first; cutover
  requires a complete readiness manifest and retains an ordered rollback path.
- **[A long-running drain consumes unbounded quota]** → hard per-slice and
  rolling budgets stop issuance and expose remediation through health.

## Migration Plan

1. Land this specification with cloud activation disabled.
2. Audit each required generic capability and link its accepted immutable
   contract; leave readiness blocked for every missing edge.
3. Materialize the private Branch/Goal/Trigger definition and deterministic
   drain policy; run side-effect-free tests through the cloud executor.
4. Bind Jonathan-owned target, provider, and TinyAssets-repository effect
   authorities; exercise activation/duplicate/fire/restart failure tests while
   still dark.
5. Complete rendered phone-chatbot control and version-evolution tests.
6. Stop the local tray drain, settle its claim, acquire the first cloud
   activation generation, and run the 24-hour computer-off proof.
7. If acceptance fails, fence cloud first and either activate the previous
   cloud version or temporarily restore the tray. Never run both.
8. After acceptance, disable tray autostart for the drain and retain only the
   documented emergency rollback procedure.

## Open Questions

- Which separately owned provider-authority successor will supply a
  cloud-usable Jonathan-owned binding without contradicting the native-only
  raw-secret custody rule?
- Does the persisted Trigger contract's declared catch-up mode satisfy
  continuous drain recovery directly, or should completion emit the next
  persisted event using the same generic Trigger surface?
- Which current generic activation/rebind operation will own the
  generation-fenced Branch binding? If none exists, its owning platform
  capability must be selected before implementation rather than adding a
  drain-local action.
