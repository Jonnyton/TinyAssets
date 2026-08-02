# Agent-runtime invocation admission handoff

Freshness: 2026-08-02 UTC, Windows worktree, `origin/main` at `c9a63cee`.

## Decision

Implement `activate-custom-agent-runtime-core` task 3.2 as one dark, generic
agent-invocation admission aggregate. It will atomically consume a live,
authenticated, single-use provider-binding draft into exactly one canonical
`ProviderWorkBinding`, server-authored `AgentInvocationCommand`, and append-only
`AgentInvocation` root. This is shared platform substrate for user-authored
workflows; it is not an OpenSpec-drain scheduler, task selector, prompt policy,
retry strategy, or public control surface.

The admission caller may supply only intent data: the target agent binding,
typed input, idempotency key, and requested budget. Owner, universe, provider,
manifest, activation fence, grants, and provider-binding authority are resolved
by trusted current-state owners. A missed request boundary creates nothing.

## Exact current-main owners

| Concern | Canonical owner | Current-main handoff |
|---|---|---|
| Manifest subject and immutable runtime definition | `tinyassets/agent_runtime.py`, `tinyassets/storage/agent_runtime.py` | PR #2091 plus compiler PRs #2095/#2097 |
| Agent activation epoch/executor/lease and typed subject | `tinyassets/storage/automation_activations.py` | `5ba557d0` / PR #2082 |
| Live grants | `tinyassets/agent_runtime_grants.py` | `b963be66` / PR #2102 |
| Narrow runtime-principal derivation | `tinyassets/agent_runtime_principal.py` | `128d3841` / PR #2114; intentionally awaits this invocation source |
| Provider binding, receipt, claim, reservation, and one-shot call carrier | `tinyassets/provider_work_authority.py`, `tinyassets/storage/provider_work_authority.py` | `1e5a3433` / PR #2137 |
| Crash-safe continuation | `tinyassets/cloud_automation_continuation.py`, `tinyassets/storage/cloud_automation_continuation.py` | `5ba557d0` / PR #2082; agent composition remains task 4.1 |
| Useful-progress health | no canonical agent-runtime owner yet | remains task 4.2; no health module is invented in task 3.2 |
| Packaged runtime | matching files under `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/` | mirror every new canonical runtime file exactly |

## Atomic and bounded flow

The invocation store uses the same SQLite database as the provider-work owner
and starts one `BEGIN IMMEDIATE` transaction. Inside it, the trusted admission
service resolves and validates current manifest, activation, grants, and the
provider seed; inserts or exactly replays the provider binding through the
provider-work transaction primitive; then inserts the immutable command and
initial invocation event/root. Any conflict or exception rolls back all three.

The durable command contains non-secret authority provenance only. It never
contains the owner's bearer or provider credential. Recovery reads the same
identities and must revalidate them; persistence does not recreate request
authority.

The live binding draft is an inert, process-local, single-use capability minted
only while `current_identity()` is authenticated. It carries a trusted resolver,
not a caller-authored seed, and is consumed by the admission owner. Directly
constructing records, invoking private helpers, possessing queue work, or
replaying a used draft grants no authority and produces no writes.

## Explicit fences

- `BackgroundBranchAttempt` and its ledger are neither imported nor queried.
- Existing Branch admission, activation, provider receipt, claim, reservation,
  launch, and continuation guards remain unchanged.
- Task 3.2 exposes no MCP handle, app ingress/reply, workflow/graph mutation,
  effect, conversation custody, tenant-code path, or provider launch.
- Provider output and cloud recovery remain later tasks 3.3 and 4.1.
- Chatbot creation/remix/activation and final rendered connector acceptance are
  successor work built on this generic seam.

## Verification gate

- `openspec validate activate-custom-agent-runtime-core --strict` — passed
  2026-08-02, Windows worktree.
- `openspec validate activate-main-universe-spec-drain --strict` — passed
  2026-08-02, Windows worktree.
- `python scripts/openspec_flow.py audit --ref origin/main` — passed with zero
  complete-unarchived exceptions and no broad collision atoms; the claimed
  cloud-drain lane remains visible as the integration path.
