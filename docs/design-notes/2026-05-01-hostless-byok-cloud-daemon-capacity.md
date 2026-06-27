# Hostless BYOK Cloud Daemon Capacity

Status: proposal for host review, not yet canonical PLAN.md truth.
Host correction 2026-05-01: v1 should be the full product surface, but
host-only/private exposure first. The host is the first exposed real tenant;
multi-user pressure is simulated until the security, budget, and load gates
prove the surface.
Follow-up correction 2026-05-01: host-only alpha must still be multi-tenant
and fleet-ready from day one. No shortcut may assume "only Jonathan forever";
new users and new daemon fleets should be able to join by changing exposure and
capacity limits, not by redesigning storage, authorization, or scheduling.
Date: 2026-05-01

## Summary

The right reframe is: users should not need to operate a machine to run
API-backed daemons. A phone or browser should be enough to grant bounded
capacity, set schedules, cap spend, choose state permissions, and revoke
access. Workflow's always-on control plane can then run daemon activations
in a cloud worker pool.

This plugs into the 2026-05-01 live PLAN direction: daemon control is
chatbot-first, tray is only a convenience surface, and all daemon controls are
ownership-scoped operations across phone, browser, local app, and cloud
sessions. Cloud BYOK is not a second control plane. It is one executor backend
behind that ownership-scoped daemon control contract.

This does not mean "no host exists." It means the old user-facing "host" idea
splits into three concepts:

- **Capacity grant**: a user's permission for Workflow to spend a bounded
  amount of model/provider capacity on specific work.
- **Control intent**: an ownership-scoped chatbot/web/local command such as
  summon, pause, resume, restart, banish, or update behavior.
- **Executor backend**: where work actually runs, such as Workflow cloud
  BYOK workers, a local tray, a future third-party host, or a platform-funded
  public pool.

Daemon identity remains durable and soul-bearing. Runtime becomes leased and
ephemeral. We should not run one always-on process per daemon. At thousands
of users and thousands of daemons, daemon "running" means "eligible to be
activated under this grant," not "a process is burning resources forever."

First-build recommendation:

1. Ship the **full private alpha surface**: cloud BYOK, local tray/private
   backend, schedules, active mode, daemon controls, budget kill, revocation,
   audit logs, and paid/network-path simulations.
2. Keep v1 exposure host-only by default, but build the data model, API,
   scheduler, and authorization as real multi-tenant infrastructure. The host
   is the only real exposed tenant at first; simulated tenants and synthetic
   grants provide load, abuse, and accounting pressure before public access.
3. Support only official provider APIs or official OAuth integrations, not
   copied subscription sessions or browser cookies.
4. Treat credential custody, budget reservation, scoped writes, and idempotent
   activation commits as launch blockers, not follow-ups.
5. Add a capacity-grant layer behind the ownership-scoped daemon control API,
   not a separate tray-first or backend-specific control surface. Existing
   `submit_request` should gain capacity-backed fulfillment paths, while grant
   management lives behind one small account/capacity API.
6. Prove scale with tests before treating it as public-ready: thousands of
   daemon identities, simulated users, hundreds of concurrent activations,
   quota pressure, revocation, and budget-kill scenarios.
7. Be ready for more users and daemons at all times: onboarding the next user
   should be an exposure/capacity decision, not a migration away from
   single-user assumptions.

## External Research Snapshot

Checked 2026-05-01 against current public documentation:

- OpenAI says API keys should not be shared, should not be deployed in browser
  or mobile clients, and should be kept server-side or in a key-management
  service. Source: [OpenAI API key safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety).
