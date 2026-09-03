"""Git-author identity for daemon and user commits.

Maps the env-var actor to a well-formed ``git`` author line. v1 is
deliberately narrow: no FastMCP request-context threading, no GitHub
verification, no per-branch override. That's a later follow-up.

Resolution order (first hit wins):
1. ``TINYASSETS_GIT_AUTHOR`` env var — verbatim override. The user
   takes responsibility for the format. Useful for "I want my real
   email on these commits, I know what I'm doing" cases.
2. The ``actor`` argument (if truthy), else the authenticated request
   identity, slugified and wrapped into
   ``TinyAssets User <slug@users.noreply.tinyassets.local>``.

There is no fallback: with no actor and no bound identity the commit has
no author and this raises (founder, 2026-09-02: no synthetic principal).

Using a ``users.noreply.tinyassets.local`` domain keeps commits
attributable (the slug identifies which actor made the change) without
pretending to be a verified email (users don't own that domain;
GitHub won't match the commit to a profile). The identity scope doc
flagged the unverified-email risk; noreply defuses it.
"""

from __future__ import annotations

import os

from tinyassets.catalog.layout import slugify

_DISPLAY_NAME = "TinyAssets User"
_NOREPLY_DOMAIN = "users.noreply.tinyassets.local"


def git_author(actor: str | None = None) -> str:
    """Return a git author string suitable for ``git commit --author=…``.

    See module docstring for resolution order.
    """
    override = os.environ.get("TINYASSETS_GIT_AUTHOR", "").strip()
    if override:
        return override

    raw = (actor or "").strip()
    if not raw:
        from tinyassets.auth.middleware import current_identity_or_none

        identity = current_identity_or_none()
        raw = (getattr(identity, "user_id", "") or "").strip() if identity else ""
    slug = slugify(raw, fallback="")
    if not slug:
        raise PermissionError("a git author needs an authenticated actor")
    return f"{_DISPLAY_NAME} <{slug}@{_NOREPLY_DOMAIN}>"
