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

import errno
import os
import stat
import uuid
from pathlib import Path

from tinyassets import workspace_fs as fs

__all__ = [
    "MAX_BRAIN_FILE_BYTES",
    "MAX_CONFIG_BYTES",
    "MAX_FRONTMATTER_BYTES",
    "MAX_PLATFORM_FILE_BYTES",
    "MAX_UNIVERSE_FILE_BYTES",
    "UniverseFileError",
    "connect_db",
    "is_data_path",
    "list_universe_dir",
    "load_untrusted_yaml",
    "open_runtime_dir",
    "read_data_path",
    "read_universe_file",
    "read_universe_text",
    "unlink_data_path",
    "unlink_universe_file",
    "write_data_path",
    "write_universe_file",
]

#: Default bound: generous (a brain file is kilobytes) but fixed.
MAX_UNIVERSE_FILE_BYTES = 8 * 1024 * 1024
#: A brain / soul / log markdown file.
MAX_BRAIN_FILE_BYTES = 1024 * 1024
#: A platform record, log or canon document the daemon reads whole.
MAX_PLATFORM_FILE_BYTES = 64 * 1024 * 1024
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


def open_runtime_dir(universe_dir: Path | str, *parts: str) -> int:
    """A descriptor for ``universe_dir/.runtime/<parts>``, created if missing.

    The daemon creates platform state inside a folder other processes of the
    same universe can write (a workflow provider jail binds it read-write), so
    every component is created and then opened through the parent descriptor
    with ``O_NOFOLLOW``: a link planted anywhere on the path refuses rather
    than redirecting the daemon into another universe. POSIX only; the caller
    closes the descriptor.
    """
    current = fs.open_dir_nofollow(Path(universe_dir).resolve(strict=False))
    try:
        for part in (".runtime", *parts):
            _check_component(part)
            try:
                os.mkdir(part, 0o700, dir_fd=current)
            except FileExistsError:
                pass
            child = fs.open_subdir_nofollow(current, part)
            os.close(current)
            current = child
    except BaseException:
        os.close(current)
        raise
    return current


def _parent_dir_fd(root: Path, parts: list[str], *, create: bool) -> int:
    """POSIX: a descriptor for the directory holding ``parts[-1]``, every
    component opened (and, with ``create``, made) with no link followed."""
    current = fs.open_dir_nofollow(root.resolve(strict=False))
    try:
        for part in parts[:-1]:
            _check_component(part)
            if create:
                try:
                    os.mkdir(part, 0o777, dir_fd=current)
                except FileExistsError:
                    pass
            child = fs.open_subdir_nofollow(current, part)
            os.close(current)
            current = child
    except BaseException:
        os.close(current)
        raise
    return current


def _split(relpath: str) -> list[str]:
    parts = str(relpath).replace("\\", "/").split("/")
    for part in parts:
        _check_component(part)
    return parts


def _windows_parent(root: Path, parts: list[str], *, create: bool) -> Path:
    """Non-POSIX: the parent of ``parts[-1]``, each component checked to be no
    link BEFORE anything is created inside it. Check-then-use: this host is
    the single-tenant tray, so the cross-universe guarantee is POSIX-only."""
    parent = root
    for part in parts[:-1]:
        parent = parent / part
        try:
            info = parent.lstat()
        except FileNotFoundError:
            if not create:
                raise
            parent.mkdir()
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0):
            raise UniverseFileError(f"{part!r} is a link; universe files are written link-free")
    return parent


