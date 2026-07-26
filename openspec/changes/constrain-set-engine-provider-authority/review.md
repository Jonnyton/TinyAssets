# Independent review

## Opus 5 architecture review — 2026-07-25

Environment: Windows, replacement branch `codex/reconcile-provider-authority`
based on `origin/main` `d182d5f8`.

Claude Opus 5 returned `ADAPT` on the reconstructed #1691 proposal. The review
found five blocking defects in the historical design:

1. `Verified[T]` could authenticate a request but could not mint
   requester-local provider authority.
2. Provider-secret binding did not prove the current principal, universe,
   provider, host, assignment generation, and binding digest at the sink.
3. Universe birth initialized engine state without a matching authority
   invariant.
4. Reciprocal acceptance gates among provider routing, secret custody,
   universe creation, and host activation formed circular dependencies.
5. Cutover could remove the current founder-home path before any replacement
   source was live-ready.

The replacement resolves those findings by:

- defining a server-minted, request-local `ProviderRequestCapability` as
  authenticated transport evidence rather than standalone provider authority;
- requiring fresh sink-side intersection with assignment state and an exact,
  live, non-tombstoned credential binding;
- adding an independent deny-all engine-authority invariant to every universe
  birth;
- publishing one-way dependency interfaces while documenting custody's
  provider-owner acceptance output gate;
- separating credential authority from fulfillment class and dynamic provider
  availability; and
- forbidding cutover until at least one live-ready custody or requester-host
  path preserves existing founder-home service.

This is a planning-only OpenSpec lane. Runtime, tests, deployment, and
packaging remain unchecked and outside this replacement's write set.

## Verification

Fresh Windows evidence on 2026-07-25:

- `openspec validate constrain-set-engine-provider-authority --strict`: valid.
- `openspec validate --all --strict`: 48 passed, 0 failed.

Final status is pending an exact-revision Opus 5 re-review and publication of
the final review disposition.

The initial sibling handoffs were published without making this target spec
wait for sibling acceptance:

- custody: PR #1746 comment `issuecomment-5081176707`;
- universe creation / first-contact authority: PR #1660 comment
  `issuecomment-5081177162`; and
- provider-attempt receipts: merged spec PR #1650 comment
  `issuecomment-5081177511`.

## Exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed commit `aa6a2799` and returned `ADAPT`. Critical findings:

1. Ambient request `ContextVar` state cannot cross the router's documented
   class-level thread pool.
2. Post-response graph/run/schedule, daemon, retrieval, and other background
   provider work had no named authority owner.
3. Source resolution did not cover the shipped domain or make
   `ollama-local` reachable under target authority.

Important findings covered conflicting active universe/receipt deltas,
custody's exact-SHA owner-acceptance gate, dependent-lane tasks that made this
change uncompletable, incomplete `complete()`/policy MODIFIED coverage, dropped
canonical clauses, and newborn deny-all ordering ahead of a rendered setup and
ready-source gate.

The adapted artifacts now:

- explicitly carry the server-minted request capability through
  `call_provider`, synchronous router helpers, and the router pool closure;
- name `harden-background-provider-execution-authority` as durable
  task/thread/process receipt owner and hold those paths before it lands;
- define total shipped/target source treatment, including successor-owned
  `local_model` -> `["ollama-local"]`;
- declare precedence over the conflicting active universe bundle and receipt
  enums;
- move sibling work to published expectations rather than this change's
  completion checklist;
- retain canonical provider `complete(...)` under
  `ProviderExecutor.start(...)`, restore every dropped canonical clause, and
  MODIFIED-cover policy plus both sandbox requirements; and
- gate newborn deny-all and cutover on rendered setup, a live-ready request
  source, and complete background bridge classification.

Final disposition remains pending strict validation, adapted exact-SHA
handoffs, and another Opus 5 review.

Adapted exact-SHA `967b048d` handoffs:

- custody provider-owner acceptance: PR #1746 comment
  `issuecomment-5081288367`;
