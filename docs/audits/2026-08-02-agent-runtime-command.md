# Custom-agent invocation command source foundation

Freshness: 2026-08-02, Windows local worktree based on `origin/main` at `61da7f21`; the exact reviewed head and final integration base are recorded in the PR.

## Outcome

The dark custom-agent runtime now has an immutable invocation-command record and a typed budget envelope shaped for the future atomic admission owner. The command pins its invocation identity, authenticated request/admission subject and canonical grant generation, universe and private binding revision, manifest execution subject, activation epoch/executor/lease, typed input, provider-work binding identity/generation/digest, scoped idempotency, request digest, typed budget, and admission witness.

The command intentionally does not contain a runtime-principal digest or grant-evidence-set digest. Those values would introduce a command/invocation/principal cycle and freeze grants that must remain live-checked. It links one way to `invocation_id`; the invocation root independently links back through command identity/generation/digest, so neither record hashes the other.

## Security boundary

This slice cannot admit or run work. `AgentRuntimeCommandStore` exposes no production `create`, `append`, `insert`, `issue`, `admit`, generic transaction, verifier injection, provider mutation, dispatch, spend, continuation, public, app, workflow, or effect path. It verifies canonical JSON, recomputed command and budget digests, and every projected SQLite column, then always returns `None`. A forged but internally self-consistent raw row is therefore inert.

`authorizing_grant_generation` has exactly one future meaning: the generation of the authenticated requester-owned admission grant consumed by the atomic admission transaction. It does not summarize live runtime grants. The future owner must revalidate the request grant, private binding, manifest source truth and live grants, activation fence, provider-work envelope, and sealed witness; prove the typed command budget is no wider than both the manifest and `ProviderWorkBinding`; and atomically create all three linked records or none. OpenSpec task 3.2 remains open.

## Evidence

- RED: `python -m pytest tests/test_agent_runtime_command.py -q` failed at collection because `tinyassets.agent_runtime_command` did not exist.
- Focused GREEN: `python -m pytest tests/test_agent_runtime_command.py -q` passed all 15 tests, including self-consistent-row inertness and projected/JSON/digest tamper refusal.
- Runtime/authority regression: 10 command, invocation, principal, grant, provider-work, activation, execution-subject, runtime, component-compiler, and plan-compiler modules passed all 173 tests in 4.40 seconds.
- Ruff format/check passed for canonical modules, packaged mirrors, and the focused test.
- `openspec validate activate-custom-agent-runtime-core --type change --strict --no-interactive` passed; the bounded-flow gate returned `ALLOWED` at global delivery WIP 4.
- Packaged isolated imports passed, and `python scripts/invariants_run.py --check mirror-parity` matched all 313 canonical files.

## Explicit remaining work

There is still no atomic admission writer, positive command or invocation resolver, provider reservation/claim/launch integration, continuation/resume composition, Slack/app conversation route, workflow action, or spend-capable customer path. This artifact is only a collision-free integrity boundary for that future integration.
