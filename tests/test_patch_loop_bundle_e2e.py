"""Patch-loop BUNDLE integration — the REAL path (Codex r15 coordinator ask).

Proves the genuine end-to-end contract on the integration branch (S1 seed + S3
enforcement + S4 effector all present): compile the reference design, INVOKE it
through the real run executor, the present node's effect dispatch PROJECTS the
PR + SUSPENDS the run (interrupted, not completed), the owner decides on the
review surface, and the continuation RESUMES the run — not a fabricated packet
+ direct effector call.

Skip semantics (Codex r15): SKIP only when the S1 seed is genuinely ABSENT
(S4-alone). When the seed is PRESENT but its contract can't be read, that is a
FAILURE (a silent skip would hide a broken bundle contract).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.runs as runs
from tinyassets.effectors import github_pr
from tinyassets.storage import review_queue as rq

_REFERENCE_SEED = (
    Path(__file__).resolve().parents[1]
    / "tinyassets" / "branch_designs" / "patch_loop_reference.json"
)


def _reference_nodes(spec: dict) -> list[dict]:
    """Extract the NodeDefinition list from whichever envelope S1 lands with:
    S1 stores nodes under ``spec.node_defs`` (a ``spec`` wrapper), with legacy
    top-level / ``spec_json`` fallbacks."""
    wrapper = spec.get("spec") if isinstance(spec.get("spec"), dict) else {}
    inner = spec.get("spec_json") if isinstance(spec.get("spec_json"), dict) else {}
    return (
        wrapper.get("node_defs")
        or spec.get("node_defs")
        or inner.get("node_defs")
        or wrapper.get("nodes")
        or spec.get("nodes")
        or inner.get("nodes")
        or []
    )


def _reference_status() -> str:
    """``absent`` (seed missing → skip) | ``unreadable`` (present but contract
    unparseable → FAIL) | ``ready`` (present + declares the effects)."""
    if not _REFERENCE_SEED.exists():
        return "absent"
    try:
        spec = json.loads(_REFERENCE_SEED.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return "unreadable"
    nodes = _reference_nodes(spec)
    if not nodes:
        return "unreadable"
    sinks = {
        sink for node in nodes if isinstance(node, dict)
        for sink in (node.get("effects") or [])
    }
    if not ({"github_pull_request", "github_merge"} <= sinks):
        return "unreadable"
    return "ready"


_STATUS = _reference_status()


def test_bundle_contract_present_and_readable_or_genuinely_absent():
    """FAIL-not-skip guard (Codex r15): the ONLY acceptable non-ready state is a
    genuinely ABSENT seed (S4-alone). A present-but-unreadable seed is a broken
    bundle contract and must FAIL, never silently skip."""
    assert _REFERENCE_SEED.name == "patch_loop_reference.json"
    assert _STATUS in ("absent", "ready"), (
        f"reference seed present but contract UNREADABLE ({_STATUS}); this is a "
        "broken bundle contract, not a skip"
    )


def _load_reference_branch():
    from tinyassets.branches import BranchDefinition

    spec = json.loads(_REFERENCE_SEED.read_text(encoding="utf-8"))
    inner = spec.get("spec") if isinstance(spec.get("spec"), dict) else spec
    return BranchDefinition.from_dict(inner)


class _FakeClient:
    def __init__(self):
        self.submitted = []

    def run_call(self, call):
        self.submitted.append(call)
        return {"ok": True, "kind": call.kind, "status": 200, "result": {}}


@pytest.mark.skipif(_STATUS != "ready", reason="S1 reference seed absent (S4-alone)")
def test_present_to_owner_resume_e2e_real_path(monkeypatch, tmp_path):
    """The REAL path: compile + invoke the reference through the run executor →
    the present effect projects + SUSPENDS the run → owner approves → the
    continuation resumes the run to a real terminal state."""
    # Open the github_pr gates so the present node "opens" a PR (no live network).
    monkeypatch.setattr(github_pr, "resolve_soul_effect_authority", lambda *a, **k: "")
    monkeypatch.setattr(github_pr, "_read_capability", lambda *a, **k: "tok")
    monkeypatch.setattr(github_pr, "_check_consent", lambda *a, **k: True)
    monkeypatch.setattr(github_pr, "_try_reserve", lambda *a, **k: {"status": "no_hint"})
    monkeypatch.setattr(
        github_pr, "_materialize_branch",
        lambda **k: {"head_branch": "auto/fix", "commit_sha": "a" * 40},
    )
    monkeypatch.setattr(
        github_pr, "_invoke_gh_pr_create",
        lambda **k: {"pr_url": "https://github.com/Owner/Repo/pull/7",
                     "pr_number": 7, "stdout": "", "invocation_mode": "gh"},
    )
    branch = _load_reference_branch()
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=branch.branch_def_id, merge_preference="manual",
        review_required=True, bound_by="owner",
    )
    # INVOKE through the real run executor (compile + graph invoke + effect
    # dispatch), NOT a fabricated packet.
    run_id = runs._prepare_run(
        tmp_path, branch=branch, inputs={}, run_name="", actor="owner",
    )
    outcome = runs._invoke_graph(
        tmp_path, run_id=run_id, branch=branch, inputs={}, provider_call=None,
    )
    # The present effect projected the PR and SUSPENDED the run.
    assert outcome.status == runs.RUN_STATUS_INTERRUPTED
    proj = rq.get_projection(tmp_path, destination="Owner/Repo", pr_number=7)
    assert proj is not None and proj["workflow_outcome"] == "open"

    # Owner approves → the continuation submits the review + completes the run.
    rq.decide_and_resume(
        tmp_path, destination="Owner/Repo", pr_number=7, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha="a" * 40,
        directive={"action": "merge", "github_call": {
            "kind": "submit_review_approve", "transport": "rest", "method": "POST",
            "path": "/repos/Owner/Repo/pulls/7/reviews",
            "params": {"event": "APPROVE", "commit_id": "a" * 40}, "summary": "ok"}},
    )
    cont = runs.continue_reviewed_run(
        tmp_path, run_id=run_id, decision="approve", github_api=_FakeClient(),
    )
    assert cont["applied"] is True
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED
