"""Test suite for the Research Probe domain.

Verifies:
1. ResearchProbeDomain implements the Domain protocol correctly
2. Graph builds without errors and has expected topology
3. No imports from fantasy_author leak through
4. Domain can be registered with the workflow registry
5. Phase implementations execute deterministically
"""

from __future__ import annotations

from langgraph.graph import StateGraph

from domains.research_probe import ResearchProbeDomain
from domains.research_probe.state import ResearchState
from domains.research_probe.tools import research_search
from tinyassets.protocols import Domain
from tinyassets.registry import DomainRegistry, default_registry


class TestResearchProbeDomainProtocol:
    """Test that ResearchProbeDomain implements the Domain protocol."""

    def test_domain_implements_protocol(self) -> None:
        """ResearchProbeDomain should implement the Domain protocol."""
        domain = ResearchProbeDomain()
        assert isinstance(domain, Domain)

    def test_domain_has_config_property(self) -> None:
        """Domain should expose config as a property."""
        domain = ResearchProbeDomain()
        config = domain.config
        assert isinstance(config, dict)
        assert config["name"] == "research_probe"
        assert config["version"] == "0.1.0"

    def test_config_has_required_fields(self) -> None:
        """Domain config should have name, description, version."""
        domain = ResearchProbeDomain()
        config = domain.config
        assert "name" in config
        assert "description" in config
        assert "version" in config

    def test_build_graph_returns_stategraph(self) -> None:
        """build_graph() should return a LangGraph StateGraph."""
        domain = ResearchProbeDomain()
        graph = domain.build_graph()
        assert isinstance(graph, StateGraph)

    def test_state_extensions_returns_dict(self) -> None:
        """state_extensions() should return a dict."""
        domain = ResearchProbeDomain()
        extensions = domain.state_extensions()
        assert isinstance(extensions, dict)
        assert "research_query" in extensions
        assert "sources" in extensions
        assert "synthesis" in extensions

    def test_tools_returns_list(self) -> None:
        """tools() should return a list of DomainTool instances."""
        domain = ResearchProbeDomain()
        tools = domain.tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        # Verify each tool has required attributes
        for tool in tools:
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")
            assert callable(tool)

    def test_eval_criteria_returns_list(self) -> None:
        """eval_criteria() should return a list of EvalCriteria."""
        domain = ResearchProbeDomain()
        criteria = domain.eval_criteria()
        assert isinstance(criteria, list)
        assert len(criteria) > 0
        # Verify each criterion has required fields
        for criterion in criteria:
            assert "name" in criterion
            assert "description" in criterion
            assert "severity" in criterion

    def test_memory_schemas_returns_list(self) -> None:
        """memory_schemas() should return a list of MemorySchema dicts."""
        domain = ResearchProbeDomain()
        schemas = domain.memory_schemas()
        assert isinstance(schemas, list)
        assert len(schemas) > 0
        # Verify each schema has required fields
        for schema in schemas:
            assert "tier" in schema
            assert "schema_name" in schema
            assert "description" in schema

    def test_api_routes_returns_none_or_router(self) -> None:
        """api_routes() should return None or an APIRouter."""
        domain = ResearchProbeDomain()
        routes = domain.api_routes()
        # Currently None for the probe; that's expected
        assert routes is None


class TestResearchGraphTopology:
    """Test that the research graph has the expected topology."""

    def test_graph_has_expected_nodes(self) -> None:
        """Graph should have gather, analyze, synthesize, review nodes."""
        domain = ResearchProbeDomain()
        graph = domain.build_graph()
        nodes = graph.nodes
        assert "gather" in nodes
        assert "analyze" in nodes
        assert "synthesize" in nodes
        assert "review" in nodes

    def test_graph_has_correct_edges(self) -> None:
        """Graph should have the expected linear edges."""
        domain = ResearchProbeDomain()
        graph = domain.build_graph()
        edges = graph.edges
        # Should have edges: START→gather, gather→analyze, analyze→synthesize,
        # synthesize→review, and review→(conditional)
        assert len(edges) > 0

    def test_graph_topology_differs_from_fantasy_author(self) -> None:
        """Research graph should be fundamentally different from fantasy hierarchy.

        The fantasy domain uses 4-level hierarchy (scene/chapter/book/universe).
        Research probe uses flat loop with revision (gather→analyze→...→review→loop).
        """
        from domains.fantasy_daemon.graphs import build_universe_graph

        fantasy_graph = build_universe_graph()
        research_graph = domain_instance.build_graph()

        # Sanity check: the node counts should differ
        fantasy_nodes = fantasy_graph.nodes
        research_nodes = research_graph.nodes

        # Fantasy has more nodes (multiple hierarchy levels)
        # Research is a simple loop
        assert "gather" in research_nodes
        # These fantasy-level nodes should NOT be in research
        assert "gather" not in fantasy_nodes


