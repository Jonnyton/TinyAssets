"""Smoke: load-bearing docs survived the clone.

AGENTS.md and PLAN.md are the two living files (AGENTS.md §Two Living Files).
If either disappears from main, every orient-first AI agent starts with
incomplete context — a silent onboarding failure.

STATUS.md was the third until 2026-08-25. Its absence is now asserted, not
tolerated: re-adding it would quietly restore the always-loaded coordination
blob the reset removed, and a smoke test is exactly where that should be
caught. Live state has typed homes instead — see AGENTS.md §Two Living Files.
"""

from __future__ import annotations

from pathlib import Path

# Repo root = three levels up from this file (tests/smoke/test_*.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_agents_md_exists():
    assert (_REPO_ROOT / "AGENTS.md").is_file(), "AGENTS.md missing from repo root"


def test_plan_md_exists():
    assert (_REPO_ROOT / "PLAN.md").is_file(), "PLAN.md missing from repo root"


def test_status_md_stays_retired():
    assert not (_REPO_ROOT / "STATUS.md").exists(), (
        "STATUS.md is back. It was retired 2026-08-25 (5.2x over its own declared "
        "ceiling, 46% of 90 days of commits). Live state belongs in the typed homes "
        "listed in AGENTS.md §Two Living Files, not in one always-loaded file."
    )


def test_pyproject_has_tinyassets_name():
    pyproject = _REPO_ROOT / "pyproject.toml"
    assert pyproject.is_file(), "pyproject.toml missing from repo root"
    content = pyproject.read_text(encoding="utf-8")
    assert 'name = "tinyassets"' in content, "pyproject.toml package name drifted"
    assert 'name = "workflow"' not in content, "old package name leaked back into pyproject.toml"
