# Tasks: request-registers-a-once-wake

## 1. Build
- [ ] 1.1 `_action_admit_request_v2` registers a `once` wake of the loop branch for the owner; refuses a non-owner with `request_owner_only` and a set retired field with `request_field_retired:<field>` (`tinyassets/api/universe.py`).
- [ ] 1.2 The admission ledger names the wake's `automation_id` and keeps replay (`tinyassets/storage/request_admissions.py`).
- [ ] 1.3 Migration: every pending request-admission task becomes `refused` with `request_retired_to_wake`.
- [ ] 1.4 Guidance rows in `tinyassets/api/prompts.py`.

## 2. Prove
- [ ] 2.1 Tests through the real pump: the owner's request runs the loop once with the text as input; a replay does not wake twice; a non-owner is refused; a retired field is refused; the migration records the reason and keeps the row.
- [ ] 2.2 Mutation-check the owner gate and the idempotency.
- [ ] 2.3 gpt-6-astra refute round: cross-user spend and a double wake.
- [ ] 2.4 Deploy; `python scripts/deployed_sha.py --assert-contains <sha>`; `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`.

## 3. Land
- [ ] 3.1 Sync the delta into `openspec/specs/user-owned-automations/`, archive.
