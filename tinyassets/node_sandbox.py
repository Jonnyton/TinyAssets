"""Sandboxed execution runtime for user-contributed LangGraph nodes.

This module is the production executor for ``source_code`` nodes
(OpenSpec change ``sandboxed-code-node``, design D2). A node runs as a child
Python process that receives **data and no credentials**:

  - **OS isolation, chosen by injection.** :class:`BwrapLauncher` wraps the
    child in ``bwrap``: ``--unshare-all`` (no network), ``--clearenv``,
    ``--die-with-parent``, ``--new-session``, ``--chdir /tmp``, a private
    ``--tmpfs /tmp`` as ``HOME``, and read-only binds of ``/usr /bin /lib
    /lib64`` plus the interpreter prefix. **No** ``--share-net``, **no**
    ``/data``, no universe root, no credential mounts. The parent launches
    with ``close_fds=True``, pipes only, a private cwd and an env
    built from scratch.
  - **No env switch.** This module reads no env var at
    all. :class:`PlainSubprocessLauncher` (no isolation) exists for the test
    suite and is reachable only by passing ``NodeSandbox(launcher=...)`` or
    by substituting :data:`DEFAULT_LAUNCHER_FACTORY`. With no launcher
    given, the factory probes for bwrap and raises
    :class:`~tinyassets.providers.base.SandboxUnavailableError` when it is
    absent — a code node never runs unsandboxed by configuration.
  - **Restricted state access.** Only declared ``input_keys`` reach the node.
    The return comes back **unfiltered**, with ``undeclared`` naming the keys
    outside ``output_keys``: the compiler applies its single-merge-writer
    guard to the full dict before dropping them.
  - **Import allowlisting** (:data:`ALLOWED_IMPORTS`) and source denylisting
    (:data:`FORBIDDEN_PATTERNS`) as defence in depth. ``requests``/``httpx``
    are *not* allowlisted: the child has no network by design. Only imports
    the node asks for directly are name-checked — an allowlisted module's own
    module-level imports are permitted (``base64`` needs ``binascii``), and
    no node code runs at that depth. A *lazy* runtime import of a
    non-allowlisted internal still fails loudly (``datetime.strptime`` →
    ``_strptime``).
  - **Resource limits first thing in the child**, before the message is read
    at all, so they hold under bwrap and against a hostile payload:
    ``RLIMIT_AS`` 512 MiB, ``RLIMIT_CPU`` ``ceil(timeout) + 1``,
    ``RLIMIT_FSIZE`` 16 MiB, ``RLIMIT_NOFILE`` 64, each set *and read back*.
    Under a launcher whose :attr:`~Launcher.requires_rlimits` is true (the
    jail) a limit that cannot be applied **fails the node** before any node
    code runs; otherwise the failures land in ``warning``. Never silently
    skipped. No ``preexec_fn`` anywhere — the daemon is multithreaded.
  - **Caps enforced while reading.** stdout and stderr are drained
    incrementally; the moment stdout passes ``max_output_bytes`` (8 MiB) or
    stderr passes :data:`MAX_STDERR_BYTES` (64 KiB) the child is killed and
    the node fails "output too large". The stdin message must be ≤ 16 MiB.
  - **The result protocol cannot be forged.** Inside the child ``sys.stdout``
    is replaced by a bounded in-memory buffer before the node's code is
    executed; the result JSON is written to the real descriptor only, at the
    end. Whatever the node prints becomes ``stdout_tail`` evidence and
    nothing more.
  - **`invoke_mcp_action` is a synchronous RPC, never an authority.** The
    child writes ``{"rpc": {"id", "action", "kwargs"}}`` on its stdout and
    blocks on stdin for ``{"id", "result"}`` / ``{"id", "error"}``; the
    parent performs the action through the caller-supplied ``invoke`` under
    the run's authority. The child never holds a credential or a handle.
    :data:`MAX_RPC_CALLS` per run, :data:`MAX_RPC_REPLY_BYTES` per reply,
    and the wall-clock timeout covers time spent blocked in a call.

Node contract — the source defines ``run`` taking one or two positional
arguments::

    def run(state, effects=None) -> dict

``state`` is the declared ``input_keys`` slice of graph state; ``effects`` is
``{node_id: {"status": int | None, "body": Any}}`` for the node's graph
ancestors. **Never headers** — a ``Set-Cookie`` there is a credential. The
return must be a ``dict``.

Usage::

    sandbox = NodeSandbox()                       # production: bwrap or raise
    result = sandbox.run_sync(
        node_id="edit-readme",
        source_code="def run(state, effects): ...",
        input_state={"content": "...", "facts": [...]},
        input_keys=["content", "facts"],
        output_keys=["content", "sha"],
        timeout=30.0,
        effects={"fetch": {"status": 200, "body": {...}}},
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from tinyassets.providers.base import (
    SandboxUnavailableError,
    probe_sandbox_available,
)

logger = logging.getLogger("universe_server.sandbox")

#: Sandbox availability probe. Module-level so tests can substitute it —
#: production always resolves the real bwrap probe.
_probe = probe_sandbox_available

#: Maximum encoded stdin message (design D2).
MAX_INPUT_BYTES = 16 * 1024 * 1024

#: Default maximum stdout — the transformed-body cap (design D2).
MAX_OUTPUT_BYTES = 8 * 1024 * 1024

#: Maximum stderr before the child is killed.
MAX_STDERR_BYTES = 64 * 1024

#: Bound on what the node's own ``print()`` calls may retain, in the child.
MAX_USER_PRINT_BYTES = 64 * 1024

#: How many ``invoke_mcp_action`` round-trips one node may make.
MAX_RPC_CALLS = 32

#: Bound on a single RPC reply written back to the child.
MAX_RPC_REPLY_BYTES = 1024 * 1024

#: Characters of stdout/stderr kept as evidence on every result.
TAIL_CHARS = 2048

#: Paths that must never be bound into the child, whatever the interpreter
#: layout looks like. ``/data`` is the universe data dir.
_NEVER_BIND_PREFIXES = ("/data",)

#: Where a workspace generation is bound inside the jail. A constant, not a
#: parameter: the runner resolves every ``ws`` path beneath the root the
#: launcher reports, and only the tests-only launcher reports anything else.
WORKSPACE_MOUNT_POINT = "/workspace"

#: Workspace caps (design D2 / graph-execution-substrate): per NODE, not per
#: command, so a loop of small commands is bounded by the same numbers.
MAX_WORKSPACE_COMMANDS = 64
MAX_WORKSPACE_OUTPUT_BYTES = 1024 * 1024
MAX_WORKSPACE_READ_BYTES = 1024 * 1024
MAX_WORKSPACE_GLOB_RESULTS = 10_000
WORKSPACE_TAIL_BYTES = 64 * 1024
#: Bounded wait for the jail to die after SIGKILL before we fail loudly.
JAIL_EXIT_GRACE_SECONDS = 5.0

#: Read-only system binds, when they exist on the host.
_SYSTEM_ROBINDS = ("/usr", "/bin", "/lib", "/lib64")

#: PATH used only to resolve ``bwrap`` itself, never inherited from the host
#: and never visible inside the jail (``--clearenv`` sets the child's own).
_LAUNCH_PATH = "/usr/bin:/bin"

_READ_CHUNK = 65536
_POLL_SECONDS = 0.02


# ═══════════════════════════════════════════════════════════════════════════
# Execution Result
# ═══════════════════════════════════════════════════════════════════════════


_PROC_FD_BIND = re.compile(r"^/proc/self/fd/([0-9]+)$")


class SandboxTerminationError(RuntimeError):
    """The jail did not die when we killed it.

    Not a node failure: the OS boundary is what failed. A jail that survives
    SIGKILL is holding a workspace and possibly a running command, so this is
    loud by design rather than folded into a node error.
    """


@dataclass(frozen=True)
class WorkspaceLimits:
    """Per-NODE workspace caps and the rlimit profile a workspace node runs under.

    ``command_timeout_s`` of ``None`` means each command may use whatever is
    left of the node timeout; a command never outlives the node, because the
    parent would kill the jail anyway and a shorter budget fails legibly.
    """

    max_commands: int = MAX_WORKSPACE_COMMANDS
    max_output_bytes: int = MAX_WORKSPACE_OUTPUT_BYTES
    command_timeout_s: float | None = None
    max_read_bytes: int = MAX_WORKSPACE_READ_BYTES
    max_glob_results: int = MAX_WORKSPACE_GLOB_RESULTS
    tail_bytes: int = WORKSPACE_TAIL_BYTES
    rlimit_as: int = 1536 * 1024 * 1024
    rlimit_nproc: int = 128
    rlimit_nofile: int = 1024
    rlimit_fsize: int = 512 * 1024 * 1024
    rlimit_core: int = 0

    def rlimit_profile(self) -> dict[str, int]:
        """The limits the child applies before it reads its message."""
        return {
            "RLIMIT_AS": self.rlimit_as,
            "RLIMIT_CORE": self.rlimit_core,
            "RLIMIT_FSIZE": self.rlimit_fsize,
            "RLIMIT_NOFILE": self.rlimit_nofile,
            "RLIMIT_NPROC": self.rlimit_nproc,
        }

    def as_message(self) -> dict[str, Any]:
        """The caps the runner enforces, as they cross the pipe."""
        return {
            "max_commands": self.max_commands,
            "max_output_bytes": self.max_output_bytes,
            "command_timeout_s": self.command_timeout_s,
            "max_read_bytes": self.max_read_bytes,
            "max_glob_results": self.max_glob_results,
            "tail_bytes": self.tail_bytes,
        }


@dataclass(frozen=True)
class WorkspaceMount:
    """One checkout generation, bound read-write at :data:`WORKSPACE_MOUNT_POINT`.

    Resolved only through the run's effect chain (design D2); it never travels
    through state, ``$ta.ref`` or JSON, which is why this is an object and not
    a string a branch could supply.
    """

    bind_source: str
    limits: WorkspaceLimits = field(default_factory=WorkspaceLimits)
    #: Descriptors the child must inherit. When ``bind_source`` is
    #: ``/proc/self/fd/<n>`` this holds ``n``: the bind then resolves in the
    #: bwrap process, which inherited it, to the directory the fd was opened
    #: on -- not to whatever the path names by the time bwrap looks.
    pass_fds: tuple[int, ...] = ()
    #: Roots a PLAIN path may sit beneath. The descriptor form needs none:
    #: its identity is the fd, not the string.
    allowed_roots: tuple[str, ...] = ()


@dataclass
class SandboxResult:
    """Result of a sandboxed node execution.

    ``output_state`` is what ``run()`` returned, **unfiltered**;
    ``undeclared`` names the keys outside the node's ``output_keys`` so the
    compiler can apply its merge-writer guard before dropping them.
    """

    node_id: str
    success: bool
    output_state: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    stdout_tail: str = ""
    stderr_tail: str = ""
    warning: str = ""
    undeclared: list[str] = field(default_factory=list)
    #: A ``ws.run`` command outlived its budget. Carried as a flag, not a
    #: message the caller has to grep, so the compiler can classify it.
    workspace_timeout: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "success": self.success,
            "output_state": self.output_state,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "warning": self.warning,
            "undeclared": list(self.undeclared),
        }


def _tail(text: str) -> str:
    """Last :data:`TAIL_CHARS` characters of *text*."""
    return text[-TAIL_CHARS:] if text else ""


# ═══════════════════════════════════════════════════════════════════════════
# Import Allowlist
# ═══════════════════════════════════════════════════════════════════════════

# Modules that user-contributed nodes are allowed to import.
# `requests`/`httpx` were removed by design D2: the child has no network, so
# an HTTP client in here would only ever fail confusingly. Authenticated
# calls belong to effect nodes, whose results arrive as `effects`.
ALLOWED_IMPORTS = {
    # Standard library — safe subset
    "json", "re", "math", "statistics", "datetime", "collections",
    "dataclasses", "typing", "textwrap", "difflib", "hashlib",
    "urllib.parse", "pathlib", "functools", "itertools", "copy",
    "string", "enum", "abc", "decimal", "fractions",
    # Text/bytes handling for the fetch → edit → write shape
    "base64", "io", "csv", "html", "unicodedata", "zlib", "struct",
    "operator", "heapq", "bisect", "time",
}

# Patterns that are never allowed in node source code
FORBIDDEN_PATTERNS = [
    "os.system",
    "os.popen",
    "os.exec",
    "os.spawn",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.makedirs",
    "os.rename",
    "subprocess",
    "shutil.rmtree",
    "shutil.move",
    "__import__",
    "eval(",
    "exec(",
    "compile(",
    "open(",
    "builtins",
    "globals(",
    "locals(",
    "breakpoint(",
    "importlib",
    "ctypes",
    "multiprocessing",
    "threading.Thread",
    "signal",
    "socket",
    "pickle",
]


# ═══════════════════════════════════════════════════════════════════════════
# Sandbox Runner Script
# ═══════════════════════════════════════════════════════════════════════════

# Applied inside the child, before anything else. Kept as source text rather
# than a function so the tests compile and drive *this* text with a fake
# `resource` module — the code under test and the code that runs are the same
# string, on every platform.
_RLIMIT_HELPER = '''
def _apply_rlimits(resource_module, timeout, profile=None):
    """Apply the code-node resource limits; return a list of failures.

    Every limit is set AND read back: a `setrlimit` that raises, a hard
    ceiling below the target, and a silently ignored call are all failures.
    The caller decides whether a failure is fatal (bwrap: yes) or a warning
    (the tests-only launcher on a platform with no `resource`).
    """
    if resource_module is None:
        return ["all limits (this platform has no 'resource' module)"]

    try:
        cpu_seconds = int(timeout) + (0 if timeout == int(timeout) else 1) + 1
    except Exception:
        cpu_seconds = 31

    failures = []
    if profile:
        wanted = [(str(k), int(v)) for k, v in sorted(profile.items())]
        if not any(name == "RLIMIT_CPU" for name, _v in wanted):
            wanted.append(("RLIMIT_CPU", cpu_seconds))
    else:
        wanted = [
            ("RLIMIT_AS", 512 * 1024 * 1024),
            ("RLIMIT_CPU", cpu_seconds),
            ("RLIMIT_FSIZE", 16 * 1024 * 1024),
            ("RLIMIT_NOFILE", 64),
        ]
    for name, want in wanted:
        try:
            res = getattr(resource_module, name)
            _soft, hard = resource_module.getrlimit(res)
            if hard == resource_module.RLIM_INFINITY:
                new_hard = want
            else:
                new_hard = min(want, hard)
            target = min(want, new_hard)
            resource_module.setrlimit(res, (target, new_hard))
            applied = resource_module.getrlimit(res)[0]
            if applied != target:
                failures.append(
                    f"{name} (asked for {target}, reads {applied})"
                )
        except Exception as exc:
            failures.append(f"{name} ({type(exc).__name__}: {exc})")
    return failures
'''


# The `ws` capability. Lives in the RUNNER's globals, never the node's: the node
# executes in its own namespace dict, so it cannot reach `os` or `subprocess`
# through `ws` even though `ws` uses them. Every import this needs happens at the
# top of the runner, BEFORE the import allowlist is installed, so the allowlist
# still refuses the same names to node code.
_WORKSPACE_HELPER = '''
class _ws_internals(object):
    """Raise the import depth for the duration of a ws call.

    ``subprocess.Popen`` imports lazily on POSIX (``warnings`` on the first
    call), and those imports happen while the node's allowlist is installed,
    at depth 0 -- so without this EVERY ws.run raises ImportError on Linux
    while passing on Windows, whose Popen takes another path. This is the
    same rule the allowlist already applies to an allowlisted module's own
    imports: no node code runs at depth > 0, so it is not a bypass. A ws
    method takes data, never a callable, so nothing of the node's runs here.
    """

    def __enter__(self):
        _import_depth[0] += 1
        return self

    def __exit__(self, kind, value, trace):
        _import_depth[0] -= 1
        return False


def _ws_resolve(root, relpath, kind):
    """One rule for every path ws touches: relative, no '..', beneath the root."""
    if not isinstance(relpath, str) or not relpath.strip():
        raise ValueError("workspace " + kind + " must be a non-empty string")
    if chr(0) in relpath:
        raise ValueError("workspace " + kind + " contains a NUL byte")
    norm = relpath.replace(chr(92), "/")
    if norm.startswith("/"):
        raise ValueError("workspace " + kind + " must be relative, not absolute: " + relpath)
    if len(norm) > 1 and norm[1] == ":":
        raise ValueError("workspace " + kind + " must be relative, not a drive path: " + relpath)
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise ValueError("workspace " + kind + " may not contain '..': " + relpath)
    target = os.path.realpath(os.path.join(root, *parts)) if parts else root
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("workspace " + kind + " escapes the workspace: " + relpath)
    return target


class _WorkspaceTail(object):
    """Incremental bounded drain: keeps the last `cap` bytes, counts the rest."""

    def __init__(self, stream, cap):
        self._stream = stream
        self._cap = cap
        self._chunks = []
        self._held = 0
        self.total = 0
        self.thread = threading.Thread(target=self._drain)
        self.thread.daemon = True

    def _drain(self):
        try:
            while True:
                chunk = self._stream.read(65536)
                if not chunk:
                    break
                self.total += len(chunk)
                self._chunks.append(chunk)
                self._held += len(chunk)
                while self._held > self._cap and len(self._chunks) > 1:
                    self._held -= len(self._chunks.pop(0))
        except Exception:
            pass
        finally:
            try:
                self._stream.close()
            except Exception:
                pass

    def text(self):
        data = b"".join(self._chunks)[-self._cap:]
        return data.decode("utf-8", "replace")

    def truncated(self):
        return self.total > self._cap


def _make_workspace(conf, remaining):
    """Return the `ws` object bound to one workspace root."""
    root = os.path.realpath(conf["root"])
    limits = conf.get("limits") or {}
    max_commands = int(limits.get("max_commands", 64))
    max_output = int(limits.get("max_output_bytes", 1048576))
    max_read = int(limits.get("max_read_bytes", 1048576))
    max_glob = int(limits.get("max_glob_results", 10000))
    tail_cap = int(limits.get("tail_bytes", 65536))
    default_timeout = limits.get("command_timeout_s")
    counters = {"commands": 0, "bytes": 0}

    class _Workspace(object):
        """The checked-out project, and nothing else."""

        path = root

        def run(self, argv, timeout=None, cwd=None, env=None):
            if not isinstance(argv, (list, tuple)) or not argv:
                raise ValueError("ws.run needs a non-empty argv list")
            argv = list(argv)
            for item in argv:
                if not isinstance(item, str):
                    raise ValueError("ws.run argv must be a list of str")
                if chr(0) in item:
                    raise ValueError("ws.run argv contains a NUL byte")
            if counters["commands"] >= max_commands:
                raise RuntimeError(
                    "workspace limit: at most %d commands per node" % max_commands
                )
            counters["commands"] += 1

            with _ws_internals():
                work = root if cwd is None else _ws_resolve(root, cwd, "cwd")
            child_env = {"HOME": "/tmp", "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
            for key, value in sorted((env or {}).items()):
                if not isinstance(key, str) or not _WS_ENV_NAME.match(key):
                    raise ValueError("ws.run env name is not an env name: %r" % (key,))
                if not isinstance(value, str) or chr(0) in value:
                    raise ValueError("ws.run env value must be a NUL-free str")
                child_env[key] = value

            budget = remaining()
            if default_timeout is not None:
                budget = min(budget, float(default_timeout))
            if timeout is not None:
                budget = min(budget, float(timeout))
            if budget <= 0:
                raise RuntimeError("workspace limit: no time left in the node budget")

            with _ws_internals():
                return self._spawn(argv, work, child_env, budget)

        def _spawn(self, argv, work, child_env, budget):
            popen_kwargs = {}
            if hasattr(os, "setsid"):
                popen_kwargs["start_new_session"] = True
            elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            proc = subprocess.Popen(
                argv,
                cwd=work,
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                **popen_kwargs
            )
            out = _WorkspaceTail(proc.stdout, tail_cap)
            err = _WorkspaceTail(proc.stderr, tail_cap)
            out.thread.start()
            err.thread.start()
            timed_out = False
            try:
                proc.wait(timeout=budget)
            except subprocess.TimeoutExpired:
                timed_out = True
                _ws_kill_group(proc)
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
            out.thread.join(timeout=2.0)
            err.thread.join(timeout=2.0)

            if timed_out:
                # The runner exits here rather than returning: the parent must
                # SIGKILL the tracked supervisor so the whole PID namespace --
                # including anything double-forked -- dies with it.
                _ws_exit_on_timeout(argv, budget, out.text(), err.text())

            result = {
                "returncode": proc.returncode,
                "stdout_tail": out.text(),
                "stderr_tail": err.text(),
                "truncated": bool(out.truncated() or err.truncated()),
            }
            counters["bytes"] += len(result["stdout_tail"]) + len(result["stderr_tail"])
            if counters["bytes"] > max_output:
                raise RuntimeError(
                    "workspace limit: returned output passed %d bytes for this node"
                    % max_output
                )
            return result

        def read(self, relpath, max_bytes=None):
            cap = max_read if max_bytes is None else int(max_bytes)
            with _ws_internals():
                target = _ws_resolve(root, relpath, "path")
                flags = (
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_BINARY", 0)
                )
                handle = os.open(target, flags)
                try:
                    data = b""
                    while len(data) <= cap:
                        chunk = os.read(handle, 65536)
                        if not chunk:
                            break
                        data += chunk
                finally:
                    os.close(handle)
            if len(data) > cap:
                raise RuntimeError(
                    "workspace limit: %s is larger than %d bytes" % (relpath, cap)
                )
            return data.decode("utf-8", "replace")

        def write(self, relpath, text):
            if not isinstance(text, str):
                raise TypeError("ws.write needs str, got %s" % type(text).__name__)
            with _ws_internals():
                target = _ws_resolve(root, relpath, "path")
                if target == root:
                    raise ValueError(
                        "ws.write needs a file path, not the workspace root"
                    )
                parent = os.path.dirname(target)
                if parent and parent != root and not os.path.isdir(parent):
                    os.makedirs(parent)
                data = text.encode("utf-8")
                flags = (
                    os.O_WRONLY | os.O_CREAT | os.O_TRUNC
                    | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
                )
                handle = os.open(target, flags, 384)
                try:
                    written = 0
                    while written < len(data):
                        written += os.write(handle, data[written:])
                finally:
                    os.close(handle)
                return len(data)

        def glob(self, pattern):
            if not isinstance(pattern, str) or not pattern.strip():
                raise ValueError("ws.glob needs a non-empty pattern")
            norm = pattern.replace(chr(92), "/")
            if norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
                raise ValueError("ws.glob pattern must be relative: " + pattern)
            if any(p == ".." for p in norm.split("/")):
                raise ValueError("ws.glob pattern may not contain '..': " + pattern)
            found = []
            with _ws_internals():
                pattern_path = os.path.join(root, *norm.split("/"))
                for hit in glob.iglob(pattern_path, recursive=True):
                    real = os.path.realpath(hit)
                    # A link that leaves the workspace is not in the workspace.
                    if real != root and not real.startswith(root + os.sep):
                        continue
                    found.append(os.path.relpath(real, root).replace(os.sep, "/"))
                    if len(found) >= max_glob:
                        break
            return sorted(set(found))

        def bundle(self, commit_sha):
            if not isinstance(commit_sha, str) or not _WS_SHA.match(commit_sha):
                raise ValueError("ws.bundle needs a 40-character hex commit sha")
            with _ws_internals():
                export_dir = _ws_resolve(root, ".tiny-export", "path")
                if not os.path.isdir(export_dir):
                    os.makedirs(export_dir)
                relative = ".tiny-export/" + commit_sha + ".bundle"
                target = _ws_resolve(root, relative, "path")
            base = ["git", "-c", "core.hooksPath=/dev/null", "--no-replace-objects"]
            steps = [
                base + ["update-ref", "refs/tiny/export", commit_sha],
                ["git", "--no-replace-objects", "bundle", "create", target,
                 "refs/tiny/export"],
            ]
            try:
                for step in steps:
                    outcome = self.run(step)
                    if outcome["returncode"] != 0:
                        raise RuntimeError(
                            "ws.bundle failed (%s): %s"
                            % (step[-1], outcome["stderr_tail"][-500:])
                        )
            finally:
                self.run(base + ["update-ref", "-d", "refs/tiny/export"])
            return relative

    return _Workspace()
'''

# Executed in the child as `python -c <script> <timeout>`. In order:
# 1. Resource limits, before anything is read or parsed.
# 2. Replace sys.stdout with a bounded buffer, so node print() can never
#    reach the descriptor the result protocol uses.
# 3. Read the JSON message from stdin (source + state + effects).
# 4. Restrict imports, execute the node source, call run(state[, effects]).
# 5. Write one result JSON object to the real stdout.

_RUNNER_SCRIPT = textwrap.dedent('''\
    import glob
    import json
    import os
    import re
    import signal
    import subprocess
    import sys
    import threading

    # Imported HERE, at the top, before the allowlist below replaces
    # __import__: `ws` needs them and node code must still be refused them.
    # The node executes in its own namespace dict and never sees these names.
    _WS_ENV_NAME = re.compile("^[A-Z_][A-Z0-9_]*$")
    _WS_SHA = re.compile("^[0-9a-f]{40}$")

    # ---- 1. Resource limits FIRST -----------------------------------------
    # Before the message is read at all: a hostile payload must not get any
    # work done under an unbounded process. argv carries the timeout and
    # whether limits are mandatory, precisely so this runs before stdin.
    try:
        _timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    except Exception:
        _timeout = 30.0
    _require_rlimits = len(sys.argv) > 2 and sys.argv[2] == "1"
    _rlimit_profile = None
    _rlimit_profile_error = None
    if len(sys.argv) > 3 and sys.argv[3]:
        try:
            _rlimit_profile = json.loads(sys.argv[3])
        except Exception as exc:
            _rlimit_profile_error = "rlimit profile is unreadable: %s" % (exc,)

    try:
        import resource as _resource
    except Exception:
        _resource = None

    __RLIMIT_HELPER__

    _ws_start = None
    _ws_real_stdout = None

    def _ws_kill_group(proc):
        killpg = getattr(os, "killpg", None)
        getpgid = getattr(os, "getpgid", None)
        sigkill = getattr(signal, "SIGKILL", None)
        if killpg is not None and getpgid is not None and sigkill is not None:
            try:
                killpg(getpgid(proc.pid), sigkill)
                return
            except Exception:
                pass
        try:
            proc.kill()
        except Exception:
            pass

    def _ws_exit_on_timeout(argv, budget, out_tail, err_tail):
        payload = {
            "success": False,
            "workspace_timeout": True,
            "error": (
                "workspace command timeout: %r exceeded %.3fs"
                % (argv[:4], budget)
            ),
            "user_stdout": _captured.getvalue(),
            "stdout_tail": out_tail[-2048:],
            "stderr_tail": err_tail[-2048:],
        }
        try:
            _ws_real_stdout.write(json.dumps(payload) + "\\n")
            _ws_real_stdout.flush()
        except Exception:
            pass
        # os._exit, not SystemExit: the node's `except BaseException` must not
        # be able to swallow a timeout and keep running in the jail.
        os._exit(4)

    __WORKSPACE_HELPER__

    _rlimit_failures = _apply_rlimits(_resource, _timeout, _rlimit_profile)
    if _rlimit_profile_error:
        _rlimit_failures = [_rlimit_profile_error] + _rlimit_failures
    if _require_rlimits and _rlimit_failures:
        # The OS sandbox demands these limits. Refuse loudly, before the
        # message is parsed and long before any node code runs.
        sys.stdout.write(json.dumps({
            "success": False,
            "error": "rlimits not applied: " + ", ".join(_rlimit_failures),
        }) + "\\n")
        sys.stdout.flush()
        raise SystemExit(3)

    import inspect

    # ---- 2. Protocol integrity --------------------------------------------
    # The node's print() must not be able to write a result. Capture it into
    # a bounded buffer; the real descriptor is written once, at the end.
    _real_stdout = sys.stdout
    _ws_real_stdout = _real_stdout


    class _BoundedStdout:
        def __init__(self, cap):
            self._cap = cap
            self._parts = []
            self._size = 0
            self.dropped = 0

        def write(self, text):
            if not isinstance(text, str):
                text = str(text)
            room = self._cap - self._size
            if room > 0:
                piece = text[:room]
                self._parts.append(piece)
                self._size += len(piece)
                overflow = len(text) - len(piece)
            else:
                overflow = len(text)
            if overflow > 0:
                self.dropped += overflow
            return len(text)

        def writelines(self, lines):
            for line in lines:
                self.write(line)

        def flush(self):
            return None

        def isatty(self):
            return False

        def getvalue(self):
            return "".join(self._parts)


    _captured = _BoundedStdout(MAX_USER_PRINT_BYTES)
    sys.stdout = _captured

    # ---- 3. Message: ONE line. stdin stays open for RPC replies. ----------
    raw = sys.stdin.readline()
    msg = json.loads(raw)

    source_code = msg["source_code"]
    input_state = msg["input_state"]
    effects = msg.get("effects") or {}
    output_keys = msg["output_keys"]
    allowed_imports = set(msg["allowed_imports"])

    # ---- 3b. The workspace capability, when the node declared one --------
    _ws = None
    if isinstance(msg.get("workspace"), dict):
        import time as _ws_time

        _ws_start = _ws_time.monotonic()

        def _ws_remaining():
            # A command never outlives the node: the parent would kill the
            # jail anyway, and a shorter budget makes the failure legible.
            return max(0.0, _timeout - (_ws_time.monotonic() - _ws_start) - 0.5)

        _ws = _make_workspace(msg["workspace"], _ws_remaining)

    # ---- 4. Import allowlist ----------------------------------------------
    _original_import = (
        __builtins__.__import__
        if hasattr(__builtins__, "__import__")
        else __import__
    )

    # Only imports the node source asks for directly are name-checked. An
    # allowlisted module's own module-level imports (base64 -> binascii,
    # statistics -> random) run at depth > 0 and are permitted, otherwise
    # half the allowlist would be unimportable. No node code ever executes
    # at depth > 0, so this is not a bypass.
    _import_depth = [0]

    def _restricted_import(name, *args, **kwargs):
        if _import_depth[0] == 0:
            top_level = name.split(".")[0]
            if top_level not in allowed_imports:
                raise ImportError(
                    f"Import '{name}' is not allowed in sandboxed nodes. "
                    f"Allowed: {sorted(allowed_imports)}"
                )
        _import_depth[0] += 1
        try:
            return _original_import(name, *args, **kwargs)
        finally:
            _import_depth[0] -= 1

    if hasattr(__builtins__, "__import__"):
        __builtins__.__import__ = _restricted_import
    else:
        import builtins
        builtins.__import__ = _restricted_import

    # ---- 4b. invoke_mcp_action: synchronous RPC to the parent -------------
    # The child holds no authority and performs no action. It writes one
    # request line to the real stdout and blocks on stdin for the parent's
    # reply; the parent runs the action under the run's authority. Code
    # needs the answer inside run() (a wiki_read returns the page it then
    # edits), so this is a call, not a deferred queue.
    _rpc = {"next_id": 1, "used": 0}

    def invoke_mcp_action(action_name, **kwargs):
        if not isinstance(action_name, str) or not action_name.strip():
            raise ValueError("invoke_mcp_action requires a non-empty action name")
        try:
            json.dumps(kwargs, default=str)
        except Exception as exc:
            raise ValueError(
                f"invoke_mcp_action kwargs are not JSON-serializable: {exc}"
            )
        if _rpc["used"] >= MAX_RPC_CALLS:
            raise RuntimeError("too many rpc calls")
        _rpc["used"] += 1
        rpc_id = _rpc["next_id"]
        _rpc["next_id"] += 1

        _real_stdout.write(json.dumps(
            {"rpc": {"id": rpc_id, "action": action_name, "kwargs": kwargs}},
            default=str,
        ) + "\\n")
        _real_stdout.flush()

        line = sys.stdin.readline()
        if not line:
            raise RuntimeError("rpc channel closed before a reply arrived")
        try:
            reply = json.loads(line)
        except Exception as exc:
            raise RuntimeError(f"rpc protocol error: unreadable reply ({exc})")
        if not isinstance(reply, dict) or reply.get("id") != rpc_id:
            raise RuntimeError(
                f"rpc protocol error: reply does not answer request {rpc_id}"
            )
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply.get("result")

    # Execute the node source to define the function. A failure here (a
    # blocked module-level import, a raised exception) is the node's failure,
    # reported structurally rather than as a bare traceback on stderr.
    namespace = {
        "__builtins__": __builtins__,
        "invoke_mcp_action": invoke_mcp_action,
    }
    if _ws is not None:
        namespace["ws"] = _ws
    load_error = None
    func = None
    try:
        exec(source_code, namespace)
    except BaseException as e:
        load_error = f"{type(e).__name__}: {e}"

    # Names the runner injected: never mistaken for the node's function.
    _injected = ("invoke_mcp_action", "ws")

    if load_error is None:
        # The node function is `run`, else the last defined callable.
        func = namespace.get("run")
        if func is None:
            for name, obj in reversed(list(namespace.items())):
                if name in _injected:
                    continue
                if callable(obj) and not name.startswith("_"):
                    func = obj
                    break


    def _wants_effects(fn):
        """True when fn takes a second positional argument (the effects map)."""
        try:
            params = list(inspect.signature(fn).parameters.values())
        except (TypeError, ValueError):
            return False
        positional = [
            p for p in params
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        if len(positional) >= 2:
            return True
        if any(p.kind is p.VAR_POSITIONAL for p in params):
            return True
        return any(p.name == "effects" for p in positional)


    if load_error is not None:
        result = {"success": False, "error": load_error}
    elif func is None:
        result = {"success": False, "error": "No callable function found in node source code."}
    else:
        try:
            if _wants_effects(func):
                output = func(input_state, effects)
            else:
                output = func(input_state)
            if not isinstance(output, dict):
                result = {
                    "success": False,
                    "error": f"Node function must return a dict, got {type(output).__name__}",
                }
            else:
                # The full dict goes back: the compiler applies its
                # single-merge-writer guard before dropping undeclared keys.
                undeclared = [k for k in output if k not in output_keys]
                result = {
                    "success": True,
                    "output_state": output,
                    "undeclared": undeclared,
                }
                if undeclared:
                    result["warning"] = f"Undeclared output keys: {undeclared}"
        except BaseException as e:
            result = {"success": False, "error": f"{type(e).__name__}: {e}"}

    # ---- 5. One result object, on the real descriptor ----------------------
    printed = _captured.getvalue()
    if _captured.dropped:
        printed += f"\\n[{_captured.dropped} more characters dropped]"
    result["user_stdout"] = printed

    # Limits that could not be set are a warning here (they are fatal above
    # when the OS sandbox requires them), never silence.
    if _rlimit_failures:
        notice = "resource limits not applied: " + ", ".join(_rlimit_failures)
        existing = result.get("warning") or ""
        result["warning"] = f"{notice}; {existing}" if existing else notice

    try:
        payload = json.dumps(result)
    except BaseException as e:
        payload = json.dumps({
            "success": False,
            "error": f"Node output is not JSON-serializable: {type(e).__name__}: {e}",
            "user_stdout": printed,
        })

    _real_stdout.write(payload + "\\n")
    _real_stdout.flush()
''').replace(
    "MAX_USER_PRINT_BYTES", str(MAX_USER_PRINT_BYTES)
).replace(
    "MAX_RPC_CALLS", str(MAX_RPC_CALLS)
).replace(
    "__RLIMIT_HELPER__", _RLIMIT_HELPER.strip()
).replace(
    "__WORKSPACE_HELPER__", _WORKSPACE_HELPER.strip()
)


# ═══════════════════════════════════════════════════════════════════════════
# bubblewrap argv
# ═══════════════════════════════════════════════════════════════════════════


def _parent_dir(path: str) -> str:
    """Parent directory of *path*, POSIX-first (bwrap paths are POSIX)."""
    if "/" in path:
        return path.rsplit("/", 1)[0]
    return path.rsplit("\\", 1)[0] if "\\" in path else ""


def _covered_by(path: str, bound: list[str]) -> bool:
    """True when *path* is already inside one of the *bound* mounts."""
    for mount in bound:
        if path == mount or path.startswith(mount.rstrip("/") + "/"):
            return True
    return False


def _beneath_any(candidate: str, roots: tuple[str, ...]) -> bool:
    """True when *candidate* is one of *roots* or sits inside one."""
    for root in roots:
        trimmed = root.rstrip("/") or "/"
        if candidate == trimmed or candidate.startswith(trimmed.rstrip("/") + "/"):
            return True
    return False


def _validate_workspace_bind(
    path: str,
    allowed_roots: tuple[str, ...],
    realpath: Callable[[str], str],
    pass_fds: tuple[int, ...] = (),
) -> str:
    """Check the one extra bind against the roots the caller vouches for.

    Two shapes, each vouched for by the thing that identifies it.

    ``/proc/self/fd/<n>`` is a held directory handle: it is admitted only when
    ``n`` is one of the descriptors the child will inherit, because that is
    what makes the string resolve, inside the bwrap process, to the directory
    the fd was opened on. Requiring it to sit beneath a root as well would be
    theatre -- the path names a descriptor, not a location.

    Any other path must be absolute and beneath a root the caller passed in,
    checked literally and after ``realpath``. The roots are what makes
    ``/data/...`` bindable at all -- a universe's workspaces live under it --
    so an empty root tuple refuses everything rather than falling back to the
    never-bind list. A plain path is also swappable by a rename between this
    check and the mount; the descriptor form is the one production uses.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("workspace bind must be a non-empty path")
    if chr(0) in path:
        raise ValueError("workspace bind contains a NUL byte")
    if not path.startswith("/"):
        raise ValueError(
            f"workspace bind must be an absolute POSIX path, got {path!r}"
        )
    if any(part == ".." for part in path.split("/")):
        raise ValueError(f"workspace bind may not contain '..': {path!r}")
    trimmed = path.rstrip("/") or "/"

    handle = _PROC_FD_BIND.match(trimmed)
    if handle is not None:
        number = int(handle.group(1))
        if number not in tuple(pass_fds or ()):
            raise ValueError(
                f"workspace bind {path!r} names a descriptor the child does not "
                f"inherit (pass_fds={tuple(pass_fds or ())!r})"
            )
        return trimmed

    roots = tuple(
        r for r in (allowed_roots or ())
        if isinstance(r, str) and r.startswith("/") and r.strip()
    )
    if not roots:
        raise ValueError(
            "no allowed workspace roots were given: refusing to bind "
            f"{path!r} into the jail"
        )
    if not _beneath_any(trimmed, roots):
        raise ValueError(
            f"workspace bind {path!r} is not beneath an allowed root {roots!r}"
        )
    # A symlinked bind source would otherwise smuggle in any directory.
    resolved = realpath(trimmed)
    if not _beneath_any(resolved, roots):
        raise ValueError(
            f"workspace bind {path!r} resolves to {resolved!r}, "
            f"outside the allowed roots {roots!r}"
        )
    return trimmed


