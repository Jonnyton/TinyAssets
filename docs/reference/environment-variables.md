# Configuration — environment variables

> **Canonical env-var reference.** Moved out of `AGENTS.md` on 2026-06-25 under
> [ADR-002](../decisions/ADR-002-static-vs-dynamic-context-budget.md): this is
> pointer-loaded *reference* content, not always-loaded *behavioral* norms, so it
> should not sit in the every-turn static context. `AGENTS.md` keeps a short
> pointer + the load-bearing invariants; the full catalog lives here.

The daemon reads configuration from env vars. Defaults are CWD-independent so
containerized deploys don't drift based on where the process was launched from.

## Scope + how this file stays complete

`AGENTS.md` claims this catalog holds **every var**, and ADR-002 pointer-loading
means a reader is told not to look further — so a gap here reads as "that var
does not exist". On 2026-07-22 an audit found 67 vars read by the daemon and
absent from this file, including the external-write kill switch, the GitHub
capability maps, and the whole WorkOS auth family. That is a correctness bug,
not doc debt.

- **Enforced scope:** every env var read under `tinyassets/` and
  `fantasy_daemon/`. `python scripts/check_env_catalog.py` diffs code against
  this file and exits non-zero on any undocumented var. Run it after adding an
  env read.
- **Also documented, not enforced:** vars read only by `deploy/`, `scripts/`,
  or `.github/workflows/`. They are marked **(deploy)** or **(tooling)** below
  so nobody deletes them as dead — the checker reports them as "not read by the
  daemon", which is expected, not a defect.
- **Ambient vars are exempt.** `PATH`, `HOME`, `GITHUB_ACTIONS`, and friends are
  read by this code but are not configuration *of* this project. The exemption
  list is `AMBIENT` in `scripts/check_env_catalog.py` — adding to it is a
  deliberate, reviewable act.

