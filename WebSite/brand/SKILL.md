---
name: tinyassets-design
description: Use this skill to design on-brand TinyAssets interfaces and assets, for production or for throwaway prototypes and mocks. Carries the warm-editorial identity: palette, type, the mark, the vocabulary, and the copy rules.
user-invocable: true
---

Read `../design-system/DESIGN.md` first: it is the rules layer, and
`../design-system/tokens/tiny.tokens.json` is the machine-readable mirror of
the canonical tokens in `../design-system/src/styles/tokens.css`.

If you are building production UI, import the real library
(`@tiny/design-system`) rather than copying values. If you are making a mock or
a one-off artifact, copy the token `:root` out of `tokens.css` into a standalone
HTML file so the look is identical.

## What TinyAssets is (get this right before designing anything)

- **The product in one line:** your own AI universe. A cloud agent with storage,
  connections, automations and a brain of its own, running on the Claude or
  ChatGPT subscription you already pay for. It builds any automation to any
  platform from a few primitives, learns you as it goes, and keeps working when
  you close the tab.
- **Naming:** *TinyAssets* is the platform and brand; *Tiny* is the universe a
  person talks to, in the first person. A chatbot connected over MCP relays to
  the universe; it never speaks as it.
- **Voice:** plain, exact, unhurried. Say what a universe finished, with the
  receipt. Never "AI-powered", never "unleash", never sparkle. Load-bearing
  verbs: found, connect, build, run, remix, refuse.
- **Never claim:** a platform-supplied model, a paid work market, tokens or
  crypto, host-run fleets, a list of integrations, or engagement metrics.

## Visual DNA (warm editorial)

- **Ground:** paper `#f4efe4`, sheets in `#fbf8f1`. Never white, never a dark
  default.
- **Ink:** `#1e1a17` for text; three quieter steps below it.
- **One accent:** terracotta `#b5471f` for the single action on a surface, one
  emphasised word, and the dot in the mark. A muted green `#3a7d47` is reserved
  for genuine liveness. Nothing else is coloured.
- **Type:** Fraunces (variable optical size) for display and first-person
  prose, Source Sans 3 for body, IBM Plex Mono for every id, number, timestamp
  and receipt line.
- **Motif:** rules and receipts. Sections are separated by hairlines, data sits
  in ruled tables (`.ledger`), and a run reports itself as a `.receipt` between
  a heavy top rule and a foot rule. Radii are small, shadows nearly absent, no
  glows or gradients.

## The mark

A ring (a universe) crossed low by a rule that runs off to the right (a ledger
line), with one terracotta dot on the rule (the agent). The geometry lives in
`../../tinyassets/desktop/icon_gen.py` and nowhere else.

- `mark.svg` — the bare mark, transparent, for light grounds and inline use.
- `mark-tile.svg` — the mark on its rounded paper tile, for app icons and dark
  grounds.
- `python render_marks.py` (from the repo root: `python WebSite/brand/render_marks.py`)
  exports every raster: site icons, `assets/`, desktop, tray, Android, Play.
- `python render_og.py` renders the site's Open Graph card with the real fonts.

Never hand-edit an exported PNG or ICO, and never redraw the mark by eye.

## Common tasks

**A marketing page or hero:** import `@tiny/design-system/styles.css` (or paste
the token `:root`). Ritual label, then an H1 in Fraunces, then one lead
paragraph, then one terracotta button. Put the proof underneath as a
`.receipt`, not as a testimonial.

**An app surface:** hairline borders, `.sheet` for cards, `.ledger` for any
table of records, mono for every value that came from a machine. One primary
action per screen; secondary actions are ink-filled or quiet outlines.

**A diagram:** ink strokes on paper, terracotta only for the element the reader
must follow. Label nodes in mono.

## Files

- `../design-system/DESIGN.md` — the full rules layer.
- `../design-system/src/styles/tokens.css` — canonical tokens.
- `../design-system/src/components/` — Button, StatusPill, RitualLabel, Tick,
  Term, Ladder, each with a `.prompt.md` describing correct use.
- `mark.svg`, `mark-tile.svg`, `render_marks.py`, `render_og.py` — the mark.
- `../site-react/` — the live site, the best reference for how the language is
  actually used.
