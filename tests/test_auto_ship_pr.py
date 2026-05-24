"""Tests for feature-flagged auto-ship PR creation."""

from __future__ import annotations

from pathlib import Path

from workflow.auto_ship_ledger import ShipAttempt, find_attempt, record_attempt
from workflow.auto_ship_pr import PR_CREATE_FLAG, open_auto_ship_pr


def _attempt(
    *,
    ship_attempt_id: str = "ship_1",
    ship_status: str = "skipped",
    would_open_pr: bool = True,
    pr_url: str = "",
) -> ShipAttempt:
    return ShipAttempt(
        ship_attempt_id=ship_attempt_id,
        created_at="2026-05-03T00:00:00+00:00",
        updated_at="2026-05-03T00:00:00+00:00",
        ship_status=ship_status,
        request_id="BUG-999",
        release_gate_result="APPROVE_AUTO_SHIP",
        ship_class="docs_canary",
        pr_url=pr_url,
        would_open_pr=would_open_pr,
    )


def _record(tmp_path: Path, **kwargs) -> str:
    row = _attempt(**kwargs)
    record_attempt(tmp_path, row)
    return row.ship_attempt_id


def test_disabled_by_default_records_pr_create_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv(PR_CREATE_FLAG, raising=False)
    attempt_id = _record(tmp_path)

    def should_not_post(url, token, payload):  # pragma: no cover - failure path
        raise AssertionError("disabled mode must not call GitHub")

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        post_json=should_not_post,
    )

    assert result["ship_status"] == "skipped"
    assert result["dry_run"] is True
    assert result["error_class"] == "pr_create_disabled"
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "skipped"
    assert row.error_class == "pr_create_disabled"


def test_enabled_rejects_non_auto_change_head(tmp_path):
    attempt_id = _record(tmp_path)

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="feature/not-allowed",
        title="[auto-change] BUG-999",
        create_enabled=True,
        token="gh-token",
    )

    assert result["ship_status"] == "failed"
    assert result["error_class"] == "pr_create_invalid_request"
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "failed"
    assert row.error_class == "pr_create_invalid_request"


def test_enabled_requires_token(tmp_path):
    attempt_id = _record(tmp_path)

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        create_enabled=True,
        token="",
    )

    assert result["ship_status"] == "failed"
    assert result["error_class"] == "pr_create_missing_token"
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "failed"


def test_enabled_creates_pr_and_updates_ledger(tmp_path):
    attempt_id = _record(tmp_path)
    calls = []

    def fake_get(url, token):
        calls.append((url, token, None))
        return 200, {"status": "ahead", "behind_by": 0}

    def fake_post(url, token, payload):
        calls.append((url, token, payload))
        return 201, {
            "html_url": "https://github.com/Jonnyton/Workflow/pull/999",
            "number": 999,
            "head": {"sha": "abc123"},
        }

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        body="test body",
        create_enabled=True,
        token="gh-token",
        get_json=fake_get,
        post_json=fake_post,
    )

    assert result["ship_status"] == "opened"
    assert result["dry_run"] is False
    assert result["pr_url"] == "https://github.com/Jonnyton/Workflow/pull/999"
    assert result["commit_sha"] == "abc123"
    assert calls == [
        (
            "https://api.github.com/repos/Jonnyton/Workflow/compare/main...auto-change%2Fissue-999-codex-123",
            "gh-token",
            None,
        ),
        (
            "https://api.github.com/repos/Jonnyton/Workflow/pulls",
            "gh-token",
            {
                "title": "[auto-change] BUG-999",
                "head": "auto-change/issue-999-codex-123",
                "base": "main",
                "body": "test body",
                "draft": False,
            },
        ),
    ]
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "opened"
    assert row.pr_url == "https://github.com/Jonnyton/Workflow/pull/999"
    assert row.commit_sha == "abc123"
    assert row.ci_status == "pending"
    assert row.rollback_handle == "pr:https://github.com/Jonnyton/Workflow/pull/999"


def test_existing_open_pr_is_idempotent(tmp_path):
    attempt_id = _record(
        tmp_path,
        ship_status="opened",
        pr_url="https://github.com/Jonnyton/Workflow/pull/123",
    )

    def should_not_post(url, token, payload):  # pragma: no cover - failure path
        raise AssertionError("opened attempt must not create another PR")

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        create_enabled=True,
        token="gh-token",
        post_json=should_not_post,
    )

    assert result["ship_status"] == "opened"
    assert result["already_open"] is True
    assert result["pr_url"] == "https://github.com/Jonnyton/Workflow/pull/123"


def test_github_api_failure_records_failed(tmp_path):
    attempt_id = _record(tmp_path)

    def fake_get(url, token):
        return 200, {"status": "ahead", "behind_by": 0}

    def fake_post(url, token, payload):
        return 422, {"message": "Validation Failed"}

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        create_enabled=True,
        token="gh-token",
        get_json=fake_get,
        post_json=fake_post,
    )

    assert result["ship_status"] == "failed"
    assert result["error_class"] == "pr_create_failed"
    assert "HTTP 422" in result["error_message"]
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "failed"
    assert row.error_class == "pr_create_failed"


def test_github_network_exception_records_failed(tmp_path):
    attempt_id = _record(tmp_path)

    def fake_get(url, token):
        return 200, {"status": "ahead", "behind_by": 0}

    def fake_post(url, token, payload):
        raise OSError("network down")

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        create_enabled=True,
        token="gh-token",
        get_json=fake_get,
        post_json=fake_post,
    )

    assert result["ship_status"] == "failed"
    assert result["error_class"] == "pr_create_failed"
    assert "network down" in result["error_message"]
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "failed"
    assert row.error_class == "pr_create_failed"
    assert "network down" in row.error_message


def test_enabled_rejects_stale_head_before_pr_creation(tmp_path):
    attempt_id = _record(tmp_path)
    calls = []

    def fake_get(url, token):
        calls.append(("get", url, token))
        return 200, {"status": "diverged", "behind_by": 3}

    def should_not_post(url, token, payload):  # pragma: no cover - failure path
        raise AssertionError("stale head must not create a PR")

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        create_enabled=True,
        token="gh-token",
        get_json=fake_get,
        post_json=should_not_post,
    )

    assert result["ship_status"] == "failed"
    assert result["error_class"] == "pr_create_stale_head"
    assert "behind/diverged" in result["error_message"]
    assert result["head_branch"] == "auto-change/issue-999-codex-123"
    assert result["base_branch"] == "main"
    assert calls == [(
        "get",
        "https://api.github.com/repos/Jonnyton/Workflow/compare/main...auto-change%2Fissue-999-codex-123",
        "gh-token",
    )]
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "failed"
    assert row.error_class == "pr_create_stale_head"


def test_blocked_attempt_is_not_eligible_for_pr_creation(tmp_path):
    attempt_id = _record(
        tmp_path,
        ship_status="blocked",
        would_open_pr=False,
    )

    result = open_auto_ship_pr(
        universe_path=tmp_path,
        ship_attempt_id=attempt_id,
        head_branch="auto-change/issue-999-codex-123",
        title="[auto-change] BUG-999",
        create_enabled=True,
        token="gh-token",
    )

    assert result["ship_status"] == "blocked"
    assert result["error_class"] == "ship_attempt_not_eligible"
    row = find_attempt(tmp_path, attempt_id)
    assert row is not None
    assert row.ship_status == "blocked"
