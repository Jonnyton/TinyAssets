## Why

`PLAN.md` has a dedicated Uptime & Alarms module and uptime is the project's Forever Rule,
but `openspec/specs/` has no capability that owns the shipped canary, paging, host recovery,
triage, deploy rollback, backup, and disaster-recovery contracts. That leaves the most
important operating surface outside the canonical as-built requirement system and makes
aspirational PLAN text easy to mistake for landed behavior.

## What Changes

- Add an as-built `uptime-and-alarms` capability covering the GitHub-hosted public canary and
  incident lifecycle, Pushover escalation, installed host watchdog paths, class-specific P0
  triage, digest-pinned deploy admission/rollback receipts, nightly backups, and the manually
  dispatched fresh-Droplet restore drill.
- Keep public MCP protocol/handle behavior in `live-mcp-connector-surface`, daemon scheduling
  behavior in `daemon-runtime-and-dispatch`, and patch-loop repair authority in
  `community-patch-loop`; this capability owns the operational orchestration around them.
- Record gaps between current behavior and `PLAN.md` as non-normative limitations rather than
  inventing future SHALL requirements.
- Fix the shared browser lock's PID liveness probe on Windows. Python implements
  `os.kill(pid, 0)` there with `TerminateProcess`, so the supposed read-only probe killed the
  canary/test process; use `OpenProcess` plus `GetExitCodeProcess` instead and add a regression.
- Replace the Layer-2 timeout regression's real 600-second sleeper subprocess with a
  deterministic injected timeout so the focused suite cannot strand a process after failure.
- Add a path-filtered Windows GitHub Actions regression job so the prohibited Layer-2 file is
  executed outside the Codex Windows host on every relevant pull request.
- Make no deployment, production workflow, or production-state change beyond the browser-lock
  liveness repair.

## Capabilities

### New Capabilities

- `uptime-and-alarms`: As-built monitoring, incident paging, bounded recovery, deploy rollback,
  backup, and disaster-recovery behavior.

### Modified Capabilities

None.

## Impact

OpenSpec artifacts, `STATUS.md` coordination state, `scripts/browser_lock.py`, its Layer-2
regression file, and one focused Windows CI workflow change. The capability is grounded in
existing files under `.github/workflows/`, `deploy/`, `scripts/`, `tests/`, and `docs/ops/`;
all other production sources remain untouched. The separately claimed
`release-reconcile-event-trigger` change and `.github/workflows/release-reconcile.yml` are
explicitly outside this change.
