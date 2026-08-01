## 0. Review and admission

- [x] 0.1 Independently review this current-main proposal, design, and both deltas before production mutation. Historical source review on 2026-07-30 returned `ADAPT`, folded all five findings, and then approved staged source diff `cecd46644c10492bcdf33134f40857f37da61568`. Current-main review returned `ADAPT` for two missing bounded-diagnostic protections, then approved exact head `48af22c6` after the finite taxonomy, rate/suppression contract, malformed-before-JWKS ordering, and truthful self-contained write boundary were restored. After the live positive-control envelope adaptation, Claude independently approved exact head `cee3baf1`, reproduced run 30681363132 and the live `cimd_not_advertised` result, ran 95 core focused tests plus Ruff/strict OpenSpec, and adversarially verified canonical-prefix isolation.

## 1. Evidence before correction

- [x] 1.1 Test-first, add the exact finite WorkOS token-validation categories (`algorithm`, `audience`, `expired`, `invalid_subject`, `invalid_token`, `issuer`, `malformed`, `required_claim`, `signature`, `signing_key`); classify malformed input before JWKS lookup; bound each category to one emission per 60-second process window with the next emission carrying only a numeric suppression count; and prove logs/responses exclude bearer tokens, JWT material, exception messages, claim values, and user-identifying data while the caller still receives standard `401 invalid_token`. Completed 2026-07-30 on Windows/Python 3.13: 10 initial red tests plus 2 independent-review red tests failed before implementation, then passed; all 53 focused tests and Ruff passed. Token acceptance and the caller response were unchanged.
- [ ] 1.2 Deploy diagnostics without changing token acceptance, reproduce one post-reconnect authenticated call, and record the safe failure category plus public metadata/deployed-resource configuration parity. Evidence through 2026-07-31/2026-08-01: ChatGPT returned through `link_success=true`, an explicitly reattached call hung, and a new Temporary Chat immediately rendered the connection expired. Historical positive-control replay 30681363132 at exact head `f4a6251f` now proves the deployed detector recognizes a fixed malformed bearer as `oauth_rejection_categories=["malformed"]` through the exact Compose-prefixed bare-warning envelope, with no truncation or raw text. Runs 30680168689 and 30680303470 remain empty, so the rendered attempts produced no rejected bearer; that does not distinguish no bearer from an accepted bearer. Public PRM/resource/scopes and deployed WorkOS variables match; AuthKit supports authorization code, refresh, PKCE S256, public-client exchange, and DCR but omits CIMD advertisement. The required authenticated call remains unproven.

## 2. Exact continuity repair

- [ ] 2.1 Test-first, repair only the evidence-identified validator or WorkOS/AuthKit configuration boundary; retain negative coverage for algorithm, signature, issuer, audience, expiry, subject, missing claims, and production audience-bypass refusal.
- [ ] 2.2 Add an automated parity/continuity check for every boundary that can be verified without secrets, and durably document any unavoidable WorkOS control-plane setting. Local test-first checker now covers resource/issuer, bearer transport, auth/token/DCR endpoints, authorization-code + refresh grants, offline scope, PKCE S256, public-client exchange, CIMD advertisement, and malformed list-shaped metadata; 9 focused tests pass. The live check fails only with `cimd_not_advertised`. Completion still requires the WorkOS control-plane correction and a green live result.

## 3. Live acceptance

- [ ] 3.1 Run focused auth tests, Ruff, the public MCP canary, and a restart check at the deployed revision; preserve dated environment, command, revision, and result evidence.
- [ ] 3.2 In one rendered ChatGPT conversation, reconnect if needed and prove an immediate authenticated call plus a later continued/refreshed call reach the same account/universe with no personal computer dependency.
- [ ] 3.3 Check production for post-fix clean user activity; if none is visible, leave a dated monitoring row rather than claiming organic-use proof.

## 4. Foldback

- [ ] 4.1 Independently review the implementation and evidence, sync both capability deltas, archive this change, and unblock the generic user-owned GitHub-to-spec cloud automation implementation gate.
