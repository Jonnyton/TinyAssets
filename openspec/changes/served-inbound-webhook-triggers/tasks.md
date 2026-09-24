# Tasks: served-inbound-webhook-triggers

## 1. Build
- [x] 1.1 Served `write_graph target=webhook` create/revoke and `read_graph target=webhooks`
      (`tinyassets/engine_mcp_server.py`, `tinyassets/served_tools.py`).
- [x] 1.2 `webhook_hooks.revoke_by_prefix` plus `revoke_webhook` token_prefix
      (`tinyassets/storage/webhook_hooks.py`, `tinyassets/api/webhook_ops.py`,
      `tinyassets/api/extensions.py`).
- [x] 1.3 `next_due_at` in the automation projection (`tinyassets/automations.py`,
      `tinyassets/api/automations.py`).

## 2. Prove
- [x] 2.1 `tests/test_served_webhook_triggers.py` (13) and `tests/test_automation_next_due.py`
      (10). Both are red on the unfixed tree and green after the change. A mutation that
      removes universe confinement in `revoke_by_prefix` turns the cross-universe test red.
- [ ] 2.2 Cross-family review (Tier 2), owed.
- [ ] 2.3 Deploy, then `python scripts/deployed_sha.py --assert-contains <sha>`.
- [ ] 2.4 Live acceptance through the app (steps in the PR body): a schedule fires on
      time and a webhook POST runs as the owner, both with no host online.

## 3. Land
- [ ] 3.1 Sync the deltas into `openspec/specs/`, then archive this change.
