"""Stage and pack the TinyAssets Server MCPB bundle.

Per `docs/design-notes/2026-04-14-packaging-mirror-decision.md` Option 1:
the bundle stages the live `tinyassets/` package directly. The legacy
`fantasy_author/universe_server.py` shim path is gone — `server.py`
inside the bundle imports `tinyassets.universe_server` like a normal
Python package consumer.

A subprocess import probe runs against the staged bundle before pack
so a missing dependency or a broken import fails the build loudly
instead of producing a silently-broken `.mcpb` artifact.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = REPO_ROOT / "packaging" / "mcpb"
DIST_ROOT = REPO_ROOT / "packaging" / "dist"
STAGE_ROOT = DIST_ROOT / "tinyassets-universe-server-src"
BUNDLE_PATH = DIST_ROOT / "tinyassets-universe-server.mcpb"

TINYASSETS_SRC = REPO_ROOT / "tinyassets"

# Patterns excluded when copying the tinyassets/ tree into the stage.
# Glob shapes match Path.match semantics.
_TREE_EXCLUDES: tuple[str, ...] = (
    "__pycache__",
    "*.db",
    "*.db-journal",
    "*.log",
    "*.pyc",
    ".pytest_cache",
    "*.tmp",
)


def _is_excluded(path: Path, repo_relative_root: Path) -> bool:
    """Return True if ``path`` matches any exclude pattern by name."""
    name = path.name
    for pattern in _TREE_EXCLUDES:
        if path.match(pattern):
            return True
        if name == pattern:
            return True
    return False


def _copy_tree(source: Path, destination: Path) -> int:
    """Copy a directory tree, skipping `_TREE_EXCLUDES` entries.

    Returns the file count actually copied — useful for the build log
    and as a smoke signal that the source wasn't empty.
    """
    if not source.is_dir():
        raise FileNotFoundError(f"Source tree not found: {source}")
    count = 0
    for src in source.rglob("*"):
        if any(_is_excluded(part_path, source) for part_path in src.parents):
            continue
        if _is_excluded(src, source):
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


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Required source file not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _stage_bundle() -> Path:
    if STAGE_ROOT.exists():
        shutil.rmtree(STAGE_ROOT)
    STAGE_ROOT.mkdir(parents=True, exist_ok=True)

    _copy_file(TEMPLATE_ROOT / "manifest.json", STAGE_ROOT / "manifest.json")
    _copy_file(TEMPLATE_ROOT / "pyproject.toml", STAGE_ROOT / "pyproject.toml")
    _copy_file(TEMPLATE_ROOT / "server.py", STAGE_ROOT / "server.py")
    _copy_file(
        REPO_ROOT / "assets" / "icon.png",
        STAGE_ROOT / "assets" / "icon.png",
    )

    # Stage the live `tinyassets/` package — single source of truth per
    # design-note Option 1. Excludes runtime artifacts (.db, __pycache__,
    # logs) that would bloat the bundle without adding value.
    file_count = _copy_tree(TINYASSETS_SRC, STAGE_ROOT / "tinyassets")
    print(f"Staged tinyassets/ package: {file_count} files")

    return STAGE_ROOT


def _probe_import(stage: Path) -> None:
    """Fail loudly if the staged bundle can't import its entry point.

    Runs in a subprocess so the probe's import side-effects don't leak
    into the build process. Sets ``sys.path`` to the stage root so the
    bundled ``tinyassets/`` package resolves before any installed copy.
    ``PYTHONDONTWRITEBYTECODE=1`` keeps the probe from littering the
    fresh stage with ``__pycache__`` files that would then be packed.
    """
    probe_script = (
        f"import sys; sys.path.insert(0, {str(stage)!r}); "
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
            "Staged bundle import probe failed.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    print(f"Import probe: {result.stdout.strip() or 'ok'}")


def _run(command: list[str], *, cwd: Path) -> None:
    executable = (
        shutil.which(command[0])
        or shutil.which(f"{command[0]}.cmd")
        or command[0]
    )
    subprocess.run([executable, *command[1:]], cwd=str(cwd), check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Stage and optionally validate/pack the TinyAssets MCPB bundle. "
            "The staging step always runs; --validate adds the @anthropic-ai/mcpb "
            "manifest validator; --pack produces the .mcpb artifact."
        ),
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate the staged bundle with the official MCPB CLI.",
    )
    parser.add_argument(
        "--pack",
        action="store_true",
        help="Pack the staged bundle into packaging/dist/tinyassets-universe-server.mcpb.",
    )
    parser.add_argument(
        "--skip-probe",
        action="store_true",
        help=(
            "Skip the subprocess import probe. Use only when running in a "
            "minimal CI matrix that lacks the bundle's runtime deps "
            "(fastmcp etc.)."
        ),
    )
    args = parser.parse_args()

    stage_root = _stage_bundle()
    print(f"Staged bundle source at {stage_root}")

    if not args.skip_probe:
        _probe_import(stage_root)

    if args.validate or args.pack:
        _run(
            ["npx", "-y", "@anthropic-ai/mcpb", "validate", str(stage_root)],
            cwd=REPO_ROOT,
        )
        print("MCPB manifest validation passed.")

    if args.pack:
        DIST_ROOT.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "npx",
                "-y",
                "@anthropic-ai/mcpb",
                "pack",
                str(stage_root),
                str(BUNDLE_PATH),
            ],
            cwd=REPO_ROOT,
        )
        print(f"Packed bundle at {BUNDLE_PATH}")


if __name__ == "__main__":
    main()
