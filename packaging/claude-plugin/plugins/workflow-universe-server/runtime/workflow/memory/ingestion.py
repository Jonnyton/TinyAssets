"""Progressive ingestion -- non-blocking canon file processing.

User drops canon files into a directory.  The system surveys, triages
by relevance to the current universe, and ingests in priority order
without blocking the writing pipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class IngestionPriority(Enum):
    """Priority levels for source material sections."""

    IMMEDIATE = "immediate"    # Needed for current book
    BACKGROUND = "background"  # Needed eventually
    DISTANT = "distant"        # Reference only


@dataclass
class SourceSection:
    """A section of source material identified during survey."""

    file_path: str
    heading: str
    start_line: int
    end_line: int
    char_count: int
    priority: IngestionPriority = IngestionPriority.DISTANT
    ingested: bool = False
    entities_found: list[str] = field(default_factory=list)


@dataclass
class IngestionState:
    """Tracks the overall ingestion progress."""

    total_files: int = 0
    total_sections: int = 0
    ingested_sections: int = 0
    sections: list[SourceSection] = field(default_factory=list)
    survey_complete: bool = False

    @property
    def progress(self) -> float:
        if self.total_sections == 0:
            return 0.0
        return self.ingested_sections / self.total_sections


class ProgressiveIngestor:
    """Non-blocking progressive ingestion of canon files.

    Parameters
    ----------
    canon_dir : str | Path
        Directory to watch for canon files.
    universe_id : str
        Current universe namespace.
    """

    def __init__(
        self,
        canon_dir: str | Path,
        universe_id: str,
    ) -> None:
        self._canon_dir = Path(canon_dir)
        self._universe_id = universe_id
        self.state = IngestionState()
        self._processed_files: set[str] = set()

    # ------------------------------------------------------------------
    # Phase 1: Survey (fast, deterministic, no LLM)
    # ------------------------------------------------------------------

    def survey(self) -> IngestionState:
        """Scan canon directory, split into sections, extract headings.

        Returns the updated ingestion state.
        """
        if not self._canon_dir.exists():
            logger.warning("Canon directory does not exist: %s", self._canon_dir)
            return self.state

        files = self._find_canon_files()
        self.state.total_files = len(files)

        for fp in files:
            if str(fp) in self._processed_files:
                continue
            sections = self._split_into_sections(fp)
            self.state.sections.extend(sections)
            self._processed_files.add(str(fp))

        self.state.total_sections = len(self.state.sections)
        self.state.survey_complete = True

        logger.info(
            "Survey complete: %d files, %d sections",
            self.state.total_files, self.state.total_sections,
        )
        return self.state

    def _find_canon_files(self) -> list[Path]:
        """Find markdown and text files in the canon directory.

        Enumeration is routed through :func:`iter_canon_files` with
        ``recursive=True`` so each entry — including descendants surfaced by
        the recursive walk — is resolved + contained before any stat/read.
        A symlinked subdirectory or file whose target escapes ``canon_dir`` is
        skipped, so the recursive walk cannot ingest external content.
        """
        from workflow.ingestion.canon_io import iter_canon_files

        extensions = (".md", ".txt", ".markdown")
        return list(
            iter_canon_files(
                self._canon_dir, suffix=extensions, recursive=True
            )
        )

    @staticmethod
    def _split_into_sections(file_path: Path) -> list[SourceSection]:
        """Split a file into sections by markdown headings."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            logger.warning("Could not read %s", file_path)
            return []

        lines = text.split("\n")
        sections: list[SourceSection] = []
        current_heading = file_path.stem
        current_start = 0

        heading_re = re.compile(r"^#{1,4}\s+(.+)")

        for i, line in enumerate(lines):
            match = heading_re.match(line)
            if match:
                if i == 0:
                    # First line is a heading -- use it as initial heading.
                    current_heading = match.group(1).strip()
                    current_start = 0
                else:
                    # Close previous section.
                    content = "\n".join(lines[current_start:i])
                    sections.append(SourceSection(
                        file_path=str(file_path),
                        heading=current_heading,
                        start_line=current_start,
                        end_line=i,
                        char_count=len(content),
                    ))
                    current_heading = match.group(1).strip()
                    current_start = i

        # Final section.
        content = "\n".join(lines[current_start:])
        if content.strip():
            sections.append(SourceSection(
                file_path=str(file_path),
                heading=current_heading,
                start_line=current_start,
                end_line=len(lines),
                char_count=len(content),
            ))

        return sections

    # ------------------------------------------------------------------
    # Phase 2: Triage (assign priorities)
    # ------------------------------------------------------------------

    def triage(
        self,
        immediate_keywords: list[str] | None = None,
        background_keywords: list[str] | None = None,
    ) -> None:
        """Assign priority levels to sections based on keyword matching.

        In production, this would use an LLM call to determine
        relevance to PROGRAM.md.  This implementation uses keyword
        matching as a fast deterministic fallback.
        """
        imm = [k.lower() for k in (immediate_keywords or [])]
        bg = [k.lower() for k in (background_keywords or [])]

        for section in self.state.sections:
            heading_lower = section.heading.lower()

            if any(k in heading_lower for k in imm):
                section.priority = IngestionPriority.IMMEDIATE
            elif any(k in heading_lower for k in bg):
                section.priority = IngestionPriority.BACKGROUND
            else:
                section.priority = IngestionPriority.DISTANT

    # ------------------------------------------------------------------
    # Phase 3-5: Incremental ingestion
    # ------------------------------------------------------------------

    def get_next_batch(
        self,
        priority: IngestionPriority = IngestionPriority.IMMEDIATE,
        batch_size: int = 10,
    ) -> list[SourceSection]:
        """Return the next batch of un-ingested sections at *priority*."""
        batch = []
        for section in self.state.sections:
            if section.ingested:
                continue
            if section.priority == priority:
                batch.append(section)
                if len(batch) >= batch_size:
                    break
        return batch

    def mark_ingested(self, section: SourceSection) -> None:
        """Mark a section as ingested."""
        section.ingested = True
        self.state.ingested_sections += 1

    def check_for_new_files(self) -> list[Path]:
        """Check for newly added canon files since last survey."""
        if not self._canon_dir.exists():
            return []

        new_files = []
        for fp in self._find_canon_files():
            if str(fp) not in self._processed_files:
                new_files.append(fp)

        if new_files:
            for fp in new_files:
                sections = self._split_into_sections(fp)
                self.state.sections.extend(sections)
                self._processed_files.add(str(fp))
            self.state.total_sections = len(self.state.sections)
            self.state.total_files = len(self._processed_files)
            logger.info("Found %d new canon files", len(new_files))

        return new_files
