## 1. Regression Proof

- [x] 1.1 Add a focused unit sentinel requiring accepted alert status 1 and exact alert-to-rotation-to-auto-prune order
- [x] 1.2 Run the focused sentinel before the unit change and record the expected failure

## 2. Unit Repair

- [x] 2.1 Add `SuccessExitStatus=1` without changing script exit semantics or command order
- [x] 2.2 Correct unit comments that overstate failure independence

## 3. Verification and Foldback

- [x] 3.1 Run focused disk-watch tests and strict OpenSpec validation
- [x] 3.2 Review the final diff for correctness, scope, security, and misleading claims
- [x] 3.3 Sync the delta into the canonical uptime-and-alarms spec and archive the completed change
