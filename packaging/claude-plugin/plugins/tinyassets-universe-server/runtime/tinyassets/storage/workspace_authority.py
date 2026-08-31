"""The two authority facts the workspace sink needs, and their grammar.

A connection SCOPE says what the deposited credential may do: an http connection's
scopes are its HTTP verbs, and a git one carries ``git_read:owner/name`` or
``git_write:owner/name`` bound to exactly one repository on exactly one host
(``github.com`` in this slice; the sink is host-agnostic later). A typed CONSENT
says the universe's owner agreed to this kind of work on that repository at all -
``workspace_checkout``, ``workspace_push``, ``workspace_provision``, recorded per
universe by :mod:`tinyassets.storage.effector_consents` under a destination this
module spells. Both gates are required and neither substitutes for the other: a
scope without a consent is a credential nobody approved using, and a consent
without a scope is an approval with no credential behind it.

The grammar lives here, away from the ledger, because three surfaces have to
agree on it letter for letter - the request rail that asks for it, the ledger
that stores it, and the sink that checks it - and a scope that means one thing at
the ask and another at the check is the whole class of bug this prevents.

A git scope is NOT an HTTP verb. The proxy's authorization is a membership test
against the same ``scopes`` tuple, so ``is_git_scope`` exists to keep a git scope
from ever being accepted as a verb.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

#: Scope kinds. ``git_read`` is checkout, ``git_write`` is push.
GIT_SCOPE_READ = "git_read"
GIT_SCOPE_WRITE = "git_write"
GIT_SCOPE_KINDS = (GIT_SCOPE_READ, GIT_SCOPE_WRITE)

#: The one host a git scope may bind to in this slice.
GIT_SCOPE_HOST = "github.com"

#: The effector-consent sink the workspace operations record under.
WORKSPACE_SINK = "workspace"

#: The typed consents, and the operation each one authorizes.
CONSENT_CHECKOUT = "workspace_checkout"
CONSENT_PUSH = "workspace_push"
CONSENT_PROVISION = "workspace_provision"
WORKSPACE_CONSENTS = (CONSENT_CHECKOUT, CONSENT_PUSH, CONSENT_PROVISION)
CONSENT_OPERATIONS = {
    CONSENT_CHECKOUT: "checkout",
    CONSENT_PUSH: "push",
    CONSENT_PROVISION: "provision",
}

#: An owner or repository name. Deliberately NOT a general path segment: it ends
#: up in a scope string, a consent destination and a canonical URL.
_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,100}")
#: A dot-run is a traversal wherever this string is later split on "/".
_DOTS_ONLY_RE = re.compile(r"[.]+")


class GitScopeError(ValueError):
    """A scope or repository that cannot be stored as written.

    A ``ValueError``: the caller handed over something malformed, which is a
    refusal to report, not a state to recover from.
    """


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def parse_repo(repo: Any) -> tuple[str, str]:
    """``"owner/name"`` -> ``("owner", "name")``, or raise.

    Refuses a ``.git`` suffix (``owner/name.git`` and ``owner/name`` are the same
    repository and must not be two different scopes), any second slash, a
    dot-only segment, and anything outside ``[A-Za-z0-9._-]``.
    """
    raw = _text(repo)
    if not raw:
        raise GitScopeError("repo is required as owner/name")
    parts = raw.split("/")
    if len(parts) != 2:
        raise GitScopeError(f"repo {raw!r} must be exactly owner/name")
    owner, name = parts
    if name.lower().endswith(".git"):
        raise GitScopeError(
            f"repo {raw!r} must not carry a .git suffix: owner/name and "
            "owner/name.git would bind as two different scopes"
        )
    for label, part in (("owner", owner), ("name", name)):
        if not _NAME_RE.fullmatch(part):
            raise GitScopeError(
                f"{label} {part!r} must be 1-100 chars of [A-Za-z0-9._-]"
            )
        if _DOTS_ONLY_RE.fullmatch(part):
            raise GitScopeError(f"{label} {part!r} is a path traversal")
    return owner, name


def normalize_repo(repo: Any) -> str:
    """The canonical ``owner/name``, validated."""
    owner, name = parse_repo(repo)
    return f"{owner}/{name}"


def format_git_scope(kind: Any, repo: Any) -> str:
    """``("git_read", "o/n")`` -> ``"git_read:o/n"``, validated."""
    normalized_kind = _text(kind).lower()
    if normalized_kind not in GIT_SCOPE_KINDS:
        raise GitScopeError(
            f"git scope kind must be one of {GIT_SCOPE_KINDS}, got {kind!r}"
        )
    return f"{normalized_kind}:{normalize_repo(repo)}"


def is_git_scope(value: Any) -> bool:
    """True for anything SHAPED like a git scope, valid or not.

    The bare kind counts. This is the predicate the HTTP verb checks use, and a
    verb named ``git_read`` must be refused whether or not it would parse.
    """
    text = _text(value)
    if not text:
        return False
    head = text.split(":", 1)[0].lower()
    return head in GIT_SCOPE_KINDS


def parse_git_scope(value: Any) -> tuple[str, str] | None:
    """``"git_read:o/n"`` -> ``("git_read", "o/n")``; None if it is not a VALID
    git scope. Never raises - use :func:`require_git_scope` for the reason."""
    try:
        return require_git_scope(value)
    except GitScopeError:
        return None


def require_git_scope(value: Any) -> tuple[str, str]:
    """``"git_read:o/n"`` -> ``("git_read", "o/n")``, or raise with the reason."""
    text = _text(value)
    kind, separator, repo = text.partition(":")
    kind = kind.lower()
    if kind not in GIT_SCOPE_KINDS or not separator:
        raise GitScopeError(
            f"{value!r} is not a git scope; expected "
            f"git_read:owner/name or git_write:owner/name"
        )
    return kind, normalize_repo(repo)


def _is_github_host(host: Any) -> bool:
    text = _text(host).lower().rstrip(".")
    return text == GIT_SCOPE_HOST or text.endswith("." + GIT_SCOPE_HOST)


def connection_hosts(connection: Any) -> tuple[str, ...]:
    """The hosts a connection's declared endpoints reach. Empty for a pipe."""
    endpoints = getattr(connection, "allowed_endpoints", ()) or ()
    return tuple(_text(getattr(endpoint, "host", "")).lower() for endpoint in endpoints)