def _bwrap_argv(
    exists: Callable[[str], bool] | None = None,
    bwrap_path: str | None = None,
    realpath: Callable[[str], str] | None = None,
    workspace_bind: str | None = None,
    allowed_workspace_roots: tuple[str, ...] = (),
    pass_fds: tuple[int, ...] = (),
) -> list[str]:
    """Build the bubblewrap prefix for a code-node child process.

    A pure function of the filesystem (``exists`` and ``realpath`` are
    injectable so the POSIX shape is unit-testable on any OS, including a
    Windows dev host where the real ``realpath`` would rewrite ``/data/...``
    into a drive-letter path and hide the very thing under test). The jail
    has **no network** (``--unshare-all`` with no ``--share-net``), **no
    inherited env** (``--clearenv`` plus four explicit ``--setenv``), a private
    writable ``/tmp`` that is both ``HOME`` and the working directory, and
    read-only binds of the system directories plus the interpreter prefix —
    never ``/data``, never a universe root, never a credential mount.

    With *workspace_bind* the jail gains **exactly one** more bind: the
    generation read-write at ``/workspace``, which also becomes the working
    directory in place of ``/tmp``. Nothing else changes -- still no network,
    still no ``/data``, still no credential mount.

    Returns argv ending in ``--``; append the child command.
    """
    if exists is None:
        exists = os.path.exists
    if realpath is None:
        realpath = os.path.realpath
    if bwrap_path is None:
        bwrap_path = shutil.which("bwrap") or "bwrap"

    bind_target = None
    if workspace_bind is not None:
        bind_target = _validate_workspace_bind(
            workspace_bind,
            tuple(allowed_workspace_roots or ()),
            realpath,
            tuple(pass_fds or ()),
        )

    argv: list[str] = [
        bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--clearenv",
        "--setenv", "HOME", "/tmp",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "PYTHONIOENCODING", "utf-8",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
    ]
    if bind_target is None:
        argv.extend(("--chdir", "/tmp"))

    bound: list[str] = []
    for system_path in _SYSTEM_ROBINDS:
        if exists(system_path):
            argv.extend(("--ro-bind", system_path, system_path))
            bound.append(system_path)

    # The interpreter may live outside /usr (a venv, /opt, a symlink farm).
    # Bind the directories it actually needs, read-only.
    for raw, is_file in (
        (sys.executable, True),
        (sys.prefix, False),
        (sys.base_prefix, False),
    ):
        if not raw:
            continue
        resolved = realpath(raw)
        directory = _parent_dir(resolved) if is_file else resolved
        if not directory or directory == "/":
            continue
        if any(
            directory == p or directory.startswith(p.rstrip("/") + "/")
            for p in _NEVER_BIND_PREFIXES
        ):
            continue
        if _covered_by(directory, bound):
            continue
        if not exists(directory):
            continue
        argv.extend(("--ro-bind", directory, directory))
        bound.append(directory)

    if bind_target is not None:
        argv.extend(
            ("--bind", bind_target, WORKSPACE_MOUNT_POINT,
             "--chdir", WORKSPACE_MOUNT_POINT)
        )

    argv.append("--")
    return argv


