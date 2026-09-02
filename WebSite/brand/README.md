# TinyAssets brand

The mark, its exporters, and the design skill.

| File | What it is |
|---|---|
| `mark.svg` | The bare mark (transparent). Inline this on light grounds. |
| `mark-tile.svg` | The mark on its rounded paper tile. App icons, dark grounds. |
| `render_marks.py` | Exports the mark to every surface. Run from the repo root. |
| `render_og.py` | Renders the site's Open Graph card with the real web fonts. |
| `SKILL.md` | The design skill: identity, palette, type, motif, copy rules. |

**One source of truth.** The geometry and palette live in
`tinyassets/desktop/icon_gen.py` (`draw_mark`, `mark_svg`). The SVGs and every
raster in this repo are generated from it:

```bash
python WebSite/brand/render_marks.py   # site icons, assets/, desktop, tray, Android, Play
python WebSite/brand/render_og.py      # WebSite/site-react/public/og-image.png
```

Both need Pillow; `render_og.py` also needs Python Playwright. Never hand-edit
an exported PNG or ICO — change the geometry and re-run.

The design language itself (tokens, components, the rules layer) lives in
`WebSite/design-system/`, with `DESIGN.md` as the brief.
