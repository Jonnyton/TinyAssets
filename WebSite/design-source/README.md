# TinyAssets — Design System

> **Summon the daemon.**
> *Design custom multi-step AI workflows. Real execution, not simulation.*

This is the design system for **TinyAssets**, an open-source platform that lets you design multi-step AI workflows inside your chatbot (Claude.ai, etc.) and have a **daemon** actually run them. The product is equal parts serious utility and a little bit occult — the vocabulary is load-bearing on the viral hook.

---

## What is TinyAssets?

TinyAssets is three things at once:

1. **An MCP server** — users paste one URL into Claude.ai and their chatbot gains a new set of tools: a catalog of reusable workflow nodes, the ability to compose them into multi-step pipelines, and the ability to hand off execution to a **daemon**.
2. **A daemon runtime** — a tray app (Windows/macOS/Linux) any user can host. Daemons pick up work: your own first, then paid work they're qualified for, then public requests. Idle is a failure state.
3. **An open commons** — every published workflow node is CC0. The concept layer (how a node works) is public; the instance layer (your actual data) is private and never training data.

Key brand/vocab: users **summon** daemons (not "start"), **bind** them to a universe (not "configure"), **entrust** them with tasks (not "assign"), **dismiss** them (not "stop"). Daemons **roam** the canon and **return** with findings.

---

## Sources consumed while building this system

All source material came from the user-attached TinyAssets codebase (`local_ls`/`local_read` against the `TinyAssets/` mount) and the GitHub repo **`Jonnyton/TinyAssets`**.

- `TinyAssets/README.md` — top-level pitch, "summoning" voice, product positioning.
- `TinyAssets/PLAN.md` — full platform plan (daemon-driven thesis, universes/canon/soul files).
- `TinyAssets/prototype/web-app-v0/src/lib/i18n/en.json` — canonical copy for the marketing site, MCP connect flow, daemon hosting, FAQ, trust signals. **This is the copy bible.** Copied to `source_copy/en.json`.
- `TinyAssets/prototype/web-app-v0/` — SvelteKit marketing + app prototype. Surfaces: landing, catalog, connect, host.
- `TinyAssets/prototype/full-platform-v0/` — Postgres/FastAPI gateway reference. Structural only; not visual.
- `TinyAssets/prototype/tinyassets-catalog-v0/` — CC0 catalog repo structure (nodes, branches, goals).
- `TinyAssets/docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md` — brand voice guide (the canonical list of verbs: *summon, bind, roam, return, dismiss, entrust*).
- `TinyAssets/assets/icon.png` — the canonical project icon: the selected A2 rotated protocol-loom mark cropped from the approved chat image. Copied to `assets/logo-mark.png` for design-system previews.

**Nothing else was available.** No photography, no illustration library, no secondary marks, no icon font. The `TinyAssets/output/*.png` files are QA screenshots from a ChatGPT builder test, not brand assets — intentionally ignored.

---

## Index — what's in this folder

```
/
├── README.md                    ← you are here
├── SKILL.md                     ← agent-skill manifest (for Claude Code / Skills)
├── colors_and_type.css          ← all design tokens (CSS vars) + semantic element styles
├── source_copy/en.json          ← verbatim product copy; use for tone-accurate mocks
├── assets/
│   ├── logo-mark.png            ← the approved cropped protocol-loom mark (USE THIS)
│   ├── logo-mark.svg            ← compatibility wrapper for the PNG
│   └── wordmark-horizontal.svg   ← mark + TinyAssets wordmark
├── preview/                     ← Design System tab cards (one HTML per token cluster)
└── ui_kits/
    └── tinyassets-web/            ← marketing + app UI kit (SvelteKit prototype, recreated as JSX)
        ├── README.md
        ├── index.html           ← interactive click-thru: landing → connect → catalog → host
        └── *.jsx                ← component factors
```

No sample slides — no deck template was provided.

---

## Content fundamentals

The copy is the brand. Get this right and everything else follows.

### Voice

Nerdy, slightly mythic, self-aware. It's confident about real utility *and* winking about the occult vocabulary. It never apologizes for the theme and it never overdoes it. Sentences are short. Claims are load-bearing.

