# Uptime Phase 1a — Static Landing + Catalog (Exec Plan)

**Date:** 2026-04-18
**Author:** navigator
**Status (2026-04-18 update):** **SUPERSEDED** by `docs/design-notes/2026-04-18-full-platform-architecture.md`. Host rejected the phased rollout in favor of single-build. Phase 1a (static landing + catalog) is absorbed into the full-platform web app (built as part of track B in the successor's §10 sequencing). Do NOT dispatch this exec plan.

**Original status:** Exec plan. Ready for dev dispatch when host greenlights §7 decisions.
**Relates to:** `docs/design-notes/2026-04-18-persistent-uptime-architecture.md` §7 Phase 1a + §3.5.4 (cache invalidation). Task #16.

---

## §1. Scope

Phase 1a is the **fastest shippable piece** of the persistent-uptime work: a read-only surface at `tinyassets.io` that stays up 24/7 regardless of whether any daemon host is online. Days to ship, not weeks.

**In scope for Phase 1a:**
- **`tinyassets.io/`** — static marketing landing page. Keeps the "summon the daemon" brand voice (project memory). Explains what Workflow is, links to "connect your Claude.ai" instructions, shows a live status badge.
- **`tinyassets.io/catalog/`** — read-only HTML browser over the flat-YAML catalog already in the repo (`goals/*.yaml`, `branches/*.yaml`, `nodes/*/`). Lists goals, drills into branches and nodes. Uses the GitHub-as-catalog direction as its source of truth.
- **`tinyassets.io/status.json`** — small JSON blob: last-seen timestamp, git SHA of the catalog snapshot, `hosts_online: 0` placeholder (populated by Phase 1b; in 1a it's always 0 and that's fine). Gives clients a 24/7 "awake" signal.
- **`tinyassets.io/catalog/index.json`** — single JSON index of all goals/branches/nodes for Phase 1b consumers (control plane reads it on cold start, Cloudflare caches it).

**Explicitly out of scope (wait for Phase 1b):**
- MCP dynamic surface (`tinyassets.io/mcp`). Phase 1a does NOT touch the existing cloudflared tunnel at `tinyassets.io/mcp` — behavior there is unchanged.
- OAuth / identity / bearer tokens.
- Bid inbox, request queue, daemon dispatch.
- Write operations of any kind.
- Any change to the on-host tray or `tinyassets/universe_server.py` runtime surface.

**What Phase 1a wins us on the three host requirements:**
- **(1) Always-on for node work** — *partial*. Users can browse goals/branches/nodes 24/7. Creation still requires a live host (Phase 1b).
- **(2) Full capability when any host is serving** — *no change*. Phase 1a doesn't touch the dynamic path.
- **(3) Reference-host independence** — *partial*. Catalog is browseable when the laptop is off. MCP is not yet.

This is a deliberately narrow win. It's worth shipping on its own because "users hit `tinyassets.io` and get a real site instead of HTTP 530" is a concrete, testable upgrade to the first-run experience.

---

## §2. Catalog source + build pipeline

**Canonical source:** this repo (`Workflow`). The `goals/`, `branches/`, `nodes/` trees are already flat YAML per the GitHub-as-catalog research. No separate catalog repo needed for v1. If splitting becomes desirable later (scale, private forks, author repos), that migration happens in v2+.

**Build pipeline (new):**

1. A small Python generator script, new file `scripts/build_catalog_site.py`, walks `goals/`, `branches/`, `nodes/` and produces:
   - `site/index.html` (landing page from a Jinja template).
   - `site/catalog/index.html` (goals list).
   - `site/catalog/goals/<slug>/index.html` (per-goal page listing its branches).
   - `site/catalog/branches/<slug>/index.html` (per-branch page listing its nodes).
   - `site/catalog/nodes/<slug>/index.html` (per-node page).
   - `site/catalog/index.json` (the machine-readable manifest for Phase 1b).
   - `site/status.json` (version + git SHA + build timestamp).
   - `site/robots.txt`, `site/favicon.ico`, basic CSS.
2. The generator uses templates from a new `scripts/catalog_templates/` directory (Jinja2). Static CSS from `scripts/catalog_static/`.
3. **Build command:** `python scripts/build_catalog_site.py --out site/` (idempotent, safe to re-run).
4. Output directory `site/` is `.gitignore`d. CI rebuilds on every merge.

**GitHub Actions wiring (new):** `.github/workflows/publish-catalog-site.yml`.
- Triggers: `push` to `main` touching `goals/**`, `branches/**`, `nodes/**`, `scripts/build_catalog_site.py`, `scripts/catalog_templates/**`, `scripts/catalog_static/**`, or the workflow file itself.
- Steps:
  1. Checkout, set up Python 3.11.
  2. `pip install jinja2 pyyaml` (thin; no full project install needed for the generator).
  3. Run the generator.
  4. Deploy `site/` to the chosen target (see §3).
  5. On success, POST to Cloudflare Cache Purge API to invalidate `/catalog/*` and `/` (scoped API token in GitHub Actions secrets).

**Why Python not Node:** the project is already Python; the generator imports `tinyassets/` schemas directly (or duplicates a minimal loader) rather than re-parsing YAML in a different language. Keeps one toolchain.

**Existing code to reuse (read-only):** `tinyassets/catalog.py` if present (grep finds usage sites) to share model definitions; otherwise the generator's YAML loader is small and standalone. Dev decides the call on implementation — don't over-couple to runtime code.

---

## §3. Deploy target — GoDaddy shared (locked in)

**Host data point 2026-04-18:** current GoDaddy plan is $89.99/year (~$7.50/mo). That pins the tier in **shared hosting** territory (Economy/Deluxe — PHP + MySQL + static HTML via cPanel). Not a VPS. Static hosting is exactly what Phase 1a needs, and this plan is already paid for.

**Decision: deploy Phase 1a to GoDaddy shared at `tinyassets.io/`.** Sunk cost. Zero new spend. Keeps one vendor for Phase 1a. GitHub Pages is documented as the fallback only if dev hits a blocking limitation on the shared tier.

### §3.1 GoDaddy shared (locked-in target)

- **Mechanism:** GitHub Actions publishes `site/` to GoDaddy via SFTP (or SSH if the tier allows). All GoDaddy shared tiers include SFTP via cPanel; SSH is limited to higher shared tiers — dev verifies at workflow-setup time. SFTP is sufficient.
- **GitHub Action step:** use a maintained SFTP-deploy action (e.g. `wlixcc/SFTP-Deploy-Action` or similar). Credentials stored as GitHub Actions secrets: `GODADDY_SFTP_HOST`, `GODADDY_SFTP_USER`, `GODADDY_SFTP_PASSWORD` (or key). Host supplies these when workflow is wired.
- **Target path:** cPanel's `public_html/` (or the account's web-root equivalent). Generator output mirrors directly into the web-root.
- **Cost:** $0 incremental — using the already-paid $89.99/yr plan.
- **Deploy latency:** ~30–90 s (SFTP transfer + Cloudflare cache purge).
- **TLS back to origin:** GoDaddy shared offers Let's Encrypt via cPanel; Cloudflare terminates TLS at the edge and re-encrypts to GoDaddy in Full (strict) mode. Universal SSL (free) covers the apex + one subdomain level.
- **Deploy-verification step:** the workflow `curl`s `tinyassets.io/status.json` post-deploy and fails the job if the expected `catalog_sha` does not match the just-pushed SHA. Prevents silent SFTP failures masked by Cloudflare cache.

