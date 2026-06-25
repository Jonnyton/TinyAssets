# design-sync notes — @tiny/design-system

First sync: 2026-06-25. Shape = storybook. 3 components (Button, StatusPill,
RitualLabel), all stories graded `match` against the reference storybook.

## Setup facts

- `buildCmd`: `npm run build` (emits dist/ + tokens/tiny.tokens.json + manifest).
- Converter entry: `dist/index.js` (in the package's own source repo, so `--entry`
  is required — there is no `node_modules/@tiny/design-system`).
- Global: `window.TinyDS`. No `.storybook/preview` decorators → no `cfg.provider`
  needed (the design language is global CSS vars, not a React context/ThemeProvider).
- Fonts are remote (`[FONT_REMOTE]`): Inter / Newsreader / IBM Plex Mono via a
  Google Fonts `@import` in styles.css — the host serves them at runtime, so both
  the storybook reference and the previews render the real fonts.

## Re-sync risks (what to re-verify next run)

- **Target project is the re-adopted "Workflow Design System" (48072c27…)** — a
  pre-existing, formerly hand-authored project. The first sync DELETED its old
  April content (JSX kit, diagrams, preview cards) and replaced it with this
  bundle. There is no `_ds_sync.json` anchor from before this sync, so the first
  run reviewed `list_files` to build the delete set; subsequent runs use the
  anchor we uploaded.
- Project rename to "Tiny Design System" is a manual UI step (the DesignSync tool
  can't rename) — if the project name still says "Workflow Design System", that
  rename hasn't happened; it does not affect the sync.
- Only 3 primitives are synced so far. The live site has more components
  (cards, readout panels, VitalSigns, nav, etc.) that are NOT yet in the DS
  package — adding them to `src/components/` + stories will grow the next sync.
