"""The universe agent's four tools: policy, wiring and refusals (no real jail).

What a jailed call can actually reach is proven in a REAL bubblewrap jail by
``tests/test_universe_tools_jail.py`` (run and asserted by
``.github/workflows/linux-jail-proof.yml``). This module holds what is true on
any host: the tool list and where it is served, the jail argv's shape, the
fail-closed refusals, the cross-user refusal, the edit semantics, and how the
skill index reaches the prompt.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.engine_authority_helpers import mock_engine_admission, seed_engine_authority
from tinyassets import universe_tools
from tinyassets.providers import provider_jail
from tinyassets.providers.provider_jail import ProviderConfinementError, default_view, jail_argv
from tinyassets.universe_tools import ToolRun, UniverseToolError

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX descriptors and signals")

FOUR = ("read", "write", "edit", "bash")


def _universe(tmp_path: Path, name: str = "u-alpha") -> Path:
    path = tmp_path / "data" / name
    path.mkdir(parents=True)
    return path


class _Spy:
    """A RUNNER that records every jailed call and answers from a script."""

    def __init__(self, *answers: ToolRun) -> None:
        self.calls: list[dict] = []
        self._answers = list(answers)

    def __call__(self, universe_dir, inner, **kwargs):
        self.calls.append({"universe_dir": universe_dir, "inner": list(inner), **kwargs})
        if not self._answers:
            return ToolRun(0, b"", None, 0.0)
        return self._answers.pop(0)


def _ok(output: bytes = b"") -> ToolRun:
    return ToolRun(exit_code=0, output=output, killed=None, elapsed=0.0)


# ── the tool list and where it is served ────────────────────────────────────


def test_exactly_four_tools_are_served_to_the_universe_agent_on_every_adapter():
    from tinyassets import engine_mcp_server as s
    from tinyassets.providers.codex_provider import _ENGINE_MCP_ENABLED_TOOLS
    from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS
    from tinyassets.universe_intelligence import _ENGINE_MCP_ALLOWED

    assert universe_tools.TOOL_NAMES == FOUR
    registered = {tool.name for tool in asyncio.run(s.mcp.list_tools())}
    for name in FOUR:
        assert name in registered
        assert name in SERVED_ENGINE_MCP_TOOLS  # the HTTP loop discovers from this
        assert name in _ENGINE_MCP_ENABLED_TOOLS  # codex
        assert f"mcp__tinyassets__{name}" in _ENGINE_MCP_ALLOWED  # claude


def test_the_public_connector_gains_no_top_level_tool():
    from tinyassets import universe_server

    public = {tool.name for tool in asyncio.run(universe_server.mcp.list_tools())}
    assert not public & set(FOUR)
    assert {"read_graph", "write_graph", "run_graph", "read_page", "write_page",
            "converse"} <= public


def test_the_vendor_cli_file_and_shell_builtins_stay_denied():
    """The platform runs the tools; the CLI's own Read/Bash never come back."""
    from tinyassets.universe_intelligence import _ENGINE_DISALLOWED_TOOLS_WITH_MCP

    for builtin in ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "Monitor"):
        assert builtin in _ENGINE_DISALLOWED_TOOLS_WITH_MCP


def test_the_four_definitions_fit_the_harness_budget():
    """Design budget: tool definitions <= 500 tokens (chars / 4)."""
    from tinyassets import engine_mcp_server as s

    size = 0
    for tool in asyncio.run(s.mcp.list_tools()):
        if tool.name in FOUR:
            served = tool.to_mcp_tool().model_dump(exclude_none=True)
            size += len(json.dumps({k: served[k] for k in ("name", "description",
                                                           "inputSchema")}))
    assert size // 4 <= 500, size


# ── the tool jail argv ──────────────────────────────────────────────────────


