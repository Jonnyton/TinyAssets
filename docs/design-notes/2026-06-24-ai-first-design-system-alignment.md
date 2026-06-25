# AI-First Design System Alignment — Research + Staged Proposal

**Date:** 2026-06-24
**Status:** PROPOSAL (host-decision pending on framework fork; Stage 1 is non-blocking)
**Trigger:** `/design-sync` invoked against this repo; no design system found to sync. Host
direction: "take the current system and research and bring it into alignment with current and
future industry standards for an AI-first project, for all providers."

---

## TL;DR

- This repo has **no shippable design system** the way AI design tools expect one. What exists is a
  private **SvelteKit** marketing site (`WebSite/site/`, Svelte 5 + Vite) with a nascent component
  set: ~20 components incl. a `Primitives/` folder (Button, StatusPill, RitualLabel) and a
  `tokens.css`. The `/design-sync` skill's high-fidelity path wants a **compiled React/esbuild
  component bundle** — which we don't have.
- **Two research passes converge:** the provider-neutral, AI-consumable substrate is **design
  tokens + per-component JSON prop schemas + usage docs + MCP exposure** — *not* a framework-specific
  component bundle. Svelte is only disadvantaged at one narrow boundary: claude.ai/design's *compiled
  React component bundle* round-trip.
