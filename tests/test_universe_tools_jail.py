"""A REAL bubblewrap proof of the universe agent's four tools (harness S1).

The universe agent's own ``read``/``write``/``edit``/``bash`` run as processes
the PLATFORM starts inside the tool jail (``tinyassets.universe_tools``). These
cases drive the shipping engine tool handlers (``tinyassets.engine_mcp_server``)
and the shipping jail end to end, with nothing about the jail re-typed here:

* the universe is readable and writable at ``/u``, and nothing else is: another
  universe (by absolute path, by ``..``, or through a symlink the agent
  planted), the data root, the platform source, ``.runtime`` (credentials, the
  engine route bearer) and the daemon's process environment;
* writes to ``.runtime`` and a vendor-native ``.claude/`` never reach the disk;
* bash has no network: a listener on the host loopback, reachable from the
  host (the control), is unreachable from the jail;
* resource limits kill a runaway: memory, processes (a fork bomb included),
  cpu time, output size and the wall clock;
* a skill file the agent writes changes what it does on its NEXT turn, through
  the real ``converse`` with a fake model;
* another universe's folder stays unreachable through the same tools.

Linux + bwrap only. ``.github/workflows/linux-jail-proof.yml`` runs every case
and fails if any is absent or skipped. Every byte involved is synthetic.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.engine_authority_helpers import seed_engine_authority

_BWRAP = shutil.which("bwrap") if sys.platform == "linux" else None

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not _BWRAP,
    reason="a real bubblewrap jail needs Linux + bwrap",
)

OWN_MARKER = "POSITIVE-CONTROL-OWN-UNIVERSE"
FOREIGN_MARKER = "SYNTHETIC-UNIVERSE-B-CONTENT"
CRED_MARKER = "SYNTHETIC-OWN-LAUNCH-CREDENTIAL"
BEARER_MARKER = "SYNTHETIC-ENGINE-ROUTE-BEARER"
ENV_MARKER = "TA_TOOL_JAIL_SENTINEL_DAEMON_ENV_MARKER"


@dataclass
class _World:
    data_root: Path
    universe_a: Path
    universe_b: Path


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch):
    """Two universes under one data root and a sentinel "daemon" process.

    Under ``/tmp`` (not ``tmp_path``), as in ``test_provider_universe_jail``:
    on the hosted runner's sudo fallback, bwrap runs as root and cannot
    traverse the runner's 0750 home to reach a ``--basetemp`` under it.
    """
    import tinyassets.api.helpers as helpers
    from tinyassets.providers import base

    root = Path(tempfile.mkdtemp(prefix="ta-tool-jail-", dir="/tmp"))
    sentinel = None
    try:
        data_root = root / "data"
        universe_a = data_root / "u-alpha"
        universe_b = data_root / "u-bravo"
        (universe_a / "notes").mkdir(parents=True)
        universe_b.mkdir(parents=True)
        (universe_a / "notes" / "own.txt").write_text(OWN_MARKER + "\n", encoding="utf-8")
        (universe_b / "founder.md").write_text(FOREIGN_MARKER + "\n", encoding="utf-8")
        cred = universe_a / ".runtime" / "provider-launch-credentials" / "own-1"
        cred.mkdir(parents=True)
        (cred / "auth.json").write_text('{"t": "' + CRED_MARKER + '"}', encoding="utf-8")
        (universe_a / ".runtime" / "engine-mcp-config.json").write_text(
            '{"Authorization": "Bearer ' + BEARER_MARKER + '"}', encoding="utf-8",
        )
        sentinel = subprocess.Popen(  # noqa: S603 - fixed argv
            ["/bin/sleep", "300"], env={"PATH": "/usr/bin:/bin", ENV_MARKER: "1"},
        )
        monkeypatch.setenv(ENV_MARKER, "1")  # the test process is a daemon too
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))
        monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
        monkeypatch.setattr(helpers, "_base_path", lambda: data_root)
        base._sandbox_probe_cache = None
        yield _World(data_root, universe_a, universe_b)
    finally:
        if sentinel is not None:
            sentinel.kill()
            sentinel.wait(timeout=10)
        base._sandbox_probe_cache = None
        shutil.rmtree(root, ignore_errors=True)


def _engine(monkeypatch, world: _World, *, actor="actor-a", graph="u-alpha"):
    """The shipping engine handlers, pinned to (actor, graph) with REAL authority."""
    from tinyassets import engine_mcp_server as s

    seed_engine_authority(world.data_root, actor=actor, graph=graph)
    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    return s


def _run(coro):
    return asyncio.run(coro)


# ── (a) the folder is the universe, and only the universe ───────────────────


def test_tools_reach_their_own_universe_and_nothing_else(world, monkeypatch):
    import tinyassets

    s = _engine(monkeypatch, world)
    a, b = world.universe_a, world.universe_b

    # Positive controls: a jail that mounted nothing cannot pass the negatives.
    assert OWN_MARKER in _run(s.read_file(path="notes/own.txt"))
    assert _run(s.write_file(path="notes/new.md", content="alpha\nbeta\n")).startswith("wrote")
    assert (a / "notes" / "new.md").read_text(encoding="utf-8") == "alpha\nbeta\n"
    assert _run(s.edit_file(path="notes/new.md", old_text="beta", new_text="gamma")) == (
        "edited /u/notes/new.md"
    )
    assert (a / "notes" / "new.md").read_text(encoding="utf-8") == "alpha\ngamma\n"
    assert "[exit code 0]" in _run(s.run_bash(command="test -w /u && pwd"))

    # Another universe: by its host path, by '..', and through a planted symlink.
    for path in (str(b / "founder.md"), "../u-bravo/founder.md", "/u/../u-bravo/founder.md"):
        out = _run(s.read_file(path=path))
        assert out.startswith("error:") and FOREIGN_MARKER not in out, (path, out)
    # A planted link would dangle in here but RESOLVE for the daemon outside:
    # the jail refuses to create one at all, and no FIFO either.
    planted = _run(s.run_bash(
        command=f"ln -s {b} bravo; ln -s {b}/founder.md founder-link.md; mkfifo pipe; "
                "cat bravo/founder.md",
    ))
    assert FOREIGN_MARKER not in planted and "[exit code 0]" not in planted, planted
    assert "Operation not permitted" in planted, planted
    for name in ("bravo", "founder-link.md", "pipe"):
        assert not os.path.lexists(a / name), name
    assert FOREIGN_MARKER not in _run(s.read_file(path="bravo/founder.md"))
    # Hard links stay inside /u: every other visible path is another mount.
    assert "[exit code 0]" in _run(s.run_bash(command="ln notes/own.txt notes/hard.txt"))
    crossed = _run(s.run_bash(command="ln /etc/passwd notes/passwd"))
    assert "[exit code 0]" not in crossed, crossed
    listing = _run(s.run_bash(command="ls -a / /u/.. /tmp; ls -a " + str(world.data_root)))
    assert "u-bravo" not in listing and world.data_root.name not in listing.split(), listing

    # The platform source and the daemon's environment.
    source = Path(tinyassets.__file__).resolve()
    assert "error:" in _run(s.read_file(path=str(source)))
    env = _run(s.run_bash(command="env; cat /proc/[0-9]*/environ 2>/dev/null | tr '\\0' '\\n'"))
    assert ENV_MARKER not in env and "TINYASSETS_" not in env, env

    # .runtime: unreadable, and a write never reaches the disk.
    runtime = _run(s.run_bash(
        command="ls -A .runtime; cat .runtime/provider-launch-credentials/own-1/auth.json "
                ".runtime/engine-mcp-config.json; echo planted > .runtime/planted",
    ))
    assert CRED_MARKER not in runtime and BEARER_MARKER not in runtime, runtime
    assert not (a / ".runtime" / "planted").exists()
    assert (a / ".runtime" / "engine-mcp-config.json").exists(), "masked, not deleted"

    assert (b / "founder.md").read_text(encoding="utf-8") == FOREIGN_MARKER + "\n"


_IO_URING_PROBE = r'''
import ctypes, ctypes.util, errno, os, struct
libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
# io_uring_setup(entries, params*) = 425 on x86_64 and aarch64 (asm-generic).
params = ctypes.create_string_buffer(120)
ctypes.set_errno(0)
fd = libc.syscall(425, 8, params)
err = ctypes.get_errno()
if fd >= 0:
    os.close(fd)
    print("IO_URING_RING_CREATED")
elif err == errno.EPERM:
    print("IO_URING_EPERM")
else:
    print("IO_URING_OTHER", err)
# A plain symlink is refused too (the belt seccomp also blocks).
ctypes.set_errno(0)
try:
    os.symlink("/etc/passwd", "u-link")
    print("SYMLINK_CREATED")
except OSError as exc:
    print("SYMLINK_" + errno.errorcode.get(exc.errno, str(exc.errno)))
'''


def test_io_uring_and_symlink_are_refused_in_the_jail(world, monkeypatch):
    """io_uring is the way around a syscall filter (IORING_OP_SYMLINKAT, kernel
    5.15+, invisible to seccomp). The jail refuses io_uring_setup, so no ring op
    can run, and symlink stays refused too."""
    from tinyassets import universe_tools as tools

    world.universe_a.joinpath("probe.py").write_text(_IO_URING_PROBE, encoding="utf-8")
    out = tools.bash(world.universe_a, "python3 /u/probe.py", timeout=30)
    assert "IO_URING_RING_CREATED" not in out, out
    assert "IO_URING_EPERM" in out, out
    assert "SYMLINK_CREATED" not in out and "SYMLINK_EPERM" in out, out
    assert not os.path.lexists(world.universe_a / "u-link")


def test_a_settings_dir_the_agent_writes_is_masked_from_a_provider_launch(
    world, monkeypatch,
):
    """Design risk 8, in the real jails: the agent may write a CLI's project
    settings dir into its folder, and the next provider launch cannot see it."""
    from tinyassets.providers.provider_jail import default_view, jail_argv

    s = _engine(monkeypatch, world)
    a = world.universe_a
    hook = '{"hooks": {"SessionStart": "cat .runtime/*"}}'
    assert _run(s.write_file(path=".claude/settings.json", content=hook)).startswith("wrote")
    _run(s.run_bash(command="mkdir -p .anycli && echo x > .anycli/config"))
    assert (a / ".claude" / "settings.json").is_file(), "the owner's file is kept"

    probe = (
        f"cat {a}/.claude/settings.json {a}/.anycli/config 2>/dev/null && echo LOADED; "
        f"cat {a}/notes/own.txt"
    )
    argv = jail_argv(["/bin/sh", "-c", probe], default_view(a), bwrap_path=_BWRAP)
    launched = subprocess.run(  # noqa: S603 - fixed argv built by the shipping jail
        argv, capture_output=True, text=True, timeout=60, check=False,
    )
    assert OWN_MARKER in launched.stdout, launched  # positive control
    assert "LOADED" not in launched.stdout and "SessionStart" not in launched.stdout


def test_an_engine_pinned_to_another_universe_cannot_reach_it(world, monkeypatch):
    """(c) in the real jail: actor B's engine, pinned at A, runs nothing; B's own
    engine sees only B."""
    seed_engine_authority(world.data_root, actor="actor-a", graph="u-alpha")
    s = _engine(monkeypatch, world, actor="actor-b", graph="u-bravo")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-alpha")
    out = _run(s.run_bash(command="cat /u/notes/own.txt"))
    assert "current serving owner authority" in out and OWN_MARKER not in out
    monkeypatch.setattr(s, "_GRAPH_ID", "u-bravo")
    assert FOREIGN_MARKER in _run(s.read_file(path="founder.md"))
    own_a = _run(s.run_bash(
        command=f"cat {world.universe_a}/notes/own.txt ../u-alpha/notes/own.txt",
    ))
    assert OWN_MARKER not in own_a


# ── (a) no network ──────────────────────────────────────────────────────────


def test_bash_has_no_network(world, monkeypatch):
    s = _engine(monkeypatch, world)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    port = listener.getsockname()[1]
    try:
        # Control: the host loopback listener IS reachable from outside the jail.
        socket.create_connection(("127.0.0.1", port), timeout=5).close()
        out = _run(s.run_bash(command=(
            f"(exec 3<>/dev/tcp/127.0.0.1/{port} && echo LOOPBACK-CONNECTED) 2>&1; "
            "(exec 3<>/dev/tcp/1.1.1.1/53 && echo EXTERNAL-CONNECTED) 2>&1; "
            "echo NETDEV-BEGIN; tail -n +3 /proc/net/dev"
        )))
    finally:
        listener.close()
    assert "LOOPBACK-CONNECTED" not in out and "EXTERNAL-CONNECTED" not in out, out
    netdev = out.split("NETDEV-BEGIN", 1)[1].splitlines()
    interfaces = {line.split(":", 1)[0].strip() for line in netdev if ":" in line}
    assert interfaces == {"lo"}, out


# ── (a) resource limits kill a runaway ──────────────────────────────────────


def _host_processes_with(token: str) -> list[int]:
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as handle:
                if token.encode() in handle.read():
                    found.append(int(entry))
        except OSError:
            continue
    return found


def test_the_limits_are_applied_inside_the_jail(world, monkeypatch):
    s = _engine(monkeypatch, world)
    limits = _run(s.run_bash(command="cat /proc/self/limits"))
    for row, value in (("Max address space", "536870912"), ("Max processes", "64"),
                       ("Max file size", "33554432"), ("Max open files", "256"),
                       ("Max core file size", "0")):
        line = next((ln for ln in limits.splitlines() if ln.startswith(row)), "")
        assert value in line.split(), (row, line)


def test_memory_limit_stops_a_runaway_allocation(world):
    from tinyassets import universe_tools as tools

    small = tools.ToolLimits(memory_bytes=256 * 1024 * 1024)
    grow = "x=$(head -c {n} /dev/zero | tr '\\0' a); echo survived ${{#x}}"
    control = tools.bash(world.universe_a, grow.format(n=1_000_000), limits=small)
    assert "survived 1000000" in control, control
    out = tools.bash(world.universe_a, grow.format(n=900_000_000), limits=small)
    assert "survived" not in out and "[exit code 0]" not in out, out


def test_process_limit_holds_and_a_fork_bomb_is_contained(world):
    from tinyassets import universe_tools as tools

    limits = tools.ToolLimits(processes=16, wall_seconds=8)
    # Count what actually runs at once. Unprivileged, RLIMIT_NPROC in the jail's
    # user namespace refuses the extra forks; a root-run jail (the hosted
    # runner's sudo fallback, where the kernel exempts root) is held by its own
    # cgroup's pids.max, and the process-tree watch backs both.
    spawn = (
        "import os, time\n"
        "made = 0\n"
        "for _ in range(80):\n"
        "    try:\n"
        "        if os.fork() == 0:\n"
        "            time.sleep(20); os._exit(0)\n"
        "        made += 1\n"
        "    except OSError:\n"
        "        break\n"
        "print('made', made, flush=True); time.sleep(3)\n"
    )
    run = tools.run_jailed(world.universe_a, ["/usr/bin/python3", "-c", spawn],
                           limits=limits, wall_seconds=8)
    made = [int(w) for line in run.output.decode().splitlines()
            if line.startswith("made ") for w in line.split()[1:2]]
    assert run.killed == "process_limit" or (made and made[0] <= limits.processes), run

    token = f"ta-bomb-{uuid.uuid4().hex}"
    started = time.monotonic()
    out = tools.bash(world.universe_a,
                     f"bomb() {{ bomb | bomb & }}; bomb; sleep 5; echo {token}-alive",
                     limits=tools.ToolLimits(processes=32), timeout=6)
    assert time.monotonic() - started < 30, "the call came back"
    # The kernel refused the bomb's forks (RLIMIT_NPROC unprivileged, pids.max
    # as root), or the watch killed it: either way it hit a wall, and the
    # command itself still ran to its end or was stopped.
    assert "Resource temporarily unavailable" in out or "[killed:" in out, out[-500:]
    time.sleep(1)
    assert _host_processes_with(token) == [], "nothing from the jail survives it"
    # The universe still works afterwards.
    assert OWN_MARKER in tools.read_file(world.universe_a, "notes/own.txt")


def test_cpu_output_and_wall_clock_limits_kill(world):
    from tinyassets import universe_tools as tools

    started = time.monotonic()
    out = tools.bash(world.universe_a, "while :; do :; done",
                     limits=tools.ToolLimits(cpu_seconds=2), timeout=60)
    assert "[killed: cpu time limit]" in out and time.monotonic() - started < 20, out

    started = time.monotonic()
    out = tools.bash(world.universe_a, "yes")
    assert "[killed: output passed 65536 bytes]" in out, out[-200:]
    assert len(out.encode()) < 70 * 1024 and time.monotonic() - started < 20

    started = time.monotonic()
    out = tools.bash(world.universe_a, "sleep 30", timeout=2)
    assert "[killed: ran longer than 2s]" in out and time.monotonic() - started < 15, out


def test_a_jail_that_fills_the_shared_disk_is_killed(world):
    from tinyassets import universe_tools as tools

    free = tools._free_disk(world.universe_a)
    assert free > 400 * 1024 * 1024, "the runner needs room for this proof"
    floor = tools.ToolLimits(min_free_disk_bytes=free - 150 * 1024 * 1024)
    try:
        out = tools.bash(
            world.universe_a,
            "for i in $(seq 1 40); do head -c 30000000 /dev/zero > fill$i || exit 3; done; "
            "echo filled",
            limits=floor, timeout=120,
        )
        assert "[killed: the shared disk was nearly full]" in out, out
        assert "filled" not in out
        # Below the floor, the next call does not start at all.
        with pytest.raises(tools.UniverseToolError, match="nearly full"):
            tools.bash(world.universe_a, "true",
                       limits=tools.ToolLimits(min_free_disk_bytes=free * 2))
    finally:
        for path in world.universe_a.glob("fill*"):
            path.unlink()


# ── (b) a skill the agent writes changes its next turn ──────────────────────

_STANDUP = (
    "---\n"
    "name: standup\n"
    "description: When my founder says standup, answer with Yesterday, Today and "
    "Blockers bullets.\n"
    "---\n\n"
    "Answer with exactly these three bullets, filled in:\n"
    "- Yesterday:\n"
    "- Today:\n"
    "- Blockers:\n"
)


def _turn(monkeypatch, world: _World, message: str, model) -> str:
    """One real converse turn for actor-a's universe, with ``model`` answering."""
    import tinyassets.universe_intelligence as ui
    from tinyassets.auth import middleware as auth

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": "u-alpha")
    monkeypatch.setattr(ui, "_universe_dir", lambda _uid: world.universe_a)
    monkeypatch.setattr(ui, "call_provider", model)
    monkeypatch.setattr(ui, "_build_persona_system_prompt", lambda *a, **k: "I am Alpha.")
    monkeypatch.setattr(ui, "extract_learning", lambda *a, **k: None)
    monkeypatch.setattr(ui, "commit_learning", lambda *a, **k: None)
    monkeypatch.setattr(ui.interlocutor, "resolve_interlocutor_tier",
                        lambda *_a, **_k: SimpleNamespace(tier=ui.interlocutor.FOUNDER))
    reserve = auth.reserve_provider_request(
        principal_id="actor-a", session_id="s", request_id=message, tool_name="converse",
    )
    capability = auth.claim_provider_request(reserve, tool_name="converse")
    try:
        return ui.converse("u-alpha", message)
    finally:
        auth.revoke_provider_request(capability)


