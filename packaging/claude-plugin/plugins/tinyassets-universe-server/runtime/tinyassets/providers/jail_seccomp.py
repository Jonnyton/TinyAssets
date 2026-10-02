"""The one seccomp filter every universe jail loads (tool jail and provider jail).

bubblewrap installs it with ``--seccomp FD`` just before it execs the jailed
command, AFTER it has built its own namespaces, so the filter binds only the
confined process and everything it starts, never bubblewrap itself.

What it refuses, and why
------------------------
* ``symlink``/``mknod`` (and their ``*at`` forms): both jails write into a
  universe the daemon later reads from OUTSIDE the jail. A planted link
  (``founder.md -> /data/<other>/founder.md``) dangles inside the jail and
  resolves on the host, pulling another user's file into this universe's
  prompt; a FIFO hangs the daemon's reading thread. Hard links cannot leave the
  universe mount (EXDEV).
* ``io_uring_setup``/``enter``/``register``: io_uring runs syscalls from a
  submission queue seccomp never sees (``IORING_OP_SYMLINKAT``, 5.15+), and
  production's 6.1 kernel has no ``io_uring_disabled`` sysctl (6.6+). With no
  ring, no ring op can run.
* new user namespaces (``unshare``/``clone`` with ``CLONE_NEWUSER``, and
  ``clone3``), ``setns``, ``bpf``, ``userfaultfd``, ``perf_event_open``,
  ``ptrace`` and the kernel keyring (``keyctl``, ``add_key``,
  ``request_key``): every universe shares one kernel, so after mount isolation
  a kernel privilege escalation is the main way left from one user's jail to
  another's. These are the interfaces such exploits keep using (OpenShell's
  denylist, 2026-10-01 comparison). A user namespace in particular hands the
  process a fresh set of capabilities over namespaces it can then create.
  ``clone3`` passes its flags in memory a filter cannot read, so it answers
  ``ENOSYS``: glibc then falls back to ``clone``, whose flags ARE checked.

One filter, both jails. No jailed process builds a NESTED sandbox of its own:
the universe tool jail runs no CLI, claude has none, and the codex adapter runs
its commands directly in this jail (``--dangerously-bypass-approvals-and-sandbox``
when ``provider_jail.launch_is_confined``) and disables the shell tool entirely
on served turns. So nothing needs the new user namespace or ``/dev`` symlinks a
nested bubblewrap would (measured 2026-10-01: a codex command runs under this
deny filter, and ``ln`` inside it fails with ``EPERM``). Earlier the provider
jail kept both open for codex's own ``--sandbox workspace-write``; that is gone.

Unknown architectures and the x32 ABI get ``EPERM`` for every call, so a filter
this module cannot vouch for never runs as ALLOW.
"""

from __future__ import annotations

import os
import struct

__all__ = ["deny_program", "program_fd"]

_AUDIT_ARCH_X86_64 = 0xC000003E
_AUDIT_ARCH_AARCH64 = 0xC00000B7
_X32_SYSCALL_BIT = 0x40000000
_CLONE_NEWUSER = 0x10000000

_RET_ALLOW = 0x7FFF0000
_RET_EPERM = 0x00050000 | 1
_RET_ENOSYS = 0x00050000 | 38

# cBPF opcodes.
_LD_W_ABS = 0x20
_JEQ_K = 0x15
_JGE_K = 0x35
_JSET_K = 0x45
_RET_K = 0x06

# seccomp_data offsets: nr, arch, then args[] from 16 (low word first on both
# little-endian architectures below).
_NR, _ARCH, _ARG0 = 0, 4, 16

#: Refused outright (EPERM). Links included: both jails write into a universe
#: the daemon later reads from OUTSIDE, so a planted link must never exist.
DENIED_X86_64: tuple[int, ...] = (
    88, 266, 133, 259,      # symlink, symlinkat, mknod, mknodat
    425, 426, 427,          # io_uring_setup, io_uring_enter, io_uring_register
    101, 321, 323, 298,     # ptrace, bpf, userfaultfd, perf_event_open
    250, 248, 249, 308,     # keyctl, add_key, request_key, setns
)
DENIED_AARCH64: tuple[int, ...] = (
    36, 33,                 # symlinkat, mknodat (no plain forms on asm-generic)
    425, 426, 427,
    117, 280, 282, 241,
    219, 217, 218, 268,
)
#: Refused only with CLONE_NEWUSER in the first argument: unshare, clone.
NEWUSER_X86_64: tuple[int, ...] = (272, 56)
NEWUSER_AARCH64: tuple[int, ...] = (97, 220)
#: clone3 on both: ENOSYS, so libc falls back to the checked clone.
ENOSYS_ALL: tuple[int, ...] = (435,)


def _arch_block(prog, denied, newuser, allow, deny, enosys):
    """One architecture's checks; ``allow`` names the RET ALLOW it ends with."""
    for nr in denied:
        prog.append((_JEQ_K, deny, 0, nr))
    for nr in ENOSYS_ALL:
        prog.append((_JEQ_K, enosys, 0, nr))
    for nr in newuser:
        # Not this call: skip its two-instruction argument check.
        prog.append((_JEQ_K, 0, 2, nr))
        prog.append((_LD_W_ABS, 0, 0, _ARG0))
        prog.append((_JSET_K, deny, allow, _CLONE_NEWUSER))
    prog.append((_RET_K, 0, 0, _RET_ALLOW))  # the ``allow`` label


def deny_program() -> bytes:
    """The compiled cBPF program bubblewrap loads with ``--seccomp``."""
    # Jump targets are symbolic here and resolved to forward offsets below.
    prog: list[tuple[int, object, object, int]] = [
        (_LD_W_ABS, 0, 0, _ARCH),
        (_JEQ_K, 0, "arm", _AUDIT_ARCH_X86_64),
        (_LD_W_ABS, 0, 0, _NR),
        (_JGE_K, "deny", 0, _X32_SYSCALL_BIT),
    ]
    _arch_block(prog, DENIED_X86_64, NEWUSER_X86_64, "allow_x86", "deny", "enosys")
    labels = {"allow_x86": len(prog) - 1, "arm": len(prog)}
    prog.append((_JEQ_K, 0, "deny", _AUDIT_ARCH_AARCH64))
    prog.append((_LD_W_ABS, 0, 0, _NR))
    _arch_block(prog, DENIED_AARCH64, NEWUSER_AARCH64, "allow_arm", "deny", "enosys")
    labels["allow_arm"] = len(prog) - 1
    labels["deny"] = len(prog)
    prog.append((_RET_K, 0, 0, _RET_EPERM))
    labels["enosys"] = len(prog)
    prog.append((_RET_K, 0, 0, _RET_ENOSYS))

    def offset(pc: int, target: object) -> int:
        if isinstance(target, int):
            return target
        jump = labels[target] - (pc + 1)
        assert 0 <= jump <= 255, (target, jump)
        return jump

    return b"".join(
        struct.pack("=HBBI", code, offset(pc, jt), offset(pc, jf), k)
        for pc, (code, jt, jf, k) in enumerate(prog)
    )


def program_fd() -> int:
    """A readable descriptor holding :func:`deny_program`, for the child.

    bubblewrap reads it to EOF and closes it; the caller closes its own copy
    once the child is spawned.
    """
    read_end, write_end = os.pipe()
    try:
        os.write(write_end, deny_program())
    finally:
        os.close(write_end)
    return read_end
