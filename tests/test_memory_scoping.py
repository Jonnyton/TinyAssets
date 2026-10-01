"""Tests for ``tinyassets.memory.scoping``.

Covers the Stage 2b 5-tier orthogonal-composition model: ``MemoryScope``,
``NodeScope``, ``SliceSpec``, ``ExternalSource``, ``ScopedQuery``,
``ScopeResolver``, ``ScopedMemoryRouter``.
"""

from __future__ import annotations

import pytest

from tinyassets.memory.scoping import (
    ExternalSource,
    MemoryScope,
    NodeScope,
    ScopedMemoryRouter,
    ScopedQuery,
    ScopeResolver,
    SliceSpec,
)

# =====================================================================
# SliceSpec + ExternalSource + NodeScope
# =====================================================================


class TestSliceSpec:
    def test_defaults_are_none(self):
        spec = SliceSpec()
        assert spec.entity_ids is None
        assert spec.relation_types is None
        assert spec.document_ids is None

    def test_carries_explicit_fields(self):
        spec = SliceSpec(
            entity_ids=["ryn", "kael"],
            relation_types=["ally_of"],
            document_ids=["doc-1"],
        )
        assert spec.entity_ids == ["ryn", "kael"]
        assert spec.relation_types == ["ally_of"]
        assert spec.document_ids == ["doc-1"]


class TestExternalSource:
    def test_kind_enum_members(self):
        # The four kinds locked by design §9.3 Q5.
        for kind in ("universe", "external_api", "system_tool", "cross_universe_join"):
            src = ExternalSource(kind=kind, identifier="x")
            assert src.kind == kind

    def test_identifier_is_opaque(self):
        src = ExternalSource(kind="external_api", identifier="arxiv")
        assert src.identifier == "arxiv"


class TestNodeScope:
    def test_default_is_universe_member_full_canon(self):
        ns = NodeScope()
        assert ns.universe_member is True
        assert ns.breadth == "full_canon"
        assert ns.slice_spec is None
        assert ns.external_sources is None

    def test_narrow_slice_requires_slice_spec(self):
        with pytest.raises(ValueError, match="narrow_slice.*slice_spec"):
            NodeScope(breadth="narrow_slice")

    def test_narrow_slice_with_spec_ok(self):
        ns = NodeScope(
            breadth="narrow_slice",
            slice_spec=SliceSpec(entity_ids=["ryn"]),
        )
        assert ns.breadth == "narrow_slice"
        assert ns.slice_spec.entity_ids == ["ryn"]

    def test_non_member_requires_external_sources(self):
        with pytest.raises(ValueError, match="external_sources"):
            NodeScope(universe_member=False)

    def test_non_member_with_sources_ok(self):
        ns = NodeScope(
            universe_member=False,
            external_sources=[ExternalSource(kind="external_api", identifier="arxiv")],
        )
        assert ns.universe_member is False
        assert len(ns.external_sources) == 1


# =====================================================================
# MemoryScope
# =====================================================================


class TestMemoryScope:
    def test_universal_scope(self):
        scope = MemoryScope(universe_id="world")
        assert scope.universe_id == "world"
        assert scope.goal_id is None
        assert scope.branch_id is None
        assert scope.user_id is None
        assert scope.node_scope is None

    def test_full_tier_construction(self):
        scope = MemoryScope(
            universe_id="world",
            goal_id="book-1",
            branch_id="main",
            user_id="alice",
            node_scope=NodeScope(),
        )
        assert scope.goal_id == "book-1"
        assert scope.branch_id == "main"
        assert scope.user_id == "alice"
        assert scope.node_scope is not None

    def test_compose_predicate_omits_none_tiers(self):
        scope = MemoryScope(universe_id="world", branch_id="main")
        pred = scope.compose_predicate()
        assert pred == {"universe_id": "world", "branch_id": "main"}

    def test_compose_predicate_all_tiers(self):
        scope = MemoryScope(
            universe_id="world",
            goal_id="book-1",
            branch_id="main",
            user_id="alice",
        )
        pred = scope.compose_predicate()
        assert pred == {
            "universe_id": "world",
            "goal_id": "book-1",
            "branch_id": "main",
            "user_id": "alice",
        }

    def test_compose_predicate_never_includes_node_scope(self):
        # node_scope is a structural attribute; it's not part of the
        # row-level predicate (that's in the slice_spec layer).
        scope = MemoryScope(universe_id="world", node_scope=NodeScope())
        pred = scope.compose_predicate()
        assert "node_scope" not in pred

    def test_to_filter_dict_alias(self):
        scope = MemoryScope(universe_id="world", branch_id="main")
        assert scope.to_filter_dict() == scope.compose_predicate()

    def test_with_overrides_replaces_tier(self):
        scope = MemoryScope(universe_id="world", branch_id="main")
        narrower = scope.with_overrides(goal_id="book-1")
        assert narrower.universe_id == "world"
        assert narrower.branch_id == "main"
        assert narrower.goal_id == "book-1"

    def test_with_overrides_can_clear_tier(self):
        scope = MemoryScope(universe_id="world", branch_id="main")
        cleared = scope.with_overrides(branch_id=None)
        assert cleared.branch_id is None

    def test_with_overrides_rejects_universe_id(self):
        scope = MemoryScope(universe_id="world")
        with pytest.raises(ValueError, match="universe_id is invariant"):
            scope.with_overrides(universe_id="other")

    def test_is_frozen(self):
        scope = MemoryScope(universe_id="world")
        with pytest.raises(Exception):  # FrozenInstanceError is dataclasses-internal
            scope.universe_id = "other"  # type: ignore[misc]


