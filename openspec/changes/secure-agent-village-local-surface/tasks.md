## 1. Executable Security Reproductions

- [x] 1.1 Add exact HTTP tests proving unauthenticated and query-token state,
  chat, provider, talk, and hire requests are rejected before collector calls.
- [x] 1.2 Add startup/config tests proving loopback is the default, omitted
  tokens become high-entropy per-process tokens, and weak explicit tokens fail.
- [x] 1.3 Add browser-source tests proving fragment bootstrap, immediate URL
  cleanup, session-only retention, and header-only API authentication.
- [x] 1.4 Add request-boundary tests proving malformed, negative, non-object,
  and greater-than-64-KiB bodies cannot reach talk/hire collectors.

## 2. Secure Local Surface

- [x] 2.1 Implement generated-or-explicit token preparation, loopback defaults,
  constant-time header authorization, and public static/health routing.
- [x] 2.2 Replace query/local-storage browser authentication with
  fragment/session-storage bootstrap and `X-Village-Token` requests.
- [x] 2.3 Reject invalid bodies before collector invocation and attach
  no-referrer, no-frame, no-sniff, and restrictive CSP headers.
- [x] 2.4 Update the CLI help and README for loopback defaults, intentional LAN
  binding, fragment share URLs, header clients, and trusted-network limits.

## 3. Verification and Review

- [x] 3.1 Run focused/full command-center pytest and Ruff gates, strict
  OpenSpec validation, and mutation probes for auth and body-boundary guards.
- [ ] 3.2 Request an independent Claude Opus 5 security review of the immutable
  implementation and resolve every blocking finding.
- [x] 3.3 Start the real CLI against a temporary repo and verify unauthenticated
  curl reads/writes fail while an authenticated state read and talk succeed.

## 4. Foldback and Shipping

- [ ] 4.1 Update `REFLECTION.md`, sync the development-coordination-runtime
  delta, archive the change, and validate all specs strictly.
- [ ] 4.2 Run required pre-merge gates, publish and merge the PR only when
  green, then remove the landed STATUS work row.
