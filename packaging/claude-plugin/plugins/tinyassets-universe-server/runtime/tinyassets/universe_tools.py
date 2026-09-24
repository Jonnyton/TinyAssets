"""The universe agent's four tools: ``read``, ``write``, ``edit``, ``bash``.

Slice S1 of "the universe is the harness" (PLAN.md Scoping Rule 1; OpenSpec
change ``universe-harness-four-tools``). A universe IS its agent's harness and
project folder, so its agent works in that folder with the same four
primitives pi.dev gives an agent, and builds everything else from them.

Vendor-neutral by construction (Hard Rule 3): the PLATFORM runs these tools,
not a vendor CLI's built-ins. They are served over the per-universe engine MCP
route every adapter already uses (``claude -p``, ``codex exec``, the
OpenAI-compatible HTTP loop), so each adapter sees the same four definitions.

The tool jail
-------------
Every call -- reads included -- runs as a process inside bubblewrap, built by
the SAME :func:`tinyassets.providers.provider_jail.jail_argv` as a provider
launch, with a narrower view:

* the owning universe read-write at ``/u``, and nothing else of ``/data``;
* ``.runtime/`` (platform-owned: launch credentials, provider homes, the engine
  route config) masked by an empty ``tmpfs``, so it is neither readable nor
  writable to disk;
* system binaries read-only, a private ``/tmp``, ``/dev`` and pid-namespace
  ``/proc``; NO ``/app``, no install tree, no credential snapshot at all;
* NO network: no ``--share-net``, so the jail has its own empty network
  namespace (network arrives in S3, through an egress filter);
* an empty environment (``--clearenv``) plus a fixed ``PATH``/``HOME``;
* a seccomp filter refusing ``symlink``/``mknod`` (see :func:`seccomp_program`):
  the daemon reads this folder from OUTSIDE the jail and follows links, so a
  link planted towards another universe must never exist on disk.

Because the process sees only ``/u``, path policy is the jail's, not Python's:
a path outside the universe, or a symlink the agent planted towards another
universe, resolves inside the jail's own mount namespace and finds nothing.

Resource limits (per call, per universe)
----------------------------------------
Measured on the production container 2026-09-24 (kernel 6.1, uid 1001, no
capabilities, cgroup2 mounted READ-ONLY, so no per-universe cgroup can be
created): ``prlimit`` runs inside the jail, after the user namespace exists,
and sets ``RLIMIT_AS``, ``RLIMIT_NPROC``, ``RLIMIT_CPU``, ``RLIMIT_FSIZE``,
``RLIMIT_NOFILE`` and ``RLIMIT_CORE``. On kernels >= 5.14 ``RLIMIT_NPROC`` is
charged per user namespace, so it bounds THIS jail's processes, not the
daemon user's (measured: with 9 daemon processes and ``--nproc=12`` the jail
forked 10). The parent adds what an rlimit cannot: a wall clock, an output
cap enforced while reading, and a watch on the jail's whole process tree
(count and resident memory), which also bounds a root-run jail where the
kernel exempts ``RLIMIT_NPROC``, and a free-space floor on the shared data
volume. Concurrency is bounded per universe and across the host by lock-file
slots, so the sum of jails is bounded too.

Fail closed: no bubblewrap, no ``prlimit``, or a jail that exits before the
marker proving the limits were applied, and the call is refused with nothing
run. There is no unjailed or unlimited fallback.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tinyassets.providers import provider_jail
from tinyassets.providers.provider_jail import (
    PLATFORM_RUNTIME_DIR,
    JailMount,
    UniverseView,
    jail_argv,
)

__all__ = [
    "MASKED_DIRS",
    "MOUNT_POINT",
    "TOOL_NAMES",
    "ToolLimits",
    "ToolRun",
    "UniverseToolError",
    "bash",
    "edit_file",
    "harness_prompt",
    "read_file",
    "seccomp_program",
    "skill_index",
    "tool_jail_argv",
    "write_file",
]

#: The whole tool list. Nothing else is an agent tool definition.
TOOL_NAMES: tuple[str, ...] = ("read", "write", "edit", "bash")

#: Where the universe appears inside the tool jail.
MOUNT_POINT = "/u"

#: Platform-owned directories inside a universe, masked by an empty tmpfs in the
#: tool jail. ``.runtime`` holds launch credentials, provider homes and the
#: engine route config (the route bearer). The agent may create any other
#: directory, hidden ones included: a provider launch masks every hidden root
#: directory (``provider_jail.hidden_dir_masks``), so none of them can become a
#: CLI's project settings.
MASKED_DIRS: tuple[str, ...] = (PLATFORM_RUNTIME_DIR,)

#: Environment inside the jail: fixed, secret-free, nothing inherited.
_JAIL_ENV: tuple[tuple[str, str], ...] = (
    ("PATH", "/usr/local/bin:/usr/bin:/bin"),
    ("HOME", "/tmp"),
    ("LANG", "C.UTF-8"),
    ("TERM", "dumb"),
)

#: Printed by the jailed wrapper AFTER prlimit applied every limit and before
#: the command runs. Output that does not start with it means nothing ran
#: under limits, and the call is refused.
_LIMITS_MARK = b"\x1eta-limits-applied\x1e"

_MiB = 1024 * 1024

#: Largest file ``write`` accepts and ``edit`` will rewrite.
MAX_WRITE_BYTES = 4 * _MiB
MAX_EDIT_BYTES = 1 * _MiB
#: ``read`` returns at most this many lines unless asked for a range.
DEFAULT_READ_LINES = 2000
#: The longest a ``bash`` call may ask to run.
MAX_BASH_SECONDS = 600.0

#: How long a call waits for a free slot before it is refused.
_SLOT_WAIT_SECONDS = 30.0
#: Jails running at once for ONE universe, and on the whole host.
_PER_UNIVERSE_SLOTS = 2
_HOST_SLOTS = 4

_POLL_SECONDS = 0.05
_KILL_GRACE_SECONDS = 5.0


class UniverseToolError(RuntimeError):
    """A tool call was refused before (or instead of) running anything."""

    failure_class = "universe_tool_refused"


@dataclass(frozen=True)
class ToolLimits:
    """The limits every tool jail runs under. Floor, not policy: on a shared
    host a fork bomb or a memory spike in one universe is an outage for the
    others (design section 4)."""

    #: ``RLIMIT_AS`` per process.
    memory_bytes: int = 512 * _MiB
    #: ``RLIMIT_NPROC``: per jail user namespace on kernel >= 5.14.
    processes: int = 64
    #: ``RLIMIT_CPU`` per process; the wall clock bounds the whole call.
    cpu_seconds: int = 120
    #: ``RLIMIT_FSIZE``: the largest file one write may produce. Kept modest
    #: because the daemon reads some universe files (the persona grounding)
    #: whole, in a process every universe shares.
    file_bytes: int = 32 * _MiB
    #: ``RLIMIT_NOFILE``.
    open_files: int = 256
    #: Wall clock for one call (``bash`` may ask for up to MAX_BASH_SECONDS).
    wall_seconds: float = 120.0
    #: Output kept per call; the jail is killed once it passes this.
    output_bytes: int = 64 * 1024
    #: Resident memory summed over the jail's process tree.
    tree_memory_bytes: int = 768 * _MiB
    #: Free space the shared data volume must keep: a call is refused below it,
    #: and a running jail is killed when its writes take the volume below it.
    min_free_disk_bytes: int = 1024 * _MiB

    def prlimit_args(self, *, cpu_seconds: int | None = None) -> list[str]:
        cpu = int(cpu_seconds if cpu_seconds is not None else self.cpu_seconds)
        return [
            f"--as={int(self.memory_bytes)}",
            f"--nproc={int(self.processes)}",
            f"--cpu={max(1, cpu)}",
            f"--fsize={int(self.file_bytes)}",
            f"--nofile={int(self.open_files)}",
            "--core=0",
        ]


DEFAULT_LIMITS = ToolLimits()


@dataclass(frozen=True)
class ToolRun:
    """What one jailed process did."""

    exit_code: int | None
    output: bytes
    #: ``timeout``, ``output_limit``, ``memory_limit``, ``process_limit``,
    #: ``disk_limit`` or None.
    killed: str | None
    elapsed: float


# ── the jail ────────────────────────────────────────────────────────────────


def _system_binary(name: str) -> str:
    """A binary the jail can see (``/usr`` or ``/bin`` are bound), or refuse."""
    found = shutil.which(name, path="/usr/bin:/bin")
    if not found or not (found.startswith("/usr/") or found.startswith("/bin/")):
        raise UniverseToolError(
            f"{name} is not installed on this host, so the tool jail cannot apply "
            "its resource limits; nothing ran"
        )
    return found


def _prepare_masks(root: Path) -> None:
    """Every masked directory exists as a real directory before the jail starts.

    A mountpoint the agent cannot remove or replace keeps it from ever writing
    to, or replacing, the platform's own directory. A symlink or file already
    there is refused, not followed.
    """
    for name in MASKED_DIRS:
        path = root / name
        if os.path.lexists(path):
            if path.is_symlink() or not path.is_dir():
                raise UniverseToolError(
                    f"the universe's {name} is not a plain directory; the tool jail "
                    "will not start over it"
                )
            continue
        path.mkdir(mode=0o700)


def tool_jail_argv(
    universe_dir: Path, inner: Sequence[str], *, seccomp_fd: int | None = None,
) -> list[str]:
    """The bubblewrap argv running ``inner`` in ``universe_dir``'s tool jail."""
    try:
        root = Path(universe_dir).resolve(strict=True)
    except OSError:
        raise UniverseToolError("the universe folder does not exist") from None
    if not root.is_dir():
        raise UniverseToolError("the universe folder does not exist")
    bwrap = provider_jail.BWRAP_RESOLVER()
    _prepare_masks(root)
    mounts = [JailMount("bind", MOUNT_POINT, root)]
    mounts.extend(JailMount("tmpfs", f"{MOUNT_POINT}/{name}") for name in MASKED_DIRS)
    view = UniverseView(
        universe_dir=root,
        mounts=tuple(mounts),
        chdir=MOUNT_POINT,
        setenv=_JAIL_ENV,
    )
    return jail_argv(
        list(inner), view, bwrap_path=bwrap, share_net=False, clearenv=True,
        seccomp_fd=seccomp_fd,
    )