- universe bundle/provider-set precedence: PR #1660 comment
  `issuecomment-5081288830`; and
- receipt closed-enum precedence: PR #1650 comment
  `issuecomment-5081289120`.

## Second exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed `f2b6e9ef` and returned `ADAPT`. One Critical finding showed
that the live first-contact mapper recognizes only
`AllProvidersExhaustedError` plus non-null chain state, so the new
pre-provider `ProviderAuthorityHeldError` would bypass
`engine_setup_required_payload` and become generic failure prose.

Important findings:

- `activate-requester-host-engines` had no durable lane, leaving the target
  zero-cloud local source owner nominal rather than actionable;
- the universe and receipt changes were already merged-active, so their
  conflict must be resolved before archive/sync rather than before merge;
- auth-health quarantine's canonical local-fallthrough requirement was not
  yet MODIFIED by the authority ceiling; and
- inherited asyncio ContextVars could outlive middleware reset without a
  positive server-checkable liveness binding.

The next adaptation adds:

- a universe-lifecycle requirement and owned RED/GREEN task mapping the exact
  typed hold to the canonical setup payload without requiring exhaustion,
  chain state, or provider attempts;
- one durable STATUS row owning both background-receipt and
  requester-host/local successor change directories;
- explicit archive/sync precedence, including the receipt
  `error/provider_error` carve-out;
- a full MODIFIED auth-health requirement with authority-bounded local
  fallback;
- a private server liveness registry bound to the owning request execution
  scope, synchronously revoked at request end and rechecked at the sink;
- explicit newborn `engine_source=unassigned`; and
- exact `credential_kind` and `authority_class` field names.

Fresh Windows strict validation after these edits: target valid; full tree
48 passed, 0 failed. Final disposition remains pending final-SHA handoffs and
another Opus 5 review.

Final candidate `1a2262b9` handoffs:

- exact-SHA custody acceptance: PR #1746 comment
  `issuecomment-5081341084`;
- typed-held setup mapping plus universe archive/sync precedence: PR #1759
  comment `issuecomment-5081342047`; and
- receipt exception carve-out plus archive/sync precedence: PR #1756 comment
  `issuecomment-5081343125`.

## Third exact-revision Opus 5 re-review — 2026-07-25

Opus 5 reviewed clean commit `1e41d6b0` and returned `ADAPT`. Critical: the
host/local successor wrote engine assignments but did not own interactive
request capability minting for unauthenticated stdio/SSE, so Tier-2 tray,
Tier-3 OSS, and Claude-plugin local surfaces could remain permanently held.

Important findings:

- the canonical setup-required contract was split between
  `identity-auth-and-access-control` and `universe-lifecycle-and-soul`, while
  the merged universe change still mandated raw BYOC/accepted-market paths;
- `_DEFAULT_ENGINE_SOURCE` and `universe_has_assigned_engine` would interpret
  new `engine_source=unassigned` as an assigned engine on the legacy
  exhaustion branch; and
- cutover proved that setup prose rendered, not that any advertised path was
  completable on the user's actual surface.

The next adaptation:

- extends `activate-requester-host-engines` into
  `identity-auth-and-access-control` and gives it the separate,
  session-scoped `ProviderHostRequestCapability` for attested same-user
  stdio/local-SSE/tray/plugin execution;
- moves the typed-held setup contract into
  `identity-auth-and-access-control` under the same requirement name as the
  merged universe change, with explicit archive/sync supersession;
- requires `_DEFAULT_ENGINE_SOURCE=unassigned` and readiness-derived
  `universe_has_assigned_engine`, including legacy exhaustion proof; and
- requires Tier-1 connector-completable accepted-market setup plus
  surface-specific local setup for tray, OSS stdio, and Claude plugin before
  cutover. Raw BYOC and unavailable desktop-only paths are not advertised.

Final disposition remains pending validation, refreshed exact-SHA handoffs,
and Opus 5 approval.
