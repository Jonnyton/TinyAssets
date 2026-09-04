# iOS App Store upload requires Xcode 26

**Filed:** 2026-09-03  
**Verified:** 2026-09-03, GitHub-hosted `macos-15`, workflow run `33824990349`  
**Severity:** P0

## Source (verbatim)

> Validation failed (409) SDK version issue. This app was built with the iOS 18.5 SDK. All iOS and iPadOS apps must be built with the iOS 26 SDK or later, included in Xcode 26 or later, in order to be uploaded to App Store Connect or submitted for distribution.

## Finding

The protected signed-build job succeeds with the certificate, provisioning profile,
bundle ID, entitlements, and six CI secrets, but `macos-15` defaults to Xcode 16.4.
App Store Connect rejects that otherwise valid IPA before upload. GitHub's official
`macos-15` image inventory on 2026-09-03 lists Xcode 26.3 at
`/Applications/Xcode_26.3.app` while retaining Xcode 16.4 as the default.

The local fix explicitly selects Xcode 26.3 in both `.github/workflows/ios-build.yml`
and `.github/workflows/ios-release.yml`, then fails closed unless the selected
`iphoneos` SDK begins with `26.`. `tests/test_mobile_ios_release.py` guards both
workflows; 16 focused tests pass locally. Local `actionlint` is unavailable, so CI is
the authoritative workflow-lint oracle.

The first default-model dispatch exited 1 after eight seconds with empty stderr. A
separate foreground check, `claude -p "Reply only: READY" --model fable`, returned
"You've hit your monthly spend limit." Jonathan clarified that only Fable was
exhausted, so the required read-only review ran once with Claude Opus against exact
revision `6ccb3d24`. It exited 0 after 274 seconds and explicitly returned **AGREE,
land it**; the verbatim receipt is
`docs/audits/2026-09-03-ios-xcode26-opus-review.md`.

## Exit

1. Push reviewed revision `6ccb3d24` and require the `actionlint` and `build-ios` checks.
2. Merge, dispatch `iOS signed release` from `main` with TestFlight upload enabled,
   and verify the build appears in App Store Connect.
3. Delete this concern when the Xcode 26 upload is accepted.
