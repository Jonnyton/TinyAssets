# The GitHub App token refresher writes a file the running daemon never re-reads

**Filed:** 2026-08-27
**Severity:** P1 — a 45-minute timer whose output cannot reach the process it
exists to serve
**Verified:** 2026-08-27 against `814b4f06`
**Found by:** Codex cross-family review,
`docs/reviews/2026-08-27-codex-auth-sync-refutation.md` (point 4), then
re-verified independently against the tree.

## The finding

`scripts/github-app-token-refresher.py` mints a GitHub App installation token
every 45 minutes (`deploy/github-app-token-refresher.timer:7`,
`OnUnitActiveSec=45min`) and writes it to the host env file as
`TINYASSETS_GITHUB_PR_CAPABILITIES` (`:97-112`, via
`install-tinyassets-env.sh set`).

**Nothing then tells the daemon.** The chain breaks in three verifiable places:

1. **The refresher never restarts or reloads anything.**
   `grep -nE "restart|reload|systemctl|docker" scripts/github-app-token-refresher.py`
   returns nothing.
2. **The env helper only writes.** `cmd_set` ends at `atomic_install` +
   `assert_readable` + an echo (`deploy/install-tinyassets-env.sh:458-465`).
   No restart, by design — it is a file primitive.
3. **The daemon's environment is a snapshot taken at container creation.**
   `deploy/compose.yml:106-110` passes `/etc/tinyassets/env` as an **`env_file`**,
   not an interpolation, so its contents become the container's static process
   environment when the container is created;
   `deploy/tinyassets-daemon.service:79` only runs `docker compose … up -d`.
   `TINYASSETS_GITHUB_PR_CAPABILITIES` appears nowhere in `compose.yml`, so
   `env_file` is its only route in.

And the consumer reads the **process** environment at call time:
`tinyassets/auth/provider.py:68`, `os.environ.get(env_var, "").strip()`, reached
from `vend_github_destination_secret` (`:101-129`).

So the daemon holds whatever token was in the file when its container was
created, and every subsequent refresh lands in a file that process will never
read again. The refresh takes effect only when something recreates the
container — a deploy, `restart-daemon`, or `apply-daemon-env`.

**A 45-minute cadence is not arbitrary:** GitHub App installation tokens are
short-lived, which is exactly why the timer is that tight. The refresher is
correct about *when* to mint and wrong about *where it lands*.

## A second, independent break in the same unit

`deploy/github-app-token-refresher.service:6` carries
`ConditionPathExists=/etc/tinyassets/github-app-token-refresher.env`, and `:14`
loads the same path as `EnvironmentFile`. Installation only installs and enables
the units (`.github/workflows/install-host-services.yml:404-417`) — **nothing
creates that file.** Absent it, systemd skips the unit silently: no failure, no
log line that reads as an error, and a timer that appears healthy while never
running its payload.

So the refresher may be failing in two independent ways at once, and both are
quiet.

## Why this was recorded as working

I triaged `TINYASSETS_GITHUB_PR_CAPABILITIES` as a clean relocation — the
deploy-workflow assertion was stale *because the capability moved to a systemd
timer*. The timer exists and the script is correct; I stopped at "a delivery
path exists" without following it to the consumer. The cross-family review
followed it one hop further and found the hop is missing.

Recorded because the failure mode generalises: **"the capability moved" is only
half a verification. The other half is that it arrives.**

## Resolving this

Two shapes, per the review's recommendation:

1. **Preferred — make the credential dynamically readable.** Have
   `vend_github_destination_secret` read the capability map from a file or the
   vault at call time instead of `os.environ`, so a refreshed token is picked up
   without touching the container. This also removes the restart entirely.
2. **Otherwise — recreate the daemon under the host-mutation lock** after a
   successful mint, sharing the flock and the `production-host-mutation`
   concurrency group that `deploy_fail_safe.sh` and `apply-daemon-env.yml` take.
   Restarting production every 45 minutes to rotate a token is a poor trade, so
   prefer (1).

Either way, **provision the refresher's own bootstrap credential file** so the
unit stops being skipped, and make a skipped run visible rather than silent.

## Verification when fixed

A green timer is not evidence. Prove the token in the *running process* changes
without a container recreate:

```
docker exec tinyassets-daemon printenv TINYASSETS_GITHUB_PR_CAPABILITIES   # before
systemctl start github-app-token-refresher.service
docker exec tinyassets-daemon printenv TINYASSETS_GITHUB_PR_CAPABILITIES   # after
```

Same value after a successful mint = still broken. This is the same
effectiveness proof `apply-daemon-env.yml` already requires of itself, for the
same reason.
