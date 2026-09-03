# App Store listing assets

Staging for the App Store Connect listing (see `../app-store-launch.md`). The
Play equivalent is `../play-assets/`.

- `icon-1024.png` — the 1024×1024 marketing icon. **Square and alpha-free, unlike
  every other icon we ship**, and that is deliberate:

  - Apple applies its own corner mask. An icon that arrives already rounded on a
    contrasting ground renders *double-masked*, with the badge's dark corners
    showing as wedges inside Apple's rounding.
  - Apple rejects an alpha channel outright; the rest of our exports are RGBA.

  So do **not** substitute `mobile/resources/icon.png`, which is the same size and
  has no alpha but carries the badge's rounded corners baked in. That file is
  correct for Android, where the launcher does its own masking of a pre-rounded
  source, and wrong here.

Rendered by `WebSite/brand/render_marks.py` from the same geometry as every other
surface (`tinyassets/desktop/icon_gen.py`), via `draw_mark(1024, tile=True,
radius=0)`. Re-render when the mark changes; the committed PNG is canonical.

Squaring the badge does not crop or add anything — it reveals the sky and ground
that the rounded badge clips at the corners.

Screenshots are **not** here yet. Apple wants roughly 19.5:9 (1290×2796 for 6.7",
1320×2868 for 6.9"); the Play captures next door are 1080×1920 (9:16) and cannot
simply be resized to fit. They need re-capturing at the iPhone aspect — see §6 of
the runbook.
