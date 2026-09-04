# TinyAssets App Store submission packet

Prepared 2026-09-03 from the shipping app, Apple Developer's current form
documentation, and the live Apple Developer account. This is copy-ready staging,
not authorization to publish declarations, upload a build, submit for review, or
release the app.

## Account and immutable identifiers

| Field | Value / action |
|---|---|
| Membership | Active; program resources, Team ID, and renewal date visible |
| Current agreements | Apple Developer Program License Agreement and Apple Developer Agreement accepted 2026-09-03; App Store Connect Terms of Service V100 (last updated 04 June 2018) accepted by the founder 2026-09-03 |
| Platform | iOS |
| App name | `TinyAssets` |
| Explicit bundle ID | `io.tinyassets.app` |
| Bundle ID description | `TinyAssets iOS` |
| App ID registration | Complete 2026-09-03; verified in the signed-in Apple Developer Identifiers list |
| App Store Connect record | Created and verified 2026-09-03; Apple ID `6808434444`; iOS 1.0 is **Prepare for Submission** |
| SKU | `tinyassets-ios` |
| User access | Full Access for the existing Account Holder; the live form disables Limited Access and no additional user is selected |
| Primary language | English (U.S.) |
| Version | `1.0.0` |
| Build | Use the numeric GitHub Actions run number |
| Primary category | Productivity |
| Secondary category | None |
| Price | Free; no in-app purchases in this build |
| TestFlight | Empty internal group `Internal`; automatic distribution off; 0 testers and 0 builds |

The explicit App ID and App Store Connect record are complete. The next persistent
portal mutation is creating signing credentials. Do not create a certificate,
private key, provisioning profile, or App Store Connect API key without explicit
action-time approval.

## Product-page metadata

- **Name (30 characters maximum):** `TinyAssets`
- **Subtitle (30 characters maximum):** `Your own AI universe`
- **Promotional text (170 characters maximum):**
  `A persistent AI universe that runs real, multi-step work on your own LLM — the same universe on web, phone, and your chatbot.`
- **Keywords (100 bytes maximum; each longer than two characters):**
  `assistant,agent,automation,workflow,universe,productivity,LLM,chat,projects,research`
- **Support URL:** `https://tinyassets.io/legal#contact`
- **Marketing URL:** `https://tinyassets.io`
- **Privacy Policy URL:** `https://tinyassets.io/legal#app-data`
- **User Privacy Choices URL:** `https://tinyassets.io/account`
- **Copyright:** `2026 TinyAssets`

The support and privacy anchors are reachable on the public site as of 2026-09-03.
Do not enter or publish the privacy URL yet: the deployed page still omits iOS,
and the legal page explicitly remains Draft v0 pending counsel. PR #2798 stages
the iOS wording but does not resolve the legal-review gate.

**Description:**

> TinyAssets gives you your own AI “universe” — a persistent, personified agent
> that lives in the cloud and runs real, multi-step work toward your goals,
> around the clock, whether you’re here or not.
>
> It’s the same universe everywhere. Open the app on your phone, the web app in
> a browser, or connect it to a chatbot like Claude or ChatGPT — sign in and it’s
> one continuous conversation and one shared memory across every surface.
>
> Your universe, your compute. You bring your own AI: connect a Claude or ChatGPT
> subscription, or add any API service right in the app. The platform never
> charges you for AI — it runs on the compute you give it.
>
> What you can do:
>
> • Chat with a universe that remembers you and grows into your projects.
> • Build multi-step automations and run them for real.
> • Add the channels and services you want through a user-composable node system.
> • Inspect runs and results so you can check the evidence.
>
> TinyAssets is open and honest by design: your data stays tied to your account,
> your AI credentials go straight to a secure vault, and the platform is
> transparent about what’s live.
>
> Get started in seconds — sign in and say hello to your universe.

Review notes should say that this is a Capacitor shell pinned to
`https://tinyassets.io/mcp/app`, not a general-purpose web browser. There is no
purchase or upgrade UI in the native shell. Sign-in, provider connection, chat,
text-file attachment, account deletion, and the privacy link are the critical
review paths. Private reviewer-account details belong only in App Store Connect,
never in this repository.