### §3.2 GitHub Pages (fallback if a shared-tier blocker surfaces)

Keep documented but do not default to it. Use only if dev discovers that the specific GoDaddy plan blocks Phase 1a in a hard way — e.g. no SFTP writes to `public_html/`, some shared-hosting proxy strips our `Cache-Control` headers in a way Cloudflare can't override, or the plan has egress limits that hurt at scale. None of these are expected on $89.99/yr Economy-tier; flag only if observed.

- **Mechanism:** `actions/deploy-pages@v4` publishes `site/` to the repo's GitHub Pages; `tinyassets.io` CNAME-flattened to `<org>.github.io`.
- **Cost:** $0.
- **Trade-off vs GoDaddy:** cleaner deploy path (no FTP credentials), abandons sunk GoDaddy value. Not chosen.

### §3.3 Cloudflare configuration

Per uptime design note §3.5.3:

- DNS: `tinyassets.io` A-record to the GoDaddy shared-hosting IP (cPanel dashboard shows it), orange-clouded.
- TLS: Full (strict). Origin certificate via cPanel Let's Encrypt or Cloudflare Origin CA.
- Cache Rule (Free tier, 1 of 10): match URL path `/catalog/*`, Edge TTL 5 min, `stale-while-revalidate` 24 h.
- Cache Rule 2 (2 of 10): match `/` and common static assets (`/*.css`, `/*.js`, `/favicon.ico`, `/status.json`), Edge TTL 5 min + swr 24 h.
- **Do not touch `/mcp*` cache settings in Phase 1a.** That path continues to route to the existing cloudflared tunnel → laptop as it does today. Preserve via Cloudflare Origin Rule (see §7.2 Q10).

