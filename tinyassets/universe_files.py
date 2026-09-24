"""One safe reader for every daemon-side read of a universe folder.

Since the universe agent can `write`, `edit` and `bash` in its own folder
(harness S1), every file in a universe is untrusted input to the daemon that
reads it from OUTSIDE the jail (persona assembly, the OKF bundle, the soul,
the skill index). Two ways that bites:

* **A planted link.** The agent (or io_uring, which seccomp cannot filter)
  makes ``founder.md -> /data/<other>/founder.md``. A plain ``read_text``
  follows it and pulls another user's file into this universe's prompt.
* **An oversized file.** A read into the shared daemon process is bounded by
  nothing; a huge file is a memory spike for every universe.

So the daemon never opens a universe file by path. It resolves every path
component with ``O_NOFOLLOW`` (no component may be a link), requires a regular
file, and reads at most ``max_bytes``. On a non-POSIX host (a single-tenant
tray) it falls back to rejecting a link at any component with ``lstat`` and the
same size bound. A refusal is an :class:`OSError`, so the callers that already
treat "unreadable" as "absent" fail closed unchanged.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from tinyassets import workspace_fs as fs

__all__ = ["UniverseFileError", "read_universe_file", "read_universe_text"]

#: Largest universe file the daemon will read into its own process. Generous
#: (a brain or grounding file is kilobytes) but bounded: the jail's file rlimit
#: allows far larger, and reading that whole into the shared daemon is the spike
#: this guards. Over-limit reads as unreadable, i.e. absent.
MAX_UNIVERSE_FILE_BYTES = 8 * 1024 * 1024


class UniverseFileError(OSError):
    """A universe file was refused: a link on the path, not a regular file, or
    over the size bound. An ``OSError`` so existing ``except OSError`` handlers
    fail closed to 'absent' without a new branch."""


def _read_nofollow_windows(root: Path, relpath: str, max_bytes: int) -> bytes:
    """Non-POSIX fallback: reject a link at any component, then bounded read."""
    current = root
    for part in Path(relpath).parts:
        if part in ("", ".", "..") or os.sep in part or (os.altsep and os.altsep in part):
            raise UniverseFileError(f"unsafe path component {part!r}")
        current = current / part
        try:
            info = current.lstat()
        except OSError as exc:
            raise UniverseFileError(str(exc)) from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0):
            raise UniverseFileError(f"{part!r} is a link; universe files are read link-free")
    try:
        info = current.lstat()
    except OSError as exc:
        raise UniverseFileError(str(exc)) from exc
    if not stat.S_ISREG(info.st_mode):
        raise UniverseFileError("not a regular file")
    if info.st_size > max_bytes:
        raise UniverseFileError(f"over the {max_bytes}-byte bound")
    with open(current, "rb") as handle:  # noqa: PTH123 - link-checked above
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UniverseFileError(f"over the {max_bytes}-byte bound")
    return data


def read_universe_file(
    universe_dir: Path | str,
    relpath: str,
    *,
    max_bytes: int = MAX_UNIVERSE_FILE_BYTES,
) -> bytes:
    """Bytes of ``universe_dir/relpath``, never following a link, bounded.

    Raises :class:`OSError` (a subclass, or the one ``workspace_fs`` raises)
    when the file is missing, is or sits behind a link, is not a regular file,
    or is over ``max_bytes``.
    """
    root = Path(universe_dir)
    if getattr(fs, "_POSIX", False):
        root_fd = fs.open_dir_nofollow(root.resolve(strict=False))
        try:
            return fs.read_regular_file_beneath(root_fd, relpath, max_bytes=max_bytes)
        finally:
            os.close(root_fd)
    return _read_nofollow_windows(root, relpath, max_bytes)


def read_universe_text(
    universe_dir: Path | str,
    relpath: str,
    *,
    max_bytes: int = MAX_UNIVERSE_FILE_BYTES,
    encoding: str = "utf-8",
) -> str:
    """:func:`read_universe_file` decoded as text, like ``Path.read_text``.

    Newlines are normalised to ``\\n`` (universal-newlines, as text-mode
    reads do), so a file written on a CRLF host parses identically and its
    content hash matches one taken through ``read_text`` elsewhere.
    """
    text = read_universe_file(universe_dir, relpath, max_bytes=max_bytes).decode(encoding)
    return text.replace("\r\n", "\n").replace("\r", "\n")
