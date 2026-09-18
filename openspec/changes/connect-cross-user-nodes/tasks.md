## 1. Ground and review

- [x] 1.1 Complete independent cross-family shape review and resolve the queue, artifact and occurrence-identity source seams before runtime implementation (ADAPT findings incorporated; concrete interfaces recorded September 9, not runtime approval).
- [x] 1.2 Repair the webhook fixture's imported-resolver leak and verify the real-owner webhook/handoff test group together without weakening ACLs (53 passed on Windows, September 9).

## 2. Implement the ownership boundary

- [x] 2.1 Add owner-scoped exposure/link records, generation checks, revocation and receiver policy validation with two-owner negative tests (49 new tests pass on Windows and supplemental Ubuntu Python 3.11, including separate-process CAS; internal management only, delivery/public wiring and required oracle/review/live gates remain below).
- [x] 2.2 Compile and preflight pinned selected-node entry projections, preserving downstream semantics and skipping predecessor-only effects (pure helper + 24 Windows tests; exposure wiring and Linux/live evidence remain subsequent gates).
- [ ] 2.3 Add durable occurrence acceptance and atomic unique receiver-run insertion/recovery with concurrent and crash-point tests. Internal reservation/attempt-lock/recovery and common worker seams are implemented. September 18 adds dispatch through the existing executor in a fresh receiver context, current receiver ACL/graph checks, persistent start fencing, safe settlement and startup/maintenance reconciliation. Public validated intake, explicit receiver retry and final integration proof remain; this task is not complete.
- [ ] 2.4 Transfer exact structured/file deliverables through scoped artifact copies, resource reservations and cleanup with integrity and cross-owner denial tests.
- [ ] 2.5 Wire sender node output/effect provenance and two-party receipts, retries, disconnect and safe processing outcomes.
- [ ] 2.6 Expose management/send/readback through canonical graph handles and shared served wrappers; verify provider-neutral tool parity and mirror output.

## 3. Deliver and prove

- [ ] 3.1 Pass focused baseline/candidate Windows and Linux tests, lint and exact-head independent review; resolve safety findings.
- [ ] 3.2 Merge through CI, deploy, verify deployed-SHA containment and authenticated public canary with asserted handles.
- [ ] 3.3 Prove two independently authenticated app users can connect, deliver a file and process it, plus unauthorized/invalid/replay/revoked outcomes, through normal conversation.
- [ ] 3.4 Sync shipped specs, record rendered proof, update the goal stage table and archive the completed slice without closing unfinished broader work.
