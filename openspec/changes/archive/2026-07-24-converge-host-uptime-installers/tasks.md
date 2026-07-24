## 1. Convergent installer

- [x] 1.1 Add the exact unit/runtime closure with canonical guarded roots, prerequisite checks, content-addressed releases, and a per-target lock.
- [x] 1.2 Pause timers, wait boundedly for active oneshots, transactionally install units/runtime, then always reload, enable/start, and verify all five timers.
- [x] 1.3 Validate the scoped local-watchdog sudoers candidate before atomic mode-0440 installation.
- [x] 1.4 Give every service a versioned-runtime execution path and disk-watch an importable installed working directory.

## 2. Caller convergence

- [x] 2.1 Install fresh-host sudo/flock prerequisites and replace bootstrap's conditional timer blocks with the shared installer.
- [x] 2.2 Pin automatic reconciliation to the triggering deploy SHA; pin manual dispatch to `github.sha`; checksum a unique remote bundle and invoke the shared installer while retaining token-refresher installation.
- [x] 2.3 Replace the restart workflow's partial watchdog installation with a `github.sha` bundle delegated to the shared installer.

## 3. Verification

- [x] 3.1 Add isolated invocation tests for fresh install, installed disk-watch import closure, backup/watchdog/canary paths, byte-current but disabled repair, missing manifest source, active-service timeout, and failure propagation.
- [x] 3.2 Prove 64 distinct targets remain isolated and a 32-caller same-target burst waits, serializes mutation, and gives every caller a verified success.
- [x] 3.3 Parse both workflows for triggering/manual SHA pinning, the installer-owned manifest, checksum, and unique remote staging; prove bootstrap has one installer owner.
- [x] 3.4 Run focused installer/unit/workflow tests, shell syntax and lint, actionlint, `systemd-analyze verify`, and strict OpenSpec validation.
- [x] 3.5 Record the section-14 proof and the still-pending disposable Debian/live-host evidence.
