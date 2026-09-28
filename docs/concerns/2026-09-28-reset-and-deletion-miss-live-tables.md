---
severity: P2
title: Scoped reset refuses on live tables it does not classify, and account deletion cannot remove fleet background attempts
filed: '2026-09-28'
summary: 'scoped_reset blocks on any main-DB table not in MAIN_DB_TABLE_CLASSIFICATIONS, and at least 17 live tables are missing; account deletion hits a FOREIGN KEY RESTRICT on background_branch_attempts for any owner holding fleet-era bindings (10 rows in production)'
---

# Scoped reset refuses on live tables it does not classify, and account deletion cannot remove fleet background attempts

**Filed:** 2026-09-28, by the gpt-6-astra refute round on plan C1 (the
fleet-era pump retirement). Both halves predate C1. C1 classified the retired
fleet tables and `automation_activations`, but that alone does not unblock a
reset.

## 1. Scoped reset

`scoped_reset.inspect_reset_scope` raises "unclassified tables block scoped
reset" for any main-DB table missing from `MAIN_DB_TABLE_CLASSIFICATIONS`.
Codex reproduced this by initializing the real stores into the reset fixture.
The following are still unclassified:

- `assigned_queue_refusals`. The consumer writes it on every poll.
- `agent_definitions`, `agent_bindings`, `agent_component_lineage`,
  `universe_app_ui`. These come from custom_agents.
- `provider_assignments`, `provider_assignment_candidates`,
  `served_provider_budget_reservations`.
- `provider_work_bindings`, `provider_work_execution_claims`,
  `provider_work_receipts`, `provider_invocation_reservations`,
  `universe_model_preferences`.
- The credential custody, deposit-owner and refresh-state tables.

If production's `/data/.tinyassets.db` holds any of these, and a serving
universe must hold several of them, scoped reset cannot run there today.

**What would close it:** read the production table list once, then classify
every table it contains. Many of these hold a user's own configuration or
credentials, so "preserve" is not automatically right: each needs a decision
between reset_home and preserve. Add a test that initializes every main-DB
store and asserts `inspect_reset_scope` succeeds, so the gate catches the next
table.

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
