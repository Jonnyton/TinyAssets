"""Non-expiring ownership of one delivery attempt, held through execution.

Server-owned sidecars are never unlinked: replacing their inode could let two
workers hold different locks for the same attempt. A timestamp, PID or missing
Future is not evidence of death. Only acquiring this OS lock establishes that
the previous cooperating worker no longer owns the attempt.
"""

from __future__ import annotations

import errno
import os
import re
import sys
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path

from tinyassets.runs import runs_db_path

_mutex_guard = threading.Lock()
_mutexes = weakref.WeakValueDictionary()


def _try_os_lock(fd):
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        contention = {errno.EAGAIN, errno.EWOULDBLOCK}
        if sys.platform == "win32":
            contention.update({errno.EACCES, errno.EDEADLK})
        if exc.errno in contention:
            return False
        raise  # I/O failure is not permission to execute or recover.
    return True


class AttemptLock:
    """Internal guard; valid only in the acquiring thread and context lifetime."""

    def __init__(self, database_path, delivery_id, attempt):
        self.database_path = database_path
        self.delivery_id = delivery_id
        self.attempt = attempt
        self._thread = threading.get_ident()
        self._held = True

    def require_held(self, conn):
        if not self._held or self._thread != threading.get_ident():
            raise RuntimeError("delivery attempt lock is not held by this worker")
        database = next(row[2] for row in conn.execute("PRAGMA database_list") if row[1] == "main")
        if Path(database).resolve() != self.database_path:
            raise RuntimeError("delivery attempt lock belongs to another database")


@contextmanager
def try_attempt_lock(base_path, *, delivery_id, attempt):
    """Yield a held guard, or None on contention; never wait or steal a lock.

    Must be acquired inside the worker, before its database transaction, and
    retained until provider/graph settlement and terminal persistence finish.
    Only server-generated delivery IDs enter a filename. The data directory is
    trusted runtime storage, not a user workspace or upload path.
    """
    if not isinstance(delivery_id, str) or re.fullmatch(r"[0-9a-f]{32}", delivery_id) is None:
        raise ValueError("invalid delivery identity")
    if type(attempt) is not int or attempt <= 0:
        raise ValueError("invalid delivery attempt")
    database_path = runs_db_path(base_path).resolve()
    lock_path = database_path.parent / ".delivery-locks" / f"{delivery_id}-{attempt}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _mutex_guard:
        mutex = _mutexes.setdefault(str(lock_path), threading.Lock())
    if not mutex.acquire(blocking=False):
        yield None
        return
    fd = None
    guard = None
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        os.set_inheritable(fd, False)
        if _try_os_lock(fd):
            guard = AttemptLock(database_path, delivery_id, attempt)
        yield guard
    finally:
        if guard is not None:
            guard._held = False
        try:
            if fd is not None:
                os.close(fd)  # Kernel releases the lock, including after process death.
        finally:
            mutex.release()
