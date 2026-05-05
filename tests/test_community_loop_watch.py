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
