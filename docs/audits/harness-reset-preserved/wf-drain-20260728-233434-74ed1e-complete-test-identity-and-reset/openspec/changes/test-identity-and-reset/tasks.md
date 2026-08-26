# Tasks - repeatable test identity and operator-scoped reset

> Reconciled against `origin/main` and PR #1560 on 2026-07-22; no implementation task was complete
> at that time.
> PR #1560 / `375b0155` is unsafe to merge wholesale and does not satisfy this ledger.
>
> Builder premise verification (2026-07-24): scope is limited to 1.1-1.4,
> 3.1-3.3, and the minimum safe preparation for 2.1-2.2. Provider-auth evidence,
> cross-user visibility, and any broader deletion/account lifecycle work remain
> deferred and out of scope.

## 1. Safe operator-scoped reset

- [x] 1.1 Before writing mutating code, freeze the exact cross-store reset/preserve/block inventory,
  ownership/path rules, durable process-shared fenced writer barrier, plan digest inputs, and
  content-free journal plus SQLite commit-witness state machine; land red tests for foreign bindings
  and grants, active market/daemon/run references, credential and receipt blockers, schema growth,
  symlinks/junctions/reparse points, concurrent writers, and every pre/post-rename/commit/cleanup
  fault point.
  - **Completed (2026-07-25).** The inventory classifies current and Epoch-2
    stores, default-denies unclassified home/root store formats and unknown
    root-run tables, freezes exact resettable columns/keys/foreign-key
    authority with hidden-column and trigger/view rejection, and blocks foreign
    actors plus preserved cascade dependencies. Root, database, sidecar, home,
    barrier, journal, and staging paths reject links, reparse points,
    hardlinks, and mount crossings. A process-shared reader-slot/all-slot
    writer barrier supports concurrent services while excluding reset; the
    legacy API acquires a replacement barrier before releasing its live one.
- [x] 1.2 Implement the read-only operator plan for one allowlisted external test principal and make
  unknown/repetition semantics explicit: unknown alias or non-allowlisted subject fails closed; an
  allowlisted subject with no state is a no-op; replay of a completed plan returns its receipt and
  cannot touch a newly created home.
  - **Completed (2026-07-25).** The credential-free operator CLI requires an
    explicit private roster (POSIX mode or Windows owner/DACL verified),
    resolves only allowlisted aliases, never emits raw subjects, and produces
    a stable content-free plan over inventory/roster revisions, principal
    digest, exact row versions, resolved paths, the home directory filesystem
    ID plus entry/content digest, blockers, and preservation scope. Read-only
    SQLite inspection creates no WAL/SHM sidecars. No-state plan/apply is a
    stable mutation-free no-op, including a root with no database. Completed
    replay returns its old receipt before inspecting or touching replacement
    state.
- [x] 1.3 Only after 1.1-1.2 pass, implement apply with exact founder-home rather than ACL-derived
  ownership, lease/fencing, path containment, explicit cross-store actions, and deterministic crash
  recovery; prove every other principal and all preserved commons, history, audit/market, daemon, and
  credential state remain unchanged; expose no MCP or API route.
  - **Completed (2026-07-25).** Apply revalidates the exact founder-home plan,
    roster-principal binding, filesystem object identity, and entry/content
    digest under the exclusive barrier and again immediately before rename. It
    writes the content-free journal before the operation witness, stages by
    same-filesystem rename, and commits exact reviewed deletes with the SQLite
    witness. Recovery re-derives all paths, compares journal/SQLite evidence,
    restores pre-commit state or completes post-commit cleanup, and durably
    flushes every rename/cleanup parent. All supported writer entrypoints join
    a clean shared barrier before traffic. The global reset is unchanged and no
    MCP/API route or action was added.
