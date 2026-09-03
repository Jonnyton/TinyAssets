# The App Store icon we are told to upload has rounded corners baked in

**Status:** Finding, with a decision the founder owns (it changes brand art).
**Found:** 2026-09-03, while closing out the remaining non-founder items for the
App Store submission.
**Blocks:** nothing today — the Apple Developer Program account does not exist yet.
It blocks the App Store *submission*, which is exactly when it would be most
expensive to discover.

## The claim that is wrong

`docs/ops/app-store-launch.md` §6 says:

> App icon: 1024×1024 (from `mobile` capacitor assets, `npm run assets:ios`).

Following that gives `mobile/resources/icon.png`, which is a correct-looking
1024×1024 RGB with no alpha — and is **not** a valid App Store icon.

## Evidence

Apple's requirement is that the 1024×1024 App Store icon be **full-bleed and
square**: no transparency, and no rounded corners, because the system applies its
own mask. An icon that arrives pre-rounded on a contrasting ground renders
double-masked, with the original corners showing as dark wedges inside Apple's
rounding.

`mobile/resources/icon.png` is pre-rounded. Sampling its bottom row (`y=1023`):

| x | pixel |
|---|---|
| 0, 20, 60, 120 | `(20, 20, 15)` — the background colour |
| 200, 400, 512 | `(210, 204, 190)` — the artwork's ground |
| 900, 1003, 1023 | `(20, 20, 15)` — background again |

Light artwork in the middle of the edge, dark at both ends, is a rounded-rect
mask. 173 of 256 sampled border pixels are the background colour.

## Where the rounding comes from

`assets/icon.svg` clips the art to `rx="13"` on a 64×64 viewBox, and paints a
matching rounded background rect:

```
<clipPath id="ta-badge"><rect width="64" height="64" rx="13"/></clipPath>
<rect width="64" height="64" rx="13" fill="#1b1b24"/>
```

`mobile/scripts/render_app_icons.py` then composites that RGBA logo onto a solid
`BG = (0x14,0x14,0x0F)` canvas (lines 88–89), which turns the transparent corners
into opaque dark ones. So the rounding is inherited from the brand source, not
introduced by the mobile renderer — and the same source feeds Android, where
pre-rounding is *correct* for the legacy launcher icon.

## Two candidate fixes, and why I did not just pick one

1. **Render a square variant for Apple only** — set `rx="0"` on both the clipPath
   rect and the background rect, rasterise at 1024, and stage it as an
   Apple-specific asset. Minimal and reversible, but it means the App Store icon
   shows artwork the rounded badge currently crops, so someone has to look at it
   and agree it reads well square. It is a brand call, not a mechanical one.
2. **Reconstruct the corners from the existing 1024 PNG** by extending the edge
   bands outward. The art is largely horizontal (sky, mountains, ground) so this
   would be nearly seamless — but it is fabricating brand art from a raster, which
   is not a thing an agent should do unasked.

I could not do either mechanically here regardless: there is **no SVG rasteriser
on this host** (no `cairosvg`, no `svglib`, no ImageMagick/Inkscape/rsvg — the
`convert` on PATH is Windows' own `convert.exe`), so option 1 needs a machine that
can rasterise `assets/icon.svg`.

## What to do

- Before any App Store submission, produce a square full-bleed 1024×1024 icon; do
  not upload `mobile/resources/icon.png`.
- Leave the Android and web assets alone — the rounding is right for them.
- Delete this file once a square Apple icon is staged and §6 points at it.
