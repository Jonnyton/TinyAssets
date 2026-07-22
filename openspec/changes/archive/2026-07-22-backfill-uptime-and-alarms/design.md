## Context

The architecture target in `PLAN.md` is broader than the system currently operating on
`main`. OpenSpec canonical specs are as-built truth, so this backfill must describe the
implemented control paths without promoting the PLAN's secondary paging path, weekly fully
automated DR, or complete public-surface coverage into requirements.

## Goals / Non-Goals

**Goals**

- Give the shipped uptime stack one canonical capability boundary.
- Make triggering, durable incident state, bounded recovery, and rollback behavior explicit.
- Preserve limitations as visible design debt with source evidence.
- Keep the Layer-2 canary and focused verification safe on Windows by using a non-destructive
  PID liveness probe and simulating the timeout at the subprocess boundary instead of
  launching a long-lived child.

**Non-goals**

- No production workflow, service, deployment, secret, schedule, or live-system mutation; the
  only runtime change is the browser-lock PID liveness repair, plus a path-filtered CI job.
- No ownership of MCP handle semantics, daemon work scheduling, or patch-loop policy.
- No claim that the full Forever Rule or PLAN target is already satisfied.

## Decisions

### D1. Own operational orchestration, reference application contracts

`uptime-and-alarms` owns when probes run, how their signals combine, how incidents page and
recover, how host-local watchdogs restart services, how P0 triage selects repair branches,
and how deploy/backup/DR safety paths behave. The probed MCP protocol stays in
`live-mcp-connector-surface`; daemon execution stays in `daemon-runtime-and-dispatch`; the
community repair loop stays in `community-patch-loop`.

### D2. Use "host-independent" only for the GitHub Actions control path

`.github/workflows/uptime-canary.yml` executes on GitHub infrastructure every five minutes,
on manual dispatch, and after a successful `Deploy prod` workflow. Its Layer-1 bundle is
therefore independent of a maintainer workstation, even though it observes the production
host. The rendered-chatbot Layer-2 job is not host-independent proof: its workflow comments
say no real browser is available, it can return SKIP, and its probe step is
`continue-on-error`. Host-local systemd watchdogs are intentionally described separately.

### D3. Treat the GitHub issue as durable alarm state

The public canary uses the open `p0-outage` issue and its comments as incident state. A second
consecutive red opens the issue, later reds append evidence, green closes it, and successful
Pushover sends append machine-readable markers. Non-bot comments after a marker acknowledge
the incident and suppress further ladder pages.

### D4. Describe both watchdogs without claiming a shared restart fence

The bootstrap-installed `tinyassets-watchdog.timer` probes MCP every 30 seconds, restarts after
three reds, and rate-limits restarts to ten minutes. The separately installed
`daemon-watchdog.timer` checks systemd, the daemon container, and the freshest supervisor
heartbeat every two minutes under its own `flock`. They do not share one cross-watchdog lock,
and the shell watchdog has no direct focused test; those facts remain limitations.

### D5. Keep DR narrower than production restoration

The nightly backup creates a transactionally copied brain tier and a best-effort live full
volume tier, uploads both to a configured rclone destination, and can additionally ship them
to GitHub releases. The manual DR workflow provisions a fresh DigitalOcean Droplet, streams a
selected full backup from the primary host, restores the data volume, starts only the daemon,
and probes through an SSH tunnel. It does not prove restoration of production secrets, the
Cloudflare tunnel, offsite-only recovery, or a zero-host weekly schedule.

### D6. Make browser-lock liveness and timeout tests non-destructive on Windows

`scripts/browser_lock.py` used the POSIX `os.kill(pid, 0)` convention to test whether a lock
owner still existed. Python's Windows implementation sends every non-console-control signal,
including `0`, through `TerminateProcess`; a Layer-2 lock check therefore killed the current
canary/test process with exit code 0. The Windows branch now opens the process with limited
query rights and checks for `STILL_ACTIVE`; POSIX retains `os.kill(pid, 0)` and treats
`PermissionError` as evidence that the process exists. This mirrors the shipped
`tinyassets.singleton_lock` strategy.

