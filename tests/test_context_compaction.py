"""Tests for tinyassets.context.compaction module."""

import tempfile
import time
from pathlib import Path

import pytest

from tinyassets.context.compaction import (
    CompactionService,
    HandoffArtifact,
    HandoffStore,
)


class TestHandoffArtifact:
    """Tests for HandoffArtifact dataclass."""

    def test_create_artifact(self):
        """Test creating a basic artifact."""
        artifact = HandoffArtifact(
            source_phase="scene",
            target_phase="chapter",
            scope={"universe_id": "test"},
            content={"summary": "Test summary"},
            token_count=42,
        )

        assert artifact.source_phase == "scene"
        assert artifact.target_phase == "chapter"
        assert artifact.scope["universe_id"] == "test"
        assert artifact.content["summary"] == "Test summary"
        assert artifact.token_count == 42
        assert artifact.artifact_id  # Should have a UUID
        assert artifact.created_at  # Should have timestamp

    def test_artifact_to_dict(self):
        """Test serializing artifact to dict."""
        artifact = HandoffArtifact(
            artifact_id="test-id",
            source_phase="scene",
            target_phase="chapter",
            scope={"universe_id": "test"},
            content={"summary": "Test"},
            token_count=10,
        )

        data = artifact.to_dict()
        assert data["artifact_id"] == "test-id"
        assert data["source_phase"] == "scene"
        assert isinstance(data["content"], dict)

    def test_artifact_from_dict(self):
        """Test deserializing artifact from dict."""
        data = {
            "artifact_id": "test-123",
            "source_phase": "chapter",
            "target_phase": "book",
            "created_at": "2026-04-06T10:00:00Z",
            "scope": {"universe_id": "u1"},
            "content": {"key_facts": ["fact1", "fact2"]},
            "token_count": 50,
            "metadata": {"tag": "test"},
        }

        artifact = HandoffArtifact.from_dict(data)
        assert artifact.artifact_id == "test-123"
        assert artifact.source_phase == "chapter"
        assert artifact.scope["universe_id"] == "u1"
        assert len(artifact.content["key_facts"]) == 2

    def test_artifact_roundtrip(self):
        """Test dict serialization roundtrip."""
        original = HandoffArtifact(
            artifact_id="trip-test",
            source_phase="book",
            target_phase="universe",
            scope={"universe_id": "u1", "branch_id": "b1"},
            content={"summary": "Test", "key_facts": ["a", "b"]},
            token_count=100,
            metadata={"custom": "data"},
        )

        data = original.to_dict()
        restored = HandoffArtifact.from_dict(data)

        assert restored.artifact_id == original.artifact_id
        assert restored.source_phase == original.source_phase
        assert restored.target_phase == original.target_phase
        assert restored.scope == original.scope
        assert restored.content == original.content
        assert restored.token_count == original.token_count
        assert restored.metadata == original.metadata


class TestCompactionService:
    """Tests for CompactionService."""

    def test_compact_phase_output_basic(self):
        """Test compacting basic phase output."""
        service = CompactionService()

        phase_output = {
            "summary": "A test scene summary",
            "key_facts": ["Fact 1", "Fact 2", "Fact 3"],
            "open_threads": ["Thread A"],
            "quality_notes": "Scene was well-written",
        }

        artifact = service.compact_phase_output(
            phase_output=phase_output,
            source_phase="scene",
            target_phase="chapter",
            scope={"universe_id": "test"},
        )

        assert artifact.source_phase == "scene"
        assert artifact.target_phase == "chapter"
        assert "summary" in artifact.content
        assert "key_facts" in artifact.content
        assert artifact.token_count > 0

    def test_compact_phase_output_large_facts(self):
        """Test that large fact lists are truncated."""
        service = CompactionService()

        # Create a large fact list
        facts = [f"Fact {i}" for i in range(50)]

        phase_output = {"key_facts": facts}

        artifact = service.compact_phase_output(
            phase_output=phase_output,
            source_phase="chapter",
            target_phase="book",
            scope={"universe_id": "test"},
        )

        # Should truncate to 10 facts
        assert len(artifact.content["key_facts"]) == 10

    def test_compact_tool_result_no_truncation(self):
        """Test that small tool results pass through."""
        service = CompactionService()

        result = "This is a short result"
        truncated = service.compact_tool_result(
            tool_name="test_tool",
            raw_result=result,
            max_tokens=1000,
        )

        assert truncated == result
        assert "[truncated]" not in truncated

    def test_compact_tool_result_with_truncation(self):
        """Test that large tool results are truncated."""
        service = CompactionService()

        result = "A" * 5000  # Very large result

        truncated = service.compact_tool_result(
            tool_name="test_tool",
            raw_result=result,
            max_tokens=100,
        )

        assert len(truncated) < len(result)
        assert "[truncated]" in truncated

    def test_merge_handoff_artifacts_empty_raises(self):
        """Test that merging empty list raises error."""
        service = CompactionService()

        with pytest.raises(ValueError):
            service.merge_handoff_artifacts([])

    def test_merge_handoff_artifacts_deduplicates_facts(self):
        """Test that merging deduplicates key facts."""
        service = CompactionService()

        artifact1 = HandoffArtifact(
            source_phase="scene",
            target_phase="chapter",
            scope={"universe_id": "test"},
            content={"key_facts": ["Fact A", "Fact B"]},
        )

        artifact2 = HandoffArtifact(
            source_phase="scene",
            target_phase="chapter",
            scope={"universe_id": "test"},
            content={"key_facts": ["Fact B", "Fact C"]},
        )

        merged = service.merge_handoff_artifacts([artifact1, artifact2])

        # Should have 3 unique facts, deduplicated
        assert "Fact A" in merged.content["key_facts"]
        assert "Fact C" in merged.content["key_facts"]
        assert len(merged.content["key_facts"]) == 3

    def test_merge_handoff_artifacts_respects_budget(self):
        """Test that merged artifact respects token budget."""
        service = CompactionService()

        # Create multiple large artifacts
        artifacts = [
            HandoffArtifact(
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "test"},
                content={"summary": "A" * 2000},
            )
            for _ in range(5)
        ]

        merged = service.merge_handoff_artifacts(artifacts, max_tokens=1000)

        # Merged token count should be <= budget
        assert merged.token_count <= 1000 + 100  # Allow small margin

    def test_truncate_text_basic(self):
        """Test basic text truncation."""
        service = CompactionService()

        text = "This is a test. It has multiple sentences. More text here."
        truncated = service._truncate_text(text, 20)

        assert len(truncated) <= 20 + 10
        assert "[...]" in truncated

    def test_truncate_text_preserves_short(self):
        """Test that short text is preserved."""
        service = CompactionService()

        text = "Short"
        truncated = service._truncate_text(text, 100)

        assert truncated == text


