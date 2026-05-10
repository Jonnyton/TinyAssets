from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path

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


def test_closing_issue_numbers_accepts_common_closing_keywords():
    assert watch._closing_issue_numbers("Fixes #568\nCloses #12; resolves #7") == {
        568,
        12,
        7,
    }


def test_list_open_prs_by_closing_issue_maps_linked_prs(monkeypatch):
    def fake_gh_get(path, **kwargs):
        assert path == "/repos/owner/repo/pulls"
        assert kwargs["params"]["state"] == "open"
        return [
            {
                "number": 598,
                "body": "Fixes #568",
                "html_url": "https://example.test/pull/598",
                "labels": [{"name": watch.READY_FOR_CHECKER_LABEL}],
            },
            {
                "number": 599,
                "body": "Mentions #999 without a closing keyword",
                "html_url": "https://example.test/pull/599",
                "labels": [],
            },
        ]

    monkeypatch.setattr(watch, "_gh_get", fake_gh_get)

    result = watch.list_open_prs_by_closing_issue(
        "owner/repo",
        {568, 999},
        api="https://api.github.test",
        token=None,
        timeout=1,
    )

    assert list(result) == [568]
    assert result[568][0]["number"] == 598


def test_community_loop_watch_workflow_can_read_pull_requests():
    workflow = Path(".github/workflows/community-loop-watch.yml").read_text(encoding="utf-8")

    assert "pull-requests: read" in workflow


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


