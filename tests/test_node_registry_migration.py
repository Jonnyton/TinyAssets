"""Tests for .node_registry.json -> SQLite migration in universe_server."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tinyassets.daemon_server import (
    get_branch_definition,
    initialize_author_server,
)


@pytest.fixture
def server_base(tmp_path: Path) -> Path:
    """Set up a temp directory as the universe server base path."""
    initialize_author_server(tmp_path)
    return tmp_path


def _legacy_nodes() -> list[dict]:
    """Sample legacy node registrations."""
    return [
        {
            "node_id": "consistency-checker",
            "display_name": "Consistency Checker",
            "description": "Checks facts for consistency",
            "phase": "commit",
            "input_keys": ["draft_output", "extracted_facts"],
            "output_keys": ["consistency_notes"],
            "source_code": "def run(state): return {}",
            "dependencies": [],
            "author": "testuser",
            "registered_at": "2026-04-01T00:00:00+00:00",
            "enabled": True,
            "approved": False,
        },
        {
            "node_id": "style-guide",
            "display_name": "Style Guide Enforcer",
            "description": "Enforces style rules",
            "phase": "draft",
            "input_keys": ["draft_output"],
            "output_keys": ["style_notes"],
            "source_code": "def run(state): return {}",
            "dependencies": [],
            "author": "admin",
            "registered_at": "2026-04-02T00:00:00+00:00",
            "enabled": True,
            "approved": True,
        },
    ]


class TestNodeRegistryMigration:
    def test_migration_from_json_file(self, server_base: Path):
        """Legacy .node_registry.json should be migrated on first access."""
        from tinyassets.api.extensions import (
            STANDALONE_NODES_BRANCH_ID,
            _load_nodes,
        )

        # Write a legacy JSON file
        json_path = server_base / ".node_registry.json"
        json_path.write_text(
            json.dumps(_legacy_nodes(), indent=2),
            encoding="utf-8",
        )

        with patch(
            "tinyassets.api.extensions._base_path",
            return_value=server_base,
        ):
            nodes = _load_nodes()

        assert len(nodes) == 2
        assert nodes[0]["node_id"] == "consistency-checker"
        assert nodes[1]["node_id"] == "style-guide"

        # Verify it's in SQLite
        branch = get_branch_definition(
            server_base, branch_def_id=STANDALONE_NODES_BRANCH_ID
        )
        assert branch["name"] == "Standalone Nodes"
        assert len(branch["graph"]["nodes"]) == 2

    def test_no_legacy_file_creates_empty_branch(self, server_base: Path):
        """If no .node_registry.json exists, an empty standalone branch is created."""
        from tinyassets.api.extensions import (
            STANDALONE_NODES_BRANCH_ID,
            _load_nodes,
        )

        with patch(
            "tinyassets.api.extensions._base_path",
            return_value=server_base,
        ):
            nodes = _load_nodes()

        assert nodes == []

        branch = get_branch_definition(
            server_base, branch_def_id=STANDALONE_NODES_BRANCH_ID
        )
        assert branch["graph"]["nodes"] == []

    def test_save_nodes_persists_to_sqlite(self, server_base: Path):
        """_save_nodes should write to SQLite, not JSON file."""
        from tinyassets.api.extensions import (
            _load_nodes,
            _save_nodes,
        )

        with patch(
            "tinyassets.api.extensions._base_path",
            return_value=server_base,
        ):
            # Initialize
            _load_nodes()

            # Save new nodes
            new_nodes = [
                {
                    "node_id": "new-node",
                    "display_name": "New Node",
                    "phase": "custom",
                }
            ]
            _save_nodes(new_nodes)

            # Reload and verify
            loaded = _load_nodes()

        assert len(loaded) == 1
        assert loaded[0]["node_id"] == "new-node"

    def test_migration_is_idempotent(self, server_base: Path):
        """Calling _load_nodes twice should not duplicate data."""
        from tinyassets.api.extensions import _load_nodes

        json_path = server_base / ".node_registry.json"
        json_path.write_text(
            json.dumps(_legacy_nodes(), indent=2),
            encoding="utf-8",
        )

        with patch(
            "tinyassets.api.extensions._base_path",
            return_value=server_base,
        ):
            nodes1 = _load_nodes()
            nodes2 = _load_nodes()

        assert len(nodes1) == 2
        assert len(nodes2) == 2

    def test_register_and_load_round_trip(self, server_base: Path):
        """Full register -> load round trip through SQLite."""
        from tinyassets.api.extensions import _load_nodes, _save_nodes

        with patch(
            "tinyassets.api.extensions._base_path",
            return_value=server_base,
        ):
            # Start empty
            nodes = _load_nodes()
            assert nodes == []

            # Register a node
            nodes.append({
                "node_id": "test-node",
                "display_name": "Test",
                "description": "A test node",
                "phase": "orient",
                "input_keys": ["universe_id"],
                "output_keys": ["test_output"],
                "source_code": "def run(s): return {}",
                "dependencies": [],
                "author": "tester",
                "enabled": True,
                "approved": False,
            })
            _save_nodes(nodes)

            # Reload
            loaded = _load_nodes()

        assert len(loaded) == 1
        assert loaded[0]["node_id"] == "test-node"
        assert loaded[0]["display_name"] == "Test"

    def test_remove_node_and_reload(self, server_base: Path):
        """Removing a node from the list and saving should persist."""
        from tinyassets.api.extensions import _load_nodes, _save_nodes

        with patch(
            "tinyassets.api.extensions._base_path",
            return_value=server_base,
        ):
            # Start with two nodes
            _load_nodes()  # init
            _save_nodes(_legacy_nodes())

            # Remove first node
            nodes = _load_nodes()
            nodes = [n for n in nodes if n.get("node_id") != "consistency-checker"]
            _save_nodes(nodes)

            # Verify
            loaded = _load_nodes()

        assert len(loaded) == 1
        assert loaded[0]["node_id"] == "style-guide"
