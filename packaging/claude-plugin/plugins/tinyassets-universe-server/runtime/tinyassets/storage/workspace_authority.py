"""The two authority facts the workspace sink needs, and their grammar.

A connection SCOPE says what the deposited credential may do: an http connection's
scopes are its HTTP verbs, and a git one carries ``git_read:owner/name`` or
``git_write:owner/name`` bound to exactly one repository on exactly one host --
**the host that connection declares**, whatever it is. GitHub, GitLab, Gitea, a
self-hosted forge: the platform never names one. A typed CONSENT
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

#: Providers whose OAuth pipe implies exactly one host even with no declared
#: endpoints. This is NOT a list of hosts git scopes may use -- any host a
#: connection declares works. It exists only because a pipe connection has no
#: endpoint list to read the host off, so the provider has to supply it.
PROVIDER_PIPE_HOSTS = {"github": "github.com"}

#: Forges that serve their API and their git transport on DIFFERENT hosts.
#:
#: A connection declares the host it makes API calls to. For most forges -- a
#: self-hosted Gitea, an internal GitLab -- that is also the host git clones
#: from, and this table is empty for them by design: the pass-through default
#: is what keeps a workspace forge-agnostic.
#:
#: GitHub is the exception, and it cost a live run to find. The founder's
#: connection declares ten endpoints, all ``api.github.com``, so the derived
#: git host was ``api.github.com`` and the clone became
#: ``https://api.github.com/owner/name.git`` -- which GitHub answers 403. The
#: same wrong value was also written into the consent key, so the owner's
#: perfectly good ``github.com`` consent looked missing.
#:
#: A TABLE, not a heuristic. "Strip the api. prefix" happens to work for GitHub
#: and is wrong for GitLab, whose API lives at ``gitlab.com/api/v4`` on the very
#: same host. An explicit fact about one forge is honest; a rule inferred from
#: one example is how the platform ends up shaped like our demo again.
FORGE_GIT_HOSTS = {"api.github.com": "github.com"}

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
#: A connection id, as it appears inside a consent destination.
_CONNECTION_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,200}")


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


def _normalize_host(host: Any) -> str:
    return _text(host).lower().rstrip(".")


def connection_hosts(connection: Any) -> tuple[str, ...]:
    """The hosts a connection's declared endpoints reach. Empty for a pipe."""
    endpoints = getattr(connection, "allowed_endpoints", ()) or ()
    return tuple(_text(getattr(endpoint, "host", "")).lower() for endpoint in endpoints)


def git_host_for_endpoints(hosts: Iterable[str], provider: Any = "") -> str:
    """The ONE host a git scope on these endpoints binds to, or ``""``.

    ``git_read:owner/name`` names a repository, and a repository only means
    something together with a host. The connection supplies it: every declared
    endpoint must be on the SAME host, and that host is the answer. Two hosts is
    not "pick one" - the scope would be ambiguous, and honouring it would lend
    one credential to whichever host the caller preferred, which is the thing a
    scope exists to stop.

    Which host it is, is none of the platform's business. github.com, an
    internal GitLab, a Gitea box: a workspace is workflow- and channel-agnostic,
    and pinning our own demo's host here is what stopped every other forge from
    working at all.

    A connection with NO declared endpoints is a provider pipe; only a provider
    in :data:`PROVIDER_PIPE_HOSTS` can say what its host is.
    """
    host_list = [_normalize_host(host) for host in hosts if _normalize_host(host)]
    if host_list:
        unique = set(host_list)
        if len(unique) != 1:
            return ""
        # The declared host is where the connection makes API CALLS. Git may
        # live somewhere else on the same forge; unknown hosts pass straight
        # through, which is what keeps every other forge working.
        return FORGE_GIT_HOSTS.get(host_list[0], host_list[0])
    return PROVIDER_PIPE_HOSTS.get(_text(provider).lower(), "")


def endpoints_allow_git_scopes(hosts: Iterable[str], provider: Any = "") -> bool:
    """Whether a connection with these endpoint hosts may carry a git scope."""
    return bool(git_host_for_endpoints(hosts, provider))


def connection_git_host(connection: Any) -> str:
    """The one git host a stored connection binds its scopes to, or ``""``.

    The single source for "which host": the sink's transport, the consent
    destination the rail writes, and the inventory the agent reads all take it
    from here, so none of them can spell a different one.
    """
    return git_host_for_endpoints(
        connection_hosts(connection), getattr(connection, "provider", "")
    )


def connection_allows_git_scopes(connection: Any) -> bool:
    """:func:`git_host_for_endpoints` for a stored connection object."""
    return bool(connection_git_host(connection))


