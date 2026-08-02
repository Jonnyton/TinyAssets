# Custom-agent invocation authority source foundation

Freshness: 2026-08-02, Windows local worktree, based on `origin/main` at `1e6d4bb4` before the final exact-head review.

## Outcome

The dark custom-agent runtime now has a concrete SQLite-backed `AgentInvocationAuthoritySource` for `AgentRuntimePrincipalDeriver`. It reads one immutable invocation root and an append-only lifecycle restricted to `ADMITTED -> INVALIDATED`, verifies canonical JSON, recomputed record digests, projected columns, exact generations, and the event hash chain, and re-reads after admission-witness verification to fence concurrent invalidation.

The root pins the authorizing subject and grant generation, universe and private binding revision, manifest execution subject, activation epoch/executor/lease, typed input, command identity/generation/digest, canonical provider-work binding identity/generation/digest, idempotency/request/budget digests, and admission-witness identity/digest. It contains no bearer, credential, conversation, provider output, graph mutation, app payload, or external-effect payload.

## Security boundary

This slice cannot admit work. `AgentRuntimeInvocationStore` exposes no production `create`, `append`, `insert`, `issue`, `admit`, or generic transaction method. A self-consistent raw row or self-hash is non-authoritative: `resolve_current()` returns `None` unless a trusted composition root supplies a canonical witness verifier that confirms the linked command and provider-work binding are still current. No production verifier or writer ships here.

The future admission owner must add the only writer inside the same `BEGIN IMMEDIATE` transaction that consumes the live authenticated provider-work draft and creates the canonical `ProviderWorkBinding`, server-authored command, and admitted invocation root. It must prove exact replay, changed-input conflict, concurrent single winner, and zero rows on rollback. This lane does not touch the active cloud owner's provider-work, continuation, dispatcher, queue, or provider files.

Independent pre-implementation architecture/security review approved only this inert read-only shape and required that raw rows never become authority, invalidation never resurrect, and the OpenSpec admission task remain incomplete.

## Evidence

- RED: `python -m pytest tests/test_agent_runtime_invocation.py -q` failed at collection because the invocation modules did not exist.
- GREEN: `python -m pytest tests/test_agent_runtime_invocation.py tests/test_agent_runtime_principal.py tests/test_agent_runtime_grants.py -q` — 36 passed in 0.83 seconds, including invalidation during witness verification.
- Runtime/authority regression: the 10 focused runtime, compiler, activation, subject, continuation, and provider-work test modules — 204 passed in 11.07 seconds.
- `python -m ruff check` passed for the new canonical modules and test.
- `python scripts/invariants_run.py --check mirror-parity` — all 311 canonical files matched their packaged plugin mirrors.

## Explicit remaining work

OpenSpec tasks 3.1 and 3.2 remain open. There is still no canonical `AgentInvocationCommand`, no atomic three-record admission writer, no provider reservation or execution call site, no continuation/resume composition, and no spend-capable or public/app/workflow path. The next implementation must wait for an exact handoff from the active provider/cloud owner and then use this read contract without adding a standalone invocation mint path.