#: Builds the jail argv. Substituted by tests (injection, never an env switch);
#: production never replaces it.
TOOL_JAIL_ARGV: Callable[..., list[str]] = tool_jail_argv


# The link filter. The jail makes the agent's view safe, but the DAEMON reads
# the same folder from outside it (persona grounding, config, soul) and follows
# links. A symlink the agent planted -- ``founder.md -> /data/<other>/founder.md``
# dangles inside the jail and resolves on the host -- would pull another user's
# file into this universe's prompt; a FIFO would hang the reading thread. So the
# jailed process may create neither: ``symlink``/``symlinkat`` and
# ``mknod``/``mknodat`` fail with EPERM. Hard links cannot reach outside ``/u``
# (every other visible path is a different mount: EXDEV). Unknown architectures
# and the x32 ABI get EPERM for every call, so a filter this module cannot vouch
# for never runs as ALLOW.
_AUDIT_ARCH_X86_64 = 0xC000003E
_AUDIT_ARCH_AARCH64 = 0xC00000B7
_X32_SYSCALL_BIT = 0x40000000
_DENIED_X86_64 = (88, 266, 133, 259)  # symlink, symlinkat, mknod, mknodat
_DENIED_AARCH64 = (36, 33)  # symlinkat, mknodat
_SECCOMP_RET_ALLOW = 0x7FFF0000
_SECCOMP_RET_EPERM = 0x00050000 | 1


