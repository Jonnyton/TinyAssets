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
- `identity-auth-and-access-control`: authenticated request capability minting;
- `universe-lifecycle-and-soul`: independent newborn deny-all invariant;
- `universe-creation`: first-contact and held/setup semantics;
- `credential-vault` plus #1746: credential isolation, custody, and retirement;
- `provider-attempt-receipts`: result-local receipt aggregation;
- `daemon-identity-and-host-pool` plus `desktop-host-runtime`: requester-host
  activation through the named successor; and
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

Every newborn begins with `engine_assignment_state="unassigned"`,
`engine_assignment_generation=0`, and `allowed_providers=[]`. `ready` requires
a non-empty ceiling; all other states require `[]`.

### 2. Source resolution is strict and held sources stay deny-all

| `engine_source` | Service | Ceiling | Preferred writer |
|---|---|---|---|
| `requester_local` | `anthropic` | `["claude-code"]` | `claude-code` |
| `requester_local` | `openai` | `["codex"]` | `codex` |

An omitted writer is derived; a supplied writer must match exactly. Aliases,
unknown values, mismatches, missing opaque binding references, and unsupported
assignment fields fail before mutation. Ready requester-local assignment
stores only an opaque credential binding reference plus non-secret
provenance. #1746 alone owns raw/recoverable `llm_api_key` ingress refusal,
binding custody, and legacy retirement.

`self_hosted_endpoint` and `host_daemon` are non-authorizing intent and remain
held until `activate-requester-host-engines` validates endpoint/daemon,
requester authorization, and a stable authenticated account-to-host
principal. That successor modifies `daemon-identity-and-host-pool`,
`desktop-host-runtime`, and the source activation seam in `provider-routing`;
it may consume `daemon_summon` but not treat pool rows or unattested client IDs
as authority. `market_rented` remains held permanently in the ordinary router.

### 3. Assignment and custody share one exported admission primitive

A per-universe exclusive writer performs:

1. mutation-free validation;
2. secret-free journal plus `pending`/deny-all quarantine;
3. source/reference update preserving unrelated credential bytes;
4. durable `commit_ready` identity and non-secret digests;
5. atomic final publication of state, generation, preference, reference,
   provenance, and ceiling; and
6. durable matching journal cleanup.

Post-quarantine failure publishes `failed + []`; it never restores prior wider
state. Startup accepts a leftover `commit_ready` only when transaction identity
and digests match final config. Every other partial state remains held.

The module exports `ProviderAssignmentAdmission`, keyed by canonical universe
identity:

- exclusive writer for assignment, custody replacement/retirement, and
  compare-delete;
- shared reader held through provider `start()`.

Callers cannot choose its lock path. Global order is assignment admission
before credential-custody index/keyring locks; reverse acquisition and
untracked reentrancy fail loud. A custody writer validates expected assignment
generation and credential-record digest before its narrower locks. A launch
reader validates the same generation/digest before dereference. #1746 consumes
this published interface without reciprocal acceptance or a second lock.

### 4. Live requester authority is transport-minted and request-scoped

`identity-auth-and-access-control` owns `ProviderRequestCapability` in
`tinyassets/auth/middleware.py`. Middleware mints it only after validating a
bearer and resolving a non-anonymous `Identity`. It contains:

- opaque request nonce;
- authenticated principal ID;
- mechanism `tinyassets.authenticated-request.v1`;
- issuer `tinyassets.auth.middleware`; and
- unexported identity token.

It is non-serializable, non-copyable, non-pickleable, unconstructible from
tool/API data or other modules, stored beside request identity in a
`ContextVar`, and reset at request end.

The provider sink requires the exact current capability and validates:

- exact mechanism/issuer and identity token;
- capability principal equals current authenticated identity;
- target universe equals routed universe and permits the invoking operation;
- binding owner equals the capability principal;
- binding universe/provider/host/generation/digest equal fresh server state;
- binding is non-empty, unexpired, non-tombstoned, and non-revoked.

The authority-derived destination set is the fresh assignment ceiling after
those checks. There is no caller-supplied eligible set and no parallel
universe bundle. Authentic A-on-A authority replayed against B fails even when
both assignments select the same provider.

