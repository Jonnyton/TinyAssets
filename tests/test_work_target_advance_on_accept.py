"""Task #33 — Sporemarch oscillation fix (b).

Fix (a) patches the dispatch boundary; fix (b) patches the root cause:
after ``commit`` returns verdict="accept", the originating WorkTarget's
positional metadata (scene_number / chapter_number / book_number) gets
bumped so the next universe cycle picks up a fresh coordinate.
"""

from __future__ import annotations

from pathlib import Path

from domains.fantasy_daemon.phases.target_actions import (
    advance_work_target_on_accept,
)
from tinyassets.work_targets import (
    PUBLISH_STAGE_PROVISIONAL,
    ROLE_PUBLISHABLE,
    WorkTarget,
    get_target,
    upsert_work_target,
)


def _seed_scene_target(
    universe_path: Path,
    *,
    book: int = 1,
    chapter: int = 15,
    scene: int = 3,
    target_id: str = "tgt-scene",
) -> str:
    target = WorkTarget(
        target_id=target_id,
        title=f"Book {book} Chapter {chapter} Scene {scene}",
        role=ROLE_PUBLISHABLE,
        publish_stage=PUBLISH_STAGE_PROVISIONAL,
        tags=["scene"],
        metadata={
            "book_number": book,
            "chapter_number": chapter,
            "scene_number": scene,
            "execution_kind": "scene",
        },
    )
    upsert_work_target(universe_path, target)
    return target.target_id


def test_scene_advance_bumps_scene_number(tmp_path):
    """Scene accept bumps metadata.scene_number by one."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()
    target_id = _seed_scene_target(
        universe_path, book=1, chapter=15, scene=3, target_id="tgt-scene",
    )

    trace = advance_work_target_on_accept(
        str(universe_path),
        target_id,
        verdict="accept",
        execution_scope={
            "execution_kind": "scene",
            "book_number": 1,
            "chapter_number": 15,
            "scene_number": 3,
        },
    )
    assert trace is not None
    assert trace["after"]["scene_number"] == 4

    reloaded = get_target(str(universe_path), target_id)
    assert reloaded is not None
    assert reloaded.metadata["scene_number"] == 4
    assert reloaded.metadata["chapter_number"] == 15


def test_chapter_advance_bumps_chapter_and_clears_scene(tmp_path):
    """Chapter-kind accept bumps chapter_number and drops scene_number."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()
    target = WorkTarget(
        target_id="tgt-chapter",
        title="Book 1 Chapter 2",
        role=ROLE_PUBLISHABLE,
        publish_stage=PUBLISH_STAGE_PROVISIONAL,
        tags=["chapter"],
        metadata={
            "book_number": 1,
            "chapter_number": 2,
            "scene_number": 5,
            "execution_kind": "chapter",
        },
    )
    upsert_work_target(universe_path, target)

    trace = advance_work_target_on_accept(
        str(universe_path),
        target.target_id,
        verdict="accept",
        execution_scope={
            "execution_kind": "chapter",
            "book_number": 1,
            "chapter_number": 2,
        },
    )
    assert trace is not None
    assert trace["after"]["chapter_number"] == 3

    reloaded = get_target(str(universe_path), target.target_id)
    assert reloaded is not None
    assert reloaded.metadata["chapter_number"] == 3
    assert "scene_number" not in reloaded.metadata


def test_book_advance_bumps_book_and_clears_chapter_scene(tmp_path):
    """Book-kind accept bumps book_number and drops chapter/scene."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()
    target = WorkTarget(
        target_id="tgt-book",
        title="Book 2",
        role=ROLE_PUBLISHABLE,
        publish_stage=PUBLISH_STAGE_PROVISIONAL,
        tags=["book"],
        metadata={
            "book_number": 2,
            "chapter_number": 7,
            "scene_number": 3,
            "execution_kind": "book",
        },
    )
    upsert_work_target(universe_path, target)

    trace = advance_work_target_on_accept(
        str(universe_path),
        target.target_id,
        verdict="accept",
        execution_scope={"execution_kind": "book", "book_number": 2},
    )
    assert trace is not None
    assert trace["after"]["book_number"] == 3

    reloaded = get_target(str(universe_path), target.target_id)
    assert reloaded is not None
    assert reloaded.metadata["book_number"] == 3
    assert "chapter_number" not in reloaded.metadata
    assert "scene_number" not in reloaded.metadata


def test_non_accept_verdict_is_noop(tmp_path):
    """verdict=second_draft / revert must not advance the target."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()
    target_id = _seed_scene_target(
        universe_path, book=1, chapter=15, scene=3, target_id="tgt-noop",
    )

    for verdict in ("second_draft", "revert", ""):
        trace = advance_work_target_on_accept(
            str(universe_path),
            target_id,
            verdict=verdict,
            execution_scope={
                "execution_kind": "scene",
                "book_number": 1,
                "chapter_number": 15,
                "scene_number": 3,
            },
        )
        assert trace is None
        reloaded = get_target(str(universe_path), target_id)
        assert reloaded is not None
        assert reloaded.metadata["scene_number"] == 3


