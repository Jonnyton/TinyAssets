## Context

The full-coverage audit found four groups of already-shipped behavior without
complete canonical ownership. The five eventual canonical files are also
coordination points for active credential, connector, identity/universe, and
release changes. This lane therefore writes only a separate delta change until
those owners clear.

The source review also found one important divergence between comment-level
intent and executable behavior: the disk-watch unit calls its three steps
“independent,” but `disk_watch.py` exits 1 on the pressure path and systemd is
not configured to ignore that status. It also found that the DNS and
LLM-binding alarm sinks test the prior workflow conclusion even though probe
failures are tolerated with `continue-on-error`, so consecutive red outputs are
not guaranteed to cross the issue threshold. The as-built spec retains both
seams.

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

### Modify an existing owner or add only absent clauses

The prompt catalog modifies the complete existing Remote Streamable-HTTP MCP
Endpoint requirement because that block already owns prompt availability. The
credential delta adds only the exact alias-selection, first-record extraction,
fixed-temporary-path, and missing-concurrency semantics absent from the active
provider-overlay and canonical vault owners. Other headings remain unique.
Before sync, the change must be rebased and duplicate clauses consolidated if a
dependency lands equivalent ownership.

Alternative considered: modify the current provider-auth, advertised-handle,
status-identity, lifecycle, and uptime requirements immediately. Rejected for
the blocks with active owners because those changes already own their full
replacement text.

### Treat code and workflow control flow as authority over comments

Requirements follow executable branches, return codes, and workflow
conditions. The disk-pressure requirement therefore states the stop-on-error
seam even though the service comment says later steps are independent. The
universe-switch requirement distinguishes the public authorization path from
the low-level anonymous helper branch that public calls cannot reach.

Alternative considered: spec the comments as intended behavior. Rejected
because canonical specs are as-built truth.

### Separate metadata from enforcement

Prompt/tool titles, tags, and annotations are specified exactly, but behavior
hints are not treated as permission grants. Runtime gates remain authoritative.

### Require fresh dependency and scale checks before sync

Each canonical owner must be re-read after its dependency lands. The uptime
foldback task also requires explicit concurrency/load evidence or an explicit
bounded limitation before archive, consistent with the Forever Rule. GitHub's
same-group pending-run replacement remains an explicit limitation, and task
3.4 stays unsatisfied until the required proof exists.

## Risks / Trade-offs

- **Dependency changes invalidate a delta clause** → Rebase and source-review
  each affected capability before broadening the STATUS Files cell.
- **Exact metadata tables are intentionally change-sensitive** → Future
  metadata changes must update their canonical owner through OpenSpec.
- **Source-only workflow claims can exceed tests** → Keep scenarios bounded,
  run all focused structural/unit tests, and retain source anchors in review.
- **The disk stop seam and consecutive-red conclusion mismatch are uptime
  defects** → Track both as P1 STATUS concerns; do not hide them inside
  documentation.

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
