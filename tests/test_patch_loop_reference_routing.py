"""Safety + honesty of the reference patch loop's conditional routing and
effect contracts.

Routing safety (Codex round-6/7): a failing verify (``send_back``) can NEVER
reach ``present`` (open the PR), and a rejected owner gate (``reject``) can NEVER
reach ``merge``. ``_build_conditional_router`` routes on ``verdict`` and falls
back to the edge's declared SCALAR ``fallback`` (the SAFE branch) — persistence
alphabetizes the conditions dict (``_json_dumps(sort_keys=True)``), so key order
cannot be trusted; the scalar fallback survives it.

Gate convention (Codex r10 #5): verify + owner_gate are gates emitting the
canonical shape from ``docs/conventions/gate-branch-shape.md`` — ``verdict``
(``pass`` / ``send_back`` / ``reject``) + ``verdict_evidence``.

Effect honesty (Codex r10 #1): present/merge declare real effects AND the
matching typed packet output_keys the effectors search, so the emitted packet is
actually findable.

Compiled-graph proof: builds the REAL artifact spec through
``_staged_branch_from_spec`` -> ``compile_branch`` -> ``graph.invoke`` with fake
providers and asserts the observed node-visit order (via the event sink).
"""
from __future__ import annotations

import json
from typing import Any, Callable

import pytest

from tinyassets.api.branches import _staged_branch_from_spec
from tinyassets.branch_designs import load_design_artifacts
from tinyassets.graph_compiler import (
    _sandbox_enforcement_available as _REAL_SANDBOX_AVAILABLE,
)
from tinyassets.graph_compiler import (
    compile_branch,
)


@pytest.fixture(autouse=True)
def _enable_sandbox_enforcement(monkeypatch):
    # Codex r13 #1 / r14 #1: the reference's repo-touching nodes are
    # requires_sandbox=true and REFUSE to execute when a real sandbox runner is
    # unavailable (honest fail-closed). These ROUTING tests exercise the graph
    # end-to-end, so they simulate the Phase-2 runner being present by
    # monkeypatching the availability FUNCTION (a test seam — NOT a production env
    # var, which was the r13 bypass Codex removed). The honest S1 default
    # (unavailable -> refuse before provider dispatch) is proven by
    # test_requires_sandbox_node_refuses_before_provider below.
    monkeypatch.setattr(
        "tinyassets.graph_compiler._sandbox_enforcement_available", lambda: True,
    )

# Binding fields a remix would bind; seeded so every node's template renders (the
# reference nodes declare no input_keys, so the full state is the render view — a
# referenced-but-unseeded key would raise at compile-run time).
_SEED_STATE: dict[str, str] = {
    "intake_source": "queue://requests",
    "request_payload": "user reports the export button is broken",
    "target_repo": "example/project",
    "merge_policy": "manual",
    "verify_command": "pytest -q",
    "reshape_notes": "",
}

_PR_PACKET = {
    "sink": "github_pull_request",
    "destination": "example/project",
    "payload": {
        "title": "Fix export button", "body": "summary",
        "base_branch": "main", "head_branch": "auto/fix-export", "draft": False,
        "changes_json": {"src/export.py": "print('fixed')\n"},
        # S4 authoritative schema: two flat keys only — request_ref + verify_verdict
        # (canonical pass|fail|unknown). Evidence lives in the PR body, not here.
        "review_queue": {"request_ref": "req-42", "verify_verdict": "pass"},
    },
}
_MERGE_PACKET = {
    "sink": "github_merge",
    "destination": "example/project",
    "payload": {
        "pr_number": 1, "expected_head_sha": "a" * 40,
        "merge_method": "squash", "authorization": {"mode": "github_branch_protection"},
    },
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
    verify_verdicts: list[str], gate_verdict: str,
) -> Callable[..., str]:
    """Fake provider: scripted canonical verdicts for the gates and valid effect
    packets for present/merge (all four are JSON-contract nodes now). Markers are
    unique node prompt-body phrases."""
    call_state = {"verify_i": 0}

    def _call(prompt: str, system: str = "", *, role: str = "writer") -> str:
        if "verification GATE" in prompt:
            i = call_state["verify_i"]
            call_state["verify_i"] += 1
            verdict = verify_verdicts[min(i, len(verify_verdicts) - 1)]
            return json.dumps({
                "verdict": verdict,
                "verdict_evidence": {"reason": f"verify:{verdict}"},
            })
        if "owner review GATE" in prompt:
            return json.dumps({
                "verdict": gate_verdict,
                "verdict_evidence": {"reason": f"gate:{gate_verdict}"},
                "reshape_notes": "please revise" if gate_verdict == "send_back" else "",
            })
        if "github_pull_request external-write packet" in prompt:
            return json.dumps({
                "github_pr_packet": _PR_PACKET, "present_output": "queued PR #1",
            })
        if "github_merge external-write packet" in prompt:
            return json.dumps({
                "github_merge_packet": _MERGE_PACKET, "merge_output": "merge receipt",
            })
        return "step ran"
    return _call


