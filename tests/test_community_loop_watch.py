from __future__ import annotations

import argparse
import datetime as dt
import subprocess

from scripts import community_loop_watch as watch


def test_github_token_prefers_explicit_argument(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    def fail_run(*_args, **_kwargs):
        raise AssertionError("gh CLI should not be used when --token is set")

    monkeypatch.setattr(watch.subprocess, "run", fail_run)

    assert watch._github_token(argparse.Namespace(token="arg-token")) == "arg-token"


def test_github_token_uses_environment_before_gh_cli(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")

    def fail_run(*_args, **_kwargs):
        raise AssertionError("gh CLI should not be used when GITHUB_TOKEN is set")

    monkeypatch.setattr(watch.subprocess, "run", fail_run)

    assert watch._github_token(argparse.Namespace(token=None)) == "env-token"


def test_github_token_falls_back_to_gh_cli(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="cli-token\n", stderr="")

    monkeypatch.setattr(watch.subprocess, "run", fake_run)

    assert watch._github_token(argparse.Namespace(token=None)) == "cli-token"
    assert calls[0][0] == ["gh", "auth", "token"]
    assert calls[0][1]["capture_output"] is True


def test_github_token_returns_none_when_gh_cli_unavailable(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(watch.subprocess, "run", fake_run)

    assert watch._github_token(argparse.Namespace(token=None)) is None


def test_workflow_stage_ignores_neutral_skipped_runs(monkeypatch):
    now = dt.datetime(2026, 5, 1, 5, 10, tzinfo=dt.timezone.utc)

    def fake_gh_get(*_args, **_kwargs):
        return {
            "workflow_runs": [
                {
                    "id": 2,
                    "status": "completed",
                    "conclusion": "skipped",
                    "created_at": "2026-05-01T05:09:00Z",
                    "updated_at": "2026-05-01T05:09:01Z",
                    "event": "workflow_run",
                    "html_url": "https://example.test/skipped",
                },
                {
                    "id": 1,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-05-01T05:04:00Z",
                    "updated_at": "2026-05-01T05:05:00Z",
                    "event": "workflow_run",
                    "html_url": "https://example.test/success",
                },
            ]
        }

    monkeypatch.setattr(watch, "_gh_get", fake_gh_get)

    stage = watch.workflow_stage(
        "Production deploy",
        "owner/repo",
        "deploy-prod.yml",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_age_min=None,
    )

    assert stage["status"] == "green"
    assert stage["details"]["run_id"] == 1
    assert stage["details"]["ignored_skipped_run_ids"] == [2]


def test_workflow_stage_keeps_in_progress_meaningful_run(monkeypatch):
    now = dt.datetime(2026, 5, 1, 5, 10, tzinfo=dt.timezone.utc)

    def fake_gh_get(*_args, **_kwargs):
        return {
            "workflow_runs": [
                {
                    "id": 3,
                    "status": "in_progress",
                    "conclusion": None,
                    "created_at": "2026-05-01T05:09:00Z",
                    "updated_at": "2026-05-01T05:09:30Z",
                    "event": "push",
                    "html_url": "https://example.test/in-progress",
                },
                {
                    "id": 2,
                    "status": "completed",
                    "conclusion": "skipped",
                    "created_at": "2026-05-01T05:08:00Z",
                    "updated_at": "2026-05-01T05:08:01Z",
                    "event": "workflow_run",
                    "html_url": "https://example.test/skipped",
                },
            ]
        }

    monkeypatch.setattr(watch, "_gh_get", fake_gh_get)

    stage = watch.workflow_stage(
        "Writer workflow",
        "owner/repo",
        "auto-fix-bug.yml",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_age_min=90,
    )

    assert stage["status"] == "yellow"
    assert stage["details"]["run_id"] == 3


def test_writer_stage_requires_recent_schedule_backfill_run_without_fallback(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 5, 0, 0, tzinfo=dt.timezone.utc)

    def fake_gh_get(*_args, **_kwargs):
        return {
            "workflow_runs": [
                {
                    "id": 42,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-05-04T23:58:00Z",
                    "updated_at": "2026-05-04T23:59:00Z",
                    "event": "workflow_dispatch",
                    "html_url": "https://example.test/manual-success",
                }
            ]
        }

    monkeypatch.setattr(watch, "_gh_get", fake_gh_get)

    stage = watch.workflow_stage(
        "Writer workflow",
        "owner/repo",
        "auto-fix-bug.yml",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_age_min=90,
        required_success_event="schedule",
    )

    assert stage["status"] == "red"
    assert "schedule backfill" in stage["summary"]
    assert stage["details"]["required_success_event"] == "schedule"
    assert stage["details"]["latest_event"] == "workflow_dispatch"


def test_writer_stage_downgrades_cancelled_schedule_when_dispatch_succeeds(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 5, 0, 0, tzinfo=dt.timezone.utc)

    def fake_gh_get(*_args, **_kwargs):
        return {
            "workflow_runs": [
                {
                    "id": 43,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-05-04T23:58:00Z",
                    "updated_at": "2026-05-04T23:59:00Z",
                    "event": "workflow_dispatch",
                    "html_url": "https://example.test/manual-success",
                },
                {
                    "id": 44,
                    "status": "completed",
                    "conclusion": "cancelled",
                    "created_at": "2026-05-04T23:37:00Z",
                    "updated_at": "2026-05-04T23:38:00Z",
                    "event": "schedule",
                    "html_url": "https://example.test/scheduled-cancelled",
                },
            ]
        }

    monkeypatch.setattr(watch, "_gh_get", fake_gh_get)

    stage = watch.workflow_stage(
        "Writer workflow",
        "owner/repo",
        "auto-fix-bug.yml",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_age_min=90,
        required_success_event="schedule",
        fallback_success_events=("workflow_dispatch", "issues"),
    )

    assert stage["status"] == "yellow"
    assert "workflow is dispatchable" in stage["summary"]
    assert stage["details"]["run_id"] == 44
    assert stage["details"]["fallback_run_id"] == 43
    assert stage["details"]["fallback_event"] == "workflow_dispatch"


def test_writer_stage_uses_scheduled_success_when_other_runs_are_newer(monkeypatch):
    now = dt.datetime(2026, 5, 5, 0, 0, tzinfo=dt.timezone.utc)

    def fake_gh_get(*_args, **_kwargs):
        return {
            "workflow_runs": [
                {
                    "id": 43,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-05-04T23:58:00Z",
                    "updated_at": "2026-05-04T23:59:00Z",
                    "event": "workflow_dispatch",
                    "html_url": "https://example.test/manual-success",
                },
                {
                    "id": 44,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-05-04T23:37:00Z",
                    "updated_at": "2026-05-04T23:38:00Z",
                    "event": "schedule",
                    "html_url": "https://example.test/scheduled-success",
                },
            ]
        }

    monkeypatch.setattr(watch, "_gh_get", fake_gh_get)

    stage = watch.workflow_stage(
        "Writer workflow",
        "owner/repo",
        "auto-fix-bug.yml",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_age_min=90,
        required_success_event="schedule",
    )

    assert stage["status"] == "green"
    assert stage["details"]["run_id"] == 44
    assert stage["details"]["required_success_event"] == "schedule"


def test_queue_stage_counts_push_blocked_issue_as_needs_human(monkeypatch):
    now = dt.datetime(2026, 5, 5, 4, 20, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 298,
                "title": "Writer produced a patch but could not push it",
                "created_at": "2026-05-05T03:00:00Z",
                "html_url": "https://example.test/issues/298",
                "labels": [
                    {"name": watch.BLOCKED_LABEL},
                    {"name": watch.ATTEMPTED_LABEL},
                    {"name": watch.REVIEWED_LABEL},
                    {"name": watch.BRANCH_PUSH_BLOCKED_LABEL},
                ],
            }
        ]

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["status"] == "red"
    assert stage["details"]["needs_human"] == [298]
    assert stage["details"]["reviewed_terminal"] == []


def test_queue_stage_counts_pr_blocked_issue_as_needs_human(monkeypatch):
    now = dt.datetime(2026, 5, 5, 21, 20, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 70,
                "title": "Writer pushed a branch but could not open the PR",
                "created_at": "2026-05-01T01:00:00Z",
                "html_url": "https://example.test/issues/70",
                "labels": [
                    {"name": watch.BLOCKED_LABEL},
                    {"name": watch.ATTEMPTED_LABEL},
                    {"name": watch.REVIEWED_LABEL},
                    {"name": watch.CLAUDE_SUBSCRIPTION_MISSING_LABEL},
                    {"name": watch.PR_BLOCKED_LABEL},
                ],
            }
        ]

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["status"] == "red"
    assert stage["details"]["needs_human"] == [70]
    assert stage["details"]["pr_blocked"] == [70]
    assert stage["details"]["reviewed_terminal"] == []
    assert "PR creation was blocked" in stage["summary"]


def test_queue_stage_summarizes_mixed_permission_blocks(monkeypatch):
    now = dt.datetime(2026, 5, 5, 21, 20, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 87,
                "title": "Writer could not push the branch",
                "created_at": "2026-04-30T23:00:00Z",
                "html_url": "https://example.test/issues/87",
                "labels": [
                    {"name": watch.BLOCKED_LABEL},
                    {"name": watch.ATTEMPTED_LABEL},
                    {"name": watch.REVIEWED_LABEL},
                    {"name": watch.BRANCH_PUSH_BLOCKED_LABEL},
                ],
            },
            {
                "number": 70,
                "title": "Writer could not open the PR",
                "created_at": "2026-05-01T01:00:00Z",
                "html_url": "https://example.test/issues/70",
                "labels": [
                    {"name": watch.BLOCKED_LABEL},
                    {"name": watch.ATTEMPTED_LABEL},
                    {"name": watch.REVIEWED_LABEL},
                    {"name": watch.PR_BLOCKED_LABEL},
                ],
            },
        ]

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["details"]["branch_push_blocked"] == [87]
    assert stage["details"]["pr_blocked"] == [70]
    assert "branch-push and PR-creation permission blocks" in stage["summary"]


