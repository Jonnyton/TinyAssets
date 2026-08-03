## 1. Security Boundary Regressions

- [x] 1.1 Add a resolved-Compose regression proving only the daemon receives the request/admission HMAC file.
- [x] 1.2 Add workflow regressions proving rotation is explicit, manual-only, two-phase, secret-safe, and immutable by default.
- [x] 1.3 Add installer regressions proving Compose-valid assignment variants cannot bypass immutable, delete, or absence guarantees, and that failed atomic transactions preserve the live file without secret disclosure or residue.

## 2. Corrective Implementation

- [x] 2.1 Remove the admission minting file from the shared worker environment and implement the reviewed two-phase manual rotation path.
- [x] 2.2 Replace protected-stdin value-file/child custody with Compose-aware in-process Bash construction plus a mode-0600 sibling transaction and atomic rename.
- [x] 2.3 Add the full worker fleet to default offsite archives and correct stale log runbook identities.

## 3. Verification And Recovery

- [x] 3.1 Run focused deploy, installer, logging, Compose-render, lint, and strict OpenSpec gates; record exact evidence.
- [ ] 3.2 Obtain independent exact-head security/deploy review, merge the correction, rotate during a manual deploy, and verify the worker environment boundary plus public health before resuming the V1 lane.

## Verification Evidence

- 2026-08-02, Windows 11: the focused deploy/installer/log/HMAC/rotation-fleet suite -> 150 passed, 25 POSIX-only skipped after the colon/BOM grammar, atomic-preservation, and cross-step quiescence regressions.
- 2026-08-02, Windows 11: admission/host-focused suites -> 36 passed; Ruff and `git diff --check` clean; strict OpenSpec valid.
- 2026-08-02, Docker Compose CLI: `docker compose ... config --no-interpolate` rendered the request HMAC file only on `daemon`; all four workers resolved to `/etc/tinyassets/env` only.
- 2026-08-02, Ubuntu WSL: `=` and `:` Compose-valid duplicate `set-once` shapes were refused before mutation with exit 5 and no value disclosure; delete/assert-absent removed or rejected the same grammar; a real `RLIMIT_FSIZE` write failure preserved the 4,102-byte live file exactly and left no sibling transaction.
- 2026-08-02, Docker Compose v5.1.4 + Ubuntu WSL: Compose resolved UTF-8-BOM-prefixed `=` and `:` declarations into the service environment; the helper now rejects/removes that first-line form across `assert-absent`, `set-once`, and `delete` without value disclosure.
- 2026-08-02, invoked workflow-state regression: the production fleet helper captured the exact four running key-free worker IDs, accepted those IDs only after all became stopped, and failed closed on key exposure, restart, or identity swap; workflow ordering binds capture before stop-writer and quiescence assertion before the first replacement-key byte.
