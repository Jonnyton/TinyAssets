"""Authenticated founder home-universe resolution for conversation entry."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

_HOME_MATERIALIZE_LOCK = threading.Lock()


def _home_dir(base: Path, universe_id: str) -> Path | None:
    """Resolve a home id inside ``base`` or fail closed on path traversal."""
    if not universe_id:
        return None
    root = base.resolve()
    candidate = (root / universe_id).resolve()
    return candidate if candidate.parent == root else None


def home_is_complete(base: Path, universe_id: str) -> bool:
    """Return whether a bound home has the canonical completed-seed marker."""
    universe_dir = _home_dir(base, universe_id)
    return universe_dir is not None and (universe_dir / "soul.md").is_file()


def ensure_founder_home(base: Path, founder: str) -> str:
    """Resolve or atomically create the authenticated founder's home universe.

    Returns ``""`` when the founder lacks create scope or materialization fails.
    The create scope is checked before reserving an id, and concurrent callers
    converge on one binding and one ledgered creation.
    """
    from tinyassets.daemon_server import claim_founder_home, get_founder_home

    home = get_founder_home(base, founder)
    if home_is_complete(base, home):
        return home

    from tinyassets.auth.middleware import require_action_scope

    try:
        require_action_scope("universe", "create_universe")
    except PermissionError:
        return ""

    from tinyassets.ids import new_universe_id

    winner = claim_founder_home(base, founder, new_universe_id())
    if not winner:
        return ""
    universe_dir = _home_dir(base, winner)
    if universe_dir is None:
        return ""
    if home_is_complete(base, winner):
        return winner

    from tinyassets.api.universe import _universe_impl

    with _HOME_MATERIALIZE_LOCK:
        if home_is_complete(base, winner):
            return winner
        if universe_dir.exists():
            try:
                shutil.rmtree(universe_dir)
            except OSError:
                pass
        try:
            _universe_impl(action="create_universe", universe_id=winner)
        except Exception:  # noqa: BLE001 - failed birth degrades honestly
            pass
        if not home_is_complete(base, winner):
            return ""
    return winner
