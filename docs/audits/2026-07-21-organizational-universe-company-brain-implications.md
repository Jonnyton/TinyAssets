# Organizational Universes and Company-Brain Implications

**Status:** Codex initial research and architecture implications; no runtime
build is authorized. Current TinyAssets evidence was checked at `0bc841aa` on
2026-07-21, with later `origin/main` changes called out where material.
External claims use the current official sources below. The required Claude
review returned **ADAPT**; its corrections are folded in and the durable review
is adjacent to this report. This remains planning research and does not
authorize an OpenSpec or implementation lane.

## Executive answer

The idea fits TinyAssets unusually well if the product boundary stays clean:

- a **universe design** is a versioned, remixable company-brain blueprint--its
  graph, roles, evaluators, policy defaults, connector recipes, dashboards, and
  deployment requirements;
- an **organization universe instance** is one company's private running state,
  people, grants, documents, conversations, memories, credentials, budgets,
  audit records, and accepted compute/model routes; and
- Slack, Teams, email, ticketing, CRM, and HR systems are **interaction and
  event surfaces**, not the canonical brain, identity authority, or workflow
  database.

That makes a company brain another democratized stack artifact: a startup can
fork a proven organizational design, bind its own directory and systems, choose
its own cloud/BYOC/market execution, and keep private company state isolated.
The reusable design can enter the commons; the company's people, prompts,
documents, traces, credentials, and learned memory do not.

Current TinyAssets has useful beginnings--multi-tenant user identity, universe
visibility plus ACLs, graphs, goals, audit-oriented receipts, WorkOS auth, and
provider-neutral MCP. It does **not** yet have a canonical organization object,
membership lifecycle, SCIM/Directory Sync, group-to-role policy, enterprise
connector grants, retention/legal hold, or organization-scoped audit export.
Calling the current surface an enterprise company-brain platform would be an
overclaim.

There is also an unresolved binding-architecture contradiction, not an
implementation detail. Canonical PLAN currently says all platform-stored data
is public-by-definition and private content lives only on user/organization-
controlled hosts; private work may be unavailable when no such host is online.
Under that rule, an always-on private company brain must run on an organization-
controlled cloud/on-prem host.

But the host-ratified direction in
`docs/specs/2026-06-10-tiny-first-principles-spec.md` section 11 explicitly says
permissioned-cloud-private is the compliance-grade north star and “supersedes
prior commons-first absolutism”--without that decision being folded into
canonical PLAN. Live code already deepens the conflict: MCP-reachable
`daemon_memory_capture` defaults records to `visibility=host_private` with a
`sensitivity_tier` and writes them to platform-root `daemon_brain.db`, exactly
the platform-private flag pattern current PLAN forbids.

Before an organization OpenSpec, the host must decide and PLAN must state which
model is operative: public platform + organization-controlled private data
plane, or a permissioned platform-private tier with its required cryptography,
residency, contracts, isolation, deletion, and evidence. The existing live
contradiction must be resolved either way; this research does not silently pick
one.

## Frontier convergence and market analogues

The frontier is converging on the same split:

- Slack now documents native agent surfaces and an MCP client/server direction,
  with streamed/threaded interaction, suggested prompts, tool invocation, and
  explicit confirmation for real-world actions. A private organization app can
  therefore make a remote TinyAssets universe feel native without moving the
  brain into Slack.
- Microsoft Copilot Studio publishes one agent across Teams/Microsoft 365 and
  other channels. Its newer federated Copilot connector pattern uses MCP to
  retrieve live data under source permissions without first indexing it into
  Microsoft 365; its synced connector is the contrasting copied/indexed model.
- Glean and Atlassian Rovo validate the existing-work-surface cockpit: the same
  assistant/agent appears in Slack/Teams, cites sources, continues threads, and
  can take actions. Their ambient/every-message triggers should be opt-in,
  visibly disclosed, channel-scoped, and disabled by default for sensitive
  profiles.

TinyAssets should adopt the interoperable surface, not their centralized data
model: remote MCP for capability discovery/invocation, source-ACL-aware
federated retrieval by default, explicit-copy bindings when justified, and
TinyAssets-native durable state/receipts behind every surface.

## Product shape

```text
Organization directory / IdP / HRIS
       SCIM or normalized directory events
                    |
                    v
Organization + memberships + groups + policy bindings
                    |
Slack / Teams / email / CRM / tickets / MCP / webhooks
          interaction and event adapters
                    |
                    v
Private organization-universe instance
  graph + goals + nodes + durable handles + governed memory
                    |
                    v
Execution authority bundle
  requester compute + required model grant OR accepted market offer(s)
                    |
                    v
Receipts, audit/evidence, retention, export, incident workflow

Reusable universe design ------------------------------> public/private commons
Private organization state ----------------------------> never promoted by default
```

