"""Tests for the scene-attempt counter + force-accept plateau-escape gate.

Task #63. Implements §5.1 of the Sporemarch C16-S3 diagnostic: the
chapter-level guard that the scene-level one-revise cap cannot
provide because the scene subgraph re-enters with
``second_draft_used=False`` on every dispatch.

Tests cover:
- bump_scene_attempt_count: persists + increments correctly.
- max_scene_attempts: env-var override, default fallback.
- advance_work_target_on_accept: resets the counter to 0.
- run_scene: force-accepts when counter reaches threshold, emits
  `[dispatch_guard]` tagged activity_log entry, advances work_target.
- run_scene: normal path when counter below threshold (scene graph
  still runs).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from domains.fantasy_daemon.graphs.chapter import run_scene
from domains.fantasy_daemon.phases.target_actions import (
    MAX_SCENE_ATTEMPTS_DEFAULT,
    advance_work_target_on_accept,
    bump_scene_attempt_count,
    max_scene_attempts,
)

# -------------------------------------------------------------------
# Helpers — minimal WorkTarget persistence fixture
# -------------------------------------------------------------------


def _write_universe(tmp_path: Path, universe_id: str = "test-universe") -> Path:
    udir = tmp_path / universe_id
    udir.mkdir()
    (udir / "universe.json").write_text(
        json.dumps({
            "id": universe_id,
            "name": "Test Universe",
            "created_at": "2026-04-19T00:00:00Z",
        }),
        encoding="utf-8",
    )
    return udir


def _make_target(
    universe_dir: Path,
    target_id: str = "tgt-1",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write a WorkTarget via the real tinyassets.work_targets API."""
    from tinyassets.work_targets import WorkTarget, save_work_targets

    t = WorkTarget(
        target_id=target_id,
        title="Test",
        role="write",
        metadata=dict(metadata or {}),
    )
    save_work_targets(universe_dir, [t])


def _read_target(universe_dir: Path, target_id: str):
    from tinyassets.work_targets import get_target

    return get_target(universe_dir, target_id)


# -------------------------------------------------------------------
# bump_scene_attempt_count
# -------------------------------------------------------------------


def test_bump_first_call_returns_one(tmp_path):
    udir = _write_universe(tmp_path)
    _make_target(udir)

    result = bump_scene_attempt_count(str(udir), "tgt-1")

    assert result == 1
    t = _read_target(udir, "tgt-1")
    assert t.metadata["scene_attempt_count"] == 1


def test_bump_increments_successive_calls(tmp_path):
    udir = _write_universe(tmp_path)
    _make_target(udir)

    assert bump_scene_attempt_count(str(udir), "tgt-1") == 1
    assert bump_scene_attempt_count(str(udir), "tgt-1") == 2
    assert bump_scene_attempt_count(str(udir), "tgt-1") == 3


def test_bump_missing_target_returns_zero(tmp_path):
    udir = _write_universe(tmp_path)
    # No target written.

    result = bump_scene_attempt_count(str(udir), "nonexistent")

    assert result == 0


def test_bump_empty_universe_path_returns_zero():
    assert bump_scene_attempt_count("", "tgt-1") == 0


def test_bump_empty_target_id_returns_zero(tmp_path):
    udir = _write_universe(tmp_path)
    assert bump_scene_attempt_count(str(udir), None) == 0


def test_bump_handles_corrupt_counter_as_zero(tmp_path):
    """A metadata.scene_attempt_count='garbage' value is treated as 0."""
    udir = _write_universe(tmp_path)
    _make_target(udir, metadata={"scene_attempt_count": "not-a-number"})

    result = bump_scene_attempt_count(str(udir), "tgt-1")

    assert result == 1
    assert _read_target(udir, "tgt-1").metadata["scene_attempt_count"] == 1


# -------------------------------------------------------------------
# max_scene_attempts — env override
# -------------------------------------------------------------------