## Data + paths

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_DATA_DIR` | Canonical root for all on-disk state (SQLite checkpoint, LanceDB indexes, per-universe output dirs). Absolute path. | Platform default — Windows: `%APPDATA%\TinyAssets`; Linux/macOS/container: `~/.workflow`. |
| `TINYASSETS_UNIVERSE` | Per-universe override — specific universe dir for the stdio MCP shim (`workflow.mcp_server`). | `$TINYASSETS_DATA_DIR/default-universe`. |
| `UNIVERSE_SERVER_DEFAULT_UNIVERSE` | Which universe ID is active when none explicit. | First subdir of `$TINYASSETS_DATA_DIR`. |
| `TINYASSETS_REPO_ROOT` | Path to the local git checkout for `workflow.producers.goal_pool` + git-backed catalog writes. When unset, resolved via `Path(__file__).resolve().parent.parent`. | Derived from module path. |
| `TINYASSETS_WIKI_PATH` | Canonical root for the cross-project knowledge wiki the `wiki` tool reads/writes. Resolved via `workflow.storage.wiki_path()`; inherits `data_dir()` platform handling when unset. | `$TINYASSETS_DATA_DIR/wiki` (platform default). |
| `TINYASSETS_UPLOAD_WHITELIST` | Colon/semicolon-separated absolute-path prefixes allowed for `add_canon_from_path`. Unset = accept any absolute path. | Unset (permissive). |
| `TINYASSETS_RELEASE_STATE_PATH` | Absolute path override for `release-state.json` — the file `deploy-prod.yml` writes at deploy time and `get_status` reads back as `release_state.git_sha` (the "merged is not deployed" check, AGENTS.md Hard Rule 14). `tinyassets/api/status.py`. | `$TINYASSETS_DATA_DIR/release-state.json`. |
| `TINYASSETS_TRIGGER_RECEIPTS_DB` | Absolute path override for the wiki trigger-receipts SQLite file. Primarily a test seam; production leaves it unset. `tinyassets/wiki/trigger_receipts.py`. | `data_dir()`-relative default. |
| `TINYASSETS_CODEX_WORKDIR` | Source workspace the Codex provider inspects for coding tasks. `tinyassets/providers/codex_provider.py`. | The repo root two levels above the provider module. |

## Auth + identity

| Var | Purpose | Default |
|-----|---------|---------|
| `UNIVERSE_SERVER_USER` | Username the TinyAssets Server credits for commit-authorship + ledger write-author + request claims. Required for paid-market claims; otherwise falls back. | `anonymous`. |
| `UNIVERSE_SERVER_HOST_USER` | Host-identity username used when a request is claimed by the box running the daemon (as opposed to an individual operator). | `host`. |
| `UNIVERSE_SERVER_AUTH` | Auth mode. `"true"` / `"1"` enables OAuth-gated MCP. Disabled by default for single-operator dev. | `false`. |
| `UNIVERSE_SERVER_PORT` | Port used by `workflow.auth.wellknown` when emitting OAuth metadata URLs. | `8001`. |
| `TINYASSETS_GIT_AUTHOR` | Verbatim override for git commit author (e.g. `"TinyAssets User <user@users.noreply.tinyassets.local>"`). Highest precedence; falls through to `UNIVERSE_SERVER_USER`-derived synthetic. | Unset (synthetic from `UNIVERSE_SERVER_USER`). |
| `TINYASSETS_AUTH_VIABILITY_PROBE` | Codex refresh-viability ladder in `subscription_auth_health` (presence → `last_refresh` freshness fast path → TTL-cached live `codex exec` probe). Catches present-but-dead tokens that pass presence + `codex login status` yet 401 at call time (2026-06-25 queue-poison class; live-proven 2026-07-14). Falsy = `"0"`/`"false"`/`"off"`/`"no"` reverts to presence-only. | `on`. |
| `TINYASSETS_CODEX_AUTH_FRESH_S` | Freshness window (seconds) for `auth.json` `last_refresh` (fallback: file mtime) under which codex auth reads viable without any probe subprocess. Finite positive only. | `86400` (24h). |
| `TINYASSETS_AUTH_PROBE_TTL_S` | Cache TTL (seconds) for live-probe verdicts per `CODEX_HOME` — the supervisor gates every loop tick; the probe must not run per tick. Finite positive only. | `1800`. |
| `TINYASSETS_AUTH_PROBE_TIMEOUT_S` | Live-probe subprocess timeout (seconds); timeout reads inconclusive → "ok" (only a positive dead signature quarantines). Finite positive only. | `120`. |
| `UNIVERSE_SERVER_URL` | Public-facing server URL emitted in OAuth metadata by `tinyassets/auth/wellknown.py`. | `http://localhost:$UNIVERSE_SERVER_PORT`. |
| `UNIVERSE_SERVER_CAPABILITIES` | Comma-separated capability grants for the current actor, read by the market + runs authz paths (`tinyassets/api/market.py`, `tinyassets/api/runs.py`). Env-sourced identity — see the STATUS.md P2 concern on the `_current_actor()` env fallback before relying on it as an authz boundary. | Unset (no grants). |
| `CLAUDE_CONFIG_DIR` | Directory holding `.credentials.json` for the claude-code provider's subscription auth check. `tinyassets/providers/base.py`. | `~/.claude`. |
| `CODEX_HOME` | Directory holding the Codex CLI's `auth.json` and the on-disk auth-probe cache (`.tinyassets_auth_probe.json`). Load-bearing in production: daemon and workers run as separate containers **sharing** this dir, so the probe verdict cache must live next to `auth.json` rather than in-process. `tinyassets/providers/base.py`, `tinyassets/api/status.py`. | `~/.codex`. |

### WorkOS (AuthKit) OAuth

Active when `UNIVERSE_SERVER_AUTH=workos`. This is the production auth path for
`https://tinyassets.io/mcp`.

| Var | Purpose | Default |
|-----|---------|---------|
| `WORKOS_AUTHKIT_DOMAIN` | AuthKit domain the provider builds its issuer + endpoint set from. Without it the WorkOS provider cannot be constructed. `tinyassets/auth/workos_provider.py`, `tinyassets/auth/wellknown.py`. | Unset. |
| `WORKOS_MCP_RESOURCE` | Registered RFC 8707 resource indicator (e.g. `https://tinyassets.io/mcp`). Also the base the protected-resource-metadata URL is derived from, so OAuth discovery starts at the routed `/mcp` prefix rather than a 404ing apex. `tinyassets/auth/middleware.py`. | Unset → falls back to the server base URL. |
| `WORKOS_ALLOW_NO_AUDIENCE` | **Security-relevant.** Audience binding is required by default (fail closed); without a registered resource indicator any valid same-issuer WorkOS token would authenticate as this MCP user (confused-deputy / token reuse, RFC 8707). Truthy deliberately disables that binding — local/dev only. | Unset (audience binding enforced). |
| `WORKOS_REQUIRE_AUTH` | Truthy makes a missing token on the MCP endpoint return a 401 challenge so the client launches the AuthKit flow. Falsy lets the connector attach anonymously, and founder first-contact never fires. Production runs `0` today (anon read preserved, writes still 401 — see STATUS.md 2026-07-15). | Unset (no challenge). |

