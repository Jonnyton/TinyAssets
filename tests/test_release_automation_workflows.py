"""Regression tests for self-healing merge and release automation."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


_REPO = Path(__file__).resolve().parent.parent
_AUTO_ENROLL = _REPO / ".github" / "workflows" / "auto-enroll-merge.yml"
_RELEASE_RECONCILE = _REPO / ".github" / "workflows" / "release-reconcile.yml"

pytestmark = pytest.mark.skipif(
    not _YAML_AVAILABLE, reason="pyyaml not installed"
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    # PyYAML parses the YAML 1.1 `on:` key as boolean True.
    return workflow.get(True, {}) or {}


def _run_steps(workflow: dict, job_name: str) -> str:
    return "\n".join(
        str(step.get("run", ""))
        for step in workflow["jobs"][job_name]["steps"]
    )


def test_release_reconciler_repairs_a_merge_with_no_workflow_runs():
    """Production drift must cause a build without relying on merge events."""

    workflow = _load(_RELEASE_RECONCILE)
    triggers = _triggers(workflow)
    script = _run_steps(workflow, "reconcile")

    assert triggers.get("schedule"), "release repair must run independently of events"
    assert "deploy-prod.yml/runs?status=success&branch=main" in script
    assert "git merge-base --is-ancestor" in script
    assert "gh workflow run build-image.yml" in script
    assert "--ref main" in script


def test_auto_enroll_periodically_updates_enrolled_prs_behind_main():
    """Strict protection must not strand enrolled PRs after main advances."""

    workflow = _load(_AUTO_ENROLL)
    triggers = _triggers(workflow)
    script = _run_steps(workflow, "update-enrolled-branches")

    assert triggers.get("schedule"), "behind-branch repair must run independently of PR events"
    assert "workflow_dispatch" in triggers
    assert "gh pr list" in script
    assert "--base main" in script
    assert "autoMergeRequest" in script
    assert "mergeStateStatus" in script
    assert "isDraft" in script
    assert "isCrossRepository" in script
    assert 'select(.autoMergeRequest != null)' in script
    assert 'select(.mergeStateStatus == "BEHIND")' in script
    assert 'select(.isDraft == false)' in script
    assert 'select(.isCrossRepository == false)' in script
    assert "gh pr update-branch" in script


def test_event_enrollment_remains_scoped_to_safe_pull_requests():
    workflow = _load(_AUTO_ENROLL)
    job = workflow["jobs"]["enroll"]
    condition = str(job.get("if", ""))

    assert "pull_request_target" in _triggers(workflow)
    assert "github.event_name == 'pull_request_target'" in condition
    assert "pull_request.draft == false" in condition
    assert "pull_request.head.repo.full_name == github.repository" in condition
    assert "pull_request.base.ref == 'main'" in condition
