"""Tests for Community Branches SQLite CRUD in daemon_server."""

from __future__ import annotations

from pathlib import Path

import pytest

from workflow.branches import (
    BranchDefinition,
    ConditionalEdge,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from workflow.daemon_server import (
    delete_branch_definition,
    fork_branch_definition,
    get_branch_definition,
    initialize_author_server,
    list_branch_definitions,
    save_branch_definition,
    update_branch_definition,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Initialize the daemon_server DB and return the base path."""
    initialize_author_server(tmp_path)
    return tmp_path


def _sample_branch_dict() -> dict:
    """Build a sample BranchDefinition dict for insertion."""
    b = BranchDefinition(
        name="test-branch",
        description="A test branch",
        author="testuser",
        domain_id="fantasy_author",
        tags=["scene", "experimental"],
        entry_point="orient",
        graph_nodes=[
            GraphNodeRef(id="orient", node_def_id="orient-def", position=0),
            GraphNodeRef(id="draft", node_def_id="draft-def", position=1),
        ],
        edges=[
            EdgeDefinition(from_node="START", to_node="orient"),
            EdgeDefinition(from_node="orient", to_node="draft"),
        ],
        conditional_edges=[
            ConditionalEdge(from_node="draft", conditions={"done": "END"}),
        ],
        node_defs=[
            NodeDefinition(
                node_id="orient-def",
                display_name="Orient",
                phase="orient",
                input_keys=["universe_id"],
                output_keys=["orient_result"],
            ),
            NodeDefinition(
                node_id="draft-def",
                display_name="Draft",
                phase="draft",
                input_keys=["orient_result"],
                output_keys=["draft_output"],
            ),
        ],
        state_schema=[
            {"name": "universe_id", "type": "string"},
            {"name": "orient_result", "type": "dict"},
            {"name": "draft_output", "type": "dict"},
        ],
    )
    return b.to_dict()


# ═══════════════════════════════════════════════════════════════════════════
# save + get
# ═══════════════════════════════════════════════════════════════════════════


class TestSaveAndGet:
    def test_save_and_retrieve(self, db_path: Path):
        d = _sample_branch_dict()
        result = save_branch_definition(db_path, branch_def=d)
        assert result["branch_def_id"] == d["branch_def_id"]
        assert result["name"] == "test-branch"
        assert result["author"] == "testuser"
        assert result["domain_id"] == "fantasy_author"
        assert result["published"] is False

        retrieved = get_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        assert retrieved["name"] == "test-branch"
        assert retrieved["tags"] == ["scene", "experimental"]

    def test_graph_topology_preserved(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)
        retrieved = get_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        graph = retrieved["graph"]
        assert graph["entry_point"] == "orient"
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) == 2
        assert len(graph["conditional_edges"]) == 1
        assert graph["nodes"][0]["id"] == "orient"
        assert graph["edges"][0]["from"] == "START"
        assert graph["conditional_edges"][0]["conditions"]["done"] == "END"

    def test_node_defs_preserved(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)
        retrieved = get_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        assert len(retrieved["node_defs"]) == 2
        assert retrieved["node_defs"][0]["node_id"] == "orient-def"

    def test_state_schema_preserved(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)
        retrieved = get_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        schema = retrieved["state_schema"]
        assert len(schema) == 3
        assert schema[0]["name"] == "universe_id"

    def test_get_nonexistent_raises(self, db_path: Path):
        with pytest.raises(KeyError):
            get_branch_definition(db_path, branch_def_id="nonexistent")

    def test_upsert_replaces(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        d["name"] = "updated-name"
        d["version"] = 2
        result = save_branch_definition(db_path, branch_def=d)
        assert result["name"] == "updated-name"
        assert result["version"] == 2

        # Only one row should exist
        all_defs = list_branch_definitions(db_path)
        assert len(all_defs) == 1

    def test_legacy_nodes_key_compat(self, db_path: Path):
        """Legacy format with 'nodes' key should store in graph_json."""
        d = {
            "branch_def_id": "legacy-test",
            "name": "Legacy",
            "nodes": [{"node_id": "x", "display_name": "X"}],
        }
        result = save_branch_definition(db_path, branch_def=d)
        assert result["graph"]["nodes"] == [{"node_id": "x", "display_name": "X"}]


# ═══════════════════════════════════════════════════════════════════════════
# list + filter
# ═══════════════════════════════════════════════════════════════════════════


class TestListAndFilter:
    def _insert_two(self, db_path: Path):
        d1 = _sample_branch_dict()
        d1["name"] = "alpha-branch"
        d1["author"] = "alice"
        d1["domain_id"] = "fantasy_author"
        d1["tags"] = ["scene"]
        d1["published"] = True
        save_branch_definition(db_path, branch_def=d1)

        d2 = _sample_branch_dict()
        d2["branch_def_id"] = "second-id"
        d2["name"] = "beta-branch"
        d2["author"] = "bob"
        d2["domain_id"] = "research_probe"
        d2["tags"] = ["chapter", "experimental"]
        d2["published"] = False
        save_branch_definition(db_path, branch_def=d2)

    def test_list_all(self, db_path: Path):
        self._insert_two(db_path)
        results = list_branch_definitions(db_path)
        assert len(results) == 2

    def test_filter_published(self, db_path: Path):
        self._insert_two(db_path)
        results = list_branch_definitions(db_path, published_only=True)
        assert len(results) == 1
        assert results[0]["name"] == "alpha-branch"

    def test_filter_published_includes_versioned_without_branch_flag(
        self, db_path: Path
    ):
        """BUG-082 regression: branches with a published version_id but no
        branch-level published flag must still appear in
        ``published_only=True`` listings.

        Repro shape from the slice-0 substrate-readiness probe (2026-05-13):
        ``publish_branch_version`` mints a permanent ``branch_version_id``
        in the branch_versions table but does not flip the branch-level
        ``published`` flag, so the discovery filter missed branches the
        substrate had genuinely version-stamped.
        """
        from workflow.branch_versions import publish_branch_version

        # Reuse the insert-two helper: alpha-branch has published=1 (the
        # already-covered legacy path); beta-branch has published=0.
        self._insert_two(db_path)

        # Mint a real published version for beta-branch — the version
        # store records it, the branch-level flag stays False.
        beta_def = get_branch_definition(db_path, branch_def_id="second-id")
        publish_branch_version(db_path, beta_def)

        results = list_branch_definitions(db_path, published_only=True)
        names = sorted(item["name"] for item in results)
        assert names == ["alpha-branch", "beta-branch"], (
            "published_only must include a branch with a published "
            "version_id even when its branch-level published flag is False"
        )

    def test_filter_author(self, db_path: Path):
        self._insert_two(db_path)
        results = list_branch_definitions(db_path, author="bob")
        assert len(results) == 1
        assert results[0]["name"] == "beta-branch"

    def test_filter_domain_id(self, db_path: Path):
        self._insert_two(db_path)
        results = list_branch_definitions(db_path, domain_id="research_probe")
        assert len(results) == 1
        assert results[0]["name"] == "beta-branch"

    def test_filter_tag(self, db_path: Path):
        self._insert_two(db_path)
        results = list_branch_definitions(db_path, tag="experimental")
        assert len(results) == 1
        assert results[0]["name"] == "beta-branch"

    def test_filter_name_contains(self, db_path: Path):
        self._insert_two(db_path)
        results = list_branch_definitions(db_path, name_contains="alpha")
        assert len(results) == 1
        assert results[0]["name"] == "alpha-branch"

    def test_filter_combined(self, db_path: Path):
        self._insert_two(db_path)
        results = list_branch_definitions(
            db_path, author="bob", tag="chapter"
        )
        assert len(results) == 1

    def test_empty_results(self, db_path: Path):
        results = list_branch_definitions(db_path)
        assert results == []


# ═══════════════════════════════════════════════════════════════════════════
# update
# ═══════════════════════════════════════════════════════════════════════════


class TestUpdate:
    def test_update_simple_fields(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"name": "new-name", "version": 5},
        )
        assert result["name"] == "new-name"
        assert result["version"] == 5

    def test_update_domain_id(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"domain_id": "research_probe"},
        )
        assert result["domain_id"] == "research_probe"

    def test_update_tags(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"tags": ["new-tag"]},
        )
        assert result["tags"] == ["new-tag"]

    def test_update_published(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"published": True},
        )
        assert result["published"] is True

    def test_update_node_defs(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        new_defs = [{"node_id": "new-def", "display_name": "New"}]
        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"node_defs": new_defs},
        )
        assert len(result["node_defs"]) == 1
        assert result["node_defs"][0]["node_id"] == "new-def"

    def test_update_graph_nodes(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        new_graph_nodes = [{"id": "new-node", "node_def_id": "", "position": 0}]
        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"graph_nodes": new_graph_nodes},
        )
        assert len(result["graph"]["nodes"]) == 1
        assert result["graph"]["nodes"][0]["id"] == "new-node"

    def test_update_legacy_nodes_key(self, db_path: Path):
        """Legacy 'nodes' key should update graph_json.nodes."""
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"nodes": [{"id": "legacy"}]},
        )
        assert result["graph"]["nodes"] == [{"id": "legacy"}]

    def test_update_bumps_updated_at(self, db_path: Path):
        d = _sample_branch_dict()
        saved = save_branch_definition(db_path, branch_def=d)
        original_ts = saved["updated_at"]

        result = update_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            updates={"name": "bump-test"},
        )
        assert result["updated_at"] >= original_ts


# ═══════════════════════════════════════════════════════════════════════════
# delete
# ═══════════════════════════════════════════════════════════════════════════


class TestDelete:
    def test_delete_existing(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)
        assert delete_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        with pytest.raises(KeyError):
            get_branch_definition(db_path, branch_def_id=d["branch_def_id"])

    def test_delete_nonexistent(self, db_path: Path):
        assert not delete_branch_definition(
            db_path, branch_def_id="nonexistent"
        )


# ═══════════════════════════════════════════════════════════════════════════
# fork
# ═══════════════════════════════════════════════════════════════════════════


class TestFork:
    def test_fork_creates_new_branch(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        forked = fork_branch_definition(
            db_path,
            branch_def_id=d["branch_def_id"],
            new_name="forked-branch",
            author="forkuser",
        )
        assert forked["branch_def_id"] != d["branch_def_id"]
        assert forked["name"] == "forked-branch"
        assert forked["author"] == "forkuser"
        assert forked["domain_id"] == "fantasy_author"
        assert forked["parent_def_id"] == d["branch_def_id"]
        assert forked["version"] == 1
        assert forked["published"] is False

    def test_fork_preserves_topology(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        forked = fork_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        assert len(forked["graph"]["nodes"]) == 2
        assert len(forked["graph"]["edges"]) == 2
        assert len(forked["node_defs"]) == 2

    def test_fork_increments_source_fork_count(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)

        fork_branch_definition(db_path, branch_def_id=d["branch_def_id"])

        source = get_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        assert source["stats"]["fork_count"] == 1

    def test_fork_resets_stats(self, db_path: Path):
        d = _sample_branch_dict()
        d["stats"] = {"fork_count": 10, "run_count": 100, "avg_quality_score": 0.9}
        save_branch_definition(db_path, branch_def=d)

        forked = fork_branch_definition(
            db_path, branch_def_id=d["branch_def_id"]
        )
        assert forked["stats"]["fork_count"] == 0
        assert forked["stats"]["run_count"] == 0

    def test_fork_nonexistent_raises(self, db_path: Path):
        with pytest.raises(KeyError):
            fork_branch_definition(
                db_path, branch_def_id="nonexistent"
            )

    def test_two_branches_after_fork(self, db_path: Path):
        d = _sample_branch_dict()
        save_branch_definition(db_path, branch_def=d)
        fork_branch_definition(db_path, branch_def_id=d["branch_def_id"])

        all_defs = list_branch_definitions(db_path)
        assert len(all_defs) == 2


# ═══════════════════════════════════════════════════════════════════════════
# Cross-Goal node reuse discovery (#62)
# ═══════════════════════════════════════════════════════════════════════════


def _branch_with_nodes(
    name: str,
    node_specs: list[dict],
    goal_id: str | None = None,
) -> dict:
    """Build a minimal branch dict with the given nodes."""
    from workflow.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    node_defs = [
        NodeDefinition(**{"display_name": spec.get("node_id", ""), **spec})
        for spec in node_specs
    ]
    graph_nodes = [
        GraphNodeRef(id=nd.node_id, node_def_id=nd.node_id, position=i)
        for i, nd in enumerate(node_defs)
    ]
    edges = [EdgeDefinition(from_node="START", to_node=node_defs[0].node_id)]
    for i in range(len(node_defs) - 1):
        edges.append(
            EdgeDefinition(from_node=node_defs[i].node_id,
                           to_node=node_defs[i + 1].node_id),
        )
    edges.append(EdgeDefinition(from_node=node_defs[-1].node_id, to_node="END"))

    b = BranchDefinition(
        name=name,
        author="testuser",
        domain_id="workflow",
        entry_point=node_defs[0].node_id,
        graph_nodes=graph_nodes,
        edges=edges,
        node_defs=node_defs,
    )
    d = b.to_dict()
    if goal_id is not None:
        d["goal_id"] = goal_id
    return d


class TestGoalCommonNodesAll:
    """Cross-Goal variant of goal_common_nodes for #62."""

    def test_aggregates_across_goals(self, db_path: Path):
        from workflow.daemon_server import goal_common_nodes_all

        rigor = {
            "node_id": "rigor_checker",
            "display_name": "Rigor Checker",
            "description": "Audits citations for rigor",
            "phase": "reflect",
        }
        other = {
            "node_id": "drafter",
            "display_name": "Drafter",
            "phase": "draft",
        }
        # Two branches in different Goals share rigor_checker.
        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "research-paper", [rigor, other], goal_id="goal-research",
        ))
        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "prosecutorial-brief", [rigor, other], goal_id="goal-legal",
        ))

        entries = goal_common_nodes_all(db_path, min_branches=2)
        rigor_entry = next(
            (e for e in entries if e["node_id"] == "rigor_checker"), None,
        )
        assert rigor_entry is not None, (
            "rigor_checker appears in 2 branches and should surface"
        )
        assert rigor_entry["occurrence_count"] == 2
        assert set(rigor_entry["goal_ids"]) == {"goal-research", "goal-legal"}

    def test_threshold_filters_singletons(self, db_path: Path):
        from workflow.daemon_server import goal_common_nodes_all

        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "solo", [{"node_id": "unique_node", "display_name": "X"}],
            goal_id="goal-a",
        ))
        entries_2 = goal_common_nodes_all(db_path, min_branches=2)
        assert not any(e["node_id"] == "unique_node" for e in entries_2)
        entries_1 = goal_common_nodes_all(db_path, min_branches=1)
        assert any(e["node_id"] == "unique_node" for e in entries_1)

    def test_unbound_branches_still_counted(self, db_path: Path):
        """Branches with no goal_id should still contribute to the
        aggregate; their node's goal_ids list just stays empty for
        that contribution.
        """
        from workflow.daemon_server import goal_common_nodes_all

        shared = {"node_id": "shared", "display_name": "S"}
        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "bound", [shared], goal_id="goal-a",
        ))
        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "unbound", [shared], goal_id=None,
        ))
        entries = goal_common_nodes_all(db_path, min_branches=2)
        shared_entry = next(
            (e for e in entries if e["node_id"] == "shared"), None,
        )
        assert shared_entry is not None
        assert shared_entry["occurrence_count"] == 2
        assert shared_entry["goal_ids"] == ["goal-a"]


