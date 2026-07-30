## 0. Review and admission

- [x] 0.1 Obtain independent review of this proposal, design, and deltas plus the dependent `activate-main-universe-spec-drain` proposal/design/spec/task amendments; use the approved fresh-context same-provider fallback if the opposite provider is at its hard limit, fold all blocking findings, and record an approve verdict before runtime implementation. Completed 2026-07-30: fresh-context independent Codex review returned `ADAPT`; all five findings were folded, and the reviewer returned `APPROVE` for staged diff `cecd46644c10492bcdf33134f40857f37da61568` at base `ed7702f3`. Both changes passed strict validation; repair has 9 tasks and the drain remains at its 12-task ceiling.

## 1. Evidence before correction

- [ ] 1.1 Test-first, add allowlisted WorkOS token-validation failure categories and prove logs/responses exclude bearer tokens, JWT material, exception messages, claim values, and user-identifying data while the caller still receives standard `401 invalid_token`.
- [ ] 1.2 Deploy diagnostics without changing token acceptance, reproduce one post-reconnect authenticated call, and record the safe failure category plus public metadata/deployed-resource configuration parity.

## 2. Exact continuity repair

- [ ] 2.1 Test-first, repair only the evidence-identified validator or WorkOS/AuthKit configuration boundary; retain negative coverage for algorithm, signature, issuer, audience, expiry, subject, missing claims, and production audience-bypass refusal.
- [ ] 2.2 Add an automated parity/continuity check for every boundary that can be verified without secrets, and durably document any unavoidable WorkOS control-plane setting.

## 3. Live acceptance

- [ ] 3.1 Run focused auth tests, ruff, the public MCP canary, and a restart check at the deployed revision; preserve dated environment, command, revision, and result evidence.
- [ ] 3.2 In one rendered ChatGPT conversation, reconnect if needed and prove an immediate authenticated call plus a later continued/refreshed call reach the same account/universe with no personal computer dependency.
- [ ] 3.3 Check production for post-fix clean user activity; if none is visible, leave a dated monitoring row rather than claiming organic-use proof.

## 4. Foldback

- [ ] 4.1 Independently review the implementation and evidence, sync both capability deltas, archive this change, and unblock the generic user-owned GitHub-to-spec cloud automation implementation gate.
