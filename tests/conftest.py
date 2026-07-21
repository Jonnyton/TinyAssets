"""Shared fixtures for TinyAssets tests.

Provides checkpointer, compiled graphs, and default state dicts
that all test modules can reuse.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

# Force mock provider responses in all tests to avoid real API calls
from tinyassets.providers import call as _provider_call

_provider_call.set_force_mock(True)


@pytest.fixture(autouse=True)
def _reset_runtime():
    """Clear runtime singletons before AND after every test to prevent leakage.

    The pre-test reset catches cases where a prior test's background thread
    (e.g. LangGraph executor) sets the global after the prior test's teardown.
    """
    from tinyassets import runtime_singletons as runtime

    runtime.reset()
    yield
    runtime.reset()


@pytest.fixture(autouse=True)
def _isolate_storage_backend(monkeypatch):
    """Pin the storage backend to ``sqlite_only`` by default for every test.

    Phase 7 Rationale: the module-global :class:`SqliteCachedBackend`
    anchors to ``Path.cwd()`` on first use and, once cached, keeps
    writing to the real repo ``branches/`` / ``goals/`` / ``nodes/``
    directories even when later tests point ``TINYASSETS_DATA_DIR``
    at a tmp dir. That causes (a) pollution of the working tree and
    (b) spurious ``DirtyFileError`` as tests fight over the same
    slug paths.

    Tests that explicitly exercise the cached backend (git-enabled
    path, YAML serialization, commit granularity) override this by
    re-setting the env var via their own ``monkeypatch``. See
    ``tests/test_storage_phase7_backend.py`` and future ``test_phase7_h3_*``.
    """
    monkeypatch.setenv("TINYASSETS_STORAGE_BACKEND", "sqlite_only")
    from tinyassets import catalog as _catalog

    _catalog.invalidate_backend_cache()
    yield
    _catalog.invalidate_backend_cache()


@pytest.fixture
def checkpointer():
    """Yield an in-memory SqliteSaver for testing.

    Uses the ``from_conn_string`` context manager pattern.
    """
    with SqliteSaver.from_conn_string(":memory:") as cp:
        yield cp


@pytest.fixture
def tmp_story_db():
    """Create a temp story.db path for world state, cleaned up after test."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="story_test_")
    os.close(fd)
    os.unlink(path)  # Remove so init_db creates fresh
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def scene_input(tmp_story_db) -> dict[str, Any]:
    """Minimal valid input for the Scene graph."""
    return {
        "universe_id": "test-universe",
        "book_number": 1,
        "chapter_number": 1,
        "scene_number": 1,
        "orient_result": {},
        "retrieved_context": {},
        "recent_prose": "",
        "workflow_instructions": {},
        "memory_context": {},
        "search_context": {},
        "plan_output": None,
        "draft_output": None,
        "commit_result": None,
        "editorial_notes": None,
        "second_draft_used": False,
        "verdict": "",
        "extracted_facts": [],
        "extracted_promises": [],
        "style_observations": [],
        "quality_trace": [],
        "quality_debt": [],
        "_universe_path": "",
        "_db_path": tmp_story_db,
        "_kg_path": "",
    }


@pytest.fixture
def chapter_input() -> dict[str, Any]:
    """Minimal valid input for the Chapter graph."""
    return {
        "universe_id": "test-universe",
        "book_number": 1,
        "chapter_number": 1,
        "scenes_completed": 0,
        "scenes_target": 2,
        "chapter_summary": None,
        "consolidated_facts": [],
        "quality_trend": {},
        "chapter_arc": {},
        "style_rules_observed": [],
        "craft_cards_generated": [],
    }


@pytest.fixture
def book_input() -> dict[str, Any]:
    """Minimal valid input for the Book graph."""
    return {
        "universe_id": "test-universe",
        "book_number": 1,
        "chapters_completed": 0,
        "chapters_target": 1,
        "book_summary": None,
        "book_arc": {},
        "health": {"stuck_level": 0},
        "cross_book_promises_active": [],
        "quality_trace": [],
    }


@pytest.fixture
def universe_input() -> dict[str, Any]:
    """Minimal valid input for the Universe graph."""
    return {
        "universe_id": "test-universe",
        "universe_path": "/tmp/test-universe",
        "review_stage": "foundation",
        "active_series": None,
        "series_completed": [],
        "selected_target_id": None,
        "selected_intent": None,
        "alternate_target_ids": [],
        "current_task": None,
        "current_execution_id": None,
        "current_execution_ref": None,
        "last_review_artifact_ref": None,
        "work_targets_ref": "work_targets.json",
        "hard_priorities_ref": "hard_priorities.json",
        "timeline_ref": None,
        "soft_conflicts": [],
        "world_state_version": 0,
        "canon_facts_count": 0,
        "total_words": 0,
        "total_chapters": 0,
        "health": {},
        "task_queue": ["write"],
        "universal_style_rules": [],
        "cross_series_facts": [],
        "quality_trace": [],
    }


@pytest.fixture()
def platform_vault_env(tmp_path, monkeypatch):
    """Isolated platform credential-vault environment (S5 seam tests).

    Provides: a tmp data root (``TINYASSETS_DATA_DIR``), a per-test
    anti-rollback guard, and an in-memory KEK provider monkeypatched over
    ``credential_broker.platform_key_provider`` (FileKeyProvider's root-only
    POSIX custody gates cannot be satisfied by an unprivileged test run).
    Yields the data root; universes live directly under it.
    """
    import nacl.bindings as sodium

    from tinyassets import credential_broker
    from tinyassets.credentials import InMemoryKeyProvider

    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))
    monkeypatch.setenv(
        "TINYASSETS_VAULT_ROLLBACK_GUARD", str(tmp_path / "_vault_guard")
    )
    monkeypatch.delenv("TINYASSETS_VAULT_KEK_DIR", raising=False)
    monkeypatch.delenv("TINYASSETS_VAULT_ACTIVE_KEY_ID", raising=False)
    keys = InMemoryKeyProvider({"k1": sodium.randombytes(32)}, "k1")
    monkeypatch.setattr(
        credential_broker, "platform_key_provider", lambda: keys
    )
    credential_broker._reset_backend_cache()
    yield data_root
    credential_broker._reset_backend_cache()
