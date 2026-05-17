"""Patch-request incentive and requester-directed daemon routing tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow.api.market import classify_filing_effort
from workflow.branch_tasks import BranchTask, read_queue
from workflow.dispatcher import DispatcherConfig, score_task
from workflow.work_targets import (
    choose_authorial_targets,
    load_work_targets,
    materialize_pending_requests,
    requests_path,
)


@pytest.fixture
def server_base(tmp_path: Path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    uid = "test-uni"
    (base / uid).mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", uid)
    monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "host")
    return base, uid


def _submit(**kwargs):
    from workflow.api.universe import _action_submit_request

    return json.loads(_action_submit_request(**kwargs))


def test_pickup_incentive_boosts_pickup_not_acceptance(
    server_base,
    monkeypatch,
):
    base, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")

    response = _submit(
        universe_id=uid,
        text="Please implement the loop status badge.",
        request_type="branch_proposal",
        priority_weight=999.0,
        pickup_incentive="20 credits for an accepted review packet",
    )

    queue = read_queue(base / uid)
    assert response["priority_weight"] == 0.0
    assert response["pickup_incentive"]["enabled"] is True
    assert response["authority_boundary"] == {
        "affects_pickup_priority": True,
        "affects_acceptance": False,
        "affects_release": False,
        "affects_merge": False,
    }
    assert response["request_classification"] == {
        "access": {
            "claimable_by": ["free_daemon", "paid_daemon"],
            "code_writer_gate": "claude_or_codex",
            "checker_gate": "opposite_family_checker",
        },
        "meaning": "branch_refinement",
        "authority": {
            "scope": "requester_pickup_only",
            "boundary": response["authority_boundary"],
        },
    }
    assert queue[0].priority_weight == 0.0
    assert 0.0 < queue[0].pickup_signal_weight <= 5.0
    assert queue[0].trigger_source == "user_request"
    assert (
        queue[0].inputs["request_classification"]
        == response["request_classification"]
    )

    plain = BranchTask(
        branch_task_id="plain",
        branch_def_id=queue[0].branch_def_id,
        universe_id=uid,
        trigger_source="user_request",
        queued_at=queue[0].queued_at,
    )
    host = BranchTask(
        branch_task_id="host",
        branch_def_id=queue[0].branch_def_id,
        universe_id=uid,
        trigger_source="host_request",
        queued_at=queue[0].queued_at,
    )
    cfg = DispatcherConfig()
    assert score_task(queue[0], now_iso=queue[0].queued_at, config=cfg) > score_task(
        plain, now_iso=plain.queued_at, config=cfg,
    )
    assert score_task(host, now_iso=host.queued_at, config=cfg) > score_task(
        queue[0], now_iso=queue[0].queued_at, config=cfg,
    )


def test_incentivized_request_materializes_ahead_with_metadata(server_base):
    base, uid = server_base
    udir = base / uid
    requests_path(udir).write_text(
        json.dumps([
            {
                "id": "req_plain",
                "type": "general",
                "text": "plain request",
                "status": "pending",
                "source": "bob",
            },
            {
                "id": "req_incentive",
                "type": "general",
                "text": "incentivized request",
                "status": "pending",
                "source": "alice",
                "pickup_incentive": {
                    "enabled": True,
                    "terms": "tip after review packet",
                    "pickup_signal_weight": 5.0,
                    "visibility": "public",
                },
                "authority_boundary": {
                    "affects_pickup_priority": True,
                    "affects_acceptance": False,
                    "affects_release": False,
                    "affects_merge": False,
                },
                "request_classification": {
                    "access": {
                        "claimable_by": ["free_daemon", "paid_daemon"],
                        "code_writer_gate": "claude_or_codex",
                        "checker_gate": "opposite_family_checker",
                    },
                    "meaning": "patch",
                    "authority": {
                        "scope": "requester_pickup_only",
                        "boundary": {
                            "affects_pickup_priority": True,
                            "affects_acceptance": False,
                            "affects_release": False,
                            "affects_merge": False,
                        },
                    },
                },
            },
        ]),
        encoding="utf-8",
    )

    created = materialize_pending_requests(udir)
    ranked = choose_authorial_targets(udir, candidate_override=created)

    assert ranked[0].metadata["request_id"] == "req_incentive"
    assert ranked[0].metadata["pickup_incentive"]["enabled"] is True
    assert ranked[0].metadata["request_classification"]["meaning"] == "patch"
    assert "pickup-incentive" in ranked[0].tags
    assert "meaning:patch" in ranked[0].tags
    stored = load_work_targets(udir)
    assert any(t.metadata.get("request_id") == "req_plain" for t in stored)


def test_submit_request_classifies_access_meaning_and_authority(
    server_base,
    monkeypatch,
):
    base, uid = server_base
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")

    response = _submit(
        universe_id=uid,
        text="Patch-loop should classify requests before implementation.",
        request_type="general",
    )

    assert response["request_classification"]["access"] == {
        "claimable_by": ["free_daemon", "paid_daemon"],
        "code_writer_gate": "claude_or_codex",
        "checker_gate": "opposite_family_checker",
    }
    assert response["request_classification"]["meaning"] == "patch"
    assert response["request_classification"]["authority"] == {
        "scope": "requester_pickup_only",
        "boundary": response["authority_boundary"],
    }
    queue = read_queue(base / uid)
    assert (
        queue[0].inputs["request_classification"]
        == response["request_classification"]
    )


def test_filing_effort_classifier_flags_research_ghost_risk():
    result = classify_filing_effort(
        title=(
            "Filing-time effort-class prediction circuit-breaker classifier "
            "for MSR prior art"
        ),
        kind="patch_request",
        observed=(
            "Mechanical filing cites AUC 0.96 on 33K agent PRs and requires "
            "opposite-family checker attention before stall."
        ),
        tags="mechanical",
    )

    assert result["effort_class"] == "ghost-risk"
    assert result["attention"] == "carrier-review-before-daemon-pickup"
    assert "research_prior_art" in result["signals"]
    assert "review_gate" in result["signals"]
    assert result["authority_boundary"]["affects_merge"] is False


def test_filing_effort_classifier_flags_merge_instant_without_ghost_signals():
    result = classify_filing_effort(
        title="Fix typo in connector docs",
        kind="patch_request",
        observed="Mechanical docs-only copy edit with no runtime behavior change.",
    )

    assert result["effort_class"] == "merge-instant"
    assert result["attention"] == "normal-review-gates"
    assert "mechanical_shape" in result["signals"]
    assert "low_runtime_risk" in result["signals"]


def test_requester_directed_daemon_requires_ownership(
    server_base,
    monkeypatch,
):
    base, uid = server_base
    from workflow import daemon_registry

    daemon = daemon_registry.create_daemon(
        base,
        display_name="Alice Patch Runner",
        created_by="alice",
        soul_text="Work on Alice's requested patches.",
    )

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    accepted = _submit(
        universe_id=uid,
        text="Work on the badge request.",
        request_type="branch_proposal",
        directed_daemon_id=daemon["daemon_id"],
        directed_daemon_instruction="Produce a proposal only.",
    )
    queue = read_queue(base / uid)
    assert accepted["requester_directed_daemon"]["effect"] == "applied"
    assert queue[0].trigger_source == "owner_queued"
    assert queue[0].directed_daemon_id == daemon["daemon_id"]
    assert queue[0].inputs["requester_directed_daemon"]["scope"] == "proposal_only"

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    refused = _submit(
        universe_id=uid,
        text="Bob tries to use Alice's daemon.",
        request_type="branch_proposal",
        directed_daemon_id=daemon["daemon_id"],
    )
    assert refused["error"] == "directed_daemon_not_authorized"
