## 0. Review and admission

- [x] 0.1 Independently review this current-main proposal, design, and both deltas before production mutation. Historical source review on 2026-07-30 returned `ADAPT`, folded all five findings, and then approved staged source diff `cecd46644c10492bcdf33134f40857f37da61568`. Current-main review returned `ADAPT` for two missing bounded-diagnostic protections, then approved exact head `48af22c6` after the finite taxonomy, rate/suppression contract, malformed-before-JWKS ordering, and truthful self-contained write boundary were restored.

## 1. Evidence before correction

- [x] 1.1 Test-first, add the exact finite WorkOS token-validation categories (`algorithm`, `audience`, `expired`, `invalid_subject`, `invalid_token`, `issuer`, `malformed`, `required_claim`, `signature`, `signing_key`); classify malformed input before JWKS lookup; bound each category to one emission per 60-second process window with the next emission carrying only a numeric suppression count; and prove logs/responses exclude bearer tokens, JWT material, exception messages, claim values, and user-identifying data while the caller still receives standard `401 invalid_token`. Completed 2026-07-30 on Windows/Python 3.13: 10 initial red tests plus 2 independent-review red tests failed before implementation, then passed; all 53 focused tests and Ruff passed. Token acceptance and the caller response were unchanged.
- [x] 1.2 Deploy diagnostics without changing token acceptance, reproduce one post-reconnect authenticated call, and record the safe failure category plus public metadata/deployed-resource configuration parity. Completed 2026-08-02 in one host-visible ChatGPT Instant conversation after same-tab OAuth reconnect and explicit TinyAssets reattachment: the first-use approval was accepted with `Always allow`, then ChatGPT rendered `Resource not found: TinyAssets.converse` before identity or universe resolution. Sanitized production run 30782860916 covered 2026-08-03T03:47:00Z through 03:51:45Z without truncation and returned `oauth_rejection_categories=[]`, localizing this attempt before the bearer validator. Public protected-resource metadata and successful deploy run 30780952337 both used `https://tinyassets.io/mcp`; WorkOS was enabled and the deploy continued to force the production audience bypass off. No token acceptance changed.

## 2. Exact continuity repair

- [ ] 2.1 Test-first, repair only the evidence-identified validator or WorkOS/AuthKit configuration boundary; retain negative coverage for algorithm, signature, issuer, audience, expiry, subject, missing claims, and production audience-bypass refusal.
- [ ] 2.2 Add an automated parity/continuity check for every boundary that can be verified without secrets, and durably document any unavoidable WorkOS control-plane setting.

## 3. Live acceptance

- [ ] 3.1 Run focused auth tests, Ruff, the public MCP canary, and a restart check at the deployed revision; preserve dated environment, command, revision, and result evidence.
- [ ] 3.2 In one rendered ChatGPT conversation, reconnect if needed and prove an immediate authenticated call plus a later continued/refreshed call reach the same account/universe with no personal computer dependency.
- [ ] 3.3 Check production for post-fix clean user activity; if none is visible, leave a dated monitoring row rather than claiming organic-use proof.

## 4. Foldback

- [ ] 4.1 Independently review the implementation and evidence, sync both capability deltas, archive this change, and unblock the generic user-owned GitHub-to-spec cloud automation implementation gate.