def _invoke_compiled(
    branch, verify_verdicts: list[str], gate_verdict: str,
) -> tuple[list[str], dict[str, Any]]:
    """Compile + invoke a branch; return (visited_node_order, final_state)."""
    visited: list[str] = []

    def _sink(**kw: Any) -> None:
        if kw.get("phase") == "ran":
            visited.append(kw.get("node_id"))

    compiled = compile_branch(
        branch,
        provider_call=_make_provider(verify_verdicts, gate_verdict),
        event_sink=_sink,
    )
    result = compiled.graph.compile().invoke(
        dict(_SEED_STATE), config={"recursion_limit": 50},
    )
    return visited, dict(result)


def _run(verify_verdicts: list[str], gate_verdict: str) -> tuple[list[str], dict[str, Any]]:
    """Compile + invoke the STAGED reference branch (never crosses persistence)."""
    return _invoke_compiled(_reference_branch(), verify_verdicts, gate_verdict)


# ── Safety semantics ────────────────────────────────────────────────────────


def test_happy_path_pass_routes_present_then_pass_routes_merge():
    # ROUTING property only: verify pass -> present, owner pass -> merge (present
    # before merge). We assert the graph REACHES merge, NOT that a fake model's
    # merge_output text means "the PR merged" — present EMITS a
    # github_pull_request effect and merge EMITS a github_merge effect; the runner
    # performs the writes. Full present -> owner review-queue -> decision -> merge
    # effector EXECUTION is wired in the durable two-stage resume phase
    # (lead-tracked); on S1 the repo-touching nodes are sandbox-required and fail
    # closed until the sandbox runner ships.
    visited, _result = _run(verify_verdicts=["pass"], gate_verdict="pass")

    assert "present" in visited, visited
    assert "merge" in visited, visited
    assert visited.index("present") < visited.index("merge")


def test_send_back_verify_routes_to_draft_patch_and_never_present():
    # First verify returns send_back -> MUST route back to draft_patch, NOT
    # present. Second verify returns pass so the run terminates (reject ends it).
    visited, _result = _run(verify_verdicts=["send_back", "pass"], gate_verdict="reject")

    first_verify = visited.index("verify")
    assert visited[first_verify + 1] == "draft_patch", visited
    assert "present" not in visited[: first_verify + 1], visited
    assert visited.count("draft_patch") >= 2, visited


def test_reject_owner_gate_routes_to_end_and_never_merge():
    # verify pass gets us to present; reject at the owner gate -> END, never merge.
    visited, result = _run(verify_verdicts=["pass"], gate_verdict="reject")

    assert "present" in visited, visited
    assert "owner_gate" in visited, visited
    assert "merge" not in visited, visited
    assert not result.get("merge_output"), result


