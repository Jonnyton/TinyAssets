# Tiny — "Field Notes" design system (how to build with it)

A naturalist's logbook crossed with a scientific instrument: warm paper ground,
ink text, calm and deliberate. One load-bearing rule — **claim vs evidence is
typographic**: prose uses serif/sans; live data, ids, and timestamps are
**always mono**.

## Setup (no provider needed)

There is NO React context/ThemeProvider. The whole look is global CSS custom
properties. Import the stylesheet **once** at the app root — it carries the
design tokens (`:root` vars), the base reset, and the vocabulary classes:

```tsx
import "@tiny/design-system/styles.css";
import { Button, StatusPill, RitualLabel } from "@tiny/design-system";
```

Without that import, components render unstyled (the tokens they reference
won't exist).

## Styling idiom: tokens + vocabulary classes (NOT utility classes)

This is **not** a Tailwind/utility system and has **no class-name component
props**. Style your own layout glue two ways:

1. **CSS custom properties** — the design language. Real names (see
   `tokens/tiny.tokens.json` for the full set):
   - color: `--bg-0`..`--bg-3` (paper grounds), `--fg-1`..`--fg-4` (ink, strong→faint),
     `--ember-600`/`--accent` (the ONE action color), `--live-600` (RESERVED for genuine
     liveness), `--violet-600` (lineage/souls), `--border-1`/`--border-2`, `--panel`/`--on-panel` (dark readout)
   - type: `--font-voice` (Newsreader serif), `--font-sans` (Inter), `--font-mono` (IBM Plex Mono — for ALL evidence)
   - space `--s-1`..`--s-24` (4px base), radius `--radius-sm`/`--radius-md`, `--shadow-sm/md/lg`
2. **Global vocabulary classes** (defined in `styles.css`, use as plain strings):
   `container` (max-width page wrap), `voice` (Tiny's first-person prose), `ev`
   (inline evidence/mono), `eyebrow` (mono small-caps section kicker), `dot` +
   `dot live|idle|error` (liveness dot), `readout` + `stat`/`stat__num`/`stat__label`
   (the dark instrument panel where data is SHOWN).

Hard rules: green (`--live-*`) only for real liveness; mono for every number/id/
timestamp; exactly one ember `Button variant="primary"` per surface; idle/asleep
is a first-class state, not an error.

## Components (real exports)

- **Button** — `variant` primary|secondary|ghost|link, `size` sm|md|lg, `href` (renders an anchor). primary = the one ember action.
- **StatusPill** — `kind` live|idle|paid|self|error, `pulse` (only when truly live). Mono caps capsule; dot color follows the liveness rule.
- **RitualLabel** — small-caps mono kicker (same as the `.eyebrow` class), optional `color`.

Read each component's `*.prompt.md` for usage rules and `styles.css` (the bound
copy) before styling. Example:

```tsx
<section className="container">
  <span className="eyebrow">Live evidence</span>
  <h1>Name a goal. Watch it run.</h1>
  <p className="voice">I turn chat into <em>finished work</em>.</p>
  <div style={{ display: "flex", gap: "var(--s-3)", alignItems: "center" }}>
    <StatusPill kind="live" pulse>live</StatusPill>
    <Button variant="primary" href="/start">Connect a chatbot</Button>
  </div>
</section>
```
