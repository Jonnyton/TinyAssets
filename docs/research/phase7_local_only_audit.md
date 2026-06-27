# Phase 7 Pre-work: Local-Only Assumptions Audit

Read-only audit of the current codebase to surface every place that
assumes "one host machine, one logged-in user." Phase 7's executable
spec needs to know what already neighbors a multi-tenant boundary,
what's flat single-tenant, and what shape each migration would take.

Source of ground truth: live state in `tinyassets/*.py` as of the
post-cluster-#58→#67 commit. Per-area breakdown follows.

## 1. Identity & actor attribution

- **Single source today**: `tinyassets/universe_server.py:163`
  `_current_actor()` reads `UNIVERSE_SERVER_USER` env var, defaults
  `"anonymous"`. Used everywhere user attribution lands (ledger,
  branch/goal/run author, judgment author).
- **Auth surface present but unused at the dispatcher boundary**:
  `tinyassets/auth/provider.py` already implements an `OAuthProvider`
  protocol with PKCE + Dynamic Client Registration shape, and a
  `DevModeAuthProvider` that returns anonymous for any token. Live
  MCP tool dispatchers do NOT consult it — actor comes from env.
- **Migration shape**: replace the env-var read with a request-scoped
  identity lookup. FastMCP context already exposes per-request state;
  thread it through `_current_actor()`. Auth provider already exists,
  so this is wiring, not greenfield.

## 2. Universe data root

- **Single source today**: `_base_path()` → `Path(os.environ.get(
  "UNIVERSE_SERVER_BASE", "output")).resolve()`. Every universe lives
  as a sibling directory under the same root. `_universe_dir()` has a
  path-traversal guard.
- **Per-universe artifacts**: prose files, `notes.json`, `canon/`,
  `output/<universe>/.author_server.db`, `knowledge.db`, LanceDB
  vector tables, `.langgraph_runs.db`. All flat under one root.
- **Migration shape**: per-tenant root (`output/<tenant_id>/<universe>`)
  is the obvious move. `_base_path()` becomes tenant-resolving. The
  path-traversal guard already prevents user-supplied universe IDs
  from escaping the base; same guard at the tenant boundary.

## 3. SQLite stores (write-locking ceiling)

Five distinct SQLite databases per universe:

| File | Owner | Purpose |
|------|-------|---------|
| `.author_server.db` | `tinyassets/author_server.py:_connect` | branches, nodes, goals, lineage, judgments, ledger |
| `.runs.db` | `tinyassets/runs.py:_connect` | run rows, run_events, node_edit_audits |
| `.langgraph_runs.db` | `tinyassets/runs.py:1059` (SqliteSaver) | LangGraph checkpointer |
| `knowledge.db` | `tinyassets/knowledge/knowledge_graph.py` | KG entities/edges/facts |
| `world_state.db` (per-domain) | domain code | world-state queries |

- **Concurrency**: `sqlite3.connect(..., timeout=30.0)` + `PRAGMA
  busy_timeout=30000` everywhere. Per-process serialization works for
  one host. **Single-writer ceiling is real** — multi-host writes
  cannot share a SQLite file safely.
- **Migration shape**: the `_connect` helpers are already the
  abstraction seam. A pluggable `Storage` protocol with sqlite/postgres
  implementations can swap underneath without touching call sites.
  STATUS.md already flagged the Postgres migration as known future
  work.

## 4. LanceDB singleton

