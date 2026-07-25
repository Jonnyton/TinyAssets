"""Authenticated founder home-universe resolution for conversation entry."""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

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

    from tinyassets.ids import is_universe_serial, new_universe_id

    candidate = new_universe_id()
    winner = claim_founder_home(base, founder, candidate)
    if not winner:
        return ""
    # Provenance gate (universe-creation 5.2): the internal-trust flag may only
    # materialize a platform-generated serial. ``winner`` is either the fresh
    # ``candidate`` we just reserved this call, or whatever the ``founder_home``
    # row already held — ``claim_founder_home`` runs INSERT ... ON CONFLICT DO
    # NOTHING, so a pre-existing binding is returned verbatim. ``founder_home``
    # has no serial-format constraint, so a stale, founder-influenced
    # *descriptive* id (from historical caller-selected creation, before this
    # boundary existed) can surface here. Materializing it through the trust
    # flag would silently defeat self-serialization at the exact seam meant to
    # protect it. Trust ``winner`` ONLY when it is the fresh candidate we just
    # generated OR it itself passes the canonical serial validator (same
    # ``is_universe_serial`` the generator round-trips, never a regex copy).
    # Otherwise fail closed and LOUDLY — never silently rebind or migrate a
    # stale descriptive home to a serial here; that is host-run migration
    # behavior (universe-creation 5.4), not a first-contact side effect.
    if winner != candidate and not is_universe_serial(winner):
        logger.warning(
            "first-contact refused to materialize founder %s home: bound "
            "universe_id %r is neither the freshly reserved serial nor a valid "
            "platform serial. Failing closed; serial migration must repair the "
            "stale binding before this founder can birth a home.",
            founder,
            winner,
        )
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
            # ``winner`` has passed the provenance gate above: it is either the
            # serial we just reserved this call or an already-recorded valid
            # platform serial. Only such a proven serial may cross the trusted
            # internal path so the public-birth boundary accepts our own id.
            _universe_impl(
                action="create_universe",
                universe_id=winner,
                allow_named_universe_id=True,
            )
        except Exception:  # noqa: BLE001 - failed birth degrades honestly
            pass
        if not home_is_complete(base, winner):
            return ""
    return winner
