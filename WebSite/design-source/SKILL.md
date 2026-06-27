---
name: tinyassets-design
description: Use this skill to generate well-branded interfaces and assets for TinyAssets, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the `README.md` file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Key facts about TinyAssets

- **Product in one line:** an open-source platform where users design multi-step AI workflows inside their chatbot (Claude.ai, etc.) and a **daemon** actually runs them. Real execution, not simulation.
- **Brand voice:** nerdy, slightly mythic, self-aware. Load-bearing verbs: **summon, bind, entrust, dismiss, roam, return.** Never: "create," "configure," "unleash," or marketing puffery.
- **Visual DNA:** dark canvas (ink `#1a1a2e`), ivory mark stroke (`#f2eee6`), ember work route (`#e94560`), live green route (`#6dd3a6`). One hero graphic: the selected A2 rotated protocol-loom mark in `assets/logo-mark.png`. Fraunces display + IBM Plex Sans/Mono. No emoji. No icons without intentional substitution (we use Lucide via CDN — flagged).

## Files

- `README.md` — full design system: sources, content fundamentals, visual foundations, iconography, index.
- `colors_and_type.css` — all design tokens as CSS variables. **Always link this first.**
- `assets/logo-mark.png` — the brand mark; `assets/logo-mark.svg` is only a compatibility wrapper.
- `source_copy/en.json` — verbatim product copy for tone-accurate mocks.
- `preview/` — individual cards showing each token cluster (use as visual reference).
- `ui_kits/tinyassets-web/` — React/JSX recreation of the landing, connect, catalog, and host surfaces. Read components before writing new ones; reuse `Button`, `StatusPill`, `DaemonTile`, `SigilMark`, `RitualLabel`.

## TinyAssets for common tasks

**Making a marketing page or hero:**
1. Link `colors_and_type.css`.
2. Default to dark theme. Add `data-theme="light"` only for docs / legal.
3. Use Fraunces for display type; italicize + ember-color the single load-bearing word (like "*daemon.*").
4. Place the protocol-loom mark as a bottom-right watermark at 0.06 opacity when a hero feels empty.
5. Pull copy from `source_copy/en.json`. If you need new copy, re-read the verb kit in `README.md` and match.

**Making an app surface:**
1. Link `colors_and_type.css`.
2. Copy / adapt from `ui_kits/tinyassets-web/`.
3. Use hairline borders (`--border-1`), never 2px. Use the graph glow (`--glow-graph`) for hover / focus, not shadow.
4. Daemon-status indicators use the filled-dot pill pattern from `Primitives.jsx` (`StatusPill`).
5. No emoji. No icons without substituting Lucide CDN and flagging it.

**Making a slide deck:**
This brand has no existing slide template. If asked to make slides, ask the user whether they want a bespoke template built, flag that no prior deck exists, and build from the visual foundations (dark canvas, Fraunces display, the protocol-loom mark as the one graphic per slide).

## Things to double-check

- "Daemon" is lowercase in running text. "TinyAssets" is always capital W.
- Ember is primary accent; one ember mark per view, max two. Violet is ring energy, secondary.
- Hover = graph glow, not shadow. Press = 1px translate, not scale.
- Never invent new iconography. Use Lucide via CDN and flag the substitution.
- Never use emoji.
