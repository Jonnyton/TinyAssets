# Host actions and decisions

Work that **only the founder can do** — because it needs an account, a dashboard, a credential, or a
judgment call no agent is authorized to make. Migrated from the `STATUS.md` Work table on
2026-08-25 when the board was retired.

Everything else that was on that board lives in `openspec/changes/` (the queue) or
`docs/concerns/` (unresolved findings). This file exists because those two homes can't hold an item
whose next step is *"the founder logs into Cloudflare."*

**Delete a row when it's done.** Git holds the history.

---

## Decide: what should be publicly discoverable, now that the site shows it?

The rewritten `/commons` page lists what the endpoint reports as publicly
discoverable. Driving it live on 2026-09-02 showed seven of twelve rows are not
universes anyone published: `_backup_subject_migration_20260829T055340Z`,
`_removed_legacy_20260829`, `_removed_universes_20260828`,
`_removed_universes_20260829`, plus the `scratch`, `daemon_wikis` and
`cloud-automation-inputs` working buckets. All are `visibility=public` because
maintenance created them that way, not because anyone chose to publish.

Nothing sensitive leaks — the public projection is id, phase, word count and a
coarse timestamp — but the bucket names disclose when removals and an identity
migration happened, and the page reads like an accident. The site does **not**
filter them, deliberately: hiding rows while claiming to show "what is public"
is exactly the dishonesty the public-read boundary exists to prevent.

Your call, because the fix writes to live universe records. Suggested shape is
in `docs/concerns/2026-09-02-migration-records-are-publicly-discoverable.md`:
create maintenance holding records private, flip the seven existing ones (do
not delete — they are migration backups), and decide whether an unpublished
universe should default to `public` at all.

## Decide: should a deposit serve the universe by itself?

The deposit spec (`openspec/changes/byo-llm-deposit-surface/specs/byo-llm-deposit-surface/spec.md`,
"The deposit result directs the owner to the existing serving re-point") says the deposit
**SHALL NOT itself enable serving**. On 2026-09-01 a pasted Codex deposit through the app
left the universe chatting but every run refused with `provider_not_bound`, because the
paste path never followed the hint. #2760 fixes that in the app (the paste path and the
heartbeat call the same `/mcp/app/serving/bind` the phone uses); a server-side
"deposit serves when nothing serves" was built, then withdrawn on Codex review because it
contradicts the requirement above.

Your call, because it is a contract change: keep the deposit write-only (every surface
finishes the gesture itself, as now), or change the spec so `connect_llm` serves when
nothing is serving yet. The second is one spec delta plus the withdrawn code; it needs
your approval first. Tiny's view from inside: "registration and selection must not be
separable in a way that leaves me runnable-on-paper but dead in practice."

## Capacity for 1,000 users

### Apply the daemon memory limit — needs a compose sync, not a decision