### §3.4 Cloudflare configuration (applies to either target)

Per uptime design note §3.5.3, the relevant records and rules for Phase 1a:

- DNS: `tinyassets.io` A/CNAME-flattened to Pages (or GoDaddy), orange-clouded.
- TLS: Full (strict).
- Cache Rule (Free tier, 1 of 10): match URL path `/catalog/*`, Edge TTL 5 min, `stale-while-revalidate` 24 h.
- Cache Rule 2: match `/` and common static assets (`/*.css`, `/*.js`, `/favicon.ico`, `/status.json`), Edge TTL 5 min + swr 24 h.
- **Do not touch `/mcp*` cache settings in Phase 1a.** That path continues to route to the existing cloudflared tunnel → laptop as it does today.

---

## §4. Content templates

Minimum templates required. Dev has latitude on HTML/CSS; copy below is the authoritative starting point.

### §4.1 Landing page (`site/index.html`)

One-page pitch with daemon-vocabulary brand voice. Required sections:
- **Hero:** headline "Summon the daemon." Sub-headline: one-sentence explanation of Workflow as a goals-and-daemons platform.
- **How it works (3 cards):** (a) Pick a goal, (b) Summon a daemon, (c) Fork and remix branches.
- **Connect your Claude.ai:** step-by-step for adding the MCP connector at `tinyassets.io/mcp` (current endpoint; Phase 1b migrates to `tinyassets.io/mcp`).
- **Status badge:** pulls from `/status.json`, shows green ("catalog live, <N> goals, <M> branches") or yellow ("no daemons currently online — you can still browse"). Never red: if `/status.json` itself is unreachable, Pages is down and the badge is invisible anyway.
- **Footer:** link to GitHub repo, link to `/catalog/`.

### §4.2 Catalog index (`site/catalog/index.html`)

List of goals. Each row: goal name, description (first ~200 chars), branch count, author, visibility. Link to per-goal page. Filter/search is Phase 1b — for now it's a flat list (~20 goals today per `goals/*.yaml` inventory).

### §4.3 Per-goal (`site/catalog/goals/<slug>/index.html`)

Goal name, full description, author, creation date, full branch list. Each branch row links to its page.

### §4.4 Per-branch (`site/catalog/branches/<slug>/index.html`)

Branch name, intent/premise, goal back-link, daemon-soul reference (if any), list of nodes. Each node row links to its page.

### §4.5 Per-node (`site/catalog/nodes/<slug>/index.html`)

Node name, description, required capabilities (if declared per the node-software-capabilities design), prompts, fork lineage if present. Node definitions may be directories (`nodes/<slug>/`) — dev's generator handles both.

### §4.6 `status.json` schema

```
{
  "version": "1a",                    # phase marker
  "generated_at": "2026-04-18T...",   # ISO-8601
  "catalog_sha": "<git-sha>",         # git commit of this snapshot
  "goals": <int>,
  "branches": <int>,
  "nodes": <int>,
  "hosts_online": 0,                  # always 0 in Phase 1a
  "mcp_endpoint": "tinyassets.io/mcp" # current; migrates in 1b
}
```

`hosts_online` is a placeholder. The real host directory is Phase 1b. Keeping the field in the schema now means Phase 1b adds a dynamic source without schema churn.

### §4.7 Catalog manifest (`site/catalog/index.json`)

Machine-readable flat manifest — arrays of `{slug, name, href, tags}` for each of goals/branches/nodes. Consumed by Phase 1b's control-plane cold start and by Claude.ai's MCP server when it wants to describe the catalog. Thin; ~20 KB at current catalog size.