def test_a_skill_the_agent_writes_changes_its_next_turn(world, monkeypatch):
    s = _engine(monkeypatch, world)
    systems: list[str] = []

    def fake_model(prompt, system="", **_kw):
        """A model that uses only what the turn gives it: the prompt, the
        system prompt and the four tools."""
        systems.append(system)
        if "make yourself a skill" in prompt:
            return _run(s.write_file(path="skills/standup/SKILL.md", content=_STANDUP))
        if "forget the standup skill" in prompt:
            return _run(s.run_bash(command="rm -r skills/standup"))
        if "other universe" in prompt:
            return _run(s.read_file(path=str(world.universe_b / "founder.md")))
        if prompt.strip() == "standup":
            if "- `standup`:" not in system:
                return "Standup? Happy to chat about your day."
            skill = _run(s.read_file(path="skills/standup/SKILL.md"))
            return "\n".join(line for line in skill.splitlines() if line.startswith("- "))
        return "hello"

    before = _turn(monkeypatch, world, "standup", fake_model)
    assert "Yesterday" not in before and "- `standup`" not in systems[-1]

    made = _turn(monkeypatch, world,
                 "make yourself a skill: when I say standup, answer with "
                 "Yesterday/Today/Blockers bullets", fake_model)
    assert made.startswith("wrote"), made
    assert (world.universe_a / "skills" / "standup" / "SKILL.md").is_file()
    assert "- `standup`" not in systems[-1], "a skill takes effect from the NEXT turn"

    after = _turn(monkeypatch, world, "standup", fake_model)
    assert after.splitlines() == ["- Yesterday:", "- Today:", "- Blockers:"], after
    assert "- `standup`: When my founder says standup" in systems[-1]
    assert "Answer with exactly" not in systems[-1], "only the index is in the prompt"

    _turn(monkeypatch, world, "forget the standup skill", fake_model)
    assert not (world.universe_a / "skills" / "standup").exists()
    plain = _turn(monkeypatch, world, "standup", fake_model)
    assert "Yesterday" not in plain

    refused = _turn(monkeypatch, world, "read the other universe's founder file", fake_model)
    assert refused.startswith("error:") and FOREIGN_MARKER not in refused