def test_tool_jail_argv_has_no_network_no_env_and_only_the_universe_at_u(
    tmp_path, monkeypatch,
):
    universe = _universe(tmp_path)
    monkeypatch.setattr(provider_jail, "BWRAP_RESOLVER", lambda: "/usr/bin/bwrap")
    argv = universe_tools.tool_jail_argv(universe, ["/bin/true"])
    root = str(universe.resolve())

    assert "--share-net" not in argv
    for flag in ("--unshare-all", "--clearenv", "--die-with-parent", "--new-session"):
        assert flag in argv, flag
    bind = argv.index("/u")
    assert argv[bind - 2:bind + 1] == ["--bind", root, "/u"]
    mask = argv.index("/u/.runtime")
    assert argv[mask - 1] == "--tmpfs" and mask > bind
    assert (universe / ".runtime").is_dir(), "a mountpoint the agent cannot replace"
    # Nothing vendor-named: hidden dirs the agent makes are masked at LAUNCH.
    assert not any(a.startswith("/u/.") and a != "/u/.runtime" for a in argv)
    # Nothing else of the data root, and no credential snapshot or install tree.
    for i, arg in enumerate(argv[:-2]):
        if arg in ("--bind", "--ro-bind"):
            source = argv[i + 1]
            assert source == root or not source.startswith(str(tmp_path)), source
    env = {argv[i + 1]: argv[i + 2] for i, a in enumerate(argv) if a == "--setenv"}
    assert env["HOME"] == "/tmp" and set(env) == {"PATH", "HOME", "LANG", "TERM"}
    assert argv[argv.index("--chdir") + 1] == "/u"
    assert argv[argv.index("--") + 1:] == ["/bin/true"]


def test_a_symlinked_mask_dir_is_refused_not_followed(tmp_path, monkeypatch):
    universe = _universe(tmp_path)
    other = _universe(tmp_path, "u-bravo")
    try:
        (universe / ".runtime").symlink_to(other, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")
    monkeypatch.setattr(provider_jail, "BWRAP_RESOLVER", lambda: "/usr/bin/bwrap")
    with pytest.raises(UniverseToolError, match="not a plain directory"):
        universe_tools.tool_jail_argv(universe, ["/bin/true"])


def test_the_jail_loads_a_filter_refusing_links_and_special_files(tmp_path, monkeypatch):
    import struct

    universe = _universe(tmp_path)
    monkeypatch.setattr(provider_jail, "BWRAP_RESOLVER", lambda: "/usr/bin/bwrap")
    argv = universe_tools.tool_jail_argv(universe, ["/bin/true"], seccomp_fd=7)
    assert argv[argv.index("--seccomp") + 1] == "7"
    assert argv.index("--seccomp") < argv.index("--")

    program = universe_tools.seccomp_program()
    insns = [struct.unpack("=HBBI", program[i:i + 8]) for i in range(0, len(program), 8)]
    denied = {k for code, jt, _jf, k in insns if code == 0x15 and jt > 0}
    # x86_64: symlink, symlinkat, mknod, mknodat, io_uring setup/enter/register.
    for syscall in (88, 266, 133, 259, 425, 426, 427):
        assert syscall in denied
    # aarch64: symlinkat, mknodat, io_uring setup/enter/register.
    for syscall in (36, 33, 425, 426, 427):
        assert syscall in denied
    assert insns[-1] == (0x06, 0, 0, 0x00050001), "the deny target is EPERM"
    # Every jump lands inside the program.
    for pc, (code, jt, jf, _k) in enumerate(insns):
        if code in (0x15, 0x35):
            assert pc + 1 + max(jt, jf) < len(insns)


def test_limits_wrap_the_command_and_prove_themselves_before_it_runs(monkeypatch):
    monkeypatch.setattr(universe_tools.shutil, "which",
                        lambda name, path=None: f"/usr/bin/{name}")
    limits = universe_tools.ToolLimits(memory_bytes=1, processes=2, cpu_seconds=3,
                                       file_bytes=4, open_files=5)
    wrapped = universe_tools._limited(["/usr/bin/bash", "-c", "x"], limits, cpu_seconds=3)
    assert wrapped[0] == "/usr/bin/prlimit"
    assert wrapped[1:8] == ["--as=1", "--nproc=2", "--cpu=3:4", "--fsize=4", "--nofile=5",
                            "--core=0", "--"]
    assert wrapped[-3:] == ["/usr/bin/bash", "-c", "x"]
    assert universe_tools._LIMITS_MARK.decode() in wrapped


def test_no_prlimit_refuses_before_anything_runs(tmp_path, monkeypatch):
    universe = _universe(tmp_path)
    monkeypatch.setattr(universe_tools.shutil, "which", lambda name, path=None: None)
    spawned = []
    monkeypatch.setattr(universe_tools.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a))
    with pytest.raises(UniverseToolError, match="prlimit"):
        universe_tools.run_jailed(universe, ["/bin/true"])
    assert spawned == []


