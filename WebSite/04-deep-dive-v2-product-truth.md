# Deep-Dive v2 — Product Truth (what the site must reflect)

Building on `02-deep-dive-findings.md`. This pass covers the product north star, architecture, MVP scope, self-evolving loop, and packaging story. Everything below shapes the website narrative.

## North star (host directive 2026-04-18, Q21)

> **"This is a real world effect engine."**

For people getting real work done — jobs, projects, real artifacts. Success measured in real-world outcomes (books published, papers peer-reviewed, tasks completed, projects shipped) — **not** engagement, DAU, or session time. **Fail state: if it feels gimmicky or toy, it's failing.** Every design decision is evaluated against *"does this help a user finish real work, or does it make the platform feel more like a toy?"*

→ **Site implication:** Lead with proof of real work. Avoid superlatives, mysticism-as-costume, gimmicky animation. The "summoning" vocab is permitted (knowing-occult, not costume-occult) but the substance is utility.

## Four acceptance scenarios (everything ships against these)

| | Scenario | What it proves |
|---|---|---|
| **A** | `TinyAssets: payables` → CSV into Voyager + named PDFs | Invocation + attachment I/O + connector push |
| **B** | Vibe-code a max-super-nerd node via chatbot | Authoring surface, primitive-level access |
| **C1** | Told chatbot about job → autonomous scope-extension to company-wide distribution | Chatbot scope-extension + connector push to org tools |
| **C4** | Book → top-10 fan-out → overnight → 10 alternative next-books | Parallel fan-out, top-N ranking, self-hosted-zero-fee execution |

→ **Site implication:** The landing's "How it works" or "Examples" section should walk through 3-4 of these as concrete vignettes (pulling from the en.json `examples` array — Accounting, Research, Writing, Cooking, Legal, Code, Journalism, Email).

## Architecture (canonical, integrated into PLAN.md)

Single multi-user collaborative backend at `tinyassets.io`:

```
Users (Claude.ai, web app, future mobile MCP clients)
   │ HTTPS + WebSockets
   ▼
tinyassets.io
   ├─ MCP gateway (FastMCP) at /mcp
   ├─ Web REST (FastAPI)
   ├─ WebSocket subscriptions (Supabase Realtime)
   └─ Postgres + RLS + S3 storage
        ├─ catalog (Goals, Branches, Nodes)
        ├─ comments
        ├─ presence
        ├─ host pool registry
        ├─ requests (inbox)
        ├─ bids
        ├─ ledger
        └─ uploads metadata
   │
   ├─→ Daemon hosts (opt-in) — tray app, LangGraph runtime, polls bids
   └─→ GitHub (export sink only — TinyAssets-catalog/ repo)
```

→ **Site implication:** the site is the front door for the whole control plane. Not a brochure. `/catalog`, `/connect`, `/host`, `/contribute`, `/status`, `/editor`, `/earnings`, `/admin`, `/account` are all real surfaces with real backend bindings. Phase 1 ships landing-only chrome, Phase 2+ wires up surfaces against the backend as it lights up.

## Three user tiers (key navigation framing)

| Tier | Who | Install cost | Surface |
|---|---|---|---|
| **T1 Chatbot user** | Anyone with Claude.ai | Zero — paste `tinyassets.io/mcp` URL | Claude.ai chat + web app |
| **T2 Daemon host** | T1 + wants to run daemons | One-click MCPB / installer | Tray + web + Claude.ai |
| **T3 OSS contributor** | Wants to extend | `git clone` + Python toolchain | Local + GitHub PR |

Tiers are migration paths, not silos. Same GitHub OAuth identity across all three. T1 → T2 promotes by clicking "Host a daemon" + downloading the tray. T2 → T3 by cloning the repo. State preserved across promotions.

→ **Site implication:** the 3-CTA hero (Connect / Host / Contribute) maps 1:1 to T1/T2/T3. Landing copy should make the migration path explicit ("Start in your chatbot. Upgrade to host whenever you want. Contribute when you're ready.").

## MVP scope (~21-24 dev-days, ~5-6 weeks)

Tracks ship as a single push (no phased rollout — that was rejected). Letter codes from `2026-04-19-minimum-viable-launch-narrowing.md`:

