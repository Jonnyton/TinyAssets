# PostgreSQL Control-Plane Restack Review

Date: 2026-07-25
Reviewer/provider: Codex GPT-5.6
Current-main base: `8ec01ab34802f349d4ca97527c0aaed0633da11c`
Historical source: draft PR #1670, substantive OpenSpec commit `49cb3de2`
Disposition: local, target-only, review-blocked; not build or production authority

Current design anchors:

- `PLAN.md:558-561` scopes PostgreSQL to catalog/ledger/inbox/market and
  leaves private custody open.
- `PLAN.md:608-610` resolves the PostgreSQL/OKF/GitHub authority split and
  names host/private-brain/vault/platform-held as candidate custody modes.

## Why PR #1670 Cannot Be Retargeted Unchanged

PR #1670 is stacked on the obsolete draft moderation branch from PR #1662.
Its decision packet predates the current PLAN foldback and carries three stale
assumptions:

1. PostgreSQL owns an open-ended shared control plane rather than the current
   catalog, ledger, inbox, and market transactional domains.
2. All private content is host-only rather than custody-neutral and selected
   per situation by the owning policy and user instance.
3. Moderation is the presumed first transaction even though readiness and
   shared-dependency impact must choose the first domain.

Retargeting the stacked branch would also import obsolete coordination and
moderation artifacts. This restack therefore transplanted only the five
OpenSpec files from `49cb3de2` onto exact current main and recreated current
coordination metadata.

## Exact Transplant

- `openspec/changes/establish-postgres-control-plane/.openspec.yaml`
- `openspec/changes/establish-postgres-control-plane/proposal.md`
- `openspec/changes/establish-postgres-control-plane/design.md`
- `openspec/changes/establish-postgres-control-plane/tasks.md`
- `openspec/changes/establish-postgres-control-plane/specs/postgres-control-plane/spec.md`

No moderation runtime, reflection, old decision packet, SQL, deployment,
Supabase, production-data, API, or PLAN change was imported.

## Current-Main Adaptations

- Narrowed canonical PostgreSQL authority to catalog, ledger, inbox, and
  market. Another domain requires both a host-approved PLAN amendment and its
  own separately accepted OpenSpec change.
- Replaced global host-only private-data prohibitions with an explicit
  custody-neutral contract. An owning policy and per-instance selection may
  choose a host, private universe brain, vault, or approved platform-held
  store. Provider credentials, signing keys, and secret authority never enter
  the shared control plane.
- Preserved OKF/default-brain, artifact, vault, GitHub-export, and host-local
  authorities without allowing dual mutation authority inside one domain.
- Required exactly one migration-history executor for TinyAssets-owned
  application schemas. Supabase Branching, `supabase db push`, dashboard SQL,
  ORM auto-create, and other paths must be disabled or subordinate for those
  schemas. Supabase-managed schemas retain inventoried, version-pinned vendor
  history owned by their adapters.
- Forbid updates, deletes, or checksum replacement of committed migration
  history. Repairs are additive forward migrations; exceptional baseline
  reconciliation requires quiescence, a preserved snapshot, explicit dual
  approval, and immutable audit.
- Bound database connection mode to role: migrations, dumps, restores,
  persistent sessions, LISTEN/NOTIFY, and advisory locks never use transaction
  pooling. Accepted application pooling must be driver-tested.
- Expanded recovery/exit proof beyond SQL dumps to Storage object bodies,
  excluded custom-role secrets, subscriptions, publications, replication
  slots, downtime, RPO, and RTO. Drills default to synthetic data; any
  production snapshot has explicit custody/residency approval, encryption,
  least privilege, retention, cleanup, and credential-replacement controls.
- Made preview branches data-less by default and allowed only versioned,
  privacy-safe synthetic production-shaped seeds with access-classified counts,
  hashes, and size evidence and no production values, digests, or sensitive
  low-cardinality distributions.
- Revoked raw domain table/sequence reads and DML and direct context-setter
  access from ordinary roles. Only narrowly granted authenticated
  query/command boundaries may establish transaction-local context and access
  protected rows; forged context,
  exception/cancel cleanup, and pooled reuse require denial tests.
- Adopted the shared `production-load-evidence` protocol while retaining
  PostgreSQL-specific populations, SLOs, and thresholds in this capability.
  Execution waits for the dependent `implement-production-load-harness`
  implementation and accepted evidence-schema version; no local substitute is
  allowed.
- Made notification-adapter fault proof conditional on an enabled, separately
  accepted adapter while retaining durable version/outbox recovery as an
  unconditional invariant.
- Removed the hard-coded moderation pilot. The first dark slice must be the
  shortest ready catalog, ledger, inbox, or market transaction with accepted
  identity, custody, and domain dependencies.
- Refreshed applicable dependencies on the active identity/universe,
  paid-market Wave 2, operator-request, outbound-boundary, custody, uptime, and
  load owners without blocking pure domain implementation or absorbing their
  decisions. Moderation has no PostgreSQL dependency unless its own future
  PLAN amendment and capability delta accept one.

## Review And Publication Gate

Three independent Codex reviews agreed that the PostgreSQL restack is the
highest-impact safe lane and that PR #1670 must be adapted, not retargeted
unchanged. A literal current-main Claude Opus 5 review remains mandatory before
push, host acceptance, implementation, sync, archive, or production action.

The 2026-07-25 Claude CLI attempt failed before inference with:

`You've hit your monthly spend limit · raise it at claude.ai/settings/usage?from=cc_cli_limit_message`

The model rate-limit reset did not clear the account monthly-spend ceiling.
This artifact therefore records no Claude verdict. The branch remains local.

## Verification

Fresh on 2026-07-25 in
`C:\Users\Jonathan\Projects\wf-postgres-control-plane-restack`:

- `openspec validate establish-postgres-control-plane --strict` — PASS.
- `openspec validate --all --strict` — PASS, 47/47 items.
- `git diff --check` — PASS.
- `git diff --no-index --check -- NUL
  docs/audits/2026-07-25-postgres-control-plane-restack-review.md` — PASS.
- Remote-branch check — no
  `origin/codex/restack-postgres-control-plane-20260725`; the lane is local.
- Independent architecture/PLAN exact-diff review — APPROVE after requiring
  PLAN+OpenSpec for domain expansion, fail-closed complete restore, and a
  normative data-less preview default.
- Independent security/data-authority exact-diff review — APPROVE after
  requiring raw-table/context denial, vendor-history separation, immutable
  migration history, sanitized evidence, synthetic-first recovery, and
  regenerated credentials.
- Independent OpenSpec/execution exact-diff review — APPROVE after making
  notification-adapter proof conditional and load execution dependent on the
  landed shared harness/schema.

These Codex-family approvals satisfy independent local quality review. They do
not replace the required fresh opposite-provider Opus 5 verdict or host
acceptance and do not authorize publication or implementation.
