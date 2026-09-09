# iOS App Review submission receipt — 2026-09-09

TinyAssets iOS 1.0, build 1.0.0 (3), was submitted to Apple App Review from
the authenticated App Store Connect account on 2026-09-09 at 02:32 PDT.

- Apple ID: `6808434444`
- Bundle ID: `io.tinyassets.app`
- Submission ID: `5c6e4844-2ca2-438c-8aec-a189efb0ebb2`
- App Store Connect status after reload: **Waiting for Review**
- Release mode: **Manually release this version**
- Initial availability: 148 non-EU storefronts, including the United States;
  all 27 EU storefronts are **Not Available**
- App-specific DSA declaration: **non-trader**, consistent with the initial
  release being unavailable in the EU

Before submission:

1. PR #3616 (`caccc05c`) published the privacy notice as privacy v1.0,
   effective 2026-09-09, while keeping the unrelated terms and token
   disclosures explicitly draft. Required tests, the static build, the
   phone/desktop sweep, visual inspection, and independent Claude review
   completed before merge.
2. Manual Pages deployment run `34334601760` succeeded. A fresh background
   browser load of `https://tinyassets.io/legal/#privacy` showed the published
   status and the complete iOS privacy section.
3. App Store Connect saved that URL and published the four declared data types:
   Email Address, User ID, Other User Content, and Other Data Types. Each is
   used for App Functionality, linked to identity, and not used for tracking.
4. The dedicated `play-review@tinyassets.io` reviewer identity was reset and
   verified through the protected `app-store` environment. Verify-only run
   `34330379943` confirmed Apple retained the reviewer username, matching
   password, sign-in requirement, and all four contact fields. No secret or
   personal phone value is stored in this repository.
5. **Add for Review** succeeded, the resulting one-item draft submission was
   submitted, and App Store Connect then showed **Waiting for Review** with the
   submission ID above.

The canonical MCP handshake, tool-list/read probe, and wiki write/read
round-trip were green after publication. A production daemon restart run
`34334878431` also completed successfully. The broader scheduled uptime
workflow remains red on its pre-existing supervisor-liveness and revert-evidence
contract mismatch, tracked separately in
`docs/concerns/2026-09-08-scheduled-uptime-probes-remain-red.md`; it did not
invalidate the successful public request/response probes or this App Store
submission.

The next external state transition belongs to Apple. When Apple approves the
version, use **Release This Version**, then verify the United States product
page can install the app before calling the launch complete.
