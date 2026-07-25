"""Universe visibility model — the anonymous-reader access surface.

Truth split (see ``openspec/changes/universe-visibility/design.md`` and the
delta spec ``openspec/specs/universe-visibility``):

  * ``tinyassets.api.permissions`` owns **ownership** (the ``universe_acl``
    grant set) and the legacy binary **``public_read``** bit.
  * This module owns the enriched **visibility level** that decomposes what an
    *unauthenticated / non-granted* reader may do into three separately-grantable
    capabilities — ``discover_existence`` / ``read_metadata`` / ``read_content``
    — composes a per-universe level with a per-page override, and **fails
    closed** on an undeclared, unrecognized, or unreadable level rather than
    defaulting to visible.

Two structural invariants (both demanded by the cross-family review that
rejected the first cut):

  1. **Tighten-only by construction.** The effective read decision is
     ``legacy_gate AND new_layer`` — ``visibility_permits`` returns ``False``
     whenever the legacy ``universe_access_allows`` read gate denies, so the new
     layer can never *grant* a read the legacy gate withholds (an inconsistent
     row with ``public_read=False`` plus a permissive explicit level can no
     longer open a read).
  2. **Fail closed by default.** ``universe_visibility`` returns the *declared*
     level or ``CLOSED``; it never derives an open default from ``public_read``.
     Undeclared, blank, unrecognized, wrong-type, corrupt, and non-dict states
     all resolve to ``private``. Existing universes are declared by
     ``backfill_universe_visibility`` (the migration path), not by a fail-open
     fallback or an env opt-in to strictness.

A reader holding a read/write/admin grant on a universe is never limited by
anonymous visibility.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from tinyassets.api.helpers import _base_path

logger = logging.getLogger("universe_server.visibility")

# The three separately-grantable capabilities, in the canonical order used by
# the delta spec (existence -> metadata -> content).
CAPABILITIES = ("discover_existence", "read_metadata", "read_content")


@dataclass(frozen=True)
class VisibilityLevel:
    """A named triple of anonymous-reader capabilities."""

    name: str
    discover_existence: bool
    read_metadata: bool
    read_content: bool

    def permits(self, capability: str) -> bool:
        if capability not in CAPABILITIES:
            raise ValueError(f"unknown visibility capability: {capability!r}")
        return bool(getattr(self, capability))


# Canonical presets. ``private`` is the fail-closed level: every undeclared,
# unrecognized, or unreadable state resolves to it.
PUBLIC = VisibilityLevel("public", True, True, True)
METADATA_ONLY = VisibilityLevel("metadata_only", True, True, False)
UNLISTED = VisibilityLevel("unlisted", False, False, True)
PRIVATE = VisibilityLevel("private", False, False, False)

LEVELS: dict[str, VisibilityLevel] = {
    lvl.name: lvl for lvl in (PUBLIC, METADATA_ONLY, UNLISTED, PRIVATE)
}

#: The fail-closed level — used whenever a level cannot be trusted.
CLOSED = PRIVATE

#: Rules-metadata key that stores the explicit declared level name.
LEVEL_METADATA_KEY = "visibility_level"

#: Page frontmatter keys a page may use to narrow its own content visibility.
_PAGE_VISIBILITY_KEYS = ("visibility", "content_visibility")

#: Page-level string values that explicitly withhold content ("content: false").
_PAGE_FALSE_VALUES = frozenset({"false", "no", "off", "0", "none"})


def parse_level(name: Any) -> VisibilityLevel | None:
    """Return the named level, or ``None`` if the name is not recognized.

    An unrecognized level name is NOT an error the caller can ignore — callers
    that resolve visibility treat ``None`` as fail-closed.
    """
    key = str(name or "").strip()
    if not key:
        return None
    return LEVELS.get(key)


# Sentinels distinguishing "no rules row recorded" from "rules unreadable".
_MISSING = object()
_CORRUPT = object()


def _read_rules(universe_id: str) -> dict[str, Any] | object:
    """Return the universe's rules dict, or a sentinel.

    ``_MISSING`` when no rules row exists yet; ``_CORRUPT`` when the rules could
    not be read (DB/store error) — which must never fall open.
    """
    uid = (universe_id or "").strip()
    if not uid:
        return _MISSING
    try:
        from tinyassets.daemon_server import get_universe_rules

        return get_universe_rules(_base_path(), universe_id=uid)
    except KeyError:
        return _MISSING
    except Exception:
        logger.warning(
            "visibility: failing closed on rules-read error for universe %r",
            uid,
            exc_info=True,
        )
        return _CORRUPT


def universe_visibility(universe_id: str) -> VisibilityLevel:
    """Resolve the *declared* visibility level for a universe, or ``CLOSED``.

    This is a strict, fail-closed resolver. It NEVER derives an open default
    from ``public_read`` — that bit is the legacy gate's concern, composed
    separately and only as a *ceiling* in :func:`visibility_permits`. Every one
    of the following resolves to the fail-closed ``private`` level:

      * blank universe id;
      * rules unreadable (corrupt store) or no rules row at all (undeclared);
      * the whole rules value, or its ``metadata`` container, is not a dict;
      * no ``visibility_level`` key present (undeclared — the backfill declares);
      * the declared value is not a string, is blank/whitespace, or is an
        unrecognized level name.

    Only a rules row carrying an explicit, recognized ``visibility_level``
    resolves to that named level.
    """
    if not (universe_id or "").strip():
        return CLOSED

    rules = _read_rules(universe_id)
    if rules is _CORRUPT or rules is _MISSING:
        return CLOSED
    if not isinstance(rules, dict):
        return CLOSED  # never AssertionError on a hand-forged/non-dict row.

    metadata = rules.get("metadata")
    if not isinstance(metadata, dict) or LEVEL_METADATA_KEY not in metadata:
        return CLOSED  # undeclared -> fail closed (backfill declares).

    declared = metadata[LEVEL_METADATA_KEY]
    if not isinstance(declared, str):
        return CLOSED  # null / number / bool / list / object -> fail closed.
    level = parse_level(declared)  # blank / whitespace / unrecognized -> None.
    if level is None:
        logger.warning(
            "visibility: undeclared-or-unrecognized level %r for universe %r "
            "-> failing closed",
            declared,
            universe_id,
        )
        return CLOSED
    return level


def declared_level_name(universe_id: str) -> str:
    """The level name to report to a permitted reader (spec Req 4)."""
    return universe_visibility(universe_id).name


def _reader_has_grant(universe_id: str) -> bool:
    """True when the current caller holds an explicit ACL grant on a universe.

    A granted reader is never limited by anonymous visibility. This checks a
    real ``universe_acl`` row (read/write/admin) for the authenticated actor —
    NOT the "public universes return read" convenience convention.
    """
    from tinyassets.api import permissions

    if not permissions.is_authenticated_request():
        return False
    actor = permissions.current_actor_id()
    if not actor or actor == "anonymous":
        return False
    try:
        from tinyassets.daemon_server import list_universe_acl

        rows = list_universe_acl(_base_path(), universe_id=universe_id)
    except Exception:
        logger.warning(
            "visibility: ACL read failed for universe %r -> no grant assumed",
            universe_id,
            exc_info=True,
        )
        return False
    return any(
        row.get("actor_id") == actor
        and str(row.get("permission") or "") in {"read", "write", "admin"}
        for row in rows
    )


def visibility_permits(universe_id: str, capability: str) -> bool:
    """Whether the current caller may exercise ``capability`` on a universe.

    Structurally tighten-only: the legacy read gate is the ceiling. If
    ``universe_access_allows`` denies the read, this returns ``False`` — the new
    layer can never grant what legacy denies (so an inconsistent row with
    ``public_read=False`` plus a permissive explicit level cannot open a read).
    Within what legacy allows, a granted reader gets full access and every other
    (anonymous / non-granted) reader is bound by the declared level, which is
    ``CLOSED`` for any undeclared universe.
    """
    if capability not in CAPABILITIES:
        raise ValueError(f"unknown visibility capability: {capability!r}")

    from tinyassets.api import permissions

    # Ceiling: legacy read gate. New layer only narrows from here.
    if not permissions.universe_access_allows(universe_id, write=False):
        return False
    if _reader_has_grant(universe_id):
        return True
    return universe_visibility(universe_id).permits(capability)


def _page_declared_visibility(page_meta: dict[str, Any]) -> str:
    """The page's own declared visibility string, or '' if none."""
    if not isinstance(page_meta, dict):
        return ""
    for key in _PAGE_VISIBILITY_KEYS:
        raw = page_meta.get(key)
        if raw not in (None, ""):
            return str(raw).strip()
    return ""


