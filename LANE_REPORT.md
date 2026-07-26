# Outbound Boundary Layer — Waves 1–3 Lane Report

Date: 2026-07-25
Branch: `codex/osx-outbound-boundary`
Base: `6cde7ef0`
Pushed commits:

- `19e0a709` — `feat: add outbound connection grant ledger`
- `ec95a40f` — `feat: enforce outbound action caps`
- `20656d23` — `feat: make outbound effects replay safe`

## Per-task summary

- **1.1** Added SQLite connection/grant persistence with owner, class, scopes, provider, destination, per-universe binding, connection/grant revocation, and PostgreSQL migration `010_outbound_boundary.sql`.
- **1.2** Added exact-grant scoped proxy resolution. Absent, revoked, and ambiguous grants fail closed. The adapter API accepts no dispatcher, factory, config, ledger path, credential path, or ambient fallback. Trusted broker construction occurs in a spawned child bound to the already-resolved ledger and grant.
- **1.3** Kept raw credentials out of proxy state, metadata, errors, audit records, artifacts, and environment observations. Credential resolution occurs only in the trusted child; production defaults fail closed. Test-only transports and credential sources require explicit trusted-ledger opt-in.
- **1.4** Added attributed connector-definition and MCP-client-config artifacts with remix ancestry and secret-material rejection.
- **2.1** Added machine-readable caps with name, finite non-negative maximum, unit, and an independent `unprompted_action` authority axis. Action units must match cap units.
- **2.2** Added automatic below-cap execution and above-cap held receipts with zero funds/quota consumption. Owner confirmation is grant-bound; execution acquisition, retries, and terminal replay are journaled atomically.
- **2.3** Added actionable held-effect remediation naming the cap and effect key. At-cap execution, owner denial, grant/proxy mismatch, concurrent confirmation, failure retry, and ambiguous outcomes are covered.
- **3.1** Added deterministic effect keys from goal ID, schedule period, and item fingerprint. Intent is reserved before fire and every replay consults the journal.
- **3.2** Added destination reconciliation with terminal success/failure/hold persistence. Wiki write-back reconciles against its deterministic destination marker; unsupported adapters declare the limitation and hold visibly.
- **3.3** Added whole-batch admission and explicit per-item outcomes. Later items do not fire after failure, and already-terminal effects are reported as not reversed.
- **3.4** Migrated GitHub PR, Twitter post, wiki write-back, and Windows desktop effectors behind legacy/dual/system identity modes. Dual mode writes and finalizes both keys; system mode cannot flip until a non-empty cohort of every alias is terminal and equal.
- **3.5** Removed time-only pending-row reclamation. Aged pending intents require destination reconciliation or become actionable terminal holds. Receipt-finalization races also persist a remediation hold.

Tasks 1.1–1.4, 2.1–2.3, and 3.1–3.5 are checked in `tasks.md`.

## Red/green evidence

TDD reds observed before implementation included missing ledger/proxy/cap/effect-key APIs, stale pending rows being reclaimed, absent reconciliation/batch helpers, alias-only parity, missing connection revocation, replaying confirmed actions twice, arbitrary confirmation identity, non-finite/unit cap bypass, and wiki stale-intent hold despite a readable marker.

Required mutation checks:

- **Permit gate forced open:** temporarily disabled the ambiguous-grant cardinality check. `test_resolve_scoped_proxy_fails_closed_without_fallback[ambiguous]` went red instead of returning the required `GrantResolutionError`. The gate was immediately restored; restored permit cases passed.
- **Cap gate forced open:** temporarily disabled the above-cap hold branch. `test_above_cap_holds_without_execution_or_consumption_until_confirmation` went red: expected `held`, observed `executed`. The gate was immediately restored; the restored test passed.

Final verification on Windows / Python 3.14 after the rejection fold:

- Full touched test files: **108 passed, 7 skipped**. The skips require an external PostgreSQL DSN.
- Ruff on every touched canonical, plugin-mirror, and test Python file: **clean**.
- `python packaging/claude-plugin/build_plugin.py`: **passed**, including `probe-ok`.
- Canonical/plugin SHA-256 parity for the rejection fold: **3/3 files matched**.
- `openspec validate outbound-boundary-layer --strict`: **valid**.
- `openspec validate --all --strict`: **41 passed, 0 failed**.
- Secret scan: **clean**.
- Opus 5 and Codex independently returned **REJECT** before this fold; all four
  requested authority/security findings are reproduced and folded below.
- `git diff --check 6cde7ef0..HEAD`: **clean**.

## Rejection fold: red -> fix -> green -> mutation

### Finding 1 — confirmation was not bound to the reviewed decision

- **Red:** Added the reviewer replay exactly: hold and confirm
  `create_issue` with the benign request at value `5`, then reuse the same
  effect key for `delete_repo` against `acme/production` at value
  `10_000_000`. The test failed because the second call did not raise, and the
  confirmation result had no `held_decision`.
- **Fix:** Held evidence now contains the canonical redacted JSON decision
  `{verb, request, action_value, action_unit, cap}`. Confirmation stores a
  SHA-256 binding to that decision and returns the held payload for review.
  Every confirmed activation/retry, including terminal replay, must match the
  stored decision byte-for-byte under canonical JSON or fail closed.