## Domain model

### Organization is not a universe and not an identity provider

Add a first-class organization boundary rather than overloading founder or
universe ownership:

| Concept | Responsibility |
|---|---|
| `Organization` | customer/tenant boundary, verified domains, policy profile, billing/market account references |
| `OrganizationMembership` | user-to-organization lifecycle and status; never inferred only from email domain |
| `DirectoryConnection` | external IdP/SCIM/HRIS authority and synchronization cursor |
| `DirectoryGroupBinding` | external group to TinyAssets role/policy mapping |
| `OrganizationRole` | stable role identifier composed from permissions; customer-defined roles allowed |
| `UniverseMembership` | a member's role(s) within one organization universe |
| `ConnectorInstallation` | Slack/Teams/etc tenant/workspace installation and bounded grants |
| `OrganizationUniverseInstance` | a private runtime binding from one immutable universe-design version |
| `PolicyProfileBinding` | versioned regulatory/internal policy packs plus explicit customer overrides |
| `ExecutionAuthorityBundle` | owner-scoped compute plus any required model access, or accepted market coverage |
| `AuditReceipt` | append-only actor/action/resource/policy/authority/result evidence |

One person may belong to several organizations and several universes with
different roles. One organization may run several universes--for example,
company-wide operations, support, engineering, and a tightly restricted health
or finance enclave. Cross-organization access is an explicit federation/share
grant, never an accidental result of shared Slack channels or matching email.

### Blueprint versus instance

The reusable blueprint declares:

- required node/graph/evaluator interfaces;
- suggested organization roles and separation-of-duty constraints;
- connector recipes and minimal requested scopes;
- data classes and default retention purposes;
- required deployment/compute/model capabilities;
- policy-pack compatibility and evidence tests; and
- upgrade/migration rules.

The instance supplies private bindings: real employees, channels, documents,
credentials, budgets, vendors, model/compute grants, policies, and learned
memory. Publishing or upgrading a blueprint never uploads those bindings.
Remixing produces a new design lineage; applying it to an instance requires a
reviewable migration plan and policy re-evaluation.

## Identity and employee lifecycle

Corporate directories remain the lifecycle authority. SCIM 2.0 or a normalized
Directory Sync provider should feed idempotent events for users, groups, and
access rules. WorkOS already offers the relevant provider-neutral direction:
Directory Sync maps organizations to external directories and emits changes;
Microsoft Entra can provision and deprovision users/groups through SCIM.

Required behavior:

1. An admin proves control of the organization and binds SSO/directory.
2. Provisioning creates or links membership without silently merging unrelated
   identities that share an email.
3. External groups map to stable organization roles through explicit rules.
4. Role changes are versioned and auditable.
5. Deprovisioning immediately blocks new sessions and effects, revokes connector
   and execution grants, cancels eligible leases, and schedules policy-correct
   ownership transfer/deletion--without erasing records under hold.
6. Break-glass access is time-bounded, justified, separately approved where
   required, and fully audited.

Directory/HRIS data is input, not the only authorization decision. TinyAssets
must combine external lifecycle state with local universe role, policy profile,
resource sensitivity, device/session assurance when available, and action risk.
SCIM group priority alone is not enough for separation of duties.

Canonical principal identity is `(organization_id, issuer, subject)`. Slack,
Teams, directory, workspace, and channel identifiers are external bindings, not
global user IDs. SCIM is an asynchronous lifecycle projection: authorization
still checks current local policy, membership, and revocation at request/effect
time. Provisioners must handle rate limits, out-of-order events, dangerous
deprovision semantics, and reconciliation rather than assuming webhook delivery
is complete.

## Slack, Teams, and existing-system control

### What users should be able to do

From their existing collaboration surface, authorized users should be able to:

- ask/search/summarize with citations and sensitivity-aware redaction;
- create, inspect, approve, pause, cancel, and resume durable work;
- review goals, tasks, incidents, budgets, market quotes, and evidence;
- contribute documents or decisions into an explicitly selected universe;
- receive actionable notifications and human-in-the-loop approval cards;
- administer membership/policy only when the enterprise identity and TinyAssets
  role both permit it; and
- deep-link to durable TinyAssets records for complex review, export, or
  governance actions.

The chatbot message is a command proposal. It is not authorization by itself.
Every inbound event resolves organization, installation, workspace/team,
channel/chat, external actor, TinyAssets principal, universe, action, and
policy before effect.

