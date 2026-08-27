# Codex opposite-provider review — subscription-platform precedents

Date: 2026-08-10  
Reviewed artifact: `docs/design-notes/2026-08-10-subscription-platform-precedents.md`  
Initial provider: Claude  
Review provider: Codex  
Freshness: primary and official sources rechecked 2026-08-10; no customer accounts or paid runs were used.

## Executive judgment

**ADAPT.** The note establishes a real market pattern and its strongest claim about
Claude Code Routines is accurate. It does not establish a customer-launch safe harbor.
Only Depot is fully documented end to end as hosted cloud + setup-token + genuine Claude
Code. ClawHosters and DevBoxer publicly advertise the relevant shape, but their public
materials do not prove every load-bearing runtime/auth detail. Terragon is a valid
historical precedent, but it used an in-product Claude OAuth flow, operated publicly for
roughly seven months rather than nine on the available dated record, and provides no
evidence that Anthropic reviewed or accepted its structure.

The sibling structures review remains controlling for customer launch: current Anthropic
documentation says third-party developers should use API authentication and may not route
Free/Pro/Max credentials on behalf of users. Live vendor practice demonstrates demand and
some present tolerance; it does not override that written default.

## Verdicts

1. **EXISTENCE/ACCURACY — ADAPT.** Depot is fully verified; ClawHosters and DevBoxer are
   currently advertised and documented, but their exact genuine-CLI/auth path is not fully
   public. Terragon's hosted Claude Code + subscription architecture and traction shutdown
   are verified from its source snapshot, while the public duration is about seven months
   and "no Anthropic action" can only be stated as "none publicly found."
2. **ROUTINES — APPROVE.** Anthropic says Routines run on Claude Code web/cloud
   infrastructure, work without a laptop, draw normal subscription usage, and have daily
   caps of Pro 5, Max 15, Team/Enterprise 25. Extra usage can exceed included caps, and
   one-off runs do not count against the daily Routine cap, so these numbers are a product
   control, not a universal policy safe harbor.
3. **ENFORCEMENT PATTERN — ADAPT.** The Jan. 9 client restriction, Mar. 19 OpenCode legal
   removal, Apr. 4 harness-class cutoff, May credit plan, and Jun. 15 pause are supported.
   No verified event was found that selected on compute location or named a hosted vendor
   running the genuine CLI. But the Apr. 4 action was broader than header spoofing, the
   universal negative is not provable from public reporting, and current written policy
   makes developer routing/custody—not binary identity—the customer-product boundary.
4. **SURVIVING-HOSTED PLAYBOOK — ADAPT.** The ingredients reduce abuse, custody, and
   capacity risk but do not grant permission. Add written Anthropic approval before any
   customer token intake; account-wide identity/concurrency/budget enforcement; encrypted
   vaulting, audit, revoke/delete, and incident controls; kill switch and API-key/Managed
   Agents fallback; and policy-version monitoring. Treat Routines caps as one input, not a
   safe harbor.
5. **RECONCILIATION — ADAPT.** Written default governs customer launch; live practice
   calibrates only implementation and internal-dogfood risk. Build provider-neutral and
   security machinery now, dogfood founder-only under tight controls, and ship hosted
   customer subscription custody only after written approval.

## Evidence corrections and gaps

### Hosted platforms

- **Depot: verified.** Its official quickstart says remote agent sandboxes run Claude Code
  in Depot's cloud and instructs Max users to generate `claude setup-token` and store it as
  the organization-scoped `CLAUDE_CODE_OAUTH_TOKEN`. The CLI reference confirms remote
  execution by default. This is the strongest third-party precedent, but the public secret
  scope is an organization, not proof of one token per human.
  - https://depot.dev/docs/agents/claude-code/quickstart
  - https://depot.dev/docs/agents/overview
- **ClawHosters: hosted + token paste verified; genuine CLI not verified.** Its official
  page says a setup-token powers a dedicated hosted OpenClaw instance and is stored on its
  servers, but says the token is passed to the OpenClaw gateway. It does not state that the
  ClawHosters runtime invokes the genuine `claude` binary. Current OpenClaw docs prefer a
  Claude CLI backend, while retaining setup-token as a separate auth-profile path; that is
  not enough to infer ClawHosters' deployment configuration. Its wording also explicitly
  says this avoids paying for separate API access, contradicting the note's clean
  "survivors never market API-cost avoidance" correlation.
  - https://clawhosters.com/docs/claude-setup-token
  - https://docs.openclaw.ai/anthropic
- **DevBoxer: current offer verified; mechanism and executed transaction unverified.** The
  live official site advertises hosted cloud sandboxes, Claude Code, recurring automations,
  separate $30/$60 infrastructure plans, and "Connect ChatGPT or Claude subscription."
  Public docs do not disclose the Claude credential flow, and this review did not create a
  paid account/run.
  - https://www.devboxer.com/
  - https://www.devboxer.com/docs
- **Terragon: architecture and traction reason verified, duration corrected.** The published
  source snapshot installs/tests Claude Code in hosted sandboxes, implements a product-run
  Claude OAuth flow, stores access/refresh tokens, and advertises BYO subscriptions. Its
  shutdown note says insufficient traction, with service through 2026-02-09. Dated release
  notes begin 2025-06-30 and the public beta announcement appeared in early July, supporting
  about seven months of public operation, not nine. The in-product OAuth flow is the exact
  mechanism the current Anthropic text now warns third-party developers not to offer.
  - https://github.com/terragon-labs/terragon-oss
  - https://github.com/terragon-labs/terragon-oss/blob/main/apps/docs/content/docs/resources/shutdown.mdx
  - https://github.com/terragon-labs/terragon-oss/blob/main/apps/www/src/components/credentials/add-credential-dialog.tsx
  - https://github.com/terragon-labs/terragon-oss/blob/main/apps/www/src/server-actions/claude-oauth.ts

