## 1. Scoped Server Authority

- [x] 1.1 Add failing middleware tests for valid, absent, short, mismatched,
  adjacent-path, extra-argument, batch, and non-wiki bearer requests.
- [x] 1.2 Add failing tool/storage tests proving the authority writes only
  `drafts/notes/uptime-probe.md` and remains anonymous to other auth checks.
- [x] 1.3 Implement constant-time token validation, exact request-local scope,
  and the fixed-path wiki writer with no token logging.
- [x] 1.4 Reproduce the stateful Streamable-HTTP context boundary with a real
  initialize-then-write transport test, then re-establish the exact authority
  in FastMCP's per-tool execution context.

## 2. PROBE-003 Roundtrip

- [x] 2.1 Add failing canary tests for credentialed write/read success,
  exact-path validation, bearer placement, and missing-secret fallback.
- [x] 2.2 Implement credentialed write-then-read mode while preserving the
  anonymous gate-plus-read mode when the token is absent.

## 3. Operations Wiring

- [x] 3.1 Pass the GitHub Actions secret to the wiki probe and cover the
  workflow shape with a test.
- [x] 3.2 Add the token to the rotation catalog and document upgraded
  PROBE-003 behavior, scope, green criteria, and red signals.

## 4. Verification and Delivery

- [x] 4.1 Run all touched test files and Ruff.
- [x] 4.2 Prove scope mutation resistance by widening the filename predicate,
  observing the security test fail, restoring the predicate, and rerunning it.
- [x] 4.3 Run actionlint when available, inspect the final diff for secrets and
  scope drift, and record evidence in the uncommitted lane report.
- [x] 4.4 Commit the strict-valid spec and implementation, then push
  `codex/osx-canary-token` to origin without opening a pull request.
