# The stop-writer fence is armed by nothing and guarded by three workflows — finish retiring it

**Filed:** 2026-08-27 (as "recovery path deleted with the fence still armed") · **Re-scoped:** 2026-08-29
**Severity:** P3 — no longer an outage class; it is dead machinery with three live call sites

## What changed on 2026-08-29

The droplet's fence state `/var/lib/tinyassets-deploy/retire-cheat-loop-task-2-1-fence.json`
had sat at `phase: unsafe_fenced` (run `32420885315-1`, last written 2026-08-20 21:46 — the day
#2442 deleted the recovery job) while production was deployed many times through
`deploy/deploy_fail_safe.sh`, which never consults the fence. `guard-host-mutation` refused on
that stale phase, so `install-host-services.yml` failed on every run since.

Done (host actions, read-only inventory first — Hard Rule 13):
- Residue check: daemon unit enabled, no masked units, every container `restart=unless-stopped`.
- The stale state file was archived to
  `retire-cheat-loop-task-2-1-fence.json.archived-stale-20260829T222720Z` (mode 600) and removed,
  so the guard falls through to its own `clean_absence` residue rule.
- `tinyassets-watchdog.timer` (public-canary watchdog, `scripts/watchdog.py`: restart after 3
  consecutive canary reds with a restart floor) re-enabled; first tick clean.
- `daemon-watchdog.timer` (heartbeat watchdog, `deploy/daemon-watchdog.sh`) is deliberately still
  disabled: it restarts the daemon when the freshest `<universe>/.worker_supervisor*.json` is
  older than 900 s, and the consumer only wrote those beats while a fleet-era runtime row
  matched (none does since the IdP subject migration; newest beat 06:00 UTC). It is re-enabled
  once the consumer beats unconditionally (`user-owned-automations` 3.2 lands) — until then the
  guard reports that timer as residue and the installer stays red.

## What remains (the actual concern now)

Nothing arms the fence any more: no workflow calls `prepare-deploy` / `quiesce-unsafe` /
`recover-unsafe`. Three workflows still stage the 5k-line script and call `guard-host-mutation`
before host mutation (`install-host-services.yml`, `p0-outage-triage.yml`,
`restart-daemon.yml`), four support files are orphaned (`deploy/recovery-restart-no.yml`,
`deploy/tinyassets-recovery-reconcile.service`, `scripts/validate_host_runtime_hmac_pair.py`,
`scripts/validate_agent_interchange_hmac.py`), and `tests/test_retire_cheat_loop_deploy_fence.py`
carries 17 of the `heavy-tests` failures. Option 2 of the original concern — finish
`retire-cheat-loop` task 2.5a — is the only coherent end state: replace `guard-host-mutation`
at the three call sites with the residue check alone (masked units / `restart=no`), delete the
script, the orphans, the host artifact under `/opt/tinyassets/deploy/`, and the test file, in
one PR with a Codex refutation.

## Resolving

Delete this file when the three call sites no longer stage the fence script and
`tests/test_retire_cheat_loop_deploy_fence.py` is gone.

## One more reason to finish 2.5a: the dormant paths still classify consumers (2026-08-29)

PR #2685 adopted production's `tinyassets-data:/data:ro` mount into
`deploy/compose.yml`'s `slack-agent` block, and the surrounding comment claimed
that made the service liable to be stopped or removed by
`retire_cheat_loop_deploy_fence.py`. **That claim was wrong, and the comment has
been corrected.** Codex checked the call graph: `install-host-services.yml:69`,
`restart-daemon.yml:68` and `p0-outage-triage.yml:82` all invoke only
`guard-host-mutation`, which checks unresolved fence state and `restart=no`
residue (`retire_cheat_loop_deploy_fence.py:2114`). It neither classifies extra
volume consumers nor stops or removes anything. The read-only mount is safe
under every workflow that runs today.

The classification and destruction live in the dormant commands instead:
`quiesce_unsafe` inventories and stops **all** volume consumers (`:2237`,
`:2330`), removing an extra one needs
`recover-unsafe --retire-extra-consumer <exact-name>` (`:3169`, `:3251`), and
canonical stopped-fleet removal happens only inside recovery (`:3556`, `:4408`).
None of that is reachable from a workflow — but the legacy boot reconciler can
still quiesce consumers while recovering an old non-terminal fence state.

So the mount is not a live hazard; the machinery that would treat it as one is
simply asleep with no way to be woken deliberately. That is the same defect this
concern already describes from the other direction — an armed fence with its
exit deleted — and it strengthens option 2 above: finishing 2.5a removes the
classifier along with everything else, and with it the question of whether a
read-only consumer is legitimate.