class TestSearchNodes:
    """Free-text search across every Branch's NodeDefinitions for #62."""

    def test_empty_query_returns_all_nodes(self, db_path: Path):
        from workflow.daemon_server import search_nodes

        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "b1", [{"node_id": "alpha"}, {"node_id": "beta"}],
        ))
        results = search_nodes(db_path, query="", limit=10)
        ids = {r["node_id"] for r in results}
        assert {"alpha", "beta"}.issubset(ids)

    def test_query_ranks_matching_over_non_matching(self, db_path: Path):
        from workflow.daemon_server import search_nodes

        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "b1", [
                {"node_id": "rigor_checker",
                 "display_name": "Rigor Checker",
                 "description": "Audits citations for rigor"},
                {"node_id": "unrelated",
                 "display_name": "Unrelated",
                 "description": "Unrelated work"},
            ],
        ))
        results = search_nodes(db_path, query="rigor", limit=10)
        # rigor_checker must come first; unrelated must not appear at
        # all because it has zero substring hits.
        assert results[0]["node_id"] == "rigor_checker"
        assert not any(r["node_id"] == "unrelated" for r in results)

    def test_reuse_count_counts_distinct_branches(self, db_path: Path):
        from workflow.daemon_server import search_nodes

        rigor = {"node_id": "rigor_checker", "display_name": "Rigor Checker"}
        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "research", [rigor], goal_id="goal-research",
        ))
        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "legal", [rigor], goal_id="goal-legal",
        ))
        results = search_nodes(db_path, query="rigor", limit=10)
        entry = next(r for r in results if r["node_id"] == "rigor_checker")
        assert entry["reuse_count"] == 2
        assert set(entry["goal_ids"]) == {"goal-research", "goal-legal"}

    def test_role_filter_restricts_by_phase(self, db_path: Path):
        from workflow.daemon_server import search_nodes

        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "b1", [
                {"node_id": "draft_one", "display_name": "D1", "phase": "draft"},
                {"node_id": "reflect_one", "display_name": "R1", "phase": "reflect"},
            ],
        ))
        results = search_nodes(db_path, query="", role="reflect", limit=10)
        ids = {r["node_id"] for r in results}
        assert ids == {"reflect_one"}

    def test_prompt_template_preview_truncates(self, db_path: Path):
        from workflow.daemon_server import search_nodes

        long_template = "x " * 500  # 1000 chars of whitespace-separated x
        save_branch_definition(db_path, branch_def=_branch_with_nodes(
            "b1", [{
                "node_id": "verbose",
                "display_name": "Verbose",
                "prompt_template": long_template,
            }],
        ))
        results = search_nodes(db_path, query="verbose", limit=5)
        entry = next(r for r in results if r["node_id"] == "verbose")
        preview = entry["prompt_template_preview"]
        assert len(preview) <= 160
        assert preview.endswith("…")
