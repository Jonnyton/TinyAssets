"""Smoke: load-bearing docs survived the clone.

AGENTS.md, PLAN.md, STATUS.md are the three living files (AGENTS.md
§Three Living Files). If any disappears from main, every orient-first
AI agent starts with incomplete context — silent onboarding failure.
"""

from __future__ import annotations

from pathlib import Path

# Repo root = three levels up from this file (tests/smoke/test_*.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_agents_md_exists():
    assert (_REPO_ROOT / "AGENTS.md").is_file(), "AGENTS.md missing from repo root"


def test_plan_md_exists():
    assert (_REPO_ROOT / "PLAN.md").is_file(), "PLAN.md missing from repo root"


def test_status_md_exists():
    assert (_REPO_ROOT / "STATUS.md").is_file(), "STATUS.md missing from repo root"


def test_pyproject_has_tinyassets_name():
    pyproject = _REPO_ROOT / "pyproject.toml"
    assert pyproject.is_file(), "pyproject.toml missing from repo root"
    content = pyproject.read_text(encoding="utf-8")
    assert 'name = "tinyassets"' in content, "pyproject.toml package name drifted"
    assert 'name = "workflow"' not in content, "old package name leaked back into pyproject.toml"
