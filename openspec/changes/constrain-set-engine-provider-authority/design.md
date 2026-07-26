## Context

The router implements `allowed_providers`, but `set_engine` writes preference
without setting that ceiling. Preference intentionally preserves fallback, so
it cannot serve as authority. PR #1592 now gives universe provider processes a
fail-closed environment; the remaining defect is which provider destination
may receive a call and which call-local authority authorized it.

Draft PR #1691 planned that boundary on obsolete, parentless history. Merged
Opus review #1727 returned `ADAPT` for circular review gates, duplicate
authority/propagation ownership, and unnamed activation owners. A first
current-main reconstruction also returned `ADAPT`: dark D0 `Verified[T]` has
no requester-provider mint domain or production composition root, sibling
gates remained circular, binding checks were incomplete, canonical behaviors
were dropped, and no engine could be ready at cutover.

This revision uses an exact live-request capability minted by authenticated
transport middleware. It keeps dark D0 fake/test-only; accepted-market work
uses the separately reviewed distributed-execution production path.

Capability ownership is explicit:

- `provider-routing`: assignment ceilings/admission, provider-layer
  propagation, frozen invocation/launch, and call-local execution evidence;
- `identity-auth-and-access-control`: HTTP and attested-local request
  capability minting plus the canonical setup-required authority envelope;
- `universe-lifecycle-and-soul`: independent newborn deny-all invariant;
- `universe-creation`: birth/home transaction and action-layer rendering of
  the canonical setup envelope;
- `credential-vault` plus #1746: credential isolation, custody, and retirement;
- `provider-attempt-receipts`: result-local receipt aggregation;
- `daemon-identity-and-host-pool`, `desktop-host-runtime`,
  `identity-auth-and-access-control`, and `provider-routing`: requester-host,
  local-model, stdio, and local-SSE activation through the named successor;
- `identity-auth-and-access-control`, `paid-market-economy`,
  `distributed-execution`, and `live-mcp-connector-surface`: Tier-1 accepted
  market activation through `activate-connector-requester-authority`; and
- `paid-market-economy` plus `distributed-execution`: accepted remote work.

## Goals / Non-Goals

**Goals**

- Make assignment and every provider attempt fail closed at the
  provider-destination boundary.
- Publish one coherent source, preference, opaque credential reference,
  assignment generation, and ceiling under concurrent assignment/routing.
- Bind live requests to the current authenticated principal, target universe,
  provider, host, and assignment generation without a caller-minted bundle.
- Freeze reference/provenance before launch while keeping native secret
  material executor-local.
- Publish one cross-capability assignment lock and one provider-layer
  propagation path.
- Supply exact call-local credential-kind and credential-authority evidence
  to the separately owned receipt seam.

**Non-goals**

- Extending or treating fake-only D0 `Verified[T]` as ordinary requester
  authority.
- Reopening ambient credential isolation settled by PR #1592.
- Owning raw API-key ingress, OS custody, or legacy secret retirement.
- Activating requester-host or accepted-market work through the ordinary
  router.
- Defining market agreement, price, settlement, B2 composition, or receipt
  persistence.
- Merging drafts #1606 or #1691 as-is.

## Decisions

### 1. `allowed_providers` is replacement-only authority

| Value | Meaning |
|---|---|
| `None` | legacy pre-cutover encoding; invalid in post-cutover runtime |
| `[]` | deny-all for unassigned, pending, held, or failed |
| non-empty canonical list | only destinations eligible for the assignment |

Assignment replaces rather than unions the ceiling and increments an immutable
generation. Preference, policy, pin, registration, auth health, quota,
fallback, and retry may never add a provider.

After gated migration, every newborn begins with
`engine_source="unassigned"`,
`engine_assignment_state="unassigned"`, `engine_assignment_generation=0`, and
`allowed_providers=[]`. `ready` requires a non-empty ceiling; all other states
require `[]`. Non-empty is necessary but not sufficient: a ready ceiling must
intersect every canonical `writer`, `judge`, `extract`, and `embed` chain and
carry one current provider-specific binding entry for every destination.