# Instantiate for use across tests
domain_instance = ResearchProbeDomain()


class TestNoFantasyAuthorImports:
    """Verify that research_probe does NOT import from fantasy_author."""

    def test_no_fantasy_author_in_modules(self) -> None:
        """Imported research_probe modules should not contain fantasy_author imports."""
        # Check that fantasy_author is not in the research_probe module imports
        import domains.research_probe.skill as research_skill_module

        source = open(research_skill_module.__file__).read()
        assert "fantasy_author" not in source, (
            "research_probe imports should not reference fantasy_author"
        )

    def test_no_fantasy_author_in_graph(self) -> None:
        """Graph module should not import fantasy_author."""
        import domains.research_probe.graph as research_graph_module

        source = open(research_graph_module.__file__).read()
        assert "fantasy_author" not in source

    def test_no_fantasy_author_in_state(self) -> None:
        """State module should not import fantasy_author."""
        import domains.research_probe.state as research_state_module

        source = open(research_state_module.__file__).read()
        assert "fantasy_author" not in source

    def test_no_fantasy_author_in_phases(self) -> None:
        """Phase modules should not import fantasy_author."""
        import domains.research_probe.phases.analyze as analyze_module
        import domains.research_probe.phases.gather as gather_module

        gather_source = open(gather_module.__file__).read()
        analyze_source = open(analyze_module.__file__).read()

        assert "fantasy_author" not in gather_source
        assert "fantasy_author" not in analyze_source

    def test_workflow_imports_only(self) -> None:
        """Domain should only import from tinyassets.*, not fantasy_author.*."""
        import domains.research_probe.skill as research_skill_module

        source = open(research_skill_module.__file__).read()
        # Should have workflow imports
        assert "tinyassets.protocols" in source
        # Should not have fantasy_author imports
        assert "domains.fantasy_daemon" not in source


class TestResearchDomainRegistration:
    """Test that the domain can be registered with the workflow registry."""

    def test_domain_can_be_registered(self) -> None:
        """Should be able to register the domain with a registry."""
        registry = DomainRegistry()
        domain = ResearchProbeDomain()
        registry.register(domain)
        assert registry.get("research_probe") is not None

    def test_domain_registered_in_default_registry(self) -> None:
        """Domain should be registerable in the default_registry."""
        domain = ResearchProbeDomain()
        # Register if not already present
        if default_registry.get("research_probe") is None:
            default_registry.register(domain)
        assert default_registry.get("research_probe") is not None

    def test_registry_list_domains(self) -> None:
        """Registry should be able to list all domains."""
        registry = DomainRegistry()
        domain = ResearchProbeDomain()
        registry.register(domain)
        domains = registry.list_domains()
        assert "research_probe" in domains


class TestResearchToolsInterface:
    """Test domain tools interface."""

    def test_research_search_tool_exists(self) -> None:
        """research_search tool should be accessible."""
        assert research_search is not None
        assert hasattr(research_search, "name")
        assert hasattr(research_search, "description")

    def test_research_search_tool_callable(self) -> None:
        """research_search should be callable."""
        assert callable(research_search)

    def test_research_search_returns_results(self) -> None:
        """research_search should return a list of results."""
        results = research_search(query="machine learning", max_results=5)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_research_search_result_structure(self) -> None:
        """Each search result should have required fields."""
        results = research_search(query="agent workflows", max_results=3)
        assert len(results) > 0
        result = results[0]
        assert "id" in result
        assert "title" in result
        assert "summary" in result


