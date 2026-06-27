"""Memory-scope Stage 2a — schema + universe_acl + manifest loader.

Task #28 / design-note ``2026-04-15-memory-scope-tiered.md`` §6 "2a —
Schema + ACL foundation." Schema-only work: no enforcement yet (2b),
no flag flip (2c). This file verifies:

1. KG tables get the 4 scope columns via idempotent migration.
2. `universe_acl` CRUD + public/private detection.
3. `branch_node_scope.yaml` loader roundtrip + validation.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.memory.node_scope import (
    ExternalSource,
    NodeScopeEntry,
    NodeScopeManifest,
    NodeScopeManifestError,
    SliceSpec,
    load_manifest,
    parse_manifest,
)

# ─── universe_acl ────────────────────────────────────────────────────


@pytest.fixture
def base_path(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    from tinyassets.daemon_server import initialize_author_server
    initialize_author_server(base)
    return base


def test_universe_is_private_false_when_no_grants(base_path):
    from tinyassets.daemon_server import universe_is_private
    assert universe_is_private(base_path, universe_id="u-public") is False


def test_grant_then_private(base_path):
    from tinyassets.daemon_server import grant_universe_access, universe_is_private

    grant_universe_access(
        base_path,
        universe_id="u-priv",
        actor_id="alice",
        permission="admin",
        granted_by="alice",
    )
    assert universe_is_private(base_path, universe_id="u-priv") is True
    # Other universes unaffected.
    assert universe_is_private(base_path, universe_id="u-other") is False


def test_grant_is_idempotent_and_updates_permission(base_path):
    from tinyassets.daemon_server import (
        grant_universe_access,
        list_universe_acl,
    )

    grant_universe_access(
        base_path, universe_id="u", actor_id="alice", permission="read",
    )
    grant_universe_access(
        base_path, universe_id="u", actor_id="alice", permission="admin",
        granted_by="alice",
    )
    rows = list_universe_acl(base_path, universe_id="u")
    assert len(rows) == 1
    assert rows[0]["permission"] == "admin"
    assert rows[0]["granted_by"] == "alice"


def test_grant_rejects_unknown_permission(base_path):
    from tinyassets.daemon_server import grant_universe_access

    with pytest.raises(ValueError, match="Unknown permission"):
        grant_universe_access(
            base_path,
            universe_id="u",
            actor_id="alice",
            permission="editor",
        )


def test_revoke_removes_grant(base_path):
    from tinyassets.daemon_server import (
        grant_universe_access,
        revoke_universe_access,
        universe_is_private,
    )

    grant_universe_access(
        base_path, universe_id="u", actor_id="alice", permission="read",
    )
    assert universe_is_private(base_path, universe_id="u") is True
    assert revoke_universe_access(base_path, universe_id="u", actor_id="alice")
    assert universe_is_private(base_path, universe_id="u") is False
    # Second revoke is a no-op.
    assert (
        revoke_universe_access(base_path, universe_id="u", actor_id="alice")
        is False
    )


def test_universe_access_permission_semantics(base_path):
    """Public universe returns 'read' for any actor; private returns
    exactly what was granted or '' if ungranted."""
    from tinyassets.daemon_server import (
        grant_universe_access,
        universe_access_permission,
    )

    # Public universe: anyone is 'read'.
    assert universe_access_permission(
        base_path, universe_id="u-pub", actor_id="alice",
    ) == "read"

    # Grant → private. Alice becomes 'write'; bob gets ''.
    grant_universe_access(
        base_path, universe_id="u-pub", actor_id="alice", permission="write",
    )
    assert universe_access_permission(
        base_path, universe_id="u-pub", actor_id="alice",
    ) == "write"
    assert universe_access_permission(
        base_path, universe_id="u-pub", actor_id="bob",
    ) == ""


def test_list_universe_acl_ordered_by_granted_at(base_path):
    from tinyassets.daemon_server import grant_universe_access, list_universe_acl

    grant_universe_access(
        base_path, universe_id="u", actor_id="first", permission="read",
    )
    grant_universe_access(
        base_path, universe_id="u", actor_id="second", permission="read",
    )
    rows = list_universe_acl(base_path, universe_id="u")
    assert [r["actor_id"] for r in rows] == ["first", "second"]


# ─── KG scope columns ────────────────────────────────────────────────


def test_kg_schema_adds_scope_columns(tmp_path):
    from tinyassets.knowledge.knowledge_graph import KnowledgeGraph

    db_path = tmp_path / "kg.db"
    kg = KnowledgeGraph(db_path=str(db_path))
    cur = kg._conn.execute("PRAGMA table_info(entities)")
    cols = {row["name"] for row in cur}
    for expected in ("universe_id", "goal_id", "branch_id", "user_id"):
        assert expected in cols, f"entities table missing {expected}"
    # Same for every scoped table.
    for table in ("edges", "facts", "communities"):
        cur = kg._conn.execute(f"PRAGMA table_info({table})")
        cols = {row["name"] for row in cur}
        for expected in ("universe_id", "goal_id", "branch_id", "user_id"):
            assert expected in cols, f"{table} missing {expected}"


def test_kg_migration_is_idempotent(tmp_path):
    """Re-opening the DB doesn't re-add columns or error."""
    from tinyassets.knowledge.knowledge_graph import KnowledgeGraph

    db_path = tmp_path / "kg.db"
    KnowledgeGraph(db_path=str(db_path))  # first open = schema create
    # Second open should be a no-op.
    kg2 = KnowledgeGraph(db_path=str(db_path))
    cur = kg2._conn.execute("PRAGMA table_info(entities)")
    cols = [row["name"] for row in cur]
    # No duplicate universe_id columns.
    assert cols.count("universe_id") == 1


