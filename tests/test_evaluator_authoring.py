"""Evaluator authoring — same session lifecycle as nodes, canonical evaluator
contract, ordered chains with explicit termination.

Requirement source:
``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets/
specs/node-authoring-and-autoresearch/spec.md`` — "Node and evaluator authoring
share one structural lifecycle" (tasks 4.2, 4.5).

The canonical evaluator contract is ``tinyassets.evaluation.EvalResult`` /
``EvalVerdict`` (pass/fail/skip/error); the authored declaration must satisfy it
rather than invent a second verdict vocabulary.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    return base


@pytest.fixture
def service(env):
    from tinyassets.authoring import service as svc

    return svc


def _terminal_stage(name="grade", **overrides):
    stage = {
        "name": name,
        "verdicts": ["pass", "fail", "skip", "error"],
        "on_verdict": {
            "pass": {"terminal": True},
            "fail": {"terminal": True},
            "skip": {"terminal": True},
            "error": {"terminal": True},
        },
    }
    stage.update(overrides)
    return stage


def _evaluator_ops(stages=None):
    return [
        {"op": "set", "path": "name", "value": "Recipe grader"},
        {
            "op": "set",
            "path": "inputs",
            "value": [
                {"name": "artifact", "source": "artifact"},
                {"name": "context", "source": "context"},
            ],
        },
        {
            "op": "set",
            "path": "outputs",
            "value": {
                "verdict": True,
                "score": True,
                "rationale": True,
                "evidence": True,
                "cost": True,
            },
        },
        {
            "op": "set",
            "path": "determinism",
            "value": {"deterministic": True, "cache": "by_definition_hash"},
        },
        {"op": "set", "path": "stages", "value": stages or [_terminal_stage()]},
    ]


def _authored_evaluator(service, stages=None, actor="alice"):
    session = service.start_session(
        actor_id=actor, artifact_kind="evaluator", sketch="grade my recipes"
    )
    service.apply_edit_batch(
        actor_id=actor,
        session_id=session["session_id"],
        operations=_evaluator_ops(stages),
    )
    return session["session_id"]


# ---------------------------------------------------------------------------
# Same lifecycle as nodes
# ---------------------------------------------------------------------------


def test_evaluator_skeleton_declares_the_canonical_contract_slots(service):
    session = service.start_session(
        actor_id="alice", artifact_kind="evaluator", sketch="grade"
    )
    definition = session["definition"]
    for key in ("inputs", "outputs", "determinism", "stages", "effects", "sandbox_policy"):
        assert key in definition
    assert session["artifact_kind"] == "evaluator"


def test_evaluator_publishes_as_a_versioned_artifact_with_lineage(service):
    session_id = _authored_evaluator(service)
    service.run_test(actor_id="alice", session_id=session_id)
    draft_version = service.inspect_session(actor_id="alice", session_id=session_id)[
        "draft_version"
    ]

    published = service.publish_session(
        actor_id="alice",
        session_id=session_id,
        expected_version=draft_version,
        change_message="v1",
    )["version"]

    assert published["artifact_kind"] == "evaluator"
    assert published["version_no"] == 1
    assert published["definition_hash"]
    assert published["provenance"]["source_session_id"] == session_id

    # Same inspection guarantees as a node version.
    full = service.get_version(actor_id="alice", version_id=published["version_id"])
    assert full["definition"]["stages"][0]["name"] == "grade"

    # And it can seed a new draft with lineage.
    resumed = service.start_session(
        actor_id="alice",
        artifact_kind="evaluator",
        base_version_id=published["version_id"],
    )
    assert resumed["lineage"]["parent_version_id"] == published["version_id"]
    assert resumed["definition"]["stages"] == full["definition"]["stages"]


def test_evaluator_summary_view_surfaces_stages_and_human_stage(service):
    session_id = _authored_evaluator(
        service,
        stages=[_terminal_stage(human_review=True, external=True)],
    )
    summary = service.inspect_session(
        actor_id="alice", session_id=session_id, view="summary"
    )
    assert [s["name"] for s in summary["stages"]] == ["grade"]
    assert summary["stages"][0]["human_review"] is True
    assert summary["stages"][0]["external"] is True


# ---------------------------------------------------------------------------
# Canonical contract enforcement
# ---------------------------------------------------------------------------


def test_missing_required_output_blocks_publication(service):
    from tinyassets.authoring.models import AuthoringValidationError

    ops = [op for op in _evaluator_ops() if op["path"] != "outputs"]
    ops.append(
        {
            "op": "set",
            "path": "outputs",
            "value": {"verdict": True, "score": True},
        }
    )
    session = service.start_session(
        actor_id="alice", artifact_kind="evaluator", sketch="grade"
    )
    with pytest.raises(AuthoringValidationError) as exc:
        service.apply_edit_batch(
            actor_id="alice", session_id=session["session_id"], operations=ops
        )
    codes = {i.code for i in exc.value.issues}
    assert "evaluator.output_missing" in codes
    missing = {i.path for i in exc.value.issues if i.code == "evaluator.output_missing"}
    assert missing == {"outputs.rationale", "outputs.evidence", "outputs.cost"}


def test_non_canonical_verdict_is_rejected(service):
    from tinyassets.authoring.models import AuthoringValidationError

    stage = _terminal_stage()
    stage["verdicts"] = ["pass", "fail", "vibes"]
    stage["on_verdict"]["vibes"] = {"terminal": True}

    with pytest.raises(AuthoringValidationError) as exc:
        _authored_evaluator(service, stages=[stage])
    assert any(i.code == "evaluator.unknown_verdict" for i in exc.value.issues)


def test_determinism_policy_must_be_declared(service):
    from tinyassets.authoring.models import AuthoringValidationError

    ops = [op for op in _evaluator_ops() if op["path"] != "determinism"]
    session = service.start_session(
        actor_id="alice", artifact_kind="evaluator", sketch="grade"
    )
    service.apply_edit_batch(
        actor_id="alice", session_id=session["session_id"], operations=ops
    )
    service.run_test(actor_id="alice", session_id=session["session_id"])
    draft_version = service.inspect_session(
        actor_id="alice", session_id=session["session_id"]
    )["draft_version"]

    with pytest.raises(AuthoringValidationError) as exc:
        service.publish_session(
            actor_id="alice",
            session_id=session["session_id"],
            expected_version=draft_version,
            change_message="no determinism policy",
        )
    assert any(i.code == "evaluator.determinism_undeclared" for i in exc.value.issues)


# ---------------------------------------------------------------------------
# Chains: explicit continuation / termination, acyclic
# ---------------------------------------------------------------------------


def test_ordered_chain_with_continuation_is_valid(service):
    stages = [
        {
            "name": "cheap_screen",
            "verdicts": ["pass", "fail", "skip", "error"],
            "on_verdict": {
                "pass": {"continue": "deep_review"},
                "fail": {"terminal": True},
                "skip": {"continue": "deep_review"},
                "error": {"terminal": True},
            },
        },
        _terminal_stage("deep_review"),
    ]
    session_id = _authored_evaluator(service, stages=stages)
    view = service.inspect_session(actor_id="alice", session_id=session_id)
    assert view["validation"]["issues"] == []


def test_uncovered_verdict_path_blocks_publication_and_names_it(service):
    from tinyassets.authoring.models import AuthoringValidationError

    stage = _terminal_stage()
    del stage["on_verdict"]["error"]

    with pytest.raises(AuthoringValidationError) as exc:
        _authored_evaluator(service, stages=[stage])
    uncovered = [
        i for i in exc.value.issues if i.code == "evaluator.chain_uncovered_verdict"
    ]
    assert uncovered
    assert uncovered[0].path == "stages[0].on_verdict.error"


def test_chain_cycle_is_rejected(service):
    from tinyassets.authoring.models import AuthoringValidationError

    stages = [
        {
            "name": "a",
            "verdicts": ["pass", "fail", "skip", "error"],
            "on_verdict": {
                "pass": {"continue": "b"},
                "fail": {"terminal": True},
                "skip": {"terminal": True},
                "error": {"terminal": True},
            },
        },
        {
            "name": "b",
            "verdicts": ["pass", "fail", "skip", "error"],
            "on_verdict": {
                "pass": {"continue": "a"},
                "fail": {"terminal": True},
                "skip": {"terminal": True},
                "error": {"terminal": True},
            },
        },
    ]
    with pytest.raises(AuthoringValidationError) as exc:
        _authored_evaluator(service, stages=stages)
    assert any(i.code == "evaluator.chain_cycle" for i in exc.value.issues)


def test_continuation_to_unknown_stage_is_rejected(service):
    from tinyassets.authoring.models import AuthoringValidationError

    stage = _terminal_stage()
    stage["on_verdict"]["pass"] = {"continue": "ghost"}
    with pytest.raises(AuthoringValidationError) as exc:
        _authored_evaluator(service, stages=[stage])
    assert any(i.code == "evaluator.chain_unknown_stage" for i in exc.value.issues)


def test_surrounding_workflow_cannot_masquerade_as_an_evaluator(service):
    from tinyassets.authoring.models import AuthoringValidationError

    for kind in ("moderation", "convergence", "scheduling"):
        stage = _terminal_stage(stage_kind=kind)
        with pytest.raises(AuthoringValidationError) as exc:
            _authored_evaluator(service, stages=[stage])
        assert any(
            i.code == "evaluator.workflow_not_an_evaluator" for i in exc.value.issues
        ), kind


def test_evaluator_binding_on_a_node_must_reference_a_published_evaluator(service):
    from tinyassets.authoring.models import AuthoringValidationError

    node_session = service.start_session(
        actor_id="alice", artifact_kind="node", sketch="bound node"
    )
    with pytest.raises(AuthoringValidationError) as exc:
        service.apply_edit_batch(
            actor_id="alice",
            session_id=node_session["session_id"],
            operations=[
                {
                    "op": "set",
                    "path": "evaluator_binding",
                    "value": {"version_id": "ver_never_published"},
                },
            ],
        )
    assert any(i.code == "definition.unknown_evaluator_binding" for i in exc.value.issues)


def test_evaluator_binding_resolves_to_a_real_published_version(service):
    evaluator_session = _authored_evaluator(service)
    service.run_test(actor_id="alice", session_id=evaluator_session)
    evaluator_version = service.publish_session(
        actor_id="alice",
        session_id=evaluator_session,
        expected_version=service.inspect_session(
            actor_id="alice", session_id=evaluator_session
        )["draft_version"],
        change_message="v1",
    )["version"]

    node_session = service.start_session(
        actor_id="alice", artifact_kind="node", sketch="bound node"
    )
    result = service.apply_edit_batch(
        actor_id="alice",
        session_id=node_session["session_id"],
        operations=[
            {
                "op": "set",
                "path": "evaluator_binding",
                "value": {"version_id": evaluator_version["version_id"]},
            },
        ],
    )
    assert result["definition"]["evaluator_binding"]["version_id"] == (
        evaluator_version["version_id"]
    )
