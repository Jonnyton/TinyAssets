# Google Play listing assets

Staging for the Play Console listing (see `../google-play-launch.md`). All rendered
2026-09-02 from the TinyAssets mark (`assets/icon.png`, exported by
`WebSite/brand/render_marks.py`) and the live app.

- `icon-512.png` — 512×512 listing icon (no alpha).
- `feature-graphic-1024x500.png` — the required feature graphic (logo + wordmark + tagline).
- `screenshots/01-universe-conversation.png`, `02-connect-subscription.png` — 1080×1920
  (9:16) phone captures of the live web app at phone width: a real universe
  conversation and the Connect view. Re-capture per §10 of the runbook when the
  app's look changes.

**Production screenshot gate (2026-09-03):** both captures have valid Play dimensions,
but `01-universe-conversation.png` shows an internal universe id and implementation/debug
discussion. Replace it with a clean real conversation before production review; do not
manufacture a mock app screen. The browser automation bridge timed out during the
2026-09-03 audit, so no honest replacement was captured in that pass.

The app's own launcher icon + splash come from `mobile/resources/` (see its README);
this folder is only what the store listing uploads.
