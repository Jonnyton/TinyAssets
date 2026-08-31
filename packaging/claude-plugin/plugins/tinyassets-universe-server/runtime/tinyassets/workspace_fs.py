"""The real :class:`~tinyassets.workspace_pool.PoolFilesystem` for the workspace
pool: the three filesystem verbs the outbox processor is allowed to perform.

It lives outside ``workspace_pool`` on purpose. That module computes paths and
never touches the filesystem, which its tests assert by reading its source; the
bytes move here, where the no-follow rules are one small reviewable place.

Deletion NEVER follows a link. A symlink - or, on Windows, a junction - inside a
lease is unlinked, not walked, so a lease containing a link to the host's data
directory cannot make the sweeper delete that directory. This is why the walk is
an explicit ``scandir`` stack rather than ``os.walk``: ``os.walk`` decides what
to descend into from ``is_dir(follow_symlinks=False)``, which is TRUE for a
Windows junction, and a junction needs no privilege to create.
"""

from __future__ import annotations

import os
from pathlib import Path


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
