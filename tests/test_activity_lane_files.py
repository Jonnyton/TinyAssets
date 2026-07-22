"""Per-lane activity files remove the structural conflict on `.agents/activity.log`.

The log is append-only, so every lane appends to the end of the same file and
collides with every other lane on the final hunk — a structural conflict, not a
semantic one. On 2026-07-22 it was the only conflicting path in PRs #1506 and
#1507 at once, and rebasing did not converge: #1507 was fixed at 02:47Z and
re-broken by #1501 at 02:53Z, then re-broken again by #1506 later the same
session.

`tests/test_activity_lane_files.py` pins three things:

1. the collision is real (two lanes appending to one file DO conflict);
2. one-file-per-lane removes it (the same two lanes, distinct files, merge clean);
3. why `merge=union` was rejected — it is not applied by a bare/server-side merge,
   which is what GitHub runs. That test is the durable record of a claim that is
   easy to get wrong, because a local working-tree merge *does* honor the rule.

Rationale in prose: `.agents/activity.d/README.md`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ".agents/activity.log"
LANE_DIR = ".agents/activity.d"


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True
    )


def _seed_repo(root: Path, *, attributes: str = "") -> str:
    root.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", "main", cwd=root)
    _git("config", "user.email", "test@example.com", cwd=root)
    _git("config", "user.name", "test", cwd=root)
    _git("config", "core.autocrlf", "false", cwd=root)

    (root / ".gitattributes").write_text(attributes, encoding="utf-8")
    log = root / LOG_PATH
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("2026-07-01 [seed] base entry.\n", encoding="utf-8")
    (root / LANE_DIR).mkdir(parents=True, exist_ok=True)
    (root / LANE_DIR / ".gitkeep").write_text("", encoding="utf-8")
    _git("add", "-A", cwd=root)
    _git("commit", "-q", "-m", "base", cwd=root)
    return _git("rev-parse", "HEAD", cwd=root).stdout.strip()


def _build_lanes(root: Path, *, shared_file: bool, attributes: str = "") -> None:
    """Two diverged lanes, each having recorded one entry. Does NOT merge.

    ``shared_file=True`` reproduces today's behaviour (both append to the log).
    ``shared_file=False`` is the fix (each writes its own file).

    Merging is deliberately left to the caller: a fixture that merged here would
    make ``lane-a`` an ancestor of ``lane-b``, so a later ``merge-tree`` would be
    a trivial fast-forward and would report "no conflict" for the wrong reason.
    """
    base = _seed_repo(root, attributes=attributes)

    for branch, marker in (("lane-a", "LANE-A"), ("lane-b", "LANE-B")):
        _git("checkout", "-q", "-b", branch, base, cwd=root)
        if shared_file:
            with (root / LOG_PATH).open("a", encoding="utf-8") as fh:
                fh.write(f"2026-07-22 [{branch}] {marker} ENTRY.\n")
        else:
            (root / LANE_DIR / f"2026-07-22-{branch}.md").write_text(
                f"# 2026-07-22 — {branch}\n\n{marker} ENTRY.\n", encoding="utf-8"
            )
        _git("add", "-A", cwd=root)
        _git("commit", "-q", "-m", f"{branch} records an entry", cwd=root)

    # Guard the fixture: the lanes must actually have diverged.
    merge_base = _git("merge-base", "lane-a", "lane-b", cwd=root).stdout.strip()
    head_a = _git("rev-parse", "lane-a", cwd=root).stdout.strip()
    head_b = _git("rev-parse", "lane-b", cwd=root).stdout.strip()
    assert merge_base not in (head_a, head_b), "lanes did not diverge"


def _two_lanes(root: Path, *, shared_file: bool, attributes: str = ""):
    """Build the two lanes and merge lane-a into lane-b. Returns the merge result."""
    _build_lanes(root, shared_file=shared_file, attributes=attributes)
    # lane-b is checked out; merge lane-a into it.
    return _git("merge", "--no-edit", "lane-a", cwd=root, check=False)


def test_shared_log_append_really_does_conflict(tmp_path: Path) -> None:
    """The red arm: this is the problem being fixed.

    If this ever stops conflicting, the fix below is no longer load-bearing and
    the whole directory can be reconsidered.
    """
    result = _two_lanes(tmp_path / "shared", shared_file=True)

    assert result.returncode != 0, "two lanes appending to one log should conflict"
    assert "<<<<<<<" in (tmp_path / "shared" / LOG_PATH).read_text(encoding="utf-8")


def test_per_lane_files_do_not_conflict(tmp_path: Path) -> None:
    """The fix: distinct files, so the conflict cannot form."""
    root = tmp_path / "per-lane"
    result = _two_lanes(root, shared_file=False)

    assert result.returncode == 0, (
        f"per-lane files must merge cleanly; git said: {result.stdout}{result.stderr}"
    )
    # Both lanes' entries survive, each in its own file.
    assert (root / LANE_DIR / "2026-07-22-lane-a.md").exists()
    assert (root / LANE_DIR / "2026-07-22-lane-b.md").exists()
    assert "LANE-A ENTRY" in (root / LANE_DIR / "2026-07-22-lane-a.md").read_text(encoding="utf-8")
    assert "LANE-B ENTRY" in (root / LANE_DIR / "2026-07-22-lane-b.md").read_text(encoding="utf-8")


def test_union_merge_is_not_applied_by_a_bare_merge(tmp_path: Path) -> None:
    """Why `merge=union` was rejected — it does not survive a server-side merge.

    Git loads `.gitattributes` from the working tree. A bare merge has none, so
    the union driver is never installed unless `--attr-source` is passed
    explicitly. GitHub runs a bare merge-ort and reported a union-ruled append
    collision as CONFLICTING (disposable PR #1525).

    A local `git merge` DOES honor the rule, which is exactly why this is easy to
    "verify" incorrectly. If this test ever flips, union becomes viable again and
    `.agents/activity.d/README.md` should be revisited.
    """
    src = tmp_path / "src"
    # Deliberately NOT merged — the lanes must still be divergent in the clone,
    # or merge-tree would fast-forward and report no conflict for the wrong reason.
    _build_lanes(src, shared_file=True, attributes=f"{LOG_PATH} merge=union\n")

    bare = tmp_path / "bare.git"
    _git("clone", "-q", "--bare", str(src), str(bare), cwd=tmp_path)

    without = _git(
        "merge-tree", "--write-tree", "lane-b", "lane-a", cwd=bare, check=False
    )
    with_source = _git(
        "--attr-source=lane-b", "merge-tree", "--write-tree", "lane-b", "lane-a",
        cwd=bare, check=False,
    )

    assert "CONFLICT" in without.stdout, (
        "bare merge unexpectedly applied merge=union — union may now be viable, "
        "see .agents/activity.d/README.md"
    )
    assert "CONFLICT" not in with_source.stdout, (
        "with an explicit --attr-source the union driver should apply; if it does "
        "not, this test no longer demonstrates what it claims"
    )


def test_local_merge_does_honor_union_which_is_the_trap(tmp_path: Path) -> None:
    """Pins the misleading half: a working-tree merge DOES apply the rule.

    Present so the contrast with the bare case is executable rather than a claim
    in a comment.
    """
    result = _two_lanes(
        tmp_path / "local-union", shared_file=True, attributes=f"{LOG_PATH} merge=union\n"
    )

    assert result.returncode == 0, "a working-tree merge should apply merge=union"
    merged = (tmp_path / "local-union" / LOG_PATH).read_text(encoding="utf-8")
    assert "LANE-A ENTRY" in merged and "LANE-B ENTRY" in merged


def test_activity_dir_exists_and_log_is_frozen() -> None:
    """The directory ships, and the old log keeps its history."""
    assert (REPO_ROOT / LANE_DIR).is_dir()
    assert (REPO_ROOT / LANE_DIR / "README.md").is_file()
    # The historical log is retained, not deleted or truncated.
    assert (REPO_ROOT / LOG_PATH).stat().st_size > 10_000


@pytest.mark.parametrize("lane", ["status-janitor", "Status Janitor", "feat/foo_bar"])
def test_helper_writes_a_unique_file_per_call(tmp_path: Path, lane: str) -> None:
    """Two entries from the same lane on the same day must not share a file."""
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import activity_append

    (tmp_path / LANE_DIR).mkdir(parents=True)
    first = activity_append.entry_path(lane, "2026-07-22", root=tmp_path)
    first.write_text("x", encoding="utf-8")
    second = activity_append.entry_path(lane, "2026-07-22", root=tmp_path)

    assert first != second, "same-day second entry must get its own file"
    assert second.name.endswith("-2.md")
