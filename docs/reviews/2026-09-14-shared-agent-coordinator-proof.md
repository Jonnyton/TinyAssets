# Shared agent coordinator — September14 2026

Feature codex/select-agent-models, based on00c6a456. Implements the approved
Fable shape's shared progress/separate authority boundary. Final release review
remains unused. This checkpoint is not workflow tool enablement or deployment.

AgentTurnCoordinator owns existing history, journal transitions, tool results,
capacity traversal and uncertainty holds. ServedChatAgentAdapter retains the
current served request, writer/converse dispatch, engine identity and exact
version1 round provenance. The original entry point remains compatible. The
shared loop imports neither chat authorization nor foreground/background work
authorization. All four existing workflow/chat refusals remain pinned unchanged.

Ten differential scenarios compare against the executable original from
00c6a456 in tests/_legacy_agent_turn_oracle.py. They use independent real SQLite
authority, router and journal fixtures with synthetic remote wires: completion,
multiple rounds, uncertain tool/inference, model/account capacity, revocation,
intent/result persistence failures and cancellation. Comparison includes exact
provider requests/tool results, state/generation, input evidence and settlement;
fresh binding/reservation IDs are checked present but excluded from equality.

An additional mixed-native test exposed an extra adapter identity check changing
the typed refusal on revoked HTTP fallback. Corrected by retaining the existing
router admission point; no authority check was removed from the original path.

Windows Python3.14: **156 passed,3 skipped,44.44s**, verified17:58UTC September14.
Command: `python -m pytest -q tests/test_agent_turn_coordinator.py tests/test_interactive_http_agent.py tests/test_agent_workflow_fences.py tests/test_provider_served_router.py tests/test_run_provider_session.py tests/test_native_discovery_integration.py tests/test_channel_agnostic_ratchet.py tests/test_mixed_agent_execution.py tests/test_native_agent_input.py --tb=short --show-capture=no --disable-warnings -rs`.
Skips: POSIX shared readers, bubblewrap and optional real connected-account
inference. No real account or rendered deployment proof is inferred.
Ruff, diff and strict OpenSpec pass. Plugin mirror/import passes440files.
Linux verification is still in progress; no result claimed yet.

Prior pushed00c6a456 required CI34816559310/job103888332425 completed successfully:
17686passed,9failed,2errors,54skipped,10deselected; **zero new failures** against
the unchanged baseline. Desktop34816559315 passed, including exact installer
103889963191 in46s (07:16:28–07:17:14UTC). Verified via gh run view. Scope guard
still requires final exact-head review; the PR remains draft. These results do
not cover this newer local refactor or resolve installer intermittency.

Still required: workflow authority adapter, versioned work journal lineage,
finite per-work round allowance, uncertainty-aware node retry, actual native
account proof, final approved review, CI, deployment and ordinary app acceptance.
No private workflow or user configuration was edited.