- OpenAI projects support project-scoped service accounts, API key permissions,
  model/rate-limit configuration, and budgets. Project budgets are monitoring
  alerts, not hard blocking caps, so Workflow still needs its own hard caps.
  Source: [OpenAI projects](https://help.openai.com/en/articles/9186755-managing-your-work-in-the-api-platform-with-projects/).
- OpenAI rate limits are organization/project/model resources, not per-user
  in the way Workflow needs. OpenAI recommends app-side user limits for
  bulk/programmatic access and exponential backoff for 429s. Source:
  [OpenAI rate limits](https://platform.openai.com/docs/guides/rate-limits).
- Anthropic rate limits are organization/workspace/model resources with
  response headers and `retry-after`; workspace limits can protect one pool
  from consuming all capacity. Source:
  [Anthropic rate limits](https://docs.anthropic.com/en/api/rate-limits).
- Supabase Vault stores encrypted secrets in Postgres and can store API keys;
  decrypted access must be restricted to backend service roles. Source:
  [Supabase Vault](https://supabase.com/docs/guides/database/vault).
- Supabase Queues provides Postgres-native durable queues through `pgmq` with
  guaranteed delivery, exactly-once delivery within a visibility window,
  archival, and RLS-aware authorization. Source:
  [Supabase Queues](https://supabase.com/docs/guides/queues).
- Supabase Realtime has concurrent connection quotas that scale by plan or
  custom quota. This supports channel-sharded presence/broadcast, but it is
  not a free infinite socket layer. Source:
  [Supabase Realtime concurrent connections](https://supabase.com/docs/guides/troubleshooting/realtime-concurrent-peak-connections-quota-jdDqcp).
- Cloudflare Queues can support high-throughput edge queueing, but queue
  consumers have finite batch, concurrency, duration, and CPU limits. Source:
  [Cloudflare Queues limits](https://developers.cloudflare.com/queues/platform/limits/).
- Phones are not reliable arbitrary daemon hosts. Apple documents that
  backgrounded iOS apps run only briefly before suspension; Android imposes
  background service limits and steers background work through scheduler APIs.
  Sources: [Apple Background App Refresh](https://support.apple.com/en-ie/118408),
  [Android background execution limits](https://developer.android.com/about/versions/oreo/background).

Implication: phone/browser should be control surfaces, not execution surfaces.
Cloud BYOK is the path for zero-install always-on execution. Local tray remains
for local/private/software-bound execution.

## Existing Workflow Constraints

This proposal must preserve these project commitments:

- **Chatbot-first daemon control.** The tray is a convenience surface, not the
  primary control plane. Cloud, phone, browser, and local sessions all submit
  ownership-scoped control intents through the same contract.
- **Zero daemons required for authoring.** Node, branch, goal, browse, fork,
  and edit flows cannot depend on daemon capacity.
- **Separate daemon identity from runtime.** `daemon_id` and soul identity are
  durable. Runtime allocation is separate and may move across providers.
- **Commons-first architecture.** Public concepts live in the platform commons.
  Private instance data lives on a host and does not become platform data.
- **Browser-only users are first-class.** A phone-only user should be able to
  get useful work done, including long-running work, through cloud mediation.
- **No fake success.** If provider capacity, budget, or permissions are absent,
  Workflow must say queued, blocked, revoked, over-budget, or provider-limited.
- **Scale proof is part of done.** Any uptime-track runtime feature needs a
  load/concurrency proof, not just unit tests.
- **Full v1 does not mean public v1.** The first build includes the whole
  control/capacity surface, but real external users remain gated until the
  host-only alpha plus simulated multi-user tests survive security, budget,
  revocation, and load proof.
- **Host-only alpha is not single-tenant architecture.** Every table, queue,
  audit event, credential, grant, daemon binding, and runtime activation has an
  owner/tenant boundary from the first build. The product may expose only the
  host initially, but the system stays ready for the next user and their daemon
  fleet without redesign.

## Terms

### Daemon

Durable public/forkable agent identity. May have a soul file. May be eligible
for different node/gate policies. A daemon is not a process.

### Runtime Activation

One leased execution of one daemon for one work item. It has start/end times,
provider/model, executor backend, budget reservation, state scopes, logs, and
result artifacts.

### Control Intent

An authenticated, ownership-scoped daemon command issued from chat, web, phone,
local app, or cloud session. It may apply immediately if the executor backend
is reachable, or it may be durably queued until the owning backend proves
authority over the daemon. It returns explicit states such as `accepted`,
`queued`, `needs_host_connection`, `forbidden`, `revoked`, or `applied`.

### Capacity Grant

A user-owned authorization record that says what Workflow may spend and touch.
It includes provider credential reference, model allowlist, capabilities,
visibility, schedule, active-mode policy, concurrency, spend caps, and state
scopes.

### Credential Broker

The only backend service allowed to unwrap provider credentials. Normal tables
store credential fingerprints, provider names, permission summaries, status,
and secret references only. Workers request short-lived credential use through
the broker; the broker checks owner, grant status, activation lease, scope,
budget reservation, egress policy, and audit requirements before a provider
call. Supabase Vault, KMS, or another secret store may back the broker, but the
broker interface is the architecture.

### Budget Reservation

An atomic hold against a capacity grant before an activation starts. The hold
uses worst-case model/input/output/retry estimates, is reconciled to actual
usage after provider calls, and is released or reduced on cancellation. No
activation starts without a successful reservation, and no activation commits
after the reservation is revoked or exhausted.

### Executor Backend

Where an activation runs:

- `workflow_cloud_byok`: Workflow cloud worker uses a user-provided official
  API credential under a capacity grant.
- `local_tray`: user's machine runs the activation. Required for local LLMs,
  local files, private instance data, and local software/hardware.
- `third_party_host`: future network or paid-market host capacity.
- `platform_pool`: future platform-funded public/commons capacity, if the
  treasury chooses to subsidize it.

### State Scope

The exact Workflow state the grant may read or write. Scopes are narrow and
auditable, for example `read:public_catalog`, `read:branch:<id>`,
`write:draft_branch:<id>`, `propose:branch:<id>`, `publish:branch:<id>`.

State scopes are typed capabilities, not arbitrary JSON policy blobs. The
worker receives scoped inputs and returns proposed operations; a scoped write
proxy validates the operation, target, owner, grant, activation lease, artifact
version, and budget state before commit.

### Activation Outbox

A durable record of proposed state changes from an activation. Queue delivery
is treated as at-least-once even when the queue offers stronger delivery inside
a visibility window. Commits are idempotent by activation id, operation id, and
target version; duplicate delivery must not duplicate writes, cost ledger rows,
settlement rows, or notifications.

## Product Shape

The primary product surface is the conversation. Users should be able to say
"summon a daemon," "pause all daemons tonight," "let this daemon use $10 of my
OpenAI API budget while I sleep," or "banish the research daemon" from Claude.ai
on a phone, ChatGPT in a browser, a local coding agent, or the website.

The user-facing product should stop saying "install a host" as the default. It
should say "add capacity" or "allow daemon runs." Installation is required only
when the chosen executor backend is local.

The capacity chooser has two initial choices:

1. **Cloud capacity**: connect an API provider, set a budget, choose schedule,
   choose what state the daemon may touch, done. Works from phone/browser.
2. **Local capacity**: install tray when the work needs local models, local
   files, local software, or private instance data.

This makes T2 broader than "daemon host." T2 becomes **capacity provider**.
The local tray is one backend under T2, not the whole tier, and it is not the
control authority of record. The ownership-scoped daemon control API is.

## Why Phone Hosting Is The Wrong Primitive

Phone hosting sounds attractive because it avoids installing a desktop host,
but it fails the product goal:

- iOS and Android can suspend or defer background work.
- The user may close the app, lose network, run out of battery, or disable
  background refresh.
- Provider API keys must not live in a mobile client.
- Long-running daemons need retries, queues, leases, budget enforcement, and
  logs that outlive the device.

So the phone should control capacity, not provide capacity. It is the steering
wheel, not the engine.

## Scenarios And Implications

### Scenario A: Phone-only user wants overnight work

User says from Claude.ai or ChatGPT: "Run 100 daemon attempts overnight and
show me the best branch in the morning."

Flow:

1. Chatbot checks `capacity_grants`.
2. No grant exists, so it offers cloud capacity setup.
3. User connects OpenAI or Anthropic API access through official key/OAuth
   flow, sets `$10 tonight`, schedule `22:00-07:00`, max concurrency `5`.
4. Workflow creates a grant with write scope limited to a draft branch.
5. Scheduler enqueues activations during the allowed window.
6. Worker pool leases tasks, uses token-bucket quota, records cost, and stops
   at budget or schedule end.
7. Morning summary links to resulting branches and audit log.

Design implications:

- Need schedule windows on grants.
- Need hard Workflow spend reservation, not just provider-side alerts.
- Need activation audit visible from chat and web.
- Need pause/revoke to halt queued and running activations.
- Need idempotent job retry so a worker crash does not duplicate writes.

### Scenario B: User has a ChatGPT/Claude subscription, no API key

User asks: "Can you use my subscription to run daemons?"

First-build answer:

- Not in cloud unless the provider offers an official delegated API mechanism
  for that subscription.
- No copied session cookies, private OAuth tokens, or browser automation against
  consumer chat UIs.
- If the provider has an official CLI or local app path the user may run under
  their own account, that belongs in `local_tray`, not Workflow cloud.

Design implications:

- UI copy must say **API capacity**, not vague "subscription" capacity.
- Provider adapters must declare supported auth modes.
- Unsupported subscription auth must fail closed with a useful explanation.

### Scenario C: User wants private invoice workflow while asleep

User wants daemons to read PDFs, extract data, and push to accounting software.

First-build answer:

- If PDFs are private instance data, cloud BYOK v1 does not run this.
- Use local tray, or wait for a separately approved confidential-cloud design.

Design implications:

- Cloud BYOK cannot become an accidental platform-private-data store.
- `state_scopes` must distinguish public concept state from private instance
  references.
- `instance_ref` pointing to local files is non-readable by cloud workers.
- Chatbot should say: "This needs local capacity because the inputs are private
  files."

### Scenario D: Thousands of users turn on active daemons

10,000 users each configure 1-5 daemon identities, some with active mode.

Wrong design:

- Spawn 50,000 long-running daemon processes.
- Let every daemon poll all work.
- Let every worker independently discover provider capacity by trial and error.

Correct design:

- Store daemon identities and desired active policy.
- Materialize eligible work queues by capability/provider/visibility.
- Use queue leases for activations.
- Rate-limit by provider, model, user, grant, and platform pool.
- Do not activate a daemon unless there is work, scheduled proactive work, or
  an allowed low-stakes stay-busy task.

Design implications:

- "Daemon running" is not a process count.
- Need queue sharding by capability/provider.
- Need token buckets and circuit breakers before provider calls.
- Need materialized demand views so active daemons read cheap ranked work.

### Scenario E: Provider returns 429s or budget is exhausted

Activation is mid-run and the provider says rate-limited.

Flow:

1. Provider adapter parses rate-limit headers and `retry-after`.
2. Activation transitions to `rate_limited_waiting` or `provider_exhausted`.
3. Scheduler delays retry with jitter.
4. If budget cannot cover retry, activation stops as `budget_exhausted`.
5. Chatbot/web UI shows exact reason and next available time where known.

Design implications:

- Provider adapters must expose normalized quota evidence.
- Retrying failed calls still burns some provider limits, so retry budgets need
  caps.
- Budget reservations must account for worst-case output, then reconcile actual
  usage.

### Scenario F: User revokes capacity

User taps "Stop all daemons" from phone while on vacation.

Required behavior:

- New activations stop immediately.
- Queued activations are canceled or paused.
- Running activation receives cancellation; if it cannot stop instantly, it
  enters `cancel_requested` and loses permission to commit further writes.
- Credential is disabled in Workflow and user is told how to rotate/revoke at
  provider if needed.

Design implications:

- Every write path checks activation lease and grant status at commit time.
- Credential refs have `disabled_at`.
- Provider calls require live grant status, not cached credentials in workers.

### Scenario G: Public paid market uses cloud BYOK capacity

User opts in: "Let my daemons earn credits when I am asleep."

The public paid market is not externally enabled in first exposure, but its
shape is simulated in v1 so the architecture stays ready. When publicly
enabled:

- The grant must include `visibility=paid`, price floor, tax/payment readiness,
  and public capability claims.
- The grant owner pays provider cost and earns ledger settlement.
- Scheduler must prevent negative-margin work unless the user explicitly allows
  it.

Design implications:

- Self-capacity and paid-market capacity share grant primitives, but paid
  market adds settlement, abuse, reputation, and tax surfaces.
- V1 includes synthetic paid/network capacity runs, settlement stubs, and
  negative-margin checks.
- Do not admit real paid-market work until self-capacity and simulated
  paid/network pressure are proven.

## First-Build Architecture

### V1 Scope

Build the full product surface, but expose it as a host-only private alpha
until simulated multi-user proof passes. "Host-only" is an exposure policy, not
a storage or scheduler shortcut.

In v1:

- Cloud executor backend: `workflow_cloud_byok`.
- Local executor backend: `local_tray` remains available for local models,
  local software, private files, and private instance data.
- One real provider adapter first, preferably OpenAI API because project keys,
  service accounts, key permissions, and project-scoped limits are documented.
- Provider adapter interface supports additional official API/OAuth providers
  without changing daemon control semantics.
- Full daemon controls: create/summon/list/get/pause/resume/restart/banish/
  update behavior/status, all ownership-scoped.
- Full capacity controls: create/update/pause/resume/revoke grants, rotate
  credentials, estimate capacity, list activations, kill activations.
- Schedules and active mode are in scope, including sleep/vacation/always-on
  windows.
- Budget reservation, budget kill, quota backoff, revocation, audit log,
  activation outbox, and scoped write proxy are launch blockers.
- Paid/network capacity is not publicly enabled, but the grant model,
  activation accounting, settlement stubs, and synthetic paid-market scenarios
  exist so public enablement is a policy flip plus compliance review, not a
  redesign.
- Public/commons and user-owned draft branch state may be used when scoped.
- Private instance data runs through `local_tray` in v1 unless a separate
  confidential-cloud design is approved.
- No consumer subscription/session auth. Official API/OAuth only.
- Multi-user readiness is mandatory: simulated tenants, synthetic grants, and
  load tests exercise thousands of users/daemons before real public exposure.

### Control Plane Components

```
chatbot / web
  |
  | capacity API + submit_request
  v
Workflow gateway
  |
  | validated request, grant, scopes
  v
Postgres canonical state
  |-- capacity_grants
  |-- provider_credentials (secret refs only)
  |-- budget_reservations
  |-- runtime_activations
  |-- activation_outbox
  |-- usage_ledger
  |-- request_inbox
  |-- audit_events
  |
  | queue message by capability/provider/grant
  v
Durable queue
  |
  | lease
  v
Cloud worker pool
  |
  | request provider call through credential broker
  | enforce quota/budget/scope
  v
Credential broker (unwraps secrets; audited; short-lived use only)
  |
  v
Provider API
  |
  | result + usage + proposed operations
  v
Activation outbox -> scoped write proxy -> Workflow state
```

### Data Model Sketch

```
capacity_grants(
  grant_id uuid primary key,
  tenant_id uuid not null,
  owner_user_id uuid not null,
  executor_backend text not null,        -- workflow_cloud_byok | local_tray | ...
  provider text not null,                -- openai | anthropic | gemini | local
  credential_id uuid null,               -- references provider_credentials
  display_name text not null,
  capability_ids text[] not null,
  model_allowlist text[] not null,
  visibility text not null,              -- self | network | paid
  state_scopes jsonb not null,
  schedule_policy jsonb not null,
  budget_policy jsonb not null,
  max_concurrent int not null,
  always_active bool not null default false,
  status text not null,                  -- active | paused | revoked | degraded
  version bigint not null default 1,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  revoked_at timestamptz null
)

provider_credentials(
  credential_id uuid primary key,
  tenant_id uuid not null,
  owner_user_id uuid not null,
  provider text not null,
  secret_ref text not null,                 -- broker-owned Vault/KMS ref
  key_fingerprint text not null,
  permissions_summary jsonb not null,
  status text not null,                  -- active | disabled | rotation_needed
  created_at timestamptz not null,
  disabled_at timestamptz null
)

daemon_capacity_bindings(
  binding_id uuid primary key,
  tenant_id uuid not null,
  daemon_id uuid not null,
  owner_user_id uuid not null,
  grant_id uuid not null,
  desired_parallelism int not null default 1,
  active_policy jsonb not null,
  status text not null
)

runtime_activations(
  activation_id uuid primary key,
  tenant_id uuid not null,
  daemon_id uuid not null,
  grant_id uuid not null,
  request_id uuid not null,
  executor_backend text not null,
  provider text not null,
  model text not null,
  state text not null,                   -- leased | running | waiting | succeeded | failed | canceled
  idempotency_key text not null unique,
  lease_expires_at timestamptz not null,
  estimated_cost_usd numeric not null,
  reserved_budget_usd numeric not null,
  actual_cost_usd numeric null,
  provider_request_ids text[] not null default '{}',
  error_code text null,
  error_evidence jsonb null,
  created_at timestamptz not null,
  started_at timestamptz null,
  finished_at timestamptz null
)

budget_reservations(
  reservation_id uuid primary key,
  tenant_id uuid not null,
  owner_user_id uuid not null,
  grant_id uuid not null,
  activation_id uuid not null,
  reserved_usd numeric not null,
  actual_usd numeric null,
  status text not null,                  -- reserved | reconciled | released | exhausted
  created_at timestamptz not null,
  reconciled_at timestamptz null
)

activation_outbox(
  outbox_id uuid primary key,
  tenant_id uuid not null,
  activation_id uuid not null,
  operation_id text not null,
  operation_type text not null,
  target_ref text not null,
  target_version text null,
  proposed_payload jsonb not null,
  status text not null,                  -- proposed | committed | rejected | conflict
  rejection_code text null,
  created_at timestamptz not null,
  committed_at timestamptz null,
  unique(activation_id, operation_id)
)

usage_ledger(
  usage_id uuid primary key,
  tenant_id uuid not null,
  activation_id uuid not null,
  owner_user_id uuid not null,
  grant_id uuid not null,
  provider text not null,
  model text not null,
  input_tokens bigint not null default 0,
  output_tokens bigint not null default 0,
  provider_cost_usd numeric not null,
  workflow_fee_usd numeric not null default 0,
  recorded_at timestamptz not null
)
```

Notes:

- `provider_credentials` never returns the secret to clients.
- `secret_ref` is dereferenced only by the credential broker. Workers do not
  receive raw secrets except through the smallest provider-call path available;
  no secret is persisted outside the broker boundary.
- `tenant_id` exists from the first migration even while real exposure is
  host-only. Simulated tenants use the same paths as future real users.
- `budget_reservations` are created atomically before activation and reconciled
  after usage. Concurrent activations cannot overspend a grant.
- `activation_outbox` is the only path from model output to state mutation.
  Workers propose operations; the scoped write proxy validates and commits.
- `state_scopes` must be enforced both when reading inputs and when committing
  outputs. Scope checks at job start are not enough.
- `version` gives optimistic concurrency for grant edits.

### API Contract Sketch

Keep the public MCP/tool surface small. The live PLAN direction already calls
for ownership-scoped daemon control operations such as list/get/create/summon/
pause/resume/restart/banish/update/status. Cloud BYOK should extend those
operations with capacity selection, not create a parallel cloud-daemon toolset.

```
capacity(
  action:
    "list_grants"
  | "create_grant"
  | "update_grant"
  | "pause_grant"
  | "resume_grant"
  | "revoke_grant"
  | "rotate_credential"
  | "estimate_capacity"
  | "list_activations"
  | "kill_activation",
  ...
) -> structured result with evidence + caveats
```

Ownership-scoped daemon control wraps capacity decisions:

```
daemon_summon(
  daemon_id?: uuid,
  soul_ref?: text,
  executor_preference?: "workflow_cloud_byok" | "local_tray" | "any",
  grant_id?: uuid,
  capability_id: text,
  model?: text,
  desired_parallelism?: int
) -> {
  daemon_id,
  binding_id,
  control_state: "applied" | "queued" | "needs_capacity" |
                 "needs_host_connection" | "forbidden",
  next_actions: [...]
}

daemon_control_status(
  daemon_id?: uuid,
  activation_id?: uuid
) -> {
  daemon,
  bindings,
  activations,
  capacity_grants,
  caveats
}
```

`submit_request` gains one peer fulfillment path:

```
fulfillment_path:
  "dry_run"
| "free_queue"
| "paid_bid"
| "capacity_prompt"
| "cloud_byok"
| "local_tray"
| "simulated_paid_capacity"
```

`capacity_prompt` replaces the old one-off `self_host_prompt` language. If no
grant or host can satisfy the work, the response explains which capacity is
missing and offers cloud BYOK, local tray, or a future paid/network option.

For capacity-backed fulfillment, request validation requires:

- Active capacity grant.
- Tenant/owner authorization for the daemon, grant, target state, and request.
- Matching capability and model.
- Current time inside schedule, or explicit user override.
- Successful atomic budget reservation.
- State scopes cover all requested reads and writes.
- Request does not require local software, local file access, or private
  instance data unless the selected backend is `local_tray`.
- Idempotency key for activation and proposed writes.
- Activation outbox path for every state mutation.

Error shape should be consistent:

```
{
  "ok": false,
  "error": {
    "code": "BUDGET_EXHAUSTED" | "GRANT_REVOKED" | "SCOPE_DENIED" |
            "PROVIDER_RATE_LIMITED" | "PRIVATE_DATA_REQUIRES_LOCAL" |
            "UNSUPPORTED_AUTH_MODE" | "CREDENTIAL_BROKER_DENIED" |
            "BUDGET_RESERVATION_CONFLICT" | "TENANT_FORBIDDEN",
    "message": "...",
    "details": {...},
    "next_actions": [...]
  }
}
```

### Scheduler And Dispatch

First build should use a durable queue and leases. Supabase Queues is the
lowest-friction match if the platform remains Supabase-first; Cloudflare
Queues is a good edge alternative if queue throughput or worker placement
pushes us there.

Scheduling rules:

- Every queue message includes `tenant_id`, `owner_user_id`, `grant_id`,
  `daemon_id`, `activation_id`, and an idempotency key.
- Queue names partition by `provider:model:capability` where practical.
- Workers lease one activation at a time or small batches.
- A worker must re-check grant status, budget, schedule, and scope after lease
  and before every state write.
- The queue is treated as at-least-once delivery. Even if a queue backend
  promises exactly-once delivery within a visibility window, Workflow side
  effects are idempotent by activation/outbox operation.
- A provider token bucket gates requests before the provider call.
- A grant token bucket gates per-user concurrency.
- A tenant token bucket gates total per-tenant concurrency so a future user
  fleet cannot starve another tenant.
- A global platform token bucket prevents the cloud worker pool from exhausting
  shared infrastructure.
- Failed jobs use bounded exponential backoff with jitter.
- Dead-letter queue stores durable failure evidence for debugging.

Important scale invariant:

No daemon polls the world. Work appears in capability-sharded queues or
materialized views, then workers claim specific activations.

Host-only alpha invariant:

The first real tenant may be the host, but simulated tenants must use the same
queues, budget reservations, credential-broker denials, scoped write proxy, and
audit paths as future real tenants. Any code path that says "because only the
host exists" is a bug unless it is an explicit exposure gate outside the core
runtime.

## Ownership-Scoped Control Semantics

Every daemon control command must answer three questions before it touches
runtime state:

1. **Who owns the daemon identity or runtime binding?**
2. **Which executor backend is allowed to apply this command?**
3. **What is the smallest durable state transition we can safely record now?**

Examples:

- Phone user pauses a cloud BYOK daemon: control plane marks the grant/binding
  paused immediately; queued activations stop; running activations receive
  cancellation and lose commit authority.
- Phone user pauses a local-tray daemon while the tray is offline: control
  plane records `queued_control_intent`; the tray applies it on next outbound
  connection before doing more work.
- Chatbot tries to banish a daemon owned by another user: return `forbidden`
  with no side effects.
- Browser user summons a daemon but has no capacity grant: return
  `needs_capacity` and offer cloud BYOK or local tray setup.

This is the key relationship to the current implementation step in STATUS.md:
the ownership-scoped daemon control API is the substrate; cloud BYOK capacity
is one execution backend and one grant type underneath it.

## Security Model

### Credentials

Rules:

- No provider key in browser, phone, localStorage, app logs, or MCP response.
- No consumer subscription cookie/session/OAuth scraping.
- Key entry happens through HTTPS to a backend endpoint or through an official
  OAuth/provider flow.
- Credential is stored behind a credential broker backed by Vault, KMS, or an
  equivalent secret store. The broker interface is the architecture; the
  backing store is swappable.
- Store only fingerprint, provider, permission summary, and status in normal
  tables.
- Workers may request provider calls through the broker, but must not query or
  log raw credential material directly.
- Broker responses are short-lived and activation-scoped. The broker checks
  tenant, owner, grant status, activation lease, budget reservation, egress
  policy, and audit status before use.
- On revoke, disable the Workflow credential immediately and tell user how to
  rotate at provider if needed.

First-build key posture:

- Accept one OpenAI project-scoped key or service-account key.
- Require user to attest it is a key created for Workflow.
- Recommend restricted key permissions where provider supports them.
- Fixed egress / IP allowlist support is not optional architecturally. It may
  arrive after the first private alpha deploy, but v1 cannot be called
  public-ready until provider keys can be restricted to Workflow egress where
  the provider supports it.
- Credential custody copy must be explicit: BYOK means Workflow is allowed to
  use the key under the grant. It does not mean Workflow owns the key, can use
  it outside scope, or can protect the user from provider-side charges after
  the user bypasses Workflow.

### Authorization

Every read/write path checks:

- Tenant boundary.
- Authenticated `owner_user_id`.
- Grant is active.
- Activation lease is live.
- `state_scopes` allow this exact operation.
- Target artifact belongs to the user or is public/commons writable under the
  requested action.
- Artifact version token still matches, or write becomes conflict/proposal.

### Prompt And Tool Injection

Cloud BYOK workers handle external content and model outputs. They must not
let prompts grant themselves more access.

Rules:

- State scopes are data, not instructions in the model prompt.
- Worker composes prompts from scoped inputs only.
- Model output is parsed into proposed operations.
- Operations are validated against scopes after model output and before write.
- Proposed operations go through the activation outbox and scoped write proxy;
  workers never mutate canonical state directly.
- Connector pushes require separate connector authorization, not just daemon
  intent.

### Privacy

First-build privacy line:

- Public/commons concepts: allowed.
- User-owned draft branch content that the user permits cloud execution to
  read/write: allowed.
- Local file paths, uploaded private source material, credentials, company
  records, private instance data: not allowed in cloud BYOK v1.

Future confidential-cloud execution would need a separate host-approved design
because it changes the commons-first privacy boundary.

## Budget And Quota Model

Provider budgets and limits are not enough:

- OpenAI project budgets are alerts, not hard caps.
- Provider rate limits are project/org/workspace/model resources.
- User-level fairness is Workflow's job.

Workflow hard-cap flow:

1. Estimate max cost before activation using model, input size, max output, and
   retries.
2. Atomically reserve budget from `capacity_grants.budget_policy` inside the
   same transaction that creates or leases the activation.
3. Refuse activation if reservation would exceed cap.
4. Record provider usage after each call.
5. Reconcile reservation to actual cost.
6. Stop grant when daily/nightly/monthly budget reaches cap.

Budget invariants:

- Reservations are tenant/grant scoped and serializable enough to prevent
  concurrent overspend.
- Every provider call has a per-call max token/output cap and a retry budget.
- Retry reservations are explicit. A retry cannot silently spend unreserved
  budget.
- Reconciliation refunds unused reservation and records actual provider usage.
- Revocation, budget exhaustion, or schedule close prevents future provider
  calls and prevents activation outbox commits after the cutoff.
- Simulated tenants exercise the same reservation path as the host tenant.

Quota flow:

- Provider adapter parses normalized limit headers where available.
- Token buckets track requests/tokens/images/etc. per provider/model/grant.
- Tenant-level token buckets protect future users from noisy-neighbor pressure.
- If provider sends 429, respect `retry-after` and back off the bucket.
- Scheduler degrades gracefully: queued, delayed, provider_exhausted, or
  budget_exhausted.

## Security And Budget Acceptance Contract

This is the non-negotiable launch contract for full v1, including host-only
alpha:

- **No secret exposure:** provider secrets never appear in chat responses,
  browser/mobile storage, logs, audit event bodies, queue payloads, screenshots,
  or activation artifacts.
- **Broker-only credential use:** workers call the credential broker or an
  equivalent provider-call service; direct secret unwrap in worker logic is a
  blocker.
- **Atomic budget reservation:** concurrent activations cannot exceed the
  grant's run/day/month cap in tests.
- **No write after revoke:** killing a grant, activation, daemon binding, or
  tenant permission prevents future commits even if a worker finishes late.
- **Scoped write proxy only:** model output cannot mutate canonical state
  without post-model validation against tenant, owner, state scope, target
  version, grant, activation lease, and budget reservation.
- **At-least-once safe:** duplicate queue delivery, worker retry, or deploy
  restart cannot duplicate writes, ledger rows, settlements, or notifications.
- **Simulated multi-user proof:** before more real users are admitted,
  synthetic tenants must prove RLS/authorization, budget isolation, queue
  fairness, quota pressure behavior, and audit separation.

## User Experience

### Capacity Setup

The setup flow should be short:

1. Choose "Cloud capacity" or "Local capacity."
2. Pick provider/model.
3. Add official API key or OAuth.
4. Set budget: per run, per day, per month.
5. Set schedule: always, sleep hours, vacation window, manual only.
6. Pick state access: read only, propose only, write draft branch, publish
   requires approval.
7. Confirm active daemon count/concurrency.
8. See "ready" with test probe and estimated plan headroom.

### Runtime Controls

Every user needs:

- Pause all.
- Pause one grant.
- Kill one activation.
- Revoke key.
- Rotate key.
- See last N activations.
- See cost by daemon/provider/model.
- See why work is not running.

### Chatbot Language

Good:

- "I can run this in Workflow cloud using your OpenAI API budget."
- "This touches private files, so it needs your local tray."
- "Your budget is exhausted; I can queue it for tomorrow or reduce fan-out."

Bad:

- "Host a daemon" as the only option.
- "Use your subscription" when the provider only supports API billing.
- "No daemon available" when the real issue is missing capacity grant.

## Failure Modes And Required Behavior

| Failure | Required behavior |
|---|---|
| Key invalid | Mark credential `rotation_needed`; pause grant; keep request queued. |
| Key revoked mid-run | Stop provider calls; activation `failed:credential_revoked`; no further writes. |
| Credential broker denies unwrap | Activation `failed:credential_broker_denied`; no provider call; audit denial evidence without secret. |
| Budget exhausted | Stop new activations; finish/cancel according to reservation policy. |
| Budget reservation race | One reservation wins atomically; losers remain queued or return `BUDGET_RESERVATION_CONFLICT`. |
| Schedule window closes | Do not start new activations; running activation may finish only if policy allows. |
| Provider 429 | Delay retry with jitter; surface next retry time when known. |
| Worker crash | Lease expires; activation retries idempotently. |
| Duplicate queue delivery | Idempotency key prevents duplicate writes and duplicate settlement. |
| Scope violation | Reject operation; log `scope_denied`; ask user for narrower approval. |
| Cross-tenant request | Return `TENANT_FORBIDDEN`; no queue message, secret access, or scoped read. |
| Model tries connector push | Require connector authorization and explicit output kind. |
| User taps kill | Re-check grant on every commit path so killed work cannot write after revoke. |
| Realtime outage | Activation continues; status updates replay from durable audit log. |

## Load-Test Proof Required Before Ship

Add Track J scenarios for hostless capacity. These tests run before public
multi-user exposure, but they simulate the next users and daemon fleets from
day one.

### S12: BYOK Grant Storm

1,000 simulated users create grants, update schedules, and submit cloud BYOK
requests in 10 minutes.

Acceptance:

- p99 grant create/update < 1s.
- No secret appears in logs or API responses.
- RLS prevents cross-user grant reads.
- Queue depth and activation state remain consistent.
- Exposing a second real user after this test requires no schema or API change.

### S13: Daemon Identity Versus Activation Scale

10,000 daemon identities, 50,000 bindings, 500 concurrent activations across
simulated tenants.

Acceptance:

- No one-process-per-daemon assumption.
- Scheduler activates only leased work.
- p99 claim/lease < 3s under request storm.
- Tenant token buckets prevent one simulated fleet from starving another.

### S14: Provider Quota Pressure

Synthetic provider returns rate-limit headers and 429s under load.

Acceptance:

- Workers respect `retry-after`.
- Retry storm does not occur.
- Failed attempts do not exceed retry budget.
- Chatbot-visible status says provider limited, not generic failure.

### S15: Budget Kill And Revocation

User budget hits cap while activations are queued/running; user revokes grant
mid-run.

Acceptance:

- New activations stop immediately.
- Running activation cannot commit after revoke.
- Usage ledger balances to actual provider usage.
- UI shows exact stopped reason.

### S16: Private Data Guard

Cloud BYOK request tries to use a local `instance_ref` or private upload.

Acceptance:

- Request fails before queueing with `PRIVATE_DATA_REQUIRES_LOCAL`.
- No cloud worker receives private input.
- Chatbot suggests local tray.

### S17: Credential Broker Red-Team

Synthetic workers, chat requests, and malicious model outputs try to leak,
log, echo, or cross-tenant use provider credentials.

Acceptance:

- No secret leaves the broker boundary.
- Queue payloads and activation artifacts contain only secret refs or
  fingerprints.
- Broker denies wrong-tenant, revoked, over-budget, and expired-lease requests.
- Audit logs record denial evidence without secret material.

### S18: New User Join Drill

Create a second real or simulated account after the host alpha is already
running. Give it one grant, one daemon, one schedule, and one draft branch.

Acceptance:

- No migration or code patch is needed to add the account.
- Existing host daemons, grants, budgets, queues, and audit logs remain
  isolated.
- The new user's chatbot can create, summon, pause, and inspect only its own
  daemons.

## Build Plan

The implementation can land in phases, but v1 is not complete until the full
private-alpha surface exists and passes S12-S18. Partial phases may merge
behind flags; they are not the product promise.

### Phase 0: Decision And Terminology

Files:

- `PLAN.md`
- `docs/design-notes/2026-04-18-full-platform-architecture.md`
- website copy later

Work:

- Accept the live 2026-05-01 PLAN direction as a constraint: chatbot-first
  daemon control, tray convenience, ownership-scoped host actions.
- Record the host correction: v1 is full-surface private alpha, not a narrow
  feature slice.
- Record the second host correction: host-only alpha is multi-tenant and
  fleet-ready from day one.
- Decide whether T2's user-facing name becomes "capacity provider" with cloud
  and local backends.
- Rename user-facing "host daemon" copy to "add capacity" where appropriate,
  without weakening the local-tray path for local/private/software-bound work.
- Keep local tray as a backend and convenience dashboard, not the default
  control plane.

Exit criteria:

- PLAN.md explicitly distinguishes daemon identity, capacity grant, runtime
  activation, control intent, and executor backend.
- PLAN.md or the accepted design note explicitly says no single-user shortcut
  may enter core storage, authorization, scheduling, or queue code.

### Phase 1: Ownership-Scoped Control API And Tenant Boundary

Files likely:

- `tinyassets/api/universe.py`
- `tinyassets/daemon_registry.py`
- `tinyassets/runtime/*`
- `tinyassets/auth/*` or account boundary module
- packaging mirror files
- `tests/test_api_universe.py`

Work:

- Implement `daemon_list`, `daemon_get`, `daemon_create`, `daemon_summon`,
  `daemon_pause`, `daemon_resume`, `daemon_restart`, `daemon_banish`,
  `daemon_update_behavior`, and `daemon_control_status` as ownership-scoped
  operations.
- Persist control intents when the executor backend is not immediately
  reachable.
- Enforce tenant/owner/binding checks before every runtime transition.
- Return explicit states: `applied`, `queued`, `needs_capacity`,
  `needs_host_connection`, `forbidden`.
- Add simulated tenants to tests even while only the host is exposed.

Exit criteria:

- The same chatbot command works from phone/browser/local/cloud session, with
  different execution paths but the same public contract.
- Cloud BYOK can later bind under this API without inventing a separate control
  plane.
- A second user/tenant can be created in tests without schema or API redesign.

### Phase 2: Capacity, Credential, Budget, And Scope Foundation

Files likely:

- `tinyassets/storage/*`
- `tinyassets/api/*`
- `tests/test_capacity_grants.py`
- Supabase migration files when platform backend exists

Work:

- Add `capacity_grants`, `provider_credentials`, `runtime_activations`,
  `budget_reservations`, `activation_outbox`, and `usage_ledger`.
- Add tenant/owner fields and RLS/authorization tests from the first migration.
- Add credential broker interface using Vault/KMS as backing storage.
- Add `capacity` API actions for list/create/update/pause/resume/revoke/
  rotate/estimate/list-activations/kill-activation.
- Add atomic budget reservation and reconciliation.
- Add scoped write proxy so workers propose operations instead of mutating
  canonical state directly.
- Add security tests for no-secret-return, no-secret-log, cross-tenant denial,
  revoke-before-commit, and duplicate outbox delivery.

Exit criteria:

- Host can create a grant with a real or test credential, pause/revoke/rotate
  it, reserve budget, list activations, and prove no secret exposure.
- Simulated tenants cannot see or spend each other's grants.

### Phase 3: Full Private-Alpha Execution Surface

Files likely:

- `tinyassets/runtime/`
- `tinyassets/providers/`
- `tinyassets/api/runs.py` or request API
- `tests/test_cloud_byok_execution.py`
- `tinyassets_tray.py` / desktop runtime surfaces

Work:

- Add `submit_request.fulfillment_path` values:
  `capacity_prompt`, `cloud_byok`, `local_tray`, and
  `simulated_paid_capacity`.
- Add queue producer and worker lease model.
- Add one provider adapter.
- Add scoped write pipeline.
- Add schedules, active mode, pause all, kill activation, status reasons, and
  overnight/always-on policies.
- Connect local tray/private execution as a peer backend under the same daemon
  control and capacity contract.
- Add paid/network simulation paths with settlement stubs and negative-margin
  checks, but keep real public paid intake disabled.

Exit criteria:

- Host can run cloud BYOK, local/private, scheduled, active-mode, and simulated
  paid/network activations through the same chatbot-first control contract.
- Every activation has budget reservation, audit trail, usage ledger, and
  idempotent retry/outbox behavior.

### Phase 4: Chatbot/Web UX And Operational Control

Files likely:

- `tinyassets/api/prompts.py`
- website/account capacity surfaces
- `output/user_sim_session.md`
- live-chat test harness docs

Work:

- Make chatbot language capacity-aware: missing grant, budget exhausted,
  provider limited, private data requires local, grant paused, queued, active.
- Expose activation/audit summaries in chat and web.
- Make phone/browser/local/cloud sessions issue the same control intents.
- Add live user-sim scripts for host-only alpha control flows.

Exit criteria:

- Host can create capacity, summon daemons, adjust schedules, pause/kill/revoke,
  and inspect costs from chatbot and web without reaching for tray-only
  controls.

### Phase 5: Scale, Abuse, And Join-Readiness Harness

Files likely:

- `scripts/load/`
- `tests/load/`
- CI or manual load-run docs

Work:

- Add S12-S18 synthetic scenarios.
- Add fake provider with quota/budget behavior.
- Add 10k identity / 50k binding / 500 activation stress test.
- Add second-user join drill that proves no redesign is needed when more
  users and daemon fleets arrive.
- Add credential broker red-team, scope denial, budget race, and duplicate
  queue delivery tests.

Exit criteria:

- Load/security proof exists before public claim that hostless daemons work.
- Adding the next real user is an exposure/capacity decision, not an
  architecture rewrite.

### Phase 6: Public Exposure Gate

Not a new feature phase. This is the gate that decides whether the full private
alpha can admit more real users.

Work:

- Review S12-S18 results.
- Review credential-custody posture and fixed-egress/IP-allowlist readiness.
- Review budget/accounting evidence and worst-case spend limits.
- Review public paid/network compliance, tax, abuse, settlement, and support
  requirements.
- Set initial public limits: users, grants, daemon bindings, concurrent
  activations, per-provider quotas, and budget caps.

Exit criteria:

- More users can join without schema/API/runtime redesign.
- Public paid/network capacity remains disabled unless compliance and market
  controls are ready.

## Decisions Needed

1. Should T2 be renamed from **Daemon host** to **Capacity provider** in the
   canonical product model, now that tray is explicitly convenience rather than
   primary control plane?
2. Which exact v1 state scopes are allowed for cloud BYOK draft work:
   propose-only, write draft branch, or publish-with-approval?
3. Should first provider be OpenAI API for project/key controls, or Anthropic
   API for product fit with current Claude.ai users?
4. Which backing store should the credential broker use first: Supabase Vault,
   cloud KMS, or a dedicated secret-service component?
5. Is confidential-cloud execution a future product line, or is private
   instance data permanently local/private-backend only?
6. Should `submit_request` replace `self_host_prompt` with broader
   `capacity_prompt` plus backend selection immediately?
7. Should ownership-scoped daemon controls expose one coarse `daemon_control`
   action with sub-actions, or separate MCP actions for each operation? The
   PLAN text lists separate operation names; minimal-primitives pressure argues
   for one coarse tool if chatbot discoverability remains good.
8. What are the first public exposure limits after host-only alpha: max users,
   grants per user, daemon bindings per user, concurrent activations, and
   default budgets?

## Recommendation

Approve the concept and build v1 as a full private alpha:

- **Yes** to hostless cloud BYOK as the default zero-install execution path.
- **Yes** to local tray as the private/local/software backend.
- **Yes** to full v1 controls, schedules, active mode, budget kill,
  revocation, audit, and simulated paid/network capacity.
- **Yes** to host-only first exposure while remaining multi-tenant and
  fleet-ready from day one.
- **No** to using consumer subscription sessions in Workflow cloud.
- **No** to single-user shortcuts in storage, authorization, queues,
  scheduling, budgets, or audit.
- **No** to private instance data in cloud BYOK v1 without separate
  confidential-cloud approval.
- **No** to real paid-market cloud BYOK until self-capacity plus simulated
  paid/network load survives security, budget, and abuse tests.

The winning first build is not "a tiny demo" and not "thousands of
always-running processes." It is the full control and capacity system operating
for the host, with simulated users and daemon fleets proving that the next real
users can join without redesign: thousands of durable daemon identities with
bounded, auditable, revocable runtime activations.
