# iOS review-recovery access receipt — 2026-09-10

Scope: TinyAssets App Store Connect app `6808434444`, iOS version `1.0`,
Build `1.0.0 (3)`.

- The Account Holder generated a separate App Store Connect team key named
  `TinyAssets Release` with the App Manager role. Its one-time private key is
  backed up in Windows Credential Manager and synchronized to the protected
  GitHub `app-store` environment; no private-key value is stored in this
  repository.
- Protected verify-only workflow run `34562826944` completed successfully and
  proved that the replacement key can read Apple's retained App Review account,
  matching password, required-account flag, and all four contact fields.
- The same verified contact and demo-account fields were copied to Apple's
  separate TestFlight beta-review record through the official App Store Connect
  API. The TestFlight feedback contact and live privacy-policy URL were also
  saved.
- The Account Holder was added to the existing `Internal` TestFlight group.
  Build 3 remained attached; refreshing only that build-to-group relationship
  changed Apple's tester state from `NOT_INVITED` to `INVITED`. The authenticated
  App Store Connect UI then showed **Internal Group · 1 Tester · 1 Build** and
  **Invited — Sep 10, 2026**.
- App Store Version 1.0 now has `releaseType=AFTER_APPROVAL`, so approval will
  release it automatically rather than leave it waiting for a manual release.
  The United States remains enabled within the 148 non-EU storefronts; the 27 EU
  storefronts remain excluded.

Apple's App Review state remains **Rejected / Unresolved Issues**. No reviewer
reply or resubmission was sent in this step. The remaining evidence is the
latest-iOS physical-iPhone recording requested under Guideline 2.1; after that
recording is attached, the prepared written response can be sent and the intact
submission resubmitted.
