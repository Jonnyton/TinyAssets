# Opus 5 review: retire MCP provider-secret deposit

Date: 2026-07-24 America/Los_Angeles
Reviewer: Claude Opus 5, high effort, isolated read-only CLI
Initial base: coordination head `c91ef19e`; reviewer refreshed current-main and
named every drift-sensitive claim
Change reviewed: `retire-mcp-provider-secret-deposit`
Verdict: **ADAPT**

## Executive finding

Keep `retire-mcp-provider-secret-deposit` as a separate OpenSpec change. The
shipped raw-secret path is a clean, independently owned P0 boundary: one hidden
MCP handler accepts an API key, one production caller writes the provider
record, and the provider child-environment overlay later resolves it.

Narrow the change so it does not create:

- a second provider ceiling or `setup_required` contract beside #1691;
- a second account-token lifecycle beside #1736;
- a second grant/lease/fence system beside D0 execution authority;
- a false claim that the existing full-platform §14 scenarios prove credential
  dereference concurrency.

The retirement change owns secret ingress prohibition, requester-executor
provider-secret custody, opaque binding semantics, local launch-time
dereference, legacy retirement, and custody-specific concurrency. Neighboring
changes keep their existing ownership and receive surgical adaptations.

## Current shipped truth confirmed

- `tinyassets/api/universe.py::_action_set_engine` reads
  `inputs_json.api_key`, base64-encodes it, and writes an `llm_api_key` record.
- `tinyassets/credential_vault.py` explicitly treats base64 fields as encoding,
  not encryption, and permits recoverable provider secrets on disk.
- `tinyassets/providers/base.py` resolves the selected universe overlay into the
  provider child environment.
- Slice A0 already prevents ambient founder credentials from entering that
  child environment; it intentionally does not fix selected-universe custody.
- The result ledger is already secret-free and should receive regression tests,
  not be presented as new behavior.
- Canonical and packaged implementations are currently byte-identical.
- `write_credential_vault` has one non-test production caller for this path.
- The vault upsert fix is landed, but the canonical contract still says
  concurrent writers have no serialization guarantee.
- Router chains can still retain maintainer/free-provider routes when no
  allowlist is present; #1691 owns that destination ceiling.
- `set_engine` is reachable through the hidden legacy `universe` tool, not one
  of the exact-seven canonical handles.
- `scripts/check_primitive_exists.py action set_engine` false-negatives because
  it recognizes `_ext_<verb>` and `def <verb>`, not `_action_<verb>` or an
  action-map entry pointing to `_action_<verb>`.

## Ownership map

| Requirement | Single owner |
|---|---|
| No provider secret in MCP arguments, prompts, logs, ledgers, traces, crash reports, argv, or control-plane state | This change |
| No new public MCP verb | This change's design constraint |
| Raw-secret `set_engine` rejection and typed `setup_required/held` result | #1691 adaptation |
| Requester-controlled native OS provider-secret custody | This change |
| Account refresh-token storage and host registration | #1736 |
| Opaque host/principal-bound provider credential binding | This change, using the distributed-execution seam |
| Destination ceiling and no founder/maintainer fallback | #1691 and existing outbound authority |
| Execution grants, leases, generations, and fences | Existing D0 distributed-execution authority |
| Legacy provider-secret inventory/rotation/revocation/deletion | This change |
| Universe administration not implying credential authority | This change modifies identity/access truth |
| Canonical/plugin parity | Repository gate/task |
| Local custody rotation/dereference/removal concurrency | This change |
| Full control-plane scale scenarios | Existing §14/Track J owner; deferred, not relabeled |

## Required neighbor adaptations

### #1691

Do not write a competing `provider-routing` delta here. #1691 already owns:

- `setup_required`;
- `engine_assignment_state`;
- the provider destination ceiling;
- the assignment transaction;
- `ProviderInvocation`.

Adapt #1691 so:

- a BYO request containing any raw-secret field returns its existing
  `setup_required` and `held` shape before config or vault mutation;
- a BYO request containing a validated credential binding reference may publish
  the singleton provider ceiling and become ready;
- legacy raw-key records never map directly to ready.

### #1736

Do not overload the stable account-token namespace
`tinyassets-desktop:<account>:<host>`. Provider secrets need a disjoint,
versioned/random reference with universe, provider, principal, host, generation,
and lifecycle binding.

