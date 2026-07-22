# Tasks - repeatable test identity and operator-scoped reset

> Reconciled against `origin/main` and PR #1560 on 2026-07-22. No implementation task is complete.
> PR #1560 / `375b0155` is unsafe to merge wholesale and does not satisfy this ledger.

## 1. Safe operator-scoped reset

- [ ] 1.1 Before writing mutating code, freeze the exact cross-store reset/preserve/block inventory,
  ownership/path rules, durable process-shared fenced writer barrier, plan digest inputs, and
  content-free journal plus SQLite commit-witness state machine; land red tests for foreign bindings
  and grants, active market/daemon/run references, credential and receipt blockers, schema growth,
  symlinks/junctions/reparse points, concurrent writers, and every pre/post-rename/commit/cleanup
  fault point.
- [ ] 1.2 Implement the read-only operator plan for one allowlisted external test principal and make
  unknown/repetition semantics explicit: unknown alias or non-allowlisted subject fails closed; an
  allowlisted subject with no state is a no-op; replay of a completed plan returns its receipt and
  cannot touch a newly created home.
- [ ] 1.3 Only after 1.1-1.2 pass, implement apply with exact founder-home rather than ACL-derived
  ownership, lease/fencing, path containment, explicit cross-store actions, and deterministic crash
  recovery; prove every other principal and all preserved commons, history, audit/market, daemon, and
  credential state remain unchanged; expose no MCP or API route.
- [ ] 1.4 Add a CI-executable mutation/fault-injection proof that goes red when principal filtering is
  removed or widened and when either side of the filesystem/SQLite recovery boundary is broken.

## 2. Real multiple test identities

- [ ] 2.1 Provision and document at least two distinct authorization-server-issued WorkOS test
  subjects with ordinary connector OAuth and founder grants; keep alias-to-subject mappings only in
  an access-controlled operator-private roster that is never committed or logged.
- [ ] 2.2 Prove through rendered live connectors that both identities travel the ordinary auth/grant
  path after 1.1-1.4 and 3.1-3.3 pass; forbid fake providers, forged headers, direct request-context
  injection, shared secrets, token persistence, and raw subjects in durable evidence. Model execution
  requires complete requester-owned BYOC or an accepted-market compute/model grant; otherwise prove
  birth/identity with zero provider calls and structured held/setup-required state. Platform or
  maintainer hardware, local routes, quota, accounts, credentials, auth homes, and limits are never
  eligible.

## 3. Self-identity observability

- [ ] 3.1 Carry a request-local bearer-presence bit without retaining the token and return only a
  versioned deployment-scoped principal fingerprint derived with domain-separated HMAC-SHA-256 or an
  equivalent reviewed PRF under a dedicated high-entropy key, failing closed with no plain-hash or
  raw-subject fallback, from the shared status implementation for first-contact, anonymous, and normal
  paths through both `get_status` and `read_graph target=status`.
- [ ] 3.2 Add regression coverage for authenticated/anonymous/invalid bearer behavior, alias parity,
  request-context cleanup, self-only semantics, no ambient host/maintainer identity fallback, and
  absence of tokens, grants, provider credentials, and auth-home paths.
- [ ] 3.3 Update the canonical `ui-test` workflow and rendered acceptance to assert resolved identity
  from status rather than browser cookies/UI inference, storing only aliases or deployment-scoped
  fingerprints; run the public canary, Claude.ai and ChatGPT rendered host matrix, required concurrency
  proof, and post-fix clean-use check before acceptance. The repeatable first-contact portion depends on
  1.1-1.4; the two-account rendered acceptance in 2.2 depends on all of this section.
