# Custom-agent invocation authority source foundation

Freshness: 2026-08-02, Windows local worktree, based on `origin/main` at `1e6d4bb4` before the final exact-head review.

## Outcome

The dark custom-agent runtime now has an inert SQLite-backed invocation record source shaped for the future `AgentInvocationAuthoritySource` used by `AgentRuntimePrincipalDeriver`. It reads one immutable invocation root and an append-only lifecycle restricted to `ADMITTED -> INVALIDATED`, and verifies canonical JSON, recomputed record digests, projected columns, exact generations, and the event hash chain.

The root pins the authorizing subject and grant generation, universe and private binding revision, manifest execution subject, activation epoch/executor/lease, typed input, command identity/generation/digest, canonical provider-work binding identity/generation/digest, idempotency/request/budget digests, and admission-witness identity/digest. It contains no bearer, credential, conversation, provider output, graph mutation, app payload, or external-effect payload.

## Security boundary

This slice cannot admit work. `AgentRuntimeInvocationStore` exposes no production `create`, `append`, `insert`, `issue`, `admit`, generic transaction, or injected-verifier method. A self-consistent raw row or self-hash is non-authoritative: after full structural validation, `resolve_current()` always returns `None`. No production verifier or writer ships here.

The future admission owner must add the only writer inside the same `BEGIN IMMEDIATE` transaction that consumes the live authenticated provider-work draft and creates the canonical `ProviderWorkBinding`, server-authored command, and admitted invocation root. Positive resolution must use a sealed, non-serializable capability or concrete canonical verifier that returns detached typed command/provider-binding witness evidence, compare every linked identity/generation/digest with the root, and revalidate that witness after the final invocation read. It must prove exact replay, changed-input conflict, concurrent single winner, witness-revocation races, and zero rows on rollback. This lane does not touch the active cloud owner's provider-work, continuation, dispatcher, queue, or provider files.

Independent exact-head review rejected the first callback-based witness design because an arbitrary `True` verifier plus self-consistent rows could mint evidence and because command/provider witness revocation was not rechecked. The callback and every positive resolution path were removed; raw rows now never become authority, invalidation never resurrects, and the OpenSpec admission task remains incomplete.

## Evidence

- RED: `python -m pytest tests/test_agent_runtime_invocation.py -q` failed at collection because the invocation modules did not exist.
- Post-review GREEN: `python -m pytest tests/test_agent_runtime_invocation.py tests/test_agent_runtime_principal.py tests/test_agent_runtime_grants.py -q` — 34 passed in 1.06 seconds; arbitrary positive-verifier injection is rejected.
- Post-review runtime/authority regression: the 10 focused runtime, compiler, activation, subject, continuation, and provider-work test modules — 202 passed in 13.50 seconds.
- `python -m ruff check` passed for the new canonical modules and test.
- `python scripts/invariants_run.py --check mirror-parity` — all 311 canonical files matched their packaged plugin mirrors.

## Explicit remaining work

OpenSpec tasks 3.1 and 3.2 remain open. There is still no canonical `AgentInvocationCommand`, no atomic three-record admission writer, no provider reservation or execution call site, no continuation/resume composition, and no spend-capable or public/app/workflow path. The next implementation must wait for an exact handoff from the active provider/cloud owner and then use this read contract without adding a standalone invocation mint path.