# ═══════════════════════════════════════════════════════════════════════════
# Launchers — how the child is started, chosen by injection only
# ═══════════════════════════════════════════════════════════════════════════


class Launcher(Protocol):
    """How a code-node child process is started."""

    name: str

    #: True when the child MUST have its resource limits, so a limit that
    #: cannot be set fails the node instead of warning.
    requires_rlimits: bool

    #: True when the child is an OS jail whose tracked process is the
    #: supervisor: killing it ends every descendant, double-forked included.
    is_jail: bool

    def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
        """Full argv for the child, including the interpreter."""

    def env(self, home_dir: str) -> dict[str, str]:
        """Env for the child, built from scratch (never inherited)."""


def _requires_rlimits(launcher: Any) -> bool:
    """Whether *launcher* makes the in-child resource limits mandatory.

    Only the OS jail does. A launcher without the attribute is a test double
    on a platform that may have no ``resource`` module at all; treating it as
    mandatory would fail every Windows test for a limit the plain launcher
    never promised.
    """
    return bool(getattr(launcher, "requires_rlimits", False))


def _is_jail(launcher: Any) -> bool:
    """Whether killing the tracked process ends everything it started."""
    return bool(getattr(launcher, "is_jail", False))


def _launcher_for_workspace(launcher: Any, mount: WorkspaceMount) -> Any:
    """The launcher that actually binds *mount*.

    Without this the mount reached the runner (which was told its root is
    ``/workspace``) but never the launcher, so a default-resolved jail bound
    nothing and the node found an empty mount point.
    """
    specialise = getattr(launcher, "for_workspace", None)
    if specialise is None:
        raise SandboxUnavailableError(
            f"launcher {getattr(launcher, 'name', launcher)!r} cannot host a "
            "workspace: it cannot bind one"
        )
    return specialise(mount)