def test_kg_migrate_scope_columns_backfills_universe_id(tmp_path):
    from tinyassets.knowledge.knowledge_graph import KnowledgeGraph
    from tinyassets.knowledge.models import GraphEntity

    db_path = tmp_path / "kg.db"
    kg = KnowledgeGraph(db_path=str(db_path))
    # Insert an entity pre-migration (universe_id defaults to NULL).
    kg.add_entity(GraphEntity(
        entity_id="e1",
        entity_type="character",
        access_tier=0,
        public_description="",
        hidden_description="",
        secret_description="",
        aliases=[],
    ))
    # Run migration.
    updated = kg.migrate_scope_columns(universe_id="u-alpha")
    assert updated >= 1
    row = kg._conn.execute(
        "SELECT universe_id FROM entities WHERE entity_id = 'e1'"
    ).fetchone()
    assert row["universe_id"] == "u-alpha"
    # Second migration is idempotent — only NULL rows are touched.
    second = kg.migrate_scope_columns(universe_id="u-alpha")
    assert second == 0


def test_kg_migrate_requires_universe_id(tmp_path):
    from tinyassets.knowledge.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    with pytest.raises(ValueError, match="non-empty universe_id"):
        kg.migrate_scope_columns(universe_id="")


def test_kg_scope_index_exists(tmp_path):
    from tinyassets.knowledge.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph(db_path=str(tmp_path / "kg.db"))
    names = [
        row["name"] for row in kg._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
    ]
    for table in ("entities", "edges", "facts", "communities"):
        assert f"idx_{table}_scope" in names


# ─── LanceDB prose_chunks schema ─────────────────────────────────────


def test_vector_store_seed_carries_scope_fields(tmp_path):
    from tinyassets.retrieval.vector_store import VectorStore, reset_db

    reset_db()
    store = VectorStore(db_path=str(tmp_path / "vec"), embedding_dim=4)
    table = store._ensure_table()
    schema_names = {field.name for field in table.schema}
    for expected in ("universe_id", "goal_id", "branch_id", "user_id"):
        assert expected in schema_names, f"prose_chunks missing {expected}"


