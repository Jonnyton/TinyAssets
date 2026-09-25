"""One safe reader for every daemon-side read of a universe folder.

Since the universe agent can `write`, `edit` and `bash` in its own folder
(harness S1), every file in a universe is untrusted input to the daemon that
reads it from OUTSIDE the jail (persona assembly, the OKF bundle, the soul,
soul edits, config, the skill index). Three ways that bites:

* **A planted link.** ``founder.md -> /data/<other>/founder.md``. A plain
  ``read_text`` follows it and pulls another user's file into this universe.
* **An oversized file.** A read into the shared daemon process is otherwise
  bounded by nothing: a 4 MB ``config.yaml`` cost a turn 30 s and 1.4 GB.
* **A hostile parse.** ``yaml.safe_load`` expands anchors/aliases: a few
  hundred bytes become gigabytes.

So the daemon never opens a universe file by path. It resolves every path
component with ``O_NOFOLLOW`` (no component may be a link), requires a regular
file, reads at most ``max_bytes``, and parses YAML only after refusing
anchors and aliases. On a non-POSIX host (a single-tenant tray) it falls back
to rejecting a link at any component with ``lstat``. A refusal is an
:class:`OSError` (``FileNotFoundError`` when simply absent), so callers that
already treat "unreadable" as "absent" fail closed unchanged.

``tests/test_universe_file_reads_are_bounded.py`` fails the build on any raw
read in the daemon turn-path modules, so this stays the only way in.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from tinyassets import workspace_fs as fs

__all__ = [
    "MAX_BRAIN_FILE_BYTES",
    "MAX_CONFIG_BYTES",
    "MAX_FRONTMATTER_BYTES",
    "MAX_UNIVERSE_FILE_BYTES",
    "UniverseFileError",
    "list_universe_dir",
    "load_untrusted_yaml",
    "read_universe_file",
    "read_universe_text",
]

#: Default bound: generous (a brain file is kilobytes) but fixed.
MAX_UNIVERSE_FILE_BYTES = 8 * 1024 * 1024
#: A brain / soul / log markdown file.
MAX_BRAIN_FILE_BYTES = 1024 * 1024
#: ``config.yaml`` and any YAML frontmatter, before the parser sees it.
MAX_CONFIG_BYTES = 64 * 1024
MAX_FRONTMATTER_BYTES = 64 * 1024


class UniverseFileError(OSError):
    """A universe file was refused: a link on the path, not a regular file,
    over the size bound, or YAML with anchors/aliases. An ``OSError`` so
    existing ``except OSError`` handlers fail closed without a new branch."""


def _check_component(part: str) -> None:
    if part in ("", ".", "..") or "/" in part or "\\" in part or "\x00" in part:
        raise UniverseFileError(f"unsafe path component {part!r}")


def _lstat_nofollow_windows(root: Path, relpath: str) -> Path:
    """Non-POSIX: walk ``relpath`` rejecting a link at any component."""
    current = root
    for part in Path(relpath).parts:
        _check_component(part)
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise UniverseFileError(str(exc)) from exc
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0):
            raise UniverseFileError(f"{part!r} is a link; universe files are read link-free")
    return current


def _read_nofollow_windows(root: Path, relpath: str, max_bytes: int) -> bytes:
    current = _lstat_nofollow_windows(root, relpath)
    info = current.lstat()
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

    Raises ``FileNotFoundError`` when absent and another :class:`OSError` when
    the file is or sits behind a link, is not a regular file, or is over
    ``max_bytes``.
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

    Newlines are normalised to ``\\n`` (universal newlines, as text-mode reads
    do), so a file written on a CRLF host parses identically and its content
    hash matches one taken through ``read_text`` elsewhere.
    """
    text = read_universe_file(universe_dir, relpath, max_bytes=max_bytes).decode(encoding)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def list_universe_dir(universe_dir: Path | str, relpath: str) -> list[str]:
    """Entry names of the directory ``universe_dir/relpath``, link-free.

    ``FileNotFoundError`` when absent; another :class:`OSError` when a
    component is a link or not a directory. Names only: read each entry with
    :func:`read_universe_file`, which re-checks it.
    """
    root = Path(universe_dir)
    if getattr(fs, "_POSIX", False):
        root_fd = fs.open_dir_nofollow(root.resolve(strict=False))
        try:
            current = root_fd
            opened: list[int] = []
            try:
                for part in Path(relpath).parts:
                    _check_component(part)
                    current = fs.open_subdir_nofollow(current, part)
                    opened.append(current)
                return sorted(os.listdir(current))
            finally:
                for handle in opened:
                    os.close(handle)
        finally:
            os.close(root_fd)
    directory = _lstat_nofollow_windows(root, relpath)
    if not directory.is_dir():
        raise UniverseFileError("not a directory")
    return sorted(entry.name for entry in os.scandir(directory))


def load_untrusted_yaml(text: str, *, max_bytes: int = MAX_CONFIG_BYTES) -> object:
    """Parse YAML from a universe file, refusing what makes a parse hostile.

    The size bound is checked BEFORE the parser runs. Anchors and aliases --
    the whole alias-bomb class -- are refused by scanning parser events, which
    never expands anything. Deep nesting and malformed YAML become a
    :class:`UniverseFileError`, never a crash in the caller.
    """
    import yaml

    if len(text.encode("utf-8", "replace")) > max_bytes:
        raise UniverseFileError(f"YAML over the {max_bytes}-byte bound")
    try:
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise UniverseFileError("YAML anchors and aliases are refused in universe files")
        return yaml.safe_load(text)
    except RecursionError:
        raise UniverseFileError("YAML nested too deeply") from None
    except yaml.YAMLError as exc:
        raise UniverseFileError(f"not valid YAML ({type(exc).__name__})") from None
