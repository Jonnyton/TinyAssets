"""Preamble engine helpers — extracted from
``tinyassets/universe_server.py`` (Task #8 — decomp Step 10).

The smallest extraction by LOC (~336 moveable) but the **highest
test-monkeypatch-target burden** of the decomposition: 11 ``mock.patch``
sites + 2 ``monkeypatch.setattr`` sites = 13 test-patch interactions
across 5 test files. This module is the foundation that every Step-1-9
submodule lazy-imports from for ledger attribution, storage backend
resolution, error formatting, and upload-whitelist enforcement. After
Step 10, the dependency-graph inversion is complete: engine_helpers.py
is a leaf module with no upstream dependency on universe_server.py.

Public surface (back-compat re-exported via ``tinyassets.universe_server``):
    Upload-whitelist trio:
      _upload_whitelist_prefixes()   - return list[Path] | None from
                                       TINYASSETS_UPLOAD_WHITELIST env var
      _split_whitelist_entry(raw)    - cross-platform path-list split
                                       (handles Windows drive-letter colons)
      _warn_if_no_upload_whitelist() - log warning at module-import time
                                       when the whitelist is unset

    Public action ledger trio:
      _current_actor()               - resolve request auth identity, falling
                                       back to UNIVERSE_SERVER_USER (default
                                       'anonymous'); patched 7+ times in tests
      _append_ledger(udir, action, ..) - durable per-universe ledger writer
      _truncate(text, limit=140)     - whitespace-collapsing string truncator
                                       for ledger summary lines

    Storage + error formatters:
      _storage_backend()             - memoized StorageBackend factory;
                                       patched 4 times in tests
      _format_dirty_file_conflict(exc) - shape DirtyFileError for MCP clients
      _filter_claims_by_branch_visibility(claims, *, viewer) - Phase 6.2.2
                                       private-branch filter for gate claims
      _filter_leaderboard_by_branch_visibility(entries, *, viewer) - sibling
                                       for leaderboard rows
      _format_commit_failed(exc)     - shape CommitFailedError for MCP clients

Cross-module note: `_filter_*_by_branch_visibility` lazy-import
`get_branch_definition` from `tinyassets.daemon_server` at function-body time
(daemon_server is a sibling, not an api/* submodule). All other engine
helpers depend only on `tinyassets.api.helpers._base_path` (top-of-module
import) and `tinyassets.catalog` types (DirtyFileError, CommitFailedError,
get_backend).

The `_warn_if_no_upload_whitelist()` import-time call is intentionally NOT
invoked at engine_helpers.py module load — universe_server.py preserves the
behavior with a lazy-import + invocation at its own module load (Option B
from Step 10 prep §3.5). Otherwise the warning would only fire when
something else imports engine_helpers, missing the at-server-start contract.

Pattern-A2-style leaf inversion: after this extraction, every Steps 1-9
submodule retargets its lazy `from tinyassets.universe_server import _X`
imports to `from tinyassets.api.engine_helpers import _X`. universe_server.py
becomes a pure routing/wrapper module (extensions() body + 6 Pattern A2
wrappers + cross-module shims + main).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tinyassets.api.helpers import _base_path, _read_json
from tinyassets.catalog import CommitFailedError, DirtyFileError, get_backend

logger = logging.getLogger("universe_server.engine_helpers")


# ---------------------------------------------------------------------------
# Upload whitelist — guards add_canon_from_path against arbitrary path reads
# ---------------------------------------------------------------------------


def _upload_whitelist_prefixes() -> list[Path] | None:
    """Return the configured upload whitelist, or ``None`` if unset.

    Reads ``TINYASSETS_UPLOAD_WHITELIST`` at call time (consistent with
    the other behavior-gate flags in this module). Values are split on
    both ``;`` and ``:`` separators, stripped, resolved to absolute
    paths. An unset or empty variable returns ``None`` meaning "no
    whitelist enforcement" — preserving the open-by-default UX the
    host wanted for the demo. ``None`` is NOT the same as an empty
    list (the latter would forbid all uploads).
    """
    raw = os.environ.get("TINYASSETS_UPLOAD_WHITELIST", "").strip()
    if not raw:
        return None
    # Accept both ``:`` (Unix PATH-style) and ``;`` (Windows PATH-style)
    # so the same env-var syntax works on either platform. Drive-letter
    # colons on Windows (``C:``) survive because the path gets split
    # again inside ``_split_whitelist_entry``.
    parts: list[Path] = []
    for entry in _split_whitelist_entry(raw):
        entry = entry.strip()
        if not entry:
            continue
        parts.append(Path(entry).resolve())
    return parts


def _split_whitelist_entry(raw: str) -> list[str]:
    """Split the env var on ``;`` (always) and on ``:`` except when the
    colon is a Windows drive-letter separator (e.g. ``C:\\Users``).
    """
    chunks: list[str] = []
    for semi_chunk in raw.split(";"):
        # A bare ``:`` separator joins two paths; a drive-letter colon
        # has a single letter to its left. Walk the string and split
        # only on the first kind.
        buffer = []
        i = 0
        while i < len(semi_chunk):
            ch = semi_chunk[i]
            if ch == ":":
                # Drive letter iff this is position 1 of the current
                # buffer AND the char before is a single letter AND
                # the char after is a path separator.
                if (
                    len(buffer) == 1
                    and buffer[0].isalpha()
                    and i + 1 < len(semi_chunk)
                    and semi_chunk[i + 1] in ("/", "\\")
                ):
                    buffer.append(ch)
                    i += 1
                    continue
                # Otherwise this colon separates paths.
                chunks.append("".join(buffer))
                buffer = []
                i += 1
                continue
            buffer.append(ch)
            i += 1
        if buffer:
            chunks.append("".join(buffer))
    return chunks


def _warn_if_no_upload_whitelist() -> None:
    """Log a WARNING once at import time if the whitelist is unset.

    Reminds the host that ``add_canon_from_path`` accepts any absolute
    path when ``TINYASSETS_UPLOAD_WHITELIST`` is empty. Best-effort —
    logger failure must never block module import.

    Intentionally NOT invoked at this module's import time. ``universe_server.py``
    invokes it at server-start via lazy-import (Option B from Step 10 prep §3.5)
    so the warning still surfaces at the at-server-start contract instead of
    only when something else imports engine_helpers.
    """
    try:
        if _upload_whitelist_prefixes() is None:
            logger.warning(
                "TINYASSETS_UPLOAD_WHITELIST is unset — add_canon_from_path "
                "will accept any absolute path. Set the env var to a "
                "colon/semicolon-separated list of prefixes to enforce.",
            )
    except Exception:
        # Never let a logger-configuration edge case break import.
        pass


# ---------------------------------------------------------------------------
# Public action ledger
# ---------------------------------------------------------------------------
# PLAN.md Design Decision: "Private chats, public actions." Every universe-
# affecting write must be publicly attributable. The ledger is the durable
# record of who did what, when.


def _current_actor() -> str:
    """Resolve the acting user's identity for ledger attribution.

    Authenticated MCP requests use the OAuth subject resolved at request
    entry. Authless paths and direct tests keep the legacy env-var fallback.
    """
    try:
        from tinyassets.auth.middleware import current_identity

        identity = current_identity()
        subject = (getattr(identity, "user_id", "") or "").strip()
        if subject and subject != "anonymous":
            return subject
    except Exception:
        logger.exception("failed to resolve request auth identity")
    return os.environ.get("UNIVERSE_SERVER_USER", "anonymous")


def _append_ledger(
    udir: Path,
    action: str,
    *,
    actor: str | None = None,
    target: str = "",
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one entry to the universe's public action ledger.

    Designed to never raise: ledger failures are logged but don't abort
    the surrounding write. The mutation has already landed on disk by the
    time this is called, so losing a ledger entry is strictly better than
    rolling back a successful user action.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor or _current_actor(),
        "action": action,
        "target": target,
        "summary": summary,
    }
    if payload:
        entry["payload"] = payload

    ledger_path = udir / "ledger.json"
    try:
        udir.mkdir(parents=True, exist_ok=True)
        existing = _read_json(ledger_path)
        if not isinstance(existing, list):
            existing = []
        existing.append(entry)
        ledger_path.write_text(
            json.dumps(existing, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Failed to append ledger entry at %s: %s", ledger_path, exc)


def _truncate(text: str, limit: int = 140) -> str:
    """Collapse whitespace and truncate for ledger summaries."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Storage backend + error formatters
