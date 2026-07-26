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

import functools
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MCPB_BUILD = REPO_ROOT / "packaging" / "mcpb" / "build_bundle.py"
MCPB_MANIFEST = REPO_ROOT / "packaging" / "mcpb" / "manifest.json"
MCPB_SERVER = REPO_ROOT / "packaging" / "mcpb" / "server.py"
MCPB_ACCEPTANCE = REPO_ROOT / "packaging" / "mcpb" / "LOCAL_ACCEPTANCE.md"
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


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_mcpb_build_module():
    return _load_module("tinyassets_mcpb_build_bundle_test", MCPB_BUILD)


@functools.lru_cache(maxsize=1)
def build_bundle_module():
    """Cached load, for reading constants without monkeypatch interference."""
    return _load_mcpb_build_module()


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


# ─── MCPB launcher + local configuration ─────────────────────────────
#
# `reconcile-external-connector-manifests` tasks 2.6/2.7 and
# `mcp-connector-distribution` requirement "MCPB Is A Local Stdio Product
# With Explicit Configuration". The MCPB is a *local* product: its wrapper
# validates and exports configuration before stdio starts, a missing data
# directory fails closed (never silently falling back to the platform
# default), and none of this proof may spend maintainer provider quota.

# Pinned probe script: enumeration only. Adding `tools/call` here would let
# the packaging gate execute `converse`/`run_graph` — i.e. a provider call.
STDIO_PROBE_METHODS = (
    "initialize",
    "notifications/initialized",
    "tools/list",
)


def _provider_free_env(data_dir: str) -> dict[str, str]:
    """Environment for a packaging probe: no provider credentials.

    Deliberately does NOT touch ``UNIVERSE_SERVER_AUTH``. That variable
    selects the runtime's auth provider (`tinyassets/auth/provider.py`
    ``create_provider``), so a probe that removed it could not then claim
    anything about the observed auth posture — it would have arranged the
    answer. Tests that reason about auth assert its absence instead.
    """
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "TINYASSETS_DATA_DIR": data_dir,
    }
    env.pop("TINYASSETS_REPO_ROOT", None)
    for name in build_bundle_module().PROVIDER_CREDENTIAL_ENV:
        env.pop(name, None)
    return env


def _build_staged_bundle() -> None:
    """Stage the bundle, failing the test when the build itself fails.

    An ignored return code would let a launch test run against whatever the
    previous build left in the fixed stage directory.
    """
    result = _run(MCPB_BUILD)
    assert result.returncode == 0, (
        f"build_bundle.py failed:\nstdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )


def _stdio_handshake(env: dict[str, str]) -> dict[int, dict]:
    """Drive the staged bundle over real stdio like an installing host would.

    Speaks newline-delimited JSON-RPC into ``server.py``'s stdin exactly as
    the MCPB `mcp_config` launcher does, and returns the responses keyed by
    request id. Each request waits for its response before the next write —
    writing the whole script and closing stdin immediately races the
    server's EOF shutdown against its in-flight dispatch.
    """
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "packaging-probe", "version": "0"},
        },
    }
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    list_tools = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    assert [
        initialize["method"], initialized["method"], list_tools["method"],
    ] == list(STDIO_PROBE_METHODS)

    responses: dict[int, dict] = {}
    # Binary: the child's stderr banner/log is console-codepage encoded.
    with tempfile.TemporaryFile() as err_file:
        proc = subprocess.Popen(
            [sys.executable, str(DIST_STAGE / "server.py")],
            cwd=str(DIST_STAGE),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=err_file,
            text=True,
            bufsize=1,
        )
        watchdog = threading.Timer(300, proc.kill)
        watchdog.start()

        def _stderr() -> str:
            err_file.seek(0)
            return err_file.read().decode("utf-8", "replace")

        def _await(request_id: int) -> None:
            while True:
                line = proc.stdout.readline()
                if not line:
                    pytest.fail(
                        f"stdio server closed before responding to "
                        f"id={request_id}.\nstderr={_stderr()}"
                    )
                line = line.strip()
                if not line.startswith("{"):
                    continue
                message = json.loads(line)
                if isinstance(message.get("id"), int):
                    responses[message["id"]] = message
                    if message["id"] == request_id:
                        return

        try:
            for payload in (initialize,):
                proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            _await(1)

            for payload in (initialized, list_tools):
                proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()
            _await(2)

            proc.stdin.close()
            returncode = proc.wait(timeout=60)
        finally:
            watchdog.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=60)
            stderr = _stderr()

    assert returncode == 0, (
        f"stdio launch failed (rc={returncode}).\nstderr={stderr}"
    )
    assert set(responses) == {1, 2}, f"stderr={stderr}"
    return responses


