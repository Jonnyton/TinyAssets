# Repeatable test identity and operator-scoped reset

## Why

TinyAssets has useful in-process multi-tenant coverage: the current suite simulates twelve distinct
subjects and exercises request-local identity, concurrent home creation, ACLs, and authorization.
That does not prove the real user path. No acceptance run has used two distinct authorization-server
issued WorkOS identities through ordinary live connector OAuth, and a stable external subject cannot
be returned safely to first-contact state between rendered-client tests.

The existing reset is deliberately global. It removes every universe and hosted daemon while
preserving the commons and run history. Reusing it for one test account would destroy unrelated state.
The stranded implementation in PR #1560 is not a safe shortcut: it infers deletion ownership from
mutable ACLs, dynamically sweeps tables, duplicates user data in backups, and does not close the
filesystem/SQLite crash boundary.

## What Changes

- Add an operator-private, access-controlled roster of allowlisted test-identity aliases mapped to
  real external subject IDs. It is never committed or logged, and every test identity authenticates
  through the same OAuth and grant path as an ordinary founder.
- Add a dry-run-first, host-operator maintenance command that returns one allowlisted test principal
  to first-contact state. It is never an MCP tool, API route, user deletion feature, or authorization
  bypass.
- Make scoped cleanup fail closed: home selection comes from the exact founder-home binding, never
  from an admin ACL; every affected store is explicitly classified; ambiguous/shared state blocks
  apply; concurrent writers are quiesced; interrupted operations recover deterministically.
- Add self-only request identity evidence to the existing status read surface so a rendered test can
  establish a deployment-scoped principal fingerprint and bearer presence without receiving a raw
  subject, token, or other secret.
- Require an executable mutation/fault-injection proof that widening the principal filter or breaking
  the crash boundary fails the suite.

Cross-user enumerate/read/write isolation is owned by `universe-visibility` plus
`identity-auth-and-access-control`, not this reset change. Provider-auth evidence classification is
owned by the provider-status lane / PR #1570. Neither residual is implemented or accepted here.

## Capabilities

### New Capabilities

- `test-identity-harness`: Real external test identities, operator-private credential-free roster
  rules, requester-authorized compute boundaries, and rendered-live acceptance evidence requirements.

### Modified Capabilities

- `universe-lifecycle-and-soul`: Preserve the no-public-delete contract while adding a tightly scoped
  host-only test-maintenance reset exception.
- `identity-auth-and-access-control`: Expose self-only request identity evidence consistently through
  the existing status reads without exposing bearer material.

## Impact

- Planning scope: operator reset safety, request-local identity evidence, test roster/runbook, and
  rendered two-account acceptance.
- Public tool count stays unchanged. The only public response change is token-safe identity evidence
  on existing status reads.
- The global clean-slate reset, commons, wiki, run history, market/audit records, and maintainer or
  provider credentials remain outside the scoped deletion surface.
- Acceptance model execution uses only requester-owned BYOC or an accepted-market compute/model grant.
  Without that complete bundle it proves birth/identity with no provider invocation; platform or
  maintainer hardware, local routes, quota, accounts, credentials, and auth homes are never eligible.
- PR #1560 / commit `375b0155` remains DO NOT MERGE and is superseded. Only independently re-authored,
  reviewed ideas may be salvaged after this change is approved.
