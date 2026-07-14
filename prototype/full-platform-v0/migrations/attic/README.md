# Attic — retired migrations

- `002_rls.sql` — DEAD: references `concept_visibility`, which `001_core_tables.sql`
  never created (deferred to Track L). It cannot apply to this schema; `003_rls.sql`
  is the superseding rewrite. Moved out of `migrations/` because docker-compose
  mounts that directory as `/docker-entrypoint-initdb.d` and applies every `.sql`
  lexicographically — a dead file aborts fresh container startup.
  Validated on vanilla Postgres 16, chain 001 → 002_flags → 003_rls → 004 → 005 →
  006 → 007 → 008 (see `docs/WORK-2026-07-11-DRIVING-SESSION.md` §3).
