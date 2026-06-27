# Content Decisions Resolved + Final Component Map

After reading the UI kit (TopNav, Connect, Host, Contribute, Catalog, ChatDemo, Showcase, Economy, Primitives) plus LAUNCH_PROMPT and CONTRIBUTING.

## 4 of 5 content decisions — ANSWERED by source

| # | Decision | Source-confirmed answer |
|---|---|---|
| 1 | **Logo source** | `assets/logo-mark.svg` (sigil) + `assets/wordmark-horizontal.svg` (sigil + "TinyAssets" wordmark) — both already in `WebSite/design-source/assets/` |
| 2 | **GitHub repo URL** | `https://github.com/Jonnyton/TinyAssets` — confirmed via Contribute.jsx + design README |
| 3 | **Contact email** | `security@tinyassets.io` (per CONTRIBUTING.md — routes to admin pool / maintainers; doubles as security inbox) |
| 4 | **MCP target page** | Just the URL `https://tinyassets.io/mcp` — Connect page is intentionally radical-simplicity (paste URL, 2 steps, done) — NOT a docs page |
| 5 | **Contract address home** | **Still unknown.** Host must provide the existing `ta` token contract address. Economy.jsx confirms the rebrand carries balances 1:1 from the original tinyassets contract, but the actual address isn't in the codebase. → **Ask host for the contract address (and chain — Ethereum mainnet?)** |

## Updated nav (TopNav.jsx canonical)

The full design's nav is wider than the spec's:

```
Home · Connect · Catalog · Host · Contribute · Agent Teams · Novel · Coding · Economy
                                                                                       [Sign in] [Summon a daemon →]
```

Three vertical-showcase pages I missed earlier: **Agent Teams · Novel · Coding** — these are case-study landing pages, each pulling from a different worked example.

For Phase 1 a slimmer nav makes sense: **Home · Connect · Host · Contribute** + the two CTAs. Add Catalog / Economy / showcases when those pages light up.

## Component map — what's portable from JSX → Svelte

### Already read & ported-ready (Phase 1)
| JSX file | Svelte target | Phase | Notes |
|---|---|---|---|
| `Primitives.jsx` | `lib/components/Primitives/{Button,StatusPill,RitualLabel,SigilAvatar,DaemonTile}.svelte` | **1** | All small. Convert React inline-style + `onMouseEnter` → Svelte `style:` + `on:mouseenter`. |
| `SigilMark.jsx` | `lib/components/SigilMark.svelte` | **1** | Or just `<img src="/logo-mark.svg">` — both work. |
| `TopNav.jsx` | `routes/+layout.svelte` (replace placeholder) | **1** | Sticky-translucent + ember underline + 2 CTAs. |
| `Landing.jsx` | `routes/+page.svelte` (replace placeholder) | **1** | Big port — 8 sections + uses ChatDemo, BranchDAG, OutcomeGateLadder. Phase 1 ships at least Hero + 3-CTA + ThreeLayer (Goal/Branch/Daemon) + WhyTinyAssets + Footer. Defer AgentTeams + ProductInOneFrame + OutcomeGates + EconomyTease to Phase 1.5. |
| `Connect.jsx` | `routes/connect/+page.svelte` (replace placeholder) | **1** | Tiny — just the URL paste card + 2-step grid. |
| `ChatDemo.jsx` | `lib/components/ChatDemo.svelte` | **1** (in landing) | Faux Claude.ai transcript with user/thought/tool/assistant messages. Pure JSX → Svelte conversion. |