def test_queue_stage_treats_attempted_loop_smoke_as_not_waiting(monkeypatch):
    now = dt.datetime(2026, 5, 2, 19, 30, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 178,
                "title": "[BUG-046] Loop circuit smoke test 2026-05-02 1902 UTC",
                "created_at": "2026-05-02T19:21:43Z",
                "html_url": "https://example.test/issues/178",
                "labels": [
                    {"name": "daemon-request"},
                    {"name": "auto-change"},
                    {"name": "auto-bug"},
                    {"name": "request:bug"},
                    {"name": "severity:minor"},
                    {"name": watch.ATTEMPTED_LABEL},
                ],
            }
        ]

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["status"] == "green"
    assert stage["details"]["attempted"] == [178]
    assert stage["details"]["pending"] == []
    assert stage["details"]["old_pending"] == []


def test_queue_stage_treats_await_primitive_layer_as_deferred_not_stuck(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 7, 3, 40, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 541,
                "title": "Single-server architecture waits for primitive layer",
                "created_at": "2026-05-06T23:46:00Z",
                "html_url": "https://example.test/issues/541",
                "labels": [
                    {"name": "daemon-request"},
                    {"name": "auto-change"},
                    {"name": "request:project-design"},
                    {"name": watch.AWAIT_PRIMITIVE_LAYER_LABEL},
                ],
            }
        ]

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["status"] == "yellow"
    assert stage["details"]["pending"] == []
    assert stage["details"]["old_pending"] == []
    assert stage["details"]["await_primitive_layer"] == [541]
    assert "intentionally waiting" in stage["summary"]


def test_queue_stage_maps_legacy_priority_labels_before_pending_stuck(monkeypatch):
    now = dt.datetime(2026, 5, 6, 21, 20, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 511,
                "title": "Old priority taxonomy request",
                "created_at": "2026-05-06T18:00:00Z",
                "html_url": "https://example.test/issues/511",
                "labels": [
                    {"name": "daemon-request"},
                    {"name": "auto-change"},
                    {"name": "loop-discipline"},
                ],
            }
        ]

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["status"] == "yellow"
    assert stage["details"]["old_pending"] == []
    assert stage["details"]["legacy_priority_migrations"] == [
        {
            "issue": 511,
            "legacy_label": "loop-discipline",
            "mapped_label": "priority:loop-discipline",
        }
    ]
    assert "legacy unprefixed priority label" in stage["summary"]