### Person

- **"You"** addresses the user directly and does most of the work.
- **"Your daemon / your workflow / your universe"** — possessive. The user *owns* the daemon; they haven't rented a tool.
- **"We"** is rare and only appears when the platform itself has an obligation (privacy, refunds). Never for feature announcements.

### Casing

- Sentence case for titles, headers, buttons. **Not** Title Case. Not ALL CAPS except the tiny `ritual-label` small-caps utility.
- Product name is always **TinyAssets** (capital W, no italics).
- The word **daemon** is always lowercase in running text ("summon a daemon", not "Summon a Daemon") — it's a common noun, not a proper noun.

### The verb kit (load-bearing)

| Use… | Not… |
|---|---|
| **summon** a daemon | create, start, spin up, launch |
| **bind** a daemon to a universe | configure, set up, attach |
| **entrust** a daemon with a task | assign, give, send |
| **dismiss** a daemon | stop, kill, terminate, shut down |
| **roam** the canon for facts | query, search, retrieve |
| **return** with findings | complete, finish, deliver |

### Tone examples (verbatim from the product, use these as calibration)

- "Summon the daemon."
- "Your chatbot becomes a workshop. Your daemon does the work."
- "Real execution. The daemon actually runs your workflow; it doesn't pretend."
- "Your data stays yours. Concept-layer public; instance-layer private; never training data."
- "Idle is a failure state — it tries to stay useful."
- "The chatbot proposes; you confirm. No cached consent."
- Error (good): *"The summoning failed. (Check that the universe exists and try again.)"*
- Empty state (good): *"No daemons summoned yet. Summon your first daemon to begin."*

### Emoji / decorative characters

**None.** TinyAssets does not use emoji in UI copy, marketing, or docs. The brand mark carries all the visual charge; emoji would dilute it. Unicode glyphs (→, ·, —) are fine for typography. Avoid ✨, 🔮, 👻, 🪄, etc. — on-theme but cheapens the aesthetic.

### Punctuation tells

- Em dash — used freely — as a rhythmic breath. No spaces around it would also be fine but the codebase uses spaces, so we do too.
- Semicolons are allowed and encouraged for parallel claims: *"Concept-layer public; instance-layer private; never training data."*
- Parentheses soften a clarification after a declarative sentence — never for sales copy.

### Things to avoid

- Marketing superlatives: "best-in-class", "blazing fast", "game-changer", "seamless", "powerful". The product's claims are concrete (real execution, 1% fee, CC0); puffery breaks the voice.
- Apologetic hedging: "we think", "we hope", "might help". Declare.
- Over-mysticism: "forbidden knowledge", "arcane arts", "unleash". The tone is *knowing* occult, not *costume* occult. "Summoning a daemon" is as far as we go.

---

## Visual foundations

The visual identity centers on the selected A2 rotated protocol-loom mark (`assets/logo-mark.png`) and four colors: ink, ivory, ember, and live green. Everything that follows is derived from that mark.

### Palette

- **Ink** (`#0e0e1a → #1a1a2e → #16213e`) — the default canvas. The product is a night-mode product. Dark surfaces are not a toggle; they're the base state.
- **Ivory** (`#f2eee6`) — the primary mark stroke and main text on dark surfaces.
- **Live green** (`#6dd3a6`) — the lower route / live-state accent in the mark and the semantic live indicator.
- **Violet** (`#533483`) — secondary graph/branch color. Never a primary CTA.
- **Ember** (`#e94560`) — the crossing work route and primary accent. Used *sparingly* — one ember mark per view, max two.
- **Bone** (`#f7f5ef`) — the warm-paper light-mode surface for docs, legal, catalog reading views. Not a "card" color — a full secondary theme.

No blues or teals outside the ink range. No greens outside `--signal-live`. No gradients as fills unless a specific production asset calls for it.

### Typography

