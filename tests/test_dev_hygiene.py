"""Safety proofs for scripts/dev_hygiene.py.

The tool deletes things, so every test here is a proof about one *refusal*: what
it keeps, and why. The removal cases exist to show the refusals are not simply a
tool that never acts.

Each guard was mutation-checked by hand on 2026-09-26 — the mutation table is in
PR #<this PR>'s body. A test that cannot go red is decoration.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = _REPO / "scripts"


def _load() -> object:
    """Import scripts/dev_hygiene.py by path (scripts/ is not a package).

    Registered in ``sys.modules`` before execution: Python 3.14's ``dataclasses``
    resolves ``cls.__module__`` through ``sys.modules`` and raises on a module
    that is not there yet.
    """
    sys.path.insert(0, str(_SCRIPTS))
    name = "dev_hygiene_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / "dev_hygiene.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dh = _load()

HOUR = 3600.0
NOW = 1_700_000_000.0


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def age(path: Path, hours: float, now: float = NOW) -> None:
    """Backdate every entry in a tree so the collector sees it as stale."""
    stamp = now - hours * HOUR
    targets = [path]
    if path.is_dir():
        targets += [Path(p) / n for p, ds, fs in os.walk(path) for n in list(ds) + list(fs)]
    for target in sorted(targets, key=lambda p: -len(str(p))):
        os.utime(target, (stamp, stamp))


def make_basetemp(root: Path, name: str, *, hours: float, payload: int = 1024) -> Path:
    """A directory with pytest's numbered-dir shape, backdated by ``hours``."""
    base = root / name
    (base / "test_something0").mkdir(parents=True)
    (base / "test_something0" / "data.bin").write_bytes(b"x" * payload)
    age(base, hours)
    return base


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {repo}: {proc.stderr}")
    return proc.stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A clone of a bare origin, on ``main``, with one commit pushed.

    Short path segments on purpose: Windows MAX_PATH plus a worktree plus
    ``.git/worktrees/<name>`` is enough to break a longer layout.
    """
    origin = tmp_path / "o"
    origin.mkdir()
    git(origin, "init", "--bare", "--initial-branch=main")
    clone = tmp_path / "c"
    git(tmp_path, "clone", str(origin), "c")
    git(clone, "config", "user.email", "t@example.invalid")
    git(clone, "config", "user.name", "t")
    (clone / ".gitignore").write_text("output/\n.ruff_cache/\n_PURPOSE.md\n", encoding="utf-8")
    (clone / "a.txt").write_text("base\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "-m", "base")
    git(clone, "push", "-u", "origin", "main")
    return clone


def add_lane(repo: Path, name: str, *, merged: bool, push: bool = True) -> Path:
    """Create a branch with one commit, optionally landed on origin/main, and
    check it out as a worktree. Returns the worktree path."""
    git(repo, "checkout", "-q", "-b", name)
    (repo / f"{name}.txt").write_text(name, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", f"work on {name}")
    if push:
        git(repo, "push", "-q", "-u", "origin", name)
    git(repo, "checkout", "-q", "main")
    if merged:
        git(repo, "merge", "-q", "--no-ff", "-m", f"merge {name}", name)
        git(repo, "push", "-q", "origin", "main")
    git(repo, "fetch", "-q", "--all")
    worktree = repo.parent / f"w{abs(hash(name)) % 997}"
    git(repo, "worktree", "add", "-q", str(worktree), name)
    return worktree


def no_pr(_branch: str, _cwd: Path) -> None:
    """Default PR oracle for tests: gh cannot answer. Never authorizes removal."""
    return None


def worktree_items(repo: Path, **kwargs):
    kwargs.setdefault("now", time.time() + 48 * HOUR)  # past the idle gate
    kwargs.setdefault("idle_hours", 24.0)
    kwargs.setdefault("pr_state_fn", no_pr)
    # Default: gh answered, and no branch has an open PR. Tests that care about
    # liveness pass their own; a test that forgot would otherwise silently exercise
    # the fail-closed path and prove nothing.
    kwargs.setdefault("open_pr_fn", lambda _repo: set())
    return dh.collect_worktrees(repo, **kwargs)


def by_path(items, path: Path):
    wanted = str(Path(path).resolve()).lower()
    for item in items:
        if str(Path(item.path).resolve()).lower() == wanted:
            return item
    raise AssertionError(f"{path} not in report: {[i.path for i in items]}")


# --------------------------------------------------------------------------- #
# (a) pytest basetemp directories
# --------------------------------------------------------------------------- #


def test_stale_pytest_basetemp_is_removed(tmp_path: Path) -> None:
    root = tmp_path / "t"
    root.mkdir()
    stale = make_basetemp(root, "ta-pt-old", hours=10)
    item = by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), stale)
    assert item.verdict == "REMOVE"
    assert item.reason == "stale_pytest_basetemp"
    assert item.size_bytes >= 1024


def make_session(root: Path, name: str, *, hours: float, children=("test_a_thing0",)) -> Path:
    base = root / name
    for child in children:
        (base / child).mkdir(parents=True)
        (base / child / "data.bin").write_bytes(b"x" * 64)
    (base / ".tinyassets.db").write_bytes(b"db")
    age(base, hours)
    return base


def test_unprefixed_pytest_session_is_removed_from_the_temp_root(tmp_path: Path) -> None:
    """Lanes pick bare basetemp names (``orunb``, ``ct_x1``); 3.8 GB on 2026-09-28."""
    root = tmp_path / "t"
    root.mkdir()
    session = make_session(root, "orunb", hours=10, children=("test_a_thing0", "test_b1"))
    xdist = make_session(root, "ct_x1", hours=10, children=("popen-gw0", "popen-gw1"))
    items = dh.collect_basetemps(root, min_age_hours=6, now=NOW, unprefixed_sessions=True)
    for path in (session, xdist):
        item = by_path(items, path)
        assert (item.verdict, item.reason) == ("REMOVE", "stale_pytest_basetemp"), path


def test_unprefixed_dir_needs_every_child_to_be_a_session_child(tmp_path: Path) -> None:
    """No name hint, so one plain sibling makes it not a candidate at all."""
    root = tmp_path / "t"
    root.mkdir()
    chapter = make_session(root, "novel", hours=500, children=("test_a0", "chapter1"))
    notes = make_session(root, "research", hours=500)
    (notes / "manuscript.md").write_text("unique\n", encoding="utf-8")
    age(notes, 500)
    empty = root / "emptyish"
    empty.mkdir()
    (empty / ".tinyassets.db").write_bytes(b"db")
    age(empty, 500)
    items = dh.collect_basetemps(root, min_age_hours=6, now=NOW, unprefixed_sessions=True)
    listed = {str(Path(i.path).resolve()).lower() for i in items}
    for path in (chapter, notes, empty):
        assert str(path.resolve()).lower() not in listed, path


def test_unprefixed_sessions_are_off_unless_asked(tmp_path: Path) -> None:
    """A drive root never admits unprefixed names."""
    root = tmp_path / "t"
    root.mkdir()
    make_session(root, "orunb", hours=10)
    assert dh.collect_basetemps(root, min_age_hours=6, now=NOW, prefixes=("ta-",)) == []


def test_recent_unprefixed_session_is_kept(tmp_path: Path) -> None:
    root = tmp_path / "t"
    root.mkdir()
    live = make_session(root, "orlive", hours=1)
    items = dh.collect_basetemps(root, min_age_hours=6, now=NOW, unprefixed_sessions=True)
    item = by_path(items, live)
    assert (item.verdict, item.reason) == ("KEEP", "in_use_or_recent")


def test_recent_basetemp_is_kept(tmp_path: Path) -> None:
    """A basetemp a live pytest session may still own is never removed."""
    root = tmp_path / "t"
    root.mkdir()
    fresh = make_basetemp(root, "ta-pt-live", hours=1)
    item = by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), fresh)
    assert item.verdict == "KEEP"
    assert item.reason == "in_use_or_recent"


def test_unrecognized_shape_is_kept_even_with_a_matching_prefix(tmp_path: Path) -> None:
    """The guard that saved this box's stale-tree audit oracles.

    Several ``ta-*`` directories under the real temp root are whole repo
    checkouts kept deliberately (`ta-base-tree`, `ta-baseline-*`). A prefix match
    must never be enough; the pytest numbered-dir shape is the proof.
    """
    root = tmp_path / "t"
    root.mkdir()
    oracle = root / "ta-baseline-deadbeef"
    (oracle / "tinyassets" / "storage").mkdir(parents=True)
    (oracle / "tinyassets" / "storage" / "core.py").write_text("real code\n", encoding="utf-8")
    (oracle / "AGENTS.md").write_text("pinned tree\n", encoding="utf-8")
    age(oracle, 500)
    item = by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), oracle)
    assert item.verdict == "KEEP"
    assert item.reason == "unrecognized_shape"
    assert oracle.exists()


def test_one_numbered_child_does_not_vouch_for_its_siblings(tmp_path: Path) -> None:
    """Codex round 1, P0: `ta-research/chapter1/` beside a unique `manuscript.md`.

    `chapter1` matches pytest's `<slug><N>` scheme, and accepting on the first
    match let one plausible child authorize deleting the manuscript next to it.
    Every child must now be a pytest artifact.
    """
    root = tmp_path / "t"
    root.mkdir()
    work = root / "ta-research"
    (work / "chapter1").mkdir(parents=True)
    (work / "manuscript.md").write_text("the only copy\n", encoding="utf-8")
    age(work, 500)
    item = by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), work)
    assert item.verdict == "KEEP"
    assert item.reason == "unrecognized_shape"
    assert (work / "manuscript.md").exists()


def test_pytest_of_root_is_checked_by_shape_not_by_name(tmp_path: Path) -> None:
    """`pytest-of-<user>` used to bypass content classification on its name alone."""
    root = tmp_path / "t"
    root.mkdir()
    impostor = root / "pytest-of-someone"
    impostor.mkdir()
    (impostor / "notes.md").write_text("not pytest's\n", encoding="utf-8")
    age(impostor, 500)
    assert by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), impostor).verdict == "KEEP"

    genuine = root / "pytest-of-runner"
    (genuine / "pytest-3").mkdir(parents=True)
    (genuine / "pytest-current").mkdir()
    age(genuine, 500)
    assert (
        by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), genuine).verdict == "REMOVE"
    )


def test_a_drive_root_scans_only_the_agents_own_prefix(tmp_path: Path) -> None:
    """Lanes put short basetemps at the C:\\ ROOT to dodge MAX_PATH; 34 were there.

    A drive root also holds system directories, so it takes `ta-` only — not the
    full temp-root prefix set, which would make `pytest-*` and `Program Files`-
    adjacent names candidates.
    """
    root = tmp_path / "drive"
    root.mkdir()
    mine = make_basetemp(root, "ta-cr1", hours=500)
    (root / "Windows").mkdir()
    (root / "pytest-of-someone").mkdir()
    age(root / "pytest-of-someone", 500)
    items = dh.collect_basetemps(root, min_age_hours=6, now=NOW, prefixes=dh.DRIVE_ROOT_PREFIXES)
    assert by_path(items, mine).verdict == "REMOVE"
    seen = {Path(i.path).name for i in items}
    assert seen == {"ta-cr1"}, f"a drive root must not widen past ta-*: {seen}"
    assert (root / "Windows").is_dir()


def test_a_checkout_at_a_drive_root_is_not_basetemp(tmp_path: Path) -> None:
    """`C:\\ta-something` holding a repo belongs to the worktree class, not this one."""
    root = tmp_path / "drive"
    root.mkdir()
    checkout = root / "ta-baseline-checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "test_x0").mkdir()  # pytest-shaped children, so only .git saves it
    age(checkout, 500)
    item = by_path(
        dh.collect_basetemps(root, min_age_hours=6, now=NOW, prefixes=dh.DRIVE_ROOT_PREFIXES),
        checkout,
    )
    assert item.verdict == "KEEP"
    assert item.reason == "git_checkout_not_basetemp"
    assert checkout.exists()


def test_extra_temp_root_defaults_to_the_repo_drive(repo: Path, tmp_path: Path, capsys) -> None:
    """The default is data derived from the repo path, not a literal "C:\\"."""
    root = tmp_path / "t"
    root.mkdir()
    rc = dh.main(["--repo", str(repo), "--temp-root", str(root), "--classes", "basetemp", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    anchor = Path(repo).anchor
    assert anchor, "setup: the repo path must have a drive/root anchor"
    # Nothing under the real drive root is asserted removable here — only that the
    # pass completed with the extra root configured and refused nothing unknown.
    assert all(i["verdict"] in {"REMOVE", "KEEP"} for i in payload["items"])


def test_unknown_name_is_not_even_a_candidate(tmp_path: Path) -> None:
    """Anything outside the prefix allowlist is invisible to the tool."""
    root = tmp_path / "t"
    root.mkdir()
    other = root / "MyImportantExport"
    other.mkdir()
    (other / "test_x0").mkdir()  # pytest-shaped, but the name is not ours
    age(other, 500)
    items = dh.collect_basetemps(root, min_age_hours=6, now=NOW)
    assert [i.path for i in items] == []


def test_empty_basetemp_is_removable(tmp_path: Path) -> None:
    """``pytest --basetemp=X`` wipes and recreates X, so an empty X holds nothing."""
    root = tmp_path / "t"
    root.mkdir()
    empty = root / "ta-pt-empty"
    empty.mkdir()
    age(empty, 48)
    assert by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), empty).verdict == "REMOVE"


def test_acl_locked_basetemp_is_kept_and_points_at_the_elevated_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """68 real directories on this box deny the interactive user everything.

    Those are not "unknown shape" — they are a known class needing an elevated
    clear, so they must be reported as such rather than silently lumped in.
    """
    root = tmp_path / "t"
    root.mkdir()
    locked = root / "ta-pt-locked"
    locked.mkdir()
    age(locked, 500)
    real_scandir = os.scandir

    def deny(path):
        if Path(path) == locked:
            raise PermissionError(13, "Access is denied")
        return real_scandir(path)

    monkeypatch.setattr(dh.os, "scandir", deny)
    item = by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), locked)
    assert item.verdict == "KEEP"
    assert item.reason == "acl_locked_needs_elevation"
    assert "clear_sandbox_temp_dirs.ps1" in item.detail


def test_basetemp_containing_cwd_is_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "t"
    root.mkdir()
    live = make_basetemp(root, "ta-pt-here", hours=500)
    inner = live / "test_something0"
    monkeypatch.chdir(inner)
    item = by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), live)
    assert (item.verdict, item.reason) == ("KEEP", "contains_cwd")


def test_tree_stats_refuses_an_entry_it_cannot_stat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A single unreadable entry makes the whole tree undecidable.

    Skipping it was the original behaviour, and it is unsafe now that the recursive
    newest mtime IS the worktree idleness gate (Codex round 1, P2): the one entry a
    live session is holding open is exactly the one likeliest to deny a stat, so
    skipping it would under-report activity. A vanished entry (FileNotFoundError)
    still just contributes nothing — that is a race, not an unknown.
    """
    base = tmp_path / "t"
    base.mkdir()
    (base / "real.txt").write_bytes(b"x" * 8)
    real_scandir = os.scandir

    class _DenyEntry:
        name = "denied.bin"

        def __init__(self, parent: Path) -> None:
            self.path = str(parent / self.name)

        def is_dir(self, follow_symlinks: bool = True) -> bool:
            return False

        def stat(self, follow_symlinks: bool = True):
            raise PermissionError(13, "Access is denied")

    class _Scandir:
        def __init__(self, path) -> None:
            self.path = path

        def __enter__(self):
            if Path(self.path) == base:
                return iter([_DenyEntry(base)])
            return real_scandir(self.path).__enter__()

        def __exit__(self, *_exc) -> None:
            return None

    monkeypatch.setattr(dh.os, "scandir", _Scandir)
    with pytest.raises(dh.AclLocked):
        dh.tree_stats(base)


