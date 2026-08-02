## 1. Regression contracts

- [x] 1.1 Add a Windows regression that runs a synthetic hung lifecycle child and proves an outer deadline returns its phase output plus a non-zero total-timeout verdict within a bounded wall clock; observe RED before the supervisor exists.
- [x] 1.2 Tighten the workflow contract test so the release job must invoke the supervisor and preserve a distinct, later job-level timeout; observe RED against the direct lifecycle invocation.

## 2. Implementation

- [x] 2.1 Add the outer Windows lifecycle supervisor with redirected diagnostic files, an exact total deadline, bounded exact-child-tree cleanup, output replay, and truthful exit propagation.
- [x] 2.2 Instrument lifecycle phase start/completion/PID evidence and remove process-tree cleanup from the lifecycle child's failure authority.
- [x] 2.3 Invoke the supervisor from Desktop release CI with a five-minute total deadline beneath the ten-minute GitHub fallback.

## 3. Verification and foldback

- [ ] 3.1 Run focused desktop tests, PowerShell syntax/execution probes, Ruff, strict OpenSpec validation, and independent exact-head review.
- [ ] 3.2 Land through a reviewed PR, observe one fresh successful exact-head Windows lifecycle CI job, sync/archive the OpenSpec change, and restore the remaining full-platform refinery row without claiming signed or clean-VM readiness.