`deploy/compose.yml` now carries `mem_limit: 4g` + `memswap_limit: 4g` (#2658), but the
droplet's copy at `/opt/tinyassets/compose.yml` is from 2026-08-22 and **is not shipped by
the deploy pipeline** — image updates do not sync it. So the limit is inert and the daemon
is still unbounded.

Much less urgent since the resize: the cgroup's observed peak of 1411.8 MiB was 69% of the
old 2 GB host and is 18% of 8 GB. Left as a follow-up rather than a second outage tonight.
It needs a compose sync plus a daemon recreate (brief blip), which is my job, not yours —
this row exists so it is not forgotten.

### Related, and free: the container has no memory limit

`docker inspect` reports `mem_limit=0`, so the daemon may consume the whole host. With
the run pool already peaking at 1.1 GB of 2 GB, an overshoot OOMs the *host* and takes
`tinyassets-tunnel` with it — a total public outage, where a container limit would have
been a restart (`restart=unless-stopped`). No OOM has happened; the margin is thin. I can
add the limit with the resize, where there is headroom for it to be generous rather than
a new way to fail.

---

## Taking real money

### WorkOS production cut-over — DONE 2026-08-29, nothing left for the founder

Kept as one paragraph so the next reader does not re-derive it: daemon on the production
key (`unassuming-environment-16.authkit.app`, Connect client `client_01M15YZXW7G7X6X1YQ4TG87Q00`,
resource indicator `https://tinyassets.io/mcp`); both founder accounts migrated and verified
live; Google consent screen **In production** (any Google account can sign in); GitHub
PR-writer re-established through production WorkOS Pipes (provider enabled, OAuth app
`TinyAssets WorkOS Pipes` carries both callbacks, connections reconciled for
`u-01kxm1vszd8hwp7em418asq8h9` and `u-tiny`). Record and boundary:
`docs/reviews/2026-08-29-codex-subject-migration-boundary.md`. Delete this paragraph on the
next host-actions pass.

---

## Legacy pre-credential data in `/data`

---

## Blocking a proof path

### Claude subscription spend limit — blocks Claude-family review and browser `ui-test`

*Reverified 2026-09-03: three `peer_agent.py claude` review dispatches exited 1; the
latest failed after 19 seconds with no review output. A minimal direct diagnostic on
the earlier attempts reported that the monthly spend limit was reached.*

Raise or reset the Claude usage limit. Until then, Codex-authored public-surface changes
cannot obtain the required opposite-family review, and the claude.ai browser route cannot
provide final rendered-chat acceptance. The desktop app remains available for supporting
SPA checks, but it does not replace either required gate.

---

### Decide what the $20 actually buys — blocks live activation

*Found 2026-08-28 while preparing Stripe to go live. Full finding:
`docs/concerns/2026-08-28-the-paid-tier-buys-nothing.md`.*

Nothing outside the billing module reads the subscription tier. There is no metering, no
quota, no paid-only capability. **A user who pays $20/month today receives a flag in a
SQLite table.** Every other blocker is mechanical; this one is a decision.

Billing shipped without the metering half of the plan you approved — that half is PR
**#2598**, still open, and it also carries a stale copy of the billing code that has since
been corrected, so it needs extracting rather than rebasing whole.

**Two questions only you can answer:**

1. **What is the free monthly effect allowance?** You said "materially more than 50."
   Marginal cost is ~$0.12/user/month, so cost is not the constraint — anchoring and abuse
   are. Give me a number and I will land the quota dark, flip it for one universe, and
   live-test it.
2. **Or launch without it** — sell the paid tier as supporting the project rather than as
   capacity. A legitimate choice, but it has to be a chosen one, and the pricing page must
   then say that is what it is.

Until one of those is answered, do not swap in the live key: the checkout would work and
the customer would get nothing for their money.

---

---

### Decide who may sign up — the platform is single-tenant by construction

*2026-08-28, from a cross-family multi-user review. Full finding:
`docs/concerns/2026-08-28-user-code-runs-in-process.md`.*

Stripe is live and provisioned. Four second-user blockers were found and fixed
(#2627 session fixation and world-readable tokens, #2629 source-approval gate, #2630
private-branch run bypass, #2632 write-ACL granting founder tier).

**One is not fixed, because it is not a bug — it is the architecture.** Universe code
runs `exec()` inside the daemon, with `os.environ` and the data dir reachable. So anyone
who can get source approved can read the live Stripe key, every credential vault, every
other user's session token, and can write the database that decides who has paid.

#2629 bounds **who** may approve source (an allowlist, currently just your universe). It
does not bound **what** approved code can do. Encryption would not help: the key lives in
the same process.

**So the decision is yours, and it is not technical:**

1. **Open checkout to the public** — accept that a paying stranger who gets source
   approved owns the deployment. Only sane if the approval allowlist stays exactly one
   universe forever, which makes the paid tier a promise you cannot keep.
2. **Keep checkout closed; subscribe yourself** — everything works, single-founder is the
   threat model it was built for, and it is materially stronger than yesterday.
3. **Build the boundary first** — run universe code in a real OS/container sandbox, or
   move credential custody into a separate process the graph cannot reach. That is the
   work that makes "real users" mean what it sounds like.

I would do (2) now and (3) next. (1) is the one I would not do.

---

### Confirm the free allowance, then I flip metering on

*The `$20` question, now with a concrete proposal rather than an open one. Quota code is
PR #2618, landed dark. Finding:
`docs/concerns/2026-08-28-the-paid-tier-buys-nothing.md`.*

You said the free tier should be "materially more than 50 effects/month". The defaults
already in the code are far more generous than that, and cost says they can be:

| | free | paid ($20/mo) |
|---|---|---|
| effects | **100 / day** (~3,000/mo) | **5,000 / day** |
| window | rolling 24h | rolling 24h |

An *effect* is one thing that reaches the outside world and succeeded. Reads, writes,
edits, retries, and failed attempts cost nothing — that was the bug that started this,
where fifteen failed 401s ate the budget the successful post needed.

Why this generous: marginal cost is ~$0.12/user/month, and the platform supplies no
inference. Cost is not what should constrain the free tier; abuse reaching the outside
world is, which is why effects are metered and runs are not.

**Say "yes" and I will:** flip `TINYASSETS_USAGE_ENFORCEMENT=1` for one universe, live
-test that a real post still goes through and that the cap actually stops the next one,
then roll it out. **Say a different number and I will use that instead** — they are env
vars, not a rebuild.

Nothing is enforced until you answer; the meter is recording either way, which is how we
will know what real usage looks like before the number matters.

---

### Phone app — send the first message and see it answered

*Live and proven on the founder's S24+ via adb (2026-08-22): OpenAI link completes, PONG inside the
sandbox on the founder's own subscription. Shipped as #2466 (FGS vs the Android freezer), #2467
(auto serving binding), #2468 (codex sandbox tmpfs home + systempaths/cap_drop), #2469 (HttpOnly
refresh); APK `android-latest`.*

What is missing is one real message from the founder, answered. Everything up to that is verified.

Owed alongside it: codex refresh-token persistence across a rotating turn, and the deploy step must
install `deploy/compose.yml` -- the droplet was patched in place, so a container recreate loses it.

Recovered 2026-08-27 from PR #2463, which carried it on the retired board and had no other home.

---

### First-class Voice — connect a compatible current provider before physical-device proof

**Do not send a credential in chat and do not buy a platform key.** The shipped dark runtime accepts
only an exact `tinyassets.voice.v1` bridge backed by a generic HTTP connection and grant already
owned by the signed-in founder and their home universe. Host credentials, maintainer accounts,
another user's connection, and platform-paid usage cannot unlock it.

The product path now binds the capability only to the universe's current serving provider and
reuses the existing provider/connection setup. An authenticated read-only app check on 2026-09-04
resolved the founder universe's actual current binding as `codex` via `subscription_cli`. That
binding cannot satisfy the shipped HTTP bridge contract. The only visible `openai_chat` HTTP
registration was the old `plug-and-play-test-model` test artifact and was not the active serving
binding. Do not ask Jonathan to name what the app can derive, and do not treat either registration
as realtime authority.

The smallest remaining founder action is therefore a choice: use the existing provider setup to
connect and select a real user-owned `api_key_http` provider that offers a compatible
`tinyassets.voice.v1` bridge, or leave Voice unavailable. Only after the app derives that compatible
current binding should Jonathan be asked to authorize one bounded non-production physical-device
proof. No host file or developer bypass counts. The proof order, stop conditions, and evidence
packet are in `docs/ops/realtime-voice-mobile-handoff.md`.

Stop for Jonathan at the rendered `ready` state before starting microphone acceptance. Enabling or
releasing Voice remains a separate explicit founder decision. Both Voice-specific production gates
remain off meanwhile; generic outbound HTTP is already enabled for unrelated effectors and cannot
unlock Voice on its own.

---

### Decide whether Claude may serve turns in production (`TINYASSETS_ALLOW_CLAUDE_SERVING`)

**The whole ask: yes or no.** The flag is an operator opt-in that gates *creating* a
`claude-code` serving binding (`tinyassets/provider_assignment.py`,
`tinyassets/provider_serving_binding.py`); it is unset in production, so every universe serves on
codex or an api-key provider. It was the last open task of the streamed-attempts change
(`openspec/changes/archive/2026-08-29-stream-and-classify-provider-attempts`, task 6.4) and is a
decision, not a build.

Two facts bear on it: Anthropic does not permit third-party use of a consumer subscription
through OAuth, so the only legitimate Claude route is the user's own CLI on their own machine
(client inference); and the claude reader still idle-kills a turn waiting on its own tool
(`docs/concerns/2026-08-29-claude-reader-tool-wait-idle-gap.md`), which would need fixing before
any Claude-served universe runs a multi-step job. If the answer is no, delete the flag and this
row; if yes, the concern above is the prerequisite.

## Credentials and accounts

### Google Play: `WORKOS_API_KEY` reaches the daemon — VERIFIED 2026-09-02, nothing for you

Account deletion removes the user's WorkOS record through the management API, and that
upstream deletion is also what ends sessions on other devices (their refresh handles are
opaque to the daemon). The key is not in the repo or in `deploy/`, so I checked the host:
`/etc/tinyassets/env` carries exactly one `WORKOS_API_KEY=` line, and
`docker exec tinyassets-daemon printenv WORKOS_API_KEY` returns an `sk_`-prefixed value of
the expected length. So a real deletion will remove the sign-in identity, which is what
`/legal` and `/account` promise.

If that ever stops being true, deletion still removes every byte of the user's data and
reports `identity: not_configured`, tells the user, and writes a receipt under
`.account-deletions/` — check it with
`python -c "from tinyassets.account_deletion import pending_deletions; print(pending_deletions('/data'))"`.
Delete this paragraph on the next host-actions pass.

### Apple App Store: enroll — signing and TestFlight cannot start without it

**Standing founder authorization (2026-09-03):** drive all ordinary Apple-required
setup and completion steps for the iPhone Store objective without repeated approval,
including required account/app attestations, API access and least-privilege credentials,
signing/provisioning, builds, verified metadata/privacy answers, screenshots, uploads,
TestFlight validation, App Review submission, and release/publication. Interrupt only
for a new monetary charge, an irreversible destructive action, a material choice Apple
does not require, or personal/legal facts that cannot be established truthfully from
verified project/account evidence. Computer-use actions that policy requires to be
confirmed at action time still follow that higher-level confirmation rule.

**Checked 2026-09-03, not assumed.** The account holder completed Apple's official
creation form, but the final step returned only **"Your account cannot be created at
this time."** There is no field-specific email, phone, birthday, country, or password
validation on the page, and no new Apple email arrived. Apple Account and iCloud Sign-In
were available on Apple's System Status page, so this is not a documented system-wide
outage. The visible evidence cannot distinguish a temporary server-side rejection from
a browser/network-specific rejection; it does not support claiming a phone-reuse,
region, locked-account, or device-limit cause. Apple Support then reported making an
unspecified change on its side and asked for one new creation attempt. After the account
holder retried, the browser reached the signed-in Apple Account **Sign-In & Security**
page and showed two-factor authentication with a trusted phone number. Account creation
is therefore complete. The account holder confirmed that result and closed the completed
Apple Support chat.

Everything autonomous on the iOS build side is staged — the Capacitor platform,
`tinyassets://` URL-scheme patch, native TinyAssets artwork, unsigned compile-check,
manual signed-IPA workflow, opt-in TestFlight upload, and listing/App-Privacy copy.
None of it can produce an installable app without account-owned signing material.

1. **Complete — Apple Account created and verified (2026-09-03).** The signed-in account
   page shows two-factor authentication and a trusted phone number. The account holder
   also accepted the Apple Developer Agreement and declined optional developer-news email.

2. **Complete — enrollment purchased and membership activated (2026-09-03).** The account
   holder completed personal information and Secure Checkout. The signed-in developer portal
   now shows program resources, a Team ID, and a 2027 renewal date. The Apple Developer
   Program License Agreement and Apple Developer Agreement both show accepted on 2026-09-03.
   At that checkpoint no signing assets or App Store Connect API credentials existed.
3. **Complete — explicit App ID and App Store Connect record created (2026-09-03).** Verified in the
   signed-in Apple Developer browser at `/account/resources/identifiers/list`: the
   Identifiers table shows `TinyAssets iOS` / `io.tinyassets.app`. App Store Connect
   Terms of Service V100 (last updated 04 June 2018) was accepted by the founder.
   The founder then confirmed record creation. Apple ID `6808434444`; iOS 1.0 is
   **Prepare for Submission**. Product metadata and manual release are saved, the
   four-type privacy draft is configured but unpublished. Build 3 is attached to
   the `Internal` TestFlight group, selected for App Store Version 1.0, and its
   en-US **What to Test** and beta app description are saved. The group has manual
   Xcode-build distribution, 0 testers, and no invitations sent. The free price
   schedule is confirmed for all 175 displayed countries or regions; availability
   remains unset.
4. **Complete — signing, profile, and CI upload credentials (2026-09-03).** The active
   Apple Distribution certificate expires 2027-09-03 and is paired with an exportable
   private key. The active `TinyAssets App Store 2026` profile is App Store type for
   `io.tinyassets.app`, contains that one certificate, and expires 2027-09-03. The
   encrypted P12 and password, verified profile, and Developer-role `TinyAssets CI Upload`
   App Store Connect API key are present as all six secrets named in §3.
   The protected GitHub environment `app-store` is complete: founder approval is required,
   and only `main` may deploy. You do NOT need a Mac — CI builds on `macos-15`.
5. **Complete — Xcode 26 build accepted and processed by TestFlight (2026-09-03).**
   Exact fix revision `6ccb3d24` received a Claude Opus **AGREE** review and landed in
   PR #2798 as `76d795a1`. Every exact-head PR check passed, including `build-ios` and
   `required-tests`. Protected run `33827279907` produced signed build 1.0.0 (3);
   Apple reported no upload errors; App Store Connect matched its delivery UUID and
   now shows Build 3 as **Ready to Submit** under Version 1.0.0. Receipt:
   `docs/audits/2026-09-03-ios-testflight-upload-receipt.md`.
6. **Complete — authenticated TestFlight/App Store metadata (2026-09-03).** The
   founder reauthenticated, after which the beta app description and marketing URL
   were saved, Build 3 was selected for App Store Version 1.0, and the free price
   schedule was confirmed. Release mode remains manual. The internal-group and
   Build 3 pages expose no automatic tester-notification control; the documented
   checkbox belongs to external testing. With no external group or tester, the API's
   residual `autoNotifyEnabled=true` has no recipient and is inert. Receipt:
   `docs/audits/2026-09-03-ios-testflight-preparation-receipt.md`.
7. **Complete — age rating and tested-platform scope (2026-09-03).** The live
   questionnaire is saved at 18+ (19+ in Korea; earlier operating systems show
   17+ with Apple's regional exceptions). Untested Apple Silicon Mac and Apple
   Vision Pro availability are disabled and saved. Storefront availability is
   still unset. Factual App Review Notes describing the pinned Capacitor shell,
   absent commerce/advertising/voice UI, and critical review paths are also saved;
   no reviewer credential or personal contact detail was persisted at that point.
8. **Complete — required screenshots (2026-09-03).** Manual macOS CI run
   `33839432494` built the simulator app from Build 3's exact source, captured and
   validated `1284x2778` iPhone and `2064x2752` iPad images, and both images were
   visually inspected and uploaded. App Store Connect shows `1 of 10 Screenshots`
   in each required set after reload. Receipt:
   `docs/audits/2026-09-03-ios-app-store-screenshot-preflight-receipt.md`.
9. **Prepared — reviewer identity (2026-09-03).** The dedicated
   `play-review@tinyassets.io` identity and its saved Google Play password were
   recovered directly from Play's `Play Reviewer` record and accepted by Apple's
   fields without entering the secret in this repository. Known contact name/email
   are Jonathan Farnsworth / `jonathan.m.farnsworth@gmail.com`. The founder's local
   candidate profile at
   `C:\Users\Jonathan\Projects\Job Search\.claude\skills\job-application-assistant\01-candidate-profile.md`
   contains the authoritative phone number; do not duplicate it in this repository.
   Explicit action-time authorization is still required before transmitting that
   number to App Store Connect. Apple will not persist this page until the whole
   contact block is complete.
10. Counsel/founder must complete Content Rights: TinyAssets accesses third-party
   content, while Apple's truthful **Yes** answer also attests necessary rights in
   every region. That legal fact was not inferred; the modal was cancelled.
11. Complete the remaining truthful console declarations. Before the final
   Submit for Review decision, choose whether to accept the documented Guideline 4.2 wrapper
   risk or first add and prove a meaningful iPhone-native interaction.
12. If realtime voice is enabled in the candidate, review the final **Audio Data** and
   **Other User Content** declarations against the provider retention configuration and
   require physical-iPhone proof that capture stops on background/end before submission.

**Apple preflight evidence (2026-09-03):** after both required screenshots persisted,
**Add for Review** returned **Unable to Add for Review** and created no submission.
The screenshot blockers are gone. The exact unresolved requirements are Content
Rights, Privacy Policy URL plus Admin-provided privacy practices, reviewer
username/password, and reviewer first name, last name, email, and `+` country-code
phone number. The reviewer credentials and contact values are known; transmitting the
existing profile phone number to Apple still requires explicit action-time
authorization. Version 1.0 remains **Prepare for Submission** with manual release.

### Google Play: start the 12-tester closed test — this is the 14-day clock

**This is the long pole for Play, and only you can start it.** A personal developer
account cannot apply for production access until it has run a **closed test with at
least 12 testers opted in continuously for 14 days**. The 14 days are wall-clock:
nothing an agent does shortens them, and the clock does not start until the testers are
actually in. Every other Play item finishes in hours; this one finishes in a fortnight,
so starting it late is what sets the public launch date.

Alongside the Apple enrolment above, this is one of **two clocks worth starting today**.
They run in parallel and neither depends on the other.

What it needs from you:

1. Recruit **15–18 people with Google accounts** so ordinary drop-off cannot take the
   continuously opted-in count below 12. Ask for a clear yes before adding an address;
   do not place personal email addresses in this repository.
2. Play Console → **Test and release → Testing → Closed testing** → create one track.
   Prefer a dedicated Google Group because membership can be maintained without
   rewriting the release; an email list is acceptable if that is simpler.
3. Promote the already phone-verified bundle (or a strictly newer version code), copy
   the opt-in link, and send the invitation below. The 14-day clock begins only after
   at least 12 people have actually opted in, not when invitations are sent.
4. Keep a private tracker with invitee, consent, opt-in confirmed, install confirmed,
   Android/device, three task results, feedback, and opt-out date. Check the Play
   tester count daily and recruit replacements early. Never remove a tester during the
   window unless they ask to leave.

Suggested invitation (send only after the closed-track link exists):

> TinyAssets is running a private 14-day Google Play test. Please open **[opt-in
> link]** while signed into the Google account you gave me, tap **Become a tester**,
> install from Play, and stay opted in through **[end date and timezone]**. During the
> test, please try: (1) launch/sign-in, (2) open Connect and return without exposing a
> credential, and (3) send one ordinary test message if your account is configured.
> Report crashes, stuck screens, sign-in trouble, or confusing copy at **[private
> feedback route]**. Do not enter confidential or regulated information. You may leave
> at any time; tell me so I can replace the test slot.

Engagement plan — Google can reject a production-access application for insufficient
testing even when the count/duration minimum was met:

| When | Operator check | Tester request |
|---|---|---|
| Day 0 | Confirm ≥12 actual opt-ins in Play; save the start timestamp and expected end timestamp. | Opt in and install from Play. |
| Days 1–3 | Triage install/sign-in failures; replace drop-offs before the count falls below 12. | Complete launch/sign-in and one navigation task. |
| Days 4–10 | Review feedback plus Play crashes/ANRs; ship fixes only with a higher version code and re-smoke. | Exercise Connect return/cancel and an ordinary message where configured. |
| Days 11–13 | Confirm ≥12 remain opted in and all launch-blocking defects have dispositions. | Recheck the latest build and submit final feedback. |
| After 14 complete days | Capture the Console eligibility state before applying for production access. | No action unless asked to verify a fix. |

This does not require daily use from every person, but it does require a real,
representative test rather than twelve idle list entries. Google's current rule and
engagement guidance are at
<https://support.google.com/googleplay/android-developer/answer/14151465>.

After the 14 days: apply for production access, which Google reviews separately, and
only then can the app be promoted to Production and be publicly downloadable.

Do not confuse this with the internal-testing track already running — internal testing
does not count toward the requirement, no matter how long it runs.

### Google Play: reusable reviewer account — DONE 2026-09-03

Play Console -> App content -> **Sign in details** (formerly "App access"). Our app is
behind WorkOS AuthKit, so the honest answer to "Is any part of your app restricted?" is
**Yes** — the form's own Yes branch lists "Google Account sign in, and / or SSO", which is
exactly what we use. Google then warns, in the dialog itself:

> "If we can't review your app, you may be prevented from releasing updates, or your app
> may be removed from Google Play. Reviewers are unable to create accounts, **use their own
> existing accounts**, or use free trials to access your app. They are also unable to
> contact you for more information."

**Live identity reconciliation, 2026-09-03:** the WorkOS dashboard admin and sole
TinyAssets team member remains Jonathan Farnsworth, `jonathan.m.farnsworth@gmail.com`,
with the Admin role. Google Play Console is also signed in with that address.

Email + Password is **enabled** in the production WorkOS environment with the
recommended strong policy (10-character minimum, complexity score 3, breached-password
rejection). GoDaddy Email & Office now has the dedicated alias
`play-review@tinyassets.io` on the TinyAssets-controlled `info@tinyassets.io` mailbox;
that mailbox forwards to the founder's primary Gmail and keeps its own copy.

The dedicated AuthKit user **Play Reviewer** is `play-review@tinyassets.io`, WorkOS id
`user_01M1N3BFV6N1V1C9PP1NEWCCHP`. WorkOS shows Verified + Active, Email + Password,
no organization membership, no connected accounts, and sign-in count **2**. The two
password authentications reached the same isolated empty reviewer universe. After the
one-time address verification, the repeat sign-in required no MFA or email challenge;
the intervening Cloudflare human check was browser abuse protection, not an account
second factor. Both sessions were signed out after proof.

Play Console now shows **Sign in details** under Actioned, last edited 2026-09-03, with
the `Play Reviewer` credentials and observed instructions: sign in with Email + Password,
then choose **Skip for now** on the Connect screen to enter the empty reviewer universe.
No organization, integrations, connected accounts, or founder data are attached. The
optional Google/trusted-partner device feedback switch is off. The credential was saved
as a draft only; it was not sent for review. The actual password exists only in Play's
credential field and is intentionally absent from this repository.

The mistaken `simkalholdingsllc+tinyassets-play-review@gmail.com` WorkOS user was
permanently deleted only after the correct alias, delivery path, two sign-ins, and Play
save were all proven. It never became the saved Play credential.

WorkOS documents that AuthKit supports Email + Password and that the hosted UI exposes
only the methods enabled in the dashboard
(<https://workos.com/docs/authkit/email-password>,
<https://workos.com/docs/authkit/hosted-ui>). Keep this reviewer as a dedicated password
user; do not attach a founder/personal provider credential. Re-check the saved credential
immediately before every submitted build. Google's reviewer-access requirements are at
<https://support.google.com/googleplay/android-developer/answer/15748846>.

**What it gated:** Sign in details, Target audience (**18 and over**), and Data safety
are now Actioned and waiting in Publishing overview; nothing was sent for review.
Data safety was corrected to list both password and OAuth account creation. Content
rating remains complete (IARC, submitted 2026-09-02, Everyone / PEGI 3 / USK 0 /
ClassInd L).

**This does not block a real install.** Play's internal testing track explicitly works
"before you've finished setting up your app" — the App content checklist gates *production*
access, not internal testing. The shortest path to the app being installable from Play by a
real person is the upload keystore below, not this section.

### Google Play: add the four upload-keystore secrets (one command)

The Play developer account exists (identity verified 2026-08-24) and the upload keystore was
generated 2026-09-01 into `~/.tinyassets/android/` on your machine. The release workflow
signs with secrets an agent is not allowed to set (`gh secret set` is denied to it). Run, in
a Git Bash at the repo root:

```bash
D="$HOME/.tinyassets/android"
# `tr -d` is load-bearing: upload-keystore.env has Windows CRLF endings, so a
# plain `. "$D/upload-keystore.env"` puts a trailing carriage return on every
# value. A CR inside the secret makes the signing step fail with
# "Keystore was tampered with, or password was incorrect", which sends you
# hunting a corrupt keystore instead of a line ending. Verified 2026-09-03.
set -a; . <(tr -d '\r' < "$D/upload-keystore.env"); set +a
tr -d '\r\n' < "$D/tinyassets-upload.jks.b64" | gh secret set ANDROID_UPLOAD_KEYSTORE_B64
printf '%s' "$ANDROID_UPLOAD_KEYSTORE_PASSWORD" | gh secret set ANDROID_UPLOAD_KEYSTORE_PASSWORD
printf '%s' "$ANDROID_UPLOAD_KEY_ALIAS"        | gh secret set ANDROID_UPLOAD_KEY_ALIAS
printf '%s' "$ANDROID_UPLOAD_KEY_PASSWORD"     | gh secret set ANDROID_UPLOAD_KEY_PASSWORD
```

To confirm the secrets took, re-run the release workflow: the signing step prints
`upload certificate fingerprint verified` before it signs, and fails closed if the
restored keystore does not carry certificate
`D0:BC:F2:...:B2:11`. I have already verified that the keystore on disk carries
exactly that certificate, so a mismatch after this points at the secret, not the key.

**The alternative that needs no secrets at all.** I can build and sign the bundle
locally in a container (JDK 21, node 22, Android SDK 36) and upload the `.aab` to
the Console by hand — no GitHub secrets involved. That path is already working.
The secrets are still worth setting, because they are what makes *every future
release* one command instead of a manual build.

Then back the keystore up somewhere that is not this laptop.

What remains after the secrets, and who does it (`docs/ops/google-play-launch.md` §11):

| Step | State |
|---|---|
| Play Console: app created, declarations accepted | **done** 2026-09-02 |
| Store listing, graphics, privacy URL, Ads/Government/Financial/Health | **done** |
| Content rating (IARC) | **done** 2026-09-02 — Everyone / PEGI 3 |
| Data safety | **done** 2026-09-03 — Actioned with password + OAuth account creation; not sent for review |
| Internal-testing tester list | **done** — "Founder devices" attached to the track |
| Build the signed AAB | **done** 2026-09-03 — built and signed in the container (`mobile/container/`), no secret needed |
| Internal-testing release: upload the AAB, roll out | **done** 2026-09-03 11:10 — release `1 (1.0)`, track Active, 3.1 MB |
| Corrected internal release `2 (1.0.1)` | **done** 2026-09-03 21:42 PT — merged source `bf432f1b2dbe`; signed AAB accepted; Play shows Active and Available to internal testers. |
| Verify the loop on a real phone (install from the internal-test link, sign in, chat) | **you — this is the live one.** Opt-in on the founder's Google account: https://play.google.com/apps/internaltest/4701716760893982267 |
| Sign in details | **done** 2026-09-03 — Actioned with the dedicated reviewer; not sent for review |
| Target audience | **done** 2026-09-03 — 18 and over, Actioned; not sent for review |
| Advertising ID declaration | **done 2026-09-03** — saved No after shipped-artifact, exact-candidate merged-manifest, and dependency verification; actioned but not sent for review |
| Foreground-service declaration + behavior video | **you** — exact gate below |
| Replace the unsafe uploaded conversation screenshot with staged `01-sign-in.png` | **done 2026-09-03** — live draft saved and both retained filenames verified; not sent for review |
| Closed test: 12 testers for 14 days, then apply for production access | **you** |
| Promote to Production → submit for review → **Roll out** | you (final click) |

### Google Play: review and submit the foreground-service declaration

The Android bundle declares a `dataSync` foreground service because **Connect
OpenAI** starts a short-lived local callback listener while subscription OAuth is
open in the external browser. For apps targeting Android 14+, Play requires a
foreground-service declaration with the use case, interruption/defer impact, and a
demonstration video. This is a Console attestation, so the final truth check and
submission are yours.

After installing the next candidate from Play:

1. Record one short phone video: tap **Connect OpenAI**, show the persistent
   notification while the browser is open, return to TinyAssets, then show the
   notification disappearing. Redact all account identifiers and secrets.
2. In Play Console, open **App content → Foreground service permissions** and use
   the staged wording and video shot list in
   `docs/ops/android-release-verification.md`.
3. Submit only if the recording confirms that exact behavior. If the notification
   remains, the callback cannot be interrupted as described, or the function has
   changed, stop and return the discrepancy to an agent instead of attesting to the
   draft.

### Mint the PAT that unblocks the deploy chain

App-merged PRs raise no `push` event, so `build-image` and `deploy-prod` never fire; human-merged
ones do (measured: **#2259 vs #2260**). Mint a fine-grained PAT with **PRs + Contents write**, add it
as an Actions secret, and point `.github/workflows/auto-enroll-merge.yml` at it.

Background: `docs/decisions/ADR-004-merge-attribution-and-the-deploy-gap.md`.
This is the mechanism behind Hard Rule 14 — five PRs merged 2026-07-21 and none reached production.

### Set `Contents: Read and write` on the PAT deposited in the universe's vault

**The whole ask: change one dropdown from Read-only to Read and write.** No new token, no re-paste
— the key already in the vault keeps working.

This is a *different* token from the one above: it is the fine-grained PAT the founder pasted into
their own universe on 2026-08-28 so the agent could open a PR itself. It is live and correctly
scoped to the repo; only the Contents permission is short.

**GitHub itself names the missing permission.** Captured 2026-08-28 19:14 UTC from the raw
effect-evidence map of a live `authenticated_external_call` run (`delivered: true` — the call
reached GitHub and was refused there, not by us):

```
POST /repos/jonnyton/tinyassets/git/refs   ->   403
{"message":"Resource not accessible by personal access token",
 "documentation_url":"https://docs.github.com/rest/git/refs#create-a-reference"}

x-accepted-github-permissions:      contents=write; contents=write,workflows=write
github-authentication-token-expiration: 2026-09-27 03:07:38 UTC
```

`x-accepted-github-permissions` is GitHub stating the requirement outright: **`contents=write`**.
The expiry header proves the token is live and not expired. `GET`s on the same repo succeed —
it reads `main`'s ref and the full `app.html` — which is what proves the repo is selected.
`Pull requests: Read and write` is already set and does **not** cover `POST /git/refs`; branch
creation, and `PUT /contents/...`, are both Contents writes.

Everything on the platform side is already open and was verified the same day: the connection
exists with `POST /git/refs` allowed, effector consent for destination `github` is granted and
unrevoked, and `TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED` /
`TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION` are both `1` in the running daemon. This one
dropdown is the only remaining gate.

*Blocks:* the founder's standing goal that the universe push a PR end-to-end to deployed.
*Where:* GitHub → Settings → Developer settings → Fine-grained tokens → this token →
Repository permissions → Contents.

### Create the WorkOS native/public client

PKCE S256, no secret, exact variable-port `127.0.0.1` loopback redirect, offline access, plus the
`WORKOS_HOST_BINDING_RESOURCE` audience.
*Depends on:* test-identity landing; #1753 tasks 1.3 / 3.2. *Where:* WorkOS dashboard.

### Register the `TinyAssets` ChatGPT connector as workspace admin

At `https://tinyassets.io/mcp`.
*Depends on:* canonical `/mcp` live and `/mcp-directory*` absent. *Where:* OpenAI workspace admin.

### Supabase infra for the market workflow

Live read access, plus the prod migration-home decision (transport 2.5 / 2.6); a prod-shaped Realtime
env (5.3); an isolated launch-region project (5.4). *Where:* Supabase account.

---

## Approvals and decisions

### Approve an isolated canonical `/mcp` baseline environment + traffic envelope

Provider-free, no maintainer quota, test identities with cleanup, canary-coordinated.
*Depends on:* `harden-production-load-evidence`; `test-identity-and-reset`.

### Authorize the reciprocal public-read / manifest Worker delta edge

One merged front-door body before public-read sync.
*Owner artifact:* `openspec/changes/archive/2026-08-26-reconcile-external-connector-manifests/tasks.md`.
*Depends on:* current owner handoff; public-read task 0.5.

### Review BYO-LLM connect flow slice 1

Round-3 credential-snapshot filesystem fixes verified; **no merge, no deploy** without this review.
*Depends on:* exact-head dual-family review; POSIX/production Codex integration.
*Owner artifacts:* `openspec/changes/byo-llm-connect-flow/`,
`openspec/changes/archive/2026-08-26-constrain-set-engine-provider-authority/`.

### Activate hosted-preview publication

`activate-hosted-preview-publication` — a no-prod account plus a fixed Worker; inert host
alias/version; Access anon-deny and reviewer-load proof; then a restricted GitHub environment.
*Where:* Cloudflare + GitHub environment.

---

## Host-recorded evidence

### Connector tool-selection accuracy — baseline and regression decision

Instrument landed in #1776; **no agent-buildable task remains** (triaged 2026-08-02). The host
records the claude.ai baseline (task 3.1) and the permitted-regression decision (task 3.2).
*Depends on:* ChatGPT connector registration, before its baseline.
*Owner artifact:* `openspec/changes/archive/2026-08-26-connector-tool-selection-accuracy/`.

### Cloud drain activation — dark deploy, cutover, and 24/7 proof

Implementation landed; the dark deploy/canary, single-active cutover, and 24/7 PC-off proof remain.
*Owner artifacts:* `docs/audits/2026-08-03-cloud-drain-epoch2-consumer.md`,
`openspec/changes/archive/2026-08-26-activate-main-universe-spec-drain/tasks.md`.

> **Changed 2026-08-25.** This row carried the dependency *"keep local drain until reviewed cloud
> health; never activate both claimers."* The local drain supervisor was deleted in the harness
> reset (it was an autonomous background worker, which the host's two-provider decision put out of
> scope). There is no longer a second claimer to conflict with — but that also means **there is no
> local fallback** if cloud activation stalls. Decide with that in mind.

---

### X app is Read-only — flip it to Read and Write

**The smallest ask:** in the X developer portal, open the app behind connection
`http_7f4a2d48423c003f5bb31b127468606c` → *User authentication settings* → set
**App permissions** to **Read and write** → then **regenerate the access token
and secret** and re-deposit them. The permission is baked into the token at
issue time, so an existing token keeps `read` access even after the app setting
changes; without the regenerate step this looks unfixed.

**Why it is a host action:** it is a setting in your X account. Nothing in this
repo can change it.

**Reproduced 2026-08-27 through the webapp**, driving `tinyassets.io/mcp/app`
as the signed-in founder rather than the MCP — run `948a32670485432a`, same
branch, same result. Two things that run additionally rules out:

- **Not throttling.** `x-rate-limit-remaining: 39999` of `40000`.
- **Not the wrong connection.** The universe enumerated every saved connection:
  `webhook:test`, `x:posting`, and the GitHub PR writer. There is exactly one X
  connection and it is the read-scoped one, so there is no alternative
  credential to try.

X names the fault itself in the response body:

```json
{"detail": "Your client app is not configured with the appropriate oauth1 app permissions for this endpoint.",
 "status": 403, "title": "Forbidden", "type": "https://api.x.com/2/problems/oauth1-permissions"}
```

**Original evidence, 2026-08-27** — run `c2b486ff315045c6`, branch `8ab6516d50c5`
("X Hello World via Codex v2"), production `44c4e205`:

```
status: completed          deliver_post: ran
POST https://api.x.com/2/tweets  ->  403 Forbidden
"Your client app is not configured with the appropriate oauth1 app
 permissions for this endpoint."
x-access-level: read
```

**What this unblocks, and what it proves.** The platform half is done. That run
authenticated, resolved the grant, built the packet, and made a real outbound
POST — the 403 is X refusing the *token's* scope, not TinyAssets failing. The
same branch failed three different ways earlier the same day, all ours and all
now fixed and deployed:

| When | Failure | Fixed by |
|---|---|---|
| 08-25/26 | `permission_denied:provider_not_bound` | #2559 |
| 08-27 am | `provider invocation usage could not be settled` | #2582 |
| 08-27 am | async sub-branch refused, run FAILED before any node | #2586 |

So this row is the last thing between the founder and a posted tweet, and it is
the only one that was never a code problem.

**How to verify after changing it:** re-run branch `8ab6516d50c5`. Expect
`external_write_results.deliver_post.authenticated_external_call.response.status`
to be 201, and `x-access-level` to read `read-write`.
