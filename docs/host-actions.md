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

**Four steps, in order. Steps 1–3 are founder-only; step 4 I can do once you have the key.**

1. **Activate the Stripe account** — business details and a bank account, at
   <https://dashboard.stripe.com/account/onboarding>. Stripe also asks for a business URL and
   usually a terms/refund page. Nothing below works until `charges_enabled` is true.
2. **Create the live product and price** — $20/month USD with lookup key
   **`tinyassets_paid_monthly`**, exactly as in test mode. `resolve_price_id()` resolves by
   lookup key, so a live price without that key makes every checkout refuse with
   `billing_unavailable`.
3. **Create a live webhook endpoint** → `https://tinyassets.io/mcp/app/billing/webhook`,
   events `customer.subscription.created/updated/deleted`. Keep its signing secret.
4. **Swap the two secrets on the droplet** — the live `sk_live_…` and that signing secret into
   `/etc/tinyassets/env`, then restart. Hand them to me and I will place them without echoing
   them; do not paste them into chat if you would rather not — a vault path works too.

**Do not do this before the checkout-lease redesign lands**
(`docs/concerns/2026-08-28-the-checkout-claim-is-not-tied-to-its-session.md`). The remaining
races there can create two subscriptions for one universe. In test mode that is a wrong number;
with a live key it is a double charge and a chargeback.

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