def _launcher_pass_fds(launcher: Any) -> tuple[int, ...]:
    """Descriptors the child must inherit for its bind to resolve."""
    return tuple(getattr(launcher, "pass_fds", ()) or ())


def _launcher_workspace_root(launcher: Any) -> str:
    """Where the launcher makes the workspace visible to the child."""
    getter = getattr(launcher, "workspace_root", None)
    if getter is None:
        raise SandboxUnavailableError(
            f"launcher {getattr(launcher, 'name', launcher)!r} cannot host a "
            "workspace: it reports no workspace root"
        )
    root = getter()
    if not root:
        raise SandboxUnavailableError(
            f"launcher {getattr(launcher, 'name', launcher)!r} reported an "
            "empty workspace root"
        )
    return str(root)


def _launcher_child_cwd(launcher: Any, work_dir: str) -> str:
    """Host-side cwd for the child (bwrap sets the child's own with --chdir)."""
    getter = getattr(launcher, "child_cwd", None)
    if getter is None:
        return work_dir
    return str(getter(work_dir) or work_dir)


def _terminate_child(
    proc: subprocess.Popen[bytes],
    launcher: Any,
    grace: float = JAIL_EXIT_GRACE_SECONDS,
) -> None:
    """Kill the child and CONFIRM it is gone, or fail loudly.

    For the jail the tracked process is the bubblewrap supervisor and PID 1 of
    the jail's pid namespace: killing it takes the namespace with it, which is
    the only thing that reaches a double-forked ``setsid`` descendant. The
    plain launcher keeps the process-group semantics it always had.
    """
    if _is_jail(launcher):
        try:
            proc.kill()
        except OSError:
            pass
    else:
        _kill_process_tree(proc)
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired as exc:
        raise SandboxTerminationError(
            f"sandbox child {proc.pid} did not exit within {grace}s of SIGKILL"
        ) from exc


