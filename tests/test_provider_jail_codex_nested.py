"""A REAL proof that a codex command runs inside our jail with its OWN sandbox
off, and that the jail then refuses what a nested sandbox would have needed.

The provider jail is the boundary. The codex adapter stops nesting codex's own
``--sandbox workspace-write`` bubblewrap for a confined launch
(``--dangerously-bypass-approvals-and-sandbox``), so the jail's seccomp filter
can deny new user namespaces and symlinks the same as the tool jail. This runs a
real codex command through the shipping ``confine_launch`` and proves: the
command runs and writes its own universe, ``ln`` is refused (the planted-link
cross-user vector is closed), and the daemon's per-universe state at the root is
unreadable. The contrast case keeps codex's own sandbox (workspace-write) and
shows ``ln`` SUCCEEDS, so the deny is live rather than vacuous.

Uses ``codex sandbox`` with an explicit ``sandbox_mode`` as a stand-in for what
``codex exec`` does per command (run with or without its own sandbox) -- it needs
no model call. Linux + bwrap + the codex CLI only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_BWRAP = shutil.which("bwrap") if sys.platform == "linux" else None
_CODEX = shutil.which("codex", path="/opt/codex-install/node_modules/.bin:/usr/local/bin:/usr/bin:/bin") \
    if sys.platform == "linux" else None

pytestmark = [
    pytest.mark.skipif(
        sys.platform != "linux" or not _BWRAP or not _CODEX,
        reason="needs Linux, bwrap and the codex CLI",
    ),
    pytest.mark.real_jail,
]

_PATH = "/opt/codex-install/node_modules/.bin:/usr/local/bin:/usr/bin:/bin"


@pytest.fixture
def world():
    root = Path(tempfile.mkdtemp(prefix="ta-cxnest-", dir="/tmp"))
    try:
        u = root / "u-alpha"
        (u / ".runtime" / "codex").mkdir(parents=True)
        (u / ".runs.db").write_text("OWN-DB-SECRET", encoding="utf-8")
        (u / "notes").mkdir()
        other = root / "u-bravo"
        other.mkdir()
        (other / "secret.txt").write_text("B-SECRET", encoding="utf-8")
        from tinyassets.providers import base
        base._sandbox_probe_cache = None
        yield u, other
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _run_codex(universe: Path, sandbox_mode: str) -> str:
    from tinyassets.providers.provider_jail import confine_launch, provider_launch_scope

    env = {
        "PATH": _PATH, "HOME": "/tmp", "TMPDIR": "/tmp",
        "CODEX_HOME": str(universe / ".runtime" / "codex"),
        "OPENAI_API_KEY": "sk-proj-" + "x" * 60,
    }
    script = (
        "echo RUNCMD; "
        f"touch {universe}/notes/made && echo WROTE_OWN; "
        f"cat {universe}/.runs.db 2>&1 | head -1; "
        f"ln -s {universe.parent}/u-bravo/secret.txt {universe}/notes/lnk "
        "2>&1 && echo LINKED || echo LINK_BLOCKED"
    )
    argv = ["codex", "sandbox", "-c", f'sandbox_mode="{sandbox_mode}"',
            "--", "/bin/sh", "-c", script]
    with provider_launch_scope(universe):
        launch = confine_launch(argv, env=env)
    try:
        r = subprocess.run(launch.argv, env=env, capture_output=True, text=True,
                           timeout=120, pass_fds=launch.pass_fds, cwd="/")
    finally:
        launch.close()
    return r.stdout + r.stderr


def test_codex_runs_with_its_sandbox_off_and_the_jail_refuses_a_planted_link(world):
    universe, _other = world
    out = _run_codex(universe, "danger-full-access")
    # The command ran and wrote its own universe (positive control).
    assert "RUNCMD" in out and "WROTE_OWN" in out, out
    assert (universe / "notes" / "made").exists(), out
    # The daemon's per-universe DB at the root is masked (reads empty, no secret).
    assert "OWN-DB-SECRET" not in out, out
    # The planted-link vector is closed: symlink creation is refused.
    assert "LINK_BLOCKED" in out and "LINKED" not in out, out
    assert not (universe / "notes" / "lnk").is_symlink(), out


def test_detection_control_codex_own_sandbox_would_allow_the_link(world):
    """With codex's OWN workspace-write sandbox (a nested bubblewrap), the jail
    must allow userns + symlink, and the link SUCCEEDS -- which is exactly the
    surface this change removes by turning that nested sandbox off."""
    from tinyassets.providers import jail_seccomp

    universe, _other = world
    # The permissive profile a nested codex sandbox needed (symlink + userns
    # allowed), kept here only as the detection control for the deny case above.
    permissive = _compile_without(
        jail_seccomp, drop={88, 266, 36, 272, 56, 97, 220, 435},
    )
    original = jail_seccomp.program_fd
    try:
        jail_seccomp.program_fd = lambda: _fd(permissive)
        out = _run_codex(universe, "workspace-write")
    finally:
        jail_seccomp.program_fd = original
    assert "RUNCMD" in out, out
    assert "LINKED" in out and "LINK_BLOCKED" not in out, out


def _fd(program: bytes) -> int:
    read_end, write_end = os.pipe()
    try:
        os.write(write_end, program)
    finally:
        os.close(write_end)
    return read_end


def _compile_without(jail_seccomp, *, drop: set[int]) -> bytes:
    """A seccomp program like the shipping one but WITHOUT the dropped syscalls
    in the denylist -- the permissive profile a nested codex sandbox needs. Only
    the plain denials are reproduced (enough for the detection control)."""
    import struct

    X86, ARM, X32 = 0xC000003E, 0xC00000B7, 0x40000000
    denied_x86 = [n for n in jail_seccomp.DENIED_X86_64 if n not in drop]
    denied_arm = [n for n in jail_seccomp.DENIED_AARCH64 if n not in drop]
    LD, JEQ, JGE, RET = 0x20, 0x15, 0x35, 0x06
    prog: list[tuple[int, int, int, int]] = []
    # x86 arch check
    arm_at = 4 + len(denied_x86) + 1
    deny_at = arm_at + 2 + len(denied_arm) + 1
    prog += [(LD, 0, 0, 4), (JEQ, 0, arm_at - 2, X86), (LD, 0, 0, 0),
             (JGE, deny_at - 4, 0, X32)]
    for nr in denied_x86:
        prog.append((JEQ, deny_at - (len(prog) + 1), 0, nr))
    prog.append((RET, 0, 0, 0x7FFF0000))
    assert len(prog) == arm_at
    prog.append((JEQ, 0, deny_at - (len(prog) + 1), ARM))
    prog.append((LD, 0, 0, 0))
    for nr in denied_arm:
        prog.append((JEQ, deny_at - (len(prog) + 1), 0, nr))
    prog.append((RET, 0, 0, 0x7FFF0000))
    assert len(prog) == deny_at
    prog.append((RET, 0, 0, 0x00050001))
    return b"".join(struct.pack("=HBBI", *i) for i in prog)