### Phase 1.5+
| JSX file | Svelte target | Phase | Notes |
|---|---|---|---|
| `Host.jsx` | `routes/host/+page.svelte` | 1.5 | Two-mode fork (Local-first download tray vs Hosted cloud) + dashboard preview. ~440 LOC. Needs OS-detect. |
| `Contribute.jsx` | `routes/contribute/+page.svelte` | 1.5 | Hero + 4-cmd quick start + threads-to-pick-up + repo card + 5-tier admin pool layout. ~440 LOC. |
| `Catalog.jsx` | `routes/catalog/+page.svelte` + `routes/catalog/[goal_id]/+page.svelte` | 2 | Goals list + drill-down to branch leaderboard. Needs real Postgres data; Phase 2 for sure. |
| `Diagrams.jsx`, `BranchDAG.jsx`, `Goal.jsx`, `Branch.jsx` | `lib/components/Diagrams/*.svelte` | 1.5+ | Diagram primitives: lifecycle, lifecycle-states, branch DAG, gate-ladder, lineage. Needed for both landing (cameo) and Catalog/Showcase pages. |
| `Showcase.jsx` | `routes/novel/+page.svelte` | 1.5 | "Write a sci-fi series. Actually ship it." 5-diagram walk-through. Vertical case study. |
| `AgentTeams.jsx` | `routes/teams/+page.svelte` | 1.5 | Phone-as-mission-control story. ~530 LOC. |
| `CodingDiagrams.jsx`, `CodingShowcase.jsx` | `routes/coding/+page.svelte` | 1.5 | Coding vertical case study. |
| `Economy.jsx` | `routes/economy/+page.svelte` | 1.5 | tinyassets refactor story. **Replaces / supersedes the legacy crypto-investor surface.** Needs actual contract address (decision #5 above). |
| `PhoneTeamCommand.jsx` | `lib/components/PhoneTeamCommand.svelte` | 1.5 | Used in Landing AgentTeams section + Teams page. |
| `tweaks-panel.jsx` | `lib/components/TweaksPanel.svelte` | 2+ | Toolbar (annotations on/off, lifecycle animation on/off) — used in interactive Showcase. Defer until interactive diagrams ship. |
| `node-detail.jsx` | `lib/components/NodeDetail.svelte` | 2+ | Right-side drawer when clicking nodes. Defer until interactive diagrams ship. |

### Don't port (read-only intel)
- `app.jsx` — top-level router for the design preview, not needed in Svelte
- `index.html` — design preview entry, replaced by SvelteKit's `app.html`
- `colors_and_type.css` — already copied target: `lib/styles/tokens.css`

## Three things that change the Phase 1 ship plan

1. **Add ChatDemo to landing's hero right column.** It's the "show don't tell" moment — a faux Claude.ai transcript proving the actual interaction pattern. The Landing.jsx hero is split 1fr/1fr with copy on the left, ChatDemo on the right. Without it, the hero feels marketing-thin.

2. **Three-Layer (Goal · Branch · Daemon) section is required vocabulary.** This trinity appears everywhere in the codebase — it's the platform's mental model. Landing absolutely needs the explainer cards.

3. **Two install paths for Host (local + cloud), not just downloads.** Host.jsx mode-fork (Local-first download vs Hosted cloud) means `/host` Phase 1.5 needs both surfaces, not just an OS-detect download button. And `~30 sec setup, browser dashboard, metered` for cloud is a real Phase 1.5 build commitment — flag it.

## Updated Phase 1 ship scope (final)

**Polish for ship:**
- `/` — Hero (copy + ChatDemo) + Three-Layer + Why TinyAssets + Token/Economy tease + Footer
- `/connect` — Connect.jsx ported as-is
- `/legal` — placeholder ToS + privacy + license

**Already in prototype (will inherit as-is for Phase 1, polish in 1.5):**
- `/catalog` — placeholder
- `/host` — placeholder
- `/contribute` — placeholder
- `/status` — server-rendered placeholder
- `/account` — server-rendered placeholder

**Components built for Phase 1:**
- `Button`, `StatusPill`, `RitualLabel`, `SigilAvatar` (Primitives)
- `SigilMark` (logo SVG, can be `<img>` or inline)
- `Nav` (TopNav port)
- `Hero` + `ChatDemo` + `ThreeLayer` + `WhyTinyAssets` + `TokenStrip` + `Footer` (landing sections)
- `ConnectURLCard` (the copy-URL card in Connect)

**Open content TODOs (host action):**
- Contract address for the `ta` token (with chain hint — Ethereum? Polygon? Base?)
- Confirmation: should `/economy` Phase 1.5 reuse the existing tinyassets economy paper if one exists, or write fresh?
- Confirmation that host has a public domain plan to point `tinyassets.io` to GitHub Pages or wherever else for Phase 1 deploy