- **Fraunces** (display/serif) — hero lines, H1/H2/H3. Its optical-size and softness axes let us dial a slightly-mythic, grimoire-ish feel without going full goth. `opsz:144` at huge sizes, italic + `SOFT:100, WONK:1` when setting a single emphatic word (the ember-colored word in "Summon the *daemon*").
- **IBM Plex Sans** (body) — all UI, buttons, forms, metadata. Chosen for its engineering-serious character; it reads "this is a real tool" against the Fraunces theatrics.
- **IBM Plex Mono** (monospace + labels) — code, IDs, and the `ritual-label` small-caps utility used for section kickers and metadata. The mono in a label says *"this is inscribed, not printed."*

⚠️ **Font substitution flag:** TinyAssets's codebase does not ship its own webfonts — the SvelteKit prototype uses the default system stack. Fraunces + IBM Plex were chosen as the nearest stylistic match based on the brand voice (serious + slightly-mythic). If the team has existing licensed faces (a commissioned display face, a specific Plex alternative, etc.), please drop the TTF/WOFF2 into `fonts/` and update `--font-display` / `--font-sans` in `colors_and_type.css`.

### Spacing, shape, scale

- 4px base. Scale is `4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96`. No 6/10/14 values — the rhythm stays on-grid.
- Radius scale: `3 / 6 / 10 / 14 / 22` px. Cards use `--radius-card: 12px`. Pills exist but only for daemon-status capsules.
- Borders are **1px and hairline** (`rgba(255,255,255,0.08)` on dark, `rgba(22,21,36,0.08)` on light). They exist to separate planes, not to decorate. A 2px border is a bug.

### Elevation & shadow

Drop-shadow is muted — dark surfaces swallow it. Elevation reads via:

- **Inner 1px highlight** on top edge (`0 1px 0 rgba(255,255,255,0.05) inset`) — the "held in a ring" feel.
- **Graph glow** — a 30px violet halo (`--glow-graph`) on focused/active elements (input focus, hovered daemon tile, summoning CTA).
- **Ember glow** — only on primary CTAs (`--glow-ember`). Tight, not diffused.

### Backgrounds

- Full-bleed ink surfaces (`--bg-1`) are the default. No patterned backgrounds, no noise textures, no grain (tempting — resisted). The logo mark is the only ornamental graphic; it may be placed large and low-opacity (0.04–0.08) as a watermark behind hero type, bottom-right or centered.
- Protection gradients only as hero-bottom fades from `--bg-1` to transparent, to seat a CTA bar over imagery. We don't use imagery much so this is rare.
- **No full-bleed stock photography.** TinyAssets's brand is text + live protocol mark.

### Animation & interaction

Daemons don't bounce. Motion is deliberate, ease-out, never springy.

- `--dur-fast` (120ms) for hover color shifts.
- `--dur-base` (200ms) for state transitions (button press, tab change).
- `--dur-slow` (360ms) for layout moves (drawer opens, row expands).
- `--dur-ritual` (700ms) reserved for "a daemon has been summoned" success animations — a slow breathe-in of the ring, not a confetti pop.
- Easing is `cubic-bezier(0.22, 1, 0.36, 1)` — a spell landing. Never `ease-in-out` (too gentle, too web-app).

### Hover & press

- **Hover**: a 1–2% lightness shift on surfaces; on links/labels, a shift up the ember scale (`--ember-600 → --ember-500`); on buttons, a faint graph glow if primary.
- **Press**: 1px downward translate + darker variant (`--ember-600 → --ember-700`). No scale transforms (no `scale(0.98)` — too web-app).
- **Focus**: 2px ember outline at `--ring-offset: 2px`. Never a default browser outline; never removed without replacement.

### Borders vs capsules

A pill capsule is used only for daemon-status indicators (`live / idle / paid`). Everything else uses hairline borders + radius. No floating pills for filters, no badge-style labels — filters are text buttons with an ember underline when active.

### Transparency & blur

Sparing. Used only for:
- Modal scrims: `rgba(14,14,26,0.72)` + 8px backdrop blur.
- The protocol-loom watermark behind hero type.
- Toast notifications pulled into the top-right (12px blur on a `rgba(31,36,71,0.72)` tint).

No frosted-glass sidebar. No glassmorphism panels.

### Imagery vibe

