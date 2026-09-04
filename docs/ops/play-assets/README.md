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
run, or credential identifiers.

**Live Console correction (2026-09-03):** the clean `01-sign-in.png` was uploaded,
the private `01-universe-conversation.png` was removed from the default listing, and
the draft was saved. Re-opening both attachment details after the save verified the
live pair as `01-sign-in.png` and `02-connect-subscription.png`. The old image may
remain in Play's account-level asset library, but it is not attached to the listing.

Removing an accidentally exposed/private listing asset and replacing it with an
already prepared, visually inspected, verifier-clean asset is routine corrective work;
it does not require a new permission ask. Sending a listing for review or publishing
it remains a separate consequential boundary.

The app's own launcher icon + splash come from `mobile/resources/` (see its README);
this folder is only what the store listing uploads.
