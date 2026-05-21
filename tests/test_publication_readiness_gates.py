"""Publication-readiness guard for research publication gate rungs."""

from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def gates_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("GATES_ENABLED", "1")
    monkeypatch.setenv("WORKFLOW_STORAGE_BACKEND", "sqlite")
    from workflow import universe_server as us
    from workflow.catalog import backend as backend_mod

    backend_mod.invalidate_backend_cache()
    importlib.reload(us)
    yield us, base
    backend_mod.invalidate_backend_cache()
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


def _ready_manifest() -> dict:
    return {
        "target_venue": "Journal of Theoretical Biology",
        "target_rung": "submitted",
        "policy_requirements": [
            {"name": "data availability", "status": "satisfied"},
            {"name": "conflict disclosure", "status": "satisfied"},
        ],
        "artifact_manifest": [
            {"path": "manuscript.pdf", "kind": "manuscript"},
            {"path": "figures/fig1.svg", "kind": "figure"},
        ],
        "code_data_release": {
            "code": {"status": "released", "doi": "10.5281/zenodo.1"},
            "data": {"status": "released", "doi": "10.5281/zenodo.2"},
        },
        "reproducibility_checks": [
            {"name": "rerun notebooks", "status": "pass"},
            {"name": "figure provenance", "status": "complete"},
        ],
        "empirical_anchor_status": "validated against source datasets",
        "disclosures": {
            "author_contributor": "CRediT roles reviewed",
            "ai_use": "AI assistance disclosed in methods",
        },
        "blockers": [],
    }


def _seed_research_goal_and_branch(us):
    goal = _call(us, "goals", "propose", name="Markovic submission")
    goal_id = goal["goal"]["goal_id"]
    branch = _call(us, "extensions", "create_branch", name="Fingerprint RD")
    branch_id = branch["branch_def_id"]
    _call(us, "goals", "bind", goal_id=goal_id, branch_def_id=branch_id)
    ladder = [
        {
            "rung_key": "draft_ready",
            "name": "Draft ready",
            "description": "Internal draft exists.",
        },
        {
            "rung_key": "submitted",
            "name": "Submitted",
            "description": "Submitted to target venue.",
            "requires_publication_readiness": True,
        },
    ]
    _call(us, "gates", "define_ladder", goal_id=goal_id, ladder=json.dumps(ladder))
    return goal_id, branch_id


def test_publication_rung_requires_ready_publication_manifest(gates_env):
    us, _ = gates_env
    _goal_id, branch_id = _seed_research_goal_and_branch(us)

    result = _call(
        us,
        "gates",
        "claim",
        branch_def_id=branch_id,
        rung_key="submitted",
        evidence_url="https://example.org/submission-receipt",
    )

    assert result["status"] == "rejected"
    assert result["error"] == "publication_readiness_required"


def test_blocked_publication_readiness_cannot_support_claim(gates_env):
    us, _ = gates_env
    goal_id, branch_id = _seed_research_goal_and_branch(us)
    manifest = _ready_manifest()
    manifest["blockers"] = ["missing JTB graphical abstract provenance"]
    recorded = _call(
        us,
        "gates",
        "record_publication_readiness",
        goal_id=goal_id,
        branch_def_id=branch_id,
        rung_key="submitted",
        readiness_json=json.dumps(manifest),
    )
    readiness_id = recorded["publication_readiness"]["readiness_id"]

    result = _call(
        us,
        "gates",
        "claim",
        branch_def_id=branch_id,
        rung_key="submitted",
        evidence_url="https://example.org/submission-receipt",
        publication_readiness_id=readiness_id,
    )

    assert result["status"] == "rejected"
    assert result["error"] == "publication_readiness_blocked"
    assert "missing JTB graphical abstract provenance" in result["blockers"]


def test_ready_publication_manifest_is_stored_on_gate_claim(gates_env):
    us, _ = gates_env
    goal_id, branch_id = _seed_research_goal_and_branch(us)
    recorded = _call(
        us,
        "gates",
        "record_publication_readiness",
        goal_id=goal_id,
        branch_def_id=branch_id,
        rung_key="submitted",
        readiness_json=json.dumps(_ready_manifest()),
    )
    readiness = recorded["publication_readiness"]
    assert readiness["status"] == "ready"

    result = _call(
        us,
        "gates",
        "claim",
        branch_def_id=branch_id,
        rung_key="submitted",
        evidence_url="https://example.org/submission-receipt",
        publication_readiness_id=readiness["readiness_id"],
    )

    assert result["status"] == "claimed"
    assert result["claim"]["publication_readiness_id"] == readiness["readiness_id"]
