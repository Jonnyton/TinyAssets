# Google Play Console read-only reconciliation

**Date:** 2026-09-03  
**Environment:** authenticated Google Play Console in Chrome; read-only navigation
only. No form control was changed, no draft was saved, and nothing was uploaded,
submitted, invited, rolled out, or published.  
**Candidate branch/head:** `codex/android-store-release` at `d4cdcfc1` before this
evidence-only update.

## Live app record

- App: **TinyAssets**, package `io.tinyassets.app`.
- App status: **Draft**; test status: **Internal testing**; installed audience: `0`.
- Production: **Inactive**.
- Dashboard setup: **8 of 11 complete**.
- Closed testing: `0` testers opted in; Play says app setup must finish before a
  closed test can start.
- Production access remains disabled until a qualifying closed test has at least 12
  continuously opted-in testers for at least 14 days.

## App content: five declarations need attention

The App content overview—not the coarser dashboard counter—is authoritative for the
remaining declarations:

| Declaration | Live state | Prepared next state |
|---|---|---|
| Sign in details | Unstarted; neither Yes nor No selected | **Yes**, after a reusable reviewer account and full, non-personal review-safe access exist. |
| Target audience and content | Unstarted | Founder confirms the staged 18+ answers after Sign in details is complete. |
| Data safety | Saved draft; not submitted | Reconcile against the exact shipped data flows and founder/legal approval, then submit only after Target audience permits it. |
| Advertising ID | Unstarted; neither Yes nor No selected | **No**. The exact merged candidate manifest must continue to contain no `com.google.android.gms.permission.AD_ID`, and no dependency may introduce an advertising-ID SDK. |
| Foreground service permissions | Unstarted | Console detects `FOREGROUND_SERVICE_DATA_SYNC`; use **Data sync → Network processing → Other** for the user-initiated local OAuth callback listener, then supply observed behavior and a redacted phone video. |

## Data safety draft observed in Console

The saved draft—not merely the runbook—currently contains:

- Collects or shares required data: **Yes**.
- All collected data encrypted in transit: **Yes**.
- Account creation: **OAuth**.
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

## Listing asset discrepancy

The default store listing is **Ready to send for review**, but its first uploaded phone
screenshot is still `01-universe-conversation.png`, 1080×1920, uploaded 2026-09-02.
That is the unsafe internal/debug conversation image removed from the repository.
The replacement `docs/ops/play-assets/screenshots/01-sign-in.png` is staged and passes
the artwork verifier, but it has **not** been uploaded because upload is an explicit
boundary. The second screenshot remains present.

## Foreground-service evidence still required

The Console directly reports that an uploaded artifact contains
`FOREGROUND_SERVICE_DATA_SYNC`. It offers Data sync categories for network processing,
local processing, and other tasks. The staged callback-listener explanation maps to
**Network processing → Other**, not backup/restore or a local-processing category.
Do not save the declaration until the Play-installed phone proves notification,
success, cancellation, timeout, and teardown behavior and supplies the redacted video
described in `docs/ops/android-release-verification.md`.
