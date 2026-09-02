# App icon + splash

- `icon.png` — 1024×1024 source (the TinyAssets monogram on the ink ground, `#14140f`).
- `splash.png` — 2732×2732 source (the mark centred on `#14140f`, matching the
  loading page).
- `android/` — the **pre-rendered density set** the app actually ships: legacy
  launcher icons (48–192 px, square + round), adaptive-icon foregrounds
  (108–432 px, mark at 66% so no launcher mask clips it) and the splash at every
  `drawable-{port,land}-*dpi` size. Mirrors the Capacitor Android template's
  paths so `scripts/add_app_icons.py` can copy by path after `npx cap add android`.

Why pre-rendered instead of `npx @capacitor/assets generate`: CI installs with
`npm ci --ignore-scripts` (read-only build), and `@capacitor/assets` needs sharp's
native libvips, which only arrives through an install script. Rendering once here
keeps CI free of an image toolchain and makes the shipped pixels reviewable.

## Regenerate

```bash
cd mobile
python scripts/render_app_icons.py                                              # density set from icon.png
python scripts/render_app_icons.py --from-logo ../assets/icon.png   # also icon.png, splash.png, Play graphics
# or, for every surface at once: python ../WebSite/brand/render_marks.py
```

`scripts/add_app_icons.py` fails the build if any file in `android/` is missing or
the wrong size for the template it is copied into, so a Capacitor upgrade that
changes the template surfaces here rather than as a blank icon on a phone.
