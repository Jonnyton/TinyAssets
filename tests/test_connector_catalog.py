from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from workflow.connector_catalog import (
    DIRECTORY_MCP_PATH,
    DIRECTORY_TOOL_CATALOG_VERSION,
    VERSIONED_DIRECTORY_MCP_PATH,
    directory_mcp_remote_url,
)


def _load_generate_server_json() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "packaging"
        / "registry"
        / "generate_server_json.py"
    )
    spec = importlib.util.spec_from_file_location("generate_server_json", path)
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