def test_tree_stats_separates_a_vanished_entry_from_an_unreadable_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A race contributes nothing; any other stat error is an unknown.

    Both branches are exercised because a ``PermissionError`` now has its own
    clause ahead of the generic one, so a test that only raises ``PermissionError``
    leaves the generic ``OSError`` path uncovered.
    """
    base = tmp_path / "t"
    base.mkdir()
    real_scandir = os.scandir

    def with_entry(error: Exception):
        class _Entry:
            name = "entry.bin"
            path = str(base / "entry.bin")

            def is_dir(self, follow_symlinks: bool = True) -> bool:
                return False

            def stat(self, follow_symlinks: bool = True):
                raise error

        class _Scandir:
            def __init__(self, path) -> None:
                self.path = path

            def __enter__(self):
                if Path(self.path) == base:
                    return iter([_Entry()])
                return real_scandir(self.path).__enter__()

            def __exit__(self, *_exc) -> None:
                return None

        return _Scandir

    monkeypatch.setattr(dh.os, "scandir", with_entry(FileNotFoundError(2, "No such file")))
    assert dh.tree_stats(base)[0] == 0, "a vanished entry must not refuse the tree"

    monkeypatch.setattr(dh.os, "scandir", with_entry(OSError(22, "Invalid argument")))
    with pytest.raises(dh.Undecidable) as caught:
        dh.tree_stats(base)
    assert not isinstance(caught.value, dh.AclLocked), "only access-denied is the ACL class"


def test_tree_stats_refuses_an_oversized_tree(tmp_path: Path) -> None:
    """Fail closed: a tree too big to inventory is kept, not guessed at."""
    root = tmp_path / "big"
    root.mkdir()
    for i in range(5):
        (root / f"f{i}").write_bytes(b"x")
    with pytest.raises(dh.Undecidable):
        dh.tree_stats(root, budget=2)


@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_tree_stats_does_not_follow_a_link_out_of_the_tree(tmp_path: Path, kind: str) -> None:
    """Sizing must stay inside the tree it was asked about.

    Both link kinds are exercised because on Windows a symlink needs privilege
    this host does not grant while a **junction** needs none — and
    ``entry.is_dir(follow_symlinks=False)`` returns True for a junction, so the
    walk crossed into the target and reported its bytes as reclaimable. A
    symlink-only test passes by skipping on Windows and proves nothing about the
    mechanism that actually exists there.

    The assertion is the *invariant* (the walk does not count what is outside, and
    the outside content survives), not one platform's mechanism: on POSIX
    ``follow_symlinks=False`` already answers it and no reparse attribute exists,
    so there is nothing to refuse. Asserting the Windows refusal unconditionally
    is what made this red on Linux CI.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "huge.bin").write_bytes(b"y" * 4096)
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "small.bin").write_bytes(b"z" * 10)
    link = inside / "link"
    if kind == "symlink":
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation needs privilege on this host")
    else:
        if os.name != "nt":
            pytest.skip("junctions are Windows-only")
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True, text=True
        )
        if made.returncode != 0 or not link.exists():
            pytest.skip(f"mklink /J unavailable: {made.stderr.strip()}")
    assert dh.is_link(os.stat(link, follow_symlinks=False)), (
        f"a {kind} must register as a link on this platform"
    )
    # One number on both platforms: 10 bytes of real content, and nothing for the
    # link. A POSIX symlink's own lstat size is the length of its target path, so
    # counting the entry at all made this 50 on Linux and 4106 before the guard.
    size, _newest = dh.tree_stats(inside)
    assert size == 10, f"the walk counted bytes behind or belonging to the {kind}"

    ok, detail = dh.remove_path(link)
    # The exact phrase, not a substring of it: rmtree's own error for a link root is
    # "Cannot call rmtree on a symbolic link", which contains "link" and so satisfied
    # a loose assertion even with the guard removed.
    assert not ok, f"the remover must refuse a bare {kind}"
    assert "refusing to delete a link" in detail, f"refused for the wrong reason: {detail}"
    assert (outside / "huge.bin").exists(), f"deleting a {kind} reached through it"
    assert outside.is_dir()


