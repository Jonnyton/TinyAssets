# Independent shape review and disposition

2026-09-08, local Windows worktree, Claude subscription peer via
`python scripts/peer_agent.py claude --out output/platform-resource-shape-review-claude.md --prompt-file output/platform-resource-shape-review-brief.md --timeout 600`.
The peer completed successfully. Its substantive response was recovered from
the same invocation's session transcript when its stop-hook replaced the wrapper's
final text. Verdict: **ADAPT**. This is shape review, not approval of subsequent code.

## Adopted

- The proposed new accounting ledger, policy epochs and historical import were
  overbuilt for the observed duplicate starts gate. Reuse existing stores.
- Remove the independent workspace jobs/hour refusal at both admission sites,
  rather than choosing another unexplained larger number. Preserve observations.
- Preserve rolling transfer bytes, lease/pool/storage guards, ownership, locks
  and outbox cleanup. No migration or quota reset.
- Use the existing authorized status seam for observations. Unknown is not zero;
  status must not initialize or migrate the stores it reads.
- Keep broader storage attribution and host-global capacity as explicit open
  work, not implied completion of the owner's simplification request.

## Qualifications / structured disagreement

- **DISAGREE_EVIDENCE:** a quarantined tree's retained size does not establish
  failed network transfer bytes. `workspace_pool` reserves transport maximums;
  interrupted checkout can have transferred compressed or discarded data. Do
  not reconcile an unknown transfer to a small retained tree.
- **DISAGREE_EVIDENCE:** workspace and terminal run records are not necessarily
  one atomic database. The production incident read found universe-local leases
  and root-level terminal run rows. This slice preserves that shape and makes
  no stronger atomicity claim.
- **DISAGREE_EVIDENCE:** existing activity is not just one admitted run: the
  admissions ledger also counts engine mutations. Status must name its actual
  units and scope, not silently change policy or imply all entry-point coverage.
- **DISAGREE_CONCERN:** host-global semaphores and total-storage enforcement need
  separate shape/authority review; neither is implemented by a usage projection.

## Remaining gate

The revised implementation needs focused tests, Linux evidence, independent
exact-head code review, required CI, deployment receipt and coordinated rendered
app-owned continuation. Patches and owner acceptance remain open.
