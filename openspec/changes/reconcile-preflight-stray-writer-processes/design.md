## Context

The deploy fence first snapshots Docker-owned PIDs and then scans `/proc` for
processes that hold the receipt database, resemble a writer command, inherit a
controlled-volume environment path, or mount the controlled volume in another
namespace. Fleet observation already reconciles those preliminary candidates
against a second Docker PID snapshot. Normal preflight does not: run
`30676899240` therefore failed before mutation on the fixed class
`pre-mutation stray writer process risk is nonzero` even though the exact fleet
had passed the prior normal deploy and remained publicly healthy.

The production fence is security-sensitive. A fix must remove only the Docker
PID snapshot race; it must not trust names, command lines, environment values,
or an unproved container replacement, and it must not mutate the host to make a
candidate disappear.

## Goals / Non-Goals

**Goals:**

- Confirm preliminary candidates against one fresh PID inventory from the
  exact container identities already inspected by preflight.
- Ignore a candidate only when it exited or the fresh exact-container snapshot
  owns its PID.
- Preserve pre-mutation refusal for every still-live unowned candidate and for
  any container identity whose ownership cannot be proved.
- Exercise container PID churn and genuine unowned writers deterministically,
  including the uptime §14 concurrency/load proof.

**Non-Goals:**

- Loosening writer markers, receipt-file checks, controlled-path checks, or
  mount-namespace checks.
- Killing, stopping, or inspecting the content of an unowned process.
- Changing OAuth validation, MCP behavior, release receipts, rollback, or
  post-quiesce process proofs.

## Decisions

### Reuse the existing exact-identity confirmation primitive

Preflight will pass its preliminary candidates and the exact inspected
container IDs to `_confirm_stray_writer_processes`. That helper takes one fresh
Docker PID snapshot, keeps live candidates not owned by those IDs, and drops
only exited or newly proved container-owned PIDs. Using IDs rather than names
keeps same-name substitution fail-closed.

Alternatives rejected:

- Rejecting the preliminary scan is the current availability failure.
- Stopping units before confirmation mutates production before preflight proof.
- Parsing cgroups or Docker internals independently duplicates an existing,
  reviewed ownership primitive and creates another identity interpretation.

### Preserve the fixed external refusal class

If any confirmed candidate remains, preflight raises the existing constant
error and publishes no PID, executable, command line, environment value, mount
namespace, or process exception. Structural candidate fields remain internal
to tests and the already-bounded observation path.

### Prove snapshot churn without timing-dependent tests

Tests will supply a preliminary candidate whose PID is absent from the first
Docker snapshot but present in the fresh exact-identity snapshot. A second test
keeps a live candidate outside the fresh ownership set. The load proof will
confirm a full bounded batch of candidates with mixed new container ownership,
exits, and one genuine unowned survivor in one snapshot operation.

## Risks / Trade-offs

- [A host writer exits before confirmation] -> It is no longer a live writer
  risk; later queue, process, and post-quiesce proofs remain mandatory.
- [A genuine writer starts after confirmation] -> Existing quiesce and final
  process scans still fail closed; this change does not remove them.
- [A container name is replaced between snapshots] -> Confirmation uses the
  captured immutable container IDs, so replacement PIDs are not trusted.
- [Docker PID lookup fails] -> No candidate is excused; it remains confirmed
  and preflight refuses before mutation.

## Migration Plan

1. Land the exact-identity confirmation with red/green focused tests and the
   bounded concurrency/load case.
2. Pass the complete recovery/deploy suite, Ruff, strict OpenSpec, flow, and an
   independent fail-closed review.
3. Build a new immutable image from current main; do not reuse
   `a6301200b668` because its fence lacks this repair.
4. Run one normal production deploy and require exact fleet, public canary,
   cleanup, and terminal-receipt proof. Rollback remains the existing
   provenance-bound previous-image path.
5. Resume the rendered OAuth/custom-agent acceptance only after the deploy is
   green.

## Open Questions

None.
