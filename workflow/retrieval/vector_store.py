"""LanceDB vector store -- singleton connection, pre-computed embeddings.

The connection is created once and reused everywhere.  Embeddings must
be pre-computed as numpy arrays; LanceDB does not call an embedding
model itself.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import lancedb
import numpy as np

if TYPE_CHECKING:
    from workflow.knowledge.tag_matrix import KnowledgeTags
    from workflow.memory.scoping import MemoryScope

# ---------------------------------------------------------------------------
# Singleton connection
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_db: lancedb.DBConnection | None = None
_db_path: str | None = None


def get_db(path: str = "") -> lancedb.DBConnection:
    """Return the singleton LanceDB connection.

    The first call creates the connection; subsequent calls reuse it.
    Thread-safe via a lock.

    ``path`` must be explicit. CWD-relative defaults cause
    cross-universe contamination: two universes sharing the same
    relative path end up reading and writing each other's vectors.
    Mirror of the guard in
    ``workflow/knowledge/knowledge_graph.py``.
    """
    if not path:
        raise ValueError(
            "get_db requires an explicit path. "
            "CWD-relative defaults cause cross-universe contamination."
        )
    global _db, _db_path
    with _lock:
        if _db is None or _db_path != path:
            Path(path).mkdir(parents=True, exist_ok=True)
            _db = lancedb.connect(path)
            _db_path = path
        return _db


def reset_db() -> None:
    """Reset the singleton (for testing only)."""
    global _db, _db_path
    with _lock:
        _db = None
        _db_path = None


# ---------------------------------------------------------------------------
# VectorStore wrapper
# ---------------------------------------------------------------------------


class VectorStore:
    """High-level wrapper around a LanceDB table for prose chunk storage.

    Parameters
    ----------
    db_path
        Path to the LanceDB directory.
    table_name
        Name of the table to create/open.
    embedding_dim
        Dimension of embedding vectors.
    """

    def __init__(
        self,
        db_path: str = "",
        table_name: str = "prose_chunks",
        embedding_dim: int = 384,
    ) -> None:
        if not db_path:
            raise ValueError(
                "VectorStore requires an explicit db_path. "
                "CWD-relative defaults cause cross-universe contamination."
            )
        self._db = get_db(db_path)
        self._table_name = table_name
        self._embedding_dim = embedding_dim
        self._table: Any = None

    def _ensure_table(self) -> Any:
        """Create or open the table.

        Memory-scope Stage 2a: new tables are seeded with the four
        scope columns (``universe_id``, ``goal_id``, ``branch_id``,
        ``user_id``) so the LanceDB side matches the KG schema shape.
        Existing tables are opened as-is — LanceDB has its own
        column-migration API that the Stage 2b write-site threading
        will invoke when it starts tagging new rows with scope.
        """
        if self._table is not None:
            return self._table

        existing = self._db.list_tables()
        if self._table_name in existing:
            self._table = self._db.open_table(self._table_name)
        else:
            # Create with a seed row (LanceDB requires at least one row)
            seed = [{
                "chunk_id": "__seed__",
                "text": "",
                "scene_id": "",
                "chapter_number": 0,
                "character": "",
                "location": "",
                "universe_id": "",
                "goal_id": "",
                "branch_id": "",
                "user_id": "",
                "tag_universes": "[]",
                "tag_domains": "[]",
                "tag_shapes": "[]",
                "tag_general": 0,
                "tag_commons": 0,
                "tag_private_canon": 0,
                "promotion_record": "",
                "embedding": np.zeros(self._embedding_dim, dtype=np.float32).tolist(),
            }]
            self._table = self._db.create_table(self._table_name, data=seed)
        return self._table

    def index(
        self,
        chunks: Sequence[dict],
        scope: "MemoryScope | None" = None,
        tags: "KnowledgeTags | None" = None,
    ) -> int:
        """Index prose chunks with pre-computed embeddings.

        Each chunk dict must have:
            - chunk_id: str
            - text: str
            - embedding: list[float] or numpy array
            - scene_id: str
            - chapter_number: int
            - character: str (optional)
            - location: str (optional)

        Memory-scope Stage 2b: an optional ``scope`` tags every chunk
        with the caller's tier values. Per-chunk ``universe_id``/
        ``goal_id``/``branch_id``/``user_id`` keys override ``scope``
        when both are supplied (the chunk wins — some callers need
        per-chunk overrides for migration tooling). When neither is
        supplied, scope columns default to the empty string to match
        the Stage 2a LanceDB seed semantic (NULL-equivalent for
        LanceDB's string-typed columns).

        Returns the number of chunks indexed.
        """
        table = self._ensure_table()
        if not chunks:
            return 0

        # Stage 2b: resolve the fallback scope values once, not per chunk.
        if scope is not None:
            scope_defaults = {
                "universe_id": scope.universe_id,
                "goal_id": scope.goal_id or "",
                "branch_id": scope.branch_id or "",
                "user_id": scope.user_id or "",
            }
        else:
            scope_defaults = {
                "universe_id": "", "goal_id": "",
                "branch_id": "", "user_id": "",
            }
        tag_defaults = tags.as_row_metadata() if tags is not None else {
            "tag_universes": "[]",
            "tag_domains": "[]",
            "tag_shapes": "[]",
            "tag_general": 0,
            "tag_commons": 0,
            "tag_private_canon": 0,
            "promotion_record": "",
        }

        rows = []
        for chunk in chunks:
            emb = chunk["embedding"]
            if isinstance(emb, np.ndarray):
                emb = emb.tolist()
            rows.append({
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "scene_id": chunk.get("scene_id", ""),
                "chapter_number": chunk.get("chapter_number", 0),
                "character": chunk.get("character", ""),
                "location": chunk.get("location", ""),
                # Memory-scope Stage 2b: per-chunk overrides take
                # precedence, then ``scope`` tier values, then empty
                # string (Stage 2a seed default).
                "universe_id": chunk.get("universe_id", scope_defaults["universe_id"]),
                "goal_id": chunk.get("goal_id", scope_defaults["goal_id"]),
                "branch_id": chunk.get("branch_id", scope_defaults["branch_id"]),
                "user_id": chunk.get("user_id", scope_defaults["user_id"]),
                "tag_universes": chunk.get(
                    "tag_universes", tag_defaults["tag_universes"],
                ),
                "tag_domains": chunk.get(
                    "tag_domains", tag_defaults["tag_domains"],
                ),
                "tag_shapes": chunk.get(
                    "tag_shapes", tag_defaults["tag_shapes"],
                ),
                "tag_general": chunk.get(
                    "tag_general", tag_defaults["tag_general"],
                ),
                "tag_commons": chunk.get(
                    "tag_commons", tag_defaults["tag_commons"],
                ),
                "tag_private_canon": chunk.get(
                    "tag_private_canon", tag_defaults["tag_private_canon"],
                ),
                "promotion_record": chunk.get(
                    "promotion_record", tag_defaults["promotion_record"],
                ),
                "embedding": emb,
            })

        table.add(rows)
        return len(rows)

    def search(
        self,
        embedding: list[float] | np.ndarray,
        limit: int = 5,
        where: str | None = None,
    ) -> list[dict]:
        """Search for similar prose chunks.

        Parameters
        ----------
        embedding
            Query embedding vector (pre-computed).
        limit
            Maximum results.
        where
            Optional SQL WHERE clause for filtering.

        Returns
        -------
        list[dict]
            Matching chunks with text, metadata, and ``_distance``.
        """
        table = self._ensure_table()
        if isinstance(embedding, np.ndarray):
            embedding = embedding.tolist()

        query = table.search(embedding).limit(limit)
        if where:
            query = query.where(where)

        results = query.to_list()
        # Filter out seed rows
        return [r for r in results if r.get("chunk_id") != "__seed__"]

    def count(self) -> int:
        """Return number of rows (excluding seed)."""
        table = self._ensure_table()
        total = len(table)
        return max(0, total - 1)  # Subtract seed row
