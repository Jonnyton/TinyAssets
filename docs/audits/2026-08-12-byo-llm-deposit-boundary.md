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
  writer. The admin ACL row is rechecked inside the admitted `BEGIN IMMEDIATE`
  transaction. Malformed input, duplicate keys or vault slots, unusable or
  wrong-service material, path escape, and cross-owner replacement fail before
  the vault write. Ownership transfer is deliberately absent.
- Codex deposits require strict, duplicate-free JSON with a non-empty
  `tokens.access_token`; Claude deposits require OAuth-token material. A
  write-ahead recovery journal links the vault replacement to a random deposit
  ID in owner metadata, so an interrupted or failed metadata commit restores
  the prior vault and serving holds while recovery is pending. Journal and
  vault files plus their directory entries are durably flushed before the
  SQLite commit; journal removal is directory-synced afterward.
- `llm_credential_deposit_owners` now records `connected_at` and the internal
  recovery ID. Existing rows are serialized and migrated in place without
  changing their owner. Redacted LLM projections are
  merged into `read_graph target="connections"` with exactly `service`,
  `owner_user_id`, and `connected_at`.
- A pre-existing ownerless vault credential remains ineligible for custody
  adoption. Re-depositing credential material through this authenticated
  boundary creates the server-authored depositor record, after which the
  existing `bind_serving_provider` path succeeds.
- Both services now produce immutable launch snapshots. Codex receives the
  snapshot as `CODEX_HOME`; Claude receives an isolated config root plus only
  the snapshotted `CLAUDE_CODE_OAUTH_TOKEN`, with ambient credentials removed.

No provider adapter or other authentication boundary was changed. The shared
provider environment builder was extended only to consume the Claude snapshot.
In particular, `app_channel_routing.py`, `universe_intelligence.py`,
`provider_serving_binding.py`, and `claude_provider.py` were not edited.

## Verification

- `python -m pytest -q tests/test_llm_subscription_connections.py`
  - RED before implementation: 14 failed because `connect_llm` did not exist.
  - A second RED cycle captured exact-head review findings: Claude launch held,
    unusable Codex/Claude material passed, ACL revocation raced, and injected
    owner-metadata failure did not roll back the vault.
  - Exact-head review then reproduced post-deposit auth rotation to unusable
    material still passing custody. Codex inline/path material and direct Claude
  OAuth tokens are now revalidated on every custody/bind/launch read.
  - The final review also found ownerless replacement inherited the previous
    owner and that the recovery protocol lacked power-crash durability. Both
    now have RED/GREEN regressions; ownerless replacement clears ownership and
    custody, while fsync ordering fences the database commit.
  - A committed ownerless write now has a durable commit marker independent of
    owner rows, so recovery retains the committed vault. All vault writes use
    the protocol, including removal of the final LLM subscription.
  - GREEN after hardening: 30 passed.
- `python -m pytest -q tests/test_llm_subscription_connections.py tests/test_workos_pipes_connections.py tests/test_provider_serving_binding.py tests/test_credential_vault.py tests/test_credential_fail_closed.py tests/test_provider_served_router.py tests/test_universe_server_five_handles.py tests/test_write_gate.py`
  - 154 passed, 4 skipped in 9.33s; one unrelated FastMCP deprecation warning.
- `python -m ruff check tinyassets/credential_vault.py tinyassets/api/cloud_connections.py tinyassets/providers/base.py tests/test_llm_subscription_connections.py`
  - All checks passed.
- `python packaging/claude-plugin/build_plugin.py`
  - Mirror staged; import probe `probe-ok`.
- `git diff --check`
  - Passed with no whitespace errors.

Tests cover both Claude and Codex deposits, ownerless-before/deposited-after
custody behavior, serving-provider binding and isolated launch material, exact
admin ACL enforcement at the admitted write, cross-owner overwrite refusal,
injected-failure rollback and restart recovery, serialized legacy migration,
strict token shapes and duplicate input, contained and escaping Codex paths,
redacted reads, and absence of credential/path material from responses and logs.

## Remaining acceptance

This build does not complete the provider-hosted OAuth/device-flow UX or the
generic GitHub project binding, so OpenSpec tasks 2.1-2.4 remain unchecked. No
merge, deployment, live credential deposit, public canary, or rendered chatbot
acceptance was performed from this branch.
