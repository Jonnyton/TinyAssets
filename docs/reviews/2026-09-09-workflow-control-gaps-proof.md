# Workflow controls: live retest, one remaining terminal-state issue

September 9, 2026 UTC / September 8 PDT. Implementation PR #3591; reviewed head
436f72b8370e6cfbff00184b5f0a0a63f75dc0df; merged and deployed revision
0082695793278fabf520c9bf2a8fa2694c4a2823.

## Cancelled-node follow-up: reviewed and merged, deployment pending

PR #3599 merged September 9 at 07:05:06 UTC as
ece0a8e25058221143b40859b2050cba0b610ad4. Reviewed head:
c5266c5061d8143b9f87481d00408f541eaba527. Independent Claude code/basic-safety
review completed exit 0 after 239 seconds and independently ran 63 passing tests.
Receipt: https://github.com/Jonnyton/TinyAssets/pull/3599#issuecomment-5597507666.

Linux Tests 34320774044 passed required-tests (14m56s) and slow-tests (1m23s).
Actual checkout 923ddba66c57ba58e9de10903835953bba4aeb63 merges reviewed head with
main58fb86b0. Fetched that exact tree and verified zero difference for all three
changed canonical files, their mirrors and both changed test files. Other merge
changes are #3590's input-method reporting, not overlapping cancellation files.
Required JUnit compared with deployed008 baseline run34318730803: focused
non-heavy selection185 passes versus178; seven added passes, no passing case
lost or made nonpassing. Full required artifact14845 passes/54 skips/9 failures/
2 errors; failure/error identities identical to baseline. Heavy files remain
outside this PR's Linux coverage. Receipt and commands:
https://github.com/Jonnyton/TinyAssets/pull/3599#issuecomment-5597654685.

Build and publish image34322091429 passed at07:09:08 UTC, publishing tag
ece0a8e25058 at digest sha256:d9c446a6c1858e4004acc66b4a385955708c1452ca0c2eb7de3400349a67949c.
Deploy34322420004 attempt1 stopped at immutable-image resolution (exit255)
before SSH or production mutation. Independent `docker buildx imagetools inspect
ghcr.io/jonnyton/tinyassets-daemon:ece0a8e25058` then resolved the same digest.
Retried unchanged through normal guards; first lookup's cause remains unknown.
Incident: https://github.com/Jonnyton/TinyAssets/issues/3602.
Attempt2 succeeded at07:11 UTC. Actual job102372152883 confirms healthy container
at07:11:21, authenticated public canary with --assert-handles at07:11:23, and
authenticated deployed_sha.py --assert-contains ece0a8e25058221143b40859b2050cba0b610ad4
reported SHIPPED at07:11:24.380Z. No rollback; same immutable digest as the build.
Credentials stayed in CI. App acceptance remains pending; next prompt is exactly
the owner's retest text.

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

## Rendered acceptance: four closed, cancelled-node display remains open

Sent exactly `Retest your workflow checklist` through the existing signed-in
https://tinyassets.io/mcp/app conversation. Verified full rendered user message
at Sep 8 23:27 PDT. At 23:30 PDT the app explicitly reported:

> Fixed: workflow editing, output readback, explicit workspace discard, and failed-node status.
> Cancellation works, but a cancelled run still displays its code node as running.

The app built its own temporary receiver and workflow. Through ordinary UI we
approved only POST delivery and DELETE cleanup for its exact receiver, retaining
the existing vault key and leaving the persistent-approval checkbox unchecked.
At 23:31 PDT the app reported delivery HTTP 200, cleanup HTTP 204, deleted its
temporary workflow, and all nine checklist rows passed. Its stated remaining
issue is the cancelled code node still appearing running. All-five completion
therefore remains unproven and requires a platform follow-up/redeploy/retest.
One controlled mission tab; no operator workflow edit or coaching prompt.
Log: output/user_sim_session.md. This is existing-owner webapp continuation,
not first-contact or cross-client compatibility proof.

No post-fix organic user exercise beyond this directed retest is visible yet. Keep
docs/concerns/2026-09-08-app-read-write-sweep-gaps.md and the change acceptance
tasks open until rendered evidence establishes closure. The broader concurrency,
activity and retained-space limit simplification remains unfinished regardless
of this slice's eventual acceptance.