"No public enforcement found" must not be rewritten as "Anthropic took no action." Vendor
pages prove an offer exists; without a paid canary they do not prove current successful
model execution, and without private correspondence they do not prove approval or silence.

### Claude Code Routines

The strongest claim is accurate. Anthropic's announcement says Routines are saved
automations that run on Claude Code web infrastructure on a schedule, API call, or event,
with nothing dependent on the user's laptop. It gives exact daily caps—Pro 5, Max 15,
Team/Enterprise 25—and says runs draw normal subscription usage. The docs call each run a
cloud environment and autonomous full Claude Code cloud session. The API reference says
the backing sessions run on Anthropic-managed cloud infrastructure and are billed as
Claude Code subscription usage.

- https://claude.com/blog/introducing-routines-in-claude-code
- https://code.claude.com/docs/en/routines
- https://platform.claude.com/docs/en/api/claude-code/routines-fire

Important nuance: current docs say one-off runs do not count against the daily Routine cap,
and organizations can continue on metered extra usage. The fixed numbers therefore do not
define all "subscription-fair autonomous cloud usage." They are useful conservative
defaults for included scheduled starts, alongside token/time/concurrency limits.

### Enforcement and the current default

- Jan. 9 is supported by contemporaneous Roo Code and OpenCode issues carrying the backend
  rejection that the credential was authorized only for Claude Code.
  - https://github.com/RooCodeInc/Roo-Code/issues/10566
  - https://github.com/anomalyco/opencode/issues/7456
- Mar. 19 is supported by OpenCode PR 18186, which removed the auth plugin and Anthropic
  references "per legal requests."
  - https://github.com/anomalyco/opencode/pull/18186
- The Apr. 4 cutoff was communicated as a class rule for third-party harnesses, including
  OpenClaw; it was not limited in wording to spoofed clients.
  - https://www.techradar.com/pro/bad-news-claude-users-anthropic-says-youll-need-to-pay-to-use-openclaw-now
- The May credit proposal and Jun. 15 pause are preserved in Anthropic's current help page.
  The operative line says Agent SDK, `claude -p`, and third-party app usage still draw from
  subscription limits; the same page says shared production automation should use the API.
  - https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
- Most importantly, Anthropic's current legal/compliance page says developers building
  products should use API keys and may not offer Claude.ai login or route Free/Pro/Max plan
  credentials on behalf of users. It offers contact sales for questions. This text applies
  even if the user pasted the credential and the genuine CLI sends the request.
  - https://code.claude.com/docs/en/legal-and-compliance

No public counterexample was found in which Anthropic singled out compute location or
named Depot/DevBoxer/ClawHosters. Official GitHub Actions, setup-token, devcontainer, and
Codespaces docs independently support the narrower claim that remote/cloud compute is not
itself prohibited when the user configures Claude Code for their own environment.

## Reconciled risk-graded recommendation

### BUILD now — low risk

- Provider-neutral user-executor and queueing architecture; customer-owned laptop/VPS
  execution where TinyAssets never receives the Claude credential.
- API-key, Workload Identity Federation, and Managed Agents routes for TinyAssets-hosted
  customer execution.
- An inert hosted-subscription adapter behind a founder-only, fail-closed flag; do not ship
  customer token intake or customer-facing connect copy.
- KMS/envelope-encrypted secrets, credential access audit, rotation/revocation/deletion,
  tenant binding, provider receipts, emergency disable, and API fallback.
- One Anthropic account identity mapped to one aggregate concurrency/run/token budget across
  every universe and daemon. "One credential per universe" is insufficient because a user
  can create many universes against one subscription.
- Configurable scheduled-run caps seeded conservatively from Routines, plus concurrent-run,
  wall-clock, token, and rolling-plan budgets. Do not imply the 5/15/25 figures are a safe
  harbor.
- Send the contact-sales request now and require a written answer covering hosted custody,
  Pro/Max versus Team/Enterprise, genuine `claude -p`, user-created schedules, revocation,
  volume, and whether a short-lived delegated/session token is available.

### DOGFOOD now — medium risk

- Founder-only use of the founder's own subscription for the founder's own work, either on
  founder-controlled compute or in one explicitly internal hosted universe.
- The founder personally generates/pastes the setup-token; genuine `claude -p` only; no
  other user, no pooling, low concurrency and run caps, full audit, immediate revocation,
  and a tested API-key/disable fallback.
- Do not call this approved, do not onboard beta users, and do not use the dogfood result as
  evidence that customer custody is permitted.

### SHIP to customers — high risk until approval

- Default customer routes may be API key/WIF/Managed Agents or a user-controlled executor
  with local Claude authentication.
- Any TinyAssets-hosted storage or use of a customer's Claude subscription credential—even
  manual setup-token paste and genuine CLI—requires prior written Anthropic approval.
- With approval, prefer Anthropic-minted short-lived, scoped delegation over a one-year
  setup-token. Preserve per-account isolation/budgets, revocation, audit, kill switch,
  truthful billing copy, and separate infrastructure charges. The approval, not the
  marketing posture or Routines analogy, is the launch gate.

## Fold-back

This review does not authorize an implementation lane. The existing sibling-note gate is
confirmed and sharpened: founder-only dogfood may continue; customer hosted-subscription
intake remains blocked on written Anthropic approval and custody hardening. No STATUS row
was added because there is no narrow implementation request in this review and the shared
coordination file is concurrently modified.

PRECEDENTS_VERDICT: ADAPT