# ---------------------------------------------------------------------------


def _storage_backend():
    """Resolve the memoized :class:`StorageBackend` for catalog writes.

    Goals + Branches live at repo root per spec §phase7_github_as_catalog
    (`goals/<slug>.yaml`, `branches/<slug>.yaml`). The repo root is
    derived from ``_base_path().parent`` — production points
    ``output/`` at the project root, so its parent IS the git repo
    root. Tests using ``TINYASSETS_DATA_DIR=<tmp_path>/output`` get
    ``<tmp_path>`` as the repo root, which isn't a git repo, so
    ``get_backend`` auto-probes to :class:`SqliteOnlyBackend` and
    leaves the host project repo untouched.
    """
    base = _base_path()
    return get_backend(base, repo_root=base.parent)


def _format_dirty_file_conflict(exc: DirtyFileError) -> dict[str, Any]:
    """Shape a :class:`DirtyFileError` for MCP clients.

    The structured payload lets the chat-side render the conflict as
    actionable options instead of an opaque traceback. Used by Phase 7.3
    write handlers; the formatter is wired separately from the raising
    sites so each handler can keep its existing return-shape idiom.
    """
    paths = [str(p) for p in getattr(exc, "paths", []) or []]
    primary = paths[0] if paths else ""
    return {
        "status": "local_edit_conflict",
        "conflicting_path": primary,
        "all_conflicts": paths,
        "options": [
            "pass force=True to overwrite",
            "commit or stash local edits first",
        ],
    }


