## Context

The emergency recovery path intentionally starts the daemon and four workers
under a unique Docker Compose project such as
`tinyassets-recovery-691142eb4348935e`. Finalization restores boot posture but
does not convert those containers into the canonical systemd service's Compose
project. A subsequent normal preflight safely stops the recovered generation
and writes its exact IDs, but `prepare_deploy` only unmasks the service. If the
service is inactive, no canonical `docker compose down` runs, and the canonical
project fails to create the fixed names already held by the stopped recovery
generation.

The existing `retire-cheat-loop` emergency-recovery requirement already makes
durable provenance, exact-five ownership, restart fencing, queue safety, and an
unchanged receipt snapshot mandatory. This repair extends that boundary rather
than introducing a second recovery authority.

## Goals / Non-Goals

**Goals:**

- Transfer a finalized, durably recorded recovery generation to the next
  canonical deploy without container-name collision.
- Remove only the exact stopped recovery-owned container IDs after all normal
  pre-start safety checks pass.
- Make interruption between removal intent, removal, and service unmasking
  safely replayable.
- Preserve the named production data volume and unrelated containers.
- Preserve recovery's public route and log forwarder after the old fixed-name
  sidecars have been retired, including partial-start and retry paths.

**Non-Goals:**

- General Docker garbage collection or removal by name/prefix.
- Replacing the systemd/Compose deployment model.
- Changing recovery image admission, MCP authentication, or public behavior.
- Retaining the transitional fence after `retire-cheat-loop` task 2.5a.

## Decisions

### 1. Carry recovery provenance through normal preflight

When the prior durable state is `restored` and contains a recovery project, the
new preflight validates that its recorded exact-five container IDs equal the
currently inspected fleet and that every container has the same recorded
`com.docker.compose.project` label. It copies that bounded handoff record into
the new run's write-ahead state before the first host mutation.

This is preferred over trusting the `tinyassets-recovery-` name prefix because
a label-shaped string is not authority. It is also preferred over rediscovering
the prior run after preflight because preflight deliberately replaces the
canonical state with the current run.

### 2. Retire the exact recovery generation inside `prepare_deploy`

After queue, receipt, and stopped-old-ID checks pass, `prepare_deploy` validates
the exact five names, IDs, project labels, stopped states, and `restart=no`
policies. It durably records removal intent, removes those IDs with
`docker rm` (without `-v`), proves the production-volume container inventory is
empty, records completion, and only then unmasks the canonical service.

Ordinary canonical-project deployments do not carry a recovery handoff record
and retain their existing systemd lifecycle. A partial, extra, running,
identity-changed, foreign-project, or unrecorded fleet fails before removal.

### 3. Replay exact remaining subsets after durable removal intent

If a process or Docker daemon dies after `docker rm` removes only a strict
subset, a retry may complete the remaining subset only when the current run
already contains exact durable removal intent. Every survivor must retain its
original recorded ID, recovery project label, stopped state, and `restart=no`;
every missing recorded ID must be proved absent; and no extra or substituted
volume consumer may exist. The retry removes only the remaining exact IDs and
proves the inventory empty. Exact empty inventory is the terminal form of the
same replay and records completion without another remove.

Before durable intent, partial absence remains an ownership failure. This
avoids recreating removed recovery containers merely to remove them again while
making the non-transactional Docker operation replayable inside the
write-ahead boundary.

### 4. Admit only a proved partial canonical target into unsafe recovery

A canonical service start may fail after creating fewer than the expected five
target containers. The unsafe fence then has complete preflight provenance but
the existing recovery path refuses the strict subset before it can restore the
previous admitted image.

Recovery may plan removal of this subset only when every production-volume
consumer has an expected canonical name, exact recorded target image and
revision, canonical `tinyassets` Compose project label, stopped state, and
`restart=no`. It also proves that every missing expected canonical name is
absent across all container states. The exact observed IDs are written before
removal. Replay accepts only the remaining recorded subset, proves removed IDs
absent, removes without `-v`, and converges to an empty volume inventory before
starting recovery.

An extra name, foreign project/image/revision, running or restart-enabled
container, same-name off-volume container, or identity substitution fails
before removal. This is not general Docker garbage collection.

### 5. Transfer fixed-name sidecars as a recovery-owned sub-generation

The tunnel and log forwarder do not mount the production data volume, so they
are outside the exact-five writer inventory but still block canonical Compose
by fixed name. A restored recovery preflight therefore binds each present
sidecar by exact ID, exact Compose project/service labels, non-writer mounts,
and saved restart policy. It restart-fences and stops those IDs with the writer
fleet. Target preparation writes exact removal intent, removes only the
recorded survivors without `-v`, and permits subset/empty replay only after the
intent is durable.

An ownership refusal reports only the fixed sidecar name and one bounded
predicate class: missing identity, invalid project, invalid service, changed
recorded identity, or failed non-writer proof. Raw IDs, labels, mount names, and
other host inspection values never enter workflow logs or uploaded evidence.

