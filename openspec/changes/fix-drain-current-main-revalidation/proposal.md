## Why

The local drain exhausted its failure budget after two valid `NO_CANDIDATE`
results. Pre-dispatch admission fetched and classified `origin/main`, while
post-result validation classified the controller worktree's detached
`STATUS.md`, which was 13 commits behind and still contained a retired claim.
The two gates therefore disagreed about work that did not exist on current
main and stopped an otherwise healthy controller.

The ensuing graceful restart exposed a second liveness defect: after the old
supervisor exited terminally, the watchdog selected a fresh run, deleted the
restart marker, then rediscovered the terminal run and overwrote that decision.

## What Changes

- Fetch `origin` before post-result claim-pressure validation.
- Classify `origin/main` explicitly, matching pre-dispatch admission.
- Regression-lock the fetch and `--status-ref origin/main` command contract.
- Preserve an explicit fresh-run decision across graceful supervisor shutdown.

## Impact

- A stale detached controller checkout can no longer create false
  `INVALID_NO_CANDIDATE` strikes.
- Real claimable, stale, or exact-identity-owned work on current main remains a
  rejection exactly as before.
- An explicit restart no longer leaves the signed-in drain terminally down.
