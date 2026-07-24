# Independent review — 2026-07-24

Environment: Windows, branch `codex/constrain-engine-providers`, based on
`origin/main` `412a876add4a1df914dea7017cd94f924e4aa30d`.

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
