"""Shared path and I/O helpers for the universe-server action handlers.

Extracted from ``tinyassets/universe_server.py`` preamble as Bundle 1 of
the #29 decomposition plan. These helpers are used by 3+ future submodules
(branches, runs, evaluation, market, wiki, status) and therefore live in
a shared leaf module with no project-level circular-import risk.

Public surface (stable contract):
    _base_path()               → Path: canonical data root
    _universe_dir(uid)         → Path: specific universe directory (path-traversal guarded)
    _default_universe()        → str:  default universe ID
    _read_json(path)           → dict | list | None: safe JSON reader
    _read_text(path, default)  → str:  safe text reader

ADDED 2026-04-26 (Task #8 — wiki-adjacent batch):
    _wiki_root()               → Path: canonical wiki directory root
    _wiki_pages_dir()          → Path: promoted-pages subtree (wiki_root/pages)
    _wiki_drafts_dir()         → Path: drafts subtree (wiki_root/drafts)
    _find_all_pages(directory) → list[Path]: recursive .md scan helper

The 4 wiki-adjacent helpers move here (rather than into a new
``wiki_helpers.py``) to keep the leaf-module count small and because
``_wiki_pages_dir`` / ``_wiki_drafts_dir`` both call ``_wiki_root``;
splitting them would create a `helpers.py → universe_server.py → helpers.py`
cycle until the wiki extraction (Task #9) lands. See
``docs/exec-plans/completed/2026-04-26-decomp-step-1-prep.md`` for the
helpers-already-extracted lesson that prompted this batch.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_WIKI_ROOT_OVERRIDE: ContextVar[Path | None] = ContextVar(
    "workflow_wiki_root_override",
    default=None,
)


def _base_path() -> Path:
    """Resolve the base directory containing all universe directories.

    Delegates to ``tinyassets.storage.data_dir`` — canonical env var
    ``TINYASSETS_DATA_DIR``. This replaces the earlier CWD-relative
    ``"output"`` default which wrote to ``/app/output`` in containers
    instead of the bind-mounted ``/data`` volume — the 2026-04-19
    containerization bug class.
    """
    from tinyassets.storage import data_dir
    return data_dir()


def _universe_dir(universe_id: str) -> Path:
    """Resolve a specific universe directory with path-traversal guard."""
    base = _base_path()
    result = (base / universe_id).resolve()
    if not result.is_relative_to(base):
        raise ValueError(f"Invalid universe_id: {universe_id}")
    return result


def _default_universe() -> str:
    """Return the default universe ID, or first available."""
    base = _base_path()
    from tinyassets.storage import active_universe_id
    active = active_universe_id(base)
    if active:
        return active

    default = os.environ.get("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "")
    if default:
        return default

    if base.is_dir():
        for child in sorted(base.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                return child.name
    return "default-universe"


def _designated_public_universe() -> str:
    """Identity-neutral public landing universe for an authenticated founder who
    has no home and cannot create one.

    Unlike :func:`_default_universe` this NEVER reads the host-global
    ``.active_universe`` marker and NEVER returns another founder's serial home
    (``u-`` + ULID) — either would leak one founder's universe to another on an
    omitted-scope read (universe-creation spec: "First MCP contact ... SHALL NOT
    use a root-global ``.active_universe`` marker to decide which universe a
    chatbot speaks as"). Env-designated default wins; otherwise the first
    non-serial public directory; else the literal ``default-universe``.
    """
    default = os.environ.get("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "")
    if default:
        return default
    from tinyassets.ids import is_universe_serial

    base = _base_path()
    if base.is_dir():
        for child in sorted(base.iterdir()):
            if (
                child.is_dir()
                and not child.name.startswith(".")
                and not is_universe_serial(child.name)
            ):
                return child.name
    return "default-universe"


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    """Safely read a JSON file, returning None on any failure."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read %s: %s", path, exc)
    return None


def _read_text(path: Path, default: str = "") -> str:
    """Safely read a text file."""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read %s: %s", path, exc)
    return default


# ─────────────────────────────────────────────────────────────────────
# Wiki-adjacent path helpers (Task #8, 2026-04-26)
# ─────────────────────────────────────────────────────────────────────


def _wiki_root() -> Path:
    """Resolve the wiki root directory.

    Delegates to ``tinyassets.storage.wiki_path`` — canonical env var
    ``TINYASSETS_WIKI_PATH``. Platform default is ``data_dir() / "wiki"``.

    Pre-2026-04-20 this hardcoded ``r"C:\\Users\\Jonathan\\Projects\\Wiki"``
    as the fallback, which broke every non-host deploy. See
    ``tinyassets.storage.wiki_path`` for the precedence + rationale.
    """
    override = _WIKI_ROOT_OVERRIDE.get()
    if override is not None:
        return override

    from tinyassets.storage import wiki_path
    return wiki_path()


@contextmanager
def _scoped_wiki_root(root: Path) -> Iterator[None]:
    """Temporarily route wiki helpers to an explicit wiki root."""
    token = _WIKI_ROOT_OVERRIDE.set(root.resolve())
    try:
        yield
    finally:
        _WIKI_ROOT_OVERRIDE.reset(token)


def _wiki_pages_dir() -> Path:
    return _wiki_root() / "pages"


def _wiki_drafts_dir() -> Path:
    return _wiki_root() / "drafts"


def _find_all_pages(directory: Path) -> list[Path]:
    """Recursively find all .md files under a directory."""
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.rglob("*.md") if p.is_file())


__all__ = [
    "_base_path",
    "_default_universe",
    "_find_all_pages",
    "_read_json",
    "_read_text",
    "_scoped_wiki_root",
    "_universe_dir",
    "_wiki_drafts_dir",
    "_wiki_pages_dir",
    "_wiki_root",
]
