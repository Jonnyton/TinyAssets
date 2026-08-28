# Host actions and decisions

Work that **only the founder can do** — because it needs an account, a dashboard, a credential, or a
judgment call no agent is authorized to make. Migrated from the `STATUS.md` Work table on
2026-08-25 when the board was retired.

Everything else that was on that board lives in `openspec/changes/` (the queue) or
`docs/concerns/` (unresolved findings). This file exists because those two homes can't hold an item
whose next step is *"the founder logs into Cloudflare."*

**Delete a row when it's done.** Git holds the history.

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

### Stripe is in sandbox — no real user can subscribe

*Verified live 2026-08-28 against the Stripe API from production.*

The subscribe/cancel flow is proven end-to-end, but against **test mode**. Real money cannot
move, and a real card would be declined:

| fact | value |
|---|---|
| `STRIPE_SECRET_KEY` in production | `sk_test_…` (sandbox) |
| `charges_enabled` | **false** |
| `payouts_enabled` | **false** |
| `details_submitted` | **false** — activation never started |
| the $20 price | `livemode: false`, test mode only |

`charges_enabled: false` is the decisive one. The account cannot take a real payment in any
mode until it is activated, and only the founder can do that.

**Check readiness at any time:** `python scripts/stripe_go_live.py --check` (run it on the
daemon, where the key lives). It reports every blocker below and refuses to call a sandbox
account ready.

**Four steps. Step 1 is yours; 2 and 3 are now one command; step 4 I do once you have the key.**

1. **Activate the Stripe account** — business details and a bank account, at
   <https://dashboard.stripe.com/account/onboarding>. Stripe also asks for a business URL and
   usually a terms/refund page. Nothing below works until `charges_enabled` is true.
2–3. **Create the live price and webhook endpoint** — one command, once the live key is in
   the environment: `python scripts/stripe_go_live.py --provision`. It creates the $20/month
   price with the lookup key the code resolves by, registers the webhook endpoint with every
   event entitlement depends on, and prints the signing secret once. Idempotent.
4. **Place the two Stripe secrets on the droplet** — the live `sk_live_…` and that signing
   secret into `/etc/tinyassets/env`. Hand them to me however you like; a vault path works,
   and I will place them without echoing them.

   **`TINYASSETS_BILLING_ENTITLEMENT_KEY` is already done** (2026-08-28): generated *on the
   droplet* so it never crossed the wire, 64 chars, `root:tinyassets 0640`. It takes effect
   on the next container **recreate** — `env_file` is read at creation, not at restart — so
   the next deploy activates it. Until then new claims still issue as v1.

   Why it exists: without it, every subscription's authority is signed with Stripe's webhook
   secret, and rolling that secret — which Stripe tells you to do, and which you must do on
   any leak — would permanently break every subscription already sold.
   `docs/reference/environment-variables.md` § Billing has the detail, including that
   rotating this key invalidates every v2 subscription.

The checkout-lease redesign that used to gate this has landed: a lease now names the Stripe
session it guards, so a lost response replays instead of creating a second session, a delayed
event releases only its own lease, and an abandoned checkout resumes instead of locking you
out. Double-billing is closed.

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

## Credentials and accounts

### Mint the PAT that unblocks the deploy chain

App-merged PRs raise no `push` event, so `build-image` and `deploy-prod` never fire; human-merged
ones do (measured: **#2259 vs #2260**). Mint a fine-grained PAT with **PRs + Contents write**, add it
as an Actions secret, and point `.github/workflows/auto-enroll-merge.yml` at it.

Background: `docs/decisions/ADR-004-merge-attribution-and-the-deploy-gap.md`.
This is the mechanism behind Hard Rule 14 — five PRs merged 2026-07-21 and none reached production.

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