### Adapter contract

Each enterprise-system adapter needs the same narrow contract:

- verified installation identity and tenant/workspace binding;
- least-privilege, purpose-labelled grants with expiration/revocation;
- signed event verification, replay window, deterministic event ID, durable
  acknowledgement, dedupe, and bounded payload/reference handling;
- explicit mapping of external users/groups/channels to organization/universe;
- typed inbound artifacts and typed outbound effects;
- rate-limit/backoff and provider idempotency/status reconciliation;
- a destination policy check immediately before every external effect; and
- append-only receipt plus export to the customer's SIEM/audit sink.

Prefer delegated or resource-specific permissions over organization-wide app
permissions. Default interaction triggers are DM, explicit mention, command,
shortcut, or approved card/modal. Ambient channel capture needs a named admin
policy, allowlisted channel, visible disclosure, data-class and retention
approval, and an easy disable path. Installation removal, token revocation,
tenant migration, missed/lifecycle notifications, subscription expiry, and
reauthorization are first-class adapter states with repair cursors.

Slack officially separates Events/Web APIs, organization-wide installations,
SCIM, and read-only Audit Logs. Microsoft similarly separates Teams app/bot or
Adaptive Card interaction, Microsoft Graph notifications/actions, Entra
identity provisioning, and Purview audit/retention. TinyAssets should preserve
those boundaries rather than pretend one bot token is a universal enterprise
grant.

### Interaction surface is not canonical storage

Slack/Teams retention, legal hold, guest/shared-channel behavior, edits,
deletions, and eDiscovery coverage vary by plan and content type. Therefore:

- store a durable TinyAssets command/effect receipt and bounded evidence
  reference, not an uncontrolled copy of every conversation;
- preserve the external message ID, tenant/workspace, channel scope, actor,
  policy decision, and content hash where lawful/useful;
- classify whether authoritative content remains in the source, is imported by
  explicit policy, or is transformed into a governed artifact;
- make deletion/retention propagation explicit and testable; and
- never promise that deleting one system's copy deletes all other systems'
  copies.

Federated retrieval is the default for sensitive or rapidly changing sources:
query under the current user/service identity, enforce source ACLs at query
time, and capture source URI/object/version/observation time with the citation.
Copy or index only under a declared purpose; every copy receives data class,
source-ACL snapshot, retention/deletion behavior, residency, and hold overlay.

## Governance and permissions

Use composable permissions and policy, not fixed job-title logic:

- organization administration;
- membership/group binding;
- universe read/contribute/operate/admin;
- connector install/read/write/admin;
- execution quote/approve/spend/operate;
- sensitive-data access/export/delete/hold;
- blueprint publish/remix/upgrade;
- audit/read/export; and
- policy-author/policy-approve/break-glass.

High-risk actions support four-eyes approval and separation of duties. Example:
the person who edits a finance payment workflow cannot alone approve its new
production connector grant and release a payment effect.

Authorization must be evaluated at action time, not cached for an entire chat
session. A removed employee, revoked Slack installation, changed group, expired
market offer, or tightened policy must stop the next effect even if the workflow
started earlier.

## Deployment and execution authority

An organization chooses its deployment profile:

- TinyAssets-hosted control plane plus organization BYOC/model access;
- organization-controlled cloud/private network installation;
- hybrid/on-prem connector or executor with outbound-only leases;
- accepted market compute/model offers allowed by organization policy; or
- authoring-only/held mode when no eligible execution authority exists.

The platform still supplies no user task/model execution quota. Every
interactive, scheduled, event, autonomous, retry, resume, child, or research
run carries the complete authority bundle from the organization/requester or
accepted market contract. Policies may restrict region, host identity,
attestation, model/vendor, data class, retention, subprocess/network access,
maximum spend, and whether private artifacts may leave an enclave.

## Multi-organization isolation and scaling

The scalability report's target topology applies directly: stateless gateways,
transactional organization-bearing authority, durable queues, tenant-fair
leases, and BYOC/market executors. Every key row and receipt carries
`organization_id`; every data query and realtime topic is organization scoped;
RLS is defense in depth, not a substitute for application authorization.

Load tests must include:

- thousands of members across many organizations plus one hot company universe;
- SCIM create/update/deactivate storms and out-of-order/replayed events;
- Slack/Teams reconnect and webhook floods;
- shared/external channels, guests, service accounts, and user renames;
- one tenant exhausting queue, connector, market, or provider quota;
- revoked membership during a long run and immediately before an effect;
- forged organization/universe/connector/task/offer identifiers;
- retention/hold/export/deletion conflicts; and
- zero cross-tenant artifact, credential, model, compute, billing, or audit leak.