def page_content_permitted(
    page_meta: dict[str, Any], universe_id: str = ""
) -> bool:
    """Whether a single wiki page's *content* may be served to this caller.

    A page narrows — never widens — its universe's content grant. A page that
    declares a restrictive visibility (``private``, ``metadata_only``, an
    unrecognized level, or an explicit ``content: false``) is withheld from any
    reader that is not a *granted* reader of the page's universe (spec Req 3).

    Authentication alone is NOT authority here: a valid user with ordinary wiki
    scope but no universe ACL grant is treated exactly like an anonymous reader,
    so page restrictions cannot be bypassed by merely logging in.
    """
    declared = _page_declared_visibility(page_meta)
    if not declared:
        return True  # no page-level restriction -> defer to the universe gate.

    # A granted reader of the universe is exempt from page-level restriction.
    if _reader_has_grant(universe_id):
        return True

    lowered = declared.lower()
    if lowered in _PAGE_FALSE_VALUES:
        return False  # explicit `content: false`
    level = parse_level(lowered)
    if level is None:
        logger.warning(
            "visibility: unrecognized page visibility %r -> withholding content",
            declared,
        )
        return False  # fail closed for a non-granted reader.
    return level.read_content


def page_visible_in_listing(
    page_meta: dict[str, Any], universe_id: str = ""
) -> bool:
    """Whether a page may appear in a sibling read (search / since / list).

    A restricted page's body, excerpt, title, and path are all disclosure; a
    page withheld from content is withheld from these enumerations too, unless
    the caller is a granted reader. Reuses the same rule as content serving.
    """
    return page_content_permitted(page_meta, universe_id)


