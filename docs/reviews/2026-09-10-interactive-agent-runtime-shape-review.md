# Interactive HTTP agent integration shape review

September10,2026; local unmerged feature a56893124bf4398d3ea72789f08c3042dd58e125.
Independent Claude review via scripts/peer_agent.py, session53896,294s, exit0.
Read-only; no suite or subprocesses. Verdict ADAPT, not implementation approval.

The known stop hook replaced the final capture with a recap. Recovered the full
original review from the exact dispatch transcript31973037-192a-4f5d-9418-d99ca380fc66
in the select-agent-models Claude project; no unrelated conversations inspected.
This is a faithful findings/disposition record, not a new independent review.

## Required adaptations

1. AGREE runner above router, one call per inference. DISAGREE_EVIDENCE observer
   timing: provider_assignment.py ServedProviderAuthority.before_provider_launch
   runs at router.py986-990 before capability consumption996-999. Add internal
   reservation/authority observer AFTER consumption and BEFORE provider.complete;
   preserve the earlier selection recheck. Unlaunched failures release reservation.
2. Seal launch allowance at first served_provider_authority assignment resolution,
   before any router launch. auth/middleware.py322-352 helper has no callers;
   legacy two-call limit cannot serve an agent loop. Sum distinct accepted binding
   max_invocations, overflow-checked. These remain rolling budgets, not new credit.
   Seal refusal must raise; never silently retain the fixed two-call allowance.
3. Explicit begin_round(after_failed_inference=True) accepts only held_transport
   with failed last inference, no reply or tools. Current begin only accepts ready;
   current _read rejects older failed rounds. Extend both while preserving all
   other state conflicts and immutable failure evidence.
4. Hoist preference _check_home to shared storage; journal create/_mutation call
   under BEGIN IMMEDIATE, querying founder_home and deleted_principals in the same
   canonical database. Add nonexecuting abandon only for ready roots with zero
   rounds; abandoned roots must not block scoped reset.
5. Size both reservation and missing-usage settlement from full encoded values.
   router.py955-962 currently sees only original prompt/system;1079 passes resp.text
   to provider_assignment.py695-698 fallback sizing. Tool requests can have empty
   text, so tool-call JSON and history must count. No network for sizing.
6. Runner stays in _call_writer's _attempt on capability-claiming thread; middleware
   capability lookup is thread-bound. Only the existing HTTP wire worker moves
   threads. All-skipped retry reuses the same zero-round journal root; otherwise
   use the explicit failed-inference path, never whole-turn tool replay.
7. Extend OpenRouter constrained body validation only for exact safe codec tool
   shape; retain max_price/require_parameters and no plugins/overrides/models-array.
   Reject selected agent model without discovered tools support before wire send.

Portable history shape AGREE: validate captured historical inventories; project
standard messages on source/model switch, dropping foreign reasoning. HTTP adapter
engine_mcp_enabled refusal is the real seam to replace; engine_tool_client already
revalidates route and records unknown outcomes rather than retrying.

## Non-gating observations

An orphaned inference_started row can block reset; later genuine-owner recovery
may fail it without tool replay, but no automatic crash resurrection is required.
Immutable agent request fits beside selected_model. Later hardening includes
journal growth/pruning, more cross-owner cases and in-process registry concurrency.
These are not reasons to add another proposal layer before building the MVP.

## Disposition

All seven requirements incorporated in interactive-agent-runtime.md. Portable
history plus guarded explicit journal retry/unused abandon are being implemented;
actual runner, observer/sealing, full accounting, wire validator and eligible
selection remain required. No deployment, live activation or completion claim.
