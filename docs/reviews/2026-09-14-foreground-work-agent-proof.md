# Foreground work-owned agent integration

September 14, 2026, feature tree based on 51cb83b1. Implements the foreground
portion of reviewed R3/R4/R5/R6 in `remaining-model-execution.md`; not deployed
or final-release reviewed. No private workflow was edited.

The existing immutable `universe_self` opt-in now enters the shared coordinator
with a work-owned adapter. Chat still creates chat roots through its separate
adapter. Each work inference gets a fresh reservation under the original receipt
and claim; its actual selected member and encoded input are journaled before
dispatch. Engine tool identity comes from the work receipt, not caller config.
Current run, subject, owner, receipt/claim, cancellation, member and custody are
checked between steps. Supplied chat requests, carriers, model plans or model
selections are rejected before foreground admission.

HTTP tools are authorized from the immutable opt-in and freshly checked model
capability. A known tool result is stored before the next inference. Unknown
inference/tool outcomes, cancellation, revocation, or later capacity exhaustion
cannot cause the compiler to replay a dispatched action. Native execution uses
the same work journal; exact execution-bound capacity evidence is retained, and
missing evidence holds without whole-node replay. These are synthetic native
executor tests, not a claim of new real-account CLI proof.

Real integration exposed two previously invisible boundaries:

- Model selection's `supports_tools` reflects the admitted requirement, so the
  immutable opt-in must reach snapshot validation before arming the reservation.
- A one-node token share originally reserved the full aggregate again after the
  first round spent seven tokens. Later agent reservations now clip to the
  remaining aggregate, then reapply model affordability. The extracted charge
  function is differential-tested against the exact old admission expression.

Unused reservations are settled with zero usage when adapter/turn construction,
engine discovery, or the pre-dispatch observer fails. Known-unsent observer
failures can still use the compiler's existing safe retry slots; every attempt
releases its allowance. Three admitted ongoing tool rounds hit an existing
three-invocation ceiling without enlarging it, creating another receipt, or
replaying completed tools.

## Verification

September 14 around 18:55–18:59 UTC, local Windows and actual Linux container:

```
python -m pytest -q tests/test_workflow_http_agent.py tests/test_work_agent_authority.py tests/test_work_agent_allowance.py tests/test_run_provider_session.py tests/test_work_model_selection.py tests/test_agent_workflow_fences.py tests/test_provider_work_authority.py tests/test_agent_turn_coordinator.py tests/test_interactive_http_agent.py tests/test_mixed_agent_execution.py --tb=short --show-capture=no --disable-warnings -rs
```

- Windows: 292 passed, zero skips, 70.09s.
- Linux: 292 passed, zero skips, 58.83s; WSL invoked
  `python3 scripts/linux_oracle.py --` with the same test arguments and explicit
  linked-worktree Git paths. Python 3.11.16, git 2.47.3, bubblewrap 0.12.0.
- Windows supplementary group: 94 passed, zero skips, 19.19s:
  `python -m pytest -q tests/test_channel_agnostic_ratchet.py tests/test_agent_work_journal.py tests/test_background_budget_finalization_e2e.py tests/test_provider_router_diagnostics.py tests/test_mirror_parity_gate.py --tb=short --show-capture=no --disable-warnings -rs`.
- Ruff on all edited runtime/test files, `openspec validate select-agent-models
  --strict`, `git diff --check`, and the 441-file plugin mirror/import probe pass.

The end-to-end tests use real compiler, admission, SQLite journal, router and
engine-client wiring, with synthetic remote model/MCP transports and persona
preparation. They prove the platform composition, not live user acceptance.
An initial supplementary command named nonexistent `test_provider_router.py`
and ran no tests; it was corrected to the existing diagnostics suite above.

Remaining: background work adapter and exact task/activation/consumer-lease
checks; work-owned safe capacity traversal retaining completed history; integrated
selector/native-account proof; the reserved final Fable release review, fresh CI,
protected deployed-SHA/canary and rendered app acceptance. The current adapter
pins its resolved model for later rounds; it does not yet claim within-turn
workflow fallback completion. Ordinary prompts and chat-only fences remain.
