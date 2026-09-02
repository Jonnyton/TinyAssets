# App icon + splash

- `icon.png` — 1024×1024 source (the site's logo mark on `#0b0b0f`). Every
  launcher icon and adaptive foreground is rendered from this.
- `splash.png` — 2732×2732 source (the mark centred on `#0b0b0f`, matching the
  loading page). Every splash size is a cover-fit centre-crop of this, so editing
  it changes what ships.
- `android/` — the **pre-rendered density set** the app actually ships: legacy
  launcher icons (48–192 px, square + round), adaptive-icon foregrounds
  (108–432 px, mark at 66% so no launcher mask clips it) and the splash at every
  `drawable-{port,land}-*dpi` size. Mirrors the Capacitor Android template's
  paths so `scripts/add_app_icons.py` can copy by path after `npx cap add android`;
  the installer also checks the manifest still points at `@mipmap/ic_launcher`.

Why pre-rendered instead of `npx @capacitor/assets generate`: CI installs with
`npm ci --ignore-scripts` (read-only build), and `@capacitor/assets` needs sharp's
native libvips, which only arrives through an install script. Rendering once here
keeps CI free of an image toolchain and makes the shipped pixels reviewable.

## Regenerate

```bash
cd mobile
python scripts/render_app_icons.py                      # density set from icon.png + splash.png
python scripts/render_app_icons.py --from-logo ../WebSite/site/static/logo-mark.png \
    --font <Regular.ttf> --font-bold <Bold.ttf>         # also icon.png, splash.png, Play graphics
```

The wordmark font is an explicit file (no host lookup), so the feature graphic
renders identically on any machine given the same file. Rendered with Pillow 10.x;
the committed PNGs are canonical — re-render only to change the art, and review
the pixel diff.

`scripts/add_app_icons.py` fails the build if any file in `android/` is missing or
the wrong size for the template it is copied into, so a Capacitor upgrade that
changes the template surfaces here rather than as a blank icon on a phone.