## Current TinyAssets fit and gaps

| Surface | Current fit | Material gap |
|---|---|---|
| Universe/graph/goal | Strong conceptual substrate | No organization-universe instance/blueprint binding contract |
| Identity | WorkOS JWT identity; authenticated writes | No organization membership, SSO connection lifecycle, SCIM, or group sync |
| Authorization | Universe visibility plus read/write/admin ACL | Too coarse for enterprise roles, connector grants, spend, export, hold, and separation of duties |
| MCP | Provider-neutral interaction surface | Slack/Teams are not MCP-equivalent identity/event/effect adapters |
| Automation | Expressive graph substrate | Boundary-layer ingress/effect/retry/connection obligations not implemented end to end |
| Audit/evidence | Receipts/idempotency concepts exist | No organization-wide immutable audit schema/export/retention policy |
| Data lifecycle | Private/public universe concepts | No classification, purpose, retention, legal hold, subject/request workflow, or residency binding |
| Execution | Provider routing and daemon/market concepts | Current provider-routing truth conflicts with owner/market-only authority; market path is not operational |
| Scale | Multi-tenant target is aligned | Current deployment remains one origin/files/SQLite/process state; no enterprise load proof |

Additional current-code truth sharpens those gaps:

- WorkOS `org_id` and `role` are surfaced only as metadata and are not used for
  authorization; current authenticated users receive broad default capability
  categories.
- authorization is exact ACL/grant membership with no deny precedence, groups,
  purpose/data/region/device/time conditions, obligations, or break-glass model;
- the identity baseline still defaults unknown auth configuration to dev
  no-auth and missing visibility rules to public, while an active visibility
  change proposes a fail-closed rule but remains unimplemented;
- audit is fragmented and some mutation paths do not roll back when audit append
  fails; one engine helper still has an environment actor fallback that
  contradicts the canonical identity spec; and
- account upsert reactivates users, sessions can have no expiry, token
  resolution does not enforce account active state, and capability grants lack
  an expiry/revoke lifecycle; enterprise offboarding is therefore not present;
- the credential vault is not an organization KMS or policy-aware secret store,
  while connector/effect-ledger requirements are stronger in OpenSpec than the
  implemented runtime.
- founder universes and missing visibility rules are currently public by
  default, while the active private-visibility change is not implemented and no
  public action currently supplies complete visibility administration; this
  alone blocks a private company-brain pilot.
- daemon `tenant_id` is metadata rather than an enforced boundary: daemon
  list/get paths are global, so tenant-filter and soul/metadata isolation need a
  P0 repair before organizational use.
- current external-effect consent is universe-wide, has no actor/org scope or
  expiry, and one dispatch maps caller-supplied author text into grant
  attribution; consent storage/enforcement also appear to resolve different
  base directories on the shared server.
- the seeded `orgchart.md` is descriptive prose, excluded from governed soul
  edits, and not an authorization source; it cannot substitute for organization
  membership or roles.
- deployed containers disable AppArmor/seccomp confinement and provider turns
  depend on tool denylists, which is insufficient for regulated untrusted
  organization workloads.
- memory has useful universe/user/goal/branch/node scopes, but only universe
  enforcement is on by default, legacy untagged rows can pass, and there is no
  organization/department/ethical-wall scope.

Fresh adjacent tests on 2026-07-21 at `0bc841aa` passed **117 tests in 26.11
seconds** across WorkOS, action scopes, 12-founder isolation, ACL behavior,
effector consent, and deploy-auth hardening. This is useful correctness evidence,
not proof of organization isolation or enterprise capacity; the audit found no
organization/Slack/Teams/offboarding/retention test surface.

