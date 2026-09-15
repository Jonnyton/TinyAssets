"""Storage samples must stay anchored, bounded and honest about uncertainty."""

import os
import stat
from unittest.mock import patch

import pytest

from tinyassets import workspace_fs as fs

pytestmark = pytest.mark.skipif(os.name != "posix", reason="held directory scans need POSIX")


@pytest.fixture
def held(tmp_path):
    root = tmp_path / "lease"
    root.mkdir()
    fd = fs.open_dir_nofollow(root)
    try:
        yield fd, root
    finally:
        os.close(fd)


def measure(fd, **kwargs):
    return fs.measure_tree_beneath(fd, **{"max_bytes": 16 * 1024 * 1024, **kwargs})


def footprint(path):
    info = path.lstat()
    return max(info.st_size, info.st_blocks * 512)


def test_repeated_samples_include_all_files_without_consuming_root_offset(held):
    fd, root = held
    (root / "nested").mkdir()
    (root / "a").write_bytes(b'a' * 9000)
    (root / "nested" / "b").write_bytes(b'b' * 17000)
    expected = sum(footprint(path) for path in
                   (root, root / 'a', root / 'nested', root / 'nested' / 'b'))
    assert measure(fd) == expected
    assert measure(fd) == expected
    assert measure(fd) == expected
    assert stat.S_ISDIR(os.fstat(fd).st_mode)


def test_held_root_survives_rename_and_name_replacement(held):
    fd, root = held
    (root / 'owned').write_bytes(b'original' * 1000)
    expected = measure(fd)
    moved = root.with_name('moved')
    root.rename(moved)
    root.mkdir()
    (root / 'unrelated').write_bytes(b'x' * 200000)
    assert measure(fd) == expected


def test_links_never_measure_their_targets_and_special_files_never_block(held):
    fd, root = held
    outside = root.with_name('outside')
    outside.mkdir()
    (outside / 'large').write_bytes(b'x' * 200000)
    os.symlink(outside, root / 'directory-link')
    os.symlink(outside / 'large', root / 'file-link')
    os.symlink('missing', root / 'broken-link')
    os.mkfifo(root / 'pipe')
    expected = sum(footprint(path) for path in (root, *root.iterdir()))
    assert measure(fd) == expected
    assert expected < 200000


def test_sparse_and_hardlinked_files_are_conservatively_counted(held):
    fd, root = held
    with (root / 'sparse').open('wb') as handle:
        handle.truncate(1024 * 1024)
    os.link(root / 'sparse', root / 'alias')
    assert measure(fd) >= 2 * 1024 * 1024


def test_over_limit_short_circuits_and_never_claims_exact_size(held):
    fd, root = held
    (root / 'large').write_bytes(b'x' * 8192)
    assert measure(fd, max_bytes=1) == 2
    assert measure(fd, max_bytes=0) == 1


def test_expired_sample_is_unknown_not_zero(held):
    fd, _ = held
    with patch.object(fs.time, 'monotonic', side_effect=[0, 2]):
        with pytest.raises(fs.UnsafePoolPath, match='deadline'):
            measure(fd, timeout_s=1)


def test_mid_scan_deadline_closes_owned_handles(held):
    fd, root = held
    (root / 'child').mkdir()
    before = len(os.listdir('/proc/self/fd'))
    with patch.object(fs.time, 'monotonic', side_effect=[0, 0, 0, 0, 0, 2]):
        with pytest.raises(fs.UnsafePoolPath, match='deadline'):
            measure(fd, timeout_s=1)
    assert len(os.listdir('/proc/self/fd')) == before


def test_directory_replacement_is_refused_not_followed(held):
    fd, root = held
    (root / 'child').mkdir()
    outside = root.with_name('outside')
    outside.mkdir()
    opened = fs._open_child_dir
    def replace(parent, name):
        if name == 'child':
            (root / 'child').rename(root / 'old-child')
            os.symlink(outside, root / 'child')
        return opened(parent, name)
    before = len(os.listdir('/proc/self/fd'))
    with patch.object(fs, '_open_child_dir', side_effect=replace):
        with pytest.raises(fs.UnsafePoolPath):
            measure(fd)
    assert len(os.listdir('/proc/self/fd')) == before


def test_replaced_real_directory_inode_is_refused(held):
    fd, root = held
    (root / 'child').mkdir()
    opened = fs._open_child_dir
    def replace(parent, name):
        (root / 'child').rename(root / 'old-child')
        (root / 'child').mkdir()
        return opened(parent, name)
    with patch.object(fs, '_open_child_dir', side_effect=replace):
        with pytest.raises(fs.UnsafePoolPath, match='directory changed'):
            measure(fd)


def test_depth_guard_closes_every_open_descriptor(held):
    fd, root = held
    (root / 'child' / 'grandchild').mkdir(parents=True)
    before = len(os.listdir('/proc/self/fd'))
    with patch.object(fs, '_MAX_TREE_DEPTH', 1):
        with pytest.raises(fs.UnsafePoolPath, match='depth'):
            measure(fd)
    assert len(os.listdir('/proc/self/fd')) == before


@pytest.mark.parametrize('kwargs', [{'max_bytes': -1}, {'max_bytes': True},
                                   {'timeout_s': 0}, {'timeout_s': True},
                                   {'timeout_s': float('inf')}])
def test_invalid_measurement_settings(held, kwargs):
    with pytest.raises(ValueError):
        measure(held[0], **kwargs)


def test_bad_descriptor_refuses_without_private_path(held):
    fd, _ = held
    duplicate = os.dup(fd)
    os.close(duplicate)
    with pytest.raises(fs.UnsafePoolPath, match='storage measurement unavailable'):
        measure(duplicate)


def test_directory_error_does_not_expose_private_names(held):
    fd, root = held
    (root / 'private-project-name').mkdir()
    with patch.object(fs, '_open_child_dir',
                      side_effect=fs.UnsafePoolPath('private-project-name')):
        with pytest.raises(fs.UnsafePoolPath) as caught:
            measure(fd)
    assert str(caught.value) == 'storage measurement directory unavailable'
