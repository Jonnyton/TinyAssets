# Workflow Web — UI Kit

A pixel-faithful recreation of the Workflow marketing + connect + catalog + host surfaces, as a React/JSX click-through prototype.

## Source

- `Workflow/prototype/web-app-v0/` — SvelteKit prototype (routes: `/`, `/connect`, `/catalog`, `/host`, `/account`, `/contribute`, `/legal`, `/status`).
- `source_copy/en.json` — all copy is verbatim from the prototype's i18n file.
- `assets/logo-mark.svg` — the summoning sigil.

## Contents

- `index.html` — interactive click-through: Landing → Connect → Catalog → Host, with a top nav.
- `TopNav.jsx` — sticky-translucent navigation bar.
- `Landing.jsx` — hero + how-it-works + why-workflow + CTAs.
- `Connect.jsx` — Claude.ai connect flow, copy-URL, step-by-step, examples.
- `Catalog.jsx` — browse workflow nodes with filters + detail view.
- `Host.jsx` — hosting flow: OS download, visibility modes, earnings, FAQ.
- `SigilMark.jsx` — the brand mark + a watermark variant.
- `Button.jsx`, `StatusPill.jsx`, `DaemonTile.jsx` — reusable primitives.

## What's faithful vs approximate

- **Faithful:** copy (verbatim), tokens (from `colors_and_type.css`), page structure (one section per Svelte route section), the sigil logo.
- **Approximate:** interactivity is a cosmetic click-thru — no real MCP connection, no real catalog fetch, no real OS detection. All state is local React state and fake data.
- **Omitted:** `/account`, `/contribute`, `/legal`, `/status` — low-signal for visual reference; surfaces reuse the same primitives.
