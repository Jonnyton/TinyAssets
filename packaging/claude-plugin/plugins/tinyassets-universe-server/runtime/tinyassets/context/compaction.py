"""Compaction services and durable handoff artifacts.

Produces structured summaries at phase/level boundaries for context
compression and handoff between phases. HandoffArtifacts are durable records
that carry compressed phase outputs forward to consuming phases, reducing
token load while preserving decision-critical information.

Compaction is progressive: simple extraction and truncation now, LLM-driven
synthesis later.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HandoffArtifact:
    """A durable summary produced at phase/level boundaries.

    Attributes
    ----------
    artifact_id : str
        Unique identifier (UUID).
    source_phase : str
        The phase that produced this artifact (e.g., 'scene', 'chapter',
        'book').
    target_phase : str
        The phase that will consume this artifact.
    created_at : str
        ISO 8601 timestamp when artifact was created.
    scope : dict[str, Any]
        Scope metadata: universe_id, branch_id, author_id, etc.
    content : dict[str, Any]
        Compressed content with keys like 'summary', 'key_facts',
        'open_threads', 'quality_notes', 'emotional_beats'.
    token_count : int
        Estimated token count of serialized content.
    metadata : dict[str, Any]
        Optional domain-specific metadata.
    """

    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_phase: str = ""
    target_phase: str = ""
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    scope: dict[str, Any] = field(default_factory=dict)
    content: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HandoffArtifact:
        """Deserialize from dict."""
        return cls(
            artifact_id=data.get("artifact_id", str(uuid.uuid4())),
            source_phase=data.get("source_phase", ""),
            target_phase=data.get("target_phase", ""),
            created_at=data.get(
                "created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ")
            ),
            scope=data.get("scope", {}),
            content=data.get("content", {}),
            token_count=data.get("token_count", 0),
            metadata=data.get("metadata", {}),
        )


class CompactionService:
    """Compresses phase outputs into durable handoff artifacts.

    Uses structured extraction (no LLM calls required). Future versions can
    add LLM-driven synthesis for richer summaries.
    """

    def __init__(self, max_summary_tokens: int = 500) -> None:
        """Initialize the service.

        Parameters
        ----------
        max_summary_tokens : int, optional
            Default token budget for summaries (default: 500).
        """
        self._max_summary_tokens = max_summary_tokens

    def compact_phase_output(
        self,
        phase_output: dict[str, Any],
        source_phase: str,
        target_phase: str,
        scope: dict[str, Any],
        max_tokens: int | None = None,
    ) -> HandoffArtifact:
        """Create a handoff artifact from raw phase output.

        Parameters
        ----------
        phase_output : dict[str, Any]
            Raw output from a phase (scene, chapter, book, etc.).
        source_phase : str
            Name of the source phase.
        target_phase : str
            Name of the consuming phase.
        scope : dict[str, Any]
            Scope metadata (universe_id, branch_id, etc.).
        max_tokens : int, optional
            Token budget for content. Defaults to instance default.

        Returns
        -------
        HandoffArtifact
            Compressed artifact ready for handoff.
        """
        if max_tokens is None:
            max_tokens = self._max_summary_tokens

        content: dict[str, Any] = {}

        # Extract standard keys if present, truncating as needed
        if "summary" in phase_output:
            content["summary"] = self._truncate_text(
                phase_output["summary"], max_tokens // 2
            )

        if "key_facts" in phase_output:
            if isinstance(phase_output["key_facts"], list):
                content["key_facts"] = phase_output["key_facts"][:10]
            else:
                content["key_facts"] = [phase_output["key_facts"]]

        if "open_threads" in phase_output:
            if isinstance(phase_output["open_threads"], list):
                content["open_threads"] = phase_output["open_threads"][:5]
            else:
                content["open_threads"] = [phase_output["open_threads"]]

        if "quality_notes" in phase_output:
            content["quality_notes"] = self._truncate_text(
                phase_output["quality_notes"], max_tokens // 4
            )

        if "emotional_beats" in phase_output:
            if isinstance(phase_output["emotional_beats"], list):
                content["emotional_beats"] = phase_output["emotional_beats"][:8]
            else:
                content["emotional_beats"] = [phase_output["emotional_beats"]]

        # Estimate token count (rough: ~4 chars per token)
        content_str = json.dumps(content)
        token_count = len(content_str) // 4

        artifact = HandoffArtifact(
            source_phase=source_phase,
            target_phase=target_phase,
            scope=scope,
            content=content,
            token_count=token_count,
        )

        return artifact

    def compact_tool_result(self, tool_name: str, raw_result: str, max_tokens: int = 500) -> str:
        """Truncate/summarize a tool result to fit token budget.

        Parameters
        ----------
        tool_name : str
            Name of the tool (for logging/context).
        raw_result : str
            Raw result string from tool.
        max_tokens : int, optional
            Token budget (default: 500).

        Returns
        -------
        str
            Truncated result with '[truncated]' marker if needed.
        """
        max_chars = max_tokens * 4
        if len(raw_result) <= max_chars:
            return raw_result

        logger.info(
            "Truncating tool result from %s: %d -> %d chars",
            tool_name,
            len(raw_result),
            max_chars,
        )

        # Try to truncate at sentence boundary
        truncated = raw_result[:max_chars]
        last_period = truncated.rfind(".")
        if last_period > max_chars * 0.8:  # Found period in last 20% of budget
            truncated = truncated[:last_period + 1]

        return truncated + " [truncated]"

    def merge_handoff_artifacts(
        self, artifacts: list[HandoffArtifact], max_tokens: int = 4000
    ) -> HandoffArtifact:
        """Merge multiple artifacts into one.

        Deduplicates facts and combines summaries while respecting token
        budget.

        Parameters
        ----------
        artifacts : list[HandoffArtifact]
            List of artifacts to merge.
        max_tokens : int, optional
            Token budget for merged artifact (default: 4000).

        Returns
        -------
        HandoffArtifact
            Merged artifact.

        Raises
        ------
        ValueError
            If artifacts list is empty.
        """
        if not artifacts:
            raise ValueError("Cannot merge empty artifacts list")

        # Use first artifact as template
        first = artifacts[0]
        merged_content: dict[str, Any] = {}

        # Merge summaries
        summaries = []
        for art in artifacts:
            if "summary" in art.content and art.content["summary"]:
                summaries.append(art.content["summary"])
        if summaries:
            merged_content["summary"] = " ".join(summaries)

        # Merge and deduplicate facts
        all_facts: set[str] = set()
        for art in artifacts:
            if "key_facts" in art.content:
                facts = art.content["key_facts"]
                if isinstance(facts, list):
                    all_facts.update(str(f) for f in facts if f)
                elif facts:
                    all_facts.add(str(facts))
        if all_facts:
            merged_content["key_facts"] = sorted(list(all_facts))[:20]

        # Merge open threads
        all_threads: set[str] = set()
        for art in artifacts:
            if "open_threads" in art.content:
                threads = art.content["open_threads"]
                if isinstance(threads, list):
                    all_threads.update(str(t) for t in threads if t)
                elif threads:
                    all_threads.add(str(threads))
        if all_threads:
            merged_content["open_threads"] = sorted(list(all_threads))[:10]

        # Merge quality notes
        quality_notes = []
        for art in artifacts:
            if "quality_notes" in art.content and art.content["quality_notes"]:
                quality_notes.append(art.content["quality_notes"])
        if quality_notes:
            merged_content["quality_notes"] = " ".join(quality_notes)

        # Merge emotional beats
        all_beats: set[str] = set()
        for art in artifacts:
            if "emotional_beats" in art.content:
                beats = art.content["emotional_beats"]
                if isinstance(beats, list):
                    all_beats.update(str(b) for b in beats if b)
                elif beats:
                    all_beats.add(str(beats))
        if all_beats:
            merged_content["emotional_beats"] = sorted(list(all_beats))[:15]

        # Truncate to fit budget
        merged_str = json.dumps(merged_content)
        max_chars = max_tokens * 4
        if len(merged_str) > max_chars:
            merged_content = self._truncate_dict(merged_content, max_chars)

        merged = HandoffArtifact(
            source_phase=first.source_phase,
            target_phase=first.target_phase,
            scope=first.scope,
            content=merged_content,
            token_count=len(json.dumps(merged_content)) // 4,
        )

        return merged

    @staticmethod
    def _truncate_text(text: str | None, max_chars: int) -> str:
        """Truncate text to fit character budget.

        Attempts to break at sentence boundary.
        """
        if not text:
            return ""
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        last_period = truncated.rfind(".")
        if last_period > max_chars * 0.8:
            return truncated[:last_period + 1]
        return truncated + "[...]"

    @staticmethod
    def _truncate_dict(data: dict[str, Any], max_chars: int) -> dict[str, Any]:
        """Truncate dict content to fit character budget.

        Removes less important fields first.
        """
        result = {}
        current_size = 0

        # Priority order: summary, key_facts, open_threads, quality_notes, emotional_beats
        priority_keys = ["summary", "key_facts", "open_threads", "quality_notes", "emotional_beats"]

        for key in priority_keys:
            if key not in data:
                continue
            value = data[key]
            value_str = json.dumps({key: value})
            if current_size + len(value_str) <= max_chars:
                result[key] = value
                current_size += len(value_str)
            else:
                # Try to fit what we can of this field
                if isinstance(value, list) and value:
                    # Reduce list size
                    for i in range(len(value), 0, -1):
                        partial_str = json.dumps({key: value[:i]})
                        if current_size + len(partial_str) <= max_chars:
                            result[key] = value[:i]
                            current_size += len(partial_str)
                            break
                break

        return result


class HandoffStore:
    """SQLite-backed storage for handoff artifacts.

    Provides efficient persistence and retrieval of HandoffArtifact instances.
    """

    def __init__(self, db_path: str | Path) -> None:
        """Initialize the store.

        Parameters
        ----------
        db_path : str or Path
            Path to SQLite database file.
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create schema if not exists."""
        # sqlite3.Connection's context manager only commits/rollbacks; on
        # Python 3.12+ it does NOT close the connection, leaving the file
        # handle open until GC. On Windows that breaks tempdir cleanup.
        # Close explicitly via try/finally.
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS handoff_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    source_phase TEXT NOT NULL,
                    target_phase TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    content_json TEXT NOT NULL,
                    token_count INTEGER,
                    metadata_json TEXT,
                    created_at_timestamp REAL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_source_phase ON handoff_artifacts(source_phase)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at "
                "ON handoff_artifacts(created_at_timestamp)"
            )
            conn.commit()
        finally:
            conn.close()

    def store(self, artifact: HandoffArtifact) -> None:
        """Store a handoff artifact.

        Parameters
        ----------
        artifact : HandoffArtifact
            Artifact to store.
        """
        # Derive the timestamp from artifact.created_at so prune() compares
        # against the artifact's logical creation time, not the wall-clock
        # at insert time. Falls back to wall-clock if the ISO string is
        # missing or unparseable.
        try:
            created_ts = time.mktime(
                time.strptime(artifact.created_at, "%Y-%m-%dT%H:%M:%SZ")
            )
        except (TypeError, ValueError):
            created_ts = time.time()

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO handoff_artifacts
                (artifact_id, source_phase, target_phase, created_at, scope_json,
                 content_json, token_count, metadata_json, created_at_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.source_phase,
                    artifact.target_phase,
                    artifact.created_at,
                    json.dumps(artifact.scope),
                    json.dumps(artifact.content),
                    artifact.token_count,
                    json.dumps(artifact.metadata),
                    created_ts,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def retrieve(self, source_phase: str, scope: dict[str, Any]) -> list[HandoffArtifact]:
        """Retrieve artifacts for a given source phase and scope.

        Parameters
        ----------
        source_phase : str
            Source phase to filter on.
        scope : dict[str, Any]
            Scope metadata to match (e.g., universe_id).

        Returns
        -------
        list[HandoffArtifact]
            Matching artifacts, sorted by created_at descending.
        """
        # For simple scope matching, filter in Python
        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                """
                SELECT artifact_id, source_phase, target_phase, created_at,
                       scope_json, content_json, token_count, metadata_json
                FROM handoff_artifacts
                WHERE source_phase = ?
                ORDER BY created_at_timestamp DESC
                """,
                (source_phase,),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        results = []
        scope_universe = scope.get("universe_id")
        for row in rows:
            artifact = self._row_to_artifact(row)
            # Filter by universe_id if provided
            if scope_universe and artifact.scope.get("universe_id") != scope_universe:
                continue
            results.append(artifact)

        return results

    def retrieve_latest(
        self, source_phase: str, scope: dict[str, Any]
    ) -> HandoffArtifact | None:
        """Retrieve the most recent artifact for a phase/scope.

        Parameters
        ----------
        source_phase : str
            Source phase to filter on.
        scope : dict[str, Any]
            Scope metadata (e.g., universe_id).

        Returns
        -------
        HandoffArtifact or None
            Most recent matching artifact, or None if not found.
        """
        artifacts = self.retrieve(source_phase, scope)
        return artifacts[0] if artifacts else None

    def prune(self, before_timestamp: str | float) -> int:
        """Remove artifacts created before a timestamp.

        Parameters
        ----------
        before_timestamp : str or float
            ISO 8601 timestamp string or Unix timestamp.

        Returns
        -------
        int
            Number of artifacts removed.
        """
        if isinstance(before_timestamp, str):
            # Parse ISO 8601
            before_time = time.mktime(time.strptime(before_timestamp, "%Y-%m-%dT%H:%M:%SZ"))
        else:
            before_time = before_timestamp

        conn = sqlite3.connect(self._db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM handoff_artifacts WHERE created_at_timestamp < ?",
                (before_time,),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    @staticmethod
    def _row_to_artifact(row: tuple) -> HandoffArtifact:
        """Convert DB row to HandoffArtifact."""
        (
            artifact_id,
            source_phase,
            target_phase,
            created_at,
            scope_json,
            content_json,
            token_count,
            metadata_json,
        ) = row

        return HandoffArtifact(
            artifact_id=artifact_id,
            source_phase=source_phase,
            target_phase=target_phase,
            created_at=created_at,
            scope=json.loads(scope_json),
            content=json.loads(content_json),
            token_count=token_count or 0,
            metadata=json.loads(metadata_json) if metadata_json else {},
        )
