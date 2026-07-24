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

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MCPB_BUILD = REPO_ROOT / "packaging" / "mcpb" / "build_bundle.py"
MCPB_MANIFEST = REPO_ROOT / "packaging" / "mcpb" / "manifest.json"
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
CANONICAL_MCPB_TOOLS = {
    "converse",
    "get_status",
    "read_graph",
    "read_page",
    "run_graph",
    "write_graph",
    "write_page",
}


def _run(script: Path, args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(script), *(args or [])]
    return subprocess.run(
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
    )


def _load_mcpb_build_module():
    spec = importlib.util.spec_from_file_location(
        "tinyassets_mcpb_build_bundle_test",
        MCPB_BUILD,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_mcpb_manifest_declares_canonical_catalog():
    manifest = json.loads(MCPB_MANIFEST.read_text(encoding="utf-8"))

    assert {tool["name"] for tool in manifest["tools"]} == CANONICAL_MCPB_TOOLS


def test_build_bundle_probes_staged_catalog():
    result = _run(MCPB_BUILD)

    assert result.returncode == 0, (
        f"build_bundle.py failed:\nstdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )
    assert (
        "Catalog parity: "
        + ", ".join(sorted(CANONICAL_MCPB_TOOLS))
    ) in result.stdout


def test_build_bundle_rejects_manifest_runtime_catalog_drift(
    tmp_path,
    monkeypatch,
):
    build = _load_mcpb_build_module()
    monkeypatch.setattr(build, "STAGE_ROOT", tmp_path / "stage")
    stage_bundle = build._stage_bundle

    def _stage_with_drift():
        stage = stage_bundle()
        manifest_path = stage / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["tools"] = [
            {
                "name": "manifest_only",
                "description": "Synthetic parity regression fixture.",
            },
        ]
        manifest_path.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return stage

    monkeypatch.setattr(build, "_stage_bundle", _stage_with_drift)
    monkeypatch.setattr(build, "_probe_import", lambda _stage: None)
    monkeypatch.setattr(sys, "argv", ["build_bundle.py"])

    with pytest.raises(RuntimeError) as exc_info:
        build.main()

    message = str(exc_info.value)
    assert "missing_from_manifest" in message
    assert "extra_in_manifest" in message
    assert "read_graph" in message
    assert "manifest_only" in message


def test_build_bundle_rejects_staged_catalog_import_failure(
    tmp_path,
    monkeypatch,
):
    build = _load_mcpb_build_module()
    monkeypatch.setattr(build, "STAGE_ROOT", tmp_path / "stage")
    stage_bundle = build._stage_bundle

    def _stage_with_broken_runtime():
        stage = stage_bundle()
        (stage / "tinyassets" / "universe_server.py").write_text(
            "this is not valid python !!!",
            encoding="utf-8",
        )
        return stage

    monkeypatch.setattr(build, "_stage_bundle", _stage_with_broken_runtime)
    monkeypatch.setattr(build, "_probe_import", lambda _stage: None)
    monkeypatch.setattr(sys, "argv", ["build_bundle.py"])

    with pytest.raises(
        RuntimeError,
        match="Staged bundle catalog probe failed",
    ):
        build.main()


def test_schema_validation_cannot_skip_semantic_catalog_probe(
    tmp_path,
    monkeypatch,
    capsys,
):
    build = _load_mcpb_build_module()
    monkeypatch.setattr(build, "_stage_bundle", lambda: tmp_path)
    monkeypatch.setattr(build, "_run", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_bundle.py", "--validate", "--skip-probe"],
    )

    with pytest.raises(SystemExit):
        build.main()

    assert "--skip-probe cannot be combined" in capsys.readouterr().err


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


def test_plugin_server_imports_tinyassets_package():
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


def test_bundle_and_plugin_tinyassets_trees_match():
    """Both build scripts stage the same set of files from tinyassets/."""
    _run(MCPB_BUILD)
    _run(PLUGIN_BUILD)
    bundle_files = {
        p.relative_to(DIST_STAGE / "tinyassets")
        for p in (DIST_STAGE / "tinyassets").rglob("*")
        if p.is_file()
    }
    plugin_files = {
        p.relative_to(PLUGIN_RUNTIME / "tinyassets")
        for p in (PLUGIN_RUNTIME / "tinyassets").rglob("*")
        if p.is_file()
    }
    diff = bundle_files.symmetric_difference(plugin_files)
    assert not diff, (
        f"Bundle and plugin tinyassets/ trees diverged: {sorted(diff)}"
    )