Before migration, optional assignment fields remain absent and
`TINYASSETS_PROVIDER_AUTHORITY_V2` defaults false. `_DEFAULT_ENGINE_SOURCE`
stays `byo_api_key`; `universe_has_assigned_engine` retains its shipped vault
credential, explicit non-default source, and unreadable-state fail-safes.
There is no flag-independent exception: every legacy `set_engine` source,
service, config write, readiness result, and `allowed_providers=None` no-op
retains shipped behavior while dark. PR #1592 already fail-closes credential
recovery for universe-scoped calls, but unchosen destination choice remains
and the process-global/no-universe provider path can still inherit maintainer
authentication. The effective V2 gate closes both; R2-1a owns that gated
runtime after the three ready-path successors, and task 8.1 migrates every
legacy `None` record.

“Retains shipped behavior” includes the configured dispatch mode: production
callers still pass the shipped `universe:admin` scope plus universe write ACL,
while development-mode stdio/SSE keeps its shipped no-auth short circuit and
write ACL behavior. This change adds no independent authenticated-founder
precondition and performs no pre-cutover destination narrowing. After the
effective gate applies, requester-local cloud assignment arrives through the
custody-owned authenticated writer; local stdio/plugin execution uses the
separate attested-host successor rather than a legacy raw-secret action.

Because `universe` is hidden from the seven canonical live handles, Tier-1
chatbots cannot reach the deprecated action. `retire-legacy-live-mcp-tools`
may remove it because removal strictly reduces new exposure. Local surfaces
then depend on `activate-requester-host-engines`; Tier-1 setup remains owned by
`activate-connector-requester-authority`.
Only after every universe has a manifest classification and all surface gates
pass does cutover flip the flag/default for new births. Post-migration,
`unassigned + []` alone is engine-less; ready/nonempty or a proven remote
grant is ready; unreadable, pending, held, failed, and inconsistent state stay
fail-safe true for the legacy exhaustion classifier. Typed authority holds
map directly to precise setup. Bare policy/pin/no-router exhaustion preserves
its current no-envelope carve-out.

### 2. Source resolution is strict and held sources stay deny-all

The resolver is total over both the shipped source domain and target values:

| `engine_source` | Target treatment | Ready ceiling / owner |
|---|---|---|
| `unassigned` | target newborn/setup state | always `unassigned + []`; no provider or credential access |
| `byo_api_key` | legacy read/migration only; new writes refused | convert to `requester_local` only after #1746 creates an opaque binding; otherwise `failed + []` |
| `self_hosted_endpoint` | held intent | `activate-requester-host-engines`; never ready before endpoint and account-to-host proof |
| `market_rented` | remote-only intent | always `[]` in ordinary routing; B2+B13 own execution |
| `host_daemon` | legacy read/migration name | rename to `founder_hosted_daemon` only through the host successor; otherwise held |
| `requester_local` + `anthropic` | target custody source | cloud binding + writer preference only; remains `held + []` until a separately authorized role supplement makes the ceiling role-complete |
| `requester_local` + `openai` | target custody source | cloud binding + writer preference only; remains `held + []` until a separately authorized role supplement makes the ceiling role-complete |
| `local_model` + `ollama` | target zero-cloud source | `["ollama-local"]`; `activate-requester-host-engines` emits source + attested host binding |
| `founder_hosted_daemon` | target hosted source | successor-selected ceiling after stable authenticated account-to-host binding |

An omitted writer is derived; a supplied writer must match exactly. Aliases,
unknown values, mismatches, missing opaque binding references, and unsupported
assignment fields fail before mutation. Requester-local assignment stores a
non-secret `provider_authority_bindings` map from canonical provider to its own
opaque binding reference/digest and provenance. #1746 alone owns
raw/recoverable `llm_api_key` ingress refusal, cloud binding custody, legacy
retirement, and the atomic post-custody writer that emits
`engine_source=requester_local`, service, the cloud binding entry, and writer
preference. Cloud custody alone remains held.

`self_hosted_endpoint`, `host_daemon`, `local_model`, and
`founder_hosted_daemon` remain held until
`activate-requester-host-engines` validates endpoint/daemon/local model,
requester authorization, and a stable authenticated account-to-host
principal or an attested same-OS-user local-installation principal. That
successor modifies `daemon-identity-and-host-pool`, `desktop-host-runtime`,
`identity-auth-and-access-control`, and the source activation seam in
`provider-routing`; it mints a separate session-scoped
`ProviderHostRequestCapability` for attested interactive local stdio/SSE and
it may consume `daemon_summon` but not treat pool rows or unattested client IDs
as authority. It is the sole writer of ready `local_model` and
`founder_hosted_daemon` assignments. It may also add an attested
requester-owned `ollama-local` binding to a requester-local cloud assignment
through the same admission transaction; only the atomic compositor may then
publish the role-complete cloud-plus-local ceiling. Maintainer compute never
supplies this supplement. `market_rented` remains held permanently in the
ordinary router.

