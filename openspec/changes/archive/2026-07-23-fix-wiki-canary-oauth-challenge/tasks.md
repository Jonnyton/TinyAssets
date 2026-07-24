## 1. OAuth-challenge canary contract

- [x] 1.1 Add failing focused tests for 401-with-challenge success and all write-gate failure shapes.
- [x] 1.2 Accept only the chained HTTP 401 with a non-empty OAuth challenge and preserve the persisted read check.

## 2. Workflow diagnostics and specification

- [x] 2.1 Invoke the wiki canary in GitHub Actions output mode while retaining captured diagnostic output, with a workflow regression test.
- [x] 2.2 Record the uptime-and-alarms delta requirement and deliberately leave main-spec sync and archive for independent review.

## 3. Verification

- [x] 3.1 Run focused tests, ruff, strict OpenSpec validation, and an available actionlint check.
- [x] 3.2 Run the live direct canary and inspect the scoped diff before independent review.