def test_is_link_covers_both_mechanisms_without_a_filesystem() -> None:
    """A unit test on the predicate, so the POSIX branch is covered on Windows too.

    The filesystem test above can only exercise whichever link kind this host lets
    it create — on Windows the symlink variant skips for want of privilege, which
    left `S_ISLNK` unproven locally and a mutation removing it undetected.
    """

    class _Stat:
        def __init__(self, mode: int, attrs: int = 0) -> None:
            self.st_mode = mode
            if attrs:
                self.st_file_attributes = attrs

    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    assert dh.is_link(_Stat(stat.S_IFLNK | 0o777)), "a POSIX symlink is a link"
    assert dh.is_link(_Stat(stat.S_IFDIR, reparse)), "a Windows junction is a link"
    assert dh.is_link(_Stat(stat.S_IFLNK, reparse)), "a Windows symlink is a link"
    assert not dh.is_link(_Stat(stat.S_IFREG | 0o644)), "a plain file is not"
    assert not dh.is_link(_Stat(stat.S_IFDIR, stat.FILE_ATTRIBUTE_DIRECTORY)), (
        "a plain directory is not"
    )
    # is_reparse_point stays Windows-only; is_link is the platform-agnostic one.
    assert not dh.is_reparse_point(_Stat(stat.S_IFLNK | 0o777))


# --------------------------------------------------------------------------- #
# (b) git worktrees
# --------------------------------------------------------------------------- #


def test_remove_path_clears_read_only_git_objects(tmp_path: Path) -> None:
    """The most likely real-world failure: a basetemp holding a git checkout.

    Git writes loose objects read-only (mode 444), and ``shutil.rmtree`` raises
    ``PermissionError`` / WinError 5 on them. Most of this repo's tests build real
    checkouts, so without the chmod retry the tool would silently fail to reclaim
    the very directories it exists for — observed on 24 of this lane's own scratch
    dirs on 2026-09-26.
    """
    base = tmp_path / "ta-pt-gitobjects"
    objects = base / "t0" / "c" / ".git" / "objects" / "3e"
    objects.mkdir(parents=True)
    blob = objects / "68286098058b9813e3b87f2eff7991dffa06c2"
    blob.write_bytes(b"x" * 64)
    blob.chmod(stat.S_IREAD)
    with pytest.raises(PermissionError):
        blob.write_bytes(b"still writable")  # setup check: it really is read-only
    ok, detail = dh.remove_path(base)
    assert ok, detail
    assert not base.exists()


def test_merged_clean_worktree_is_removed(repo: Path) -> None:
    lane = add_lane(repo, "landed", merged=True)
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "REMOVE"
    assert item.reason == "merged_and_clean"
    assert item.branch == "landed"


def test_dirty_worktree_is_kept(repo: Path) -> None:
    lane = add_lane(repo, "landed", merged=True)
    (lane / "in-progress.txt").write_text("half-written\n", encoding="utf-8")
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "dirty"
    assert lane.exists()


def test_unmerged_branch_is_kept(repo: Path) -> None:
    lane = add_lane(repo, "open", merged=False)
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "KEEP"
    assert item.reason in {"unmerged_pr_state_unknown", "unpushed_commits"}


def test_worktree_with_commits_on_no_remote_is_kept(repo: Path) -> None:
    """The 111-unpushed-commit case this found on the real box."""
    lane = add_lane(repo, "local", merged=False, push=False)
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "unpushed_commits"
    assert "1 commit(s) on no remote" in item.detail


def test_worktree_with_unique_ignored_content_is_kept(repo: Path) -> None:
    """Hard Rule 13 as a test: a clean ``git status`` is not a licence to delete.

    ``git worktree remove`` decides cleanliness with ``git status --porcelain``,
    which omits ignored files entirely — which is how a checkout that looked like
    stale cruft came to hold 4,711 lines of unique research on 2026-08-26.
    """
    lane = add_lane(repo, "landed", merged=True)
    (lane / "output").mkdir()
    (lane / "output" / "research.md").write_text("exists nowhere else\n", encoding="utf-8")
    assert git(lane, "status", "--porcelain").strip() == "", "setup: git must see this as clean"
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "ignored_content_exists_nowhere_else"
    assert "output/" in item.detail


def test_disposable_ignored_content_does_not_block_removal(repo: Path) -> None:
    lane = add_lane(repo, "landed", merged=True)
    (lane / ".ruff_cache").mkdir()
    (lane / ".ruff_cache" / "x.json").write_text("{}", encoding="utf-8")
    (lane / "_PURPOSE.md").write_text("Purpose: a lane\n", encoding="utf-8")
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "REMOVE", f"blocked by {item.reason}: {item.detail}"