def write_universe_file(
    universe_dir: Path | str,
    relpath: str,
    data: bytes,
    *,
    make_parents: bool = True,
    mode: str = "replace",
) -> None:
    """Write ``universe_dir/relpath`` with no link followed. The one writer.

    Every directory component is opened (and with ``make_parents`` created)
    with no link followed. ``mode``:

    * ``"replace"`` (default): the bytes go to a fresh temp file created
      ``O_EXCL|O_NOFOLLOW`` in the verified directory, then renamed over the
      name. A rename replaces a link at the final name rather than writing
      through it, so a planted ``config.yaml -> /data/<other>/config.yaml``
      becomes this universe's own file and the other is never touched.
    * ``"exclusive"``: create the name ``O_CREAT|O_EXCL|O_NOFOLLOW``;
      ``FileExistsError`` if anything (a link included) is already there.
    * ``"append"``: open ``O_APPEND|O_CREAT|O_NOFOLLOW``; a link refuses.
    """
    if mode not in ("replace", "exclusive", "append"):
        raise ValueError(f"unknown write mode {mode!r}")
    root = Path(universe_dir)
    parts = _split(relpath)
    name = parts[-1]
    nofollow = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    if not getattr(fs, "_POSIX", False):
        parent = _windows_parent(root, parts, create=make_parents)
        target = parent / name
        if mode != "replace":
            if mode == "exclusive" and os.path.lexists(target):
                # Same contract as POSIX O_EXCL: anything there, a link included.
                raise FileExistsError(str(target))
            if os.path.islink(target):
                raise UniverseFileError(f"{relpath!r} is a link; nothing was written")
            with open(target, "xb" if mode == "exclusive" else "ab") as handle:  # noqa: PTH123
                handle.write(data)
            return
        temp = parent / f".{name}.{uuid.uuid4().hex[:12]}.tmp"
        try:
            with open(temp, "xb") as handle:  # noqa: PTH123 - parent link-checked above
                handle.write(data)
            os.replace(temp, target)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        return
    dir_fd = _parent_dir_fd(root, parts, create=make_parents)
    try:
        if mode != "replace":
            flags = os.O_WRONLY | os.O_CREAT | nofollow
            flags |= os.O_EXCL if mode == "exclusive" else os.O_APPEND
            try:
                fd = os.open(name, flags, 0o666, dir_fd=dir_fd)
            except OSError as exc:
                if exc.errno == errno.ELOOP:
                    raise UniverseFileError(
                        f"{relpath!r} is a link; universe files are written link-free"
                    ) from exc
                raise
            try:
                _write_all(fd, data)
            finally:
                os.close(fd)
            return
        tmp = f".{name}.{uuid.uuid4().hex[:12]}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o666, dir_fd=dir_fd)
        try:
            try:
                _write_all(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        except BaseException:
            try:
                os.unlink(tmp, dir_fd=dir_fd)
            except OSError:
                pass
            raise
    finally:
        os.close(dir_fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def unlink_universe_file(universe_dir: Path | str, relpath: str) -> None:
    """Remove ``universe_dir/relpath`` (a link there is removed itself), never
    through a linked directory. ``FileNotFoundError`` when absent."""
    root = Path(universe_dir)
    parts = _split(relpath)
    if not getattr(fs, "_POSIX", False):
        (_windows_parent(root, parts, create=False) / parts[-1]).unlink()
        return
    dir_fd = _parent_dir_fd(root, parts, create=False)
    try:
        os.unlink(parts[-1], dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _data_relative(path: Path) -> tuple[Path, str] | None:
    """``(data root, relpath)`` when ``path`` names something under the data
    dir, else ``None``. ``path`` is never resolved -- that would follow the
    very link being refused -- so both spellings of the root are tried."""
    from tinyassets.storage import data_dir

    base = data_dir()
    for root in (base, base.resolve()):
        try:
            rel = Path(path).relative_to(root).as_posix()
        except ValueError:
            continue
        if rel in ("", "."):
            return None
        return root, rel
    return None


def is_data_path(path: Path | str) -> bool:
    """Whether ``path`` names something under the data dir (lexically)."""
    return _data_relative(Path(path)) is not None


def read_data_path(path: Path | str, *, max_bytes: int = MAX_UNIVERSE_FILE_BYTES) -> bytes | None:
    """Bytes of a daemon file by absolute path; ``None`` when it is absent.

    Under the data dir every universe folder is writable by something the
    universe runs (a workflow provider jail binds it read-write and allows
    ``symlink``), so the path is walked from the data dir with no link at any
    component. Any refusal -- a link, a non-regular file, over ``max_bytes``,
    an unreadable component -- raises :class:`UniverseFileError`: it must
    never read as "absent", which a read-modify-write would then overwrite.
    A path outside the data dir is in no universe and reads plainly.
    """
    located = _data_relative(Path(path))
    try:
        if located is None:
            return Path(path).read_bytes()
        return read_universe_file(located[0], located[1], max_bytes=max_bytes)
    except FileNotFoundError:
        return None
    except UniverseFileError:
        raise
    except OSError as exc:
        if located is None:
            raise
        raise UniverseFileError(f"{located[1]!r} was refused: {exc}") from exc


def write_data_path(
    path: Path | str,
    data: bytes | str,
    *,
    make_parents: bool = True,
    mode: str = "replace",
) -> None:
    """Write a daemon file by absolute path, never through a link.

    Under the data dir this is :func:`write_universe_file` from the data root
    (no link at any component; ``mode`` replace / exclusive / append). Outside
    it -- a path in no universe -- the same modes on a plain path.
    """
    payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    located = _data_relative(Path(path))
    if located is not None:
        write_universe_file(
            located[0], located[1], payload, make_parents=make_parents, mode=mode,
        )
        return
    target = Path(path)
    if make_parents:
        target.parent.mkdir(parents=True, exist_ok=True)
    if mode != "replace":
        with open(target, "xb" if mode == "exclusive" else "ab") as handle:  # noqa: PTH123
            handle.write(payload)
        return
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:12]}.tmp")
    try:
        with open(temp, "xb") as handle:  # noqa: PTH123 - outside every universe
            handle.write(payload)
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def unlink_data_path(path: Path | str) -> None:
    """Remove a daemon file by absolute path, never through a linked directory.
    ``FileNotFoundError`` when absent."""
    located = _data_relative(Path(path))
    if located is None:
        Path(path).unlink()
        return
    unlink_universe_file(located[0], located[1])


#: Files SQLite opens beside a database; each could be planted as a link.
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")


def _sqlite_target(database: str, uri: bool) -> tuple[Path, str] | None:
    """``(filesystem path, uri to open)`` for an on-disk database, else ``None``."""
    from urllib.parse import unquote, urlsplit
    from urllib.request import url2pathname

    if not uri:
        if database in ("", ":memory:"):
            return None
        target = Path(database).absolute()
        return target, f"{target.as_uri()}?nofollow=1"
    if not database.startswith("file:"):
        return None
    parts = urlsplit(database)
    if parts.path in ("", ":memory:") or "mode=memory" in parts.query:
        return None
    target = Path(url2pathname(unquote(parts.path))).absolute()
    joiner = "&" if parts.query else "?"
    return target, f"{database}{joiner}nofollow=1"


#: Daemon-owned per-universe state outside every jail; must equal
#: ``tinyassets.providers.provider_jail.UNIVERSE_SIDECARS_DIR``.
_SIDECARS_DIR = ".universe-sidecars"
_PROVENANCE_DIR = "db-provenance"
_PROVENANCE_READY = ".initialized"


def _is_universe_state_db(parts: list[str]) -> bool:
    """A hidden database at a universe's root: platform state the universe's
    own processes can pre-create (``<data>/<uid>/.<name>.db``)."""
    return (
        len(parts) == 2
        and not parts[0].startswith(".")
        and parts[1].startswith(".")
        and parts[1].endswith(".db")
    )


def _provenance_path(root: Path, uid: str, name: str) -> Path:
    return root / _SIDECARS_DIR / uid / _PROVENANCE_DIR / name


def _identity(info: os.stat_result) -> str:
    return f"{info.st_dev}:{info.st_ino}"


def _provenance_epoch(root: Path) -> float:
    """When provenance first ran on this data dir (written once, exclusively)."""
    import time

    epoch = root / _SIDECARS_DIR / ".db-provenance-epoch"
    try:
        write_data_path(epoch, repr(time.time()), mode="exclusive")
    except FileExistsError:
        pass
    return float((read_data_path(epoch) or b"0").decode("ascii"))


def _registered_at(root: Path, uid: str) -> float | None:
    """The universe's ``created_at`` from the data-root registry (which no jail
    binds), or ``None`` for an unregistered directory."""
    from tinyassets.daemon_server import get_universe

    try:
        return float(get_universe(root, universe_id=uid)["created_at"])
    except KeyError:
        return None


def _grandfather_state_dbs(root: Path, uid: str, dir_fd: int) -> None:
    """First sight of a universe since provenance landed.

    A universe registered BEFORE provenance existed (or an unregistered legacy
    directory) has its hidden databases recorded as daemon-made: they predate
    the check, a one-time window. A universe registered AFTER it gets nothing
    grandfathered -- every state database it has must be one the daemon made,
    so a file pre-seeded by its own processes before the daemon's first open
    is refused rather than trusted.
    """
    ready = _provenance_path(root, uid, _PROVENANCE_READY)
    if read_data_path(ready) is not None:
        return
    registered = _registered_at(root, uid)
    if registered is not None and registered >= _provenance_epoch(root):
        try:
            write_data_path(ready, "1", mode="exclusive")
        except FileExistsError:
            pass
        return
    for entry in os.listdir(dir_fd):
        if not _is_universe_state_db([uid, entry]):
            continue
        info = os.lstat(entry, dir_fd=dir_fd)
        if stat.S_ISREG(info.st_mode):
            write_data_path(_provenance_path(root, uid, entry), _identity(info))
    try:
        write_data_path(ready, "1", mode="exclusive")
    except FileExistsError:
        pass


def _check_db_provenance(root: Path, parts: list[str], dir_fd: int, *, read_only: bool) -> None:
    """Refuse a universe state database the daemon did not create.

    The universe's processes can write its root, so a hidden database that is
    absent until first use (``.effector_consents.db``) could be pre-seeded as
    a regular SQLite file holding forged rows -- an agent granting itself its
    owner's consent (concern 2026-10-01-platform-state-inside-the-universe-dir).
    The daemon records the device and inode of every state database it
    creates, outside the universe; an existing file without a matching record
    is refused. A new database is created here ``O_EXCL|O_NOFOLLOW`` and
    recorded BEFORE SQLite opens it.
    """
    import time

    uid, name = parts
    _grandfather_state_dbs(root, uid, dir_fd)
    record = _provenance_path(root, uid, name)
    try:
        info = os.lstat(name, dir_fd=dir_fd)
    except FileNotFoundError:
        if read_only:
            return  # SQLite reports the missing file itself
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            fd = os.open(name, flags | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=dir_fd)
        except FileExistsError:
            info = os.lstat(name, dir_fd=dir_fd)  # a concurrent daemon open made it
        else:
            try:
                write_data_path(record, _identity(os.fstat(fd)))
            finally:
                os.close(fd)
            return
    expected = _identity(info)
    for _ in range(20):  # a concurrent creator writes the record just after O_EXCL
        found = read_data_path(record)
        if found is not None and found.decode("ascii", "replace") == expected:
            return
        if found is not None:
            break
        time.sleep(0.05)
    raise UniverseFileError(
        f"{name} in universe {uid!r} was not created by the daemon; refusing to "
        "open it as platform state"
    )


def connect_db(database: str | os.PathLike, *args: object, uri: bool = False, **kwargs: object):
    """``sqlite3.connect`` that never opens a database through a link under the data dir.

    A workflow provider jail binds its universe read-write and allows
    ``symlink``, so ``.runs.db -> /data/<other>/.runs.db`` would otherwise make
    the daemon read and write another universe's database in this one's
    context. Under the data dir: every directory component must be link-free,
    the database opens with SQLite's ``nofollow`` (``SQLITE_OPEN_NOFOLLOW``,
    refusing a link at the file itself), and a ``-wal``/``-shm``/``-journal``
    sidecar that is a link is refused before SQLite can open it. A refusal is
    a :class:`UniverseFileError`. Elsewhere this is plain ``sqlite3.connect``.
    ``sqlite3.connect`` is looked up at call time, so tests that patch it still
    see every call.
    """
    import sqlite3

    raw = os.fspath(database)
    if isinstance(raw, bytes):
        return sqlite3.connect(database, *args, uri=uri, **kwargs)
    target = _sqlite_target(raw, uri)
    located = _data_relative(target[0]) if target is not None else None
    if target is None or located is None:
        return sqlite3.connect(database, *args, uri=uri, **kwargs)
    root, relpath = located
    parts = _split(relpath)
    try:
        if getattr(fs, "_POSIX", False):
            dir_fd = _parent_dir_fd(root, parts, create=False)
            try:
                for suffix in _SQLITE_SIDECARS:
                    try:
                        info = os.lstat(parts[-1] + suffix, dir_fd=dir_fd)
                    except FileNotFoundError:
                        continue
                    if stat.S_ISLNK(info.st_mode):
                        raise UniverseFileError(
                            f"{relpath}{suffix} is a link; a database is opened link-free"
                        )
                if _is_universe_state_db(parts):
                    read_only = "mode=ro" in target[1]
                    _check_db_provenance(root, parts, dir_fd, read_only=read_only)
            finally:
                os.close(dir_fd)
        elif len(parts) > 1:
            _lstat_nofollow_windows(root, "/".join(parts[:-1]))
    except FileNotFoundError:
        pass  # a missing parent: let SQLite report it in its own terms
    except UniverseFileError:
        raise
    except OSError as exc:
        raise UniverseFileError(f"{relpath!r} was refused: {exc}") from exc
    return sqlite3.connect(target[1], *args, uri=True, **kwargs)


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
