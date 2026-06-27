"""Packaging Option 1 — build script smoke + import-probe coverage.

Covers task #26 / planner's design-note
``2026-04-14-packaging-mirror-decision.md`` Option 1.

The load-bearing checks:
1. ``build_bundle.py`` stages the live ``tinyassets/`` package into the
   bundle source dir (no shim, no fantasy_author/).
2. The staged bundle's ``server.py`` imports
   ``tinyassets.universe_server`` cleanly (subprocess probe).
3. The mirror script ``build_plugin.py`` does the same for the
   claude-plugin runtime tree.
4. Excluded patterns (``__pycache__``, ``*.db``, ``*.log``) don't end
   up in the staged tree.

These are smoke tests — actual ``--validate`` / ``--pack`` requires
``npx @anthropic-ai/mcpb`` which CI installs separately.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MCPB_BUILD = REPO_ROOT / "packaging" / "mcpb" / "build_bundle.py"
PLUGIN_BUILD = REPO_ROOT / "packaging" / "claude-plugin" / "build_plugin.py"
DIST_STAGE = (
    REPO_ROOT / "packaging" / "dist" / "tinyassets-universe-server-src"
)
PLUGIN_RUNTIME = (
    REPO_ROOT
    / "packaging"
    / "claude-plugin"
    / "plugins"
    / "tinyassets-universe-server"
    / "runtime"
)


def _run(script: Path, args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(script), *(args or [])]
    return subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
    )


# ─── build_bundle.py ─────────────────────────────────────────────────


def test_build_bundle_stages_tinyassets_package(tmp_path):
    """Stage step copies tinyassets/ into the bundle and probe passes."""
    result = _run(MCPB_BUILD)
    assert result.returncode == 0, (
        f"build_bundle.py failed:\nstdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )
    assert (DIST_STAGE / "tinyassets" / "universe_server.py").is_file(), (
        "Staged bundle must contain tinyassets/universe_server.py"
    )
    assert (DIST_STAGE / "server.py").is_file()
    assert (DIST_STAGE / "manifest.json").is_file()
    assert (DIST_STAGE / "pyproject.toml").is_file()
    # The shim path must NOT be staged anymore.
    assert not (DIST_STAGE / "fantasy_author").exists(), (
        "fantasy_author/ shim path must not be in the staged bundle"
    )
    assert "probe-ok" in result.stdout


def test_build_bundle_excludes_pycache_and_dbs(tmp_path):
    """Excludes prevent runtime artifacts from polluting the bundle."""
    _run(MCPB_BUILD)
    # No pycache directories anywhere under staged tinyassets/.
    pycache_hits = list(DIST_STAGE.rglob("__pycache__"))
    assert not pycache_hits, f"__pycache__ found in staged bundle: {pycache_hits}"
    db_hits = list(DIST_STAGE.rglob("*.db"))
    assert not db_hits, f"*.db files leaked into staged bundle: {db_hits}"


def test_bundle_server_imports_tinyassets_package():
    """Direct import probe — same shape build_bundle's --skip-probe bypasses."""
    _run(MCPB_BUILD)
    probe = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, {str(DIST_STAGE)!r}); "
            "import tinyassets.universe_server as us; "
            "assert callable(us.main); print('ok')",
        ],
        capture_output=True, text=True, check=False,
    )
    assert probe.returncode == 0, (
        f"Bundle import probe failed:\nstdout={probe.stdout}\n"
        f"stderr={probe.stderr}"
    )
    assert "ok" in probe.stdout


# ─── build_plugin.py ─────────────────────────────────────────────────


def test_build_plugin_stages_tinyassets_package():
    """Plugin build re-stages tinyassets/ next to runtime/server.py."""
    result = _run(PLUGIN_BUILD)
    assert result.returncode == 0, (
        f"build_plugin.py failed:\nstdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )
    assert (PLUGIN_RUNTIME / "tinyassets" / "universe_server.py").is_file()
    assert (PLUGIN_RUNTIME / "server.py").is_file()
    assert "probe-ok" in result.stdout


def test_build_plugin_purges_legacy_fantasy_author_snapshot():
    """The pre-shim fantasy_author/ snapshot must be removed."""
    # Pre-create a stale fantasy_author dir with a stub file to mimic
    # the pre-Option-1 layout. The build should purge it.
    legacy_dir = PLUGIN_RUNTIME / "fantasy_author"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "universe_server.py").write_text("# stale\n")
    try:
        result = _run(PLUGIN_BUILD)
        assert result.returncode == 0
        assert not legacy_dir.exists(), (
            "Stale fantasy_author/ snapshot must be purged on build"
        )
    finally:
        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)


def test_plugin_server_imports_workflow_package():
    _run(PLUGIN_BUILD)
    probe = subprocess.run(
        [
            sys.executable, "-c",
            f"import sys; sys.path.insert(0, {str(PLUGIN_RUNTIME)!r}); "
            "import tinyassets.universe_server as us; "
            "assert callable(us.main); print('ok')",
        ],
        capture_output=True, text=True, check=False,
    )
    assert probe.returncode == 0, (
        f"Plugin import probe failed:\nstdout={probe.stdout}\n"
        f"stderr={probe.stderr}"
    )


# ─── shape parity ────────────────────────────────────────────────────


def test_bundle_and_plugin_workflow_trees_match():
    """Both build scripts stage the same set of files from tinyassets/."""
    _run(MCPB_BUILD)
    _run(PLUGIN_BUILD)
    bundle_files = {
        p.relative_to(DIST_STAGE / "workflow")
        for p in (DIST_STAGE / "workflow").rglob("*")
        if p.is_file()
    }
    plugin_files = {
        p.relative_to(PLUGIN_RUNTIME / "workflow")
        for p in (PLUGIN_RUNTIME / "workflow").rglob("*")
        if p.is_file()
    }
    diff = bundle_files.symmetric_difference(plugin_files)
    assert not diff, (
        f"Bundle and plugin tinyassets/ trees diverged: {sorted(diff)}"
    )
