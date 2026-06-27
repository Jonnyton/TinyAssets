"""Process evaluation over scene traces and search artifacts.

Grades how the scene loop behaved, not just what prose it produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tinyassets.evaluation import EvalResult


@dataclass
class ProcessCheck:
    """Result of one process-quality dimension."""

    name: str
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)
    observation: str = ""


@dataclass
class ProcessEvaluation:
    """Aggregated result across process-oriented checks."""

    checks: list[ProcessCheck]
    aggregate_score: float
    failing_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return {
            "aggregate_score": self.aggregate_score,
            "failing_checks": list(self.failing_checks),
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "score": check.score,
                    "details": check.details,
                    "observation": check.observation,
                }
                for check in self.checks
            ],
        }

    def to_eval_result(self) -> "EvalResult":
        """Convert to a unified EvalResult for protocol-compatible routing."""
        from tinyassets.evaluation import EvalResult

        score = max(-1.0, min(1.0, self.aggregate_score))
        verdict: str
        if self.failing_checks:
            verdict = "fail"
        else:
            verdict = "pass"
        return EvalResult(
            score=score,
            verdict=verdict,  # type: ignore[arg-type]
            kind="process",
            label="process_evaluation",
            details={
                "aggregate_score": self.aggregate_score,
                "failing_checks": list(self.failing_checks),
            },
        )


_CHECK_WEIGHTS: dict[str, float] = {
    "trace_handoff": 0.2,
    "tool_use": 0.2,
    "retrieval_choices": 0.2,
    "grounding_quality": 0.25,
    "stopping_behavior": 0.15,
}


def evaluate_scene_process(
    state: dict[str, Any],
    *,
    pending_trace: list[dict[str, Any]] | None = None,
    verdict: str | None = None,
    second_draft_used: bool | None = None,
    commit_result: dict[str, Any] | None = None,
) -> ProcessEvaluation:
    """Evaluate scene-loop process quality from traces and search artifacts."""
    trace = list(state.get("quality_trace", []))
    if pending_trace:
        trace.extend(pending_trace)

    verdict = verdict if verdict is not None else str(state.get("verdict", ""))
    if second_draft_used is None:
        second_draft_used = bool(state.get("second_draft_used", False))
    if commit_result is None:
        commit_result = state.get("commit_result", {}) or {}

    checks = [
        _check_trace_handoff(state, trace, verdict),
        _check_tool_use(trace),
        _check_retrieval_choices(trace),
        _check_grounding_quality(state, trace, commit_result),
        _check_stopping_behavior(verdict, second_draft_used, trace),
    ]

    weighted_total = 0.0
    weight_sum = 0.0
    failing_checks: list[str] = []
    for check in checks:
        weight = _CHECK_WEIGHTS.get(check.name, 1.0)
        weighted_total += check.score * weight
        weight_sum += weight
        if not check.passed:
            failing_checks.append(check.name)

    aggregate = weighted_total / weight_sum if weight_sum else 0.0
    return ProcessEvaluation(
        checks=checks,
        aggregate_score=aggregate,
        failing_checks=failing_checks,
    )


def _check_trace_handoff(
    state: dict[str, Any],
    trace: list[dict[str, Any]],
    verdict: str,
) -> ProcessCheck:
    node_entries = _latest_trace_entries(trace)
    orient_result = state.get("orient_result") or {}
    plan_output = state.get("plan_output") or {}
    draft_output = state.get("draft_output") or {}

    required = ["orient", "plan", "draft"]
    if verdict:
        required.append("commit")
    missing = [node for node in required if node not in node_entries]

    scene_ids = {
        scene_id
        for scene_id in (
            orient_result.get("scene_id"),
            plan_output.get("scene_id"),
            draft_output.get("scene_id"),
            *[
                entry.get("scene_id")
                for entry in node_entries.values()
                if entry.get("scene_id")
            ],
        )
        if scene_id
    }
    consistent_scene_id = len(scene_ids) <= 1

    beats_count = len(plan_output.get("beats", []) or [])
    word_count = int(draft_output.get("word_count", 0) or 0)

    score = 1.0
    if missing:
        score -= min(0.6, 0.2 * len(missing))
    if not consistent_scene_id:
        score -= 0.2
    if beats_count <= 0:
        score -= 0.1
    if word_count <= 0 and verdict != "revert":
        score -= 0.1
    score = max(score, 0.0)

    passed = not missing and consistent_scene_id and (beats_count > 0 or "plan" not in required)
    observation = ""
    if missing:
        observation = f"Missing trace handoff through: {', '.join(missing)}."
    elif not consistent_scene_id:
        observation = "Scene identity drifted across node handoffs."

    return ProcessCheck(
        name="trace_handoff",
        passed=passed,
        score=score,
        details={
            "missing_nodes": missing,
            "scene_ids": sorted(scene_ids),
            "beats_count": beats_count,
            "word_count": word_count,
        },
        observation=observation,
    )


def _check_tool_use(trace: list[dict[str, Any]]) -> ProcessCheck:
    node_entries = _latest_trace_entries(trace)
    plan_tools = list(node_entries.get("plan", {}).get("writer_tools", []) or [])
    draft_tools = list(node_entries.get("draft", {}).get("writer_tools", []) or [])

    phases_with_tools = sum(1 for tools in (plan_tools, draft_tools) if tools)
    story_search_used = int("story_search" in plan_tools) + int(
        "story_search" in draft_tools
    )

    score = 0.25 * phases_with_tools + 0.25 * story_search_used
    score = min(score, 1.0)
    passed = phases_with_tools == 2 and story_search_used == 2

    observation = ""
    if not passed:
        observation = "Writer tool usage did not cover both plan and draft phases."

    return ProcessCheck(
        name="tool_use",
        passed=passed,
        score=score,
        details={
            "plan_tools": plan_tools,
            "draft_tools": draft_tools,
        },
        observation=observation,
    )


def _check_retrieval_choices(trace: list[dict[str, Any]]) -> ProcessCheck:
    node_entries = _latest_trace_entries(trace)
    per_node: dict[str, dict[str, Any]] = {}
    covered = 0

    for node in ("orient", "plan", "draft"):
        entry = node_entries.get(node, {})
        sources = list(entry.get("search_sources", []) or [])
        token_count = int(entry.get("search_token_count", 0) or 0)
        fact_count = int(entry.get("search_fact_count", 0) or 0)
        covered_here = bool(sources or token_count or fact_count)
        if covered_here:
            covered += 1
        per_node[node] = {
            "sources": sources,
            "token_count": token_count,
            "fact_count": fact_count,
        }

    score = covered / 3 if per_node else 0.0
    passed = covered >= 2
    observation = ""
    if not passed:
        observation = "Search routing is under-specified across the scene loop."

    return ProcessCheck(
        name="retrieval_choices",
        passed=passed,
        score=score,
        details=per_node,
        observation=observation,
    )


def _check_grounding_quality(
    state: dict[str, Any],
    trace: list[dict[str, Any]],
    commit_result: dict[str, Any],
) -> ProcessCheck:
    search_context = state.get("search_context", {}) or {}
    retrieved_context = state.get("retrieved_context", {}) or {}
    orient_result = state.get("orient_result", {}) or {}

    facts = _first_non_empty(
        search_context.get("facts", []),
        retrieved_context.get("facts", []),
        retrieved_context.get("canon_facts", []),
    )
    passages = _first_non_empty(
        search_context.get("prose_chunks", []),
        retrieved_context.get("prose_chunks", []),
    )
    summaries = _first_non_empty(
        search_context.get("community_summaries", []),
        retrieved_context.get("community_summaries", []),
    )
    canon_context = orient_result.get("canon_context", "")

    evidence_count = len(facts) + len(passages) + len(summaries)
    if canon_context:
        evidence_count += 1

    canon_check = _find_structural_check(commit_result, "canon_breach")
    canon_score = float(canon_check.get("score", 1.0) or 0.0) if canon_check else 1.0
    canon_passed = bool(canon_check.get("passed", True)) if canon_check else True

    tool_use = _check_tool_use(trace)
    base_score = 0.5 if evidence_count > 0 else 0.1
    score = min(1.0, base_score + 0.25 * canon_score + 0.25 * tool_use.score)
    passed = evidence_count > 0 and canon_passed

    observation = ""
    if evidence_count <= 0:
        observation = "No grounding evidence was threaded into the writer loop."
    elif not canon_passed:
        observation = "Grounding inputs were present but canon alignment still slipped."

    return ProcessCheck(
        name="grounding_quality",
        passed=passed,
        score=score,
        details={
            "grounding_evidence_count": evidence_count,
            "canon_check_passed": canon_passed,
            "canon_check_score": canon_score,
        },
        observation=observation,
    )


def _check_stopping_behavior(
    verdict: str,
    second_draft_used: bool,
    trace: list[dict[str, Any]],
) -> ProcessCheck:
    node_entries = _latest_trace_entries(trace)
    draft_entry = node_entries.get("draft", {})
    draft_failed = draft_entry.get("action") == "draft_provider_exhausted"
    invalid_third_draft = second_draft_used and verdict == "second_draft"

    score = 1.0
    if invalid_third_draft:
        score = 0.0
    elif draft_failed and verdict != "revert":
        score = 0.2
    elif verdict == "second_draft":
        score = 0.9

    passed = not invalid_third_draft and (not draft_failed or verdict == "revert")
    observation = ""
    if invalid_third_draft:
        observation = "The workflow attempted to request a third draft."
    elif draft_failed and verdict != "revert":
        observation = "Provider failure did not terminate the scene cleanly."

    return ProcessCheck(
        name="stopping_behavior",
        passed=passed,
        score=score,
        details={
            "verdict": verdict,
            "second_draft_used": second_draft_used,
            "draft_failed": draft_failed,
        },
        observation=observation,
    )


def _latest_trace_entries(trace: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in trace:
        node = entry.get("node")
        if isinstance(node, str) and node:
            latest[node] = entry
    return latest


def _find_structural_check(
    commit_result: dict[str, Any],
    check_name: str,
) -> dict[str, Any]:
    for check in commit_result.get("structural_checks", []) or []:
        if isinstance(check, dict) and check.get("name") == check_name:
            return check
    return {}


def _first_non_empty(*values: list[Any]) -> list[Any]:
    for value in values:
        if value:
            return list(value)
    return []
