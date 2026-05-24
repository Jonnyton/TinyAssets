# Provider Identity Bridge

Status: accepted design direction from 2026-05-02 host direction; folded into
`PLAN.md` and the MCP host customer matrix in branch
`codex/provider-identity-bridge`.

## Problem

The same human may reach Workflow through Claude, ChatGPT, Codex, OpenClaw,
local IDE hosts, and future MCP clients. The product goal is that the user can
control their own daemons, capacity grants, money-adjacent balances, and
connected account assets from whichever logged-in chatbot they are using.

The unsafe shortcut is treating "the chatbot session is logged in" as Workflow
account authority by itself. Provider login proves that the user is logged into
that provider account. It does not prove which Workflow account it should bind
to, which daemon/runtime/capacity scopes it controls, or whether money,
credential, or account-access authority has been delegated.

## Proposed Boundary

Use a provider identity bridge:

1. **Person identity:** the Workflow account / real owner. Launch design
   currently names GitHub OAuth as the first identity primitive, with native
   accounts later if needed.
2. **Client identity:** Claude.ai session, ChatGPT session, Claude Code, Codex
   desktop, local tray, CLI, IDE host, or future MCP host. These are surfaces,
   not users.
3. **Daemon identity:** a soul-bearing daemon, separate from both the user and
   the client surface that summoned or controlled it.
4. **Runtime identity:** a temporary execution instance bound to provider,
   model, executor backend, budget, and lease.
5. **Authority binding:** the durable record of what a given client is allowed
   to do on behalf of a given Workflow user.
6. Each chatbot/provider identity becomes a verified external identity binding
   on the Workflow account: `provider`, `provider_subject`, verification time,
   assurance level, scopes, revocation status, and last proof.
7. Binding a provider requires an explicit linking ceremony: OAuth/PKCE where
   available, or a signed one-time nonce shown in Workflow and returned through
   the provider client. A provider session cannot self-assert ownership.
8. Once linked, low-risk reads and reversible controls may feel automatic from
   that provider, but every operation still checks tenant, owner, grant,
   runtime lease, state scope, target version, and action class.
9. High-risk classes stay gated even for linked sessions: irreversible actions,
   credential custody, external account writes, financial/crypto transfers,
   regulated submissions, and final publish/submit boundaries.
10. For crypto or money-like flows, Workflow may prepare, validate, simulate,
    queue, explain, and hand off. It must not execute prohibited transfers on
    the user's behalf. Reversible internal ledger proposals can be batched only
    when the reversal semantics are real and tested.

## Rollout Implications

1. A request started in Claude should be inspectable or continuable from ChatGPT
   if both are bound to the same Workflow user and the ChatGPT client has
   authority for the requested action.
2. A daemon summoned from ChatGPT must not create a duplicate of the
   Claude-side daemon. Resolve by Workflow account, user-owned universe,
   daemon identity, and soul/version before creating a new daemon.
3. Approvals and ownership bind to the Workflow user/account and audited
   authority grant, not just a chat thread.
4. Daemon memory attaches to the daemon and user-owned universe, not the
   chatbot surface that triggered it. Client/provider metadata is audit and
   routing context.
5. Security-sensitive actions may still require per-client re-authentication or
   stronger evidence, even when the client is already linked.
6. Public UX should avoid provider jargon: "same Workflow account, different
   connected apps."

## Relationship To Existing Plan

This follows existing constraints rather than replacing them:

- `PLAN.md` already says GitHub OAuth is the launch identity primitive and
  sessions are scoped per user.
- `PLAN.md` says human control belongs at irreversible boundaries and
  reversibility earns batched autonomy.
- `PLAN.md` says provider compliance is a product boundary: Workflow can
  prepare, explain, validate, simulate, or hand off provider-forbidden actions,
  but cannot disguise the final prohibited action as daemon work.
- `docs/design-notes/2026-05-01-hostless-byok-cloud-daemon-capacity.md`
  requires ownership-scoped control semantics, no subscription cookie/session
  scraping, broker-only credential use, scoped write proxies, budget
  reservation, revocation, and simulated multi-user proof.

## Data Shape Sketch

```text
workflow_users
  id
  primary_identity_provider
  created_at

external_identity_bindings
  id
  workflow_user_id
  provider                 # github | openai | anthropic | codex | openclaw | ...
  provider_subject_hash
  display_hint
  assurance_level          # unverified | nonce | oauth | workspace_admin
  scopes                   # read, reversible_control, propose, publish_request, ...
  status                   # active | revoked | rotation_needed
  verified_at
  last_seen_at

authority_grants
  id
  workflow_user_id
  binding_id
  grant_type               # daemon_control | capacity | credential | ledger | account_asset
  allowed_actions
  reversible_until
  budget_or_limit
  status
```

## Open Questions

- Which provider bindings are acceptable for launch besides GitHub OAuth?
- Does ChatGPT/OpenAI app identity expose a stable subject suitable for account
  linking, or must first launch use a Workflow-side nonce?
- Which actions can be made genuinely reversible enough for checkpoint/batched
  approval, and which must stay final-step handoff?
- What is the minimum simulated multi-user test proving that Claude, ChatGPT,
  Codex, and OpenClaw sessions cannot cross-control another user's daemon,
  capacity, money-like grants, or connected accounts?

## Implementation Follow-Up

Current design fold-in lane:

- Branch: `codex/provider-identity-bridge`
- Worktree: `../wf-provider-identity-bridge`
- PR expectation: ready docs/design PR after checks
- First write set: this note, `PLAN.md`, and
  `docs/design-notes/2026-05-01-mcp-host-customer-matrix.md`

Do not implement runtime identity or account-control code from this design note
alone. First create a new implementation lane against current auth/control-plane
work, active review gates, prior-provider memory refs, and related compliance
implications.
