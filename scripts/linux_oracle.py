#!/usr/bin/env python3
"""Run the suite on Linux, from the dev box, before pushing.

WHY THIS EXISTS. ``AGENTS.md`` says a local Windows run is not an oracle on its
own. That was a warning; on the workspace change it became six CI rounds. Every
one of those failures had the same shape: the behaviour changed, the Windows
suite went green, and a test that encodes the OLD contract survived because its
assertion only executes on POSIX -- where the old behaviour was still correct.
Two of them were not even reachable on this host at any price: the sandbox jail
needs bubblewrap, which Windows does not have and WSL here does not ship.

So the oracle is a container: the same Python CI uses, with bubblewrap and real
POSIX descriptor semantics, running the WORKING TREE (uncommitted changes
included -- a local oracle that only sees committed code is a slower CI, not an
oracle).

    python scripts/linux_oracle.py -- tests/test_workspace_end_to_end.py -q
    python scripts/linux_oracle.py --shell          # poke around inside
    python scripts/linux_oracle.py --build          # force an image rebuild

WHAT IT IS NOT. It is not a replacement for CI: it runs one Python version on
one architecture, and the container's kernel is the host's. CI stays
authoritative. This exists so a Linux-only mistake is found in a minute here
instead of ten minutes there -- and so the two bubblewrap proofs have somewhere
to run at all.

SECCOMP. The run relaxes seccomp (``--security-opt seccomp=unconfined``)
because Docker's default profile blocks the unprivileged ``clone`` flags
bubblewrap needs, so every jail test would skip and the oracle would quietly
cover less than it claims. It is a throwaway local container with no
credentials and no network access to anything of ours. ``--no-bwrap`` runs
without the relaxation, which is also how you verify the jail tests SKIP rather
than silently pass when bubblewrap is unavailable.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

IMAGE_REPO = "tinyassets-linux-oracle"
DOCKERFILE = Path("docker/linux-oracle.Dockerfile")
#: Copied into the container, minus what is huge, host-specific, or rebuilt
#: there. ``.git`` is excluded deliberately: in a linked worktree it is a FILE
#: pointing at a path that does not exist in the container, so the copy gets a
#: fresh repository instead (see ``_RUN_SCRIPT``).
COPY_EXCLUDES = (
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "output",
    ".codex-worktrees",
    ".codex-scratch-uptime-canary-1461",
)

#: Runs inside the container. Copies the mounted tree onto the container's own
#: filesystem (a bind mount from Windows is slow and carries host permissions),
#: gives it a real git repository so git-dependent tests have one, then hands
#: over to the command.
_RUN_SCRIPT = r"""
set -e
mkdir -p /work
tar -C /src -cf - {excludes} . | tar -C /work -xf -
cd /work
# A real repository, not the host's: the worktree's .git is a file pointing at
# a path this container does not have. History is irrelevant to the suite; a
# valid HEAD is not.
git init -q .
git config user.email oracle@localhost
git config user.name "linux oracle"
git add -A >/dev/null 2>&1 || true
git commit -q -m "linux oracle snapshot" >/dev/null 2>&1 || true
_py=$(python -V 2>&1 | cut -d' ' -f2)
_git=$(git --version | cut -d' ' -f3)
_bwrap=$(bwrap --version 2>/dev/null | cut -d' ' -f2 || echo absent)
echo "[oracle] python $_py | git $_git | bwrap $_bwrap"
exec {command}
"""


def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


def _image_tag(root: Path) -> str:
    """Tag the image with what determines its contents, so a dependency change
    rebuilds it and an unrelated edit never does."""
    digest = hashlib.sha256()
    for relative in (DOCKERFILE, Path("pyproject.toml")):
        digest.update((root / relative).read_bytes())
    return f"{IMAGE_REPO}:{digest.hexdigest()[:12]}"


def _image_exists(tag: str) -> bool:
    return subprocess.run(
        ["docker", "image", "inspect", tag],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def _build(root: Path, tag: str) -> None:
    print(f"[oracle] building {tag} (first run pulls and compiles dependencies)")
    result = subprocess.run(
        ["docker", "build", "-f", str(root / DOCKERFILE), "-t", tag, str(root)],
    )
    if result.returncode != 0:
        raise SystemExit(f"[oracle] image build failed ({result.returncode})")


def _docker_path(path: Path) -> str:
    """A host path Docker Desktop accepts as a bind source."""
    text = str(path.resolve())
    if len(text) > 2 and text[1] == ":":  # C:\... -> /c/...
        return "/" + text[0].lower() + text[2:].replace("\\", "/")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the suite on Linux, in a container, against the working tree.",
    )
    parser.add_argument("--build", action="store_true", help="rebuild the image first")
    parser.add_argument("--shell", action="store_true", help="interactive shell instead of pytest")
    parser.add_argument(
        "--no-bwrap", action="store_true",
        help="keep Docker's default seccomp, so bubblewrap cannot unshare "
             "(use to prove the jail tests SKIP rather than silently pass)",
    )
    parser.add_argument(
        "pytest_args", nargs="*",
        help="passed to pytest (put them after --); default: the whole suite, quiet",
    )
    args = parser.parse_args(argv)

    if shutil.which("docker") is None:
        raise SystemExit("[oracle] docker is not on PATH")
    probe = subprocess.run(
        ["docker", "info", "--format", "{{.OSType}}"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0 or "linux" not in probe.stdout:
        raise SystemExit(
            "[oracle] no Linux Docker engine. Start Docker Desktop and retry; "
            f"docker info said: {(probe.stderr or probe.stdout).strip()[:200]}"
        )

    root = _repo_root()
    tag = _image_tag(root)
    if args.build or not _image_exists(tag):
        _build(root, tag)

    if args.shell:
        command = "bash"
    else:
        pytest_args = args.pytest_args or ["-q", "tests"]
        command = "python -m pytest -p no:cacheprovider " + " ".join(
            f"'{a}'" for a in pytest_args
        )
    script = _RUN_SCRIPT.format(
        excludes=" ".join(f"--exclude=./{name}" for name in COPY_EXCLUDES),
        command=command,
    )

    run = ["docker", "run", "--rm", "-v", f"{_docker_path(root)}:/src:ro"]
    if not args.no_bwrap:
        # Docker's default seccomp profile blocks the clone flags bubblewrap
        # needs; without this every jail test skips and the oracle covers less
        # than it says it does.
        run += ["--security-opt", "seccomp=unconfined"]
    if args.shell:
        run.append("-it")
    run += [tag, "bash", "-lc", script]

    return subprocess.run(run).returncode


if __name__ == "__main__":
    sys.exit(main())
