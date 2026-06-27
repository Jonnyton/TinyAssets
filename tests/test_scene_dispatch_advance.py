"""Task #33 — Sporemarch oscillation fix.

Per user-sim Mission 7: B1-C15-S3 stuck oscillating SECOND_DRAFT scores
across 3+ universe cycles because `_build_book_execution_seed` trusted
the WorkTarget's explicit `metadata.scene_number` unconditionally, even
when that scene file already existed on disk. Each cycle rewrote the
same scene → revision budget reset → word count frozen.

Fix: advance `scene_number` past any existing scene file, even when
the WorkTarget pins an explicit value. Proper root-cause fix
(WorkTarget metadata advance on accept) is filed as a follow-up.
"""

from __future__ import annotations

from pathlib import Path

from domains.fantasy_daemon.graphs.universe import _build_book_execution_seed
from tinyassets.work_targets import (
    PUBLISH_STAGE_PROVISIONAL,
    ROLE_PUBLISHABLE,
    WorkTarget,
    upsert_work_target,
)


def _make_chapter_scene(
    universe_path: Path, book: int, chapter: int, scene: int,
) -> None:
    """Create a scene file on disk to simulate prior accepted work."""
    chapter_dir = (
        universe_path / "output"
        / f"book-{book}" / f"chapter-{chapter:02d}"
    )
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / f"scene-{scene:02d}.md").write_text(
        f"# Scene {scene}\n\nExisting prose.\n", encoding="utf-8",
    )


def _make_scene_target(
    universe_path: Path, book: int, chapter: int, scene: int,
) -> str:
    """Seed a ROLE_PUBLISHABLE scene WorkTarget pinned at a scene number."""
    target = WorkTarget(
        target_id=f"book-{book}-ch-{chapter}-scene-{scene}",
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


def test_dispatch_advances_past_existing_scene_file(tmp_path):
    """Sporemarch oscillation case: target pins scene_number=3 AND
    scene-03.md already exists → dispatch advances to scene 4."""
    universe_path = tmp_path / "test-universe"
    universe_path.mkdir()
    # Existing accepted scenes 1, 2, 3 on disk.
    for n in (1, 2, 3):
        _make_chapter_scene(universe_path, book=1, chapter=15, scene=n)
    target_id = _make_scene_target(
        universe_path, book=1, chapter=15, scene=3,
    )

    state = {
        "_universe_path": str(universe_path),
        "selected_target_id": target_id,
    }
    seed, execution_scope = _build_book_execution_seed(state)
    assert execution_scope["scene_number"] == 4, (
        "dispatch must advance past the existing scene-03.md "
        "rather than rewriting it"
    )
    assert execution_scope["chapter_number"] == 15


def test_dispatch_uses_explicit_scene_when_file_absent(tmp_path):
    """Additive guard: no existing scene file → dispatch still honors
    the explicit scene_number. Preserves the pre-fix contract for
    first-time scene targeting."""
    universe_path = tmp_path / "test-universe"
    universe_path.mkdir()
    # Only scenes 1 and 2 exist; WorkTarget pins scene_number=3.
    for n in (1, 2):
        _make_chapter_scene(universe_path, book=1, chapter=15, scene=n)
    target_id = _make_scene_target(
        universe_path, book=1, chapter=15, scene=3,
    )

    state = {
        "_universe_path": str(universe_path),
        "selected_target_id": target_id,
    }
    seed, execution_scope = _build_book_execution_seed(state)
    assert execution_scope["scene_number"] == 3, (
        "dispatch should target the explicit scene_number when no "
        "matching scene file exists"
    )


def test_dispatch_default_max_plus_one_still_works(tmp_path):
    """Regression: target has no explicit scene_number → dispatch uses
    max(existing) + 1 (pre-fix default path)."""
    universe_path = tmp_path / "test-universe"
    universe_path.mkdir()
    for n in (1, 2, 3):
        _make_chapter_scene(universe_path, book=1, chapter=15, scene=n)

    target = WorkTarget(
        target_id="book-1-ch-15-next",
        title="Book 1 Chapter 15 (next scene)",
        role=ROLE_PUBLISHABLE,
        publish_stage=PUBLISH_STAGE_PROVISIONAL,
        tags=["scene"],
        metadata={
            "book_number": 1,
            "chapter_number": 15,
            # no scene_number key
            "execution_kind": "scene",
        },
    )
    upsert_work_target(universe_path, target)

    state = {
        "_universe_path": str(universe_path),
        "selected_target_id": target.target_id,
    }
    seed, execution_scope = _build_book_execution_seed(state)
    assert execution_scope["scene_number"] == 4


def test_dispatch_advances_when_explicit_scene_equals_max_existing(tmp_path):
    """Boundary case: WorkTarget pins scene_number equal to the highest
    existing scene number. Must bump to N+1, not stay at N."""
    universe_path = tmp_path / "test-universe"
    universe_path.mkdir()
    for n in (1, 2, 5):  # non-contiguous scenes; max_existing=5
        _make_chapter_scene(universe_path, book=1, chapter=15, scene=n)
    target_id = _make_scene_target(
        universe_path, book=1, chapter=15, scene=5,
    )

    state = {
        "_universe_path": str(universe_path),
        "selected_target_id": target_id,
    }
    _, execution_scope = _build_book_execution_seed(state)
    assert execution_scope["scene_number"] == 6
