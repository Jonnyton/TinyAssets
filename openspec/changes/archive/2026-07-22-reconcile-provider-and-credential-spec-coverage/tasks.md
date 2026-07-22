## 1. Confirm capability ownership

- [x] 1.1 Audit provider envelopes, explicit universe context, registration, quota, diagnostics, and status gaps against the existing provider-routing capability.
- [x] 1.2 Audit vault overlay and host-subscription inheritance against the existing credential-vault capability.
- [x] 1.3 Confirm pending R2-1a owns set_engine allowlist writes rather than this lane's call and credential-environment contracts.

## 2. Draft provider and credential deltas

- [x] 2.1 Add the common provider call contract and explicit per-universe routing requirements to provider-routing.
- [x] 2.2 Add runtime eligibility, cooldown, structured exhaustion, and status evidence requirements to provider-routing.
- [x] 2.3 Add conservative subscription-auth health and Codex refresh-viability requirements to provider-routing.
- [x] 2.4 Replace the full per-universe auth overlay requirement with ordinary host-subscription stripping plus the shipped partial-overlay and unexpected-error limitations.

## 3. Verify as-built truth

- [x] 3.1 Map every added or modified requirement to current source and focused tests, including explicit current limitations.
- [x] 3.2 Run strict OpenSpec validation and focused provider, credential, and status evidence suites.
- [x] 3.3 Obtain independent review for grounding, cross-capability ownership, status-shape truth, security-boundary truth, and future-state overclaims.

## 4. Sync and publish

- [x] 4.1 Re-fetch main and recheck R2-1a before syncing the reviewed deltas.
- [x] 4.2 Archive the change, sync the two canonical specs, and compare archived delta results with canonical content.
- [ ] 4.3 Strict-validate the complete OpenSpec tree, publish and land the PR, then retire or promote the STATUS lane.