def set_universe_visibility(universe_id: str, level: str) -> VisibilityLevel:
    """Declare a universe's explicit visibility level.

    Writes the level into the universe rules metadata (creating the rules row if
    needed) and keeps the legacy ``public_read`` bit consistent so older read
    paths that still consult it behave sensibly.
    """
    resolved = parse_level(level)
    if resolved is None:
        raise ValueError(
            f"unknown visibility level {level!r}; expected one of "
            f"{sorted(LEVELS)}"
        )
    from tinyassets.daemon_server import (
        ensure_universe_rules,
        update_universe_rules,
    )

    base = _base_path()
    ensure_universe_rules(base, universe_id=universe_id)
    # Keep the legacy public_read ceiling consistent: it is True iff the level
    # grants an anonymous reader ANY capability. This makes the legacy gate a
    # correct ceiling for `visibility_permits` (which ANDs with it).
    any_anon_capability = (
        resolved.discover_existence
        or resolved.read_metadata
        or resolved.read_content
    )
    update_universe_rules(
        base,
        universe_id=universe_id,
        updates={
            "public_read": any_anon_capability,
            "metadata": {LEVEL_METADATA_KEY: resolved.name},
        },
    )
    return resolved


def backfill_universe_visibility(
    universe_ids: list[str] | None = None,
) -> dict[str, str]:
    """Declare an explicit level for every universe lacking one.

    Idempotent. For each universe with no explicit ``visibility_level`` yet,
    derive it from the current effective ``public_read`` bit (``True`` ->
    ``public``, ``False`` -> ``private``) so **no universe changes visibility**
    — it only becomes *declared*. This is what makes
    ``TINYASSETS_VISIBILITY_STRICT_UNDECLARED`` safe to switch on afterward:
    an undeclared state then means genuine corruption, and fails closed.

    Returns a map of universe_id -> declared level name for the ones written.
    """
    from tinyassets.daemon_server import (
        ensure_universe_rules,
        get_universe_rules,
    )

    base = _base_path()
    ids = universe_ids if universe_ids is not None else _discover_universe_ids()
    written: dict[str, str] = {}
    for uid in ids:
        uid = (uid or "").strip()
        if not uid:
            continue
        rules = ensure_universe_rules(base, universe_id=uid)
        metadata = rules.get("metadata") if isinstance(rules, dict) else None
        if isinstance(metadata, dict) and metadata.get(LEVEL_METADATA_KEY):
            continue  # already declared -> leave as-is.
        # Re-read to be certain of the current bit, then map to a level.
        current = get_universe_rules(base, universe_id=uid)
        level = PUBLIC if bool(current.get("public_read", True)) else PRIVATE
        set_universe_visibility(uid, level.name)
        written[uid] = level.name
    return written


def _discover_universe_ids() -> list[str]:
    """Best-effort enumeration of on-disk universe ids for backfill."""
    base = _base_path()
    if not base.is_dir():
        return []
    try:
        from tinyassets.api.universe import _is_listable_universe_dir
    except Exception:
        _is_listable_universe_dir = None  # type: ignore[assignment]
    ids: list[str] = []
    for child in sorted(base.iterdir()):
        if _is_listable_universe_dir is not None:
            if not _is_listable_universe_dir(child):
                continue
        elif not child.is_dir() or child.name.startswith("."):
            continue
        ids.append(child.name)
    return ids
