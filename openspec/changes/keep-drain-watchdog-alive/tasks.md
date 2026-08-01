## 1. Failure Reproduction

- [x] 1.1 Add focused tests proving exhausted Windows health-file replacement does not escape the watchdog and leaves a diagnostic.
- [x] 1.2 Add focused checks for bounded tray relaunch and a periodic hidden current-user scheduled-task trigger.
- [x] 1.3 Add loop-level publication recovery and real Windows registration proof for separate logon/guard tasks.
- [x] 1.4 Add full-loop session-stop survival and stopped-session installer deferral regressions.

## 2. Self-Heal Implementation

- [x] 2.1 Make health publication failure non-fatal while preserving the last complete atomic health document.
- [x] 2.2 Add stale-health watchdog relaunch to the tray with a recovery cooldown.
- [x] 2.3 Add an idempotent one-minute periodic recovery trigger to a separate current-user guard task.
- [x] 2.4 Preserve explicit session stop across self-heal and require versioned single-process activation during reinstall.
- [x] 2.5 Restrict observer recycle to anchored executable/argument matches and defer activation when session stop is active.
- [x] 2.6 Serialize tray control mutations and live installation with a named mutex, including a concurrent-stop integration regression.

## 3. Verification And Activation

- [ ] 3.1 Pass focused tests, Ruff, strict OpenSpec validation, drift checks, and independent exact-head review.
- [ ] 3.2 Reinstall the task and fault-inject watchdog and tray death, proving recovery without a duplicate supervisor or visible console.
