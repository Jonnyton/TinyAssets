"""Publisher/collector exclusion uses the same kernel lock through final commit."""

import multiprocessing
import os
import sqlite3

import pytest

from tinyassets import runs
from tinyassets.storage.run_file_lock import FileOperationGuard, try_file_operation_lock


def _contender(base, output):
    with try_file_operation_lock(base, operation_id="operation") as guard:
        output.put(guard is not None)


def _crash(base):
    context = try_file_operation_lock(base, operation_id="operation")
    guard = context.__enter__()
    os._exit(0 if guard is not None else 1)


def test_publisher_excludes_independent_collector_until_commit(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    output = ctx.Queue()
    with sqlite3.connect(runs.runs_db_path(tmp_path)) as conn:
        with try_file_operation_lock(tmp_path, operation_id="operation") as guard:
            guard.require_held(conn)
            with try_file_operation_lock(tmp_path, operation_id="operation") as duplicate:
                assert duplicate is None
            child = ctx.Process(target=_contender, args=(tmp_path, output))
            child.start()
            child.join(15)
            assert child.exitcode == 0
            assert output.get(timeout=2) is False
            with pytest.raises(RuntimeError):
                FileOperationGuard(runs.runs_db_path(tmp_path), "operation").require_held(conn)
        with pytest.raises(RuntimeError):
            guard.require_held(conn)
    output.close()


def test_crash_releases_without_replacing_inventory_sidecar(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    child = ctx.Process(target=_crash, args=(tmp_path,))
    child.start()
    child.join(15)
    assert child.exitcode == 0
    path = next((tmp_path / ".run-file-operation-locks").glob("*.lock"))
    before = path.stat()
    with try_file_operation_lock(tmp_path, operation_id="operation") as guard:
        assert guard is not None
    after = path.stat()
    assert (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
