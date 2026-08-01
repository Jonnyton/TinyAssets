# Custom-agent runtime-core owner handoff audit

Date: 2026-08-01
Environment: Windows 11, Python 3.14, current main `88a1ac8df6fb0e9b1821b6f68cef665b97e950fe`
Change: `activate-custom-agent-runtime-core` (merged specification PR #2084)

## Outcome

The arbitrary-agent definition, n-parent remix, import/export, and private
binding substrate is present, but no runtime manifest, execution subject,
agent invocation, or invocation-admission implementation exists on current
main. The runtime core is therefore specified but not built.

No runtime file can be claimed safely yet. The active
`codex-gpt5-desktop-cloud` lane owns every canonical activation, provider-work,
and cloud-continuation file that PR #2084 deliberately extends. That lane is
still dark and explicitly lacks provider launch/effect reconciliation and
cutover. Its authority must not be forked or bypassed for agents.

The next implementation claim requires either release of the exact files in
the handoff table below or an agreed split in which the current owner lands the
shared `ExecutionSubject` and aggregate-provider admission seams first.

## Current seam map

| Authority | Current-main owner and invariant | Runtime-core change | Exact collision boundary |
|---|---|---|---|
| Private agent snapshot | `tinyassets/custom_agents.py` stores a private binding revision and arbitrary secret-free configuration against one immutable public definition; bindings stay `configured` | Read one exact binding/definition snapshot; add no runtime state to either public definition or binding row | Read-only dependency on `tinyassets/custom_agents.py`; focused baseline in `tests/test_custom_agents.py` |
| Activation | `tinyassets/storage/automation_activations.py` owns CAS state at primary key `(universe_id, automation_id)` and hard-codes `immutable_branch_version` | Add the shared typed subject and derive one reserved automation ID from `("agent_binding", agent_binding_id)` so aliases race on the same row | Active owner files: canonical store, `tests/test_automation_activations.py`, and packaged activation mirror |
| Provider binding and receipt | `tinyassets/provider_work_authority.py` and its SQLite store own deterministic owner/universe/provider bindings, the closed `background_attempt|branch_task|run` work-item union, Branch-pinned receipts, claims, and reservations | Add `agent_invocation`, typed subject/lineage, and atomic linkage from a live authenticated draft to `ProviderWorkBinding + AgentInvocationCommand + AgentInvocation` without weakening existing Branch checks | Active owner files: canonical model/service/store and `tests/test_provider_work_authority.py` |
| Authenticated provider draft | The OpenSpec provider contract describes a current-message inert binding draft, but no provider-work draft symbol or persistence exists in `tinyassets/` or tests on this commit | The command cannot become a provider-binding issuance root; live request middleware must create the inert draft and admission must consume it atomically | Requires exact provider/request-admission owner decision; current cloud claim includes `tinyassets/storage/request_admissions.py` |
| Cloud continuation | `tinyassets/cloud_automation_continuation.py` and its store require Branch definition/version/content plus a `BackgroundBranchAttempt` | Carry the same typed subject and agent command/invocation lineage without constructing or querying a Branch attempt | Active owner files: canonical continuation model/resolvers/store and `tests/test_cloud_automation_continuation.py` |
| Delegated grants | `tinyassets/storage/accounts.py:list_capabilities` live-checks current capability names at global/universe scope; grant rows have generations. Provider assignment and outbound connection owners separately expose current non-secret references | Add one typed runtime resolver that returns exact current generations/digests for every requested capability/resource/provider reference; never snapshot a bearer | Read dependency is available, but no existing aggregate runtime-grant resolver owns this contract |
| Health | `RepositorySpecOperationalProjection` is a Branch/background-attempt projection. The cloud audit confirms `EPOCH2_QUEUE_CONSUMER_READY` is false and no provider launch/effect exists | Add a private projection over manifest, activation, command/invocation, provider, and continuation records; heartbeat alone is not progress | New agent projection is collision-free only after canonical record shapes stabilize |

## Required handoff contract

1. The cloud owner either releases or lands the typed-subject conversion for:
   `tinyassets/storage/automation_activations.py`,
   `tinyassets/provider_work_authority.py`,
   `tinyassets/storage/provider_work_authority.py`,
   `tinyassets/cloud_automation_continuation.py`, and
   `tinyassets/storage/cloud_automation_continuation.py`, with their focused
   tests and the packaged activation mirror.
2. Existing Branch values become `ExecutionSubject(kind="branch_version",
   ref=<branch-version-id>, digest=<branch-content-digest>)` without losing any
   Branch definition/version/background-attempt validation. Agent work uses
   `kind="agent_runtime_manifest"`; the two shapes cannot substitute for one
   another.
3. The provider owner selects the canonical live-request draft location and
   transaction boundary. Current code has no such draft. The selected boundary
   must atomically consume authenticated intent into the existing/replayed
   provider binding plus one new command/invocation aggregate; a command or
   queue row alone grants nothing.
4. The owner confirms schema migration and rollback for existing activation,
   continuation, provider receipt, claim, and reservation rows. No destructive
   rewrite and no dual old/new authority are allowed.
5. The handoff includes current-main tests and packaged-mirror responsibility,
   not only model names. The runtime-core lane then updates `STATUS.md` with the
   smallest exact implementation slice before editing.

## First safe implementation slices after handoff

1. **Typed activation subject:** add a small shared subject model, migrate the
   canonical activation store, derive the reserved agent activation key, and
   prove existing Branch transitions plus concurrent binding-alias races.
2. **Immutable manifest/compiler:** add new agent-runtime manifest persistence,
   governed component/plan descriptor registries, exhaustive adapter-declared
   plan compilation, and deterministic/idempotent tests. This slice reads the
   existing definition/binding substrate but does not modify it.
3. **Invocation admission:** add the server-authored command/invocation store
   and atomically consume the canonical live-request provider draft. Prove
   replay, changed-input conflict, missed-boundary no-write, and lower-level
   bypass refusal before provider receipts are reachable.
4. **Provider and continuation composition:** admit the exact command lineage
   and typed subject into the canonical receipt/claim/reservation and
   continuation owners, with Branch regressions and no `BackgroundBranchAttempt`
   on agent paths.
5. **Private recovery/health and dark proof:** reconcile the same identities,
   run production-shaped concurrency/restart/load tests, check packaged parity,
   and verify all seven public MCP handles remain unchanged.

Each slice requires a fresh exact `STATUS.md` Files claim. This audit itself
does not authorize any runtime write.

## Fresh verification

- `py -m pytest tests/test_custom_agents.py tests/test_agent_interchange.py tests/test_automation_activations.py tests/test_provider_work_authority.py tests/test_cloud_automation_continuation.py -q`
  - 146 passed in 9.07 seconds on 2026-08-01 at `a829d428`; the rebase to
    `88a1ac8d` changed only `STATUS.md`, not tested runtime or test files.
- `rg -n "AgentRuntime|agent_runtime|AgentInvocation|agent_invocation|ExecutionSubject" tinyassets tests packaging`
  - no runtime symbols found on current main.
- `docs/audits/2026-08-01-cloud-drain-claim-custody.md`
  - current evidence says one claimed background attempt reaches the bounded
    provider receipt owner, but provider launch/effect and cutover remain absent
    and `EPOCH2_QUEUE_CONSUMER_READY` remains false.

## Decision

Keep the runtime core in claimed coordination state with no runtime files.
Advance only after the active cloud/provider owner records an exact release or
split. In the meantime, the already-live arbitrary import/export and public
remix pipeline remains the source of agent definitions; runtime adapters must
consume it without narrowing the number or shapes of agents users can remix.
