# GitHub App setup — patch-loop owner review/merge (S4)

A **5-minute checklist** the host runs personally when we go live. It creates the
GitHub App that AUTHORS patch PRs (so the owner can't self-approve), installs it
on the target repo, and records where each credential goes.

## Two merge modes → two scope tiers (Codex r13 #3 / host decision 2026-07-16)

**MANUAL merge is the DEFAULT and works with MINIMAL scope:**
**`Contents: write` + `Pull requests: write` + `Metadata: read` only.** The
owner reviews every PR themselves and GitHub's native ruleset enforcement runs
AT MERGE — the owner is in the loop each time, so the platform does NOT pre-read
`bypass_actors`, and the App needs no elevated access. This is the whole MVP.

**AUTONOMOUS merge (`auto` / `not_before`) is an explicit OPT-IN with an extra
disclosed grant.** It merges without a per-PR owner action, so before enabling
it the platform must positively verify the repo is review-gated — which requires
reading `bypass_actors`. GitHub returns `bypass_actors` **only to a caller with
ruleset *write* access**, which the App's minimal merge identity deliberately
lacks. So autonomous merge uses a **separate, narrowly-scoped VERIFIER identity
— the owner's own token, which already has ruleset access — used ONLY for the
gate read**, never for merging. If that verifier identity isn't wired, `auto` /
`not_before` fail closed (`autonomous_requires_verifier`) and `manual` stays
available. Do NOT grant the App `Administration` to make autonomous work — use
the owner verifier token.

No webhook for the MVP (polling reconciliation is fine; webhooks are a later
upgrade).

> Why an App (not a PAT): GitHub does not let a PR author approve their own PR.
> The App authors the PR; the owner's chat approval is submitted as a REAL
> GitHub review with the owner's user token, and a required-code-owner-review
> ruleset makes that review the native merge gate. See
> `docs/design-notes/2026-07-16-s4-github-native-redirect.md`.

## 1. Create the App (~2 min)

Either use the **manifest flow** (fastest) or click through settings.

### Option A — manifest flow (recommended)

1. Open `https://github.com/settings/apps/new` (personal) or
   `https://github.com/organizations/<org>/settings/apps/new` (org).
2. Paste the manifest below into the manifest-flow form (or POST it to the
   manifest conversion endpoint). It pre-fills the name, permissions, and the
   no-webhook setting. Adjust `name` / `url` as desired.

```json
{
  "name": "TinyAssets Patch Loop",
  "url": "https://tinyassets.io",
  "hook_attributes": { "active": false },
  "public": false,
  "default_permissions": {
    "contents": "write",
    "pull_requests": "write",
    "metadata": "read"
  },
  "default_events": []
}
```

### Option B — manual

Settings → Developer settings → GitHub Apps → **New GitHub App**:
- **Webhook**: uncheck **Active** (no webhook for MVP).
- **Repository permissions**: Contents → **Read and write**; Pull requests →
  **Read and write**; Metadata → **Read-only** (auto). Leave everything else
  **No access** — do NOT grant `Administration` (the design reads rulesets via
  `Metadata`, never classic branch protection).
- **Where can this GitHub App be installed?** Only on this account.
- Create.

## 2. Generate + record credentials (~1 min)

On the App's page:
1. **App ID** — copy it. → goes to the credential vault as the App id
   (non-secret metadata; also used as the JWT `iss`).
2. **Private keys → Generate a private key** — downloads a `.pem` (PKCS#1 RSA).
   → this is the **crown-jewel secret**. Hand it to the vault lane
   (`SecretStore`), NOT into any universe/repo/shared artifact. Never commit it.
   Rotate via GitHub's overlapping-keys support if it ever leaks.

## 3. Install on the target repo (~1 min)

App page → **Install App** → choose the account → **Only select repositories** →
pick the owner's patch-loop repo → Install.
- After install, the URL is `.../installations/<INSTALLATION_ID>`. Copy the
  **Installation ID**. → vault (non-secret metadata; used to mint the 1h
  installation token).
- Note the App's **integration/actor id** if you will assert it is not a ruleset
  bypass actor (used by `verify_review_gate_active`'s `app_actor_id`).

## 4. Configure the required-review ruleset (one-time, on the repo)

The App's authority is only safe if the repo actually requires review. On the
repo: Settings → Rules → **New branch ruleset**, targeting the default branch:
- **Require a pull request before merging** → Required approvals **1**,
  **Require review from Code Owners**, **Dismiss stale approvals on push**,
  **Require approval of the most recent reviewable push**.
- Add a repo-root `CODEOWNERS` (`.github/CODEOWNERS` or `CODEOWNERS`) with
  `* @<owner>` and protect it (it should itself require code-owner review).
- **Bypass list**: leave it EMPTY. The App must NOT be a bypass actor — if it
  is, autonomous-merge verification fails closed and refuses.

This ruleset is what makes **manual merge safe with minimal scope**: the owner's
review + these rules enforced by GitHub at merge are the whole gate. Autonomous
merge additionally *pre-verifies* this configuration via the verifier identity
(step 6) before enabling auto-merge; `manual` stays available with an explicit
unprotected-repo warning if the pre-verify can't run.

## 5. Owner user token (for review submission)

The owner's chat **approval** is submitted as a GitHub review using the owner's
**user access token** (8h; the vault lane handles the OAuth refresh — E4 just
consumes it via `StaticTokenProvider(purpose=user_review)`). Obtain it through
the App's user-authorization (OAuth) flow when the owner connects their account.
Minimum scope: `Pull requests: write` on the target repo.

## 6. (AUTONOMOUS ONLY) Owner ruleset-read verifier token

**Skip this for the default (manual) mode.** For `auto` / `not_before`, wire a
**ruleset-read verifier identity** — the owner's token (or a fine-grained PAT)
that has **ruleset read/write on the repo** so GitHub returns `bypass_actors`.
E4 consumes it via `github_http.verifier_client(token)` /
`StaticTokenProvider(purpose=ruleset_verify)` and uses it ONLY for the gate
read, never for merging. This is the disclosed extra grant that autonomous merge
costs; the App's merge identity stays minimal.

## Credential placement summary

| Credential | Secret? | Destination |
|---|---|---|
| App ID | no | vault metadata (JWT `iss`) |
| App private key (`.pem`) | **YES (crown jewel)** | vault `SecretStore` — never a repo/universe artifact, never logged |
| Installation ID | no | vault metadata (mints 1h installation token) |
| App integration/actor id | no | config for the `app_actor_id` bypass check |
| Owner user access token | **YES** | vault (8h token + refresh); E4 consumes via `user_review` purpose |
| Owner ruleset-read verifier token (AUTONOMOUS ONLY) | **YES** | vault; E4 consumes via `ruleset_verify` purpose — gate reads only, never merges |

## Verify it works (read-only)

With credentials in env, run the env-gated live smoke (no writes):

```bash
TINYASSETS_GITHUB_LIVE_SMOKE=1 \
TINYASSETS_GITHUB_SMOKE_REPO=<owner>/<repo> \
TINYASSETS_GITHUB_SMOKE_BRANCH=main \
TINYASSETS_GITHUB_SMOKE_PAT=<fine-grained-pat>   # or the App triple \
python scripts/github_live_smoke.py
```

It prints `verify_review_gate_active`'s verdict (gated / what's missing) and
performs **no writes**. Green here means the App id / key / installation and the
required-review ruleset are all wired correctly.

## Later upgrade: webhooks

The MVP reconciles PR state by re-reading GitHub immediately before reporting
success (polling). When throughput warrants it, add a webhook (Pull request +
Pull request review events) and set `hook_attributes.active = true` — the
projection store's `reconcile_projection` is already the write target a webhook
consumer would call.