def seccomp_program() -> bytes:
    """The compiled cBPF filter bubblewrap loads with ``--seccomp``."""
    import struct

    ld_abs, jeq, jge, ret = 0x20, 0x15, 0x35, 0x06
    x86 = list(_DENIED_X86_64)
    arm = list(_DENIED_AARCH64)
    # Layout: [0] ld arch; [1] arch==x86_64?; [2] ld nr; [3] x32?; x86 checks;
    # allow; [arm] arch==aarch64?; ld nr; arm checks; allow; [deny].
    arm_at = 4 + len(x86) + 1
    deny_at = arm_at + 2 + len(arm) + 1
    prog: list[tuple[int, int, int, int]] = [
        (ld_abs, 0, 0, 4),
        (jeq, 0, arm_at - 2, _AUDIT_ARCH_X86_64),
        (ld_abs, 0, 0, 0),
        (jge, deny_at - 4, 0, _X32_SYSCALL_BIT),
    ]
    for nr in x86:
        prog.append((jeq, deny_at - (len(prog) + 1), 0, nr))
    prog.append((ret, 0, 0, _SECCOMP_RET_ALLOW))
    assert len(prog) == arm_at
    prog.append((jeq, 0, deny_at - (len(prog) + 1), _AUDIT_ARCH_AARCH64))
    prog.append((ld_abs, 0, 0, 0))
    for nr in arm:
        prog.append((jeq, deny_at - (len(prog) + 1), 0, nr))
    prog.append((ret, 0, 0, _SECCOMP_RET_ALLOW))
    assert len(prog) == deny_at
    prog.append((ret, 0, 0, _SECCOMP_RET_EPERM))
    return b"".join(struct.pack("=HBBI", *insn) for insn in prog)


