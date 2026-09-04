# Google Play listing assets

Staging for the Play Console listing (see `../google-play-launch.md`). All rendered
2026-09-02 from the TinyAssets mark (`assets/icon.png`, exported by
`WebSite/brand/render_marks.py`) and the live app.

- `icon-512.png` — 512×512 listing icon (no alpha).
- `feature-graphic-1024x500.png` — the required feature graphic (logo + wordmark + tagline).
- `screenshots/01-sign-in.png` — 540×960 (9:16) capture of the live, signed-out
  app at phone width.
- `screenshots/02-connect-subscription.png` — 1080×1920 (9:16) capture of the
  live Connect view. Re-capture per §10 of the runbook when the app's look changes.

**Production screenshot gate (2026-09-03):** the unsafe conversation capture was
removed and replaced with `01-sign-in.png`, captured directly from
`https://tinyassets.io/mcp/app` in a clean signed-out browser. Both retained captures
meet Play's dimension and aspect-ratio rules and expose no account, universe, branch,
run, or credential identifiers. They are staged only; uploading them remains an
outbound Console action.

**Live Console reconciliation (2026-09-03):** the default listing still contains
uploaded `01-universe-conversation.png` (1080×1920, uploaded 2026-09-02). The clean
`01-sign-in.png` replacement is repository-staged only. Remove/replace the Console
asset only under the explicit upload boundary; until then, the listing is not ready to
send for review even though Play labels the saved listing that way.

The app's own launcher icon + splash come from `mobile/resources/` (see its README);
this folder is only what the store listing uploads.