def test_vector_store_index_accepts_scope_fields(tmp_path):
    from tinyassets.retrieval.vector_store import VectorStore, reset_db

    reset_db()
    store = VectorStore(db_path=str(tmp_path / "vec"), embedding_dim=4)
    import numpy as np
    rows = [{
        "chunk_id": "c1",
        "text": "hello",
        "scene_id": "s1",
        "chapter_number": 1,
        "character": "",
        "location": "",
        "universe_id": "u-alpha",
        "goal_id": "g-alpha",
        "branch_id": "",
        "user_id": "",
        "embedding": np.ones(4, dtype=np.float32),
    }]
    assert store.index(rows) == 1
    # Seed + 1 real row; count() subtracts seed.
    assert store.count() == 1


# ─── node_scope manifest loader ──────────────────────────────────────


def test_empty_manifest_returns_defaults():
    manifest = parse_manifest("")
    assert isinstance(manifest, NodeScopeManifest)
    assert manifest.default == NodeScopeEntry()
    assert manifest.nodes == {}


def test_missing_file_returns_empty_manifest(tmp_path):
    manifest = load_manifest(tmp_path / "does-not-exist.yaml")
    assert manifest == NodeScopeManifest()


def test_manifest_default_and_per_node_entries():
    raw = """
default:
  universe_member: true
  breadth: full_canon

nodes:
  tone_match:
    breadth: narrow_slice
    slice_spec:
      relation_types: [voice_example, dialogue_sample]

  market_summary:
    universe_member: false
    external_sources:
      - kind: external_api
        identifier: market_data_api
"""
    manifest = parse_manifest(raw)
    assert manifest.default.universe_member is True
    assert manifest.default.breadth == "full_canon"

    tm = manifest.for_node("tone_match")
    assert tm.breadth == "narrow_slice"
    assert tm.slice_spec == SliceSpec(
        relation_types=("voice_example", "dialogue_sample"),
    )

    ms = manifest.for_node("market_summary")
    assert ms.universe_member is False
    assert ms.external_sources == (
        ExternalSource(kind="external_api", identifier="market_data_api"),
    )

    # Missing node falls back to default.
    fallback = manifest.for_node("never_declared")
    assert fallback == manifest.default


def test_manifest_rejects_unknown_top_level_field():
    with pytest.raises(NodeScopeManifestError, match="unknown top-level"):
        parse_manifest("unknown_field: 1\n")


def test_manifest_rejects_narrow_slice_without_spec():
    raw = """
default:
  breadth: narrow_slice
"""
    with pytest.raises(NodeScopeManifestError, match="narrow_slice requires"):
        parse_manifest(raw)


def test_manifest_rejects_external_member_without_sources():
    raw = """
nodes:
  out_of_universe:
    universe_member: false
"""
    with pytest.raises(NodeScopeManifestError, match="requires at least one"):
        parse_manifest(raw)


def test_manifest_rejects_unknown_external_kind():
    raw = """
nodes:
  x:
    universe_member: false
    external_sources:
      - kind: weird_source
        identifier: foo
"""
    with pytest.raises(NodeScopeManifestError, match="must be one of"):
        parse_manifest(raw)


def test_manifest_rejects_empty_slice_spec():
    raw = """
default:
  breadth: narrow_slice
  slice_spec:
    entity_ids: []
"""
    with pytest.raises(NodeScopeManifestError, match="narrow_slice requires"):
        parse_manifest(raw)


def test_manifest_rejects_invalid_yaml():
    with pytest.raises(NodeScopeManifestError, match="invalid YAML"):
        parse_manifest("::: not yaml ::")


def test_manifest_roundtrip_from_file(tmp_path):
    raw = """
default:
  universe_member: true
  breadth: full_canon

nodes:
  basic:
    breadth: full_canon
"""
    p = Path(tmp_path) / "node_scope.yaml"
    p.write_text(raw, encoding="utf-8")
    manifest = load_manifest(p)
    assert "basic" in manifest.nodes
    assert manifest.for_node("basic").breadth == "full_canon"
