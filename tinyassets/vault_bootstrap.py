"""Container custody boundary: preload root-only KEKs, then drop privileges."""

from __future__ import annotations

import os
import pwd
import runpy
import sys
from pathlib import Path


def _drop_privileges(user: str = "tinyassets") -> None:
    if os.geteuid() != 0:
        raise RuntimeError("vault bootstrap must start as root")
    account = pwd.getpwnam(user)
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    if os.geteuid() != account.pw_uid or os.getegid() != account.pw_gid:
        raise RuntimeError("vault bootstrap failed to drop privileges")


def _run_python(argv: list[str]) -> None:
    if len(argv) >= 3 and argv[1] == "-m":
        module = argv[2]
        sys.argv = [module, *argv[3:]]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return
    if len(argv) >= 2 and Path(argv[1]).suffix == ".py":
        script = argv[1]
        sys.argv = [script, *argv[2:]]
        runpy.run_path(script, run_name="__main__")
        return
    raise RuntimeError("vault-enabled container commands must be Python modules/scripts")


def main(argv: list[str] | None = None) -> None:
    command = list(sys.argv[1:] if argv is None else argv)
    if not command:
        raise RuntimeError("container command is required")
    from tinyassets.credential_broker import preload_platform_keys

    if os.environ.get("TINYASSETS_VAULT_KEK_DIR", "").strip():
        preload_platform_keys()
    _drop_privileges()
    executable = Path(command[0]).name
    if executable.startswith("python"):
        _run_python(command)
        return
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
