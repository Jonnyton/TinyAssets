# Google Play listing assets

Staging for the Play Console listing (see ../google-play-launch.md).

- `icon-512.png` — 512×512 app icon (from mobile capacitor assets).
- `feature-graphic-1024x500.png` — required feature graphic.
- `screenshots/` — ≥2 phone screenshots captured from the live app (§10 of the runbook).

Icon + splash source live in `mobile/` (regenerate with `npm run assets`). Feature
graphic + screenshots are produced during launch prep.
