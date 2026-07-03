# Mobile app release convention (website download button)

Status: predicted/pre-wired 2026-07-03, ahead of the native app scaffold
landing on `main`. Read this before wiring the mobile app's build/release
pipeline so the existing website download button lights up automatically —
no further website edit needed.

## Why this exists

The website (`WebSite/site/`) needs a "download the app" button that is
always current, without a person editing the site every time a new build
ships. Rather than hardcode a version number or a guessed artifact URL, the
site does a live read of GitHub's Releases API for one fixed tag/asset name.
As long as CI publishes to that exact tag/name, the button works — forever,
automatically — the day the app scaffold merges to `main`.

## The contract

- **Release tag:** `android-latest` — a rolling release, replaced (not
  accumulated) on every build. Tag/release delete-then-recreate is fine;
  the site only reads the current one.
- **Asset name:** `tinyassets-android-latest.apk` — must be exact. The site
  falls back to "first asset ending in `.apk`" if the exact name is absent,
  but don't rely on that; use the exact name.
- **Repo:** `Jonnyton/TinyAssets` (current name as of 2026-07-03 — see the
  TinyAssets rename migration row in `STATUS.md` if this ever changes again).
- **Live-check endpoint:** `GET https://api.github.com/repos/Jonnyton/TinyAssets/releases/tags/android-latest`
  (public, unauthenticated, no rate-limit-sensitive polling — the site reads
  it once per page load, on demand via "Refresh GitHub").

## Where each side lives

| Piece | Path |
|---|---|
| Website live-read + honest empty state | `WebSite/site/src/lib/mcp/appRelease.ts`, `WebSite/site/src/lib/components/AppDownload.svelte` |
| Home page button (compact) | `WebSite/site/src/routes/+page.svelte` — "Take me with you" strip |
| Start page section (full, with iOS build-from-source card) | `WebSite/site/src/routes/start/+page.svelte` — "entry five · take me with you" |
| CI that should publish the release | `.github/workflows/release-android.yml` (dormant — path-filtered on `clients/android/**`, which doesn't exist on `main` yet) |

## What the mobile-app session needs to do

Nothing, if `clients/android` merges to `main` with a committed Gradle
wrapper (`gradlew`) and a standard `:app:assembleDebug` task — the workflow
above will fire on the next push touching `clients/android/**` and the
website starts working with zero further changes.

If the module layout differs (different module name, no wrapper committed,
signing requirements, etc.), update `.github/workflows/release-android.yml`
to match — keep the tag (`android-latest`) and asset name
(`tinyassets-android-latest.apk`) the same so the website doesn't need a
matching edit.

## iOS

No equivalent exists yet. Direct `.ipa` sideloading isn't realistically
downloadable without an Apple Developer Program enrollment (TestFlight or a
provisioning profile) — none is configured today. The website's iOS card
points at building from source (`clients/ios`, Xcode) rather than faking a
download button. If/when TestFlight is set up, add a public TestFlight link
to the iOS card in `AppDownload.svelte` — that's the realistic iOS
equivalent of this Android convention, not a raw `.ipa` download link.
