"""Runtime singletons for non-serializable objects.

LangGraph's checkpointer serializes the full state dict via msgpack.
Objects like MemoryManager, OutputVersionStore, and SeriesPromiseTracker
are not serializable. Instead of storing them in graph state, they live
here as module-level references that DaemonController sets before
starting the graph and nodes read at execution time.

Universe isolation invariant
----------------------------
Every singleton here (``knowledge_graph``, ``vector_store``, ``raptor_tree``,
``memory_manager``, ``embed_fn``, ``universe_config``) is **bound to exactly
one universe** at daemon startup. These singletons are the hot retrieval
path for the writer and carry no ``universe_id`` filter of their own —
isolation is entirely path- and binding-based.

Therefore: **never swap universes in-process without calling ``reset()``
first.** The current daemon design enforces this via
``DaemonController._cleanup()`` → ``runtime.reset()`` on universe switch
(a new process is spawned to bind the next universe). If a future caller
mutates these singletons to point at a second universe without a reset,
the writer will be fed cross-universe retrieval hits and produce
wrong-universe content.

Historical note: pre-2026-04-11 leaks of Ashwater content into
``default-universe/canon/`` (see STATUS.md #47/#48) are attributable to
this class of invariant violation under the old architecture. The
current hard-refuse guards on ``KnowledgeGraph`` and ``VectorStore``
empty-path construction (see #51) plus per-universe ``db_path`` threading
close the file-level half; ``reset()`` on switch closes the in-memory half.
"""

from __future__ import annotations

from typing import Any, Callable

from tinyassets.config import UniverseConfig

# Set by DaemonController.start() before graph execution begins.
memory_manager: Any | None = None
version_store: Any | None = None
promise_tracker: Any | None = None

# Retrieval backends (set by DaemonController.start())
knowledge_graph: Any | None = None
vector_store: Any | None = None
raptor_tree: Any | None = None
embed_fn: Callable[[str], list[float]] | None = None

# Per-universe configuration (loaded from config.yaml)
universe_config: UniverseConfig = UniverseConfig()


def reset() -> None:
    """Clear all runtime references (used in tests and shutdown).

    MUST be called before re-binding these singletons to a different
    universe. See the module docstring's "Universe isolation invariant"
    section for why.
    """
    global memory_manager, version_store, promise_tracker
    global knowledge_graph, vector_store, raptor_tree, embed_fn
    global universe_config
    memory_manager = None
    version_store = None
    promise_tracker = None
    knowledge_graph = None
    vector_store = None
    raptor_tree = None
    embed_fn = None
    universe_config = UniverseConfig()
