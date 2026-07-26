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
- publishing one-way exported interfaces with no reciprocal acceptance gates;
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
the one-way sibling handoffs.
