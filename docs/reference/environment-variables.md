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
| `TINYASSETS_GIT_AUTHOR` | Verbatim override for git commit author (e.g. `"TinyAssets User <user@users.noreply.tinyassets.local>"`). Highest precedence; falls through to `UNIVERSE_SERVER_USER`-derived synthetic. | Unset (synthetic from `UNIVERSE_SERVER_USER`). |
| `TINYASSETS_AUTH_VIABILITY_PROBE` | Codex refresh-viability ladder in `subscription_auth_health` (presence → `last_refresh` freshness fast path → TTL-cached live `codex exec` probe). Catches present-but-dead tokens that pass presence + `codex login status` yet 401 at call time (2026-06-25 queue-poison class; live-proven 2026-07-14). Falsy = `"0"`/`"false"`/`"off"`/`"no"` reverts to presence-only. | `on`. |
| `TINYASSETS_CODEX_AUTH_FRESH_S` | Freshness window (seconds) for `auth.json` `last_refresh` (fallback: file mtime) under which codex auth reads viable without any probe subprocess. Finite positive only. | `86400` (24h). |
| `TINYASSETS_AUTH_PROBE_TTL_S` | Cache TTL (seconds) for live-probe verdicts per `CODEX_HOME` — the supervisor gates every loop tick; the probe must not run per tick. Finite positive only. | `1800`. |
| `TINYASSETS_AUTH_PROBE_TIMEOUT_S` | Live-probe subprocess timeout (seconds); timeout reads inconclusive → "ok" (only a positive dead signature quarantines). Finite positive only. | `120`. |
| `TINYASSETS_IDENTITY_FINGERPRINT_KEY` | Dedicated high-entropy HMAC key for self-only `get_status` / `read_graph target=status` principal fingerprints. Minimum 32 UTF-8 bytes; never reuse OAuth, provider, maintainer, roster, or bearer material. Missing, short, or invalid values leave the status surface available but set `principal_fingerprint` to `null` with an explicit `identity_evidence.status=unavailable` marker. Canonical local-vault key: `scripts/secrets_keys.txt`; production supplies it through `/etc/tinyassets/env`. | Unset; identity evidence is explicitly unavailable while operational status remains readable. |
| `TINYASSETS_IDENTITY_FINGERPRINT_VERSION` | Safe version tag prefixed to deployment-scoped identity fingerprints. Allowed characters: letters, digits, `.`, `_`, `-`. Change when rotating the key so evidence cannot silently cross rotations. Invalid values leave identity evidence explicitly unavailable without weakening or failing the status surface. | `v1`. |

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
| `TINYASSETS_SUPERVISOR_LIVENESS_TTL_S` | How long `get_status` may reuse a supervisor-liveness snapshot. Computing it reads ~59 per-worker liveness files and was 58% of a status request after the storage walk was cached. The default is sized against the watchdog threshold it feeds (`stuck_pending_max_age_s < 60`), not by feel. `0` disables. | `5` (seconds). |
| `TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS` | Concurrent provider SUBPROCESSES — the binding capacity constraint on real turns. **Size it against the CGROUP limit, not host memory**: provider and engine-MCP children live inside the daemon's cgroup, so host MemAvailable is the wrong ceiling (this was the third sizing attempt and the third wrong baseline). Measured marginal ~31 MB per process at the `--version` FLOOR; a real turn adds prompt, streaming state and an MCP child by an unmeasured factor, carried at 5x. Move it on `refused` climbing while `peak_concurrent` sits at the limit in `get_status.provider_admission`, not on arithmetic. | `15` (4 vCPU / 8 GB box). |
| `TINYASSETS_PROVIDER_NESTED_RESERVE` | Slots outer (user-facing) turns may NOT take, held for nested `run_graph` children so a served turn cannot starve the work it spawned. Scales with the limit — one slot shared by every nested call at 15 outer turns is a queue, not a reserve. Clamped so outer turns always keep at least one. | `3`. |
| `TINYASSETS_PROVIDER_ADMISSION_WAIT_S` | How long a turn waits for a provider slot before being refused with an honest, retryable message (Hard Rule 8). | `20` (seconds). |
| `TINYASSETS_STORAGE_SNAPSHOT_TTL_S` | How long `inspect_storage_utilization` may reuse a snapshot. The walk recursively sums every subsystem directory (~3,300 `stat` syscalls, 24-49 ms measured on the live box 2026-08-28) and its cost is O(files on disk), so it must not run per request. `0` disables the memo for an operator who needs the number right now. | `60` (seconds). |
| `TINYASSETS_STORAGE_BACKEND` | Catalog storage backend selection. Values: empty (default), `"git"`, `"sqlite"`. | Empty (auto-select per backend factory). |
| `TINYASSETS_RUN_MAX_CONCURRENT` | Integer cap on concurrent in-flight branch runs. | Unset = unlimited. |
| `TINYASSETS_IDLE_CYCLE_SINGLE_FLIGHT` | Dedupe the no-claim idle heartbeat cycle across fleet workers (`tinyassets/idle_cycle.py`): the winner holds a run lock for the cycle's lifetime (long cycles exclude others; released on process death), and a worker skips when a DIFFERENT worker's stamp is fresh; own stamps never block. Falsy = `"0"`/`"false"`/`"off"`/`"no"`. | `on`. |
| `TINYASSETS_IDLE_CYCLE_FOREIGN_FRESH_S` | Freshness window (seconds) for the idle-cycle stamp; finite positive numbers only (anything else falls back to default). Keep below the supervisor idle respawn period (~322s at backoff ceiling) and above worker phase offset; also the max heartbeat gap after a stamp-holder death. | `240`. |

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
| `TINYASSETS_OUTBOUND_PROXY_STARTUP_TIMEOUT_S` | Seconds the outbound credential broker waits for its spawned child's ready handshake before failing the call. The wait occupies a run-executor thread and that pool has only four workers, so a few hung startups stall all top-level graph progress for this long — keep it tight. A startup failure now names its cause, so read that before raising this. | `15` (~100x the measured ~0.13s child import). Capped at `120`; an unparseable, non-finite, or ≤0 value is announced on stderr and falls back to the default rather than failing egress. |