def _seccomp_fd() -> int:
    """A readable descriptor holding :func:`seccomp_program`, for the child."""
    read_end, write_end = os.pipe()
    try:
        os.write(write_end, seccomp_program())
    finally:
        os.close(write_end)
    return read_end


def _free_disk(path: Path) -> int:
    try:
        stats = os.statvfs(path)
    except (AttributeError, OSError):
        return -1
    return int(stats.f_bavail) * int(stats.f_frsize)


def _limited(inner: Sequence[str], limits: ToolLimits, cpu_seconds: int) -> list[str]:
    """``inner`` wrapped so it runs only after every rlimit is in place."""
    prlimit = _system_binary("prlimit")
    return [
        prlimit, *limits.prlimit_args(cpu_seconds=cpu_seconds), "--",
        "/bin/sh", "-c", 'printf "%s" "$0"; exec "$@" 2>&1',
        _LIMITS_MARK.decode("ascii"), *inner,
    ]


def _slot_dir() -> Path:
    from tinyassets.storage import data_dir

    path = Path(data_dir()) / ".universe-tool-slots"
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextlib.contextmanager
def _slot(universe_dir: Path) -> Iterator[None]:
    """Hold one per-universe slot and one host slot, or refuse.

    Lock files, so the bound holds across the per-universe engine processes.
    """
    import fcntl

    directory = _slot_dir()
    key = hashlib.sha256(str(universe_dir).encode("utf-8")).hexdigest()[:16]
    pools = (
        [directory / f"u-{key}-{i}.lock" for i in range(_PER_UNIVERSE_SLOTS)],
        [directory / f"host-{i}.lock" for i in range(_HOST_SLOTS)],
    )
    held: list[int] = []
    deadline = time.monotonic() + _SLOT_WAIT_SECONDS
    try:
        for pool, what in zip(pools, ("this universe", "this host"), strict=True):
            while True:
                fd = _try_lock_one(pool, fcntl)
                if fd is not None:
                    held.append(fd)
                    break
                if time.monotonic() >= deadline:
                    raise UniverseToolError(
                        f"every tool slot for {what} is busy; try again shortly"
                    )
                time.sleep(0.1)
        yield
    finally:
        for fd in held:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _try_lock_one(paths: list[Path], fcntl) -> int | None:
    for path in paths:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            continue
        return fd
    return None


