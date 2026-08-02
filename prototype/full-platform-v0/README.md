# Full-Platform v0 Prototype

**Status:** Throwaway prototype proving the #25 schema + #27 gateway specs compose. NOT a production artifact.
**Purpose:** Demonstrate that the concept/instance schema, the `discover_nodes` RPC, and a FastMCP gateway over them actually work end-to-end before track A dispatches real coding.
**Out of scope for v0:** Supabase's full Realtime + Edge-Function stack, OAuth 2.1 + PKCE (stubbed with bearer string), multi-region Fly.io deploy, pgvector HNSW index (simple cosine works at tiny scale).

## Stack

- **Docker Compose** — `postgres:15` with pgvector extension preinstalled.
- **Python 3.11+** — FastMCP gateway + pytest for e2e.
- **psycopg** — Postgres driver.

## Running

**One-command startup** — the `migrate` service applies every pending fixture
migration through `schema_migrations` before the gateway starts:

```bash
cd prototype/full-platform-v0
docker compose up -d          # starts postgres, migrates, then starts gateway
```

Gateway exposes FastMCP streamable-HTTP at `http://localhost:8001/mcp`. Postgres at `localhost:5433` (non-default to avoid host clashes).

### Running tests (requires host Python + deps)

```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
pytest tests/ -v                                   # talks to docker-compose postgres on :5433
```

### Migration replay and fixture baselining

```bash
python migrate.py
# Only for an exact verified pre-runner fixture:
python migrate.py --baseline-existing
```

The runner hashes exact SQL bytes, holds a bounded PostgreSQL advisory lock,
requires unique gap-free migration IDs, and commits each SQL file with its
history row in one transaction. Checksum drift, gaps, ambiguous pre-existing
schemas, and lock timeout fail closed.

## Structure

```
prototype/full-platform-v0/
├── README.md
├── docker-compose.yml
├── requirements.txt
├── migrations/
│   ├── 001_core_tables.sql      # users, nodes, artifact_field_visibility (subset of #25 §1)
│   ├── 002_flags.sql … 009_market_ledger.sql   # replay-safe fixture chain
│   ├── 006_discover_nodes.sql   # the RPC from #25 §3 (establishes pgvector)
│   └── attic/                   # retired migrations that must not auto-apply (002_rls.sql)
├── migrate.py                   # checksums, history, locking, replay/resume
├── gateway.py                    # FastMCP skeleton per #27
├── tests/
│   ├── conftest.py               # fixtures: fresh DB state per test
│   ├── test_schema.py            # schema migrates cleanly
│   ├── test_rls.py               # non-owner sees public-concept-only
│   ├── test_discover_nodes.py    # RPC returns ranked candidates
│   ├── test_cas.py               # version-based CAS blocks silent overwrites
│   └── test_gateway.py           # FastMCP tool → RPC roundtrip
```

## What we're proving

1. **Schema migrates cleanly.** The §1 schema from #25 actually creates in Postgres 15 + pgvector.
2. **RLS works.** Non-owner SELECT on `nodes` returns only `concept_visibility='public'` rows with private fields stripped.
3. **`discover_nodes` RPC runs.** Returns ranked candidates with the signal block per #25 §3.1 shape.
4. **CAS holds under concurrent writes.** Two simulated writers racing on the same node — one wins, other gets zero-row-affected.
5. **Gateway tool calls land.** FastMCP tool → RPC round-trips with RLS context applied via `SET LOCAL request.jwt.claims`.

Not in scope: Realtime, performance at scale, HNSW index tuning, Supabase Auth, multi-region. Those live in the real track-A build.

## OPEN flags encountered during prototyping

See inline comments in SQL + Python files. Consolidated list:

1. **v0 auth shim** — `app.current_user_id` GUC via `SET LOCAL` replaces Supabase's `request.jwt.claims` for prototyping. Real build uses Supabase-native JWT decode per #27 §5.3. Both paths are mediated by the `auth.uid()` SQL function — only the source of truth changes.
2. **v0 embedding dim = 16** — stub; real is 1536. Tests use deterministic `stub_embedding(seed)` to keep them reproducible without a real embedding service.
3. **v0 skips HNSW index** — cosine scan is fine at tiny row counts. Real build per #25 §1.2 uses `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`.
4. **v0 uses `TO PUBLIC` in RLS policies** — real Supabase uses `TO authenticated`. Semantic is identical for the owner-check predicates.
5. **v0 skips Realtime entirely** — not a v0 concern; gateway is pure HTTP. Real build adds Realtime channels per #27 §1 + #30 §3.
6. **Gateway `bearer_token == user_id`** — stub for v0. Real build decodes Supabase JWT + pulls `sub` claim.

## Fixture-only authority

This runner and SQL remain a throwaway local fixture. They are not a production
migration home, do not prove the deployed Supabase baseline, and must never be
used as wallet-funding or chain-settlement authority.
