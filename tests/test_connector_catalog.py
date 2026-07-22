from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

from tinyassets.connector_catalog import (
    DIRECTORY_MCP_PATH,
    DIRECTORY_TOOL_CATALOG_VERSION,
    VERSIONED_DIRECTORY_MCP_PATH,
    directory_mcp_remote_url,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "packaging" / "registry" / "generate_server_json.py"
SERVER_JSON_PATH = REPO_ROOT / "packaging" / "registry" / "server.json"


def _load_generate_server_json() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_server_json", GENERATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_directory_catalog_path_is_versioned_for_host_cache_invalidation() -> None:
    assert DIRECTORY_MCP_PATH == "/mcp-directory"
    assert DIRECTORY_TOOL_CATALOG_VERSION in VERSIONED_DIRECTORY_MCP_PATH
    assert VERSIONED_DIRECTORY_MCP_PATH.startswith("/mcp-directory/catalog/")


def test_registry_advertises_versioned_directory_catalog_url() -> None:
    document = _load_generate_server_json()._build_document()

    assert document["remotes"] == [
        {
            "type": "streamable-http",
            "url": directory_mcp_remote_url(),
        }
    ]


def test_committed_registry_manifest_matches_generated_document() -> None:
    committed_document = json.loads(SERVER_JSON_PATH.read_text(encoding="utf-8"))
    generated_document = _load_generate_server_json()._build_document()

    assert committed_document == generated_document


def test_registry_generator_check_runs_directly_from_repository_root() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR_PATH), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
