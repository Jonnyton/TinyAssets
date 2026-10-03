"""What the shared jail seccomp filter decides, per architecture and per call.

The program is run through a small cBPF interpreter here, so each assertion is
about the DECISION a syscall gets, not about instruction layout: a rule moved,
merged or dropped is caught by what it stops refusing. The real-kernel proof is
in ``tests/test_provider_jail_network.py`` (provider jail) and
``tests/test_universe_tools_jail.py`` (tool jail).
"""

from __future__ import annotations

import struct

import pytest

from tinyassets.providers import jail_seccomp
from tinyassets.providers.jail_seccomp import deny_program

X86_64, AARCH64, I386 = 0xC000003E, 0xC00000B7, 0x40000003
ALLOW, EPERM, ENOSYS = 0x7FFF0000, 0x00050001, 0x00050026
NEWUSER = 0x10000000


def decide(program: bytes, arch: int, nr: int, arg0: int = 0) -> int:
    """Run ``program`` on one seccomp_data and return the action it picks."""
    data = struct.pack("=iIQ6Q", nr, arch, 0, arg0, 0, 0, 0, 0, 0)
    insns = [struct.unpack("=HBBI", program[i:i + 8]) for i in range(0, len(program), 8)]
    pc, acc = 0, 0
    while True:
        code, jt, jf, k = insns[pc]
        if code == 0x20:
            acc = struct.unpack_from("=I", data, k)[0]
        elif code == 0x06:
            return k
        elif code in (0x15, 0x35, 0x45):
            hit = {0x15: acc == k, 0x35: acc >= k, 0x45: bool(acc & k)}[code]
            pc += jt if hit else jf
        else:
            raise AssertionError(f"unexpected opcode {code:#x}")
        pc += 1


#: Every launch but a served codex turn: the tool jail, claude, non-served codex.
DENY = deny_program()
#: A served codex turn, whose apply_patch helper builds a nested sandbox.
SERVED = deny_program(nested_sandbox=True)

# (name, x86_64 nr, aarch64 nr)
KERNEL_SURFACE = [
    ("mknodat", 259, 33), ("io_uring_setup", 425, 425), ("io_uring_enter", 426, 426),
    ("io_uring_register", 427, 427), ("ptrace", 101, 117), ("bpf", 321, 280),
    ("userfaultfd", 323, 282), ("perf_event_open", 298, 241), ("keyctl", 250, 219),
    ("add_key", 248, 217), ("request_key", 249, 218), ("setns", 308, 268),
]
ORDINARY = [("read", 0, 63), ("openat", 257, 56), ("socket", 41, 198), ("execve", 59, 221),
            ("mount", 165, 40), ("seccomp", 317, 277)]


@pytest.mark.parametrize("program", [DENY, SERVED], ids=["deny", "served"])
@pytest.mark.parametrize("name,x86,arm", KERNEL_SURFACE)
def test_both_jails_refuse_the_kernel_surface_on_both_arches(program, name, x86, arm):
    assert decide(program, X86_64, x86) == EPERM, name
    assert decide(program, AARCH64, arm) == EPERM, name


@pytest.mark.parametrize("program", [DENY, SERVED], ids=["deny", "served"])
@pytest.mark.parametrize("name,x86,arm", ORDINARY)
def test_ordinary_calls_are_allowed(program, name, x86, arm):
    assert decide(program, X86_64, x86) == ALLOW, name
    assert decide(program, AARCH64, arm) == ALLOW, name


def test_x86_mknod_is_refused_in_both():
    for program in (DENY, SERVED):
        assert decide(program, X86_64, 133) == EPERM


def test_the_deny_profile_refuses_links_and_new_user_namespaces():
    """The tool jail, claude and a non-served codex call (its sandbox off)."""
    for nr in (88, 266):  # symlink, symlinkat
        assert decide(DENY, X86_64, nr) == EPERM
    assert decide(DENY, AARCH64, 36) == EPERM
    for arch, unshare, clone in ((X86_64, 272, 56), (AARCH64, 97, 220)):
        assert decide(DENY, arch, unshare, NEWUSER) == EPERM
        assert decide(DENY, arch, clone, NEWUSER | 0x11) == EPERM
        # Threads and forks (no CLONE_NEWUSER) still work.
        assert decide(DENY, arch, clone, 0x003D0F00) == ALLOW
        assert decide(DENY, arch, unshare, 0x00000200) == ALLOW  # CLONE_FS
        # clone3 hides its flags, so libc is sent back to the checked clone.
        assert decide(DENY, arch, 435) == ENOSYS


def test_the_served_profile_keeps_what_codexs_nested_sandbox_needs():
    """A served codex turn's apply_patch helper needs a user namespace and /dev
    symlinks, so this profile keeps both; every other launch denies them."""
    assert decide(SERVED, X86_64, 88) == ALLOW
    assert decide(SERVED, AARCH64, 36) == ALLOW
    for arch, unshare, clone in ((X86_64, 272, 56), (AARCH64, 97, 220)):
        assert decide(SERVED, arch, unshare, NEWUSER) == ALLOW
        assert decide(SERVED, arch, clone, NEWUSER) == ALLOW
        assert decide(SERVED, arch, 435) == ALLOW


@pytest.mark.parametrize("program", [DENY, SERVED], ids=["deny", "served"])
def test_unknown_arches_and_x32_are_refused_outright(program):
    assert decide(program, I386, 3) == EPERM
    assert decide(program, X86_64, 0x40000000 | 0) == EPERM


def test_every_jump_lands_inside_the_program():
    for program in (DENY, SERVED):
        insns = [struct.unpack("=HBBI", program[i:i + 8]) for i in range(0, len(program), 8)]
        for pc, (code, jt, jf, _k) in enumerate(insns):
            if code in (0x15, 0x35, 0x45):
                assert pc + 1 + max(jt, jf) < len(insns)
        assert insns[-1][0] == 0x06


def test_program_fd_holds_exactly_the_program():
    import os

    fd = jail_seccomp.program_fd(nested_sandbox=True)
    try:
        assert os.read(fd, 1 << 16) == SERVED
    finally:
        os.close(fd)
