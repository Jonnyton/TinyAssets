## Context

The full-coverage audit correctly noticed that the repository added a per-job
sandbox runner after the original OpenSpec baseline, but its final
shipped-backfill inventory named only four other groups. PR #1485 had already
landed `tinyassets.sandbox_runner`, a byte-identical plugin mirror, and focused
tests. The active `distributed-execution` task ledger marks that seam shipped,
while its delta spec contains only the broader future authority program.

Two independent ownership audits agree that `distributed-execution` is the
semantic owner. The seam carries job, owner, workspace, credential-grant, and
idempotency references and supports repository and coding capabilities beyond
graph nodes. `graph-execution-substrate` instead owns the current
`compile_branch` path, which still executes approved source in-process and does
not invoke this seam.

## Goals / Non-Goals

**Goals:**

- Give the landed `runner/v1` behavior an honest canonical owner.
- Make every normative clause traceable to current code and focused tests.
- Preserve all negative boundaries that prevent the seam from being mistaken
  for deployed confinement.
- Establish a canonical base that the active distributed-execution change can
  extend when its future behavior lands.

**Non-Goals:**

- Build or specify a container, WSL2, bwrap, or other isolation backend.
- Wire graph execution, `converse`, paid-market jobs, or coding jobs into the
  seam.
- Claim cryptographic attestation, authorization, leases, fencing, persistence,
  retries, timeout handling, cancellation transport, credential resolution,
  deduplication, or exactly-once effects.
- Modify the active `distributed-execution` delta or PR #1475.

## Decisions

### Canonicalize the landed base under `distributed-execution`

The backfill creates a canonical `distributed-execution` capability containing
only the shipped runner seam. The active change may then add its separate
future requirements against that base. This avoids syncing the active delta's
unimplemented authority guarantees and avoids inventing a parallel
`sandbox-runner` capability for a component already owned by the distributed
execution program.

Putting the seam in `graph-execution-substrate` was rejected. Its capability
set includes repository read/execute and coding, no production graph path calls
it, and assigning it to graph execution would imply integration that does not
exist.

### Treat backend reports and receipts as structural assertions

The runner refuses dispatch unless the backend reports readiness, isolation,
secret absence, self-test success, matching protocol/schema, and requested
capability support. Returned enforcement evidence is structurally validated
and bound to the request and preflight report.

The spec deliberately does not call this cryptographic attestation. The module
does not authenticate or recompute those assertions, and `policy_sha256` is
only checked as a 64-character string.

### Specify the exact JSON boundary without claiming payload scrubbing

Requests contain nine landed wire fields and derive actions from the immutable
capability mapping. Payloads are detached through strict JSON round-trip and
must be objects. The top-level contract carries only opaque credential and
workspace references, but arbitrary JSON payload keys are not scrubbed.
Therefore the requirement cannot claim that a caller is prevented from placing
sensitive data inside the payload.

### Keep absence executable and visible

The only built-in backend reports no capability and fails readiness. No
production module imports the runner. Both facts are canonical limitations,
not temporary prose, so future code cannot treat the existence of the seam as
proof that platform secrets are no longer co-resident with executed work.

## Risks / Trade-offs

- **[Risk] A structural receipt is mistaken for trusted enforcement evidence.**
  → State that reports are backend assertions and enumerate the absent
  authentication/recomputation guarantees.
- **[Risk] The canonical capability appears to mean distributed execution is
  generally shipped.**
  → Limit its purpose and requirements to `runner/v1`, include the unwired and
  unavailable boundary in normative text, and leave broader behavior in the
  active change.
- **[Risk] Concurrent work modifies the same active delta.**
  → Do not edit `openspec/changes/distributed-execution/` or PR #1475 files;
  sync only the new canonical base.
- **[Risk] Runtime and packaged copies drift after reconciliation.**
  → Verify exact file equality before land and retain the existing mirror
  parity gate.

## Migration Plan

1. Strictly validate this isolated delta and run the focused runner tests.
2. Verify the runtime and plugin copies are byte-identical.
3. Obtain independent requirement-to-source and whole-diff review.
4. Sync only this delta into the new canonical `distributed-execution` base,
   update the coverage audit, validate the full tree, and archive the change.

There is no runtime rollout or rollback. Reverting the documentation commit is
the rollback if a clause is later shown to misdescribe current behavior.

## Open Questions

None. Backend selection and the future authenticated execution path remain
owned by the active `distributed-execution` change.