def test_max_scene_attempts_default():
    # Clear any env override for this test.
    os.environ.pop("TINYASSETS_MAX_SCENE_ATTEMPTS", None)
    assert max_scene_attempts() == MAX_SCENE_ATTEMPTS_DEFAULT
    assert MAX_SCENE_ATTEMPTS_DEFAULT == 3


def test_max_scene_attempts_env_override(monkeypatch):
    monkeypatch.setenv("TINYASSETS_MAX_SCENE_ATTEMPTS", "7")
    assert max_scene_attempts() == 7


def test_max_scene_attempts_rejects_zero_or_negative(monkeypatch):
    """A zero/negative value falls back to default — never 0 (infinite)."""
    monkeypatch.setenv("TINYASSETS_MAX_SCENE_ATTEMPTS", "0")
    assert max_scene_attempts() == MAX_SCENE_ATTEMPTS_DEFAULT
    monkeypatch.setenv("TINYASSETS_MAX_SCENE_ATTEMPTS", "-5")
    assert max_scene_attempts() == MAX_SCENE_ATTEMPTS_DEFAULT


def test_max_scene_attempts_rejects_garbage(monkeypatch):
    monkeypatch.setenv("TINYASSETS_MAX_SCENE_ATTEMPTS", "not-a-number")
    assert max_scene_attempts() == MAX_SCENE_ATTEMPTS_DEFAULT


# -------------------------------------------------------------------
# advance_work_target_on_accept resets the counter
# -------------------------------------------------------------------


def test_advance_on_accept_resets_counter(tmp_path):
    """The accept path must zero scene_attempt_count so the next scene
    starts with a fresh budget."""
    udir = _write_universe(tmp_path)
    _make_target(udir, metadata={
        "scene_number": 5,
        "scene_attempt_count": 2,
    })

    trace = advance_work_target_on_accept(
        str(udir), "tgt-1",
        verdict="accept",
        execution_scope={"execution_kind": "scene", "scene_number": 5},
    )

    assert trace is not None
    t = _read_target(udir, "tgt-1")
    assert t.metadata["scene_number"] == 6
    assert t.metadata["scene_attempt_count"] == 0


def test_advance_on_accept_no_counter_noop_on_field(tmp_path):
    """If the target has no counter yet, advance doesn't spuriously add one."""
    udir = _write_universe(tmp_path)
    _make_target(udir, metadata={"scene_number": 5})

    advance_work_target_on_accept(
        str(udir), "tgt-1",
        verdict="accept",
        execution_scope={"execution_kind": "scene", "scene_number": 5},
    )

    t = _read_target(udir, "tgt-1")
    # Counter field not added unless it was there to begin with — keeps
    # the metadata shape clean for universes that never plateaued.
    assert "scene_attempt_count" not in t.metadata


# -------------------------------------------------------------------
# run_scene force-accept integration
# -------------------------------------------------------------------


