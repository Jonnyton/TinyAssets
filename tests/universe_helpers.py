"""Making a universe in a test, the way creating one makes it.

A universe is a directory somebody OWNS (founder, 2026-09-02). It used to be
any directory under the data root, so a test could make one with ``mkdir`` --
which is exactly how the platform's own backups and every prune's archive
became universes on production. A test that wants a universe grants it an
owner, because that is what the real creation path does.
"""

from __future__ import annotations

from pathlib import Path


def own_universe(
    base_path: str | Path,
    universe_id: str,
    *,
    actor_id: str = "test-owner",
    permission: str = "admin",
) -> Path:
    """Create ``universe_id`` under ``base_path``, registered and owned."""
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        grant_universe_access,
    )

    base = Path(base_path)
    udir = base / universe_id
    udir.mkdir(parents=True, exist_ok=True)
    ensure_universe_registered(
        base,
        universe_id=universe_id,
        universe_path=udir,
        display_name=universe_id,
    )
    grant_universe_access(
        base,
        universe_id=universe_id,
        actor_id=actor_id,
        permission=permission,
        granted_by="tests",
    )
    return udir
