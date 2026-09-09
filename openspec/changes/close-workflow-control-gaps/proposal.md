## Why

The owner's app agent passed its workflow checklist but reported five platform
gaps at 21:39 PDT on September 8: editing guidance names an unavailable operation,
workspace discard falsely refuses ancestry, ordinary outputs are absent, failed
nodes remain running, and cancellation is not exposed. The owner explicitly added
closing these gaps to the active limits goal, with rendered agent confirmation.

## What Changes

- Make documented in-place workflow edits reachable through existing write_graph
  vocabulary and shared definition validation; remove contradictory guidance.
- Resolve workspace ancestry from the compiler's graph relation, not from the
  subset of ancestors that happened to produce HTTP responses.
- Expose persisted run output through the existing read_graph handle with accurate
  scope, generated-content provenance and bounded field access when needed.
- Record actual failing node identity/status, including code failures, so live
  and terminal readback agree without falsely marking parallel siblings failed.
- Expose cancellation through run_graph, reusing the existing scoped cancellation
  primitive and distinguishing request acknowledgment from terminal completion.

No top-level tool, private workflow repair, storage migration, provider entitlement,
new execution authority, PLAN change or platform quota increase. This does not
replace or complete the broader resource-policy goal.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: existing graph handles expose coherent editing,
  output inspection and run cancellation with canonical/served scope parity.

Internal ancestry and event corrections preserve existing workspace/run contracts.

## Impact

Owner: Codex (Patches). Branch: `codex/close-workflow-control-gaps`.
One intent: let the agent maintain and control its own workflows through ordinary
graph handles. Expected source: engine/universe wrappers, api/runs, graph compiler
events, workspace effect dispatch, tests and generated mirror. Review actual
diffs of adjacent open PRs before overlap; #3074 and #2617 touch universe_server
outside these operation routes, #2751 currently changes documentation only.
Deployed retirement #3577 remains in acceptance/spec-sync, not a second runtime
implementation lane. Normal shape/code review, Linux proof and authenticated
deployment gates apply; completion requires the app agent's explicit retest reply.