def test_writer_stage_downgrades_stale_schedule_when_issue_run_succeeds(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 8, 3, 30, tzinfo=dt.timezone.utc)

    def fake_gh_get(*_args, **kwargs):
        params = kwargs.get("params", {})
        scheduled = {
            "id": 44,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-05-08T00:10:00Z",
            "updated_at": "2026-05-08T00:14:00Z",
            "event": "schedule",
            "html_url": "https://example.test/scheduled-success",
        }
        if params.get("event") == "schedule":
            return {"workflow_runs": [scheduled]}
        return {
            "workflow_runs": [
                {
                    "id": 45,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-05-08T02:39:00Z",
                    "updated_at": "2026-05-08T02:40:00Z",
                    "event": "issues",
                    "html_url": "https://example.test/issues-success",
                },
                scheduled,
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
    assert "success is stale" in stage["summary"]
    assert "workflow is productive" in stage["summary"]
    assert stage["details"]["run_id"] == 44
    assert stage["details"]["fallback_run_id"] == 45
    assert stage["details"]["fallback_event"] == "issues"


def test_writer_stage_downgrades_stale_schedule_when_fallback_is_in_progress(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 8, 6, 2, tzinfo=dt.timezone.utc)

    def fake_gh_get(*_args, **kwargs):
        params = kwargs.get("params", {})
        scheduled = {
            "id": 44,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-05-08T03:55:48Z",
            "updated_at": "2026-05-08T03:59:15Z",
            "event": "schedule",
            "html_url": "https://example.test/scheduled-success",
        }
        if params.get("event") == "schedule":
            return {"workflow_runs": [scheduled]}
        return {
            "workflow_runs": [
                {
                    "id": 45,
                    "status": "in_progress",
                    "conclusion": None,
                    "created_at": "2026-05-08T06:01:30Z",
                    "updated_at": "2026-05-08T06:01:45Z",
                    "event": "workflow_dispatch",
                    "html_url": "https://example.test/manual-in-progress",
                },
                scheduled,
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
        fallback_success_events=("workflow_dispatch", "issues", "workflow_run"),
    )

    assert stage["status"] == "yellow"
    assert "run is in_progress" in stage["summary"]
    assert stage["details"]["fallback_run_id"] == 45
    assert stage["details"]["fallback_event"] == "workflow_dispatch"
    assert stage["details"]["fallback_status"] == "in_progress"


def test_build_status_downgrades_stale_writer_schedule_when_workflow_run_succeeds(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 8, 5, 47, tzinfo=dt.timezone.utc)

    stale_schedule = {
        "id": 44,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-05-08T03:55:48Z",
        "updated_at": "2026-05-08T03:59:15Z",
        "event": "schedule",
        "html_url": "https://example.test/auto-fix-schedule",
    }
    recent_workflow_run = {
        "id": 45,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-05-08T04:28:48Z",
        "updated_at": "2026-05-08T04:33:07Z",
        "event": "workflow_run",
        "html_url": "https://example.test/auto-fix-workflow-run",
    }
    fresh_schedule = {
        "id": 46,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-05-08T04:45:00Z",
        "updated_at": "2026-05-08T04:46:00Z",
        "event": "schedule",
        "html_url": "https://example.test/other-schedule",
    }

    def fake_recent_workflow_runs(_repo, workflow_id, **kwargs):
        if workflow_id == watch.WORKFLOWS["writer"]:
            if kwargs.get("event") == "schedule":
                return [stale_schedule]
            return [recent_workflow_run, stale_schedule]
        return [fresh_schedule]

    monkeypatch.setattr(watch, "_recent_workflow_runs", fake_recent_workflow_runs)
    monkeypatch.setattr(watch, "list_loop_issues", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(watch, "list_open_issues_by_label", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(watch, "_github_token", lambda _args: None)

    status = watch.build_status(
        argparse.Namespace(
            repo="owner/repo",
            api="https://api.github.test",
            token=None,
            timeout=1,
            max_sync_age_min=90,
            max_writer_age_min=90,
            max_observation_age_min=90,
            max_pending_age_min=45,
        ),
        now=now,
    )

    writer_stage = [stage for stage in status["stages"] if stage["name"] == "Writer workflow"][0]
    assert status["overall"] == "yellow"
    assert writer_stage["status"] == "yellow"
    assert writer_stage["details"]["run_id"] == 44
    assert writer_stage["details"]["fallback_run_id"] == 45
    assert writer_stage["details"]["fallback_event"] == "workflow_run"


def test_build_status_downgrades_stale_writer_schedule_when_queue_has_only_deferrals(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 8, 5, 47, tzinfo=dt.timezone.utc)
    stale_writer_schedule = {
        "id": 44,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-05-08T03:55:48Z",
        "updated_at": "2026-05-08T03:59:15Z",
        "event": "schedule",
        "html_url": "https://example.test/auto-fix-schedule",
    }
    fresh_schedule = {
        "id": 46,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-05-08T04:45:00Z",
        "updated_at": "2026-05-08T04:46:00Z",
        "event": "schedule",
        "html_url": "https://example.test/other-schedule",
    }

    def fake_recent_workflow_runs(_repo, workflow_id, **kwargs):
        if workflow_id == watch.WORKFLOWS["writer"]:
            return [stale_writer_schedule]
        if kwargs.get("event") == "schedule":
            return [fresh_schedule]
        return [fresh_schedule]

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
                    {"name": watch.AWAIT_PRIMITIVE_LAYER_LABEL},
                ],
            }
        ]

    monkeypatch.setattr(watch, "_recent_workflow_runs", fake_recent_workflow_runs)
    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)
    monkeypatch.setattr(watch, "list_open_issues_by_label", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(watch, "_github_token", lambda _args: None)

    status = watch.build_status(
        argparse.Namespace(
            repo="owner/repo",
            api="https://api.github.test",
            token=None,
            timeout=1,
            max_sync_age_min=90,
            max_writer_age_min=90,
            max_observation_age_min=90,
            max_pending_age_min=45,
        ),
        now=now,
    )

    writer_stage = [stage for stage in status["stages"] if stage["name"] == "Writer workflow"][0]
    queue_stage = [stage for stage in status["stages"] if stage["name"] == "Writer queue"][0]
    assert status["overall"] == "yellow"
    assert writer_stage["status"] == "yellow"
    expected_reason = "no writer-eligible queue (1 await-primitive-layer deferrals)"
    assert expected_reason in writer_stage["evidence"]
    assert writer_stage["details"]["queue_downgrade"] == expected_reason
    assert queue_stage["details"]["await_primitive_layer"] == [541]


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


def test_writer_stage_fetches_required_event_when_general_runs_are_flooded(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 8, 2, 41, tzinfo=dt.timezone.utc)
    calls = []

    def fake_gh_get(*_args, **kwargs):
        params = kwargs.get("params", {})
        calls.append(params)
        if params.get("event") == "schedule":
            return {
                "workflow_runs": [
                    {
                        "id": 90,
                        "status": "completed",
                        "conclusion": "success",
                        "created_at": "2026-05-08T01:52:00Z",
                        "updated_at": "2026-05-08T01:56:00Z",
                        "event": "schedule",
                        "html_url": "https://example.test/scheduled-success",
                    }
                ]
            }
        return {
            "workflow_runs": [
                {
                    "id": issue_run_id,
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-05-08T02:39:00Z",
                    "updated_at": "2026-05-08T02:39:10Z",
                    "event": "issues",
                    "html_url": f"https://example.test/issues-run-{issue_run_id}",
                }
                for issue_run_id in range(100, 200)
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
        per_page=100,
    )

    assert stage["status"] == "green"
    assert stage["details"]["run_id"] == 90
    assert stage["details"]["required_success_event"] == "schedule"
    assert any(call.get("event") == "schedule" for call in calls)


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
    monkeypatch.setattr(watch, "list_open_prs_by_closing_issue", lambda *_, **__: {})

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
    assert stage["details"]["stale_gate"] == []


def test_queue_stage_marks_old_attempted_without_terminal_review_red(monkeypatch):
    now = dt.datetime(2026, 5, 7, 10, 0, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 589,
                "title": "Attempted request with no terminal review",
                "created_at": "2026-05-07T08:00:00Z",
                "html_url": "https://example.test/issues/589",
                "labels": [
                    {"name": "daemon-request"},
                    {"name": "auto-change"},
                    {"name": watch.ATTEMPTED_LABEL},
                ],
            }
        ]

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)
    monkeypatch.setattr(watch, "list_open_prs_by_closing_issue", lambda *_, **__: {})

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["status"] == "red"
    assert stage["details"]["attempted"] == [589]
    assert stage["details"]["stale_gate"] == [589]
    assert watch.STALE_GATE_LABEL in stage["evidence"]


def test_queue_stage_treats_attempted_with_open_pr_as_review_waiting(monkeypatch):
    now = dt.datetime(2026, 5, 8, 3, 30, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 568,
                "title": "Attempted request with linked PR",
                "created_at": "2026-05-07T23:00:00Z",
                "html_url": "https://example.test/issues/568",
                "labels": [
                    {"name": "daemon-request"},
                    {"name": "auto-change"},
                    {"name": watch.ATTEMPTED_LABEL},
                    {"name": watch.STALE_GATE_LABEL},
                ],
            }
        ]

    def fake_open_prs_by_issue(*_args, **_kwargs):
        return {
            568: [
                {
                    "number": 598,
                    "html_url": "https://example.test/pull/598",
                    "labels": [{"name": watch.READY_FOR_CHECKER_LABEL}],
                }
            ]
        }

    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)
    monkeypatch.setattr(watch, "list_open_prs_by_closing_issue", fake_open_prs_by_issue)

    stage = watch.queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
        now=now,
        max_pending_age_min=45,
    )

    assert stage["status"] == "yellow"
    assert stage["details"]["attempted"] == [568]
    assert stage["details"]["stale_gate"] == []
    assert stage["details"]["attempted_with_open_pr"] == [
        {"issue": 568, "prs": [598], "ready_for_checker": [598]}
    ]
    assert "linked open PRs" in stage["summary"]
    assert stage["url"] == "https://example.test/pull/598"


