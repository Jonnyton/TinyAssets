# App Store listing assets

Notes for the App Store Connect listing (see `../app-store-launch.md`). The Play
equivalent is `../play-assets/`, which does hold uploadable files; this folder is
deliberately mostly pointers, because the two stores take their icon differently.

## The app icon is not uploaded — it ships inside the build

Google Play takes a 512 listing icon as metadata you upload. **Apple does not.** It
reads the App Store icon out of the asset catalog inside the uploaded build. So the
icon is *build input*, and it lives where the build reads it:

**`mobile/resources/icon-ios.png`** — 1024×1024, square, RGB.

`ios-release.yml` copies it over `resources/icon.png` before running
`capacitor-assets generate --ios`, so the whole generated `AppIcon.appiconset`
comes from the square source, and verifies the swap by hash first. A square PNG
staged in a docs folder would change nothing about what Apple displays.

### Why a separate source from `mobile/resources/icon.png`

`icon.png` is the rounded badge. Apple applies its **own** corner mask, so a
pre-rounded icon renders double-masked, with the badge's dark corners showing as
wedges inside Apple's rounding.

The distinguishing property is **square/full-bleed, not alpha**: both files are
1024×1024 with no alpha channel, so checking "RGB, no alpha" passes the wrong one.
Check the corners — `icon-ios.png` has artwork there, `icon.png` has background.

The rounding in `icon.png` is correct for Android, whose launcher masks a
pre-rounded source, and for the web. Only Apple needs the square variant.

Both are rendered by `WebSite/brand/render_marks.py` from the same geometry as
every other surface (`tinyassets/desktop/icon_gen.py`); the square one via
`draw_mark(1024, tile=True, radius=0)`. Re-render when the mark changes. Squaring
the badge does not crop or add anything — it reveals the sky and ground the rounded
badge clips at the corners.

## Screenshots

Not staged. Apple wants roughly 19.5:9 (1290×2796 for 6.7", 1320×2868 for 6.9");
the Play captures next door are 1080×1920 (9:16) and cannot be resized to fit.

Before re-capturing anything, read
`docs/concerns/2026-09-03-play-listing-screenshot-shows-internal-repo-detail.md`:
the existing Play conversation capture publishes internal repo and architecture
detail, and must not be reused here.