### 3. Assignment and custody share one exported admission primitive

A per-universe exclusive writer performs:

1. mutation-free validation;
2. secret-free journal plus `pending`/deny-all quarantine;
3. source/per-provider-binding-map update preserving unrelated credential
   bytes;
4. durable `commit_ready` identity and non-secret digests;
5. atomic final publication of state, generation, preference, binding map,
   provenance, and role-complete ceiling; and
6. durable matching journal cleanup.

Post-quarantine failure publishes `failed + []`; it never restores prior wider
state. Startup accepts a leftover `commit_ready` only when transaction identity
and digests match final config. Every other partial state remains held.

The module exports `ProviderAssignmentAdmission`, keyed by canonical universe
identity:

- exclusive writer for assignment, custody replacement/retirement, and
  compare-delete;
- shared reader held through `ProviderExecutor.start()`.

Callers cannot choose its lock path. Global order is assignment admission
before credential-custody index/keyring locks; reverse acquisition and
untracked reentrancy fail loud. A custody writer validates expected assignment
generation and affected provider-binding digest before its narrower locks. A
launch reader validates the selected provider's same generation/digest before
dereference. #1746 consumes
this published interface without a second lock; its exact-SHA provider-owner
acceptance is an output gate from this owner, not a dependency back onto this
target spec.

### 4. Live requester authority is transport-minted and request-scoped

`identity-auth-and-access-control` owns `ProviderRequestCapability` plus the
TinyAssets FastMCP message middleware and registered-tool wrapper seams.
The outer ASGI `AuthContextMiddleware` continues OAuth challenge,
invalid-token, and anonymous-write pre-dispatch, but its task-local
`ContextVar` lifetime is not provider authority. In stateful streamable HTTP,
the ASGI request task does not parent the synchronous tool worker: FastMCP's
long-lived session task creates a per-message task, and FastMCP 3.2 dispatches
the registered synchronous wrapper through `anyio.to_thread.run_sync`.

For each `tools/call`, TinyAssets FastMCP `Middleware.on_call_tool` uses
`fastmcp.server.dependencies.get_http_request()` to inspect the current
message's HTTP request, resolves its bearer through the configured TinyAssets
auth provider, and refuses anonymous/invalid identity. This deliberately
avoids the copied initialize-request Context that stateful sessions otherwise
retain. Before `call_next`, it registers one opaque dispatch reserve
containing:

- opaque request nonce;
- authenticated principal ID;
- current MCP session ID, request ID, and exact tool name;
- mechanism `tinyassets.authenticated-request.v1`;
- issuer `tinyassets.auth.middleware`; and
- unexported identity token; and
- owning per-message task identity.

The reserve is non-authorizing, non-serializable, one-shot, and unavailable
through tool/API data. The TinyAssets wrapper installed by
`_register_structured_tool` receives its private copied reserve, then
atomically claims it at synchronous worker entry after AnyIO has chosen the
actual thread. The server registry binds the resulting
`ProviderRequestCapability` and lease to that worker, message, tool, and
principal. An async registered handler claims in the per-message task before
entry. Wrapper and message-middleware `finally` paths revoke before returning
the result. A copied reserve, initialize/prior-message Context, detached task
or thread, nested worker, second claimant, stale invocation, or
caller-controlled identifier cannot claim or reuse it.

`call_provider` retrieves the exact current capability, proves the server
registry still marks its message lease plus actual execution claim active, and
mints an internal-only sealed `ProviderAuthorityCarrier` argument for `call_sync`,
`call_with_policy_sync`, every retry/judge branch, the router pool closure,
and `ProviderInvocation`. This explicit carrier is required because
`ProviderRouter.call_sync` deliberately does not propagate `ContextVar` state
into its class-level `ThreadPoolExecutor` (`router.py:816-819`). Public
API/MCP schemas, universe/request payloads, caller kwargs, serialized state,
and ambient worker context cannot populate the carrier.

The provider sink requires the exact capability carried from the current
transport edge and validates:

- exact mechanism/issuer and identity token;
- capability principal equals the current-message identity captured in the
  server-owned lease;
