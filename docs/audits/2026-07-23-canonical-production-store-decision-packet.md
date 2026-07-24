# Canonical Production Store Decision Packet

**Date:** 2026-07-23  
**Author:** Codex initial finding  
**Status:** Review input only; not PLAN truth or implementation authority  
**Required next review:** Claude opposite-provider source re-check after the
2026-07-24 evening PT capacity reset

## Decision needed

TinyAssets has final-target language for a shared PostgreSQL/Supabase control
plane, a deployed single-volume SQLite bridge, and a fixture-only PostgreSQL
prototype. The repository does not yet have an approved production migration
home or runner. This blocks production persistence for moderation, paid-market
transport, authoring, and handoff/outcome lifecycle work.

The host must approve or adapt one canonical-store decision in `PLAN.md`.
Until then:

- no provider may promote `prototype/full-platform-v0/migrations/` into
  production;
- no provider may create `009_moderation_*` (the paid-market change already
  owns the prototype renumbering to `009_market_ledger`);
- no provider may treat local SQLite plus PostgreSQL as dual authorities;
- storage-independent domain contracts and tests may proceed, but production
  persistence and §14 acceptance remain open.

## Current evidence

| Question | Current evidence | Implication |
|---|---|---|
| What persists the deployed service? | `deploy/compose.yml:46-73,165-179,229-231` mounts one Docker volume at `/data`. `tinyassets/storage/__init__.py:46,181-216,502-504,752-760` opens `.tinyassets.db` with SQLite/WAL. | Production reality is a single-host bridge, not the final shared control plane. |
| Is the paid market live in compose? | `deploy/compose.yml:58,171-172` disables the goal pool and paid market. | A new moderation or market store cannot claim compatibility with a live PostgreSQL market that is not active. |
| Is Supabase wired as canonical runtime state? | `deploy/tinyassets-env.template:150-155` solicits `SUPABASE_DB_URL`, while `deploy/docker-entrypoint.sh:39` only checks environment readability. `tinyassets/host_pool/client.py:10,130-155` uses a separate service-role client with no runtime callers outside its package/tests. | Supabase is aspirational/configured, not the active authority. A service-role-only client also does not establish the target end-user RLS boundary. |
| Can the prototype be the baseline? | `prototype/full-platform-v0/README.md:3,15,78,80` calls it throwaway; its compose uses init-on-empty SQL; `migrations/003_rls.sql:28-235` grants broad prototype policies and uses a bearer=user-id shim. The directory has duplicate `003` names. | It is fixture provenance only and must never become production history. |
| What does the final architecture say? | `docs/design-notes/2026-04-18-full-platform-architecture.md:50-53,198,206-218,229-252` selects an authoritative Supabase/PostgreSQL control plane and demotes GitHub to an export sink. | The final vision already points to shared PostgreSQL authority with local execution retained. |
| Why is work still blocked? | `PLAN.md:510,534,560-561` carries the integrated target, while `PLAN.md:580` still calls PostgreSQL-vs-GitHub unresolved. | PLAN contains contradictory state; AGENTS.md forbids implementing through it. |
| What does active OpenSpec require? | `openspec/changes/paid-market-track-e-wave-2-transport/design.md:95-109,139-150` requires a read-only deployed inventory, host-approved baseline/home, production-native SQL, checksums/history, and no prototype promotion. `complete-independent-full-platform-targets/tasks.md:10-14` asks for a numbered migration without naming that home. | The production migration system must precede domain migrations. |
| Why not dual-write? | `tinyassets/api/market.py:727-742,880-893` already has local SQLite state. Paid-market design/spec freezes v1 history and forbids dual money mutation. | Cutover may shadow-read, but exactly one store may authorize each mutation. |

## Recommended host decision

> **Canonical production store and migration home.** TinyAssets' sole
> canonical store for multi-user control-plane state is Supabase-hosted
> PostgreSQL at launch, with a self-hostable PostgreSQL exit path. It owns
> identity-bound catalog and collaboration state, moderation and audit history,
> host registry, shared inbox/bid lifecycle, and future logical market
> accounting. Host-local SQLite and filesystem state remain daemon
> execution/artifact stores and are never a second authority for multi-user
> state.
>
> Production SQL lives only in a new provider-neutral
> `db/postgres/migrations/` home, initially owned by the
> platform-persistence/control-plane lane. A dedicated migration role applies
> it through an advisory-lock, checksum-verified `schema_migrations` runner.
> `prototype/full-platform-v0/migrations/` remains fixture-only and is never a
> production baseline. The first production baseline is a read-only inventory
> of the deployed Supabase project approved by the host; domain changes then
> own only their migrations after that baseline.

This decision selects authority and migration mechanics. It does **not** decide:

- which existing local artifacts or fields migrate;
- private-instance storage placement;
- field-level public/private classification;
- retention, deletion, export, or legal-hold policy;
- analytics or training access to user data.

Those remain separate PLAN decisions and must not be inferred from selecting
PostgreSQL.

## Rollout contract

1. Inventory the actual Supabase project read-only: schemas, roles/RLS,
   extensions, functions, migration history, and deployment mechanism.
2. Record and approve the production baseline before applying feature SQL.
3. Add the migration runner with a dedicated role, advisory lock, immutable
   checksums, ordered history, and fail-closed drift detection.
4. Keep the paid market dark during establishment of the baseline.
5. Implement moderation against the canonical control-plane store; do not add
   a temporary SQLite authority that would later require dual-write migration.
6. Migrate any accepted existing shared state through a quiesced one-time
   export/import with counts, hashes, and a preserved source snapshot.
7. Shadow reads may compare old and new projections. Dual mutation and dual
   money movement are forbidden.
8. Before the first PostgreSQL-only write, rollback may return to the previous
   system. Afterwards, use forward fixes and preserve immutable audit/accounting
   history.

## Required opposite-provider review

Claude must independently:

1. re-open every cited file and verify current line-level evidence;
2. inspect current deploy and any accessible Supabase configuration without
   mutating external state;
3. search for a newer canonical-store or migration owner that supersedes this
   packet;
4. assess whether PostgreSQL control-plane authority conflicts with BYOC,
   self-hostability, privacy, deletion, or zero-host uptime principles;
5. return **APPROVE**, **ADAPT**, or **REJECT** with exact corrections.

No PLAN edit, production migration, market rollout, or moderation persistence
may cite this packet as accepted authority until that review returns and the
host approves the resulting decision.

