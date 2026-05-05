"""Regression checks for the wiki bug sync GitHub Actions workflow."""

from __future__ import annotations

from pathlib import Path

WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "wiki-bug-sync.yml"
)


def test_sync_state_push_rebases_and_retries_when_main_advances():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "for attempt in 1 2 3; do" in workflow
    assert 'git push origin "HEAD:${branch}"' in workflow
    assert 'git fetch origin "$branch"' in workflow
    assert 'git rebase "origin/${branch}"' in workflow
    assert "Sync state push rejected; rebasing" in workflow