The same test file previously exercised `subprocess.run(..., timeout=...)` by launching a
Python child that slept for 600 seconds. The regression only needs to prove that
`subprocess.TimeoutExpired` maps to `_BrowserLoadError`, so it now injects that exception at
the subprocess boundary. Production timeout behavior remains unchanged. A dedicated
`windows-latest` pull-request job runs the full file when the lock, canary, test, or workflow
changes. Per the recovery directive, Codex on Windows never executes that file directly.

## Evidence Map

| Contract | Primary implementation | Focused evidence |
|---|---|---|
| Public canary + incident lifecycle | `.github/workflows/uptime-canary.yml`, `scripts/*canary.py` | `tests/test_mcp_public_canary.py`, `test_mcp_tool_canary.py`, `test_last_activity_canary.py`, `test_revert_loop_canary.py`, `test_wiki_canary.py`, `test_uptime_canary.py`, `test_uptime_canary_layer2.py` |
| Pushover ladder | `scripts/pushover_page.py`, uptime workflow alarm sink | `tests/test_pushover_page.py` |
| Host-local recovery | `deploy/tinyassets-daemon.service`, `deploy/tinyassets-watchdog.*`, `scripts/watchdog.py`, `deploy/daemon-watchdog.*` | `tests/test_watchdog.py`; source inspection for the shell watchdog |
| Classed P0 repair | `scripts/triage_classify.py`, `.github/workflows/p0-outage-triage.yml` | `tests/test_triage_classify.py`, `test_triage_classify_provider_exhaustion.py`, `test_p0_triage_workflow.py` |
| Deploy rollback + receipt | `.github/workflows/deploy-prod.yml`, `deploy/install-tinyassets-env.sh` | `tests/test_deploy_prod_workflow.py`, `test_api_status.py` |
| Backup + DR | `deploy/backup.sh`, `deploy/backup-restore.sh`, `deploy/tinyassets-backup.*`, `.github/workflows/dr-drill.yml` | `tests/test_backup_script.py`, `test_backup_restore_drill_invariants.py`, `test_dr_drill_workflow.py` |

## Known Limitations (non-normative)

- There are no dedicated paid-market, realtime collaboration, discovery, moderation, or abuse
  response canaries, so the full Forever Rule surface is not proven by the Layer-1 bundle.
- Rendered chatbot acceptance is not autonomous in GitHub Actions; Layer 2 can SKIP and is
  `continue-on-error`.
- The wiki probe proves anonymous write rejection plus persisted read, not authenticated
  write-then-read persistence; STATUS tracks the missing service credential.
- Pushover is the only emergency paging provider; the PLAN's independent 4-hour secondary
  path does not exist.
- `tinyassets-autoheal.service/.timer` are present but no checked-in install path enables them.
- The two installed watchdogs have separate concurrency controls and no shared restart fence;
  the shell daemon-watchdog lacks a direct focused regression test.
- Tunnel-token repair is manual; provider-exhaustion repair is feature-gated and otherwise
  warn/page only.
- Automatic rollback is scoped to `deploy-prod.yml`; it is not a general runtime rollback
  controller.
- DR is manual dispatch, described as quarterly/after major changes, and sources the selected
  archive through the primary host. It does not restore production env/tunnel secrets or
  prove offsite-only recovery. The latest durable passing log entry is 2026-04-22.
- No current §14 concurrency/load proof exercises the complete alarm-and-recovery chain, and
  there is no automated S7-style autoheal rehearsal covering both watchdogs.

## Rollback Plan

Revert the OpenSpec and browser-lock commit if any requirement overstates current sources or
the Windows query path regresses lock ownership. The rollback restores the destructive
`os.kill(pid, 0)` behavior on Windows, so it is an emergency-only fallback; prefer a follow-up
fix that preserves non-destructive process querying.
