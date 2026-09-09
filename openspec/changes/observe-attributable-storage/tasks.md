## 1. Shape

- [x] 1.1 Record proposal/design and independent cross-family shape/basic-safety review; resolve blocking approach findings.

## 2. Implement and verify

- [x] 2.1 Implement bounded metadata sampler with existing descriptor helpers and memo, scoped lease attribution, explicit coverage and no data writes.
- [x] 2.2 Wire additive admin-only status and test cache authorization, privacy, hard links, races, missing data and traversal bounds; rebuild plugin.
- [ ] 2.3 Run focused Windows and Linux proof, compare affected outcomes, obtain exact-head independent approval and required CI.

## 3. Deliver

- [ ] 3.1 Deploy with authenticated public canary/revision proof and synchronize shipped spec; report readiness only.
- [ ] 3.2 Record owner-provided rendered acceptance before closure; no autonomous app prompt or production load test, broader simplification remains open.

2026-09-08 Windows/Python 3.14: focused six-file suite (`test_storage_observations`,
`test_resource_usage_status`, `test_ttl_memo`, `test_api_status`,
`test_get_status_primitive`, `test_workspace_fs`) = 117 passed, 66 skipped.
This is portable/cache/status evidence ONLY: new traversal and existing POSIX
filesystem cases are skipped here and must pass the authorized Linux CI route.
Ruff, plugin rebuild/import probe, strict OpenSpec validation and diff check pass.
