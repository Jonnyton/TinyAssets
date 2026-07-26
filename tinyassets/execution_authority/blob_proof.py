"""Fresh content-addressed blob proof with physical-root serialization."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import stat
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any, ContextManager, Iterator, TypeVar

if TYPE_CHECKING:
    from .verified import Verified

_INDEX_NAME = ".blob-index.json"
_LOCK_NAME = ".blob-root.lock"
_TEMP_PREFIX = ".blob-tmp-"
_INDEX_VERSION = 1
_MAX_INDEX_BYTES = 8 * 1024 * 1024
_MAX_BLOB_SIZE = (1 << 63) - 1
_WINDOWS_LOCK_RETRY_SECONDS = 0.05
_TransactionT = TypeVar("_TransactionT")


class BlobProofError(ValueError):
    """Blob state is malformed, stale, or cannot be proven safely."""


def _canonical_relative_path(value: object) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise BlobProofError("blob path must be a non-empty relative string")
    if "\\" in value or PureWindowsPath(value).drive:
        raise BlobProofError("blob path must use canonical relative separators")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise BlobProofError("blob path must be canonical and cannot escape the root")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise BlobProofError("blob path must be canonical and relative")
    if value in {_INDEX_NAME, _LOCK_NAME} or raw_parts[-1].startswith(_TEMP_PREFIX):
        raise BlobProofError("blob path is reserved for store coordination")
    return value


@dataclass(frozen=True, slots=True)
class BlobRef:
    """Immutable exact-byte identity for one blob binding."""

    relative_path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        _canonical_relative_path(self.relative_path)
        if (
            type(self.sha256) is not str
            or len(self.sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.sha256)
        ):
            raise BlobProofError("blob digest must be lowercase SHA-256 hex")
        if type(self.size) is not int or not 0 <= self.size <= _MAX_BLOB_SIZE:
            raise BlobProofError("blob size must be a non-negative 63-bit integer")


def _validated_ref(value: object) -> BlobRef:
    if type(value) is not BlobRef:
        raise BlobProofError("operation requires an exact BlobRef")
    try:
        validated = BlobRef(
            relative_path=value.relative_path,
            sha256=value.sha256,
            size=value.size,
        )
    except AttributeError as exc:
        raise BlobProofError("BlobRef contract is incomplete") from exc
    if validated != value:
        raise BlobProofError("BlobRef contract is invalid")
    return value


PhysicalRootIdentity = tuple[int, int]


def physical_root_identity(root: Path | str) -> PhysicalRootIdentity:
    """Return filesystem identity, following a supported alias to its directory."""

    try:
        resolved = Path(root).resolve(strict=True)
        root_stat = resolved.stat()
    except (OSError, RuntimeError) as exc:
        raise BlobProofError("physical blob-root identity is unavailable") from exc
    if not stat.S_ISDIR(root_stat.st_mode):
        raise BlobProofError("physical blob root must be a directory")
    device = getattr(root_stat, "st_dev", None)
    inode = getattr(root_stat, "st_ino", None)
    if type(device) is not int or type(inode) is not int or inode == 0:
        raise BlobProofError("physical blob-root identity is unavailable")
    return device, inode


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(file_stat.st_mode):
        return True
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def _lock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        while True:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                time.sleep(_WINDOWS_LOCK_RETRY_SECONDS)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock_fd(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def _windows_open_directory(path: Path) -> int:
    import ctypes
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80,  # FILE_READ_ATTRIBUTES
        0x1 | 0x2,  # share read/write, deliberately deny delete/rename
        None,
        3,  # OPEN_EXISTING
        0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        raise OSError(ctypes.get_last_error(), f"cannot lock directory {path}")

    class _HandleInformation(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("access_time", wintypes.FILETIME),
            ("write_time", wintypes.FILETIME),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("index_high", wintypes.DWORD),
            ("index_low", wintypes.DWORD),
        ]

    information = _HandleInformation()
    if not ctypes.windll.kernel32.GetFileInformationByHandle(handle, ctypes.byref(information)):
        ctypes.windll.kernel32.CloseHandle(handle)
        raise OSError(ctypes.get_last_error(), f"cannot inspect directory {path}")
    if not information.attributes & 0x10 or information.attributes & 0x400:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise BlobProofError("blob path contains a symlink or reparse point")
    try:
        current = path.lstat()
    except OSError:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise
    file_index = (information.index_high << 32) | information.index_low
    if _is_reparse_point(current) or current.st_ino != file_index:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise BlobProofError("blob directory identity changed while opening")
    return int(handle)


def _windows_close_handle(handle: int) -> None:
    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)


def _windows_create_file(path: Path) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    create_file = ctypes.windll.kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80000000 | 0x40000000,  # GENERIC_READ | GENERIC_WRITE
        0x1 | 0x2 | 0x4,  # share read/write/delete; identity checked after rename
        None,
        1,  # CREATE_NEW
        0x80,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), f"cannot create temporary blob {path}")
    try:
        return msvcrt.open_osfhandle(int(handle), os.O_BINARY)
    except BaseException:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise


class _SecureParent:
    """Stable parent traversal held for one filesystem decision."""

    def __init__(
        self,
        *,
        root: Path,
        parent_path: Path,
        handles: list[int],
        links: list[tuple[int, str, tuple[int, int]]],
        windows_links: list[tuple[Path, tuple[int, int]]],
        root_identity: PhysicalRootIdentity,
    ) -> None:
        self.root = root
        self.parent_path = parent_path
        self._handles = handles
        self._links = links
        self._windows_links = windows_links
        self._root_identity = root_identity

    @property
    def parent_fd(self) -> int | None:
        if os.name == "nt":
            return None
        return self._handles[-1]

    def stat_leaf(self, name: str) -> os.stat_result | None:
        try:
            if self.parent_fd is None:
                return (self.parent_path / name).lstat()
            return os.stat(name, dir_fd=self.parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise BlobProofError("blob target cannot be inspected safely") from exc

    def unlink_leaf(self, name: str) -> None:
        try:
            if self.parent_fd is None:
                (self.parent_path / name).unlink()
            else:
                os.unlink(name, dir_fd=self.parent_fd)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise BlobProofError("collected blob could not be removed") from exc

    def ensure_stable(self) -> None:
        if physical_root_identity(self.root) != self._root_identity:
            raise BlobProofError("physical blob-root identity changed during operation")
        if os.name == "nt":
            for path, expected_identity in self._windows_links:
                try:
                    current = path.lstat()
                except OSError as exc:
                    raise BlobProofError("blob parent changed during operation") from exc
                if (
                    _is_reparse_point(current)
                    or (current.st_dev, current.st_ino) != expected_identity
                ):
                    raise BlobProofError("blob parent changed during operation")
            return
        for parent_fd, name, expected_identity in self._links:
            try:
                current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise BlobProofError("blob parent changed during operation") from exc
            if _is_reparse_point(current) or (current.st_dev, current.st_ino) != expected_identity:
                raise BlobProofError("blob parent changed during operation")

    def close(self) -> None:
        close = _windows_close_handle if os.name == "nt" else os.close
        for handle in reversed(self._handles):
            close(handle)


class _HeldRegularFile:
    """Exact bytes whose open leaf identity remains held until proof completion."""

    def __init__(
        self,
        *,
        fd: int,
        content: bytes,
        path: Path,
        parent: _SecureParent,
        snapshot: os.stat_result,
    ) -> None:
        self.fd = fd
        self.content = content
        self.path = path
        self.parent = parent
        self.snapshot = snapshot

    @staticmethod
    def _identity_and_metadata(
        file_stat: os.stat_result,
    ) -> tuple[int, int, int, int]:
        return (
            file_stat.st_dev,
            file_stat.st_ino,
            file_stat.st_size,
            file_stat.st_mtime_ns,
        )

    def _ensure_leaf_snapshot(self) -> None:
        try:
            opened = os.fstat(self.fd)
        except OSError as exc:
            raise BlobProofError("blob leaf could not be rechecked safely") from exc
        current = self.parent.stat_leaf(self.path.name)
        expected = self._identity_and_metadata(self.snapshot)
        if (
            current is None
            or _is_reparse_point(current)
            or not stat.S_ISREG(opened.st_mode)
            or self._identity_and_metadata(opened) != expected
            or self._identity_and_metadata(current) != expected
        ):
            raise BlobProofError("blob leaf changed before proof completion")

    def _ensure_exact_content(self, expected_digest: str) -> None:
        digest = hashlib.sha256()
        offset = 0
        try:
            os.lseek(self.fd, 0, os.SEEK_SET)
            while True:
                chunk = os.read(self.fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                end = offset + len(chunk)
                if chunk != self.content[offset:end]:
                    raise BlobProofError("blob content changed before proof completion")
                offset = end
        except OSError as exc:
            raise BlobProofError("blob leaf could not be reread safely") from exc
        if offset != len(self.content) or digest.hexdigest() != expected_digest:
            raise BlobProofError("blob digest changed before proof completion")

    def ensure_stable(self, *, expected_digest: str | None = None) -> None:
        self.parent.ensure_stable()
        self._ensure_leaf_snapshot()
        if expected_digest is not None:
            self._ensure_exact_content(expected_digest)
            self._ensure_leaf_snapshot()
        self.parent.ensure_stable()

    def close(self) -> None:
        os.close(self.fd)


class _PhysicalRootCoordinator:
    def __init__(self, root: Path, identity: PhysicalRootIdentity) -> None:
        self.root = root
        self.identity = identity
        self._thread_lock = threading.RLock()
        self._local = threading.local()

    def _open_lock_file(self) -> int:
        path = self.root / _LOCK_NAME
        try:
            existing = path.lstat()
        except FileNotFoundError:
            existing = None
        except OSError as exc:
            raise BlobProofError("blob-root lock cannot be inspected") from exc
        if existing is not None and (
            _is_reparse_point(existing) or not stat.S_ISREG(existing.st_mode)
        ):
            raise BlobProofError("blob-root lock cannot be a symlink or reparse point")

        flags = os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
            opened = os.fstat(fd)
            current = path.lstat()
            if (
                _is_reparse_point(current)
                or not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise BlobProofError("blob-root lock identity changed while opening")
            if opened.st_size == 0:
                os.write(fd, b"\0")
                os.fsync(fd)
            return fd
        except Exception:
            if "fd" in locals():
                os.close(fd)
            raise

    def acquire(self) -> None:
        self._thread_lock.acquire()
        depth = getattr(self._local, "depth", 0)
        if depth:
            self._local.depth = depth + 1
            return
        try:
            if physical_root_identity(self.root) != self.identity:
                raise BlobProofError("physical blob-root identity changed")
            fd = self._open_lock_file()
            try:
                _lock_fd(fd)
            except BaseException:
                os.close(fd)
                raise
            if physical_root_identity(self.root) != self.identity:
                _unlock_fd(fd)
                os.close(fd)
                raise BlobProofError("physical blob-root identity changed")
            self._local.fd = fd
            self._local.depth = 1
        except Exception:
            self._thread_lock.release()
            raise

    def release(self) -> None:
        depth = getattr(self._local, "depth", 0)
        if depth <= 0:
            raise RuntimeError("blob-root coordinator released without acquisition")
        if depth > 1:
            self._local.depth = depth - 1
            self._thread_lock.release()
            return
        fd = self._local.fd
        try:
            _unlock_fd(fd)
        finally:
            os.close(fd)
            del self._local.fd
            self._local.depth = 0
            self._thread_lock.release()


_COORDINATORS: dict[PhysicalRootIdentity, _PhysicalRootCoordinator] = {}
_COORDINATORS_LOCK = threading.Lock()


def _coordinator_for(root: Path, identity: PhysicalRootIdentity) -> _PhysicalRootCoordinator:
    with _COORDINATORS_LOCK:
        coordinator = _COORDINATORS.get(identity)
        if coordinator is None:
            coordinator = _PhysicalRootCoordinator(root, identity)
            _COORDINATORS[identity] = coordinator
        return coordinator


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BlobProofError(f"blob index contains duplicate key {key!r}")
        result[key] = value
    return result


class _BlobProofStoreBase:
    """Strict operation-local blob index and fresh M2 verifier."""

    def __init__(self, root: Path | str) -> None:
        try:
            self._root = Path(root).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise BlobProofError("physical blob root is unavailable") from exc
        self._identity = physical_root_identity(self._root)
        self._coordinator = _coordinator_for(self._root, self._identity)

    @property
    def root_identity(self) -> PhysicalRootIdentity:
        return self._identity

    @contextmanager
    def coordinated(self) -> Iterator[None]:
        """Acquire the blob-root lock before a caller opens its SQLite transaction."""

        self._coordinator.acquire()
        try:
            yield
        finally:
            self._coordinator.release()

    @contextmanager
    def coordinated_transaction(
        self,
        begin_transaction: Callable[[], ContextManager[_TransactionT]],
    ) -> Iterator[_TransactionT]:
        """Acquire the blob root before invoking a transaction context factory."""

        if not callable(begin_transaction):
            raise TypeError("begin_transaction must be a zero-argument callable")
        with self.coordinated():
            with begin_transaction() as transaction:
                yield transaction

    @contextmanager
    def _secure_parent(
        self,
        relative_path: str,
        *,
        create_parents: bool,
    ) -> Iterator[tuple[_SecureParent, str, Path]]:
        parts = _canonical_relative_path(relative_path).split("/")
        handles: list[int] = []
        links: list[tuple[int, str, tuple[int, int]]] = []
        windows_links: list[tuple[Path, tuple[int, int]]] = []
        current_path = self._root
        try:
            if os.name == "nt":
                handles.append(_windows_open_directory(self._root))
            else:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                try:
                    root_fd = os.open(self._root, flags)
                except OSError as exc:
                    raise BlobProofError("physical blob root cannot be opened") from exc
                root_stat = os.fstat(root_fd)
                if (root_stat.st_dev, root_stat.st_ino) != self._identity:
                    os.close(root_fd)
                    raise BlobProofError("physical blob-root identity changed")
                handles.append(root_fd)

            for part in parts[:-1]:
                next_path = current_path / part
                if os.name == "nt":
                    if create_parents:
                        try:
                            next_path.mkdir()
                        except FileExistsError:
                            pass
                        except OSError as exc:
                            raise BlobProofError("blob parent cannot be created safely") from exc
                    try:
                        handles.append(_windows_open_directory(next_path))
                    except OSError as exc:
                        if not create_parents and not next_path.exists():
                            raise BlobProofError("blob path is missing from the root") from exc
                        raise BlobProofError(
                            "blob path cannot be opened without reparse traversal"
                        ) from exc
                    opened_stat = next_path.lstat()
                    if _is_reparse_point(opened_stat):
                        raise BlobProofError("blob path contains a symlink or reparse point")
                    windows_links.append((next_path, (opened_stat.st_dev, opened_stat.st_ino)))
                else:
                    parent_fd = handles[-1]
                    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                    flags |= getattr(os, "O_NOFOLLOW", 0)
                    try:
                        child_fd = os.open(part, flags, dir_fd=parent_fd)
                    except FileNotFoundError:
                        if not create_parents:
                            raise BlobProofError("blob path is missing from the root")
                        try:
                            os.mkdir(part, mode=0o700, dir_fd=parent_fd)
                            child_fd = os.open(part, flags, dir_fd=parent_fd)
                        except OSError as exc:
                            raise BlobProofError("blob parent cannot be created safely") from exc
                    except OSError as exc:
                        raise BlobProofError(
                            "blob path cannot be opened without symlink traversal"
                        ) from exc
                    child_stat = os.fstat(child_fd)
                    if not stat.S_ISDIR(child_stat.st_mode):
                        os.close(child_fd)
                        raise BlobProofError("blob path parent is not a directory")
                    links.append((parent_fd, part, (child_stat.st_dev, child_stat.st_ino)))
                    handles.append(child_fd)
                current_path = next_path

            parent = _SecureParent(
                root=self._root,
                parent_path=current_path,
                handles=handles,
                links=links,
                windows_links=windows_links,
                root_identity=self._identity,
            )
            leaf = parts[-1]
            leaf_stat = parent.stat_leaf(leaf)
            if leaf_stat is not None:
                if _is_reparse_point(leaf_stat):
                    raise BlobProofError("blob target cannot be a symlink or reparse point")
                if not stat.S_ISREG(leaf_stat.st_mode):
                    raise BlobProofError("blob target must be a regular file")
            yield parent, leaf, current_path / leaf
        finally:
            if "parent" in locals():
                parent.close()
            else:
                close = _windows_close_handle if os.name == "nt" else os.close
                for handle in reversed(handles):
                    close(handle)

    @contextmanager
    def _secure_root_parent(self) -> Iterator[_SecureParent]:
        handles: list[int] = []
        try:
            if os.name == "nt":
                handles.append(_windows_open_directory(self._root))
            else:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                flags |= getattr(os, "O_NOFOLLOW", 0)
                root_fd = os.open(self._root, flags)
                root_stat = os.fstat(root_fd)
                if (root_stat.st_dev, root_stat.st_ino) != self._identity:
                    os.close(root_fd)
                    raise BlobProofError("physical blob-root identity changed")
                handles.append(root_fd)
            parent = _SecureParent(
                root=self._root,
                parent_path=self._root,
                handles=handles,
                links=[],
                windows_links=[],
                root_identity=self._identity,
            )
            yield parent
        finally:
            if "parent" in locals():
                parent.close()
            else:
                close = _windows_close_handle if os.name == "nt" else os.close
                for handle in reversed(handles):
                    close(handle)

    @staticmethod
    def _read_regular_file(
        path: Path,
        *,
        max_bytes: int | None = None,
        parent: _SecureParent | None = None,
        hold_open: bool = False,
    ) -> bytes | _HeldRegularFile:
        if hold_open and parent is None:
            raise BlobProofError("held blob reads require a secure parent")
        if parent is not None:
            parent.ensure_stable()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            if parent is not None and parent.parent_fd is not None:
                fd = os.open(path.name, flags, dir_fd=parent.parent_fd)
            else:
                fd = os.open(path, flags)
        except OSError as exc:
            raise BlobProofError("blob or index file is missing or unsafe") from exc
        keep_open = False
        try:
            before = os.fstat(fd)
            current = parent.stat_leaf(path.name) if parent is not None else path.lstat()
            if current is None:
                raise BlobProofError("blob or index disappeared while opening")
            if (
                _is_reparse_point(current)
                or not stat.S_ISREG(before.st_mode)
                or (before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise BlobProofError("blob or index identity changed while opening")
            if max_bytes is not None and before.st_size > max_bytes:
                raise BlobProofError("blob index exceeds its size limit")
            chunks: list[bytes] = []
            remaining = max_bytes
            while True:
                chunk_size = 1024 * 1024
                if remaining is not None:
                    chunk_size = min(chunk_size, remaining + 1)
                chunk = os.read(fd, chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining < 0:
                        raise BlobProofError("blob index exceeds its size limit")
            after = os.fstat(fd)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise BlobProofError("blob changed while exact bytes were read")
            latest = parent.stat_leaf(path.name) if parent is not None else path.lstat()
            if (
                latest is None
                or _is_reparse_point(latest)
                or (after.st_dev, after.st_ino) != (latest.st_dev, latest.st_ino)
            ):
                raise BlobProofError("blob path changed while exact bytes were read")
            content = b"".join(chunks)
            if hold_open:
                assert parent is not None
                held = _HeldRegularFile(
                    fd=fd,
                    content=content,
                    path=path,
                    parent=parent,
                    snapshot=after,
                )
                keep_open = True
                return held
            return content
        finally:
            if not keep_open:
                os.close(fd)

    def _load_index(self) -> dict[str, BlobRef]:
        path = self._root / _INDEX_NAME
        try:
            with self._secure_root_parent() as parent:
                index_stat = parent.stat_leaf(_INDEX_NAME)
                if index_stat is None:
                    return {}
                if _is_reparse_point(index_stat) or not stat.S_ISREG(index_stat.st_mode):
                    raise BlobProofError("blob index must be a regular non-link file")
                raw = self._read_regular_file(
                    path,
                    max_bytes=_MAX_INDEX_BYTES,
                    parent=parent,
                )
                assert isinstance(raw, bytes)
                parent.ensure_stable()
            document = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
            if type(document) is not dict or set(document) != {"version", "blobs"}:
                raise BlobProofError("blob index has an invalid top-level contract")
            if type(document["version"]) is not int or document["version"] != _INDEX_VERSION:
                raise BlobProofError("blob index has an unsupported version")
            entries = document["blobs"]
            if type(entries) is not list:
                raise BlobProofError("blob index blobs must be a list")
            index: dict[str, BlobRef] = {}
            previous_path: str | None = None
            for entry in entries:
                if type(entry) is not dict or set(entry) != {
                    "relative_path",
                    "sha256",
                    "size",
                }:
                    raise BlobProofError("blob index entry has an invalid contract")
                ref = BlobRef(
                    relative_path=entry["relative_path"],
                    sha256=entry["sha256"],
                    size=entry["size"],
                )
                if previous_path is not None and ref.relative_path <= previous_path:
                    raise BlobProofError("blob index entries must be unique and sorted")
                index[ref.relative_path] = ref
                previous_path = ref.relative_path
            return index
        except (BlobProofError, UnicodeDecodeError, json.JSONDecodeError):
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise BlobProofError("blob index is malformed") from exc

    def _persist_index(self, index: dict[str, BlobRef]) -> None:
        payload = {
            "version": _INDEX_VERSION,
            "blobs": [
                {
                    "relative_path": ref.relative_path,
                    "sha256": ref.sha256,
                    "size": ref.size,
                }
                for ref in sorted(index.values(), key=lambda item: item.relative_path)
            ],
        }
        data = (
            json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
        with self._secure_root_parent() as parent:
            self._atomic_replace(self._root / _INDEX_NAME, data, parent=parent)
            parent.ensure_stable()

    @staticmethod
    def _atomic_replace(
        target: Path,
        data: bytes,
        *,
        parent: _SecureParent,
    ) -> None:
        parent.ensure_stable()
        temporary_name = f"{_TEMP_PREFIX}{secrets.token_hex(16)}"
        temporary = parent.parent_path / temporary_name
        fd: int | None = None
        try:
            if parent.parent_fd is None:
                fd = _windows_create_file(temporary)
            else:
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                flags |= getattr(os, "O_NOFOLLOW", 0)
                fd = os.open(
                    temporary_name,
                    flags,
                    0o600,
                    dir_fd=parent.parent_fd,
                )
            with os.fdopen(fd, "wb", closefd=False) as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            before = os.fstat(fd)
            if parent.parent_fd is None:
                os.replace(temporary, target)
                current = target.lstat()
            else:
                os.replace(
                    temporary_name,
                    target.name,
                    src_dir_fd=parent.parent_fd,
                    dst_dir_fd=parent.parent_fd,
                )
                current = os.stat(
                    target.name,
                    dir_fd=parent.parent_fd,
                    follow_symlinks=False,
                )
                os.fsync(parent.parent_fd)
            if _is_reparse_point(current) or (before.st_dev, before.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise BlobProofError("atomic blob target identity changed")
        except BaseException:
            try:
                if parent.parent_fd is None:
                    temporary.unlink()
                else:
                    os.unlink(temporary_name, dir_fd=parent.parent_fd)
            except OSError:
                pass
            raise
        finally:
            if fd is not None:
                os.close(fd)

    def put_blob(self, relative_path: str, content: bytes) -> BlobRef:
        if type(content) is not bytes:
            raise BlobProofError("blob content must be exact bytes")
        ref = BlobRef(
            relative_path=_canonical_relative_path(relative_path),
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )
        with self.coordinated():
            index = self._load_index()
            previous_index = index.copy()
            with self._secure_parent(
                ref.relative_path,
                create_parents=True,
            ) as (parent, _leaf, target):
                self._atomic_replace(target, content, parent=parent)
                parent.ensure_stable()
                index[ref.relative_path] = ref
                self._persist_index(index)
                try:
                    parent.ensure_stable()
                except BlobProofError:
                    self._persist_index(previous_index)
                    raise
        return ref

    def collect_blob(self, ref: BlobRef) -> None:
        ref = _validated_ref(ref)
        with self.coordinated():
            index = self._load_index()
            if index.get(ref.relative_path) != ref:
                raise BlobProofError("blob reference is stale or missing from the index")
            with self._secure_parent(
                ref.relative_path,
                create_parents=False,
            ) as (parent, leaf, _target):
                parent.ensure_stable()
                del index[ref.relative_path]
                self._persist_index(index)
                parent.unlink_leaf(leaf)
                parent.ensure_stable()

    def _verify_blob(
        self,
        ref: BlobRef,
        *,
        verified_at: int,
        mint_verified: Callable[..., Any],
    ) -> Any:
        ref = _validated_ref(ref)
        if type(verified_at) is not int or verified_at < 0:
            raise BlobProofError("verified_at must be a non-negative integer")
        with self.coordinated():
            index = self._load_index()
            if index.get(ref.relative_path) != ref:
                raise BlobProofError("blob reference is stale or missing from the index")
            with self._secure_parent(
                ref.relative_path,
                create_parents=False,
            ) as (parent, _leaf, target):
                held = self._read_regular_file(
                    target,
                    parent=parent,
                    hold_open=True,
                )
                assert isinstance(held, _HeldRegularFile)
                try:
                    digest = hashlib.sha256(held.content).hexdigest()
                    if len(held.content) != ref.size:
                        raise BlobProofError("blob size does not match its indexed reference")
                    if digest != ref.sha256:
                        raise BlobProofError("blob digest does not match its indexed reference")
                    held.ensure_stable()
                    verified = mint_verified(
                        ref,
                        domain="tinyassets.blob-ref.v1",
                        evidence_digest=digest,
                        verifier_id=(f"filesystem:{self._identity[0]:x}:{self._identity[1]:x}"),
                        verified_at=verified_at,
                    )
                    held.ensure_stable(expected_digest=digest)
                    return verified
                finally:
                    held.close()

    def list_refs(self) -> tuple[BlobRef, ...]:
        with self.coordinated():
            index = self._load_index()
            return tuple(sorted(index.values(), key=lambda ref: ref.relative_path))


class _UninstalledBlobProofStore(_BlobProofStoreBase):
    def __init__(self, root: Path | str) -> None:
        raise RuntimeError("blob proof capabilities are not installed")


BlobProofStore: type[_BlobProofStoreBase] = _UninstalledBlobProofStore
_CAPABILITIES_INSTALLED = False


def _install_verified_capabilities(
    mint_m2: Callable[..., Any],
    auth_checker: Callable[..., Any],
) -> None:
    """One-shot package bootstrap; package ``__init__`` deletes this installer."""

    global BlobProofStore, _CAPABILITIES_INSTALLED
    if _CAPABILITIES_INSTALLED:
        raise RuntimeError("blob proof capabilities are already installed")
    if not callable(mint_m2) or not callable(auth_checker):
        raise TypeError("blob proof capabilities must be callable")

    class _InstalledBlobProofStore(_BlobProofStoreBase):
        def verify_blob(
            self,
            ref: BlobRef,
            *,
            verified_at: int,
        ) -> Verified[BlobRef]:
            def mint_verified(value: BlobRef, **metadata: Any) -> Verified[BlobRef]:
                evidence = mint_m2(value, **metadata)
                return auth_checker(evidence, expected_mechanism="m2")

            return self._verify_blob(
                ref,
                verified_at=verified_at,
                mint_verified=mint_verified,
            )

    _InstalledBlobProofStore.__name__ = "BlobProofStore"
    _InstalledBlobProofStore.__qualname__ = "BlobProofStore"
    BlobProofStore = _InstalledBlobProofStore
    _CAPABILITIES_INSTALLED = True


__all__ = [
    "BlobProofError",
    "BlobProofStore",
    "BlobRef",
    "PhysicalRootIdentity",
    "physical_root_identity",
]
