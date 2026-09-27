"""Pin the trigger cuts that keep PR CI from starving on runners.

The repo is user-owned, so GitHub-hosted jobs are capped at about 20 concurrent
across every PR, main push and deploy. On 2026-09-27 two triggers spent about
2,150 of about 4,300 runner-minutes in 4 h without gating anything, and the
deploy job waited 22 min for a runner. See
docs/design-notes/2026-09-27-lean-ci-pipeline.md. A quiet revert of either cut
brings that back, and nothing else would notice.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _triggers(name: str) -> dict:
    wf = yaml.safe_load((_WORKFLOWS / name).read_text(encoding="utf-8"))
    # PyYAML parses a bare `on:` key as the boolean True.
    return wf[True] if True in wf else wf["on"]


def test_desktop_installer_matrix_does_not_run_on_pull_requests() -> None:
    triggers = _triggers("desktop-release.yml")
    assert "pull_request" not in triggers and "pull_request_target" not in triggers
    # The cut moves the work, it does not delete it: landed changes still build.
    assert triggers["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in triggers


def test_docker_smoke_push_runs_only_on_main() -> None:
    triggers = _triggers("docker-build.yml")
    assert triggers["push"].get("branches") == ["main"], (
        "an unfiltered push trigger builds every agent-branch push on top of "
        "that branch's PR run"
    )
    assert "pull_request" in triggers, "PRs must still get the Docker smoke"


def test_mobile_builds_do_not_run_on_pull_requests() -> None:
    """Lean pipeline: no platform builds on PRs; landed changes still build."""
    for name in ("android-build.yml", "ios-build.yml"):
        triggers = _triggers(name)
        assert "pull_request" not in triggers, name
        assert "main" in triggers["push"]["branches"], name
        assert "workflow_dispatch" in triggers, name
