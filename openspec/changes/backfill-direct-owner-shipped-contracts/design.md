## Context

The full-coverage audit found four groups of already-shipped behavior without
complete canonical ownership. The five eventual canonical files are also
coordination points for active credential, connector, identity/universe, and
release changes. This lane therefore writes only a separate delta change until
those owners clear.

The source review also found one important divergence between comment-level
intent and executable behavior: the disk-watch unit calls its three steps
“independent,” but `disk_watch.py` exits 1 on the pressure path and systemd is
not configured to ignore that status. The as-built spec retains that stop seam.

## Goals / Non-Goals

**Goals:**

- State the exact credential projection aliases, prompt/tool metadata,
  status variants, universe-switch scopes, and four uptime controllers.
- Preserve observable failure modes and missing guarantees.
- Produce strict-valid deltas that can be independently reviewed now and
  rebased onto dependency owners before canonical sync.
- Keep executable source and tests unchanged.

**Non-Goals:**

- Repair credential fail-closed behavior, status identity coverage, universe
  visibility/creation, release triggers, or disk-pressure cleanup.
- Sync or archive while an overlapping canonical owner remains in flight.
- Claim live-model execution from the LLM-binding canary, public-address
  validation from the DNS canary, live-receipt validation from release
  reconciliation, or cross-process serialization from credential writes.

## Decisions

### Use separate ADDED requirements rather than editing active owners

Every heading in this change is unique relative to canonical and active
changes. This avoids silently replacing an active MODIFIED block. Before sync,
the change must be rebased and duplicate clauses consolidated if a dependency
lands equivalent ownership.

Alternative considered: modify the current provider-auth, advertised-handle,
status-identity, lifecycle, and uptime requirements immediately. Rejected
because active changes already own several of those blocks.

### Treat code and workflow control flow as authority over comments

Requirements follow executable branches, return codes, and workflow
conditions. The disk-pressure requirement therefore states the stop-on-error
seam even though the service comment says later steps are independent.

Alternative considered: spec the comments as intended behavior. Rejected
because canonical specs are as-built truth.

### Separate metadata from enforcement

Prompt/tool titles, tags, and annotations are specified exactly, but behavior
hints are not treated as permission grants. Runtime gates remain authoritative.

### Require fresh dependency and scale checks before sync

Each canonical owner must be re-read after its dependency lands. The uptime
foldback task also requires explicit concurrency/load evidence or an explicit
bounded limitation before archive, consistent with the Forever Rule.

## Risks / Trade-offs

- **Dependency changes invalidate a delta clause** → Rebase and source-review
  each affected capability before broadening the STATUS Files cell.
- **Exact metadata tables are intentionally change-sensitive** → Future
  metadata changes must update their canonical owner through OpenSpec.
- **Source-only workflow claims can exceed tests** → Keep scenarios bounded,
  run all focused structural/unit tests, and retain source anchors in review.
- **The disk stop seam is an uptime defect** → Track it as a P1 STATUS concern;
  do not hide it inside documentation.

## Migration Plan

1. Strict-validate and independently review this draft change.
2. Wait for or coordinate each named dependency owner.
3. Rebase, re-run source/test grounding, and remove any duplicated clauses.
4. Broaden the STATUS write boundary to only the canonical files whose
   dependencies have cleared.
5. Run focused evidence plus the explicit uptime concurrency/load gate.
6. Sync, prove preservation of untouched requirements, archive, review, and
   merge.

Rollback before canonical sync is deletion of this draft change. After sync,
normal OpenSpec history and git revert preserve the prior canonical state.

## Open Questions

- Whether the release dependency will replace deploy-run ancestry with the
  live release receipt before this delta can sync.
- Whether identity/reset makes `session_boundary` present in early status
  responses, eliminating the current three-shape distinction.
- Whether legacy-tool retirement lands before metadata sync, shrinking the
  registered-tool table.
