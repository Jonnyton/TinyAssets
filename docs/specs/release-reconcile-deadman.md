# Release reconcile dead-man

## Objective

Detect when `.github/workflows/release-reconcile.yml` has no successful
`schedule` run within 30 minutes, without depending on GitHub's scheduler.
The ordinary push-triggered release path remains unchanged; this protects the
automatic fallback used by token-mediated merges whose push event is suppressed.

## Runtime design

- A stdlib-only Python probe reads the public GitHub Actions runs API and
  considers only successful `event=schedule` runs.
- A production-host systemd timer runs the probe every five minutes.
- A Healthchecks-compatible external monitor receives a success ping while the
  newest qualifying run is at most 30 minutes old and a `/fail` ping otherwise.
- Missing probe/timer/VM/network heartbeats are detected by that external
  monitor, so the checker cannot stop silently.
- The existing reconcile cron and reconcile logic remain unchanged.

The 30-minute threshold is two nominal 15-minute slots: it tolerates one missed
tick while alarming after the second objective breach, matching PR #1507's
audited recommendation.

## Commands and structure

- Focused test: `python -m pytest tests/test_release_reconcile_deadman.py -q`
- Regression test: `python -m pytest tests/test_uptime_canary.py tests/test_canary_scripts_import_smoke.py -q`
- Style: `ruff check scripts/release_reconcile_deadman.py tests/test_release_reconcile_deadman.py`
- Probe: `python scripts/release_reconcile_deadman.py --heartbeat-url <ping-url>`
- Source: `scripts/release_reconcile_deadman.py`
- Unit tests: `tests/test_release_reconcile_deadman.py`
- Runtime units: `deploy/tinyassets-release-deadman.{service,timer}`
- Installer: `.github/workflows/install-host-services.yml`

## Testing strategy

Unit tests inject time and HTTP responses. They cover fresh, stale, never-ran,
malformed/API-failure, success heartbeat, failure heartbeat, and heartbeat
delivery failure. The §14 proof runs 1,000 freshness classifications across 32
threads and verifies the systemd unit is a single non-overlapping oneshot. A
forced-stale CLI run must show a `/fail` request and a nonzero exit before the
PR is opened.

## Boundaries

- Always: filter to successful scheduled runs; fail closed on missing/malformed
  data; signal the external monitor on every invocation; keep credentials out of
  source; leave the reconcile workflow untouched.
- Ask first: selecting a different external monitor contract or adding
  auto-dispatch/recovery authority.
- Never: schedule the watchdog through GitHub Actions, shorten the reconciler
  cron, count manual runs as scheduler health, or suppress an existing test.

## Success criteria

- A run at age `<= 30 minutes` exits zero and sends the normal heartbeat.
- A run older than 30 minutes, or no successful scheduled run, sends `/fail`
  and exits nonzero with an explicit reason.
- GitHub/API/heartbeat errors exit nonzero and print to stderr.
- The production timer is installed independently of GitHub scheduling.
- The PR documents the single host action: configure the external ping URL and
  dispatch the host-service installer.