### Third-party service credentials

| Var | Purpose | Default |
|-----|---------|---------|
| `GITHUB_TOKEN` / `GH_TOKEN` | Bearer token for the GitHub REST reads in `tinyassets/api/universe.py` (checked in that order). Unset = unauthenticated, public-repo, rate-limited. Also the token source for auto-ship PR creation (`TOKEN_ENV_VARS` in `tinyassets/auto_ship_pr.py`). | Unset. |
| `SUPABASE_URL` | Base URL of the host-pool Supabase project (`https://<project>.supabase.co`). `tinyassets/host_pool/client.py`. | Unset. |
| `SUPABASE_SERVICE_ROLE_KEY` | **Secret.** Supabase *service-role* JWT (not the anon key) for server-side host-pool writes — daemons are trusted hosts, so this bypasses RLS. Treat as a full-database credential. | Unset. |
| `FA_API_KEY` | Shared API key for the `fantasy_daemon` FastAPI surface. **Unset disables auth entirely** and every caller is `"anonymous"` (development mode) — `fantasy_daemon/api.py`. | Unset (auth disabled). |

## Feature flags

Each flag reads as a string; truthy = `"on"`, `"1"`, `"true"`, `"yes"` (case-insensitive). Defaults chosen so out-of-the-box behavior matches current tier-1 contract.

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_DISPATCHER_ENABLED` | Master switch for the dispatcher. Off = every request runs inline; on = dispatch goes through the claim/bid surface. | `on`. |
| `TINYASSETS_PAID_MARKET` | Enables the paid-market bid/claim surface. `TINYASSETS_DISPATCHER_ENABLED` must also be on. Phase-G flag. | `off`. |
| `TINYASSETS_GOAL_POOL` | Enables the goal-pool producer in `workflow.producers.goal_pool` — cross-branch goal aggregation. | `off`. |
| `TINYASSETS_PRODUCER_INTERFACE` | Enables the producer-interface surface — multi-producer concurrency for branches. | `on`. |
| `TINYASSETS_TIERED_SCOPE` | Enables the tiered-memory-scope retrieval router (`workflow.retrieval.router`). Memory scope is tier-gated (node/branch/goal/user/universe). | `off` (Stage 1 monitoring; flip to `on` at Stage 2c per task #19). |
| `GATES_ENABLED` | Enables outcome-gate claims (Phase 6). When off, `gates` tool returns placeholder. | `off`. |
| `TINYASSETS_STORAGE_BACKEND` | Catalog storage backend selection. Values: empty (default), `"git"`, `"sqlite"`. | Empty (auto-select per backend factory). |
| `TINYASSETS_RUN_MAX_CONCURRENT` | Integer cap on concurrent in-flight branch runs. | Unset = unlimited. |
| `TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT` | Dedupe the no-claim idle heartbeat cycle across fleet workers (`tinyassets/idle_cycle.py`): the winner holds a run lock for the cycle's lifetime (long cycles exclude others; released on process death), and a worker skips when a DIFFERENT worker's stamp is fresh; own stamps never block. Falsy = `"0"`/`"false"`/`"off"`/`"no"`. | `on`. |
| `TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S` | Freshness window (seconds) for the idle-cycle stamp; finite positive numbers only (anything else falls back to default). Keep below the supervisor idle respawn period (~322s at backoff ceiling) and above worker phase offset; also the max heartbeat gap after a stamp-holder death. | `240`. |
| `TINYASSETS_UNIFIED_EXECUTION` | Routes daemon work through the unified Branch execution path. `cloud_worker` forces it on in the child env so worker behavior is deterministic regardless of the host env file. | `1` (on). |
| `TINYASSETS_SOUL_LOOP_DISPATCH` | Lets the Phase-5 bridge run a non-fantasy domain through the soul loop. `fantasy_daemon/__main__.py`, `tinyassets/__main__.py`. | Unset (off). |
| `TINYASSETS_NODE_ENQUEUE_ENABLED` | Master switch for in-node `enqueue_branch_run` dispatch. **Ships dark** — see the STATUS.md Work row: Codex verdict `ADAPT` requires current-universe context, queue/lineage caps, and branch-target validation before this is flipped. `tinyassets/graph_compiler.py`. | Unset (off; enqueue raises). |
| `TINYASSETS_EPISODIC_SCHEMA_MIGRATION` | Host gate for the destructive episodic-memory schema rebuild. Must be exactly `"1"`; anything else raises `PermissionError`. `dry_run=True` does not require it. `tinyassets/memory/episodic.py`. | Unset (migration refused). |
| `TINYASSETS_DEBUG_CONTEXT` | Verbose context-assembly logging in the memory manager. Truthy = `1`/`on`/`true`/`yes`. | Unset (off). |
| `TINYASSETS_SETTLEMENT_BACKEND` | Paid-market settlement backend: `internal` (ledger-only marker, no network; `tx_ref` is a local id) or `base_sepolia` (ERC-20 USDC transfer on Base Sepolia; `tx_ref` is a tx hash). `tinyassets/payments/settlement_backend.py`. | `internal`. |

## External writes + GitHub effectors

`TINYASSETS_EXTERNAL_WRITE_ENABLED` is the operator kill switch for every
outbound write. Everything else here bounds or credentials those writes.

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_EXTERNAL_WRITE_ENABLED` | **Operator panic-button kill switch.** Checked before any gate — including Phase-1 backward-compat packets — so a falsy value makes every external-write effector return dry-run evidence regardless of capability or consent. `tinyassets/effectors/github_pr.py`. | Unset (writes disabled → dry-run). |
| `TINYASSETS_EXTERNAL_WRITE_DRY_RUN` | Forces dry-run evidence even when writes are enabled and a capability is present. Applies to the GitHub PR and Twitter post effectors. | Unset (off). |
| `TINYASSETS_GITHUB_PUSH_CAPABILITIES` | **Secret.** Canonical JSON map of `{"<owner>/<repo>": "<token>"}` granting destination-scoped GitHub *push* credentials. Keys by the literal `owner/repo` string so distinct destinations cannot collide on a suffix-encoded name. Vended by `tinyassets.auth.provider.vend_github_destination_secret`. | Unset (no push capability). |
| `TINYASSETS_GITHUB_PR_CAPABILITIES` | **Secret. Legacy.** The older PR-specific capability map, still accepted as a fallback so unmigrated hosts keep working. Prefer `TINYASSETS_GITHUB_PUSH_CAPABILITIES`. | Unset. |
| `TINYASSETS_GITHUB_READ_CAPABILITIES` | **Secret.** JSON map granting *read* tokens, deliberately separate from the write map. Unset falls back to unauthenticated reads (public repos only, rate-limited); a private repo without a read token returns `denied` per file rather than leaking the write token. | Unset. |
| `TINYASSETS_GITHUB_API` | GitHub REST API base URL — a test/enterprise seam. `tinyassets/api/universe.py`. | `https://api.github.com`. |
| `TINYASSETS_GITHUB_REPO` | `owner/repo` the universe API reads PR/issue context from. | `Jonnyton/TinyAssets`. |
| `TINYASSETS_GITHUB_READ_MAX_FILES` | Cap on files returned by one `github_read` effector call. | `20`. |
| `TINYASSETS_GITHUB_READ_MAX_BYTES_PER_FILE` | Per-file byte cap for `github_read`. | `100000`. |
| `TINYASSETS_GITHUB_READ_MAX_TOTAL_BYTES` | Total byte cap across one `github_read` call. | `400000`. |
| `TINYASSETS_GITHUB_SEARCH_MAX_RESULTS` | Cap on results returned by one `github_search` effector call. | `50`. |

