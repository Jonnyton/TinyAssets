"""Git-author identity for daemon and user commits.

Maps the env-var actor to a well-formed ``git`` author line. v1 is
deliberately narrow: no FastMCP request-context threading, no GitHub
verification, no per-branch override. That's a later follow-up.

Resolution order (first hit wins):

1. ``WORKFLOW_GIT_AUTHOR`` env var — verbatim override. The user
   takes responsibility for the format. Useful for "I want my real
   email on these commits, I know what I'm doing" cases.
2. The ``actor`` argument (if truthy) or ``UNIVERSE_SERVER_USER`` env
   var, slugified and wrapped into
   ``Workflow User <slug@users.noreply.workflow.local>``.
3. Fallback slug ``anonymous`` when nothing useful is available.

Using a ``users.noreply.workflow.local`` domain keeps commits
attributable (the slug identifies which actor made the change) without
pretending to be a verified email (users don't own that domain;
GitHub won't match the commit to a profile). The identity scope doc
flagged the unverified-email risk; noreply defuses it.
"""

from __future__ import annotations

import os

from workflow.catalog.layout import slugify

_DISPLAY_NAME = "Workflow User"
_NOREPLY_DOMAIN = "users.noreply.workflow.local"
_ANONYMOUS_SLUG = "anonymous"


def git_author(actor: str | None = None) -> str:
    """Return a git author string suitable for ``git commit --author=…``.

    See module docstring for resolution order.
    """
    override = os.environ.get("WORKFLOW_GIT_AUTHOR", "").strip()
    if override:
        return override

    raw = (actor or os.environ.get("UNIVERSE_SERVER_USER", "") or "").strip()
    slug = slugify(raw, fallback=_ANONYMOUS_SLUG)
    return f"{_DISPLAY_NAME} <{slug}@{_NOREPLY_DOMAIN}>"