def test_checker_queue_surfaces_independent_checker_blocker(monkeypatch):
    def fake_list_open_issues_by_label(*_args, **_kwargs):
        return [
            {
                "number": 720,
                "title": "Recruiter-readiness bundle",
                "state": "open",
                "html_url": "https://example.test/pull/720",
                "pull_request": {},
                "labels": [
                    {"name": "writer:claude"},
                    {"name": "checker:codex"},
                    {"name": watch.READY_FOR_CHECKER_LABEL},
                    {"name": "priority:urgent"},
                ],
            }
        ]

    def fake_gh_get(path, **_kwargs):
        assert path == "/repos/owner/repo/pulls/720"
        return {"mergeable_state": "clean", "html_url": "https://example.test/pull/720"}

    def fake_gh_get_paginated(path, **_kwargs):
        if path == "/repos/owner/repo/issues/720/comments":
            return [
                {
                    "body": (
                        "Host key recorded: user explicitly said `720 approved`.\n\n"
                        "This same Codex executor session mechanically opened the "
                        "PR, so it is not an independent Codex checker path."
                    )
                }
            ]
        if path == "/repos/owner/repo/pulls/720/reviews":
            return []
        raise AssertionError(path)

    monkeypatch.setattr(watch, "list_open_issues_by_label", fake_list_open_issues_by_label)
    monkeypatch.setattr(watch, "_gh_get", fake_gh_get)
    monkeypatch.setattr(watch, "_gh_get_paginated", fake_gh_get_paginated)

    stage = watch.checker_queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
    )

    assert stage["status"] == "yellow"
    assert "independent checker" in stage["summary"]
    assert stage["details"]["by_state"] == {"needs_independent_codex_checker": [720]}
    assert "current executor is ineligible" in stage["evidence"]
    assert stage["details"]["self_heal_dispatches"] == [
        {
            "workflow_id": "auto-check-pr.yml",
            "pr_number": 720,
            "checker_family": "codex",
            "reason": "blocked_ineligible_checker",
            "inputs": {
                "pr_number": "720",
                "checker_family": "codex",
                "reason": "blocked_ineligible_checker",
            },
        }
    ]


