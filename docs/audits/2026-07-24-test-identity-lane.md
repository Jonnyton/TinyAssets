# Lane report: test-identity-and-reset

Date: 2026-07-24

Branch: `codex/osx-test-identity-reset`

Result: partial — token-safe identity observability shipped to the review
branch; scoped reset correctly stopped at its stale inventory/writer-fence gate.

## Tasks completed

- **3.1** Request-local bearer presence is carried without retaining bearer
  material. `get_status` and `read_graph target=status` now share version-2
  status responses containing a versioned, deployment-scoped HMAC-SHA-256
  principal fingerprint. Missing/short dedicated keys fail closed.
- **3.2** Regression coverage now exercises authenticated, anonymous,
  first-contact, invalid-bearer, alias-parity, request-cleanup, no-ambient-actor,
  raw-subject redaction, and provider credential/auth-home redaction behavior.
- **3.3 (workflow portion only)** Canonical and mirrored `ui-test` instructions
  now require rendered status identity evidence and forbid cookie/UI inference
  or durable raw identifiers.
- Minimum safe preparation for **2.1–2.2** is documented in
  `docs/ops/test-identities.md`, including private roster constraints,
  deployment key requirements, and the two-client proof procedure.

## Skipped as already landed

- None. Premise verification found identity observability and scoped reset
  absent on the starting tree.

## Skipped or blocked

- **1.1 — live but blocked.** The approved deletion inventory is stale against
  current main. New `request_admissions`, `branch_tasks_v2`,
  quarantine/maintenance/rollout, and execution-authority evidence stores are
  unclassified. No durable affected-scope fence is enforced by every database
  and filesystem writer.
- **1.2 — live but blocked by 1.1.** A partial read-only plan would look
  authoritative while omitting new stores and has no trustworthy inventory
  revision or completed-plan receipt contract.
- **1.3 — live but blocked by 1.1–1.2.** Per the OpenSpec pre-implementation
  gate, no mutating scoped-reset apply was written. `tinyassets/reset.py`
  remains the existing global confirm-gated operation, with no MCP/API/user
  route added.
- **1.4 — live but blocked by 1.1–1.3.** There is intentionally no scoped
  apply/recovery implementation to mutate or fault-inject yet.
- **2.1 — host action.** Two real WorkOS users and their private alias mapping
  require authorization-server/operator access. No fake subjects or committed
  roster were substituted.
- **2.2 — blocked.** Requires host provisioning, deployment of
  `TINYASSETS_IDENTITY_FINGERPRINT_KEY`, completed reset tasks, and rendered
  Claude.ai plus ChatGPT runs.
- **3.3 — partially blocked.** Public canary, rendered host matrix, concurrency
  proof, and post-fix clean-use evidence cannot truthfully run before deployment
  and the dependencies above.
- Broader provider-auth evidence, cross-user visibility, and public
  deletion/account-lifecycle work were explicitly deferred as out of scope.

## Open-PR collision check

`gh pr list --limit 60` found no open PR touching `tinyassets/reset.py`, this
change directory, or the new identity test. Existing open PRs overlap
`tinyassets/api/status.py` (#1570 and #1569) and the `ui-test` skill (#1585).
This lane did not duplicate their provider-health/storage work: it added the
OpenSpec-required request identity and narrowed only the public provider-auth
detail so auth-home paths cannot leak. Those file overlaps require rebase-aware
cross-family review before any PR.

## Verification evidence

- `python -m pytest -q tests/test_identity_observability.py
  tests/test_provider_auth_quarantine.py tests/test_optional_auth_mode.py
  tests/test_current_actor_auth_context.py tests/test_get_status_primitive.py
  tests/test_universe_server_five_handles.py tests/test_reset_universes.py`
  — **94 passed**, one pre-existing FastMCP/Python 3.14 deprecation warning,
  zero skipped/xfail.
- `python -m ruff check` on every changed Python source/test and packaged
  runtime mirror — **clean**.
- `openspec validate test-identity-and-reset --strict` — **valid**.
- `scripts/sync-skills.ps1` — skill validation passed and mirrors refreshed.
- `git diff --check origin/main...HEAD` — clean before report creation.
- Red/green evidence: the new identity suite initially failed 5/5 for missing
  evidence; raw-subject activity and auth-home-path assertions each failed
  before their fixes; the schema-v2 assertions failed 2/2 before the version
  bump.

Repository-wide `python -m ruff check .` remains pre-existing red with 169
unrelated E501 violations, mainly mojibake-era long separator comments in
untouched packaged/runtime files plus `.claude/hooks/fuse_pre_write_reject.py`.
No assertion was weakened, skipped, xfailed, or modified to hide this.

## Commits pushed

- `f9da52aa` — `feat: expose token-safe request identity evidence`
- `3c8083db` — `docs(ui-test): require resolved identity evidence`
- `b1ec74dc` — `fix: redact identity secrets from status evidence`
- `f8dbc056` — `docs: record scoped reset safety blockers`
- `8f994950` — `fix: version the token-safe status contract`
- The final `LANE_REPORT.md` commit is pushed as the branch tip after this
  report is committed.

No pull request was opened.
