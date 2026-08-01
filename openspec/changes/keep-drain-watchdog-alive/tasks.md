## 1. Failure Reproduction

- [x] 1.1 Add focused tests proving exhausted Windows health-file replacement does not escape the watchdog and leaves a diagnostic.
- [x] 1.2 Add focused checks for bounded tray relaunch and a periodic hidden current-user scheduled-task trigger.

## 2. Self-Heal Implementation

- [x] 2.1 Make health publication failure non-fatal while preserving the last complete atomic health document.
- [x] 2.2 Add stale-health watchdog relaunch to the tray with a recovery cooldown.
- [x] 2.3 Add an idempotent one-minute periodic recovery trigger to the existing current-user task.

## 3. Verification And Activation

- [ ] 3.1 Pass focused tests, Ruff, strict OpenSpec validation, drift checks, and independent exact-head review.
- [ ] 3.2 Reinstall the task and fault-inject watchdog and tray death, proving recovery without a duplicate supervisor or visible console.
