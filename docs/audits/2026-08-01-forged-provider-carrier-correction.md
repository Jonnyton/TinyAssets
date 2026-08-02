# Forged provider-carrier correction

Date: 2026-08-01 America/Los_Angeles
Environment: Windows 11, Python 3.14.3
Merged vulnerable commit: `1e5a3433405cdc92a2111d70a73fa0459ca89449`
Security-rejected PR head: `3af28d6bce8b79c431af0b00d6757ef969295710`
Correction implementation commit: `8d83990f07569311717d7692c1b0e7e5ec403138`

## Finding and reproduction

The merged `_issue_provider_invocation_mint_grant` accepted any exact
`ProviderInvocationReservation` in `launch_started` state whose public digest
recomputed correctly. Starting from a legitimate receipt, claim, and armed
reservation, the regression derives a new reservation ID and invocation key,
recomputes the digest, issues a grant for that forged record, mints a carrier,
and validates the provider call. On merged main the test failed with `DID NOT
RAISE PermissionError`; the forged carrier returned `codex`. This bypassed the
durable invocation, token, and cost ledger.

## Correction

- Removed the provider-model record-only grant issuer.
- Added an opaque, immutable, non-serializable store mint proof issued only
  after the SQLite arm transaction commits `APPLIED`.
- Bound the proof registry to the exact armed reservation digest and issuer
  PID; proof consumption is one-shot and occurs before carrier publication.
- Bound carriers and their keyed seal to the issuer PID. Cross-process copies
  fail before acquiring a possibly copied lock.
- Registered at-fork resets for carrier keys/locks/registries and store-proof
  locks/registries.
- Installed weakref cleanup before publishing either proof or carrier into its
  active registry; cleanup verification uses explicit `gc.collect()`.
- Kept the carrier dark. No provider, credential, public API, activation, or
  cutover path was enabled.

## Fresh verification

- `python -m pytest tests/test_provider_work_authority.py::test_self_consistent_forged_reservation_cannot_mint_or_validate -q`
  - RED on vulnerable main: 1 failed, forged carrier validated.
  - GREEN after correction: 1 passed.
- `python -m pytest tests/test_provider_work_authority.py -q`
  - 55 passed.
- Provider authority/router suite (`test_provider_work_authority.py`,
  `test_providers.py`, and `test_provider_router*.py`)
  - 157 passed.
  - Two known mocked-provider unawaited-coroutine warnings remain; the cleanup
    test's explicit collection can surface one warning allocated by the prior
    provider timeout test, but the authority suite alone is warning-free.
- Twenty-five consecutive iterations of the durable arm single-winner,
  one-shot mint-proof, and concurrent carrier-consumption tests
  - 25/25 passed.
- Ruff on all changed Python files
  - passed.
- Canonical/package SHA-256 parity
  - provider model: `edbd7211ec317b55a3cb82ed3768805d2d35fe9ebb324bd9521d2c83fbda29c7`
  - provider store: `ba747ebc71e6bf37c733dfd754d73e9a530c550a37ced851e23da876f675a3ee`
- `openspec validate repair-provider-carrier-store-provenance --strict`
  - passed before implementation.
- `openspec validate --specs --strict` after sync/archive on merged main
  - 28/28 canonical specs passed.

## Exact review and merged-main verification

- Independent security review approved exact PR head
  `da1aca89c40c9802f4df8426b1d3bc2e1da0391a` with no blocking security,
  correctness, concurrency, parity, fork, import, test, or spec-truth finding.
- PR #2141 squash-merged as
  `20424140764fba887babd3a99972b138c32b8eb1` after required policy,
  Linux/macOS/Windows build, package/import, trust-boundary, and smoke gates.
- Freshly fetched `origin/main` at that merge has the same tree as the exact
  reviewed head, passes the forged-reservation regression (1/1), passes the
  full authority file (55/55), retains canonical/package hash parity, and
  validates all 28 canonical specs strictly.

## Activation gate

The correction gate is complete. The cloud lane may resume its remaining
provider-authority, rendered-chatbot, 24-hour PC-off, and cutover acceptance
work; this correction does not itself authorize or enable activation.
