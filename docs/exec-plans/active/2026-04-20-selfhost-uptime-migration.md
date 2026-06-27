# Self-Host Uptime Migration — Near-Term Execution Plan

**Date:** 2026-04-20 (post P0 outage + host directive)
**Author:** navigator
**Status:** Active exec plan. Draws mechanics from `docs/specs/2026-04-19-plan-b-selfhost-migration-playbook.md`; narrows scope to "make uptime independent of the host's computer in the near term."
**Lens:** 3-layer chain. Today the System layer is physically bound to one Windows machine in the host's home — its cloudflared tunnel, its MCP process, its LanceDB singleton, its disk-backed DBs. Host directive today: **"full uptime no longer dependent of this computer."** That is the scope.
**Navigator-owned decisions:** provider + secrets posture + Postgres + host-machine-role + first-ship data volume. Host directive: *"cant the navigator think long term and pick the cleanest design that always works for us having a website."* Criterion applied throughout: **always-works over ship-speed, cost-optimization, or elegance.** Navigator decides; lead ratifies; dispatch proceeds without host round-trip.

---

## 0. Canonical URL (2026-04-20 post host Option-A pick)

Two URLs, two roles. Named here once so every subsequent row + the docs-sweep follow-up land on the same shape.

| URL | Role | Notes |
|---|---|---|
| `https://tinyassets.io/mcp` | **User-facing canonical. Single public entry point.** The URL that ships in Claude.ai connector configs, README, onboarding docs, and any tier-1 / tier-2 UX copy. Also the URL probed by all canaries. | Served via a Cloudflare Worker at the apex that routes `/mcp*` → tunnel origin → daemon. Worker is an independent Cloudflare edge layer. |
| `https://mcp.tinyassets.io/mcp` | **Access-gated internal tunnel origin. Not user-facing.** | cloudflared tunnel hostname. Protected by Cloudflare Access (service-token, host directive 2026-04-20): direct requests without CF service-token headers return 401/403. Only the Worker injects those headers. Do not document or share in user-facing contexts; do not add to canary configs. |
| ~~`https://api.tinyassets.io/mcp`~~ | **NOT live. Do not resurrect.** | Referenced in older docs as the intended-canonical but never shipped (NXDOMAIN in the 2026-04-19 P0 event). User-facing setup/runbook references are stale; audit-history notes may retain `api.tinyassets.io` when clearly labeled historical. |

**Interaction rule.** If a future tunnel reconfig (Cloudflare dash work) touches `tinyassets.io/mcp`, Hard Rule 11 fires — run `scripts/uptime_canary.py --once` post-change and confirm green before marking the change complete.

---

## 1. Scope — what "near-term" means precisely

**IN SCOPE:** the minimum surface that, when moved off the host machine, means the host's computer can be powered off for 48 hours without any surface going red.

That surface is exactly two things:
1. **The MCP daemon process** (`tinyassets/daemon_server.py` + `tinyassets/universe_server.py`, served via `fastmcp` on streamable-http transport).
2. **The cloudflared tunnel origin** that terminates `mcp.tinyassets.io/mcp` + `tinyassets.io/` and forwards to (1).

Every other uptime surface is already independent of the host machine:

| Surface | Status today | Migration need |
|---|---|---|
| Tier-3 OSS `git clone` | GitHub-hosted | None |
| Tier-3 CI / nightly smoke GHA | GitHub-hosted | None |
| Web landing (future) | Cloudflare Pages / GoDaddy W+M | None today; plan-b migrates to Hetzner later |
| **MCP daemon (tier-1 + tier-2 chatbot path)** | **Host machine** | **THIS PLAN** |
| **cloudflared tunnel origin** | **Host machine** | **THIS PLAN** |
| Uptime canary (Layer 1) | Windows Task Scheduler on host | Probes from OUTSIDE — should continue from host for now; later add GHA independent vantage point |
| Uptime canary (Layer 2) | Shared CDP browser on host | Remains host-bound by necessity (user-sim needs browser); NOT in scope |
| Future Supabase/Postgres | Supabase managed | None |
| Future paid-market | Supabase-backed | None |

**OUT OF SCOPE (deferred to full plan-b):**
- Moving the web app, GitHub Action targets, catalog mirror, convergence tools, or any primary persistence layer. Today we have none of these; the plan-b playbook covers them when they exist.
- Moving Supabase-hosted state (doesn't exist yet; being built under Track A).
- DR / multi-region / high-availability beyond "one remote host is up."

The goal is tight: **one remote Linux box runs the MCP daemon + the cloudflared origin. Host machine becomes replaceable.**

---

## 2. Provider pick: **DigitalOcean Basic Droplet** (Debian 12, Docker Compose) — pivoted from Hetzner 2026-04-20

**Single pick, no option-buffet.** Host directive: *"pick the cleanest design that always works for us having a website."* Criterion = always-works (operational simplicity + proven uptime + low-oops-factor, scaled through the full-platform target without a second migration).

**Pivot 2026-04-20:** Hetzner was the original pick (reasoning preserved below). Mid-cutover, host hit a broken Hetzner US individual-signup flow — the signup form wouldn't accept the verification path cleanly, blocking account provision. Rather than burn the cutover window, pivoted to **DigitalOcean Basic Droplet**: GitHub-OAuth-based signup (1-click for host who already had GitHub auth'd), same Debian 12 image target, same Docker Compose stack, same `hetzner-bootstrap.sh` script runs unchanged (file name kept for git history; script is provider-neutral). Monthly cost ~$6 Basic Droplet is comparable to CX22 €5.83 at this scale. Cutover completed on DO.

**Fallback-if-primary-goes-bad:** **Hetzner Cloud** (CX22, Debian 12). The always-works reasoning below ranks Hetzner as the superior long-term choice; pivot was friction-driven, not preference-driven. If Hetzner's US individual-signup form becomes fixable (retry in ~6 months) or the host re-attempts via EU/business-signup path, migrating back is: provision CX22 → `hetzner-bootstrap.sh` runs unchanged → `rsync` data from DO Droplet → DNS flip via `emergency-dns.yml`. Estimated ~2 hours.

**Tertiary fallback:** Fly.io. Engaged only if both DO AND Hetzner degrade.

### Why DigitalOcean works fine near-term