- **Singleton enforced**: `tinyassets/retrieval/vector_store.py:27`
  `get_db(path)` lazily creates one `lancedb.DBConnection` per
  process, refuses CWD-relative defaults (post-#48/#51 hardening).
- **Cross-universe risk**: explicit path required, so the singleton
  switches connections when path changes. Multi-tenant safe at the
  process level; not safe across processes if tenants share disk.
- **Migration shape**: per-tenant subdirectory under base. Same
  singleton mechanism still works because path is the cache key.

## 5. Run executor (background work)

- **Process-local**: `tinyassets/runs.py:1230` shared
  `ThreadPoolExecutor(max_workers=TINYASSETS_RUN_MAX_CONCURRENT or 4)`
  thread-prefix `workflow-run`. Future map keyed by `run_id`.
- **Implication**: runs are tied to the process that submitted them.
  No cross-host scheduling, no resume across host restart (recovery
  marks in-flight runs as `interrupted`; doesn't re-execute).
- **Migration shape**: replace direct `executor.submit` with a queue
  abstraction (Redis/RabbitMQ/Postgres-LISTEN). Workers can run on
  any host that can reach the storage layer. SqliteSaver checkpointer
  becomes the resumption substrate (it already supports thread_id
  resumption — that's why we kept it).

## 6. Provider credentials

- **Process-env today**: each provider in `tinyassets/providers/*.py`
  reads its API key from a `*_API_KEY` env var at construction time
  (`GROQ_API_KEY`, `GEMINI_API_KEY`, `GROK_API_KEY`, etc).
- **Implication**: host-machine-wide credentials, not per-tenant.
  If multiple users share one host, they all use the host's keys.
- **Migration shape**: per-tenant credential store, looked up at
  provider construction. Either a small SQLite/secrets table keyed on
  tenant_id, or BYO-key-from-MCP-context.

## 7. Desktop / tray / tunnel (host-side only)

- **Host-only by design**: `tinyassets/desktop/host_tray.py`,
  `tray.py`, `launcher.py`, `dashboard.py` — local UI for the host
  operator. Not part of the multi-tenant runtime.
- **Tunnel**: `universe_tray.py` runs `cloudflared` with a hardcoded
  `TUNNEL_TOKEN`, ingress `tinyassets.io → http://localhost:8001`.
  One named tunnel = one public origin per host.
- **MCP server bind**: tray spawns `mcp.run(host='0.0.0.0',
  port=8001)`. One MCP listener per host.
- **Migration shape**: desktop stays host-only (PLAN.md principle:
  "MCP clients, local host dashboard"). Tunnel + bind don't need to
  change for Phase 7 — multi-tenancy lives behind one origin.

## 8. Active universe + default-universe selection

- **File-based session**: `output/.active_universe` is a sticky
  marker. `_default_universe()` reads `UNIVERSE_SERVER_DEFAULT_UNIVERSE`
  env or first universe directory.
- **Implication**: process-global "current universe" — fine for
  single-user, hostile for multi-tenant if two users want different
  defaults concurrently.
- **Migration shape**: per-session/per-tenant active-universe in
  storage instead of a flat file. Already half-modeled in
  `author_server.py` sessions table.

## 9. Logs

- **Single tree today**: `logs/daemon.log`, `logs/mcp_server.log`,
  `logs/tunnel.log` written from project root regardless of which
  tenant triggered the run. Universe-scoped logging is not
  implemented.
- **Migration shape**: route per-tenant logs into
  `output/<tenant>/<universe>/logs/` and keep host-process logs
  (tunnel, tray) at the root. Two log channels, distinct retention
  policies.

## Multi-tenantization Difficulty Heatmap

| Area | Difficulty | Notes |
|------|-----------|-------|
| Identity | **Low** | Auth provider exists; wire FastMCP context |
| Universe data root | **Low** | Path helper, one chokepoint |
| SQLite stores | **Medium** | Storage protocol per `_connect`; Postgres backend |
| LanceDB singleton | **Low** | Already path-keyed |
| Run executor | **Medium-High** | Queue abstraction + cross-host workers |
| Provider creds | **Medium** | Per-tenant secrets table |
| Desktop/tray/tunnel | **N/A** | Host-only by design; no change needed |
| Active universe | **Low** | Move from file to session row |

## Recommended Phase 7 sequencing

1. Identity wiring (auth → context → `_current_actor`) — unblocks
   per-tenant attribution everywhere downstream.
2. Tenant-scoped `_base_path` + `_universe_dir` — storage isolation.
3. Per-tenant credential store — provider construction reads from it.
4. Storage protocol for the SQLite-backed layer (no Postgres yet —
   just the seam, so Postgres lands later without churn).
5. Run executor remains process-local for v1; queue abstraction is
   Phase 7.5+ once tenant count requires it.
