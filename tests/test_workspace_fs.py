"""The no-follow directory handles the workspace sink holds.

Every guard here is a link-swap defence, so the tests are about paths that are
NOT what they look like: a symlinked component, a symlinked leaf, a FIFO, a
traversal, a file whose stat under-reports its size. POSIX only - the sink runs
on Linux, and on Windows the helpers refuse rather than imitate.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from tinyassets import workspace_fs as wfs

#: A lease name the hardened create_lease_dir accepts: 16 hex characters,
#: which is what secrets.token_hex(8) produces.
GOOD_NAME = "0123456789abcdef"

posix_only = pytest.mark.skipif(
    os.name != "posix",
    reason="POSIX openat semantics (O_NOFOLLOW + dir_fd); the workspace sink runs on Linux",
)
windows_only = pytest.mark.skipif(os.name == "posix", reason="the off-POSIX refusal")


def a_proc_dir_fd() -> int | None:
    """A handle on ``/proc/<pid>``, whose files report ``st_size == 0`` and then
    read out real bytes - the only honest way to test that the read bound does
    not trust the stat. None when there is no procfs."""
    candidate = f"/proc/{os.getpid()}"
    if not os.path.isdir(candidate):
        return None
    try:
        return wfs.open_dir_nofollow(candidate)
    except OSError:
        return None


# --------------------------------------------------------------------------
# open_dir_nofollow
# --------------------------------------------------------------------------


@posix_only
def test_open_dir_nofollow_hands_back_the_directory_it_named(tmp_path: Path) -> None:
    target = tmp_path / "pool" / "lease"
    target.mkdir(parents=True)
    fd = wfs.open_dir_nofollow(target)
    try:
        opened = os.fstat(fd)
        on_disk = os.stat(target)
        assert (opened.st_dev, opened.st_ino) == (on_disk.st_dev, on_disk.st_ino)
    finally:
        os.close(fd)


@posix_only
def test_open_dir_nofollow_refuses_a_symlinked_component(tmp_path: Path) -> None:
    real = tmp_path / "real"
    (real / "inside").mkdir(parents=True)
    link = tmp_path / "link"
    os.symlink(real, link, target_is_directory=True)
    # The LAST component is a real directory; the middle one is the swap.
    with pytest.raises(wfs.UnsafePoolPath):
        wfs.open_dir_nofollow(link / "inside")


@posix_only
def test_open_dir_nofollow_refuses_a_symlinked_final_component(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    os.symlink(real, link, target_is_directory=True)
    with pytest.raises(wfs.UnsafePoolPath):
        wfs.open_dir_nofollow(link)


@posix_only
def test_open_dir_nofollow_refuses_a_relative_path(tmp_path: Path) -> None:
    with pytest.raises(wfs.UnsafePoolPath, match="absolute"):
        wfs.open_dir_nofollow("pool/lease")


@posix_only
def test_open_dir_nofollow_refuses_a_traversal_component(tmp_path: Path) -> None:
    with pytest.raises(wfs.UnsafePoolPath, match="traversal"):
        wfs.open_dir_nofollow(str(tmp_path) + "/../etc")


# --------------------------------------------------------------------------
# create_lease_dir
# --------------------------------------------------------------------------


@posix_only
def test_create_lease_dir_returns_a_handle_on_the_inode_it_created(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    parent = wfs.open_dir_nofollow(tmp_path)
    try:
        fd = wfs.create_lease_dir(parent, GOOD_NAME)
        try:
            opened = os.fstat(fd)
            on_disk = os.stat(tmp_path / GOOD_NAME)
            assert (opened.st_dev, opened.st_ino) == (on_disk.st_dev, on_disk.st_ino)
            assert stat.S_ISDIR(opened.st_mode)
            # Nothing for group or other: a lease is the daemon's alone.
            assert stat.S_IMODE(opened.st_mode) & 0o077 == 0
        finally:
            os.close(fd)
    finally:
        os.close(parent)


@posix_only
def test_create_lease_dir_refuses_a_name_that_is_not_one_component(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    parent = wfs.open_dir_nofollow(tmp_path)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="separator"):
            wfs.create_lease_dir(parent, "nested/lease")
        with pytest.raises(wfs.UnsafePoolPath, match="traversal"):
            wfs.create_lease_dir(parent, "..")
        with pytest.raises(wfs.UnsafePoolPath):
            wfs.create_lease_dir(parent, "")
    finally:
        os.close(parent)


@posix_only
def test_create_lease_dir_refuses_a_directory_swapped_in_after_the_create(
    tmp_path: Path,
) -> None:
    """The race the inode compare exists for: between the mkdir and the open,
    a DIFFERENT real directory is renamed over the name. O_NOFOLLOW does not
    see it - it is not a link - so only the inode compare catches it."""
    os.chmod(tmp_path, 0o700)
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    parent = wfs.open_dir_nofollow(tmp_path)
    original = wfs._open_child_dir

    def swap_then_open(parent_fd: int, name: str) -> int:
        os.rename(decoy, tmp_path / name)
        return original(parent_fd, name)

    # Patched only AFTER the parent handle is open: this seam is also how
    # open_dir_nofollow walks, so patching first would swap during resolution.
    wfs._open_child_dir = swap_then_open
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="was replaced"):
            wfs.create_lease_dir(parent, GOOD_NAME)
    finally:
        wfs._open_child_dir = original
        os.close(parent)


@posix_only
def test_create_lease_dir_refuses_an_existing_name(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o700)
    (tmp_path / GOOD_NAME).mkdir()
    parent = wfs.open_dir_nofollow(tmp_path)
    try:
        with pytest.raises(FileExistsError):
            wfs.create_lease_dir(parent, GOOD_NAME)
    finally:
        os.close(parent)


# --------------------------------------------------------------------------
# read_regular_file_beneath
# --------------------------------------------------------------------------


@posix_only
def test_read_returns_the_bytes_of_a_regular_file(tmp_path: Path) -> None:
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "manifest.json").write_bytes(b'{"ok": true}')
    fd = wfs.open_dir_nofollow(tmp_path)
    try:
        assert (
            wfs.read_regular_file_beneath(fd, "repo/manifest.json", max_bytes=1024)
            == b'{"ok": true}'
        )
    finally:
        os.close(fd)


@posix_only
def test_read_refuses_a_symlinked_directory_component(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"the host's key")
    lease = tmp_path / "lease"
    lease.mkdir()
    os.symlink(outside, lease / "escape", target_is_directory=True)
    fd = wfs.open_dir_nofollow(lease)
    try:
        with pytest.raises(wfs.UnsafePoolPath):
            wfs.read_regular_file_beneath(fd, "escape/secret.txt", max_bytes=1024)
    finally:
        os.close(fd)


@posix_only
def test_read_refuses_a_symlinked_leaf(tmp_path: Path) -> None:
    """The file was replaced by a link to somewhere else: the open refuses, and
    the type check happens on the OPEN descriptor, never on a stat of the name."""
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"the host's key")
    lease = tmp_path / "lease"
    lease.mkdir()
    os.symlink(outside, lease / "manifest.json")
    fd = wfs.open_dir_nofollow(lease)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="symlink"):
            wfs.read_regular_file_beneath(fd, "manifest.json", max_bytes=1024)
    finally:
        os.close(fd)


@posix_only
def test_read_refuses_a_fifo_leaf(tmp_path: Path) -> None:
    """A FIFO would block the daemon forever on a normal open; O_NONBLOCK opens
    it and the S_ISREG check on the descriptor refuses it."""
    lease = tmp_path / "lease"
    lease.mkdir()
    os.mkfifo(lease / "manifest.json")
    fd = wfs.open_dir_nofollow(lease)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="not a regular file"):
            wfs.read_regular_file_beneath(fd, "manifest.json", max_bytes=1024)
    finally:
        os.close(fd)


@posix_only
def test_read_refuses_a_directory_leaf(tmp_path: Path) -> None:
    lease = tmp_path / "lease"
    (lease / "subdir").mkdir(parents=True)
    fd = wfs.open_dir_nofollow(lease)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="not a regular file"):
            wfs.read_regular_file_beneath(fd, "subdir", max_bytes=1024)
    finally:
        os.close(fd)


@posix_only
def test_read_refuses_traversals_absolutes_and_empty_components(tmp_path: Path) -> None:
    (tmp_path / "lease").mkdir()
    (tmp_path / "outside.txt").write_bytes(b"x")
    fd = wfs.open_dir_nofollow(tmp_path / "lease")
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="traversal"):
            wfs.read_regular_file_beneath(fd, "../outside.txt", max_bytes=1024)
        with pytest.raises(wfs.UnsafePoolPath, match="absolute"):
            wfs.read_regular_file_beneath(fd, "/etc/passwd", max_bytes=1024)
        with pytest.raises(wfs.UnsafePoolPath, match="empty component"):
            wfs.read_regular_file_beneath(fd, "repo//manifest.json", max_bytes=1024)
        with pytest.raises(wfs.UnsafePoolPath):
            wfs.read_regular_file_beneath(fd, "", max_bytes=1024)
    finally:
        os.close(fd)


@posix_only
def test_read_refuses_an_oversize_file(tmp_path: Path) -> None:
    (tmp_path / "big.bin").write_bytes(b"0" * 4096)
    fd = wfs.open_dir_nofollow(tmp_path)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="over the 1024 bound"):
            wfs.read_regular_file_beneath(fd, "big.bin", max_bytes=1024)
        assert len(wfs.read_regular_file_beneath(fd, "big.bin", max_bytes=4096)) == 4096
    finally:
        os.close(fd)


@posix_only
def test_read_does_not_trust_the_size_the_stat_reported(tmp_path: Path) -> None:
    """A procfs file stats as zero bytes and then reads out hundreds: exactly
    the shape of a file that grows between the stat and the read."""
    fd = a_proc_dir_fd()
    if fd is None:
        pytest.skip("no procfs on this host")
    try:
        assert os.stat(f"/proc/{os.getpid()}/status").st_size == 0
        with pytest.raises(wfs.UnsafePoolPath, match="grew past"):
            wfs.read_regular_file_beneath(fd, "status", max_bytes=8)
    finally:
        os.close(fd)


# --------------------------------------------------------------------------
# copy_regular_file_beneath
# --------------------------------------------------------------------------


@posix_only
def test_copy_is_byte_exact_and_private(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 8
    (tmp_path / "lease").mkdir()
    (tmp_path / "lease" / "bundle.pack").write_bytes(payload)
    dest = tmp_path / "staged.pack"
    fd = wfs.open_dir_nofollow(tmp_path / "lease")
    try:
        copied = wfs.copy_regular_file_beneath(fd, "bundle.pack", dest, max_bytes=1 << 20)
    finally:
        os.close(fd)
    assert copied == len(payload)
    assert dest.read_bytes() == payload
    assert stat.S_IMODE(os.stat(dest).st_mode) & 0o077 == 0


@posix_only
def test_copy_refuses_an_oversize_source_without_creating_the_destination(
    tmp_path: Path,
) -> None:
    (tmp_path / "bundle.pack").write_bytes(b"0" * 4096)
    dest = tmp_path / "staged.pack"
    fd = wfs.open_dir_nofollow(tmp_path)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="over the 1024 bound"):
            wfs.copy_regular_file_beneath(fd, "bundle.pack", dest, max_bytes=1024)
    finally:
        os.close(fd)
    assert not dest.exists()


@posix_only
def test_copy_removes_the_partial_destination_when_the_bound_is_hit(tmp_path: Path) -> None:
    """The source under-reports its size, so the bound is only hit MID-copy:
    the destination has already been created and must not be left behind."""
    fd = a_proc_dir_fd()
    if fd is None:
        pytest.skip("no procfs on this host")
    dest = tmp_path / "staged.txt"
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="grew past"):
            wfs.copy_regular_file_beneath(fd, "status", dest, max_bytes=8)
    finally:
        os.close(fd)
    assert not dest.exists()


@posix_only
def test_copy_refuses_an_existing_destination(tmp_path: Path) -> None:
    (tmp_path / "bundle.pack").write_bytes(b"payload")
    dest = tmp_path / "staged.pack"
    dest.write_bytes(b"do not overwrite me")
    fd = wfs.open_dir_nofollow(tmp_path)
    try:
        with pytest.raises(FileExistsError):
            wfs.copy_regular_file_beneath(fd, "bundle.pack", dest, max_bytes=1 << 20)
    finally:
        os.close(fd)
    assert dest.read_bytes() == b"do not overwrite me"


@posix_only
def test_copy_refuses_a_symlink_planted_at_the_destination(tmp_path: Path) -> None:
    (tmp_path / "bundle.pack").write_bytes(b"payload")
    victim = tmp_path / "victim.txt"
    victim.write_bytes(b"the host's file")
    dest = tmp_path / "staged.pack"
    os.symlink(victim, dest)
    fd = wfs.open_dir_nofollow(tmp_path)
    try:
        with pytest.raises(OSError):
            wfs.copy_regular_file_beneath(fd, "bundle.pack", dest, max_bytes=1 << 20)
    finally:
        os.close(fd)
    assert victim.read_bytes() == b"the host's file"
    # And the link itself survives: a destination this call did not create is
    # not this call's to clean up.
    assert os.path.islink(dest)


@posix_only
def test_copy_refuses_a_symlinked_source_leaf(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"the host's key")
    lease = tmp_path / "lease"
    lease.mkdir()
    os.symlink(outside, lease / "bundle.pack")
    dest = tmp_path / "staged.pack"
    fd = wfs.open_dir_nofollow(lease)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="symlink"):
            wfs.copy_regular_file_beneath(fd, "bundle.pack", dest, max_bytes=1 << 20)
    finally:
        os.close(fd)
    assert not dest.exists()


# --------------------------------------------------------------------------
# bind_target_for
# --------------------------------------------------------------------------


@posix_only
def test_bind_target_names_the_descriptor_and_resolves_to_its_inode(tmp_path: Path) -> None:
    lease = tmp_path / "lease"
    lease.mkdir()
    fd = wfs.open_dir_nofollow(lease)
    try:
        target = wfs.bind_target_for(fd)
        assert target == f"/proc/self/fd/{fd}"
        if not os.path.isdir("/proc/self/fd"):
            pytest.skip("no procfs on this host")
        through_fd = os.stat(target)
        on_disk = os.stat(lease)
        assert (through_fd.st_dev, through_fd.st_ino) == (on_disk.st_dev, on_disk.st_ino)
        # The rename the bind must survive: the NAME now points elsewhere, the
        # descriptor still names the directory that was checked.
        moved = tmp_path / "moved"
        os.rename(lease, moved)
        decoy = tmp_path / "lease"
        decoy.mkdir()
        still = os.stat(target)
        assert (still.st_dev, still.st_ino) == (on_disk.st_dev, on_disk.st_ino)
        assert os.stat(decoy).st_ino != still.st_ino
    finally:
        os.close(fd)


@posix_only
def test_bind_target_refuses_a_non_descriptor() -> None:
    with pytest.raises(ValueError):
        wfs.bind_target_for(-1)


# --------------------------------------------------------------------------
# off-POSIX, and the module's own discipline
# --------------------------------------------------------------------------


@windows_only
def test_the_descriptor_helpers_refuse_loudly_off_posix(tmp_path: Path) -> None:
    """No imitation: a path-based stand-in would look like the guarantee and
    not be it."""
    for call in (
        lambda: wfs.open_dir_nofollow(tmp_path),
        lambda: wfs.create_lease_dir(0, "lease1"),
        lambda: wfs.read_regular_file_beneath(0, "manifest.json", max_bytes=16),
        lambda: wfs.copy_regular_file_beneath(0, "a", tmp_path / "b", max_bytes=16),
        lambda: wfs.bind_target_for(0),
    ):
        with pytest.raises(NotImplementedError, match="POSIX"):
            call()


def test_the_module_reads_no_env_vars() -> None:
    source = Path(wfs.__file__).read_text(encoding="utf-8")
    for forbidden in ("environ", "getenv"):
        assert forbidden not in source, forbidden


# --------------------------------------------------------------------------
# the POSIX branch acts only through descriptors (Codex P1 #5)
# --------------------------------------------------------------------------


def _boom(name):
    def _raise(*args, **kwargs):
        raise AssertionError(f"os.{name} is a path-based call: TOCTOU by construction")

    return _raise


def _needs_dir_fd(original, name):
    def _checked(*args, **kwargs):
        if "dir_fd" not in kwargs and not any(
            key in kwargs for key in ("src_dir_fd", "dst_dir_fd")
        ):
            raise AssertionError(f"os.{name} was called by PATH, not through a handle")
        return original(*args, **kwargs)

    return _checked


def _forbid_path_based_calls(monkeypatch) -> None:
    """Make every path-based filesystem call an error.

    The POSIX branch resolves once and then acts through descriptors; a
    path-based call AFTER a check is the race this module exists to close, so
    the honest test is that those calls simply do not happen.
    """
    for name in ("makedirs", "replace", "scandir", "walk", "removedirs", "rmtree"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, _boom(name))
    for name in ("mkdir", "rmdir", "unlink", "rename", "lstat"):
        monkeypatch.setattr(os, name, _needs_dir_fd(getattr(os, name), name))
    original_listdir = os.listdir

    def _listdir(target=None):
        if not isinstance(target, int):
            raise AssertionError("os.listdir was called by PATH, not on a handle")
        return original_listdir(target)

    monkeypatch.setattr(os, "listdir", _listdir)


@posix_only
def test_the_posix_branch_never_touches_a_path_after_it_resolves_one(
    tmp_path: Path, monkeypatch
) -> None:
    pool = tmp_path / "scratch"
    lease = pool / "lease1"
    (lease / "repo" / ".git").mkdir(parents=True)
    (lease / "repo" / ".git" / "HEAD").write_text("ref: main", encoding="utf-8")
    (lease / "repo" / "file.txt").write_text("work", encoding="utf-8")
    quarantine = pool / ".quarantine" / "lease1.1"
    fs = wfs.RealPoolFilesystem()

    _forbid_path_based_calls(monkeypatch)

    assert fs.exists(lease) is True
    assert fs.exists(quarantine) is False
    fs.rename(lease, quarantine)          # creates .quarantine through a handle
    assert fs.exists(lease) is False
    assert fs.exists(quarantine) is True
    fs.remove_tree_no_follow(quarantine)
    assert fs.exists(quarantine) is False

    monkeypatch.undo()
    assert not lease.exists()
    assert not quarantine.exists()
    assert (pool / ".quarantine").is_dir()


@posix_only
def test_the_posix_branch_unlinks_a_link_and_leaves_its_target(tmp_path: Path) -> None:
    lease = tmp_path / "scratch" / "lease1"
    (lease / "repo").mkdir(parents=True)
    (lease / "repo" / "keep.txt").write_text("x", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("the host's data", encoding="utf-8")
    os.symlink(outside, lease / "repo" / "escape", target_is_directory=True)

    wfs.RealPoolFilesystem().remove_tree_no_follow(lease)

    assert not lease.exists()
    assert (outside / "precious.txt").read_text(encoding="utf-8") == "the host's data"


@posix_only
def test_removing_something_that_is_already_gone_is_a_no_op(tmp_path: Path) -> None:
    fs = wfs.RealPoolFilesystem()
    fs.remove_tree_no_follow(tmp_path / "never" / "existed")
    fs.remove_tree_no_follow(tmp_path / "gone")


@posix_only
def test_a_tree_deeper_than_the_cap_is_refused_rather_than_recursed(
    tmp_path: Path
) -> None:
    """Unbounded recursion through descriptors is a stack overflow waiting for
    a fixture; the cap makes it a refusal the lease can be LOST on."""
    deep = tmp_path / "scratch" / "lease1"
    current = deep
    for index in range(wfs._MAX_TREE_DEPTH + 3):
        current = current / f"d{index}"
    current.mkdir(parents=True)
    with pytest.raises(wfs.UnsafePoolPath, match="deeper than"):
        wfs.RealPoolFilesystem().remove_tree_no_follow(deep)


def test_the_windows_branch_is_selectable_and_still_deletes(tmp_path: Path) -> None:
    """The platform branch is injectable so both halves are testable on either
    host - a branch nobody can run is a branch nobody has checked."""
    lease = tmp_path / "lease1"
    (lease / "sub").mkdir(parents=True)
    (lease / "sub" / "file.txt").write_text("x", encoding="utf-8")
    wfs.RealPoolFilesystem(posix=False).remove_tree_no_follow(lease)
    assert not lease.exists()


# --------------------------------------------------------------------------
# create_lease_dir states its guarantee and enforces it (Codex P1 #6)
# --------------------------------------------------------------------------


@posix_only
def test_create_lease_dir_refuses_a_parent_anyone_could_write_to(tmp_path: Path) -> None:
    """The whole swap attack needs a parent someone else can rename into."""
    parent = tmp_path / "pool"
    parent.mkdir(mode=0o777)
    os.chmod(parent, 0o777)
    fd = wfs.open_dir_nofollow(parent)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="world-writable"):
            wfs.create_lease_dir(fd, GOOD_NAME)
    finally:
        os.close(fd)
    assert not (parent / GOOD_NAME).exists(), "it must refuse BEFORE creating anything"


@posix_only
def test_create_lease_dir_refuses_a_group_writable_parent(tmp_path: Path) -> None:
    parent = tmp_path / "pool"
    parent.mkdir()
    os.chmod(parent, 0o770)
    fd = wfs.open_dir_nofollow(parent)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="writable"):
            wfs.create_lease_dir(fd, GOOD_NAME)
    finally:
        os.close(fd)


@posix_only
def test_create_lease_dir_refuses_a_guessable_name(tmp_path: Path) -> None:
    """A name an attacker can predict is a name they can create first."""
    parent = tmp_path / "pool"
    parent.mkdir(mode=0o700)
    fd = wfs.open_dir_nofollow(parent)
    try:
        for name in ("lease1", "0123456789abcde", "0123456789abcdeg", "a" * 15):
            with pytest.raises(wfs.UnsafePoolPath, match="random hex"):
                wfs.create_lease_dir(fd, name)
        assert wfs.create_lease_dir(fd, GOOD_NAME) >= 0
    finally:
        os.close(fd)


@posix_only
def test_a_directory_swapped_in_before_the_first_stat_is_still_refused(
    tmp_path: Path, monkeypatch
) -> None:
    """The inode compare alone would MISS this: a rename that lands before the
    first stat is invisible to it, because both the stat and the open then see
    the intruder. What catches it is the handle having to be a fresh, empty,
    own-uid directory with exactly the mode we asked for."""
    parent = tmp_path / "pool"
    parent.mkdir(mode=0o700)
    decoy = tmp_path / "decoy"
    decoy.mkdir(mode=0o700)
    (decoy / "planted.txt").write_text("not ours", encoding="utf-8")

    original_mkdir = os.mkdir

    def _mkdir_then_swap(name, mode=0o777, *, dir_fd=None):
        original_mkdir(name, mode, dir_fd=dir_fd)
        # The swap lands BEFORE create_lease_dir's first stat.
        os.rename(str(decoy), str(parent / name))

    monkeypatch.setattr(os, "mkdir", _mkdir_then_swap)
    fd = wfs.open_dir_nofollow(parent)
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="not the empty directory"):
            wfs.create_lease_dir(fd, GOOD_NAME)
    finally:
        os.close(fd)


@posix_only
def test_the_created_lease_dir_is_private_and_empty(tmp_path: Path) -> None:
    parent = tmp_path / "pool"
    parent.mkdir(mode=0o700)
    parent_fd = wfs.open_dir_nofollow(parent)
    try:
        fd = wfs.create_lease_dir(parent_fd, GOOD_NAME)
        try:
            info = os.fstat(fd)
            assert stat.S_ISDIR(info.st_mode)
            assert stat.S_IMODE(info.st_mode) == 0o700
            assert info.st_uid == os.getuid()
            assert os.listdir(fd) == []
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


@posix_only
def test_the_copy_cleanup_never_deletes_a_file_it_did_not_create(
    tmp_path: Path
) -> None:
    """Cleanup by NAME would delete whatever now answers to it. Only the inode
    it created is this call's to remove."""
    created = tmp_path / "staged.pack"
    created.write_text("mine", encoding="utf-8")
    info = os.lstat(created)
    replacement = tmp_path / "theirs.txt"
    replacement.write_text("somebody else's file", encoding="utf-8")
    os.replace(str(replacement), str(created))

    wfs._unlink_if_same_inode(str(created), info)

    assert created.read_text(encoding="utf-8") == "somebody else's file"

    # And when it IS the same inode, it goes.
    mine = tmp_path / "mine.pack"
    mine.write_text("mine", encoding="utf-8")
    wfs._unlink_if_same_inode(str(mine), os.lstat(mine))
    assert not mine.exists()
