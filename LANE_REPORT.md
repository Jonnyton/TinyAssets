# Credential-Vault Shipped-Contract Backfill Lane Report

Date: 2026-07-24

Environment: Windows local, branch `codex/osx-credential-vault-backfill`

## Dependency And Collision Result

- Draft PR #1606 is open, unmerged, and `DIRTY`. It proposes future
  provider-routing and credential-ceiling behavior, so it is not the canonical
  owner gate for an as-built backfill of shipped `main`.
- The branch began exactly at `origin/main` commit `2a26a115`; it was neither
  ahead nor behind when the premise check ran.
- Of the first 60 open PRs, #1549 is the only one touching
  `openspec/specs/credential-vault/spec.md`. Its patch rewrites the separate
  provider-auth overlay requirement. This lane appended two disjoint
  requirements and proved the entire pre-existing canonical spec remained an
  exact prefix.

## Tasks Completed

- 2.3: Compared the delta with current source and the canonical spec. No
  duplicate requirement existed. Corrected two source-truth details: effective
  services are trimmed/lowercased, and base64 decoding is permissive except
  when the base64 or UTF-8 decoder actually raises. Added an explicit BYO
  first-record-shadowing scenario and reran focused evidence.
- 3.1: Broadened the STATUS write boundary to the canonical credential-vault
  spec and moved the lane to `host-review` after the builder work completed.
- 3.2: Synced the two reviewed requirements into the canonical spec. A
  prefix/suffix comparison proved all untouched requirements were preserved
  and the canonical suffix exactly matches the delta.
- 3.3 builder portion: Strict validation completed for both the change and the
  canonical capability.

Tasks 1.1 and 1.2 were already checked before this lane and remained intact.

## Skipped-Landed Or Stale

- 2.1: Skipped as inverted/stale. Waiting for unlanded PR #1606 would make a
  shipped-behavior backfill depend on future behavior.
- 2.2: Skipped as already satisfied. `HEAD`, `origin/main`, and their merge base
  were all `2a26a115`; the current runtime and canonical spec were re-read
  directly, so there was no resulting #1606 runtime to rebase onto.

## Skipped-Blocked

- 3.3 remaining portion: Cross-family review, archive, PR/land, and STATUS-row
  retirement remain open. The user required the branch to be pushed without a
  PR so cross-family review can happen first. Archiving or claiming land before
  that review would falsify the gate.

## Test, Ruff, And Validation Evidence

Fresh on 2026-07-24, Windows local:

- `python -m pytest tests/test_credential_vault.py tests/test_s2_engine_assignment.py tests/test_credential_fail_closed.py -q`
  — `20 passed in 0.49s`.
- Executable source-contract probe covering normalized aliases, provider
  fallback, BYO and Claude first-record shadowing, direct/base64 priority,
  decoder exceptions, permissive non-alphabet base64, and the exact fixed
  replacement path — `credential contract evidence: PASS`.
- `python -m ruff check tinyassets/credential_vault.py tinyassets/providers/base.py tinyassets/api/universe.py`
  — `All checks passed!`.
- `openspec validate backfill-credential-vault-shipped-contracts --type change --strict --no-interactive`
  — valid.
- `openspec validate credential-vault --type spec --strict --no-interactive`
  — valid.
- Canonical preservation/idempotence probe — `canonical preservation and
  idempotent delta sync: PASS`.
- `git diff --check` — clean.

Scope-guard note: a broader lint attempt that included unchanged
`tests/test_credential_fail_closed.py` found its pre-existing unused `Path`
import. This lane did not delete it because draft PR #1606 actively uses that
import in its open patch; deleting it here would create a future undefined name
or needless conflict. No Python file was modified by this lane.

## Commits Pushed

- `3af50092` — `spec: remove false credential backfill gate`
- `447bf38b` — `spec: sync credential vault as-built contracts`
- Final STATUS/report handoff commit (the commit containing this report)