- current session/request/tool, lease, and registered execution claim remain
  active;
- target universe equals routed universe and permits the invoking operation;
- binding owner equals the capability principal;
- binding universe/provider/host/generation/digest equal fresh server state;
- binding is non-empty, unexpired, non-tombstoned, and non-revoked.

The authority-derived destination set is the fresh assignment ceiling after
those checks. There is no caller-supplied eligible set and no parallel
universe bundle. Authentic A-on-A authority replayed against B fails even when
both assignments select the same provider.

An asyncio child or nested thread may inherit copied Context but cannot claim
the already-consumed reserve or match the registered execution identity.
After wrapper/message middleware returns, the synchronously revoked lease
fails again. ContextVar reset is cleanup, not the authority invalidation
mechanism.

Background/resumed/scheduled work cannot reuse this capability.
`harden-background-provider-execution-authority` owns the durable
`ProviderWorkAuthorityReceipt` for graph pools, resumed/versioned runs,
schedules, daemon loops, and every provider call whose request middleware has
already returned. The receipt is server-issued, names exact
principal/actor/run/branch/universe/operation, carries assignment
generation/digest and a bounded lifetime, and is reloaded plus revalidated
from server state rather than accepted from caller payload. Before that
successor lands, every such path holds. Accepted-market and
volunteered-capacity work use distributed execution. Missing capability or
receipt, anonymous identity, wrong current capability, stale generation, wrong
principal/universe/provider/host, or invalid binding state fails held before
provider, credential, auth-health, or quota access.

The dependency direction is one-way: provider routing publishes this contract
and does not require sibling acceptance before the target spec lands. Custody
does require exact-SHA provider-owner acceptance before its dependent runtime
advances; that acceptance is an output of this owner, not a reciprocal gate
back onto this spec. The merged active `universe-creation` and
`provider-attempt-receipts` changes currently conflict with this replacement
and MUST adapt before archive/sync into canonical specs: the former removes
its caller-built eligible provider set and keeps only target lineage plus
`fulfillment_class`; the latter extends its closed enums with
`authority_held` and carves this typed hold out of its otherwise-unrelated
exception `error/provider_error` rule.

### 5. Propagation has one owner; host-local cannot rescue request work

This change owns exhaustive provider-layer propagation. Every live request
uses the explicit internal carrier through `call_provider`, synchronous
router helpers, their thread-pool closures, retry/policy/judge branches, and
launch. `harden-background-provider-execution-authority` owns receipt minting
and transport across task/thread/process boundaries after the request ends,
including graph/run/resume/version, RAPTOR, reflexion, agentic retrieval,
scheduler, cloud worker, and daemon paths. No caller is presumed classified
ahead of the task-3.2 inventory: current editorial, ingestion extractor, and
selector-dispatch provider spends are background-owner candidates and hold
until assigned to request or work authority. Every remaining caller MUST be
proven request-carried, work-receipted, one of the closed zero-output probes,
or non-provider local-only before runtime advances.

`HostLocalProviderCapability` has a closed, spec-listed operation set:
`subscription_auth_probe`, `local_model_readiness_probe`, and
`sandbox_readiness_probe`. Each operation is zero-output, accepts no user
prompt, mutates no universe/branch, and cannot produce a
`ProviderInvocation`; the subscription operation is non-completion credential
inspection only. The shipped `_AUTH_PROBE_PROMPT` refresh-viability completion
is a background maintenance provider call, not a host-local probe. It holds
until `harden-background-provider-execution-authority` issues its exact
bounded maintenance receipt or a proven zero-output replacement lands; ambient
maintainer authentication is never enough. The capability is
bootstrap-minted after local operator configuration, identity-validated,
non-serializable, mutually exclusive with request/work authority, and absent
from API/MCP/config/state/environment inputs. A closure test fails when any
host-local operation exists outside the three-name set. `None`, strings,
enums, lookalikes, ambient process identity, or a genuine host token
substituted on request lineage authorize nothing.

### 6. Authority emptiness is distinct from runtime exhaustion

`effective_provider_authority` means only:

`fresh assignment ceiling` after request-capability/receipt and binding checks.

An empty authority set raises `ProviderAuthorityHeldError` before dynamic
routing. Subscription-only policy, role-chain membership, `llm_policy`,
registration, auth health, cooldown, and quota are applied afterward and may
only narrow the authorized set. Emptiness caused by those runtime filters
retains canonical `AllProvidersExhaustedError`, chain-drain, policy-fallback,
retry, explicit fallback, and judge degradation behavior. A pin outside
authority is held; an authorized pin that is unavailable is exhaustion.