class BwrapLauncher:
    """Production launcher: the child runs inside a bubblewrap jail.

    No network, no host env, no ``/data``, no universe root, no
    credential mounts, cwd ``/tmp`` on a private tmpfs.
    """

    name = "bwrap"
    requires_rlimits = True
    is_jail = True

    def __init__(
        self,
        bwrap_path: str | None = None,
        workspace_bind: str | None = None,
        allowed_workspace_roots: tuple[str, ...] = (),
        pass_fds: tuple[int, ...] = (),
    ) -> None:
        self.bwrap_path = bwrap_path
        self.workspace_bind = workspace_bind
        self.allowed_workspace_roots = tuple(allowed_workspace_roots or ())
        self.pass_fds = tuple(pass_fds or ())

    def for_workspace(self, mount: WorkspaceMount) -> BwrapLauncher:
        """A launcher that binds *mount*, inheriting whatever fds it names."""
        return type(self)(
            bwrap_path=self.bwrap_path,
            workspace_bind=mount.bind_source,
            allowed_workspace_roots=(
                mount.allowed_roots or self.allowed_workspace_roots
            ),
            pass_fds=mount.pass_fds,
        )

    def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
        return [
            *_bwrap_argv(
                bwrap_path=self.bwrap_path,
                workspace_bind=self.workspace_bind,
                allowed_workspace_roots=self.allowed_workspace_roots,
                pass_fds=self.pass_fds,
            ),
            sys.executable, "-c", runner_script, *args,
        ]

    def workspace_root(self) -> str:
        """Inside the jail the generation is always at the same place."""
        return WORKSPACE_MOUNT_POINT

    def env(self, home_dir: str) -> dict[str, str]:
        # Only what the parent needs to resolve `bwrap`; `--clearenv` means
        # none of it is visible to the child.
        return {"PATH": _LAUNCH_PATH}


