"""Conformance-pack guards for standards-backed gate rungs."""

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


def _ready_research_publication_evidence() -> dict:
    return {
        "target_venue": "Journal of Theoretical Biology",
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


def _research_publication_pack() -> dict:
    return {
        "standard_id": "research-publication-v0",
        "standard_version": "v0",
        "jurisdiction": "global",
        "target_rung": "submitted",
        "evidence_requirements": _ready_research_publication_evidence(),
        "vocab_refs": ["CRediT"],
        "checklist": [
            {"name": "venue policy requirements", "status": "satisfied"},
            {"name": "reproducibility checks", "status": "satisfied"},
        ],
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
            "requires_conformance_pack": "research-publication-v0",
        },
    ]
    _call(us, "gates", "define_ladder", goal_id=goal_id, ladder=json.dumps(ladder))
    return goal_id, branch_id


def test_standard_backed_rung_requires_ready_conformance_pack(gates_env):
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
    assert result["error"] == "conformance_pack_required"
    assert result["required_standard_id"] == "research-publication-v0"


def test_blocked_conformance_pack_cannot_support_claim(gates_env):
    us, _ = gates_env
    goal_id, branch_id = _seed_research_goal_and_branch(us)
    pack = _research_publication_pack()
    pack["blockers"] = ["missing JTB graphical abstract provenance"]
    recorded = _call(
        us,
        "gates",
        "record_conformance_pack",
        goal_id=goal_id,
        branch_def_id=branch_id,
        rung_key="submitted",
        conformance_pack_json=json.dumps(pack),
    )
    pack_id = recorded["conformance_pack"]["pack_id"]

    result = _call(
        us,
        "gates",
        "claim",
        branch_def_id=branch_id,
        rung_key="submitted",
        evidence_url="https://example.org/submission-receipt",
        conformance_pack_id=pack_id,
    )

    assert result["status"] == "rejected"
    assert result["error"] == "conformance_pack_not_ready"
    assert "missing JTB graphical abstract provenance" in result["blockers"]


def test_ready_research_publication_pack_is_stored_on_gate_claim(gates_env):
    us, _ = gates_env
    goal_id, branch_id = _seed_research_goal_and_branch(us)
    recorded = _call(
        us,
        "gates",
        "record_conformance_pack",
        goal_id=goal_id,
        branch_def_id=branch_id,
        rung_key="submitted",
        conformance_pack_json=json.dumps(_research_publication_pack()),
    )
    pack = recorded["conformance_pack"]
    assert pack["status"] == "ready"
    assert pack["standard_id"] == "research-publication-v0"

    result = _call(
        us,
        "gates",
        "claim",
        branch_def_id=branch_id,
        rung_key="submitted",
        evidence_url="https://example.org/submission-receipt",
        conformance_pack_id=pack["pack_id"],
    )

    assert result["status"] == "claimed"
    assert result["claim"]["conformance_pack_id"] == pack["pack_id"]


def test_non_builtin_standard_pack_defaults_to_human_review(gates_env):
    us, _ = gates_env
    goal_id, branch_id = _seed_research_goal_and_branch(us)

    recorded = _call(
        us,
        "gates",
        "record_conformance_pack",
        goal_id=goal_id,
        branch_def_id=branch_id,
        rung_key="submitted",
        conformance_pack_json=json.dumps({
            "standard_id": "frcp-edisc-2023",
            "jurisdiction": "US",
            "evidence_requirements": {
                "case_caption": "Smith v Example",
                "docket_number": "1:26-cv-00123",
                "chain_of_custody_hash_manifest": ["sha256:abc"],
            },
        }),
    )

    pack = recorded["conformance_pack"]
    assert pack["standard_id"] == "frcp-edisc-2023"
    assert pack["status"] == "requires-human-review"