## TestFlight copy — staged, not transmitted

- **Beta App Description:**
  `TinyAssets is a persistent AI universe for real multi-step work. This beta validates the installed iPhone shell, sign-in return, conversation continuity, file attachment, and recovery behavior before App Store submission.`
- **What to Test:**
  `Test sign-in and the return to TinyAssets, reconnect after force-quit, send a substantive message, confirm the same conversation on web, attach a small text file, open Account and Privacy, and recover after briefly disabling the network. Voice, purchases, and ads are not included. Report any blank screen, dead sign-in callback, lost conversation, inaccessible control, layout overflow, or recovery failure.`
- **Feedback Email:** enter an account-holder-controlled support address directly
  in App Store Connect. Do not commit it here.
- **Beta App Review Information:** provide a dedicated disposable review account
  and account-holder contact details directly in App Store Connect. Never place
  credentials or personal contact details in this repository.

Keep automatic tester notification off until the founder approves invitations.
Internal testing comes first. External testing may trigger TestFlight App Review
and is a separate submission boundary.

## Accessibility Nutrition Label plan — voluntary, not published

Apple's label is voluntary as of 2026-09-03 but is expected to become mandatory.
Do not claim support from web checks alone: Apple requires every common task to
work with the named feature on the named device. The common-task set for iPhone is
first launch, sign-in, provider connection, conversation, text-file attachment,
Account/Privacy navigation, sign-out, and recovery after network interruption.

| Feature | Current basis | Evidence required before claiming support |
|---|---|---|
| VoiceOver | The shared client uses semantic controls and ARIA status regions. | Complete every common task on the signed iPhone build with VoiceOver. |
| Voice Control | Primary actions are ordinary labeled controls. | Complete every common task using Voice Control without touch. |
| Larger Text | The layout is responsive, but iOS Dynamic Type behavior is unproven in the WebView. | Test the largest accessibility text sizes with no clipped or unreachable controls. |
| Dark Interface | The app has a dark interface. | Verify every common-task screen, system prompt, and external-auth transition. |
| Differentiate Without Color Alone | Primary states use words or icons in addition to color. | Verify errors, connection status, disabled controls, and focus states on device. |
| Sufficient Contrast | Automated site sweeps are clean, but they do not prove the signed app flow. | Run contrast checks across every common-task state on device. |
| Reduced Motion | No support claim is staged. | Audit all animation and add/verify reduced-motion behavior before claiming. |
| Captions / Audio Descriptions | The voice-dark build contains no prerecorded audiovisual content. | Mark not applicable unless audiovisual content ships; re-evaluate if it does. |

Leave all accessibility responses unclaimed until the signed-device matrix is
complete. Publishing the label is a separate founder approval and cannot be
undone for a published device response.

## App Privacy draft — first release with realtime voice dark

Choose **Yes, we collect data from this app**. This table is the conservative
draft for the shipping app on `main`; each type is linked to the user's identity,
used only for the named purpose, and not used for tracking.

| Apple data type | What the app sends or stores | Purpose |
|---|---|---|
| Contact Info → Email Address | WorkOS sign-in email | App Functionality |
| Identifiers → User ID | WorkOS account identifier | App Functionality |
| User Content → Other User Content | Conversation text and user-selected text/code/document attachments | App Functionality |
| Other Data → Other Data Types | Provider credential or connection material deposited by the user into the secure vault | App Functionality |

For every row: **linked to identity: Yes**; **tracking: No**; advertising,
third-party advertising, and developer advertising purposes: **No**. The app has
no advertising SDK, analytics SDK, mobile crash-reporting SDK, location, contacts,
photos, camera, health, fitness, or payment collection. The native shell accepts
text-like attachments only. Payment-card data entered on a processor-hosted web
page is not collected by this app, and the native shell exposes no checkout.

WorkOS and the infrastructure provider process data to operate the service. A
user-connected AI provider receives user content at the user's direction. Before
publishing the label, confirm the current vendor contracts and production data
path support the intended service-provider/user-directed-transfer treatment.
App Store Connect's **Publish** confirmation is a separate founder approval.
The live 2026-09-03 questionnaire did not offer a separate Account Management
purpose; all four saved draft entries use App Functionality only.

