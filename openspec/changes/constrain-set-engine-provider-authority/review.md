# Independent review — 2026-07-24

Environment: Windows, branch `codex/constrain-engine-providers`, based on
`origin/main` `129a68f728a0bcb9a7bfaeddd396993178f42189`.

This is a planning-only OpenSpec review. No runtime, test, deployment, or
packaging files are changed by this lane.

## Ownership review

The review confirmed that this change owns persistent provider-destination
assignment, fail-closed request/assignment intersection at routing time, and
provider transport launch lifecycle only.

It preserves these separate owners:

- `universe-creation` owns requester and market semantic execution authority.
- A subordinate future `provider-authority-propagation` change may carry the
  accepted authority through call sites, but may not define another requester
  authority, router, receipt, vault, market, or credential-isolation contract.
- `provider-attempt-receipts` owns result-local attempt evidence.
- The provider-auth overlay owns ambient-credential isolation.
- Paid-market and distributed-execution contracts own accepted market grants,
  remote execution, leases, settlement, and economic accounting.

## Security review

The first independent review returned `ADAPT` with two blocking findings:

1. The ordinary provider router incorrectly owned accepted-market leases and
   accounting.
2. A host-local capability could rescue universe work that omitted request
   authority.

Both findings were corrected. The independent re-review returned `APPROVE`:

- `market_rented` remains `allowed_providers=[]` before and after acceptance
  in the ordinary router. Accepted work uses only the signed paid-market /
  distributed-execution path, whose agreements, leases, settlement, and
  accounting never enter ordinary provider invocation or launch records.
- The host-local capability is bootstrap-minted, identity-validated,
  non-serializable, and bound to enumerated non-request-reachable operations.
  It cannot authorize graph, run, resume, version, policy, judge, extract,
  embed, first-contact, or any other user/request/universe lineage, and it
  exposes no maintainer credentials, quota, accounts, models, or hardware.

## Verification

Independent scoped verification returned `SHIP` on 2026-07-24:

- `openspec validate constrain-set-engine-provider-authority --strict`:
  1/1 valid.
- `openspec validate --all --strict`: 42/42 valid, 0 failed.
- `git diff --check origin/main`: exit 0.
- Planning boundary: zero runtime, test, deployment, or packaging files.
- Added-line secret scan: 0 hits.
- Competing-authority scan outside this change: 0 hits.
- Market lease/accounting and host-local rescue contradiction scans: 0 hits.

Repo-wide pytest and Ruff were not used as gates for this planning-only change.
An earlier pytest run exceeded its time budget, and repo-wide Ruff reported
pre-existing line-length findings. This review therefore makes no claim that
the unrelated runtime test or lint baselines are green.

Implementation remains entirely unchecked and gated on the dependencies in
`tasks.md`, especially the opposite-provider verdict on #1660 and the accepted
requester-authority fold into `universe-creation`.

## Current-main refresh review — 2026-07-24

The lane was rebased onto `origin/main`
`129a68f728a0bcb9a7bfaeddd396993178f42189` after PR #1692 landed
request-local operator admission. The refresh:

- treats #1692's verdict, priority grant, and queued v1 `BranchTask` as
  admission/ordering artifacts, never provider, compute, market, lease,
  settlement, or spending authority;
- separately denies provider authority to any current or future admission
  receipt or scheduling claim;
- calls the provider-layer carrier a provider-destination call scope so it
  does not imply ownership of requester or distributed-execution authority;
- removes the landed operator-priority row from `STATUS.md`; and
- leaves every runtime task unchecked.

The independent reviewer first returned `ADAPT` because the draft implied
#1692 had landed a future transactional admission receipt. The wording was
corrected to distinguish #1692's landed artifacts from current/future
admission artifacts. Focused re-review returned `APPROVE` with no remaining
blocking or important findings.

Fresh Windows verification on 2026-07-24:

- targeted strict OpenSpec validation: 1/1 valid;
- full strict OpenSpec validation: 42/42 valid;
- `git diff --check origin/main`: exit 0;
- implementation tasks: 0/41 checked;
- exact branch scope: planning/coordination only, with no runtime, test,
  packaging, deployment, website, or script files.

The verifier returned `SHIP` for publishing this planning refresh. Runtime
implementation remains gated by `tasks.md`.