---

## §5. Claude.ai connector behavior during Phase 1a

**Fact:** the existing MCP connector URL in Claude.ai is `https://tinyassets.io/mcp`. That path still routes through cloudflared → laptop → FastMCP on :8001. Phase 1a **does not change this**.

**What changes for users in Phase 1a:**
- Users hitting the domain root `https://tinyassets.io/` now see the landing page 24/7 instead of HTTP 530 when the laptop is off.
- Users hitting `https://tinyassets.io/catalog/` get a browseable catalog 24/7.

**What does NOT change in Phase 1a:**
- Users' MCP connectors at `tinyassets.io/mcp` still go HTTP 530 when the laptop is off. That's fixed in Phase 1b when `tinyassets.io/mcp` comes online with a queued-response path.

**User-facing messaging in the transitional window:**
- Landing page's "Connect your Claude.ai" section includes a clear note: *"Workflow is in Phase 1 — MCP dynamic tools require a running daemon host. You can browse the catalog anytime; creation and daemon summoning resume when a host is online. We'll announce always-on MCP (Phase 1b) shortly."*
- The status badge explicitly reads "no daemons currently online — browse-only mode" when `hosts_online == 0`.

This is honest, short, and gives users a reason to come back. Avoids the worst outcome (user adds connector, gets 530 once, never tries again) by giving a working non-MCP surface that explains the state.

---

## §6. Tasks

Dev-sized rows ready for the STATUS.md Work table. Files column is the collision boundary; Depends is intra-plan unless noted.

| # | Task | Files | Depends | Estimate |
|---|------|-------|---------|---|
| 1a-1 | Scaffold generator + templates | `scripts/build_catalog_site.py`, `scripts/catalog_templates/*.j2`, `scripts/catalog_static/*.css` | — | 0.5 dev-day |
| 1a-2 | Landing page copy + hero CSS | `scripts/catalog_templates/index.html.j2`, `scripts/catalog_static/style.css` | 1a-1 | 0.25 dev-day |
| 1a-3 | Catalog index + per-goal/branch/node templates + manifest | `scripts/catalog_templates/catalog_*.html.j2`, generator logic for `/catalog/*.json` | 1a-1 | 0.5 dev-day |
| 1a-4 | `status.json` generator + badge endpoint contract | `scripts/build_catalog_site.py` (status.json section) | 1a-1 | 0.1 dev-day |
| 1a-5 | GitHub Action `publish-catalog-site.yml` | `.github/workflows/publish-catalog-site.yml` | 1a-1 through 1a-4 | 0.25 dev-day |
| 1a-6 | Cloudflare DNS + TLS + Cache Rules setup | (Cloudflare dashboard — no repo files) | 1a-5 live | 0.25 host-day (not dev) |
| 1a-7 | Cache-purge token + GitHub Actions secret wiring | `.github/workflows/publish-catalog-site.yml` (purge step) | 1a-6 | 0.1 dev-day |
| 1a-8 | Smoke test: curl the public surface end-to-end | `tests/test_catalog_site_smoke.py` (optional — can live as a manual checklist) | 1a-7 live | 0.1 dev-day |

**Total dev estimate:** ~1.75 dev-days + ~0.25 host-day for Cloudflare config clicks. Days-to-ship is realistic.

---

## §7. Risks + host decisions before dev starts

### §7.1 Risks

