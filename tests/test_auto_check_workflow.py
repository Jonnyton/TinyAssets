"""Static tests for .github/workflows/auto-check-pr.yml."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "auto-check-pr.yml"
COMMUNITY_WATCH = REPO_ROOT / ".github" / "workflows" / "community-loop-watch.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_auto_check_is_dispatch_only():
    wf = _workflow()
    triggers = wf.get(True, wf.get("on", {}))

    assert "workflow_dispatch" in triggers
    assert "schedule" not in triggers
    assert "push" not in triggers


def test_auto_check_uses_pr_scoped_concurrency():
    wf = _workflow()
    concurrency = wf.get("concurrency", {})

    assert "inputs.pr_number" in concurrency.get("group", "")
    assert concurrency.get("cancel-in-progress") is False


def test_auto_check_has_checker_permissions_not_writer_permissions():
    wf = _workflow()
    permissions = wf.get("permissions", {})

    assert permissions.get("contents") == "read"
    assert permissions.get("issues") == "write"
    assert permissions.get("pull-requests") == "write"


def test_community_watch_can_mark_checker_prs_without_content_write():
    wf = yaml.safe_load(COMMUNITY_WATCH.read_text(encoding="utf-8"))
    permissions = wf.get("permissions", {})

    assert permissions.get("contents") == "read"
    assert permissions.get("issues") == "write"
    assert permissions.get("pull-requests") == "write"
    assert permissions.get("actions") == "write"


def test_auto_check_codex_lane_posts_structured_verdict_marker():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "WORKFLOW_CODEX_AUTH_JSON_B64" in text
    assert "workflow-checker-verdict:v1 family=codex" in text
    assert "verdict=${markerVerdict}" in text
    assert "head=${process.env.HEAD_SHA}" in text
    assert "Do not commit, push, merge" in text


def test_community_watch_dispatches_auto_check_workflow():
    text = COMMUNITY_WATCH.read_text(encoding="utf-8")

    assert '"Auto-check PR"' in text
    assert "self_heal_dispatches" in text
    assert "auto-check-pr.yml" in text
    assert "auto-checker-dispatched" in text
