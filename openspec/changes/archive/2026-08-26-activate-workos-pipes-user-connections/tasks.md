## 1. WorkOS Pipes client and ledger resolver

- [x] 1.1 Add a secret-safe WorkOS Pipes client with authorize, connected-account, and credential-vending methods using injected HTTP transport; test exact paths, owner derivation, redaction, and malformed responses. Focused client tests pass.
- [x] 1.2 Extend the credential-blind broker with an owner-bound `workos-pipes://github/<owner>` resolver; test token custody, cross-owner rejection, and failure redaction while preserving vault/test fixtures. Existing ledger suite plus resolver boundary pass.

## 2. Phone connection handles

- [x] 2.1 Add owner-authenticated `connection` read/write actions and idempotent ledger reconciliation for GitHub destination grants; test ACL, spoofing, replay, duplicate ambiguity, and needs-authorization responses. Three focused API tests pass.
- [x] 2.2 Wire `write_graph`/`read_graph` canonical routing and cloud-automation prerequisite next-action projections; update prompt text and focused API tests. 72 focused tests pass.

## 3. Production proof

- [ ] 3.1 Run focused tests, Ruff, strict OpenSpec validation, package/mirror checks, and public canary; open one review PR with no secret material in artifacts.
- [ ] 3.2 After merge/deploy, perform rendered phone authorization/reconciliation proof and sync/archive this change; leave compute binding as the next explicit blocker if provider authority is still absent.
