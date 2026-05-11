"""Git-author identity for daemon and user commits.

Maps the env-var actor to a well-formed ``git`` author line. v1 is
deliberately narrow: no FastMCP request-context threading, no GitHub
verification, no per-branch override. That's a later follow-up.

Resolution order (first hit wins):

1. ``WORKFLOW_GITHUB_AUTHOR_LOGIN`` + ``WORKFLOW_GITHUB_AUTHOR_ID`` —
   request-linked GitHub identity. Emits GitHub's public noreply format,
   which can count for contribution-graph credit when the linked account
   has noreply enabled.
2. ``WORKFLOW_GIT_AUTHOR`` env var — verbatim override. The user
   takes responsibility for the format. Useful for "I want my real
   email on these commits, I know what I'm doing" cases.
3. ``WORKFLOW_GITHUB_USERNAME`` + ``WORKFLOW_GITHUB_USER_ID`` — process
   default GitHub identity for local/dev runs.
4. The ``actor`` argument (if truthy) or ``UNIVERSE_SERVER_USER`` env
   var, slugified and wrapped into
   ``Workflow User <slug@users.noreply.workflow.local>``.
5. Fallback slug ``anonymous`` when nothing useful is available.

Using a ``users.noreply.workflow.local`` domain keeps commits
attributable (the slug identifies which actor made the change) without
pretending to be a verified email (users don't own that domain;
GitHub won't match the commit to a profile). The identity scope doc
flagged the unverified-email risk; noreply defuses it.
"""

from __future__ import annotations

import os
import re

from workflow.catalog.layout import slugify

_DISPLAY_NAME = "Workflow User"
_NOREPLY_DOMAIN = "users.noreply.workflow.local"
_GITHUB_NOREPLY_DOMAIN = "users.noreply.github.com"
_ANONYMOUS_SLUG = "anonymous"
_GITHUB_LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?$")
_GITHUB_ID_RE = re.compile(r"^[1-9][0-9]{0,19}$")


def _github_noreply_author(login: str, user_id: str) -> str | None:
    clean_login = login.strip()
    clean_id = user_id.strip()
    if not _GITHUB_LOGIN_RE.fullmatch(clean_login):
        return None
    if not _GITHUB_ID_RE.fullmatch(clean_id):
        return None
    return f"{clean_login} <{clean_id}+{clean_login}@{_GITHUB_NOREPLY_DOMAIN}>"


def _github_author_from_env(login_var: str, id_var: str) -> str | None:
    login = os.environ.get(login_var, "")
    user_id = os.environ.get(id_var, "")
    if not login.strip() or not user_id.strip():
        return None
    return _github_noreply_author(login, user_id)


def git_author(actor: str | None = None) -> str:
    """Return a git author string suitable for ``git commit --author=…``.

    See module docstring for resolution order.
    """
    request_linked = _github_author_from_env(
        "WORKFLOW_GITHUB_AUTHOR_LOGIN",
        "WORKFLOW_GITHUB_AUTHOR_ID",
    )
    if request_linked:
        return request_linked

    override = os.environ.get("WORKFLOW_GIT_AUTHOR", "").strip()
    if override:
        return override

    process_linked = _github_author_from_env(
        "WORKFLOW_GITHUB_USERNAME",
        "WORKFLOW_GITHUB_USER_ID",
    )
    if process_linked:
        return process_linked

    raw = (actor or os.environ.get("UNIVERSE_SERVER_USER", "") or "").strip()
    slug = slugify(raw, fallback=_ANONYMOUS_SLUG)
    return f"{_DISPLAY_NAME} <{slug}@{_NOREPLY_DOMAIN}>"
