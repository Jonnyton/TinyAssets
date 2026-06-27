"""Engine-domain interface protocols.

Defines the contract between the shared TinyAssets engine infrastructure
and domain implementations. TinyAssets is the first domain to
implement these protocols.

These are deliberately minimal — designed from one domain, expected to
evolve when a second domain pressures the interface.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from typing_extensions import TypedDict

# ============================================================================
# Tool Interface
# ============================================================================


@runtime_checkable
class DomainTool(Protocol):
    """A tool available to domain graph nodes.

    Tools are callable with keyword arguments and return any result type.
    Standard LangGraph tool interface.
    """

    name: str
    """Tool identifier used in node implementations."""

    description: str
    """One-line description for model context and discovery."""

    def __call__(self, **kwargs: Any) -> Any:
        """Execute the tool with keyword arguments."""
        ...


# ============================================================================
# Evaluation Interface
# ============================================================================


class EvalCriteria(TypedDict, total=False):
    """Domain-specific evaluation criteria.

    Each criterion represents a testable assertion about quality,
    correctness, or coherence.
    """

    name: str
    """Criterion identifier."""

    description: str
    """What this criterion checks."""

    check_fn: Callable[[Any], bool | str]
    """Function that checks the criterion. Returns True/False or a message."""

    severity: str
    """How much to weight this check: 'error' | 'warning' | 'info'."""


# ============================================================================
# State Interface
# ============================================================================


class TinyAssetsState(TypedDict, total=False):
    """Base engine state shared by all domains.

    Domains extend this with their own fields via state_extensions().
    Contains only infrastructure concerns: identity, health, control,
    and artifact references. Domain-specific fields are added via
    TypedDict inheritance and merged at graph build time.

    All fields are optional (total=False) to allow flexible domain
    extensions.
    """

    # --------
    # Identity
    # --------
    workflow_id: str
    """Unique identifier for this workflow run."""

    domain_name: str
    """Name of the domain."""

    # --------
    # Health and control
    # --------
    stopped: bool
    """Flag set by user or daemon to halt execution."""

    paused: bool
    """Flag set by user to pause execution without stopping."""

    health: dict[str, Any]
    """Domain-level health snapshot: status, errors, warnings, metrics."""

    # --------
    # Artifact references
    # --------
    checkpoint_ref: str | None
    """Reference to the latest checkpoint artifact."""

    last_artifact_ref: str | None
    """Reference to the most recent output artifact."""

    # --------
    # Quality and tracing
    # --------
    quality_trace: list[dict[str, Any]]
    """Trace of quality checks, evaluations, and decision points."""

    # --------
    # Shared infrastructure
    # --------
    notes_ref: str | None
    """Reference to the unified notes store for this tinyassets."""

    work_targets_ref: str | None
    """Reference to the durable work target registry."""


class DomainStateExtension(TypedDict, total=False):
    """Marker base for domain-specific state extensions.

    Domains should create a TypedDict that includes this and adds
    their own fields. The protocol does not enforce field names
    because each domain's state shape is unique.
    """

    pass


# ============================================================================
# Configuration Interface
# ============================================================================


class DomainConfig(TypedDict, total=False):
    """Domain registration metadata.

    Passed to the engine at registration time to identify and configure
    a domain.
    """

    name: str
    """Domain name (e.g., 'workflow'). Used as a unique key."""

    description: str
    """One-line description of what this domain does."""

    version: str
    """Domain version (e.g., '0.1.0'). Used for compatibility tracking."""

    default_config: dict[str, Any]
    """Default configuration merged with user overrides."""


# ============================================================================
# Phase Implementation Interface
# ============================================================================


class PhaseImplementation(Protocol):
    """A single phase node in a domain's graph.

    This is a standard LangGraph node signature: accepts a state dict,
    returns a partial state update dict. The engine will merge returned
    updates into the full graph state.
    """

    def __call__(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """Execute one phase step.

        Args:
            state: Current workflow state (merged domain + engine fields).

        Returns:
            Partial state update dict, or None if no state changes.
        """
        ...


# ============================================================================
# Memory Interface
# ============================================================================


class MemorySchema(TypedDict, total=False):
    """Domain-specific memory schema definition.

    Describes how a domain stores and retrieves information across
    episodes, sessions, or long time horizons.
    """

    tier: str
    """Which memory tier: 'core' | 'episodic' | 'archival' | custom."""

    schema_name: str
    """Name of this memory schema (e.g., 'narrative_facts', 'character_arcs')."""

    description: str
    """What this memory stores."""

    fields: dict[str, str]
    """Field names and types (informal; for documentation)."""


# ============================================================================
# Domain Interface
# ============================================================================


@runtime_checkable
class Domain(Protocol):
    """Main protocol a domain module must implement.

    A domain provides its own graph topology (LangGraph StateGraph),
    state extensions (TypedDict additions), tools, eval criteria,
    memory schemas, and optional API routes.

    The engine calls these methods during registration and startup.
    The domain does not have access to engine internals; it works
    through the tool/note/memory interfaces exposed by the engine.
    """

    # --------
    # Metadata
    # --------

    @property
    def config(self) -> DomainConfig:
        """Return metadata about this domain.

        Used by the engine to register and identify the domain.
        """
        ...

    # --------
    # Graph
    # --------

    def build_graph(self) -> Any:
        """Return an uncompiled LangGraph StateGraph.

        The domain owns its topology entirely. The engine provides
        infrastructure (providers, memory, checkpointing, notes) but
        does not dictate graph shape.

        Returns:
            A LangGraph StateGraph with no compiled runtime (the engine
            will add checkpointing and compile).

        Expected structure (from TinyAssets):
            StateGraph(state=DomainState)
                .add_node('phase1', phase1_impl)
                .add_node('phase2', phase2_impl)
                .add_edge('phase1', 'phase2')
                .add_edge('START', 'phase1')
                .add_edge('phase2', 'END')
        """
        ...

    # --------
    # State
    # --------

    def state_extensions(self) -> dict[str, type]:
        """Return TypedDict field definitions to merge into base engine state.

        These extend the base TinyAssetsState with domain-specific fields.

        Returns:
            Dict mapping field name to field type (e.g., {'scene_id': str}).
            The engine will merge these into the full state schema before
            graph compilation.

        Expected (from TinyAssets):
            {
                'universe_id': str,
                'active_series': str | None,
                'series_completed': list,
                'selected_target_id': str | None,
                'universal_style_rules': list,
                'quality_trace': Annotated[list, operator.add],
                # ... more domain fields
            }
        """
        ...

    # --------
    # Tools
    # --------

    def tools(self) -> list[DomainTool]:
        """Return domain-specific tools available to graph nodes.

        These are made available during graph execution. The engine
        may also provide shared tools (e.g., logging, checkpointing).

        Returns:
            List of tools with name, description, and __call__ method.

        Expected (from TinyAssets):
            [
                story_search,     # Retrieve canon, KG, notes
                canon_query,      # Direct fact lookup
                world_state_set,  # Assert new world facts
                # ... more domain tools
            ]
        """
        ...

    # --------
    # Evaluation
    # --------

    def eval_criteria(self) -> list[EvalCriteria]:
        """Return domain-specific evaluation criteria.

        Used by evaluator nodes to check quality, correctness,
        and coherence.

        Returns:
            List of EvalCriteria dicts.

        Expected (from TinyAssets):
            [
                {
                    'name': 'scene_coherence',
                    'description': 'Scene events follow logically from state',
                    'check_fn': lambda output: check_coherence(output),
                    'severity': 'warning',
                },
                # ... more criteria
            ]
        """
        ...

    # --------
    # Memory
    # --------

    def memory_schemas(self) -> list[MemorySchema]:
        """Return domain-specific memory schema definitions.

        Describes how the domain stores and retrieves information.

        Returns:
            List of MemorySchema dicts describing storage patterns.

        Expected (from TinyAssets):
            [
                {
                    'tier': 'episodic',
                    'schema_name': 'scene_outputs',
                    'description': 'Scene drafts and editorial feedback',
                    'fields': {'scene_id': 'str', 'draft': 'str', 'notes': 'list'},
                },
                # ... more schemas
            ]
        """
        ...

    # --------
    # API routes (optional)
    # --------

    def api_routes(self) -> Any | None:
        """Return a FastAPI APIRouter with domain-specific routes, or None.

        If the domain exposes HTTP endpoints, return a configured
        APIRouter. The engine will mount these under /api/domain/<name>/.

        Returns:
            A FastAPI APIRouter, or None if no routes are needed.

        Expected (from TinyAssets):
            APIRouter()
                .get('/status')(get_status_handler)
                .post('/note')(post_note_handler)
                .get('/universe/{universe_id}')(get_universe_handler)
                # ... more routes
        """
        ...


# ============================================================================
# Registry Interface
# ============================================================================


class DomainRegistry(Protocol):
    """Optional: Interface for discovering and registering domains.

    The engine may use a registry to load domains at startup or
    dynamically. This is a convenience interface; domains can also
    be registered directly via explicit imports.
    """

    def register(self, domain: Domain) -> None:
        """Register a domain with the engine."""
        ...

    def get(self, name: str) -> Domain | None:
        """Look up a domain by name."""
        ...

    def list_domains(self) -> list[str]:
        """Return names of all registered domains."""
        ...
