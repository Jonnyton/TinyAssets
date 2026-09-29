from __future__ import annotations

import asyncio
import inspect
import json
import math
import sqlite3
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import tinyassets.universe_server as universe_server
from tinyassets.api import universe as universe_api
from tinyassets.auth.provider import Identity
from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
    initialize_author_server,
)
from tinyassets.storage import CAP_GRANT_CAPABILITIES, db_path
from tinyassets.storage.accounts import (
    create_or_update_account,
    grant_capabilities,
)

REQUEST_FIELDS = {
    "idempotency_key",
    "graph_id",
    "text",
    "request_type",
    "branch_id",
    "pickup_incentive",
    "directed_daemon_id",
    "directed_daemon_instruction",
    "priority_weight",
}


def _connect(base_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(base_path))
    conn.row_factory = sqlite3.Row
    return conn


def _add_universe(base_path: Path, universe_id: str) -> None:
    universe_dir = base_path / universe_id
    universe_dir.mkdir(parents=True, exist_ok=True)
    ensure_universe_registered(
        base_path,
        universe_id=universe_id,
        universe_path=universe_dir,
    )


def _actor(base_path: Path, username: str) -> str:
    return str(
        create_or_update_account(base_path, username=username)["user_id"]
    )


def _authenticate(
    monkeypatch: pytest.MonkeyPatch,
    *,
    actor_id: str,
    tenant_id: str = "tenant-a",
    capabilities: list[str] | None = None,
) -> None:
    identity = Identity(
        user_id=actor_id,
        username=actor_id,
        capabilities=capabilities or ["tinyassets.universe.write"],
        metadata={"org_id": tenant_id},
    )
    monkeypatch.setattr(
        "tinyassets.auth.middleware.current_identity",
        lambda: identity,
    )


@pytest.fixture
def admission_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str | Path]:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY",
        "test-only-request-admission-secret-32-bytes",
    )
    monkeypatch.setattr(
        universe_server,
        "write_gate_rejection",
        lambda _tool: None,
    )
    monkeypatch.setattr(
        universe_api,
        "_universe_loop_dispatch",
        lambda _udir: ("loop-branch", {"mode": "v2"}),
    )
    initialize_author_server(tmp_path)
    _add_universe(tmp_path, "universe-a")
    issuer_id = _actor(tmp_path, "issuer")
    subject_id = _actor(tmp_path, "subject")
    grant_universe_access(
        tmp_path,
        universe_id="universe-a",
        actor_id=issuer_id,
        permission="admin",
        granted_by=issuer_id,
    )
    grant_capabilities(
        tmp_path,
        user_id=issuer_id,
        capabilities=[CAP_GRANT_CAPABILITIES],
        granted_by=issuer_id,
        universe_id="universe-a",
    )
    grant_universe_access(
        tmp_path,
        universe_id="universe-a",
        actor_id=subject_id,
        permission="write",
        granted_by=issuer_id,
    )
    _authenticate(monkeypatch, actor_id=subject_id)
    return {
        "base_path": tmp_path,
        "issuer_id": issuer_id,
        "subject_id": subject_id,
    }


def _request(
    *,
    key: str = "request-key-0001",
    text: str = "Build the next verified scene.",
    priority_weight: float = 0.0,
) -> dict:
    return {
        "target": "request",
        "idempotency_key": key,
        "graph_id": "universe-a",
        "text": text,
        "request_type": "general",
        "branch_id": "",
        "pickup_incentive": "",
        "directed_daemon_id": "",
        "directed_daemon_instruction": "",
        "priority_weight": priority_weight,
    }


def _table_count(base_path: Path, table: str) -> int:
    with _connect(base_path) as conn:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return 0
            raise
    return int(row[0])


def test_canonical_write_graph_advertises_request_fields() -> None:
    signature = inspect.signature(universe_server.write_graph)
    for field in REQUEST_FIELDS:
        assert field in signature.parameters

    tool = next(
        tool
        for tool in asyncio.run(
            universe_server.mcp.list_tools(run_middleware=False)
        )
        if tool.name == "write_graph"
    )
    assert REQUEST_FIELDS <= set(tool.parameters["properties"])
    assert tool.annotations.idempotentHint is False


def test_all_runtime_manifests_include_rfc8785() -> None:
    root = Path(__file__).parents[1]
    manifests = (
        root / "pyproject.toml",
        root / "packaging" / "mcpb" / "pyproject.toml",
        root
        / "packaging"
        / "claude-plugin"
        / "plugins"
        / "tinyassets-universe-server"
        / "runtime"
        / "pyproject.toml",
    )

    for manifest in manifests:
        dependencies = tomllib.loads(
            manifest.read_text(encoding="utf-8")
        )["project"]["dependencies"]
        assert any(
            dependency.startswith("rfc8785")
            for dependency in dependencies
        ), manifest


def test_server_import_probe_does_not_require_uninstalled_runtime_dependency(
) -> None:
    root = Path(__file__).parents[1]
    script = """
import builtins
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == "rfc8785":
        raise ModuleNotFoundError("blocked probe dependency")
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
import tinyassets.universe_server
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("key", "weight"),
    [
        ("", 0),
        ("short-key", 0),
        ("x" * 129, 0),
        ("invalid key spaces", 0),
        ("unicode-key-é-0001", 0),
        ("request-key-0001", True),
        ("request-key-0001", "1"),
        ("request-key-0001", math.nan),
        ("request-key-0001", math.inf),
        ("request-key-0001", -math.inf),
        ("request-key-0001", -1),
        ("request-key-0001", 100.0000001),
        ("request-key-0001", 10**400),
    ],
)
def test_invalid_key_or_numeric_shape_fails_before_persistence(
    admission_context: dict[str, str | Path],
    key,
    weight,
) -> None:
    result = json.loads(
        universe_server.write_graph(
            **_request(key=key, priority_weight=weight)
        )
    )

    assert result == {"error": "request_validation_error"}
    base_path = Path(admission_context["base_path"])
    assert _table_count(base_path, "request_admissions") == 0
    assert _table_count(base_path, "user_requests") == 0
    assert _table_count(base_path, "branch_tasks_v2") == 0


def test_non_utf8_request_field_fails_before_persistence(
    admission_context: dict[str, str | Path],
) -> None:
    result = json.loads(
        universe_server.write_graph(
            **_request(text="invalid-surrogate-\ud800")
        )
    )

    assert result == {"error": "request_validation_error"}
    base_path = Path(admission_context["base_path"])
    assert _table_count(base_path, "request_admissions") == 0
    assert _table_count(base_path, "user_requests") == 0
    assert _table_count(base_path, "branch_tasks_v2") == 0


def test_unknown_request_target_fields_are_rejected_without_mutation(
    admission_context: dict[str, str | Path],
) -> None:
    result = json.loads(
        universe_server.write_graph(
            **_request(),
            name="goal-only-field",
        )
    )

    assert result == {"error": "request_validation_error"}
    assert _table_count(
        Path(admission_context["base_path"]),
        "request_admissions",
    ) == 0
