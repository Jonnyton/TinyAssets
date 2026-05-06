"""MCP server exposing the Workflow daemon's file interface.

Provides tools for any AI client to read status, add notes for the daemon,
manage premises, read output, and control execution.

Usage::

    python -m workflow.mcp_server

Set ``WORKFLOW_UNIVERSE`` to the universe directory path,
or it defaults to ``output/default-universe/``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP(
    "fantasy-author",
    instructions=(
        "Workflow daemon interface. Use these tools to monitor "
        "and guide an autonomous fiction-writing daemon through notes. "
        "Start with get_status to see the daemon's current phase, then "
        "use get_progress for a human-readable summary of what's been written."
    ),
    version="0.1.0",
)


def _repo_root() -> Path:
    """Absolute path to the repository root (two levels up from this module)."""
    return Path(__file__).resolve().parent.parent


def _universe_dir() -> Path:
    """Resolve the universe directory from environment or default.

    Precedence:
      1. ``$WORKFLOW_UNIVERSE`` — explicit per-universe override.
      2. ``workflow.storage.data_dir() / "default-universe"`` — anchored
         to the canonical ``WORKFLOW_DATA_DIR`` root (or its legacy
         alias / platform default).

    The default is anchored to the daemon's on-disk data root, NOT the
    repo root. Pre-2026-04-20 this defaulted to
    ``<repo_root>/output/default-universe`` which worked on a dev
    machine but wrote to ``/app/output/default-universe`` in a
    container — NOT the bind-mounted ``/data`` volume. Rooting at
    ``data_dir()`` closes the container CWD-drift bug class.

    Cross-universe contamination guard still applies: never CWD-relative.
    See STATUS.md #47/#48 + ``KnowledgeGraph`` / ``VectorStore``
    hard-refuse guards from #51.
    """
    env = os.environ.get("WORKFLOW_UNIVERSE")
    if env:
        return Path(env).expanduser().resolve()
    from workflow.storage import data_dir
    return data_dir() / "default-universe"



def _structured_return(raw):
    """Wrap an MCP tool result so FastMCP populates ``structured_content``.

    ChatGPT (OpenAI Apps SDK) wedges on substrate-changing tool calls when
    the response carries only ``content`` (text) without ``structuredContent``
    (typed dict) + ``_meta`` annotations. Claude tolerates either shape.

    Mirrors the helper in workflow.universe_server applied via PR #493.
    """
    import json as _json
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"result": raw}
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return {"text": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    return {"result": raw}


@mcp.tool(
    tags={"status", "monitoring"},
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
)
def get_status() -> dict:
    """Read the daemon's current status including phase, word count, and accept rate.

    Call this first to orient yourself.
    """
    status_path = _universe_dir() / "status.json"
    if not status_path.exists():
        return "No status.json found. The daemon may not be running."
    try:
        return _structured_return(status_path.read_text(encoding="utf-8"))
    except OSError as e:
        return f"Error reading status.json: {e}"


@mcp.tool(
    tags={"notes", "steering", "direction"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False),
)
def add_note(text: str, category: str = "direction") -> dict:
    """Add a note that the daemon reads at each scene boundary.

    Notes are the primary feedback mechanism — use them to steer the story,
    protect elements you like, flag concerns, or record observations.

    Args:
        text: The note text (what you want the daemon to know).
        category: One of 'direction' (steer the story), 'protect' (preserve
            something), 'concern' (flag a problem), 'observation' (neutral
            note), or 'error' (report a mistake).
    """
    valid_categories = {"direction", "protect", "concern", "observation", "error"}
    if category not in valid_categories:
        category = "direction"
    try:
        from workflow.notes import add_note as add_note_to_store

        _universe_dir().mkdir(parents=True, exist_ok=True)
        note = add_note_to_store(
            _universe_dir(), source="user", text=text, category=category,
        )
        return f"Note added (id={note.id[:8]}..., category={category})."
    except Exception as e:
        return f"Error adding note: {e}"


def steer(directive: str, category: str = "direction") -> str:
    """Backward-compatible alias for ``add_note``."""
    return _structured_return(add_note(directive, category))@mcp.tool(
    tags={"premise", "story"},
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_premise() -> dict:
    """Read the current story premise from PROGRAM.md.

    The premise seeds the daemon's creative direction.
    """
    program_path = _universe_dir() / "PROGRAM.md"
    if not program_path.exists():
        return "No PROGRAM.md found. Use set_premise() to create one."
    try:
        return _structured_return(program_path.read_text(encoding="utf-8"))
    except OSError as e:
        return f"Error reading PROGRAM.md: {e}"


@mcp.tool(
    tags={"premise", "story"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True),
)
def set_premise(text: str) -> dict:
    """Write or overwrite the story premise in PROGRAM.md.

    The daemon reads this at startup to seed the story direction.
    Overwrites any existing premise — use get_premise first if you want to
    edit rather than replace.
    """
    program_path = _universe_dir() / "PROGRAM.md"
    try:
        _universe_dir().mkdir(parents=True, exist_ok=True)
        program_path.write_text(text, encoding="utf-8")
        return _structured_return("PROGRAM.md updated.")
    except OSError as e:
        return _structured_return(f"Error writing PROGRAM.md: {e}")


@mcp.tool(
    tags={"progress", "monitoring"},
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_progress() -> dict:
    """Read the human-readable progress summary.

    Includes story outline, word counts, and current chapter status.
    """
    progress_path = _universe_dir() / "progress.md"
    if not progress_path.exists():
        return "No progress.md found. The daemon may not have started writing yet."
    try:
        return _structured_return(progress_path.read_text(encoding="utf-8"))
    except OSError as e:
        return f"Error reading progress.md: {e}"


@mcp.tool(
    tags={"work-targets", "planning"},
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_work_targets() -> dict:
    """Read the durable work target registry.

    Shows what the daemon is working on, what's queued, and lifecycle state.
    """
    path = _universe_dir() / "work_targets.json"
    if not path.exists():
        return "No work_targets.json found."
    try:
        return _structured_return(path.read_text(encoding="utf-8"))
    except OSError as e:
        return f"Error reading work_targets.json: {e}"


@mcp.tool(
    tags={"review", "monitoring"},
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_review_state() -> dict:
    """Read the latest review-state snapshot including daemon phase, word count, and accept rate."""
    status_path = _universe_dir() / "status.json"
    if not status_path.exists():
        return "No status.json found."
    try:
        return _structured_return(status_path.read_text(encoding="utf-8"))
    except OSError as e:
        return f"Error reading status.json: {e}"


@mcp.tool(
    tags={"output", "reading"},
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_chapter(book: int, chapter: int) -> dict:
    """Read a completed chapter from the daemon's output.

    Args:
        book: Book number (e.g. 1).
        chapter: Chapter number (e.g. 3). Returns the full chapter markdown.
    """
    chapter_path = _universe_dir() / "output" / f"book-{book}" / f"chapter-{chapter:02d}.md"
    if not chapter_path.exists():
        return f"Chapter file not found: book-{book}/chapter-{chapter:02d}.md"
    try:
        return _structured_return(chapter_path.read_text(encoding="utf-8"))
    except OSError as e:
        return f"Error reading chapter file: {e}"


@mcp.tool(
    tags={"activity", "monitoring"},
    annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
)
def get_activity(lines: int = 20) -> dict:
    """Read the most recent lines from the daemon's activity log.

    Shows scene completions, reviews, and errors.

    Args:
        lines: Number of lines to return (default 20, max 200).
    """
    log_path = _universe_dir() / "activity.log"
    if not log_path.exists():
        return _structured_return("No activity.log found.")
    try:
        content = log_path.read_text(encoding="utf-8")
        all_lines = content.strip().splitlines()
        tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
        return _structured_return("\n".join(tail))
    except OSError as e:
        return _structured_return(f"Error reading activity.log: {e}")


@mcp.tool(
    tags={"control", "daemon"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
)
def pause() -> dict:
    """Pause the daemon at the next scene boundary.

    The daemon checks for a pause signal between scenes.
    """
    pause_path = _universe_dir() / ".pause"
    try:
        _universe_dir().mkdir(parents=True, exist_ok=True)
        pause_path.write_text(
            datetime.now(timezone.utc).isoformat(), encoding="utf-8",
        )
        return _structured_return("Pause signal written. The daemon will pause at the next scene boundary.")
    except OSError as e:
        return _structured_return(f"Error writing pause signal: {e}")


@mcp.tool(
    tags={"control", "daemon"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
)
def resume() -> dict:
    """Resume a paused daemon by removing the pause signal."""
    pause_path = _universe_dir() / ".pause"
    if not pause_path.exists():
        return _structured_return("Daemon is not paused (no .pause file found).")
    try:
        pause_path.unlink()
        return _structured_return("Pause signal removed. The daemon will resume.")
    except OSError as e:
        return _structured_return(f"Error removing pause signal: {e}")


@mcp.tool(
    tags={"canon", "worldbuilding"},
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True),
)
def add_canon(filename: str, content: str) -> dict:
    """Add a reference document to the canon/ directory for the daemon to ingest.

    Canon files provide worldbuilding context — character sheets, maps, lore
    documents, timelines, style guides, or any reference material the daemon
    should know about.

    Args:
        filename: Name for the file (e.g. "characters.md", "magic-system.md").
        content: File content to write.
    """
    canon_dir = _universe_dir() / "canon"
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    if not safe_name:
        return _structured_return("Invalid filename.")
    try:
        canon_dir.mkdir(parents=True, exist_ok=True)
        target = canon_dir / safe_name
        target.write_text(content, encoding="utf-8")
        return _structured_return(f"Written {safe_name} to canon/.")
    except OSError as e:
        return _structured_return(f"Error writing to canon/: {e}")


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
