"""What only the gVisor driver promises: the whole box is the unit of containment.

The local driver tracks process groups and leaves two crash gaps
(box-provider-foundation D7). Here every exec runs inside the box's own sandbox,
so ending the sandbox ends every process in it, however it was started. These
tests run where rootful runsc is available (opt in with
``TINYASSETS_BOX_GVISOR_ROOTFS``, see tests/test_box_provider_contract.py), and
skip everywhere else, with the reason.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tinyassets.boxes import BoxDeadline, ExecLimits, ExecState

pytestmark = pytest.mark.skipif(
    not os.environ.get("TINYASSETS_BOX_GVISOR_ROOTFS") or os.name != "posix"
    or os.geteuid() != 0,
    reason="gVisor driver: needs root and TINYASSETS_BOX_GVISOR_ROOTFS",
)

OWNERS = {"cc-a": "acct-a", "cc-b": "acct-b"}
REPO = Path(__file__).resolve().parents[1]


def _flags() -> tuple[str, ...]:
    return tuple(os.environ.get("TINYASSETS_BOX_RUNSC_FLAGS", "").split())


def _host(tmp_path: Path, **kw):
    from tinyassets.boxes.gvisor import GVisorBoxProvider

    return GVisorBoxProvider(
        boxes_root=tmp_path / "boxes", state_dir=tmp_path / "state", owner_of=OWNERS.get,
        rootfs=Path(os.environ["TINYASSETS_BOX_GVISOR_ROOTFS"]), package_dir=REPO,
        runsc=os.environ.get("TINYASSETS_BOX_RUNSC", "runsc"),
        python=os.environ.get("TINYASSETS_BOX_PYTHON", "/usr/bin/python3"),
        extra_runsc_flags=_flags(), **kw)


def _sandbox_pids(tmp_path: Path) -> list[int]:
    """Host processes belonging to this test's sandboxes (the sentry and the gofer)."""
    marker = str(tmp_path / "state" / "runsc").encode()
    pids = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit() and int(entry.name) != os.getpid():
            try:
                if marker in (entry / "cmdline").read_bytes():
                    pids.append(int(entry.name))
            except OSError:
                pass
    return pids


def _gone(tmp_path: Path, within: float = 5.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        if not _sandbox_pids(tmp_path):
            return True
        time.sleep(0.1)
    return False


def _drain(host, handle, exec_id, timeout=30.0):
    out, done = b"", None
    for ev in host.stream(handle, exec_id, timeout=timeout):
        if ev.kind == "output":
            out += ev.data
        else:
            done = ev
    return out, done


def test_destroy_ends_a_detached_background_process_with_the_box(tmp_path):
    host = _host(tmp_path)
    try:
        h = host.bind("cc-a", account_id="acct-a")
        # The leader exits at once and leaves a child in its own session: the local
        # driver's leaderless-group gap. In a box it is just another process in the box.
        e = host.start_exec(h, "e1", ["sh", "-c", "setsid sleep 300 >/dev/null 2>&1 & echo ok"])
        _out, done = _drain(host, h, e)
        assert done.exit_code == 0
        assert _sandbox_pids(tmp_path), "the box's sandbox should be running"
        host.destroy(h, "d1")
        assert _gone(tmp_path), "destroy must end the sandbox, and everything in it"
    finally:
        host.close()


_CRASHING_HOST = """
import os, sys
from pathlib import Path
from tinyassets.boxes import ExecLimits
from tests.test_box_gvisor_driver import _host
host = _host(Path(sys.argv[1]))
h = host.bind("cc-a", account_id="acct-a")
host.start_exec(h, "e1", ["sh", "-c", "echo started > marker; sleep 300"],
                limits=ExecLimits(wall_seconds=600))
time = __import__("time")
time.sleep(1)
os._exit(0)  # a crash: the box host dies without a clean shutdown
"""


def test_a_new_host_kills_every_box_the_crashed_host_left(tmp_path):
    subprocess.run([sys.executable, "-c", _CRASHING_HOST, str(tmp_path)], check=True,
                   cwd=REPO, env={**os.environ, "PYTHONPATH": str(REPO)}, timeout=120)
    assert _sandbox_pids(tmp_path), "the crashed host's box should still be running"
    host = _host(tmp_path)  # the restart
    try:
        assert _gone(tmp_path), "a new host must end every box a previous host left"
        h = host.bind("cc-a", account_id="acct-a")
        assert host.exec_status(h, "e1").state is ExecState.UNKNOWN_AFTER_RESTORE
        assert host.read(h, "/cc/marker", max_bytes=20).data == b"started\n"
    finally:
        host.close()


def test_a_box_has_no_network(tmp_path):
    host = _host(tmp_path)
    try:
        h = host.bind("cc-a", account_id="acct-a")
        probe = ("import socket\n"
                 "try:\n"
                 "    socket.create_connection(('1.1.1.1', 443), timeout=3)\n"
                 "    print('CONNECTED')\n"
                 "except OSError as exc:\n"
                 "    print('refused', exc)\n")
        e = host.start_exec(h, "e1", ["python3", "-c", probe])
        out, _done = _drain(host, h, e)
        assert b"CONNECTED" not in out and b"refused" in out
    finally:
        host.close()


def test_each_box_writes_as_its_own_host_uid(tmp_path):
    host = _host(tmp_path)
    try:
        for cc, acct in OWNERS.items():
            host.write(host.bind(cc, account_id=acct), "w1", "/cc/f.txt", b"x", max_bytes=10)
        a = (tmp_path / "boxes" / "cc-a" / "data" / "f.txt").stat().st_uid
        b = (tmp_path / "boxes" / "cc-b" / "data" / "f.txt").stat().st_uid
        assert a != b and a != 0 and b != 0
    finally:
        host.close()


@pytest.mark.skipif("--ignore-cgroups" in _flags(), reason="cgroups are disabled here")
def test_a_box_cannot_use_more_memory_than_its_limit(tmp_path):
    host = _host(tmp_path, memory_bytes=256 << 20)
    try:
        h = host.bind("cc-a", account_id="acct-a")
        hog = ("b = []\n"
               "for _ in range(64):\n"
               "    b.append(bytearray(b'x') * (16 << 20))\n"  # touched, so resident
               "print('ALLOCATED', len(b) * 16, 'MiB')\n")
        e = host.start_exec(h, "e1", ["python3", "-c", hog], limits=ExecLimits(wall_seconds=60))
        out, _done = _drain(host, h, e, timeout=60)
        assert b"ALLOCATED" not in out, "a 1 GiB allocation in a 256 MiB box must fail"
    finally:
        host.close()


def test_a_hung_box_ends_the_box_not_the_host(tmp_path):
    host = _host(tmp_path)
    try:
        h = host.bind("cc-a", account_id="acct-a")
        host.write(h, "w0", "/cc/keep.txt", b"kept", max_bytes=10)
        # Freeze boxd itself (it is pid 1 in the box), so a forwarded write cannot answer.
        e = host.start_exec(h, "e1", ["sh", "-c", "kill -STOP 1"])
        _drain(host, h, e, timeout=5)
        with host.bounded(2), pytest.raises(BoxDeadline):
            host.write(h, "w1", "/cc/x.txt", b"x", max_bytes=10)
        assert _gone(tmp_path), "a call with an unknown outcome must end the box"
        # the next call starts a fresh box; the files are still there
        assert host.read(h, "/cc/keep.txt", max_bytes=10).data == b"kept"
    finally:
        host.close()
