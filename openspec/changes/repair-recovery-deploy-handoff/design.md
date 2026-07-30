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

## Migration Plan

1. Add red tests for the production-reproduced recovered-generation handoff,
   foreign/partial/running refusal, ordinary canonical deploy preservation, and
   removal-intent replay.
2. Implement provenance capture and exact idempotent retirement.
3. Run the focused fence suite, Ruff, strict OpenSpec validation, and
   independent security/fail-closed review.
4. Merge and build an immutable image.
5. From the currently restored old-image recovery, execute one normal deploy
   through the repaired fence and prove the exact five canonical containers,
   public MCP canary, and durable restored state.
6. Resume PR #1935's OAuth diagnostic deployment.
7. Sync the delta into the main capability spec, archive the change, and retire
   its live coordination row.

Rollback uses the existing provenance-bound unsafe recovery workflow with the
previous admitted stop-writer image. No direct host deletion or fence bypass is
an acceptable rollback.

## Open Questions

None. Production artifacts from runs `30578541098` and `30578968815` establish
the failure and safe starting state.
