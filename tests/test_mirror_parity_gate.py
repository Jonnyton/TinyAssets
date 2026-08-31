"""The mirror-parity gate, driven against a temp tree so it can be proved red.

The gate reported "mirror parity verified" for three commits while
``workspace_pool.py`` and ``workspace_fs.py`` were absent from the plugin mirror
entirely, because a canonical file with no counterpart was skipped as "not
mirrored yet". These tests pin both failure kinds - MISSING and DIVERGED - at
the shared checker the hook and CI both use, and pin the exclusion list to the
build's own, since the build's copy rule is what parity means.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.invariants import Status
from scripts.invariants.mirror_parity import (
    TREE_EXCLUDES,
    MirrorParityInvariant,
    scan_parity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_mirror_parity.py"


@pytest.fixture
def tree(tmp_path: Path):
    """A canonical tree and a mirror that matches it exactly."""
    canonical = tmp_path / "tinyassets"
    mirror = tmp_path / "mirror" / "tinyassets"
    (canonical / "api").mkdir(parents=True)
    (mirror / "api").mkdir(parents=True)
    for root in (canonical, mirror):
        (root / "runs.py").write_text("print('runs')\n", encoding="utf-8")
        (root / "api" / "market.py").write_text("print('market')\n", encoding="utf-8")
        (root / "onboarding.html").write_text("<html></html>", encoding="utf-8")
    return canonical, mirror


def _run_checker(canonical: Path, mirror: Path, *paths: str):
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--canonical-root",
            str(canonical),
            "--mirror-root",
            str(mirror),
            *paths,
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def test_a_matching_tree_passes(tree) -> None:
    canonical, mirror = tree
    report = scan_parity(canonical, mirror)
    assert report.ok is True
    assert report.checked == 3
    assert report.diverged == () and report.missing == ()

    done = _run_checker(canonical, mirror)
    assert done.returncode == 0, done.stderr
    assert "mirror-matched" in done.stdout


def test_a_canonical_file_with_no_mirror_counterpart_fails_by_name(tree) -> None:
    """(a) - the case that shipped. A new module the mirror does not have is
    drift, not a grace period."""
    canonical, mirror = tree
    (canonical / "workspace_pool.py").write_text("print('pool')\n", encoding="utf-8")

    report = scan_parity(canonical, mirror)
    assert report.ok is False
    assert report.missing == ("workspace_pool.py",)
    assert report.diverged == ()
    assert report.detail_lines() == ["  missing from the mirror: workspace_pool.py"]

    done = _run_checker(canonical, mirror)
    assert done.returncode == 1
    assert "workspace_pool.py" in done.stderr
    assert "build_plugin.py" in done.stderr


def test_a_mirror_copy_that_differs_fails_by_name(tree) -> None:
    """(b) - the mirror is running older code than canonical."""
    canonical, mirror = tree
    (canonical / "runs.py").write_text("print('runs v2')\n", encoding="utf-8")

    report = scan_parity(canonical, mirror)
    assert report.ok is False
    assert report.diverged == ("runs.py",)
    assert report.missing == ()

    done = _run_checker(canonical, mirror)
    assert done.returncode == 1
    assert "diverged: runs.py" in done.stderr


def test_both_kinds_are_reported_together(tree) -> None:
    canonical, mirror = tree
    (canonical / "workspace_fs.py").write_text("print('fs')\n", encoding="utf-8")
    (canonical / "api" / "market.py").write_text("print('v2')\n", encoding="utf-8")

    report = scan_parity(canonical, mirror)
    assert report.diverged == ("api/market.py",)
    assert report.missing == ("workspace_fs.py",)
    assert "1 diverged" in report.message()
    assert "1 missing from the mirror" in report.message()


def test_the_staged_subset_only_judges_the_paths_it_was_given(tree) -> None:
    """The hook's scope: a commit fails for the drift it stages, not for drift
    someone else left in the tree."""
    canonical, mirror = tree
    (canonical / "workspace_pool.py").write_text("print('pool')\n", encoding="utf-8")
    (canonical / "runs.py").write_text("print('runs v2')\n", encoding="utf-8")

    only_clean = scan_parity(canonical, mirror, relative_paths=["api/market.py"])
    assert only_clean.ok is True
    assert only_clean.checked == 1

    staged_missing = scan_parity(canonical, mirror, relative_paths=["workspace_pool.py"])
    assert staged_missing.missing == ("workspace_pool.py",)

    # git stages repo-relative paths; the checker accepts that spelling too.
    done = _run_checker(canonical, mirror, "tinyassets/runs.py")
    assert done.returncode == 1
    assert "diverged: runs.py" in done.stderr


def test_a_path_that_no_longer_exists_is_not_drift(tree) -> None:
    canonical, mirror = tree
    report = scan_parity(canonical, mirror, relative_paths=["gone.py"])
    assert report.ok is True
    assert report.checked == 0


def test_files_the_build_never_copies_are_not_missing(tree) -> None:
    """The exclusion list is the build's, so a compiled artefact or a local db
    is not drift - it was never meant to be in the mirror."""
    canonical, mirror = tree
    (canonical / "__pycache__").mkdir()
    (canonical / "__pycache__" / "runs.cpython-311.pyc").write_bytes(b"\x00")
    (canonical / "local.db").write_bytes(b"sqlite")
    (canonical / "debug.log").write_text("noise", encoding="utf-8")

    report = scan_parity(canonical, mirror)
    assert report.ok is True, report.detail_lines()
    assert report.checked == 3


def test_the_exclusions_are_the_builds_own(tree) -> None:
    """A gate holding a different list would either miss drift or fail on files
    the build never copies."""
    spec = importlib.util.spec_from_file_location(
        "_build_plugin_probe",
        REPO_ROOT / "packaging" / "claude-plugin" / "build_plugin.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert TREE_EXCLUDES == module._TREE_EXCLUDES


def test_the_invariant_reports_violated_with_the_paths(tree) -> None:
    """What CI runs: `invariants_run.py --pre-commit` lands on this class."""
    canonical, mirror = tree
    invariant = MirrorParityInvariant(canonical_root=canonical, mirror_root=mirror)
    assert invariant.check().status is Status.OK

    (canonical / "workspace_pool.py").write_text("print('pool')\n", encoding="utf-8")
    (canonical / "runs.py").write_text("print('runs v2')\n", encoding="utf-8")
    result = invariant.check()
    assert result.status is Status.VIOLATED
    assert result.evidence["missing"] == ["workspace_pool.py"]
    assert result.evidence["mismatches"] == ["runs.py"]
    assert "build_plugin.py" in result.message


def test_a_missing_root_skips_rather_than_fails(tmp_path) -> None:
    invariant = MirrorParityInvariant(
        canonical_root=tmp_path / "nope", mirror_root=tmp_path / "also-nope"
    )
    assert invariant.check().status is Status.SKIPPED


def test_the_packaging_workflow_notices_an_untracked_mirror_file() -> None:
    """The third gate on the same class. build-bundle.yml rebuilds the mirror
    and then asks git whether anything moved - and `git diff` does not see
    UNTRACKED paths, which is exactly what a brand-new mirror file is. Pinned as
    text because the assertion is about the command, and there is no way to run
    a GitHub-hosted step here."""
    import yaml

    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "build-bundle.yml").read_text(
            encoding="utf-8"
        )
    )
    steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if "Verify committed plugin runtime" in str(step.get("name", ""))
    ]
    assert len(steps) == 1, "the staleness check moved; re-point this test"
    script = steps[0]["run"]
    assert "git status --porcelain" in script
    assert "git diff --quiet" not in script


def test_the_hook_delegates_to_the_shared_checker() -> None:
    """The hook and CI must not hold two ideas of what parity means: the bash
    loop that used to live in the hook had its own, and skipped the missing
    case for three commits."""
    hook = (REPO_ROOT / "scripts" / "git-hooks" / "pre-commit").read_text(
        encoding="utf-8"
    )
    # A live invocation, not a mention in a comment: the whole point is that the
    # hook RUNS the shared checker.
    invocations = [
        line
        for line in hook.splitlines()
        if "check_mirror_parity.py" in line and not line.strip().startswith("#")
    ]
    assert invocations, "the hook does not invoke scripts/check_mirror_parity.py"
    # The installed hook is SHARED by every worktree (linked worktrees use the
    # main repo's .git/hooks), so it can be newer than the checkout it runs in.
    # A worktree whose branch predates the script must fall back, not fail on a
    # missing file - execing it there blocked four lanes at once (2026-08-30).
    assert 'if [ ! -f "scripts/check_mirror_parity.py" ]; then' in hook
    assert "falling back to the legacy divergence-only comparison" in hook
    # The legacy comparison exists ONLY as that fallback: the unconditional
    # inline loop this hook used to run is gone.
    assert "LEGACY_MIRROR_PREFIX" in hook
    assert not any(
        line.startswith("MIRROR_PREFIX=") for line in hook.splitlines()
    ), "the unconditional inline comparison is back"


def _bash() -> str | None:
    """A bash that can see a Windows path. ``shutil.which("bash")`` finds the
    WSL launcher first on this host, and WSL cannot open ``C:/...`` - it wants
    ``/mnt/c/...`` - so Git Bash is preferred where it exists."""
    candidates: list[str] = []
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        ]
    found = shutil.which("bash")
    if found:
        candidates.append(found)
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _hook_repo(tmp_path: Path, *, diverge: bool) -> Path:
    """A minimal repo shaped like this one, WITHOUT the shared checker."""
    repo = tmp_path / "repo"
    canonical = repo / "tinyassets"
    mirror = (
        repo
        / "packaging"
        / "claude-plugin"
        / "plugins"
        / "tinyassets-universe-server"
        / "runtime"
        / "tinyassets"
    )
    canonical.mkdir(parents=True)
    mirror.mkdir(parents=True)
    (canonical / "runs.py").write_text("x = 1", encoding="utf-8")
    (mirror / "runs.py").write_text("x = 2" if diverge else "x = 1", encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["config", "user.email", "gate@test"],
        ["config", "user.name", "gate"],
        ["add", "-A"],
    ):
        subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True)
    return repo


@pytest.mark.skipif(_bash() is None, reason="the hook is a bash script")
def test_the_hook_falls_back_when_the_checker_is_not_in_this_worktree(tmp_path) -> None:
    """The installed hook is shared by every worktree, so it can be newer than
    the checkout: it must degrade to the legacy comparison, not die on a missing
    file. Execing the absent script blocked four lanes at once (2026-08-30)."""
    repo = _hook_repo(tmp_path, diverge=False)
    done = subprocess.run(
        # POSIX spelling: Git Bash on Windows eats the backslashes of a native
        # path passed as an argument.
        [_bash(), (REPO_ROOT / "scripts" / "git-hooks" / "pre-commit").as_posix()],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    output = done.stdout + done.stderr
    assert "is not in this worktree" in output
    assert "mirror parity verified (legacy comparison)" in output
    assert "can't open file" not in output
    assert "plugin-mirror parity broken" not in output


@pytest.mark.skipif(_bash() is None, reason="the hook is a bash script")
def test_the_fallback_still_gates_divergence(tmp_path) -> None:
    """Falling back is not waving through: a worktree behind the gate is still
    gated on the case the legacy comparison can see."""
    repo = _hook_repo(tmp_path, diverge=True)
    done = subprocess.run(
        # POSIX spelling: Git Bash on Windows eats the backslashes of a native
        # path passed as an argument.
        [_bash(), (REPO_ROOT / "scripts" / "git-hooks" / "pre-commit").as_posix()],
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    output = done.stdout + done.stderr
    assert done.returncode == 1
    assert "plugin-mirror parity broken" in output
    assert "tinyassets/runs.py" in output


def test_the_real_tree_is_in_parity() -> None:
    """The gate is only worth having if the repo currently satisfies it."""
    report = scan_parity(
        REPO_ROOT / "tinyassets",
        REPO_ROOT
        / "packaging"
        / "claude-plugin"
        / "plugins"
        / "tinyassets-universe-server"
        / "runtime"
        / "tinyassets",
    )
    assert report.ok, report.detail_lines()