- Independent exact-head architecture/security review: APPROVED on
  `e63822120de4651e80f3d47b30c4a9a2b0b5b685` by a read-only Codex peer on
  2026-08-02. The reviewer confirmed atomicity, live-boundary authority,
  replay/concurrency, bearer-free recovery provenance, Branch isolation, and
  the absence of drain-specific platform logic. Claude and the first broad
  Codex attempt hit bounded provider timeouts without verdicts; the
  user-approved same-provider fallback returned in 38 seconds when narrowed
  to the decision artifact and normative spec.
- Before completion: focused failure-first tests must prove exact replay,
  changed-input conflict, concurrent single winner, missed-boundary rollback,
  bearer-free recovery evidence, forged-record refusal, and Branch-ledger
  isolation; broader authority regressions, lint, strict OpenSpec, and packaged
  mirror parity must pass.

## Implementation candidate and open gate

Task 3.2 has a reviewed implementation candidate, but is not complete and must
not merge yet. The final post-rebase review at
`bab1bc5bb11f37f075e386b426d2ffb580e27abe` found that the
`AgentInvocationExternalAuthorityFenceSource` is implemented only by the test
double. The interface correctly requires a mutation lock spanning validation
through commit, but no canonical production owner currently provides that lock
across manifest, grant, and provider-assignment mutation paths. An interface is
not operational authority.

- `tinyassets/agent_runtime_invocation.py` owns caller-intent validation, the
  authenticated one-use draft, a second live-state resolution, the sealed
  one-use persistence grant, immutable command/root types, and the required
  `AgentInvocationExternalAuthorityFenceSource` contract. There is no unsafe
  fallback when a trusted authority owner cannot validate its pinned manifest,
  grant, and provider-assignment generations while holding their mutation lock
  through commit.
- `tinyassets/storage/agent_runtime_invocation.py` holds that external fence
  across one `BEGIN IMMEDIATE` transaction, checks the exact activation fence
  inside the transaction, links canonical provider-binding issuance with the
  command/root/initial event, and rolls the entire aggregate back on failure.
  Commands, roots, and events are immutable or append-only and digest-checked
  on replay/read.
- `tinyassets/storage/provider_work_authority.py` exposes only a private
  active-transaction composition hook. It does not issue receipts, claims,
  reservations, call carriers, or provider work.
- Canonical runtime changes are byte-identical in the packaged daemon. No MCP,
  app, Branch-attempt, drain-policy, workflow/graph, effect, provider-call, or
  public-control route was added.

Failure-first evidence includes exact replay, changed-input conflict, eight-way
single-winner admission, ended/reused/cloned draft refusal, direct-store bypass
refusal, forced post-binding rollback, budget refusal, bearer-free recovery,
initial-event integrity, and a concurrent provider-assignment revocation that
blocks on the external fence until after commit.

Verification on 2026-08-02, Windows worktree:

- 12 focused invocation-admission tests passed.
- 255 combined custom-agent manifest/compiler/grant/principal/invocation,
  activation, execution-subject, provider-authority, continuation, and
  user-owned-cloud regressions passed.
- Ruff, strict OpenSpec, canonical/plugin mirror parity, pre-commit import graph,
  and isolated packaged imports passed.
- Pre-rebase independent capability review: APPROVE at `063e1576`.
- Independent exact-head storage/concurrency review: APPROVE at `063e1576`.
- Final post-rebase capability review: REQUEST_CHANGES at `bab1bc5b`; implement
  and wire the production fence owner and prove manifest/grant/provider mutation
  exclusion, not only the provider-assignment test double.

The first exact code review correctly rejected the original repeated-read
design because authority could change after its last check but before commit.
The candidate design instead requires the trusted external authority owner to
hold its mutation fence across commit while activation is transactionally
checked in SQLite. The remaining gate is concrete production ownership and
wiring of that fence. Task 3.3 follows only after task 3.2 passes that gate:
only the exact admitted lineage may enter canonical provider
receipt/claim/reservation/launch, with a fresh live authority check before
spend.