If both the candidate and ordinary rollback fail, unsafe recovery cannot rely
on removed sidecars. Before recovery it may retire a newly present fixed-name
sidecar only after writing its exact ID and proving the canonical or currently
owned recovery project plus exact service label. Recovery starts the five
writers first, proves them, then starts both sidecars under the same unique
recovery project with the restart-no override. Their IDs are durably bound and
their running/restart-fenced posture is proved before recovery returns.

A partial sidecar Compose start is captured from exact recovery project/service
labels before cleanup. The same recovery invocation restart-fences, stops, and
removes only those recorded IDs, then makes one bounded sidecar-only retry. If
Compose exits zero but the exact pair is incomplete, the observed subset uses
that same path. If the bounded retry also fails, the new partial IDs remain
durably bound and stopped under the ordinary unsafe fence. Fixed-name identity
drift or a sidecar stop failure after capture cannot preempt the independent
volume-writer fence: a captured exact ID that still exists is restart-fenced
and stopped by ID without removal when possible, while a replacement fixed-name
occupant is untouched. Any sidecar refence error is recorded after the writer
fence is attempted. An absent partial fleet, foreign ownership, or an unexpected
data mount never enters the retry removal path. Finalization restores the
preflight-saved sidecar policies;
a sidecar that was already absent uses the canonical Compose `unless-stopped`
posture rather than inheriting temporary `restart=no`. The next normal
preflight accepts recovery sidecars only when their exact recorded IDs and
recovery project still match.

## Risks / Trade-offs

- [Prior recovery state is incomplete or stale] → refuse before preflight
  mutation rather than infer ownership.
- [Docker removal succeeds partially] → the canonical service remains masked;
  durable intent permits only provenance-bound removal of the exact remaining
  subset.
- [Crash after removal] → current-run removal intent permits only the exact
  remaining-subset or empty-fleet replay path.
- [Canonical containers are accidentally targeted] → removal requires prior
  restored-recovery state plus exact IDs and exact recovery project labels.
- [Data loss from container removal] → use exact `docker rm` IDs with no volume
  flag; the named data volume is never a command target.
- [Partial target is not the failed canonical generation] → require exact
  target image/revision, canonical project label, expected-name subset,
  stopped/restart-fenced state, and absent-name proof before write-ahead intent.
- [Sidecar removal strands recovery without ingress] → unsafe recovery starts
  and proves an exact recovery-owned tunnel/log pair; one recovery-owned
  partial creation is removed by exact ID and retried in the same invocation,
  while a repeated failure is durably re-fenced.
- [Ownership evidence leaks host state] → publish only the fixed name and fixed
  predicate class; keep every observed label, ID, and mount value private.

## Migration Plan

1. Add red tests for the production-reproduced recovered-generation handoff,
   foreign/partial/running refusal, ordinary canonical deploy preservation, and
   removal-intent replay.
2. Implement provenance capture and exact idempotent retirement.
3. Run the focused fence suite, Ruff, strict OpenSpec validation, and
   independent security/fail-closed review.
4. Before rollback, reduce bounded candidate startup logs and state to
   allowlisted structural signals under hard deadlines. A traceback frame is
   eligible only when its path names an actual public Python file in the
   checked-out `tinyassets/` source tree; function names and line values are not
   emitted. Collect raw logs only after the inspected container's immutable
   image reference and OCI revision equal the fence-proved target; transport
   those fixed fields with a literal safe separator rather than escape
   sequences whose rendering depends on Docker's Go template behavior. Append
   Docker's JSON-escaped pre-start error as the final field, split only the
   preceding fixed boundaries, and publish only an identity-bound fixed error
   class. Failure
   and cancellation after image mutation take the same bounded capture path,
   including deploy or environment-assert failures that skip the named health
   step. Publish only sanitized evidence, and gate publication on an explicit
   cleanup output proving the fleet was restored or authoritatively
   restart-fenced plus a published terminal release-state receipt. Mismatched
   observed container identities are reduced to `unavailable`.
   When an identity-matched container remains `created` with no Docker start
   error, inspect the already-preserved unit journal through a separate
   read-only workflow. Accept only a strict past UTC window of at most ten
   minutes, frame a one-byte source-truncation flag plus at most 256 KiB total
   before SSH, and expose fixed Compose stages/failure classes rather than raw
   journal text. Anchor the terminal phase at the last daemon `Creating` or
   `Starting` marker so a retry without another create cannot inherit an older
   success. Preserve container-name conflicts and line-level unclassified
   failures even when another known class is also present.
5. Merge and build an immutable image.
6. From the currently restored old-image recovery, execute one normal deploy
   through the repaired fence and prove the exact five canonical containers,
   public MCP canary, and durable restored state.
7. Resume PR #1935's OAuth diagnostic deployment.
8. Sync the delta into the main capability spec, archive the change, and retire
   its live coordination row.

Rollback uses the existing provenance-bound unsafe recovery workflow with the
previous admitted stop-writer image. No direct host deletion or fence bypass is
an acceptable rollback.

## Open Questions

None. Production artifacts from runs `30578541098` and `30578968815` establish
the failure and safe starting state.
