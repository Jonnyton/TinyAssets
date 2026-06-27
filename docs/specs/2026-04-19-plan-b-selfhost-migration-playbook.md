---
status: active
---

# Plan-B Self-Host Migration Playbook

**Date:** 2026-04-19
**Author:** dev (self-dispatch #57)
**Status:** Pre-draft. Executable if Supabase / Fly.io become unreliable or unavailable.
**Purpose:** document the migration path from managed services (Supabase + Fly.io) to self-hosted (Hetzner + Docker) so the platform has a real exit option. Preserves the forever-rule "system is always up without us" when a single vendor dependency breaks.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` §3.2 recommends Supabase + notes ceiling-insurance.
- `docs/design-notes/2026-04-18-persistent-uptime-architecture.md` §3.2 external-host options matrix.
- `SUCCESSION.md` §6.6 one-liner pointing here.
- Memory: `project_godaddy_hosting.md` (host owns tinyassets.io + GoDaddy hosting).

---

## 1. When to execute this playbook

Four triggers, any one fires → evaluate migration:

1. **Service reliability collapse.** Supabase or Fly.io has sustained outage >24h OR repeated <99% monthly availability for 3 consecutive months.
2. **Pricing shock.** A vendor triples prices mid-quarter OR introduces a new tier making current-plan cost >4× prior.
3. **Business risk.** Vendor announces shutdown, is acquired by a company with misaligned policy, or forces a policy change we can't accept (e.g. training-data clause, export-restriction clause).
4. **Scale ceiling.** Sustained 100k+ DAU where managed costs exceed ~$800/mo vs self-host ~€50/mo (break-even stated in §3.3 of uptime note).

Partial triggers → stay + monitor. Full triggers → execute this playbook.

---

## 2. Target architecture (post-migration)

| Layer | Current | Target |
|---|---|---|
| DB | Supabase-hosted Postgres + PostgREST | Hetzner CX31 box: Postgres 15 + PostgREST + PgBouncer |
| Realtime | Supabase Realtime (WebSocket fan-out) | Same Hetzner box OR a second box: [supabase/realtime OSS](https://github.com/supabase/realtime) |
| Auth | Supabase Auth (GitHub OAuth) | Same Hetzner box: [supabase/auth OSS](https://github.com/supabase/auth) (formerly GoTrue) |
| Storage | Supabase Storage (S3-compat) | Cloudflare R2 (cheap S3-compat) OR Hetzner Object Storage |
| Edge Functions | Supabase Edge | Fly.io if still available; else Hetzner as Deno Deploy workers OR systemd-managed Python processes |
| Gateway | Fly.io Machines (tinyassets-gateway + tinyassets-web) | Hetzner CX11 boxes (1-2 per region) running same Docker images behind Cloudflare |
| CDN / Cache | Cloudflare (Free tier) | Unchanged — Cloudflare isn't part of the migration |
| Domain | GoDaddy (host-owned per memory) | Unchanged |

**Target cost:** ~€50-80/month at 10k-100k DAU range. Per uptime note §3.3 comparison. Per-DAU-tier breakdown in §6.5.

**One-click self-host alternatives:** if admin pool wants managed-style UX on self-hosted infra, consider [Coolify](https://coolify.io/) or [Easypanel](https://easypanel.io/) — Docker-compose orchestration layers that wrap the Supabase OSS stack + add a UI. Recommend keeping vanilla Docker Compose at launch (fewer moving parts to debug); revisit Coolify/Easypanel if the ops-burden from §6.6 becomes painful.

---

## 3. Pre-migration readiness (do this before trigger fires)

Don't wait for a crisis. Each of these keeps the migration path warm:

### 3.1 Monthly backup-to-self-host-storage smoke

- `pg_dump` of production Supabase → encrypted → Cloudflare R2 bucket.
- Automated via GitHub Action on a weekly cron (per `SUCCESSION.md` §5.2).
- **Monthly: manually restore the latest dump to a fresh Postgres container** and verify data integrity (check row counts on nodes, users, ledger match production). Target: <2h from download to verified restore.

### 3.2 Docker images parity

- Gateway + web-app already ship as Docker images to Fly (per #27 + #35 specs).
- **Also push images to a self-hostable registry** (Docker Hub, GHCR, or self-hosted Harbor). Any self-host box can pull.
- Quarterly: run `docker compose up` against a local Hetzner-shaped box and verify gateway serves `/mcp/health`. Catches drift early.

### 3.3 Supabase OSS compatibility tracking

- Track releases of `supabase/auth`, `supabase/realtime`, `supabase/postgrest` OSS components.
- Our schema + queries should work against OSS releases at any recent point. No vendor-specific Supabase-dashboard SQL.
- Audit quarterly: run a migration test against a pure-OSS stack.

### 3.4 DNS freeze rehearsal

- Document + test the exact Cloudflare DNS changes needed to point `mcp.tinyassets.io` (tunnel origin) + `tinyassets.io` (apex — landing + Worker-routed `/mcp*`) at Hetzner boxes. (Pre-launch drafts of this playbook named `api.tinyassets.io`; that was the intended canonical but was never shipped. Post-P0 canonical user-facing URL is `tinyassets.io/mcp`, Worker-proxied to `mcp.tinyassets.io`.)
- Rehearse once per year: temporarily add a staging Hetzner box, point a staging subdomain at it, verify TLS + health.

---

## 4. Migration execution — 4-phase

### Phase 1: Spin up self-host infra (1-2 days)

1. **Hetzner account:** if admin-pool doesn't have one, sign up + add billing per `SUCCESSION.md` §2.3 (bills-paying party).
2. **Provision boxes:**
   - **db-primary** (CX31, 8 GB RAM): Postgres 15 + PgBouncer + supabase/realtime + supabase/auth + pg_cron + weekly pg_dump to R2.
   - **gateway-1** (CX11, 2 GB RAM): Docker Compose with FastMCP gateway + SvelteKit web-app Node adapter.
   - **gateway-2** (CX11, 2 GB RAM): same, different region if budget allows (Hetzner Helsinki + Falkenstein = diverse).
3. **Install via automation.** Maintain `infra/selfhost/` in the `TinyAssets/` repo with:
   - `terraform/` or `docker-compose.yml` + `systemd/` unit files for the box configs.
   - `migrations/` — same SQL migrations as the Supabase stack.
   - `scripts/provision.sh` — one-command bootstrap.
4. **Secrets** — copy from vault (`TinyAssets-Prod` per SUCCESSION.md §3.2) to Hetzner-boxes' `.env` files. JWT secret + S3-API key + any remaining service creds.

### Phase 2: Restore data (4-8 hours, depending on DB size)

1. **Latest Supabase pg_dump** → restore to Hetzner db-primary.
2. **Verify row counts** match production (nodes, users, ledger, moderation tables).
3. **Sanity-query** a handful of discover_nodes calls against the restored DB.
4. **Start a DB-replication stream** from Supabase to Hetzner (optional but recommended; catches writes between dump + cutover).

### Phase 3: DNS cutover (30-60 minutes active, plus TTL propagation)

1. **Short-TTL preparation** (do this 24-48h ahead of cutover): lower Cloudflare DNS TTL on `mcp.tinyassets.io` + `tinyassets.io` to 60s.
2. **Final data sync:** stop Supabase writes (put gateway in read-only mode via `UPDATE app_config SET writes_enabled=false`). Take final dump; restore delta to Hetzner.
3. **Flip DNS:**
   - `mcp.tinyassets.io` A record → Hetzner gateway-1 IP (and gateway-2 as second record for round-robin).
   - `tinyassets.io` CNAME/flatten → Hetzner gateway-1 (SvelteKit dynamic routes) OR keep GitHub Pages for static catalog content (static/dynamic split holds even on self-host).
4. **Cloudflare Origin CA certs:** valid for 15 years per uptime note §3.5.3 — no new cert needed; existing one works against any origin.
5. **Propagation window (~5-10 min at 60s TTL):** monitor `tinyassets.io/mcp/health` (canonical apex). Check `mcp.tinyassets.io` only with the internal Access/service-token path when debugging tunnel parity. Some traffic hits old Supabase until propagation completes; readers get cached data, writers retry.

### Phase 4: Verify + decommission (first week post-cutover)

1. **Hour 1:** Verify all 8 scenarios from #26 load-test harness pass against new infra.
2. **Day 1:** Watch error rate + p95 latency. Compare to pre-cutover baseline.
3. **Day 3:** If stable, cancel Supabase auto-renewal. Keep project alive on free tier for 30 days as safety net (can point DNS back in under 1h if something cataclysmic happens).
4. **Day 30:** Delete Supabase project fully.
5. **Update `docs/design-notes/2026-04-18-full-platform-architecture.md` §3** to reflect new infra as the current state. `SUCCESSION.md` §5.2 updates box IPs + runbook URLs.

---

## 5. Per-failure-mode variants

The full playbook above migrates the whole stack. Cheaper partial migrations handle single-vendor failure:

### 5.1 Supabase only — keep Fly.io

- Trigger: Supabase pricing shock; Fly.io unaffected.
- Swap: DB + Auth + Realtime + Storage → Hetzner; Gateway + Web stay on Fly.
- Gateway config change: point at Hetzner's Postgres + Realtime URLs instead of Supabase's.
- Skip Phase 1 step 2's gateway boxes; keep Fly.

### 5.2 Fly.io only — keep Supabase

- Trigger: Fly.io outage or pricing shock; Supabase fine.
- Swap: Gateway + Web → Hetzner CX11; DB stays on Supabase.
- Gateway config change: same Postgres URL (Supabase-hosted); point `mcp.tinyassets.io` DNS at Hetzner IP.
- Skip Phase 1 step 2's db-primary; keep Supabase.

### 5.3 GitHub itself — most extreme

- Trigger: GitHub down or hostile to project; `TinyAssets/` + `TinyAssets-catalog/` repos become unreliable.
- Migration target: GitLab or self-hosted Gitea (Hetzner box, 1 GB RAM is enough).
- TinyAssets-catalog bot reconfigured for target VCS API.
- Contributors have the mirror URL; PR-ingest Action ported to target CI.
- **Highest-friction migration** — contributor community disruption is real cost.
- Mitigation: weekly full mirror to alternate VCS even pre-trigger. Per uptime note §14.9.

### 5.4 Cloudflare only

- Trigger: Cloudflare restricts us or the Free tier becomes unusable.
- Migration: Fastly / Bunny.net / direct origin-serve with self-hosted HAProxy.
- Lowest-friction because Cloudflare is stateless — just DNS + cache.

### 5.5 Mid-cutover rollback (migration fails after Phase 3 DNS flip)

If the self-host stack is unhealthy after the cutover + the 30-day safety net is still active (per §4 Phase 4), revert as follows. Target: total revert in <1 hour.

1. **Stop admitting new writes to self-host** — put self-host Postgres in read-only mode (`ALTER DATABASE workflow SET default_transaction_read_only = on`).
2. **Identify the delta** — rows written to self-host since the cutover. Export via `pg_dump --where='updated_at > '<cutover_timestamp>'` (or use logical replication if it was set up in Phase 2).
3. **Apply delta to original Supabase** — `pg_restore` the delta dump against the paused-but-alive Supabase project.
4. **DNS flip back** — Cloudflare DNS records point back at Supabase's origin. Because TTL was lowered to 60s in Phase 3, propagation completes in ~5-10 min.
5. **Resume writes on Supabase** — original project had auto-renewal cancelled but project was kept alive on free tier; re-enable Pro plan.
6. **Post-mortem** — write up what failed in self-host; fix for next attempt.

**If the 30-day safety net has expired:** rollback is harder but possible via `pg_dump` from self-host → restore to a fresh Supabase project + DNS repoint. Worst case ~4-6 hours. Document lessons for next time.

**Rollback triggers** (start executing when):
- Gateway p99 latency >5s sustained >15 min on self-host.
- Error rate >5% on self-host for >15 min.
- Postgres connection exhaustion on self-host box (likely PgBouncer misconfig).
- Storage corruption detected in the first 24h.

---

## 6. Data migration details

### 6.1 Postgres → Postgres

`pg_dump -F c` + `pg_restore` is the reliable path. Custom format (`-F c`) is compressed + parallel-restorable. For our data sizes (<100 GB at 100k DAU), a restore completes in under an hour on CX31.

### 6.2 Supabase Auth → supabase/auth OSS

Same schema (both use `auth.users`, `auth.identities`, `auth.refresh_tokens`). OSS image reads from the same DB once the DB is migrated. Zero schema transformation needed. GitHub OAuth config (client ID + secret) moves via env vars.

### 6.3 Supabase Storage → R2

Storage API is S3-compatible both sides. `rclone sync` between buckets handles migration; takes hours for large canons, but canons are per-host so the control-plane-only portion is small.

### 6.4 Supabase Edge Functions → Hetzner

Edge Function code is Deno or Node. Port to:
- **Option A:** Deno Deploy (managed, similar to Supabase Edge).
- **Option B:** Systemd-managed processes on Hetzner boxes (ugly but portable).
- **Option C:** Cloudflare Workers (more restrictions but cheap).

Recommend **A** for minimal code change; **B** if we're fully anti-managed-services by this point.

### 6.5 Cost comparison per scale tier

Approximate monthly costs (USD), hosted vs self-hosted on Hetzner. Managed-service numbers per the live pricing pages (Apr 2026); self-host numbers based on Hetzner Cloud CX-line pricing.

| DAU tier | Managed (Supabase Pro + Fly) | Self-hosted (Hetzner) | Break-even |
|---|---|---|---|
| **1k DAU** | ~$40/mo — Supabase Pro $25 + Fly min=2 $15 | ~$15/mo — 1× CX31 (8 GB) + 2× CX11 (2 GB) ≈ €14 | Hosted wins on ops-burden; cost basically a wash. Stay managed. |
| **10k DAU** | ~$75-150/mo — Pro $25 + Realtime overage ~$20 + Fly $30 + storage $15 | ~$25-35/mo — CX41 (16 GB) + 2× CX21 (4 GB) + R2 | Self-host is ~3× cheaper; ops-burden matters more than $. See §6.6. |
| **100k DAU** | ~$800-1500/mo — Pro + heavy Realtime + larger Fly fleet + bandwidth | ~$80-120/mo — dedicated AX41 (32 GB) + 4× CX31 + R2 + bandwidth | **Self-host saves ~10×.** Below this scale the savings don't justify migration; above this scale they do. |

**Break-even takeaway:** at 1k DAU managed is free-equivalent. At 10k DAU self-host is cheaper but not compellingly so. **At 100k DAU, self-hosting is the correct decision** — both for cost AND because the managed plans at that scale start having per-request overage patterns that don't align with our workflow (bursty daemon work).

Figures are rough — exact costs depend on Realtime-connection concurrency (dominant Supabase variable) + outbound-bandwidth (dominant on both sides).

### 6.6 Ops-burden comparison

Migration from managed → self-hosted lands new responsibilities on the admin pool.

| Responsibility | Managed (today) | Self-hosted (post-migration) |
|---|---|---|
| Postgres version upgrades | Supabase handles automatic | Admin runs `pg_upgrade` on schedule; downtime window required. ~1 hour per major version. |
| Security patches (Postgres, Realtime, Auth) | Supabase handles | Admin applies. Usually monthly. Dependabot-style reminder via cron. |
| Backup automation | Supabase daily PITR | Admin runs `pg_dump` cron + R2 upload + quarterly restore-test. |
| TLS cert rotation | Cloudflare Origin CA 15-year validity (unchanged). Let's Encrypt for origin-direct. | Same — Cloudflare handles public-facing; Postgres connection uses cert-from-vault. |
| Realtime server health | Managed by Supabase | Admin monitors via healthcheck cron + PagerDuty/Pushover-style alert. |
| DDoS mitigation | Cloudflare (unchanged) + Supabase-layer protections | Cloudflare still in front (free tier is fine); origin-layer protections must be added (fail2ban, Postgres rate limits). |
| Scaling decisions | Supabase plan tier change | Admin sizes Hetzner box + does blue-green swap for upgrade. |
| On-call coverage | None needed | Admin-pool rotation; bus-factor ≥ 2 (per SUCCESSION.md §2). |

**Estimated added ops time:** ~2-4 admin-hours/month during steady-state, assuming weekly restore-test + monthly patch + emergency incident buffer. Spikes on version upgrades (~1 day every 12-18 months).

**This is NOT free.** At 1k DAU, managed saves more than it costs vs self-host ops overhead. At 100k DAU, self-host dollars saved ($700-1400/mo) dwarf ops time at any reasonable contributor rate.

**Critical pre-migration check:** does the admin pool have the skill to run Postgres competently? If yes, self-host is viable. If no, managed + accept the cost is the honest answer.

---

## 7. Dev-day estimate

Full 4-phase migration at 10k DAU, assuming pre-migration readiness (§3) is maintained:

| Phase | Estimate |
|---|---|
| Phase 1: Provision + config | 1.5 d |
| Phase 2: Data restore + verify | 0.5 d (DB size dependent) |
| Phase 3: DNS cutover | 0.5 d |
| Phase 4: Verify + 30-day hold | 1 d active; rest is monitoring |
| **Total** | **~3.5 d active work over 30 days** |

At 100k DAU, add ~1 d for larger DB restore + more scenario verification.

Without pre-migration readiness (cold-start migration): add 2-3 d for tooling that should have been warm.

**Recommend: keep pre-migration readiness warm so full migration is ~3.5 d. Cold-start migration could take 6+ d in crisis conditions.**

---

## 8. OPEN flags

| # | Question | Tag |
|---|---|---|
| Q1 | Hetzner vs other self-host (Linode / Vultr / OVH) — pick a preferred backup-host per cost + regulatory fit | LATER |
| Q2 | Terraform vs Docker-Compose for self-host provisioning | LATER |
| Q3 | Monthly vs quarterly restore-rehearsal cadence — tradeoff of discipline cost vs rust | LATER |
| Q4 | Supabase Realtime OSS vs roll-our-own-WebSocket-fan-out if OSS gets archived | LATER |
| Q5 | Pre-cutover DB replication mechanism — logical replication vs Debezium vs pg_dump-based | LATER |
| Q6 | Contingency if GitHub bans the project — which alternative VCS is the pre-selected backup? | HOST |

---

## 9. Cross-references

- `SUCCESSION.md` §6.6 — the one-liner that points readers here.
- `docs/design-notes/2026-04-18-persistent-uptime-architecture.md` §3 — external-host matrix + recommendation path.
- `docs/design-notes/2026-04-18-full-platform-architecture.md` §3.2 — Supabase pick + ceiling-insurance framing.
- `docs/specs/2026-04-18-load-test-harness-plan.md` §10 — acceptance test post-migration.
- Memory: `project_godaddy_hosting.md` — domain ownership outside the migration surface.
- Memory: `project_host_independent_succession.md` — forever-rule motivation.
