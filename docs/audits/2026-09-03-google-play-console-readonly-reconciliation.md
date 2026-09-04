# Google Play Console read-only reconciliation

**Date:** 2026-09-03
**Environment:** authenticated Google Play Console in Chrome. The initial inventory
was read-only. Subsequent explicitly authorized corrections saved the safe listing
asset pair, the evidence-backed Advertising ID answer, and the verified dedicated
reviewer credentials described below. Nothing was sent for review, submitted, invited,
rolled out, or published.
**Candidate evidence:** `codex/android-store-release`; Android code head
`d7bb24d1c28a64ed5c50b2ad7608916227899dd2`, verified by release run
`33823719041`. Later commits in this audit lane are documentation-only.

## Live app record

- App: **TinyAssets**, package `io.tinyassets.app`.
- App status: **Draft**; test status: **Internal testing**; installed audience: `0`.
- Production: **Inactive**.
- Dashboard setup: **8 of 11 complete**.
- Closed testing: `0` testers opted in; Play says app setup must finish before a
  closed test can start.
- Production access remains disabled until a qualifying closed test has at least 12
  continuously opted-in testers for at least 14 days.

## App content: one declaration needs attention

The App content overview—not the coarser dashboard counter—is authoritative for the
remaining declarations:

| Declaration | Live state | Prepared next state |
|---|---|---|
| Sign in details | **Actioned** 2026-09-03; saved **Yes** with the `Play Reviewer` credential set, not sent for review | Dedicated address `play-review@tinyassets.io` routes through the TinyAssets mailbox to the founder-controlled Gmail. WorkOS user `user_01M1N3BFV6N1V1C9PP1NEWCCHP` is Verified + Active, has no organization or connected accounts, and shows sign-in count **2**. Both password sign-ins reached the same isolated empty universe without MFA or an email challenge after verification. The saved instructions identify the **Skip for now** path; the optional partner-device feedback switch is off. The mistaken Simkal plus-alias user was deleted only after this replacement was proven and saved. |
| Target audience and content | **Actioned** 2026-09-03; target age **18 and over**, not sent for review | No remaining form work. Re-check only if the intended audience changes. |
| Data safety | **Actioned** 2026-09-03; not sent for review | Preview still shows the staged collected types, no third-party sharing, encryption in transit, and account deletion. Account creation was corrected from OAuth-only to **Username and password + OAuth** after the reviewer flow proved the production password method. |
| Advertising ID | **Actioned** 2026-09-03; saved **No**, not sent for review | Re-open if the exact uploaded artifact or any native/JavaScript SDK dependency changes. |
| Foreground service permissions | Unstarted | Console detects `FOREGROUND_SERVICE_DATA_SYNC`; use **Data sync → Network processing → Other** for the user-initiated local OAuth callback listener, then supply observed behavior and a redacted phone video. |

## Data safety declaration observed in Console

The saved Actioned declaration—not merely the runbook—currently contains:

- Collects or shares required data: **Yes**.
- All collected data encrypted in transit: **Yes**.
- Account creation: **Username and password** and **OAuth**.
- Account deletion URL: `https://tinyassets.io/account`.
- Separate partial-data deletion without account deletion: **No**.
- Selected types: Personal info (`Email address`, `User IDs`), Messages (`Other
  in-app messages`), Files and docs, and App activity (`Other user-generated
  content`). Each handling questionnaire shows **Completed**.
- Audio files: `0/3` selected. This must remain true while voice is dormant; use the
  conditional evidence branch in `docs/ops/google-play-launch.md` before enabling it.
- Preview: no third-party sharing; collected types as above; encrypted in transit;
  account-deletion link and privacy policy present.

The preview also says the developer has not provided **partial data deletion without
deleting the account**. That follows the saved `No` answer; it does not negate the
separately displayed account-deletion link.

## Code-backed Advertising ID answer

`mobile/package.json` contains only Capacitor app/browser/core/platform, splash, and
status-bar dependencies—no ads, analytics, Firebase, or Play advertising SDK. More
importantly, `mobile/scripts/verify_android_release.py` uses an explicit merged-manifest
permission allowlist. `com.google.android.gms.permission.AD_ID` is absent; if any
dependency adds it, the verifier fails with `permission drift` before the bundle gate
can pass. The Play draft should therefore answer **No** only for an exact bundle that
passes the merged-manifest verifier.

Re-verification on 2026-09-03, Windows host:

- `gh run download 33797592515 --name tinyassets-android-debug-apk` retrieved the
  version `1 (1.0)` artifact used for the baseline/internal-release evidence. Its
  SHA-256 is
  `5baadde6f09c0afcfcc34a0ccdc76613d3744280d7865abe05c6012bc548689e`, matching
  the recorded artifact exactly.
- Android build-tools 36.0.0 `aapt dump permissions app-debug.apk` reports only
  `INTERNET`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, and Capacitor's
  package-scoped non-exported receiver permission. It does not report
  `com.google.android.gms.permission.AD_ID`.
- The authenticated Play Console's **App bundles and APKs using sensitive
  permissions** view lists uploaded version `1 (1.0)` on Internal testing, first
  published 2026-09-03. Expanding that exact row reports only
  `android.permission.FOREGROUND_SERVICE_DATA_SYNC`; Play does not report `AD_ID` for
  the shipped artifact.
- Exact candidate head `d7bb24d1c28a64ed5c50b2ad7608916227899dd2` passed Android
  release run `33823719041`. The log records version `1.0.1 (2)`, a successful real
  `bundleRelease`, and a successful `verify_android_release.py --merged` check. That
  check's permission allowlist excludes `AD_ID` and fails on any unexpected merged
  permission.
- Parsing all 226 package entries in `mobile/package-lock.json` found no dependency
  name matching advertising, ads, analytics, Firebase, Google Mobile Ads, or Play
  Services. The runtime dependencies remain the Capacitor shell packages listed in
  `mobile/package.json`.

Exact truthful declaration for these artifacts: **Does your app use advertising ID?
No.** Re-open this decision if the uploaded artifact or any native/JavaScript SDK
dependency changes.

With explicit user authorization, **No** was selected and saved on 2026-09-03. Play
displayed **Change saved. Send for review in Publishing overview.** The form then
showed No selected with Save and Discard disabled. Returning to App content reduced
**Need attention** from five to four; **Actioned** showed seven declarations and listed
Advertising ID with last-edited date Sep 3, 2026. The change was not sent for review.

## Listing asset discrepancy — resolved 2026-09-03

With explicit user authorization, the clean
`docs/ops/play-assets/screenshots/01-sign-in.png` was uploaded, the private
`01-universe-conversation.png` attachment was removed, and the default-listing draft
was saved. Play displayed both **Your changes have been saved** and **Draft saved**.
Re-opening the two attachment-detail panels after the save verified the live pair as:

- `02-connect-subscription.png`, 1080×1920, uploaded 2026-09-02;
- `01-sign-in.png`, 540×960, uploaded 2026-09-03.

The old file remains visible in Play's account-level asset picker, but is no longer
attached to the listing. The listing was not sent for review or published.

## Foreground-service evidence still required

The Console directly reports that an uploaded artifact contains
`FOREGROUND_SERVICE_DATA_SYNC`. It offers Data sync categories for network processing,
local processing, and other tasks. The staged callback-listener explanation maps to
**Network processing → Other**, not backup/restore or a local-processing category.
Do not save the declaration until the Play-installed phone proves notification,
success, cancellation, timeout, and teardown behavior and supplies the redacted video
described in `docs/ops/android-release-verification.md`.
