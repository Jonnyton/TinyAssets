# Custom-agent runtime principal foundation

Freshness: 2026-08-02 UTC, Windows local worktree, exact-restacked on `origin/main` base `ad001d99` after prerequisite PR #2082 landed.

## Outcome

The dark custom-agent runtime now has a server-composed `AgentRuntimePrincipal` boundary. It derives one immutable, non-bearer identity from:

- the exact validated runtime manifest and owner/binding revision;
- the reserved current agent activation, typed manifest subject, epoch, executor, and lease;
- an authoritative current invocation identity returned by a server-owned source; and
- a fresh exhaustive resolution of every requested capability, resource, and provider-policy grant.

Component or binding configuration may claim an actor such as `maintainer`, but that value is never consulted. The principal contains no bearer, credential, environment, host, maintainer, market, graph, workflow, app, or effect authority.

## Fail-closed composition

`AgentRuntimePrincipalDeriver` is installed by the trusted composition root; callers supply only an immutable manifest and invocation ID. It reads the current activation and invocation owners itself, rejects untyped or mismatched evidence, resolves grants live, then re-reads the invocation and revalidates the exact activation claim after grant resolution. Deterministic race tests prove an invocation revocation or activation epoch/lease change during derivation blocks the result.

The returned principal is a diagnostic authority snapshot, not a transferable capability. Every privileged successor must use its trusted deriver again immediately before its transition. Constructing a dataclass, knowing a digest, holding queue work, or persisting an actor label grants nothing.

Typed safe blockers distinguish missing/current-state, identity, fence, source, manifest, and grant failures without copying backend exceptions or secret values. Grant blockers retain only the existing non-secret reference identity and generation contract.

## Evidence

- RED: nine focused tests failed because the principal module did not exist.
- RED: an activation rebound during grant resolution incorrectly returned a principal before the final activation recheck was added.
- RED: an invocation revoked during grant resolution incorrectly returned a principal before the final invocation re-read was added.
- GREEN: `python -m pytest tests/test_agent_runtime_principal.py -q` — 11 passed.
- Exact-restack regression: 331 agent-runtime, compiler, activation, execution-subject, continuation, provider-authority, queue, and admission tests passed in 31.50 seconds.
- Ruff lint and `py_compile` passed.
- Both affected OpenSpec changes passed strict validation.
- Canonical/plugin mirror parity passed, and the packaged principal imported in a fresh process.

## Explicit remaining work

This is a partial foundation for `activate-custom-agent-runtime-core` task 3.1; its checkbox stays open. The canonical `AgentInvocation` store/admission owner does not exist yet, so this slice defines its narrow read protocol but does not mint invocation evidence. It also does not activate agents, reserve provider work, launch models, resume continuations, expose public controls, connect Slack/apps, run workflows, mutate graphs, or perform effects.

PR #2082 supplied the required typed `ExecutionSubject` and reserved activation-key prerequisite and is now landed. The runtime-principal implementation was cherry-picked alone onto current `main`; its stable patch ID matches reviewed commit `d5ca5e3b`, and PR #2114 must expose only the four files named in this audit.