class _Drain(threading.Thread):
    """Read a pipe, keeping at most ``cap`` bytes; flag the moment it passes."""

    def __init__(self, stream, cap: int) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._cap = cap
        self._chunks: list[bytes] = []
        self._size = 0
        self.over = threading.Event()

    def run(self) -> None:
        try:
            while True:
                chunk = self._stream.read1(65536)
                if not chunk:
                    return
                room = self._cap - self._size
                if room > 0:
                    self._chunks.append(chunk[:room])
                    self._size += min(len(chunk), room)
                if len(chunk) > room:
                    self.over.set()
                    return
        except (OSError, ValueError):
            return

    @property
    def data(self) -> bytes:
        return b"".join(self._chunks)


def _feed(stdin, payload: bytes) -> None:
    try:
        stdin.write(payload)
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        with contextlib.suppress(OSError, ValueError):
            stdin.close()


def _kill(proc: subprocess.Popen) -> None:
    """Kill the jail: bwrap's group; ``--die-with-parent`` and the pid
    namespace take every process inside with it."""
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(OSError):
        proc.kill()


def _tree(pid: int) -> tuple[int, int]:
    from tinyassets.node_sandbox import read_process_tree

    return read_process_tree(pid)


def run_jailed(
    universe_dir: Path,
    inner: Sequence[str],
    *,
    stdin: bytes | None = None,
    limits: ToolLimits = DEFAULT_LIMITS,
    wall_seconds: float | None = None,
    output_bytes: int | None = None,
) -> ToolRun:
    """Run ``inner`` in the universe's tool jail under ``limits``, or refuse."""
    wall = float(wall_seconds if wall_seconds is not None else limits.wall_seconds)
    cap = int(output_bytes if output_bytes is not None else limits.output_bytes)
    cpu = min(int(limits.cpu_seconds), int(wall) + 1)
    limited = _limited(inner, limits, cpu_seconds=cpu)
    root = Path(universe_dir).resolve()
    # The jail itself adds up to three processes (bwrap, its pid-1, prlimit's
    # exec target); the tree cap is the rlimit plus that overhead.
    process_cap = int(limits.processes) + 3
    filter_fd = _seccomp_fd()
    try:
        argv = TOOL_JAIL_ARGV(root, limited, seccomp_fd=filter_fd)
        with _slot(root):
            free = _free_disk(root)
            if 0 <= free < limits.min_free_disk_bytes:
                raise UniverseToolError(
                    "the shared disk is nearly full, so the tool jail will not start; "
                    "nothing ran"
                )
            return _supervise(
                argv, root, filter_fd, stdin=stdin, limits=limits, wall=wall, cap=cap,
                process_cap=process_cap,
            )
    finally:
        os.close(filter_fd)


