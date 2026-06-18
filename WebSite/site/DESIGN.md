---
version: alpha
name: Tiny — The Logbook & The Readout
description: >-
  Tiny is a living instrument that shows its own readings honestly. Its whole
  identity is claim vs. evidence, so the design makes that duality physical:
  everything Tiny SAYS lives on a warm letterpress "logbook" (serif voice, ink
  on paper, ember for action); everything Tiny SHOWS — live stats, the brain
  graph, run logs, addresses — sits on a dark "readout" instrument panel (mono,
  ink-black ground, a single live-green heartbeat). A promise and a measurement
  are always distinguishable three ways at once: surface, type, and colour.
colors:
  # — Action (ember). primary is AA-clean; accent-bright is decoration/ring only.
  primary: "#b62744"        # ember-700 — buttons, links, actions (both surfaces)
  accent-bright: "#e94560"  # ember-600 — focus ring, wordmark, decorative marks
  accent-press: "#8a1a33"   # ember-900 — pressed / link hover
  # — Liveness (green). RESERVED for genuinely live readings. Never decorative.
  live: "#1f8a5c"           # on paper
  live-bright: "#46b483"    # on the dark readout
  live-tint: "#ddf0e4"
  # — Lineage (violet). Souls, forks, the graph trace. Quiet accent only.
  violet: "#6b44a8"
  violet-ink: "#4a2f76"     # readable violet on paper
  violet-bright: "#a98fe0"  # violet on the dark readout
  # — Logbook surface (warm paper) + ink.
  ground: "#efe7d4"         # the desk — page background
  paper: "#faf8f2"          # sheet — cards, raised containers
  paper-sunk: "#ece7d8"     # inset surfaces on paper
  rule: "#ded7c2"           # hairline rules / dividers on paper
  ink: "#1c1a14"            # primary text + headlines (warm near-black)
  ink-soft: "#45412f"       # body / secondary text
  ink-faint: "#736d54"      # captions, metadata (large / non-essential only)
  # — Readout surface (dark instrument panel).
  panel: "#16150f"          # readout ground — deep warm black
  panel-raised: "#211f17"   # raised cells within the readout
  panel-line: "#36331f"     # faint graph-paper grid / cell borders on the panel
  on-panel: "#f4f1e7"       # primary text on the readout
  on-panel-soft: "#b9b2a0"  # secondary mono text on the readout
  # — On-colour + status
  on-ember: "#fff8f2"
  signal-idle: "#b08a2e"    # asleep — a first-class, honest state (amber)
  signal-warn: "#c96f24"
  error: "#b62744"
typography:
  # Voice & display — Newsreader, optical (opsz tracks size), single 500 weight.
  display:
    fontFamily: Newsreader
    fontSize: 60px
    fontWeight: 500
    lineHeight: 1.04
    letterSpacing: -0.022em
    fontVariation: "opsz 72"
  h2:
    fontFamily: Newsreader
    fontSize: 36px
    fontWeight: 500
    lineHeight: 1.08
    letterSpacing: -0.02em
    fontVariation: "opsz 40"
  h3:
    fontFamily: Newsreader
    fontSize: 24px
    fontWeight: 500
    lineHeight: 1.18
    letterSpacing: -0.012em
  voice:
    fontFamily: Newsreader
    fontSize: 19px
    fontWeight: 400
    lineHeight: 1.6
  # Chrome — Inter, quiet.
  body:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.2
  # Evidence — IBM Plex Mono, always, with tabular figures for aligned data.
  eyebrow:
    fontFamily: IBM Plex Mono
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: 0.16em
  evidence:
    fontFamily: IBM Plex Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: 0.01em
    fontFeature: "tnum"
  readout-stat:
    fontFamily: IBM Plex Mono
    fontSize: 28px
    fontWeight: 500
    lineHeight: 1.1
    fontFeature: "tnum"
rounded:
  xs: 3px
  sm: 6px
  md: 10px
  lg: 14px
  full: 999px
