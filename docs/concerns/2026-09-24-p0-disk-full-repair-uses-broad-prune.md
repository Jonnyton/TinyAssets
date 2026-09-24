# P0 disk-full repair still runs a broad `docker system prune -af`

**Filed:** 2026-09-24 (while building count-based daemon image retention, PR #3960)
**Verified:** 2026-09-24, `.github/workflows/p0-outage-triage.yml` step `Repair — disk full (docker prune + journalctl vacuum)` at origin/main `9c11050f`
**Severity:** P2

## Source (verbatim)

```
# --- Repair branch 3: disk full ----------------------------------
# docker system prune -af reclaims dangling images/containers/cache.
# tinyassets-prune.timer runs this weekly, but P0 disk-full is an
# emergency fire. Journalctl vacuum trims old log state too.
...
docker system prune -af 2>&1 | tail -20
journalctl --vacuum-time=3d 2>&1 | tail -5
```

## Why it matters

- On the production containerd image store, `-a` removes every image that no container uses. That
  includes the rollback images that the bounded retention path deliberately keeps (the canary-rollback
  target and one spare). Rollback then needs a re-pull of about 2.7 GB, and that happens during a
  disk-full P0.
- The comment is wrong twice. `tinyassets-prune.timer` never ran a system prune: it runs the bounded
  registry-verified retention. It is also daily now (PR #3960), not weekly.

## Mitigating facts

- The step only runs when triage has already classified the incident as disk full, so production is
  probably already down.
- Removed daemon images can be re-pulled from GHCR by digest.
- Count-based retention after every deploy (PR #3960) should make this branch much rarer.

## Resolution sketch

Replace the broad prune with `systemctl start tinyassets-prune.service`, which runs the same keep set.
Add a narrower fallback only if the rule cannot free space. Update the comment at the same time.
