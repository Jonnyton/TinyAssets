# Configuration — environment variables

> **Canonical env-var reference.** Moved out of `AGENTS.md` on 2026-06-25 under
> [ADR-002](../decisions/ADR-002-static-vs-dynamic-context-budget.md): this is
> pointer-loaded *reference* content, not always-loaded *behavioral* norms, so it
> should not sit in the every-turn static context. `AGENTS.md` keeps a short
> pointer + the load-bearing invariants; the full catalog lives here.

The daemon reads configuration from env vars. Defaults are CWD-independent so
containerized deploys don't drift based on where the process was launched from.

## Data + paths

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_DATA_DIR` | Canonical root for all on-disk state (SQLite checkpoint, LanceDB indexes, per-universe output dirs). Absolute path. | Platform default — Windows: `%APPDATA%\TinyAssets`; Linux/macOS/container: `~/.workflow`. |
| `TINYASSETS_UNIVERSE` | Per-universe override — specific universe dir for the stdio MCP shim (`workflow.mcp_server`). | `$TINYASSETS_DATA_DIR/default-universe`. |
| `UNIVERSE_SERVER_DEFAULT_UNIVERSE` | Which universe ID is active when none explicit. | First subdir of `$TINYASSETS_DATA_DIR`. |
| `TINYASSETS_REPO_ROOT` | Path to the local git checkout for `workflow.producers.goal_pool` + git-backed catalog writes. When unset, resolved via `Path(__file__).resolve().parent.parent`. | Derived from module path. |
| `TINYASSETS_WIKI_PATH` | Canonical root for the cross-project knowledge wiki the `wiki` tool reads/writes. Resolved via `workflow.storage.wiki_path()`; inherits `data_dir()` platform handling when unset. | `$TINYASSETS_DATA_DIR/wiki` (platform default). |
| `TINYASSETS_UPLOAD_WHITELIST` | Colon/semicolon-separated absolute-path prefixes allowed for `add_canon_from_path`. Unset = accept any absolute path. | Unset (permissive). |

## Auth + identity

| Var | Purpose | Default |
|-----|---------|---------|
| `UNIVERSE_SERVER_USER` | Username the TinyAssets Server credits for commit-authorship + ledger write-author + request claims. Required for paid-market claims; otherwise falls back. | `anonymous`. |
| `UNIVERSE_SERVER_HOST_USER` | Host-identity username used when a request is claimed by the box running the daemon (as opposed to an individual operator). | `host`. |
| `UNIVERSE_SERVER_AUTH` | Auth mode. `"true"` / `"1"` enables OAuth-gated MCP. Disabled by default for single-operator dev. | `false`. |
| `UNIVERSE_SERVER_PORT` | Port used by `workflow.auth.wellknown` when emitting OAuth metadata URLs. | `8001`. |
| `TINYASSETS_GIT_AUTHOR` | Verbatim override for git commit author (e.g. `"TinyAssets User <user@users.noreply.workflow.local>"`). Highest precedence; falls through to `UNIVERSE_SERVER_USER`-derived synthetic. | Unset (synthetic from `UNIVERSE_SERVER_USER`). |

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

## LLM + provider routing

| Var | Purpose | Default |
|-----|---------|---------|
| `OLLAMA_HOST` | Local Ollama endpoint URL. Presence is the "local-LLM-bound" signal `get_status` reports. | Unset. |
| `ANTHROPIC_BASE_URL` | Alternate Anthropic endpoint (e.g. self-hosted relay). Presence also flips `llm_endpoint_bound` to truthy. | Unset. |
| `TINYASSETS_PIN_WRITER` | Pin a specific writer provider by name (e.g. `"claude-code"`, `"codex"`). Overrides the provider router's fallback chain. | Unset. |
| `TINYASSETS_CODEX_AUTH_JSON_B64` | Base64-encoded `~/.codex/auth.json` bundle for the Codex provider's subscription auth. `deploy/docker-entrypoint.sh` decodes it on container startup and writes `~/.codex/auth.json`; rotate on each Codex CLI re-auth. | Unset. |
| `CLAUDE_CODE_OAUTH_TOKEN` | Preferred Claude provider auth on the droplet: a `claude setup-token` long-lived token Claude Code reads straight from the env (no file, rotation-safe). The entrypoint reports it when present and no credentials file exists. Same secret the CI workers use. | Unset. |
| `TINYASSETS_CLAUDE_CREDENTIALS_JSON_B64` | Base64 of a subscription `~/.claude/.credentials.json` bundle (the Codex-style mirror). `deploy/docker-entrypoint.sh` decodes it to `$CLAUDE_CONFIG_DIR/.credentials.json` only when that file is missing (first boot / volume recovery), never clobbering a rotated in-place token. A fresh `/data` volume with neither this nor `CLAUDE_CODE_OAUTH_TOKEN` leaves claude-code "Not logged in" (2026-06-25 loop-wedge root cause). | Unset. |
| `TINYASSETS_ALLOW_API_KEY_PROVIDERS` | Explicit opt-in for API-key-backed daemon providers. Default project-wide policy, including self-hosted daemons, is subscription-only: API-key env vars are ignored unless this is truthy. Use only when the host deliberately chooses to run an API-key daemon. | `off` |
| `TINYASSETS_CLOUD_DAEMON_SUBSCRIPTION_ONLY` | Deprecated no-op placeholder retained in `deploy/compose.yml` and `deploy/workflow-env.template` for migration safety. No code path reads this flag; use `TINYASSETS_ALLOW_API_KEY_PROVIDERS` directly. | Unset (no-op). |
| `OPENAI_API_KEY` | Stripped by `deploy/docker-entrypoint.sh` unless `TINYASSETS_ALLOW_API_KEY_PROVIDERS=1`. The legacy `codex login --with-api-key` path is intentionally not run; Codex auth flows through `TINYASSETS_CODEX_AUTH_JSON_B64`. | Unset. |
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `XAI_API_KEY` | Provider API keys for the Gemini / Groq / Grok providers respectively. Ignored unless `TINYASSETS_ALLOW_API_KEY_PROVIDERS` is truthy. | Unset. |
| `FANTASY_DAEMON_LLM_TYPES` | Comma-separated list of LLM types the fantasy daemon prefers (e.g. `"claude,codex"`). Filters provider selection. | Unset. |

## Observability + uptime

| Var | Purpose | Default |
|-----|---------|---------|
| `TINYASSETS_MCP_CANARY_URL` | Public MCP URL the uptime canary probes. | `https://tinyassets.io/mcp` (canonical apex; `mcp.tinyassets.io` is an Access-gated internal tunnel origin, not user-facing — host directive 2026-04-20). |
| `TAB_WATCHDOG_INTERVAL_S` | Interval (seconds) for the tray tab-watchdog's polling. `scripts/tab_watchdog.py`. | `60`. |
| `TINYASSETS_CLAUDE_CHAT_SCREENSHOTS` | User-sim skill flag — capture a screenshot on every `claude_chat.py` response settle. Cost: ~200 KB per response. | Unset (off). |

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
