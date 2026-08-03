## 1. Security Boundary Regressions

- [x] 1.1 Add a resolved-Compose regression proving only the daemon receives the request/admission HMAC file.
- [x] 1.2 Add workflow regressions proving rotation is explicit, manual-only, two-phase, secret-safe, and immutable by default.
- [x] 1.3 Add installer regressions proving normal, error, and parent-only signal paths create no named plaintext secret file.

## 2. Corrective Implementation

- [x] 2.1 Remove the admission minting file from the shared worker environment and implement the reviewed two-phase manual rotation path.
- [x] 2.2 Replace protected-stdin temporary-file custody with a pipe-based handoff that cannot strand a named plaintext file.
- [x] 2.3 Add the full worker fleet to default offsite archives and correct stale log runbook identities.

## 3. Verification And Recovery

- [x] 3.1 Run focused deploy, installer, logging, Compose-render, lint, and strict OpenSpec gates; record exact evidence.
- [ ] 3.2 Obtain independent exact-head security/deploy review, merge the correction, rotate during a manual deploy, and verify the worker environment boundary plus public health before resuming the V1 lane.

## Verification Evidence

- 2026-08-02, Windows 11: `python -m pytest -q tests/test_deploy_prod_workflow.py tests/test_install_tinyassets_env.py tests/test_log_aggregation.py tests/test_validate_host_runtime_hmac_pair.py` -> 147 passed, 9 skipped.
- 2026-08-02, Windows 11: admission/host-focused suites -> 36 passed; Ruff and `git diff --check` clean; strict OpenSpec valid.
- 2026-08-02, Docker Compose CLI: `docker compose ... config --no-interpolate` rendered the request HMAC file only on `daemon`; all four workers resolved to `/etc/tinyassets/env` only.
- 2026-08-02, Ubuntu WSL: real normal/failure/parent-only-TERM probes created no named plaintext residue and exited 0/3/-15; both shell scripts passed `bash -n`.
- 2026-08-02, Ubuntu WSL: malformed duplicate `set-once` assignments were refused before mutation with exit 5 and no value disclosure.