Background/resumed/scheduled work cannot reuse this capability. It needs its
own server-owned background/run authority receipt. Accepted-market and
volunteered-capacity work use distributed execution. Missing capability or
receipt, anonymous identity, wrong current capability, stale generation, wrong
principal/universe/provider/host, or invalid binding state fails held before
provider, credential, auth-health, or quota access.

The interface is one-way. This change does not block on #1660,
universe-creation, #1746, or receipts accepting it. Those lanes consume the
published request capability, assignment admission, held outcome, and
reference-only launch contracts before their own dependent runtime advances.

### 5. Propagation has one owner; host-local cannot rescue request work

This change owns exhaustive provider-layer propagation. Every live-request
graph/run/resume/version/policy/judge, RAPTOR, reflexion, agentic-retrieval,
and other `call_provider` path retains the request capability. Background
paths supply their owner-defined receipt. Remaining callers are explicitly
classified host-local or local-only.

Only enumerated non-request maintenance may receive
`HostLocalProviderCapability`, bootstrap-minted after local operator
configuration. It is identity-validated, non-serializable, mutually exclusive
with request authority, and absent from API/MCP/config/state/environment
inputs. `None`, strings, enums, lookalikes, ambient process identity, or a
genuine host token substituted on request lineage authorize nothing.

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
- credential kind and credential-authority class;
- immutable prompt/system/model/endpoint inputs; and
- router-only launch token.

Immutable `ProviderInvocation` contains those values and no native API key,
OAuth token, decrypted/base64 secret, subscription-file bytes, or other
recoverable material.

The provider interface is:

1. `await BaseProvider.start(invocation) -> ProviderLaunchHandle`;
2. `await ProviderLaunchHandle.result() -> ProviderResponse`.

Only executor-local `start()` may validate the full non-empty, unexpired,
non-tombstoned, non-revoked principal/universe/provider/host/generation/digest
tuple and dereference the binding. Native material exists only in provider
child/request memory, never argv, journal, log, config, receipt, or server
state. `start()` returns after transport owns an irreversible registered copy
of inputs. Provider/handle code then cannot reread universe config, vault,
ambient environment, or auth homes.

Launch timeout is bounded separately from model completion. Cancellation,
partial creation, result/close races, and crash recovery have one terminal
owner and secret-free launch identity. Unprovable cleanup installs a durable
universe fence. Shared admission remains held through `start()`, then releases
while result completion continues.

### 8. Call-local evidence has two non-competing vocabularies

The provider boundary emits credential execution evidence:

- `credential_kind`: `llm_subscription`, `llm_api_key`, `local`, `none`,
  `unknown`;
- `credential_authority_class` (the receipt field currently named
  `authority_class`): `universe`, `host`, `local`, `none`, `unknown`.

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

### 10. Cutover preserves at least one live-ready path

No runtime enforcement or legacy conversion may begin until at least one
end-to-end ready source is deployed and rendered:

1. requester-local opaque OS custody through #1746 and the request capability;
   or
2. `activate-requester-host-engines` with stable account-to-host binding.

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
- **Request ContextVar propagation can be lost across custom executors.**
  Exhaustively test every thread/task bridge; missing capability holds.
- **Cross-capability locking can deadlock.** One exported primitive and fixed
  assignment-before-custody order; reverse/reentrant acquisition fails.
- **Fresh admission adds latency.** Keep reads secret-free/small and prove real
  connector load.
- **Two-phase launch increases lifecycle complexity.** Require crash,
  cancellation, and double-terminal tests before cutover.

## Migration Plan

1. Land target specs and one-way sibling handoffs; keep runtime dark.
2. Add request capability and newborn deny-all state.
3. Add assignment generation, exported admission, transaction, and held
   source behavior.
4. Add sole propagation plus reference-only invocation/launch.
5. Make at least one requester-local or requester-host source live-ready.
6. Inventory legacy universes; treat raw-key-only assignments as non-ready.
7. Run race/crash/security suites and real connector load proof.
8. Quiesce legacy writers only after the ready-path gate; convert, canary,
   render chatbot acceptance, and inspect post-fix clean use.

Rollback before cutover restores code/config artifacts while deny-all state
remains safe. After cutover, forward-fix authority state; never reinterpret
failed, held, `[]`, or an opaque reference as unrestricted legacy authority.

## Open Questions

None for the target contract. Runtime file partitions remain a coordination
gate while adjacent universe, receipt, custody, daemon, and broad test lanes
are active.