### Conditional voice delta

The voice implementation is not on `main` and must stay dark in the first build
unless it is deliberately reconciled and passes physical-iPhone proof. If a
voice-enabled build is chosen, add **User Content → Audio Data**, conservatively
marked linked to identity, for App Functionality, with tracking **No**, unless a
fresh review of the production OpenAI retention configuration establishes that
Apple's collection definition excludes the transient audio. TinyAssets retains
canonical conversation text and does not persist raw audio; the client sends raw
microphone audio directly to OpenAI for live speech. Re-approve the entire label
after that production review.

## Age-rating draft

The app is not Made for Kids, has no parental controls or age-assurance feature,
and the legal minimum age is 18. The WebView is pinned to TinyAssets; therefore
**Unrestricted Web Access: No**. Private AI conversation is not broad
distribution to other users; therefore **User-Generated Content: No**,
**Messaging and Chat: No**, **Social Media: No**, and **Advertising: No** under
Apple's current definitions.

Because responses come from a user-selected generative AI provider, use the
conservative content draft below rather than claiming that open-ended output can
never contain mature material:

- Infrequent or Mild: profanity/crude humor; horror/fear; alcohol/tobacco/drug
  references; medical/treatment information; health/wellness topics;
  mature/suggestive themes; sexual content/nudity; cartoon/fantasy violence;
  realistic violence; guns/other weapons.
- None: graphic sexual content/nudity; prolonged graphic or sadistic realistic
  violence; contests; loot boxes; simulated gambling; gambling.
- Age Categories and Override: override to **18+** to align the storefront with
  the product's 18+ legal minimum, after founder confirmation.

This is a draft declaration, not a completed rating. The founder must compare it
with the exact live questionnaire and approve before saving.

## Export compliance

The shell contains no custom, proprietary, or non-standard cryptography. It uses
operating-system WebKit/network APIs for ordinary HTTPS/TLS. The generated
`Info.plist` now declares `ITSAppUsesNonExemptEncryption = false`, the value Apple
documents for apps that use no encryption or only encryption exempt from export
documentation. No export document is expected for this binary.

If App Store Connect asks whether the app uses encryption, follow the exact live
wording: disclose the ordinary OS-provided HTTPS/TLS path and select the branch
for exempt encryption. Do not interpret a broad “uses encryption” question as a
claim that the app sends plaintext. Any future custom crypto or new native SDK
requires a fresh determination.

## Screenshot asset manifest

The capture contract is checked in at
`app-store-assets/screenshot-manifest.json`. Capture one to ten PNG or JPEG images
with no alpha channel. Prefer one portrait 6.5-inch set at an Apple-accepted size
(`1242×2688` or `1284×2778`); the live App Store Connect form presented these
under the 6.5-inch display slot on 2026-09-03 and scales them for
smaller iPhones. Use an actual iPhone or iOS Simulator build, not resized Android
captures or a browser mockup.

The five planned scenes are: signed-in universe home, a substantive conversation,
an inspectable work result, provider connection, and account/privacy controls.
Use a dedicated clean review universe; remove personal content, credentials,
notifications, and debug UI. The icon asset is already complete at
`mobile/resources/icon.png`; the release build installs and validates it.

## TestFlight and physical-device smoke checklist

Run this against the exact signed artifact before any App Review submission:

1. Record source SHA, version, build number, IPA checksum, iOS version, and iPhone model.
2. Fresh-install; confirm the icon, splash, safe areas, portrait layout, keyboard, and no blank/offline shell.
3. Complete sign-in and verify the native OAuth return opens TinyAssets, not Safari or a dead callback page.
4. Force-quit/relaunch and background/foreground; confirm the session recovers without duplicating a universe.
5. Connect a test provider, return to chat, send a message, and receive the same canonical conversation on web.
6. Attach an allowed text file; verify it is shown accurately and no photo-library permission is requested.
7. Open Account and the privacy link; verify the deletion path is present. Exercise deletion only with a disposable test account.
8. Confirm the native build contains no plan, upgrade, Stripe checkout, ads, tracking prompt, or unrestricted browser.
9. Disable network, reopen, restore network, and verify the shell fails clearly and recovers.
10. Inspect App Store Connect/Xcode diagnostics for crashes, hangs, signing errors, and entitlement mismatches.
11. If voice is dark, confirm no Voice control is exposed and no microphone prompt occurs.
12. If voice is enabled, separately prove disclosure, allow/deny, start/stop,
    interruption, timeout, force-quit, page change, and backgrounding on a physical
    iPhone; confirm every microphone track is released and then re-approve App Privacy.