- **Recommendation (revised after framework-trajectory research — see below): build the design
  system / AI-facing component surface in React + Tailwind + shadcn.** For an *AI-first* project
  this is the decisive call — every AI codegen/design tool (v0, shadcn+MCP, AI Elements, Claude
  Design's compiled bundle, agent defaults) is React-shaped, and the training-data flywheel makes
  that gap widen, not close. Keep **design tokens framework-neutral**; keep the existing **SvelteKit
  marketing site as a human-owned surface** (no urgent rewrite). Building the DS in React also makes
  the original `/design-sync` work — the compiled React bundle is exactly what it ingests.

---

## What "AI-first design system" means in 2026 (ranked by leverage)

1. **Machine-readable token file** — W3C DTCG spec reached its **first stable version `2025.10`**
   (Oct 2025). Canonical interchange: `.tokens.json`, `$value`/`$type`/`$description`. Built with
   **Style Dictionary v5** (DTCG default export) → CSS custom properties + JS/JSON. Fully
   framework-neutral; zero provider risk. *This is the single highest-leverage, lowest-cost move.*
2. **Per-component JSON prop/variant schema** — benchmark evidence (Indeed, 1,056-prompt study)
   found JSON component metadata matched/beat Markdown for AI accuracy at ~80% fewer tokens. JSON is
   the *contract*; Markdown/JSDoc is the *usage-rules* layer, kept separate.
3. **Usage / prompt docs** — "when to use which variant" companion (`.prompt.md` / MDX / JSDoc).
4. **MCP exposure of the design system** — the defining 2026 move (Figma: "MCP servers are the
   unlock"; shadcn, SVAR ship MCP). Lets agents *query* the system instead of guessing.
   **Framework-neutral — Svelte competes fully here.** We already run an MCP server.
5. **Auto-regenerating pipeline** — metadata re-derived from source on every change so the AI-facing
   surface never drifts from real components.
6. **Compiled dist + `.d.ts` + Storybook** — the "real product UI" half; **Storybook 10 supports
   Svelte 5 / SvelteKit first-class** (`@storybook/sveltekit`, autodocs, a11y/interaction/visual
   tests). Svelte CSF authoring addon is community-maintained with a minor feature gap vs React.

## The one place Svelte is genuinely disadvantaged

claude.ai/design's `/design-sync` **high-fidelity component bundle** path wants a compiled
**React** library (`dist/` → global, `.d.ts`, `.prompt.md` per component). No Svelte or
web-component *component-bundle* ingestion is documented. **However** — Claude Design's *design-system
setup* (not the same as the compiled round-trip) ingests **tokens + component descriptions
(`DESIGN.md`-style), framework-agnostically**; React is an example input, never a requirement, and it
scaffolds generated code into *your* repo's stack. So:
- For **general AI-consumability across all providers** → tokens + JSON schema + MCP + `DESIGN.md`. Svelte is fine.
- For the **specific compiled claude.ai/design round-trip** → React (or a web-component) shim is the path of least resistance.

## Framework-direction verdict (the question that decides everything)

"Is the industry moving toward React, Svelte, or something else?" — answered on three axes:

- **Technical paradigm → signals + compiler, and Svelte 5 is already there.** Solid, Vue Vapor,
  Angular signals, Svelte 5 runes, and even a TC39 Signals proposal all converge; React is the
  mechanism outlier (React Compiler v1.0 auto-memoization over the VDOM instead of signals). So
  Svelte is **not** technically behind — a migration cannot be justified on technical grounds.
- **Raw gravity → React, decisively.** ~50M npm weekly + dominant jobs/installed base vs Svelte's
  ~1.8M (fast-growing +45% but tiny base). Svelte wins *love/satisfaction*; React owns *adoption*.
- **AI-first lens → React, and the gap compounds.** v0 only emits React+Tailwind+shadcn; shadcn's
  registry+MCP is the de-facto AI component-distribution format; AI Elements is React; agent defaults
  (Cursor/Copilot/Claude Code/Artifacts) skew React. Svelte exists in AI tooling only via community
  glue (`shadcn-svelte`, community MCP servers). **Web components are a false hedge** — runtime-neutral
  but near-zero AI codegen gravity. Cause is the **training-data flywheel**: bigger corpus → better AI
  output → more written → bigger corpus. React is on the right side of that loop; Svelte isn't.

**Verdict for an explicitly AI-first project where "all providers must build with our components":
the canonical component surface should be React.** Not because Svelte is worse, but because the AI
ecosystem this project is built around is React-shaped and self-reinforcing. The smart shape is
*hybrid, not binary*: React-canonical for the AI-facing design system, neutral tokens, Svelte fine
for human-owned surfaces.

## Strategy matrix

| Strategy | Effort | Keep | Serves "all AI providers" |
|---|---|---|---|
| **A. Token-only sharing** (Style Dictionary → CSS+JS/JSON) + DESIGN.md + Storybook + MCP schema | **S–M** (days) | Everything Svelte | **Best** — universal substrate every AI tool/framework reads |
| **B. Keep Svelte canonical, generate thin React/Web-Component shim of primitives** | **M** (1–3 wks) | Svelte canonical | Good — only if a provider needs runnable React |
| **C. Web components (Lit) as canonical** | **L** | Tokens, concepts | Strong long-term, weak ROI now |
| **D. Full Svelte → React migration** | **XL** | Tokens only | Overkill — abandons working product; portability does NOT require it |

**Revised recommendation (post-trajectory):** build a **new React + Tailwind + shadcn design-system
package** as the canonical AI-facing surface (matrix row ≈ B, but React-canonical rather than a
Svelte-canonical shim). Keep tokens neutral (A's token layer still applies). Keep the SvelteKit
marketing site as-is; migrate it to React only opportunistically, never as a blocking rewrite.

## Staged plan (React-canonical)

- **Stage 1 (days):** new `packages/design-system` — React + TypeScript + Tailwind + shadcn,
  esbuild bundle (the `/design-sync`-compatible `dist/` + `.d.ts`). DTCG `.tokens.json` →
  Style Dictionary v5 → CSS vars + Tailwind preset (shared by both React DS and the Svelte site).
  Port the Primitives (Button, StatusPill, RitualLabel) first.
- **Stage 2 (days):** Storybook 10 (React) over the ported components; per-component JSON prop
  schemas + `.prompt.md` usage docs; expose a `design-system` surface on our existing MCP server.
- **Stage 3 (then):** run `/design-sync` for real — the compiled React bundle now satisfies it —
  and decide site-migration cadence (Svelte site → React/Next is a separate, non-urgent track).

## Host-decision (now narrow)

The framework question is answered: **React-canonical for the AI-facing design system.** The only
remaining product call is **cadence**: build the React DS package now (recommended), and separately,
do we ever want the existing Svelte marketing site fully migrated to React, or does it stay Svelte
as a human-owned surface indefinitely?

## Build status (2026-06-24)

**Stage 1+2 DONE + verified + committed** (`WebSite/design-system/`, branch
`worktree-design-system-alignment`, commit 41904b1a):
- DTCG 2025.10 tokens generated from canonical CSS (123 tokens), exact var names preserved.
- React primitives ported faithfully: Button, StatusPill, RitualLabel.
- `dist/` builds: `index.js` (ESM) + `styles.css` (12.4kb) + `index.d.ts` + `manifest.json`.
- Storybook 10 (React+Vite) builds clean. DESIGN.md + per-component schema/prompt docs.
- Live Svelte site untouched; nothing deployed.

## Phase B — site migration DONE (2026-06-24)

All 23 routes migrated Svelte→React/Next; final integrated `next build` green
(28 static pages, types+lint clean). Commits: 05efea5a (shell+home), aedeb5af
(20 routes wave 1), eca44d9b (graph+loop). Executed via parallel fan-out:
2 Codex sessions + 2 dev agents, conventions in `WebSite/site-react/PORTING.md`.
- Shell + home + VitalSigns/Ladder/Tick/Term; 9 redirect stubs + account;
  legal/fine-print/build/alliance/soul/host/start/commons/goals/goals[id];
  graph (d3-force) + loop (patch-loop feed).

**Completion pass (2026-06-24, commits fc874694 / e8032e09 / e0a4d1a1):**
- TinyBot fully ported (replaces stub) — the floating assistant widget.
- Visual fidelity sweep via Playwright screenshots (home, soul, graph, goals,
  loop, fine-print, catalog-redirect, +): all render faithfully in the Field
  Notes language. **Caught + fixed a real bug** — the home `page.tsx` was a
  top-level `"use client"` page and 404'd on hydration under `output:export`;
  refactored to server-page + `HomeClient` (the pattern every other route uses).
  All `page.tsx` confirmed server components.
- Dedupe: N/A — the co-located `_components` are legitimate route-specific
  client wrappers, not duplicates of shared components.
- Cutover PREPARED (host-gated, not activated): `deploy-site-react.yml`
  (workflow_dispatch-only, `confirm:deploy` guard), `public/CNAME` + `.nojekyll`,
  and `docs/runbooks/2026-06-24-site-react-cutover.md`.

**Still host-gated / optional:**
- Run the cutover (swap GH Pages site/ → site-react/) — needs host approval +
  public-surface canary; live Svelte site untouched until then.
- goals/[id] static export prerenders only the 3 home-page ids (SPA-fallback for
  others, same as the original ssr=false page) — acceptable; documented.
- Optional: run the now-unblocked `/design-sync` to push `@tiny/design-system`
  to claude.ai/design (external publish — explicit action).

## Phase B — original site migration plan (superseded by DONE above)

Honest scope: **23 routes**, and they are NOT standalone. Inventory of shared
dependencies that must port first (each is real work):
- **Live MCP data layer** — `$lib/mcp/live.ts` (`fetchLive`/`fetchVitals`) + `$lib/fmt.ts`. Client-side fetch against `https://tinyassets.io/mcp`. → port to framework-neutral TS (no Svelte) — reusable as-is.
- **Shell** — `+layout.svelte`, `TopNav`, `Footer`, `TinyBot` (chat widget), `WorkflowMark` (SVG). Uses `$app/state` for active-route → Next `usePathname`.
- **Shared components** — VitalSigns, Ladder, Tick, Term, ChatDemo, Playground (MCP playground), ChapterFolio, LiveBadge, LiveSourceBar, MoodPill, TokenDisclaimer (~14 components).
- **Special-hard routes** — `graph` (d3-force whole-brain graph), `notebook`/`playground` (MCP playground), i18n (`$lib/i18n`), `goals/[id]` (dynamic).

Recommended execution:
1. **Scaffold** `WebSite/site-react/` — Next App Router, depends on `@tiny/design-system` (file:). Port the data layer (`live.ts`,`fmt.ts`) + shell first. Verify `next build`.
2. **Prove the slice** — port the home page (660 lines, ~6 deps) end-to-end; this de-risks the pattern.
3. **Fan out** the remaining 22 routes in batches via parallel `developer` subagents, each given the Svelte source + the established React/DS conventions, each verified to `next build`. Static-content routes (legal, fine-print, patterns, proof, soul, host, alliance, contribute, economy, commons, connect, build, start) are mostly mechanical. Data/interactive routes (graph, loop, status, goals, notebook, catalog, wiki) are the hard tail.
4. **Cutover** — only after the React site is visually verified against the live Svelte site, host approves; the GH Pages deploy target swaps. Never auto-deploy.

Effort estimate: shell+home ~half a session; the 22 routes are several sessions
of agent time (the d3 graph + MCP playground are the long poles). This is why
it is staged and host-resourced rather than claimed done in one pass.

## Sources

DTCG `2025.10` stable (w3.org/community/design-tokens); Style Dictionary v5 DTCG default
(styledictionary.com/info/dtcg); Storybook 10 SvelteKit (storybook.js.org/docs/get-started/frameworks/sveltekit);
Indeed JSON-metadata benchmark (intodesignsystems.substack.com); Figma "MCP is the unlock"
(figma.com/blog/design-systems-ai-mcp); Claude Design setup + handoff (support.claude.com
articles 14604397 / 14604416; anthropic.com/news/claude-design-anthropic-labs); `DESIGN.md`
convention (github.com/VoltAgent/awesome-claude-design).