- **Green:** `test_confirmed_hold_refuses_a_later_different_decision` passed.
- **Mutation:** Temporarily disabled the stored/current decision comparison.
  The reviewer replay went red with `DID NOT RAISE PermissionError`. Restoring
  the comparison returned the test to green.

### Finding 2 — caller-supplied owner identity was accepted as authority

- **Red:** Added forged-owner reproductions for both proxy resolution and held
  confirmation. Both failed because caller-supplied `owner_user_id` /
  `authorized_by` strings were accepted.
- **Fix:** Removed both identity parameters. Authority-bearing ledger
  operations call a required `AuthenticatedPrincipalVerifier` installed at
  trusted ledger construction; absence, verifier failure, anonymous identity,
  non-string identity, and authenticated non-owner identity all fail closed.
  `execute_capped_action` also re-verifies the current authenticated owner at
  execution time rather than relying only on an earlier proxy resolution.
- **Green:** The forged-owner, missing-verifier, and authenticated-non-owner
  tests passed.
- **Mutation:** Temporarily disabled the authenticated-owner comparison in
  confirmation. The non-owner reproduction went red with
  `DID NOT RAISE PermissionError`. Restoring it returned the test to green.

Authenticated-principal seam contract: the daemon-authenticated request
boundary constructs `ConnectionLedger` with
`verify_authenticated_principal: Callable[[], str]`. The callback must resolve
the fresh request-local principal from server-owned authentication context; it
must never be sourced from a universe, action payload, request field, grant
record, or caller-provided identity string. The primitive has no ambient,
anonymous, or caller-string fallback, and no production call site is wired yet.

### Finding 3 — credential material leaked through ambiguous errors

- **Red:** Added an induced `AmbiguousProxyOutcome` whose message contains
  `Authorization: Bearer transport-echoed-bearer-secret`; the secret appeared
  in the raised adapter-visible exception.
- **Fix:** The broker now replaces ambiguous transport exceptions with a
  constant secret-free exception, and the spawned worker maps every known
  adapter-visible error class to constant text instead of forwarding
  `str(exc)`.
- **Green:** `test_ambiguous_transport_error_cannot_leak_credential_material`
  passed; the full credential-blindness tests also passed.
- **Mutation:** Temporarily restored the bare `raise`. The test went red with
  the secret present in the exception. Restoring the scrub returned it to
  green.

### Finding 6 — wiki reconciliation trusted attacker-controlled body text

- **Red:** Added the reviewer victim-effect reproduction: a stale pending
  victim receipt plus attacker-controlled sentinel comments in the wiki body
  reconciled as `succeeded`.
- **Fix:** Payload bodies containing reserved effect-marker syntax are
  rejected. After a real page write, the trusted effector records an exact
  effect-key/destination/page-hash marker in server-side wiki metadata.
  Reconciliation consults only that metadata, never page body text. A receipt
  finalization or marker-record failure returns successful destination
  evidence with `receipt_finalize_failed=true` and
  `reconciliation_required=true`, leaves the receipt pending, and a stale
  replay reconciles from the trusted marker.
- **Green:** The attacker-marker refusal, trusted-marker reconciliation, and
  receipt-finalize-failure reconciliation tests passed.
- **Mutation:** Temporarily restored body-sentinel reconciliation. The victim
  reproduction went red (`succeeded` instead of `held`). Restoring trusted-only
  reconciliation returned it to green.

## Files touched

- Storage/boundary: `tinyassets/storage/outbound_connections.py`, `tinyassets/storage/external_write_receipts.py`, `prototype/full-platform-v0/migrations/010_outbound_boundary.sql`
- Identity/boundary effectors: `tinyassets/idempotency.py`, `tinyassets/effectors/outbound_boundary.py`
- Migrated effectors: `tinyassets/effectors/github_pr.py`, `twitter_post.py`, `wiki_write_back.py`, `windows_desktop.py`
- Tests: `test_outbound_connection_ledger.py`, `test_outbound_effect_boundary.py`, `test_external_write_phase_2_atomicity.py`, `test_idempotency.py`, `test_paid_market_migrations.py`, `test_wiki_write_back_effector.py`
- OpenSpec checklist: `openspec/changes/outbound-boundary-layer/tasks.md`
- Generated Claude plugin mirrors for all changed canonical plugin-shipped files

## Deliberate omissions and notes

- Section 4.x and later sections were not implemented.
- No value-moving, settlement, payment, wallet, price, or accounting behavior was added.
- No requirement or framing was taken from the unapproved open-production-commons reframe.
- `tinyassets/api/universe.py` and `tinyassets/universe_server.py` were not touched.
- Provider/router wiring owned by those other lanes was not changed. Unregistered production credential/transport schemes fail closed; test fixtures require explicit opt-in.
- Migration number **010** was used as directed. No `010` collision exists on this branch; the known parallel lane remains on `011`. If integration creates a `010` collision, it must be resolved at land time rather than by unilateral renumbering here.
- No PR was opened.
- This report is committed with the rejection fold.

LANE_RESULT: done - Four rejected authority/security findings folded with red-green-mutation evidence; verified, committed, and pushed.
