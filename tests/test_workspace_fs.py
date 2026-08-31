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
    parent = wfs.open_dir_nofollow(tmp_path)
    try:
        fd = wfs.create_lease_dir(parent, "lease1")
        try:
            opened = os.fstat(fd)
            on_disk = os.stat(tmp_path / "lease1")
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
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    parent = wfs.open_dir_nofollow(tmp_path)
    original = wfs._open_child_dir

    def swap_then_open(parent_fd: int, name: str) -> int:
        os.rename(decoy, tmp_path / name)
        return original(parent_fd, name)

    wfs._open_child_dir = swap_then_open
    try:
        with pytest.raises(wfs.UnsafePoolPath, match="was replaced"):
            wfs.create_lease_dir(parent, "lease1")
    finally:
        wfs._open_child_dir = original
        os.close(parent)


@posix_only
def test_create_lease_dir_refuses_an_existing_name(tmp_path: Path) -> None:
    (tmp_path / "lease1").mkdir()
    parent = wfs.open_dir_nofollow(tmp_path)
    try:
        with pytest.raises(FileExistsError):
            wfs.create_lease_dir(parent, "lease1")
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
