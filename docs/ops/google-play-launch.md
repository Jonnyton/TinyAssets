# Google Play launch — drive-everything runbook

Everything needed to publish the TinyAssets Android app to Google Play, staged so
the founder's only actions are: (1) create the Play Console account, (2) authorize
the $25 one-time fee, (3) provide the upload keystore as a repo secret, and (4)
click "roll out" after review. All content below is copy-paste ready.

Package name (permanent once published): **`io.tinyassets.app`**
(`mobile/capacitor.config.json`). App is the Capacitor shell over
`https://tinyassets.io/mcp/app` — see `desktop-app/README.md` + `mobile/README.md`.

---

## 0. Founder-only actions (I cannot do these)

| Step | Action | Where |
|---|---|---|
| Account | ~~Create a Google Play Developer account.~~ **Done** — developer `8089695267825659874`, identity verified 2026-08-24 (Play Console mail). | https://play.google.com/console/developers/8089695267825659874 |
| Payment | ~~Authorize the $25 fee.~~ **Done** with the account. | — |
| Signing key | The keystore is generated (§2, 2026-09-01). **Add its 4 values as repo secrets** — one command, §3. An agent cannot: `gh secret set` is denied to it. | your machine → GitHub secrets |
| Publish | After the AAB uploads + review passes, click **Roll out**. | Play Console |

Everything else below I build/stage.

---

## 1. What ships

A signed **`.aab`** (Android App Bundle — Play's required format) produced by CI
(`.github/workflows/android-release.yml`), signed with your **upload key**; Google
holds the real app-signing key via **Play App Signing** (recommended default). The
web app updates ship instantly (no store resubmit) — only a native-shell/config
change needs a new AAB.

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
it; this change adds a Play-compliant privacy section there (what's collected: a
sign-in identity via WorkOS, and the AI credential you deposit; how it's used;
that it's not sold; deletion path). Confirm `https://tinyassets.io/legal` renders
the privacy section before submitting.

---

## 6. Data safety form (Play Console → App content → Data safety)

Answer exactly:

- **Does your app collect or share user data?** Yes.
- **Data types collected:**
  - *Personal info → Email address / User IDs* — collected, for **App
    functionality** + **Account management**. Not shared. Processed on the
    server. Required (sign-in).
  - *App activity → other user-generated content* (the messages you send your
    universe) — collected, for **App functionality**. Not shared.
  - *Credentials* — the AI provider credential you deposit is stored in a secure
    vault for **App functionality**; not shared; never used for ads.
- **Is all data encrypted in transit?** Yes.
- **Do you provide a way to request data deletion?** Yes — via the contact email /
  account sign-out + deletion request.
- **Data sold?** No. **Used for ads?** No.

---

## 7. Content rating (App content → Content rating questionnaire)

- Category: **Utility / Productivity / Communication**.
- Violence / sexual / profanity / controlled substances: **No**.
- User-generated content / user communication: **Yes** (the user chats with an AI;
  no user-to-user social feed) — declare in-app communication accordingly.
- Expected result: rated **Everyone / PEGI 3** (confirm from the questionnaire).

---

## 8. Target audience & other declarations

- **Target audience:** 18+ (an AI productivity tool; avoids the stricter
  child-directed rules). Confirm.
- **Ads:** No ads → declare "No".
- **Government app:** No. **Financial features:** No.
- **News app:** No.

---

## 9. Graphics (staged in `docs/ops/play-assets/` — see that folder)

- **App icon:** 512×512 PNG (from `mobile` capacitor assets; regenerate via
  `npm run assets` in `mobile/` if needed).
- **Feature graphic:** 1024×500 PNG.
- **Phone screenshots:** ≥2, 16:9 or 9:16, min 320px — captured from the live app
  (sign-in, a universe conversation). Capture procedure in §10.

---

## 10. Screenshot capture

Screenshots come from the live app so they're honest:
1. Open `https://tinyassets.io/mcp/app` (or the installed app) at phone width.
2. Capture: the sign-in screen, a universe conversation, the Connect view.
3. Save to `docs/ops/play-assets/screenshots/` and upload in the listing.

---

## 11. Submit (after §1–§10)

1. Play Console → **Create app** — name `TinyAssets`, App, Free, declarations.
2. Fill the listing (§4), Data safety (§6), Content rating (§7), Target audience
   (§8), privacy URL (§4/§5), graphics (§9).
3. **Internal testing** release first (reaches testers in minutes): create a
   release → upload the CI-built `app-release.aab` → add your email as a tester →
   roll out → verify the full loop on a device.
4. Promote to **Production** → submit for review (hours–days) → **Roll out**.
5. Enroll in **Play App Signing** when prompted (recommended default).

---

## Status checklist (I keep this current)

- [x] Package id decided (`io.tinyassets.app`)
- [x] Release AAB CI workflow (`android-release.yml`)
- [x] Listing content written (§4)
- [x] Data safety + content rating answers (§6, §7)
- [x] Privacy policy section (§5) — on the **production** `/legal` (React site) as of this
      change; #2507 had only put it on the retired Svelte site
- [x] Founder: Play Console account + $25 (§0) — verified 2026-08-24
- [x] Upload keystore generated (§2, 2026-09-01) + certificate pinned in the workflow
- [ ] Founder: the four upload-keystore secrets (§3, one command)
- [x] Launcher icon + splash (`mobile/resources/`, installed by `scripts/add_app_icons.py`)
- [x] Listing graphics: icon-512, feature graphic, 2 phone screenshots (§9, §10 — 2026-09-01)
- [ ] AAB built via CI + uploaded (§11) — blocked on the secrets
- [ ] Play Console: app created, listing + declarations filled (§11.1–2)
- [ ] Internal testing verified → Production roll out (§11)