### 7. Invocation is reference-only and launch freezes authority

Under shared admission, the router resolves:

- request capability or owner-defined background receipt;
- target universe and authenticated principal;
- canonical provider and assignment generation;
- opaque credential binding reference and digest when required;
- credential/auth provenance;
- exact `credential_kind` and `authority_class` fields;
- immutable prompt/system/model/endpoint inputs; and
- router-only launch token.

Immutable `ProviderInvocation` contains those values and no native API key,
OAuth token, decrypted/base64 secret, subscription-file bytes, or other
recoverable material.

The launch interface layered above the canonical provider interface is:

1. `await ProviderExecutor.start(invocation) -> ProviderLaunchHandle`;
2. `await ProviderLaunchHandle.result() -> ProviderResponse`.

Every `BaseProvider` retains canonical
`complete(prompt, system, config, *, universe_dir=None)`. Only
executor-local `ProviderExecutor.start()` may validate the full non-empty, unexpired,
non-tombstoned, non-revoked principal/universe/provider/host/generation/digest
tuple, dereference the binding, and call the selected provider's
`complete(...)`. Native material exists only in provider child/request memory,
never argv, journal, log, config, receipt, or server state. `start()` returns
after transport owns an irreversible registered copy of inputs.
Provider/handle code then cannot reread universe config, vault, ambient
environment, or auth homes.

Launch timeout is bounded separately from model completion. Cancellation,
partial creation, result/close races, and crash recovery have one terminal
owner and secret-free launch identity. Unprovable cleanup installs a durable
universe fence. Shared admission remains held through `start()`, then releases
while result completion continues.

### 8. Call-local evidence has two non-competing vocabularies

The provider boundary emits credential execution evidence:

- `credential_kind`: `llm_subscription`, `llm_api_key`, `local`, `none`,
  `unknown`;
- `authority_class`: `universe`, `host`, `local`, `none`, `unknown`.

This answers how/whose credential permitted the provider call. `unknown`
grants nothing; universe remote success cannot report host. The receipt lane
owns immutable aggregation/sinks and must add:

- `outcome=authority_held`;
- `route_condition=authority_held`.

`ProviderAuthorityHeldError` may never be recorded as provider
`error`/`provider_error`.

Universe-creation's `requester_owned|accepted_market` vocabulary answers a
different question and is renamed `fulfillment_class`. It must not populate
credential authority. This one-way terminology handoff removes the collision.

### 9. Remote activation ownership is exact

`paid-market-economy` owns accepted semantic/economic agreement. The
distributed-execution B2 signed-remote protocol plus anti-loss B13 task 5.13
owns the sole complete production authority composition root. V6 owns
deterministic market selection, escrow, verification, settlement, and
reputation; it does not mint the execution authority. Dark D0 record/seal
types remain fake/test-only and are not production authority.

Volunteered public capacity similarly uses the executing operator's recorded
consent and the reviewed distributed-execution production route. It is not
host fallback, maintainer capacity, requester-local assignment, or market
acceptance.

### 10. Cutover preserves a completable path on every first-class surface

The global gate cannot be validated by observing shipped behavior while it is
dark. A server-owned, default-empty canary set may enable the complete target
contract for named isolated acceptance-test universes whose manifests and
ready paths are already complete. A separate default-empty principal set
solves generated-ID public/first-contact birth: only a preflight-clean
isolated test principal with no existing home/universe may bootstrap a birth,
and the server registers the generated ID before visibility. Later
enforcement keys only on the registered ID. Caller data cannot populate either
set. Unlisted universes retain shipped behavior; existing user universes are
never migrated just to obtain proof. Global flip requires the same
Tier-1/Tier-2/Tier-3/plugin acceptance under this bounded
post-flip-equivalent mode, followed by canary cleanup.

No runtime enforcement or legacy conversion may begin until each affected
surface has an end-to-end ready and advertised path:

1. a newborn Tier-1 streamable-HTTP chatbot user can accept market execution
   through `activate-connector-requester-authority` after paid-market
   agreement and distributed-execution B2/B13 are live; that successor's own
   OpenSpec must name an action carried by one of the seven canonical live
   connector handles and must not depend on the deprecated `universe` handle;
