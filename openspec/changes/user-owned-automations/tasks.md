## 1. Retire the fleet

- [ ] 1.1 Remove the four `worker*` services and fleet env from `deploy/compose.yml`; fetch the droplet's live compose, reconcile, and only then let `deploy-prod.yml` ship the file. Verify: `docker compose config --services` on the droplet lists daemon/cloudflared/logs only; `deployed_sha` green.
- [ ] 1.2 Delete `tinyassets/cloud_worker.py`, `cloud_worker_healthcheck.py`, `.github/workflows/reconcile-stale-fleet.yml`, the `DEFAULT_HOST_USER` import in `fantasy_daemon/__main__.py`; relocate `_worker_model_for_provider` and `supervisor_heartbeat_filename`; update the named tests and `scripts/check_background_authority_inventory.py`, `scripts/retire_cheat_loop_deploy_fence.py`; rebuild the plugin mirror; sync the REMOVED requirements into `daemon-runtime-and-dispatch`. Verify: full pytest + `mirror-parity` green.

## 2. Schedules obey the rule

- [ ] 2.1 Registration requires the authenticated owner with admin ACL, refuses `scheduler_unavailable` when the tick thread is not running, and the run actor is `universe:<id>`. Verify: tests that go red on the old code (anonymous accepted, actor mismatch), then a live registration refusal through the app.
- [ ] 2.2 Split the scheduler lifecycle from `TINYASSETS_INBOUND_ENABLED`; owner pause/delete on the schedule row. Verify: the founder's heartbeat schedule fires on `u-01kxm1vszd8hwp7em418asq8h9` and appears in the run list.

## 3. User-owned automations

- [ ] 3.1 Automation row + owner controls on `write_graph target=automation` (create/pause/resume/delete/list), universe-scoped, authenticated, fail-loud per D4. Verify: tests red→green; live create and list from the app.
- [ ] 3.2 Consumer executes due automations on the CURRENT assignment through the served carrier with foreground admission/budget; `(automation_id, due_at)` fence; recorded refusal per skip; no runtime pin, no enrollment manifest. Verify: restart-survival and provider-switch tests; live run on the founder's universe with a receipt.
- [ ] 3.3 Retire the fleet-era activation layer and the old-principal `cloud_automation_controls` / `background_branch_bindings` (explicit retired rows with reason). Verify: the pump ignores retired rows; refusal table stops growing.

## 4. Prove and close

- [ ] 4.1 Codex refutation of 3.x, live proof through the app (`ui-test`), spec sync, archive this change and `execute-assigned-queue-consumer`.
