## 1. Enrollment resolver

- [x] 1.1 Implement strict server-only enrollment parsing and owner/universe/provider resolution with no wildcard, raw secret, test fixture, or market fallback.
- [x] 1.2 Add focused resolver tests for malformed, duplicate, expired, ambiguous, and exact valid entries, including secret-free/redacted projections.

## 2. Phone bind surface

- [x] 2.1 Add owner-authenticated `bind_provider`/`reconcile` behavior to the canonical cloud automation handle, reusing `ProviderWorkBindingService.issue` and deterministic store replay semantics.
- [x] 2.2 Add tests proving spoofed authority fields are rejected/ignored, concurrent bind is idempotent, and missing enrollment remains held without mutation.

## 3. Integration and ship gates

- [x] 3.1 Expose only redacted provider-binding state and actionable next steps through `read_graph`/prompts; regenerate the packaged mirror and prove parity.
- [ ] 3.2 Run focused tests, Ruff, strict OpenSpec validation, and the §14 concurrency proof; obtain independent security/domain review before merge.
- [ ] 3.3 Deploy the dark bind path (including `.github/workflows/deploy-prod.yml` secret propagation) and run the public canary; reconcile one explicit owner enrollment through the rendered phone connector before activation/cutover.
