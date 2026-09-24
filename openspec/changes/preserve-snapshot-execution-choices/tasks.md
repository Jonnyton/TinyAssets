## 1. Correct snapshot identity

- [x] 1.1 Reproduce field loss and approve minimal compatibility-preserving shape before code.
- [x] 1.2 Implement conditional preservation and production-sensitive focused regressions.
- [ ] 1.3 Run focused tests, mirror, independent root review and required CI.

## 2. Persist and author the choices

- [x] 2.1 Reproduce the storage/build/patch/fork gaps and get the storage-shape plus validation design reviewed before code (`output/execution-choice-authoring-result.md`, `output/execution-choice-design-result.md`).
- [x] 2.2 Add the additive nullable `default_llm_policy_json` / `concurrency_budget` columns with the PRAGMA-probed migration, the 22-column insert and the guarded row read; prove legacy rows unchanged.
- [x] 2.3 Read both choices in `_staged_branch_from_spec` by resolving key PRESENCE (top-level wins even when null, then nested `graph`, null clears rather than re-inheriting -- root correction; `_spec_get` is not reused because it falls through on explicit null), inherit both in the fork block, and echo the applied values in the build receipt.
- [x] 2.4 Add `set_default_llm_policy` and `set_concurrency_budget` to the existing patch op table on the `set_io_manifest` pattern (`null` clears; unknown ops still refuse) and echo the applied values.
- [x] 2.5 Validate `concurrency_budget` as `type(...) is int and > 0` matching `run_input_runtime`, with no structural ceiling, and surface both choices on the read/describe text.
- [x] 2.6 Rewrite the 22 diagnostic assertions in `tests/test_branch_execution_choice_authoring.py` into capability assertions: **29 of the 45 cases verified RED against `ff1320d5`, 16 GREEN there** (the deliberate compatibility pins — unknown-op refusal, legacy-row absence, unset snapshot form, unknown-spec-key tolerance, the validator unit checks); not every assertion is red-first and the module docstring says which. Rebuild the plugin mirror.
- [x] 2.7 Add `TestLegacyDatabaseMigration` (6 cases): a real pre-`ff1320d5` SQLite `branch_definitions` table migrated in place — every old field preserved, new columns NULL, re-running the migration idempotent, the migrated install then storing and clearing both choices — plus the old-writer boundary regression the design promises (the 20-column `INSERT OR REPLACE` erases the two columns it does not name). Not executed against `ff1320d5`; no red-first claim.

## 3. Release and acceptance

- [ ] 3.1 Deploy and verify protected revision/public canary.
- [ ] 3.2 Verify saved choices through an ordinary app-agent conversation, sync specification and archive after acceptance.
