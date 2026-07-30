# Ringer Production-Orchestration Independent Review

Date: 2026-07-30
Initial provider: Codex (`codex-gpt5-desktop`)
Required opposite provider: authenticated Claude Code 2.1.220
Fallback reviewer: fresh-context Codex CLI, high reasoning
TinyAssets base reviewed: `ef65fdc7f37fb96d7d1be711dda3b34e9de9c0c8`
Ringer source reviewed: `a1a91b8b384a90dcca379e1cb9ab91405275ac46`
Initial verdict: **ADAPT**
Folded exact-head verdict: **APPROVE** at
`53d44236c76a9e3c8b66070988ab6778f9f631c0`

## Provider-Limit Evidence

Claude Code was invoked read-only with only `Read`, `Glob`, and `Grep`
available. It returned the hard account result:

> You've hit your monthly spend limit

The host had already approved a same-provider, fresh-context independent review
when the opposite-provider limit is reached. The fallback review was dispatched
through `scripts/peer_agent.py` with a self-contained brief, no inherited chat
context, read-only repository access, and the exact Ringer clone. Its complete
output is preserved at `output/ringer-codex-fallback-review.md`.

## Blocking Adaptations

1. **Do not create a second aggregate authority.** The user-authored object is
   only an immutable work definition. User-facing status is a read-only
   projection over the existing activation, background attempt, provider,
   evaluation, outbound-effect, and GitHub/OpenSpec owners.
2. **Do not execute tenant repository code on the control plane.** The first
   slice may use typed deterministic evaluators that execute no tenant code.
   Shell, repository tests, or external tools fail closed with
   `sandbox_unavailable` until the distributed-execution owner supplies
   production confinement, secret absence, resource limits, cleanup, and
   fenced terminal evidence.
3. **Do not implement target-local GitHub reconciliation.** Current
   `github_pr.py` declares destination reconciliation unsupported. Activation
   depends on the `outbound-boundary-layer` owner landing exact remote lookup
   and crash-after-effect reconciliation, or on an explicit reviewed
   delegation inside that owner.

## Important Adaptations

- Ringer isolates one workspace per task; retries reuse that task workspace.
  TinyAssets must specify continuation versus reset and mint fresh
  target/provider attempt generations while preserving one logical definition
  and one system-derived effect identity.
- Keep `activate-main-universe-spec-drain` single-packet and single-repository.
  Dependency waves, refinery automation, and multi-repository operation belong
  to later deltas after conformance.
- Phone control uses existing canonical handles. The first slice supports
  authenticated inspect, pause, resume, stop, publish, and rollback-by-rebind.
  Reprioritization waits for an epoch-2 queue-policy contract.
- Freeze the existing `AcceptanceScenario` identity/version, evaluator chain,
  input artifact digests, privacy scope, and expected evidence before an
  attempt. Persist an immutable evaluation receipt; evaluation never grants
  provider, GitHub, merge, or foldback authority.
- The PolyForm Shield boundary forbids using, incorporating, adapting, or
  deriving Ringer code, tests, templates, command structure, or internal data
  formats without compatible licensing or qualified legal approval.
- Preserve a content-addressed commit/diff artifact before workspace cleanup.
  Combine fresh GitHub PR/check/merge facts with TinyAssets authority
  generations; GitHub is not the owner of activation or internal receipts.

## Required OpenSpec Foldback

The existing change remains the owner and Jonathan's drain remains its first
acceptance fixture. Before runtime implementation:

- make principal, universe, repository, accepted spec, Branch version,
  evaluator policy, provider route, and destination data-bound inputs;
- add explicit dependencies on epoch-2 activation, background Branch/provider
  authority, safe execution for tenant code, and outbound GitHub
  reconciliation;
- define the immutable work definition and derived projection without a packet
  state machine;
- limit the first evaluator to typed no-tenant-code behavior;
- specify one bounded retry with explicit workspace and generation semantics;
- remove reprioritization and dependency waves from the first slice.

No Ringer implementation code was copied or adapted.

## Folded Exact-Head Approval

After every required adaptation was folded, an independent read-only reviewer
confirmed that the proposal, design, tasks, delta spec, implications, and this
review artifact were mutually consistent. Strict OpenSpec validation and
`git diff --check origin/main...53d44236` passed. No runtime implementation
blocker remains for task 1.1; activation remains gated by the explicit
prerequisite owners.
