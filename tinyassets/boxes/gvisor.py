"""The gVisor `BoxProvider` driver: one runsc sandbox per command center.

The host side is deliberately small: **identify, forward, kill the box.**

* **Identify.** Every call is checked on the host, against the box host's own
  record: the account owns the command center, the epoch is current, the owner
  fence admits the handle's generation, and the op id is new (or its outcome is
  returned). Nothing inside the box is trusted for any of this.
* **Forward.** The call goes to `boxd`, the box's only long-lived process, over
  a socket bound into the sandbox (`tinyassets.boxes.boxd`). Inside, `boxd`
  runs the descriptor-safe core under gVisor's kernel. Paths, exec supervision
  and atomic writes all happen inside the box.
* **Kill the box.** Anything that cannot finish in time, or a box host
  restart, ends the WHOLE sandbox (``runsc kill`` + ``delete``). Every process
  in the box dies with it, by construction. This closes the two crash gaps that
  process-group tracking left in the local driver (box-provider-foundation D7).

Generations: the box counts its own (every write, remove, import and finished exec
advances it, inside the box, atomically with the change). The host adds a per-box
base, set past every generation it has ever reported whenever a box (re)starts, so
the number a caller sees only moves up, across box restarts and host crashes.

Isolation per box: a user-space kernel (systrap, no KVM needed), no network
(``--network=none`` and its own network namespace), a host uid range that is the
box's alone (user namespace mappings from a per-box slot), its own cgroup with a
memory limit (no swap past it) and a pids limit, and, given ``disk_bound_bytes``,
a hard disk bound per box: an XFS project quota on the box's directory.

The driver needs root on the box host (rootful runsc). Linux only.
"""

from __future__ import annotations

import base64
import contextlib
import errno
import hashlib
import itertools
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from tinyassets import rpc_frames
from tinyassets.boxes import provider as P
from tinyassets.boxes.provider import (
    BOX_ROOT,
    BoxDeadline,
    BoxDeadlineBeforeStart,
    BoxError,
    BoxHandle,
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
    StaleOwner,
    StreamIn,
    WriteMode,
    box_relpath,
)
from tinyassets.boxes.state import BoxHostState, op_digest

__all__ = ["GVisorBoxProvider"]

_STREAM = 1
_UID_BASE = 200_000
_UID_RANGE = 65_536
_MAX_SLOTS = (2**32 - _UID_BASE) // _UID_RANGE - 1
_SOCKET_NAME = "boxd.sock"
_ERRORS = {cls.__name__: cls for cls in (
    P.BoxAuthError, P.BoxBusy, P.BoxDeadline, P.BoxDeadlineBeforeStart, P.BoxError,
    P.BoxNotFound, P.BoxOperationRefused, P.BoxPathError, P.OpIdReuse, P.StaleHandle,
    P.StaleOwner, P.WriteConflict)}