## Auto-ship (coding loop)

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_AUTO_SHIP_PR_CREATE_ENABLED` | Gates real PR creation from the auto-ship lane. Falsy leaves PR creation in dry-run and records the reason in the attempt ledger. `tinyassets/auto_ship_pr.py`. | Unset (dry-run). |
| `TINYASSETS_AUTO_SHIP_REPO` | Target `owner/name` for auto-ship PRs. Validated against a simple GitHub path-part pattern; a malformed value raises. | `Jonnyton/TinyAssets`. |
| `TINYASSETS_AUTO_SHIP_RUBRIC_MODE` | Rubric eval mode: `off` / `warn` / `enforce`. Unknown values resolve to `warn`. `enforce` promotes rubric-only rule IDs to blocking violations — flip only after producers populate the rubric fields. | `warn`. |
| `TINYASSETS_AUTO_SHIP_TRAJECTORY_MODE` | Coding-lane trajectory eval mode: `off` / `warn` / `enforce`. Unknown values resolve to `warn`. `enforce` promotes a conclusive path-quality failure to a blocking violation on its own channel. | `warn`. |
| `TINYASSETS_AUTO_SHIP_OBSERVATION_WINDOW_SECONDS` | Window `get_status.auto_ship_health` observes. A malformed value falls back to the default rather than breaking the public status probe. | `86400` (24h). |

## Run execution + concurrency limits

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_CHILD_POOL_SIZE` | Pool size for sub-branch (depth ≥ 1) invocations. Clamped to ≥ 1. | `MAX_INVOKE_BRANCH_DEPTH + 1` (`6`). |
| `TINYASSETS_INVOCATION_MAX_DEPTH` | Runtime cap on sub-branch invocation depth. Host-tunable for research workflows needing deeper chains. | `MAX_INVOKE_BRANCH_DEPTH` (`5`). |
| `TINYASSETS_MAX_CHILD_RETRIES_TOTAL` | Total child-retry budget per run. Clamped to ≥ 0. `tinyassets/graph_compiler.py`. | `5`. |
| `TINYASSETS_NODE_ENQUEUE_MAX_DEPTH` | Spawn-depth cap for in-node enqueue — each queue level is a full independent run. | `2`. |
| `TINYASSETS_NODE_ENQUEUE_MAX_PER_RUN` | Per-run enqueue budget; bounds the branching *factor*. | `50`. |
| `TINYASSETS_NODE_ENQUEUE_MAX_QUEUE` | Ceiling on pending+running tasks one enqueue may grow the global queue to. | `500`. |
| `TINYASSETS_NODE_ENQUEUE_MAX_LINEAGE` | Cap on one lineage's total enqueues, so a single lineage cannot consume the global queue and starve other work. | `200`. |
| `TINYASSETS_ORPHANED_RUN_GRACE_SECONDS` | Grace period before a run with no progress reports is treated as orphaned. `0` / `off` / `false` / `no` / `disabled` turns the sweep off. | `3600`. |
| `TINYASSETS_RECEIPT_PAYLOAD_MAX_BYTES` | Max serialized receipt payload size. | `65536`. |
| `TINYASSETS_SELECTOR_TIMEOUT_S` | Timeout (seconds) for selector-dispatch prompts. `tinyassets/api/selector_dispatch.py`. | `60.0`. |
| `TINYASSETS_BRANCH_TASK_HEARTBEAT_INTERVAL_S` / `TINYASSETS_BRANCH_TASK_HEARTBEAT_INTERVAL_SECONDS` | Branch-task heartbeat interval (seconds). The `_S` form wins; the `_SECONDS` form is an accepted alias read only when `_S` is unset. `fantasy_daemon/__main__.py`. | `30.0`. |
| `TINYASSETS_REQUEST_TYPE_PRIORITIES` | Comma-separated `request_type` allowlist this daemon will claim (e.g. `bug_investigation,paid_market,branch_run`). Empty = accept all types. `tinyassets/dispatcher.py`. | Unset (accept all). |