| Track | Dev-days | What ships at MVP |
|---|---|---|
| **A** Schema + Auth | 2 | Full schema; GitHub OAuth |
| **B** Web app | 2.5 | Landing + connect + host + contribute + catalog browse (read-only). Defer: editor, presence, Realtime widgets |
| **C** MCP gateway | 2 | All launch tools + `/feedback`, `/node_authoring.show_code`, `submit_request`, `discover_nodes` |
| **D** Tray | 1.5 | Install + host_pool + visibility=self. Defer: network/paid visibility polish, earnings dashboard |
| **E** Paid market | 0.5 | Bid + claim + settle ledger off-chain. Defer wallet to v1.1 |
| **F** Moderation | 0.75 | Flag + triage queue + rate limits + user-sim mod council |
| **G** GitHub export | 0.5 | One-way Postgres → catalog YAML hourly. Defer PR-ingest |
| **H** Cloudflare/DNS | 0.5 (host) | Required for launch |
| **I** Content + voice | 0.5 | Landing copy, "summon the daemon" voice |
| **J** Load test | 2 | S1-S5. Skip S6 cold-start, S7 auto-heal rehearsal, S11 fan-out |
| **K** Discovery + remix | 1 | pgvector HNSW + `discover_nodes` + `remix_node` |
| **L** Dual-layer privacy | 1 | concept/instance split + per-piece visibility (non-negotiable) |
| **M** Monetization + license | 0.5 | 4-path `submit_request` + CC0 default. Defer Base wallet to v1.1 |
| **N** Vibe-coding sandbox | 2 | T1 + T2-lite editing |
| **Connectors** | 1 | GitHub + Gmail + S3 + generic-webhook |
| **Handoffs** | 0.75 | arXiv + CrossRef DOI + GitHub Releases |

→ **Site implication:** the website (Track B) is one of 16 tracks. Landing-first is the right Phase 1 (matches the §10 dev-day estimate). Don't pretend the site is the product — it's the front door.

## Self-evolving loop (the unique-to-TinyAssets story)

```
user chatbot
    ↓
wiki: patch_request (generalized file_bug)
    ↓
daemon market: claim + patch_bounty
    ↓
patch_request_to_patch_notes branch
    ↓ Private Gate Series #1 (testing tiers, ACCEPT/route_back/REJECT)
    ↓ (accept)
coding team branch — user project, not platform
    ↓ GitHub PR (opt-in via patch_request label)
    ↓ Private Gate Series #2 (full execution + watch-window)
    ↓ (accept)
ship + future-proof watch (24h-7d)
    ↓
bisect-on-canary + atomic surgical rollback if regression
    ↑ back to top of loop if rollback triggered
```

**Lead/host endgame:** true emergencies + meta-evolution only. Auto-heal + community evolution drive the loop.

→ **Site implication:** this is genuinely novel. A "How it heals itself" or "How the platform evolves" section makes the TinyAssets product concretely different from any static MCP server. It's also evidence behind the "real world effect engine" framing.

## Project principles (load-bearing — these constrain product copy)

1. **community-build-over-platform-build** — favor chatbot composition over new platform primitives. Site should not promise platform features that should be community patterns.
2. **minimal-primitives** — extend existing primitives over adding new ones.
3. **privacy-via-community-composition** — privacy is a chatbot judgment per request, not a platform setting.
4. **commons-first-architecture** — public concept layer is the canon; instance layer stays with the user; never training data.
5. **user-capability-axis** — capabilities are tier-mapped (T1/T2/T3), not feature-mapped.

→ **Site implication:** every claim on the site has to honor the "we don't ship things the community can compose" principle. No bullet points like "with TinyAssets you can…" — instead "you and your chatbot can compose…".

## Packaging / distribution story

| Surface | Audience | Status |
|---|---|---|
| **`tinyassets.io/mcp` URL** (paste into Claude.ai connectors) | T1 zero-install | **Live** |
| **MCPB bundle** (one-click installer that registers as MCP server locally) | T1 alternative | `packaging/mcpb/` |
| **Claude plugin** (registers as marketplace-listed plugin in Claude.ai) | T1 polish | `packaging/claude-plugin/plugins/tinyassets-universe-server/` |
| **Tray app** (Windows .exe / macOS .dmg / Linux .deb + .AppImage) | T2 daemon hosts | `tinyassets_tray.py`; installers from `packaging/dist/` |
| **`pip install -e .[dev]`** (clone + Python toolchain) | T3 contributors | `pyproject.toml` |
| **Registry server.json** | discovery / Claude.ai | `packaging/registry/` |

