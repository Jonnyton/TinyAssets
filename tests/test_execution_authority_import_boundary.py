from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_ROOT = _REPO_ROOT / "tinyassets"
_FAKE_MODULE = "tests.support.execution_authority"


def _fake_api():
    try:
        from tests.support.execution_authority import (
            D0ConfigurationError,
            TestAuthorityRoot,
            test_authority_sentinel,
        )
    except ImportError as exc:
        pytest.fail(f"D0 fake composition root is missing: {exc}")
    return D0ConfigurationError, TestAuthorityRoot, test_authority_sentinel


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_no_production_module_imports_the_fake_root() -> None:
    offenders: list[str] = []
    for path in _PACKAGE_ROOT.rglob("*.py"):
        relative = path.relative_to(_PACKAGE_ROOT)
        if _FAKE_MODULE in _imports_in(path):
            offenders.append(relative.as_posix())
    assert offenders == []


def test_authority_core_cannot_import_operational_adapters() -> None:
    forbidden = (
        "tinyassets.api",
        "tinyassets.bid",
        "tinyassets.branch_tasks",
        "tinyassets.cloud_worker",
        "tinyassets.credentials",
        "tinyassets.daemon_registry",
        "tinyassets.effectors",
        "tinyassets.graph",
        "tinyassets.providers",
        "tinyassets.sandbox",
        "tinyassets.storage",
    )
    offenders: list[str] = []
    authority_root = _PACKAGE_ROOT / "execution_authority"
    if not authority_root.is_dir():
        pytest.fail("D0 execution_authority package is missing")
    for path in authority_root.rglob("*.py"):
        for imported in _imports_in(path):
            if imported.startswith(forbidden):
                offenders.append(f"{path.name}: {imported}")
    assert offenders == []


