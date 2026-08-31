#!/usr/bin/env python3
"""Prove the workspace jail's Linux-only claims INSIDE the deployed container.

    docker exec <daemon> python /app/scripts/workspace_bwrap_oracle.py

Seven things cannot be proved on a developer box: they need Linux, a real
``bwrap``, a real ``git`` and this image's libcurl. The suite skips them, so
they are asserted here instead -- against the SHIPPED modules, with a real
:class:`BwrapLauncher`, on the machine that actually runs them.

Safe on a live box by construction: everything happens under a temp root in
``/tmp`` (never ``/data``), no daemon state is read or written, no run is
started, and the only socket it opens is a loopback connect it expects to fail.
One ``PASS``/``FAIL`` line per check with the evidence that decided it; exit 1
if any check fails, 2 if the host cannot run them at all.

Add a check by appending to :data:`CHECKS`. Each one takes a :class:`Context`
and returns :class:`Outcome`; raising is the same as failing, with the
exception as the evidence.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Where a temp root may live. ``/data`` is the daemon's; this never touches it.
TEMP_PARENT = "/tmp"
TEMP_PREFIX = "ws-bwrap-oracle-"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


@dataclass(frozen=True)
class Outcome:
    """What one check decided, and the observation that decided it."""

    ok: bool
    evidence: str
    skipped: bool = False

    @property
    def status(self) -> str:
        if self.skipped:
            return SKIP
        return PASS if self.ok else FAIL


@dataclass(frozen=True)
class Check:
    name: str
    summary: str
    run: Callable[[Context], Outcome]


@dataclass(frozen=True)
class Result:
    name: str
    summary: str
    outcome: Outcome
    seconds: float = 0.0


@dataclass
class Context:
    """Everything a check may touch. Nothing outside ``root`` is written."""

    root: Path
    git_binary: str = "git"
    bwrap_path: str | None = None
    keep: bool = False
    counter: int = field(default=0)

    def scratch(self, name: str) -> Path:
        """A fresh directory for one check, under the temp root."""
        self.counter += 1
        made = self.root / f"{self.counter:02d}-{name}"
        made.mkdir(parents=True, exist_ok=False)
        return made


# --------------------------------------------------------------------------- #
# Rendering and selection (the harness -- unit-tested off-Linux)
# --------------------------------------------------------------------------- #


def render(result: Result) -> str:
    """One line per check: status, name, and the evidence behind it."""
    evidence = " ".join(str(result.outcome.evidence).split())
    if len(evidence) > 240:
        evidence = evidence[:237] + "..."
    return f"{result.outcome.status:<4} {result.name:<38} {evidence}"


def check_names() -> list[str]:
    return [check.name for check in CHECKS]


def select_checks(only: Sequence[str] | None) -> list[Check]:
    """The checks to run. An unknown name is an error, never a silent no-op."""
    if not only:
        return list(CHECKS)
    known = {check.name: check for check in CHECKS}
    unknown = [name for name in only if name not in known]
    if unknown:
        raise KeyError(
            f"unknown check(s): {', '.join(sorted(unknown))}; "
            f"known: {', '.join(check_names())}"
        )
    return [known[name] for name in only]


def run_checks(checks: Sequence[Check], context: Context) -> list[Result]:
    """Run each check, turning a raised exception into a failure with evidence."""
    results: list[Result] = []
    for check in checks:
        started = time.monotonic()
        try:
            outcome = check.run(context)
        except Exception as exc:  # noqa: BLE001 - a crash IS a failed check
            outcome = Outcome(False, f"{type(exc).__name__}: {exc}")
        results.append(
            Result(check.name, check.summary, outcome, time.monotonic() - started)
        )
    return results


def exit_code_for(results: Sequence[Result]) -> int:
    """1 if anything failed. A skip is not a pass, but it is not a failure."""
    return 1 if any(not r.outcome.ok and not r.outcome.skipped for r in results) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workspace_bwrap_oracle",
        description=(
            "Prove the workspace jail's Linux-only claims inside the deployed "
            "container. Writes only under a temp root in /tmp."
        ),
    )
    parser.add_argument(
        "--only",
        action="append",
        metavar="CHECK",
        help="run only this check (repeatable); default is all of them",
    )
    parser.add_argument(
        "--list", action="store_true", help="print the checks and exit"
    )
    parser.add_argument(
        "--temp-parent",
        default=TEMP_PARENT,
        help=f"where the temp root is created (default {TEMP_PARENT})",
    )
    parser.add_argument(
        "--keep", action="store_true", help="leave the temp root behind for inspection"
    )
    return parser


def preflight(temp_parent: str) -> list[str]:
    """What is missing before any check can mean anything. Empty is good."""
    problems: list[str] = []
    if sys.platform != "linux":
        problems.append(f"this is {sys.platform!r}; the jail is Linux-only")
    if shutil.which("bwrap") is None:
        problems.append("bwrap is not on PATH")
    if shutil.which("git") is None:
        problems.append("git is not on PATH")
    parent = Path(temp_parent)
    if not parent.is_dir():
        problems.append(f"{temp_parent} is not a directory")
    resolved = str(parent.resolve()) if parent.exists() else temp_parent
    if resolved == "/data" or resolved.startswith("/data/"):
        problems.append("refusing to write under /data")
    return problems


# --------------------------------------------------------------------------- #
# Shared helpers for the checks
# --------------------------------------------------------------------------- #

_PY = "/usr/bin/python3"


def _python() -> str:
    return _PY if Path(_PY).exists() else (shutil.which("python3") or sys.executable)


def _process_is_alive(pid_dir: Path) -> bool:
    """Whether ``/proc/<pid>`` names a process that is still RUNNING.

    An entry existing is not enough: a killed process whose parent has not
    reaped it stays as a ``Z`` entry, and whether anything reaps it depends on
    the environment's init. The state letter is the first field after the LAST
    ``)`` -- ``comm`` is parenthesised and may itself contain a paren.
    """
    try:
        stat_text = (pid_dir / "stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    _before, paren, after = stat_text.rpartition(")")
    fields = after.split() if paren else []
    return bool(fields) and fields[0] != "Z"


def _marker_is_running(marker: str) -> bool:
    """Any LIVE process whose command line carries *marker*.

    A jailed pid is namespace-local and means nothing out here, so a unique
    marker in ``/proc/*/cmdline`` is the only host-side question worth asking.
    The marker also answers the pid-recycling problem for free: a recycled pid
    belongs to a process with a different command line.
    """
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue
        if marker.encode() in cmdline and _process_is_alive(entry):
            return True
    return False


def _libcurl_version_and_source() -> tuple[str, str]:
    """The libcurl version text, and the name of whatever answered.

    Reads through the SAME function the worker uses
    (:func:`workspace_git.libcurl_version_text`), instrumented only to record
    which candidate answered -- there is no second reader here to drift from
    production.

    "Which one" is the fact worth printing in this image: it ships no ``curl``
    binary at all, and ``git-remote-https`` links ``libcurl-gnutls.so.4`` while
    ``find_library('curl')`` answers the OpenSSL build. A version read off the
    wrong libcurl decides the multi-resolve rule for a library git never calls.
    """
    import ctypes

    from tinyassets.workspace_git import libcurl_version_text

    loaded: list[str] = []
    binaries: list[str] = []

    def _load(name: str) -> Any:
        library = ctypes.CDLL(name)  # raises OSError, which the reader skips
        loaded.append(name)
        return library

    def _which(name: str) -> str | None:
        # Only reached when no library answered, so a hit here IS the source.
        found = shutil.which(name)
        if found:
            binaries.append(found)
        return found

    text = libcurl_version_text(load_library=_load, which=_which)
    if binaries:
        return text, binaries[-1]
    return text, (loaded[-1] if loaded else "?")


def _pin_verdict(stderr_text: str) -> tuple[bool, bool]:
    """``(ignored_the_pin, used_the_pin)``, read off git's own words.

    The whole discrimination in check 6: pin a name to an address nothing
    listens on and see WHICH failure comes back. "could not resolve" means git
    asked DNS and ``http.curloptResolve`` was ignored; "failed to connect" or
    "connection refused" means it took the pinned address and tried it. Only
    the second proves the pin is honoured -- a check that accepted any failure
    would pass on a libcurl that silently dropped the entry.
    """
    lowered = (stderr_text or "").lower()
    ignored = "could not resolve" in lowered
    used = "failed to connect" in lowered or "connection refused" in lowered
    return ignored, used


def _git_links_libcurl() -> str:
    """Which libcurl ``git-remote-https`` links, for the evidence line.

    Best effort: it is a cross-check on :func:`_libcurl_version_and_source`,
    never a gate -- ``ldd`` is absent from some images and a static build links
    none at all.
    """
    try:
        exec_path = subprocess.run(
            ["git", "--exec-path"], capture_output=True, text=True, timeout=30,
            check=False,
        ).stdout.strip()
        helper = Path(exec_path) / "git-remote-https"
        if not exec_path or not helper.exists():
            return "?"
        listed = subprocess.run(
            ["ldd", str(helper)], capture_output=True, text=True, timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "?"
    for line in listed.splitlines():
        if "libcurl" in line:
            return line.strip().split(" ")[0]
    return "?"


def double_fork_node_source(marker: str, *, detacher: str = "") -> str:
    """The node that detaches a sleeper and then hangs, for check 2.

    A MODULE-LEVEL builder, not a literal inside the check, so a test can hand
    it to the real code-node validator. Both jail probes were written as
    embedded Python and carried ``subprocess`` / ``open(`` / ``socket`` in
    their string literals; the validator scans the whole source text, so the
    two checks never ran and reported a validation error instead of an answer.
    Nothing here goes through Python at all.
    """
    spawn = f"{detacher}/bin/sh -c 'sleep 300 # {marker}' </dev/null >/dev/null 2>&1 &"
    return (
        "def run(state):\n"
        f"    ws.run(['/bin/sh', '-c', {spawn!r}])\n"
        "    ws.run(['/bin/sh', '-c', 'sleep 120'], timeout=2)\n"
        "    return {'result': 'never'}\n"
    )


def isolation_node_source(python: str, *, host_witness: str = "/usr/bin") -> str:
    """The node that probes network, ``/data`` and escape, for check 3.

    ``http.client`` rather than ``socket``, and ``Path.write_text`` rather than
    ``open(``: those two are FORBIDDEN_PATTERNS and this text is part of the
    node's source. The probe is placed with ``ws.write`` and run with
    ``ws.run`` -- the surface a real user's node has.

    Two escape questions, because the obvious one has a misleading answer.
    ``BwrapLauncher`` emits no ``--ro-bind / /``: bwrap builds a fresh PRIVATE
    root and binds specific paths into it. Writing ``/escape-probe`` therefore
    SUCCEEDS and reaches nothing, which is fine and is not what anyone wanted
    to know. What matters is whether the write is visible on the host (the
    check looks, from outside) and whether a read-only bind is really read-only
    -- ``host_witness`` is a directory bound with ``--ro-bind``, so a write
    landing there would be a real escape.
    """
    probe = (
        "import http.client, json, os, pathlib\n"
        "out = {}\n"
        "try:\n"
        "    conn = http.client.HTTPSConnection('1.1.1.1', 443, timeout=5)\n"
        "    conn.request('GET', '/')\n"
        "    out['net'] = 'CONNECTED'\n"
        "except Exception as exc:\n"
        "    out['net'] = type(exc).__name__\n"
        "out['data'] = os.path.isdir('/data')\n"
        "try:\n"
        "    pathlib.Path('/escape-probe').write_text('x')\n"
        "    out['root'] = 'WROTE'\n"
        "except Exception as exc:\n"
        "    out['root'] = type(exc).__name__\n"
        "try:\n"
        f"    pathlib.Path({host_witness!r} + '/ta-escape-probe').write_text('x')\n"
        "    out['readonly_bind'] = 'WROTE'\n"
        "except Exception as exc:\n"
        "    out['readonly_bind'] = type(exc).__name__\n"
        "print(json.dumps(out))\n"
    )
    return (
        "def run(state):\n"
        f"    ws.write('probe.py', {probe!r})\n"
        f"    out = ws.run([{python!r}, '/workspace/probe.py'])\n"
        "    return {'result': out}\n"
    )


def _home(path: Path) -> Path:
    """A HOME directory that EXISTS, because ``git_environment`` requires one.

    Three checks passed a path they never created and failed on their own
    scaffolding rather than on what they were testing (found in the live
    container, 2026-08-31). Every ``home_dir=`` in this file goes through here.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def _git_env(home: Path, git_binary: str) -> dict[str, str]:
    from tinyassets.workspace_git import git_environment

    home.mkdir(parents=True, exist_ok=True)
    resolved = shutil.which(git_binary) or git_binary
    return git_environment(home, path=str(Path(resolved).parent))


def _seed_repo(repo: Path, git_binary: str, env: dict[str, str]) -> str:
    """A one-commit repository, built with plain subprocess (not the layer)."""
    repo.mkdir(parents=True, exist_ok=True)

    def run(argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [git_binary, *argv], cwd=str(repo), env=env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120, check=True,
        )

    run(["init", "--quiet", "."])
    (repo / "README.md").write_text("oracle\n", encoding="utf-8")
    run(["add", "README.md"])
    run([
        "-c", "user.name=Tiny", "-c", "user.email=tiny@universes.tinyassets.io",
        "commit", "--quiet", "-m", "first",
    ])
    return run(["rev-parse", "HEAD"]).stdout.strip()


def _run_workspace_node(
    source: str,
    *,
    bind_source: str,
    pass_fds: tuple[int, ...] = (),
    allowed_roots: tuple[str, ...] = (),
    timeout: float = 60.0,
    bwrap_path: str | None = None,
):
    """Run one code node in a real bwrap jail with a workspace bound."""
    from tinyassets.node_sandbox import BwrapLauncher, NodeSandbox, WorkspaceMount

    mount = WorkspaceMount(bind_source=bind_source, pass_fds=pass_fds)
    launcher = BwrapLauncher(
        bwrap_path=bwrap_path,
        workspace_bind=bind_source,
        allowed_workspace_roots=allowed_roots,
        pass_fds=pass_fds,
    )
    sandbox = NodeSandbox(launcher=launcher, timeout=timeout)
    return sandbox.run_sync(
        node_id="oracle-node",
        source_code=source,
        input_state={},
        input_keys=[],
        output_keys=["result"],
        timeout=timeout,
        workspace=mount,
    )


# --------------------------------------------------------------------------- #
# The checks
# --------------------------------------------------------------------------- #


def check_bind_survives_a_rename(context: Context) -> Outcome:
    """(1) The bind follows the DESCRIPTOR, so renaming the path cannot swap it."""
    import threading

    scratch = context.scratch("rename")
    lease = scratch / "lease-1"
    lease.mkdir()
    (lease / "README.md").write_text("bound through the fd\n", encoding="utf-8")
    decoy = scratch / "lease-2"
    decoy.mkdir()
    (decoy / "README.md").write_text("the wrong directory\n", encoding="utf-8")

    handle = os.open(str(lease), os.O_RDONLY)
    renamed = threading.Event()

    def swap() -> None:
        time.sleep(1.0)
        os.rename(str(lease), str(scratch / "lease-1-moved"))
        os.rename(str(decoy), str(lease))
        renamed.set()

    mover = threading.Thread(target=swap, daemon=True)
    source = (
        "def run(state):\n"
        f"    ws.run([{_python()!r}, '-c', 'import time; time.sleep(3)'])\n"
        "    return {'result': ws.read('README.md')}\n"
    )
    try:
        mover.start()
        result = _run_workspace_node(
            source,
            bind_source=f"/proc/self/fd/{handle}",
            pass_fds=(handle,),
            bwrap_path=context.bwrap_path,
        )
    finally:
        os.close(handle)

    if not renamed.is_set():
        return Outcome(False, "the rename never happened, so this proves nothing")
    if not result.success:
        return Outcome(False, f"the node failed: {result.error}")
    read = result.output_state.get("result")
    return Outcome(
        read == "bound through the fd\n",
        f"after the swap the node read {read!r} (decoy said 'the wrong directory')",
    )


def check_jail_kill_reaps_a_double_fork(context: Context) -> Outcome:
    """(2) A `setsid` double-fork survives a group kill; it must not survive the jail."""
    scratch = context.scratch("jail-kill")
    root = scratch / "generation"
    root.mkdir()
    marker = "ta-oracle-canary-" + os.urandom(6).hex()
    # Shell, not embedded Python. The node's SOURCE TEXT is what the code-node
    # validator scans, and a probe written in Python carried `subprocess` in a
    # string literal -- so this check never ran at all until the droplet said
    # "Forbidden pattern: 'subprocess'" (2026-08-31). Everything here goes
    # through `ws.run`, which is also the path a real user's node takes.
    detacher = "setsid " if shutil.which("setsid") else ""
    source = double_fork_node_source(marker, detacher=detacher)
    started = time.monotonic()
    result = _run_workspace_node(
        source,
        bind_source=str(root),
        allowed_roots=(str(scratch),),
        timeout=45,
        bwrap_path=context.bwrap_path,
    )
    elapsed = time.monotonic() - started

    error = str(result.error or "")
    # The FLAG on the result classifies, not a phrase in the message: the
    # message is prose and the flag is the contract.
    flagged = bool(getattr(result, "workspace_timeout", False))
    timed_out = (not result.success) and flagged
    deadline = time.monotonic() + 10
    while _marker_is_running(marker) and time.monotonic() < deadline:
        time.sleep(0.2)
    sleeper_alive = _marker_is_running(marker)
    return Outcome(
        timed_out and not sleeper_alive,
        f"node failed after {elapsed:.1f}s with workspace_timeout={flagged}, "
        f"error {error[:100]!r}; sleeper carrying {marker} still running: "
        f"{sleeper_alive} (detached with {detacher.strip() or 'a plain background job'})",
    )


def check_jail_has_no_network_no_data_no_escape(context: Context) -> Outcome:
    """(3) No network, no ``/data``, and nothing writable outside ``/workspace``."""
    scratch = context.scratch("jail-isolation")
    root = scratch / "generation"
    root.mkdir()
    # Written to the workspace with ws.write and run with ws.run. The probe
    # avoids `socket` and `open(` deliberately: those are FORBIDDEN_PATTERNS,
    # the validator scans the node's whole source text including this literal,
    # and with them in it the check never ran (droplet, 2026-08-31).
    # `http.client` connects just as well, and `Path.write_text` writes.
    witness = "/usr/bin"
    source = isolation_node_source(_python(), host_witness=witness)
    result = _run_workspace_node(
        source,
        bind_source=str(root),
        allowed_roots=(str(scratch),),
        timeout=60,
        bwrap_path=context.bwrap_path,
    )
    if not result.success:
        return Outcome(False, f"the probe node failed: {result.error}")
    payload = str(result.output_state.get("result"))
    connected = "CONNECTED" in payload
    saw_data = '"data": true' in payload.lower()
    # The read-only bind must have refused. The jail's own private root is
    # allowed to be writable -- see isolation_node_source.
    wrote_readonly = '"readonly_bind": "wrote"' in payload.lower()
    # And the host is asked directly, which is the only escape question whose
    # answer cannot be argued with.
    on_host = [
        path
        for path in (Path("/escape-probe"), Path(witness) / "ta-escape-probe")
        if path.exists()
    ]
    return Outcome(
        not connected and not saw_data and not wrote_readonly and not on_host,
        f"probe said {payload[:220]}; visible on the host: {[str(p) for p in on_host]}",
    )


def check_ws_bundle_imports_under_fsck(context: Context) -> Outcome:
    """(4) A jail-made bundle survives the fsck-checked import in an empty repo."""
    from tinyassets.workspace_git import unbundle_into_fresh_repo, verify_bundle

    scratch = context.scratch("ws-bundle")
    env = _git_env(scratch / "githome", context.git_binary)
    root = scratch / "generation"
    sha = _seed_repo(root, context.git_binary, env)

    source = (
        "def run(state):\n"
        "    return {'result': ws.bundle(state['sha'])}\n"
    )
    from tinyassets.node_sandbox import BwrapLauncher, NodeSandbox, WorkspaceMount

    launcher = BwrapLauncher(
        bwrap_path=context.bwrap_path,
        workspace_bind=str(root),
        allowed_workspace_roots=(str(scratch),),
    )
    result = NodeSandbox(launcher=launcher, timeout=120).run_sync(
        node_id="oracle-bundle",
        source_code=source,
        input_state={"sha": sha},
        input_keys=["sha"],
        output_keys=["result"],
        timeout=120,
        workspace=WorkspaceMount(bind_source=str(root)),
    )
    if not result.success:
        return Outcome(False, f"ws.bundle failed in the jail: {result.error}")
    relative = str(result.output_state.get("result") or "").lstrip("/")
    bundle = root / relative
    if not bundle.is_file():
        return Outcome(False, f"ws.bundle returned {relative!r}, which is not a file")

    # git_environment refuses a HOME that does not exist, and this one was
    # never created -- the check failed on its own scaffolding, not on the
    # bundle (droplet, 2026-08-31).
    home = _home(scratch / "verify-home")
    git_path = str(Path(shutil.which(context.git_binary) or context.git_binary).parent)
    verify_scratch = scratch / "verify-scratch"
    verify_scratch.mkdir()
    refs = verify_bundle(
        bundle,
        max_bytes=512 * 1024 * 1024,
        scratch_dir=verify_scratch,
        home_dir=home,
        path=git_path,
        git_binary=context.git_binary,
    )
    if not refs:
        return Outcome(False, "verify_bundle reported no refs")
    # Verify is NOT the gate (a shallow source passes it); the fsck-checked
    # import is what actually proves the bundle self-contained.
    imported = unbundle_into_fresh_repo(
        bundle,
        scratch / "imported",
        ref_name=refs[0],
        home_dir=_home(scratch / "import-home"),
        path=git_path,
        git_binary=context.git_binary,
    )
    return Outcome(
        imported == sha,
        f"ws.bundle wrote {relative}; verify saw {refs}; the fsck-checked import "
        f"reproduced {imported[:12]} (wanted {sha[:12]})",
    )


def check_run_git_timeout_reaps_a_descendant(context: Context) -> Outcome:
    """(5) ``run_git``'s timeout kills the process GROUP, not just the child."""
    from tinyassets.workspace_git import WorkspaceGitError, run_git

    scratch = context.scratch("run-git-kill")
    home = scratch / "home"
    home.mkdir()
    marker = scratch / "descendant.pid"
    started = time.monotonic()
    try:
        run_git(
            ["-c", f"sleep 300 & echo $! > {marker}; sleep 300"],
            cwd=scratch,
            home_dir=home,
            path="/usr/bin:/bin",
            timeout_s=3,
            git_binary="/bin/sh",
        )
        return Outcome(False, "run_git returned instead of timing out")
    except WorkspaceGitError as exc:
        if exc.code != "timeout":
            return Outcome(False, f"the failure class was {exc.code!r}, not 'timeout'")
    elapsed = time.monotonic() - started

    if not marker.exists():
        return Outcome(False, "the child never recorded a descendant pid")
    descendant = int(marker.read_text().strip())
    deadline = time.monotonic() + 10
    while _process_is_alive(Path(f"/proc/{descendant}")) and time.monotonic() < deadline:
        time.sleep(0.05)
    # NOT `os.path.isdir`: a killed process whose parent has not reaped it
    # stays as a `Z` entry, and whether anything reaps it depends on the
    # environment's init -- this check reported "alive: True" for a process
    # that was dead, in a container whose PID 1 is not a reaper (2026-08-31).
    alive = _process_is_alive(Path(f"/proc/{descendant}"))
    return Outcome(
        not alive,
        f"timed out after {elapsed:.1f}s; double-forked pid {descendant} alive: {alive}",
    )


def check_libcurl_multi_resolve_is_honoured(context: Context) -> Outcome:
    """(6) This libcurl takes the comma list, and the pin actually redirects."""
    from tinyassets.workspace_git import (
        GitTransport,
        libcurl_supports_multi_resolve,
        run_git,
    )

    scratch = context.scratch("libcurl")
    home = scratch / "home"
    home.mkdir()
    # NOT `curl -V`: this image has no curl binary, so a binary-only probe
    # would fail this check for the wrong reason (and, in the worker, refuse
    # every checkout). The library git links is the one that decides.
    version_text, answered_by = _libcurl_version_and_source()
    supported = libcurl_supports_multi_resolve(version_text)
    token = next(
        (part for part in version_text.split() if part.startswith("libcurl/")), "?"
    )
    git_links = _git_links_libcurl()

    # Pin a name that does not resolve to loopback and observe which failure we
    # get: "could not resolve" means the pin was ignored, "failed to connect"
    # means libcurl used it. Loopback only -- no packet leaves the box.
    transport = GitTransport.build(
        "owner/name",
        host="example.invalid",
        curl_version_text=version_text,
        resolver=lambda hostname, port: ["127.0.0.1"],
        classifier=lambda ip_text: ip_text,
    )
    result = run_git(
        ["ls-remote", transport.url],
        cwd=scratch,
        home_dir=home,
        path="/usr/bin:/bin",
        options=transport.forced_options("!/bin/false"),
        timeout_s=60,
        git_binary=context.git_binary,
    )
    ignored_the_pin, used_the_pin = _pin_verdict(result.stderr_scrubbed)
    return Outcome(
        supported and used_the_pin and not ignored_the_pin,
        f"{token} multi_resolve={supported} read from {answered_by!r} "
        f"(git-remote-https links {git_links}); pinned example.invalid to "
        f"127.0.0.1 and git said {result.stderr_scrubbed.strip()[:160]!r}",
    )


def check_full_route(context: Context) -> Outcome:
    """(7) A COMPILED GRAPH through the production launcher, credential and all.

    Not a hand-built launcher and not a fake credential path: the branch is
    compiled by ``compile_branch``, the code node reaches the jail through
    ``WORKSPACE_LAUNCHER_FACTORY``, and the canary token travels the REAL
    ``CredentialBroker`` over its unix socket. That is what makes
    ``leaked=False`` an assertion rather than a hope -- a canary that never
    entered the system cannot be observed leaving it.

    This is the check that must pass before any production claim: the other six
    can all pass while ``/workspace`` is the wrong directory.
    """
    import threading

    from tinyassets import graph_compiler as gc
    from tinyassets import runs
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.effectors import EffectChain
    from tinyassets.effectors.workspace import run_workspace_effector
    from tinyassets.storage.effector_consents import grant_consent
    from tinyassets.storage.outbound_connections import ConnectionLedger
    from tinyassets.storage.workspace_authority import workspace_consent_destination

    scratch = context.scratch("full-route")
    data_root = scratch / "data"
    universe_dir = data_root / "universe-oracle"
    universe_dir.mkdir(parents=True)
    (data_root / "scratch").mkdir()
    runs.initialize_runs_db(universe_dir)

    repo = "owner/name"
    canary = "ghp_ORACLECANARY0123456789ABCDEFGHIJ"
    _write_vault(universe_dir, canary)

    ledger = ConnectionLedger(
        data_root / "outbound.db", verify_authenticated_principal=lambda: "user-1"
    )
    ledger.create_connection(
        connection_id="conn-git",
        owner_user_id="user-1",
        connection_class="outbound-http",
        scopes=(f"git_read:{repo}", f"git_write:{repo}"),
        provider="http",
        destination=f"github.com/{repo}",
        credential_ref="vault://http/oracle",
        connection_type="http",
        auth_scheme="bearer",
        allowed_endpoints=[
            {"host": "github.com", "path_template": "/owner/name", "methods": ["GET"]}
        ],
    )
    ledger.grant_connection(
        grant_id="grant-git",
        connection_id="conn-git",
        owner_user_id="user-1",
        universe_id="universe-oracle",
    )
    grant_consent(
        universe_dir,
        sink="workspace",
        destination=workspace_consent_destination(
            "workspace_checkout", repo, connection_id="conn-git", host="github.com"),
        granted_by="oracle",
    )

    source_repo = scratch / "source"
    git_env = _git_env(scratch / "seed-home", context.git_binary)
    sha = _seed_repo(source_repo, context.git_binary, git_env)
    broker_seen: list[str] = []
    route_libcurl: list[str] = []

    def worker_with_a_real_broker(request: dict[str, Any]) -> dict[str, Any]:
        """The worker's shape, with the REAL credential path exercised.

        It resolves the reference through the vault resolver and serves the
        token over a real ``CredentialBroker`` socket, so the canary genuinely
        passes through the broker before the leak scan looks for it.
        """
        from tinyassets.storage.outbound_connections import (
            _GeneralVaultCredentialResolver,
        )
        from tinyassets.workspace_git import (
            CredentialBroker,
            GitTransport,
            create_bundle,
        )

        staging = Path(request["staging_dir"])
        secret = _GeneralVaultCredentialResolver(universe_dir=universe_dir)(
            request["credential_ref"]
        )
        # The same reader the worker uses, in this image, on this route: if
        # `libcurl_version_text` cannot answer here it cannot answer in a real
        # checkout either, and GitTransport.build refuses without it.
        version_text, answered_by = _libcurl_version_and_source()
        route_libcurl.append(answered_by)
        transport = GitTransport.build(
            request["owner_repo"],
            host=request["host"],
            curl_version_text=version_text,
            # Loopback, so nothing leaves the box: this route serves the broker
            # and bundles a local repository, it never reaches the wire.
            resolver=lambda hostname, port: ["127.0.0.1"],
            classifier=lambda ip_text: ip_text,
        )
        protocol, broker_host, broker_path = transport.broker_binding()
        broker = CredentialBroker(
            protocol, broker_host, broker_path, "x-access-token", secret
        )
        try:
            # No socket_dir: the broker's own short path, exactly as the real
            # worker does it. Passing the staging directory is what made this
            # check refuse with "too long for sun_path" in production.
            broker.serve()
            wanted = (
                "operation=get" + chr(10)
                + "protocol=" + protocol + chr(10)
                + "host=" + broker_host + chr(10)
                + "path=" + broker_path + chr(10)
            )
            answered = broker.answer(wanted)
            broker_seen.append(
                "answered" if answered and secret in answered else "refused"
            )
            verify = staging / "verify"
            verify.mkdir(parents=True, exist_ok=True)
            bundle = staging / "out.bundle"
            create_bundle(
                source_repo,
                sha,
                bundle,
                home_dir=_home(staging / "bundle-home"),
                path=str(Path(shutil.which(context.git_binary) or "git").parent),
                scratch_dir=verify,
                git_binary=context.git_binary,
            )
        finally:
            broker.close()
        return {
            "ok": True,
            "resolved_sha": sha,
            "bytes": bundle.stat().st_size,
            "bundle_name": "out.bundle",
            "ref_name": "refs/tiny/export",
        }

    chain = EffectChain(run_id="oracle-run", base_path=str(universe_dir))
    evidence = run_workspace_effector(
        node_id="checkout-node",
        output_keys=["ws"],
        run_state={
            "ws": {
                "sink": "workspace",
                "op": "checkout",
                "connection_id": "conn-git",
                "grant_id": "grant-git",
                "repo": repo,
                "ref": "main",
                "storage": "scratch",
            }
        },
        base_path=universe_dir,
        run_id="oracle-run",
        chain=chain,
        execute=worker_with_a_real_broker,
    )
    if evidence.get("error_kind"):
        return Outcome(False, f"the real adapter refused: {evidence}")
    if broker_seen != ["answered"]:
        return Outcome(False, f"the real broker path did not run: {broker_seen}")
    if not route_libcurl:
        return Outcome(False, "the route never read a libcurl version")

    mount = chain.workspace_mount_or_none("checkout-node")
    if mount is None:
        return Outcome(False, "the adapter published no capability")
    lease_root = Path(mount.lease.path)
    sandbox_mount = gc._sandbox_workspace_mount(mount, "code-node")
    inherited_fd = str(sandbox_mount.bind_source).startswith("/proc/self/fd/")

    renamed = threading.Event()

    def swap() -> None:
        time.sleep(1.0)
        decoy = lease_root.parent / (lease_root.name + "-decoy")
        (decoy / "repo").mkdir(parents=True, exist_ok=True)
        (decoy / "repo" / "README.md").write_text("the wrong tree", encoding="utf-8")
        os.rename(str(lease_root), str(lease_root.parent / (lease_root.name + "-moved")))
        os.rename(str(decoy), str(lease_root))
        renamed.set()

    # Everything through the `ws` surface. An embedded `os.listdir` /
    # `open(...)` probe cannot run at all: `open(` is a FORBIDDEN_PATTERN and
    # the validator scans the node's whole source text.
    body = (
        "def run(state):" + chr(10)
        + "    import time; time.sleep(3)" + chr(10)
        + "    try:" + chr(10)
        + "        head = ws.read('.git/HEAD')" + chr(10)
        + "    except Exception:" + chr(10)
        + "        head = ''" + chr(10)
        + "    return {'result': repr({" + chr(10)
        + "        'entries': sorted(ws.glob('*'))[:12]," + chr(10)
        + "        'readme': ws.read('README.md')," + chr(10)
        + "        'has_git': head.startswith('ref:') or len(head.strip()) == 40," + chr(10)
        + "    })}" + chr(10)
    )
    # The checkout fired outside the graph, so the graph has to CONTAIN it for
    # the ancestry rule to hold -- a workspace is resolved from a checkout the
    # node depends on, and "not one of its ancestors ([])" is what a branch
    # with a single node gets. This is the shape a real branch has.
    upstream = NodeDefinition(
        node_id="checkout-node",
        display_name="oracle checkout node",
        output_keys=["checked_out"],
        source_code="def run(state):" + chr(10) + "    return {'checked_out': True}" + chr(10),
    )
    node = NodeDefinition(
        node_id="code-node",
        display_name="oracle code node",
        output_keys=["result"],
        source_code=body,
        workspace="checkout-node",
    )
    branch = BranchDefinition(name="oracle", entry_point="checkout-node")
    branch.node_defs = [upstream, node]
    branch.graph_nodes = [
        GraphNodeRef(id="checkout-node", node_def_id="checkout-node"),
        GraphNodeRef(id="code-node", node_def_id="code-node"),
    ]
    branch.edges = [
        EdgeDefinition(from_node="START", to_node="checkout-node"),
        EdgeDefinition(from_node="checkout-node", to_node="code-node"),
        EdgeDefinition(from_node="code-node", to_node="END"),
    ]
    branch.state_schema = [
        {"name": "result", "type": "str"},
        {"name": "checked_out", "type": "bool"},
    ]

    mover = threading.Thread(target=swap, daemon=True)
    mover.start()
    compiled = gc.compile_branch(
        branch, provider_call=None, effect_chain=chain, base_path=str(universe_dir)
    )
    # `compiled.graph` is the UNCOMPILED StateGraph -- the runner attaches its
    # own checkpointer, so the oracle compiles it without one.
    final = compiled.graph.compile().invoke({})
    payload = str(final.get("result") or "")

    workspace_is_the_repo = "README.md" in payload and "has_git': True" in payload.replace(
        '"has_git": true', "has_git': True"
    )
    lease_not_visible = "'repo'" not in payload and '"repo"' not in payload
    read_the_original = "the wrong tree" not in payload and "oracle" in payload
    leaked = _canary_is_anywhere(canary, payload, evidence, (universe_dir, lease_root.parent))

    ok = (
        workspace_is_the_repo
        and lease_not_visible
        and read_the_original
        and inherited_fd
        and renamed.is_set()
        and not leaked
    )
    return Outcome(
        ok,
        f"bind={sandbox_mount.bind_source} renamed={renamed.is_set()} "
        f"is_repo={workspace_is_the_repo} lease_hidden={lease_not_visible} "
        f"original={read_the_original} leaked={leaked} broker={broker_seen} "
        f"libcurl={route_libcurl[-1]!r}; node saw {payload[:140]}",
    )


def _write_vault(universe_dir: Path, secret: str) -> None:
    from tinyassets.credential_vault import write_credential_vault

    write_credential_vault(
        universe_dir,
        [{"credential_type": "http", "destination": "oracle", "token": secret}],
    )


def _canary_is_anywhere(
    canary: str, payload: str, evidence: dict[str, Any], roots: Sequence[Path]
) -> bool:
    """The canary must not reach the node, the evidence, or anything on disk
    except the vault it was deposited in."""
    if canary in payload or canary in str(evidence):
        return True
    for root in roots:
        for found in root.rglob("*"):
            try:
                if not found.is_file() or "vault" in found.name:
                    continue
                if canary.encode() in found.read_bytes():
                    return True
            except OSError:
                continue
    return False


#: Every check, in the order the report prints them.
CHECKS: tuple[Check, ...] = (
    Check(
        "bind_survives_a_rename",
        "an fd-bound workspace still reads the original lease after a mid-run swap",
        check_bind_survives_a_rename,
    ),
    Check(
        "jail_kill_reaps_a_double_fork",
        "a ws.run timeout fails the node and leaves no setsid sleeper alive",
        check_jail_kill_reaps_a_double_fork,
    ),
    Check(
        "jail_has_no_network_no_data_no_escape",
        "the jail has no network, no /data, and nothing writable outside /workspace",
        check_jail_has_no_network_no_data_no_escape,
    ),
    Check(
        "ws_bundle_imports_under_fsck",
        "a jail-made bundle survives verify plus the fsck-checked import",
        check_ws_bundle_imports_under_fsck,
    ),
    Check(
        "run_git_timeout_reaps_a_descendant",
        "run_git's timeout kills the process group, not just the tracked child",
        check_run_git_timeout_reaps_a_descendant,
    ),
    Check(
        "libcurl_multi_resolve_is_honoured",
        "this libcurl takes the comma list and honours the curloptResolve pin",
        check_libcurl_multi_resolve_is_honoured,
    ),
    Check(
        "full_route",
        "the real adapter -> chain -> compiler -> bwrap: /workspace IS the repo",
        check_full_route,
    ),
)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        for check in CHECKS:
            print(f"{check.name:<38} {check.summary}")
        return 0

    try:
        checks = select_checks(args.only)
    except KeyError as exc:
        print(f"{FAIL} selection {exc}", file=sys.stderr)
        return 2

    problems = preflight(args.temp_parent)
    if problems:
        for problem in problems:
            print(f"{FAIL} preflight {problem}", file=sys.stderr)
        print(
            "This oracle asserts Linux-only behaviour and must run inside the "
            "deployed container.",
            file=sys.stderr,
        )
        return 2

    root = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=args.temp_parent))
    context = Context(
        root=root,
        git_binary=shutil.which("git") or "git",
        bwrap_path=shutil.which("bwrap"),
        keep=bool(args.keep),
    )
    print(f"# temp root {root} (never /data)")
    results = run_checks(checks, context)
    for result in results:
        print(render(result))
    failed = [r for r in results if not r.outcome.ok and not r.outcome.skipped]
    print(f"# {len(results) - len(failed)}/{len(results)} passed")
    if context.keep:
        print(f"# kept {root}")
    else:
        shutil.rmtree(root, ignore_errors=True)
    return exit_code_for(results)


if __name__ == "__main__":
    raise SystemExit(main())
