## Context

Original design recorded September 19, 2026; implementation is now reviewed at
`f9b91ed7`, with final docs/tests and live acceptance still gated. The provisional
choices below are superseded where specified by `turn-contract.md`, the current
delta specs and `release-integration.md`; they are not open implementation asks.
Full PLAN read, including Scoping Rules,
Daemon Platform, Providers, canonical conversation and no platform actor rules.
No PLAN amendment is needed for a caller of existing user-owned graph execution;
retired fleet-era paragraphs are not authority to revive that fleet.

The native public definition/private binding split is already specified in
`openspec/specs/universe-custom-agents/spec.md`. Definitions are immutable,
multi-parent remix preserves lineage, unknown kinds remain portable, and binding
updates are revision guarded. Existing handles already own these operations.
The deployed `AppLayout` consumes just one declarative component and deliberately
never writes the serving binding. The first-party conversation path still
builds persona/context, calls its writer and performs default learning in
`tinyassets/universe_intelligence.py:961-1135`.

Primitive inventory (direct source verification, not absence inference):

| Responsibility | Existing primitive / limitation |
|---|---|
| Discover/read/publish/remix | `universe_server.py:621,1295`, `api/custom_agents.py` |
| Private installation/CAS | `custom_agents.py:1013,1147`, `write_graph target=agent_binding` |
| Public immutable executable snapshot | `write_graph target=branch operation=publish` at `universe_server.py:1144`; `branch_versions.py:234` |
| Snapshot execution | `runs.execute_branch_version_async` and synchronous sibling, same executor core; not a new runtime |
| Current receiver provider authority | `foreground_run_provider.py`, `api/runs.py:59`; each run session uses current verified actor/universe |
| Canonical turn, receipt and model selection | `universe_server.converse`, `universe_intelligence.converse`, `providers/served_model_plan.py` |
| Native component compilation | `agent_runtime_compiler.py:358`, `agent_runtime_plan_compiler.py:412`; these are not installed app/turn consumers |
| Existing UI adapter | `onboarding/app_layout.js`; exact trusted surfaces, no arbitrary code |

`check_primitive_exists.py action` returned CLEAN for run_graph/create_binding/
update_binding/run_branch_version/bind/update. Direct inspection above proves
several already exist: the checker's match coverage is incomplete, so its CLEAN
is NOT evidence authorizing duplicates. No new MCP action is proposed here.

Original user PR #3840 and #3842 remain draft inert source/edit/preview work.
This proposal neither adopts their format as a platform standard nor implements
their designs. The prior inventory and 68 passing layout/custom-agent/interchange
tests established no additional runtime defect for the four-surface layout MVP.
Its outstanding live two-owner proof stays in its own delivery lane.

## Goals / Non-Goals

**One intent:** make a receiver-selected public behavioral component usable at
the canonical foreground turn boundary without transferring private state or
authority. A public composition may include both this behavior and the already
supported layout; installation explicitly selects each consumed component.

**Non-goals:** new public catalog/storage; a second actor/writer; imported
same-origin HTML/JS; arbitrary executable UI, 3D/device/push adapters; full
foreign-project importer; general setup migration; automatic activation of
schedules; user design implementation; background-self policy; retired runtime
activation/worker infrastructure. This first adapter does not complete every
possible UI/harness/setup. Unsupported capabilities stay visible and inactive.

## Decisions

### 1. Reuse private installation; public content cannot select authority

The existing receiving owner's dedicated non-serving `app_experience` binding
can point to a public composition that includes layout and a turn component.
Its ordinary private configuration gains an explicitly versioned consumer
selection, not a new table. Provisional semantic fields are: selected component
key, supported adapter identity/version, exact public definition fingerprint,
and explicit active/disabled state. Do not freeze names until review.

The default is no selected custom turn handler. Merely discovering, importing,
previewing, publishing, applying a layout or changing a public definition ID
does not activate behavior. An explicit receiver installation operation selects
the exact compatible handler and shows the declared executable version, input
exposure and effects. Reuse `write_graph` binding update/CAS through trusted UI
or a user-directed authenticated agent operation. This is not a new grant:
resource/provider/effect authority remains in its current stores.

