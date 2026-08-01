# Cloud-drain current-main prerequisite refresh

Date: 2026-07-31 (America/Los_Angeles)
Rebased verification revision: `1c97a41bb22df0b2aa3bc09c540c3ac0b7c759b2`
Environment: Windows development worktree `wf-cloud-drain-activation`

## Verdict

The recovery-to-normal deploy chain is landed and the canonical public MCP
canary is green. The repaired local OpenSpec drain is green and remains the only
live drain; at 2026-07-31 21:27 America/Los_Angeles it reported 48 refinable
targets and dispatched a refinery worker. The cloud drain is not live and
neither queue epoch may be enabled by this slice.

Current main now contains the dark activation CAS, activation-bound epoch-2
admission, dark background Branch binding/attempt stores and lifecycle
services, and outbound-owned exact GitHub reconciliation. The epoch-2 cloud
consumer remains explicitly disabled by `EPOCH2_QUEUE_CONSUMER_READY = False`.

The remaining task-1.2 blocker was not compute supervision. It was the absence
of a durable requester-owned provider binding. The repository already has the
correct exact-destination owner in `ConnectionLedger`: authenticated-principal
ownership, exact universe grant, exact connection class/destination/scopes,
revocation, and credential-blind proxy resolution. The older
`.effector_consents.db` row is not sufficient for cloud activation because its
`granted_by` field is caller-influenced and it is not the outbound boundary's
canonical grant.

## This slice

This branch adds the first dark `ProviderWorkBinding` domain/read/revocation
slice behind the existing provider-authority OpenSpec owner. Records are
secret-free and bounded: owner, universe, provider, assignment and
credential-reference digests, allowed operation/role, budgets, generation,
expiry, and revocation. IDs and serialized records are explicitly non-bearer.
The SQLite owner validates exact provider-binding state inside its own
control-plane transaction and fails closed on tamper, stale generation,
revocation, expiry, scope mismatch, or restart. Cloud preflight then performs
sequential, non-atomic provider-binding, grant, and connection reads. Execution
must revalidate both authority owners just in time; preflight is not a
cross-store snapshot.

Production issuance is deliberately not implemented. The store's only install
path is named `install_test_binding`, is disabled by default, and raises unless
the test-fixture flag is explicitly enabled. The future authenticated/server
background roots in provider-authority section 3 must supply production
issuance. Consequently a production preflight with no canonical binding fails
closed; this slice cannot bootstrap its own authority.

The cloud composition then resolves, without activation or credential access:

1. the exact active provider binding named by the immutable definition; and
2. the exact active `pull-request-writer` grant for
   `github.com/<definition.repository>` owned by the same authenticated
   principal and universe, including `pull_requests:write`.

Missing, revoked, foreign, broad, wrong-repository, expired provider bindings,
under-budget bindings, non-exact connection scopes, or a non-one-PR action cap
fail before queue, provider, credential, or outbound mutation. The current
`ConnectionGrant` model is revocation-based and has no expiry field; this slice
does not claim or invent grant expiry.

## Deliberate remaining gates

- The general provider-work receipt/claim/reservation ledger is still absent;
  a binding cannot launch provider work.
- Task 1.2 remains unchecked until the resolved authority is persisted through
  activation-bound epoch-2 admission and the background-attempt owner with
  restart/concurrent-trigger proof.
- Task 4.1 must fence epoch 1 and the local tray before any epoch-2 consumer is
  enabled. A dark cloud activation record is not permission to overlap live
  tray/cloud execution.
- Tasks 2.1-3.2, 5.1, and 5.2 still own bounded PR delivery, receipts/health,
  phone controls/evolution, release evidence, and the real 24-hour PC-off run.
- PR #1935 is source-only; current-main diagnostic publication #2032/#2033
  still requires its immutable deploy and rendered reconnect proof. No OAuth
  continuity claim is assumed from those commits.

## Fresh verification

Verified 2026-07-31 in the Windows worktree after review adaptation:

- `python -m pytest tests/test_provider_work_authority.py tests/test_user_owned_cloud_automation.py tests/test_outbound_connection_ledger.py tests/test_outbound_effect_boundary.py tests/test_github_pr_reconciliation.py tests/test_background_branch_authority.py tests/test_background_branch_authority_store.py tests/test_background_branch_authority_service.py tests/test_branch_tasks_v2.py tests/test_request_admission_store.py tests/test_workos_provider.py -q` — 487 passed, two pre-existing dependency deprecation warnings.
- Ruff on the three implementation files and two focused test files — clean.
- strict OpenSpec validation for both owning changes — valid.
- `git diff --check` — clean.

No production state was changed by this audit or implementation slice.

## Independent review

Claude Code 2.1.220 reported the hard monthly spend limit on 2026-07-31, so
the host-approved fresh-context same-provider fallback reviewed exact head
`6be7474f`. It returned `ADAPT`: caller-constructed binding seeds, an
under-constrained coherent CAS, broad provider/connection scopes, and an
unchecked action cap could overstate authority. The findings were converted
to regression tests and folded by requiring a trusted server resolver,
deterministic identity validation, one legal immutable active-to-revoked CAS,
exact operation/role/budgets, exact GitHub scopes, and an exact one-PR cap.
The failed concurrency rerun also exposed and fixed simultaneous WAL setup
contention. Rereview of `274ad027` correctly found that a structural resolver
still did not establish canonical provenance and that several regressions were
not isolated. The resolver and all production creation APIs were removed;
fixture installation is disabled by default, coherent owner and scope transfer
tests now begin from an otherwise legal revoke transition, wrong-owner,
wrong-universe, and wrong-destination fixtures keep exact scopes and action
caps, and missing/foreign/raising principals, missing/broad caps, and expired
bindings have dedicated cases. A new exact-head review is still required before
merge.
