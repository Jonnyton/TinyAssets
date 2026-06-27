"""One-shot KG recovery: rebuild a universe's knowledge.db from committed prose.

Motivation
----------
Scenes committed before 2026-04-11 wrote KG entities to a CWD-relative
``./knowledge.db`` instead of the per-universe file under ``output/<u>/``.
That historical data was then archived under ``archive/stale-root-dbs/`` where
it mingled across universes and cannot be safely copied back. This script
re-extracts entities/edges/facts from each scene's committed prose and
populates the per-universe KG directly.

Recovery only. Does NOT modify the live daemon pipeline. Idempotent (upsert).

Usage
-----
    python scripts/rebuild_sporemarch_kg.py --universe output/sporemarch
    python scripts/rebuild_sporemarch_kg.py --universe output/sporemarch --dry-run

Expected layout under ``--universe``::

    output/<u>/
      output/book-<N>/chapter-<NN>/scene-<NN>.md
      knowledge.db  (will be created or upserted into)
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Make workflow package importable when run from repo root
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from tinyassets.ingestion.indexer import index_text  # noqa: E402
from tinyassets.knowledge.knowledge_graph import KnowledgeGraph  # noqa: E402

logger = logging.getLogger("rebuild_kg")

_CHAPTER_RE = re.compile(r"chapter-(\d+)", re.IGNORECASE)
_SCENE_RE = re.compile(r"scene-(\d+)\.md$", re.IGNORECASE)
_BOOK_RE = re.compile(r"book-(\d+)", re.IGNORECASE)


@dataclass
class SceneFile:
    path: Path
    book: int
    chapter: int
    scene: int

    def scene_id(self, universe_name: str) -> str:
        return f"{universe_name}-B{self.book}-C{self.chapter}-S{self.scene}"


def discover_scenes(universe_dir: Path) -> list[SceneFile]:
    """Walk ``<universe>/output/book-*/chapter-*/scene-*.md`` and return
    them sorted by (book, chapter, scene).
    """
    out_dir = universe_dir / "output"
    if not out_dir.is_dir():
        raise FileNotFoundError(f"No output/ directory under {universe_dir}")

    scenes: list[SceneFile] = []
    for scene_path in out_dir.rglob("scene-*.md"):
        scene_match = _SCENE_RE.search(scene_path.name)
        chapter_match = _CHAPTER_RE.search(str(scene_path.parent))
        book_match = _BOOK_RE.search(str(scene_path))
        if not (scene_match and chapter_match and book_match):
            logger.warning(
                "Skipping unrecognized path: %s", scene_path,
            )
            continue
        scenes.append(SceneFile(
            path=scene_path,
            book=int(book_match.group(1)),
            chapter=int(chapter_match.group(1)),
            scene=int(scene_match.group(1)),
        ))

    scenes.sort(key=lambda s: (s.book, s.chapter, s.scene))
    return scenes


def _load_provider_call():
    """Import the production provider stub. Fails loudly on import error."""
    from domains.fantasy_daemon.phases._provider_stub import call_provider

    return call_provider


def rebuild(universe_dir: Path, *, dry_run: bool) -> dict[str, int]:
    """Walk scenes, run index_text against each, return summary totals."""
    universe_name = universe_dir.name
    kg_path = universe_dir / "knowledge.db"

    scenes = discover_scenes(universe_dir)
    logger.info("Discovered %d scenes under %s", len(scenes), universe_dir)
    if not scenes:
        return {"scenes": 0, "entities": 0, "edges": 0, "facts": 0, "failures": 0}

    if dry_run:
        logger.info("DRY RUN: not opening KG; printing scene plan only")
        for s in scenes:
            prose = s.path.read_text(encoding="utf-8", errors="replace")
            logger.info(
                "would index %s -> %s (%d chars)",
                s.scene_id(universe_name), s.path, len(prose),
            )
        return {
            "scenes": len(scenes),
            "entities": 0, "edges": 0, "facts": 0, "failures": 0,
        }

    call_provider = _load_provider_call()
    kg = KnowledgeGraph(db_path=str(kg_path))

    totals = {"scenes": 0, "entities": 0, "edges": 0, "facts": 0, "failures": 0}
    try:
        for s in scenes:
            sid = s.scene_id(universe_name)
            prose = s.path.read_text(encoding="utf-8", errors="replace").strip()
            if not prose:
                logger.warning("Skipping empty scene file: %s", s.path)
                totals["failures"] += 1
                continue

            try:
                result = index_text(
                    prose,
                    source_id=sid,
                    knowledge_graph=kg,
                    vector_store=None,
                    embed_fn=None,
                    provider_call=call_provider,
                    chapter_number=s.chapter,
                )
            except Exception:
                logger.exception("Failed to index %s (%s)", sid, s.path)
                totals["failures"] += 1
                continue

            totals["scenes"] += 1
            totals["entities"] += result.get("entities", 0)
            totals["edges"] += result.get("edges", 0)
            totals["facts"] += result.get("facts", 0)
            logger.info(
                "indexed %s: %d entities, %d edges, %d facts",
                sid,
                result.get("entities", 0),
                result.get("edges", 0),
                result.get("facts", 0),
            )
    finally:
        kg.close()

    # Verify by reading final row counts from the DB
    verify_kg = KnowledgeGraph(db_path=str(kg_path))
    try:
        totals["db_entities"] = verify_kg._conn.execute(
            "SELECT COUNT(*) FROM entities"
        ).fetchone()[0]
        totals["db_edges"] = verify_kg._conn.execute(
            "SELECT COUNT(*) FROM edges"
        ).fetchone()[0]
        totals["db_facts"] = verify_kg._conn.execute(
            "SELECT COUNT(*) FROM facts"
        ).fetchone()[0]
    finally:
        verify_kg.close()

    return totals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild a universe's knowledge.db from committed prose.",
    )
    parser.add_argument(
        "--universe",
        required=True,
        help="Path to the universe directory (e.g. output/sporemarch).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover scenes and print plan without writing to the KG.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    universe_dir = Path(args.universe).resolve()
    if not universe_dir.is_dir():
        logger.error("Universe directory not found: %s", universe_dir)
        return 2

    totals = rebuild(universe_dir, dry_run=args.dry_run)

    logger.info("=" * 60)
    logger.info("Summary for %s", universe_dir)
    for k, v in totals.items():
        logger.info("  %s: %s", k, v)

    if not args.dry_run and totals.get("failures", 0) > 0:
        logger.warning(
            "%d scene(s) failed to index. See warnings above.",
            totals["failures"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
