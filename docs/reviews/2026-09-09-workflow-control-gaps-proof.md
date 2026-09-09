# Workflow controls: deployed technical proof, app retest pending

September 9, 2026 UTC / September 8 PDT. Implementation PR #3591; reviewed head
436f72b8370e6cfbff00184b5f0a0a63f75dc0df; merged and deployed revision
0082695793278fabf520c9bf2a8fa2694c4a2823.

## Scope and independent evidence

Correct update_node guidance, trusted workspace ancestry, exact bounded run
output, graph-instance failure events and exposed cooperative cancellation.
Existing scope/ACL checks remain authoritative; cancellation is owner-write
control, not new execution authority. No private workflow edits or new ledger.

Claude shape review ADAPT was incorporated; full runtime review approved 41df8819.
Follow-up exact-head review approved 436f72b8, verified identical runtime/mirror,
and ran two lifecycle tests. Full receipts:
https://github.com/Jonnyton/TinyAssets/pull/3591#issuecomment-5596516658
https://github.com/Jonnyton/TinyAssets/pull/3591#issuecomment-5596798037.

Linux run 34317601056 required-tests and slow-tests passed. Actual checked-out
merge e570f22e7f2eef65299849b76fb2dd3e7f80e554 has identical runtime, mirror and
tests to 436f72b8; three unrelated Play documents differ. Focused comparison:
441 passes/two Windows-only skips versus 390+2 at baseline, no new failures or
lost passing focused cases. Full required artifact retains the same nine
failures/two collection errors as baseline's existing ledger; not a fully green
repository-suite claim. Heavy tests omitted by the existing PR policy are not
claimed as candidate Linux coverage. Commands and complete evidence:
https://github.com/Jonnyton/TinyAssets/pull/3591#issuecomment-5596933164.

## Deployment evidence

`gh run view 34318730934` shows image publication success at 06:25:30Z.
`gh run view 34318999188 --json status,conclusion,jobs` shows deployment success
at 06:26:38Z. Actual deploy job 102361270235 log confirms:

- Fail-safe deployment/health step succeeded; no rollback needed.
- Authenticated `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles` succeeded at 06:26 UTC.
- Authenticated `python scripts/deployed_sha.py --url https://tinyassets.io/mcp --assert-contains 0082695793278fabf520c9bf2a8fa2694c4a2823` reported SHIPPED at 06:26:34Z.
- Immutable digest: sha256:4f745bf9437271a4771799f56aeea2b1ced53ffc439685e7ca20780335424450.

Credentials remained in CI. Deployment receipt:
https://github.com/Jonnyton/TinyAssets/actions/runs/34318999188.
Rollback is a reviewed revert/redeploy of the implementation, with no migration
or deletion of user workflows/runs.

## Rendered acceptance remains open

Sent exactly `Retest your workflow checklist` through the existing signed-in
https://tinyassets.io/mcp/app conversation. Verified full rendered user message
at Sep 8 23:27 PDT; app is thinking. No acceptance result yet. One controlled
mission tab, no operator workflow edit, new grant or coaching prompt.
Log: output/user_sim_session.md. This is existing-owner webapp continuation,
not first-contact or cross-client compatibility proof.

No post-fix organic user exercise of these five controls is visible yet. Keep
docs/concerns/2026-09-08-app-read-write-sweep-gaps.md and the change acceptance
tasks open until rendered evidence establishes closure. The broader concurrency,
activity and retained-space limit simplification remains unfinished regardless
of this slice's eventual acceptance.