spacing:
  # 4px base; dense at the small end for instrument data, generous chrome.
  hair: 2px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
  section: 96px
  container-max: 1120px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-ember}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: 11px 18px
  button-primary-hover:
    backgroundColor: "{colors.accent-press}"
    textColor: "{colors.on-ember}"
  button-ghost:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: 10px 16px
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.md}"
    padding: 24px
  readout-panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.on-panel}"
    rounded: "{rounded.sm}"
    padding: 24px
  readout-cell:
    backgroundColor: "{colors.panel-raised}"
    textColor: "{colors.on-panel-soft}"
    typography: "{typography.evidence}"
    rounded: "{rounded.xs}"
    padding: 10px 12px
  code-chip:
    backgroundColor: "{colors.paper-sunk}"
    textColor: "{colors.ink-soft}"
    typography: "{typography.evidence}"
    rounded: "{rounded.xs}"
    padding: 1px 6px
  eyebrow-label:
    textColor: "{colors.ink-faint}"
    typography: "{typography.eyebrow}"
  liveness-dot:
    backgroundColor: "{colors.live}"
    size: 7px
---

# Tiny — The Logbook & The Readout

## Overview

Tiny is not a brochure for a product; it is the product **speaking for itself**
— and, crucially, **showing its own readings while it speaks**. The governing
idea is the same one that makes Tiny trustworthy as an engine: **claim vs.
evidence.** A brochure can't be wrong; an instrument can — so Tiny is built to
read like an instrument that admits its state.

That duality is the entire design system. The site has two surfaces, and they
mean two different things:

- **The Logbook (warm paper).** Everything Tiny *says* — first-person voice,
  narrative, claims, navigation, explanation. Warm letterpress ground, ink text,
  serif voice (Newsreader), ember for action. It reads like a naturalist's
  logbook printed by a fine press: unhurried, human, credible.
- **The Readout (dark panel).** Everything Tiny *shows* — live stats, the brain
  graph, run logs, the loop, contract addresses, anything read live. An ink-black
  instrument panel, mono type (IBM Plex Mono), faint graph-paper grid, with the
  **live-green** as the only heartbeat. It reads like the lit face of a working
  instrument.

A reader can always tell a promise from a measurement, reinforced three ways:
**surface** (paper vs. panel), **type** (serif/sans vs. mono), and **colour**
(warm ink/ember vs. ink-ground/live-green). Evidence is never dressed as a claim,
and a claim never borrows the authority of a reading.

Audience: technically literate people deciding whether to connect a chatbot, fork
a universe, or trust the loop. Emotional target: **quiet credibility** — earned,
not asserted, because the instrument shows its work.

**Key characteristics**

- Two surfaces with fixed meaning: paper = says, panel = shows.
- Warm-only neutrals; no cool blue-gray anywhere.
- One action colour (ember), one liveness colour (green, reserved), one lineage
  colour (violet). Nothing else competes.
- Optical typography: Newsreader at its display optical size, weight 500 as the
  single headline voice, progressive negative tracking, tabular mono figures for
  all data.
- Calm grounds — a single faint texture per surface (paper grain; panel grid),
  never stacked washes.
- Depth is felt, not seen: layered low-opacity warm shadows on paper; inset
  lightness + hairline rules on the panel. No glow.

## Colors

Three meaning-bearing accents, spent sparingly, over two warm grounds.

- **Ink on paper (`#1c1a14` → `#736d54`):** Warm near-black for headlines/body,
  stepping to `#45412f` (body) and `#736d54` (metadata only — it is ~4.4:1, so
  never for long body text). Never pure black.
- **Paper (`#faf8f2`) over desk (`#efe7d4`):** Sheets are always *lighter* than
  the desk they rest on — depth reads as objects on a table. The warmth is the
  personality; never flatten to white.
- **Panel (`#16150f`) with `on-panel #f4f1e7`:** The readout ground is a deep
  warm black, not a cool charcoal. Text on it is paper-light (≈16:1). Raised
  cells (`#211f17`) and a faint grid (`#36331f`) build structure without borders.
- **Ember — action (`#b62744` primary / `#e94560` bright):** `primary` is the
  AA-clean action and link colour on both surfaces and the fill of primary
  buttons (white text ≈6:1). `accent-bright` is the louder red, reserved for the
  focus/liveness *ring*, the wordmark, and small decorative marks — never small
  text on a fill.
- **Live green (`#1f8a5c` paper / `#46b483` panel):** Reserved for genuine
  liveness — the status dot, "read just now" stamps, live readings. If it isn't
  live, it isn't green.
- **Lineage violet (`#6b44a8`, `#4a2f76` on paper, `#a98fe0` on panel):** Souls,
  forks, the `/graph` trace. A quiet accent, never an action.
- **Status:** asleep/idle is amber (`#b08a2e`) and a *first-class* state — Tiny
  says plainly when it sleeps.

