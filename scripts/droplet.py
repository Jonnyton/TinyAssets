#!/usr/bin/env python3
"""Thin, read-only helper for reaching the live TinyAssets daemon droplet.

Standardizes the SSH incantation that otherwise trips up sessions. The deploy
key is **non-default-named** (`~/.ssh/tinyassets_deploy_ed25519`) and there is no
`~/.ssh/config` host entry by default, so a bare `ssh root@<ip>` does NOT offer
it and dies with "Permission denied (publickey)" — which a session can mistake
for "no access" (this happened 2026-06-25 during the auto-ship enforce flip).
This wrapper always passes `-i <key> -o IdentitiesOnly=yes`, so it Just Works,
and it fixes the key's perms if a fresh checkout left it world-readable.

**Read-only / diagnostic by design.** It deliberately does NOT recreate
containers or mutate the daemon — applying a config/env change (which briefly
blips the public MCP surface) stays a deliberate, documented step:
`deploy/DEPLOY.md` §"Operator access to the live droplet + config/env changes".

Usage:
  python scripts/droplet.py status        # container names + daemon health
  python scripts/droplet.py env           # auto-ship + writer/provider env in the daemon
  python scripts/droplet.py canary        # loopback MCP canary from inside the daemon
  python scripts/droplet.py ssh           # open an interactive shell
  python scripts/droplet.py ssh -- <cmd>  # run a one-off remote command

Override defaults via env: TINYASSETS_DROPLET_HOST, TINYASSETS_DROPLET_USER,
TINYASSETS_DROPLET_KEY.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

HOST = os.environ.get("TINYASSETS_DROPLET_HOST", "161.35.237.133")
USER = os.environ.get("TINYASSETS_DROPLET_USER", "root")
KEY = os.environ.get(
    "TINYASSETS_DROPLET_KEY", str(Path.home() / ".ssh" / "tinyassets_deploy_ed25519")
)


def _ensure_key() -> str | None:
    """Return the key path, fixing world-readable perms; None with a hint if absent."""
    kp = Path(KEY)
    if not kp.is_file():
        print(
            f"droplet: SSH key not found at {kp}.\n"
            "  The droplet deploy key is non-default-named; a bare `ssh root@<ip>`\n"
            "  will fail with 'Permission denied (publickey)' — that is NOT no access.\n"
            "  See deploy/DEPLOY.md §'Operator access to the live droplet'.",
            file=sys.stderr,
        )
        return None
    try:  # ssh refuses a world/group-readable private key on POSIX
        mode = kp.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            kp.chmod(0o600)
    except OSError:
        pass  # best-effort; Windows ACLs differ and ssh tolerates them
    return str(kp)


def _ssh_base(interactive: bool) -> list[str] | None:
    key = _ensure_key()
    if key is None:
        return None
    base = [
        "ssh", "-i", key,
        "-o", "IdentitiesOnly=yes",
        "-o", "ConnectTimeout=12",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    if not interactive:
        base += ["-o", "BatchMode=yes"]
    base.append(f"{USER}@{HOST}")
    return base


def _run(remote_cmd: str | None, *, interactive: bool) -> int:
    base = _ssh_base(interactive)
    if base is None:
        return 3
    if remote_cmd:
        base.append(remote_cmd)
    return subprocess.call(base)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="docker ps + daemon health")
    sub.add_parser("env", help="auto-ship + writer/provider env in the running daemon")
    sub.add_parser("canary", help="loopback MCP canary from inside the daemon container")
    p_ssh = sub.add_parser("ssh", help="open a shell, or run a one-off command after --")
    p_ssh.add_argument("remote", nargs=argparse.REMAINDER, help="optional: -- <command>")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        return _run(
            'docker ps --format "{{.Names}}: {{.Status}}"; echo "--- daemon health ---"; '
            'docker inspect tinyassets-daemon --format '
            '"{{.State.Health.Status}} (started {{.State.StartedAt}})"',
            interactive=False,
        )
    if args.cmd == "env":
        return _run(
            'docker exec tinyassets-daemon printenv '
            '| grep -iE "AUTO_SHIP|OLLAMA|PIN_WRITER|GOAL_POOL" | sort '
            '|| echo "(no matching env — gates run on code defaults)"',
            interactive=False,
        )
    if args.cmd == "canary":
        return _run(
            'docker exec tinyassets-daemon python /app/scripts/mcp_public_canary.py '
            '--url http://127.0.0.1:8001/mcp --timeout 10 '
            '&& echo "loopback canary GREEN"',
            interactive=False,
        )
    if args.cmd == "ssh":
        remote = list(args.remote or [])
        if remote and remote[0] == "--":
            remote = remote[1:]
        if remote:
            return _run(" ".join(remote), interactive=False)
        return _run(None, interactive=True)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