**Canonical resolver:** `workflow.storage.data_dir()` is the single
source of truth for `TINYASSETS_DATA_DIR` resolution. Do not re-implement
the precedence logic elsewhere — call the resolver.

**Container deploys:** set `TINYASSETS_DATA_DIR=/data` + bind-mount the
host path to `/data`. See `deploy/README.md` for the full pattern.

## Billing (Stripe)

All three live on the daemon in `/etc/tinyassets/env` (root:tinyassets, 0640). None is
baked into `deploy/compose.yml`: compose `environment` values ship in this repo, and
these are secrets.

| Variable | What it is |
|---|---|
| `STRIPE_SECRET_KEY` | `sk_live_…` in production, `sk_test_…` in sandbox. Authorizes real charges. |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…`, **per-endpoint and per-mode**. Going live means a new endpoint and therefore a new secret. |
| `TINYASSETS_BILLING_ENTITLEMENT_KEY` | Signs the HMAC claim in each subscription's Stripe metadata. **Ours, not Stripe's.** |

Billing is inert unless the first two are set (`billing_enabled()`), so a deployment
without them serves the app with the Upgrade control disabled rather than failing.

**Why the entitlement key is separate from the webhook secret.** The claim proves a
subscription is one *we* created for a given universe. Signing it with Stripe's webhook
secret tied that authority to a key Stripe tells you to rotate — and that you must
rotate the moment it leaks. Rotating it would invalidate the claim on every subscription
already sold, and those subscriptions could then never move a tier again: a later
cancellation would fail authorization and be ignored, leaving someone entitled who had
cancelled. Claims are versioned; `v1` (webhook secret) is still verified so existing
subscriptions keep working, `v2` uses this key, and nothing new is issued as `v1` once
it is set.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Rotating `TINYASSETS_BILLING_ENTITLEMENT_KEY` invalidates every v2 subscription.** Only
rotate it with a re-signing migration, or by adding a `v3` that verifies `v2` alongside.

**Mode safety.** The webhook refuses any event whose `livemode` disagrees with the
configured key, so a leftover test secret on a live deployment fails loudly instead of
letting free test-mode subscriptions grant the paid tier.

Readiness: `python scripts/stripe_go_live.py --check`.

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