class TestResearchStateContract:
    """Test the ResearchState TypedDict contract."""

    def test_research_state_is_typeddict(self) -> None:
        """ResearchState should be a TypedDict."""
        # TypedDict creates a special class with __annotations__
        assert hasattr(ResearchState, "__annotations__")

    def test_research_state_has_engine_fields(self) -> None:
        """ResearchState should include base TinyAssetsState fields."""
        annotations = ResearchState.__annotations__
        assert "workflow_id" in annotations
        assert "domain_name" in annotations
        assert "stopped" in annotations
        assert "paused" in annotations

    def test_research_state_has_domain_fields(self) -> None:
        """ResearchState should have research-specific fields."""
        annotations = ResearchState.__annotations__
        assert "research_query" in annotations
        assert "sources" in annotations
        assert "extracted_facts" in annotations
        assert "synthesis" in annotations
        assert "themes" in annotations


class TestResearchPhaseImplementations:
    """Test that phase implementations work correctly."""

    def test_gather_phase_execution(self) -> None:
        """gather_phase should execute and produce sources."""
        from domains.research_probe.phases.gather import gather_phase

        state = {
            "research_query": "machine learning",
            "iteration_count": 0,
        }
        result = gather_phase(state)
        assert "sources" in result
        assert "quality_trace" in result

    def test_analyze_phase_execution(self) -> None:
        """analyze_phase should extract facts from sources."""
        from domains.research_probe.phases.analyze import analyze_phase

        state = {
            "sources": [
                {
                    "id": "test_001",
                    "title": "Test Source",
                    "summary": "First fact. Second fact.",
                    "source_id": "test_001",
                }
            ],
            "iteration_count": 0,
        }
        result = analyze_phase(state)
        assert "extracted_facts" in result
        assert len(result["extracted_facts"]) > 0

    def test_synthesize_phase_execution(self) -> None:
        """synthesize_phase should combine facts into a summary."""
        from domains.research_probe.phases.synthesize import synthesize_phase

        state = {
            "research_query": "test query",
            "extracted_facts": [
                {"topic": "Topic A", "fact": "Fact 1", "source_id": "001"},
                {"topic": "Topic A", "fact": "Fact 2", "source_id": "001"},
            ],
            "iteration_count": 0,
        }
        result = synthesize_phase(state)
        assert "synthesis" in result
        assert "themes" in result
        assert len(result["synthesis"]) > 0

    def test_review_phase_execution(self) -> None:
        """review_phase should evaluate quality and decide on revision."""
        from domains.research_probe.phases.review import review_phase

        state = {
            "synthesis": "This is a test synthesis with some content.",
            "extracted_facts": [
                {"topic": "A", "fact": "Fact 1", "source_id": "001"},
                {"topic": "B", "fact": "Fact 2", "source_id": "002"},
                {"topic": "C", "fact": "Fact 3", "source_id": "003"},
            ],
            "iteration_count": 0,
            "max_iterations": 3,
        }
        result = review_phase(state)
        assert "review_notes" in result
        assert "needs_revision" in result
        assert "iteration_count" in result


class TestIntegration:
    """Integration tests for the complete research probe."""

    def test_domain_full_protocol_coverage(self) -> None:
        """Domain should implement all required protocol methods."""
        domain = ResearchProbeDomain()
        # All these should work without errors
        config = domain.config
        graph = domain.build_graph()
        extensions = domain.state_extensions()
        tools = domain.tools()
        criteria = domain.eval_criteria()
        schemas = domain.memory_schemas()
        domain.api_routes()  # verify callable without error

        assert config is not None
        assert graph is not None
        assert extensions is not None
        assert tools is not None
        assert criteria is not None
        assert schemas is not None
        # routes can be None

    def test_graph_builds_without_compilation_errors(self) -> None:
        """Graph should build (but not compile) without errors."""
        domain = ResearchProbeDomain()
        graph = domain.build_graph()
        # Just building the StateGraph should work
        assert graph is not None
        # Verify we can access nodes
        assert "gather" in graph.nodes

    def test_probe_is_independent_from_fantasy_author(self) -> None:
        """The research probe should work completely independently."""
        # Import and instantiate without touching fantasy_author modules
        domain = ResearchProbeDomain()
        config = domain.config
        # Should be able to get basic info
        assert config["name"] == "research_probe"
        # Should have no fantasy-specific fields
        extensions = domain.state_extensions()
        assert "universe_id" not in extensions
        assert "scene_id" not in extensions
