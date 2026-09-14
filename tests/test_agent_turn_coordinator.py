"""Differential real-store chat proof; remote provider/tool wires are synthetic."""

from contextlib import contextmanager
from dataclasses import asdict

import pytest

from tests import _legacy_agent_turn_oracle as legacy
from tests import test_interactive_http_agent as integration
from tinyassets import interactive_http_agent
from tinyassets.storage.agent_turn_journal import AgentTurnJournal


def _exercise(path, implementation, scenario):
    path.mkdir()
    with pytest.MonkeyPatch.context() as patch:
        rig = integration.rig.__wrapped__(path, patch)
        reader = integration.reader.__wrapped__(rig, patch)
        with contextmanager(integration.served.__wrapped__)(rig, reader, patch) as served:
            agent = integration.agent.__wrapped__(served, patch)
            patch.setattr(interactive_http_agent, "InteractiveHttpAgentTurn", implementation)
            if scenario == "many_rounds":
                agent.requested_rounds = 3
            elif scenario == "unknown_tool":
                agent.fail_tool = True
            elif scenario == "unknown_inference":
                agent.unknown_inference = True
            elif scenario in {"model_capacity", "account_capacity"}:
                integration._with_fallback(agent, patch)
                agent.capacity_failures[2] = 503 if scenario == "model_capacity" else 429
            elif scenario == "revoked_before_tool":
                agent.before_reply = lambda: rig.ledger.revoke_grant("grant-models")
            elif scenario in {"intent_failure", "result_failure"}:
                def refuse(*args, **kwargs):
                    raise RuntimeError("synthetic persistence failure")

                patch.setattr(AgentTurnJournal, "begin_round" if scenario == "intent_failure"
                              else "finish_tool", refuse)
            elif scenario == "cancelled_tool":
                import asyncio

                async def cancelled(*args, **kwargs):
                    raise asyncio.CancelledError

                patch.setattr(integration.engine_tool_client.EngineToolSession, "call", cancelled)
            answer, error = None, None
            try:
                answer = integration.run(agent)
            except BaseException as exc:
                error = type(exc).__name__
            turn = agent.latest()
            rounds = []
            for item in turn.rounds:
                candidate = asdict(item.candidate)
                # Each isolated run mints fresh authority IDs. Compare actual
                # inference input, lineage version, results and spend, not UUIDs.
                for field in ("binding_id", "reservation_id", "binding_digest"):
                    assert candidate.pop(field)
                rounds.append((item.state, candidate, item.reply, item.tools))
            with agent.journal._ledger.connection() as conn:
                spend = [tuple(row) for row in conn.execute(
                    "SELECT state, actual_total_tokens, actual_cost_microunits "
                    "FROM served_provider_budget_reservations ORDER BY rowid"
                )]
            return {
                "answer": answer, "error": error, "state": turn.state,
                "generation": turn.generation, "rounds": rounds,
                "wires": agent.wires, "tools": agent.tools, "spend": spend,
                "closed": agent.closed,
            }


@pytest.mark.parametrize("scenario", [
    "complete", "many_rounds", "unknown_tool", "unknown_inference", "model_capacity",
    "account_capacity", "revoked_before_tool", "intent_failure", "result_failure",
    "cancelled_tool",
])
def test_shared_coordinator_preserves_legacy_chat_progress(tmp_path, scenario):
    current = interactive_http_agent.InteractiveHttpAgentTurn
    expected = _exercise(tmp_path / "legacy", legacy.InteractiveHttpAgentTurn, scenario)
    actual = _exercise(tmp_path / "shared", current, scenario)
    assert actual == expected
    assert expected["wires"] or scenario == "intent_failure"


def test_shared_progress_has_no_served_request_authority_import():
    import ast
    import inspect

    from tinyassets import agent_turn_coordinator

    tree = ast.parse(inspect.getsource(agent_turn_coordinator))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "tinyassets.provider_assignment" not in imports
    assert "tinyassets.foreground_run_provider" not in imports
    assert "tinyassets.background_served_provider" not in imports
