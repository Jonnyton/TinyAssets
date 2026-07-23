"""Independent-clone discovery in scripts/worktree_status.py.

Covers the blind spot these tests exist for: directories under
``.codex-worktrees/`` are independent clones (real ``.git`` *directories*), so
``git worktree list`` returns none of them, and no script scanned the path.
Every coordination tool therefore reported that directory as empty while it
accumulated finished, unpushed work.

Kept separate from test_worktree_status.py because this is a different subject:
a distinct kind of checkout, discovered by directory scan rather than by git.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "worktree_status.py"
SPEC = importlib.util.spec_from_file_location("worktree_status_clones", SCRIPT)
assert SPEC is not None
worktree_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = worktree_status
SPEC.loader.exec_module(worktree_status)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")


def _commit(repo: Path, name: str, body: str = "x") -> str:
    (repo / name).write_text(body, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", f"add {name}")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture()
def canonical(tmp_path: Path) -> Path:
    """A canonical checkout with an `origin` remote, plus .codex-worktrees/."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(origin, "init", "-q", "--bare", "-b", "main")

    seed = tmp_path / "seed"
    _init_repo(seed)
    _commit(seed, "seed.txt")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "main")

    canon = tmp_path / "canonical"
    _git(tmp_path, "clone", "-q", str(origin), str(canon))
    (canon / worktree_status.CODEX_CLONE_DIR).mkdir()
    return canon


def _make_clone(canonical_repo: Path, slug: str) -> Path:
    """An INDEPENDENT clone (real .git dir) under .codex-worktrees/."""
    origin = _git(canonical_repo, "remote", "get-url", "origin")
    dest = canonical_repo / worktree_status.CODEX_CLONE_DIR / slug
    _git(canonical_repo, "clone", "-q", origin, str(dest))
    _git(dest, "config", "user.email", "t@example.com")
    _git(dest, "config", "user.name", "t")
    return dest


def test_independent_clone_is_invisible_to_git_worktree_list(canonical: Path) -> None:
    """The premise of the whole feature, asserted rather than assumed."""
    clone = _make_clone(canonical, "lane-a")

    assert (clone / ".git").is_dir(), "must be an independent clone, not a linked worktree"
    assert "lane-a" not in _git(canonical, "worktree", "list")
    assert [p.name for p in worktree_status.discover_clone_dirs(canonical)] == ["lane-a"]


def test_discover_skips_non_directories(canonical: Path) -> None:
    _make_clone(canonical, "lane-a")
    (canonical / worktree_status.CODEX_CLONE_DIR / "stray.bundle").write_text(
        "x", encoding="utf-8"
    )

    assert [p.name for p in worktree_status.discover_clone_dirs(canonical)] == ["lane-a"]


def test_unpushed_commit_reports_unpublished(canonical: Path) -> None:
    clone = _make_clone(canonical, "lane-unpub")
    _git(clone, "checkout", "-q", "-b", "feat/stranded")
    sha = _commit(clone, "only-here.txt")

    status = worktree_status.probe_clone(canonical, clone)

    assert status.state == "CLONE_UNPUBLISHED_ABSENT"
    assert status.published == "absent"
    assert status.branch == "feat/stranded"
    assert status.head == sha
    assert "UNPUBLISHED" in status.action
    # The canonical repo genuinely cannot see the object — that is the signal.
    assert worktree_status._published_state(canonical, sha) == ("absent", [])


def test_pushed_commit_reports_published(canonical: Path) -> None:
    clone = _make_clone(canonical, "lane-pub")
    _git(clone, "checkout", "-q", "-b", "feat/landed")
    _commit(clone, "shared.txt")
    _git(clone, "push", "-q", "origin", "feat/landed")
    _git(canonical, "fetch", "-q", "--prune", "origin")

    status = worktree_status.probe_clone(canonical, clone)

    assert status.state == "CLONE_PUBLISHED"
    assert status.published == "origin"
    assert status.origin_refs == ["refs/remotes/origin/feat/landed"]