@pytest.fixture
def mcpb_launcher(monkeypatch):
    """Load the MCPB wrapper with a recording stand-in for the runtime.

    The stand-in makes "validated and exported configuration *before*
    starting stdio" observable: if the wrapper never reaches the runtime,
    no transport started.
    """
    import tinyassets

    module = _load_module("tinyassets_mcpb_server_test", MCPB_SERVER)
    calls: list[dict] = []

    class _RecordingRuntime:
        @staticmethod
        def main(**kwargs):
            calls.append({"kwargs": kwargs, "env": dict(os.environ)})

    monkeypatch.setattr(
        tinyassets, "universe_server", _RecordingRuntime, raising=False,
    )
    # main() prepends the bundle root; keep that out of the session's sys.path.
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("TINYASSETS_DATA_DIR", raising=False)
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    return SimpleNamespace(module=module, calls=calls)


@pytest.mark.parametrize("configured", ["", "   "])
def test_mcpb_launcher_requires_a_configured_data_dir(
    mcpb_launcher, monkeypatch, configured,
):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", configured)

    with pytest.raises(RuntimeError, match="TINYASSETS_DATA_DIR is required"):
        mcpb_launcher.module.main()

    assert mcpb_launcher.calls == [], "transport must not start"


def test_mcpb_launcher_rejects_missing_data_dir(
    mcpb_launcher, monkeypatch, tmp_path,
):
    missing = tmp_path / "not-there"
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(missing))

    with pytest.raises(RuntimeError, match="does not exist"):
        mcpb_launcher.module.main()

    assert mcpb_launcher.calls == []


def test_mcpb_launcher_rejects_non_directory_data_dir(
    mcpb_launcher, monkeypatch, tmp_path,
):
    not_a_dir = tmp_path / "universes.txt"
    not_a_dir.write_text("not a directory\n", encoding="utf-8")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(not_a_dir))

    with pytest.raises(RuntimeError, match="must be a directory"):
        mcpb_launcher.module.main()

    assert mcpb_launcher.calls == []


def test_mcpb_launcher_guard_blocks_the_platform_default_data_dir(
    mcpb_launcher, monkeypatch,
):
    """The fail-closed guard is load-bearing, not decorative.

    ``storage.data_dir()`` resolves an *unset* ``TINYASSETS_DATA_DIR`` to a
    platform default (``%APPDATA%/TinyAssets``, ``~/.tinyassets``). Without
    the wrapper's guard an unconfigured install would silently serve that
    host-global directory instead of the user's selected one.
    """
    from tinyassets import storage

    monkeypatch.delenv("TINYASSETS_DATA_DIR", raising=False)
    platform_default = storage.data_dir()
    assert platform_default.is_absolute()

    with pytest.raises(RuntimeError):
        mcpb_launcher.module.main()

    assert mcpb_launcher.calls == []
    assert os.environ.get("TINYASSETS_DATA_DIR", "") == "", (
        "the wrapper must not select a directory the user did not choose"
    )


def test_mcpb_launcher_exports_config_then_starts_stdio(
    mcpb_launcher, monkeypatch, tmp_path,
):
    data_dir = tmp_path / "universes"
    data_dir.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", f" {data_dir} ")
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", " my-universe ")

    mcpb_launcher.module.main()

    assert len(mcpb_launcher.calls) == 1
    call = mcpb_launcher.calls[0]
    assert call["kwargs"] == {"transport": "stdio"}
    # Configuration is exported *before* the runtime is handed control.
    assert call["env"]["TINYASSETS_DATA_DIR"] == str(data_dir.resolve())
    assert call["env"]["UNIVERSE_SERVER_DEFAULT_UNIVERSE"] == "my-universe"


def test_mcpb_launcher_unsets_a_blank_default_universe(
    mcpb_launcher, monkeypatch, tmp_path,
):
    """`default_universe` is optional; a blank host substitution means unset.

    MCPB substitutes ``${user_config.default_universe}`` with an empty (or
    whitespace) value when the user leaves the optional field alone. Passing
    that through would make the runtime resolve a whitespace universe id
    instead of its ordinary default resolution.
    """
    data_dir = tmp_path / "universes"
    data_dir.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "   ")

    mcpb_launcher.module.main()

    assert len(mcpb_launcher.calls) == 1
    assert (
        "UNIVERSE_SERVER_DEFAULT_UNIVERSE"
        not in mcpb_launcher.calls[0]["env"]
    )


