## 1. Baseline and contract

- [x] 1.1 Capture live feed size and representative onboarding search contamination in `docs/audits/2026-07-21-wiki-discovery-contamination.md`.
- [x] 1.2 Choose the logical read-scope split and record alternatives/compatibility in proposal, design, and delta specs.

## 2. Scoped wiki discovery (RED -> GREEN)

- [x] 2.1 Add failing tests for default discovery exclusion, explicit coordination/all scopes, metadata overrides, category filtering, invalid scope, and ambient/since filtering.
- [x] 2.2 Implement the smallest scope classifier/filter in `tinyassets/api/wiki.py` and forward `scope` through the public wrapper.
- [x] 2.3 Mirror wiki/runtime wrapper changes and run focused tests plus mirror parity.

## 3. Discoverable branch authoring (RED -> GREEN)

- [x] 3.1 Add failing live-handle tests for branch create routing, patch compatibility, and mixed-payload rejection.
- [x] 3.2 Add additive `spec_json` routing to the existing `build_branch` handler.
- [x] 3.3 Publish the discovery-classified workflow-definition schema page and assert it is found by the canonical query.
- [x] 3.4 Mirror the live server and run focused tests plus mirror parity.

## 4. Verification and publication

- [ ] 4.1 Run focused suites, ruff on touched Python, OpenSpec/spec consistency checks, and the relevant broader suite.
- [ ] 4.2 Review the diff independently where available and address findings.
- [ ] 4.3 Run provider foldback gate; commit, push, and open a draft PR with live baseline and deployment acceptance requirements.
- [ ] 4.4 Leave rendered chatbot `ui-test` and post-fix organic-use proof explicitly pending deployment; add/retain a STATUS watch until observed.