class PlainSubprocessLauncher:
    """**TESTS ONLY.** A bare child process with no OS isolation.

    It has the host's network, the host's filesystem and the host's user.
    The only things bounding it are the import allowlist, the source
    denylist, the in-child resource limits and the parent's caps — none of
    which is an OS boundary. Production never selects this: it is reachable
    only by passing it to :class:`NodeSandbox` or by substituting
    :data:`DEFAULT_LAUNCHER_FACTORY` in a test.
    """

    name = "plain"
    #: Windows has no `resource` module, and this launcher is not the OS
    #: boundary anyway: missing limits are a warning, not a refusal.
    requires_rlimits = False
    #: There is no jail here: killing the child needs the process group.
    is_jail = False

    def __init__(self, workspace_bind: str | None = None) -> None:
        #: Stands in for the bind mount: with no jail there is nothing to
        #: mount, so the directory keeps its real path and the child is
        #: started inside it.
        self.workspace_bind = workspace_bind
        #: No jail, no bind, nothing to inherit.
        self.pass_fds: tuple[int, ...] = ()

    def for_workspace(self, mount: WorkspaceMount) -> PlainSubprocessLauncher:
        """The path, never the descriptor: there is no bind to resolve it in."""
        if mount.bind_source.startswith("/proc/self/fd/"):
            raise SandboxUnavailableError(
                "the tests-only launcher cannot bind a descriptor: it performs "
                "no mount, so /proc/self/fd/<n> would name this process's fd"
            )
        return type(self)(workspace_bind=mount.bind_source)

    def build_argv(self, runner_script: str, args: list[str]) -> list[str]:
        return [sys.executable, "-c", runner_script, *args]

    def workspace_root(self) -> str:
        if not self.workspace_bind:
            raise SandboxUnavailableError(
                "this launcher was built without a workspace bind"
            )
        return os.path.realpath(self.workspace_bind)

    def child_cwd(self, work_dir: str) -> str:
        return self.workspace_bind or work_dir

    def env(self, home_dir: str) -> dict[str, str]:
        # Built from constants: this module reads no env var.
        env = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": "",
            "HOME": home_dir,
        }
        if sys.platform == "win32":
            env["USERPROFILE"] = home_dir
            env["TEMP"] = home_dir
            env["TMP"] = home_dir
        return env


def _default_launcher() -> Launcher:
    """Resolve the production launcher, or refuse to run at all."""
    probe = _probe() or {}
    if probe.get("bwrap_available"):
        return BwrapLauncher()
    reason = probe.get("reason") or "bwrap unavailable"
    raise SandboxUnavailableError(f"code nodes need the OS sandbox: {reason}")


#: Resolves the launcher when ``NodeSandbox`` was given none. Substituted by
#: tests; production never replaces it.
DEFAULT_LAUNCHER_FACTORY: Callable[[], Launcher] = _default_launcher


# ═══════════════════════════════════════════════════════════════════════════
# Child process plumbing
# ═══════════════════════════════════════════════════════════════════════════


def _kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    """Kill *proc* and, where the OS supports it, its whole process group."""
    killpg = getattr(os, "killpg", None)
    getpgid = getattr(os, "getpgid", None)
    sigkill = getattr(signal, "SIGKILL", None)
    if killpg is not None and getpgid is not None and sigkill is not None:
        try:
            killpg(getpgid(proc.pid), sigkill)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


