# Custom-agent app-conversation owner handoff audit

**Freshness:** 2026-08-03 PDT, audited against `origin/main`
`97654c3ebc8d7f866979cb0f9626d031b79c7d25` (PR #2235 foldback), with
read-only inspection of active OpenSpec changes and current source. This audit
authorizes no deployment, app installation, secret mutation, or runtime write.

## Verdict

`connect-custom-agent-app-conversations` is **not yet admissible for runtime
implementation**. The secure custom-agent core, private binding, and first
private conversation custody mode exist, but the trusted app edge does not.
There is currently no production Slack verifier/adapter, no durable app-event
replay owner, no installation/workspace/member-to-TinyAssets authority map, no
custody-grant issuer, and no speaking path for a provider-authenticated app
sender. Current `converse` authorization remains intentionally founder-only.

The shortest safe V1 is narrower than general workspace collaboration:

1. authenticate one Slack installation and event through a generic boundary;
2. map the Slack workspace and sender to the existing TinyAssets account,
   universe, binding owner, and current membership;
3. admit only the mapped universe founder in the first cohort, with every
   other sender receiving a typed refusal;
4. persist the turn through the existing `private_universe` custody mode;
5. invoke the exact active custom-agent runtime identity; and
6. send one reply through the existing connection/effect authority.

That owner-only first slice proves the approved customer demo without inventing
a parallel non-founder permission system. General member/group conversation
remains a later interlocutor/organization-authority expansion.

## Landed foundations

| Foundation | Exact current owner | Handoff state |
|---|---|---|
| Public arbitrary definition, N-parent remix, private channel reference | `universe-custom-agents`; `tinyassets/custom_agents.py`; canonical `universe-custom-agents` spec | Landed. A binding may carry private channel-address and adapter references, while raw credentials, conversations, and effect payloads remain excluded. The reference is configuration, not proof of a live Slack connection. |
| Secure runtime activation and invocation identities | `activate-custom-agent-runtime-core`; `tinyassets/agent_runtime_activation.py`, `agent_runtime_invocation.py`, provider/continuation/health owners | Dark core behavior is built. PR #2230 merged trusted activation; PR #2234 merged cross-process activation/restart/revocation proof. Core tasks 5.1 and 5.2 still require current deployed-head/public-route evidence and final review/sync/archive. |
| Private conversation custody | canonical `conversation-custody` spec; `tinyassets/conversation_custody.py`; `tinyassets/storage/conversation_custody.py` | PR #2224 merged and PR #2227 synced/archived it. The store is append-only, scoped, exportable, deletable, and dark. Every operation requires a one-use signed grant from a future app-conversation authority; no production issuer ships. |
| Outbound connection/effect authority | `outbound-boundary-layer`; `ConnectionLedger` / `ScopedConnectionProxy`; `execute_replay_safe_effect` | Connection grants, credential-blind proxying, caps, system-derived effect identities, and reconciliation exist dark for non-value effects. There is no production Slack adapter or Slack reply reconciler. |
| Interlocutor tier and disclosure ceiling | `reconcile-universe-personification-relay`; `tinyassets/api/interlocutor.py` | T0/T1/T2 derivation and pre-assembly disclosure filtering landed. `authorize_conversation_turn()` still rejects every non-founder, by design. The only production speaking surface is `converse`. |
| Public control surface | canonical `live-mcp-connector-surface` spec; `scripts/mcp_public_canary.py` | Exactly seven handles remain authoritative. App conversation must add no handle and custom-agent control remains routed behind existing graph/status handles. |

## Missing authority and runtime owners

### 1. Canonical authenticated app ingress

`outbound-boundary-layer` tasks 4.1 and 4.2 are still unchecked. Their current
contract covers approved goal/universe webhook and email items joining a
scheduled batch exactly once; it does not yet define the app-event envelope
required by the custom-agent root. Current source contains no Slack signature
verification, timestamp validation, installation-scoped event replay record, or
Slack Events API route.

Before the app successor, the boundary owner must land or explicitly hand off:

- provider authentication before normalization;
- replay identity `(provider, installation_or_tenant_id, event_or_message_id)`
  plus immutable normalized-body digest;
- timestamp, size, rate, attachment, source-approval, and abuse decisions;
- one durable admitted/refused/held event record; and
- raw-auth-material erasure before any agent context or adapter call.

The custom-agent runtime must consume that record. It must not create its own
webhook verifier, inbox table, or replay ledger.

### 2. External app principal and organization mapping

No active OpenSpec change or production API owns Slack installation, workspace,
member/group, role, and offboarding state. `bind-host-principal-to-account` is
not this owner: its optional WorkOS `org_id` is explicitly non-authoritative
metadata, and host-principal ownership is only the verified `(issuer, sub)`.

A narrow prerequisite change must own a provider-neutral mapping with a Slack
adapter. Its server-derived resolver must bind:

```text
verified installation/tenant + workspace + external sender
    -> current TinyAssets subject
    -> current universe + agent binding
    -> current membership/role/offboarding generation
```

Message content, mentions, channel names, webhook secrets, and caller-provided
IDs must never select any right-hand value. Missing, revoked, stale, multiple,
or cross-tenant matches fail closed. The first V1 may require the mapped subject
to equal the binding owner/founder; it must not silently promote other workspace
members.

### 3. Interlocutor and personification handoff

The app path cannot call the current HTTP-request-derived resolver as though a
Slack event were an OAuth bearer request. The interlocutor owner must supply a
trusted mapped-interlocutor seam that consumes the authority result above and
applies the same visibility ceiling before context assembly. For V1, only a
mapped T2/founder proceeds; T0/T1 stay refused.

The same owner must reconcile the first outbound agent speaking surface:
personification tasks 6.4, 6.5, and 6.9 explicitly remain open because outbound
and non-founder surfaces did not exist. A bound agent must speak as that named
agent projection, not impersonate the whole universe and not inherit private
founder grounding beyond the permitted projection.

### 4. Conversation-custody authority integration

Custody deliberately ships no private signing key or self-issuer. The future
app-conversation authority must mint one-use, at-most-five-minute,
request-digest-bound grants only after app authentication, organization/member,
binding owner, custody selection/path, interlocutor, and delivery authority all
pass. The custody store remains storage-only: accepting a message cannot invoke
a provider, mutate a workflow, or send a reply.

### 5. Slack reply adapter and moderation floor

The existing connection/effect boundary can carry a future Slack reply, but
current production drivers do not. The Slack adapter must remain credential
blind, enforce the exact connection grant/destination/effect kind and cap, use
the root's system-derived reply identity, and reconcile or hold ambiguous remote
outcomes without sending a second logical reply.

Ingress also depends on a real bounded abuse/rate decision. The active
`moderation-and-abuse-response` change has not landed its canonical API/rate and
concurrency acceptance. The app successor may begin with an allowlisted bounded
cohort and explicit typed holds, but it must not claim general production
availability or omit the root requirement's abuse gate.

## Admission dependency graph

```text
runtime-core 5.1/5.2 deployed-head + foldback
        |
        +-- boundary ingress/replay handoff
        +-- external app principal/org mapping handoff
        +-- interlocutor founder-mapping + first outbound-voice handoff
        +-- private custody grant-issuer handoff
        +-- outbound Slack effect-adapter handoff
        `-- bounded abuse/rate policy
                         |
                         v
          connect-custom-agent-app-conversations
             (one ingress -> one invocation -> one reply;
              no workflow mutation lifecycle)
```

The app successor itself should remain at most twelve session-sized tasks and
own only integration records/projections that no prerequisite owner already
owns. It must not absorb workflow authoring, add an eighth MCP handle, copy
credentials into a binding or conversation, or introduce a Slack-agent
archetype.

## Exact first-slice acceptance

The first implementation slice is ready to admit only when all of these are
true on the same current main:

- runtime-core 5.1/5.2 are complete and the immutable activation/invocation
  seams are handed off;
- the boundary owner exposes one authenticated, replay-safe app-event record;
- one exact installation/workspace/sender maps to one current founder-owned
  universe and agent binding, with generation/offboarding revalidation;
- the interlocutor owner accepts that trusted founder mapping before assembly;
- the app authority can issue exact one-use custody grants without exposing its
  private key to the runtime;
- the outbound boundary can execute and reconcile one Slack reply under the
  same connection grant; and
- duplicate delivery, changed-body reuse, membership revocation after
  admission, worker restart, revoked connection, and ambiguous reply outcome
  all fail closed under tests.

Final customer acceptance is still later: a rendered real Slack conversation,
deployed exact-seven connector proof, 24-hour PC-off workflow delivery,
cross-account remix/export boundaries, and organic use remain owned by
`prove-custom-agent-runtime-live`.

## Evidence commands

Fresh commands run from the audited worktree:

```text
git log -1 --format='%H %cI %s' origin/main
openspec list --json
openspec status --change activate-custom-agent-runtime-core --json
rg -n -i 'Slack|workspace_id|team_id|installation_id|offboard|membership' tinyassets --glob '*.py'
rg -n 'slack_sdk|slack_bolt|x-slack|chat.postMessage|events_api' . --glob '!tests/**' --glob '!docs/**' --glob '!openspec/**' --glob '!*.lock' --glob '!node_modules/**'
python scripts/docview.py lines openspec/changes/outbound-boundary-layer/tasks.md --start 1 --end 55
python scripts/docview.py lines openspec/changes/reconcile-universe-personification-relay/tasks.md --start 48 --end 67
python scripts/docview.py lines openspec/specs/conversation-custody/spec.md --start 30 --end 60
python scripts/docview.py lines openspec/specs/conversation-custody/spec.md --start 240 --end 255
```

The production Slack implementation search returned no verifier, Events API
route, SDK/HTTP adapter, or post-message call; the only source-code Slack match
was a secret-pattern detector in `tinyassets/auto_ship.py`.