def test_indeterminate_publication_state_fails_closed(
    canonical: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unanswerable publication check must NOT read as 'published, safe'."""
    clone = _make_clone(canonical, "lane-weird")
    _commit(clone, "local.txt")
    monkeypatch.setattr(worktree_status, "_published_state", lambda *_a, **_k: ("unknown", []))

    status = worktree_status.probe_clone(canonical, clone)

    assert status.state == "CLONE_UNKNOWN"
    assert status.state != "CLONE_PUBLISHED"
    assert "INDETERMINATE" in status.action
    assert "do not sweep" in status.action.lower()


def test_dubious_ownership_is_reported_not_repaired(
    canonical: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sandbox-owned dirs surface a remedy; the tool never mutates git config."""
    clone = _make_clone(canonical, "lane-owned")
    calls: list[list[str]] = []
    real = worktree_status.run_git

    def fake(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:1] == ["rev-parse"] and Path(cwd) == clone:
            return subprocess.CompletedProcess(
                args,
                128,
                "",
                f"fatal: detected dubious ownership in repository at '{clone}'",
            )
        return real(args, cwd)

    monkeypatch.setattr(worktree_status, "run_git", fake)

    status = worktree_status.probe_clone(canonical, clone)

    assert status.state == "CLONE_UNREADABLE"
    assert status.published == "unknown"
    assert status.remedy is not None and "safe.directory" in status.remedy
    assert "UNKNOWN" in status.action
    assert not any(call[:1] == ["config"] for call in calls), "must not write git config"


def test_missing_git_dir_and_unborn_head_do_not_crash(canonical: Path) -> None:
    plain = canonical / worktree_status.CODEX_CLONE_DIR / "not-a-repo"
    plain.mkdir()
    unborn = canonical / worktree_status.CODEX_CLONE_DIR / "empty-clone"
    _init_repo(unborn)

    assert worktree_status.probe_clone(canonical, plain).state == "CLONE_NOT_A_REPO"
    assert worktree_status.probe_clone(canonical, unborn).state == "CLONE_NO_COMMITS"


def test_scratch_only_changes_do_not_mark_lane_dirty(canonical: Path) -> None:
    clone = _make_clone(canonical, "lane-scratch")
    scratch = clone / ".pytest-tmp-run1" / "pytest-of-Jonathan"
    scratch.mkdir(parents=True)
    (scratch / "leftover.txt").write_text("junk", encoding="utf-8")

    status = worktree_status.probe_clone(canonical, clone)

    assert status.dirty == "scratch"
    assert status.scratch_ignored >= 1
    assert status.dirty_paths == []


def test_real_change_alongside_scratch_still_reports_dirty(canonical: Path) -> None:
    clone = _make_clone(canonical, "lane-mixed")
    (clone / ".pytest-tmp-run1").mkdir()
    (clone / ".pytest-tmp-run1" / "junk.txt").write_text("junk", encoding="utf-8")
    (clone / "real_work.py").write_text("print(1)\n", encoding="utf-8")

    status = worktree_status.probe_clone(canonical, clone)

    assert status.dirty == "yes"
    assert "real_work.py" in status.dirty_paths


def test_split_porcelain_keeps_leading_dot_scratch_names() -> None:
    """Guards the lstrip('./') bug: that strips a char set, eating the dot."""
    real, scratch = worktree_status.split_porcelain_paths(
        "?? .pytest-tmp-final3/\n"
        "?? .test-tmp/pytest-of-Jonathan/a.yaml\n"
        "?? .pytest_cache/v/x\n"
        " M tinyassets/api/wiki.py\n"
        'R  old.py -> "new work.py"\n'
    )

    assert scratch == 3
    assert real == ["tinyassets/api/wiki.py", "new work.py"]


def test_scratch_filter_only_matches_first_path_segment() -> None:
    """Narrow by design: a nested lookalike must not mask real work."""
    real, scratch = worktree_status.split_porcelain_paths(
        "?? src/.pytest-tmp-helper/conftest.py\n?? .pytest-tmp/x\n"
    )

    assert scratch == 1
    assert real == ["src/.pytest-tmp-helper/conftest.py"]


def test_clone_table_labels_them_as_a_distinct_kind(canonical: Path) -> None:
    clone = _make_clone(canonical, "lane-render")
    _git(clone, "checkout", "-q", "-b", "feat/x")
    _commit(clone, "a.txt")

    rendered = worktree_status.render_clone_table(
        worktree_status.collect_clones(canonical, workers=2)
    )

    assert "INDEPENDENT CLONES, not linked worktrees" in rendered
    assert "CLONE_UNPUBLISHED_ABSENT" in rendered
    assert "lane-render" in rendered
    assert "1 with UNPUBLISHED commits" in rendered
    assert "1 certain" in rendered
    # The squash-merge caveat must travel with the claim, per the project's
    # "classify by PR state, not by reachability" rule.
    assert "squash-merged" in rendered


def test_collect_clones_returns_empty_without_the_directory(tmp_path: Path) -> None:
    assert worktree_status.collect_clones(tmp_path) == []


def test_json_output_stays_a_bare_list_for_wt_and_collector(canonical: Path) -> None:
    """scripts/wt.py iterates this list; command_center drops non-lists."""
    _make_clone(canonical, "lane-json")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        cwd=canonical,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(proc.stdout)

    assert isinstance(payload, list)
    assert all(isinstance(row, dict) for row in payload)


def test_clones_only_json_is_a_list_of_clone_records(canonical: Path) -> None:
    clone = _make_clone(canonical, "lane-json2")
    _git(clone, "checkout", "-q", "-b", "feat/y")
    _commit(clone, "b.txt")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--clones-only"],
        cwd=canonical,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(proc.stdout)

    assert isinstance(payload, list)
    assert payload[0]["kind"] == "independent-clone"
    assert payload[0]["state"] == "CLONE_UNPUBLISHED_ABSENT"


def test_tracked_deletions_under_scratch_paths_are_never_suppressed() -> None:
    """Cross-family review (Codex, 2026-07-22) caught this concealing real work.

    `.codex-worktrees/wf-unified-authority` had 65 *tracked* `.test-tmp/...`
    files showing as ' D' deletions. Filtering scratch by pathname alone
    reported that clone clean and hid genuine index divergence. Only untracked
    ('??') entries may be suppressed.
    """
    real, scratch = worktree_status.split_porcelain_paths(
        " D .test-tmp/pytest-of-Jonathan/pytest-9/branches/fingerprint-rd.yaml\n"
        " M .pytest-tmp-run1/tracked.yaml\n"
        "A  .test-tmp/added-on-purpose.yaml\n"
        "?? .test-tmp/genuinely-untracked.yaml\n"
    )

    assert scratch == 1, "only the '??' entry may be suppressed"
    assert real == [
        ".test-tmp/pytest-of-Jonathan/pytest-9/branches/fingerprint-rd.yaml",
        ".pytest-tmp-run1/tracked.yaml",
        ".test-tmp/added-on-purpose.yaml",
    ]


def test_tracked_scratch_deletion_marks_clone_dirty(canonical: Path) -> None:
    """End-to-end form of the same defect, against a real repo."""
    clone = _make_clone(canonical, "lane-tracked-scratch")
    scratch = clone / ".test-tmp" / "pytest-of-Jonathan"
    scratch.mkdir(parents=True)
    (scratch / "fixture.yaml").write_text("a: 1\n", encoding="utf-8")
    _git(clone, "add", "-f", ".test-tmp")
    _git(clone, "commit", "-q", "-m", "track fixture")
    (scratch / "fixture.yaml").unlink()

    status = worktree_status.probe_clone(canonical, clone)

    assert status.dirty == "yes", "a tracked deletion must not read as scratch"
    assert any("fixture.yaml" in p for p in status.dirty_paths)


def test_no_origin_ref_state_routes_to_pr_classification(canonical: Path) -> None:
    """Object exists canonically but no origin ref contains it.

    Indistinguishable from a squash-merged-then-deleted branch, so the action
    must send the operator to PR metadata rather than assert unlanded work.
    """
    clone = _make_clone(canonical, "lane-noref")
    _git(clone, "checkout", "-q", "-b", "feat/maybe-squashed")
    sha = _commit(clone, "c.txt")
    _git(clone, "push", "-q", "origin", "feat/maybe-squashed")
    _git(canonical, "fetch", "-q", "--prune", "origin")
    # Branch deleted on origin, exactly as a squash merge would leave it.
    _git(clone, "push", "-q", "origin", "--delete", "feat/maybe-squashed")
    _git(canonical, "fetch", "-q", "--prune", "origin")

    published, refs = worktree_status._published_state(canonical, sha)
    status = worktree_status.probe_clone(canonical, clone)

    assert (published, refs) == ("no-origin-ref", [])
    assert status.state == "CLONE_UNPUBLISHED_NO_ORIGIN_REF"
    assert "gh pr view" in status.action
    assert "squash-merged" in status.action