@pytest.mark.parametrize(
    "configured",
    [
        "${user_config.default_universe}",
        "../escape",
        "nested/universe",
        "nested\\universe",
        ".hidden",
        "stream:name",
    ],
)
def test_mcpb_launcher_rejects_unusable_default_universe(
    mcpb_launcher, monkeypatch, tmp_path, configured,
):
    data_dir = tmp_path / "universes"
    data_dir.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", configured)

    with pytest.raises(
        RuntimeError, match="UNIVERSE_SERVER_DEFAULT_UNIVERSE",
    ):
        mcpb_launcher.module.main()

    assert mcpb_launcher.calls == [], "transport must not start"


def test_mcpb_launcher_configures_no_remote_auth(
    mcpb_launcher, monkeypatch, tmp_path,
):
    """Observed local auth posture: the wrapper configures no hosted identity."""
    data_dir = tmp_path / "universes"
    data_dir.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_dir))
    before = set(os.environ)

    mcpb_launcher.module.main()

    introduced = set(mcpb_launcher.calls[0]["env"]) - before
    assert introduced == set(), (
        f"wrapper introduced unexpected environment: {sorted(introduced)}"
    )
    source = MCPB_SERVER.read_text(encoding="utf-8").lower()
    for claim in ("workos", "oauth", "authkit", "bearer"):
        assert claim not in source, (
            f"local launcher must not configure a remote {claim} boundary"
        )


def test_mcpb_manifest_declares_local_stdio_configuration():
    manifest = json.loads(MCPB_MANIFEST.read_text(encoding="utf-8"))

    user_config = manifest["user_config"]
    assert user_config["tinyassets_data_dir"]["required"] is True
    assert user_config["tinyassets_data_dir"]["type"] == "directory"
    assert user_config["default_universe"]["required"] is False

    mcp_config = manifest["server"]["mcp_config"]
    assert mcp_config["env"] == {
        "TINYASSETS_DATA_DIR": "${user_config.tinyassets_data_dir}",
        "UNIVERSE_SERVER_DEFAULT_UNIVERSE": "${user_config.default_universe}",
    }
    assert mcp_config["args"][-1].endswith("server.py"), (
        "the bundle launches its local wrapper, not a remote URL"
    )

    # A local stdio product must not advertise the hosted OAuth boundary.
    blob = MCPB_MANIFEST.read_text(encoding="utf-8").lower()
    for claim in ("workos", "oauth", "authkit", "tinyassets.io/mcp", "http"):
        assert claim not in blob, f"MCPB manifest must not claim {claim}"


def test_staged_bundle_launches_over_stdio_and_enumerates_seven():
    """Real launcher proof: install-shaped stdio boot from an isolated dir."""
    _build_staged_bundle()
    with tempfile.TemporaryDirectory(prefix="tinyassets-mcpb-stdio-") as data:
        responses = _stdio_handshake(_provider_free_env(data))

    initialize = responses[1]["result"]
    assert initialize["serverInfo"]["name"] == "TinyAssets"
    tools = {tool["name"] for tool in responses[2]["result"]["tools"]}
    assert tools == CANONICAL_MCPB_TOOLS