def test_send_back_owner_gate_routes_back_to_draft_and_never_merge():
    # owner send_back must loop back to draft_patch (not merge). One send_back,
    # then a reject terminates so the graph doesn't spin forever in the test.
    visited: list[str] = []
    call_state = {"verify_i": 0, "gate_i": 0}
    gate_verdicts = ["send_back", "reject"]

    def _call(prompt: str, system: str = "", *, role: str = "writer") -> str:
        if "verification GATE" in prompt:
            return json.dumps({
                "verdict": "pass", "verdict_evidence": {"reason": "verify:pass"},
            })
        if "owner review GATE" in prompt:
            i = call_state["gate_i"]
            call_state["gate_i"] += 1
            verdict = gate_verdicts[min(i, len(gate_verdicts) - 1)]
            return json.dumps({
                "verdict": verdict,
                "verdict_evidence": {"reason": f"gate:{verdict}"},
                "reshape_notes": "tighten error handling" if verdict == "send_back" else "",
            })
        if "github_pull_request external-write packet" in prompt:
            return json.dumps({"github_pr_packet": _PR_PACKET, "present_output": "PR"})
        if "github_merge external-write packet" in prompt:
            return json.dumps({"github_merge_packet": _MERGE_PACKET, "merge_output": "m"})
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
    assert visited[first_gate + 1] == "draft_patch", visited
    assert "merge" not in visited, visited
    assert not dict(result).get("merge_output"), result


# ── Honest-reference structure: gate convention + effect contracts ───────────


def test_gates_use_canonical_verdict_convention():
    # Codex r10 #5: verify + owner_gate emit the canonical gate shape
    # (verdict + verdict_evidence), route on the canonical verdict vocabulary,
    # and the SAFE-first scalar fallback is the canonical safe verdict.
    spec = _reference_spec()
    nodes = {n["node_id"]: n for n in spec["node_defs"]}
    edges = {c["from"]: c for c in spec["conditional_edges"]}
    fields = {f["name"] for f in spec["state_schema"]}

    assert nodes["verify"]["output_keys"][:2] == ["verdict", "verdict_evidence"]
    assert nodes["owner_gate"]["output_keys"][:2] == ["verdict", "verdict_evidence"]
    assert {"verdict", "verdict_evidence"} <= fields
    # Canonical verdict vocabulary only (no green/red/approve/reshape).
    assert set(edges["verify"]["conditions"]) == {"pass", "send_back"}
    assert set(edges["owner_gate"]["conditions"]) == {"pass", "send_back", "reject"}
    # Safe-first fallback = the canonical SAFE verdict (never forward-to-write).
    assert edges["verify"]["fallback"] == "send_back"
    assert edges["owner_gate"]["fallback"] == "reject"


def test_reference_declares_real_effects_and_sandbox_node_kinds():
    # Codex r10 #1 + node_kind reconciliation: present/merge carry REAL effect
    # declarations AND the packet output_keys the effectors search; the
    # repo-touching nodes are sandbox-required and carry S3's node_kind values
    # (repo_read / repo_exec / coding). Full effector EXECUTION is wired in the
    # durable two-stage resume phase (lead-tracked).
    spec = _reference_spec()
    nodes = {n["node_id"]: n for n in spec["node_defs"]}

    # node_kind reconciled with S3's taxonomy (NOT a capabilities list).
    assert nodes["investigate"]["node_kind"] == "repo_read"
    assert nodes["verify"]["node_kind"] == "repo_exec"
    assert nodes["draft_patch"]["node_kind"] == "coding"
    assert "capabilities" not in nodes["investigate"]
    for nid in ("investigate", "verify", "draft_patch"):
        assert nodes[nid]["requires_sandbox"] is True, nid

    # Real effect declarations + the matching typed packet output_keys.
    assert nodes["present"]["effects"] == ["github_pull_request"]
    assert nodes["present"]["output_keys"][0] == "github_pr_packet"
    assert nodes["merge"]["effects"] == ["github_merge"]
    assert nodes["merge"]["output_keys"][0] == "github_merge_packet"

    # Codex r11 #2: present's packet contract instructs the changes reference
    # (changes_json from the drafted patch — Phase-2 sandbox coding node produces
    # the diff) AND S4's review_queue metadata (so the PR enters owner review).
    present_prompt = nodes["present"]["prompt_template"]
    assert "changes_json" in present_prompt
    assert "review_queue" in present_prompt
    # S4 authoritative schema (relayed): review_queue carries the two FLAT keys
    # S4 reads — request_ref + verify_verdict (canonical pass|fail|unknown). The
    # nested verification object is NOT read (would degrade to unknown); evidence
    # belongs in the PR body / present_output, not queue metadata.
    assert "request_ref" in present_prompt
    assert "verify_verdict" in present_prompt

    # requires_sandbox + effects are REAL NodeDefinition fields — they survive
    # the build (node_kind/capabilities are artifact-only data the build drops).
    branch = _reference_branch()
    built = {n.node_id: n for n in branch.node_defs}
    for nid in ("investigate", "verify", "draft_patch"):
        assert built[nid].requires_sandbox is True, nid
    assert built["present"].effects == ["github_pull_request"]
    assert built["merge"].effects == ["github_merge"]


