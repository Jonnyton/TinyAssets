# Credential vault Codex review r11

**Verdict:** ADAPT at `feb0fd45`; addressed on `feat/credential-vault` by the
r11 builder commit recorded in PR #1469.

## Findings reproduced

1. **Critical — mutation outran the guard.** Guard advancement occurred after
   the vault commit and `GuardUnavailable` was suppressed, so a delete could
   commit without an external rollback witness.
2. **Critical — guard loss failed open.** An absent guard row read as epoch zero;
   deleting/recreating the guard domain let a nonzero vault reopen.
3. **Critical — concurrency false alarms.** The guard could advance between the
   DB-first read and guard read. Baseline focused evidence: `1 failed, 101
   passed, 2 skipped`; 11/64 lifecycle workers received false
   `REAUTHORIZATION_REQUIRED` in the reproduced run.
4. **Required — local stores aliased.** Two daemon-local stores with the default
   `store_id` shared one guard row because `daemon_id`/generation were omitted.
5. **Required — job authority remained caller-asserted.** Mint trusted raw
   `run_id` plus expected scope; resolve allowed no live executor verifier.
6. **Required — typed closure was incomplete.** Malformed refresh tickets leaked
   `AttributeError`; malformed persisted grant kinds leaked `ValueError`; other
   persisted grant fields were not normalized.
7. **Required — durable evidence was stale.** STATUS and the design header did
   not match the current collected suite/review round.

## Resolution

- `EpochGuard.reserve(expected_epoch)` now durably reserves the next external
  epoch while the vault holds its `BEGIN IMMEDIATE` transaction. The vault then
  commits that exact epoch with the mutation. Guard reservation failures abort
  the vault transaction and are never suppressed; a later vault-commit failure
  intentionally leaves the guard ahead and forces reauthorization.
- Rollback checks take a stable, guard-first snapshot under the vault write lock.
  Missing/recreated/mismatched guard identity at a nonzero vault epoch forces
  `REAUTHORIZATION_REQUIRED`; corrupt/unavailable guard storage is typed
  `BACKEND_UNAVAILABLE`.
- Guard identities bind the physical recovery generation and custody. Local
  identities additionally bind `store_id` + `daemon_id`, so independent daemons
  cannot collide. Platform logical `store_id` remains AEAD-authenticated within
  its single physical DB generation, preserving the cross-store tamper proof.
- `mint_job_grant` treats `run_id` only as a key into an injected authoritative
  run lookup and verifies run/founder/universe before mint. The public
  `resolve_job_grant(grant, *, verify_context=None)` signature is unchanged, but
  `None` fails closed; `JobGrant` stays opaque and the named `JobContext`,
  `DELETE_PENDING`, and mint/resolve exports remain stable.
- Refresh-ticket types are checked before attribute access. Persisted grant rows
  are fully parsed and normalized (capability hash, ref, scope fields, kind,
  run id, finite expiry) before capability/context use.

## Fresh verification (2026-07-17, Windows)

- Focused vault suite: `119 passed, 2 skipped` in 18.61s.
- 64-process / 100+ operation lifecycle gate: three consecutive fresh runs,
  all passed (3.16s, 2.94s, 3.19s); zero false rollback alarms.
- Targeted r11 regressions: `23 passed` before the full gate.
- `python -m ruff check tinyassets/credentials tests/test_credential_vault_hardening.py tests/test_credential_vault_concurrency.py`: clean.
- `python -m compileall -q tinyassets/credentials tests/test_credential_vault_hardening.py tests/test_credential_vault_concurrency.py`: clean.
- `git diff --check`: clean apart from Git's informational CRLF-to-LF warnings.

No existing assertion was weakened, skipped, or xfailed. The grant surface shape
required by S3/S4 remained stable.
