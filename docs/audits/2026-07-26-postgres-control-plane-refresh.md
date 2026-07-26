# PostgreSQL Control-Plane Current-Main Refresh

**Date:** 2026-07-26

**Base:** `origin/main` `f810f3371759736107568378f666fcb7ff2b4294`

**Historical sources:** draft PR #1670; substantive packet commits `54d2ab1a`
and `27f19947`; historical packet review remains on
`origin/codex/restack-postgres-control-plane-20260725`

**Status:** exact semantic SHA `bc5fdcbb` approved by Claude Opus 5 and three
independent Codex-side architecture/spec/verification review paths; draft PR
#1802 published. Host acceptance and every implementation/production gate
remain open.

**Authority:** target OpenSpec/audit only. No PLAN, SQL, runtime, production
inventory, Supabase mutation, migration, first write, sync, archive,
deployment, or production authority.

## Current architecture truth

`PLAN.md` makes canonical storage per-domain: PostgreSQL owns the platform's
transactional catalog, ledger, inbox, and market domains; the OKF bundle owns
commons/default-brain knowledge; GitHub is an export sink for transactional
state. Private-data custody remains deliberately per-situation and
user-selected. The current `origin/main` tree has no canonical or active
`postgres-control-plane` OpenSpec owner, so this target change fills a real
behavioral-authority gap without changing PLAN.

`Inbox` is narrowed here to durable request/admission and domain
transition/outbox state. The unresolved PLAN file-lock versus epoch-2
transactional-claim contradiction is not silently decided; scheduling,
work-claim, execution-lease, and coordination integration stay blocked on a
host-approved PLAN reconciliation and their owning capability.

## Historical branch disposition

PR #1670 was stacked on an obsolete moderation branch and could not be
retargeted unchanged. `origin/codex/restack-postgres-control-plane-20260725`
was a useful five-file source packet but was behind current main and carried
stale coordination and review truth. This lane transplanted only its OpenSpec
content onto current main, regenerated review evidence, published successor
draft PR #1802, and closed #1670 as superseded rather than force-pushing either
historical branch.

## Current-main owner reconciliation

- #1784 is merged and owns requester/provider authority. PostgreSQL cannot
  mint or replace `ProviderInvocation`, `ProviderExecutor`, or accepted-market
  B2/B13 authority.
- #1573 is merged and owns backend-neutral execution admission. A queue row,
  lock, lease, claim, or database receipt is not pre-launch authority,
  isolation proof, or post-launch actual-execution evidence.
- #1797 is merged and owns authenticated-subject branch access. Catalog and
  inbox projections must preserve unreadable-private indistinguishability and
  cannot derive readability from row presence or RLS visibility.
- #1786 is merged and owns the dark paid-market workflow/accounting state
  machine. #1798 is merged and owns descriptor/market-class identity,
  fee-schedule/version, settlement identity, and price evidence. The generic
  production migration substrate never creates capacity, payment, custody,
  chain-finality, fee, price, claim, or settlement authority.
- #1775 is merged and owns the shared load-evidence protocol. Its implementation
  successor PR #1792 is still open/draft and is not main authority; PostgreSQL
  load evidence remains `not_run` until that dependency and an accepted schema
  land.
- #1800 is merged and owns real-world handoff lifecycle plus integration with
  the evolved outcome registry. Canonical receipt storage, consent, effect
  authority, and dedup identity remain owned by the external-effect/outbound-
  boundary capabilities; #1800's task 5.4 verification/foldback is still
  unchecked. Its prototype migration `014_real_world_handoffs.sql` remains
  fixture-only provenance. This generic substrate cannot promote that SQL,
  mint handoff or receipt authority from a row, or move handoff into PostgreSQL
  without a host-approved PLAN amendment and a separately accepted handoff
  capability contract.
- Identity, visibility, custody, credential, outbound-boundary, uptime/DR,
  operator-request, artifact, and per-domain command owners retain their
  decisions. This change consumes them and does not duplicate them.

## Required current-candidate corrections

The first current-main architecture review returned `ADAPT` and required:

1. eliminate stale claims that Opus review is spend-blocked or already current;
2. regenerate exact-main review evidence rather than reuse the July 25 audit;
3. define `inbox` narrowly and block claim integration on the PLAN
   contradiction;
4. state explicitly that persistence evidence never escalates provider,
   accepted-market, execution, branch, credential, custody, capacity, payment,
   or market authority;
5. name #1784/#1786/#1797/#1798/#1573/#1800 as landed and #1792 as open;
6. preserve #1800 handoff/outcome integration without stealing canonical
   receipt/dedup ownership, keep task 5.4 open, and keep its migration
   fixture-only; and
7. preserve the production baseline, migration-home, DR/uptime, load, custody,
   per-domain identity, stock-PostgreSQL exit, and first-write gates.

Those corrections are present in semantic SHA `bc5fdcbb` and were confirmed
before its push and PR replacement.

## Verification of exact semantic candidate

- `openspec validate establish-postgres-control-plane --strict` — pass
- `openspec validate --all --strict` — 54/54 pass
- `git diff --check` — pass
- exact current-main Claude Opus 5 review — `APPROVE` at `bc5fdcbb`
- three independent architecture/spec/verification paths — `APPROVE` at
  `bc5fdcbb`
- `STATUS.md` — 60 lines; claim boundary matches the eight-file target packet

These verdicts approve target OpenSpec/audit publication only. They grant no
runtime, database, migration, deployment, or production authority.
