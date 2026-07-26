# Independent Review — Per-Job Sandbox Runner Backfill

- **Change:** `backfill-per-job-sandbox-runner-seam`
- **PR:** #1629
- **Evidence base:** `origin/main` `505161f6`, landed runtime commit
  `8c70b5f0`, and branch heads through `ee29262f` plus the final corrections
- **Date:** 2026-07-22 PT / 2026-07-23 UTC

## Review Paths

### Requirement-to-source review

Reviewer: independent Codex ownership/source auditor.

Initial verdict: **ADAPT**. The review found that the first draft:

- overstated the whole request as JSON-validated instead of limiting strict
  validation to the payload;
- treated the optional result `error` as required;
- blurred the unconditional `backend.capabilities()` call with conditional job
  dispatch;
- used a non-executable inference scenario;
- overgeneralized the pass-through request fields; and
- described the repository as lacking any sandbox instead of lacking an
  OS-isolating `SandboxBackend` usable by `SandboxRunner`.

Final verdict: **APPROVE**. Every clause now matches the source boundary,
including the exact five unvalidated pass-through fields, optional result
errors, tolerated extension fields, propagated backend exceptions, and the
separate existing `NodeSandbox`.

### Capability and collision review

Reviewer: independent Codex OpenSpec coverage auditor.

Verdict: **APPROVE**.

- `distributed-execution` is the correct owner; the seam's job/owner/workspace
  and credential references plus repository/coding capabilities are broader
  than graph execution.
- The four requirement names do not collide with the six requirements in the
  active same-capability delta.
- Creating a canonical base composes safely with that active delta.
- The lane does not modify PR #1475 or
  `openspec/changes/distributed-execution/`.
- Strict validation passed all 35 pre-archive OpenSpec items.

### Whole-diff and completion review

Reviewer: independent Codex foldback auditor.

Initial verdict: **ADAPT**. It independently confirmed the pass-through-field
overclaim and required every affected audit count/grounding statement plus the
active-owner proposal-reclassification handoff to be explicit.

Final verdict: **APPROVE**.

- Audit totals reconcile from 25 / 245 / 692 to **26 capabilities / 249
  requirements / 699 scenarios**.
- The runner contributes exactly 4 requirements and 7 scenarios.
- The four other dependency-bound shipped backfills remain open.
- The active distributed-execution owner has a durable handoff to reclassify
  its proposal without this lane touching collision-owned files.

### Post-archive canonical review

Reviewer: independent Codex whole-branch auditor.

Initial verdict: **ADAPT**. OpenSpec's archive command generated the new
canonical capability with a `TBD` Purpose placeholder.

Final verdict: **APPROVE**. The canonical Purpose now narrowly owns the shipped
backend-neutral `runner/v1` seam and explicitly preserves the lack of an
OS-isolating `SandboxBackend` usable by `SandboxRunner` and the lack of a
production caller. Fresh post-archive validation passed 35/35, focused tests
passed 18/18, counts recomputed to 26 / 249 / 699 / 9, and diff-check was clean.

## Evidence

- `openspec validate backfill-per-job-sandbox-runner-seam --strict` — valid.
- `openspec validate --all --strict` — 35 passed, 0 failed before archive.
- `python -m pytest tests/test_sandbox_runner.py -q` — 18 passed.
- Runtime and plugin mirror SHA-256:
  `F461555404F82F992B8C49C09A70CDB0E0D98D6C3082777FB18DFDB9F9548ECC`.
- `python scripts/check_cross_provider_drift.py` — clean.
- `git diff --check` — clean.

## Final Verdict

**APPROVE.** No Critical or Important finding remains. Sync and archive are
approved for the landed `runner/v1` seam only; no runtime confinement claim is
approved.