def _supervise(
    argv: list[str], root: Path, filter_fd: int, *, stdin: bytes | None,
    limits: ToolLimits, wall: float, cap: int, process_cap: int,
) -> ToolRun:
    """Start the jail and watch it until it ends or a limit kills it."""
    started = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603 - argv is built above, never a shell string
        argv,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin"},
        cwd="/",
        close_fds=True,
        pass_fds=(filter_fd,),
        start_new_session=True,
    )
    out = _Drain(proc.stdout, cap + len(_LIMITS_MARK))
    err = _Drain(proc.stderr, 16 * 1024)
    out.start()
    err.start()
    feeder = None
    if stdin is not None:
        feeder = threading.Thread(target=_feed, args=(proc.stdin, stdin), daemon=True)
        feeder.start()
    killed = None
    try:
        killed = _watch(proc, out, root, limits=limits, wall=wall,
                        process_cap=process_cap, started=started)
    finally:
        try:
            proc.wait(timeout=_KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _kill(proc)
            proc.wait(timeout=_KILL_GRACE_SECONDS)
        out.join(timeout=_KILL_GRACE_SECONDS)
        err.join(timeout=_KILL_GRACE_SECONDS)
        if feeder is not None:
            feeder.join(timeout=_KILL_GRACE_SECONDS)
    if killed is None and out.over.is_set():
        killed = "output_limit"
    elapsed = time.monotonic() - started
    data = out.data
    if not data.startswith(_LIMITS_MARK):
        detail = err.data.decode("utf-8", "replace").strip()[-400:]
        raise UniverseToolError(
            "the tool jail did not start under its resource limits; nothing ran"
            + (f" ({detail})" if detail else "")
        )
    return ToolRun(
        exit_code=proc.returncode,
        output=data[len(_LIMITS_MARK):],
        killed=killed,
        elapsed=elapsed,
    )


def _watch(
    proc: subprocess.Popen, out: _Drain, root: Path, *, limits: ToolLimits,
    wall: float, process_cap: int, started: float,
) -> str | None:
    """Poll the running jail; kill it and name the limit the moment one breaks."""
    next_tree = 0.0
    while proc.poll() is None:
        now = time.monotonic()
        killed = None
        if now - started > wall:
            killed = "timeout"
        elif out.over.is_set():
            killed = "output_limit"
        elif now >= next_tree:
            next_tree = now + 0.2
            count, rss = _tree(proc.pid)
            free = _free_disk(root)
            if count > process_cap:
                killed = "process_limit"
            elif rss > limits.tree_memory_bytes:
                killed = "memory_limit"
            elif 0 <= free < limits.min_free_disk_bytes:
                killed = "disk_limit"
        if killed:
            _kill(proc)
            return killed
        time.sleep(_POLL_SECONDS)
    return None


#: Runs one jailed call. Substituted by tests that need no real jail.
RUNNER: Callable[..., ToolRun] = run_jailed


# ── the four tools ──────────────────────────────────────────────────────────


def _jail_path(path: str) -> str:
    """The path as the jail sees it: relative paths are under ``/u``.

    No containment check here on purpose: the jail is the boundary, and a
    path outside ``/u`` simply does not exist inside it.
    """
    raw = (path or "").strip()
    if not raw:
        raise UniverseToolError("a path is required")
    if "\x00" in raw:
        raise UniverseToolError("a path may not contain a NUL byte")
    candidate = PurePosixPath(raw)
    if not candidate.is_absolute():
        candidate = PurePosixPath(MOUNT_POINT) / candidate
    return str(candidate)


def _text(data: bytes) -> str:
    return data.decode("utf-8", "replace")


_SIGXCPU = getattr(signal, "SIGXCPU", 24)


def _trailer(run: ToolRun, limits: ToolLimits, wall: float) -> str:
    if run.killed == "timeout":
        return f"[killed: ran longer than {wall:g}s]"
    if run.killed == "output_limit":
        return f"[killed: output passed {limits.output_bytes} bytes]"
    if run.killed == "memory_limit":
        return f"[killed: the jail's processes used more than {limits.tree_memory_bytes} bytes]"
    if run.killed == "process_limit":
        return f"[killed: more than {limits.processes} processes]"
    if run.killed == "disk_limit":
        return "[killed: the shared disk was nearly full]"
    if run.exit_code == 128 + _SIGXCPU:
        return "[killed: cpu time limit]"
    return f"[exit code {run.exit_code}]"


def read_file(
    universe_dir: Path, path: str, offset: int = 0, limit: int = 0,
    *, limits: ToolLimits = DEFAULT_LIMITS,
) -> str:
    """Up to ``limit`` lines of a file from line ``offset`` (1-based)."""
    target = _jail_path(path)
    start = max(1, int(offset or 1))
    count = int(limit) if limit and int(limit) > 0 else DEFAULT_READ_LINES
    script = (
        '[ -e "$1" ] || { echo "no such file: $1"; exit 1; }; '
        'if [ -d "$1" ]; then ls -la -- "$1"; exit $?; fi; '
        'tail -n "+$2" -- "$1" | head -n "$3"'
    )
    run = RUNNER(
        universe_dir, ["/bin/sh", "-c", script, "sh", target, str(start), str(count)],
        limits=limits,
    )
    if run.killed == "output_limit":
        return (
            _text(run.output)
            + f"\n[truncated at {limits.output_bytes} bytes; read a smaller range "
            "with offset and limit]"
        )
    if run.killed or run.exit_code != 0:
        return f"error: {_text(run.output).strip() or _trailer(run, limits, limits.wall_seconds)}"
    return _text(run.output)


def write_file(
    universe_dir: Path, path: str, content: str,
    *, limits: ToolLimits = DEFAULT_LIMITS,
) -> str:
    """Create or replace a file, making parent directories."""
    target = _jail_path(path)
    payload = (content or "").encode("utf-8")
    if len(payload) > MAX_WRITE_BYTES:
        raise UniverseToolError(f"content is over the {MAX_WRITE_BYTES}-byte write limit")
    script = 'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"'
    run = RUNNER(
        universe_dir, ["/bin/sh", "-c", script, "sh", target],
        stdin=payload, limits=limits,
    )
    if run.killed or run.exit_code != 0:
        return f"error: {_text(run.output).strip() or _trailer(run, limits, limits.wall_seconds)}"
    return f"wrote {len(payload)} bytes to {target}"


def edit_file(
    universe_dir: Path, path: str, old_text: str, new_text: str,
    *, limits: ToolLimits = DEFAULT_LIMITS,
) -> str:
    """Replace the one exact occurrence of ``old_text`` with ``new_text``."""
    target = _jail_path(path)
    if not old_text:
        raise UniverseToolError("old_text is required: the exact passage to replace")
    run = RUNNER(
        universe_dir,
        ["/bin/sh", "-c", '[ -f "$1" ] || { echo "no such file: $1"; exit 1; }; cat -- "$1"',
         "sh", target],
        limits=limits, output_bytes=MAX_EDIT_BYTES,
    )
    if run.killed == "output_limit":
        return f"error: {target} is over the {MAX_EDIT_BYTES}-byte edit limit; use bash"
    if run.killed or run.exit_code != 0:
        return f"error: {_text(run.output).strip() or _trailer(run, limits, limits.wall_seconds)}"
    try:
        current = run.output.decode("utf-8")
    except UnicodeDecodeError:
        return f"error: {target} is not UTF-8 text; use bash"
    found = current.count(old_text)
    if found == 0:
        return f"error: old_text was not found in {target}"
    if found > 1:
        return (
            f"error: old_text matches {found} places in {target}; include more "
            "surrounding text so it matches exactly one"
        )
    written = write_file(
        universe_dir, target, current.replace(old_text, new_text, 1), limits=limits,
    )
    if written.startswith("error:"):
        return written
    return f"edited {target}"


def bash(
    universe_dir: Path, command: str, timeout: float = 0,
    *, limits: ToolLimits = DEFAULT_LIMITS,
) -> str:
    """Run ``command`` with bash in ``/u``; stdout and stderr, then the outcome."""
    if not (command or "").strip():
        raise UniverseToolError("a command is required")
    wall = float(timeout) if timeout and float(timeout) > 0 else limits.wall_seconds
    wall = min(max(wall, 1.0), MAX_BASH_SECONDS)
    shell = _system_binary("bash")
    run = RUNNER(universe_dir, [shell, "-c", command], limits=limits, wall_seconds=wall)
    body = _text(run.output)
    if body and not body.endswith("\n"):
        body += "\n"
    return body + _trailer(run, limits, wall)


# ── the skill index (progressive disclosure) ────────────────────────────────

SKILLS_DIR = "skills"
MAX_SKILLS = 64
_MAX_SKILL_FILE_BYTES = 256 * 1024
_MAX_DESCRIPTION_CHARS = 300
_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _skill_description(raw: bytes) -> str:
    """The frontmatter ``description``, one line, or '' when there is none."""
    import yaml

    text = raw.decode("utf-8", "replace").lstrip("﻿")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end < 0:
        return ""
    try:
        meta = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return ""
    if not isinstance(meta, dict):
        return ""
    description = " ".join(str(meta.get("description") or "").split())
    if len(description) > _MAX_DESCRIPTION_CHARS:
        description = description[: _MAX_DESCRIPTION_CHARS - 1] + "…"
    return description


def skill_index(universe_dir: Path) -> list[tuple[str, str]]:
    """``(name, description)`` for each ``skills/<name>/SKILL.md``.

    Read by the daemon, so every component is opened without following a link
    (a skill file the agent symlinked at another universe is skipped, never
    read). POSIX only; elsewhere the tools cannot run, so there is no index.
    """
    from tinyassets import workspace_fs as fs

    if not getattr(fs, "_POSIX", False):
        return []
    try:
        root_fd = fs.open_dir_nofollow(Path(universe_dir).resolve(strict=True))
    except (OSError, NotImplementedError):
        return []
    skills: list[tuple[str, str]] = []
    try:
        try:
            skills_fd = fs.open_subdir_nofollow(root_fd, SKILLS_DIR)
        except (OSError, NotImplementedError):
            return []
        try:
            names = sorted(os.listdir(skills_fd))
            for name in names:
                if len(skills) >= MAX_SKILLS:
                    break
                if not _SKILL_NAME.match(name):
                    continue
                try:
                    raw = fs.read_regular_file_beneath(
                        skills_fd, f"{name}/SKILL.md", max_bytes=_MAX_SKILL_FILE_BYTES,
                    )
                except (OSError, NotImplementedError):
                    continue
                description = _skill_description(raw)
                if description:
                    skills.append((name, description))
        finally:
            os.close(skills_fd)
    finally:
        os.close(root_fd)
    return skills


_HARNESS_HEAD = (
    "# My folder and my four tools\n"
    "My universe is a folder, mounted at /u, and I work in it with four tools: "
    "`read` (a file, or a range of its lines), `write` (create or replace a "
    "file), `edit` (replace one exact passage in a file) and `bash` (a shell in "
    "/u with no network and bounded memory, processes and time, so long-running "
    "work does not belong there). Relative paths are under /u. Nothing outside "
    "/u is mine or reachable, and `.runtime/` is the platform's.\n"
    "A skill is `skills/<name>/SKILL.md`, starting with frontmatter that has a "
    "`name:` and a one-line `description:` of when to use it. Only the list "
    "below is in this prompt: when a request matches a skill, I `read` its "
    "SKILL.md and follow it. I make or change my own skills by writing that "
    "file; a skill takes effect from my next turn.\n"
    "## My skills\n"
)


def harness_prompt(universe_dir: Path) -> str:
    """The base harness section: the four tools, the folder, the skill index."""
    skills = skill_index(universe_dir)
    if not skills:
        return _HARNESS_HEAD + "(none yet)"
    lines = [
        f"- `{name}`: {description} ({SKILLS_DIR}/{name}/SKILL.md)"
        for name, description in skills
    ]
    return _HARNESS_HEAD + "\n".join(lines)