- [x] 1.4 Add a CI-executable mutation/fault-injection proof that goes red when principal filtering is
  removed or widened and when either side of the filesystem/SQLite recovery boundary is broken.
  - **Completed (2026-07-25).** The 13-case CI proof mutates both
    `founder_home` and `universe_acl` selection predicates plus exact delete
    keys, corrupts the commit witness and journal/path evidence, injects
    partial journal publication and rollback rename failures, covers pre/post
    journal, rename, commit, cleanup, and completion windows, verifies durable
    reverse-rename flushes, and rejects a linked staging ancestor. Separate
    mutation challenges prove that path-only home binding, permissive future
    store classification, and release-before-acquire legacy fencing each turn
    their reviewer regression red.

## 2. Real multiple test identities

- [ ] 2.1 Provision and document at least two distinct authorization-server-issued WorkOS test
  subjects with ordinary connector OAuth and founder grants; keep alias-to-subject mappings only in
  an access-controlled operator-private roster that is never committed or logged.
  - **Premise: live; host action required (2026-07-24).** The credential-free
    provisioning/runbook is in `docs/ops/test-identities.md`. Creating the two
    WorkOS users and storing their private aliases requires host access and was
    not fabricated in source.
- [ ] 2.2 Prove through rendered live connectors that both identities travel the ordinary auth/grant
  path after 1.1-1.4 and 3.1-3.3 pass; forbid fake providers, forged headers, direct request-context
  injection, shared secrets, token persistence, and raw subjects in durable evidence. Model execution
  requires complete requester-owned BYOC or an accepted-market compute/model grant; otherwise prove
  birth/identity with zero provider calls and structured held/setup-required state. Platform or
  maintainer hardware, local routes, quota, accounts, credentials, auth homes, and limits are never
  eligible.
  - **Premise refreshed; host-blocked (2026-07-29).** PR #1846 records the
    dedicated fingerprint-key deployment, a green public canary, and one
    rendered anonymous fingerprint. The remaining proof still requires two
    ordinary authorization-server-issued test founders, private roster state,
    and distinct authenticated rendered fingerprints. No direct-MCP or fake
    rendered proof was substituted.

## 3. Self-identity observability

- [x] 3.1 Carry a request-local bearer-presence bit without retaining the token and return only a
  versioned deployment-scoped principal fingerprint derived with domain-separated HMAC-SHA-256 or an
  equivalent reviewed PRF under a dedicated high-entropy key, failing closed with no plain-hash or
  raw-subject fallback, from the shared status implementation for first-contact, anonymous, and normal
  paths through both `get_status` and `read_graph target=status`.
  - **Premise: live; completed (2026-07-24).** Implemented in
    `f9da52aa` and adapted after cross-family review: missing/invalid keys fail
    closed for fingerprint integrity while the observational status surface
    stays available with an explicit unavailable marker. The packaged runtime
    mirror is identical.
- [x] 3.2 Add regression coverage for authenticated/anonymous/invalid bearer behavior, alias parity,
  request-context cleanup, self-only semantics, no ambient host/maintainer identity fallback, and
  absence of tokens, grants, provider credentials, and auth-home paths.
  - **Premise: live; completed (2026-07-24).** Focused coverage proves
    authenticated, anonymous, first-contact, missing-key, alias-parity,
    request-cleanup, raw-subject redaction, short/wrong-type key handling,
    version validation, provisioned fingerprint output, and status-surface
    availability without skips. The public canary calls `get_status` and
    requires `active_host` plus `release_state`.
- [ ] 3.3 Update the canonical `ui-test` workflow and rendered acceptance to assert resolved identity
  from status rather than browser cookies/UI inference, storing only aliases or deployment-scoped
  fingerprints; run the public canary, Claude.ai and ChatGPT rendered host matrix, required concurrency
  proof, and post-fix clean-use check before acceptance. The repeatable first-contact portion depends on
  1.1-1.4; the two-account rendered acceptance in 2.2 depends on all of this section.
  - **Premise refreshed; partially completed / blocked (2026-07-29).**
    Canonical and mirrored `ui-test` instructions were updated in `3c8083db`.
    PR #1846 records the deployed fingerprint key, green public canary, and a
    host-visible ChatGPT anonymous fingerprint. The authenticated two-founder
    Claude.ai/ChatGPT matrix, required concurrency proof, and post-fix
    clean-use check still require host identities and host-visible sessions.
