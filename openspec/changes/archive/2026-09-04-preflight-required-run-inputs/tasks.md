## 1. Preflight Contract

- [x] 1.1 Implement deterministic required-input analysis over frozen Branch topology, schema defaults, statically mandatory node accesses, and guaranteed predecessor outputs.
- [x] 1.2 Add a typed pre-admission failure carrying sorted missing keys and schema-derived type, description, and example guidance.

## 2. Run Integration

- [x] 2.1 Enforce preflight immediately before persistence in live-definition and immutable-version synchronous and asynchronous execution paths.
- [x] 2.2 Map the typed failure to the stable public `run_graph` response without disclosing contracts before existing authority checks.

## 3. Verification and Delivery

- [x] 3.1 Prove supplied, defaulted, predecessor-produced, conditional-join, loop-first-entry, falsey, live/version parity, and no-run/no-provider/no-effect refusal behavior in focused tests.
- [x] 3.2 Run focused pytest, ruff, plugin mirror build, strict OpenSpec validation, and the three-round independent cross-family review cap; address every finding before merge. *(2026-09-04: focused 60, branch/preflight 71, related 370 and CI-only fixture 23 passed; ruff, mirror build/parity and strict validation passed. Three Claude review rounds found and drove fixes for parallel fan-in, selector/claimed projection parity, `input_keys` optionality, and guarded code access. No fourth round was opened after the cap; there is therefore no separate exact-final-head approval claim.)*
- [x] 3.3 Merge, deploy, run the authenticated public handle canary, and obtain sanitized rendered proof from a bound agent using an owner-controlled Branch. *(2026-09-04: PR #2862 merged as `e6363f7b`; deploy run 33907391555 passed the authenticated handle canary; the rendered founder-universe retest returned `failure_class=missing_required_inputs` for the unresolved `context` input before execution.)*
- [x] 3.4 Sync the shipped delta specs, delete the resolved concern, archive this change, and verify production contains the exact merged SHA. *(2026-09-04: deploy run 33908373166 passed the protected receipt assertion: production reports `e6363f7bc160`, containing exact merge SHA `e6363f7bc1607dedb4ebe28aad1e4c4770ad5683`.)*
