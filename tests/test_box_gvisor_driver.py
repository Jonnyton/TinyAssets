"""What only the gVisor driver promises: the whole box is the unit of containment.

The local driver tracks process groups and leaves two crash gaps
(box-provider-foundation D7). Here every exec runs inside the box's own sandbox,
so ending the sandbox ends every process in it, however it was started. Sandbox
tests run where rootful runsc is available (opt in with
``TINYASSETS_BOX_GVISOR_ROOTFS``, see tests/test_box_provider_contract.py), and
skip everywhere else, with the reason. Host-side unit tests also run without runsc.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tinyassets import rpc_frames
from tinyassets.boxes import BoxDeadline, BoxError, ExecLimits, ExecState
from tinyassets.boxes.gvisor import GVisorBoxProvider, _BoxKilled

needs_runsc = pytest.mark.skipif(
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


@needs_runsc
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


@needs_runsc
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


@needs_runsc
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


@needs_runsc
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
@needs_runsc
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


@needs_runsc
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


@needs_runsc
def test_idle_fence_ends_a_detached_background_process_with_the_box(tmp_path):
    host = _host(tmp_path)
    try:
        h = host.bind("cc-a", account_id="acct-a")
        e = host.start_exec(h, "e1", ["sh", "-c", "setsid sleep 300 >/dev/null 2>&1 & echo ok"])
        _out, done = _drain(host, h, e)
        assert done.exit_code == 0
        assert _sandbox_pids(tmp_path)
        assert host.try_fence_idle("cc-a", owner_generation=1)
        assert _gone(tmp_path), "a successful fence must end every process in the box"
    finally:
        host.close()


def _socketpair():
    try:
        return socket.socketpair()
    except (AttributeError, OSError):
        pytest.skip("socketpair is unavailable")


def test_exchange_deadline_bounds_a_trickling_frame(monkeypatch):
    client, peer = _socketpair()
    host = object.__new__(GVisorBoxProvider)
    monkeypatch.setattr(host, "_connect", lambda cc, deadline: client)
    stop = threading.Event()

    def trickle():
        with peer:
            try:
                rpc_frames.read_frame_blocking(peer)
                header = rpc_frames.data(1, b"x" * 1000)[0][:rpc_frames.HEADER_BYTES]
                peer.sendall(header)
                while not stop.wait(0.1):
                    peer.sendall(b"x")
            except OSError:
                pass

    sender = threading.Thread(target=trickle, daemon=True)
    sender.start()
    deadline = time.monotonic() + 0.4
    # Rescue a broken implementation so the red check cannot hang indefinitely.
    rescue = threading.Timer(2.0, stop.set)
    rescue.start()
    try:
        with pytest.raises(BoxDeadline):
            list(host._exchange("cc-a", "read", {}, deadline=deadline))
        assert time.monotonic() < deadline + 1
    finally:
        stop.set()
        rescue.cancel()
        sender.join(timeout=3)


def test_exchange_deadline_bounds_a_box_that_reads_slowly(monkeypatch):
    """The SEND side is bounded by the same deadline, re-armed per frame.

    A box that DRAINS slowly is the case a single socket timeout cannot catch:
    every individual ``sendall`` makes progress and so never times out, while
    the request as a whole runs past its deadline (``sendall`` applies the
    timeout to each underlying send, not to the total). Re-arming from what is
    left of the budget ends it -- and without a second thread shutting the
    socket down, which can fire after the connection is closed and land on
    whatever reused its descriptor.
    """
    client, peer = _socketpair()
    try:
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    except OSError:
        pytest.skip("the send buffer cannot be shrunk here")
    stop = threading.Event()

    def drain():
        with peer:
            try:
                while not stop.wait(0.05):
                    peer.recv(256)
            except OSError:
                pass

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    host = object.__new__(GVisorBoxProvider)
    monkeypatch.setattr(host, "_connect", lambda cc, deadline: client)
    deadline = time.monotonic() + 0.4
    try:
        with pytest.raises(BoxDeadline):
            list(host._exchange("cc-a", "write", {}, payload=b"x" * (8 << 20),
                                deadline=deadline))
        assert time.monotonic() < deadline + 2
    finally:
        stop.set()
        reader.join(timeout=3)
        client.close()


def test_kill_box_keeps_live_box_when_teardown_fails(monkeypatch):
    host = object.__new__(GVisorBoxProvider)
    host._runsc = ["runsc"]
    host._live = {"cc-a"}
    bumped = []
    host._state = SimpleNamespace(bump_generation=bumped.append)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, '{"status": "running"}', "")

    monkeypatch.setattr("tinyassets.boxes.gvisor.subprocess.run", run)
    with pytest.raises(BoxError, match="still exists"):
        host._kill_box("cc-a")
    assert "cc-a" in host._live
    assert not bumped
    assert sum("delete" in argv for argv in calls) == 2
    assert sum("state" in argv for argv in calls) == 2


@pytest.mark.parametrize("returncode, output", [(1, "[]"), (0, "broken"), (0, "{}")])
def test_kill_all_boxes_rejects_invalid_listing(monkeypatch, returncode, output):
    host = object.__new__(GVisorBoxProvider)
    host._runsc = ["runsc"]
    monkeypatch.setattr("tinyassets.boxes.gvisor.subprocess.run",
                        lambda argv, **kw: subprocess.CompletedProcess(
                            argv, returncode, output, ""))
    with pytest.raises(BoxError):
        host._kill_all_boxes()


@pytest.mark.parametrize("output", ["null\n", "[]\n"])
def test_kill_all_boxes_accepts_empty_listing(monkeypatch, output):
    host = object.__new__(GVisorBoxProvider)
    host._runsc = ["runsc"]
    monkeypatch.setattr("tinyassets.boxes.gvisor.subprocess.run",
                        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, output, ""))
    host._kill_all_boxes()


@pytest.fixture
def host_without_runsc(tmp_path, monkeypatch):
    if os.name != "posix":
        pytest.skip("box host state needs POSIX locking")
    from tinyassets.boxes.state import BoxHostState

    host = object.__new__(GVisorBoxProvider)
    host._state = BoxHostState(tmp_path / "boxhost.db")
    host._tls = threading.local()
    host._call_timeout_s = 5
    host._locks = {}
    host._locks_guard = threading.Lock()
    host._owner_of = OWNERS.get
    host._closing = False
    host._live = {"cc-a"}
    host._disk_bound = None
    monkeypatch.setattr(host, "_ensure_box", lambda cc: None)
    yield host
    host._state.close()


def test_gvisor_write_replay_rejects_changed_cas_arguments(host_without_runsc, monkeypatch):
    from tests.test_box_provider_contract import test_write_replay_rejects_changed_cas_arguments

    monkeypatch.setattr(host_without_runsc, "_rpc",
                        lambda *args, **kw: {"size": 3, "generation": 1})
    test_write_replay_rejects_changed_cas_arguments(host_without_runsc)


@pytest.mark.parametrize("method, kwargs, value", [
    ("read", {"path": "/cc/a", "max_bytes": 10}, {"data": b"a", "size": 1}),
    ("read_many", {"paths": ["/cc/a"], "max_total": 10},
     {"files": {"/cc/a": b"a"}, "missing": []}),
    ("usage", {}, {"logical_bytes": 1}),
])
def test_read_reply_uses_base_from_before_restart(host_without_runsc, monkeypatch,
                                                 method, kwargs, value):
    host = host_without_runsc
    h = host.bind("cc-a", account_id="acct-a")
    host._state.set_generation_base("cc-a", 10)

    def reply(*args, **kw):
        host._state.set_generation_base("cc-a", 20)
        host._state.observe_generation("cc-a", 20)
        return {**value, "generation": 2}

    monkeypatch.setattr(host, "_rpc", reply)
    assert getattr(host, method)(h, **kwargs).generation == 12
    assert host._state.generation("cc-a") == 20


@pytest.mark.parametrize("reply", [
    {"op": "SURPRISE"},
    {"op": "END", "outcome": "surprise"},
])
def test_exchange_protocol_violation_has_unknown_outcome(monkeypatch, reply):
    client, peer = _socketpair()
    host = object.__new__(GVisorBoxProvider)
    monkeypatch.setattr(host, "_connect", lambda cc, deadline: client)
    with peer:
        peer.sendall(rpc_frames.control(1, reply))
        with pytest.raises(_BoxKilled):
            list(host._exchange("cc-a", "write", {}, deadline=time.monotonic() + 2))


def test_disk_quota_covers_data_and_socket_directory(monkeypatch):
    host = object.__new__(GVisorBoxProvider)
    host._disk_bound = 4096
    host._state = SimpleNamespace(slot=lambda cc: 7)
    commands = []
    monkeypatch.setattr(host, "_xfs_quota", lambda *args: commands.extend(args))
    host._apply_disk_bound("cc-a", Path("/data"), Path("/sock"))
    assert commands == [f"project -s -p {Path('/data')} 7",
                        f"project -s -p {Path('/sock')} 7", "limit -p bhard=4096 7"]


@pytest.mark.parametrize("idle", [False, True])
def test_idle_fence_requires_box_death(host_without_runsc, monkeypatch, idle):
    host = host_without_runsc
    killed = []
    monkeypatch.setattr(host, "_rpc", lambda *args: {"idle": idle})

    def kill(cc):
        assert host._state.owner_fence(cc) is None
        killed.append(cc)
        host._live.remove(cc)

    monkeypatch.setattr(host, "_kill_box", kill)
    assert host.try_fence_idle("cc-a", owner_generation=1) is idle
    assert killed == (["cc-a"] if idle else [])
    assert host._state.owner_fence("cc-a") == (1 if idle else None)


def test_failed_teardown_prevents_fence_and_destroy(host_without_runsc, monkeypatch):
    host = host_without_runsc
    h = host.bind("cc-a", account_id="acct-a")
    monkeypatch.setattr(host, "_rpc", lambda *args: {"idle": True})

    def kill(cc):
        raise BoxError("still exists")

    monkeypatch.setattr(host, "_kill_box", kill)
    with pytest.raises(BoxError, match="still exists"):
        host.try_fence_idle("cc-a", owner_generation=1)
    assert host._state.owner_fence("cc-a") is None
    with pytest.raises(BoxError, match="still exists"):
        host.destroy(h, "d1")
    assert host._state.epoch("cc-a") == h.epoch
