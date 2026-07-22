"""`.agents/activity.log` must union-merge, so concurrent lanes stop colliding.

The log is append-only: every lane appends its entry to the end of the same
file. Two lanes that both append therefore conflict on the final hunk *by
construction* — a structural conflict, not a semantic one. On 2026-07-22 this
blocked PRs #1506 and #1507 simultaneously, and a manual rebase of #1507 was
invalidated six minutes later when #1501 merged and touched the same file.

`merge=union` in `.gitattributes` is git's built-in driver for this case: it
concatenates both sides instead of raising a conflict.

These tests exercise the *actual merge machinery* rather than asserting that a
line exists in `.gitattributes` — a config-text check would pass even if the
rule had no runtime effect. The control test is what proves the treatment test
can go red: it runs the identical collision with the rule stripped out and
asserts that git really does conflict there.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ".agents/activity.log"

# Mirrors the real collision shape: main landed a multi-line block (#1501),
# each PR appended a single line.
MAIN_SIDE = "\n2026-07-22 [lane-A] MAIN-SIDE ENTRY.\n- MAIN-SIDE bullet.\n"
PR_SIDE = "2026-07-22 [lane-B] PR-SIDE ENTRY.\n"


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _build_collision(root: Path, *, union: bool) -> subprocess.CompletedProcess:
    """Build a two-branch append collision and return the merge result.

    With ``union=True`` the throwaway repo carries the union rule; otherwise it
    carries a `.gitattributes` with the rule absent, which is the control.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "test", cwd=root)
    # Deterministic line endings regardless of host platform.
    _git("config", "core.autocrlf", "false", cwd=root)

    attributes = f"{LOG_PATH} merge=union\n" if union else "*.py text eol=lf\n"
    (root / ".gitattributes").write_text(attributes, encoding="utf-8")
    log = root / LOG_PATH
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("2026-07-01 [seed] base entry.\n", encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "base", cwd=root)
    base = _git("rev-parse", "HEAD", cwd=root).stdout.strip()

    _git("checkout", "-q", "-b", "lane-a", base, cwd=root)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(MAIN_SIDE)
    _git("commit", "-q", "-am", "lane A appends", cwd=root)

    _git("checkout", "-q", "-b", "lane-b", base, cwd=root)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(PR_SIDE)
    _git("commit", "-q", "-am", "lane B appends", cwd=root)

    return _git("merge", "--no-edit", "lane-a", cwd=root, check=False)


def test_union_rule_is_declared_for_the_activity_log() -> None:
    """The real repo carries the rule (necessary, not sufficient — see below)."""
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert f"{LOG_PATH} merge=union" in attributes


def test_control_append_collision_conflicts_without_the_union_rule(
    tmp_path: Path,
) -> None:
    """Without the rule the collision really does conflict.

    This is the red arm. If this test ever passes-by-conflicting-nothing, the
    treatment test below proves nothing either.
    """
    result = _build_collision(tmp_path / "control", union=False)

    assert result.returncode != 0, "expected the control collision to conflict"
    merged = (tmp_path / "control" / LOG_PATH).read_text(encoding="utf-8")
    assert "<<<<<<<" in merged, "expected conflict markers in the control arm"


def test_append_collision_merges_cleanly_with_the_union_rule(
    tmp_path: Path,
) -> None:
    """With the rule the same collision merges clean and keeps both entries."""
    result = _build_collision(tmp_path / "treatment", union=True)

    assert result.returncode == 0, (
        f"union merge should not conflict; git said: {result.stdout}{result.stderr}"
    )
    merged = (tmp_path / "treatment" / LOG_PATH).read_text(encoding="utf-8")
    assert "<<<<<<<" not in merged, "union merge must not leave conflict markers"
    # Neither side may be dropped — the whole point is that no entry is lost.
    assert "MAIN-SIDE ENTRY" in merged
    assert "PR-SIDE ENTRY" in merged
    assert "[seed] base entry" in merged


def test_union_merge_orders_ours_before_theirs(tmp_path: Path) -> None:
    """Ours-then-theirs ordering is what keeps the log roughly chronological.

    GitHub merges the PR *into* main, so main is `ours`; its (earlier) entries
    land above the PR's. This asserts the ordering the log's readers rely on.
    """
    _build_collision(tmp_path / "order", union=True)
    merged = (tmp_path / "order" / LOG_PATH).read_text(encoding="utf-8")

    # lane-b is `ours` here (it is the branch being merged into).
    assert merged.index("PR-SIDE ENTRY") < merged.index("MAIN-SIDE ENTRY")


@pytest.mark.parametrize("union", [True, False])
def test_collision_fixture_is_actually_a_collision(tmp_path: Path, union: bool) -> None:
    """Guard the fixture itself: both lanes must really have diverged.

    A fixture bug that left one branch empty would make the union arm pass for
    the wrong reason ("Already up to date"), which is how the first manual run
    of this experiment fooled its author.
    """
    root = tmp_path / f"fixture-{union}"
    _build_collision(root, union=union)
    log = (root / LOG_PATH).read_text(encoding="utf-8")
    assert "MAIN-SIDE ENTRY" in log and "PR-SIDE ENTRY" in log
