# BYO-LLM subscription deposit boundary

**Date:** 2026-08-12

**Environment:** Windows, branch `claude/enable-claude-serving`

**OpenSpec:** `openspec/changes/byo-llm-connect-flow/design.md`, Decision 3 and
Custody owner

## Built

- Added MCP operation `write_graph target="connection" operation="connect_llm"`.
  The existing `write_graph` connection router remains unchanged and delegates
  to `tinyassets.api.cloud_connections`.
- The operation re-derives the authenticated request subject, requires that
  subject's current `admin` ACL row on the canonical universe, accepts only a
  Claude or Codex `llm_subscription`, and calls `write_credential_vault` with
  the server-derived owner and universe IDs.
- Inline `auth_json_b64` is supported for Claude OAuth material and Codex auth
  JSON. Codex also accepts a contained `codex_home` whose `auth.json` is usable.
- Deposits run under `ProviderAssignmentAdmission.exclusive` through the vault
  writer. Malformed input, duplicate keys or vault slots, unusable or
  wrong-service material, path escape, and cross-owner replacement fail before
  the vault write. Ownership transfer is deliberately absent.
- `llm_credential_deposit_owners` now records `connected_at`. Existing rows are
  migrated in place without changing their owner. Redacted LLM projections are
  merged into `read_graph target="connections"` with exactly `service`,
  `owner_user_id`, and `connected_at`.
- A pre-existing ownerless vault credential remains ineligible for custody
  adoption. Re-depositing credential material through this authenticated
  boundary creates the server-authored depositor record, after which the
  existing `bind_serving_provider` path succeeds.

No serving/router/provider implementation or other authentication boundary was
changed. In particular, `app_channel_routing.py`, `universe_intelligence.py`,
`provider_serving_binding.py`, and `claude_provider.py` were not edited.

## Verification

- `python -m pytest -q tests/test_llm_subscription_connections.py`
  - RED before implementation: 14 failed because `connect_llm` did not exist.
  - GREEN after implementation: 15 passed, including the later cross-service
    depositor-owner regression found during local security review.
- `python -m pytest -q tests/test_llm_subscription_connections.py tests/test_workos_pipes_connections.py tests/test_provider_serving_binding.py tests/test_credential_vault.py`
  - 62 passed, 1 skipped in 5.85s.
- `python -m ruff check tinyassets/credential_vault.py tinyassets/api/cloud_connections.py tests/test_llm_subscription_connections.py`
  - All checks passed.
- `python packaging/claude-plugin/build_plugin.py`
  - Mirror staged; import probe `probe-ok`.
- `git diff --check`
  - Passed with no whitespace errors.

Tests cover both Claude and Codex deposits, ownerless-before/deposited-after
custody behavior, successful serving-provider binding, exact admin ACL
enforcement, cross-owner overwrite refusal with vault preservation, malformed
and duplicate input, contained and escaping Codex paths, redacted connection
reads, and absence of credential/path material from responses and captured logs.

## Remaining acceptance

This build does not complete the provider-hosted OAuth/device-flow UX or the
generic GitHub project binding, so OpenSpec tasks 2.1-2.4 remain unchecked. No
merge, deployment, live credential deposit, public canary, or rendered chatbot
acceptance was performed from this branch.