## Typography

Three families, each with one job, executed optically.

- **Newsreader — voice & display.** All headlines and Tiny's first-person prose.
  Headlines are weight **500 only** (one author's voice; never bold, never
  light), set at Newsreader's high **optical size** so the display cut is refined,
  with progressive negative tracking that tightens as size grows (−0.022em at
  60px easing toward 0 at body). Italic Newsreader — ember on paper, green on the
  panel — is the single emphasis gesture.
- **Inter — chrome.** Navigation, buttons, labels, dense UI. Quiet; gets out of
  the way.
- **IBM Plex Mono — evidence.** Every live number, id, hash, timestamp and
  address, **always**, with **tabular figures (`tnum`)** so columns and changing
  readouts stay aligned. Also section eyebrows (uppercase, tracked 0.16em) and
  inline code. Mono is how the page signals "measured, not claimed."

| Role | Family | Size | Weight | Line height | Tracking | Notes |
|------|--------|------|--------|-------------|----------|-------|
| Display / H1 | Newsreader | 60px | 500 | 1.04 | −0.022em | opsz 72; hero |
| H2 | Newsreader | 36px | 500 | 1.08 | −0.02em | opsz 40; section anchors |
| H3 | Newsreader | 24px | 500 | 1.18 | −0.012em | card / sub-section |
| Voice | Newsreader | 19px | 400 | 1.60 | normal | first-person prose; italic→accent |
| Body | Inter | 16px | 400 | 1.60 | normal | standard UI text |
| Label | Inter | 13px | 500 | 1.20 | normal | buttons, chips |
| Eyebrow | IBM Plex Mono | 11px | 500 | 1.20 | 0.16em | uppercase section labels |
| Evidence | IBM Plex Mono | 13px | 400 | 1.50 | 0.01em | live data, ids; `tnum` |
| Readout stat | IBM Plex Mono | 28px | 500 | 1.10 | normal | big live numbers; `tnum` |

Encode the rule with classes: `.voice` (serif first-person), `.ev` (mono
evidence), `.eyebrow` (mono label). Reach for them rather than restyling ad hoc.

## Layout

A **4px spacing base**, dense at the small end (2/4/8) for instrument data,
generous for chrome (24/40) and **96px between major sections**. Content sits in
a centered column, **max ~1120px**, magazine-paced.

Surfaces alternate to tell the story: **paper sections** carry voice and
narrative; a **readout panel** is dropped in wherever Tiny shows live data — the
hero's pulse, the stats band, the graph, the loop log, the fine-print contract
table. The panel is full-bleed or a bordered slab, visually *recessed into* the
page like the lit face of an instrument set into a desk. Never scatter live
numbers loose on paper — collect them onto a readout.

## Elevation & Depth

Depth is **warm and quiet, never luminous.**

- **Paper:** layered low-opacity warm shadows (`sm` 1–2 layers ≤0.06; `md` adds a
  10–26px spread; `lg` for the rare floating element) — felt, not seen. Hairline
  `rule` dividers do most of the structural work.
- **Panel:** depth comes from *lightness*, not shadow — `panel-raised` cells sit
  above the `panel` ground, separated by the faint `panel-line` grid. The only
  "glow" anywhere is a **1px ring** (`accent-bright` for focus, `violet` for
  graph) — a hairline halo, never a bloom.

## Shapes

Conservative, instrument-precise corners. Scale: `xs 3px` (data/code chips),
`sm 6px` (buttons, readout panels/cells — the engineered default), `md 10px`
(paper cards), `lg 14px` (large paper containers), `full` (status pills + the
liveness dot **only**). Buttons are **not pills** — pills are reserved for status,
so a pill always reads as "state," never "action."

## Components

**Primary button** — `primary (#b62744)` fill, `on-ember` text, `label` type,
`sm` radius, ~11×18px. Hover → `accent-press`. One per view; works on both
surfaces.

**Ghost button** — `paper` fill, `ink` text, hairline `rule` border, `sm` radius.
Secondary actions.

**Card (logbook)** — `paper` sheet, hairline border, `md` radius, ~24px padding,
`sm` shadow when raised. Holds voice and narrative.

**Readout panel (the signature)** — `panel` ground, `on-panel` text, `sm` radius,
faint `panel-line` grid, `readout-cell` blocks for individual readings. A big
number uses `readout-stat` mono; every value carries a `liveness-dot`. This is
where the brain graph, the live pulse, run logs, and the loop live.

