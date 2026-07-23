# Mobile app release convention (website download button)

Status: predicted/pre-wired 2026-07-03, ahead of the native app scaffold
landing on `main`. Read this before wiring the mobile app's build/release
pipeline so the existing website download button lights up automatically —
no further website edit needed.

## Why this exists

The website (`WebSite/site/`) has a "Download SDK" button (home hero, start
hero, and the /start "take me with you" section) that needs to work the
instant a real Android build ships, with no follow-up site edit. Rather than
live-check an API or guess a version number, the button is a plain, static
link to the exact URL the real release will occupy — a direct GitHub
release-asset URL, which doesn't need any API call to resolve. Host it at
that fixed tag/asset name and the button starts working immediately.

## The contract

- **Release tag:** `android-latest` — a rolling release, replaced (not
  accumulated) on every build. Delete-then-recreate the tag/release on each
  publish; the URL below always points at whatever currently occupies it.
- **Asset name:** `tinyassets-android-latest.apk` — must be exact; this is a
  static link, not a live API lookup, so there's no fallback pattern-matching.
- **Repo:** `Jonnyton/TinyAssets` (current name as of 2026-07-03 — see the
  TinyAssets rename migration row in `STATUS.md` if this ever changes again).
- **The link itself:** `https://github.com/Jonnyton/TinyAssets/releases/download/android-latest/tinyassets-android-latest.apk`
  — a direct GitHub release-asset download URL. Publish a release with that
  exact tag and asset name and this URL starts serving the real APK; until
  then it 404s (acceptable — the button is wired for the predicted, most-likely
  outcome, not gated on it).

## Where each side lives

| Piece | Path |
|---|---|
| The download URL constant | `WebSite/site/src/lib/mcp/appRelease.ts` (`ANDROID_DOWNLOAD_URL`) |
| Shared button component | `WebSite/site/src/lib/components/AppDownload.svelte` (`compact` = hero button, `full` = /start card) |
| Home page hero button | `WebSite/site/src/routes/+page.svelte` — third button in `.cover__actions`, next to "Put me to work" |
| Start page hero button + full section | `WebSite/site/src/routes/start/+page.svelte` — third button in `.cover__actions`, and "entry five · take me with you" |
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