def test_artifact_envelope_shape_for_s4_bundle_reader():
    # Codex r15 #2: S4's bundle detector reads nodes from spec.node_defs (after
    # S4's corrected reader). S1's only obligation is to keep that envelope shape
    # STABLE so future drift trips a test here (S1 does NOT edit S4's detector).
    # Pin: spec.node_defs present + non-empty, and each node carries the shape
    # S4 + the enforcement slice expect (node_kind + requires_sandbox on the
    # repo-touching nodes; effects on the effect nodes).
    spec = _reference_spec()
    assert isinstance(spec.get("node_defs"), list) and spec["node_defs"], spec
    assert "nodes" not in spec   # S1 stores under node_defs, not top-level nodes
    nodes = {n["node_id"]: n for n in spec["node_defs"]}
    for nid, kind in (
        ("investigate", "repo_read"), ("verify", "repo_exec"), ("draft_patch", "coding"),
    ):
        assert nodes[nid]["node_kind"] == kind, nid
        assert nodes[nid]["requires_sandbox"] is True, nid
    assert nodes["present"]["effects"] == ["github_pull_request"]
    assert nodes["merge"]["effects"] == ["github_merge"]


def test_present_output_keys_satisfy_github_pr_effector_contract():
    # Codex r10 #1 (effector contract): a valid github_pull_request packet placed
    # under one of present's declared output_keys must be FOUND by the effector —
    # NOT no_matching_packet. Proves the node's declared keys match what the
    # effector searches.
    from tinyassets.effectors.github_pr import run_github_pr_effector

    present = next(n for n in _reference_branch().node_defs if n.node_id == "present")
    run_state = {"github_pr_packet": dict(_PR_PACKET)}
    result = run_github_pr_effector(
        node_id="present", output_keys=present.output_keys,
        run_state=run_state, base_path=None,
    )
    assert result.get("error_kind") != "no_matching_packet", result
    assert result.get("matched_output_key") == "github_pr_packet" or result.get("dry_run"), result


def test_merge_output_keys_satisfy_github_merge_effector_contract():
    from tinyassets.effectors.github_merge import run_github_merge_effector

    merge = next(n for n in _reference_branch().node_defs if n.node_id == "merge")
    run_state = {"github_merge_packet": dict(_MERGE_PACKET)}
    result = run_github_merge_effector(
        node_id="merge", output_keys=merge.output_keys,
        run_state=run_state, base_path=None,
    )
    assert result.get("error_kind") != "no_matching_packet", result


# ── fail-closed sandbox enforcement (Codex r13 #1) ───────────────────────────


