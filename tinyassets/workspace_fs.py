"""The filesystem side of the workspace sink: the real
:class:`~tinyassets.workspace_pool.PoolFilesystem`, and the no-follow directory
handles both sink paths hold while they touch a workspace.

It lives outside ``workspace_pool`` on purpose. That module computes paths and
never touches the filesystem, which its tests assert by reading its source; the
bytes move here, where the no-follow rules are one small reviewable place.

Nothing here trusts a path a second time. A path is resolved once, component by
component, from an already-open ancestor descriptor, and every later access goes
through the descriptor that resolution produced - so a rename or a symlink
swapped in afterwards cannot redirect it. Deletion never follows a link: a
symlink, or on Windows a junction, inside a lease is unlinked rather than walked,
so a lease containing a link to the host's data directory cannot make the sweeper
delete that directory. This is why the walk is an explicit ``scandir`` stack
rather than ``os.walk``: ``os.walk`` decides what to descend into from
``is_dir(follow_symlinks=False)``, which is TRUE for a Windows junction, and a
junction needs no privilege to create.

The descriptor helpers are POSIX; on Windows they raise ``NotImplementedError``.
The sink runs on Linux, and there is no Windows equivalent of ``O_NOFOLLOW`` +
``dir_fd`` that would be safe rather than merely present.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

#: Present on POSIX only. The zero fallbacks are never reached: every function
#: that would use them refuses on a non-POSIX host first.
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)

_COPY_CHUNK = 1024 * 1024
_LEASE_DIR_MODE = 0o700
_COPY_DEST_MODE = 0o600


class UnsafePoolPath(OSError):
    """A path was refused before it was used: a link where a real directory or
    file was required, a traversal, or a file larger than the caller's bound.

    An ``OSError`` so that a caller which already treats filesystem failure as
    failure - the outbox processor marking a lease ``LOST`` - keeps working
    without a second except clause.
    """


def _is_link(path: str) -> bool:
    """A symlink or a Windows junction: something whose target is elsewhere."""
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is None:
        return False
    try:
        return bool(isjunction(path))
    except OSError:
        return False


def _unlink_link(path: str) -> None:
    """Remove the link itself. Windows needs ``rmdir`` for a directory link."""
    try:
        os.unlink(path)
    except OSError:
        os.rmdir(path)


class RealPoolFilesystem:
    """``exists``/``rename``/``remove_tree_no_follow`` against the real disk."""

    def exists(self, path: Path) -> bool:
        """Presence WITHOUT following links: a dangling symlink is present, and
        the processor still owes its removal."""
        return os.path.lexists(str(path))

    def rename(self, src: Path, dst: Path) -> None:
        """Move a workspace to its deterministic quarantine name.

        The quarantine parent is created here when missing - the pool module
        creates no directories, and a rename into a missing parent would leave
        the bytes in place with the entry marked done.
        """
        parent = os.path.dirname(str(dst))
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.replace(str(src), str(dst))

    def remove_tree_no_follow(self, path: Path) -> None:
        """Delete a tree bottom-up, never descending into a link or junction.

        A path that is already gone is not an error: the processor is
        at-least-once, so a repeat has to be a no-op. Anything else propagates as
        ``OSError`` and the lease becomes ``LOST`` with its bytes still charged.
        """
        target = str(path)
        if not os.path.lexists(target):
            return
        if _is_link(target):
            _unlink_link(target)
            return
        if not os.path.isdir(target):
            os.unlink(target)
            return
        # Post-order without recursion: push a directory, then its children;
        # a directory is removed only after everything under it is gone.
        pending: list[str] = [target]
        emptied: list[str] = []
        while pending:
            current = pending.pop()
            emptied.append(current)
            try:
                with os.scandir(current) as entries:
                    children = list(entries)
            except FileNotFoundError:
                continue
            for entry in children:
                child = entry.path
                try:
                    if entry.is_symlink() or _is_link(child):
                        _unlink_link(child)
                    elif entry.is_dir(follow_symlinks=False):
                        pending.append(child)
                    else:
                        os.unlink(child)
                except FileNotFoundError:
                    continue
        for directory in reversed(emptied):
            try:
                os.rmdir(directory)
            except FileNotFoundError:
                continue


# --------------------------------------------------------------------------
# no-follow directory handles (POSIX)
# --------------------------------------------------------------------------


def _require_posix(what: str) -> None:
    """Refuse loudly rather than pretend. A Windows fallback here would be a
    path-based imitation of a descriptor-based guarantee, which is the bug this
    module exists to prevent."""
    if os.name != "posix" or os.open not in os.supports_dir_fd:
        raise NotImplementedError(
            f"{what} needs POSIX openat semantics (O_NOFOLLOW + dir_fd); "
            f"this host is {os.name!r}. The workspace sink runs on Linux; "
            "on Windows there is no safe equivalent, so there is no fallback."
        )


def _require_component(name: str) -> str:
    """One path component, never a traversal and never a separator."""
    if not isinstance(name, str) or not name:
        raise UnsafePoolPath(f"path component must be a non-empty string, got {name!r}")
    if name in (".", ".."):
        raise UnsafePoolPath(f"path component {name!r} is a traversal")
    if "/" in name or "\\" in name or "\0" in name:
        raise UnsafePoolPath(f"path component {name!r} contains a separator")
    return name


def _split_relpath(relpath: str | Path) -> list[str]:
    """Split a relative path into safe components, refusing anything that could
    leave the directory the descriptor names."""
    raw = str(relpath)
    if not raw:
        raise UnsafePoolPath("relpath is empty")
    if raw.startswith("/") or raw.startswith("\\") or os.path.isabs(raw):
        raise UnsafePoolPath(f"relpath {raw!r} is absolute; it must be relative to the handle")
    parts = [part for part in raw.replace("\\", "/").split("/")]
    if any(part == "" for part in parts):
        raise UnsafePoolPath(f"relpath {raw!r} has an empty component")
    return [_require_component(part) for part in parts]


def _open_child_dir(parent_fd: int, name: str) -> int:
    """``openat`` one directory component, refusing a symlink at that step."""
    try:
        return os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=parent_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UnsafePoolPath(
                f"{name!r} is a link or not a directory; a workspace path is "
                "resolved without following links"
            ) from exc
        raise


def _open_leaf(parent_fd: int, name: str) -> int:
    """``openat`` the final component for reading, never following a link."""
    try:
        return os.open(
            name, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK, dir_fd=parent_fd
        )
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise UnsafePoolPath(
                f"{name!r} is a symlink; a workspace file is read through the "
                "descriptor of the file itself"
            ) from exc
        raise


def open_dir_nofollow(path: str | Path) -> int:
    """Open ``path`` as a directory with no component allowed to be a symlink.

    Resolution walks from the root, opening each component with ``dir_fd`` and
    ``O_NOFOLLOW``, never a single ``os.open`` on the whole path: one ``os.open``
    would only refuse a symlink at the LAST component, and a swapped parent is
    exactly the attack. The caller owns the returned descriptor and closes it.
    """
    _require_posix("open_dir_nofollow")
    raw = str(path)
    if not os.path.isabs(raw):
        raise UnsafePoolPath(f"{raw!r} must be absolute: resolution starts at the root")
    parts = [part for part in raw.replace("\\", "/").split("/") if part]
    current = os.open("/", os.O_RDONLY | _O_DIRECTORY)
    try:
        for part in parts:
            _require_component(part)
            child = _open_child_dir(current, part)
            os.close(current)
            current = child
    except BaseException:
        os.close(current)
        raise
    return current


def create_lease_dir(parent_fd: int, name: str, *, mode: int = _LEASE_DIR_MODE) -> int:
    """Create one directory under ``parent_fd`` and return a handle to IT.

    The handle is verified: the inode the open descriptor reports must be the
    inode the create produced. Without that check a race could replace the fresh
    directory with a symlink between ``mkdir`` and ``open`` and hand back a
    handle to somewhere else entirely.
    """
    _require_posix("create_lease_dir")
    _require_component(name)
    os.mkdir(name, mode, dir_fd=parent_fd)
    created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    fd = _open_child_dir(parent_fd, name)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (created.st_dev, created.st_ino):
            raise UnsafePoolPath(
                f"{name!r} was replaced between its creation and its open "
                f"(inode {created.st_ino} became {opened.st_ino})"
            )
    except BaseException:
        os.close(fd)
        raise
    return fd


def _open_regular_beneath(dir_fd: int, relpath: str | Path, *, max_bytes: int) -> tuple[int, int]:
    """Open a REGULAR file beneath ``dir_fd``; return ``(fd, size)``.

    Every directory component is opened with ``O_NOFOLLOW``, the leaf too, and
    the file type is checked with ``fstat`` on the OPEN descriptor - never a
    stat of the path, which describes whatever the name pointed at a moment ago.
    """
    _require_posix("read_regular_file_beneath")
    if int(max_bytes) < 0:
        raise ValueError(f"max_bytes must be >= 0, got {max_bytes}")
    parts = _split_relpath(relpath)
    current = dir_fd
    opened: list[int] = []
    try:
        for part in parts[:-1]:
            current = _open_child_dir(current, part)
            opened.append(current)
        fd = _open_leaf(current, parts[-1])
    finally:
        for handle in opened:
            os.close(handle)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise UnsafePoolPath(
                f"{str(relpath)!r} is not a regular file (mode {info.st_mode:#o}); "
                "a workspace read never opens a device, a FIFO or a directory"
            )
        if info.st_size > int(max_bytes):
            raise UnsafePoolPath(
                f"{str(relpath)!r} is {info.st_size} bytes, over the {max_bytes} bound"
            )
    except BaseException:
        os.close(fd)
        raise
    return fd, int(info.st_size)


def read_regular_file_beneath(dir_fd: int, relpath: str | Path, *, max_bytes: int) -> bytes:
    """Read a regular file beneath a held directory handle, bounded.

    The bound is enforced twice: the size reported by ``fstat`` on the open
    descriptor, and the read itself, which stops at ``max_bytes + 1`` and
    refuses. A file that GROWS between the stat and the read must not slip
    through on the strength of its earlier size.
    """
    fd, _size = _open_regular_beneath(dir_fd, relpath, max_bytes=max_bytes)
    try:
        chunks: list[bytes] = []
        remaining = int(max_bytes) + 1
        while remaining > 0:
            chunk = os.read(fd, min(_COPY_CHUNK, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(fd)
    if len(data) > int(max_bytes):
        raise UnsafePoolPath(
            f"{str(relpath)!r} grew past the {max_bytes} bound while it was being read"
        )
    return data


def copy_regular_file_beneath(
    dir_fd: int, relpath: str | Path, dest_path: str | Path, *, max_bytes: int
) -> int:
    """Stream a regular file from beneath a held handle to ``dest_path``.

    The destination is created ``O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW`` at
    mode 0o600, so an existing file or a symlink planted at the destination is a
    refusal rather than an overwrite of whatever it points at. A partial
    destination is removed on ANY failure, the bound included: half a manifest
    left behind would be read later as a whole one.
    """
    fd, _size = _open_regular_beneath(dir_fd, relpath, max_bytes=max_bytes)
    dest = str(dest_path)
    copied = 0
    try:
        # Outside the cleanup below on purpose: a destination this call did not
        # create is not this call's to delete. A symlink already sitting there
        # is refused by O_EXCL and left exactly as it was found.
        dest_fd = os.open(dest, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _O_NOFOLLOW, _COPY_DEST_MODE)
    except BaseException:
        os.close(fd)
        raise
    try:
        try:
            while True:
                chunk = os.read(fd, _COPY_CHUNK)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > int(max_bytes):
                    raise UnsafePoolPath(
                        f"{str(relpath)!r} grew past the {max_bytes} bound while it "
                        "was being copied"
                    )
                offset = 0
                while offset < len(chunk):
                    offset += os.write(dest_fd, chunk[offset:])
        finally:
            os.close(dest_fd)
    except BaseException:
        try:
            os.unlink(dest)
        except OSError:
            pass
        raise
    finally:
        os.close(fd)
    return copied


def bind_target_for(dir_fd: int) -> str:
    """The ``/proc/self/fd/<n>`` name of a held directory handle.

    A sandbox is given THIS as its ``--bind`` source, not the path the handle
    was opened from. The path is a name that can be re-pointed: between the
    check and the bind, a rename can put a different directory - or a symlink to
    one - under the same name, and the sandbox would mount that instead. The
    descriptor cannot be re-pointed; it names the inode that was verified.
    """
    _require_posix("bind_target_for")
    if not isinstance(dir_fd, int) or isinstance(dir_fd, bool) or dir_fd < 0:
        raise ValueError(f"dir_fd must be a non-negative descriptor, got {dir_fd!r}")
    return f"/proc/self/fd/{dir_fd}"
