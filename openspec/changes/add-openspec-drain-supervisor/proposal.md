## Why

The finish-first guard stops new OpenSpec overload, but it still requires the
host to relaunch and steer one session per slice. TinyAssets needs one bounded
controller that can run for a workday while each implementation slice receives
a fresh agent context and a one-PR terminal boundary.

## What Changes

- Add an all-day drain supervisor that invokes `peer_agent.py` sequentially,
  never maintaining a utilization floor.
- Give every fresh worker a fixed one-slice contract: select safely, claim one
  lane, deliver at most one PR, wait for merge/archive, and return a
  machine-readable terminal result.
- Keep one exact provider identity for the whole run so a replacement worker
  resumes and finishes the run's own abandoned claim before selecting more
  work.
- Independently verify GitHub merged state before counting a completed slice;
  preserve a distinct partial-progress state when merge succeeded but foldback
  remains.
- Persist controller state, logs, stop requests, time/slice budgets, recent
  blocked targets, and failure counts outside tracked product source.
- Stop after repeated worker failures; idle with a configurable delay when work
  is blocked or no candidate is currently deliverable.
- Add a runbook and cross-provider rules for launching, monitoring, stopping,
  and recovering the supervisor.
- Preserve `fleet_supervisor.py` for explicit prewritten fleet queues; the drain
  supervisor does not inherit its four-Codex/four-Claude utilization defaults.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: add a bounded sequential OpenSpec drain
  controller and fresh-worker terminal contract.

## Impact

- New stdlib-only development supervisor, focused tests, and an operations
  runbook.
- Reuses the existing subscription-authenticated `scripts/peer_agent.py`
  boundary; no API key, product runtime, MCP surface, deployment, or user data
  change.
- Adds bounded drain-worker rules to AGENTS.md and the canonical OpenSpec skill.
