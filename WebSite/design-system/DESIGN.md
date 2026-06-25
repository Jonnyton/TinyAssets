# Tiny — Design System ("Field Notes")

> Framework-agnostic design brief for AI design tools and coding agents.
> This file is the high-leverage, provider-neutral artifact: any agent that
> reads it can build on-brand UI without the compiled bundle. The compiled
> React library (`dist/`) and DTCG tokens (`tokens/tiny.tokens.json`) are the
> machine contracts; this is the rules layer.

## 1. Theme & feeling

Tiny's surface is **a naturalist's logbook crossed with a scientific
instrument** — "Field Notes." Warm paper ground, ink text, calm and
deliberate. Instruments don't bounce. A core distinction is **claim vs
evidence, made typographic**: prose/claims use serif (voice) or sans
(chrome); live data, ids, and timestamps are **always mono**.

## 2. Color (semantic roles → CSS variables)

Use the semantic variables, not raw hex. Full list in `tokens/tiny.tokens.json`.

| Role | Variable | Use |
|---|---|---|
| Page ground (the desk) | `--bg-0` | body background |
| Card / sheet | `--bg-1` … `--bg-3` | raised paper surfaces |
| Text | `--fg-1` (strong) → `--fg-4` (faint) | ink hierarchy |
| Action | `--ember-600` / `--accent` | **the one** primary action; never decorative |
| Liveness | `--live-600` / `--signal-live` | **reserved** for genuine live evidence only |
| Soul / lineage | `--violet-600` | forks, souls, lineage traces |
| Borders | `--border-1` / `--border-2` | hairlines on paper |
| Dark readout | `--panel`, `--on-panel` | the instrument panel where Tiny SHOWS data |

**Hard rule:** green (`--live-*`) is load-bearing — only for genuinely live
state. Amber (`--signal-idle`) for asleep/idle (a first-class state, not an
error). Ember for action and error.

## 3. Typography

Three families, each with a job:

- **Voice** `--font-voice` (Newsreader serif) — Tiny's first-person prose, display headlines.
- **Chrome** `--font-sans` (Inter) — UI labels, nav, body chrome.
- **Evidence** `--font-mono` (IBM Plex Mono) — every live number, id, timestamp, address. No exceptions.

Scale: `--fs-xs` (11px) … `--fs-6xl` (96px). Headings use `--font-display`,
weight 500, tight tracking (`--ls-tight`). Eyebrows/kickers use mono + wide
caps tracking (`--ls-caps`) — that's the `RitualLabel` / `.eyebrow` vocabulary.

## 4. Components (stylings + states)

Real components ship in the React library; these are the patterns.

- **Button** (`btn`) — variants `primary` (ember, the single key action) /
  `secondary` (violet) / `ghost` (quiet outline) / `link`; sizes `sm|md|lg`.
  Renders `<a>` when `href` is set. Hover lifts with `--glow-ember`.
- **StatusPill** (`pill`) — `kind` live/idle/paid/self/error; `pulse` only when
  truly live. Mono, uppercase, dot colour follows the liveness rule above.
- **RitualLabel** (`ritual-label` / `.eyebrow`) — small-caps mono kicker.

## 5. Vocabulary classes (global, in `styles.css`)

`.voice` (first-person prose), `.ev` (inline evidence/mono), `.eyebrow`
(section kicker), `.dot.live/.idle/.error` (liveness dot), `.readout` (the dark
instrument panel), `.stat` / `.stat__num` / `.stat__label` (a live reading),
`.container` (max-width 1240px). Prefer these to reinventing styles.

## 6. Layout, spacing, shape

4px spacing base (`--s-1`=4 … `--s-24`=96). Radius `--radius-sm` (6) for chrome,
`--radius-md` (10) for cards. Page content lives in `.container`
(max-width 1240px, fluid side padding). Sections get vertical `--s-12` rhythm.

## 7. Elevation & motion

Graphite-soft shadows on paper (`--shadow-sm/md/lg`) — **never glow** except
the deliberate `--glow-ember` on a primary action. Motion is calm:
`--ease-summon` for entrances, `--dur-base` (200ms) default.

## 8. Do / don't

- DO reserve green for real liveness; DO use mono for all evidence; DO keep one
  ember primary action per surface; DO treat idle/asleep as a normal state.
- DON'T use pure black/white; DON'T make green decorative; DON'T add glows;
  DON'T mix claim and evidence type registers.

## 9. Agent build guide

Wrap any design so the token `:root` is present — import the library's
`styles.css` (or `@tiny/design-system/styles.css`) once at the root; it carries
tokens + reset + vocabulary. Then compose with the real components and the
semantic variables. Read `tokens/tiny.tokens.json` for the exact token names and
each component's `*.prompt.md` for usage. Example:

```tsx
import "@tiny/design-system/styles.css";
import { Button, StatusPill } from "@tiny/design-system";

<section className="container">
  <span className="eyebrow">Live evidence</span>
  <h1>Name a goal. Watch it run.</h1>
  <p className="voice">I turn chat into <em>finished work</em>.</p>
  <StatusPill kind="live" pulse>live</StatusPill>
  <Button href="/start">Connect a chatbot</Button>
</section>
```