def endpoints_allow_git_scopes(hosts: Iterable[str], provider: Any = "") -> bool:
    """Whether a connection with these endpoint hosts may carry a git scope.

    Every declared endpoint must be on ``github.com``: a connection that can also
    reach elsewhere would be lending the same credential to another host under a
    git-shaped name. A connection with NO declared endpoints qualifies only when
    its provider IS github - that is the OAuth pipe, whose destination is a
    github repository by construction.
    """
    host_list = [_text(host).lower() for host in hosts]
    if host_list:
        return all(_is_github_host(host) for host in host_list)
    return _text(provider).lower() == "github"


def connection_allows_git_scopes(connection: Any) -> bool:
    """:func:`endpoints_allow_git_scopes` for a stored connection object."""
    return endpoints_allow_git_scopes(
        connection_hosts(connection), getattr(connection, "provider", "")
    )


def validate_git_scopes(
    scopes: Iterable[Any], *, hosts: Iterable[str] = (), provider: Any = ""
) -> None:
    """Raise unless every git-shaped scope is well formed and legal here.

    Called at every write of a scope tuple, so no stored row can carry a git
    scope on a connection that is not provably a github one - the check cannot
    be skipped by a caller that assembles its own tuple.
    """
    git_scopes = [scope for scope in scopes if is_git_scope(scope)]
    if not git_scopes:
        return
    for scope in git_scopes:
        require_git_scope(scope)
    if not endpoints_allow_git_scopes(hosts, provider):
        raise GitScopeError(
            "a git scope needs a connection whose declared endpoints are all on "
            f"{GIT_SCOPE_HOST} (or a github pipe with none); "
            f"got {sorted(set(_text(host).lower() for host in hosts)) or 'no endpoints'}"
        )