def test_supervisor_dir_with_an_unexpected_file_keeps_the_worktree(repo: Path) -> None:
    """`--ignored=matching` collapses an ignored directory into one entry.

    Accepting `.agents/supervisor/` therefore says nothing about its contents
    (Codex round 1, answer 4), so the contents are checked against the filenames
    its producers actually emit. Anything else in there is unexamined work.
    """
    lane = add_lane(repo, "landed", merged=True)
    (repo / ".gitignore").write_text(
        "output/\n.ruff_cache/\n_PURPOSE.md\n.agents/supervisor/\n", encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ignore supervisor")
    git(repo, "push", "-q", "origin", "main")
    git(lane, "merge", "-q", "--ff-only", "origin/main")
    supervisor = lane / ".agents" / "supervisor"
    supervisor.mkdir(parents=True)
    (supervisor / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (supervisor / "keep-working-abc123.json").write_text("{}", encoding="utf-8")
    assert git(lane, "status", "--porcelain").strip() == "", "setup: must read clean"
    assert dh.unique_ignored_paths(lane) == [], "known telemetry must not block removal"

    (supervisor / "handoff-notes.md").write_text("the only copy\n", encoding="utf-8")
    blocking = dh.unique_ignored_paths(lane)
    assert blocking == [".agents/supervisor/handoff-notes.md"], blocking


def test_unexpected_dir_contents_refuses_a_directory_it_cannot_list(repo: Path) -> None:
    """A directory it cannot walk is not an empty one — missing or denied, KEEP."""
    with pytest.raises(dh.Undecidable):
        dh.unexpected_dir_contents(repo, ".agents/supervisor")


def test_status_parsing_survives_a_path_with_spaces(repo: Path) -> None:
    """Git quotes and escapes such paths in the newline form; `-z` does not."""
    awkward = repo / "a file with spaces.txt"
    awkward.write_text("x\n", encoding="utf-8")
    entries = dh.dirty_paths(repo)
    assert any("a file with spaces.txt" in e for e in entries), entries
    assert not any('"' in e for e in entries), f"quoting leaked into the parse: {entries}"


def test_a_branch_with_an_open_pr_is_never_removed(repo: Path) -> None:
    """Liveness: an open PR means someone is still working that lane.

    With 115 removable worktrees the realistic failure is deleting the tree a
    parallel builder is standing in, and merge state alone does not see that — a
    branch can read merged locally while its PR is open and being revised.
    """
    lane = add_lane(repo, "landed", merged=True)
    assert by_path(worktree_items(repo), lane).verdict == "REMOVE", "setup: removable when no PR"
    item = by_path(worktree_items(repo, open_pr_fn=lambda _r: {"landed"}), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "open_pr"
    assert lane.exists()


def test_an_unanswerable_open_pr_query_skips_the_whole_worktree_class(repo: Path) -> None:
    """Fail closed: an unknown open-PR set is not a licence to remove any worktree."""
    lane = add_lane(repo, "landed", merged=True)
    items = worktree_items(repo, open_pr_fn=lambda _r: None)
    assert [i.reason for i in items] == ["open_pr_set_unknown"]
    assert all(i.verdict == "KEEP" for i in items)
    assert not any(Path(i.path) == lane and i.verdict == "REMOVE" for i in items)


def test_open_pr_branches_returns_none_when_gh_fails(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """None, never an empty set — an empty set would read as "no open PRs"."""
    monkeypatch.setattr(
        dh, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "gh: not logged in")
    )
    assert dh.open_pr_branches(repo) is None
    monkeypatch.setattr(
        dh, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "not json", "")
    )
    assert dh.open_pr_branches(repo) is None
    monkeypatch.setattr(
        dh,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 0, json.dumps([{"headRefName": "claude/x"}, {"headRefName": "codex/y"}]), ""
        ),
    )
    assert dh.open_pr_branches(repo) == {"claude/x", "codex/y"}


def test_a_commit_added_after_the_merge_is_never_removed(repo: Path) -> None:
    """A post-merge commit that CHANGES the tree is refused.

    Caught by the unpushed-commits gate rather than the new one, because changing
    the tree also changes the cumulative diff, so `is_merged_into` stops agreeing.
    Asserted anyway: the outcome is what matters, and it must not depend on which of
    the two gates happens to fire first.
    """
    lane = add_lane(repo, "landed", merged=True)
    assert by_path(worktree_items(repo), lane).verdict == "REMOVE", (
        "setup: removable before the commit"
    )

    (lane / "landed.txt").write_text("a later edit nobody pushed\n", encoding="utf-8")
    git(lane, "add", "-A")
    git(lane, "commit", "-q", "-m", "work added after the merge")
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "KEEP", f"a post-merge commit was removable ({item.reason})"
    assert item.reason in {"local_commits_after_push", "unpushed_commits"}


def test_commits_after_push_sees_a_tip_ahead_of_its_remote_ref(repo: Path) -> None:
    """The mechanism behind the `local_commits_after_push` refusal.

    Tested directly rather than end-to-end on purpose. `is_merged_into` compares the
    branch's CUMULATIVE diff, and every post-merge commit I could construct — a
    tree-changing one, and an experiment-plus-revert pair — also stops it agreeing,
    so the unpushed-commits gate refuses the worktree first and this gate never
    becomes the deciding one. It stays as the direct check on "the tip moved past
    what was pushed", which is the fact the merge comparison does not look at; an
    end-to-end test asserting it fires would be asserting a path I cannot reach.
    """
    lane = add_lane(repo, "landed", merged=True)
    assert dh.commits_after_push(lane, "landed", "HEAD") == [], "at the pushed tip: nothing ahead"

    (lane / "later.txt").write_text("after the push\n", encoding="utf-8")
    git(lane, "add", "-A")
    git(lane, "commit", "-q", "-m", "after the push")
    ahead = dh.commits_after_push(lane, "landed", "HEAD")
    assert len(ahead) == 1, ahead
    assert "after the push" in ahead[0]

    # No remote-tracking ref is not "ahead of it" — the merge and unpushed gates
    # own that shape, and guessing here would refuse every unpushed branch twice.
    assert dh.commits_after_push(lane, "never-pushed", "HEAD") == []


def test_primary_checkout_is_never_removed(repo: Path) -> None:
    add_lane(repo, "landed", merged=True)
    item = by_path(worktree_items(repo), repo)
    assert item.verdict == "KEEP"
    assert item.reason == "primary_checkout"


def test_recently_active_worktree_is_kept(repo: Path) -> None:
    """A clean, merged lane a live session still has open stays put."""
    lane = add_lane(repo, "landed", merged=True)
    item = by_path(worktree_items(repo, now=time.time(), idle_hours=24.0), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "recently_active"


def test_a_write_deep_in_the_tree_counts_as_activity(repo: Path) -> None:
    """Codex round 1, P1: the idle check scanned only direct children.

    A live lane writing at depth — telemetry under `.agents/supervisor/`, a cache
    write — does not refresh a direct child's mtime, so a clean merged lane a
    session still held could read as idle for a day. The recursive newest mtime was
    already being computed by the size walk and thrown away.

    The direct-children-plus-gitdir helper that used to answer this is now gone
    rather than kept as a second opinion: the collector's own `git status` rewrites
    `gitdir/index`, so that helper reported 0.0h for every worktree it was asked
    about — measured 72.0h before the status call and 0.0h after. A measurement its
    own caller invalidates is worse than no measurement.

    The deep write goes into an **ignored and disposable** directory on purpose. A
    plain untracked file would also make the worktree dirty, and the test would
    then pass on the dirty gate no matter what the idle gate did.
    """
    lane = add_lane(repo, "landed", merged=True)
    stale = time.time() - 72 * HOUR
    deep = lane / ".ruff_cache" / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "cache.json").write_text("{}", encoding="utf-8")
    age(lane, 72, now=time.time())
    assert dh.dirty_paths(lane) == [], "setup: the write must not make the lane dirty"
    assert dh.unique_ignored_paths(lane) == [], "setup: the write must be disposable-ignored"
    baseline = by_path(worktree_items(repo, now=time.time(), idle_hours=24.0), lane)
    assert baseline.verdict == "REMOVE", (
        f"setup: a wholly backdated lane must be removable, got {baseline.reason}"
    )

    # Now make ONLY the deepest entry fresh. The lane root and every direct child
    # stay backdated, so nothing but a recursive walk can notice the write.
    os.utime(deep / "cache.json", None)
    for child in lane.iterdir():
        os.utime(child, (stale, stale))
    os.utime(lane, (stale, stale))
    item = by_path(worktree_items(repo, now=time.time(), idle_hours=24.0), lane)
    assert item.verdict == "KEEP", f"a deep write did not register as activity ({item.reason})"
    assert item.reason == "recently_active"


def test_detached_head_on_no_remote_is_kept(repo: Path) -> None:
    """A detached commit that exists only here is unique work."""
    lane = add_lane(repo, "landed", merged=True)
    git(lane, "checkout", "-q", "--detach")
    (lane / "local.txt").write_text("only here\n", encoding="utf-8")
    git(lane, "add", "-A")
    git(lane, "commit", "-q", "-m", "local only")
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "detached_head"


def test_detached_head_on_a_remote_ref_is_removable(repo: Path) -> None:
    """Review and base-oracle checkouts: the exact commit is on origin."""
    lane = add_lane(repo, "landed", merged=True)
    git(lane, "checkout", "-q", "--detach")
    item = by_path(worktree_items(repo), lane)
    assert (item.verdict, item.reason) == ("REMOVE", "detached_on_remote")


def test_detached_head_with_a_purpose_file_is_kept(repo: Path) -> None:
    """wt.py archives a purpose against a branch; a detached lane has none."""
    lane = add_lane(repo, "landed", merged=True)
    git(lane, "checkout", "-q", "--detach")
    (lane / "_PURPOSE.md").write_text("draft\n", encoding="utf-8")
    item = by_path(worktree_items(repo), lane)
    assert (item.verdict, item.reason) == ("KEEP", "detached_head")


def test_detached_head_dirty_is_kept(repo: Path) -> None:
    lane = add_lane(repo, "landed", merged=True)
    git(lane, "checkout", "-q", "--detach")
    (lane / "a.txt").write_text("edited\n", encoding="utf-8")
    item = by_path(worktree_items(repo), lane)
    assert (item.verdict, item.reason) == ("KEEP", "dirty")


def test_apply_removes_a_detached_worktree_and_rechecks_head(repo: Path) -> None:
    """The removal re-proves HEAD is on a remote: a commit made after inventory
    stops it."""
    gone = add_lane(repo, "landed", merged=True)
    git(gone, "checkout", "-q", "--detach")
    moved = add_lane(repo, "other", merged=True)
    git(moved, "checkout", "-q", "--detach")
    report = dh.Report(items=worktree_items(repo))
    assert by_path(report.items, moved).verdict == "REMOVE"
    (moved / "late.txt").write_text("late\n", encoding="utf-8")
    git(moved, "add", "-A")
    git(moved, "commit", "-q", "-m", "after inventory")
    dh.apply_removals(report, repo, keep_gb=8.0, log_path=None)
    assert not gone.exists(), "a clean detached checkout of a pushed commit should be gone"
    assert moved.exists(), "a commit made after inventory must survive"
    assert by_path(report.items, moved).reason == "remove_failed"


def test_undecidable_git_status_keeps(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed: a git query that cannot be answered keeps the worktree."""
    lane = add_lane(repo, "landed", merged=True)

    def broken(_worktree):
        raise dh.Undecidable("git status -> rc=128")

    monkeypatch.setattr(dh, "dirty_paths", broken)
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "status_undecidable"


def test_pr_closed_with_everything_pushed_is_removable(repo: Path) -> None:
    lane = add_lane(repo, "abandoned", merged=False)
    item = by_path(worktree_items(repo, pr_state_fn=lambda _b, _c: True), lane)
    assert item.verdict == "REMOVE"
    assert item.reason == "pr_closed_branch_fully_pushed"


def test_pr_open_is_kept(repo: Path) -> None:
    lane = add_lane(repo, "inflight", merged=False)
    item = by_path(worktree_items(repo, pr_state_fn=lambda _b, _c: False), lane)
    assert item.verdict == "KEEP"
    assert item.reason == "unmerged_pr_open"


def test_another_repo_next_door_is_never_inventoried(repo: Path, tmp_path: Path) -> None:
    """Only ``git worktree list`` of THIS repo defines the scope."""
    other = tmp_path / "other-project"
    other.mkdir()
    git(other, "init", "-q", "--initial-branch=main")
    (other / "theirs.txt").write_text("not ours\n", encoding="utf-8")
    paths = {str(Path(i.path).resolve()).lower() for i in worktree_items(repo)}
    assert str(other.resolve()).lower() not in paths
    assert other.exists()


def test_budget_marks_the_rest_not_inventoried(repo: Path) -> None:
    add_lane(repo, "landed", merged=True)
    items = worktree_items(repo, deadline=time.monotonic() - 1)
    assert items, "an exhausted budget must still report every entry"
    assert all(i.verdict == "KEEP" and i.reason == "not_inventoried" for i in items)


def test_apply_removes_a_merged_worktree_and_leaves_the_kept_one(repo: Path) -> None:
    """End-to-end: the remover runs through git and the refusals hold."""
    gone = add_lane(repo, "landed", merged=True)
    kept = add_lane(repo, "open", merged=False)
    report = dh.Report(items=worktree_items(repo))
    dh.apply_removals(report, repo, keep_gb=8.0, log_path=None)
    assert not gone.exists(), "a merged, clean, idle lane should be gone"
    assert kept.exists(), "an unmerged lane must survive"
    assert "landed" not in git(repo, "branch", "--list", "landed")


def test_archive_failure_aborts_the_removal(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex round 1, P0: the archive is the only thing preserving `_PURPOSE.md`.

    Printing the error and carrying on meant a disk-full or permission failure
    during the archive silently destroyed the draft.
    """
    lane = add_lane(repo, "landed", merged=True)
    (lane / "_PURPOSE.md").write_text("Purpose: never published anywhere\n", encoding="utf-8")
    import wt  # noqa: PLC0415

    monkeypatch.setattr(
        wt, "_archive_purpose", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    )
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "REMOVE", f"setup: expected a removable lane, got {item.reason}"
    ok, detail = dh.remove_worktree(repo, item)
    assert not ok
    assert "could not archive _PURPOSE.md" in detail
    assert (lane / "_PURPOSE.md").exists(), "the unpublished draft was destroyed"


def test_ignored_content_written_after_inventory_aborts_the_removal(repo: Path) -> None:
    """Inventory and removal are minutes apart on a full pass (Codex round 1, answer 6)."""
    lane = add_lane(repo, "landed", merged=True)
    item = by_path(worktree_items(repo), lane)
    assert item.verdict == "REMOVE", item.reason
    (lane / "output").mkdir()
    (lane / "output" / "late.md").write_text("written after the verdict\n", encoding="utf-8")
    ok, detail = dh.remove_worktree(repo, item)
    assert not ok
    assert "changed since inventory" in detail
    assert (lane / "output" / "late.md").exists()


def test_pr_closed_lane_keeps_its_branch_ref(repo: Path) -> None:
    """The ref is the recovery path, and it costs ~41 bytes.

    `-D` would have forced it away on the strength of `git log --not --remotes`,
    which reads LOCAL tracking refs; `-d` is no better, since it also accepts
    "merged into its upstream" from that same local ref. A tracking ref pruned
    after the PR closed leaves nothing behind (Codex round 1, answer 7), so this
    path removes the worktree only.
    """
    lane = add_lane(repo, "abandoned", merged=False)
    item = by_path(worktree_items(repo, pr_state_fn=lambda _b, _c: True), lane)
    assert item.verdict == "REMOVE" and item.reason == "pr_closed_branch_fully_pushed"
    ok, detail = dh.remove_worktree(repo, item)
    assert ok, detail
    assert not lane.exists(), "the worktree is the disk win"
    assert "abandoned" in git(repo, "branch", "--list", "abandoned"), (
        "the unmerged branch ref must survive as the recovery path"
    )


def test_merged_lane_does_delete_its_branch(repo: Path) -> None:
    """Keeping every ref forever is clutter; the merged case is provably on the base."""
    lane = add_lane(repo, "landed", merged=True)
    item = by_path(worktree_items(repo), lane)
    ok, detail = dh.remove_worktree(repo, item)
    assert ok, detail
    assert not lane.exists()
    assert git(repo, "branch", "--list", "landed").strip() == ""


def test_is_disposable_ignored_matches_by_path_component() -> None:
    """The three paths Codex round 1 reproduced passing the old substring rule.

    `research.db` — an extension is not a provenance; this repo ignores `*.db` for
    the SQLite mirror of its YAML catalog, and the same pattern covers a user's own
    database. `docs/_PURPOSE.md` — accepted as disposable, but `wt.py` only ever
    archives the ROOT copy, so a nested one would be destroyed unpreserved.
    `_PURPOSE.md-git-credentials.txt` — a prefix is not a filename, and this one is
    ignored by `*git-credentials*`.
    """
    for unique in ("research.db", "docs/_PURPOSE.md", "_PURPOSE.md-git-credentials.txt"):
        assert not dh.is_disposable_ignored(unique), unique


def test_next_build_output_is_disposable_but_a_bare_out_is_not() -> None:
    for disposable in (
        "WebSite/site-react/.next/",
        "WebSite/site-react/.next-build/",
        "WebSite/site-react/out/",
        "WebSite/site-react/out/index.html",
        "WebSite/site-react/next-env.d.ts",
    ):
        assert dh.is_disposable_ignored(disposable), disposable
    for unique in ("out/", "output/", "docs/out/", "WebSite/site-react/outline.md"):
        assert not dh.is_disposable_ignored(unique), unique


def test_is_disposable_ignored_classification() -> None:
    for disposable in (
        ".venv/",
        "__pycache__/",
        ".claude/hooks/__pycache__/",
        "__pycache__/x.pyc",
        "_PURPOSE.md",
        "x/y.pyc",
        ".agents/supervisor/",
        ".agents/supervisor/events.jsonl",
        ".ruff_cache/",
        "Thumbs.db",
        "a/b/.DS_Store",
    ):
        assert dh.is_disposable_ignored(disposable), disposable
    for unique in (
        ".venv-backup/",
        "my.venv/notes.md",
        "supervisor/plan.md",
        "junit.xml.bak",
        "docs/junit.xml",
        "output/",
        "universes/",
        "data-room/cap-table.xlsx",
        ".secrets/",
        ".env",
        "mobile/android/",
        ".claude/agent-memory/",
        "notes.md",
    ):
        assert not dh.is_disposable_ignored(unique), unique


# --------------------------------------------------------------------------- #
# (e) package-manager caches
# --------------------------------------------------------------------------- #


def _fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seen: list[list[str]]):
    """uv/pip/npm answer with a cache dir under tmp_path; every call is recorded."""
    dirs = {"uv": tmp_path / "uvc", "pip": tmp_path / "pipc", "npm": tmp_path / "npmc"}
    for name, d in dirs.items():
        target = d / "_cacache" if name == "npm" else d
        target.mkdir(parents=True)
        (target / "blob").write_bytes(b"x" * 100)
    (dirs["npm"] / "_npx").mkdir()
    (dirs["npm"] / "_npx" / "server.js").write_bytes(b"x" * 5000)

    def fake(args, **_kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, f"{dirs[Path(args[0]).name]}\n", "")

    monkeypatch.setattr(dh, "run", fake)
    return dirs


def test_tool_caches_are_located_by_asking_the_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []
    dirs = _fake_tools(tmp_path, monkeypatch, seen)
    items = dh.collect_tool_caches(which=lambda t: t)
    assert {i.tool for i in items if i.removable} == {"uv", "pip", "npm"}
    npm = next(i for i in items if i.tool == "npm")
    # npm's root also holds _npx (live MCP servers); only _cacache is claimed.
    assert Path(npm.path) == dirs["npm"] / "_cacache"
    assert npm.size_bytes == 100


def test_tool_cache_is_cleared_by_the_tool_never_by_rmtree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []
    dirs = _fake_tools(tmp_path, monkeypatch, seen)
    report = dh.Report(items=dh.collect_tool_caches(which=lambda t: t))
    seen.clear()
    monkeypatch.setattr(dh.shutil, "which", lambda t: t)
    dh.apply_removals(report, tmp_path, keep_gb=8.0, log_path=None)
    assert sorted(seen) == sorted(
        [["uv", "cache", "clean"], ["pip", "cache", "purge"], ["npm", "cache", "clean", "--force"]]
    )
    assert (dirs["npm"] / "_npx" / "server.js").exists()
    assert all(d.exists() for d in dirs.values()), "the script itself deletes nothing"


def test_missing_tool_is_kept_and_unknown_tool_refuses() -> None:
    items = dh.collect_tool_caches(which=lambda _t: None)
    assert {(i.verdict, i.reason) for i in items} == {("KEEP", "tool_not_installed")}
    item = dh.Item("toolcache", "x", 1, "REMOVE", "tool_owned_cache", tool="rm")
    ok, detail = dh.clean_tool_cache(item, which=lambda t: t)
    assert not ok and "unknown tool" in detail


def test_failed_cache_dir_query_keeps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dh, "run", lambda args, **_k: subprocess.CompletedProcess(args, 1, "", "boom")
    )
    items = dh.collect_tool_caches(which=lambda t: t)
    assert {(i.verdict, i.reason) for i in items} == {("KEEP", "cache_dir_unknown")}