Where imagery *must* appear (team photos, screenshot mocks, OG cards), it is:
- **Cool** (not warm) — blue-biased white balance, slight desaturation.
- **Moody but not dark** — enough shadow detail that nothing feels grimy.
- Never tinted duotone. Never cyan/magenta split-tone. If imagery is present, it's imagery; no filter performance.

### Card anatomy

- Surface: `--bg-2` (one step up from page), 1px `--border-1` hairline, `--radius-card` (12px).
- No drop-shadow by default. On hover, the graph glow appears (`--glow-graph`) instead of a heavier shadow.
- Padding: `--s-5` (20px) default, `--s-6` (24px) for feature cards.
- The card's title is sans-serif semibold. Metadata beneath uses `.ritual-label` (mono, small-caps).

### Layout rules

- Max content column: 1240px; hero content: 960px; prose: 640px (`62ch`).
- Fixed elements: top nav is sticky-translucent (backdrop-blur) on scroll, not a solid bar. The footer is not fixed.
- The protocol-loom mark is bottom-right of any marketing hero as a faint watermark when the hero feels empty.

---

## Iconography

**TinyAssets ships no icon set.** The codebase is a prototype; the SvelteKit app uses text labels and HTML bullet characters where other apps would use icons. This is an intentional gap — the design system has to answer it.

### What the product uses today

- The single **logo mark** (`assets/logo-mark.png`) — the selected A2 rotated protocol-loom mark cropped from the approved chat image: ivory woven routes crossed by ember work and a live-green state route. This is the hero graphic and the favicon.
- **Unicode glyphs** for directional and separator use: → (proceed / next), · (bullet separator), — (em dash). These are deliberate and should not be replaced with icons.
- **No emoji anywhere.** See Content Fundamentals.

### What we substitute (flagged)

For UI surfaces that need affordance icons (navigation, form inputs, tool chips, daemon status), this system uses **Lucide** via CDN:

```html
<script src="https://unpkg.com/lucide@latest"></script>
<i data-lucide="moon-star"></i>
```

Lucide is chosen because:
- Consistent 1.5px stroke weight reads "engineering-tool" rather than "consumer-app."
- Line icons (not filled) let them sit on the dark canvas without feeling heavy.
- The set is comprehensive enough to cover every UI need without forcing us to invent.

**🚩 Flag:** Lucide is a **substitution**, not a brand decision. When TinyAssets commissions or adopts an official icon set, swap the CDN reference in `ui_kits/tinyassets-web/index.html` and update the usage notes here.

### Icon usage rules (apply to Lucide today, to whatever replaces it tomorrow)

- **Stroke, never filled.** Exception: status dot indicators (`live`, `idle`) are filled circles, not icons.
- **Size steps:** 14px, 16px, 20px, 24px. Never scale arbitrarily.
- **Color:** inherit currentColor. Icons never carry their own color unless they're an ember-accent affordance (the "summon" button's star, the active-daemon pulse).
- **Pair rule:** Text + icon is better than icon-only. Icon-only is reserved for the 24×24 tray-app surface where space is truly gone. Tooltip required.
- **Favored icon metaphors** (on-brand): `moon-star`, `sparkles` (sparing), `orbit`, `radio`, `zap` (sparing), `book-open`, `scroll-text`, `shield`, `link-2`, `play`, `pause`, `circle-stop`.
- **Off-brand metaphors** (avoid): rocket (🚀 energy), lightning-on-a-shield, shopping carts, generic cogs for "summon" (use the star, not a cog).

### Favicon

`assets/logo-mark.png` is already square and compact. Use it as the favicon at 32px without modification.

---

## Quick-start for designers

1. Link `colors_and_type.css` at the top of any HTML.
2. Default to the dark theme. Add `data-theme="light"` only for docs / legal / reading surfaces.
3. Copy/adapt from `ui_kits/tinyassets-web/` — don't reinvent components.
4. Use `source_copy/en.json` verbatim when possible. When you need new copy, re-read Content Fundamentals and match the verb kit.
5. The logo mark goes bottom-right at 0.06 opacity when a hero feels empty. Resist putting it anywhere else.
