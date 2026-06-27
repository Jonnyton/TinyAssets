"""Tests for scripts/import_graph_smoke.py — catches the 2026-04-19 P0 class.

Includes positive smoke (current tree is green) AND negative coverage:
a synthetic package whose ``__all__`` declares a name that doesn't exist
must make the smoke exit 1 with the regression in stderr. That's the
"ALL_CAPABILITIES missing from tinyassets.storage" scenario generalized.

Also exercises the lazy-``__getattr__`` surface on ``tinyassets.storage``
directly to prove the Option-A change is observable.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "import_graph_smoke.py"


def _run_smoke(*extra_args: str, cwd: Path = _REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *extra_args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---- positive path ---------------------------------------------------------


def test_primary_targets_import_clean():
    """Current HEAD must pass the smoke — regression guard."""
    result = _run_smoke("--primary-only", "--verbose")
    assert result.returncode == 0, (
        f"primary-only smoke failed unexpectedly\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "ALL CLEAN" in result.stdout


def test_full_extended_target_set_is_clean():
    result = _run_smoke()
    assert result.returncode == 0, (
        f"extended smoke failed unexpectedly\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---- negative path: missing __all__ name ----------------------------------


def test_missing_all_name_raises(tmp_path):
    """Synthesize a package whose __all__ declares a name that doesn't resolve.

    Reproduces the 2026-04-19 P0 class at test scope: ``__all__``
    declares ``ALL_CAPABILITIES`` but the module doesn't bind it. The
    smoke must detect + exit 1.
    """
    pkg = tmp_path / "broken_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(textwrap.dedent('''
        """A deliberately-broken package: __all__ lies."""
        __all__ = ["ALL_CAPABILITIES", "real_name"]
        real_name = "ok"
        # ALL_CAPABILITIES deliberately not bound — reproduces the
        # 2026-04-19 P0 class (symbol declared but missing at runtime).
    '''), encoding="utf-8")

    # Build a tiny smoke-runner that targets our synthetic package.
    runner = tmp_path / "run_smoke.py"
    runner.write_text(textwrap.dedent(f'''
        import sys
        sys.path.insert(0, {str(_REPO_ROOT / "scripts")!r})
        sys.path.insert(0, {str(tmp_path)!r})
        from import_graph_smoke import _check_module
        errors = _check_module("broken_pkg", verbose=False)
        if errors:
            for err in errors:
                print("ERR:", err)
            sys.exit(1)
        sys.exit(0)
    '''), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(runner)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1, (
        f"smoke should have caught the missing symbol\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "ALL_CAPABILITIES" in result.stdout
    assert "AttributeError" in result.stdout


def test_missing_package_raises(tmp_path):
    """If a target package doesn't import at all, smoke must fail too."""
    runner = tmp_path / "run_smoke.py"
    runner.write_text(textwrap.dedent(f'''
        import sys
        sys.path.insert(0, {str(_REPO_ROOT / "scripts")!r})
        from import_graph_smoke import _check_module
        errors = _check_module("no_such_package_exists_anywhere", verbose=False)
        if errors:
            for err in errors:
                print("ERR:", err)
            sys.exit(1)
        sys.exit(0)
    '''), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(runner)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "no_such_package_exists_anywhere" in result.stdout
    assert "FAILED" in result.stdout


# ---- lazy-__getattr__ surface on tinyassets.storage -------------------------


def test_workflow_storage_lazy_getattr_resolves():
    """Option A: from-import a lazy name + confirm it's the accounts submodule's."""
    import tinyassets.storage as ws
    import tinyassets.storage.accounts as wsa

    # Lazy names the Option A commit routes via __getattr__.
    for name in [
        "ensure_host_account",
        "create_or_update_account",
        "grant_capabilities",
        "resolve_bearer_token",
    ]:
        value = getattr(ws, name)
        assert value is getattr(wsa, name), (
            f"lazy {name} not the same object as accounts.{name}"
        )


def test_workflow_storage_lazy_getattr_caches():
    """Repeat access hits the cached global, not the importlib roundtrip."""
    import tinyassets.storage as ws

    first = ws.ensure_host_account
    second = ws.ensure_host_account
    assert first is second


def test_workflow_storage_dir_enumerates_lazy_names():
    """__dir__ must expose lazy names so static analyzers + import* work."""
    import tinyassets.storage as ws

    names = dir(ws)
    for lazy in [
        "ensure_host_account", "create_or_update_account",
        "grant_capabilities", "resolve_bearer_token",
    ]:
        assert lazy in names, f"dir(tinyassets.storage) missing {lazy}"


def test_workflow_storage_unknown_attr_raises_attribute_error():
    import tinyassets.storage as ws

    with pytest.raises(AttributeError, match="no attribute"):
        ws.definitely_not_an_exported_name  # noqa: B018


# ---- regression guard for the 2026-04-19 P0 scenario ----------------------


def test_all_capabilities_accessible_via_package():
    """Direct regression guard for 2026-04-19 P0 failure mode."""
    from tinyassets.storage import ALL_CAPABILITIES
    assert isinstance(ALL_CAPABILITIES, tuple)
    assert len(ALL_CAPABILITIES) >= 1
    # Sanity: the expected scope of caps shouldn't drop to zero silently.
    assert any("read_public_universe" in cap for cap in ALL_CAPABILITIES)


def test_daemon_server_ALL_CAPABILITIES_still_reachable():
    """Consumer surface: tinyassets.daemon_server re-exports from tinyassets.storage."""
    from tinyassets.daemon_server import ALL_CAPABILITIES as AC_daemon
    from tinyassets.storage import ALL_CAPABILITIES as AC_storage
    assert AC_daemon is AC_storage