def test_staged_bundle_stdio_launch_fails_closed_without_data_dir():
    """The same fail-closed guard, proven on the artifact users install."""
    _build_staged_bundle()
    env = _provider_free_env("")
    env.pop("TINYASSETS_DATA_DIR")

    proc = subprocess.run(
        [sys.executable, str(DIST_STAGE / "server.py")],
        cwd=str(DIST_STAGE),
        env=env,
        input='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n',
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert proc.returncode != 0, "unconfigured launch must fail loudly"
    assert "TINYASSETS_DATA_DIR is required" in proc.stderr
    assert '"result"' not in proc.stdout, "transport must not have started"


def test_bundle_configures_no_auth_provider_selection():
    """Observed local auth posture, stated as what is actually provable.

    ``create_provider()`` picks the runtime's auth provider from
    ``UNIVERSE_SERVER_AUTH`` in the *inherited* environment. The bundle
    declares no such value, so a bundle-configured process gets the
    no-auth ``DevAuthProvider`` default. Proven by asking the staged
    runtime which provider it selects under exactly the environment the
    manifest configures — not by deleting the variable and calling the
    result unauthenticated.
    """
    _build_staged_bundle()
    manifest = json.loads(MCPB_MANIFEST.read_text(encoding="utf-8"))
    assert "UNIVERSE_SERVER_AUTH" not in manifest["server"]["mcp_config"]["env"]

    with tempfile.TemporaryDirectory(prefix="tinyassets-mcpb-auth-") as data:
        env = _provider_free_env(data)
        assert "UNIVERSE_SERVER_AUTH" not in env, (
            "this proof needs an environment where the bundle's own "
            "configuration decides the auth provider"
        )
        probe = subprocess.run(
            [
                sys.executable, "-c",
                f"import sys; sys.path.insert(0, {str(DIST_STAGE)!r}); "
                "from tinyassets.auth.provider import create_provider; "
                "print(type(create_provider()).__name__)",
            ],
            cwd=str(DIST_STAGE),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )

    assert probe.returncode == 0, (
        f"auth provider probe failed:\nstdout={probe.stdout}\n"
        f"stderr={probe.stderr}"
    )
    assert "DevAuthProvider" in probe.stdout, (
        f"expected the no-auth default, got: {probe.stdout.strip()}"
    )


def test_staged_bundle_enumerates_without_credentials():
    """An uncredentialed client completes initialize and enumeration.

    Enumeration is not an authorization check — per-call gating is not
    proven here, and `LOCAL_ACCEPTANCE.md` says so.
    """
    _build_staged_bundle()
    with tempfile.TemporaryDirectory(prefix="tinyassets-mcpb-anon-") as data:
        responses = _stdio_handshake(_provider_free_env(data))

    assert "error" not in responses[2]
    assert responses[2]["result"]["tools"], "catalog must enumerate"


def test_packaging_probes_are_provider_free():
    """Task 2.7: no packaging/parity/acceptance probe may spend maintainer quota."""
    env = _provider_free_env("/tmp/does-not-matter")
    credentials = build_bundle_module().PROVIDER_CREDENTIAL_ENV
    leaked = [name for name in credentials if name in env]
    assert leaked == [], f"provider credentials leaked into a probe: {leaked}"
    assert STDIO_PROBE_METHODS == (
        "initialize",
        "notifications/initialized",
        "tools/list",
    ), (
        "the stdio proof is enumeration-only; adding tools/call would let "
        "packaging execute converse/run_graph against a provider"
    )


def test_build_bundle_probes_strip_provider_credentials(monkeypatch, tmp_path):
    """The build's own runtime probes must not inherit maintainer credentials.

    ``_probe_catalog`` boots the staged runtime, so an inherited provider key
    is exactly the shape that turns a packaging gate into billable work.
    """
    build = _load_mcpb_build_module()
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "manifest.json").write_text(
        json.dumps(
            {"tools": [{"name": name} for name in sorted(CANONICAL_MCPB_TOOLS)]},
        ),
        encoding="utf-8",
    )
    for name in build.PROVIDER_CREDENTIAL_ENV:
        monkeypatch.setenv(name, "must-not-reach-a-probe")

    captured: list[dict[str, str]] = []

    def _fake_run(cmd, **kwargs):
        captured.append(dict(kwargs.get("env") or {}))
        payload = json.dumps(sorted(CANONICAL_MCPB_TOOLS))
        return subprocess.CompletedProcess(
            cmd, 0, f"TINYASSETS_MCPB_CATALOG={payload}\nprobe-ok\n", "",
        )

    monkeypatch.setattr(build.subprocess, "run", _fake_run)
    build._probe_import(stage)
    build._probe_catalog(stage)

    assert len(captured) == 2, "both probes must run"
    for env in captured:
        leaked = [name for name in build.PROVIDER_CREDENTIAL_ENV if name in env]
        assert leaked == [], f"probe inherited provider credentials: {leaked}"


def test_mcpb_local_acceptance_record_is_explicit():
    """Task 2.7: actor-dependent limitations are recorded, not implied."""
    assert MCPB_ACCEPTANCE.is_file(), (
        "packaging/mcpb/LOCAL_ACCEPTANCE.md must record what the local "
        "product's proof does and does not cover"
    )
    text = MCPB_ACCEPTANCE.read_text(encoding="utf-8")
    lowered = text.lower()

    for heading in ("## proven", "## not proven", "## observed local auth posture"):
        assert heading in lowered, f"missing section: {heading}"
    for limitation in ("provider", "identity parity", "anonymous"):
        assert limitation in lowered, f"limitation not recorded: {limitation}"
    assert "tests/test_packaging_build.py" in text, (
        "the record must name the tests that back it"
    )
    # Structural only — it cannot judge prose. Its job is to keep the two
    # claims that would silently become false from being made at all.
    for overclaim in ("oauth-backed", "workos-backed", "hosted parity"):
        assert overclaim not in lowered, f"record overclaims: {overclaim}"
