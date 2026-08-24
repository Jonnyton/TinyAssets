## 1. Task reconciliation

- [x] 1.1 Add failing tests proving the task planner selects only stale, valid, policy-enabled, legacy-capacity-blocked cloud-class epoch-2 tasks and remains read-only.
- [x] 1.2 Implement the task plan record/planner and `BEGIN IMMEDIATE` cancellation CAS by reusing the existing request-v2 lifecycle with retained payload and reasoned event evidence.

## 2. Runtime reconciliation

- [x] 2.1 Add failing tests proving the runtime planner selects only stale, dead, unclaimed/unleased provisioned cloud-worker runtimes and excludes fresh/foreign/non-cloud rows.
- [x] 2.2 Implement the runtime plan record/planner and `BEGIN IMMEDIATE` retirement CAS by reusing the existing runtime lifecycle.

## 3. Guarded CLI

- [x] 3.1 Add failing CLI tests for default/explicit dry-run, stable output/digest, required apply guards, digest mismatch, count mismatch, and zero writes before successful apply.
- [x] 3.2 Implement `python -m tinyassets.runtime_reconcile stale-fleet` with canonical plan output, exact pre-mutation guards, and explicit nonzero failures.

## 4. Verification

- [x] 4.1 Run the requested focused pytest and Ruff commands, rebuild and verify the Claude plugin mirror, inspect the diff for `DELETE`/scope drift, and resolve independent review findings without committing or pushing.