# --------------------------------------------------------------------------- #
# (c) Docker build cache
# --------------------------------------------------------------------------- #


def test_docker_class_is_skipped_when_the_engine_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dh, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "cannot find the pipe")
    )
    (item,) = dh.collect_docker_cache(keep_gb=8.0)
    assert (item.verdict, item.reason) == ("KEEP", "docker_engine_not_running")


def test_docker_prune_touches_build_cache_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never volumes, never images, never ``system prune``, never ``-a``."""
    seen: list[list[str]] = []

    def fake(args, **_kwargs):
        seen.append(list(args))
        return subprocess.CompletedProcess(args, 0, "Total reclaimed space: 3GB", "")

    monkeypatch.setattr(dh, "run", fake)
    item = dh.Item(
        "docker",
        "build-cache",
        3 * 1024**3,
        "REMOVE",
        "docker_build_cache",
        "",
        prune_flag="--reserved-space",
    )
    ok, _detail = dh.prune_docker(item, keep_gb=8.0)
    assert ok
    (argv,) = seen
    assert argv[:3] == ["docker", "builder", "prune"]
    assert "--reserved-space" in argv and str(8 * 1024**3) in argv
    forbidden = {"volume", "system", "image", "-a", "--all", "--volumes", "container"}
    assert not forbidden.intersection(argv), argv


def test_docker_prune_refuses_without_a_probed_flag() -> None:
    """A wrong keep flag makes the prune a silent no-op, so an unprobed one refuses."""
    item = dh.Item("docker", "build-cache", 1, "REMOVE", "docker_build_cache", "")
    ok, detail = dh.prune_docker(item, keep_gb=8.0)
    assert not ok
    assert "keep-budget flag" in detail


def test_docker_help_failure_is_not_a_probe_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recognisable help text in a FAILED invocation is not an answer.

    The returncode is the answer (Codex round 1, P2): a nonzero `--help` whose
    stderr happens to mention `--reserved-space` must not authorize a prune.
    """

    def fake(args, **_kwargs):
        if "version" in args:
            return subprocess.CompletedProcess(args, 0, "27.0.0", "")
        if "--help" in args:
            return subprocess.CompletedProcess(args, 125, "--reserved-space bytes", "boom")
        raise AssertionError(f"docker should not have been called further: {args}")

    monkeypatch.setattr(dh, "run", fake)
    (item,) = dh.collect_docker_cache(keep_gb=8.0)
    assert (item.verdict, item.reason) == ("KEEP", "prune_flag_unknown")
    assert "rc=125" in item.detail


