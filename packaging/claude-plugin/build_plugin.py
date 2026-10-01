"""Stage the TinyAssets Server claude-plugin runtime tree.

Mirrors the auto-build contract that ``packaging/mcpb/build_bundle.py``
implements for the MCPB surface. Both surfaces auto-derive from the
live ``tinyassets/`` package — no hand-maintained snapshots, no shim,
no drift between commits.

Per design-note ``2026-04-14-packaging-mirror-decision.md`` Option 1.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = (
    REPO_ROOT
    / "packaging"
    / "claude-plugin"
    / "plugins"
    / "tinyassets-universe-server"
)
RUNTIME_ROOT = PLUGIN_ROOT / "runtime"
TINYASSETS_SRC = REPO_ROOT / "tinyassets"

_TREE_EXCLUDES: tuple[str, ...] = (
    "__pycache__",
    "*.db",
    "*.db-journal",
    "*.log",
    "*.pyc",
    ".pytest_cache",
    "*.tmp",
)


def _is_excluded(path: Path) -> bool:
    name = path.name
    for pattern in _TREE_EXCLUDES:
        if path.match(pattern) or name == pattern:
            return True
    return False


def _copy_tree(source: Path, destination: Path) -> int:
    if not source.is_dir():
        raise FileNotFoundError(f"Source tree not found: {source}")
    count = 0
    for src in source.rglob("*"):
        if any(_is_excluded(part_path) for part_path in src.parents):
            continue
        if _is_excluded(src):
            continue
        rel = src.relative_to(source)
        dst = destination / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1
    return count


@contextlib.contextmanager
def _exclusive_build(runtime_root: Path):
    """One build at a time per runtime root, released when the process dies.

    The mirror is TRACKED, so a half-staged tree is a working-tree full of
    deleted files. Two concurrent builds (pytest-xdist runs several build tests
    at once) interleaved one's rmtree with the other's copy and left 247-302
    tracked mirror files deleted (reproduced 2026-10-01). An OS file lock, not a
    marker file, so a killed build never strands the next one.
    """
    # In the temp dir, keyed by the runtime it guards: a lock file inside the
    # tracked runtime would itself show up as an untracked file.
    key = hashlib.sha256(str(runtime_root.resolve()).encode("utf-8")).hexdigest()[:16]
    with open(Path(tempfile.gettempdir()) / f"tinyassets-plugin-build-{key}.lock",
              "a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:  # LK_LOCK gives up after ~10s; keep waiting
                    continue
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _replace_tree(source: Path, destination: Path) -> int:
    """Stage ``source`` beside ``destination``, then swap it in whole.

    Copying into a fresh sibling first means a copy that fails part-way (a full
    disk, a locked file) raises with the old tree still in place, rather than
    after an rmtree has already deleted it.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-",
                                    dir=destination.parent))
    try:
        count = _copy_tree(source, staging)
        if destination.exists():
            retired = Path(tempfile.mkdtemp(prefix=f".{destination.name}.old-",
                                            dir=destination.parent))
            retired.rmdir()
            destination.rename(retired)
            staging.rename(destination)
            shutil.rmtree(retired)
        else:
            staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return count


def _stage_runtime(runtime_root: Path = RUNTIME_ROOT) -> int:
    """Replace the runtime's bundled `tinyassets/` tree with the live one.

    Preserves the runtime scaffolding (server.py, bootstrap.py,
    requirements.txt, pyproject.toml) — those carry venv-bootstrap
    logic the build script does not regenerate. Only the
    ``tinyassets/`` subtree (and the now-retired ``fantasy_author/``
    snapshot, if present) is purged + re-staged.
    """
    with _exclusive_build(runtime_root):
        for retired in ("workflow", "fantasy_author"):
            # Pre-Option-1 snapshots. Remove so the runtime imports the
            # auto-staged ``tinyassets.universe_server`` and never a frozen copy.
            if (runtime_root / retired).exists():
                shutil.rmtree(runtime_root / retired)

        staged = _replace_tree(TINYASSETS_SRC, runtime_root / "tinyassets")

        # The public model lists are DATA the runtime reads, resolved relative to
        # the package (`public_model_lists.lists_directory()` ->
        # parents[2]/"models"), which in this layout is the runtime root. Without
        # them every source kind reads as unlisted and the picker silently loses
        # its shared models -- Codex found the same omission in the Docker image
        # on #4028, where the feature would have shipped dead.
        lists_src = REPO_ROOT / "models"
        if lists_src.is_dir():
            staged += _replace_tree(lists_src, runtime_root / "models")
    return staged


def _probe_import(runtime_root: Path = RUNTIME_ROOT) -> None:
    """Subprocess probe — same shape as build_bundle.py's probe.

    ``PYTHONDONTWRITEBYTECODE=1`` keeps the probe from generating
    ``__pycache__`` directories under the freshly-staged tree.
    """
    probe_script = (
        f"import sys; sys.path.insert(0, {str(runtime_root)!r}); "
        "import tinyassets.universe_server as us; "
        "assert hasattr(us, 'main'), 'tinyassets.universe_server.main missing'; "
        # WorkOS provider is lazy-imported at runtime; probe it explicitly so a
        # missing pyjwt[crypto] dependency fails the build, not a live request.
        "import tinyassets.auth.workos_provider; "
        "print('probe-ok')"
    )
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, "-c", probe_script],
        capture_output=True, text=True, check=False, env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Plugin runtime import probe failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    print(f"Import probe: {result.stdout.strip() or 'ok'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Stage the TinyAssets claude-plugin runtime by re-staging the "
            "live tinyassets/ package into "
            "packaging/claude-plugin/.../runtime/tinyassets/."
        ),
    )
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help=(
            "Skip the subprocess import probe. Use only when running in a "
            "minimal CI matrix that lacks the runtime's deps."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=RUNTIME_ROOT,
        help=(
            "Stage into this runtime directory instead of the tracked plugin "
            "mirror. Tests use it so the suite never rewrites the working tree."
        ),
    )
    args = parser.parse_args()
    runtime_root = args.runtime_root.resolve()

    file_count = _stage_runtime(runtime_root)
    print(
        f"Staged claude-plugin runtime tinyassets/ at {runtime_root / 'tinyassets'} "
        f"({file_count} files)"
    )

    if not args.skip_probe:
        _probe_import(runtime_root)


if __name__ == "__main__":
    main()
