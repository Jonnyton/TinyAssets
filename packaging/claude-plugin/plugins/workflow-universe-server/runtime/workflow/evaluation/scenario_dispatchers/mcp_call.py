"""mcp_call dispatcher — Slice 3 of the AcceptanceScenario lane.

Concrete dispatcher for `target_surface="mcp_call"`: invokes a single
MCP action handler with declared kwargs, parses the JSON response, runs
evaluator callables against the parsed response, returns aggregated
score + verdict.

This is the SIMPLEST realistic dispatcher and the natural first slice
per the Slice 1 design's recommendation:

> Slice 3: one concrete scenario shipped end-to-end. Recommendation: a
> small MCP scenario for an existing `goals` action (e.g., `goals
> action=propose` correctly creates a Goal record + binds the chatbot's
> request). Smallest possible real test of the full contract.

Slice 4+ scope: dispatchers for ui_test_mission (compose with existing
user-sim discipline), branch_run (compose with workflow.api.runs),
external_effect (compose with the #914 external-write authority design),
session_trace_summary (review-against-summary check).

Cost-budget enforcement is intentionally minimal here: the dispatcher
records `wall_time_seconds` actually elapsed in the response and lets
the scenario's evaluators inspect it. Hard kills on long-running calls
are a Slice 4+ refinement that needs a process-isolation primitive.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from workflow.evaluation.scenario_runner import AcceptanceScenario

# Evaluator signature: (parsed_response) -> {"score": float, "label": str, "details": dict}
EvaluatorCallable = Callable[[dict], dict]


def mcp_call_dispatcher(
    scenario: AcceptanceScenario,
    candidate_ref: str,
    *,
    action_handler: Callable[[dict], str] | None = None,
    invocation_kwargs: dict[str, Any] | None = None,
    evaluators: list[EvaluatorCallable] | None = None,
    **_extra: Any,
) -> dict[str, Any]:
    """Invoke an MCP action handler and evaluate its response.

    Args:
        scenario: the AcceptanceScenario being run (validated by runner).
        candidate_ref: identifier of what is being tested (e.g., "goals.propose").
        action_handler: callable matching the MCP-action contract
            (`(kwargs: dict) -> json_str`). For platform-side action
            handlers, this is the function from `workflow/api/market.py`
            or equivalent. Required.
        invocation_kwargs: kwargs the dispatcher passes to action_handler.
            Required for non-trivial cases.
        evaluators: ordered list of evaluator callables to run against
            the parsed response. Each evaluator returns
            `{"score": float, "label": str, "details": dict}`.
            Defaults to a single status-check evaluator if omitted.

    Returns:
        A dict matching the scenario_runner's expected dispatcher return
        shape: `{"score": float, "verdict": str, "label": str, "details": dict}`.
        The runner wraps this into a standard EvalResult.
    """
    if scenario.target_surface != "mcp_call":
        raise ValueError(
            f"mcp_call_dispatcher invoked for unsupported target_surface "
            f"{scenario.target_surface!r}"
        )
    if action_handler is None:
        raise ValueError(
            "mcp_call_dispatcher requires `action_handler=` kwarg "
            "(the MCP action callable to invoke)"
        )
    invocation_kwargs = dict(invocation_kwargs or {})

    start = time.monotonic()
    raw_response_text: str
    parse_error: str | None = None
    parsed: dict[str, Any] = {}
    handler_exception: str | None = None

    try:
        raw_response_text = action_handler(invocation_kwargs)
    except Exception as exc:  # noqa: BLE001 — surface for evaluator review
        handler_exception = f"{type(exc).__name__}: {exc}"
        raw_response_text = ""

    wall_time_seconds = max(0.0, time.monotonic() - start)

    if not handler_exception:
        try:
            parsed = json.loads(raw_response_text) if raw_response_text else {}
        except json.JSONDecodeError as exc:
            parse_error = f"json decode failed: {exc}"

    evaluator_results: list[dict[str, Any]] = []

    if evaluators is None:
        # Default evaluator: response must have non-error status.
        evaluators = [_default_status_check_evaluator]

    for evaluator in evaluators:
        try:
            result = evaluator(parsed)
            if not isinstance(result, dict):
                raise TypeError(
                    f"evaluator {evaluator!r} must return a dict; got "
                    f"{type(result).__name__}"
                )
            score = float(result.get("score", 0.0))
            label = str(result.get("label", evaluator.__name__))
            details = dict(result.get("details", {}))
            evaluator_results.append({
                "score": max(-1.0, min(1.0, score)),
                "label": label,
                "details": details,
            })
        except Exception as exc:  # noqa: BLE001
            evaluator_results.append({
                "score": 0.0,
                "label": getattr(evaluator, "__name__", "anonymous_evaluator"),
                "details": {
                    "evaluator_exception": f"{type(exc).__name__}: {exc}",
                },
            })

    # Aggregate scores per the scenario's pass_threshold.
    score_aggregation = scenario.pass_threshold.get("score_aggregation", "mean")
    scores = [r["score"] for r in evaluator_results]
    final_score = _aggregate_scores(scores, score_aggregation, scenario.pass_threshold)

    details_out: dict[str, Any] = {
        "candidate_ref": candidate_ref,
        "invocation_kwargs": invocation_kwargs,
        "raw_response_text": raw_response_text,
        "parsed_response": parsed,
        "wall_time_seconds": wall_time_seconds,
        "evaluator_results": evaluator_results,
        "score_aggregation": score_aggregation,
    }
    if handler_exception:
        details_out["handler_exception"] = handler_exception
        final_score = -1.0
    if parse_error:
        details_out["parse_error"] = parse_error
        final_score = min(final_score, 0.0)

    # Cost-budget reporting (enforcement comes in Slice 4+).
    cost_budget = scenario.cost_budget
    over_budget_wall_time = wall_time_seconds > cost_budget.get(
        "max_wall_time_seconds", float("inf")
    )
    if over_budget_wall_time:
        details_out["over_budget"] = {
            "wall_time_seconds": wall_time_seconds,
            "max_wall_time_seconds": cost_budget.get("max_wall_time_seconds"),
        }

    return {
        "score": final_score,
        "details": details_out,
        "label": f"mcp_call:{candidate_ref}",
    }


def _default_status_check_evaluator(parsed: dict[str, Any]) -> dict[str, Any]:
    """Default evaluator when scenario does not supply its own.

    Passes when the parsed response carries a non-error status. Useful
    for trivial happy-path scenarios; real scenarios should supply their
    own evaluator list.
    """
    status = parsed.get("status", "")
    is_error = "error" in parsed or status in {"rejected", "error", "failed"}
    return {
        "score": 0.0 if is_error else 1.0,
        "label": "default_status_check",
        "details": {
            "status": status,
            "is_error": is_error,
        },
    }


def _aggregate_scores(
    scores: list[float],
    aggregation: str,
    pass_threshold: dict[str, Any],
) -> float:
    """Aggregate per-evaluator scores into a single scenario score."""
    if not scores:
        return 0.0
    if aggregation == "min":
        return min(scores)
    if aggregation == "weighted":
        weights = pass_threshold.get("weights") or {}
        # Slice 3 simplification: ignore label-keyed weights; fallback to
        # uniform mean. Slice 4 can layer in proper weighted aggregation
        # once evaluator IDs are stable.
        return sum(scores) / len(scores)
    # mean (default)
    return sum(scores) / len(scores)


def register() -> None:
    """Register this dispatcher with the scenario_runner registry.

    Universes call this at startup if they want mcp_call scenarios to be
    runnable. Tests call it explicitly per case (the fixture clears the
    registry between tests).
    """
    from workflow.evaluation.scenario_runner import register_dispatcher
    register_dispatcher("mcp_call", mcp_call_dispatcher)


__all__ = [
    "EvaluatorCallable",
    "mcp_call_dispatcher",
    "register",
]
