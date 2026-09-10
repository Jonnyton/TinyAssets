# iOS App Review submission receipt — 2026-09-09

TinyAssets iOS 1.0, build 1.0.0 (3), was submitted to Apple App Review from
the authenticated App Store Connect account on 2026-09-09 at 02:32 PDT.

- Apple ID: `6808434444`
- Bundle ID: `io.tinyassets.app`
- Submission ID: `5c6e4844-2ca2-438c-8aec-a189efb0ebb2`
- App Store Connect status after submission: **Waiting for Review**
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

## App Review response — 2026-09-10

Apple changed the submission to **Unresolved Issues** and iOS 1.0 to
**Rejected**. The first authenticated UI read at 2026-09-10 11:27 PDT showed a
single issue, **Guideline 2.1 - Information Needed - New App Submission**. Apple
did not report a crash, broken login, metadata defect, or Guideline 4.2 finding.
Because the developer account has a limited review history, Apple requested:

1. a screen recording captured on a physical device running the latest iOS,
   beginning with app launch and demonstrating the ordinary user flow;
2. the app's purpose, target audience, problem solved, and user value;
3. setup and access instructions, including review credentials and sample files;
4. the external services used for core functionality;
5. regional differences, or confirmation that the app behaves consistently; and
6. any authorization evidence for regulated or protected third-party material,
   if applicable.

The recording must also show account login and account deletion. TinyAssets has
no public or user-to-user content surface, so content reporting and blocking are
not applicable; user prompts, attachments, and universe output are private to
the signed-in user's universe. The submitted build has no purchase, subscription,
upgrade, advertising, or paid-content UI.

At 2026-09-10 12:20 PDT the isolated App Review account completed a fresh,
rendered production turn in universe `u-01m26ac5ds3t48mktxykvgnvwg`. Its
review-only OpenRouter connection uses the zero-cost `openrouter/free` router,
has a $5 hard key ceiling, and expires on 2026-10-10. The two superseded test
keys were deleted. Reviewers therefore land in a working private universe and
do not need to connect a provider or supply payment information. The production
receipt showed the selected free provider returned a normal answer through the
same `/mcp/app` surface used by the iOS shell. OpenRouter's provider log recorded
the two production calls at $0.00, and a full page reload restored the same
question and answer from the canonical conversation.

The same session exposed and fixed an independent host-watchdog packaging fault:
PR #3828 (merge `41034bf0171463d328e40c8eed84b0f66bfcc912`) now installs the
canary helper beside the watchdog. No later auto-restart incident was created
after the final pre-fix event at 2026-09-10 19:04:11 UTC, and the canonical
authenticated public probe was green after convergence.

PR #3830 (merge `f497050f6586ae70f41e98f78c412932176a46c7`) closed the
last submitted-scope mismatch in the remotely hosted native client. Capacitor
shells now keep Voice hidden and do not initialize its capability, while the
browser-hosted client remains unchanged. The submitted binary still carries its
defensive microphone usage string, but App Review Notes, App Privacy answers,
and the reachable native product remain voice-dark. Deploy run `34523794549`
published that exact revision, passed the authenticated public MCP canary with
the canonical handles, and verified the protected release receipt. A fresh
production fetch contained the default-hidden Voice controls and both native
gates; a signed-in browser reload still rendered Voice, proving the web-only
surface remained available.

Protected read-only workflow run `34522734323` reverified the retained reviewer
account/contact block plus `submission_state=UNRESOLVED_ISSUES`,
`app_store_state=REJECTED`, manual release, and `listed_in_us=false` at
2026-09-10 12:50 PDT. The United States remains in the
148 enabled non-EU storefronts and all 27 EU storefronts remain excluded. Do not
cancel the submission. Resubmit only after the physical-iPhone recording and the
complete written response have both been attached/saved in App Store Connect.