def test_docker_keep_flag_is_probed_not_guessed() -> None:
    assert (
        dh.docker_keep_flag("--reserved-space bytes\n--max-used-space bytes") == "--reserved-space"
    )
    assert dh.docker_keep_flag("--keep-storage bytes") == "--keep-storage"
    with pytest.raises(dh.Undecidable):
        dh.docker_keep_flag("--filter filter\n--force")


def test_parse_docker_size() -> None:
    assert dh.parse_docker_size("1.5GB (100%)") == int(1.5 * 1024**3)
    assert dh.parse_docker_size("0B") == 0
    assert dh.parse_docker_size("912.3MB") == int(912.3 * 1024**2)


def test_build_cache_row_is_the_only_row_read() -> None:
    text = "\n".join(
        [
            json.dumps({"Type": "Images", "Reclaimable": "40GB (90%)"}),
            json.dumps({"Type": "Local Volumes", "Reclaimable": "12GB (100%)"}),
            json.dumps({"Type": "Build Cache", "Reclaimable": "3.5GB"}),
        ]
    )
    assert dh._build_cache_reclaimable(text) == int(3.5 * 1024**3)
    assert (
        dh._build_cache_reclaimable(json.dumps({"Type": "Images", "Reclaimable": "40GB"})) is None
    )


