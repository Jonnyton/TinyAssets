# The live Play listing screenshot shows internal repo and architecture detail

**Status:** Finding. The fix needs a founder decision about what the store listing
should show, so no replacement has been made.
**Found:** 2026-09-03, while capturing the iPhone-aspect screenshots §6 of
`app-store-launch.md` still needs.
**Where:** `docs/ops/play-assets/screenshots/01-universe-conversation.png`, which
per `docs/ops/google-play-launch.md` was entered into the Play Console listing on
2026-09-02. It is public.

## What the screenshot contains

It is a phone capture of the founder's real universe mid-debugging, not a product
demo. Visible in the frame:

- **The private repo path** `jonnyton/tinyassets`.
- **Seventeen internal commit SHAs** (`71ee69318062`, `fb052471ad77`, …).
- Internal architecture vocabulary: `git_read` / `git_write` scopes,
  `source_code` nodes, `checkout_repo`, `inspect_repo`, `apply_pass_1`,
  `apply_pass_2`, `push_branch`, `open_pr`, and a `write_graph` cap.
- A candid internal blocker: *"the branch is explicitly `runnable: false`"*, and
  reasoning about whether "platform-side source-code approval" is the missing
  piece.
- The universe id `u-01kxm1vszd8hwp7em418asq8h9`.

## Why it matters beyond tidiness

1. **It is a public disclosure surface.** A store listing is world-readable and
   mirrored by scrapers. Commit SHAs plus a repo path plus internal capability
   names is reconnaissance material, and none of it was chosen for publication.
2. **It shows the app not working.** The footer reads **"WAITING ON YOU"** above
   **"Add a key yourself"** — the blocked, no-provider-connected state. The first
   impression of the product is a wall of debugging prose in an error state.
3. **A mouse cursor is baked into the image**, mid-sentence.

`02-connect-subscription.png` is fine by contrast: clean product UI, though it also
carries a cursor artifact and a visible scrollbar.

## Why I did not just replace it

A good conversation screenshot needs a *presentable* conversation. The only
universe I can drive is the founder's own, whose entire thread is internal
development chat, so the options are:

- **Compose a demo exchange** in a universe and capture that — which means writing
  into the founder's account to manufacture marketing content, and deciding what
  the product's headline example conversation should be.
- **Capture only non-conversation views** (Connect, Account) — safe, but then the
  listing never shows the core experience.

Both are the founder's call, and changing what a live public listing shows is
outward-facing. So this is filed rather than fixed.

## What to do

- Decide what the headline screenshot should show, then re-capture per §10 of
  `google-play-launch.md`, and replace the Play listing asset.
- **Do not reuse `01-universe-conversation.png` for the App Store.** The iPhone
  screenshots §6 wants are still outstanding precisely because capturing the same
  thread at 19.5:9 would carry this into Apple's listing too.
- Re-capture at 1290×2796 (6.7") or 1320×2868 (6.9") — the Play captures are
  1080×1920 and cannot be resized into Apple's aspect.
- Delete this file once the Play asset is replaced and the Apple set is staged.
