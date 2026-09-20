"""Nonexpiring, run-keyed worker ownership for all managed execution origins.

No file/admission row is required. Recovery must acquire and retain this guard,
not inspect a process-local Future or probe then act. Ordering is execution
guard -> family fence -> short DB transactions. A sidecar is NEVER unlinked;
PID/timestamp/TTL is never permission to steal it. Trusted daemon data only.
"""

from __future__ import annotations

import hashlib
import os
import stat
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path

from tinyassets.runs import runs_db_path
from tinyassets.storage.delivery_lock import _try_os_lock

_mutex_guard = threading.Lock()
_mutexes = weakref.WeakValueDictionary()
_active = set()


def _require_database(conn, database_path):
    database = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
    if not database or Path(database).resolve() != database_path:
        raise RuntimeError("run execution guard belongs to another database")


class RunExecutionUse:
    """Owner-issued, same-process scoped work; never start/terminal authority."""

    def __init__(self, guard):
        self._guard = guard
        self.database_path = guard.database_path
        self.run_id = guard.run_id

    def __reduce__(self):
        raise TypeError("run execution use is not serializable")

    def _identity(self, conn):
        guard = self._guard
        # Refuse inherited copies BEFORE touching possibly fork-held locks.
        if guard._pid != os.getpid() or guard._use is not self:
            raise RuntimeError("run execution use was not issued to this process")
        _require_database(conn, self.database_path)

    @contextmanager
    def hold(self, conn):
        self._identity(conn)
        guard = self._guard
        token = object()
        with guard._condition:
            if guard not in _active or guard._closing:
                raise RuntimeError("run execution use is retired or closing")
            guard._pins[token] = threading.get_ident()
        try:
            yield self
        finally:
            with guard._condition:
                del guard._pins[token]
                guard._condition.notify_all()

    def require_in_use(self, conn):
        self._identity(conn)
        guard = self._guard
        with guard._condition:
            if guard not in _active or threading.get_ident() not in guard._pins.values():
                raise RuntimeError("run execution use is not held by this operation")


class RunExecutionGuard:
    """Internal acquisition receipt, valid in its process/thread/context only."""

    def __init__(self, database_path, run_id):
        self.database_path = database_path
        self.run_id = run_id
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._condition = threading.Condition()
        self._closing = False
        self._pins = {}
        self._use = None

    def require_held(self, conn):
        if self not in _active or self._pid != os.getpid() or self._thread != threading.get_ident():
            raise RuntimeError("run execution guard is not held by this worker")
        _require_database(conn, self.database_path)

    def issue_use(self, conn):
        self.require_held(conn)
        with self._condition:
            if self._closing:
                raise RuntimeError("run execution owner is closing")
            if self._use is None:
                self._use = RunExecutionUse(self)
            return self._use

    def _retire_uses(self):
        """Retain this same OS guard until actual operation scopes have ended.

        Even an interrupted wait cannot publish availability while a callback
        can still launch. Defer that exception until pins drain and normal
        descriptor/mutex cleanup completes. Stop never waits on this condition.
        """
        interrupted = None
        while True:
            try:
                with self._condition:
                    self._closing = True
                    while self._pins:
                        self._condition.wait()
                    _active.discard(self)
                    return interrupted
            except BaseException as exc:
                if interrupted is None:
                    interrupted = exc


@contextmanager
def try_run_execution_lock(base_path, *, run_id):
    """Yield one current guard or None on contention; no waiting or TTL takeover."""
    if type(run_id) is not str or not run_id or len(run_id) > 256:
        raise ValueError("invalid run identity")
    database_path = runs_db_path(base_path).resolve()
    key = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    path = database_path.parent / ".run-execution-locks" / f"{key}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _mutex_guard:
        mutex = _mutexes.setdefault(str(path), threading.Lock())
    if not mutex.acquire(blocking=False):
        yield None
        return
    fd = None
    guard = None
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.set_inheritable(fd, False)
        opened = os.fstat(fd)
        current = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or getattr(current, "st_file_attributes", 0) & 0x400
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise RuntimeError("run execution sidecar is unsafe")
        if _try_os_lock(fd):
            guard = RunExecutionGuard(database_path, run_id)
            _active.add(guard)
        yield guard
    finally:
        interrupted = None
        if guard is not None:
            interrupted = guard._retire_uses()
        try:
            if fd is not None:
                os.close(fd)
        finally:
            mutex.release()
        if interrupted is not None:
            raise interrupted
