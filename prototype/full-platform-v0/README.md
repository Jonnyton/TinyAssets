# Full-Platform v0 Prototype

**Status:** Throwaway prototype proving the #25 schema + #27 gateway specs compose. NOT a production artifact.
**Purpose:** Demonstrate that the concept/instance schema, the `discover_nodes` RPC, and a FastMCP gateway over them actually work end-to-end before track A dispatches real coding.
**Out of scope for v0:** Supabase's full Realtime + Edge-Function stack, OAuth 2.1 + PKCE (stubbed with bearer string), multi-region Fly.io deploy, pgvector HNSW index (simple cosine works at tiny scale).

## Stack

- **Docker Compose** — `postgres:15` with pgvector extension preinstalled.
- **Python 3.11+** — FastMCP gateway + pytest for e2e.
- **psycopg** — Postgres driver.

## Running

**One-command startup** — migrations auto-apply via Postgres's `docker-entrypoint-initdb.d` convention on first container start:

```bash
cd prototype/full-platform-v0
docker compose up -d          # starts postgres + gateway; migrations run automatically
```

Gateway exposes FastMCP streamable-HTTP at `http://localhost:8001/mcp`. Postgres at `localhost:5433` (non-default to avoid host clashes).

### Running tests (requires host Python + deps)

```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
pytest tests/ -v                                   # talks to docker-compose postgres on :5433
```

### Manual migration re-apply (if SQL changes)

```bash
# Nuke the volume + restart to re-run migrations cleanly:
docker compose down -v && docker compose up -d
```

## Structure

```
prototype/full-platform-v0/
├── README.md
├── docker-compose.yml
├── requirements.txt
├── migrations/
│   ├── 001_core_tables.sql      # users, nodes, artifact_field_visibility (subset of #25 §1)
│   ├── 002_flags.sql … 008_market_ledger.sql   # applied lexicographically (see attic/README.md)
│   ├── 003_discover_nodes.sql   # the RPC from #25 §3 (requires pgvector)
│   └── attic/                   # retired migrations that must not auto-apply (002_rls.sql)
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

## Environmental blocker encountered

**Docker Desktop was not running when I tried `docker compose up -d` (2026-04-19)**. Got:

```
unable to get image 'pgvector/pgvector:pg15': failed to connect to the docker API
at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct
and if the daemon is running
```

Scaffolding is complete + ruff-clean + ready to run. **When Docker Desktop is running**, the full 5-file test suite should exercise end-to-end:

1. `docker compose up -d`
2. `docker exec -i tinyassets_v0_postgres psql -U tinyassets -d tinyassets_v0 < migrations/001_core_tables.sql` (repeat for 002, 003)
3. `pytest tests/ -v`

Tests expected green when DB is live: 10 tests across 5 files (schema×3, rls×3, discover×2, cas×2 — test_gateway has 2). Any failure = spec discrepancy worth flagging.

If Docker remains unavailable, the prototype is still valuable as **syntactically-verified SQL + ruff-clean Python** — the track-A coder can pick this up as a starting scaffold without redesigning.
