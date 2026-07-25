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
  - **Completed (2026-07-25).** The reviewed inventory now explicitly
    classifies the Epoch-2 admission/task/quarantine/maintenance/rollout stores,
    rejects every unknown main-database table, freezes exact-founder-home and
    path rules, and provides a process-shared shared/exclusive writer barrier
    plus the durable fence/journal boundary contract. Safety tests cover foreign
    bindings/grants, active daemon/request/task references, credentials,
    symlinks/reparse points, schema growth, contention, and every recovery fault
    boundary. No scoped mutation is implemented in this task.
- [x] 1.2 Implement the read-only operator plan for one allowlisted external test principal and make
  unknown/repetition semantics explicit: unknown alias or non-allowlisted subject fails closed; an
  allowlisted subject with no state is a no-op; replay of a completed plan returns its receipt and
  cannot touch a newly created home.
  - **Completed (2026-07-25).** The operator-only CLI loads an explicit
    credential-free private roster file, resolves only an allowlisted alias,
    emits no raw subject, and returns a stable plan binding roster/inventory
    revisions, a domain-separated principal digest, exact row versions,
    resolved paths, blockers, and preservation scope. Empty state is a stable
    no-op; completed-plan receipt lookup is read-only and cannot touch
    replacement state.
- [x] 1.3 Only after 1.1-1.2 pass, implement apply with exact founder-home rather than ACL-derived
  ownership, lease/fencing, path containment, explicit cross-store actions, and deterministic crash
  recovery; prove every other principal and all preserved commons, history, audit/market, daemon, and
  credential state remain unchanged; expose no MCP or API route.
  - **Completed (2026-07-25).** Operator-only apply now revalidates the exact
    founder-home plan under a process-shared exclusive barrier and durable
    principal/home fence, stages the home by same-filesystem rename, deletes
    only exact reviewed rows, and writes the commit witness with those deletes
    in one SQLite transaction. Content-free journal recovery restores
    pre-commit state or completes post-commit cleanup at every fault boundary;
    completed replay returns its receipt without touching a replacement home.
    All writer process entrypoints recover before traffic and hold shared
    barriers. The global reset is unchanged and no MCP/API route was added.
- [x] 1.4 Add a CI-executable mutation/fault-injection proof that goes red when principal filtering is
  removed or widened and when either side of the filesystem/SQLite recovery boundary is broken.
  - **Completed (2026-07-25).** The dedicated pytest mutation proof widens the
    ACL delete predicate and requires exact-primary-key rejection, corrupts the
    SQLite commit witness after deletion and requires recovery to stop before
    restoring files, and injects a rollback rename failure and requires loud,
    retryable recovery. Removing either filter/recovery guard makes the proof
    red in CI.

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
  - **Premise: live but blocked (2026-07-24).** Depends on host provisioning,
    deployment of the dedicated fingerprint key, and tasks 1.1-1.4 plus
    3.1-3.3. No direct-MCP or fake rendered proof was substituted.

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
  - **Premise: live; partially completed / blocked (2026-07-24).** Canonical
    and mirrored `ui-test` instructions were updated in `3c8083db`. The public
    canary, two rendered clients, concurrency proof, and post-fix clean-use
    check require deployment and the blocked reset/host-identity prerequisites.