def connection_git_scopes(connection: Any) -> set[tuple[str, str]]:
    """The ``(kind, "owner/name")`` pairs a connection carries.

    A malformed stored scope is dropped rather than raised on: this is the read
    the sink makes on every checkout, and one bad row must not take the whole
    connection out. It grants nothing, which is the fail-closed direction.
    """
    found: set[tuple[str, str]] = set()
    for scope in getattr(connection, "scopes", ()) or ():
        parsed = parse_git_scope(scope)
        if parsed is not None:
            found.add(parsed)
    return found


def has_git_scope(connection: Any, kind: Any, repo: Any) -> bool:
    """Whether ``connection`` may do ``kind`` on exactly ``repo``.

    Exact binding: ``git_read:owner/name`` does not grant ``owner/name2``, and a
    revoked connection grants nothing.
    """
    if connection is None or getattr(connection, "revoked_at", None) is not None:
        return False
    normalized_kind = _text(kind).lower()
    if normalized_kind not in GIT_SCOPE_KINDS:
        return False
    try:
        normalized_repo = normalize_repo(repo)
    except GitScopeError:
        return False
    if not connection_allows_git_scopes(connection):
        return False
    return (normalized_kind, normalized_repo) in connection_git_scopes(connection)


def workspace_consent_destination(
    consent: Any, repo: Any, *, host: str = GIT_SCOPE_HOST
) -> str:
    """The ``effector_consents`` destination for one operation on one repo.

    ``("workspace_checkout", "o/n")`` -> ``"checkout:github.com/o/n"``. One
    spelling, in one place, because the rail writes it and the sink reads it.
    """
    text = _text(consent).lower()
    operation = CONSENT_OPERATIONS.get(text, text)
    if operation not in CONSENT_OPERATIONS.values():
        raise GitScopeError(
            f"consent must be one of {WORKSPACE_CONSENTS}, got {consent!r}"
        )
    return f"{operation}:{_text(host).lower()}/{normalize_repo(repo)}"


def parse_workspace_consent_destination(destination: Any) -> dict[str, str] | None:
    """The inverse, for the inventory surface. None when it is not one of ours."""
    text = _text(destination)
    operation, separator, rest = text.partition(":")
    if not separator or operation not in CONSENT_OPERATIONS.values():
        return None
    host, _, repo = rest.partition("/")
    try:
        normalized_repo = normalize_repo(repo)
    except GitScopeError:
        return None
    consent = next(
        name for name, op in CONSENT_OPERATIONS.items() if op == operation
    )
    return {
        "consent": consent,
        "operation": operation,
        "host": host.lower(),
        "repo": normalized_repo,
    }


__all__ = [
    "CONSENT_CHECKOUT",
    "CONSENT_OPERATIONS",
    "CONSENT_PROVISION",
    "CONSENT_PUSH",
    "GIT_SCOPE_HOST",
    "GIT_SCOPE_KINDS",
    "GIT_SCOPE_READ",
    "GIT_SCOPE_WRITE",
    "GitScopeError",
    "WORKSPACE_CONSENTS",
    "WORKSPACE_SINK",
    "connection_allows_git_scopes",
    "connection_git_scopes",
    "connection_hosts",
    "endpoints_allow_git_scopes",
    "format_git_scope",
    "has_git_scope",
    "is_git_scope",
    "normalize_repo",
    "parse_git_scope",
    "parse_repo",
    "parse_workspace_consent_destination",
    "require_git_scope",
    "validate_git_scopes",
    "workspace_consent_destination",
]