## Storage caps + retention

Caps are **off by default**: unset, zero, or negative disables the cap and the
subsystem reports `unbounded`. Soft cap fires at `SOFT_RATIO` (0.80) of the hard
cap; hard cap is 1.0 of the configured value.

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_CAP_CHECKPOINTS_BYTES` | Hard byte cap for the checkpoints subsystem. `tinyassets/storage/caps.py`. | Unset (cap disabled). |
| `TINYASSETS_CAP_LOGS_BYTES` | Hard byte cap for the logs subsystem. | Unset (cap disabled). |
| `TINYASSETS_CAP_RUN_ARTIFACTS_BYTES` | Hard byte cap for run artifacts. | Unset (cap disabled). |
| `TINYASSETS_CAP_ACTIVITY_LOG_BYTES` | Soft byte cap that triggers `activity.log` rotation. `tinyassets/storage/rotation.py`. | Unset (rotation disabled). |
| `TINYASSETS_CAP_UNIVERSE_OUTPUTS_BYTES` | Hard byte cap that triggers oldest-first pruning of `<data_dir>/output/`. **Deletes files** when set. | Unset (pruning disabled). |
| `TINYASSETS_CHECKPOINT_RETENTION_KEEP_LAST` | Number of most-recent checkpoints retained per thread. `tinyassets/checkpointing/sqlite_saver.py`. | `500`. |
| `TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS` | Age (days) past which run transcripts under `<data_dir>/runs/` are moved out. | `30`. |

## Worker + daemon identity

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_WORKER_ID` | Unique id for this worker. Load-bearing: when unset, `cloud_worker` materializes the shared `DEFAULT_HOST_USER` (`cloud-droplet`) into the child env, which several manually-started supervisors could share — and reclaiming "our own" non-unique id would steal a live peer's task (the 2026-06-25 wedge). Set it per worker. | `cloud-droplet` (shared — set explicitly). |
| `TINYASSETS_RUNTIME_INSTANCE_ID` | Per-process runtime instance id used with `TINYASSETS_WORKER_ID` for task claims. `cloud_worker` sets it in the child env, or pops it when absent. | Unset. |
| `TINYASSETS_DAEMON_ID` | Daemon-registry id override for this process. | Unset (registry selection). |
| `TINYASSETS_LOOP_DAEMON_ID` | Project-loop daemon id. Takes precedence over `TINYASSETS_DAEMON_ID`, which is the fallback. | Unset. |
| `TINYASSETS_WORKER_MODEL` | Explicit model override for the worker, applied regardless of provider. | Unset (per-provider default). |
| `TINYASSETS_CODEX_MODEL` | Codex model to request. Note the two call sites disagree: `tinyassets/providers/codex_provider.py` defaults to `gpt-5.4`, while `cloud_worker`'s `DEFAULT_WORKER_MODELS` uses `gpt-5`. | `gpt-5.4` (provider) / `gpt-5` (cloud worker). |
| `TINYASSETS_CLAUDE_MODEL` | Claude model to request for the claude-code provider. | `claude`. |

