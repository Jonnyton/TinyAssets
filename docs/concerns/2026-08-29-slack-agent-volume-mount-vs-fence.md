# `slack-agent` now mounts the production volume the fence exists to keep empty

**Filed:** 2026-08-29
**Verified:** 2026-08-29 (repo read; the live droplet fact is second-hand, see below)
**Severity:** P2 — latent, not live. `slack-agent` is profile-gated and no deploy
converges it, so nothing is mounting the volume right now.

## What changed

PR #2685 makes `deploy/compose.yml` authoritative on production again (the sync
PR #2442 dropped, restored inside the fail-safe transaction). Production had
drifted ahead of the repo, so the deploy would have *reverted* two live
`slack-agent` directives. Per the build brief they were adopted into the repo
instead, keeping the durable definition equal to what production ran:

```yaml
    entrypoint: ["/usr/bin/tini", "--"]
    volumes:
      - tinyassets-data:/data:ro
```

## The conflict

`deploy/compose.yml`'s own comment on that service says the mount *could not
survive*:

> It used to read each universe's vault off the data volume. That could not
> survive: `retire_cheat_loop_deploy_fence.py` deletes any container mounting
> that volume outside the canonical five, and it did so six times between 03:36
> and 04:25 UTC on 2026-08-06 while failing two production deploys. The
> invariant is structural, not an allowlist gap — several fence call sites
> require the consumer set be EXACTLY the five and four require it be EMPTY
> during removal, and Docker labels are self-asserted so a label-gated allowlist
> is forgeable by the writer the fence exists to catch.

That fence is still armed. `scripts/retire_cheat_loop_deploy_fence.py` knows
`EXPECTED_CONTAINERS = ("tinyassets-daemon",)` plus `CANONICAL_SIDECARS`
(`tinyassets-tunnel`, `tinyassets-logs`); anything else holding `tinyassets-data`
is an `extra_volume_consumer`, and the script raises
`FenceError("extra production-volume consumer was fenced; refusing deployment")`.
It is invoked by `.github/workflows/install-host-services.yml`,
`p0-outage-triage.yml` and `restart-daemon.yml` — **not** by `deploy-prod.yml`,
which is why this is latent rather than an outage.

The trigger is: someone starts `slack-agent` (`docker compose --profile slack up
-d --no-deps slack-agent`, the documented way to enable a user's Slack
workspace) and then any of those three workflows runs. The fence stops/removes
the container, or refuses the operation outright.

`:ro` does not exempt it. The fence matches on the mount's volume `Name`
(`retire_cheat_loop_deploy_fence.py:458`), not on write access.

## What is not verified here

The live-droplet facts — that `/opt/tinyassets/compose.yml` carries these two
lines today, and that a separate `/opt/tinyassets/compose.slack.yml` exists —
come from a host-run diff on 2026-08-29 reported in the build brief. This
session cannot SSH to the droplet and did not re-check them. If that diff was
wrong, the adoption above is unnecessary and the cheapest resolution is to drop
the mount from `deploy/compose.yml`.

## The decision this needs

One of:

1. **Widen the fence.** Add `tinyassets-slack-agent` to the canonical consumer
   set. Requires a read-only-consumer concept the fence does not have today —
   several call sites require the set be EMPTY during removal, so this is not a
   one-tuple edit.
2. **Drop the mount from production.** Revert the two adopted lines and let the
   next deploy install a `slack-agent` without them, accepting that whatever
   added them on the droplet had a reason nobody has written down.
3. **Leave it latent and gate the start.** Document that starting `slack-agent`
   is incompatible with the three fence workflows until (1) or (2) lands.

Nothing in this repo records *why* production grew the mount, which is the fact
that decides between (1) and (2). Resolve by deleting this file.