def test_missing_target_is_noop(tmp_path):
    """If the target_id doesn't exist, return None and don't raise."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()

    trace = advance_work_target_on_accept(
        str(universe_path),
        "does-not-exist",
        verdict="accept",
        execution_scope={
            "execution_kind": "scene",
            "book_number": 1,
            "chapter_number": 15,
            "scene_number": 3,
        },
    )
    assert trace is None


def test_missing_target_id_is_noop(tmp_path):
    """If target_id is None or blank, return None without touching storage."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()

    assert advance_work_target_on_accept(
        str(universe_path), None, verdict="accept", execution_scope={},
    ) is None
    assert advance_work_target_on_accept(
        str(universe_path), "", verdict="accept", execution_scope={},
    ) is None


def test_missing_execution_kind_is_noop(tmp_path):
    """No execution_kind → don't know how to advance; no-op."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()
    target_id = _seed_scene_target(
        universe_path, book=1, chapter=15, scene=3, target_id="tgt-kind",
    )

    trace = advance_work_target_on_accept(
        str(universe_path),
        target_id,
        verdict="accept",
        execution_scope={},  # no execution_kind
    )
    assert trace is None

    trace = advance_work_target_on_accept(
        str(universe_path),
        target_id,
        verdict="accept",
        execution_scope={"execution_kind": "notes"},
    )
    assert trace is None


def test_gap_scenario_advances_to_pinned_plus_one_not_past_max(tmp_path):
    """Gap-scenario: scenes 1+3 exist on disk, target pins scene_number=2.

    Fix (a)'s dispatch guard `scene_number <= max_existing_scene` would
    skip over the pinned gap-slot to scene 4. Fix (b) advances exactly
    past what was accepted: if we accept the pinned scene 2, the target
    becomes 3 — the next un-drafted coordinate — not 4.

    This proves (b) handles what (a)'s guard skips and makes the guard
    redundant in the normal-flow path.
    """
    universe_path = tmp_path / "universe"
    universe_path.mkdir()
    # Seed scenes 1 and 3 on disk (scene 2 is the gap).
    chapter_dir = universe_path / "output" / "book-1" / "chapter-15"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    for scene in (1, 3):
        (chapter_dir / f"scene-{scene:02d}.md").write_text(
            f"# Scene {scene}\n", encoding="utf-8",
        )
    target_id = _seed_scene_target(
        universe_path, book=1, chapter=15, scene=2, target_id="tgt-gap",
    )

    # Simulate daemon accepting the pinned scene 2.
    trace = advance_work_target_on_accept(
        str(universe_path),
        target_id,
        verdict="accept",
        execution_scope={
            "execution_kind": "scene",
            "book_number": 1,
            "chapter_number": 15,
            "scene_number": 2,
        },
    )
    assert trace is not None
    assert trace["after"]["scene_number"] == 3, (
        "advance must bump pinned scene_number 2 → 3, NOT skip to 4 "
        "past the scene-3.md that exists on disk. Fix (a)'s dispatch "
        "guard would skip; fix (b) advances precisely."
    )

    reloaded = get_target(str(universe_path), target_id)
    assert reloaded is not None
    assert reloaded.metadata["scene_number"] == 3


def test_scene_advance_uses_scope_when_metadata_missing(tmp_path):
    """If metadata.scene_number is missing, fall back to execution_scope."""
    universe_path = tmp_path / "universe"
    universe_path.mkdir()
    target = WorkTarget(
        target_id="tgt-no-meta",
        title="Book 1 Scene",
        role=ROLE_PUBLISHABLE,
        publish_stage=PUBLISH_STAGE_PROVISIONAL,
        tags=["scene"],
        metadata={
            "book_number": 1,
            "chapter_number": 15,
            # scene_number intentionally absent
            "execution_kind": "scene",
        },
    )
    upsert_work_target(universe_path, target)

    trace = advance_work_target_on_accept(
        str(universe_path),
        target.target_id,
        verdict="accept",
        execution_scope={
            "execution_kind": "scene",
            "book_number": 1,
            "chapter_number": 15,
            "scene_number": 7,  # dispatch resolved scene=7
        },
    )
    assert trace is not None
    assert trace["after"]["scene_number"] == 8

    reloaded = get_target(str(universe_path), target.target_id)
    assert reloaded is not None
    assert reloaded.metadata["scene_number"] == 8