- **Catalog YAML schema drift.** Several `goals/*.yaml` files are clearly test fixtures (`a.yaml`, `b.yaml`, `todelete.yaml`, `doomed.yaml`). The generator needs a filter policy: default to `visibility: public` only, skip `deleted` / `discarded` / well-known test slugs. *Mitigation:* generator has an explicit whitelist/blacklist pass, documented in `scripts/build_catalog_site.py`. Host may want a `catalog_public: true` flag convention going forward — flag in §7.2 Q11.
- **Daemon-soul / sensitive content leakage.** If any branch frontmatter contains private-tier content (privacy design note §7.5), it must not render. *Mitigation:* generator refuses to include artifacts with `sensitivity_tier != public`. Confidential content never enters the static snapshot. Dev implements as a hard filter.
- **Apex DNS currently points at the cloudflared tunnel.** Switching the A-record to GoDaddy shared-hosting would break the live `/mcp` connector. *Mitigation:* Cloudflare Origin Rule keeping `/mcp*` on the existing `<tunnel-uuid>.cfargotunnel.com` origin while `/` and `/catalog/*` go to GoDaddy. Confirm in §7.2 Q10.
- **SFTP deploy credential management.** GoDaddy SFTP password stored as GitHub Actions secret. If the password rotates or the plan migrates, the workflow fails silently at deploy time. *Mitigation:* post-deploy `curl`-status-json verification step fails the job when `catalog_sha` doesn't match — catches silent SFTP failure.
- **cPanel webroot assumption.** `public_html/` is the standard path but host plan may vary. *Mitigation:* dev confirms webroot via cPanel on setup. One-line config in the workflow.
- **GoDaddy shared-hosting header behavior.** Some shared tiers strip or override `Cache-Control` headers. *Mitigation:* Cloudflare Cache Rules override at the edge regardless of origin headers. No risk in practice.
- **Cloudflare Cache Rules count.** Free tier allows 10. Phase 1a uses 2. 8 left for Phase 1b + future growth.

### §7.2 Host decisions required before dev starts

**Uptime design note §8 Q1 partially resolved** (GoDaddy plan = $89.99/yr shared, NOT VPS). Phase 1b control plane therefore targets Fly.io — unblocked for Phase 1a dispatch. Phase 1a itself uses GoDaddy shared as the locked-in static host per §3.

**Q9 — RESOLVED.** Deploy target locked as GoDaddy shared (sunk cost, $0 incremental). GitHub Pages remains as a dev-fallback if a shared-tier blocker appears during implementation. No host decision required.

**Q10: `/mcp` routing during DNS cut-over (still required).** Confirm Cloudflare Origin Rule keeping `/mcp*` on the cloudflared tunnel while `/` and `/catalog/*` go to GoDaddy shared. Recommended. Alternative is a brief `/mcp` outage during DNS propagation — not recommended, would break live Claude.ai connectors.

**Q11: Catalog visibility filter (still required).** Static site includes all public goals/branches/nodes by default, filtering `visibility != public` and well-known test slugs (`a`, `b`, `todelete`, `doomed`, `x`). Confirm filter policy, or provide explicit allow-list / blacklist.

**Q12 (new, minor): GoDaddy SFTP credentials.** Host provides SFTP hostname, username, and password (or SSH key if tier allows) to wire as GitHub Actions secrets. Also confirms webroot path (typically `public_html/`). Not blocking the design; blocking the first workflow run.

Three Qs (Q10, Q11, Q12) answerable in a single message. All preferences + credentials.

---

## §8. Go/no-go — acceptance + rollback

### §8.1 Acceptance criteria

1. `curl https://tinyassets.io/` returns the landing page with HTTP 200 when the laptop is off.
2. `curl https://tinyassets.io/catalog/` returns a browseable goals list, HTTP 200, laptop state irrelevant.
3. `curl https://tinyassets.io/status.json` returns valid JSON matching the §4.6 schema, HTTP 200.
4. A push to `main` that touches `goals/X.yaml` results in `https://tinyassets.io/catalog/goals/X/` reflecting the change within 3 minutes (90 s deploy + swr buffer).
5. `curl https://tinyassets.io/mcp` behavior is unchanged — still routes through cloudflared.
6. All CF Cache Rules verified via `cf-cache-status` response header (`HIT` after first request on cached paths, `BYPASS` on `/mcp*`).
7. Claude.ai users report landing page + catalog visible when laptop is off (manual host-watching-browser check per user-sim conventions).

### §8.2 Rollback

Phase 1a is **additive and fully reversible.**

1. Revert the DNS change at Cloudflare (A-record back to the tunnel, remove any Origin Rules for `/mcp*`). ~60 s propagation at Cloudflare's edge.
2. Disable the GitHub Action workflow.
3. Delete the Pages deployment (or leave it dormant — costs $0).
4. No on-host code was touched. `universe_tray.py` behavior identical pre- and post-rollback.

Rollback MTTR: under 5 minutes if the host has Cloudflare dashboard access.

---

**Ready for dev dispatch when host greenlights §7.2 decisions (Q10 `/mcp` routing, Q11 visibility filter, Q12 SFTP credentials).**
