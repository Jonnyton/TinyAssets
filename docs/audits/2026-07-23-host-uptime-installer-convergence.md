# Fresh-host uptime installer convergence audit

**Status:** current diagnostic evidence, not implementation authority  
**Verified:** 2026-07-23 on `origin/main` `5de747d6`  
**Existing implementation lane:** `codex/converge-host-uptime-installers` in
`C:\Users\Jonathan\Projects\wf-openspec-conformance-audit2`

## Finding

The P0 STATUS concern is valid. A fresh host does not converge the complete
uptime service set:

- `hetzner-bootstrap.sh` installs only the TinyAssets watchdog, backup, and
  prune timers. It omits the daemon watchdog and disk-watch timer.
- Bootstrap enables timers only when files change, so byte-current but disabled
  timers remain disabled.
- `install-host-services.yml` installs only the daemon watchdog plus the
  separately owned GitHub token refresher.
- `restart-daemon.yml` contains a third partial watchdog installer.
- `tinyassets-disk-watch.service` invokes
  `python3 -m scripts.rotate_run_transcripts` without the installed runtime as
  its working directory. Invocation outside the checkout reproduces
  `No module named scripts`.
- Existing tests inspect isolated unit text. They do not invoke one convergent
  installer, and `tests/test_prune_units.py` currently requires the duplicated
  bootstrap implementation.

This contradicts the canonical `uptime-and-alarms` requirements for two
watchdog paths and installed backup/disk-pressure scheduling. PR #1652 fixed
ordered disk-pressure remediation after installation; it explicitly did not
prove installation or activation.

## Complete change boundary

The active OpenSpec change `converge-host-uptime-installers` should require:

1. One shared installer owns all five unit/timer pairs and their runtime
   manifest.
2. Bootstrap, post-deploy host installation, and the restart workflow's install
   option delegate to that installer.
3. Complete source preflight and hashing occur before destination mutation.
4. Every invocation reloads systemd, enables and starts all five timers, then
   verifies both enabled and active state, even when installed bytes were
   already current.
5. Same-target invocations wait under a bounded lock and each eventually
   verifies convergence. A nonblocking loser is insufficient because the only
   post-deploy run could lose and leave the host stale indefinitely.
6. Different target roots remain parallel and isolated.
7. Disk-watch receives an executable installed-module context.
8. The delta is synced into the canonical uptime spec and archived on land.

Workflow uploads must use a run-unique remote staging directory. A target-root
installer lock does not protect today's shared `/tmp/<basename>` files from
pre-lock overwrite. For `workflow_run`, the bundle must come from
`github.event.workflow_run.head_sha`; manual dispatch uses `github.sha`.

The direct runtime manifest is:

- `scripts/watchdog.py`
- `scripts/mcp_public_canary.py`
- `deploy/daemon-watchdog.sh`
- `deploy/backup.sh`
- `scripts/backup_ship_gh.py`
- `scripts/backup_prune.py`
- `scripts/disk_watch.py`
- `scripts/disk_autoprune.py`
- `scripts/rotate_run_transcripts.py`
- `tinyassets/storage/__init__.py`
- `tinyassets/storage/rotation.py`

The GitHub App token refresher remains a separate workflow-owned service.

## Required write set

- `deploy/install-host-uptime-services.sh`
- `deploy/hetzner-bootstrap.sh`
- `deploy/tinyassets-disk-watch.service`
- `.github/workflows/install-host-services.yml`
- `.github/workflows/restart-daemon.yml`
- `tests/test_host_uptime_installers.py`
- `tests/test_disk_watch.py`
- `tests/test_prune_units.py`
- `deploy/DEPLOY.md`
- `docs/audits/2026-07-23-host-uptime-installer-concurrency-proof.md`
- `openspec/changes/converge-host-uptime-installers/`, then its archive
- `openspec/specs/uptime-and-alarms/spec.md`
- `STATUS.md` and `REFLECTION.md`

The active lane's STATUS Files cell should be broadened to this boundary before
implementation.

## Concurrency and runtime proof

The section-14 proof must execute the real installer:

- At least 64 distinct fake host roots concurrently: all succeed, receive exact
  manifests, and show no cross-root contamination.
- A 32-caller same-root burst: no mutation interleaving; every caller waits and
  subsequently verifies convergence, or follows an explicitly tested automatic
  retry path.
- Missing source, copy, reload, activation, enabled-check, and active-check
  failures remain red.

Run focused installer, prune, disk-watch, watchdog, and backup suites plus
`bash -n`, ShellCheck, actionlint, strict OpenSpec validation, and
`systemd-analyze verify` for all ten units/timers.

Fresh-host proof requires a disposable Debian 12 host from the exact commit:

1. Start with all units absent and run bootstrap.
2. Verify installed hashes and all five timers enabled and active.
3. Disable/stop the timers without changing files; rerun and verify repair.
4. Safely invoke every oneshot with disposable Docker/data/backup fixtures.
5. Record systemd results and the post-install public MCP canary.

After merge, retain a monitoring item until production evidence shows the real
install workflow and subsequent watchdog, disk, backup, and prune executions
using the landed artifacts.

## Coordination

The pending DR-drill lane also needs
`openspec/specs/uptime-and-alarms/spec.md`; the P0 installer convergence change
should land first. Draft PRs #1557 and #1606 overlap installer/workflow files
but are marked not to merge and do not own this P0. They must rebase and adapt
after the convergence lane rather than block it.