Before runtime use, #1736 or its successor must:

- wire native-store deletion (the current `delete()` has no caller);
- add compare-and-swap or equivalent rotation protection;
- finish production account-to-host binding.

### Distributed execution

Reuse the existing runner seam's `credential_grant_ref`; do not add a parallel
grant type or put credential authority into a new lease/fence system. The
current seam permits an empty string and explicitly disclaims validation, so
the owning capability must accept a coordinated MODIFIED requirement before
runtime work. Fail-closed is absence of a valid grant, not an empty-ceiling
grant.

### #1469 and #1606

- #1469 is source-only/future and is not a dependency. Its server ciphertext
  store contradicts requester-only custody, and its grants/leases duplicate D0.
- #1606 is predecessor context only; #1691 remains the routing successor.

## Required OpenSpec shape

### New capability: `provider-credential-custody`

Own:

1. provider secrets live only in the requester-controlled executor's native OS
   secret store, with no file/env/plaintext fallback;
2. the control plane stores only a non-secret, non-derivable, opaque binding
   scoped to provider, universe, principal, host, generation, scopes, and
   expiry;
3. dereference occurs only on the selected executor at provider launch inside
   the frozen-authority window;
4. no secret enters MCP/prompts/logs/ledgers/traces/crash reports/argv;
5. rotation and removal are monotonic, concurrency-safe, and idempotent.

### Modified/removed `credential-vault` truth

Use full MODIFIED/REMOVED blocks rather than parallel ADDED requirements:

- REMOVE `As-Built Storage Protection Is Filesystem Permissions Only` once its
  provider-secret class is retired; leaving it would license the forbidden
  recoverable storage.
- MODIFY `Per-Universe Typed Credential Store`: reject new
  `llm_api_key` writes; permit legacy loading only for metadata inventory and
  exact deletion.
- MODIFY `Per-Universe Provider Auth Env Overlay Without Cross-Universe
  Leakage`: replace BYO deposit with local binding dereference at launch.
- MODIFY credential alias/secret extraction so raw `llm_api_key` selection is
  retired.
- MODIFY the unversioned replacement requirement so migration transitions use
  a per-universe exclusive lock external to the existing write helper.

### Modified identity/access truth

Modify the existing access-axis requirement:

- a universe `admin` grant permits universe administration but does not confer
  authority to resolve, rotate, delete, replace, or use another principal's
  provider credential binding;
- cross-principal or cross-host resolution fails closed.

### No provider-routing delta here

#1691 owns the conflicting canonical requirement and must carry its two
adaptation scenarios.

## Legacy retirement saga

Retirement is a cross-system saga, not an atomic file migration.

Recommended monotonic states:

1. `discovered` — metadata-only inventory; never decode secret fields.
2. `held_ambiguous` — no resolvable owner; terminal hold, no export/deletion/use.
3. `notified` — owner notified out of band.
4. `rotation_required` — provider launch held.
5. `revoked_upstream` — positive provider or explicitly labeled owner
   attestation.
6. `artifacts_deleted` — exact materialized provider homes removed.
7. `record_deleted` — compare-and-delete succeeds against inventoried digest.
8. `closed` — idempotent terminal state.

Required invariants:

- Inventory contains only universe/slot/service, field names, record digest,
  generation, and byte length; it never decodes or returns secret bytes.
- No state exports plaintext or silently migrates a legacy secret.
- Owner action and provider rotation/revocation precede deletion.
- Every transition holds the existing per-universe assignment lock.
- Record deletion is compare-and-delete against the inventory digest.
- Stale generations re-inventory; they never act.
- Idempotency key is scoped to universe, credential slot, and generation.
- Materialized artifacts are enumerated and deleted before the source record.
- Migration and credential use share the existing launch fence/generation.
- Any incomplete, ambiguous, or failed state is held with no provider call and
  no maintainer/founder fallback.
- Rollback rebinds a new local generation or remains held; it never resurrects
  raw vault material.

## Shared-universe shape

Canonical identity currently has principals, universe ACLs, and
`read|write|admin`; it has no accepted organization-owned credential model.

Build now:

- bind a credential reference to the exact depositing principal and executing
  host;
- do not derive credential-use authority from universe administration;
- fail closed when requester/principal/host/provider/generation does not match.

Explicitly defer:

- organization-owned pooled provider credentials;
- cross-principal credential delegation;
- tenant-wide grants and seat/quota accounting;
- volunteered public-capacity authority.

Those require their own accepted owner and must not be invented in this change.

## Threat findings that changed the proposal

### P0: prompt elicitation is the earliest leak

The current prompt invites the founder to provide an engine including an API
key. Handler rejection happens after the user and chatbot may already place the
secret in a transcript or tool argument. The retirement contract must remove
raw-key elicitation and direct setup to an authenticated requester-local
surface.

`tinyassets/api/prompts.py` and its packaged mirror need an exact future claim;
they are outside this review/spec-only lane.

### P0: empty opaque reference currently fails open

The distributed runner seam permits `credential_grant_ref=""`. A
credential-bearing execution must validate a non-empty, current, correctly
bound reference before dispatch.

### P1: deletion and launch can race

The current vault has no serialization guarantee. Migration must reuse the
assignment lock, compare-and-delete, and launch fence.

### P1: account-token delete/rotation is incomplete

The native credential manager's delete path is unwired, and rotation uses
unconditional overwrite. Provider-secret custody cannot inherit those shapes.

### P1: full-platform §14 is not a custody proof

The integrated architecture's §14 scenarios cover control-plane subscriber,
bidding, read-storm, and presence load. They do not exercise credential
dereference, and their full harness is not yet delivered.

Require a named local multi-process rotate/dereference/delete proof now. Keep
the real §14 Track J obligation explicit and deferred; do not claim the local
test satisfies it.

### P2: successor setup surface is unresolved

The hidden legacy `universe` tool is scheduled for retirement, while
`set_engine` is not one of the exact-seven canonical handles. Before runtime,
the design must decide which existing canonical primitive carries typed
`setup_required` without adding a new MCP verb.

## Dependency order

Already landed:

1. Slice A0 fail-closed provider child environment.
2. Credential-vault single-record upsert.

Specify now:

3. #1691 amendment ownership in writing.
4. This change's proposal/design/deltas/tasks.
5. Identity/access non-conflation and new custody capability.
6. Distributed-execution delta only with that capability owner's acceptance.

Runtime waits for:

7. #1736/native store plus production principal-to-host binding.
8. #1484 and universe-creation release of `api/universe.py`.
9. #1691/provider routing and frozen invocation authority.
10. Resolution of legacy-tool retirement and the successor setup surface.
11. An explicit claim for `api/prompts.py` and mirror.

## Required verification

RED-first requirements include:

- raw `api_key` input produces typed hold/setup with byte-identical config and
  vault and no secret echo;
- mutation probe proves the rejection test is non-vacuous;
- no production path can create a new raw provider-secret record;
- prompt/mirror never instruct a user to provide an API key through MCP;
- no native store or wrong principal/host/provider/generation fails with zero
  provider calls and no ambient fallback;
- dereference occurs once inside the frozen-authority launch boundary;
- empty/stale/tombstoned binding refs fail preflight;
- metadata inventory serializes zero secret bytes;
- every saga transition is monotonic and idempotent;
- digest changes abort deletion and re-inventory;
- crash injection at every transition resumes without export/resurrection;
- ambiguous ownership remains terminally held;
- artifact enumeration/deletion precedes record deletion;
- concurrent rotate/dereference/delete has one coherent winner, no torn read,
  no lost rotation, and no orphaned active native reference;
- canonical/plugin bytes remain identical;
- live exact-seven `/mcp`, rendered connector conversation, and post-fix
  organic-use watch complete the public acceptance path.

## Unresolved decisions

These block runtime but do not block this review/spec lane:

1. Which existing canonical handle carries `setup_required` after hidden
   `universe/set_engine` retires?
2. Will #1691's owner accept the two-scenario raw-secret/reference amendment?
3. Will the distributed-execution owner accept non-empty, bound
   `credential_grant_ref` validation?
4. What accepted owner will eventually define organization-pooled credential
   delegation?

## Final reviewer disposition

**ADAPT accepted for specification work.** A separate change is warranted and
may be drafted now within its claimed change directory and audit file. No
runtime, canonical-spec foldback, prompt edit, push claiming implementation, or
live rollout is authorized until the owner/dependency decisions above are
resolved.

## 2026-07-24 exact-artifact correction note