def _filter_claims_by_branch_visibility(
    claims: list[dict[str, Any]],
    *,
    viewer: str,
) -> list[dict[str, Any]]:
    """Phase 6.2.2 — hide gate claims whose Branch is private.

    A private Branch's claim is visible only to its author. Public
    Branches are visible to everyone. The Goal's visibility is NOT
    consulted here; private Branch on public Goal is a supported
    product state.

    Branches that have been deleted (no row) are treated as "orphan
    claims" and left in the list — the caller's orphan tagging
    handles that surface separately.
    """
    if not claims:
        return claims
    from tinyassets.daemon_server import get_branch_definition

    visibility_cache: dict[str, tuple[str, str]] = {}
    filtered: list[dict[str, Any]] = []
    for claim in claims:
        bid = claim.get("branch_def_id", "")
        if not bid:
            filtered.append(claim)
            continue
        if bid not in visibility_cache:
            try:
                branch = get_branch_definition(
                    _base_path(), branch_def_id=bid,
                )
                visibility_cache[bid] = (
                    branch.get("visibility", "public") or "public",
                    branch.get("author", "") or "",
                )
            except KeyError:
                # Orphan claim — branch row gone. Keep the claim.
                visibility_cache[bid] = ("public", "")
        branch_visibility, branch_author = visibility_cache[bid]
        if branch_visibility == "private" and branch_author != viewer:
            continue
        filtered.append(claim)
    return filtered


def _filter_leaderboard_by_branch_visibility(
    entries: list[dict[str, Any]],
    *,
    viewer: str,
) -> list[dict[str, Any]]:
    """Phase 6.2.2 — hide leaderboard entries whose Branch is private.

    Same contract as :func:`_filter_claims_by_branch_visibility` but
    operates on leaderboard shape (``branch_def_id`` key present).
    """
    if not entries:
        return entries
    from tinyassets.daemon_server import get_branch_definition

    filtered: list[dict[str, Any]] = []
    for entry in entries:
        bid = entry.get("branch_def_id", "")
        if not bid:
            filtered.append(entry)
            continue
        try:
            branch = get_branch_definition(
                _base_path(), branch_def_id=bid,
            )
        except KeyError:
            filtered.append(entry)
            continue
        visibility = branch.get("visibility", "public") or "public"
        author = branch.get("author", "") or ""
        if visibility == "private" and author != viewer:
            continue
        filtered.append(entry)
    return filtered


def _format_commit_failed(exc: CommitFailedError) -> dict[str, Any]:
    """Shape a :class:`CommitFailedError` for MCP clients.

    SQLite row is retained (Path A — SQLite is the accepted-write
    boundary); YAML is rolled back; the write is queued in
    ``unreconciled_writes`` for a future ``sync_commit`` replay.
    """
    paths = [str(p) for p in getattr(exc, "paths", []) or []]
    return {
        "status": "git_commit_failed",
        "error": "git_commit_failed",
        "helper": exc.helper,
        "git_error": exc.git_error,
        "paths": paths,
        "row_ref": exc.row_ref,
        "note": (
            "SQLite write accepted; git commit failed and was rolled "
            "back. Entry queued in unreconciled_writes for later "
            "sync_commit replay."
        ),
    }
