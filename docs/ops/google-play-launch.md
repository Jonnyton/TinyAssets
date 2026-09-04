# Google Play launch — drive-everything runbook

Everything needed to publish the TinyAssets Android app to Google Play. As of
2026-09-03 the app is created, the listing and declarations are filled, and a signed
bundle is live on the internal testing track, so the founder's remaining actions are:
(1) try the internal-test build on a phone, (2) enable password sign-in in WorkOS and
create a Play reviewer account — the one thing genuinely blocking the App content
rows, (3) review and submit the foreground-service declaration staged in §8a, (4) run
the closed test Play requires before production access, and (5) click **Roll out**
after review. The four upload-keystore secrets are **optional**: see §0.
All content below is copy-paste ready.

Package name (permanent once published): **`io.tinyassets.app`**
(`mobile/capacitor.config.json`). App is the Capacitor shell over
`https://tinyassets.io/mcp/app` — see `desktop-app/README.md` + `mobile/README.md`.

> **Picking this up cold? Read [`mobile-launch-handoff.md`](mobile-launch-handoff.md)
> first.** This file is the procedure; that one is where both platforms actually
> stand, what is genuinely blocked on whom, and the traps already paid for.

---

## 0. Founder-only actions (I cannot do these)

| Step | Action | Where |
|---|---|---|
| Account | ~~Create a Google Play Developer account.~~ **Done** — developer `8089695267825659874`, identity verified 2026-08-24 (Play Console mail). | https://play.google.com/console/developers/8089695267825659874 |
| Phone | ~~Verify the contact phone `+12067997835`.~~ **Done 2026-09-02 — and it was never a founder action.** It took one click in the Console and sent no SMS code, despite the padlock text implying otherwise. Try such a step before handing it over. | — |
| Payment | ~~Authorize the $25 fee.~~ **Done** with the account. | — |
| Signing key | The keystore is generated (§2, 2026-09-01). Adding its 4 values as repo secrets is **optional, not blocking** — `mobile/container/` builds and signs the bundle with no secret at all, and that is how the shipped build was made. Worth doing anyway: it turns each future release into one `gh workflow run`. One command, §3; an agent cannot run it (`gh secret set` is denied to it). | your machine → GitHub secrets |
| Console forms | Creating the app, its declarations (incl. US export laws), listing, Data safety, content rating and the internal-testing release are **form submissions on your Google account**: the agent drives them in the browser only after an explicit "yes" in chat. Those named here are **done** (2026-09-02/03); what is left needs the reviewer account below. | Play Console (agent, gated on your yes) |
| **Device check** | **The live one.** Install the internal-test build, sign in, chat once: <https://play.google.com/apps/internaltest/4701716760893982267> | your phone |
| Publish | Promote to Production → submit for review → click **Roll out**. | Play Console |

Everything else below I build/stage.

---

## 1. What ships