class TestHandoffStore:
    """Tests for HandoffStore."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = HandoffStore(db_path)

            artifact = HandoffArtifact(
                artifact_id="test-1",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                content={"summary": "Test"},
                token_count=10,
            )

            store.store(artifact)

            retrieved = store.retrieve(
                source_phase="scene", scope={"universe_id": "u1"}
            )

            assert len(retrieved) == 1
            assert retrieved[0].artifact_id == "test-1"
            assert retrieved[0].content["summary"] == "Test"

    def test_retrieve_latest(self):
        """Test retrieving most recent artifact."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = HandoffStore(db_path)

            # Create two artifacts with different timestamps
            art1 = HandoffArtifact(
                artifact_id="old",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                created_at="2026-04-05T10:00:00Z",
                content={"summary": "Old"},
            )

            art2 = HandoffArtifact(
                artifact_id="new",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                created_at="2026-04-06T10:00:00Z",
                content={"summary": "New"},
            )

            store.store(art1)
            store.store(art2)

            latest = store.retrieve_latest(
                source_phase="scene", scope={"universe_id": "u1"}
            )

            assert latest is not None
            assert latest.artifact_id == "new"

    def test_retrieve_scope_filtering(self):
        """Test that retrieval filters by scope."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = HandoffStore(db_path)

            # Store artifacts in different universes
            art_u1 = HandoffArtifact(
                artifact_id="u1-art",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                content={"summary": "U1"},
            )

            art_u2 = HandoffArtifact(
                artifact_id="u2-art",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u2"},
                content={"summary": "U2"},
            )

            store.store(art_u1)
            store.store(art_u2)

            # Retrieve only from u1
            retrieved = store.retrieve(
                source_phase="scene", scope={"universe_id": "u1"}
            )

            assert len(retrieved) == 1
            assert retrieved[0].scope["universe_id"] == "u1"

    def test_prune_removes_old_artifacts(self):
        """Test that prune removes old artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = HandoffStore(db_path)

            # Store an old artifact
            old_artifact = HandoffArtifact(
                artifact_id="old",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                created_at="2026-01-01T10:00:00Z",
                content={"summary": "Old"},
            )

            # Store a new artifact
            new_artifact = HandoffArtifact(
                artifact_id="new",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                created_at="2026-04-06T10:00:00Z",
                content={"summary": "New"},
            )

            store.store(old_artifact)
            store.store(new_artifact)

            # Prune artifacts before 2026-04-01
            count = store.prune("2026-04-01T00:00:00Z")

            assert count == 1

            # Verify old artifact is gone
            retrieved = store.retrieve(
                source_phase="scene", scope={"universe_id": "u1"}
            )
            assert len(retrieved) == 1
            assert retrieved[0].artifact_id == "new"

    def test_prune_with_unix_timestamp(self):
        """Test pruning with Unix timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            store = HandoffStore(db_path)

            artifact = HandoffArtifact(
                artifact_id="test",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                content={"summary": "Test"},
            )

            store.store(artifact)

            # Prune from far in the future
            future_time = time.time() + (365 * 24 * 3600)
            count = store.prune(future_time)

            assert count == 1

    def test_db_persistence(self):
        """Test that data persists across store instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create first store and add data
            store1 = HandoffStore(db_path)
            artifact = HandoffArtifact(
                artifact_id="persist-test",
                source_phase="scene",
                target_phase="chapter",
                scope={"universe_id": "u1"},
                content={"summary": "Persist"},
            )
            store1.store(artifact)

            # Create second store instance with same db path
            store2 = HandoffStore(db_path)
            retrieved = store2.retrieve(
                source_phase="scene", scope={"universe_id": "u1"}
            )

            assert len(retrieved) == 1
            assert retrieved[0].artifact_id == "persist-test"
