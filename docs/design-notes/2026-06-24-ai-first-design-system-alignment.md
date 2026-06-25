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

## Sources

DTCG `2025.10` stable (w3.org/community/design-tokens); Style Dictionary v5 DTCG default
(styledictionary.com/info/dtcg); Storybook 10 SvelteKit (storybook.js.org/docs/get-started/frameworks/sveltekit);
Indeed JSON-metadata benchmark (intodesignsystems.substack.com); Figma "MCP is the unlock"
(figma.com/blog/design-systems-ai-mcp); Claude Design setup + handoff (support.claude.com
articles 14604397 / 14604416; anthropic.com/news/claude-design-anthropic-labs); `DESIGN.md`
convention (github.com/VoltAgent/awesome-claude-design).
