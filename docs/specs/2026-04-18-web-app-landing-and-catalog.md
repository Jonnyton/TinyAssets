---
status: active
---

# Web App — Landing + Catalog + Per-Tier Onboarding (Track B)

**Date:** 2026-04-18
**Author:** dev (task #34 pre-draft; unblocks track B when dispatched)
**Status:** Pre-draft spec. No code yet. Executable on dispatch without design re-research.
**Source of truth:**
- `docs/design-notes/2026-04-18-full-platform-architecture.md` — §2.3 diagram, §5 hosting, §13 onboarding per tier, §15 discovery.
- `docs/design-notes/2026-04-18-persistent-uptime-architecture.md` — §3.5 Cloudflare cache rules, GitHub Pages / GoDaddy static split, per-subdomain layout.
- `docs/specs/2026-04-18-full-platform-schema-sketch.md` — `discover_nodes` RPC shape, `nodes.concept` public read via `nodes_public_concept` view.
- `docs/specs/2026-04-18-mcp-gateway-skeleton.md` — OAuth 2.1 handshake endpoints gateway exposes.
- `docs/specs/2026-04-18-paid-market-crypto-settlement.md` — wallet-connect at bid time.
- `docs/specs/2026-04-18-daemon-host-tray-changes.md` — tray download flow from `/host`.
- `docs/specs/2026-04-18-export-sync-cross-repo.md` — catalog content published to `TinyAssets-catalog/` and rendered into `/catalog/*`.

Track B is tier-1's browser surface + tier-2 + tier-3 onboarding gateway. It is the first thing a viral-loop visitor sees. Getting it wrong means losing users at the top of the funnel. Getting it right means a 60-second path from "never heard of Workflow" to "my first MCP tool call landed."

---

## 1. Stack pick

Four candidates. Criteria: (a) SSR for SEO (viral catalog URLs must be indexable), (b) Supabase-native auth + Realtime bindings, (c) the static `/catalog/*` portion is static-hostable (GitHub Pages / GoDaddy shared hosting), (d) the dynamic portion runs on the same control-plane infra as the gateway (Fly.io / Supabase Edge).

| Stack | SSR | Supabase-native | Static-hostable | Fly.io-compat | Verdict |
|---|---|---|---|---|---|
| **SvelteKit** | ✓ (Vite-powered, adapter-static for fully-static builds) | ✓ (`@supabase/ssr` package first-class) | ✓ (`adapter-static`) or edge-rendered via `adapter-netlify`/`adapter-cloudflare` | ✓ (Node or edge) | **Recommend**. Smallest bundle, best SEO, clean static/dynamic split via adapters. |
| **Next.js** | ✓ (heavyweight) | ✓ (supabase-js, auth helpers) | Partial — app-router SSG works; app itself is a Node bundle | ✓ | Biggest community; bundle overhead; opinionated on Vercel. |
| **Remix** | ✓ | ✓ | ❌ — Remix is server-rendered only; no pure-static output | ✓ | Drops because we want `/catalog/*` pure-static for Cloudflare-edge caching. |
| **Plain HTML + HTMX + Astro** | ✓ (Astro SSG for static; HTMX for interactivity) | Manual (supabase-js vanilla) | ✓ | ✓ | Minimal; trades framework ergonomics for control. Strong fallback if SvelteKit proves heavy. |

**Pick: SvelteKit** with a dual-adapter deployment:
- `adapter-static` generates `/catalog/*` + landing page at build time. Artifacts deploy to GitHub Pages (`tinyassets.io/catalog/` per uptime note §3.5.3).
- `adapter-node` (or `adapter-fly`) runs the dynamic routes — `/connect`, `/host`, `/contribute`, `/status`, `/editor/*` — on Fly.io Machines alongside the gateway. Shares the same bearer-token + RLS primitives.

**Why SvelteKit over Next:**
- Smaller bundles matter on the landing page's TTFB (tier-1 is a cold-visitor funnel; every 100ms of JS load loses 2% of funnel).
- Sveltekit's islands-style partial hydration fits the "mostly-static landing + small interactive widgets" shape better than Next's all-React model.
- Supabase officially supports both, parity on auth helpers.

**Why not Astro+HTMX fallback:** catalog UX needs per-card interactive widgets (fork button, upvote, presence indicator) that HTMX handles via ad-hoc endpoints. SvelteKit gives the same with a component model. Astro stays in reserve if SvelteKit's dynamic-route cost grows.

---

## 2. Site map — 10 URL surfaces

All under `tinyassets.io/`. SEO-relevant URLs in bold.

| Path | Rendered | Purpose | Surface |
|---|---|---|---|
| **`/`** | SSG | Landing. Hero ("Summon the daemon"), 3-step how-it-works, 3 CTAs for 3 tiers. | Static (GH Pages) |
| **`/catalog/`** | SSG | Catalog home. Top goals / trending branches / recent remixes. Ranked via `nodes_hot` MV at build time + client-side Realtime refresh. | Static (GH Pages) + client hydration |
| **`/catalog/nodes/<slug>`** | SSG per node | Individual node page. Full public-concept, provenance chain, usage stats, remix CTA. One canonical URL per public node. | Static (GH Pages, regenerated on catalog export) |
| **`/catalog/goals/<slug>`** | SSG per goal | Goal page. Description, associated branches, leaderboard. | Static (GH Pages) |
| **`/catalog/branches/<slug>`** | SSG per branch | Branch page. BranchDefinition, node graph viz, recent runs, run-it CTA. | Static (GH Pages) |
| **`/catalog/search?q=…&domain=…`** | SSR | Search results. Calls `discover_nodes` RPC; shows ranked candidates with scores. | Dynamic (Fly.io) |
| **`/connect`** | SSG | Tier-1 onboarding. One-line copy-paste `tinyassets.io/mcp` as MCP URL. GitHub OAuth sign-in widget. 60-sec timer showing "first tool call success" metric. | Static (GH Pages) |
| **`/host`** | SSR | Tier-2 onboarding. OS-detect → correct installer (Win `.exe` / macOS `.dmg` / Linux `.deb`+`.AppImage`). Earnings preview. | Dynamic (Fly.io) |
| **`/contribute`** | SSG | Tier-3 onboarding. Clone link, CONTRIBUTING.md preview, CLA/DCO pointer, active-PR list via GitHub API client-side. | Static |
| **`/status`** | SSR + Realtime | Live platform status. Host count, inbox depth, catalog freshness, last-batch timestamp. Uses Supabase Realtime subscriptions. | Dynamic |
| **`/auth/*`** | Dynamic | OAuth callback routes for Supabase Auth. | Dynamic |
| **`/editor/*`** | Dynamic (auth-gated) | In-browser node/goal/branch editor. Presence + CAS from §14.3. | Dynamic |
| **`/earnings`** | Dynamic (auth-gated, T2+) | Tier-2 earnings + payout dashboard. Mirrors tray's earnings panel for non-tray users. | Dynamic |
| **`/admin`** | Dynamic (role-gated) | Host/tier-3 moderation triage queue. Report handling, bot-token rotation UI. | Dynamic |
| **`/account`** | Dynamic (auth-gated) | Signup landing, session status, "my exports" list (per-user data inventory), **delete account** action (full wipe + 30-day grace). Required for regulatory posture + trust. | Dynamic |
| **`/legal`** | SSG | ToS + privacy policy + license info (CC0-1.0 content, MIT platform per host Q7). Versioned: each legal-update commits a new subpath `/legal/v<N>` + redirects from `/legal/`. | Static (GH Pages) |

16 surfaces total. 8 SSG + 8 dynamic. Static ones regenerate on catalog-export commit (hourly diff-batched per #32) or on `TinyAssets/` repo merge (landing + legal).

---

## 3. Static vs dynamic split

### 3.1 Static surface (deploys to GitHub Pages — or GoDaddy shared via cPanel SFTP)

- Pages: `/`, `/catalog/`, `/catalog/nodes/<slug>`, `/catalog/goals/<slug>`, `/catalog/branches/<slug>`, `/connect`, `/contribute`, `/legal`.
- **Build source:** SvelteKit `adapter-static` consumes the `TinyAssets-catalog/` repo at build-time (per #32: that repo is the canonical public-content source). Generates per-artifact pages.

**Static-host pick: GitHub Pages (primary), GoDaddy-cPanel (fallback).** Comparison:

| Criterion | GitHub Pages | GoDaddy shared hosting (cPanel SFTP) |
|---|---|---|
| Cost | Free | ~$0 marginal (host already pays) |
| Deploy friction | `peaceiris/actions-gh-pages` is one-liner | GH Action `samkirkland/ftp-deploy-action` + cPanel SFTP creds as secrets |
| Custom domain (`tinyassets.io`) | CNAME + `CNAME` file in repo; Pages sets TLS cert; Cloudflare fronts | Native at cPanel; Cloudflare fronts |
| Cloudflare compat | Full (strict) TLS verified in uptime note §3.5.3 | Same |
| Build-to-live latency | ~60-90s (Action + Pages deploy) | ~20-30s (SFTP copy) |
| Fail behavior if origin down | Pages 404 bubbles through | cPanel 5xx bubbles through |
| Host lock-in | None (repo mirrors content) | GoDaddy vendor dependency |
| Recommended | **Yes** — cleanest OSS pathway + auditable deploys | Fallback if GH Pages has an outage or Pages policy changes |

Go with **GitHub Pages as primary**. Run the cPanel-SFTP path as a parallel Action that fires AFTER successful Pages deploy — gives us a warm fallback that Cloudflare can re-point to in <1 minute via a DNS swap if Pages breaks.

- **Deploy path:** GitHub Action on `TinyAssets-catalog/` merge → `npm run build` → push `build/` to `gh-pages` branch → GitHub Pages serves `tinyassets.io/*`. Cloudflare fronts with 5-min edge TTL + `stale-while-revalidate: 24h` per uptime §3.5.4. Parallel SFTP mirror to GoDaddy for fast fallback.
- **Cache-bust:** GitHub Action calls Cloudflare Cache Purge API for `/catalog/*` after deploy (scoped API token as secret).
- **SEO:** per-artifact pages emit `<link rel="canonical">`, OG tags, JSON-LD `CreativeWork` structured data. `sitemap.xml` regenerated on each build.

### 3.2 Dynamic surface (runs on Fly.io alongside gateway)

- Pages: `/catalog/search`, `/host`, `/status`, `/auth/*`, `/editor/*`, `/earnings`, `/admin`.
- **Runtime:** SvelteKit `adapter-node` → Fly.io Machine. Same min=2 autoscale config as gateway (#27 §6). Shares the same region fleet.
- **Auth:** Bearer-token middleware identical to gateway. Reuses the JWT claims + RLS-context pattern (#27 §2).
- **Supabase bindings:** `@supabase/ssr` handles cookie-based session for browser users; same JWT for API calls to RPCs.

### 3.3 Why split this way

- **Catalog reads dominate traffic at 100:1+ vs writes.** Static-with-5min-TTL at Cloudflare edge = ~free, infinite scale. Dynamic rendering of catalog pages at 10k DAU would force hot-caching mid-stack.
- **Search needs live data.** Pre-rendering 50k+ possible query permutations is wasteful; SSR + pgvector HNSW query at request time is fast (~150ms p95 per #25 §3.1).
- **Editor + admin need auth + RLS.** Static can't enforce. Dynamic with `set_config('request.jwt.claims', ...)` inherits the same security model the gateway uses.

---

## 4. Catalog browser UX (via `discover_nodes`)

### 4.1 Catalog home (`/catalog/`)

Build-time content:
- Top 20 nodes by `nodes_hot` materialized view (from #25 §5).
- Top 5 goals by upvotes.
- Top 5 branches by run count.
- Links to `/catalog/domains/<domain>` index pages.

Client-side enhancement (hydration):
- Subscribe to Supabase Realtime channel `catalog:updates` for live "new node added" ticker.
- "Refresh rankings" button re-queries `discover_nodes` with empty intent → server reranks + returns fresh top-N.

### 4.2 Node page (`/catalog/nodes/<slug>`)

Build-time: full public-concept blob rendered from the exported YAML. Provenance chain (parents → this node → children) as a mini-graph. Quality signals panel (usage_count, success_rate, upvotes, forks). License badge (CC0-1.0 per host's Q7 answer).

Client-side: "Remix" button → auth flow → chatbot-init link (`claude.ai/new?q=remix+<node_id>`). "Upvote" button → authed write to `node_activity` via `discover_nodes`-adjacent RPC `upvote_node(node_id)`. Presence indicator if others are currently editing (from §14.5).

### 4.3 Search (`/catalog/search`)

URL: `/catalog/search?q=<intent>&domain=<hint>&cross_domain=true&limit=20`.

SSR:
1. Extract params.
2. Pre-compute embedding via Edge Function (per #25 §3.1 OPEN Q5: caller pre-computes).
3. Call `discover_nodes(p_intent, p_domain_hint, ...)` as anonymous (RLS gives public-concept-only).
4. Render ranked candidates with all §15.1 signal badges (semantic_score, structural_score, quality panel, cross_domain flag).
5. Cache-Control: `public, max-age=60, stale-while-revalidate=300`. Query-result freshness is forgiving; duplicate queries coalesce at the edge.

Client-side: filter chips for domain, status, deprecated-or-not. Each click triggers a new SSR navigation.

### 4.4 Editor (`/editor/nodes/<id>`)

Auth-gated. Runs the full wiki-open collab stack from §16.2:
- Optimistic CAS on save via `update_node(id, concept, version)` RPC.
- Supabase Presence channel `editing:<node_id>` for "Alice is editing" indicator.
- Append-only comments via `post_comment(node_id, text)` RPC.
- Per-piece visibility UI: chatbot-judged defaults + explicit override per field (§17.2 `artifact_field_visibility`).

---

## 5. Auth flow

### 5.1 Per-tier auth requirement

| Surface | Auth required? | Who |
|---|---|---|
| `/` landing | No | Anonymous |
| `/catalog/*` reads | No (RLS returns public-concept-only for anonymous) | Anonymous |
| `/catalog/search` | No | Anonymous |
| `/connect` (tier-1 onboarding) | No initially — signup-flow itself | — |
| `/host` (tier-2 onboarding) | No to read, yes to download installer (to track which user → which host_pool row) | — |
| `/contribute` (tier-3 info) | No | Anonymous |
| `/editor/*` | Yes (GitHub OAuth) | T1+ |
| `/earnings` | Yes + trust_tier ≥ t2 | T2+ |
| `/admin` | Yes + role=moderator or host | T3+/host |
| `/status` | No (live public data) | Anonymous |

### 5.2 GitHub OAuth flow

Reuses the same Supabase Auth pattern the gateway uses (#27 §5.1). Web-app-side difference: cookie-based session (via `@supabase/ssr`) instead of pure bearer. Cookie carries refresh-token; SSR routes exchange for short-lived access token per request.

Flow:
1. User clicks "Sign in with GitHub" on `/connect` or `/editor`.
2. Browser redirects to `mcp.tinyassets.io/auth/github` → Supabase Auth redirects to GitHub.
3. GitHub callback returns to `mcp.tinyassets.io/auth/callback` → Supabase issues session.
4. Web app reads session cookie; populates `Authorization: Bearer <jwt>` on XHRs.

### 5.3 Tier-1 lightweight path

Tier-1 users can add the MCP URL to Claude.ai without a web-app signin. The signin flow happens during the FIRST MCP tool call via the gateway's OAuth 2.1 + PKCE. Web-app signin is for when a tier-1 user wants to visit `/editor` directly — a minority path.

`/connect` page sequence:
1. **Primary CTA**: "Copy this URL" → `tinyassets.io/mcp`.
2. **Secondary**: "Sign in with GitHub" → optional; unlocks `/editor` and richer in-browser features.

Measured metric on landing: % of visitors who reach step 1's copy-to-clipboard. Target ≥40% at viral-traffic launch.

---

## 6. Real-time widgets on `/status`

Live numbers via Supabase Realtime subscriptions. Ship four widgets at MVP:

1. **Host count online** — subscribes to Presence state on `host_pool:online` channel (#30 §3.1). Aggregated count (not per-user list). Updates within 90s TTL.
2. **Inbox depth** — subscribes to `request_inbox` CDC filtered `state='pending'`. Shows queue-length delta in real time. Lets tier-2 daemon-hosts see how much pending work is out there.
3. **Catalog freshness** — reads `status.json` from the `TinyAssets-catalog/` repo (via GH raw URL, Cloudflare-cached 30s). Renders "last sync: N min ago" badge. Links to the last batch commit.
4. **Recent activity ticker** — subscribes to `node_activity` CDC + filters for `event_kind IN ('created', 'remixed', 'converged', 'run_succeeded')`. Client-side rate-limit (max 1 entry/sec) to prevent UI thrash at busy times.

All four degrade gracefully on Realtime outage — show cached last-known values with "Live updates paused — check back in a moment" banner. Web app remains fully usable.

### 6.1 `/status` also shows

Static/dynamic split visible to user:
- Gateway status (up/degraded/down) via `tinyassets.io/mcp/health` check.
- Catalog export status (last batch committed N min ago).
- Realtime status (connected/reconnecting).
- Postgres status (indirect: if RPCs work, it's up).

Transparent degradation. Page never returns 503; always renders something informative.

---

## 7. SEO for viral discovery

### 7.1 Canonical URL pattern

One node → one canonical URL → one permanent page. Enables search engines to index + link back. URL slug is `/catalog/nodes/<domain>--<slug>` — stable across edits (slug derived from initial node name, locked at creation).

### 7.2 Structured data

Per `/catalog/nodes/<slug>`:
```html
<link rel="canonical" href="https://tinyassets.io/catalog/nodes/<slug>">
<meta property="og:title" content="<node.name> — Workflow">
<meta property="og:description" content="<first 150 chars of concept.purpose>">
<meta property="og:image" content="https://tinyassets.io/og/nodes/<slug>.png">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "CreativeWork",
  "name": "<node.name>",
  "creator": {"@type": "Person", "name": "<author github_handle>"},
  "license": "https://creativecommons.org/publicdomain/zero/1.0/",
  "dateCreated": "<node.created_at>",
  "dateModified": "<node.last_edited_at>",
  "keywords": "<node.tags joined>"
}
</script>
```

OG images generated at build time via a Node script (lightweight: node name + domain over a branded background). Caches to `/og/*` as flat PNGs; served statically.

### 7.3 Sitemap

`/sitemap.xml` regenerated at each build. Includes:
- Landing + onboarding routes (low priority).
- Every public node (medium priority, last-mod from `nodes.last_edited_at`).
- Every public goal + branch (medium priority).

Ping Google + Bing sitemap endpoints from the GH Action after deploy — standard webmaster flow. Ignored by robots.txt: `/auth/*`, `/editor/*`, `/admin/*`, `/status`.

### 7.4 Robots.txt

```
User-agent: *
Allow: /
Allow: /catalog/
Disallow: /auth/
Disallow: /editor/
Disallow: /admin/
Disallow: /earnings

Sitemap: https://tinyassets.io/sitemap.xml
```

### 7.5 What we don't do

- No paywalled content (CC0 license = everything public-spidered). No "members-only" gating on SEO-relevant pages.
- No heavy JS on landing — defer non-critical bundles. Target LCP ≤ 2.5s on 3G per Core Web Vitals.
- No dark patterns. "Sign in with GitHub" is opt-in; browse works forever without an account.

### 7.6 Internationalization posture

**English-only at launch, scaffold-ready for i18n post-launch.** SvelteKit's `$app/paths` + `svelte-i18n` (or Inlang) wire in with zero URL impact if we reserve a `[lang]` route prefix from day one. Phase-in plan:

- Day-one launch: all URLs un-prefixed (`tinyassets.io/catalog/`). Internally, content strings live in `src/lib/i18n/en.json`.
- Future: add `[lang]/` prefix. `en` continues at un-prefixed URL (SEO preserved). Other langs land at `/es/catalog/` etc. Canonical tags maintain one-URL-per-language-per-content-item.
- Scaffold cost: ~0.15 d day-one. Retrofit cost without scaffold: ~1+ d.

Catalog content (node names, descriptions, concept text) stays in the source language the creator authored. Translations are a future "translate this workflow" feature — not an MVP concern.

---

## 8. `/account` specifics

Auth-gated at `/account`. Single-page dashboard covering:

1. **Session status** — signed-in-as, GitHub handle, account_age_days, trust_tier.
2. **My exports** — list of the user's public nodes/goals/branches currently in the `TinyAssets-catalog/` repo. Links to the canonical URLs. Indicates "last exported: N min ago" per artifact (reads `status.json` from the catalog repo).
3. **Delete account** — the regulatory + trust posture surface. UX:
   - Button reveals a confirm dialog listing everything that gets deleted (private nodes, wallets, session, activity log attribution) vs preserved (public concepts per CC0 license — cannot be unilaterally deleted from the commons, per license memory; public-attribution gets anonymized rather than removed).
   - Confirm requires typing the user's GitHub handle as anti-accident gate.
   - On confirm: `delete_account` RPC enters a 30-day grace window (`users.deleted_at = now()`). Session logged out immediately. Full purge fires after 30 days via pg_cron.
   - Grace window is reversible — user can re-sign-in within 30 days and cancel the delete. Post-30d, only a support ticket can restore (and only metadata; content is gone).
4. **Export my data** — GDPR-adjacent. Button triggers a background job that produces a ZIP of everything the user owns (private nodes, activity log, ledger entries, wallet history) + ships it to their email. Takes ~10 min at typical volume.

Trust + legal posture: `/account` is the page regulators + privacy-conscious users expect. Not optional for a platform that handles user data. Reference: CCPA, GDPR Article 17 (right to erasure).

---

## 9. Honest dev-day estimate

Navigator's §10 estimate: **4 dev-days** for track B.

My build-out:

| Work item | Estimate |
|---|---|
| SvelteKit project scaffold + adapter-static + adapter-node dual setup | 0.3 d |
| Landing page `/` + 3-CTA flow + OG meta + hero assets | 0.35 d |
| `/catalog/` home — pulls from `TinyAssets-catalog/` repo at build time; top-N MV consumer | 0.4 d |
| Per-artifact SSG: `/catalog/nodes/<slug>`, `/catalog/goals/<slug>`, `/catalog/branches/<slug>` | 0.5 d |
| `/catalog/search` SSR — embedding precompute + `discover_nodes` call + results UI | 0.5 d |
| `/connect` tier-1 onboarding + copy-to-clipboard widget + optional GitHub OAuth | 0.3 d |
| `/host` tier-2 onboarding — OS-detect + installer download links + earnings preview | 0.3 d |
| `/contribute` tier-3 onboarding + GitHub API client-side PR list | 0.2 d |
| `/status` real-time widgets (4× Realtime subscriptions) + degradation UI | 0.5 d |
| `/editor/*` auth-gated editor — optimistic CAS + Presence + per-piece visibility UI | 1.0 d |
| `/earnings` dashboard — reads `daemon_earnings` view, payout button | 0.3 d |
| `/admin` moderation triage UI — report queue + action buttons | 0.5 d |
| `/account` — session status + my-exports + delete-account + data-export | 0.4 d |
| `/legal` — ToS + privacy + license page with version subpaths | 0.15 d |
| i18n scaffold — `[lang]` route reserved + `svelte-i18n` setup + `en.json` content split | 0.15 d |
| GoDaddy-cPanel parallel SFTP mirror (fast-fallback deploy path) | 0.2 d |
| GitHub OAuth + `@supabase/ssr` session cookie plumbing | 0.4 d |
| SEO: canonical URLs, OG images build script, JSON-LD, sitemap.xml, robots.txt | 0.4 d |
| GH Action: catalog-export-triggered rebuild + GH-Pages-deploy + Cloudflare-purge hook | 0.35 d |
| Fly.io deploy config (dynamic routes) — alongside gateway config | 0.2 d |
| Accessibility pass — keyboard navigation, semantic HTML, color-contrast, ARIA where needed | 0.3 d |
| Integration smoke — full 3-tier onboarding path tested end-to-end | 0.4 d |
| Docs — contributor runbook for building locally, deploy runbook | 0.2 d |
| **Total** | **~8.3 d** |

**Revision: 4 d → ~8.3 d.** Navigator's 4d is materially under-scoped — same pattern as #26/#29/#30/#32. The /account + /legal + i18n-scaffold + GoDaddy-fallback additions added ~0.9 d over my initial 7.4 d estimate. Both are load-bearing for trust (GDPR) + operational robustness, not cosmetic.

Biggest single under-count: **`/editor/*` (~1 d)**. The CAS + Presence + per-piece-visibility editor is the wiki-open collab surface from §16.2 — not a weekend project. Per-piece-visibility UI alone is novel (chatbot-suggested + explicit override per field).

Second-biggest: the dual-adapter SvelteKit setup itself adds integration overhead (~0.3 d sunk before any pages ship).

**Defer paths** to hit closer to navigator's 4d:
- **Ship without `/editor/*` at launch** = saves ~1 d. Users edit via Claude.ai chat (which is the dominant surface anyway). Editor becomes fast-follow. Risk: tier-1 users without Claude.ai access have nowhere to edit — mitigated because the MCP connector IS the primary edit surface per §16.2.
- **Ship without `/admin`** = saves ~0.5 d. Use direct Supabase dashboard for moderation at launch (host-only). Add web UI when moderation volume warrants.
- **Ship without `/earnings`** = saves ~0.3 d. Tier-2 earnings visible via tray dashboard only. Web dashboard fast-follow.
- **Skip OG image generation** = saves ~0.15 d. Use default OG image for all node pages. Loses some viral-share polish.

**Recommend ship ~7d with `/earnings` + OG-images deferred.** Both are fast-follows. Ship the editor day one — without it the "wiki-open collab" claim has a hole for non-Claude-users.

**Session revision tally:** 7 honest dev-day estimates now total **+15d over navigator's §10 estimates** (25:+0, 26:+2, 27:+1, 29:+3, 30:+2.5, 32:+3, 34:+3.5). §10's "8.5–10.5 dev-days with 2 devs" → **~23–26 dev-days with 2 devs** at full scope. Still weeks, not months, but at the high end. Defer-path totals per spec give the host levers to pull back toward 13–15d with 2 devs.

---

## 9. OPEN flags

| # | Question |
|---|---|
| Q1 | SvelteKit adapter-static vs Cloudflare Pages native — Cloudflare Pages auto-builds SvelteKit projects; zero-config deploy path. Host prefer GitHub Pages (uptime note §3.5.3) vs Pages (simpler ops)? |
| Q2 | OG image generation — satori (HTML→PNG Node lib) vs Resvg (Rust-bindings) vs pre-rendered Figma templates + string-replace? Recommend satori for v1. |
| Q3 | `/editor` file-paste import — tier-1 users dragging a node YAML into the editor — in or out of scope? Parallels the tray's `add_canon_from_path` for web. Recommend in scope; adds ~0.2 d. |
| Q4 | Real-time presence payload — include user's GitHub avatar via Realtime Presence metadata, or fetch separately? Presence metadata adds transit cost per pub/sub. Recommend fetch separately + cache in memory. |
| Q5 | Moderation triage UI at `/admin` — does it include arbitrary SQL-style filter, or fixed queues? Recommend fixed queues (reports by severity × age); arbitrary queries via Supabase dashboard. |
| Q6 | Accessibility target — WCAG 2.1 AA fully, or practical partial-compliance at launch with AA promised at v1.1? Legal-friendly answer is full AA; resource-friendly is partial with plan. |
| Q7 | Analytics — Plausible (OSS, privacy-friendly, ~$9/mo self-host or $9/mo hosted), Fathom, or none at launch? Recommend Plausible self-host on same Fly fleet. |
| Q8 | Error-tracking — Sentry SaaS (~$26/mo) or self-host? Recommend SaaS at launch, migrate if volume forces it (mirrors tray decision #30 Q5). |
| Q9 | Internationalization — English only at launch, or scaffold i18n from day one? Recommend scaffold i18n but ship en only; retrofitting to multi-lingual is expensive. ~0.15 d to scaffold. |
| Q10 | `/editor` WebSocket fallback — presence uses Realtime; if user's network blocks WS, fall back to polling? Recommend yes; Realtime already supports long-poll fallback. |

---

## 10. Acceptance criteria

Track B is done when:

1. `tinyassets.io/` serves the landing page with 3-CTA flow, LCP ≤ 2.5s on mobile 3G (Core Web Vitals), renders without JS for basic-browser fallback.
2. `/catalog/` shows top-20 nodes with quality badges; per-node canonical URLs resolve and render public-concept-only.
3. `/catalog/search?q=...` returns `discover_nodes` results within p95 ≤ 500ms (including embedding compute).
4. `/connect` → user copies MCP URL → adds to Claude.ai → first tool call lands within 60 seconds. (Measured via time-to-first-successful-tool-call metric.)
5. `/host` → OS-detect → correct installer downloads; tray first-run completes registration visible in `host_pool`.
6. `/contribute` → clone instructions visible; live PR list renders from GitHub API.
7. `/status` → 4 live widgets (host count, inbox depth, catalog freshness, activity ticker) update in real time; degrade to cached state on Realtime outage.
8. `/editor/nodes/<id>` → authed user can edit; CAS conflict surfaces merge-prompt; per-piece visibility toggles work.
9. Load-test S8 mixed-workload (per #26) exercises `/catalog/search` + `/status` + gateway together; all ship-gate thresholds green.
10. SEO: Lighthouse SEO score ≥ 95 on landing + per-node pages; sitemap submitted to Google + Bing.
11. All 10 OPEN flags in §9 resolved or explicitly deferred.

If any of the above fails, track B is not shippable; tier-1 user acquisition + tier-2 daemon-host discovery + tier-3 OSS funnel all break without it.
