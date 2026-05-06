"""Deprecated compatibility shim for the old 12-tool daemon-file MCP server.

The public MCP surface now lives in :mod:`workflow.universe_server`, which
exposes the coarse-grained Workflow handles (``universe``, ``extensions``,
``goals``, ``gates``, ``wiki``, plus status/context aliases). This module stays
importable for old console scripts and tests, but it no longer registers a
separate 12-tool FastMCP surface.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from workflow.universe_server import main, mcp

DEPRECATION_NOTICE = (
    "workflow.mcp_server is deprecated; use workflow.universe_server and the "
    "coarse-grained universe/extensions/goals/gates/wiki surface."
)


def _universe_dir() -> Path:
    """Resolve the legacy per-universe directory.

    ``WORKFLOW_UNIVERSE`` remains supported for import-level compatibility.
    Without it, the shim matches the old default of
    ``workflow.storage.data_dir() / "default-universe"``.
    """
    env = os.environ.get("WORKFLOW_UNIVERSE")
    if env:
        return Path(env).expanduser().resolve()
    from workflow.storage import data_dir

    return data_dir() / "default-universe"


@contextmanager
def _legacy_universe_scope() -> Iterator[str]:
    """Map ``WORKFLOW_UNIVERSE=/root/name`` to universe_server's root/id model."""
    env = os.environ.get("WORKFLOW_UNIVERSE")
    if not env:
        yield ""
        return

    explicit = Path(env).expanduser().resolve()
    old_data_dir = os.environ.get("WORKFLOW_DATA_DIR")
    os.environ["WORKFLOW_DATA_DIR"] = str(explicit.parent)
    try:
        yield explicit.name
    finally:
        if old_data_dir is None:
            os.environ.pop("WORKFLOW_DATA_DIR", None)
        else:
            os.environ["WORKFLOW_DATA_DIR"] = old_data_dir


def _call_universe(action: str, **kwargs: Any) -> str:
    from workflow.universe_server import universe

    with _legacy_universe_scope() as universe_id:
        return universe(action=action, universe_id=universe_id, **kwargs)


def _json_dict(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_status() -> str:
    """Deprecated: use ``universe action=control_daemon text=status``."""
    status_path = _universe_dir() / "status.json"
    if not status_path.exists():
        return "No status.json found. The daemon may not be running."
    try:
        return status_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading status.json: {exc}"


def add_note(text: str, category: str = "direction") -> str:
    """Deprecated: use ``universe action=give_direction``."""
    _universe_dir().mkdir(parents=True, exist_ok=True)
    data = _json_dict(_call_universe("give_direction", text=text, category=category))
    if data.get("error"):
        return f"Error adding note: {data['error']}"
    note_id = str(data.get("note_id", ""))
    suffix = (
        f" (id={note_id[:8]}..., category={data.get('category', category)})."
        if note_id
        else "."
    )
    return f"Note added{suffix}"


def steer(directive: str, category: str = "direction") -> str:
    """Backward-compatible alias for ``add_note``."""
    return add_note(directive, category)


def get_premise() -> str:
    """Deprecated: use ``universe action=read_premise``."""
    data = _json_dict(_call_universe("read_premise"))
    if data.get("premise") is None:
        return "No PROGRAM.md found. Use set_premise() to create one."
    if "premise" in data:
        return str(data["premise"])
    return f"Error reading PROGRAM.md: {data.get('error', 'unknown error')}"


def set_premise(text: str) -> str:
    """Deprecated: use ``universe action=set_premise``."""
    _universe_dir().mkdir(parents=True, exist_ok=True)
    data = _json_dict(_call_universe("set_premise", text=text))
    if data.get("error"):
        return f"Error writing PROGRAM.md: {data['error']}"
    return "PROGRAM.md updated."


def get_progress() -> str:
    """Deprecated legacy file read. No standalone MCP tool is registered."""
    progress_path = _universe_dir() / "progress.md"
    if not progress_path.exists():
        return "No progress.md found. The daemon may not have started writing yet."
    try:
        return progress_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading progress.md: {exc}"


def get_work_targets() -> str:
    """Deprecated legacy file read. Use ``universe action=inspect``."""
    path = _universe_dir() / "work_targets.json"
    if not path.exists():
        return "No work_targets.json found."
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading work_targets.json: {exc}"


def get_review_state() -> str:
    """Deprecated legacy alias for ``get_status``."""
    status_path = _universe_dir() / "status.json"
    if not status_path.exists():
        return "No status.json found."
    try:
        return status_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading status.json: {exc}"


def get_chapter(book: int, chapter: int) -> str:
    """Deprecated: use ``universe action=read_output``."""
    rel_path = f"book-{book}/chapter-{chapter:02d}.md"
    data = _json_dict(_call_universe("read_output", path=rel_path))
    if "content" in data:
        return str(data["content"])
    if data.get("error"):
        return f"Chapter file not found: {rel_path}"
    return "Chapter file not found."


def get_activity(lines: int = 20) -> str:
    """Deprecated: use ``universe action=get_activity``."""
    data = _json_dict(_call_universe("get_activity", limit=lines))
    if isinstance(data.get("lines"), list):
        if data["lines"]:
            return "\n".join(str(line) for line in data["lines"])
        return "No activity.log found."
    if data.get("error"):
        return f"Error reading activity.log: {data['error']}"
    return "No activity.log found."


def pause() -> str:
    """Deprecated: use ``universe action=control_daemon text=pause``."""
    _universe_dir().mkdir(parents=True, exist_ok=True)
    data = _json_dict(_call_universe("control_daemon", text="pause"))
    if data.get("error"):
        return f"Error writing pause signal: {data['error']}"
    return "Pause signal written. The daemon will pause at the next scene boundary."


def resume() -> str:
    """Deprecated: use ``universe action=control_daemon text=resume``."""
    data = _json_dict(_call_universe("control_daemon", text="resume"))
    if data.get("status") == "not_paused":
        return "Daemon is not paused (no .pause file found)."
    if data.get("error"):
        return f"Error removing pause signal: {data['error']}"
    return "Pause signal removed. The daemon will resume."


def add_canon(filename: str, content: str) -> str:
    """Deprecated: use ``universe action=add_canon``."""
    _universe_dir().mkdir(parents=True, exist_ok=True)
    data = _json_dict(_call_universe("add_canon", filename=filename, text=content))
    if data.get("error"):
        return f"Error writing to canon/: {data['error']}"
    safe_name = str(data.get("filename") or Path(filename).name)
    return f"Written {safe_name} to canon/."


__all__ = [
    "DEPRECATION_NOTICE",
    "_universe_dir",
    "add_canon",
    "add_note",
    "get_activity",
    "get_chapter",
    "get_premise",
    "get_progress",
    "get_review_state",
    "get_status",
    "get_work_targets",
    "main",
    "mcp",
    "pause",
    "resume",
    "set_premise",
    "steer",
]


if __name__ == "__main__":
    main()