def test_production_imports_never_load_the_fake_root() -> None:
    script = """
import importlib, json, sys
targets = [
    "tinyassets.api.runs",
    "tinyassets.runs",
    "tinyassets.branch_tasks_v2",
]
for target in targets:
    importlib.import_module(target)
print(json.dumps({"fake_loaded": "tests.support.execution_authority" in sys.modules}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"fake_loaded": False}


def test_fake_root_is_not_exported_from_the_authority_package() -> None:
    import tinyassets.execution_authority as authority

    assert not hasattr(authority, "TestAuthorityRoot")
    assert not hasattr(authority, "test_authority_sentinel")
    assert not (_PACKAGE_ROOT / "testing" / "execution_authority.py").exists()
    assert not (
        _REPO_ROOT
        / "packaging"
        / "claude-plugin"
        / "plugins"
        / "tinyassets-universe-server"
        / "runtime"
        / "tinyassets"
        / "testing"
        / "execution_authority.py"
    ).exists()


@pytest.mark.parametrize("mode", ["production", "prod", "unknown", ""])
def test_fake_root_rejects_every_non_test_mode(tmp_path: Path, mode: str) -> None:
    error, root_type, sentinel = _fake_api()
    with pytest.raises(error, match="test mode"):
        root_type.create(
            sentinel=sentinel(),
            mode=mode,
            state_dir=tmp_path,
        )


def test_fake_root_rejects_missing_or_forged_sentinel(tmp_path: Path) -> None:
    error, root_type, _ = _fake_api()
    for sentinel in (None, object(), "test", True):
        with pytest.raises(error, match="sentinel"):
            root_type.create(sentinel=sentinel, mode="test", state_dir=tmp_path)


def test_environment_cannot_enable_or_supply_the_fake_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error, root_type, _ = _fake_api()
    monkeypatch.setenv("TINYASSETS_MODE", "test")
    monkeypatch.setenv("TINYASSETS_D0_TEST_SENTINEL", "enabled")
    monkeypatch.setenv("TINYASSETS_AUTHORITY_KEY", "caller-key")

    with pytest.raises(error, match="sentinel"):
        root_type.create(sentinel=object(), mode="test", state_dir=tmp_path)


def test_invalid_configuration_fails_before_test_key_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tests.support.execution_authority as fake_module

    error, root_type, sentinel = _fake_api()

    class KeyCreationTripwire:
        @staticmethod
        def from_private_bytes(seed: bytes):
            raise AssertionError(f"key creation was reached with {len(seed)} bytes")

    monkeypatch.setattr(fake_module, "Ed25519PrivateKey", KeyCreationTripwire)
    with pytest.raises(error, match="test mode"):
        root_type.create(
            sentinel=sentinel(),
            mode="production",
            state_dir=tmp_path,
        )


def test_fake_root_rejects_non_temporary_or_escaped_state(tmp_path: Path) -> None:
    error, root_type, sentinel = _fake_api()
    durable = _REPO_ROOT / ".d0-must-not-create"
    with pytest.raises(error, match="temporary"):
        root_type.create(
            sentinel=sentinel(),
            mode="test",
            state_dir=durable,
        )
    assert not durable.exists()

    escaped = tmp_path / "escaped"
    try:
        escaped.symlink_to(_REPO_ROOT, target_is_directory=True)
    except OSError:
        return
    with pytest.raises(error, match="temporary|escape"):
        root_type.create(
            sentinel=sentinel(),
            mode="test",
            state_dir=escaped,
        )


@pytest.mark.parametrize(
    "aliased_name",
    ("blobs", "execution-authority.sqlite3", ".d0-authority-initialized"),
)
def test_fake_root_rejects_aliased_child_state_entries(
    tmp_path: Path,
    aliased_name: str,
) -> None:
    error, root_type, sentinel = _fake_api()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    target = tmp_path / f"{aliased_name}-target"
    aliased = state_dir / aliased_name
    if aliased_name == "blobs":
        target.mkdir()
        is_directory = True
    else:
        target.write_bytes(
            b"d0-authority-state/v1\n" if aliased_name == ".d0-authority-initialized" else b""
        )
        is_directory = False
        companion = (
            state_dir / ".d0-authority-initialized"
            if aliased_name == "execution-authority.sqlite3"
            else state_dir / "execution-authority.sqlite3"
        )
        companion.write_bytes(
            b"d0-authority-state/v1\n" if companion.name == ".d0-authority-initialized" else b""
        )
    try:
        aliased.symlink_to(target, target_is_directory=is_directory)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"this host cannot create the required symlink: {exc}")
        if is_directory:
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(aliased), str(target)],
                capture_output=True,
                check=False,
                text=True,
            )
            assert junction.returncode == 0, junction.stderr
        else:
            os.link(target, aliased)

    with pytest.raises(error, match="plain|securely open|hard-linked"):
        root_type.create(
            sentinel=sentinel(),
            mode="test",
            state_dir=state_dir,
        )


def test_database_check_use_swap_fails_before_authority_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tests.support.execution_authority as fake_module

    error, root_type, sentinel = _fake_api()
    original_connect = fake_module.sqlite3.connect

    def swapping_connect(database, *args, **kwargs):
        database_path = Path(database)
        displaced = database_path.with_name("displaced.sqlite3")
        try:
            database_path.replace(displaced)
        except PermissionError as exc:
            raise error("D0 authority state entry was held against a check/use swap") from exc
        database_path.touch()
        return original_connect(database_path, *args, **kwargs)

    monkeypatch.setattr(fake_module.sqlite3, "connect", swapping_connect)
    with pytest.raises(error, match="changed during use|held against"):
        root_type.create(
            sentinel=sentinel(),
            mode="test",
            state_dir=tmp_path / "state",
        )


def test_built_plugin_and_wheel_package_set_exclude_fake_authority() -> None:
    build_script = _REPO_ROOT / "packaging" / "claude-plugin" / "build_plugin.py"
    completed = subprocess.run(
        [sys.executable, str(build_script), "--skip-probe"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    runtime = (
        _REPO_ROOT
        / "packaging"
        / "claude-plugin"
        / "plugins"
        / "tinyassets-universe-server"
        / "runtime"
    )
    assert (runtime / "tinyassets" / "execution_authority").is_dir()
    assert not (runtime / "tests").exists()
    forbidden = (
        b"TestAuthorityRoot",
        b"d0-test-capsule-key-v1",
        b"000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    )
    leaks = [
        path.relative_to(runtime).as_posix()
        for path in runtime.rglob("*")
        if path.is_file() and any(marker in path.read_bytes() for marker in forbidden)
    ]
    assert leaks == []

    project = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel_packages = project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "tinyassets" in wheel_packages
    assert all(
        package != "tests" and not package.startswith("tests/") for package in wheel_packages
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"route_registration": object()}, "route"),
        ({"issuer": object()}, "issuer"),
        ({"key_material": b"caller-key"}, "key"),
        ({"verifier": object()}, "verifier"),
        ({"adapters": {"provider": object()}}, "adapter"),
        ({"adapters": {"credential": object()}}, "adapter"),
        ({"adapters": {"queue": object()}}, "adapter"),
        ({"adapters": {"graph": object()}}, "adapter"),
        ({"adapters": {"github": object()}}, "adapter"),
        ({"adapters": {"market": object()}}, "adapter"),
        ({"adapters": {"money": object()}}, "adapter"),
    ],
)
def test_fake_root_rejects_routes_caller_authority_and_external_adapters(
    tmp_path: Path,
    kwargs: dict[str, object],
    message: str,
) -> None:
    error, root_type, sentinel = _fake_api()
    with pytest.raises(error, match=message):
        root_type.create(
            sentinel=sentinel(),
            mode="test",
            state_dir=tmp_path,
            **kwargs,
        )
