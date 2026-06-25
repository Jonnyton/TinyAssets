"""Tests for scripts/community_loop_watch.py after cheat-loop retirement."""

from __future__ import annotations

import argparse
import datetime as dt

from scripts import community_loop_watch as watch


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        repo="owner/repo",
        api="https://api.test",
        token=None,
        timeout=1.0,
        max_observation_age_min=90,
        json=False,
    )


def _success_run(workflow_id: str, created_at: str = "2026-06-25T12:00:00Z") -> dict:
    return {
        "id": f"{workflow_id}:1",
        "status": "completed",
        "conclusion": "success",
        "event": "schedule",
        "created_at": created_at,
        "html_url": f"https://example.test/{workflow_id}",
    }


def test_build_status_keeps_only_uptime_deploy_and_tier3_stages(monkeypatch) -> None:
    monkeypatch.setattr(
        watch,
        "_latest_workflow_run",
        lambda _repo, workflow_id, **_kwargs: _success_run(workflow_id),
    )
    monkeypatch.setattr(
        watch,
        "list_open_issues_by_label",
        lambda *_args, **_kwargs: [],
    )

    status = watch.build_status(
        _args(),
        now=dt.datetime(2026, 6, 25, 12, 5, tzinfo=dt.timezone.utc),
    )

    assert status["overall"] == "green"
    assert [stage["name"] for stage in status["stages"]] == [
        "Observation canary",
        "Observation incidents",
        "Tier-3 clone smoke",
        "Production deploy",
        "Website deploy",
    ]


def test_build_status_does_not_read_deleted_cheat_loop_workflows(monkeypatch) -> None:
    seen: list[str] = []

    def fake_latest(_repo: str, workflow_id: str, **_kwargs) -> dict:
        seen.append(workflow_id)
        return _success_run(workflow_id)

    monkeypatch.setattr(watch, "_latest_workflow_run", fake_latest)
    monkeypatch.setattr(watch, "list_open_issues_by_label", lambda *_args, **_kwargs: [])

    watch.build_status(
        _args(),
        now=dt.datetime(2026, 6, 25, 12, 5, tzinfo=dt.timezone.utc),
    )

    retired_workflows = [
        "wiki-" + "bug-sync.yml",
        "auto-" + "fix-bug.yml",
        "auto-" + "check-pr.yml",
    ]
    for workflow_id in retired_workflows:
        assert workflow_id not in seen


def test_observation_canary_staleness_still_goes_red(monkeypatch) -> None:
    monkeypatch.setattr(
        watch,
        "_latest_workflow_run",
        lambda _repo, workflow_id, **_kwargs: _success_run(
            workflow_id,
            created_at="2026-06-25T10:00:00Z",
        ),
    )
    monkeypatch.setattr(watch, "list_open_issues_by_label", lambda *_args, **_kwargs: [])

    status = watch.build_status(
        _args(),
        now=dt.datetime(2026, 6, 25, 12, 5, tzinfo=dt.timezone.utc),
    )

    observation = status["stages"][0]
    assert observation["name"] == "Observation canary"
    assert observation["status"] == "red"
    assert status["overall"] == "red"


def test_open_p0_outage_still_goes_red(monkeypatch) -> None:
    def fake_issues(_repo: str, label: str, **_kwargs) -> list[dict]:
        if label == watch.P0_OUTAGE_LABEL:
            return [
                {
                    "number": 44,
                    "title": "MCP canary red",
                    "html_url": "https://example.test/issues/44",
                }
            ]
        return []

    monkeypatch.setattr(
        watch,
        "_latest_workflow_run",
        lambda _repo, workflow_id, **_kwargs: _success_run(workflow_id),
    )
    monkeypatch.setattr(watch, "list_open_issues_by_label", fake_issues)

    status = watch.build_status(
        _args(),
        now=dt.datetime(2026, 6, 25, 12, 5, tzinfo=dt.timezone.utc),
    )

    incident = next(stage for stage in status["stages"] if stage["name"] == "Observation incidents")
    assert incident["status"] == "red"
    assert incident["details"] == {"open_p0_outages": [44]}
    assert status["overall"] == "red"