def test_no_os_sandbox_refuses_before_anything_runs(tmp_path, monkeypatch):
    universe = _universe(tmp_path)
    monkeypatch.setattr(universe_tools.shutil, "which",
                        lambda name, path=None: f"/usr/bin/{name}")

    def no_bwrap():
        raise ProviderConfinementError("provider launch refused: no OS sandbox")

    monkeypatch.setattr(provider_jail, "BWRAP_RESOLVER", no_bwrap)
    spawned = []
    monkeypatch.setattr(universe_tools.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a))
    with pytest.raises(ProviderConfinementError):
        universe_tools.run_jailed(universe, ["/bin/true"])
    assert spawned == []


@posix_only
def test_a_jail_that_never_proves_its_limits_is_refused(tmp_path, monkeypatch):
    """Output without the marker means the limits were not in place: refuse."""
    universe = _universe(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(universe_tools.shutil, "which",
                        lambda name, path=None: f"/usr/bin/{name}")
    monkeypatch.setattr(universe_tools, "TOOL_JAIL_ARGV",
                        lambda udir, inner, **_kw: ["/bin/sh", "-c", "echo unlimited output"])
    with pytest.raises(UniverseToolError, match="did not start under its resource limits"):
        universe_tools.run_jailed(universe, ["/bin/true"])


@posix_only
def test_a_root_run_jail_without_a_cgroup_is_refused(tmp_path, monkeypatch):
    """Root is exempt from RLIMIT_NPROC: no cgroup to hold it, no call."""
    universe = _universe(tmp_path)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(universe_tools.os, "geteuid", lambda: 0)
    monkeypatch.setattr(universe_tools, "CGROUP_ROOT", tmp_path / "no-cgroup")
    monkeypatch.setattr(universe_tools.shutil, "which",
                        lambda name, path=None: f"/usr/bin/{name}")
    monkeypatch.setattr(universe_tools, "TOOL_JAIL_ARGV",
                        lambda udir, inner, **_kw: ["/bin/true"])
    spawned = []
    monkeypatch.setattr(universe_tools.subprocess, "Popen",
                        lambda *a, **k: spawned.append(a))
    with pytest.raises(UniverseToolError, match="exempts root from the process limit"):
        universe_tools.run_jailed(universe, ["/bin/true"])
    assert spawned == []


# ── the launch jail masks vendor-native harness dirs ────────────────────────


@posix_only
def test_a_provider_launch_view_masks_every_hidden_root_dir(tmp_path):
    """A CLI's own project settings dir is never a loading mechanism, for any
    CLI: every hidden root dir but .runtime is an empty tmpfs at launch."""
    universe = _universe(tmp_path).resolve()
    for name in (".claude", ".codex", ".some-future-cli"):
        (universe / name).mkdir()
        (universe / name / "settings.json").write_text('{"hooks": {}}', encoding="utf-8")
    (universe / ".runtime").mkdir()
    (universe / ".hidden-file").write_text("x", encoding="utf-8")
    view = default_view(universe)
    argv = jail_argv(["cli", "-p"], view, bwrap_path="/usr/bin/bwrap")
    for name in (".claude", ".codex", ".some-future-cli"):
        mask = argv.index(f"{universe}/{name}")
        assert argv[mask - 1] == "--tmpfs", name
        assert mask > argv.index(str(universe)), "the mask sits over the universe bind"
    assert f"{universe}/.runtime" not in argv, "the launch still needs its runtime"
    assert f"{universe}/.hidden-file" not in argv
    # A share-net launch is unchanged: only the tool jail drops the network.
    assert "--share-net" in argv and "--clearenv" not in argv


def test_a_provider_launch_refuses_a_symlinked_hidden_dir(tmp_path):
    universe = _universe(tmp_path).resolve()
    try:
        (universe / ".codex").symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")
    with pytest.raises(ProviderConfinementError, match="is a link"):
        default_view(universe)


def test_the_engine_route_bearer_config_lives_under_masked_runtime(tmp_path, monkeypatch):
    from tinyassets.providers.base import ModelConfig
    from tinyassets.providers.claude_provider import _engine_mcp_flags

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    legacy = tmp_path / ".engine_mcp_config.json"
    legacy.write_text('{"stale": "bearer"}', encoding="utf-8")
    flags = _engine_mcp_flags(
        ModelConfig(engine_mcp_actor_id="a", engine_mcp_graph_id="u-a"), tmp_path,
    )
    config = Path(flags[flags.index("--mcp-config") + 1])
    assert config == tmp_path / ".runtime" / "engine-mcp-config.json"
    assert ".runtime" in universe_tools.MASKED_DIRS
    assert not legacy.exists(), "no stale bearer left where the agent can read it"


# ── the four tools' semantics (runner substituted) ──────────────────────────


def test_edit_replaces_exactly_one_match_and_writes_it_back(tmp_path, monkeypatch):
    universe = _universe(tmp_path)
    spy = _Spy(_ok(b"alpha\nbeta\n"), _ok())
    monkeypatch.setattr(universe_tools, "RUNNER", spy)
    assert universe_tools.edit_file(universe, "notes/a.md", "beta", "gamma") == (
        "edited /u/notes/a.md"
    )
    write = spy.calls[1]
    assert write["stdin"] == b"alpha\ngamma\n"
    assert write["inner"][-1] == "/u/notes/a.md"


@pytest.mark.parametrize(("content", "expect"), [
    (b"alpha\n", "was not found"),
    (b"beta beta\n", "matches 2 places"),
])
def test_edit_refuses_an_ambiguous_or_missing_passage(tmp_path, monkeypatch, content, expect):
    universe = _universe(tmp_path)
    spy = _Spy(_ok(content))
    monkeypatch.setattr(universe_tools, "RUNNER", spy)
    assert expect in universe_tools.edit_file(universe, "a.md", "beta", "x")
    assert len(spy.calls) == 1, "nothing is written back"


def test_paths_are_the_jails_paths_and_the_jail_is_the_boundary(tmp_path, monkeypatch):
    universe = _universe(tmp_path)
    spy = _Spy()
    monkeypatch.setattr(universe_tools, "RUNNER", spy)
    universe_tools.read_file(universe, "skills/x/SKILL.md")
    universe_tools.read_file(universe, "/data/u-bravo/founder.md")
    assert spy.calls[0]["inner"][4] == "/u/skills/x/SKILL.md"
    # Not rewritten, not "cleaned": outside /u it simply does not exist in the jail.
    assert spy.calls[1]["inner"][4] == "/data/u-bravo/founder.md"
    with pytest.raises(UniverseToolError):
        universe_tools.read_file(universe, "")


@pytest.mark.parametrize(("run", "trailer"), [
    (ToolRun(0, b"hi\n", None, 0.1), "[exit code 0]"),
    (ToolRun(137, b"", "timeout", 5.0), "ran longer than"),
    (ToolRun(137, b"y\n" * 10, "output_limit", 0.1), "output passed"),
    (ToolRun(137, b"", "memory_limit", 0.1), "used more than"),
    (ToolRun(137, b"", "process_limit", 0.1), "more than 64 processes"),
    (ToolRun(137, b"", "disk_limit", 0.1), "disk was nearly full"),
    (ToolRun(152, b"", None, 2.0), "cpu time limit"),
    (ToolRun(137, b"", None, 2.0), "killed by the kernel"),
])
def test_bash_reports_how_the_command_ended(tmp_path, monkeypatch, run, trailer):
    universe = _universe(tmp_path)
    monkeypatch.setattr(universe_tools.shutil, "which",
                        lambda name, path=None: f"/usr/bin/{name}")
    monkeypatch.setattr(universe_tools, "RUNNER", _Spy(run))
    assert trailer in universe_tools.bash(universe, "echo hi")


def test_bash_clamps_its_wall_clock(tmp_path, monkeypatch):
    universe = _universe(tmp_path)
    monkeypatch.setattr(universe_tools.shutil, "which",
                        lambda name, path=None: f"/usr/bin/{name}")
    spy = _Spy(_ok(), _ok())
    monkeypatch.setattr(universe_tools, "RUNNER", spy)
    universe_tools.bash(universe, "true", timeout=99999)
    universe_tools.bash(universe, "true")
    assert spy.calls[0]["wall_seconds"] == universe_tools.MAX_BASH_SECONDS
    assert spy.calls[1]["wall_seconds"] == universe_tools.DEFAULT_LIMITS.wall_seconds


# ── cross-user refusal through the engine surface ───────────────────────────


def _bind_engine(monkeypatch, root: Path, *, actor: str, graph: str):
    import tinyassets.api.helpers as helpers
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(helpers, "_base_path", lambda: root)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    return s


def _call_all_four(s) -> list[str]:
    return [
        asyncio.run(s.read_file(path="founder.md")),
        asyncio.run(s.write_file(path="notes/x.md", content="x")),
        asyncio.run(s.edit_file(path="founder.md", old_text="a", new_text="b")),
        asyncio.run(s.run_bash(command="cat founder.md")),
    ]


def test_another_user_cannot_drive_the_tools_over_someone_elses_universe(
    tmp_path, monkeypatch,
):
    """Real SQLite authority: universe A is owned by actor A. An engine bound to
    actor B and pinned at A refuses every tool before any jail is built."""
    root = tmp_path / "data"
    root.mkdir()
    (root / "u-a").mkdir()
    (root / "u-a" / "founder.md").write_text("A's private founder notes", encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    seed_engine_authority(root, actor="actor-a", graph="u-a")
    seed_engine_authority(root, actor="actor-b", graph="u-b")
    spy = _Spy()
    monkeypatch.setattr(universe_tools, "RUNNER", spy)

    s = _bind_engine(monkeypatch, root, actor="actor-b", graph="u-a")
    for out in _call_all_four(s):
        assert "current serving owner authority" in out, out
        assert "private founder notes" not in out
    assert spy.calls == [], "no jail was built for a foreign universe"

    # Control: the real owner, same universe, same code path, reaches the runner.
    s = _bind_engine(monkeypatch, root, actor="actor-a", graph="u-a")
    monkeypatch.setattr(universe_tools.shutil, "which",
                        lambda name, path=None: f"/usr/bin/{name}")
    _call_all_four(s)
    assert spy.calls and all(c["universe_dir"] == root / "u-a" for c in spy.calls)


def test_an_unbound_engine_refuses_every_tool(monkeypatch):
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", "")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-x")
    mock_engine_admission(monkeypatch, {"u-x"})
    for out in _call_all_four(s):
        assert "refusing" in out


def test_a_jail_refusal_reaches_the_agent_as_an_error_not_a_crash(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "u-a").mkdir(parents=True)
    s = _bind_engine(monkeypatch, root, actor="actor-a", graph="u-a")
    mock_engine_admission(monkeypatch, {"u-a"})

    def refuse(*_a, **_k):
        raise ProviderConfinementError("provider launch refused: no OS sandbox")

    monkeypatch.setattr(universe_tools, "RUNNER", refuse)
    assert asyncio.run(s.read_file(path="x")).startswith("error: provider launch refused")


# ── the skill index reaches the prompt ──────────────────────────────────────

_SKILL = (
    "---\nname: standup\ndescription: When my founder says standup, answer with "
    "Yesterday / Today / Blockers bullets.\n---\n\nThree bullets.\n"
)


@posix_only
def test_skill_index_lists_name_and_description_only(tmp_path):
    universe = _universe(tmp_path)
    (universe / "skills" / "standup").mkdir(parents=True)
    (universe / "skills" / "standup" / "SKILL.md").write_text(_SKILL, encoding="utf-8")
    (universe / "skills" / "nodesc").mkdir()
    (universe / "skills" / "nodesc" / "SKILL.md").write_text("no frontmatter", encoding="utf-8")
    prompt = universe_tools.harness_prompt(universe)
    assert "- `standup`: When my founder says standup" in prompt
    assert "Three bullets" not in prompt, "the body is read on demand, not preloaded"
    assert "nodesc" not in prompt


@posix_only
def test_a_skill_file_symlinked_elsewhere_is_never_read_into_the_prompt(tmp_path):
    universe = _universe(tmp_path)
    foreign = _universe(tmp_path, "u-bravo") / "SKILL.md"
    foreign.write_text(_SKILL.replace("standup", "stolen"), encoding="utf-8")
    (universe / "skills" / "stolen").mkdir(parents=True)
    (universe / "skills" / "stolen" / "SKILL.md").symlink_to(foreign)
    (universe / "skills" / "linkdir").symlink_to(foreign.parent, target_is_directory=True)
    assert universe_tools.skill_index(universe) == []


# ── untrusted universe files: the shared safe reader and skill parse ─────────


def test_skill_description_never_hands_frontmatter_to_a_yaml_loader():
    """An alias bomb expands to gigabytes under yaml.safe_load; the flat parse
    returns fast with bounded memory and no description."""
    bomb = (
        "---\n"
        "a: &a [x,x,x,x,x,x,x,x,x]\n"
        "b: &b [*a,*a,*a,*a,*a,*a,*a,*a,*a]\n"
        "c: &c [*b,*b,*b,*b,*b,*b,*b,*b,*b]\n"
        "d: &d [*c,*c,*c,*c,*c,*c,*c,*c,*c]\n"
        "description: *d\n"
        "---\n"
    ).encode("utf-8")
    # The value is a YAML alias, never expanded: it is read as the literal text.
    out = universe_tools._skill_description(bomb)
    assert out == "*d"
    assert len(bomb) < 300 and len(out) < 300


def test_skill_description_caps_length_before_building_a_string():
    huge = ("---\ndescription: " + "z" * 100_000 + "\n---\n").encode("utf-8")
    out = universe_tools._skill_description(huge)
    assert len(out) <= universe_tools._MAX_DESCRIPTION_CHARS


@pytest.mark.parametrize("body", [
    b"no frontmatter at all",
    b"---\nname: x\n---\nno description key\n",
    b"---\ndescription:\n---\n",
    b"\xff\xfe not even utf-8 \x00",
    b"---\n" + b"description: " + "é".encode() * 10 + b"\n---\n",
])
def test_skill_description_never_raises(body):
    universe_tools._skill_description(body)  # returns a str, never throws


@posix_only
def test_skill_index_leaves_out_a_bad_skill_without_breaking(tmp_path):
    universe = _universe(tmp_path)
    (universe / "skills" / "good").mkdir(parents=True)
    (universe / "skills" / "good" / "SKILL.md").write_text(_SKILL, encoding="utf-8")
    (universe / "skills" / "bomb").mkdir()
    (universe / "skills" / "bomb" / "SKILL.md").write_text(
        "---\ndescription: &a [*a]\n---\n", encoding="utf-8",
    )
    names = {name for name, _ in universe_tools.skill_index(universe)}
    assert "good" in names  # the turn still gets the working skills


def test_read_universe_file_refuses_a_symlink_component(tmp_path):
    from tinyassets.universe_files import read_universe_file

    universe = _universe(tmp_path)
    (universe / "founder.md").write_text("mine", encoding="utf-8")
    assert read_universe_file(universe, "founder.md") == b"mine"
    outside = tmp_path / "secret.txt"
    outside.write_text("SOMEONE ELSE", encoding="utf-8")
    try:
        (universe / "leak.md").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")
    with pytest.raises(OSError):
        read_universe_file(universe, "leak.md")


def test_read_universe_file_bounds_size(tmp_path):
    from tinyassets.universe_files import read_universe_file

    universe = _universe(tmp_path)
    (universe / "big.md").write_text("z" * 5000, encoding="utf-8")
    assert read_universe_file(universe, "big.md", max_bytes=10_000) == b"z" * 5000
    with pytest.raises(OSError):
        read_universe_file(universe, "big.md", max_bytes=100)


def test_a_planted_link_is_not_followed_by_the_persona_read(tmp_path):
    """A link that already exists (planted from outside, or via io_uring the
    seccomp cannot see) is refused by the daemon-side bundle read."""
    import tinyassets.universe_intelligence as ui

    universe = _universe(tmp_path)
    secret = tmp_path / "other" / "founder.md"
    secret.parent.mkdir()
    secret.write_text("ANOTHER USER'S PRIVATE FOUNDER", encoding="utf-8")
    (universe / "founder.md").write_text("my own founder notes", encoding="utf-8")
    assert ui._read_bundle_body(universe, "founder.md") == "my own founder notes"
    (universe / "founder.md").unlink()
    try:
        (universe / "founder.md").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")
    assert ui._read_bundle_body(universe, "founder.md") == ""


def _founder_turn(monkeypatch, root: Path, uid: str, message: str, *, founder: bool):
    """One real converse turn; returns the system prompt the model received."""
    import tinyassets.universe_intelligence as ui
    from tinyassets.auth import middleware as auth

    seen: dict = {}

    def model(prompt, system="", **_kw):
        seen["system"] = system
        return "ok"

    monkeypatch.setattr(ui, "_request_universe", lambda universe_id="": uid)
    monkeypatch.setattr(ui, "_universe_dir", lambda _uid: root / uid)
    monkeypatch.setattr(ui, "call_provider", model)
    monkeypatch.setattr(ui, "_build_persona_system_prompt", lambda *a, **k: "I am u.")
    monkeypatch.setattr(ui, "extract_learning", lambda *a, **k: None)
    monkeypatch.setattr(ui, "commit_learning", lambda *a, **k: None)
    tier = ui.interlocutor.FOUNDER if founder else ui.interlocutor.T1
    monkeypatch.setattr(ui.interlocutor, "resolve_interlocutor_tier",
                        lambda *_a, **_k: SimpleNamespace(tier=tier))
    reserve = auth.reserve_provider_request(
        principal_id="actor-a", session_id="s", request_id=message, tool_name="converse",
    )
    capability = auth.claim_provider_request(reserve, tool_name="converse")
    try:
        ui.converse(uid, message)
    finally:
        auth.revoke_provider_request(capability)
    return seen["system"]


@posix_only
def test_only_a_founder_turn_with_the_tools_is_shown_the_folder_and_skills(
    tmp_path, monkeypatch,
):
    root = tmp_path / "data"
    (root / "u-a" / "skills" / "standup").mkdir(parents=True)
    (root / "u-a" / "skills" / "standup" / "SKILL.md").write_text(_SKILL, encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    seed_engine_authority(root, actor="actor-a", graph="u-a")

    founder = _founder_turn(monkeypatch, root, "u-a", "hi", founder=True)
    assert "# My folder and my four tools" in founder
    assert "- `standup`:" in founder

    visitor = _founder_turn(monkeypatch, root, "u-a", "hi again", founder=False)
    assert "My folder" not in visitor and "standup" not in visitor

    monkeypatch.delenv("TINYASSETS_ENGINE_MCP_TOOLS")
    dark = _founder_turn(monkeypatch, root, "u-a", "hi dark", founder=True)
    assert "My folder" not in dark