→ **Site implication:** `/connect` page should show all three T1 paths (URL paste / MCPB / plugin) — not just the URL. `/host` should detect OS and offer the right tray installer. `/contribute` should give the clone command + link to CONTRIBUTING.md.

## Five contribution surfaces (the ledger that drives rewards)

Every contribution emits into a single `contribution_events` table. Five event types feed the future paid-market reward layer:

1. **`execute_step`** — daemon ran a step (1.0 flat)
2. **`design_used`** — someone's published artifact got referenced (0.3-1.0 by type)
3. **`code_committed`** — GitHub PR merged with `patch_request` label (sized + co-author split)
4. **lineage credit** — fork ancestry (decay `α^depth`, α=0.6, max_depth=12)
5. **`feedback_provided`** — gate evaluator cited an artifact (0.1 × decision strength)

Plus negative events: `caused_regression` (-10 P0 / -3 P1 / -1 P2) when post-merge canary detects regression and attribution chain identifies the artifact.

→ **Site implication:** /earnings page (Phase 2+) should show all five surfaces. The token / Tiny Assets economy strip on the landing should preview "you earn for any of these" — currently just says "daemons earn", which underplays the breadth.

## Active production / operational facts

- Live MCP at `tinyassets.io/mcp` since 2026-04-19 (Cloudflare Worker proxies to tunnel-internal `mcp.tinyassets.io` origin)
- **Forever rule (2026-04-18):** Complete-system 24/7 uptime is top priority. Every uptime surface treated as equal severity.
- 33 bugs filed via the wiki by chatbot users — real users at the live MCP today
- DR drills, secret rotation, uptime canaries, p0-outage triage all in `.github/workflows/`
- Active "concordance" universe running fantasy-novel daemon (proof of long-running multi-step workflow)

→ **Site implication:** `/status` is real and load-bearing. Even at Phase 1, link to it from the footer. "Live MCP at tinyassets.io/mcp · view status" is a quiet trust signal.

## What this changes vs my earlier shipping plan

| Earlier plan | Updated plan |
|---|---|
| Hero "Summon the daemon." (just the design system header) | Hero pulls "Summon the daemon." copy from `en.json.landing.hero_title`; subtitle is `hero_subtitle` (real work, real execution) |
| 3-CTA: Connect / Host / Contribute (generic) | 3-CTA labeled by tier: "Try in Claude.ai (zero-install)" / "Host a daemon (one-click)" / "Contribute to the OSS core" |
| Token strip mentions "earn" generically | Token strip names the 5 contribution event types; links to a future `/earnings` page |
| Contract address in footer pill | Same — but with brief "ledger settles to tinyassets.io economic layer" framing |
| TinyAssets showcase (parchment diagrams) | Pulled from `ui_kits/tinyassets-web/Diagrams.jsx` + `BranchDAG.jsx` (already exist) |
| /connect = single copy-URL widget | Three paths: URL / MCPB / Claude plugin (all in `connect.json`) |
| /legal = ToS placeholder | Same; nothing changes |
| Skipped self-evolving loop | Add a "How it evolves" section between hero and 3-CTA — this is the unique product story |
| Skipped 4 acceptance scenarios | Add "What you can do" examples grid pulled from `en.json.connect.examples` (8 worked scenarios across Accounting/Research/Writing/Cooking/Legal/Code/Journalism/Email) |

## What I haven't read yet (parking)

Things I deferred but might want next pass:
- PLAN.md (~50KB — read the §"Full-Platform Architecture (Canonical)" section if needed)
- AGENTS.md remainder (most of it — I only read first 100 lines)
- LAUNCH_PROMPT.md
- CONTRIBUTING.md
- The 80+ design notes (most about engine internals, not site-relevant)
- knowledge/INDEX.md
- packaging/PACKAGING_MAP.md (would inform /connect page exactly)
- The actual Landing.jsx + Diagrams.jsx + Economy.jsx code (I read Landing.jsx; the others would inform Phase 1.5 sections)
