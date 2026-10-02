"""Local-driver specifics that the portable contract suite does not cover.

These reach the local driver's own construction options (busy wait) or simulate
a box-host restart with a second driver instance over the same state. The
behaviour is part of the contract; the way it is provoked here is local-only.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

from tinyassets.boxes import (
    BoxBusy,
    BoxError,
    BoxNotFound,
    ExecLimits,
    ExecState,
    OpIdReuse,
    WriteConflict,
    WriteMode,
)

pytestmark = pytest.mark.skipif(
    os.name != "posix" or sys.platform == "win32" or not Path("/proc/self/fd").is_dir(),
    reason="the local box driver needs Linux",
)

OWNERS = {"cc-a": "acct-a", "cc-b": "acct-b"}


def _local(tmp_path: Path, **kw):
    from tinyassets.boxes.local import LocalBoxProvider

    return LocalBoxProvider(boxes_root=tmp_path / "boxes", state_dir=tmp_path / "state",
                            owner_of=OWNERS.get, allow_unisolated=True, **kw)


def test_unacknowledged_construction_is_refused(tmp_path):
    from tinyassets.boxes.local import LocalBoxProvider

    with pytest.raises(BoxError):
        LocalBoxProvider(boxes_root=tmp_path / "b", state_dir=tmp_path / "s",
                         owner_of=OWNERS.get)
    assert not (tmp_path / "b").exists()


def test_an_old_host_cannot_overwrite_unknown_with_done(tmp_path):
    first = _local(tmp_path)
    handle = first.bind("cc-a", account_id="acct-a")
    exec_id = first.start_exec(handle, "e1", ["sleep", "1"], limits=ExecLimits(wall_seconds=30))
    second = _local(tmp_path)  # a restart while the old host's supervisor is still alive
    assert second.exec_status(handle, "e1").state is ExecState.UNKNOWN_AFTER_RESTORE
    time.sleep(2.0)  # the old supervisor finishes and tries to record "done"
    status = second.exec_status(handle, "e1")
    assert status.state is ExecState.UNKNOWN_AFTER_RESTORE
    # a retry is never a second run, and the op id stays bound to the exec
    assert second.start_exec(handle, "e1", ["sleep", "1"],
                             limits=ExecLimits(wall_seconds=30)) == exec_id
    events = list(second.stream(handle, exec_id, timeout=2))
    assert events[-1].killed == ExecState.UNKNOWN_AFTER_RESTORE.value
    with pytest.raises(OpIdReuse):
        second.write(handle, "e1", "/cc/x", b"x", max_bytes=10)


def test_read_many_refuses_while_an_exec_may_be_changing_files(tmp_path):
    provider = _local(tmp_path, busy_wait_s=0.3)
    handle = provider.bind("cc-a", account_id="acct-a")
    provider.write(handle, "w1", "/cc/soul.md", b"S", max_bytes=10)
    exec_id = provider.start_exec(handle, "e1", ["sleep", "5"],
                                  limits=ExecLimits(wall_seconds=30))
    with pytest.raises(BoxBusy):
        provider.read_many(handle, ["/cc/soul.md"], max_total=10)
    provider.cancel(handle, exec_id)
    list(provider.stream(handle, exec_id, timeout=10))
    assert provider.read_many(handle, ["/cc/soul.md"], max_total=10).files == {
        "/cc/soul.md": b"S"}


def test_cas_refuses_while_an_exec_is_running(tmp_path):
    provider = _local(tmp_path)
    handle = provider.bind("cc-a", account_id="acct-a")
    w = provider.write(handle, "w1", "/cc/a.txt", b"1", max_bytes=10)
    exec_id = provider.start_exec(handle, "e1", ["sleep", "5"],
                                  limits=ExecLimits(wall_seconds=30))
    with pytest.raises(WriteConflict):
        provider.write(handle, "w2", "/cc/a.txt", b"2", max_bytes=10, mode=WriteMode.CAS,
                       expect_generation=w.generation)
    provider.cancel(handle, exec_id)
    list(provider.stream(handle, exec_id, timeout=10))


def test_a_launch_refused_before_running_can_be_retried(tmp_path):
    provider = _local(tmp_path)
    handle = provider.bind("cc-a", account_id="acct-a")
    for _ in range(2):  # the second attempt meets the same refusal, not a leftover spool
        with pytest.raises(BoxNotFound):
            provider.start_exec(handle, "e1", ["true"], cwd="/cc/missing")
    provider.write(handle, "w1", "/cc/missing/.keep", b"", max_bytes=1)
    exec_id = provider.start_exec(handle, "e1", ["true"], cwd="/cc/missing")
    assert list(provider.stream(handle, exec_id, timeout=10))[-1].exit_code == 0


def test_a_missing_program_is_an_exec_result_not_a_refusal(tmp_path):
    provider = _local(tmp_path)
    handle = provider.bind("cc-a", account_id="acct-a")
    exec_id = provider.start_exec(handle, "e1", ["/no/such/program"])
    assert list(provider.stream(handle, exec_id, timeout=10))[-1].exit_code == 127


def test_streaming_write_input_is_bounded_as_it_arrives(tmp_path):
    provider = _local(tmp_path)
    handle = provider.bind("cc-a", account_id="acct-a")

    def endless():
        while True:
            yield b"x" * 1024

    with pytest.raises(BoxError):
        provider.write(handle, "w1", "/cc/a.bin", endless(), max_bytes=4096)
    assert provider.stat(handle, "/cc/a.bin") is None


def test_an_unconsumed_download_does_not_leak_its_descriptor(tmp_path):
    provider = _local(tmp_path)
    handle = provider.bind("cc-a", account_id="acct-a")
    provider.write(handle, "w1", "/cc/a.bin", b"x" * 10, max_bytes=100)
    before = len(os.listdir("/proc/self/fd"))
    for _ in range(50):
        provider.download(handle, "/cc/a.bin").close()
    assert len(os.listdir("/proc/self/fd")) <= before + 1
