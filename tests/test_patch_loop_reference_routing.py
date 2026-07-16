"""Codex S1 round-6 Finding 1 (CRITICAL): the reference patch loop's
conditional routing must be SAFE — a ``red`` verify verdict can NEVER reach
``present`` (open the PR), and a ``reject`` owner decision can NEVER reach
``merge``. Before the fix the ``verify`` / ``owner_gate`` nodes declared no
output_keys, so ``_build_conditional_router`` fell back to the FIRST condition
label (green→present, approve→merge) regardless of the node's actual output —
a rejected patch would merge.

This is a compiled-graph proof: it builds the REAL artifact spec through the
ordinary ``_staged_branch_from_spec`` -> ``compile_branch`` -> ``graph.invoke``
path with fake providers, and asserts on the observed node-visit order (via the
event sink) — the only way to prove the safety semantics rather than the
serialized shape.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from tinyassets.api.branches import _staged_branch_from_spec
from tinyassets.branch_designs import load_design_artifacts
from tinyassets.graph_compiler import compile_branch

# The seven binding fields a remix would bind; seeded so every node's template
# renders (the reference nodes declare no input_keys, so the full state is the
# render view — a referenced-but-unseeded key would raise at compile-run time).
_SEED_STATE: dict[str, str] = {
    "intake_source": "queue://requests",
    "request_payload": "user reports the export button is broken",
    "target_repo": "example/project",
    "credential_ref": "vault://example/gh",
    "merge_policy": "manual",
    "verify_command": "pytest -q",
    "reshape_notes": "",
}


def _reference_branch():
    artifact = next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )
    branch, errors = _staged_branch_from_spec(artifact["spec"])
    assert errors == [], errors
    return branch


def _make_provider(
    verify_verdicts: list[str], gate_decision: str,
) -> Callable[..., str]:
    """Fake provider: emits a scripted JSON verdict for ``verify`` (advancing
    through ``verify_verdicts`` per call so a red→green retry can terminate),
    a scripted JSON decision for ``owner_gate``, and a stable leaf string for
    every other node. Markers are the unique node prompt-body phrases."""
    call_state = {"verify_i": 0}

    def _call(prompt: str, system: str = "", *, role: str = "writer") -> str:
        if "Run the project's verification" in prompt:
            i = call_state["verify_i"]
            call_state["verify_i"] += 1
            verdict = verify_verdicts[min(i, len(verify_verdicts) - 1)]
            return json.dumps({"verdict": verdict, "verify_output": f"verify:{verdict}"})
        if "Apply the owner's merge_policy" in prompt:
            return json.dumps({
                "decision": gate_decision,
                "reshape_notes": "please fix X" if gate_decision == "reshape" else "",
                "owner_gate_output": f"gate:{gate_decision}",
            })
        return "step ran"
    return _call


def _run(verify_verdicts: list[str], gate_decision: str) -> tuple[list[str], dict[str, Any]]:
    """Compile + invoke the reference branch; return (visited_node_order, final_state)."""
    visited: list[str] = []

    def _sink(**kw: Any) -> None:
        if kw.get("phase") == "ran":
            visited.append(kw.get("node_id"))

    compiled = compile_branch(
        _reference_branch(),
        provider_call=_make_provider(verify_verdicts, gate_decision),
        event_sink=_sink,
    )
    app = compiled.graph.compile()
    result = app.invoke(dict(_SEED_STATE), config={"recursion_limit": 50})
    return visited, dict(result)


# ── Safety semantics ────────────────────────────────────────────────────────


def test_happy_path_green_reaches_present_then_approve_reaches_merge():
    # green verdict -> present; approve decision -> merge. The full loop closes.
    visited, result = _run(verify_verdicts=["green"], gate_decision="approve")

    assert "present" in visited, visited
    assert "merge" in visited, visited
    assert visited.index("present") < visited.index("merge")
    assert result.get("merge_output"), result


def test_red_verify_routes_to_draft_patch_and_never_present():
    # First verify returns red -> MUST route back to draft_patch, NOT present.
    # Second verify returns green so the run terminates (reject ends it cleanly).
    visited, result = _run(verify_verdicts=["red", "green"], gate_decision="reject")

    first_verify = visited.index("verify")
    # The node immediately after the red verify is draft_patch, never present.
    assert visited[first_verify + 1] == "draft_patch", visited
    # present is not reached at or before the red verdict.
    assert "present" not in visited[: first_verify + 1], visited
    # The red verdict caused a second draft_patch attempt.
    assert visited.count("draft_patch") >= 2, visited


def test_reject_owner_gate_routes_to_end_and_never_merge():
    # green gets us to present; reject at the owner gate -> END, never merge.
    visited, result = _run(verify_verdicts=["green"], gate_decision="reject")

    assert "present" in visited, visited
    assert "owner_gate" in visited, visited
    assert "merge" not in visited, visited
    assert not result.get("merge_output"), result


def test_reshape_owner_gate_routes_back_to_draft_and_never_merge():
    # reshape must loop back to draft_patch (not merge). One reshape, then a
    # reject terminates so the graph doesn't spin forever in the test.
    visited: list[str] = []
    call_state = {"verify_i": 0, "gate_i": 0}
    gate_decisions = ["reshape", "reject"]

    def _call(prompt: str, system: str = "", *, role: str = "writer") -> str:
        if "Run the project's verification" in prompt:
            return json.dumps({"verdict": "green", "verify_output": "verify:green"})
        if "Apply the owner's merge_policy" in prompt:
            i = call_state["gate_i"]
            call_state["gate_i"] += 1
            decision = gate_decisions[min(i, len(gate_decisions) - 1)]
            return json.dumps({
                "decision": decision,
                "reshape_notes": "tighten error handling" if decision == "reshape" else "",
                "owner_gate_output": f"gate:{decision}",
            })
        return "step ran"

    def _sink(**kw: Any) -> None:
        if kw.get("phase") == "ran":
            visited.append(kw.get("node_id"))

    compiled = compile_branch(
        _reference_branch(), provider_call=_call, event_sink=_sink,
    )
    result = compiled.graph.compile().invoke(
        dict(_SEED_STATE), config={"recursion_limit": 50},
    )

    first_gate = visited.index("owner_gate")
    # After the reshape decision the next node is draft_patch, not merge.
    assert visited[first_gate + 1] == "draft_patch", visited
    assert "merge" not in visited, visited
    assert not dict(result).get("merge_output"), result