A signed **`.aab`** (Android App Bundle — Play's required format) produced either by
CI (`.github/workflows/android-release.yml`) or locally by `mobile/container/`, which
mirrors the same steps and needs no repo secrets — that is how the shipped bundle was
built. Signed with your **upload key**; Google
holds the real app-signing key via **Play App Signing** (recommended default). The
web app updates ship instantly (no store resubmit) — only a native-shell/config
change needs a new AAB.

---

## 1a. Target API level — Play rejects anything below 36 for a NEW app

**Caught 2026-09-03, before an upload burned a cycle.** Google's requirement
(`developer.android.com/google/play/requirements/target-sdk`) changed on
**2026-08-31**: a *new* app must target **Android 16 (API 36)** or higher. App
updates must too. Existing apps need 35 just to stay visible to new users on
current devices.

We were on Capacitor 6, whose template pins `compileSdkVersion = 34` and
`targetSdkVersion = 34` in the generated `android/variables.gradle`. That is two
levels short, and the Console refuses the bundle at upload — it is not a warning.

**The fix is the Capacitor major, not a one-line override.** Capacitor 8 defaults
to `compileSdk = 36`, `targetSdkVersion = 36`, `minSdkVersion = 24` (read straight
out of `@capacitor/android@8.5.1`'s `capacitor/build.gradle`). Overriding 34 → 36
under Capacitor 6's AGP is unsupported and would have to be re-applied on every
`cap add android`, because `mobile/android/` is generated and gitignored.

So `mobile/package.json` now pins the Capacitor 8 line, and the three mobile
workflows moved to **node 22** because `@capacitor/cli@8` declares
`engines.node >= 22.0.0`.

Two consequences worth knowing:

- **`minSdk` rises 22 → 24.** That drops **API 22 (Android 5.1)** and **API 23
  (Android 6.0)** — two levels, not one; API 21 was already unsupported. Forced by
  the template and not worth fighting for an app with no users yet.
- **The custom `LocalCallbackPlugin` survives.** Its full Capacitor surface is
  `Plugin`, `PluginCall`, `PluginMethod`, `@CapacitorPlugin`, `JSObject`,
  `getActivity()`, `getContext()`, `notifyListeners()`, the `handleOnDestroy`
  lifecycle hook, and `BridgeActivity` for the registration splice. All are
  retained in 8, and `add_app_scheme.py` still patches the same manifest and
  `MainActivity` paths.
- **The foreground service is already Android 14+ clean.** `add_app_scheme.py`
  writes the non-exported service with `android:foregroundServiceType="dataSync"`
  plus both required permissions, and the service promotes itself with the matching
  type. There is no `PendingIntent`; every service and activity launch is explicit.

**Upgrading a checkout that predates this change: delete `mobile/android` first.**
`cap sync` preserves `android/variables.gradle`, so a project generated under
Capacitor 6 keeps `minSdkVersion = 22` and compile/target 34 even after the
dependency bump — a locally built bundle would still be rejected while looking
correct. CI is immune because it always starts clean.

**Do not "fix" a future rejection by lowering the target.** The number only ever
goes up; re-check the page above before each release, because the August cutover
repeats annually.

---

## 1b. Version and release gates — generated defaults are not a release strategy

`mobile/android-release.json` is the checked-in Android release source of truth. It
records the next candidate: package `io.tinyassets.app`, version code `2`, version
name `1.0.1`, min SDK 24, target/compile SDK 36. The existing internal-track artifact
is code `1`, name `1.0`; promoting that exact artifact between tracks needs no rebuild.

Before uploading any new AAB, increase `versionCode`; Play never accepts a code it has
seen before, even on a test track. A `mobile-v<versionName>` tag must match the file's
`versionName` exactly. Both the GitHub workflow and local container now regenerate the
platform, apply the checked-in version, verify identity/SDK/permissions/artwork, run
`lintRelease`, verify Gradle's merged release manifest, sign with the pinned upload
certificate, and emit a SHA-256 file beside the AAB.

The dated evidence, smoke-test matrix, Android-vitals thresholds, track progression,
and first-release/update rollback plans live in
[`android-release-verification.md`](android-release-verification.md).

The next candidate also carries a dormant native microphone bridge for the
first-class voice lane. It requests `RECORD_AUDIO` only after a web request from the
exact production origin and a native disclosure/Continue tap, grants audio capture
only, and tears capture down when the app backgrounds. **Do not enable the web voice
flag, mention voice in the listing, or change Data safety answers until the internal
phone matrix in the verification sheet is green.** Presence of the permission is not
evidence that capture works or that audio is collected.

---

## 2. Generate the upload keystore (once, keep it secret)

**Done 2026-09-01** on the founder's machine, outside the repo:

| File | What |
|---|---|
| `~/.tinyassets/android/tinyassets-upload.jks` | the upload keystore (JKS, RSA 2048, alias `upload`, valid to 2054) |
| `~/.tinyassets/android/upload-keystore.env` | the two passwords + alias, `KEY=value` lines, mode 0600 |
| `~/.tinyassets/android/tinyassets-upload.jks.b64` | base64 of the keystore, ready for the CI secret |

Upload certificate SHA-256 (pinned in `android-release.yml`, which refuses any other):
`D0:BC:F2:FB:EA:4E:11:6D:87:DD:DD:BD:B2:4C:1E:28:53:7A:CA:77:BE:8E:69:BE:AD:52:C7:C1:C1:03:B2:11`

**Back it up** (password manager or the vault) — it is the only copy besides the
CI secret. With Play App Signing (§11.5) a lost upload key is resettable through
Play support; the app-signing key stays with Google.

Regenerate (only if lost — a new upload key then has to be registered with Play):

```bash
keytool -genkey -v -keystore tinyassets-upload.jks -keyalg RSA -keysize 2048 \
        -validity 10000 -alias upload
# choose a store password + key password; answer the name prompts (any real org/name)
```

Then base64 it for the CI secret:

```bash
base64 -w0 tinyassets-upload.jks > tinyassets-upload.jks.b64   # Linux
# macOS: base64 -i tinyassets-upload.jks -o tinyassets-upload.jks.b64
```

Keep `tinyassets-upload.jks` + both passwords somewhere safe (a lost upload key is
recoverable via Play support; a lost non-Play-App-Signing key is not — so enroll
in Play App Signing, step §6.4).

---

## 3. Repo secrets to add (Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `ANDROID_UPLOAD_KEYSTORE_B64` | contents of `tinyassets-upload.jks.b64` |
| `ANDROID_UPLOAD_KEYSTORE_PASSWORD` | the store password |
| `ANDROID_UPLOAD_KEY_ALIAS` | `upload` |
| `ANDROID_UPLOAD_KEY_PASSWORD` | the key password |

One command does all four, reading the files §2 left behind (run it in a Git Bash
at the repo root; `gh` is already logged in):

```bash
D="$HOME/.tinyassets/android"; set -a; . "$D/upload-keystore.env"; set +a
gh secret set ANDROID_UPLOAD_KEYSTORE_B64 < "$D/tinyassets-upload.jks.b64"
printf '%s' "$ANDROID_UPLOAD_KEYSTORE_PASSWORD" | gh secret set ANDROID_UPLOAD_KEYSTORE_PASSWORD
printf '%s' upload | gh secret set ANDROID_UPLOAD_KEY_ALIAS
printf '%s' "$ANDROID_UPLOAD_KEY_PASSWORD" | gh secret set ANDROID_UPLOAD_KEY_PASSWORD
gh secret list | grep ANDROID_UPLOAD_
```

Once these exist, run the **Android release AAB** workflow (Actions tab →
workflow_dispatch, or it runs on a `mobile-v*` tag) to produce the signed
`app-release.aab` artifact to upload:

```bash
gh workflow run android-release.yml && sleep 5 && gh run list --workflow android-release.yml --limit 1
gh run download <run-id> -n tinyassets-release-aab -D dist/   # after it goes green
```

---

## 4. Store listing content (copy-paste)

- **App name:** `TinyAssets`
- **Short description (≤80 chars):**
  `Your own AI universe — a persistent agent that runs real work on your own LLM.`
- **Full description (≤4000 chars):**

```
TinyAssets gives you your own AI "universe" — a persistent, personified agent that
lives in the cloud and runs real, multi-step work toward your goals, around the
clock, whether you're here or not.

It's the same universe everywhere. Open the app on your phone, the web app in a
browser, or connect it to a chatbot like Claude or ChatGPT — sign in and it's one
continuous conversation and one shared memory across every surface.

Your universe, your compute. You bring your own AI: connect a Claude or ChatGPT
subscription, or add any API service (OpenRouter's free models, or any HTTPS API)
right in the app. The platform never charges you for AI — it runs on the compute
you give it.

What you can do:
• Chat with a universe that remembers you and grows into your projects.
• Build multi-step automations ("workflows") and run them for real.
• Add the channels and services you want — the app is built on a general,
  user-composable node system, so you can wire up new integrations yourself.
• Keep your evidence where you can check it: runs and results are inspectable.

TinyAssets is open and honest by design: your data stays tied to your account, your
AI credentials go straight to a secure vault (never through chat), and the platform
is transparent about what's live.

Get started in seconds — sign in and say hello to your universe.
```

- **App category:** Productivity
- **Tags:** productivity, AI assistant, automation
- **Contact email:** jonathan.m.farnsworth@gmail.com  *(founder: confirm/replace)*
- **Website:** https://tinyassets.io
- **Privacy policy URL:** https://tinyassets.io/legal  *(see §5)*

---

## 5. Privacy policy

Play requires a public privacy-policy URL. The site's `/legal` page is the home for
it (`WebSite/site-react/app/legal/page.tsx`, deployed by the manual
`deploy-site-react.yml`). Its Privacy section now carries the four paragraphs Play's
policy asks for — what is collected (email, user id, messages, files, deposited
credential, billing records), who receives it (WorkOS, the user's own AI provider,
Stripe, hosting), how it is protected (honest about the vault not being encrypted
at rest and about the chatbot deposit path), and retention + deletion (immediate,
in-app and at `/account`, email fallback within 30 days).

Play also requires an **account-deletion path in-app and on the web** for any app
with sign-in. Both exist as of 2026-09-02: the app's **Account → Delete my
account** view (`POST /mcp/app/account/delete` → `tinyassets.account_deletion`)
and `https://tinyassets.io/account`, which documents the steps, what is removed,
what is kept, and the email route. Confirm `https://tinyassets.io/legal#app-data`
and `https://tinyassets.io/account` render before submitting.

---

## 6. Data safety form (Play Console → App content → Data safety)

Play's taxonomy, not ours. Answer exactly:

- **Does your app collect or share user data?** Yes.
- **Is all of the user data collected by your app encrypted in transit?** Yes.
- **Do you provide a way for users to request that their data is deleted?** Yes.
- **Account creation:** Yes, the app lets users create an account (sign-in via
  WorkOS AuthKit). **Account deletion URL:** `https://tinyassets.io/account`.
  Deleting the account deletes all associated data → answer that no separate
  partial-deletion option is offered.
- **Data types collected** — each one *Collected*, *Not shared*, *not ephemeral*.
  Play defines "required" as data the user has no choice about, so only sign-in
  is required; everything else is **optional** because the user decides whether
  to send it:

  | Play category → data type | What it is here | Required? | Purposes |
  |---|---|---|---|
  | Personal info → **Email address** | sign-in email | Required | App functionality, Account management |
  | Personal info → **User IDs** | WorkOS user id | Required | App functionality, Account management |
  | Messages → **Other in-app messages** | what you say to your universe | **Required** — chatting *is* the app's primary functionality, and Play asks that data required for primary functionality be declared required, not that the user could decline to type | App functionality |
  | Files and docs → **Files and docs** | attachments you send it | Optional (attaching is a choice) | App functionality |
  | App activity → **Other user-generated content** | the AI-provider credential you deposit (Play has no "credentials" type; this is its category for user-entered content that fits nowhere else) | Optional (Connect can be skipped) | App functionality |

  **Voice is intentionally absent from this saved-data draft.** The Android
  candidate contains dormant microphone plumbing, but the web control and store copy
  remain off. Before enabling it, record the real phone/network behavior and take one
  of these evidence-backed branches:

  | Observed voice behavior | Data safety consequence |
  |---|---|
  | Raw audio leaves the device or is retained by TinyAssets/a provider | Add **Audio files → Voice or sound recordings** and accurately mark collection, sharing, retention/ephemeral handling, optionality, and purpose. |
  | Audio stays on-device and only a transcript leaves the device | Do not add the audio type solely for local processing; keep the retained/sent transcript under **Messages → Other in-app messages**, and preserve device/network proof. |
  | Behavior cannot be proved | Keep voice disabled and do not guess at the declaration. |

  Do **not** declare Financial info → Purchase history unless the paid plan is
  bought inside the Android app (see §8, payments).
- **Shared with third parties?** No, for every type — but the answer rests on two
  of Play's named exclusions, so record why before submitting rather than
  ticking "no" blind:
  - *Service providers.* WorkOS (sign-in), Stripe (payments) and the hosting
    provider process on our behalf under their standard data-processing terms.
    Confirm each contract is actually in force for this account before relying
    on the exclusion; a provider used without a DPA is a transfer, not a
    service-provider relationship.
  - *User-initiated transfer.* The AI provider receives the user's messages only
    because the user connected their own account to it and the traffic runs on
    their subscription. This is the exclusion Play describes for a transfer the
    user asks for; the app makes the destination explicit at Connect time.
- **Data sold?** No. **Used for ads?** No.
- **Security practices:** encrypted in transit — Yes; deletion mechanism — Yes;
  independent security review — No.

This section is a **policy draft, not legal approval**. Immediately before submission,
compare every selected Console row against the exact release's permissions, SDKs,
live privacy notice, account-deletion behavior, and processor contracts. The founder
must approve the final answers; an agent must not make that declaration.

---

## 7. Content rating — DONE (IARC, submitted 2026-09-02)

Recorded as answered, not as predicted. Re-take the questionnaire only if the app
gains a surface that changes one of these, and then match this table so the rating
does not move under us.

- **Category step:** email `ops@tinyassets.io`; category **All Other App Types**
  (the only non-game option offered — the earlier "Utility / Productivity /
  Communication" guess is not a choice this questionnaire presents); IARC terms
  agreed.

| Question | Answer | Why |
|---|---|---|
| Downloaded App — ratings-relevant content in the app package | No | The APK is a Capacitor shell; it ships no content of its own. |
| User Content Sharing — users interact or exchange content with **other users** | No | The app shell has four views (sign-in, chat, connect, account). There is no discovery, remix, or user-to-user surface in it. |
| Online Content — content not in the initial download, incl. **generated AI content** | **Yes** | This is the one Yes. The chat is served, and it is AI-generated. Answering No here would be a misrepresentation. |
| Violence | No | Seller-catalog scoped; we publish no catalog. |
| Sexuality | No | Same. |
| Language — potentially offensive language | No | Question explicitly excludes user-generated content. |
| Controlled Substance | No | Seller-catalog scoped. |
| Promotion or Sale of Age-Restricted Products | No | |
| Misc — shares precise location with other users | No | |
| Misc — allows purchase of digital goods | No | The Android build is consumption-only (see §8 payments). |
| Misc — cash rewards / gift cards / play-to-earn / crypto / NFTs | No | None of it is in the app. |
| Misc — is a web browser or search engine | No | A WebView pinned to our own origin is not a general browser. |
| Misc — primarily news or educational | No | |

**Resulting ratings:** ClassInd **L**, ESRB **Everyone**, PEGI **3**, USK **0**,
IARC generic **3+**. Content descriptors: none.

Note the Yes on Online Content expands the questionnaire from 3 questions to 13 —
that is expected, not a mis-click.

---

## 8. Target audience & other declarations

- **Target audience:** 18+ (an AI productivity tool; avoids the stricter
  child-directed rules). Confirm.
- **Ads:** No ads → declare "No".
- **Government app:** No. **Financial features:** No.
- **News app:** No.
- **Payments (Play's payments policy):** digital subscriptions bought *inside* an
  app installed from Play must go through Google Play Billing. The Android shell
  therefore shows **no plan/upgrade/checkout UI** — the SPA hides it when it runs
  inside the Capacitor shell (`app.html`, `renderPlan` returns early when `NATIVE`), so the app is a
  consumption-only client of a plan bought on the web. Do not add a Stripe link
  to the Android build without switching to Play Billing.

---

## 8a. Foreground-service declaration — required before production review

The app targets Android 14+ and declares a `dataSync` foreground service for the
short-lived, user-initiated local OAuth callback listener. Google's current rule
requires every foreground-service type to be declared in Play Console with a feature
description, defer/interruption impact, and demonstration video. The earlier claim
that this type needed no Play declaration was false.

The exact staged copy and video shot list are in
[`android-release-verification.md`](android-release-verification.md). They are prepared
evidence, not a submitted legal/policy declaration. The founder must review the facts
and authorize the Console submission.

Use this approval packet only after the internal-phone recording matches it:

| Play prompt | Draft answer / evidence |
|---|---|
| Foreground-service type | `dataSync` |
| Feature using it | User-initiated **Connect OpenAI** subscription sign-in. TinyAssets temporarily runs a local loopback callback listener while the external browser completes OAuth; a persistent notification keeps the operation visible. |
| Why it cannot be deferred | If the listener is not ready while the external sign-in completes, its local callback cannot be received and the user must restart sign-in. No background sync or user content is lost. |
| What happens if interrupted | The callback is not delivered, the attempt times out, and no credential from that attempt is stored. The user can retry. |
| Video evidence | Tap **Connect OpenAI**; show the foreground-service notification; complete or cancel the browser step; return to TinyAssets; show the notification disappearing. Redact account identifiers, callback parameters, and secrets. |

Do not submit if the notification is absent, remains after success/cancel/timeout, the
service starts without the user's Connect action, or the callback/credential behavior
differs from the draft. Record the discrepancy and fix/retest first.

---

## 8b. Advertising ID declaration — staged answer: No

The live App content overview shows this as a separate unstarted declaration. For the
current candidate, answer **No** only after rebuilding the exact upload artifact and
passing merged-manifest verification:

- `mobile/package.json` contains no ads, analytics, Firebase, or Play advertising SDK.
- `mobile/scripts/verify_android_release.py` permits only Internet, foreground-service,
  microphone, and Capacitor's non-exported receiver permission. If a dependency merges
  `com.google.android.gms.permission.AD_ID`, the release fails on permission drift.
- Re-open this decision whenever dependencies change; absence from the source manifest
  alone is insufficient because library manifests can add it during merge.

This is a staged policy answer, not a saved declaration. The founder must confirm the
exact candidate evidence and save it in Play Console.

---

## 9. Graphics (staged in `docs/ops/play-assets/` — see that folder)

- **App icon:** 512×512 PNG (rendered by `mobile/scripts/render_app_icons.py
  --from-logo … --font …`, see `mobile/resources/README.md`; the committed file
  is canonical — regenerate only to change the mark).
- **Feature graphic:** 1024×500 PNG.
- **Phone screenshots:** ≥2, 16:9 or 9:16, min 320px — captured from the live app.
  The staged pair is the signed-out screen plus the Connect view; dimensions and
  privacy state are recorded in the asset README. Capture procedure in §10.

---

## 10. Screenshot capture

Screenshots come from the live app so they're honest:
1. Open `https://tinyassets.io/mcp/app` (or the installed app) at phone width.
2. Capture a representative set without account, universe, credential, branch, run,
   debug, notification, or browser-chrome identifiers.
3. Save to `docs/ops/play-assets/screenshots/`; run the release artwork verifier;
   visually inspect every file; only then upload it in the listing.

On 2026-09-03, a clean 540×960 signed-out capture replaced the stale conversation
image that exposed an internal universe id and implementation discussion. The staged
pair now passes the repository's Play artwork rules. This is asset readiness, not
evidence that the Console listing has been updated.

---

## 11. Submit (after §1–§10)

Steps 1–3 are **done** (2026-09-02/03) and are kept here as the shape of a release,
not as work outstanding:

1. ~~Play Console → **Create app**~~ — done: name `TinyAssets`, App, Free, declarations
   accepted, Play App Signing enrolled.
2. ~~Fill the listing (§4), Data safety incl. the account-deletion URL (§6), Content
   rating (§7), privacy URL (§4/§5), graphics (§9).~~ — done, except **Target audience
   (§8)**, which Play refuses to open until Sign in details has a reviewer account.
3. ~~**Internal testing** release~~ — done 2026-09-03 11:10: bundle built by
   `mobile/container/`, uploaded, rolled out. Opt-in link in the status checklist below.

Outstanding:

4. Verify the full loop on a device from the internal-test link.
5. Reviewer account → Sign in details → Target audience (§8) → submit Data safety.
6. Review and submit the foreground-service declaration (§8a), including its video.
7. **Closed test**, 12 testers for 14 days, then apply for production access.
8. Promote to **Production** → submit for review (hours–days) → **Roll out**.

---

## Status checklist (I keep this current — last swept 2026-09-03)

> **The app is on Google Play.** Internal testing track, release `1 (1.0)`,
> published 2026-09-03 11:10, "Available to internal testers", 3.1 MB install.
> **Opt-in link: https://play.google.com/apps/internaltest/4701716760893982267**
> (that number is the *track* id, not the app id — verified by loading the page,
> which renders "You're invited to test io.tinyassets.app (unreviewed)"). Open it
> on the phone signed in as the founder's Google account, tap **Accept invite**,
> then install from Play.
> Testers see the temporary name `io.tinyassets.app (unreviewed)` until the
> listing review completes; that is expected, not a defect.

Play Console's dashboard counter reads **8 of 11**, but the authoritative App content
overview shows **five declarations need attention**: Sign in details, Target audience,
Data safety, Advertising ID, and Foreground service permissions. Read-only inspection
on 2026-09-03 confirmed the Data safety draft is complete through Preview, while the
other four declarations are unstarted. That work gates *production*, not the existing
internal test. Full evidence is in
`docs/audits/2026-09-03-google-play-console-readonly-reconciliation.md`.

Done:

- [x] Package id `io.tinyassets.app`, keystore generated + certificate pinned
- [x] Store listing, graphics, privacy policy URL, in-app privacy link (#2778)
- [x] Account deletion in-app and at `tinyassets.io/account`
- [x] Ads / Government / Financial / Health declarations, category, contact details
- [x] **Content rating** — IARC submitted 2026-09-02, Everyone / PEGI 3 / USK 0 / ClassInd L
- [x] Data safety answered and **saved as a draft**; read-only Console Preview matches
      the staged types and shows Audio files `0/3`
- [x] Contact phone verified — one click, no SMS code. It was never a founder action.
- [x] **targetSdk 36** via Capacitor 8 (§1a) — Play rejects anything less for a new app
- [x] Internal-testing tester list "Founder devices"
- [x] **Signed AAB built and uploaded** — see "How to build one" below
- [x] Unsafe conversation screenshot removed; clean live signed-out capture staged
      alongside the Connect capture. The live Console still has the unsafe old image;
      replacement is not uploaded by this change.

Open, with what each actually waits on:

- [ ] **You: open the opt-in link, accept, install, and try the loop** — sign in,
      connect a provider, send a message. This is the first real-user test and it is
      the only thing that can find what a compile cannot.
- [ ] Founder: enable Email + Password sign-in in WorkOS and create a review account.
      AuthKit currently offers only "Continue with SSO" and "Continue with Google"
      (verified on the live page 2026-09-02), so there is no credential to give Google.
      See `docs/host-actions.md`.
- [ ] Sign in details → Target audience → Data safety submit — the chain that unlocks
      the last three App content rows, all gated on the account above.
- [ ] Advertising ID declaration: answer **No** only after confirming the exact
      candidate still passes the merged-manifest permission gate (no `AD_ID`) and no
      dependency introduces an advertising-ID SDK.
- [ ] Foreground-service declaration (§8a): confirm the Console row, record the
      user-initiated OAuth callback video, select **Data sync → Network processing →
      Other**, founder reviews the staged facts, then submit.
- [ ] Replace the uploaded `01-universe-conversation.png` with staged
      `01-sign-in.png`; this remains an explicit Console upload action.
- [ ] Founder: the four `ANDROID_UPLOAD_*` secrets. Not on the critical path any more —
      the container build below needs none of them — but they turn every future release
      into one `gh workflow run` instead of a manual build.
- [ ] Closed testing: 12 testers for 14 days, then apply for production access.
- [ ] Independent cross-family review of the later voice-native slice. The original
      release review does not cover it; the prepared request and exact retry path are
      in `docs/audits/2026-09-03-android-store-release-claude-review.md`.
- [ ] Production roll out (§11) — your final click.

### How to build a signed AAB with no GitHub secrets

The release workflow is the nice path, but it is not the only one, and it was never
the blocker it looked like. A container that mirrors the workflow's build half
produces the same verified **unsigned** bundle in about five minutes; `sign.sh` then
applies the upload key:

- **Toolchain**: Ubuntu 24.04, **JDK 21** (Capacitor 8 compiles at source/target 21),
  **node 22**, Android **platform 36** + **build-tools 36.0.0**.
- **Build**: `npm ci` → preserve any old `android/` as a superseded snapshot →
  `cap add android` → `cap sync android` → `add_app_scheme.py` → `add_app_icons.py` →
  `configure_android_release.py` → `verify_android_release.py` →
  `gradlew lintRelease bundleRelease` → merged-manifest verification.
- **Sign**: the workflow's own jarsigner step, including the fail-closed certificate
  pin, with passwords passed via `-storepass:env` so they never reach argv. Strip
  CRLF from `upload-keystore.env` first — see `docs/host-actions.md` for why.
- **Upload**: the Console's file input accepts the `.aab` directly.

Fresh generation is load-bearing: `cap add android` refuses to overwrite an existing
platform, and `cap sync` *preserves* a stale `variables.gradle`, so a tree generated
under Capacitor 6 keeps minSdk 22 / SDK 34 and would build a bundle Play rejects while
looking perfectly healthy. The release config asserts those generated SDK values; it
does not rewrite the dependency-owned template. The container moves an existing
directory aside; it does not delete untracked native work. Create a `mobile-v*` tag
only after its commit is in `main`; the signing workflow rejects refs outside main's
history.