def validate_git_scopes(
    scopes: Iterable[Any], *, hosts: Iterable[str] = (), provider: Any = ""
) -> None:
    """Raise unless every git-shaped scope is well formed and legal here.

    Called at every write of a scope tuple, so no stored row can carry a git
    scope on a connection whose host is ambiguous - the check cannot be skipped
    by a caller that assembles its own tuple. "Ambiguous", not "not github":
    the forge is the connection's to name.
    """
    git_scopes = [scope for scope in scopes if is_git_scope(scope)]
    if not git_scopes:
        return
    for scope in git_scopes:
        require_git_scope(scope)
    if not endpoints_allow_git_scopes(hosts, provider):
        raise GitScopeError(
            "a git scope needs a connection whose declared endpoints are all on "
            "ONE host (any host), or a provider pipe that names one; got "
            f"{sorted(set(_normalize_host(host) for host in hosts)) or 'no endpoints'}"
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


def require_connection_token(connection_id: Any) -> str:
    """One safe token: a connection id that is about to key a consent row.

    It sits between two ``:`` separators in the destination, so a value carrying
    a colon or a slash would make the row ambiguous to parse and could forge a
    different repository's key.
    """
    text = _text(connection_id)
    if not text or not _CONNECTION_ID_RE.fullmatch(text):
        raise GitScopeError(
            f"connection_id must be 1-200 chars of [A-Za-z0-9._-], got "
            f"{connection_id!r}"
        )
    return text


def workspace_consent_destination(
    consent: Any, repo: Any, *, connection_id: Any, host: str
) -> str:
    """The ``effector_consents`` destination for one operation on one repo
    through ONE connection.

    ``("workspace_checkout", "o/n", connection_id="http_ab",
    host="github.com")`` -> ``"checkout:http_ab:github.com/o/n"``. One spelling,
    in one place, because the rail writes it and the sink reads it.

    ``host`` is REQUIRED, with no default. It used to default to github.com
    while the sink passed the host it derived from the connection, so a consent
    granted for a repository on any other forge was written at a key the sink
    would never look up - the grant appeared to work and authorized nothing.
    Both sides now take it from :func:`connection_git_host`.

    The connection is IN the key, not merely checked when the consent is
    granted: the delta binds a typed consent to ``(connection, repo)``, and a
    universe can hold more than one connection to the same host - a second key
    deposited under another destination label. Keying on the repository alone
    would let a consent given for one credential authorize work under another.
    """
    text = _text(consent).lower()
    operation = CONSENT_OPERATIONS.get(text, text)
    if operation not in CONSENT_OPERATIONS.values():
        raise GitScopeError(
            f"consent must be one of {WORKSPACE_CONSENTS}, got {consent!r}"
        )
    token = require_connection_token(connection_id)
    normalized_host = _normalize_host(host)
    if not normalized_host:
        raise GitScopeError("a workspace consent destination needs the connection's host")
    return f"{operation}:{token}:{normalized_host}/{normalize_repo(repo)}"


def parse_workspace_consent_destination(destination: Any) -> dict[str, str] | None:
    """The inverse, for the inventory surface. None when it is not one of ours."""
    text = _text(destination)
    operation, separator, rest = text.partition(":")
    if not separator or operation not in CONSENT_OPERATIONS.values():
        return None
    connection_id, separator, address = rest.partition(":")
    if not separator:
        return None
    try:
        token = require_connection_token(connection_id)
    except GitScopeError:
        return None
    host, _, repo = address.partition("/")
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
        "connection_id": token,
        "host": host.lower(),
        "repo": normalized_repo,
    }


__all__ = [
    "CONSENT_CHECKOUT",
    "CONSENT_OPERATIONS",
    "CONSENT_PROVISION",
    "CONSENT_PUSH",
    "GIT_SCOPE_KINDS",
    "GIT_SCOPE_READ",
    "GIT_SCOPE_WRITE",
    "GitScopeError",
    "WORKSPACE_CONSENTS",
    "WORKSPACE_SINK",
    "PROVIDER_PIPE_HOSTS",
    "connection_allows_git_scopes",
    "connection_git_host",
    "connection_git_scopes",
    "connection_hosts",
    "endpoints_allow_git_scopes",
    "git_host_for_endpoints",
    "format_git_scope",
    "has_git_scope",
    "is_git_scope",
    "normalize_repo",
    "parse_git_scope",
    "parse_repo",
    "parse_workspace_consent_destination",
    "require_connection_token",
    "require_git_scope",
    "validate_git_scopes",
    "workspace_consent_destination",
]