def _unb64(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"__b64__"}:
            return base64.b64decode(value["__b64__"])
        return {k: _unb64(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unb64(v) for v in value]
    return value


class _BoxKilled(BoxError):
    """The box was killed while the call was in flight: its outcome is unknown."""


class GVisorBoxProvider:
    """`BoxProvider` over one rootful runsc sandbox per command center."""

    def __init__(
        self,
        *,
        boxes_root: Path,
        state_dir: Path,
        owner_of: Callable[[str], str | None],
        rootfs: Path,
        package_dir: Path,
        runsc: str = "runsc",
        python: str = "/usr/bin/python3",
        memory_bytes: int = 1 << 30,
        pids_limit: int = 512,
        disk_bound_bytes: int | None = None,
        quota_mount: Path | None = None,
        call_timeout_s: float = 30.0,
        start_timeout_s: float = 30.0,
        extra_runsc_flags: Sequence[str] = (),
    ) -> None:
        if os.name != "posix" or os.geteuid() != 0:
            raise BoxError("the gVisor box driver needs root on a Linux box host (rootful runsc)")
        if shutil.which(runsc) is None:
            raise BoxError(f"runsc not found ({runsc!r})")
        self._root = Path(boxes_root)
        self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._runsc_root = self._state_dir / "runsc"
        self._runsc_root.mkdir(exist_ok=True, mode=0o700)
        self._state = BoxHostState(self._state_dir / "boxhost.db")
        self._owner_of = owner_of
        self._rootfs = Path(rootfs)
        self._package_dir = Path(package_dir)
        self._runsc = [runsc, "--root", str(self._runsc_root), "--network=none",
                       "--platform=systrap", "--host-uds=create", *extra_runsc_flags]
        self._python = python
        self._memory = int(memory_bytes)
        self._pids = int(pids_limit)
        self._disk_bound = disk_bound_bytes
        self._quota_mount = Path(quota_mount) if quota_mount else self._root
        if disk_bound_bytes is not None:
            self._require_project_quota()
        self._call_timeout_s = call_timeout_s
        self._start_timeout_s = start_timeout_s
        self._tls = threading.local()
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._closing = False
        #: Boxes this host started and has not seen die. A new host starts with none
        #: running (it kills every box below), so this is the truth, without a
        #: `runsc state` process per call.
        self._live: set[str] = set()
        # A new box host: every sandbox a previous host left running dies now, with every
        # process in it. That is the crash containment, by construction.
        self._kill_all_boxes()
        self._state.bump_all_generations()

    # -- deadlines and locks -------------------------------------------------------

    @contextlib.contextmanager
    def bounded(self, deadline_s: float) -> Iterator[None]:
        previous = getattr(self._tls, "deadline", None)
        self._tls.deadline = time.monotonic() + max(0.0, float(deadline_s))
        try:
            yield
        finally:
            self._tls.deadline = previous

    def _deadline(self) -> float:
        explicit = getattr(self._tls, "deadline", None)
        return explicit if explicit is not None else time.monotonic() + self._call_timeout_s

    def _raw_lock(self, cc: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(cc, threading.RLock())

    @contextlib.contextmanager
    def _lock(self, cc: str) -> Iterator[None]:
        lock = self._raw_lock(cc)
        remaining = self._deadline() - time.monotonic()
        if remaining <= 0 or not lock.acquire(timeout=remaining):
            raise BoxDeadlineBeforeStart(f"command center {cc!r} stayed locked past the "
                                         "call's deadline; nothing was done")
        try:
            yield
        finally:
            lock.release()

    # -- identify ---------------------------------------------------------------------

    def _check_cc(self, cc: str) -> str:
        from tinyassets.boxes.local import LocalBoxProvider

        return LocalBoxProvider._check_cc(cc)

    def _require_owner(self, cc: str, account_id: str) -> None:
        owner = self._owner_of(cc)
        if owner is None or owner != account_id:
            raise P.BoxAuthError(f"account {account_id!r} does not own command center {cc!r}")

    def _auth(self, handle: BoxHandle) -> str:
        cc = self._check_cc(handle.command_center_id)
        self._require_owner(cc, handle.account_id)
        current = self._state.epoch(cc)
        if handle.epoch != current:
            raise StaleHandle(f"handle for {cc!r} has epoch {handle.epoch}, current is {current}")
        if self._closing:
            raise BoxError("the box host is shutting down")
        return cc

    def _require_owner_generation(self, cc: str, handle: BoxHandle) -> None:
        fence = self._state.owner_fence(cc)
        if fence is not None and (handle.owner_generation is None
                                  or handle.owner_generation < fence):
            raise StaleOwner(f"command center {cc!r} is fenced at owner generation {fence}")

    def bind(self, command_center_id: str, *, account_id: str,
             turn_id: str | None = None, owner_generation: int | None = None) -> BoxHandle:
        cc = self._check_cc(command_center_id)
        self._require_owner(cc, account_id)
        return BoxHandle(cc, account_id, self._state.epoch(cc), turn_id, owner_generation)

    def committed_generation(self, handle: BoxHandle) -> int:
        with self._lock(handle.command_center_id):
            cc = self._auth(handle)
            if not self._running(cc):
                return self._state.generation(cc)  # a stopped box changes nothing
            return self._host_gen(cc, self._rpc(cc, "generation", {}))

    def _host_gen(self, cc: str, box_generation: int) -> int:
        generation = self._state.generation_base(cc) + int(box_generation)
        self._state.observe_generation(cc, generation)
        return generation

    # -- box lifecycle (the only thing the host does to a box besides forwarding) ----

    def _container(self, cc: str) -> str:
        return "box-" + hashlib.sha256(cc.encode()).hexdigest()[:24]

    def _box_dirs(self, cc: str) -> tuple[Path, Path, Path]:
        base = self._root / cc
        return base / "data", base / "sock", base / "bundle"

    def _uid_base(self, cc: str) -> int:
        slot = self._state.slot(cc)
        if slot >= _MAX_SLOTS:
            raise BoxError("this box host has no uid range left for another box")
        return _UID_BASE + slot * _UID_RANGE

    def _xfs_quota(self, *commands: str) -> str:
        argv = ["xfs_quota", "-x"]
        for command in commands:
            argv += ["-c", command]
        r = subprocess.run([*argv, str(self._quota_mount)], capture_output=True, text=True,
                           timeout=30)
        if r.returncode != 0:
            raise BoxError(f"xfs_quota failed: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout

    def _require_project_quota(self) -> None:
        if shutil.which("xfs_quota") is None:
            raise BoxError("a per-box disk bound needs xfs_quota (xfsprogs) on the box host")
        state = self._xfs_quota("state -p")
        if "Enforcement: ON" not in state:
            raise BoxError(f"{self._quota_mount} is not XFS with project quotas enforced "
                           "(mount it with prjquota): the disk bound would not hold")

    def _apply_disk_bound(self, cc: str, data: Path) -> None:
        if self._disk_bound is None:
            return
        project = self._state.slot(cc)
        self._xfs_quota(f"project -s -p {data} {project}",
                        f"limit -p bhard={int(self._disk_bound)} {project}")

    def _running(self, cc: str) -> bool:
        return cc in self._live

    def _kill_box(self, cc: str) -> None:
        """End the whole sandbox: every process in the box dies with it."""
        name = self._container(cc)
        subprocess.run([*self._runsc, "kill", name, "KILL"], capture_output=True, timeout=10)
        subprocess.run([*self._runsc, "delete", "--force", name], capture_output=True,
                       timeout=30)
        if cc in self._live:
            self._live.discard(cc)
            # It may have changed files after anyone last asked: a later start counts
            # from past this.
            self._state.bump_generation(cc)

    def _kill_all_boxes(self) -> None:
        r = subprocess.run([*self._runsc, "list", "--format=json"], capture_output=True,
                           text=True, timeout=30)
        try:
            listed = json.loads(r.stdout or "[]") or []
        except json.JSONDecodeError:
            listed = []
        for entry in listed:
            name = entry.get("id", "")
            if name.startswith("box-"):
                subprocess.run([*self._runsc, "kill", name, "KILL"], capture_output=True,
                               timeout=10)
                subprocess.run([*self._runsc, "delete", "--force", name],
                               capture_output=True, timeout=30)

    def _ensure_box(self, cc: str) -> None:
        if cc in self._live:
            return
        self._kill_box(cc)  # a dead or half-started sandbox: clear it first
        data, sock, bundle = self._box_dirs(cc)
        uid = self._uid_base(cc)
        for d in (data, sock, bundle):
            d.mkdir(parents=True, exist_ok=True)
        os.chown(data, uid, uid)
        os.chmod(data, 0o700)
        self._apply_disk_bound(cc, data)
        os.chown(sock, uid, uid)
        for leftover in sock.iterdir():
            leftover.unlink()
        spec = {
            "ociVersion": "1.0.2",
            "process": {
                "terminal": False, "user": {"uid": 0, "gid": 0}, "cwd": BOX_ROOT,
                "args": [self._python, "-m", "tinyassets.boxes.boxd",
                         "--socket", f"/run/boxsock/{_SOCKET_NAME}", "--root", BOX_ROOT,
                         "--state", "/run/boxd"],
                "env": ["PATH=/usr/local/bin:/usr/bin:/bin", "PYTHONPATH=/opt/tinyassets",
                        "LANG=C.UTF-8", f"HOME={BOX_ROOT}"],
                "noNewPrivileges": True,
            },
            "root": {"path": str(self._rootfs), "readonly": True},
            "hostname": "box",
            "mounts": [
                {"destination": "/proc", "type": "proc", "source": "proc"},
                {"destination": "/dev", "type": "tmpfs", "source": "tmpfs",
                 "options": ["nosuid", "strictatime", "mode=755", "size=65536k"]},
                {"destination": "/tmp", "type": "tmpfs", "source": "tmpfs",
                 "options": ["nosuid", "nodev", "size=268435456"]},
                {"destination": "/run/boxd", "type": "tmpfs", "source": "tmpfs",
                 "options": ["nosuid", "nodev", "size=16777216"]},
                {"destination": BOX_ROOT, "type": "bind", "source": str(data),
                 "options": ["rbind", "rw"]},
                {"destination": "/run/boxsock", "type": "bind", "source": str(sock),
                 "options": ["rbind", "rw"]},
                {"destination": "/opt/tinyassets", "type": "bind",
                 "source": str(self._package_dir), "options": ["rbind", "ro"]},
            ],
            "linux": {
                "cgroupsPath": f"/tinyassets-boxes/{self._container(cc)}",
                "namespaces": [{"type": t} for t in
                               ("pid", "network", "ipc", "uts", "mount", "user")],
                "uidMappings": [{"containerID": 0, "hostID": uid, "size": _UID_RANGE}],
                "gidMappings": [{"containerID": 0, "hostID": uid, "size": _UID_RANGE}],
                "resources": {"memory": {"limit": self._memory, "swap": self._memory},
                              "pids": {"limit": self._pids}},
            },
        }
        (bundle / "config.json").write_text(json.dumps(spec))
        # A detached sandbox inherits pipes it never closes: capture to a file, not a pipe.
        log = bundle / "start.log"
        with open(log, "wb") as out:
            r = subprocess.run([*self._runsc, "run", "--detach", "--bundle", str(bundle),
                                self._container(cc)], stdout=out, stderr=out,
                               stdin=subprocess.DEVNULL, timeout=self._start_timeout_s)
        if r.returncode != 0:
            tail = log.read_bytes()[-400:].decode("utf-8", "replace")
            raise BoxError(f"box {cc!r} failed to start: {tail}")
        deadline = time.monotonic() + self._start_timeout_s
        while time.monotonic() < deadline:
            try:
                self._rpc(cc, "ping", {}, deadline=time.monotonic() + 2)
            except BoxError:
                time.sleep(0.02)
                continue
            # A fresh box counts from 0, and nothing changed while it was stopped (every
            # stop advanced the generation): it starts at the last one reported.
            self._state.set_generation_base(cc, self._state.generation(cc))
            self._live.add(cc)
            return
        self._kill_box(cc)
        raise BoxError(f"box {cc!r} started but boxd never answered")

    # -- forward ------------------------------------------------------------------

    def _connect(self, cc: str, deadline: float) -> socket.socket:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BoxDeadline(f"box {cc!r}: out of time before the request was sent")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(remaining)
        s.connect(str(self._box_dirs(cc)[1] / _SOCKET_NAME))
        return s

    def _rpc(self, cc: str, op: str, args: dict, *, payload: bytes | None = None,
             deadline: float | None = None) -> Any:
        """One request, its streamed items discarded; returns the result value."""
        for kind, value in self._exchange(cc, op, args, payload=payload, deadline=deadline):
            if kind == "result":
                return value
        raise _BoxKilled(f"box {cc!r}: {op} ended without a result")

    def _exchange(self, cc: str, op: str, args: dict, *, payload: bytes | None = None,
                  deadline: float | None = None) -> Iterator[tuple[str, Any]]:
        """One request on its own connection, yielding replies AS THEY ARRIVE.

        Yields ``("output", ExecEvent)``, ``("exit", ExecEvent)``, ``("data", bytes)`` and
        finally ``("result", value)``. Raises the box's own typed error as-is; a
        transport failure (the box is gone or broke the protocol) as `_BoxKilled`; running
        out of time as `BoxDeadline`.
        """
        deadline = deadline if deadline is not None else self._deadline()
        try:
            conn = self._connect(cc, deadline)
        except BoxError:
            raise
        except OSError as exc:
            raise _BoxKilled(f"box {cc!r}: cannot reach boxd for {op} ({exc})") from None
        try:
            request = {"op": op.upper(), "args": args,
                       "deadline_ms": int((time.time() + (deadline - time.monotonic())) * 1000)}
            output: dict | None = None
            try:
                conn.sendall(rpc_frames.control(_STREAM, request))
                if payload is not None:
                    for frame in rpc_frames.data(_STREAM, payload):
                        conn.sendall(frame)
                    conn.sendall(rpc_frames.control(_STREAM, {"op": "END",
                                                              "outcome": "completed"}))
                while True:
                    conn.settimeout(max(0.01, deadline - time.monotonic()))
                    try:
                        frame = rpc_frames.read_frame_blocking(conn)
                    except (TimeoutError, socket.timeout):
                        raise BoxDeadline(f"box {cc!r}: {op} did not answer in time; "
                                          "outcome unknown") from None
                    if frame is None:
                        raise _BoxKilled(f"box {cc!r} closed the connection during {op}")
                    if frame.kind == rpc_frames.DATA:
                        if output is not None:
                            yield "output", ExecEvent("output", offset=output["offset"],
                                                      data=frame.payload)
                            output["offset"] += len(frame.payload)
                        else:
                            yield "data", frame.payload
                        continue
                    doc = frame.control()
                    if doc["op"] == "EVENT" and doc.get("kind") == "output":
                        output = {"offset": int(doc.get("offset", 0))}
                    elif doc["op"] == "EVENT":
                        output = None
                        yield "exit", ExecEvent("exit", offset=int(doc.get("offset", 0)),
                                                exit_code=doc.get("exit_code"),
                                                killed=doc.get("killed"))
                    elif doc["op"] == "END" and doc.get("outcome") == "completed":
                        yield "result", _unb64(doc.get("value"))
                        return
                    elif doc["op"] == "END":
                        cls = _ERRORS.get(doc.get("error_class"), BoxError)
                        if doc.get("side_effect_state") != "none" and issubclass(
                                cls, P.BoxOperationRefused):
                            cls = BoxError  # a refusal must also say it never ran
                        if cls is P.BoxNotFound:
                            raise P.BoxNotFound(errno.ENOENT, doc.get("message", ""))
                        raise cls(doc.get("message", ""))
                    else:
                        raise BoxError(f"unexpected reply {doc['op']!r} from box {cc!r}")
            except BoxError:
                raise
            except (OSError, rpc_frames.FrameError) as exc:
                if time.monotonic() >= deadline:  # a timeout inside a frame
                    raise BoxDeadline(f"box {cc!r}: {op} did not answer in time; outcome "
                                      "unknown") from None
                raise _BoxKilled(f"box {cc!r}: {op} lost its connection ({exc})") from None
        finally:
            conn.close()

    def _mutate(self, handle: BoxHandle, op_id: str, op: str, args: dict,
                payload: bytes | None = None, expect_generation: int | None = None) -> Any:
        """Identify, record the op, forward, record the outcome. Kill the box if it hangs."""
        digest_args = {**args, "sha": hashlib.sha256(payload or b"").hexdigest()}
        with self._lock(handle.command_center_id):
            cc = self._auth(handle)
            self._require_owner_generation(cc, handle)
            record = self._state.begin(cc, op_id, op, op_digest(op, digest_args))
            if record is not None:
                if record["state"] == "done":
                    outcome = record["outcome"] or {}
                    if "error" in outcome:
                        raise BoxError(f"{op} {op_id!r} failed earlier and is not re-run: "
                                       f"{outcome['error']}")
                    return outcome.get("value")
                raise BoxError(f"{op} {op_id!r} has an unknown outcome; it is not re-run")
            try:
                self._ensure_box(cc)
                if expect_generation is not None:
                    # cas is checked INSIDE the box, atomically with the write and with
                    # "no exec running"; the host only translates its generation.
                    box_expect = expect_generation - self._state.generation_base(cc)
                    if box_expect < 0:
                        raise P.WriteConflict(f"box generation is not {expect_generation}")
                    args = {**args, "mode": WriteMode.CAS.value,
                            "expect_generation": box_expect}
            except BaseException:
                self._state.abandon(cc, op_id)  # the box never got the request
                raise
            try:
                value = self._rpc(cc, op, {**args, "op_id": op_id}, payload=payload)
            except (P.BoxOperationRefused, P.WriteConflict):
                self._state.abandon(cc, op_id)  # provably changed nothing inside the box
                raise
            except (BoxDeadline, _BoxKilled):
                # Unknown outcome. End the box so nothing it was doing can continue.
                self._kill_box(cc)
                raise BoxDeadline(f"{op} {op_id!r} in {cc!r}: outcome unknown; the box was "
                                  "stopped") from None
            except BoxError as exc:
                # The box advanced its own generation if anything changed.
                self._state.finish(cc, op_id, {"error": str(exc)})
                raise
            if isinstance(value, dict) and "generation" in value:
                value = {**value, "generation": self._host_gen(cc, value["generation"])}
            self._state.finish(cc, op_id, {"value": value})
            return value

    def _awake(self, handle: BoxHandle) -> str:
        with self._lock(handle.command_center_id):
            cc = self._auth(handle)
            self._ensure_box(cc)
        return cc

    def _read(self, handle: BoxHandle, op: str, args: dict) -> Any:
        cc = self._awake(handle)
        try:
            return self._rpc(cc, op, args)
        except _BoxKilled:
            # The box died on its own (boxd out of memory, say). A read has no effect, so
            # it is safe to start the box again and ask once more.
            with self._lock(cc):
                self._kill_box(cc)
            return self._rpc(self._awake(handle), op, args)

    def _data(self, handle: BoxHandle, op: str, args: dict) -> Iterator[bytes]:
        """Streamed bytes. The first reply is read now, so a refusal (a link, a missing
        file, a busy box) raises at the call, as with every other driver."""
        cc = self._awake(handle)
        replies = self._exchange(cc, op, args, deadline=self._deadline())
        first = next(replies)

        def chunks() -> Iterator[bytes]:
            for kind, value in itertools.chain([first], replies):
                if kind == "data":
                    yield value

        return chunks()

    # -- the contract ---------------------------------------------------------------

    def ensure_awake(self, handle: BoxHandle, *, reason: str) -> None:
        with self._lock(handle.command_center_id):
            self._ensure_box(self._auth(handle))

    def suspend(self, handle: BoxHandle) -> None:
        with self._lock(handle.command_center_id):
            cc = self._auth(handle)
            self._kill_box(cc)  # gVisor driver v1: suspend = stop (files persist on disk)

    def read(self, handle: BoxHandle, path: str, *, offset: int = 0,
             max_bytes: int) -> FileRead:
        box_relpath(path)
        v = self._read(handle, "read", {"path": path, "offset": offset, "max_bytes": max_bytes})
        return FileRead(data=v["data"], size=v["size"],
                        generation=self._host_gen(handle.command_center_id, v["generation"]))

    def read_many(self, handle: BoxHandle, paths: Sequence[str], *, max_total: int) -> Snapshot:
        for p in paths:
            box_relpath(p)
        v = self._read(handle, "read_many", {"paths": list(paths), "max_total": max_total})
        return Snapshot(files=v["files"], missing=tuple(v["missing"]),
                        generation=self._host_gen(handle.command_center_id, v["generation"]))

    def write(self, handle: BoxHandle, op_id: str, path: str, data: StreamIn, *,
              max_bytes: int, mode: WriteMode = WriteMode.REPLACE,
              expect_generation: int | None = None) -> FileWrite:
        from tinyassets.boxes.local import _bounded

        box_relpath(path)
        body = _bounded(data, max_bytes)
        mode = WriteMode(mode)
        if mode is WriteMode.CAS and expect_generation is None:
            raise ValueError("a cas write needs expect_generation")
        v = self._mutate(handle, op_id, "write", {
            "path": path, "max_bytes": max_bytes,
            "mode": WriteMode.REPLACE.value if mode is WriteMode.CAS else mode.value},
            payload=body, expect_generation=expect_generation if mode is WriteMode.CAS else None)
        return FileWrite(path=path, size=v["size"], generation=v["generation"])

    def download(self, handle: BoxHandle, path: str, *,
                 chunk_bytes: int = 64 * 1024) -> Iterator[bytes]:
        box_relpath(path)
        return self._data(handle, "download", {"path": path})

    def list(self, handle: BoxHandle, path: str, *, cursor: str | None = None,
             limit: int = 200) -> DirPage:
        box_relpath(path)
        v = self._read(handle, "list", {"path": path, "cursor": cursor, "limit": limit})
        return DirPage(tuple(DirEntry(**e) for e in v["entries"]), v["next_cursor"])

    def stat(self, handle: BoxHandle, path: str) -> FileStat | None:
        box_relpath(path)
        v = self._read(handle, "stat", {"path": path})
        return None if v is None else FileStat(**v)

    def remove(self, handle: BoxHandle, op_id: str, path: str) -> None:
        box_relpath(path)
        self._mutate(handle, op_id, "remove", {"path": path})

    def start_exec(self, handle: BoxHandle, op_id: str, argv: Sequence[str], *,
                   stdin: bytes = b"", env: Mapping[str, str] | None = None,
                   cwd: str = BOX_ROOT, limits: ExecLimits = ExecLimits()) -> str:
        box_relpath(cwd)
        return self._mutate(handle, op_id, "start_exec", {
            "argv": list(argv), "stdin_b64": base64.b64encode(bytes(stdin)).decode(),
            "env": dict(env or {}), "cwd": cwd,
            "limits": {"wall_seconds": limits.wall_seconds,
                       "output_bytes": limits.output_bytes}})

    def stream(self, handle: BoxHandle, exec_id: str, *,
               from_offset: int = 0, timeout: float | None = None) -> Iterator[ExecEvent]:
        """Events as the box produces them. A timeout ends the stream with no exit event
        (stream again from the last offset), as with every driver. If the box dies
        mid-stream the exec's outcome is unknown, and the stream ends saying so."""
        cc = self._awake(handle)  # refusals raise here, at the call
        wait = timeout if timeout is not None else self._call_timeout_s

        def events() -> Iterator[ExecEvent]:
            try:
                for kind, value in self._exchange(cc, "stream", {
                        "exec_id": exec_id, "from_offset": from_offset, "timeout": wait},
                        deadline=time.monotonic() + wait + 5):
                    if kind in ("output", "exit"):
                        yield value
            except BoxDeadline:
                return
            except _BoxKilled:
                yield ExecEvent("exit", killed=ExecState.UNKNOWN_AFTER_RESTORE.value)

        return events()

    def cancel(self, handle: BoxHandle, exec_id: str) -> None:
        cc = self._auth(handle)  # no box lock: a cancel never waits behind another call
        with self.bounded(5):
            try:
                self._rpc(cc, "cancel_exec", {"exec_id": exec_id})
            except (BoxDeadline, _BoxKilled):
                self._kill_box(cc)  # the backstop: end the box, and every exec in it

    def exec_status(self, handle: BoxHandle, op_id: str) -> ExecStatus:
        cc = self._auth(handle)
        record = self._state.lookup(cc, op_id)
        if record is None or record["kind"] != "start_exec":
            raise P.BoxNotFound(errno.ENOENT, f"no exec operation {op_id!r} in this box")
        exec_id = (record["outcome"] or {}).get("value")
        if record["state"] != "done" or exec_id is None:
            return ExecStatus(op_id, exec_id or "", ExecState.UNKNOWN_AFTER_RESTORE)
        try:
            v = self._read(handle, "exec_status", {"op_id": op_id})
        except BoxError:
            return ExecStatus(op_id, exec_id, ExecState.UNKNOWN_AFTER_RESTORE)
        return ExecStatus(op_id, v["exec_id"], ExecState(v["state"]), v.get("exit_code"),
                          v.get("killed"))

    def usage(self, handle: BoxHandle) -> BoxUsage:
        v = self._read(handle, "usage", {})
        return BoxUsage(logical_bytes=v["logical_bytes"], bound_bytes=self._disk_bound,
                        generation=self._host_gen(handle.command_center_id, v["generation"]))

    def export(self, handle: BoxHandle, *, profile: ExportProfile) -> Iterator[bytes]:
        return self._data(handle, "export", {"profile": ExportProfile(profile).value})

    def import_bundle(self, handle: BoxHandle, op_id: str, chunks: Iterable[bytes], *,
                      profile: ExportProfile) -> ImportReport:
        body = b"".join(bytes(c) for c in chunks)
        v = self._mutate(handle, op_id, "import_bundle",
                         {"profile": ExportProfile(profile).value}, payload=body)
        return ImportReport(v["files"], v["bytes"], tuple(v["refused"]))

    def try_fence_idle(self, command_center_id: str, *, owner_generation: int) -> bool:
        cc = self._check_cc(command_center_id)
        with self._lock(cc):  # no forwarded mutation can start while this is held
            fence = self._state.owner_fence(cc)
            if fence is not None and owner_generation < fence:
                raise StaleOwner(f"command center {cc!r} is already fenced at {fence}")
            if self._running(cc) and not self._rpc(cc, "idle", {})["idle"]:
                return False
            return self._state.raise_owner_fence(cc, owner_generation)

    def destroy(self, handle: BoxHandle, op_id: str) -> DestroyReceipt:
        cc = self._check_cc(handle.command_center_id)
        with self._lock(cc):
            self._require_owner(cc, handle.account_id)
            recorded = self._state.lookup(cc, op_id)
            if recorded and recorded["kind"] == "destroy" and recorded["state"] == "done":
                o = recorded["outcome"] or {}
                return DestroyReceipt(cc, op_id, o["files_removed"], o["new_epoch"])
            self._auth(handle)
            self._require_owner_generation(cc, handle)
            if self._state.begin(cc, op_id, "destroy", op_digest("destroy", {})) is not None:
                raise BoxError(f"destroy {op_id!r} has an earlier record")
            self._kill_box(cc)  # every process in the box ends here
            data = self._box_dirs(cc)[0]
            removed = sum(1 for p in data.rglob("*") if p.is_file()) if data.exists() else 0
            shutil.rmtree(self._root / cc, ignore_errors=False) if (self._root / cc).exists() \
                else None
            new_epoch = self._state.bump_epoch(cc)
            self._state.finish(cc, op_id, {"files_removed": removed, "new_epoch": new_epoch})
        return DestroyReceipt(cc, op_id, removed, new_epoch)

    def close(self) -> None:
        with self._locks_guard:
            self._closing = True
        self._kill_all_boxes()
        self._state.close()
