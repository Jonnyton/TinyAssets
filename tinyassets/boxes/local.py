"""The local `BoxProvider` driver: one host directory per command center, for tests and dev.

**This driver has no kernel boundary.** It runs commands as host processes in
the box directory. It exists so the platform can code against `BoxProvider`
today, and so the driver-agnostic contract suite has a reference driver. It
refuses to start unless the caller passes ``allow_unisolated=True``. The
isolating drivers (gVisor, then Firecracker) implement the same contract.

What it does guarantee is everything above the kernel:

* paths resolve beneath the box directory through directory descriptors, with
  every component opened ``O_NOFOLLOW``, so a planted link is never followed;
* every operation checks the handle's account against the command center's
  owner and its epoch against the current placement epoch;
* mutations are idempotent by operation id, and a restart turns in-flight
  operations into ``unknown_after_restore``;
* writes go to a temporary file in the same directory and are renamed into
  place, so a reader never sees a half-written file.

POSIX only, like `tinyassets.workspace_fs`: there is no safe descriptor-based
equivalent on Windows, so there is no fallback.
"""

from __future__ import annotations

import errno
import hashlib
import os
import re
import secrets
import signal
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from tinyassets.boxes.provider import (
    BOX_ROOT,
    BoxAuthError,
    BoxError,
    BoxHandle,
    BoxNotFound,
    BoxPathError,
    BoxUsage,
    DestroyReceipt,
    DirEntry,
    DirPage,
    ExecEvent,
    ExecLimits,
    ExecState,
    ExecStatus,
    ExportProfile,
    FileRead,
    FileStat,
    FileWrite,
    ImportReport,
    Snapshot,
    StaleHandle,
    StreamIn,
    WriteConflict,
    WriteMode,
    box_relpath,
)
from tinyassets.boxes.state import BoxHostState, op_digest

__all__ = ["LocalBoxProvider"]

_POSIX = os.name == "posix"
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_CC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TMP_PREFIX = ".boxtmp-"
_POLL_S = 0.02
_READ_MANY_RETRIES = 3