def test_requires_sandbox_node_refuses_before_provider(monkeypatch):
    # Codex r13 #1 / r14 #1: with no real sandbox runner, a requires_sandbox node
    # must REFUSE at invoke time BEFORE any provider dispatch — the provider is
    # NEVER called. Honestly fail-closed, not silently executable, and NOT
    # bypassable by an env var.
    from tinyassets.branches import NodeDefinition
    from tinyassets.graph_compiler import (
        SandboxEnforcementUnavailableError,
        _build_prompt_template_node,
    )

    # S1 default: force the availability FUNCTION to report unavailable.
    monkeypatch.setattr(
        "tinyassets.graph_compiler._sandbox_enforcement_available", lambda: False,
    )
    called: list[str] = []

    def _provider(prompt: str, system: str = "", *, role: str = "writer") -> str:
        called.append(prompt)
        return "should never run"

    node = NodeDefinition(
        node_id="coder", display_name="Coder", prompt_template="do {x}",
        requires_sandbox=True,
    )
    fn = _build_prompt_template_node(node, provider_call=_provider, event_sink=None)
    with pytest.raises(SandboxEnforcementUnavailableError):
        fn({"x": "work"})
    assert called == [], "provider must NOT be dispatched for a requires_sandbox node"


def test_env_var_alone_does_not_enable_availability(monkeypatch):
    # Codex r14 #1: a truthy TINYASSETS_SANDBOX_ENFORCEMENT env var must NOT make
    # the availability function return True — it does not prove confinement.
    # Availability comes ONLY from the real runner-capability import, which is
    # absent on this branch, so even with the env var set it stays False. (Uses
    # the REAL function captured at import, bypassing the routing autouse seam.)
    monkeypatch.setenv("TINYASSETS_SANDBOX_ENFORCEMENT", "1")
    assert _REAL_SANDBOX_AVAILABLE() is False


def test_sandbox_availability_unpacks_s3_tuple_contract(monkeypatch):
    # Codex r15 #3: S3's coding_nodes_runnable() returns (runnable, reason). A
    # non-empty tuple is TRUTHY, so bool(result) would misread (False, reason) as
    # "available" and run unconfined. The availability probe must UNPACK. Tested
    # against S3's ACTUAL shape via a fake sandbox_policy module (not a
    # monkeypatch-to-True, which proves nothing about the real contract).
    import sys
    import types

    fake = types.ModuleType("tinyassets.sandbox_policy")
    monkeypatch.setitem(sys.modules, "tinyassets.sandbox_policy", fake)

    # (False, reason) — the CURRENT S3 enforcement-only state — must read False.
    fake.coding_nodes_runnable = lambda: (False, "sandbox runner not integrated")
    assert _REAL_SANDBOX_AVAILABLE() is False
    # (True, reason) — a real runner present — reads True.
    fake.coding_nodes_runnable = lambda: (True, "runner ready")
    assert _REAL_SANDBOX_AVAILABLE() is True
    # Forward/backward compat: a bare bool still works.
    fake.coding_nodes_runnable = lambda: False
    assert _REAL_SANDBOX_AVAILABLE() is False
    fake.coding_nodes_runnable = lambda: True
    assert _REAL_SANDBOX_AVAILABLE() is True


def test_requires_sandbox_node_runs_when_runner_available(monkeypatch):
    # With the runner capability available (simulating the Phase-2 runner via the
    # availability function seam), the node runs and the provider IS dispatched —
    # the gate is capability-gated, not an unconditional block.
    from tinyassets.branches import NodeDefinition
    from tinyassets.graph_compiler import _build_prompt_template_node

    monkeypatch.setattr(
        "tinyassets.graph_compiler._sandbox_enforcement_available", lambda: True,
    )
    called: list[str] = []

    def _provider(prompt: str, system: str = "", *, role: str = "writer") -> str:
        called.append(prompt)
        return "ran"

    node = NodeDefinition(
        node_id="coder", display_name="Coder", prompt_template="do {x}",
        requires_sandbox=True,
    )
    fn = _build_prompt_template_node(node, provider_call=_provider, event_sink=None)
    out = fn({"x": "work"})
    assert called, "provider must be dispatched when the runner is available"
    assert out.get("coder_output") == "ran"


# ── fallback type-safety (Codex r11 #3) ──────────────────────────────────────


