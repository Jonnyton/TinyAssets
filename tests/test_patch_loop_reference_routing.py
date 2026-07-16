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

import pytest

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
    "merge_policy": "manual",
    "verify_command": "pytest -q",
    "reshape_notes": "",
}


def _reference_spec() -> dict:
    return next(
        a for a in load_design_artifacts()
        if a["design_id"] == "patch_loop_reference"
    )["spec"]


def _reference_branch():
    branch, errors = _staged_branch_from_spec(_reference_spec())
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


def _invoke_compiled(
    branch, verify_verdicts: list[str], gate_decision: str,
) -> tuple[list[str], dict[str, Any]]:
    """Compile + invoke a branch; return (visited_node_order, final_state)."""
    visited: list[str] = []

    def _sink(**kw: Any) -> None:
        if kw.get("phase") == "ran":
            visited.append(kw.get("node_id"))

    compiled = compile_branch(
        branch,
        provider_call=_make_provider(verify_verdicts, gate_decision),
        event_sink=_sink,
    )
    result = compiled.graph.compile().invoke(
        dict(_SEED_STATE), config={"recursion_limit": 50},
    )
    return visited, dict(result)


def _run(verify_verdicts: list[str], gate_decision: str) -> tuple[list[str], dict[str, Any]]:
    """Compile + invoke the STAGED reference branch (never crosses persistence)."""
    return _invoke_compiled(_reference_branch(), verify_verdicts, gate_decision)


# ── Safety semantics ────────────────────────────────────────────────────────


def test_happy_path_green_routes_present_then_approve_routes_merge():
    # ROUTING property only: green -> present, approve -> merge (present before
    # merge). We assert the graph REACHES merge, NOT that a fake model's
    # merge_output text means "the PR merged" — the present node EMITS a
    # github_pull_request effect and merge EMITS a github_merge effect; the
    # runner performs the writes. Full present -> owner review-queue -> decision
    # -> merge effector EXECUTION is proven in the bundled S1+S3+S4 integration
    # test (S4 owns that + the github_merge effector); on S1 the repo-touching
    # nodes are sandbox-required and fail closed until the sandbox runner ships.
    visited, _result = _run(verify_verdicts=["green"], gate_decision="approve")

    assert "present" in visited, visited
    assert "merge" in visited, visited
    assert visited.index("present") < visited.index("merge")


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


# ── Honest-reference structure (effects + capability tags) ───────────────────


def test_reference_declares_real_effects_and_sandbox_capabilities():
    # Codex F1/F2: the reference is HONEST, not a prompt-only simulation. present
    # and merge carry REAL effect declarations (the runner performs the writes);
    # the repo-touching nodes are sandbox-required and carry capability tags for
    # the S3 enforcement slice. Structural proof at the artifact + built layers.
    #
    # NOTE: full present -> review-queue -> decision -> merge EFFECTOR EXECUTION
    # is proven in the bundled S1+S3+S4 integration test (S4 owns it). On S1
    # requires_sandbox/effects are declarations; enforcement lands with S3/S4.
    spec = _reference_spec()
    nodes = {n["node_id"]: n for n in spec["node_defs"]}

    # (a) Capability tags on repo-touching nodes (artifact data for S3).
    assert nodes["investigate"]["capabilities"] == ["repo-read"]
    assert nodes["verify"]["capabilities"] == ["repo-exec"]
    assert nodes["draft_patch"]["capabilities"] == ["repo-write"]
    assert nodes["draft_patch"]["node_kind"] == "coding"
    # ...all three are sandbox-required (fail-closed until the sandbox runner).
    for nid in ("investigate", "verify", "draft_patch"):
        assert nodes[nid]["requires_sandbox"] is True, nid

    # (b) Real effect declarations on present + merge.
    assert nodes["present"]["effects"] == ["github_pull_request"]
    assert nodes["merge"]["effects"] == ["github_merge"]

    # requires_sandbox + effects are REAL NodeDefinition fields — they must
    # survive the build into the compiled branch (capabilities/node_kind are
    # artifact-only data the current build drops; S3 consumes them).
    branch = _reference_branch()
    built = {n.node_id: n for n in branch.node_defs}
    for nid in ("investigate", "verify", "draft_patch"):
        assert built[nid].requires_sandbox is True, nid
    assert built["present"].effects == ["github_pull_request"]
    assert built["merge"].effects == ["github_merge"]