## Bug investigation

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_BUG_INVESTIGATION_GOAL_ID` | Goal id auto-triggered bug investigations bind to. Empty disables auto-trigger — filing falls back to wiki-write-only. | Unset (auto-trigger disabled). |
| `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID` | Canonical branch-def id investigations route through. When set, `enqueue_investigation_request` goes via the general dispatcher. | Unset. |

## LLM + provider routing

| Var | Purpose | Default |
|-----|---------|---------|
| `OLLAMA_HOST` | Local Ollama endpoint URL. Presence is the "local-LLM-bound" signal `get_status` reports. | Unset. |
| `ANTHROPIC_BASE_URL` | Alternate Anthropic endpoint (e.g. self-hosted relay). Presence also flips `llm_endpoint_bound` to truthy. | Unset. |
| `TINYASSETS_PIN_WRITER` | Pin a specific writer provider by name (e.g. `"claude-code"`, `"codex"`). Overrides the provider router's fallback chain. | Unset. |
| `TINYASSETS_CODEX_AUTH_JSON_B64` | **(deploy)** Base64-encoded `~/.codex/auth.json` bundle for the Codex provider's subscription auth. `deploy/docker-entrypoint.sh` decodes it on container startup and writes `~/.codex/auth.json`; rotate on each Codex CLI re-auth. | Unset. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Preferred Claude provider auth on the droplet: a `claude setup-token` long-lived token Claude Code reads straight from the env (no file, rotation-safe). The entrypoint reports it when present and no credentials file exists. Same secret the CI workers use. | Unset. |
| `TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64` | **(deploy)** Base64 of a subscription `~/.claude/.credentials.json` bundle (the Codex-style mirror). `deploy/docker-entrypoint.sh` decodes it to `$CLAUDE_CONFIG_DIR/.credentials.json` only when that file is missing (first boot / volume recovery), never clobbering a rotated in-place token. A fresh `/data` volume with neither this nor `CLAUDE_CODE_OAUTH_TOKEN` leaves claude-code "Not logged in" (2026-06-25 loop-wedge root cause). | Unset. |
| `TINYASSETS_ALLOW_API_KEY_PROVIDERS` | Explicit opt-in for API-key-backed daemon providers. Default project-wide policy, including self-hosted daemons, is subscription-only: API-key env vars are ignored unless this is truthy. Use only when the host deliberately chooses to run an API-key daemon. | `off` |
| `TINYASSETS_CLOUD_DAEMON_SUBSCRIPTION_ONLY` | **(deploy)** Deprecated no-op placeholder retained in `deploy/compose.yml` and `deploy/workflow-env.template` for migration safety. No code path reads this flag; use `TINYASSETS_ALLOW_API_KEY_PROVIDERS` directly. | Unset (no-op). |
| `OPENAI_API_KEY` | Stripped by `deploy/docker-entrypoint.sh` unless `TINYASSETS_ALLOW_API_KEY_PROVIDERS=1`. The legacy `codex login --with-api-key` path is intentionally not run; Codex auth flows through `TINYASSETS_CODEX_AUTH_JSON_B64`. | Unset. |
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `XAI_API_KEY` | Provider API keys for the Gemini / Groq / Grok providers respectively. Ignored unless `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy. | Unset. |
| `FANTASY_DAEMON_LLM_TYPES` | Comma-separated list of LLM types the fantasy daemon prefers (e.g. `"claude,codex"`). Filters provider selection. | Unset. |