class _BoundedDrain(threading.Thread):
    """Read a child pipe incrementally, keeping at most *cap* bytes.

    The cap is enforced **while reading**: the moment the stream passes it,
    the thread records the breach and stops, so the caller can kill the
    child instead of buffering an unbounded write into the daemon's memory.

    With *on_line*, complete newline-terminated lines are handed to the
    callback as they arrive and only the lines it keeps (returns ``True``
    for) are retained — that is how an RPC request is answered mid-run
    without polluting the result frame. Bytes count toward the cap either
    way, so an RPC flood is still killed.
    """

    def __init__(
        self,
        stream: Any,
        cap: int,
        label: str,
        breaches: list[str],
        on_line: Callable[[bytes], bool] | None = None,
    ) -> None:
        super().__init__(daemon=True, name=f"node-sandbox-{label}")
        self._stream = stream
        self._cap = cap
        self._label = label
        self._breaches = breaches
        self._on_line = on_line
        self._chunks: list[bytes] = []
        self.kept = 0
        self.total = 0

    def _keep(self, data: bytes) -> None:
        if self.kept >= self._cap:
            return
        piece = data[: self._cap - self.kept]
        self._chunks.append(piece)
        self.kept += len(piece)

    def run(self) -> None:
        read = getattr(self._stream, "read1", None) or self._stream.read
        pending = b""
        try:
            while True:
                chunk = read(_READ_CHUNK)
                if not chunk:
                    break
                self.total += len(chunk)
                if self._on_line is None:
                    self._keep(chunk)
                else:
                    pending += chunk
                    while True:
                        cut = pending.find(b"\n")
                        if cut < 0:
                            break
                        line, pending = pending[:cut], pending[cut + 1:]
                        if self._on_line(line):
                            self._keep(line + b"\n")
                if self.total > self._cap:
                    self._breaches.append(self._label)
                    break
        except (OSError, ValueError):
            pass
        finally:
            # A child that exited without a trailing newline still gets its
            # last line looked at.
            if self._on_line is not None and pending and not self._breaches:
                try:
                    if self._on_line(pending):
                        self._keep(pending)
                except Exception:
                    logger.exception("node sandbox: trailing line handler failed")

    @property
    def data(self) -> bytes:
        return b"".join(self._chunks)


def _rpc_reply_line(
    rpc_id: Any,
    action: str,
    kwargs: dict[str, Any],
    invoke: Callable[[str, dict[str, Any]], Any] | None,
) -> str:
    """Answer one ``invoke_mcp_action`` request. Never raises.

    The child is blocked on this reply, so every path — no invoker, a
    raising invoker, an unencodable or oversized result — must produce a
    line. Silence would hang the node until its timeout.
    """
    def _error(message: str) -> str:
        return json.dumps({"id": rpc_id, "error": message})

    if invoke is None:
        return _error("invoke_mcp_action is not available for this node")
    try:
        value = invoke(action, dict(kwargs))
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")
    try:
        encoded = json.dumps({"id": rpc_id, "result": value}, default=str)
    except (TypeError, ValueError) as exc:
        return _error(
            f"action result is not JSON-serializable: {type(exc).__name__}: {exc}"
        )
    if len(encoded.encode("utf-8")) > MAX_RPC_REPLY_BYTES:
        return _error(
            f"action result exceeds the {MAX_RPC_REPLY_BYTES}-byte reply limit"
        )
    return encoded


def _feed_stdin(proc: subprocess.Popen[bytes], payload: bytes) -> None:
    """Write the message line, tolerating a child that died.

    stdin is **not** closed: it is the return path for RPC replies.
    """
    try:
        if proc.stdin is not None:
            proc.stdin.write(payload)
            proc.stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass


def _close_stdin(proc: subprocess.Popen[bytes]) -> None:
    """Close the child's stdin once the run is over."""
    try:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
    except (BrokenPipeError, OSError, ValueError):
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Sandbox
# ═══════════════════════════════════════════════════════════════════════════


