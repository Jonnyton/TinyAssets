## Why

An agent inspecting its own failed workflow can read terminal status but cannot
see useful node activity and completed-provider evidence already stored with the
run. This forces unsupported guesses about provider silence, startup and latency.

## What Changes

- Add compact, typed node-activity evidence to the existing authorized run read,
  reusing persisted events without another tool, selector, storage table or run.
- Preserve completed-call observations when a later node fails, distinguish
  local start/return from provider acknowledgment and output validation, and
  label missing evidence as unknown.
- Expose only selected metadata and normalized answering-provider receipts;
  never copy raw event details, prompt/response text, code, arbitrary exceptions,
  credentials or nested provider objects into this new projection.
- Preserve current graph selection, ACL checks, generated-content provenance,
  node status, exact-output reads and client response adapters.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: existing run inspection includes honest stored
  node-activity evidence for authorized callers.

## Impact

One intent: let an agent diagnose its existing runs from preserved evidence.
Owner: Codex. Branch: `codex/run-activity`. One PR after implementation/review.
Implementation belongs in `tinyassets/api/` with a small pure projection helper,
the run snapshot integration, focused tests, and generated plugin mirror.
No provider pins, permission grants, private-workflow edits, event producer or
storage migration, retry/cancellation change, top-level tool, or PLAN amendment.

Acceptance: independent review, focused/CI regressions, verified deployment,
then the ordinary app agent inspects an existing failed run and can accurately
report preserved node/call evidence and its limits without rerunning it. A
passing workflow smoke test alone does not close this diagnostic capability.
