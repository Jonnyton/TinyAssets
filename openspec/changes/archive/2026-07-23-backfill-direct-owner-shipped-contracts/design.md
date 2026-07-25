## Context

The full-coverage audit found four groups of already-shipped behavior without
complete canonical ownership. Requirement-level comparison found that the
prompt/status, universe-switch, and uptime clauses do not replace requirements
owned by active target changes. The credential clauses alone overlap an
actively claimed canonical file and now live in
`backfill-credential-vault-shipped-contracts`.

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

- State the exact prompt/tool metadata, status variants, universe-switch
  scopes, and four uptime controllers.
- Preserve observable failure modes and missing guarantees.
- Produce strict-valid deltas that can be independently reviewed and synced
  without importing target behavior.
- Keep executable source and tests unchanged.

**Non-Goals:**

- Repair credential behavior, status identity coverage, universe
  visibility/creation, release triggers, or disk-pressure cleanup.
- Claim live-model execution from the LLM-binding canary, public-address
  validation from the DNS canary, live-receipt validation from release
  reconciliation, or launch-scale load coverage.

## Decisions

### Modify an existing owner or add only absent clauses

The prompt catalog modifies the complete existing Remote Streamable-HTTP MCP
Endpoint requirement because that block already owns prompt availability.
Every other heading in this change is absent canonically. Active target deltas
modify different requirements or add future behavior. The credential delta is
split because its canonical file remains actively claimed.

Alternative considered: wait for every active change that mentions the same
capability. Rejected because capability-level adjacency is not a
requirement-level collision and would leave shipped truth indefinitely
unspecified.

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

### Preserve future-owner and scale obligations

Each active target owner was compared at requirement level before sync. The
uptime foldback retains an explicit bounded limitation: repository workflow
concurrency declarations serialize running jobs but GitHub may replace pending
same-group runs, and no launch-scale load test is claimed. This specification
change ships no new uptime behavior; any future uptime behavior change still
requires its own Forever Rule section 14 proof.

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

1. Strict-validate and independently review the combined draft.
2. Isolate the actively claimed credential remainder.
3. Compare every remaining requirement against active target deltas.
4. Broaden the STATUS write boundary to the dependency-cleared canonical files.
5. Record the bounded uptime concurrency/load limitation.
6. Sync, prove preservation of untouched requirements, archive, review, and
   merge.

Rollback before canonical sync is deletion of this draft change. After sync,
normal OpenSpec history and git revert preserve the prior canonical state.

## Open Questions

- The release event-trigger lane must modify the deploy-run-ancestry owner if
  it changes shipped reconciliation behavior.
- Identity/reset must modify the response-shape owner if it adds evidence to
  early status responses.
- Legacy-tool retirement must modify the metadata owner when it shrinks the
  registered-tool table.
