## 1. Coordination Recovery

- [x] 1.1 Preserve the false-idle evidence and release the 11 claims that the host confirmed belong to closed sessions.
- [x] 1.2 Add the bounded OpenSpec proposal, design, delta requirement, and exact STATUS claim.

## 2. Hard Exhaustion Gate

- [x] 2.1 Add failing tests for the mandatory worker exhaustion order and controller rejection of `NO_CANDIDATE` with claimable or stale rows.
- [x] 2.2 Implement claim-check JSON inspection, bounded semantic rejection, and the strengthened drain-worker brief.

## 3. Governance And Proof

- [x] 3.1 Update AGENTS.md, the drain runbook, and a durable root-cause audit with the false-idle prevention rule.
- [ ] 3.2 Obtain opposite-provider review and pass focused tests, Ruff, strict OpenSpec validation, and a live no-false-idle recovery proof.

## 4. Foldback

- [ ] 4.1 Sync/archive the change, retire its STATUS row, land the PR, update the controller to merged main, and verify the drain claims real work.