# =====================================================================
# ScopedQuery
# =====================================================================


class TestScopedQuery:
    def test_minimal_query(self):
        scope = MemoryScope(universe_id="world")
        query = ScopedQuery(scope=scope)
        assert query.scope == scope
        assert query.query_text is None
        assert query.max_results == 50

    def test_full_query(self):
        scope = MemoryScope(universe_id="world", branch_id="main")
        query = ScopedQuery(
            scope=scope,
            query_text="What happened to Ryn?",
            entity="Ryn",
            attribute="history",
            time_range=("2025-01-01", "2025-12-31"),
            include_superseded=True,
            max_results=20,
            tiers=["episodic", "archival"],
        )
        assert query.entity == "Ryn"
        assert query.max_results == 20
        assert query.tiers == ["episodic", "archival"]


# =====================================================================
# ScopeResolver
# =====================================================================


class TestScopeResolver:
    def test_compose_read_predicate_matches_scope(self):
        resolver = ScopeResolver()
        scope = MemoryScope(universe_id="world", branch_id="main")
        assert resolver.compose_read_predicate(scope) == scope.compose_predicate()

    def test_can_write_same_scope(self):
        resolver = ScopeResolver()
        scope = MemoryScope(universe_id="world", branch_id="main")
        assert resolver.can_write(scope, scope)

    def test_can_write_universe_only_caller_to_any_subscope(self):
        # Design intent: an unpinned caller at universe level can write
        # rows tagged at any sub-scope of that universe.
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world")
        target_branch = MemoryScope(universe_id="world", branch_id="main")
        target_goal = MemoryScope(universe_id="world", goal_id="book-1")
        target_user = MemoryScope(universe_id="world", user_id="alice")
        assert resolver.can_write(target_branch, caller)
        assert resolver.can_write(target_goal, caller)
        assert resolver.can_write(target_user, caller)

    def test_pinned_branch_caller_cannot_write_other_branch(self):
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world", branch_id="main")
        target = MemoryScope(universe_id="world", branch_id="dev")
        assert not resolver.can_write(target, caller)

    def test_pinned_branch_caller_cannot_write_null_branch(self):
        # A pinned branch caller also can't write broader-than-its-pin
        # rows — their writes must stay inside their branch.
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world", branch_id="main")
        target = MemoryScope(universe_id="world")
        assert not resolver.can_write(target, caller)

    def test_cross_universe_write_denied(self):
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world-a")
        target = MemoryScope(universe_id="world-b")
        assert not resolver.can_write(target, caller)

    def test_pinned_goal_caller_writes_matching_goal(self):
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world", goal_id="book-1")
        ok = MemoryScope(universe_id="world", goal_id="book-1", branch_id="main")
        bad = MemoryScope(universe_id="world", goal_id="book-2", branch_id="main")
        assert resolver.can_write(ok, caller)
        assert not resolver.can_write(bad, caller)

    def test_pinned_user_caller_cannot_cross_user(self):
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world", user_id="alice")
        target = MemoryScope(universe_id="world", user_id="bob")
        assert not resolver.can_write(target, caller)

    def test_visible_branches_unpinned_caller(self):
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world")
        assert resolver.visible_branches(caller, ["main", "dev", "feature"]) == [
            "main", "dev", "feature",
        ]

    def test_visible_branches_pinned_caller(self):
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world", branch_id="main")
        assert resolver.visible_branches(caller, ["main", "dev"]) == ["main"]

    def test_visible_branches_pinned_caller_missing_branch(self):
        resolver = ScopeResolver()
        caller = MemoryScope(universe_id="world", branch_id="ghost")
        assert resolver.visible_branches(caller, ["main", "dev"]) == []


# =====================================================================
# ScopedMemoryRouter
# =====================================================================


class TestScopedMemoryRouter:
    def test_router_initializes(self):
        mock_manager = type("MockManager", (), {})()
        router = ScopedMemoryRouter(mock_manager)
        assert router._manager is mock_manager

    def test_router_query_returns_list(self):
        mock_manager = type("MockManager", (), {})()
        router = ScopedMemoryRouter(mock_manager)
        query = ScopedQuery(scope=MemoryScope(universe_id="world"))
        result = router.query(query)
        assert isinstance(result, list)

    def test_router_store_accepts_data_and_scope(self):
        mock_manager = type("MockManager", (), {})()
        router = ScopedMemoryRouter(mock_manager)
        scope = MemoryScope(universe_id="world", branch_id="main")
        router.store({"fact_id": "f1", "text": "Ryn is a scout"}, scope)


# =====================================================================
# Agent-controlled memory tools (unchanged by Stage 2b; still exercised
# here so the tools entry points stay covered alongside the scope tests)
# =====================================================================