def test_checker_queue_does_not_redispatch_labeled_checker_pr(monkeypatch):
    def fake_list_open_issues_by_label(*_args, **_kwargs):
        return [
            {
                "number": 720,
                "title": "Recruiter-readiness bundle",
                "state": "open",
                "html_url": "https://example.test/pull/720",
                "pull_request": {},
                "labels": [
                    {"name": "writer:claude"},
                    {"name": "checker:codex"},
                    {"name": watch.READY_FOR_CHECKER_LABEL},
                    {"name": watch.AUTO_CHECKER_DISPATCHED_LABEL},
                ],
            }
        ]

    def fake_gh_get_paginated(path, **_kwargs):
        if path == "/repos/owner/repo/issues/720/comments":
            return [
                {
                    "body": (
                        "Host key recorded: user explicitly said `720 approved`.\n\n"
                        "This same Codex executor session mechanically opened the "
                        "PR, so it is not an independent Codex checker path."
                    )
                }
            ]
        raise AssertionError(path)

    monkeypatch.setattr(watch, "list_open_issues_by_label", fake_list_open_issues_by_label)
    monkeypatch.setattr(watch, "_gh_get_paginated", fake_gh_get_paginated)

    stage = watch.checker_queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
    )

    assert stage["status"] == "yellow"
    assert "already dispatched" in stage["summary"]
    assert stage["details"]["self_heal_dispatches"] == []


def test_checker_queue_surfaces_failed_checker_dispatch(monkeypatch):
    def fake_list_open_issues_by_label(*_args, **_kwargs):
        return [
            {
                "number": 720,
                "title": "Recruiter-readiness bundle",
                "state": "open",
                "html_url": "https://example.test/pull/720",
                "pull_request": {},
                "labels": [
                    {"name": "writer:claude"},
                    {"name": "checker:codex"},
                    {"name": watch.READY_FOR_CHECKER_LABEL},
                    {"name": watch.AUTO_CHECKER_FAILED_LABEL},
                ],
            }
        ]

    def fake_gh_get_paginated(path, **_kwargs):
        if path == "/repos/owner/repo/issues/720/comments":
            return [
                {
                    "body": (
                        "Host key recorded: user explicitly said `720 approved`.\n\n"
                        "This same Codex executor session mechanically opened the "
                        "PR, so it is not an independent Codex checker path."
                    )
                }
            ]
        raise AssertionError(path)

    monkeypatch.setattr(watch, "list_open_issues_by_label", fake_list_open_issues_by_label)
    monkeypatch.setattr(watch, "_gh_get_paginated", fake_gh_get_paginated)

    stage = watch.checker_queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
    )

    assert stage["status"] == "yellow"
    assert "failed independent checker dispatch" in stage["summary"]
    assert stage["details"]["failed_independent_checker_dispatches"] == [720]
    assert stage["details"]["self_heal_dispatches"] == []


def test_checker_queue_green_when_no_ready_prs(monkeypatch):
    monkeypatch.setattr(watch, "list_open_issues_by_label", lambda *_args, **_kwargs: [])

    stage = watch.checker_queue_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
    )

    assert stage["status"] == "green"
    assert stage["details"]["ready_for_checker_prs"] == []


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