**Evidence row / readout cell** — mono `evidence` with `tnum`, a live/idle dot,
on `panel-raised`. The atomic unit of "showing."

**Code / address chip** — `paper-sunk` (on paper) or `panel-raised` (on panel),
`xs` radius, mono. Wraps any id, hash, or contract address.

**Eyebrow** — mono, uppercase, tracked 0.16em, `ink-faint` on paper /
`on-panel-soft` on panel. Labels a section above its serif headline.

**Liveness dot** — 7px pill: green when genuinely live (with a soft green ring),
amber when asleep, ember when errored. Never green unless the reading is live.

**Navigation** — sticky translucent paper; serif-italic "Tiny" wordmark with a
mono `tinyassets.io` sub-label; Inter nav items; active item gets an ember
underline. Hamburger drawer ≤1000px.

## Do's and Don'ts

**Do**
- Put claims on paper and live evidence on the readout panel — surface carries meaning.
- Set every headline in Newsreader weight **500** at display optical size; let italic-accent carry emphasis.
- Set **all** live data in mono with tabular figures; group it onto a readout, never loose on paper.
- Reserve green for genuine liveness, ember for action, violet for lineage. Keep all neutrals warm.
- Keep paper sheets lighter than the desk; build panel depth from lightness + the faint grid.
- Hold AA: body in `ink`/`ink-soft` and `on-panel`; actions in `primary (#b62744)`.
- Say "asleep" plainly — idle is a first-class amber state.

**Don't**
- Don't scatter live numbers on paper, or set evidence in serif/sans — that's claim costume on a measurement.
- Don't use pure white grounds or pure black text; don't use cool blue-grays.
- Don't put small text on `accent-bright (#e94560)` (≈3.8:1) — use `primary` or large/semibold.
- Don't make anything green that isn't live; don't dress filing/tags as readings.
- Don't bold or lighten Newsreader headlines; don't use pills for buttons (pills = state only).
- Don't stack background washes/textures — one faint texture per surface, max.
- Don't add luminous glows or heavy drop shadows; rings + soft warm shadows only.

## Agent Prompt Guide

**Decide first: is this a claim or a reading?** Claim → paper + serif/sans +
ember. Reading → dark readout panel + mono + green. That one decision drives
everything.

**Colours:** desk `#efe7d4` · sheet `#faf8f2` · ink `#1c1a14` · body `#45412f` ·
action/link `#b62744` · live `#1f8a5c` · soul `#6b44a8` · panel `#16150f` ·
on-panel `#f4f1e7` · live-on-panel `#46b483`.

**Type:** headlines/voice = Newsreader (500 / 400-italic, optical) · UI = Inter ·
all evidence/eyebrows/code = IBM Plex Mono with `tnum`.

**Example prompts**
- "Hero on the warm desk (`#efe7d4`): mono eyebrow `#736d54`, an H1 in Newsreader
  60px/500, tracking −0.022em, `#1c1a14`, one italic word in ember (`#b62744`),
  then a first-person `voice` line in Newsreader 19px/1.6. Beside it, a **readout
  panel** (`#16150f`, 6px radius, faint `#36331f` grid): three `readout-stat`
  numbers in IBM Plex Mono with tabular figures, each with a 7px green
  (`#46b483`) liveness dot and a mono caption."
- "Stats band: a full-width dark readout (`#16150f`). Each stat is a
  `panel-raised` (`#211f17`) cell, 3px radius: big number in IBM Plex Mono 28/500
  `#f4f1e7` (tnum), label in mono 11px uppercase `#b9b2a0`, live dot green."
- "Card on paper: `#faf8f2`, 1px `#ded7c2` border, 10px radius, 24px padding,
  soft warm shadow. Title Newsreader 24/500; body Inter 16 `#45412f`."

**Iteration rules**
1. Name colours by role ("action ember `#b62744`"), never "red."
2. Claim vs. evidence picks the surface, the family, and the colour — in that order.
3. One ember action per view; spend green only on live readings.
4. Neutrals stay warm; paper lighter than desk; panel depth from lightness + grid.
5. Depth = layers + space + 1px rings, never glow. Buttons are never pills.

*Follows Google's [DESIGN.md](https://github.com/google-labs-code/design.md) spec
(YAML tokens + prose). Lint: `npx @google/design.md lint DESIGN.md`. The runtime
source of truth is `src/lib/styles/tokens.css`; keep them in sync.*
