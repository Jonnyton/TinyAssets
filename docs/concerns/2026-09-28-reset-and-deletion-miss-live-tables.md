---
severity: P2
title: Scoped reset refuses on live tables it does not classify, and account deletion cannot remove fleet background attempts
filed: '2026-09-28'
summary: 'scoped_reset blocks on any main-DB table not in MAIN_DB_TABLE_CLASSIFICATIONS, and 35 of production''s 84 tables are missing (host read 2026-09-28); account deletion hits a FOREIGN KEY RESTRICT on background_branch_attempts for any owner holding fleet-era bindings (10 rows in production)'
---

# Scoped reset refuses on live tables it does not classify, and account deletion cannot remove fleet background attempts

**Filed:** 2026-09-28, by the gpt-6-astra refute round on plan C1 (the
fleet-era pump retirement). Both halves predate C1. C1 classified the retired
fleet tables and `automation_activations`, but that alone does not unblock a
reset.

## 1. Scoped reset

`scoped_reset.inspect_reset_scope` raises "unclassified tables block scoped
reset" for any main-DB table missing from `MAIN_DB_TABLE_CLASSIFICATIONS`.

Production's `/data/.tinyassets.db` holds 84 tables (host read, 2026-09-28).
After plan C1 classified the retired fleet tables and `automation_activations`,
**35 are still unclassified**. Any one of them blocks every scoped reset in
production today:

- Agents and interchange: `agent_definitions`, `agent_bindings`,
  `agent_component_lineage`, `agent_conversion_receipts`,
  `agent_conversion_receipt_links`, `agent_conversion_receipt_owners`,
  `agent_import_stages`, `agent_interchange_idempotency`, `universe_app_ui`.
- App channels: `app_channel_bindings`, `app_event_admissions`,
  `app_principal_mappings`.
- Providers and credentials: `provider_assignments`,
  `provider_assignment_candidates`, `served_provider_budget_reservations`,
  `universe_model_preferences`, `llm_credential_custody`,
  `llm_credential_deposit_commits`, `llm_credential_deposit_owners`,
  `llm_credential_refresh_state`, `connection_disconnections`.
- Provider work: `provider_work_bindings`, `provider_work_receipts`,
  `provider_work_execution_claims`, `provider_invocation_reservations`.
- Actions and outboxes: `action_approvals`, `action_result_outbox`,
  `action_result_receipts`, `operation_scopes`, `scheduled_work`.
- Webhooks: `webhook_hooks`, `webhook_admissions`, `webhook_deliveries`,
  `webhook_inflight`.
- Consumer: `assigned_queue_refusals`.

**What would close it** (its own lane): classify each table. Per-user-owned
tables need the owner-only rule (`account_deletion.OWNER_ONLY_TABLES`, #4038),
not a blanket "preserve". Many of these hold a user's own configuration or
credentials, so each needs a decision between reset_home and preserve. Then add
a test that initializes every main-DB store and asserts `inspect_reset_scope`
succeeds, so the gate catches the next new table in CI rather than in
production.

## 2. Account deletion

`account_deletion.deletion_plan` derives its tables from principal and universe
columns. `background_branch_attempts` has neither. Its FK to
`background_branch_bindings` is `ON DELETE RESTRICT`, so deleting a universe's
bindings fails with `IntegrityError: FOREIGN KEY constraint failed` whenever
attempts exist. Codex reproduced this with `_seed_claimable_background_path()`
followed by `_delete_root_rows()`. Production holds 10
`background_branch_bindings` rows.

**What would close it:** a host action that drops the fleet tables after plan
C2 deletes their code. Until then, account deletion should delete a binding's
attempts before the binding.
