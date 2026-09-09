# Bounded attributable storage observations

September 8 PDT / September 9 UTC, 2026. This is an enabling measurement slice,
not completion of the user's simpler resource system or owner acceptance.

## Scope and implementation

[PR #3568](https://github.com/Jonnyton/TinyAssets/pull/3568) merged as
`cb74e2165f213205186437eade310b710c410c76`. Existing admin-only resource status
adds a bounded metadata footprint: permanent workspaces, provider runtime, other
universe files and scratch/quarantine attributed by current lease records.
It uses canonical no-follow descriptor traversal, bounded existing TTL memo and
existing read-only lease authority. No paths/content/private IDs are returned.
Partial and unsupported reads stay explicit. Complete attributed storage remains
unavailable; shared-root overhead and billing attribution are not invented.
No quota, ledger, migration, workflow, account-pooling or pricing change.

## Review and verification

- Independent Claude pre-build shape ADAPT resolved before implementation;
  exact-head review APPROVE for `bf39c4478bb368fd5724270e8a151e3295957cbf`.
  [Approval and nonblocking follow-ups](https://github.com/Jonnyton/TinyAssets/pull/3568#issuecomment-5595344630).
- Windows/Python 3.14: `python -m pytest -q tests/test_storage_observations.py
  tests/test_resource_usage_status.py tests/test_ttl_memo.py tests/test_api_status.py
  tests/test_get_status_primitive.py tests/test_workspace_fs.py` gave
  **117 passed, 66 skipped**. Explicitly not POSIX proof.
- Ubuntu/Python 3.11 [34306784859](https://github.com/Jonnyton/TinyAssets/actions/runs/34306784859):
  required and slow jobs passed. Downloaded required JUnit and compared exact
  affected identities against baseline 34305496977: **181 passed, two unchanged
  Windows-only skips**. All 27 new tests (21 POSIX-specific) and the new current
  admin-cache regression passed; no removed test, new failure or new skip.
- Actual candidate checkout `2c321ed57e1225b4d42f2468c0023295b7c7a268` has the
  identical complete tree to approved bf39c447. Actual baseline checkout
  `1733ffa47a0dc5fca7edbe4a39be479b3bb3229c` equals base 20ae3883. Both verified
  with `git diff --exit-code` after fetching the logged checkout commits.
  [Full comparison](https://github.com/Jonnyton/TinyAssets/pull/3568#issuecomment-5595397012).
- Ruff, plugin rebuild/import/mirror checks, strict OpenSpec validation, scope,
  invariants, build-smoke and Linux/macOS/Windows packaging passed.

The Linux route was authorized because local Docker failed before tests; no
host repair, test weakening or production test workload substituted for it.

## Deployment and acceptance

Image build 34307787375 succeeded; [automatic deploy 34308081219](https://github.com/Jonnyton/TinyAssets/actions/runs/34308081219)
completed SUCCESS at **2026-09-09 03:42:33 UTC** (September 8, 20:42 PDT).
Inspected its actual steps and log using `gh run view 34308081219 --json
status,conclusion,headSha,jobs` and `gh run view 34308081219 --log`:

- Fail-safe immutable-image deploy and health verification passed.
- Authenticated `python scripts/mcp_public_canary.py --url
  https://tinyassets.io/mcp --assert-handles` passed.
- Authenticated `python scripts/deployed_sha.py --url https://tinyassets.io/mcp
  --assert-contains cb74e2165f213205186437eade310b710c410c76` reported
  `SHIPPED (per receipt)` at **03:42:31.6721450 UTC**, with production revision
  cb74e2165f21 containing the requested commit. Credentials stayed in CI.

The bounded feature is **deployed and ready for owner testing**. These gates do
not prove actual rendered feature use, complete storage attribution or acceptance.
No in-app prompt or user-workflow action has been taken. Owner retains rendered
testing/acceptance; no post-fix organic-use evidence is claimed.

Remaining resource consolidation and actual attribution/enforcement gaps stay in
the [existing concern](../concerns/2026-09-08-workspace-hourly-cap-stalls-light-use.md).