Reproduction (Windows/Python 3.14; no other setup):

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider tests/test_workos_provider.py tests/test_action_scopes.py tests/test_multi_tenant_isolation.py tests/test_memory_scope_stage_2b3.py tests/test_effector_consents.py tests/test_extensions_consent_actions.py tests/test_predeploy_auth_hardening.py
```

Result: `117 passed, 1 warning in 26.11s`; the warning was the existing
Starlette TestClient/httpx deprecation. Fresh `origin/main` was four commits
ahead at audit end; the auditor inspected that delta and found no later
organization/ACL/connector/retention/daemon-registry implementation.

## Recommended sequence

1. Resolve provider authority, boundary-layer effect semantics, and scale
   authority first. Name `R2-1a` (strict authorized-provider selection) and
   `R2-1b` (race-safe provider/credential-class receipt) as direct dependencies;
   an organization feature cannot safely sit on founder quota or process-local
   tenancy.
2. Create an OpenSpec change for organization identity/membership plus a policy
   decision contract; do not begin with a Slack bot.
3. Add normalized SSO/directory connection, SCIM lifecycle, group bindings, and
   organization/universe roles with deprovision tests.
4. Add governed `ConnectorInstallation` and generic ingress/effect receipts,
   then implement Slack as the first conformance adapter and Teams as the second.
5. Add blueprint/instance packaging, private-binding separation, upgrade review,
   and commons publication leak tests.
6. Add organization audit export, retention/hold/deletion orchestration, SIEM
   delivery, and regulated policy-profile bindings.
7. Prove multi-tenant scale, revocation-at-effect, noisy-neighbor isolation, and
   zero founder-resource use through rendered Slack/Teams and chatbot paths.
8. Reconcile canonical PLAN's commons-first rule with the host-ratified
   tiny-first-principles section 11 direction and the live platform-root
   `host_private` daemon-memory behavior; do not silently blend the models.
9. File and repair the confirmed consent storage/enforcement base-directory
   mismatch as an independent live bug; do not wait for the organization lane.

## Adopt / adapt / avoid

**Adopt:** SCIM lifecycle; external IdP as identity source; stable local roles;
least-privilege installations; durable event dedupe; explicit audit/retention;
versioned blueprints; customer-controlled compute/model authority.

**Adapt:** Slack/Teams app UX into a shared connector contract; IdP group roles
into local policy rather than blindly trusting group priority; enterprise
retention into cross-system lifecycle orchestration; company-brain templates
into sanitized universe designs.

**Avoid:** treating a channel as a tenant; inferring membership from email;
storing bot tokens as general credentials; copying whole workspaces by default;
making Slack/Teams the source of workflow truth; publishing learned private
memory with a design; promising enterprise compliance from feature presence.

## Source provenance

Primary TinyAssets evidence:

- `PLAN.md` Project Thesis, Scoping Rules, Daemon Platform, Providers, API & MCP;
- `docs/specs/2026-06-10-tiny-first-principles-spec.md` section 11/11.3;
- `openspec/specs/identity-auth-and-access-control/spec.md`;
- `openspec/specs/boundary-layer/spec.md`;
- `openspec/specs/graph-execution-substrate/spec.md`;
- `openspec/specs/live-mcp-connector-surface/spec.md`;
- the concurrent-user, Zapier, and compute-market implication reports in this
  research lane.

Current official external references:

- Slack APIs and organization-ready apps:
  <https://api.slack.com/apis> and <https://api.slack.com/enterprise/apps>
- Slack agent and remote-MCP surfaces:
  <https://docs.slack.dev/ai/> and <https://docs.slack.dev/ai/agents/>
- Slack admin, SCIM, and Audit Logs APIs:
  <https://api.slack.com/admins> and <https://api.slack.com/admins/audit-logs>
- Slack retention and legal holds:
  <https://slack.com/help/articles/203457187-Customize-data-retention-in-Slack>
  and <https://slack.com/help/articles/4401830811795-Create-and-manage-legal-holds>
- Microsoft Entra SCIM provisioning:
  <https://learn.microsoft.com/en-us/entra/identity/app-provisioning/scim-support-in-entra-id>
  and <https://learn.microsoft.com/en-us/entra/identity/app-provisioning/how-provisioning-works>
- Microsoft Graph Teams change notifications and activity notifications:
  <https://learn.microsoft.com/en-us/graph/teams-changenotifications-appinstallation>
  and <https://learn.microsoft.com/en-us/graph/teams-send-activityfeednotifications>
- Microsoft Teams permissions, lifecycle notifications, and federated Copilot
  connectors:
  <https://learn.microsoft.com/en-us/microsoftteams/app-permissions>,
  <https://learn.microsoft.com/en-us/graph/change-notifications-lifecycle-events>,
  and <https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/federated-connectors-overview>
- Microsoft Purview retention and Teams eDiscovery:
  <https://learn.microsoft.com/en-us/purview/retention> and
  <https://learn.microsoft.com/en-us/purview/edisc-search-teams>
- WorkOS Directory Sync and role assignment:
  <https://workos.com/docs/directory-sync> and
  <https://workos.com/docs/directory-sync/identity-provider-role-assignment>
- Official product analogues for embedded enterprise agents:
  <https://docs.glean.com/administration/assistant/slackbot/about-slackbot>,
  <https://docs.glean.com/administration/glean-agents-in-microsoft-teams/glean-agents-ms-teams>,
  and <https://support.atlassian.com/rovo/docs/using-the-atlassian-rovo-slack-app/>