def _kind(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISLNK(mode):
        return "link"
    return "other"


def _path_error(exc: OSError, path: str) -> BoxError:
    if exc.errno == errno.ENOENT:
        return BoxNotFound(errno.ENOENT, f"no such box path: {path}")
    if exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return BoxPathError(f"box path {path!r} crosses a link or a non-directory")
    return BoxError(exc.errno, f"{path}: {exc.strerror}")


@dataclass
class _Running:
    proc: subprocess.Popen
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class LocalBoxProvider:
    """`BoxProvider` over ``<boxes_root>/<command_center_id>/``. Dev and tests only."""

    def __init__(
        self,
        *,
        boxes_root: Path,
        state_dir: Path,
        owner_of: Callable[[str], str | None],
        allow_unisolated: bool = False,
    ) -> None:
        if not allow_unisolated:
            raise BoxError(
                "the local box driver runs commands on the host with no kernel boundary; "
                "construct it with allow_unisolated=True only for tests and single-user dev"
            )
        if not _POSIX:
            raise NotImplementedError(
                "the local box driver needs POSIX openat semantics (O_NOFOLLOW + dir_fd); "
                f"this host is {os.name!r}, and there is no safe fallback"
            )
        self._root = Path(boxes_root)
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._state_dir = Path(state_dir)
        self._exec_dir = self._state_dir / "execs"
        self._exec_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._state = BoxHostState(self._state_dir / "boxhost.db")
        self._owner_of = owner_of
        self._running: dict[str, _Running] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # -- authentication ----------------------------------------------------------

    def _cc_lock(self, cc: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(cc, threading.Lock())

    @staticmethod
    def _check_cc(cc: str) -> str:
        if not isinstance(cc, str) or not _CC_ID.match(cc) or set(cc) <= {"."}:
            raise BoxPathError(f"command center id {cc!r} is not a valid box id")
        return cc

    def _require_owner(self, cc: str, account_id: str) -> None:
        owner = self._owner_of(cc)
        if owner is None or owner != account_id:
            raise BoxAuthError(
                f"account {account_id!r} does not own command center {cc!r}"
            )

    def _auth(self, handle: BoxHandle) -> str:
        cc = self._check_cc(handle.command_center_id)
        self._require_owner(cc, handle.account_id)
        current = self._state.epoch(cc)
        if handle.epoch != current:
            raise StaleHandle(
                f"handle for {cc!r} has epoch {handle.epoch}, current is {current}"
            )
        return cc

    # -- descriptors ---------------------------------------------------------------

    def _root_fd(self) -> int:
        from tinyassets.workspace_fs import open_dir_nofollow

        return open_dir_nofollow(self._root.resolve())

    def _box_fd(self, cc: str, *, create: bool = True) -> int:
        root = self._root_fd()
        try:
            try:
                return os.open(cc, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=root)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(cc, 0o700, dir_fd=root)
                except FileExistsError:
                    pass
                return os.open(cc, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=root)
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise BoxPathError(f"box directory for {cc!r} is a link") from exc
            raise
        finally:
            os.close(root)

    @staticmethod
    def _open_dir(parent_fd: int, name: str, path: str, *, create: bool) -> int:
        try:
            return os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=parent_fd)
        except FileNotFoundError:
            if not create:
                raise BoxNotFound(errno.ENOENT, f"no such box path: {path}") from None
            try:
                os.mkdir(name, 0o755, dir_fd=parent_fd)
            except FileExistsError:
                pass
            try:
                return os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=parent_fd)
            except OSError as exc:
                raise _path_error(exc, path) from exc
        except OSError as exc:
            raise _path_error(exc, path) from exc

    def _walk(self, box_fd: int, rel: str, path: str, *, create: bool) -> int:
        """Open the directory ``rel`` beneath ``box_fd`` (``""`` is the box root)."""
        current = os.dup(box_fd)
        try:
            for part in [p for p in rel.split("/") if p]:
                child = self._open_dir(current, part, path, create=create)
                os.close(current)
                current = child
        except BaseException:
            os.close(current)
            raise
        return current

    def _parent(self, box_fd: int, rel: str, path: str, *, create: bool) -> tuple[int, str]:
        if not rel:
            raise BoxPathError(f"{path!r} names the box root, not a file")
        head, _, leaf = rel.rpartition("/")
        return self._walk(box_fd, head, path, create=create), leaf

    @staticmethod
    def _open_regular(parent_fd: int, leaf: str, path: str) -> int:
        try:
            fd = os.open(leaf, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK, dir_fd=parent_fd)
        except OSError as exc:
            raise _path_error(exc, path) from exc
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            raise BoxPathError(f"{path!r} is not a regular file ({_kind(info.st_mode)})")
        return fd

    # -- binding and waking ----------------------------------------------------------

    def bind(self, command_center_id: str, *, account_id: str,
             turn_id: str | None = None) -> BoxHandle:
        cc = self._check_cc(command_center_id)
        self._require_owner(cc, account_id)
        return BoxHandle(cc, account_id, self._state.epoch(cc), turn_id)

    def committed_generation(self, handle: BoxHandle) -> int:
        return self._state.generation(self._auth(handle))

    def ensure_awake(self, handle: BoxHandle, *, reason: str) -> None:
        os.close(self._box_fd(self._auth(handle)))

    def suspend(self, handle: BoxHandle) -> None:
        self._auth(handle)  # no memory state to checkpoint in the local driver

    # -- operation-id bookkeeping -------------------------------------------------------

    def _begin(self, cc: str, op_id: str, kind: str, payload: object) -> dict | None:
        record = self._state.begin(cc, op_id, kind, op_digest(kind, payload))
        if record is None:
            return None
        if record["state"] == "unknown_after_restore":
            raise BoxError(
                f"{kind} {op_id!r} was in flight across a box-host restart; its outcome is "
                "unknown, so it is not re-run (hold and reconcile)"
            )
        if record["state"] == "running":
            raise BoxError(f"{kind} {op_id!r} is still in flight")
        return record["outcome"] or {}

    # -- files -----------------------------------------------------------------------------

    def read(self, handle: BoxHandle, path: str, *, offset: int = 0,
             max_bytes: int) -> FileRead:
        cc = self._auth(handle)
        rel = box_relpath(path)
        if max_bytes < 0 or offset < 0:
            raise ValueError("offset and max_bytes must be >= 0")
        box = self._box_fd(cc)
        try:
            parent, leaf = self._parent(box, rel, path, create=False)
            try:
                fd = self._open_regular(parent, leaf, path)
            finally:
                os.close(parent)
            try:
                size = os.fstat(fd).st_size
                os.lseek(fd, offset, os.SEEK_SET)
                data = os.read(fd, max_bytes) if max_bytes else b""
            finally:
                os.close(fd)
        finally:
            os.close(box)
        return FileRead(data=data, generation=self._state.generation(cc), size=size)

    def read_many(self, handle: BoxHandle, paths: Sequence[str], *,
                  max_total: int) -> Snapshot:
        cc = self._auth(handle)
        for _ in range(_READ_MANY_RETRIES):
            before = self._state.generation(cc)
            files: dict[str, bytes] = {}
            missing: list[str] = []
            total = 0
            for path in paths:
                try:
                    got = self.read(handle, path, max_bytes=max_total - total + 1)
                except BoxNotFound:
                    missing.append(path)
                    continue
                if got.size > max_total - total:
                    raise BoxError(f"read_many over its {max_total}-byte bound at {path!r}")
                files[path] = got.data
                total += got.size
            if self._state.generation(cc) == before:
                return Snapshot(files=files, missing=tuple(missing), generation=before)
        raise BoxError("the box kept changing during read_many; retry later")

    def download(self, handle: BoxHandle, path: str, *,
                 chunk_bytes: int = 64 * 1024) -> Iterator[bytes]:
        cc = self._auth(handle)
        rel = box_relpath(path)
        box = self._box_fd(cc)
        try:
            parent, leaf = self._parent(box, rel, path, create=False)
            try:
                fd = self._open_regular(parent, leaf, path)
            finally:
                os.close(parent)
        finally:
            os.close(box)

        def chunks() -> Iterator[bytes]:
            try:
                while True:
                    block = os.read(fd, chunk_bytes)
                    if not block:
                        return
                    yield block
            finally:
                os.close(fd)

        return chunks()

    def write(self, handle: BoxHandle, op_id: str, path: str, data: StreamIn, *,
              max_bytes: int, mode: WriteMode = WriteMode.REPLACE,
              expect_generation: int | None = None) -> FileWrite:
        cc = self._auth(handle)
        rel = box_relpath(path)
        mode = WriteMode(mode)
        if mode is WriteMode.CAS and expect_generation is None:
            raise ValueError("a cas write needs expect_generation")
        body = data if isinstance(data, (bytes, bytearray)) else b"".join(data)
        if len(body) > max_bytes:
            raise BoxError(f"write of {len(body)} bytes is over its {max_bytes}-byte bound")
        payload = {"path": rel, "sha": hashlib.sha256(body).hexdigest(), "mode": mode.value,
                   "expect": expect_generation}
        with self._cc_lock(cc):
            done = self._begin(cc, op_id, "write", payload)
            if done is not None:
                return FileWrite(path=path, size=done["size"], generation=done["generation"])
            try:
                written = self._write_now(cc, rel, path, bytes(body), mode, expect_generation)
            except BaseException:
                self._state.abandon(cc, op_id)
                raise
            generation = self._state.bump_generation(cc)
            self._state.finish(cc, op_id, {"size": written, "generation": generation})
        return FileWrite(path=path, size=written, generation=generation)

    def _write_now(self, cc: str, rel: str, path: str, body: bytes, mode: WriteMode,
                   expect_generation: int | None) -> int:
        if mode is WriteMode.CAS and self._state.generation(cc) != expect_generation:
            raise WriteConflict(f"box generation moved past {expect_generation}")
        box = self._box_fd(cc)
        try:
            parent, leaf = self._parent(box, rel, path, create=True)
        finally:
            os.close(box)
        try:
            try:
                existing = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                existing = None
            if existing is not None:
                if mode is WriteMode.CREATE:
                    raise WriteConflict(f"{path!r} already exists")
                if stat.S_ISDIR(existing.st_mode):
                    raise BoxPathError(f"{path!r} is a directory")
            tmp = _TMP_PREFIX + secrets.token_hex(8)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW, 0o644,
                         dir_fd=parent)
            try:
                with os.fdopen(fd, "wb", closefd=False) as fh:
                    fh.write(body)
                    fh.flush()
                    os.fsync(fd)
            except BaseException:
                os.close(fd)
                os.unlink(tmp, dir_fd=parent)
                raise
            os.close(fd)
            os.rename(tmp, leaf, src_dir_fd=parent, dst_dir_fd=parent)
            return len(body)
        finally:
            os.close(parent)

    def list(self, handle: BoxHandle, path: str, *, cursor: str | None = None,
             limit: int = 200) -> DirPage:
        cc = self._auth(handle)
        rel = box_relpath(path)
        if limit < 1:
            raise ValueError("limit must be >= 1")
        box = self._box_fd(cc)
        try:
            dfd = self._walk(box, rel, path, create=False)
        finally:
            os.close(box)
        try:
            names = sorted(n for n in os.listdir(dfd) if not n.startswith(_TMP_PREFIX))
            if cursor is not None:
                names = [n for n in names if n > cursor]
            page, rest = names[:limit], names[limit:]
            entries = []
            for name in page:
                info = os.stat(name, dir_fd=dfd, follow_symlinks=False)
                entries.append(DirEntry(name, _kind(info.st_mode), int(info.st_size)))
        finally:
            os.close(dfd)
        return DirPage(tuple(entries), page[-1] if rest else None)

    def stat(self, handle: BoxHandle, path: str) -> FileStat | None:
        cc = self._auth(handle)
        rel = box_relpath(path)
        box = self._box_fd(cc)
        try:
            if not rel:
                info = os.fstat(box)
            else:
                try:
                    parent, leaf = self._parent(box, rel, path, create=False)
                except BoxNotFound:
                    return None
                try:
                    info = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    return None
                finally:
                    os.close(parent)
        finally:
            os.close(box)
        return FileStat(path, _kind(info.st_mode), int(info.st_size), info.st_mtime)

    def remove(self, handle: BoxHandle, op_id: str, path: str) -> None:
        cc = self._auth(handle)
        rel = box_relpath(path)
        with self._cc_lock(cc):
            if self._begin(cc, op_id, "remove", {"path": rel}) is not None:
                return
            try:
                box = self._box_fd(cc)
                try:
                    parent, leaf = self._parent(box, rel, path, create=False)
                finally:
                    os.close(box)
                try:
                    removed = _remove_beneath(parent, leaf, path)
                finally:
                    os.close(parent)
            except BaseException:
                self._state.abandon(cc, op_id)
                raise
            generation = self._state.bump_generation(cc)
            self._state.finish(cc, op_id, {"removed": removed, "generation": generation})

    # -- execution ----------------------------------------------------------------------------

    def _exec_id(self, cc: str, op_id: str) -> str:
        return "x" + hashlib.sha256(f"{cc}\0{op_id}".encode()).hexdigest()[:31]

    def start_exec(self, handle: BoxHandle, op_id: str, argv: Sequence[str], *,
                   stdin: bytes = b"", env: Mapping[str, str] | None = None,
                   cwd: str = BOX_ROOT, limits: ExecLimits = ExecLimits()) -> str:
        cc = self._auth(handle)
        if not argv or not all(isinstance(a, str) and "\0" not in a for a in argv):
            raise ValueError("argv must be a non-empty list of strings without NULs")
        extra = dict(env or {})
        for key, value in extra.items():
            if not _ENV_KEY.match(key) or "\0" in str(value):
                raise ValueError(f"environment key {key!r} is not allowed")
        rel_cwd = box_relpath(cwd)
        payload = {"argv": list(argv), "stdin": hashlib.sha256(stdin).hexdigest(),
                   "env": extra, "cwd": rel_cwd,
                   "limits": [limits.wall_seconds, limits.output_bytes]}
        exec_id = self._exec_id(cc, op_id)
        record = self._state.begin(cc, op_id, "exec", op_digest("exec", payload))
        if record is not None:
            return exec_id  # done, running, or unknown: never run twice
        try:
            box = self._box_fd(cc)
            try:
                os.close(self._walk(box, rel_cwd, cwd, create=False))
            finally:
                os.close(box)
            box_dir = self._root.resolve() / cc
            workdir = box_dir / rel_cwd if rel_cwd else box_dir
            self._state.register_exec(cc, op_id, exec_id)
            self._state.update(cc, op_id, {"exec_id": exec_id,
                                           "output_bytes": limits.output_bytes})
            out_path = self._exec_dir / f"{exec_id}.out"
            out_fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            child_env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(box_dir),
                         "LANG": "C.UTF-8", **extra}
            try:
                proc = subprocess.Popen(
                    list(argv), cwd=workdir, env=child_env, stdin=subprocess.PIPE,
                    stdout=out_fd, stderr=subprocess.STDOUT, start_new_session=True,
                )
            finally:
                os.close(out_fd)
        except BaseException:
            self._state.abandon(cc, op_id)
            raise
        running = _Running(proc)
        self._running[exec_id] = running
        running.thread = threading.Thread(
            target=self._supervise, args=(cc, op_id, exec_id, running, stdin, limits, out_path),
            daemon=True, name=f"box-exec-{exec_id[:8]}",
        )
        running.thread.start()
        return exec_id

    def _supervise(self, cc: str, op_id: str, exec_id: str, running: _Running,
                   stdin: bytes, limits: ExecLimits, out_path: Path) -> None:
        proc = running.proc
        try:
            if proc.stdin is not None:
                try:
                    proc.stdin.write(stdin)
                    proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            started = time.monotonic()
            killed: str | None = None
            while proc.poll() is None:
                if running.cancel.is_set():
                    killed = "cancelled"
                elif time.monotonic() - started > limits.wall_seconds:
                    killed = "timeout"
                elif out_path.stat().st_size > limits.output_bytes:
                    killed = "output_limit"
                if killed:
                    _kill_group(proc)
                    break
                time.sleep(_POLL_S)
            code = proc.wait()
            if killed == "output_limit":
                with open(out_path, "r+b") as fh:
                    fh.truncate(limits.output_bytes)
            generation = self._state.bump_generation(cc)  # the command may have changed files
            self._state.finish(cc, op_id, {"exec_id": exec_id, "exit_code": code,
                                           "killed": killed, "generation": generation,
                                           "output_bytes": limits.output_bytes})
        finally:
            self._running.pop(exec_id, None)

    def stream(self, handle: BoxHandle, exec_id: str, *,
               from_offset: int = 0, timeout: float | None = None) -> Iterator[ExecEvent]:
        cc = self._auth(handle)
        if self._state.find_exec(cc, exec_id) is None:
            raise BoxNotFound(errno.ENOENT, f"no exec {exec_id!r} in this box")
        out_path = self._exec_dir / f"{exec_id}.out"
        deadline = None if timeout is None else time.monotonic() + timeout

        def events() -> Iterator[ExecEvent]:
            offset = from_offset
            while True:
                record = self._state.find_exec(cc, exec_id) or {}
                state = record.get("state")
                cap = int((record.get("outcome") or {}).get("output_bytes") or 0)
                if out_path.exists() and offset < cap:
                    with open(out_path, "rb") as fh:
                        fh.seek(offset)
                        block = fh.read(cap - offset)  # never past the output limit
                    if block:
                        yield ExecEvent("output", offset=offset, data=block)
                        offset += len(block)
                if state == "done":
                    outcome = record.get("outcome") or {}
                    yield ExecEvent("exit", offset=offset, exit_code=outcome.get("exit_code"),
                                    killed=outcome.get("killed"))
                    return
                if state == "unknown_after_restore":
                    yield ExecEvent("exit", offset=offset,
                                    killed=ExecState.UNKNOWN_AFTER_RESTORE.value)
                    return
                if deadline is not None and time.monotonic() > deadline:
                    return
                time.sleep(_POLL_S)

        return events()

    def cancel(self, handle: BoxHandle, exec_id: str) -> None:
        cc = self._auth(handle)
        if self._state.find_exec(cc, exec_id) is None:
            raise BoxNotFound(errno.ENOENT, f"no exec {exec_id!r} in this box")
        running = self._running.get(exec_id)
        if running is not None:
            running.cancel.set()

    def exec_status(self, handle: BoxHandle, op_id: str) -> ExecStatus:
        cc = self._auth(handle)
        record = self._state.lookup(cc, op_id)
        if record is None or record["kind"] != "exec":
            raise BoxNotFound(errno.ENOENT, f"no exec operation {op_id!r} in this box")
        outcome = record["outcome"] or {}
        state = {"running": ExecState.RUNNING, "done": ExecState.EXITED,
                 "unknown_after_restore": ExecState.UNKNOWN_AFTER_RESTORE}[record["state"]]
        return ExecStatus(op_id=op_id, exec_id=outcome.get("exec_id", self._exec_id(cc, op_id)),
                          state=state, exit_code=outcome.get("exit_code"),
                          killed=outcome.get("killed"))

    # -- whole box -------------------------------------------------------------------------------

    def usage(self, handle: BoxHandle) -> BoxUsage:
        cc = self._auth(handle)
        box = self._box_fd(cc)
        seen: set[tuple[int, int]] = set()
        total = 0
        try:
            for _dirpath, _dirs, files, dfd in os.fwalk(".", dir_fd=box, follow_symlinks=False):
                for name in files:
                    info = os.stat(name, dir_fd=dfd, follow_symlinks=False)
                    if stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) not in seen:
                        seen.add((info.st_dev, info.st_ino))
                        total += int(info.st_size)
        finally:
            os.close(box)
        return BoxUsage(logical_bytes=total, bound_bytes=None,
                        generation=self._state.generation(cc))

    def export(self, handle: BoxHandle, *, profile: ExportProfile) -> Iterator[bytes]:
        """A tar of the box's regular files and directories. Links and special files are left out.

        Profile scrubbing (the `share` manifest, harness §4.17) is applied by the export layer
        above the driver; the driver's job is a faithful, link-free copy.
        """
        cc = self._auth(handle)
        ExportProfile(profile)
        spool = tempfile.TemporaryFile(dir=self._state_dir)
        box = self._box_fd(cc)
        try:
            with tarfile.open(fileobj=spool, mode="w") as tar:
                for dirpath, dirs, files, dfd in os.fwalk(".", dir_fd=box, follow_symlinks=False):
                    base = dirpath[2:] if dirpath.startswith("./") else ""
                    for name in sorted(dirs):
                        info = os.stat(name, dir_fd=dfd, follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            entry = tarfile.TarInfo(f"{base}/{name}".lstrip("/"))
                            entry.type, entry.mode = tarfile.DIRTYPE, 0o755
                            tar.addfile(entry)
                    for name in sorted(files):
                        if name.startswith(_TMP_PREFIX):
                            continue
                        try:
                            fd = os.open(name, os.O_RDONLY | _O_NOFOLLOW | _O_NONBLOCK, dir_fd=dfd)
                        except OSError:
                            continue  # a link (ELOOP) or vanished: not exported
                        try:
                            info = os.fstat(fd)
                            if not stat.S_ISREG(info.st_mode):
                                continue
                            entry = tarfile.TarInfo(f"{base}/{name}".lstrip("/"))
                            entry.size, entry.mode = info.st_size, 0o644
                            entry.mtime = int(info.st_mtime)
                            with os.fdopen(os.dup(fd), "rb") as fh:
                                tar.addfile(entry, fh)
                        finally:
                            os.close(fd)
        finally:
            os.close(box)
        spool.seek(0)

        def chunks() -> Iterator[bytes]:
            with spool:
                while True:
                    block = spool.read(64 * 1024)
                    if not block:
                        return
                    yield block

        return chunks()

    def import_bundle(self, handle: BoxHandle, op_id: str, chunks: Iterable[bytes], *,
                      profile: ExportProfile) -> ImportReport:
        cc = self._auth(handle)
        ExportProfile(profile)
        spool = tempfile.TemporaryFile(dir=self._state_dir)
        digest = hashlib.sha256()
        for block in chunks:
            digest.update(block)
            spool.write(block)
        spool.seek(0)
        with self._cc_lock(cc):
            done = self._begin(cc, op_id, "import", {"sha": digest.hexdigest(),
                                                     "profile": ExportProfile(profile).value})
            if done is not None:
                return ImportReport(done["files"], done["bytes"], tuple(done["refused"]))
            files = size = 0
            refused: list[str] = []
            try:
                with spool, tarfile.open(fileobj=spool, mode="r:") as tar:
                    for member in tar:
                        name = member.name[2:] if member.name.startswith("./") else member.name
                        try:
                            rel = box_relpath(f"{BOX_ROOT}/{name}")
                            if not rel:
                                raise BoxPathError(f"{member.name!r} names the box root")
                        except BoxPathError:
                            refused.append(member.name)
                            continue
                        if member.isdir():
                            box = self._box_fd(cc)
                            try:
                                os.close(self._walk(box, rel, member.name, create=True))
                            finally:
                                os.close(box)
                        elif member.isreg():
                            src = tar.extractfile(member)
                            body = src.read() if src is not None else b""
                            self._write_now(cc, rel, member.name, body, WriteMode.REPLACE, None)
                            files += 1
                            size += len(body)
                        else:
                            refused.append(member.name)  # links, devices, FIFOs
            except BaseException:
                self._state.abandon(cc, op_id)
                raise
            self._state.bump_generation(cc)
            self._state.finish(cc, op_id, {"files": files, "bytes": size, "refused": refused})
        return ImportReport(files, size, tuple(refused))

    def destroy(self, handle: BoxHandle, op_id: str) -> DestroyReceipt:
        cc = self._auth(handle)
        with self._cc_lock(cc):
            done = self._begin(cc, op_id, "destroy", {})
            if done is not None:
                return DestroyReceipt(cc, op_id, done["files_removed"], done["new_epoch"])
            for exec_id, running in list(self._running.items()):
                if (self._state.find_exec(cc, exec_id) or {}).get("op_id"):
                    running.cancel.set()
            root = self._root_fd()
            try:
                try:
                    removed = _remove_beneath(root, cc, cc)
                except BoxNotFound:
                    removed = 0
            finally:
                os.close(root)
            new_epoch = self._state.bump_epoch(cc)
            self._state.finish(cc, op_id, {"files_removed": removed, "new_epoch": new_epoch})
        return DestroyReceipt(cc, op_id, removed, new_epoch)


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _remove_beneath(parent_fd: int, name: str, path: str, depth: int = 0) -> int:
    """Remove ``name`` beneath ``parent_fd`` without following any link. Returns files removed."""
    if depth > 256:
        raise BoxError(f"{path!r}: directory tree too deep to remove")
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise _path_error(exc, path) from exc
    if not stat.S_ISDIR(info.st_mode):
        os.unlink(name, dir_fd=parent_fd)  # a link is removed itself, never its target
        return 1
    dfd = os.open(name, os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW, dir_fd=parent_fd)
    removed = 0
    try:
        for child in os.listdir(dfd):
            removed += _remove_beneath(dfd, child, f"{path}/{child}", depth + 1)
    finally:
        os.close(dfd)
    os.rmdir(name, dir_fd=parent_fd)
    return removed