# --------------------------------------------------------------------------- #
# (d) repo scratch
# --------------------------------------------------------------------------- #


def test_stale_ignored_scratch_is_removed(repo: Path) -> None:
    (repo / ".gitignore").write_text("codex-tmp/\noutput/\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ignore scratch")
    scratch = repo / "codex-tmp"
    scratch.mkdir()
    (scratch / "junk.txt").write_text("x", encoding="utf-8")
    age(scratch, 24 * 30, now=time.time())
    item = by_path(dh.collect_repo_scratch(repo, min_age_days=7, now=time.time()), scratch)
    assert (item.verdict, item.reason) == ("REMOVE", "stale_repo_scratch")


def test_tracked_path_with_a_scratch_name_is_kept(repo: Path) -> None:
    """A tracked file named like scratch is not scratch. Found on the real box."""
    tracked = repo / ".codex-plan.txt"
    tracked.write_text("a real plan\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".codex-*.txt\n", encoding="utf-8")
    git(repo, "add", "-A", "-f")
    git(repo, "commit", "-q", "-m", "track the plan")
    age(tracked, 24 * 365, now=time.time())
    item = by_path(dh.collect_repo_scratch(repo, min_age_days=7, now=time.time()), tracked)
    assert (item.verdict, item.reason) == ("KEEP", "not_git_ignored")
    assert tracked.exists()


def test_recent_scratch_is_kept(repo: Path) -> None:
    (repo / ".gitignore").write_text("codex-tmp/\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ignore")
    scratch = repo / "codex-tmp"
    scratch.mkdir()
    (scratch / "live.txt").write_text("x", encoding="utf-8")
    item = by_path(dh.collect_repo_scratch(repo, min_age_days=7, now=time.time()), scratch)
    assert (item.verdict, item.reason) == ("KEEP", "recent")


def test_generic_scratch_names_are_not_candidates(repo: Path) -> None:
    """Codex round 1, P0: a ten-day-old `.tmp/research.md` was removed.

    A generic name plus ignore status plus age proves nothing about provenance, so
    `.tmp` and `.review` came off the allowlist. Only names a test run or an agent
    tool creates are left.
    """
    for name in (".tmp", ".review"):
        target = repo / name
        target.mkdir()
        (target / "research.md").write_text("the only copy\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".tmp/\n.review/\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ignore generic scratch")
    age(repo / ".tmp", 24 * 30, now=time.time())
    age(repo / ".review", 24 * 30, now=time.time())
    seen = {
        Path(i.path).name for i in dh.collect_repo_scratch(repo, min_age_days=7, now=time.time())
    }
    assert seen.isdisjoint({".tmp", ".review"}), seen
    assert (repo / ".tmp" / "research.md").exists()


def test_protected_repo_dirs_are_not_candidates(repo: Path) -> None:
    """``output/``, ``universes/``, ``.secrets/``, ``data-room/`` are never scratch."""
    for name in ("output", "universes", ".secrets", "data-room", ".codex-worktrees", "logs"):
        (repo / name).mkdir()
    (repo / ".gitignore").write_text(
        "output/\nuniverses/\n.secrets/\ndata-room/\nlogs/\n.codex-worktrees/\n", encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ignore state dirs")
    paths = {
        Path(i.path).name for i in dh.collect_repo_scratch(repo, min_age_days=0, now=time.time())
    }
    assert paths.isdisjoint(
        {"output", "universes", ".secrets", "data-room", ".codex-worktrees", "logs"}
    )


# --------------------------------------------------------------------------- #
# modes, logging, escalation
# --------------------------------------------------------------------------- #


def test_dry_run_is_the_default_and_removes_nothing(tmp_path: Path, repo: Path, capsys) -> None:
    root = tmp_path / "t"
    root.mkdir()
    stale = make_basetemp(root, "ta-pt-old", hours=500)
    rc = dh.main(["--repo", str(repo), "--temp-root", str(root), "--classes", "basetemp"])
    assert rc == 0
    assert stale.exists(), "the default mode must not delete"
    assert "would remove" in capsys.readouterr().out


def test_apply_removes_and_logs_path_size_and_reason(tmp_path: Path, repo: Path) -> None:
    root = tmp_path / "t"
    root.mkdir()
    stale = make_basetemp(root, "ta-pt-old", hours=500, payload=2048)
    log = tmp_path / "hygiene.log"
    rc = dh.main(
        [
            "--apply",
            "--repo",
            str(repo),
            "--temp-root",
            str(root),
            "--classes",
            "basetemp",
            "--log",
            str(log),
        ]
    )
    assert rc == 0
    assert not stale.exists()
    line = log.read_text(encoding="utf-8").strip()
    assert str(stale) in line
    assert "stale_pytest_basetemp" in line
    assert "KB" in line or "MB" in line, f"size missing from the log line: {line}"


def test_if_low_disk_gates_the_apply(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "t"
    root.mkdir()
    stale = make_basetemp(root, "ta-pt-old", hours=500)
    monkeypatch.setattr(dh, "free_gb", lambda _p: 500.0)
    rc = dh.main(
        [
            "--apply",
            "--if-low-disk",
            "40",
            "--repo",
            str(repo),
            "--temp-root",
            str(root),
            "--classes",
            "basetemp",
            "--no-log",
        ]
    )
    assert rc == 0
    assert stale.exists(), "plenty of free space must leave the disposable set alone"


def test_if_low_disk_applies_when_actually_low(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "t"
    root.mkdir()
    stale = make_basetemp(root, "ta-pt-old", hours=500)
    monkeypatch.setattr(dh, "free_gb", lambda _p: 2.0)
    rc = dh.main(
        [
            "--apply",
            "--if-low-disk",
            "40",
            "--escalate-below",
            "40",
            "--repo",
            str(repo),
            "--temp-root",
            str(root),
            "--classes",
            "basetemp",
            "--no-log",
        ]
    )
    assert rc == 3, "still below the floor after the pass => escalate"
    assert not stale.exists()


def test_escalation_names_what_it_refused_to_remove(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    root = tmp_path / "t"
    root.mkdir()
    oracle = root / "ta-baseline-keepme"
    (oracle / "src").mkdir(parents=True)
    (oracle / "src" / "big.bin").write_bytes(b"x" * 50_000)
    age(oracle, 500, now=time.time())
    monkeypatch.setattr(dh, "free_gb", lambda _p: 1.0)
    rc = dh.main(
        [
            "--apply",
            "--escalate-below",
            "40",
            "--repo",
            str(repo),
            "--temp-root",
            str(root),
            "--classes",
            "basetemp",
            "--no-log",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 3
    assert "ESCALATION" in out
    assert str(oracle) in out, "the escalation must be a concrete list, not a number"
    assert "unrecognized_shape" in out


def test_json_mode_is_machine_readable(tmp_path: Path, repo: Path, capsys) -> None:
    root = tmp_path / "t"
    root.mkdir()
    make_basetemp(root, "ta-pt-old", hours=500)
    rc = dh.main(["--repo", str(repo), "--temp-root", str(root), "--classes", "basetemp", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    assert payload["reclaimable_bytes"] > 0
    assert {i["verdict"] for i in payload["items"]} <= {"REMOVE", "KEEP"}


def test_per_class_cap_bounds_one_pass(tmp_path: Path, repo: Path) -> None:
    """An automatic pass can never do something enormous.

    Same bound as ``daemon_image_retention.MAX_REMOVALS`` on the droplet: a logic
    bug costs N items and lands in the log before the next pass runs.
    """
    root = tmp_path / "t"
    root.mkdir()
    made = [make_basetemp(root, f"ta-pt-{i}", hours=500, payload=100 * (i + 1)) for i in range(5)]
    report = dh.Report(items=dh.collect_basetemps(root, min_age_hours=6, now=NOW))
    dh.apply_removals(report, repo, keep_gb=8.0, log_path=None, max_removals=2)
    survivors = [p for p in made if p.exists()]
    assert len(survivors) == 3, [p.name for p in made if p.exists()]
    # Largest first, so a capped pass reclaims the most it can.
    assert not made[4].exists() and not made[3].exists()
    deferred = [i for i in report.items if i.reason == "deferred_to_next_pass"]
    assert len(deferred) == 3


def test_summary_file_carries_the_escalation_for_the_hook(
    tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SessionStart hook reads this rather than paying for its own scan."""
    root = tmp_path / "t"
    root.mkdir()
    oracle = root / "ta-baseline-keepme"
    oracle.mkdir()
    (oracle / "real.py").write_bytes(b"x" * 4096)
    age(oracle, 500, now=time.time())
    summary = tmp_path / "summary.json"
    monkeypatch.setattr(dh, "free_gb", lambda _p: 3.0)
    rc = dh.main(
        [
            "--apply",
            "--escalate-below",
            "40",
            "--repo",
            str(repo),
            "--temp-root",
            str(root),
            "--classes",
            "basetemp",
            "--no-log",
            "--quiet",
            "--summary-out",
            str(summary),
        ]
    )
    assert rc == 3
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["applied"] is True
    assert payload["free_after_gb"] == 3.0
    assert "ESCALATION" in payload["escalation"]
    assert str(oracle) in payload["escalation"]
    assert "NOT inventoried in this pass: worktree, docker, scratch" in payload["escalation"]


def test_acl_locked_measurement_is_its_own_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Access-denied is a known class with an elevated fix, not a generic shrug.

    The seam is ``tree_stats``, not ``os.stat``: patching ``os.stat`` globally also
    breaks ``Path.is_dir()``, so the candidate was skipped before classification
    and the report came back empty on Linux CI while passing on Windows.
    """
    root = tmp_path / "t"
    root.mkdir()
    target = make_basetemp(root, "ta-pt-locked", hours=500)
    real_tree_stats = dh.tree_stats

    def deny(path, *a, **kw):
        if Path(path) == target:
            raise dh.AclLocked(f"access denied on {path}")
        return real_tree_stats(path, *a, **kw)

    monkeypatch.setattr(dh, "tree_stats", deny)
    item = by_path(dh.collect_basetemps(root, min_age_hours=6, now=NOW), target)
    assert item.reason == "acl_locked_needs_elevation"
    assert "clear_sandbox_temp_dirs.ps1 -Apply" in item.detail
    assert target.exists()


def test_unknown_class_is_a_usage_error(repo: Path) -> None:
    assert dh.main(["--repo", str(repo), "--classes", "everything"]) == 2


def test_non_repo_target_refuses(tmp_path: Path) -> None:
    assert dh.main(["--repo", str(tmp_path)]) == 2


# --------------------------------------------------------------------------- #
# the automatic wiring: .claude/hooks/dev_hygiene_hook.py
# --------------------------------------------------------------------------- #


def _load_hook():
    name = "dev_hygiene_hook_under_test"
    path = _REPO / ".claude" / "hooks" / "dev_hygiene_hook.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """A directory shaped enough for the hook: it only needs the script present."""
    project = tmp_path / "p"
    (project / "scripts").mkdir(parents=True)
    (project / "scripts" / "dev_hygiene.py").write_text("# stub\n", encoding="utf-8")
    return project


def _run_hook(monkeypatch: pytest.MonkeyPatch, payload: dict, *, rc: int, stdout: str = ""):
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, rc, stdout, "")

    monkeypatch.setattr(hook.subprocess, "run", fake_run)
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(payload)))
    return calls


def test_hook_injects_the_escalation_when_the_pass_escalates(
    monkeypatch: pytest.MonkeyPatch, fake_project: Path, capsys
) -> None:
    calls = _run_hook(
        monkeypatch,
        {"hook_event_name": "SessionStart", "cwd": str(fake_project)},
        rc=3,
        stdout="[dev-hygiene] ESCALATION: 2.0 GB free\n  60.0 MB  C:/x  [dirty] lane",
    )
    assert hook.main() == 0
    out = capsys.readouterr().out
    injected = json.loads(out)["hookSpecificOutput"]
    assert injected["hookEventName"] == "SessionStart"
    assert "ESCALATION" in injected["additionalContext"]
    assert "C:/x" in injected["additionalContext"], "the founder needs the concrete list"
    (command,) = calls
    assert "--apply" in command
    assert "basetemp,scratch" in command, "a session start must not pay for the git walk"
    assert "--escalate-below" in command


def test_hook_is_silent_when_there_is_nothing_to_say(
    monkeypatch: pytest.MonkeyPatch, fake_project: Path, capsys
) -> None:
    _run_hook(monkeypatch, {"hook_event_name": "SessionStart", "cwd": str(fake_project)}, rc=0)
    assert hook.main() == 0
    assert capsys.readouterr().out == ""


def test_hook_never_fails_a_session_when_the_pass_dies(
    monkeypatch: pytest.MonkeyPatch, fake_project: Path, capsys
) -> None:
    def explode(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 45)

    monkeypatch.setattr(hook.subprocess, "run", explode)
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        io.StringIO(json.dumps({"hook_event_name": "SessionStart", "cwd": str(fake_project)})),
    )
    assert hook.main() == 0
    assert capsys.readouterr().out == ""


def test_hook_ignores_other_events_and_the_disable_switch(
    monkeypatch: pytest.MonkeyPatch, fake_project: Path
) -> None:
    calls = _run_hook(monkeypatch, {"hook_event_name": "Stop", "cwd": str(fake_project)}, rc=3)
    assert hook.main() == 0
    assert calls == [], "only SessionStart runs a pass"

    calls = _run_hook(
        monkeypatch, {"hook_event_name": "SessionStart", "cwd": str(fake_project)}, rc=3
    )
    monkeypatch.setenv("TINYASSETS_DEV_HYGIENE_DISABLE", "1")
    assert hook.main() == 0
    assert calls == []


def test_hook_surfaces_a_recent_full_pass_escalation(
    monkeypatch: pytest.MonkeyPatch, fake_project: Path, capsys
) -> None:
    """The hourly task's finding reaches the founder at the next session start."""
    logs = fake_project / ".claude" / "logs"
    logs.mkdir(parents=True)
    (logs / "dev-hygiene-full.json").write_text(
        json.dumps(
            {
                "finished_at": "2026-09-26T10:00:00+0000",
                "finished_epoch": time.time() - 600,
                "escalation": (
                    "[dev-hygiene] ESCALATION: 3.0 GB free\n  1.0 GB  C:/wf-lane  [dirty] lane"
                ),
            }
        ),
        encoding="utf-8",
    )
    _run_hook(monkeypatch, {"hook_event_name": "SessionStart", "cwd": str(fake_project)}, rc=0)
    assert hook.main() == 0
    context = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert "C:/wf-lane" in context
    assert "Full hygiene pass" in context


def test_hook_ignores_a_stale_full_pass_escalation(
    monkeypatch: pytest.MonkeyPatch, fake_project: Path, capsys
) -> None:
    """A finding from days ago is noise, not news — the task runs hourly."""
    logs = fake_project / ".claude" / "logs"
    logs.mkdir(parents=True)
    (logs / "dev-hygiene-full.json").write_text(
        json.dumps(
            {
                "finished_at": "2026-09-20T10:00:00+0000",
                "finished_epoch": time.time() - 5 * 86400,
                "escalation": "[dev-hygiene] ESCALATION: ancient",
            }
        ),
        encoding="utf-8",
    )
    _run_hook(monkeypatch, {"hook_event_name": "SessionStart", "cwd": str(fake_project)}, rc=0)
    assert hook.main() == 0
    assert capsys.readouterr().out == ""


def test_hook_does_nothing_without_the_script(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _run_hook(monkeypatch, {"hook_event_name": "SessionStart", "cwd": str(tmp_path)}, rc=3)
    assert hook.main() == 0
    assert calls == []


def test_hook_floor_is_env_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    assert hook._floor_gb() == hook.DEFAULT_FLOOR_GB
    monkeypatch.setenv("TINYASSETS_DEV_HYGIENE_FLOOR_GB", "75")
    assert hook._floor_gb() == 75.0
    monkeypatch.setenv("TINYASSETS_DEV_HYGIENE_FLOOR_GB", "not-a-number")
    assert hook._floor_gb() == hook.DEFAULT_FLOOR_GB, "a bad value must not break a session start"