def test_run_scene_force_accepts_at_threshold(tmp_path, monkeypatch):
    """When scene_attempt_count has reached max, run_scene short-circuits
    with a force-accept and emits a [dispatch_guard] tagged log entry."""
    udir = _write_universe(tmp_path, "sporemarch")
    _make_target(udir, metadata={"scene_number": 3, "scene_attempt_count": 2})

    # Patch build_scene_graph so a failure here confirms short-circuit
    # (if the function is called, the test fails).
    called: list[str] = []

    def _never_build():
        called.append("scene_graph_built")
        raise AssertionError("scene graph must not build when force-accepting")

    import domains.fantasy_daemon.graphs.chapter as chapter_mod
    monkeypatch.setattr(
        "domains.fantasy_daemon.graphs.scene.build_scene_graph", _never_build,
    )

    # Stub _activity_log so we can capture the tagged entry without
    # touching the real universe directory's activity.log.
    logged: list[tuple[str, str]] = []

    def _capture_log(state, message, tag=""):
        logged.append((message, tag))

    monkeypatch.setattr(chapter_mod, "_activity_log", _capture_log)

    state = {
        "_universe_path": str(udir),
        "book_number": 1,
        "chapter_number": 16,
        "scenes_completed": 2,  # → scene_num = 3
        "chapter_word_count": 0,
        "workflow_instructions": {
            "selected_target_id": "tgt-1",
            "execution_scope": {"execution_kind": "scene", "scene_number": 3},
        },
    }

    # Counter is currently 2; bump inside run_scene → 3 → force-accept.
    result = run_scene(state)

    # Assert scene graph was NOT built.
    assert "scene_graph_built" not in called

    # Assert scenes_completed advanced.
    assert result["scenes_completed"] == 3
    # Assert quality_trace shows the plateau-escape action.
    traces = result.get("quality_trace", [])
    assert any(
        t.get("action") == "force_accept_plateau_escape" for t in traces
    ), f"quality_trace should flag force_accept; got {traces!r}"

    # Assert the tagged log entry was emitted.
    tagged = [(msg, tag) for msg, tag in logged if tag == "dispatch_guard"]
    assert len(tagged) == 1, f"expected 1 dispatch_guard log; got {logged!r}"
    msg, _ = tagged[0]
    assert "force_accept" in msg
    assert "attempts=3" in msg
    assert "plateau_escape" in msg
    assert "sporemarch-B1-C16-S3" in msg

    # Assert counter was reset to 0 by advance_work_target_on_accept.
    t = _read_target(udir, "tgt-1")
    assert t.metadata["scene_attempt_count"] == 0
    # Scene number advanced past the plateau.
    assert t.metadata["scene_number"] == 4


def test_run_scene_does_not_force_accept_below_threshold(
    tmp_path, monkeypatch,
):
    """Counter at 1 (below threshold of 3) → scene graph runs normally."""
    from domains.fantasy_daemon.graphs import chapter as chapter_mod

    udir = _write_universe(tmp_path, "testuniverse")
    _make_target(udir, metadata={"scene_number": 1, "scene_attempt_count": 0})

    # Stub build_scene_graph to a shape that returns quickly with an
    # accept verdict — we only want to confirm it WAS called.
    called: list[str] = []

    class _FakeCompiled:
        def invoke(self, scene_state):
            return {
                "draft_output": {"prose": "x", "word_count": 1},
                "verdict": "accept",
                "extracted_facts": [],
            }

    def _fake_build():
        called.append("built")

        class _Wrap:
            def compile(self):
                return _FakeCompiled()

        return _Wrap()

    monkeypatch.setattr(
        "domains.fantasy_daemon.graphs.scene.build_scene_graph", _fake_build,
    )
    monkeypatch.setattr(chapter_mod, "_activity_log", lambda *a, **k: None)

    state = {
        "universe_id": "testuniverse",
        "_universe_path": str(udir),
        "book_number": 1,
        "chapter_number": 1,
        "scenes_completed": 0,
        "chapter_word_count": 0,
        "workflow_instructions": {
            "selected_target_id": "tgt-1",
            "execution_scope": {"execution_kind": "scene", "scene_number": 1},
        },
    }

    result = run_scene(state)

    assert "built" in called  # scene graph DID run.
    # Should not carry plateau-escape trace.
    traces = result.get("quality_trace") or []
    assert not any(
        t.get("action") == "force_accept_plateau_escape" for t in traces
    )


# -------------------------------------------------------------------
# Regression guard — chapter.py actually invokes the counter
# -------------------------------------------------------------------


def test_chapter_run_scene_references_counter_helpers():
    """Guard against a future refactor removing the counter call."""
    source = Path(
        "domains/fantasy_daemon/graphs/chapter.py"
    ).read_text(encoding="utf-8")
    assert "bump_scene_attempt_count" in source, (
        "run_scene must call bump_scene_attempt_count (Task #63)"
    )
    assert "max_scene_attempts" in source, (
        "run_scene must check max_scene_attempts (Task #63)"
    )
    assert "force_accept_plateau_escape" in source, (
        "force-accept trace action must be emitted (Task #63)"
    )
