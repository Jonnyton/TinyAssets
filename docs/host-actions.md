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

### claude.ai account out of credits — blocks the browser `ui-test` route

*2026-08-25 22:18Z: composer disabled, "monthly spend limit … out of credits"; weekly reset
2026-08-28 19:00 PDT.*

Raise the limit, **or** test via the desktop app — Electron over the live SPA, CDP-testable, and it
runs on the founder's own deposited subscription rather than the metered account.

`ui-test` is the final acceptance path for chatbot-facing changes (`AGENTS.md` § *Quality Gates*),
so this blocks acceptance, not just convenience.

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

### Google Play: verify the contact phone number — BLOCKS EVERYTHING ELSE

**Observed in the Play Console 2026-09-02.** `Create app` is greyed out with a padlock and
"Complete account verifications to create new apps". The one outstanding verification is
the contact phone number: `+12067997835` is on file but carries no verification tick, while
both email addresses do. Until it is verified, no app can be created, so no listing, no
upload, no internal test and no rollout can happen — the whole launch is behind this.

Only you can do it: Google sends a code by SMS or voice call to that phone, and I cannot
read it. Roughly a minute:

1. https://play.google.com/console/u/0/developers/8089695267825659874/account
2. **Contact details** → check the number is right → **Verify**
3. Choose SMS or call, enter the code, **Verify**

The `Create app` button un-greys once it goes through. Tell me and I will take the launch
from there. (Earlier notes recorded "identity verified 2026-08-24" — that was a *different*
verification; the phone step is separate and still open.)

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

### Apple App Store: enroll in the Apple Developer Program — nothing iOS can start without it

**Checked 2026-09-02, not assumed.** Gmail holds exactly one Apple message, an Apple
Account email verification from 2026-08-24; there is no Developer Program enrollment
confirmation, no App Store Connect welcome, and no $99 receipt. `developer.apple.com/account`
asks for a sign-in I cannot complete (I must not enter a password), so the browser cannot
confirm it either. On that evidence: **not enrolled**.

Everything on the iOS side is already staged — the Capacitor iOS platform, the
`tinyassets://` URL-scheme patch, the unsigned compile-check in `ios-build.yml`, and the
listing/App-Privacy copy in `docs/ops/app-store-launch.md`. None of it can produce an
installable app without an account.

1. **Enroll**: https://developer.apple.com/programs/enroll/ — $99/year, and identity
   verification usually takes a day or two, sometimes longer. **Start this first**, because
   the waiting is the long pole and it runs in parallel with everything else.
2. Then the signing assets: a Distribution certificate, an App Store provisioning profile,
   and an **App Store Connect API key** for CI upload (§3 of the runbook). You do NOT need a
   Mac — CI builds on `macos-15` runners once those secrets exist.
3. Then I create the App Store Connect record, fill the listing and App Privacy, and push a
   build to TestFlight.

### Google Play: a reviewer test account — and AuthKit has no password to give it

Play Console -> App content -> **Sign in details** (formerly "App access"). Our app is
behind WorkOS AuthKit, so the honest answer to "Is any part of your app restricted?" is
**Yes** — the form's own Yes branch lists "Google Account sign in, and / or SSO", which is
exactly what we use. Google then warns, in the dialog itself:

> "If we can't review your app, you may be prevented from releasing updates, or your app
> may be removed from Google Play. Reviewers are unable to create accounts, **use their own
> existing accounts**, or use free trials to access your app. They are also unable to
> contact you for more information."

**The fork in the earlier draft of this file is now closed.** I checked the live AuthKit
sign-in page (`https://unassuming-environment-16.authkit.app/`, the issuer the served app
config actually names) on 2026-09-02. It offers exactly two things: an email box whose
button reads **"Continue with SSO"**, and **"Continue with Google"**. There is no
email-and-password option. So password sign-in is **not enabled** in our WorkOS
environment, and no credential we could hand Google today would work.

That leaves one clean action and one poor one:

- **Enable Email + Password authentication in the WorkOS dashboard** (Authentication ->
  sign-in methods), then create a single review account such as `play-review@tinyassets.io`
  and sign into the app once so its universe exists. This is the one I recommend: it
  produces a reusable credential with no second factor, which is what Google's own guidance
  asks for ("provide reusable sign in details that don't expire").
- **Hand over a dedicated Google account.** Works in principle, but a fresh Google account
  signing in from a reviewer's machine invites exactly the 2-step-verification and
  new-device challenges Google's guidance tells us to avoid. Prefer the first option.

Why this is yours and not mine: I must not create accounts, and I must not type a password
into any field. Both halves of this are the parts I am barred from.

**The exact form, so it is a two-minute job when you have the credential.** "Add details"
opens a dialog with:

| Field | Required | What to put |
|---|---|---|
| Name | yes | `Reviewer account` |
| Username, email address, or phone number | no* | the review account's email |
| Password | no* | the review account's password |
| Any other information required to access your app | no | see the paragraph below |
| "…provide full access to all the features and content within this app" | checkbox | tick it |

\* Marked optional by the form, but leaving them empty is what gets an app rejected —
the reviewer has no other way in.

For the free-text box, the one thing a reviewer will otherwise trip on is that **the app
needs an AI provider connected before the chat does anything**. Either connect one on the
review account beforehand, or say so there and point at the "Skip for now" control.

**What it actually gates (corrected 2026-09-02):** Target audience and content refuses to
start until Sign in details is complete — verified by opening it and reading the block:
"You must complete the Sign in details section before starting the Target audience and
content questionnaire." Data safety is answered and saved as a draft but cannot be
submitted until Target audience is done. So this gates **two** remaining rows, not three.
Content rating was *not* gated and is now complete (IARC, submitted 2026-09-02, Everyone /
PEGI 3 / USK 0 / ClassInd L).

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
| Data safety | answered, **saved as a draft**; cannot submit until Target audience is done |
| Internal-testing tester list | **done** — "Founder devices" attached to the track |
| Build the signed AAB | agent, locally in a container, or in CI once the secrets exist |
| Internal-testing release: upload the AAB, roll out | agent |
| Verify the loop on a real phone (install from the internal-test link, sign in, chat) | **you** |
| Sign in details → Target audience → Data safety submit | blocked on the reviewer account above |
| Closed test: 12 testers for 14 days, then apply for production access | **you** |
| Promote to Production → submit for review → **Roll out** | you (final click) |

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