Independent Codex exact-artifact review on 2026-07-24
America/Los_Angeles compared the first draft with current canonical specs and
code at `origin/main` `4b5c7fce9520c71686936b0301bc51423c5a15f4`. Its
verdict was **ADAPT**, not approval. It found broad canonical-requirement loss,
ordinary-write retirement bypass, missing replacement/cutover states,
unimplementable runner/D0 coupling, A0 guarantee loss, unversioned binding
authority, and a setup surface presented as existing behavior.

Opus 5 then rereviewed the corrected exact artifacts on 2026-07-24 and again
returned **ADAPT**, with blockers B1-B7. This note durably records the resulting
corrections; task 1.2 remains open and no Opus approval is claimed:

- **B1:** the canonical Codex `llm_subscription.auth_json_b64` non-empty,
  strict-base64, valid-JSON write-time validation sentence and `ValueError`
  scenario are restored verbatim.
- **B2:** Claude subscription resolution again means only the first normalized
  effective-service `claude` record, direct `oauth_token` then
  `claude_code_oauth_token`, then selected `token_b64`/`secret_b64`, using the
  permissive standard base64 decoder and surfacing actual base64/UTF-8 errors.
  No Claude alias widening or Codex `auth_json_b64` conflation remains.
- **B3:** legacy retirement covers all ten shipped aliases:
  `anthropic`, `claude`, `claude-code`, `openai`, `codex`, `gemini`, `google`,
  `groq`, `xai`, and `grok`. Slot identity includes environment-variable slot,
  stored occurrence, and record digest; unsupported service is terminally
  held ambiguous.
- **B4:** retained `llm_subscription`, `vcs`, and `social` one-record, bulk,
  and empty writes remain usable through an opaque byte-preserving dual loader
  under draft PR #1691's exclusive assignment lock. Every legacy
  `llm_api_key` object slice remains byte-exact and ordered; ambiguous or
  malformed state blocks before replacement.
- **B5:** canonical replacement semantics are restored, including
  first-position replacement/append, exact resolver selectors, VCS purpose
  containment and no-shadow behavior, removed-purpose descriptor tuple,
  Claude/Codex alias-family subscription merge, duplicate first-record
  semantics, fixed sibling behavior, and explicit `ValueError`.
- **B6:** this dated note replaces the earlier unsupported generic review claim
  with the exact Codex findings and Opus rereview disposition.
- **B7:** the review and correction date is 2026-07-24
  America/Los_Angeles.

The same correction pass also records later independent ADAPT findings:

- requester-owned local invocation uses draft PR #1691's shared-reader
  `ProviderInvocation -> ProviderLaunchHandle` barrier; accepted-market remote
  execution waits for owner-accepted production B2 authority; current D0 is
  fake-only/production-denied and is not ordinary provider authority;
- `runner/v1` remains an opaque nine-field carrier;
- `openspec/changes/test-identity-and-reset/` cannot bypass the legacy saga,
  and malformed or unclassifiable existing state blocks every ordinary write,
  replacement, and reset;
- two stores use a commit token plus local acknowledgement, not a fictional
  shared CAS; a late control-plane binding after local tombstone is held and
  compare-cleared by exact enrollment/token/generation;
- TinyAssets stops eliciting, rejects without echo, and protects inventoried
  TinyAssets-owned sinks, but cannot redact client-owned upstream chatbot
  transcript bytes already sent;
- wrong-scope bindings fail closed; `failed_held` is an overlay carrying the
  last committed state, not a backward saga transition;
- `write_graph(target=universe)` remains a successor candidate, not existing
  configuration behavior; native backend, artifact ownership/digest/refcount,
  async principal, and confused-deputy gates remain required.

This correction note did not itself change the original review's
authorization. The subsequent exact-artifact disposition below closes only
task 1.2 and authorizes publication of the still-blocked specification lane.

## 2026-07-25 exact-artifact approval

Opus 5 rereviewed the exact proposal, design, delta specs, tasks, and audit
after the B1-B7 correction pass. Its final verdict was **APPROVE —
spec/review-only** after three additional consistency corrections:

- `.openspec.yaml` records the actual `2026-07-24`
  America/Los_Angeles creation/review date;
- both the credential-vault and owning provider-custody reset requirements
  require confirmed global reset to perform zero mutation and remain blocked
  until every legacy key's retirement saga reaches safe terminal deletion;