Any critical-flow failure holds the build. A web regression rolls back by
reverting the compatible `/mcp/app` deployment. A native-shell failure requires
a higher build/version; the old binary cannot be restored over an installed new
one, so the server must remain compatible with the last released shell.

## Exact portal sequence from the active membership

1. **Complete 2026-09-03:** Developer portal → Certificates, IDs & Profiles →
   Identifiers → **+** → App IDs → App → description `TinyAssets iOS` → explicit
   bundle ID `io.tinyassets.app` → Register. The signed-in Identifiers list showed
   the resulting name and exact bundle ID.
2. **Complete 2026-09-03:** the founder accepted App Store Connect Terms of Service
   V100 (last updated 04 June 2018), then confirmed creation of the TinyAssets app
   record. Apple ID `6808434444`; iOS 1.0 is **Prepare for Submission**.
3. **Partially complete 2026-09-03:** product-page copy, subtitle, Productivity
   category, copyright, support/marketing URLs, and manual release are saved. The
   four-type App Privacy draft is fully configured for App Functionality, linked
   to identity, and no tracking, but it is not published and its legal-policy URLs
   remain blank. An empty `Internal` TestFlight group exists with automatic
   distribution off. No tester or build was added. Stop at any new agreement,
   DSA trader-status choice, privacy publication, or other legal declaration.
4. On a Mac/Xcode, create or select an Apple Distribution certificate and an App
   Store Connect provisioning profile for the exact bundle ID. Creating these
   persistent credentials requires explicit action-time approval.
5. Export the `.p12` and profile securely, create an App Store Connect API key
   with the minimum role needed for upload, and store the six values only as
   protected `app-store` environment secrets. API-key creation requires explicit
   action-time approval.
6. Dispatch **iOS signed release** from `main` with version `1.0.0` and
   `upload_to_testflight=false`. Approve the protected environment, download the
   IPA manifest/checksum, and complete the device smoke pass.
7. Only after explicit upload approval, re-dispatch the same source/version with
   upload enabled. TestFlight upload does not submit App Review.
8. Complete App Privacy publication, age rating, export answer, screenshots,
   review notes, availability, and DSA status only with the founder's truthful
   approvals. Keep release mode manual.
9. Stop before **Submit for Review**. After review approval, stop again before
   **Release This Version**.

## External gates that remain

- A CSR/private key and explicit action-time approval to create the Apple
  Distribution certificate, provisioning profile, and App Store Connect API key.
- A signed build plus actual iPhone or iOS Simulator for authentic screenshots;
  a physical iPhone is required for microphone-release proof if voice ships.
- Founder approval of live privacy, age-rating, content-rights, export,
  availability, and DSA/trader declarations.
- Final founder/counsel approval of the privacy policy, followed by PR #2798 land,
  deploy, and a live check that the iOS disclosure is present.
- Explicit approval for TestFlight upload, App Review submission, and publication.

Official references checked 2026-09-03: [add a new app](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-a-new-app/),
[app information](https://developer.apple.com/help/app-store-connect/reference/app-information/app-information/),
[platform version information](https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information/),
[app privacy](https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy/),
[age ratings](https://developer.apple.com/help/app-store-connect/reference/app-information/age-ratings-values-and-definitions/),
[screenshots](https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications/),
[export compliance](https://developer.apple.com/help/app-store-connect/manage-app-information/overview-of-export-compliance/),
[TestFlight test information](https://developer.apple.com/help/app-store-connect/test-a-beta-version/provide-test-information/),
and [Accessibility Nutrition Labels](https://developer.apple.com/help/app-store-connect/manage-app-accessibility/overview-of-accessibility-nutrition-labels/).
