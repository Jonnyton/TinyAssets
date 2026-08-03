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
- 2026-08-02, Windows 11 + Ubuntu WSL: 210 focused deploy/installer/log/admission tests passed (25 Windows platform skips), and all 5 fleet-helper tests passed on Linux. The regression plants worker-controlled `sitecustomize.py`, reproduces false success from the retired in-container Python oracle, then proves host Docker `.Config.Env` inspection rejects the still-configured key without invoking worker code.
- 2026-08-02, Windows 11 + Docker Compose v5.1.4: 215 focused tests passed (33 platform skips); real Compose resolved U+0085/U+00A0 leading/delimiter whitespace across plain and `export` declarations, and the helper rejected, refused immutable replacement, and deleted those forms without disclosure. Ubuntu WSL: 64 installer/log/fleet tests passed (5 unavailable-Compose skips), including parent-only TERM with no secret-reading child and complete stopped-worker archives that fail before upload on missing/unreadable members.
- 2026-08-03, Windows 11 after rebase onto `340f5ebf`: the complete six-file security/deployment suite passed 224 tests with 34 POSIX-only skips, including byte-identical installed runtime/unit closure and both-thread completion before releasing the process-wide subprocess patch. Ubuntu WSL passed 65 installer/log/fleet tests with 5 unavailable-Compose skips, including complete, missing, unreadable, and container-recreated archive paths. Ruff, Bash syntax, `git diff --check`, and strict OpenSpec validation passed.
- 2026-08-03, Windows 11 after exact-head `31f1a38b` review closure: the complete six-file suite passed 263 tests with 73 platform skips; installed Docker Compose v5.1.4 accepted all 42 tested leading/export and supported-delimiter Unicode cases. Ubuntu WSL passed 104 installer/log/fleet tests with 43 unavailable-Compose skips, including the full Unicode scrub and both current-member and earlier-member recreation failures before upload. The deploy regression proves host-owned `LOG_DEST` survives application scrubbing.
