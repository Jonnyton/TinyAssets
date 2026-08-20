# Deploy pipeline rewrite: fail-safe swap replaces the stop-writer fence

**Date:** 2026-08-20 · **Host directive:** "solve the wedged deploy pipeline —
it's not working unless it's working 24/7 without this computer; that's a hard
rule." Chose the clean rewrite (option a) over patching the fence.

## What was broken

`deploy-prod` failed on **every run since 2026-08-10**, and each failure left
production with **zero containers** (full outage). Root cause (independently
confirmed by Codex):

1. **Fence-first, fail-stopped.** The `retire-cheat-loop` stop-writer fence
   quiesced prod *before* proving the new image. On any preflight failure the
   restore couldn't run — it read write-ahead state from a *foreign* run
   (`current_run_matches=false`) and `STOP_WRITER_CLEANUP_SAFELY_FENCED=true`
   meant cleanup actively *enforced* the outage.
2. **Obsolete.** The fence guarded a multi-container writer fleet
   (`tinyassets-worker-*`) retired 2026-06-25. Only the daemon + sidecars remain.
3. **exit-2 tuple bug.** The rollback step emitted `rollback_reason` from empty
   state *before* cleanup mutated production, so the terminal receipt saw
   `production_mutation_started=true` + `pre_host_write_failure` →
   `deploy_terminal_receipt.py` raised "contradictory rollback_reason tuple".
4. **Reboot re-fence.** `tinyassets-recovery-reconcile.service`
   (`Before=tinyassets-daemon`) re-ran the old fence on boot from stale state.

## The replacement

`deploy/deploy_fail_safe.sh` — a single-daemon fail-safe swap that **never
leaves prod at zero**:

```
flock -> record current image -> pull new -> prove it loads (ephemeral, no
volume/net) -> swap TINYASSETS_IMAGE + restart -> health-check (fail-fast on
terminal states, tunnel-up required) -> roll back to the recorded image if
unhealthy
```

The workflow (`.github/workflows/deploy-prod.yml`) wraps it: resolve image +
verify the target descends from the stop-writer floor → run the script → public
`--assert-handles` canary → roll back if the public surface is red → publish
`release-state.json`. Worst case restores the previous healthy image; compose
`restart: unless-stopped` + systemd `Restart=always` are the backstop.

## Codex review findings folded in

Hardened per Codex's adversarial review: shared host-mutation `flock` (#7),
cloudflared-up gate before acceptance (#8), fail-fast health probe with a
validated timeout and no bare-`running` fallback (#12). Disabled the boot
re-fence unit (#13).

## Known follow-ups (documented, not silently dropped)

- **Slack-agent** is profile-gated, outside the swap/rollback (#9) — separately
  managed; a code deploy leaves it on its prior image. Needs its own recorded
  transaction + a socket heartbeat before automating.
- **Public canary depth** (#10): the compose runtime healthcheck is a local MCP
  `initialize`; the workflow adds the public `--assert-handles` gate, but a
  broader converse/auth canary would catch more.
- **Data migrations** (#11): an irreversible startup migration on `/data` can
  make an image-only rollback insufficient. Startup migrations must stay
  additive/backward-compatible; a data snapshot/forward-recovery contract is the
  durable fix.
- **True zero-downtime** (blue/green) would remove the brief recreate window; not
  required by the never-zero-containers invariant.

## Proof

Validated live on prod 2026-08-18: guards refuse bad input with zero mutation;
happy path (pull → prove-load → swap → restart → healthy + tunnel up) exits 0;
a real deploy advanced prod from a 7-day-stale image to current `main`
(`fe1aaf32`), canary green with `--assert-handles`.