2. Tier-2 tray, Tier-3 OSS stdio, and mirrored Claude-plugin local runtime can
   mint `ProviderHostRequestCapability` through
   `activate-requester-host-engines` and complete attested requester-host or
   `local_model` execution; and
3. any retained requester-local opaque OS custody path through #1746 has a
   surface that can actually complete its secure setup.

The canonical `engine_setup_required_payload` must be live and rendered for
the exact pre-provider `ProviderAuthorityHeldError` cause before newborn
deny-all state is enabled. The universe action layer owns the direct mapping;
it MUST NOT require `AllProvidersExhaustedError`, non-null chain state, or a
provider attempt. Its `setup_paths` list contains only routes that pass
end-to-end acceptance on the current request surface; raw `byo_api_key` and
unavailable desktop-only routes are absent. Provider routing supplies only
the typed held cause. Any background/run/scheduled or daemon path that can
reach providers must also carry a valid
`ProviderWorkAuthorityReceipt` from
`harden-background-provider-execution-authority`, or be held and proven not to
break the connector's canonical handles and autonomous loops, before cutover.
A fully held OSS clone, tray, stdio/SSE server, or Claude-plugin runtime is a
failed release, not a safe cutover.

The existing live founder home remains on the pre-cutover artifact until its
credential/source is inventoried. Current raw `byo_api_key` records have no
opaque reference and therefore map to `failed + []`, never ready. A valid
retained `llm_subscription` may map ready only if current principal, universe,
provider, host, generation, and custody evidence all validate. If no ready
replacement exists, deployment stops before quiescing legacy writers.

### 11. Draft histories are source-only

PR #1606 may contribute reviewed assignment-lock, transaction, migration, and
deployment-fence pieces only after current-main comparison. Draft #1691 is
superseded after the replacement lands. Closed #1617 remains a citation.
Every custody-lane citation to “draft PR #1691” must be re-pointed at the
replacement change and exact accepted SHA before #1691 closes.

## Risks / Trade-offs

- **Held sources appear less functional.** Return truthful
  `setup_required` rather than borrow platform resources.
- **Authority can be lost at thread/task/process bridges.** Request calls use
  the explicit internal carrier across the router pool; background work uses
  the separately owned durable receipt. A startup/CI inventory asserts every
  provider bridge carries one exact authority type or is held.
- **Cross-capability locking can deadlock.** One exported primitive and fixed
  assignment-before-custody order; reverse/reentrant acquisition fails.
- **Fresh admission adds latency.** Keep reads secret-free/small and prove real
  connector load.
- **Two-phase launch increases lifecycle complexity.** Require crash,
  cancellation, and double-terminal tests before cutover.

## Migration Plan

1. Land target specs and one-way sibling handoffs; keep runtime dark.
2. Add request capability plus the explicit internal thread-pool carrier,
   assignment generation/admission, reference-only launch, and the rendered
   held/`setup_required` envelope with the global flag false and canary state
   empty; preserve every shipped helper, default, fail-safe, source/service
   write, destination choice, and bare-exhaustion behavior.
3. Land `harden-background-provider-execution-authority`,
   `activate-requester-host-engines`, and
   `activate-connector-requester-authority`; classify every provider bridge
   and make connector/local setup paths live.
4. With the flag still false, inventory every legacy universe; preserve
   credentialed/non-default sources, fail-safe unreadable state, and convert
   verified custody/host/local/remote sources into explicit assignment state.
5. Prove the manifest is complete and all Tier-1/Tier-2/Tier-3/plugin surface
   gates pass under the server-owned isolated-universe canary; prove unlisted
   universes remain on shipped behavior and clean up canary universes,
   principal entries, and registered IDs.
6. Only then flip the flag/default, enable newborn deny-all initialization,
   and prove typed holds render setup while bare infrastructure exhaustion
   remains loud.
7. Run race/crash/security suites and real connector load proof.
8. Quiesce legacy writers only after request and background ready-path gates;
   convert, canary, render chatbot acceptance, and inspect post-fix clean use.

Rollback before cutover restores code/config artifacts while deny-all state
remains safe. After cutover, forward-fix authority state; never reinterpret
failed, held, `[]`, or an opaque reference as unrestricted legacy authority.

## Open Questions

None for the target contract. Runtime file partitions remain a coordination
gate while adjacent universe, receipt, custody, daemon, and broad test lanes
are active.