def _fallback_spec(fallback):
    return {
        "name": "fb", "entry_point": "g",
        "node_defs": [
            {"node_id": "g", "display_name": "G", "output_keys": ["verdict"],
             "prompt_template": "decide {y}"},
            {"node_id": "leaf", "display_name": "L", "prompt_template": "leaf"},
        ],
        "edges": [{"from": "START", "to": "g"}, {"from": "leaf", "to": "END"}],
        "conditional_edges": [
            {"from": "g", "conditions": {"pass": "leaf"}, "fallback": fallback},
        ],
        "state_schema": [
            {"name": "y", "type": "str"}, {"name": "verdict", "type": "str"},
        ],
    }


@pytest.mark.parametrize("bad", [123, ["x"], {"a": 1}, True])
def test_authoring_rejects_nonstring_fallback_without_crashing(bad):
    # Authoring boundary: `fallback: 123` must be a CLEAN validation error, NOT
    # an AttributeError crash on .strip() (Codex r11 #3).
    branch, errors = _staged_branch_from_spec(_fallback_spec(bad))  # must NOT raise
    assert any("fallback" in e.lower() for e in errors), errors


def test_authoring_accepts_none_fallback():
    _branch, errors = _staged_branch_from_spec(_fallback_spec(None))
    assert not any("fallback" in e.lower() for e in errors), errors


@pytest.mark.parametrize("bad", [123, ["x"], {"a": 1}])
def test_persisted_nonstring_fallback_does_not_crash_and_validates(bad):
    # Deserialization boundary: from_dict must NOT crash on a persisted
    # non-string fallback; validate() surfaces a clean error (Codex r11 #3).
    from tinyassets.branches import (
        BranchDefinition,
        ConditionalEdge,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    ce = ConditionalEdge.from_dict(
        {"from": "g", "conditions": {"pass": "leaf"}, "fallback": bad}
    )  # must NOT raise
    assert ce.fallback == bad

    b = BranchDefinition(name="fb", entry_point="g")
    b.node_defs = [
        NodeDefinition(node_id="g", display_name="G", prompt_template="x",
                       output_keys=["verdict"]),
        NodeDefinition(node_id="leaf", display_name="L", prompt_template="leaf"),
    ]
    b.graph_nodes = [
        GraphNodeRef(id="g", node_def_id="g"),
        GraphNodeRef(id="leaf", node_def_id="leaf"),
    ]
    b.edges = [
        EdgeDefinition(from_node="START", to_node="g"),
        EdgeDefinition(from_node="leaf", to_node="END"),
    ]
    b.conditional_edges = [ce]
    errors = b.validate()
    assert any("fallback" in e.lower() and "string" in e.lower() for e in errors), errors


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
        assert list(verify_ce.conditions.keys()) == ["pass", "send_back"]
        assert list(gate_ce.conditions.keys()) == ["pass", "reject", "send_back"]
        # ...but the scalar fallback survived and still pins the SAFE verdict.
        assert verify_ce.fallback == "send_back"
        assert gate_ce.fallback == "reject"

    def test_offlabel_verify_routes_to_draft_across_persistence(self, data_dir):
        # An off-label verdict ("orange") must route to draft_patch, NEVER
        # present — across the persistence boundary.
        branch = _persisted_reference_branch(data_dir)
        visited, _result = _invoke_compiled(
            branch, verify_verdicts=["orange", "pass"], gate_verdict="maybe",
        )
        first_verify = visited.index("verify")
        assert visited[first_verify + 1] == "draft_patch", visited
        assert "present" not in visited[: first_verify + 1], visited

    def test_offlabel_owner_verdict_routes_to_end_across_persistence(self, data_dir):
        # An off-label owner verdict ("maybe") must route to END, NEVER merge.
        branch = _persisted_reference_branch(data_dir)
        visited, result = _invoke_compiled(
            branch, verify_verdicts=["pass"], gate_verdict="maybe",
        )
        assert "present" in visited, visited
        assert "owner_gate" in visited, visited
        assert "merge" not in visited, visited
        assert not result.get("merge_output"), result

    def test_happy_path_survives_persistence(self, data_dir):
        branch = _persisted_reference_branch(data_dir)
        visited, _result = _invoke_compiled(
            branch, verify_verdicts=["pass"], gate_verdict="pass",
        )
        assert "present" in visited and "merge" in visited, visited