The runtime requires current receiver/home identity, current owner authority,
creator AND latest updater matching that receiver, configured non-serving role,
no provider_ref, and one unambiguous eligible binding. A collaborator's write
cannot make public content execute under the owner's provider. A selection
fingerprint that no longer matches its definition is held, not silently repaired.
The server, not renderer arguments, derives the principal and universe.

Alternative rejected: repoint the serving binding to an arbitrary rediscovered
definition. `onboarding/serving.py:107` documents why this is a confused-deputy
risk; selection is independent from credentials and serving connectivity.

### 2. One functional native adapter, not an arbitrary-code dispatcher

Candidate first adapter: a public component names an immutable published Branch
version and a versioned **turn input/output contract**. It is descriptive
configuration for ordinary graph execution, not executable Python/JS loaded in
the daemon. Public graph access/ownership checks precede loading the snapshot.
The adapter cannot execute a mutable latest branch or select an arbitrary module,
URL, executable path, resource grant or remote creator identity.

Proposed v1 semantics for review: input is the current founder message plus
the same receiver-scoped conversation context/reference currently permitted for
that founder turn; a declared input mapping adapts those named fields to the
Branch's typed inputs. Output selects one declared terminal text field as the
canonical reply. Mappings are field names only, no evaluation language. Reject
missing inputs, wrong output type and unknown contract version visibly.

The user's graph owns its prompt, memory/context strategy, multi-step control
and learning policy using ordinary tools. The platform does not add a default
private graph or hidden extra writer to make it succeed. After selecting this
adapter, do not also execute the default persona/writer/learning pipeline. The
default path remains unchanged when no custom handler is selected.

Alternative rejected: a framework-specific source-project loader. The first
consumer should prove receiver-owned execution over the existing graph substrate;
foreign harness/renderer adapters can later target the same boundary, but their
unreviewed formats do not become a new mandatory product standard.

### 3. Canonical turn remains the trusted shell

The exact proposed request/status schema, private tables, two-database projection,
source checks, migration and legacy behavior are in [turn-contract.md](turn-contract.md).
It incorporates Fable's ADAPT and the lead's accepted narrow choices; runtime
remains gated on the exact API/storage contract. In particular, canonical
correlation is not a second execution-start claim or authoritative run lifecycle.

Resolve selection after the existing authentication/home/interlocutor gates and
before selecting the writer. Capture one binding revision and immutable source
identity for that turn. Resolve current serving/model policy in the same trusted
path; an explicit current-turn model choice and saved fallback policy apply to
writer calls in the selected adapter as they do to the default writer.

Use current foreground graph/provider admission, confinement, model access,
effect grant and spend boundaries. Do not relabel a converse carrier as run
authority or reuse a single-use provider carrier for multiple graph nodes.
Every child invocation receives the ordinary current run-derived authority.
Source model suggestions cannot override receiver exclusions or paid consent.
The selection itself cannot mint provider authority or start a graph at install.

The graph executor owns run state/checkpoints/effect receipts; the existing
conversation path owns one canonical reply and execution attribution. Link that
turn to its run, source version and selection revision. The bounded
[seam check](turn-seam-evidence.md) found no canonical durable admission link:
conversation persistence is after execution, provider turn IDs are separate,
and existing run comparison lineage is not causal ancestry. Shape review must
choose the minimal reservation/terminal commit extension before implementation.

No automatic default-writer retry on custom failure or uncertainty. There may
already have been effects. Report the run's actual outcome and retain the user's
selection until explicit disable/rollback. Changing selection affects subsequent
turn admission, not replay of an admitted turn. Prevent re-entry into the same
canonical conversation handler from its descendant execution using existing
causal run/turn ancestry, not `run_lineage.parent_run_id` comparison history;
do not grant another autonomous writer under another identity. The seam check
proposes self-contained graphs first (no nested/unresolved executable references)
and a trusted model preference-data bridge, never reuse of converse authority.
These explicit choices remain review-gated, not implemented primitives.

The review's broad in-process code premise was contradicted by the actual compiler;
preserve current OS sandbox and foreign-code provenance rules instead. Public
content remains reusable through ordinary receiver-authorized remix/install with
lineage, without a new blanket author restriction. Preserve the existing engine
agent-binding write refusal; the review did not establish a current consent hole.
Engine-tool graphs currently require one prompt node; ordinary self-contained
graphs may have multiple prompt nodes. This is a v1 limit, not full harness proof.

