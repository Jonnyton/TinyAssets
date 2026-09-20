"""Nonexpiring exclusion of one immutable file operation, including its cleanup.

Uses the same OS primitive as run/delivery ownership, not a family lock manager.
No TTL takeover or unlink. Does not grant owner, run, workspace or byte authority.
Order: maintenance barrier -> operation guard -> short authority/store writers.
No database writer is held for copying or physical cleanup.
"""

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


class FileOperationGuard:
    def __init__(self, database, operation_id):
        self.database = database
        self.operation_id = operation_id
        self._pid = os.getpid()
        self._thread = threading.get_ident()

    def require_held(self, conn):
        if self not in _active or self._pid != os.getpid() or self._thread != threading.get_ident():
            raise RuntimeError("file operation guard is not held")
        database = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
        if not database or Path(database).resolve() != self.database:
            raise RuntimeError("file operation guard belongs to another database")


@contextmanager
def try_file_operation_lock(base_path, *, operation_id):
    if type(operation_id) is not str or not operation_id or len(operation_id) > 256:
        raise ValueError("invalid file operation identity")
    database = runs_db_path(base_path).resolve()
    name = hashlib.sha256(operation_id.encode("utf-8")).hexdigest() + ".lock"
    path = database.parent / ".run-file-operation-locks" / name
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
        opened, current = os.fstat(fd), path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(current.st_mode)
            or getattr(current, "st_file_attributes", 0) & 0x400
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise RuntimeError("file operation sidecar is unsafe")
        if _try_os_lock(fd):
            guard = FileOperationGuard(database, operation_id)
            _active.add(guard)
        yield guard
    finally:
        if guard is not None:
            _active.discard(guard)
        try:
            if fd is not None:
                os.close(fd)
        finally:
            mutex.release()