- the provider-custody requirement no longer permits reset to invoke that
  saga while the credential-vault requirement requires zero mutation.

An independent Codex exact-artifact rereview also returned **APPROVE —
spec/review-only** after confirming the date and reset semantics, strict
target validation, all-item strict validation (42/42), and a clean diff.

This approval permits committing, pushing, and reviewing this OpenSpec change
as a blocked specification lane. It does **not** authorize runtime edits,
canonical-spec sync/archive, deployment, or rollout. Tasks 1.3-1.9 and all
runtime/owner gates remain open.

## 2026-07-25 owner-resolution ADAPT

After the Claude Opus rate reset, Opus 5 performed a fresh read-only
owner-resolution review against draft PR #1746 at `4e5e7529`, current
`origin/main` at `3f933caf`, PR #1691 at `2954e4cb`, and PR #1736's runtime
branch. An independent Codex explorer mapped the same ownership seams in
parallel. Both returned **ADAPT**; neither authorized runtime work.

The converged corrections are:

- #1691 owns generic `setup_required`/held assignment state,
  provider-destination ceilings, assignment CAS/generation, and the frozen
  launch barrier. This change owns the `llm_api_key`-typed ingress refusal;
  landed Slice A0/provider-auth isolation owns the general no-maintainer-route
  invariant.
- #1691's current `ProviderInvocation` wording is internally ambiguous between
  credential material and a material reference. Requester-owned local launch
  must carry only the opaque reference/provenance; executor-local `start()` is
  the sole native-secret resolution boundary. Acceptance must bind to an exact
  #1691 SHA after review #1727 is folded and the branch is rebased.
- PR #1736 is not a target-only draft. It contains runtime for account
  refresh-token custody, exact native-backend allowlisting, and a client-side
  `OriginClient` protocol, while explicitly leaving the production
  server-side account-to-host binding unfinished. Those shipped seams must be
  consumed rather than duplicated.
- No current lane owns an authenticated, stable, server-attested host
  principal. A separate `bind-host-principal-to-account` successor must derive
  the account principal from verified identity, keep it distinct from
  insert-always host-pool rows and unattested client identifiers, implement
  the server side behind #1736's protocol, and expose the authenticated
  binding read required by custody reconciliation.
- Portable native keyrings expose exact-reference set/get/delete, not
  enumeration. Custody therefore needs an atomic secret-free bounded local
  pending index as the sole reconciliation enumeration source.
- Consuming landed D0 record types is type reuse, not a D0 authority grant;
  D0 remains fake-only/production-denied.

The proposal, design, custody delta, and tasks were adapted to this split.
Because those edits postdate the earlier exact-artifact approval, task 1.2 is
open again until Opus 5 confirms the exact new head. Tasks 1.3a/1.3b and
1.5a/1.5c also remain open for counterparty/owner acceptance. Runtime,
canonical-spec sync/archive, deployment, and rollout remain unauthorized.

## 2026-07-25 adapted exact-head approval

Opus 5 rereviewed exact adapted head `4fa0dc4e` against current
`origin/main` at `3f933caf` and returned **APPROVE — spec/review-only**.
It verified all seven owner-resolution folds, the exact ten-file planning
scope, canonical MODIFIED/RENAMED requirement preservation, the 60-line
STATUS budget, and these gates:

- `git diff --check origin/main...HEAD`: clean;
- target strict OpenSpec validation: valid;
- all-item strict OpenSpec validation: 42 passed, 0 failed;
- no stale `draft PR #1736`, target-only tray, #1736-owns-provider-custody,
  or `ProviderInvocation`-contains-material wording;
- no new MCP verb, raw-secret control-plane path, maintainer/founder fallback,
  second authority system, runtime edit, or canonical-spec mutation.

An independent Codex verifier also returned **APPROVE — spec/review-only** on
the same exact head and gates. Opus noted two non-blocking wording
observations: “shipped branch” means the open PR's runtime-bearing branch, not
a merged change, and “authenticated binding read” means the host-principal
binding read rather than the separate credential-binding read. The surrounding
gates make both meanings explicit; neither changes ownership.

This exact-head approval authorizes publication of the adapted draft only.
Tasks 1.3a/1.3b, 1.4, 1.5a/1.5b/1.5c, and 1.6-1.9 remain open. Runtime,
canonical-spec sync/archive, deployment, and rollout remain unauthorized.