DO Basic Droplet is not "as good as Hetzner at always-works" — it's "good enough that the cutover-window ship cost of switching was worth it." Specifically:
- **Track record is ≥99.99% SLA documented.** DO has had fewer multi-region control-plane outages in 2024-2026 than Fly.io; comparable to Hetzner at this tier.
- **Zero managed-runtime fate-sharing** — same as Hetzner: running Droplet keeps serving if DO control plane hiccups. Docker Compose + systemd on a Linux VM.
- **Same portability story** — `Dockerfile` + `docker-compose.yml` + `hetzner-bootstrap.sh` lifts to any other Debian 12 Linux VM (Hetzner, Linode, Vultr, GoDaddy VPS, all work). Handoff shape unchanged.
- **Supabase + DO + Cloudflare-front** maps cleanly to the same architecture target as Supabase + Hetzner + Cloudflare-front.

### Why Hetzner remains the documented long-term target (original reasoning, preserved)

Reasoning below is the 5-bullet always-works case for Hetzner. It still applies — that's why Hetzner is the named fallback, not a dismissed option. The only reason we're not on Hetzner today is the signup-form bug, which is resolvable.

- **Proven uptime over the relevant timescale.** Hetzner Cloud has operated since 2018 with a documented ≥99.9% SLA. Fly.io has had multiple multi-hour all-region control-plane outages in 2024-2025 affecting `flyctl`, machine scheduling, and running apps simultaneously. For the forever rule ("user never sees an outage"), a boring Linux VM with a long clean uptime record beats an elegant orchestrator that goes hard-down a few times per year.
- **Zero managed-runtime fate-sharing.** The daemon runs on a rented Linux box. If Hetzner's *control plane* has a bad day, the *running VM keeps serving* with its tunnel attached — only NEW provisioning breaks. Fly/Render/Railway all have documented modes where control-plane outage takes running apps down.
- **Same box scales from MVP to full-platform target.** CX22 (€4/mo, 2 vCPU, 4 GB) handles near-term MVP; resize in-place to CX42 (€20/mo, 8 vCPU, 16 GB) covers thousands-concurrent + paid-market (`project_full_platform_target.md`). One-command upgrade, no migration event.
- **Zero lock-in; clean succession handoff.** Deployment is `Dockerfile` + `docker-compose.yml` + a shell script. Any successor admin (`project_host_independent_succession.md`) can lift the whole stack to a different Linux provider with `rsync` + a DNS flip.
- **Clean alignment with the rest of the architecture.** Supabase + Hetzner + Cloudflare-front is exactly the target shape in plan-b playbook §2. DigitalOcean slots into the same architecture equally cleanly — the migration path Hetzner → DO → Hetzner → anywhere-else is all the same two-command lift.

### Why not the alternatives — one sentence each

- **Fly.io:** ship-speed win goes to dev experience, not to the user's outage count. Track record penalty weighed more than the ~4h faster first-deploy.
- **GoDaddy VPS:** existing-vendor memory is real, but GoDaddy VPS is a tertiary product with no track record among shops running Docker services in production — "existing vendor" does not override "proven for the exact shape we need."
- **AWS Lightsail / EC2:** IAM surface adds ops complexity with no offsetting uptime win at our scale.
- **Cloudflare Workers:** would require rewriting SqliteSaver + LanceDB + local fs access (~4-6 dev-days refactor) before a single probe passes; rewrite cost exceeds the whole migration budget. Queue as a future architectural target if we ever hit Workers-scale traffic; not near-term.
- **Render / Railway:** same managed-runtime fate-sharing as Fly; adds a vendor without adding robustness.

---

## 3. Internal decisions that used to be host asks — pre-decided

Per host directive *"think long term and pick the cleanest design."* Navigator decides; no host round-trip. All four answers below are HIGH confidence unless noted; lead ratifies silently.

- **Secrets storage for prod:** env vars injected via Hetzner cloud-init + systemd `EnvironmentFile` pointing at `/etc/tinyassets/secrets.env` with `chmod 600` root-only read. One secret today (`CLOUDFLARE_TUNNEL_TOKEN`); vault integration is overkill at this count. Revisit when Supabase JWT + wallet keys land (post-Track A, ~2-3 secrets total). Rationale: file-on-box + ownership-restricted is standard Linux posture, no third-party dependency, easy to rotate by re-writing the file, survives all the secret-vault migration scenarios in plan-b.
- **Postgres:** Supabase managed. Already ratified as Q1 per v3 host-Q digest. No near-term change.
- **Host machine role post-cutover:** dev seat only. Host keeps the full local dev loop; prod is on Hetzner. Warm-fallback adds operational complexity (sync issues, split-brain risk) without measurable robustness win. Pure-off wastes a capable local dev environment. Standard one-person-project pattern.
- **Data on first box:** box starts empty. Universes are tier-2 per-host concept (`project_user_tiers.md`); the public MCP endpoint exists to serve catalog + paid-market + connector handshake, not per-user universe state. MEDIUM confidence — flagging in case this contradicts an unstated host model — but going with it. Any universe-migration scope that surfaces later is additive work, not a foundation change.

---

## 4. Shippable-now work (no host input needed) — Work-table rows

Five rows. All dispatchable immediately against the current main. Zero provider-specific code in rows 1-3; provider-specific in rows 4-5.

### Row A: Containerize the daemon

**Files:** `Dockerfile` (new at repo root), `.dockerignore` (new), `docs/ops/docker-notes.md` (new).

