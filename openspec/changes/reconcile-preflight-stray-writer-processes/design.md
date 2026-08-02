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

- Use captured nonempty exact IDs for expected containers, extra volume
  consumers, and recovery sidecars in both ownership snapshots.
- Confirm preliminary candidates against one fresh, complete PID inventory
  from those exact identities and re-prove the same Linux process generation.
- Ignore a candidate only when it exited or the fresh snapshot owns its PID
  and the current process generation still equals the scanned generation.
- Preserve pre-mutation refusal for every still-live unowned candidate and for
  any container identity whose ownership cannot be proved.
- Treat failed, timed-out, malformed, or partial per-identity Docker PID output
  as zero trusted ownership without exposing the raw failure.
- Exercise PID churn, PID reuse, malformed ownership output, genuine unowned
  writers, and 100/101 candidate boundaries deterministically for the uptime
  §14 concurrency/load proof.

**Non-Goals:**

- Loosening writer markers, receipt-file checks, controlled-path checks, or
  mount-namespace checks.
- Killing, stopping, or inspecting the content of an unowned process.
- Changing OAuth validation, MCP behavior, release receipts, rollback, or
  post-quiesce process proofs.

## Decisions

### Use captured exact identities in both ownership snapshots

Preflight will assemble nonempty captured IDs from the expected fleet, extra
volume consumers, and admitted recovery sidecars. The initial exclusion
snapshot and `_confirm_stray_writer_processes` will both query only those IDs.
This closes the existing initial-snapshot gap where a same-name replacement
could otherwise be excluded before becoming a candidate.

Alternatives rejected:

- Rejecting the preliminary scan is the current availability failure.
- Stopping units before confirmation mutates production before preflight proof.
- Parsing cgroups or Docker internals independently duplicates an existing,
  reviewed ownership primitive and creates another identity interpretation.

### Trust only complete per-identity Docker PID output

`Host.container_pids` will add ownership for an exact identity only after the
`docker top <id> -eo pid` call succeeds and the complete output has one exact
header plus only valid PID rows. A nonzero exit, timeout, missing header,
malformed row, or partial result contributes no PIDs for that identity. The
raw command failure remains private. Zero trusted ownership is conservative:
container processes found by `/proc` remain candidates and block preflight.

### Bind PID ownership to the scanned process generation

Each preliminary risk records Linux `/proc/<pid>/stat` start time. After the
fresh Docker snapshot, confirmation re-reads that token before excusing a PID.
Only equal start time plus fresh exact-container ownership proves the same
process is owned. A changed or unreadable generation remains a confirmed risk,
even if Docker reported the numeric PID, closing exit-and-PID-reuse TOCTOU.

### Preserve the fixed external refusal class

If any confirmed candidate remains, preflight raises the existing constant
error and publishes no PID, executable, command line, environment value, mount
namespace, or process exception. Structural candidate fields remain internal
to tests and the already-bounded observation path. A 101st candidate raises a
separate fixed overflow class before mutation rather than truncating evidence.

### Prove snapshot churn without timing-dependent tests

Tests will supply a preliminary same-generation candidate absent from the first
snapshot but present in the fresh exact-identity snapshot. Separate tests cover
same-name replacement before the initial snapshot, failed/partial Docker
output, a changed process generation reusing an owned numeric PID, and a live
unowned candidate. The load proof covers exactly 100 mixed candidates and
proves candidate 101 fails closed rather than disappearing.

## Risks / Trade-offs

- [A host writer exits before confirmation] -> It is no longer a live writer
  risk; later queue, process, and post-quiesce proofs remain mandatory.
- [A genuine writer starts after confirmation] -> Existing quiesce and final
  process scans still fail closed; this change does not remove them. Numeric
  PID reuse during confirmation is independently blocked by start-time binding.
- [A container name is replaced between snapshots] -> Confirmation uses the
  captured immutable container IDs, so replacement PIDs are not trusted.
- [Docker PID lookup fails or is partial] -> That identity contributes zero
  ownership; raw errors remain private and candidates fail before mutation.
- [Candidate inventory exceeds the bounded evidence shape] -> Candidate 101
  raises a fixed overflow refusal before mutation; no tail is silently omitted.

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
