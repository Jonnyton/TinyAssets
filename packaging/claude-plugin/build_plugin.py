"""Stage the TinyAssets Server claude-plugin runtime tree.

Mirrors the auto-build contract that ``packaging/mcpb/build_bundle.py``
implements for the MCPB surface. Both surfaces auto-derive from the
live ``tinyassets/`` package — no hand-maintained snapshots, no shim,
no drift between commits.

Per design-note ``2026-04-14-packaging-mirror-decision.md`` Option 1.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
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


def _stage_runtime() -> int:
    """Replace the runtime's bundled `tinyassets/` tree with the live one.

    Preserves the runtime scaffolding (server.py, bootstrap.py,
    requirements.txt, pyproject.toml) — those carry venv-bootstrap
    logic the build script does not regenerate. Only the
    ``tinyassets/`` subtree (and the now-retired ``fantasy_author/``
    snapshot, if present) is purged + re-staged.
    """
    tinyassets_dir = RUNTIME_ROOT / "tinyassets"
    old_workflow_dir = RUNTIME_ROOT / "workflow"
    legacy_fantasy = RUNTIME_ROOT / "fantasy_author"

    if tinyassets_dir.exists():
        shutil.rmtree(tinyassets_dir)
    if old_workflow_dir.exists():
        shutil.rmtree(old_workflow_dir)
    if legacy_fantasy.exists():
        # Pre-Option-1 snapshot. Remove so the runtime imports the
        # auto-staged ``tinyassets.universe_server`` and never the
        # frozen ``fantasy_author/universe_server.py``.
        shutil.rmtree(legacy_fantasy)

    tinyassets_dir.mkdir(parents=True, exist_ok=True)
    return _copy_tree(TINYASSETS_SRC, tinyassets_dir)


def _probe_import() -> None:
    """Subprocess probe — same shape as build_bundle.py's probe.

    ``PYTHONDONTWRITEBYTECODE=1`` keeps the probe from generating
    ``__pycache__`` directories under the freshly-staged tree.
    """
    probe_script = (
        f"import sys; sys.path.insert(0, {str(RUNTIME_ROOT)!r}); "
        "import tinyassets.universe_server as us; "
        "assert hasattr(us, 'main'), 'tinyassets.universe_server.main missing'; "
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
    args = parser.parse_args()

    file_count = _stage_runtime()
    print(
        f"Staged claude-plugin runtime tinyassets/ at {RUNTIME_ROOT / 'tinyassets'} "
        f"({file_count} files)"
    )

    if not args.skip_probe:
        _probe_import()


if __name__ == "__main__":
    main()
