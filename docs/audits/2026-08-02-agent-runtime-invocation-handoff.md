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