**Scope:**
- Multi-stage Dockerfile: Python 3.11 base, `pip install -e .`, install cloudflared binary, expose port 8001, entrypoint = `python -m tinyassets.daemon_server` or equivalent.
- `.dockerignore` excludes `.venv/`, `__pycache__/`, `output/`, `*.db`, `node_modules/`, `.git/`, `packaging/` (the Windows tray plugin doesn't ship in the server image).
- Short ops-notes doc explaining build + local test.

**Acceptance:** `docker build -t tinyassets-daemon . && docker run -p 8001:8001 tinyassets-daemon` serves `/mcp` locally; `curl -X POST localhost:8001/mcp` gets a valid MCP initialize response.

**Effort:** ~0.5 dev-day. First draft; iterations expected.

**Blocks:** Row D (deploy) depends on this.

### Row B: Extract hardcoded host-machine paths

**Files:** audit + refactor any `C:\Users\...` / `C:\\Users\\...` / `Path(os.environ["USERPROFILE"])` / similar absolute-path assumptions in `tinyassets/` server code. Suspect surfaces per grep: `tinyassets/daemon_server.py`, `tinyassets/universe_server.py`, `tinyassets/storage/__init__.py`, anywhere LanceDB or SqliteSaver construct paths.

**Scope:**
- Audit: grep for literal `C:\` and `USERPROFILE` across `tinyassets/` (exclude tests + packaging + scripts). Expect: LanceDB default path, universe_base path, any sqlite path.
- Refactor to env-driven: `TINYASSETS_DATA_DIR` (default `~/.workflow` on Unix, `%APPDATA%\TinyAssets` on Windows). All on-disk state roots through this variable.
- Docstring: document the env var in `tinyassets/daemon_server.py` module docstring + `AGENTS.md` if warranted.

**Acceptance:** `TINYASSETS_DATA_DIR=/tmp/test_data python -m tinyassets.daemon_server` starts cleanly on a Linux host with no `C:\` paths touched in the success path. Existing Windows-host behavior unchanged when the env var is unset (defaults resolve to the current Windows path).

**Effort:** ~0.5-1 dev-day. Surface area unknown until audit; estimate widens if LanceDB / FAISS / etc. deeply encode Windows paths.

**Blocks:** Row D (deploy).

### Row C: Tunnel config shape — provider-agnostic

**Files:** `deploy/cloudflared.yml` (new template), `deploy/cloudflared-README.md` (new), `scripts/run-tunnel.sh` (new).

**Scope:**
- Template cloudflared config parameterized by `$TUNNEL_TOKEN` + `$ORIGIN_PORT`. No hardcoded tunnel names, no hardcoded hostnames.
- Runbook: how to create a new tunnel + bind it to `mcp.tinyassets.io` (leans on the godaddy-ops skill's Cloudflare gotchas).
- Shell script that runs `cloudflared tunnel --config deploy/cloudflared.yml run` — suitable for systemd/Docker entrypoint.

**Acceptance:** A dev (or future provider) can clone the repo, set `TUNNEL_TOKEN` + `ORIGIN_PORT` env, run `scripts/run-tunnel.sh`, and a tunnel lives on the public URL. No Windows-specific steps.

**Effort:** ~0.25-0.5 dev-day.

**Blocks:** Row D (deploy).

### Row D: Deploy to Hetzner

**Files:** `deploy/compose.yml` (new), `deploy/provision.sh` (new), `docs/ops/hetzner-deploy.md` (new).

**Scope:**
- Provision a Hetzner Cloud CX22 (Debian 12, Falkenstein or Nuremberg region — both have long clean track records; first-draft picks whichever has lower latency to tinyassets.io's Cloudflare edge).
- Run `scripts/provision.sh` (new): installs Docker + Compose, creates `/etc/tinyassets/secrets.env` with `chmod 600`, fetches the daemon image + cloudflared image, sets up systemd unit files for both.
- `docker compose up -d` brings up the daemon + tunnel sidecar containers; healthcheck confirms `localhost:8001/mcp` responds.
- DNS: `mcp.tinyassets.io` CNAME points at the Hetzner box's tunnel (NOT the host's tunnel). Host machine's tunnel removed from the Cloudflare Zero-Trust config to prevent dual-origin routing.
- Secrets: `CLOUDFLARE_TUNNEL_TOKEN` written once to `/etc/tinyassets/secrets.env`; systemd `EnvironmentFile` pulls it on service start.

**Relationship to Row E (Worker):** Row D lands the direct-tunnel-origin side (`mcp.tinyassets.io/mcp`). The user-facing canonical `tinyassets.io/mcp` is fronted by an independent Cloudflare Worker (Row E) that forwards to this origin. Worker + tunnel origin are independent layers — either can be updated without the other. The Worker ships BEFORE the Hetzner cutover (it routes to the current tunnel origin regardless of whether that origin is the host machine or the Hetzner box); Hetzner cutover just changes which origin the Worker reaches.

**Acceptance:** Host machine powered off for 1 hour -> user-facing `tinyassets.io/mcp` green via Layer-1 canary and public direct access to `mcp.tinyassets.io/mcp` still blocked by Cloudflare Access. That's the pass gate.

**Effort:** ~1-1.5 dev-days. Hetzner provisioning + Docker Compose + Cloudflare tunnel binding + DNS flip + post-flip Hard Rule 11 probe on canonical URL plus direct-origin gate check.

**Blocks:** Row F (trial).

### Row E: Cloudflare Worker — restore `tinyassets.io/mcp` as canonical

**Files:** `deploy/cloudflare-worker/worker.js` (new), `deploy/cloudflare-worker/wrangler.toml` (new), `deploy/cloudflare-worker/README.md` (new).

**Scope:**
- Cloudflare Worker attached to `tinyassets.io/*` zone routes, matching route pattern `tinyassets.io/mcp*`.
- Worker forwards matching requests to `https://mcp.tinyassets.io/mcp...` preserving method, headers, streaming body, and trailing path segments (so that `/mcp/anything/nested` routes cleanly if FastMCP ever adds sub-routes).
- Non-`/mcp*` requests at apex pass through unchanged (landing HTML served by the daemon's own `@mcp.custom_route("/")` or any future GoDaddy/Pages route — Worker doesn't intercept them).
- Streaming HTTP transport support: the Worker must proxy `Content-Type: text/event-stream` and chunked-transfer bodies correctly. FastMCP's streamable-http transport depends on long-lived streaming responses; naïve `fetch(...).then(r => new Response(r))` works in Workers for this.
- `wrangler.toml` declares the route + environment variables + Worker name (recommend `tinyassets-mcp-router`).
- README: one-command deploy via `wrangler deploy`; secret setup (none needed for MVP — tunnel origin is public; revisit when Supabase JWT lands); rollback procedure (remove route binding = apex serves whatever was behind it before).

**Independence from Row D:** Row E ships NOW (post-Row-A, no dependency on Row D). While the host machine is still serving `mcp.tinyassets.io`, the Worker restores `tinyassets.io/mcp` as canonical immediately. When Row D cuts over to Hetzner, the Worker's target (`mcp.tinyassets.io/mcp`) points at the new origin automatically — no Worker redeploy needed. This sequencing gets the user-facing canonical URL back online FAST without gating on the full self-host migration.

**Acceptance:**
1. `curl -X POST https://tinyassets.io/mcp -H 'content-type: application/json' -d '<initialize payload>'` returns a valid MCP initialize response.
2. Response equivalence through the Worker to the tunnel origin — same JSON-RPC result shape, same tools available on `tools/list`; the public direct origin remains Access-gated.
3. Streaming transport works end-to-end: an MCP session over Claude.ai using `tinyassets.io/mcp` connector URL completes a tool call (e.g., `get_status`) without disconnection.
4. Layer-1 canary probes `tinyassets.io/mcp` green for 10 min; direct-origin gate check stays 401/403.
5. Hard Rule 11 satisfied post-deploy.

**Effort:** ~0.5 dev-day. Worker is small (≤50 LOC), wrangler setup is standard, testing is single-run local + live smoke.

**Blocks:** nothing hard. Enables: Row F (trial can now exercise the user-facing canonical), Row G (docs sweep) once Worker stable.

### Row F: Migration smoke script + 48-hour-offline acceptance

**Files:** `scripts/selfhost_smoke.py` (new), `tests/smoke/test_selfhost_parity.py` (new under tier-3 smoke directory).

**Scope:**
- Current default `selfhost_smoke.py` hits `tinyassets.io/mcp` (user-facing canonical via Worker) for MCP behavior and confirms public direct access to `mcp.tinyassets.io/mcp` is blocked by Cloudflare Access (401/403).
- Use `selfhost_smoke.py --internal-parity` only when `--tunnel` points at an internal/service-token path that is expected to speak MCP. Parity assertion: both URLs return equivalent tool sets + equivalent `get_status` structure.
- Integration test should cover both modes: public direct-origin gate is blocked; internal/service-token parity has same tool set, same public-tool-output shape, same success behavior.
- Runs in the nightly tier-3 GHA (once that's live) against both URLs.

**Acceptance (48-hour trial):**
1. After Row D + Row E land, host powers down their local daemon.
2. Layer-1 canary runs every 2 min for 48 hours against `tinyassets.io/mcp`; direct-origin checks expect `mcp.tinyassets.io/mcp` to stay Access-gated.
3. Zero Layer-1 reds in the trailing 48 hours; zero direct-origin gate regressions.
4. `selfhost_smoke.py` green at hour 1, hour 24, hour 47.
5. Hard Rule 11 satisfied: no post-change DNS, Worker, or provider reconfig blips went undetected.

**Effort:** ~0.25 dev-day for the script + test. Acceptance is 48h wall time + canary monitoring, ~0 dev-hours active.

**Blocks:** Row G (sweep fires on clean trial).

### Row G (follow-up, do NOT execute now): Canonical-URL docs sweep

**Files:** grep + update. Expected surfaces include `docs/specs/*`, `docs/audits/*`, `SUCCESSION.md`, `.claude/skills/ui-test/*`, `docs/ops/*`, any setup/runbook `.md` referencing `api.tinyassets.io/mcp` or referencing `mcp.tinyassets.io/mcp` as user-facing (vs debug-only). Preserve audit-history mentions that explicitly identify `api.` as historical / never-live.

**Scope:**
- Replace every user-facing reference to `mcp.tinyassets.io/mcp` OR `api.tinyassets.io/mcp` with `tinyassets.io/mcp` (canonical per §0). EXCEPTIONS: `mcp.tinyassets.io/mcp` stays in canary/debug/tunnel docs; `api.tinyassets.io` may remain only in audit-history notes that label it historical / never-live.
- Add a one-line reminder near each canonical reference about the three-URL shape from §0 if the surface is contributor-facing (specs + skills); user-facing surfaces (README, onboarding) get the canonical only.
- **No flip-flops after this sweep.** The URL architecture is locked: apex canonical via Worker, subdomain debug-only via tunnel. Future changes require explicit exec-plan amendment.

**Trigger:** fires only after Row F acceptance closes (48h trial green). Do not run preemptively — the sweep on not-yet-stable routing creates docs that lie if the Worker has to be rolled back.

**Effort:** ~0.5-1 dev-day depending on surface size. Mechanical grep + replace + review.

**Blocks:** nothing. Sweep is the final closer for the post-P0 URL-architecture arc.

---

## 4b. Additional uptime gaps (Rows H-N) — post-host-list triage + expansion

Lead surfaced 10 gaps 2026-04-20 after host asked *"what else is needed for 24/7 uptime without my computer?"* Navigator triaged, bundled related items, kept the row count tight.

**Triage outcome — 10 gaps → 7 rows + 1 already-covered + 1 new addition:**

| Gap | Disposition | Row |
|---|---|---|
| 1. Canary Layer 1 on host Task Scheduler | Standalone row — critical for acceptance gate. | **H** |
| 2. Alarms to disk only, no out-of-band sink | Bundles with Gap 1 (same commit, same file set — the alarm sink is how the cloud canary gets noticed). | **H** |
| 3. Docker image registry (GHCR) | Standalone row — blocks Row D reliably. | **I** |
| 4. State backup (LanceDB + SqliteSaver + data to off-box storage) | Standalone row — single-disk failure is currently unmitigated. | **J** |
| 5. Log aggregation (stdout → cloud sink) | Standalone row — if box dies we need the evidence. | **K** |
| 6. Daemon auto-restart + watchdog | Standalone row — systemd Restart=always + MCP-initialize watchdog. | **L** |
| 7. Deploy pipeline (merge → build → SSH deploy) | Standalone row — post-merge ship without host action. | **M** |
| 8. Bill-payment autonomy | Bundles with 9 + 10 under "host-independence admin." | **N** |
| 9. DNS changes locked to host login | Bundles with 8 + 10. | **N** |
| 10. Secrets rotation calendar + alerts | Bundles with 8 + 9. | **N** |
| (already covered) Row E Worker fallback-on-outage | Gap 9's "emergency DNS flip" is materially covered by the Worker's independence from tunnel origin — apex route change at the Worker level is a one-command `wrangler deploy` that uses a checked-in-repo API token, not a dashboard login. Row N narrows Gap 9 to "non-Worker DNS surfaces" (A/CNAME records under Cloudflare zone). | — |
| **11th gap navigator sees — acceptance gate IS the canary** | The whole 48h acceptance in §6 depends on the Layer-1 canary existing. Row H explicitly makes that dependency a hard block in the sequencing. Not a new row, but a clarification. | — |

**Per-row summaries below.** All Rows H-N dispatchable in parallel with existing A-G work unless explicitly noted.

### Row H: Cloud canary + out-of-band alarm sink (gaps 1 + 2)

**Files:**
- `.github/workflows/uptime-canary.yml` (new) — GHA cron scheduling.
- `scripts/uptime_canary.py` (already sketched in `docs/design-notes/2026-04-19-uptime-canary-layered.md` — ship it, don't re-design).
- `scripts/uptime_alarm.py` (new) — reads last N log lines, applies escalation table, fires alarms.
- `.github/workflows/uptime-canary.yml` posts alarms via a Discord webhook OR opens a GitHub issue via `gh issue create` using the built-in `GITHUB_TOKEN`.

**Scope:**
- GHA cron at every 5 minutes (GHA's floor is `*/5` practically — 2-min cadence from host Task Scheduler remains best-effort + supplementary, not primary). Probes `tinyassets.io/mcp` for MCP health and the `mcp.tinyassets.io/mcp` public direct-origin gate for 401/403.
- Alarm sink: **GitHub Issue on 2 consecutive reds.** Pre-decided per always-works criterion — Discord webhook requires a webhook secret + a Discord server we depend on; GitHub Issue uses the repo's existing infrastructure with zero new dependencies. Issue body includes last N probe lines + suspected cause from exit code. Issue is auto-closed on 3 consecutive greens (same workflow).
- Host Task Scheduler canary continues as supplementary when host is online (2-min cadence catches faster); GHA is the uptime-critical path.

**Effort:** ~0.75 dev-day. Canary script exists in design; GHA yml + alarm script + issue-auto-open/close + tests.

**Cost:** $0/mo. GHA free tier, GitHub Issues free.

**Sequence:** Dispatchable NOW. Independent of all existing rows.

**Acceptance:** With host box offline, canary probes every 5 min from GHA; a forced outage (temporarily stop daemon) produces a GitHub issue within ~10 min; bringing daemon back closes the issue within ~15 min.

**This row is a hard block on §6 acceptance gate** — the 48h-offline trial cannot be validated if the canary itself lives on the host.

### Row I: Docker image registry (gap 3)

**Files:**
- `.github/workflows/build-image.yml` (new) — build + push on every main-branch push.
- `Dockerfile` (Row A artifact) tagged for GHCR.
- `deploy/compose.yml` pulls from `ghcr.io/<owner>/tinyassets-daemon:<tag>`.

**Scope:**
- GitHub Actions workflow on push to main: `docker buildx build` + push to GHCR. Tags: `latest` + git SHA short.
- GHCR visibility: public read for OSS posture (matches `project_license_fully_open_commons.md`); no private-repo premium needed.
- `deploy/compose.yml` references `:latest` for simplicity at MVP; upgrade to SHA-pinning when first deploy regression happens (foundation-end-state discipline says no phased complexity, so this is intentionally simple).

**Effort:** ~0.25 dev-day. GitHub provides GHCR + the Action template.

**Cost:** $0/mo. GHCR free for public images.

**Sequence:** Dispatchable NOW. Collides only with whoever is editing `Dockerfile` (Row A already landed — no collision).

**Acceptance:** `docker pull ghcr.io/<owner>/tinyassets-daemon:latest` from a fresh machine succeeds + `docker run` serves `/mcp` green. Row D's deploy can pull from registry instead of local build.

**Without this row, Row D has no deploy source.** The plan previously hand-waved image source; Row I names it.

### Row J: State backup (gap 4)

**Files:**
- `deploy/backup.sh` (new) — nightly snapshot.
- `deploy/compose.yml` adds a backup sidecar OR systemd timer on the Hetzner box.
- `docs/ops/backup-restore.md` (new) — runbook.

**Scope:**
- Hetzner Storage Box (€1/mo, 100GB, S3-compatible via `rclone`) — the plan-b playbook already references this shape.
- `backup.sh` runs nightly at 03:00 UTC (low-traffic): rsync'd snapshot of `/var/lib/tinyassets/data/` (LanceDB + SqliteSaver + SQLite DBs + any disk-backed state) to Storage Box with 7-day rotation + 4-week weekly retention + 12-month monthly retention.
- Supabase-hosted data (Postgres rows) NOT in this backup — Supabase Pro handles its own daily PITR.
- Restore runbook: one-command restore from a named snapshot date.

**Effort:** ~0.5 dev-day. rsync + systemd timer + restore script + a restore-test.

**Cost:** €1/mo (~$1.10).

**Sequence:** Depends on Row D (box must exist). Parallel-safe with Row F / G once D lands.

**Acceptance:**
- Nightly backup runs for 7 consecutive days without failure (check via alarm sink — Row H fires an alarm if backup job fails).
- Restore-test: spin up a second CX22, restore from last night's snapshot, confirm daemon starts + `get_status` green + recent state visible.

### Row K: Log aggregation (gap 5)

**Files:**
- `deploy/compose.yml` adds a `vector` or `fluent-bit` sidecar (whichever ships with simplest config).
- `docs/ops/logs.md` (new) — runbook to grep aggregated logs.

**Scope:**
- Daemon writes to stdout (already does). Docker captures → journald. Sidecar ships journald → cloud sink.
- **Sink choice (navigator-decided, always-works criterion):** Better Stack (formerly Logtail) free tier — 3 GB/mo retention, 3-day history, zero-credit-card free signup. Matches Papertrail's shape; Papertrail is now SolarWinds and harder to get a free account on in 2026.
- Alternative if Better Stack's free tier changes: ship to an S3-compatible bucket (Hetzner Storage Box already available from Row J) with date-partitioned files. Less queryable but zero external dependency. Acceptable fallback.
- No log-based alerting at first-draft — Row H's canary handles outage alerts; log aggregation is for forensic reconstruction.

**Effort:** ~0.5 dev-day.

**Cost:** $0/mo (Better Stack free tier) or €0 marginal (Storage Box if fallback chosen).

**Sequence:** Depends on Row D (box must exist). Parallel-safe with Row F.

**Acceptance:** Induce an error in the daemon; verify the error line appears in Better Stack (or fallback bucket) within 30 s. During an outage test (daemon killed), the final 60 s of logs are queryable after the box recovers.

### Row L: Daemon auto-restart + watchdog (gap 6)

**Files:**
- `deploy/systemd/tinyassets-daemon.service` (new OR extend existing).
- `scripts/watchdog.py` (new) — external MCP-initialize probe every 30 s on `localhost:8001/mcp`; if 3 consecutive failures, `systemctl restart tinyassets-daemon`.
- `deploy/systemd/tinyassets-watchdog.service` + `.timer`.

**Scope:**
- systemd `Restart=always` + `RestartSec=5` on the daemon unit. Covers plain crashes.
- Watchdog covers the scarier failure modes: OOM-kill (systemd sees the kill + restarts) + stale-bytecode class (#11 fixed the acute case; watchdog catches any future regression) + hung-but-not-crashed (socket accepting, initialize hanging — systemd won't catch this, watchdog will).
- Restart count ceiling: if watchdog restarts the daemon >5 times in 10 min, stop + fire an alarm via Row H instead of flapping. Prevents restart-loop-burning-CPU.

**Effort:** ~0.5 dev-day.

**Cost:** $0/mo.

**Sequence:** Depends on Row D. Parallel-safe with Row F.

**Acceptance:**
- `kill -9 $(pgrep -f tinyassets-daemon)` — daemon back and serving within 10 s.
- Force-hang (simulate infinite loop in a test build) — watchdog restarts within 90 s.
- Induce flap (crash the daemon in a restart loop) — after 5 restarts in 10 min, watchdog stops + Row H fires an alarm; box does NOT go into a CPU-burning loop.

### Row M: Deploy pipeline — merge to production (gap 7)

**Files:**
- `.github/workflows/deploy-prod.yml` (new) — triggered on main-branch push after Row I's image build succeeds.
- Required secrets in repo settings: `HETZNER_SSH_HOST`, `HETZNER_SSH_USER`, `HETZNER_SSH_KEY` (private key for a deploy-only user on the box).

**Scope:**
- On main-branch push (after Row I's image build green), GHA SSHs into the Hetzner box as a deploy-only user (`chmod`-restricted, `sudo` allowed for only `docker compose pull && docker compose up -d tinyassets-daemon`).
- Deploy step: `docker compose pull && docker compose up -d tinyassets-daemon` — rolling restart; systemd's `Restart=always` + Row L's watchdog + the daemon's own graceful-shutdown-of-pending-MCP-sessions keep continuity.
- Post-deploy: GHA runs a remote `scripts/uptime_canary.py --once` against `tinyassets.io/mcp` AND `mcp.tinyassets.io/mcp`. Green = ship confirmed; red = **automatic rollback** via `docker compose pull --tag=<previous-SHA>` + retry canary.
- Manual override: `workflow_dispatch` trigger with a `--skip-canary` parameter (NOT default) for emergency rollback scenarios.

**Effort:** ~0.75 dev-day. SSH key management is the fiddly part.

**Cost:** $0/mo.

**Sequence:** Depends on Rows D + I. Parallel-safe with Row F.

**Acceptance:**
- Merge a trivial PR (e.g., README typo fix); image builds; deploy runs; canary green within 5 min of merge.
- Merge a regression (intentional test: a PR that breaks `get_status`); canary goes red post-deploy; rollback triggers; next canary green within 10 min. Row H fires an alarm during the red window.

### Row N: Host-independence admin — bills + DNS + secrets (gaps 8 + 9 + 10)

**Files:**
- `docs/ops/host-independence-runbook.md` (new) — a single runbook covering all three concerns.
- `scripts/emergency_dns_flip.py` (new) — Cloudflare API script that flips `tinyassets.io/mcp` Worker route OR `mcp.tinyassets.io` CNAME OR apex routing to a named fallback target, using a Cloudflare API token stored in GitHub Actions secrets (not host's dashboard login).
- `.github/workflows/secrets-expiry-check.yml` (new) — monthly cron that queries expiry dates on known secrets + opens a GitHub issue ≥30 days pre-expiry.

**Scope:**

**Bills autonomy (gap 8):**
- GoDaddy domain: host pre-pays for 5 years (GoDaddy allows multi-year — already recommended in SUCCESSION.md §4.1). Runbook: "at next renewal window, pre-pay to 2031."
- Cloudflare: Free tier covers current + foreseeable 10k-user scale; no bill to fail. Worker paid tier at ~$5/mo enters when we scale beyond Workers free quota (~100k requests/day — not near-term).
- Hetzner: monthly billing via card. Pre-pay options exist (Hetzner accepts 12-month advance pay). Runbook: "pay 12 months in advance immediately post-Row-D; review annually."
- Supabase: Pro plan $25/mo via card; Supabase allows annual prepay ($300 with ~1 month free). Runbook: "switch to annual pre-pay at Row-D+30-day mark once traffic pattern confirmed."
- Fallback card: runbook names a secondary card (host's spouse's card or a backup card) that can be swapped in via each vendor's dashboard by a co-admin with vault access.

**DNS autonomy (gap 9):**
- Cloudflare API token (zone-edit scope) stored in GitHub Actions secrets + in SUCCESSION.md's vault.
- `scripts/emergency_dns_flip.py` supports: (a) flip Worker route off (apex `/mcp` back to raw tunnel), (b) change CNAME target, (c) add/remove a record. Runs via `gh workflow run emergency-dns.yml` by anyone with repo write access — host login to Cloudflare dashboard NOT required.
- Row E's Worker is a *separate* emergency path — deployed via `wrangler` from a repo-stored API token.
- **Row E's Worker independence materially covers Gap 9's primary scenario.** The emergency DNS script covers the residual: non-Worker DNS records (the tunnel subdomain, MX records, TXT for SPF/DKIM, any future subdomains).

**Secrets rotation (gap 10):**
- Monthly GHA cron queries: Cloudflare token expiry (Cloudflare API `/user/tokens/<id>`), Supabase JWT rotation date (manual — Supabase doesn't expose expiry API; cron checks a local `secrets-metadata.json` with human-maintained renewal dates), GitHub OAuth app secret expiry, Hetzner API token expiry.
- If any < 30 days from expiry, open a GitHub issue titled `SECRET EXPIRY: <name> in <N> days` with rotation runbook link.
- `docs/ops/host-independence-runbook.md` §3 carries a table of all known secrets + their metadata.
- `secrets-metadata.json` committed to repo (no secret values, only names + expiry dates + rotation runbook pointers).

**Effort:** ~1 dev-day bundled. Runbook is the longest; scripts are small.

**Cost:** $0/mo marginal (uses existing GHA + Cloudflare free-tier API).

**Sequence:** Dispatchable NOW for the scripts + runbook. Bill pre-pay is a host-action (not dev work) — can happen at any point; `SUCCESSION.md` §4.1 already recommends it.

**Acceptance:**
- A simulated DNS emergency: co-admin (or lead agent) runs `gh workflow run emergency-dns.yml` with a test payload; DNS change lands within 60 s; canary verifies; change is reverted.
- Secrets-expiry cron opens a test issue on a known-expiring secret.
- Bill pre-pay: Hetzner annual prepay confirmed in dashboard; runbook reflects the new expiry date.

---

## 5. Sequencing + timeline

Provider pick is locked (Hetzner). Worker (Row E) ships independently of Hetzner cutover. Row H (cloud canary) gates the §6 acceptance. No host round-trip in the critical path.

| Phase | Sequence | Dev-days | Wall-time |
|---|---|---|---|
| **P1 — Rows A + B + C** | Parallel across 1-2 devs (A + C independent; B serial) | ~1.5-2 dev-days serial, ~1 dev-day with 2 devs | 1-2 calendar days |
| **P1b — Row E (Worker, parallel)** | Independent of A/B/C; dispatchable post-Row-A | ~0.5 dev-day | 1 calendar day (overlapping P1) |
| **P1c — Rows H + I + N (all repo-only, parallel)** | Dispatchable NOW — no dependencies on D/Hetzner. H = cloud canary, I = GHCR, N = admin runbook + scripts. | ~2 dev-days total serial, ~1 dev-day with 2 devs | 1-2 calendar days (overlapping P1) |
| **P2 — Row D (Hetzner deploy)** | After A + B + C + I land | ~1-1.5 dev-days | 1-2 calendar days |
| **P2b — Rows J + K + L + M (on-box infra, parallel post-D)** | J = backup, K = logs, L = watchdog, M = CI deploy. All parallel; all depend on D. | ~2.25 dev-days total, ~1-1.5 dev-days with 2 devs | 1-2 calendar days |
| **P3 — Row F (smoke + 48h offline trial)** | After D + E + H land; J/K/L/M recommended but not hard-block | ~0.25 dev-day active + 48h wall | 3 calendar days |
| **P4 — Row G (canonical-URL docs sweep)** | After P3 acceptance closes clean | ~0.5-1 dev-day | 1 calendar day |
| **Total dispatch to sweep closed** | | **~8-11 dev-days active** | **7-10 calendar days with 2 devs; 10-13 with 1** |

**Realistic range:** 7-10 days with 2 devs in normal conditions. 11-14 days with 1 dev or if Row B surfaces more Windows-path surface area than audit predicts.

**Row H is a HARD BLOCK on §6 acceptance.** The 48h-offline gate cannot be validated if the canary itself runs on the host — without Row H, we're measuring host uptime, not public-URL uptime. Dispatch Row H as priority-equal to Row E.

**Critical path observation (updated):** parallelism now significant. Two devs can run:
- **Lane 1 (repo-only, no dependencies):** A → C → E → H → I → N. ~3.5 dev-days.
- **Lane 2 (serial but cheap):** B → wait-for-lane-1-A-done → parallel with lane-1-remainder.
- **After D:** J/K/L/M parallel.
Single-dev serial: ~8-11 dev-days. Two-dev parallel: ~5-7 dev-days.

**User-facing canonical restores on Row E ship, NOT on Row D / F.** Once the Worker is live, `tinyassets.io/mcp` works regardless of whether the tunnel origin is the host machine or the Hetzner box. Row H's cloud canary + Row I's GHCR + Row N's admin runbook all ship alongside E — the "user-visible restored + monitoring-independent + deploy-independent" story gets to green in roughly the same window.

---

## 6. Day 1 after cutover — acceptance criteria

The migration is "done" when all seven hold simultaneously for a 48-hour window:

1. **Cloud canary (Row H GHA cron) green for 48 consecutive hours** — `tinyassets.io/mcp` MCP health stays green and `mcp.tinyassets.io/mcp` public direct-origin access stays gated. Zero `exit != 0` probes on either. **Probed from GHA, not from host** — that is the load-bearing part.
2. **`selfhost_smoke.py` green at hour 1, 24, 47.** No tool output regressions from the remote box vs local prod baseline (captured one week before cutover). Default mode asserts canonical MCP health plus direct-origin Access gate; `--internal-parity` is reserved for service-token/internal tunnel paths.
3. **Host machine powered off or hibernated for ≥48 hours** without a single user-visible outage on `tinyassets.io/mcp`.
4. **Hard Rule 11 satisfied:** any Cloudflare Worker, DNS, or provider-dashboard reconfig during the 48h window ran `scripts/uptime_canary.py --once` post-change against the canonical URL and confirmed the direct-origin gate stayed closed.
5. **Succession runbook updated** — `SUCCESSION.md` §5 references the provider box as the current authoritative origin, with a link to Row C's cloudflared config template for rebuild-from-scratch.
6. **Row H alarm path verified** — induced outage during the trial produces a GitHub issue within ~10 min (Row H acceptance criterion held under live conditions).
7. **Row J backup ran at least once during the 48h window** — nightly snapshot landed in Hetzner Storage Box, rotation logic verified (not a bare "does it work" — an actual snapshot for that date is browsable).

**Recommended but not hard-block for the 48h gate:** Rows K (log aggregation), L (watchdog), M (CI deploy), N (admin runbook). These are always-works resilience layers; the gate is demonstrably independent without them, but shipping them before the gate closes means the system is durable, not merely currently-up.

If all seven hold, **the host's computer is officially replaceable.** The forever rule's "system is always up without us" has gained an important piece: "without this specific machine" is now provably true, and a suite of independence layers means the state stays true through next-week's power outage / card expiry / secret rotation.

---

## 7. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Row B (path extraction) surfaces undocumented Windows assumptions in LanceDB or a vendored dep | Start Row B audit in parallel with A; if surface area exceeds 1 dev-day, scope creep flag → re-estimate before committing. |
| Hetzner regional outage during near-term operation | Per plan-b §5.2 fallback trigger: move to Fly.io if Hetzner sustained outage > 24h or repeated <99% availability for 3 months. Fallback shape documented; not engaged until observed. |
| Tunnel auth regression during provider-swap | Row D includes Layer-1 canary probe immediately post-deploy + Hard Rule 11 post-change discipline. |
| Host local dev setup breaks after path-extraction refactor | Row B acceptance requires Windows-host behavior unchanged when `TINYASSETS_DATA_DIR` is unset. Regression test in tests/smoke/ covers both Unix + Windows default resolution. |
| Remote box starts empty but user-sim actually needs a universe | Box-starts-empty decision made in §3. If evidence surfaces post-deploy that a universe IS needed public-side, add a one-off data-seeding commit — additive, not re-architecture. |
| 48h offline trial during host travel / real use | Trial period can be any 48 consecutive hours; host picks a low-stakes window. Do NOT gate acceptance on trial completion — acceptance is "when 48h clean has happened," not "immediately." |
| OS patch cadence adds ~2-4 ops-hours/month | Accepted cost. Plan-b §6.6 documents this tradeoff; the always-works criterion weighed OS maintenance below control-plane-fate-sharing. Host runs `apt upgrade` + reboot on a monthly cron or delegates per SUCCESSION.md. |

---

## 8. What this plan does NOT decide

- **Full plan-b migration (Supabase → Hetzner / everything OSS-self-host).** That's `docs/specs/2026-04-19-plan-b-selfhost-migration-playbook.md` — executes when triggers fire per playbook §1. Near-term plan deliberately NOT that.
- **Multi-region / HA / load-test-at-scale.** Track J (per `docs/design-notes/2026-04-18-full-platform-architecture.md` §10) — pre-launch scale validation, not near-term.
- **CI/CD pipeline for the remote box.** First-ship uses manual `rsync + docker compose pull + up -d` to the Hetzner box. Automated deploy on push → later improvement.
- **Custom-domain TLS from the provider's origin** (beyond the Cloudflare-Origin-CA relationship). Existing Cloudflare CA cert (15-year validity per plan-b §3.5.3) fronts the provider; no new cert work.
- **Secrets migration for wallet / paid-market.** Those don't exist yet; Track A ships first, then wallet secrets join the Q-uptime-2 posture.
- **Dev → prod promotion flow.** Out of scope; today's question is "can host's computer be offline." Multi-env plumbing comes when there's a reason for staging.

---

## 9. Follow-up — merge into plan-b

After near-term ships + 48h trial green:

1. Update `docs/specs/2026-04-19-plan-b-selfhost-migration-playbook.md` §2 target architecture row "Gateway" to reflect Hetzner as current state rather than future assumption. Plan-b is now primarily about Supabase-escape scenarios (§5.1) rather than Gateway-escape; the near-term plan collapsed "plan-b for Gateway" into "current state for Gateway."
2. Add §3.5 "Pre-migration readiness — daemon/tunnel portability" as a warm path; Rows A+B+C artifacts from this plan ARE that warm path.
3. Cancel the host-machine-as-primary assumption anywhere it persists in docs (grep TBD).

Navigator owns the merge; ~0.25 nav-day after the 48h trial closes.

---

## 10. Summary for dispatcher

- **Scope:** MCP daemon + tunnel origin off the host machine. Near-term, not full plan-b.
- **Provider:** **Hetzner Cloud CX22 (Debian 12, Docker Compose).** Single pick, no host round-trip. Fallback: Fly.io (only on observed primary regression). Anti: Cloudflare Workers (rewrite cost too high).
- **Internal decisions pre-made (§3):** secrets = systemd EnvironmentFile; Postgres = Supabase managed; host machine = dev seat only; first box = empty.
- **Canonical URL architecture (§0):** user-facing `tinyassets.io/mcp` via Cloudflare Worker; debug `mcp.tinyassets.io/mcp` via tunnel direct; `api.tinyassets.io/mcp` never live, don't resurrect.
- **14 Work rows** across core migration (A-G) and 24/7 uptime gaps (H-N):
  - **Core migration A-G (7 rows):** containerize → extract paths → tunnel config → Hetzner deploy → Worker → smoke+trial → docs sweep.
  - **24/7 gaps H-N (7 rows, triaged from 10 lead-surfaced gaps):** cloud canary + alarm sink (H) / GHCR (I) / state backup (J) / log aggregation (K) / watchdog (L) / CI deploy pipeline (M) / bills+DNS+secrets admin (N).
- **Everything dispatchable now except D + J/K/L/M (depend on D) + F (depends on D+E+H) + G (depends on F).** Lanes:
  - Lane 1 (repo-only, no dependencies): A, C, E, H, I, N — ~3.5 dev-days.
  - Lane 2 (path-refactor serial): B — ~0.5-1 dev-day.
  - Post-D parallel: J, K, L, M — ~2.25 dev-days.
- **Total active dev:** ~8-11 dev-days serial, ~5-7 dev-days with 2 devs. Calendar 7-10 days with 2 devs to sweep closed.
- **Row H (cloud canary) is a HARD BLOCK on the §6 acceptance gate** — 48h-offline trial can't be validated by a canary that lives on the host.
- **Monthly infra cost at MVP:** Hetzner CX22 €4 + Storage Box €1 + Supabase Pro $25 + Cloudflare $0 + GHA $0 + GHCR $0 + Better Stack $0 = **~$30-35/month**. No line item scales surprisingly through the full-platform target.
- **User-facing canonical URL restores on Row E ship (~1-2 days from dispatch).** Host-machine-replaceable happens at §6 acceptance (7-10 days with 2 devs).

Go.