## Observability + uptime

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_MCP_CANARY_URL` | **(deploy)** Public MCP URL the uptime canary probes. | `https://tinyassets.io/mcp` (canonical apex; `mcp.tinyassets.io` is an Access-gated internal tunnel origin, not user-facing — host directive 2026-04-20). |
| `TINYASSETS_LOOP_STALL_WINDOW_S` | Window (seconds) after which `get_status` reports the loop stalled — the signal that distinguishes "claiming but never completing" from healthy operation. Added because the 2026-06-25 wedge ran ~3 weeks with workers looking busy. `tinyassets/api/status.py`. | `1800`. |
| `TAB_WATCHDOG_INTERVAL_S` | **(tooling)** Interval (seconds) for the tray tab-watchdog's polling. `scripts/tab_watchdog.py`. | `60`. |
| `TINYASSETS_CLAUDE_CHAT_SCREENSHOTS` | **(tooling)** User-sim skill flag — capture a screenshot on every `claude_chat.py` response settle. Cost: ~200 KB per response. | Unset (off). |

**Canonical resolver:** `workflow.storage.data_dir()` is the single
source of truth for `TINYASSETS_DATA_DIR` resolution. Do not re-implement
the precedence logic elsewhere — call the resolver.

**Container deploys:** set `TINYASSETS_DATA_DIR=/data` + bind-mount the
host path to `/data`. See `deploy/README.md` for the full pattern.

## Local secrets — vault-first

Local operator secrets (Cloudflare tokens, DigitalOcean token, Hetzner creds, OpenAI key) load from a password manager, not a plaintext file. Vendor is chosen via `TINYASSETS_SECRETS_VENDOR` — `1password` (default), `bitwarden`, or `plaintext` (migration-period opt-out, to be retired after cutover).

Bootstrap on a fresh machine:

```bash
# 1. install vendor CLI (see docs/design-notes/2026-04-22-secrets-vault-integration.md)
# 2. sign in:
eval $(op signin)                       # 1Password
# or: bw login && export BW_SESSION=$(bw unlock --raw)   # Bitwarden
# 3. load into current shell:
set -a; source scripts/load_secrets.sh; set +a
```

One-shot migration from the legacy `$HOME/workflow-secrets.env`:

```bash
python scripts/migrate_secrets_to_vault.py --vendor 1password --dry-run
python scripts/migrate_secrets_to_vault.py --vendor 1password
# verify, then shred ~/workflow-secrets.env
```

Canonical list of keys: `scripts/secrets_keys.txt` (edit there, not in shell profiles). Full rationale + vendor comparison + bootstrap runbook: `docs/design-notes/2026-04-22-secrets-vault-integration.md`. GitHub Actions secrets are out of scope — they stay in repo settings.