### 4. Keep private state in place; setup selection is not setup migration

Reuse the receiver's chosen private-universe custody mode. Updating the
installation preserves its unrelated private configuration, conversations,
memory, files, connection ledgers, model preferences, pending approvals and run
state. No destructive migration or source-owner data copy occurs.

The public definition carries requirements and reusable configuration, not
private resource IDs, channel addresses, keys, conversations or granted consent.
Private references are resolved under the receiver's current authority when
used. A missing dependency reports its exact prerequisite and uses the ordinary
connection/request surface only when requested; install does not grant it.
Mixing components changes lineage/composition, not actor identity.

### 5. Explicit compatibility and recovery outside custom content

The trusted picker shows the selected definition/component, adapter, effective
model/provider separately, requirements and supported/unsupported consumers.
Support is checked at installation and use. Unknown components remain portable;
they do not become executed just because another component is supported.

Keep select/disable/restore-default controls outside the custom layout. Receiver
disable is an exact revision update that removes the custom turn selection and
restores the existing default path for the next turn. Rollback selects an explicit
previous immutable definition/component via the same current checks; it cannot
restore revoked credentials, obsolete grants or undo effects. No automatic
dependency update or unsafe "closest" adapter. Uncertain save means read current
state before another explicit change, not replay.

## Risks / Trade-offs

- The snapshot runner and live-turn model-choice path are separate today ->
  prove their combination with the real receiver authority helpers before any
  release; do not assume a provider callback parameter proves policy parity.
- Immutable snapshot alone may name mutable descendants -> installation must
  report/reject unresolved executable closure for a pinned consumer; inspect
  existing dependency/snapshot helpers before proposing a new manifest store.
- A slow graph exceeds a chat transport lifetime -> use the existing durable
  run and current turn progress contract; pending is not completed. Determine
  reply correlation/recovery before implementation, with no effect replay.
- Selection races/revocation during a turn -> recheck current authority at each
  existing admission/effect boundary; do not reinterpret an in-flight operation
  as permission for a new one. Default restoration is not cancellation.
- Public component tells a model to exfiltrate -> publication grants no new
  access; show the selected behavior/input exposure and use existing governed
  outbound effects. Creator-owned endpoint/grant references never auto-bind.
- Existing relay spec contains obsolete Codex/WebFetch-only statements -> do
  not use those as design authority to remove current uniform engine tools.
  The targeted delta below preserves current verified policy and identifies
  this source/spec mismatch for lead sync, without claiming a broad cleanup.

## Migration Plan

No migration, new secret store or runtime implementation in this proposal.
After shape acceptance, build a scoped feature with absent-selection default
unchanged; existing app_experience installations cannot implicitly opt in.
Run real-store and actual-consumer negative tests, cross-family exact-head review,
Linux confinement gates, hosted CI, protected deployment/handles and ordinary
two-owner acceptance. Rollback disables this consumer path while retaining
definitions and private data. The lead controls rollout; never install a user's
design as an operator workaround. Sync only demonstrated behavior on land.

## Open Questions — gate implementation, not settled by this proposal

1. Is Branch-backed canonical turn dispatch the smallest functional generic
   adapter, or can an existing governed consumer already supply it? Name the
   caller and evidence if it exists; do not create a second runtime.
2. Can snapshot closure, current-turn model preference, run admission, cancellation
   and terminal reply correlation be reused with no new durable shape? Identify
   exact missing boundary before code, rather than calling the old helper with
   ambient authority and hoping it matches.
3. Are a receiver-owner/latest-updater check plus exact private component pin
   sufficient for explicit installation, or must the existing pending-request
   approval path bind that selection? Review one-user confused-deputy safety.
4. Does the proposed input/output contract support a real user-authored harness
   without dictating its cognitive steps? The user's agent should select/build
   the fixture, not this platform worker.
5. Arbitrary executable UI remains unserved: a later adapter must define genuine
   browser isolation and a receiver-scoped state/action interface. This first
   slice must not be advertised as that renderer or full setup portability.