class NodeSandbox:
    """Executes user-contributed nodes in isolated subprocesses."""

    def __init__(
        self,
        timeout: float = 30.0,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
        launcher: Launcher | None = None,
    ) -> None:
        self.default_timeout = timeout
        self.max_output_bytes = max_output_bytes
        #: ``None`` means "resolve the production launcher at run time".
        self.launcher = launcher

    def validate_source(self, source_code: str) -> list[str]:
        """Pre-validate source code before execution.

        Returns a list of validation errors (empty if valid).
        """
        errors = []

        for pattern in FORBIDDEN_PATTERNS:
            if pattern in source_code:
                errors.append(f"Forbidden pattern: '{pattern}'")

        # Check for excessive code size
        if len(source_code) > 50_000:
            errors.append("Source code exceeds 50KB limit")

        # Basic syntax check
        try:
            compile(source_code, "<node>", "exec")
        except SyntaxError as exc:
            errors.append(f"Syntax error: {exc}")

        return errors

    def resolve_launcher(self) -> Launcher:
        """The injected launcher, or the production one.

        Raises :class:`SandboxUnavailableError` when there is no OS sandbox
        and none was injected — a code node never runs unsandboxed by
        configuration.
        """
        if self.launcher is not None:
            return self.launcher
        return DEFAULT_LAUNCHER_FACTORY()

    # ---- execution --------------------------------------------------------

    def run_sync(
        self,
        node_id: str,
        source_code: str,
        input_state: dict[str, Any],
        input_keys: list[str],
        output_keys: list[str],
        timeout: float | None = None,
        effects: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        invoke: Callable[[str, dict[str, Any]], Any] | None = None,
        workspace: WorkspaceMount | None = None,
    ) -> SandboxResult:
        """Execute a node in a sandboxed subprocess, synchronously.

        Args:
            node_id: Identifier for logging and tracking.
            source_code: Python source defining ``run(state)`` or
                ``run(state, effects)``.
            input_state: Full graph state (filtered to *input_keys*).
            input_keys: Which state keys the node is allowed to read.
            output_keys: Which state keys the node declares. The return is
                **not** filtered here; keys outside this list come back in
                ``SandboxResult.undeclared``.
            timeout: Max wall-clock seconds for the child, including any
                time it spends blocked on an RPC.
            effects: ``{node_id: {"status", "body"}}`` for the node's graph
                ancestors. Never headers.
            dependencies: Required pip packages (pre-validated).
            invoke: Performs one ``invoke_mcp_action`` under the run's
                authority, ``invoke(action, kwargs)``. Called on the drain
                thread. ``None`` means the node has no action surface and
                every call is answered "not available".
            workspace: The checkout generation to bind at ``/workspace``,
                resolved through the run's effect chain. When set the node
                gets a ``ws`` object and runs under the workspace rlimit
                profile; when ``None`` neither exists.

        Returns:
            SandboxResult with success/failure, output state, and timing.

        Raises:
            SandboxUnavailableError: no OS sandbox and no launcher injected.
        """
        timeout = timeout or self.default_timeout
        start_time = time.monotonic()

        # Pre-validation
        errors = self.validate_source(source_code)
        if errors:
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=f"Validation failed: {'; '.join(errors)}",
            )

        # Filter input state to declared keys only
        filtered_input = {
            k: v for k, v in input_state.items()
            if k in input_keys
        }

        payload: dict[str, Any] = {
            "source_code": source_code,
            "input_state": filtered_input,
            "effects": effects or {},
            "output_keys": output_keys,
            "allowed_imports": sorted(ALLOWED_IMPORTS),
        }
        message = json.dumps(payload, default=str)
        message_bytes = message.encode("utf-8")
        if len(message_bytes) > MAX_INPUT_BYTES:
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=(
                    f"input too large: {len(message_bytes)} bytes exceeds the "
                    f"{MAX_INPUT_BYTES}-byte sandbox message limit"
                ),
                duration_seconds=time.monotonic() - start_time,
            )

        # bwrap, or an injected launcher, or refuse to run at all. Resolved
        # AFTER the size check: an oversized message must not cost a sandbox
        # probe. The workspace payload is added here because only the launcher
        # knows the root it makes the generation visible at; it is a path and
        # six integers, so it cannot move the message past the cap.
        launcher = self.resolve_launcher()
        rlimit_profile_arg = ""
        if workspace is not None:
            launcher = _launcher_for_workspace(launcher, workspace)
            payload["workspace"] = {
                "root": _launcher_workspace_root(launcher),
                "limits": workspace.limits.as_message(),
            }
            rlimit_profile_arg = json.dumps(workspace.limits.rlimit_profile())
            message = json.dumps(payload, default=str)
            message_bytes = message.encode("utf-8")

        argv = launcher.build_argv(
            _RUNNER_SCRIPT,
            [
                str(timeout),
                "1" if _requires_rlimits(launcher) else "0",
                rlimit_profile_arg,
            ],
        )

        work_dir = tempfile.mkdtemp(prefix="ta-node-sandbox-")
        popen_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # Not preexec_fn: start_new_session is done by the C layer, which
            # is the only fork-time work that is safe in a threaded parent.
            popen_kwargs["start_new_session"] = True

        inherited = _launcher_pass_fds(launcher)
        if inherited:
            if sys.platform == "win32":
                raise SandboxUnavailableError(
                    "descriptor inheritance is POSIX-only; this launcher asked "
                    f"to pass {inherited!r} on win32"
                )
            # close_fds stays True: pass_fds is the exception list, and the
            # bind resolves only because the bwrap process holds these.
            popen_kwargs["pass_fds"] = inherited

        try:
            try:
                proc = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    close_fds=True,
                    cwd=_launcher_child_cwd(launcher, work_dir),
                    env=launcher.env(work_dir),
                    **popen_kwargs,
                )
            except OSError as exc:
                return SandboxResult(
                    node_id=node_id,
                    success=False,
                    error=f"Failed to start subprocess: {exc}",
                    duration_seconds=time.monotonic() - start_time,
                )

            # One writer at a time on the child's stdin: the message goes in
            # on its own thread, RPC replies come from the drain thread.
            stdin_lock = threading.Lock()

            def _send_to_child(line: str) -> None:
                with stdin_lock:
                    try:
                        if proc.stdin is not None and not proc.stdin.closed:
                            proc.stdin.write(line.encode("utf-8") + b"\n")
                            proc.stdin.flush()
                    except (BrokenPipeError, OSError, ValueError):
                        pass

            def _handle_stdout_line(line: bytes) -> bool:
                """Answer RPC request lines; keep everything else."""
                try:
                    parsed = json.loads(line.decode("utf-8", errors="replace"))
                except (json.JSONDecodeError, ValueError):
                    return True
                if not isinstance(parsed, dict) or "rpc" not in parsed:
                    return True
                request = parsed.get("rpc")
                rpc_id = request.get("id") if isinstance(request, dict) else None
                try:
                    if not isinstance(request, dict):
                        raise ValueError("rpc request must be an object")
                    action = str(request.get("action") or "")
                    kwargs = request.get("kwargs")
                    reply = _rpc_reply_line(
                        rpc_id,
                        action,
                        kwargs if isinstance(kwargs, dict) else {},
                        invoke,
                    )
                except Exception as exc:
                    # The child is blocked on this line: always answer.
                    reply = json.dumps({
                        "id": rpc_id,
                        "error": f"sandbox rpc failure: {type(exc).__name__}: {exc}",
                    })
                _send_to_child(reply)
                return False

            breaches: list[str] = []
            out_drain = _BoundedDrain(
                proc.stdout,
                self.max_output_bytes,
                "stdout",
                breaches,
                on_line=_handle_stdout_line,
            )
            err_drain = _BoundedDrain(
                proc.stderr, MAX_STDERR_BYTES, "stderr", breaches
            )
            out_drain.start()
            err_drain.start()
            def _send_message() -> None:
                with stdin_lock:
                    _feed_stdin(proc, message_bytes + b"\n")

            feeder = threading.Thread(
                target=_send_message,
                daemon=True,
                name="node-sandbox-stdin",
            )
            feeder.start()

            outcome = "exited"
            deadline = start_time + timeout
            while True:
                if breaches:
                    outcome = "too-large"
                    _terminate_child(proc, launcher)
                    break
                try:
                    proc.wait(timeout=_POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if time.monotonic() >= deadline:
                    outcome = "timeout"
                    _terminate_child(proc, launcher)
                    break

            _close_stdin(proc)
            feeder.join(timeout=2.0)
            out_drain.join(timeout=2.0)
            err_drain.join(timeout=2.0)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        duration = time.monotonic() - start_time
        stdout_text = out_drain.data.decode("utf-8", errors="replace")
        stderr_text = err_drain.data.decode("utf-8", errors="replace")
        stderr_tail = _tail(stderr_text)

        if outcome == "too-large":
            stream = breaches[0]
            cap = self.max_output_bytes if stream == "stdout" else MAX_STDERR_BYTES
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=(
                    f"output too large: {stream} exceeded the {cap}-byte limit "
                    f"and the node was killed"
                ),
                duration_seconds=duration,
                stdout_tail=_tail(stdout_text),
                stderr_tail=stderr_tail,
            )

        if outcome == "timeout":
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=f"Execution timed out after {timeout}s",
                duration_seconds=duration,
                stdout_tail=_tail(stdout_text),
                stderr_tail=stderr_tail,
            )

        # A structured result wins over the exit code: the child refuses
        # loudly (unappliable rlimits) by printing one and exiting non-zero,
        # and that message is far more actionable than "exited with 3".
        result = None
        stripped = stdout_text.strip()
        if stripped:
            try:
                candidate = json.loads(stripped)
            except json.JSONDecodeError:
                candidate = None
            if isinstance(candidate, dict) and "success" in candidate:
                result = candidate

        if result is None:
            if proc.returncode != 0:
                return SandboxResult(
                    node_id=node_id,
                    success=False,
                    error=(
                        f"Process exited with code {proc.returncode}: "
                        f"{stderr_text[:2000]}"
                    ),
                    duration_seconds=duration,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    stdout_tail=_tail(stdout_text),
                    stderr_tail=stderr_tail,
                )
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=f"Node produced invalid JSON output: {stdout_text[:200]}",
                duration_seconds=duration,
                stdout_tail=_tail(stdout_text),
                stderr_tail=stderr_tail,
            )

        # A ws.run command that outlived its budget: the runner already wrote
        # this frame and left with os._exit, so all that remains is to make
        # certain the supervisor -- and with it the whole pid namespace, and
        # with that any double-forked descendant -- is gone.
        if result.get("workspace_timeout"):
            _terminate_child(proc, launcher)
            return SandboxResult(
                node_id=node_id,
                success=False,
                error=result.get("error") or "workspace command timeout",
                duration_seconds=duration,
                stdout=result.get("user_stdout", ""),
                stderr=stderr_text,
                stdout_tail=_tail(result.get("stdout_tail", "")),
                stderr_tail=_tail(result.get("stderr_tail", "") or stderr_text),
                workspace_timeout=True,
            )

        # `stdout_tail` is what the node printed, not the protocol frame.
        printed = result.get("user_stdout", "")
        undeclared = result.get("undeclared") or []
        return SandboxResult(
            node_id=node_id,
            success=result.get("success", False),
            output_state=result.get("output_state", {}),
            error=result.get("error", ""),
            duration_seconds=duration,
            stdout=printed,
            stderr=stderr_text,
            stdout_tail=_tail(printed),
            stderr_tail=stderr_tail,
            warning=result.get("warning", ""),
            undeclared=[str(k) for k in undeclared],
        )

    async def execute(
        self,
        node_id: str,
        source_code: str,
        input_state: dict[str, Any],
        input_keys: list[str],
        output_keys: list[str],
        timeout: float | None = None,
        effects: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        invoke: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> SandboxResult:
        """Async wrapper around :meth:`run_sync` (runs it on a worker thread)."""
        return await asyncio.to_thread(
            self.run_sync,
            node_id=node_id,
            source_code=source_code,
            input_state=input_state,
            input_keys=input_keys,
            output_keys=output_keys,
            timeout=timeout,
            effects=effects,
            dependencies=dependencies,
            invoke=invoke,
        )

    async def execute_registered(
        self,
        node_registration: dict[str, Any],
        graph_state: dict[str, Any],
        timeout: float | None = None,
        effects: dict[str, Any] | None = None,
    ) -> SandboxResult:
        """Execute a registered node from the node registry.

        Convenience wrapper that unpacks a NodeRegistration dict.
        """
        return await self.execute(
            node_id=node_registration["node_id"],
            source_code=node_registration["source_code"],
            input_state=graph_state,
            input_keys=node_registration.get("input_keys", []),
            output_keys=node_registration.get("output_keys", []),
            timeout=timeout,
            effects=effects,
            dependencies=node_registration.get("dependencies", []),
        )


__all__ = [
    "ALLOWED_IMPORTS",
    "DEFAULT_LAUNCHER_FACTORY",
    "FORBIDDEN_PATTERNS",
    "MAX_INPUT_BYTES",
    "MAX_OUTPUT_BYTES",
    "MAX_STDERR_BYTES",
    "BwrapLauncher",
    "Launcher",
    "NodeSandbox",
    "PlainSubprocessLauncher",
    "SandboxResult",
    "SandboxTerminationError",
    "SandboxUnavailableError",
    "WorkspaceLimits",
    "WorkspaceMount",
    "WORKSPACE_MOUNT_POINT",
]