def test_queue_stage_treats_attempted_await_primitive_layer_as_deferred(
    monkeypatch,
):
    now = dt.datetime(2026, 5, 7, 3, 40, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 376,
                "title": "Attempted request waits for primitive layer",
                "created_at": "2026-05-06T23:46:00Z",
                "html_url": "https://example.test/issues/376",
                "labels": [
                    {"name": "daemon-request"},
                    {"name": "auto-change"},
                    {"name": watch.ATTEMPTED_LABEL},
                    {"name": watch.STALE_GATE_LABEL},
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
    assert stage["details"]["attempted"] == []
    assert stage["details"]["stale_gate"] == []
    assert stage["details"]["await_primitive_layer"] == [376]


def test_queue_stage_treats_complete_attempted_issue_as_terminal(monkeypatch):
    now = dt.datetime(2026, 5, 8, 2, 41, tzinfo=dt.timezone.utc)

    def fake_list_loop_issues(*_args, **_kwargs):
        return [
            {
                "number": 300,
                "title": "Completed request should not keep stale gate red",
                "created_at": "2026-05-05T03:00:00Z",
                "html_url": "https://example.test/issues/300",
                "labels": [
                    {"name": "daemon-request"},
                    {"name": "auto-change"},
                    {"name": watch.ATTEMPTED_LABEL},
                    {"name": watch.STALE_GATE_LABEL},
                    {"name": watch.COMPLETE_LABEL},
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
    assert stage["details"]["attempted"] == []
    assert stage["details"]["stale_gate"] == []
    assert stage["details"]["reviewed_terminal"] == [300]


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


def test_tier3_broken_issue_marks_clone_smoke_stage_red(monkeypatch):
    def fake_list_open_issues_by_label(repo, label, **kwargs):
        assert repo == "owner/repo"
        assert label == watch.TIER3_BROKEN_LABEL
        return [
            {
                "number": 521,
                "title": "Tier-3 OSS clone smoke failed",
                "html_url": "https://example.test/issues/521",
            }
        ]

    monkeypatch.setattr(watch, "list_open_issues_by_label", fake_list_open_issues_by_label)
    monkeypatch.setattr(watch, "_latest_workflow_run", lambda *_, **__: None)

    stage = watch.tier3_clone_smoke_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
    )

    assert stage["status"] == "red"
    assert stage["details"]["open_tier3_broken"] == [521]
    assert "Forever Rule" in stage["summary"]


def test_tier3_broken_issues_are_yellow_when_newer_smoke_success_exists(
    monkeypatch,
):
    def fake_list_open_issues_by_label(*_args, **_kwargs):
        return [
            {
                "number": 506,
                "title": "Tier-3 OSS clone smoke failed",
                "created_at": "2026-05-06T09:37:32Z",
                "html_url": "https://example.test/issues/506",
            }
        ]

    def fake_latest_workflow_run(*_args, **_kwargs):
        return {
            "id": 25488453292,
            "status": "completed",
            "conclusion": "success",
            "created_at": "2026-05-07T09:46:45Z",
            "html_url": "https://example.test/runs/25488453292",
        }

    monkeypatch.setattr(watch, "list_open_issues_by_label", fake_list_open_issues_by_label)
    monkeypatch.setattr(watch, "_latest_workflow_run", fake_latest_workflow_run)

    stage = watch.tier3_clone_smoke_stage(
        "owner/repo",
        api="https://api.github.test",
        token=None,
        timeout=1,
    )

    assert stage["status"] == "yellow"
    assert stage["details"]["open_tier3_broken"] == [506]
    assert stage["details"]["latest_run_id"] == 25488453292
    assert "newer than 1 open" in stage["summary"]


def test_build_status_is_red_when_tier3_broken_issue_is_open(monkeypatch):
    now = dt.datetime(2026, 5, 6, 12, 0, tzinfo=dt.timezone.utc)

    def fake_recent_workflow_runs(*_args, **_kwargs):
        return [
            {
                "id": 1,
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-05-06T11:50:00Z",
                "updated_at": "2026-05-06T11:51:00Z",
                "event": "schedule",
                "html_url": "https://example.test/runs/1",
            }
        ]

    def fake_list_loop_issues(*_args, **_kwargs):
        return []

    def fake_list_open_issues_by_label(_repo, label, **_kwargs):
        if label == watch.TIER3_BROKEN_LABEL:
            return [
                {
                    "number": 521,
                    "title": "Tier-3 OSS clone smoke failed",
                    "html_url": "https://example.test/issues/521",
                }
            ]
        return []

    monkeypatch.setattr(watch, "_recent_workflow_runs", fake_recent_workflow_runs)
    monkeypatch.setattr(watch, "list_loop_issues", fake_list_loop_issues)
    monkeypatch.setattr(watch, "list_open_issues_by_label", fake_list_open_issues_by_label)
    monkeypatch.setattr(watch, "_github_token", lambda _args: None)

    status = watch.build_status(
        argparse.Namespace(
            repo="owner/repo",
            api="https://api.github.test",
            token=None,
            timeout=1,
            max_sync_age_min=90,
            max_writer_age_min=90,
            max_observation_age_min=90,
            max_pending_age_min=45,
        ),
        now=now,
    )

    assert status["overall"] == "red"
    assert status["exit_code"] == 2
    assert [stage for stage in status["stages"] if stage["name"] == "Tier-3 clone smoke"][0][
        "status"
    ] == "red"