# ── Persistence-crossing safety (the durable lesson) ─────────────────────────


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


def _persisted_reference_branch(data_dir):
    """Build the reference, PERSIST it to the registry, then RELOAD it — so the
    branch under test has crossed ``_json_dumps(sort_keys=True)``, which
    ALPHABETIZES every conditions dict on the way to graph_json.

    Durable lesson (Fable-5 CRITICAL, 2026-07-15): a routing-safety test that
    builds via ``_staged_branch_from_spec`` alone NEVER crosses the persistence
    boundary, so it cannot see that key-order-based fallback is destroyed by
    ``sort_keys``. The real run path is registry -> from_dict -> compile_branch;
    safety tests MUST cross build -> save -> load -> compile -> invoke.
    """
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        initialize_author_server,
        save_branch_definition,
    )

    initialize_author_server(data_dir)
    branch, errors = _staged_branch_from_spec(_reference_spec())
    assert errors == [], errors
    saved = save_branch_definition(data_dir, branch_def=branch.to_dict())
    return BranchDefinition.from_dict(
        get_branch_definition(data_dir, branch_def_id=saved["branch_def_id"])
    )


class TestRegistryRoundTripRoutingIsSafe:
    """build -> save -> load -> compile -> invoke, the REAL run path. The
    staged-only tests above never cross ``_json_dumps(sort_keys=True)``; this
    class is the durable guard that the off-label fallback survives persistence
    (the scalar ``fallback`` label, immune to key sorting)."""

    def test_persisted_conditions_are_alphabetized_but_fallback_survives(self, data_dir):
        branch = _persisted_reference_branch(data_dir)
        verify_ce = next(
            c for c in branch.conditional_edges if c.from_node == "verify"
        )
        gate_ce = next(
            c for c in branch.conditional_edges if c.from_node == "owner_gate"
        )
        # sort_keys reordered the safe-first authoring order at the DB layer...
        assert list(verify_ce.conditions.keys()) == ["green", "red"]
        assert list(gate_ce.conditions.keys()) == ["approve", "reject", "reshape"]
        # ...but the scalar fallback survived and still pins the SAFE branch.
        assert verify_ce.fallback == "red"
        assert gate_ce.fallback == "reject"

    def test_offlabel_verify_routes_to_draft_across_persistence(self, data_dir):
        # An off-label verdict ("orange": capitalization/synonym/truncation) must
        # route to draft_patch, NEVER present — across the persistence boundary.
        branch = _persisted_reference_branch(data_dir)
        visited, result = _invoke_compiled(
            branch, verify_verdicts=["orange", "green"], gate_decision="maybe",
        )
        first_verify = visited.index("verify")
        assert visited[first_verify + 1] == "draft_patch", visited
        assert "present" not in visited[: first_verify + 1], visited

    def test_offlabel_decision_routes_to_end_across_persistence(self, data_dir):
        # An off-label decision ("maybe") must route to END, NEVER merge.
        branch = _persisted_reference_branch(data_dir)
        visited, result = _invoke_compiled(
            branch, verify_verdicts=["green"], gate_decision="maybe",
        )
        assert "present" in visited, visited
        assert "owner_gate" in visited, visited
        assert "merge" not in visited, visited
        assert not result.get("merge_output"), result

    def test_happy_path_survives_persistence(self, data_dir):
        branch = _persisted_reference_branch(data_dir)
        visited, result = _invoke_compiled(
            branch, verify_verdicts=["green"], gate_decision="approve",
        )
        assert "present" in visited and "merge" in visited, visited
        assert result.get("merge_output"), result
