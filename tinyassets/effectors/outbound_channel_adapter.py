"""Single-call outbound channels expressed as general ``http`` connections.

Channel-agnostic-outbound tracks 2 + 5: instead of a bespoke module per channel,
Slack ``chat.postMessage`` and X/Twitter ``POST /2/tweets`` each become a request
that the general credential-blind SSRF-hardened driver
(``storage/outbound_connections``) sends through a vault ``http`` credential + an
``OutboundEndpoint`` allowlist. Auth is applied INSIDE the broker child from the
connection's bundle (Bearer bot token for Slack; OAuth 1.0a signature for X) —
this module is credential-blind and only shapes the request.

The migration ORACLES are ``effectors/slack_transport.py`` and
``effectors/twitter_post.py``; the request builders here reproduce their
BYTE-IDENTICAL normalized wire request (endpoint, method, body, non-auth headers),
proven by the differential tests in ``tests/test_outbound_channel_migration.py``.
The oracles stay in place, each behind a per-channel readiness flag, until parity
is proven and the universe is atomically cut over — never two credential paths
live.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from typing import Any

from tinyassets.storage.outbound_connections import (
    ConnectionSecretBundle,
    OutboundEndpoint,
    SsrfValidationError,
    _github_repository_from_destination,
    _parse_allowed_endpoints,
    _SsrfHardenedHttpDriver,
)

#: One ASCII owner/repo pair. ``_github_repository_from_destination`` validates the
#: destination with ``re``'s Unicode ``\w``, but the allowlist compares template
#: literals as ASCII strings — so the two grammars must agree or a Unicode
#: confusable could parse as one repo yet fail the literal segment validator
#: (Codex). This ASCII re-check pins the derived ``owner/repo`` to the byte
#: alphabet the matcher uses, failing closed with a clear error otherwise.
_GH_ASCII_OWNER_REPO_RE = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")

# --- Slack ------------------------------------------------------------------ #
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
#: The connection allowlist entry a Slack ``http`` connection must carry.
SLACK_ALLOWED_ENDPOINT: dict[str, Any] = {
    "host": "slack.com",
    "path_template": "/api/chat.postMessage",
    "methods": ["POST"],
}
#: Per-channel readiness flag: until truthy, Slack keeps posting through the
#: legacy ``slack_transport`` effector (no dual credential path).
SLACK_VIA_CONNECTION_FLAG = "TINYASSETS_SLACK_OUTBOUND_VIA_CONNECTION"

# --- X / Twitter ------------------------------------------------------------ #
TWITTER_TWEETS_URL = "https://api.x.com/2/tweets"
TWITTER_ALLOWED_ENDPOINT: dict[str, Any] = {
    "host": "api.x.com",
    "path_template": "/2/tweets",
    "methods": ["POST"],
}
TWITTER_VIA_CONNECTION_FLAG = "TINYASSETS_TWITTER_OUTBOUND_VIA_CONNECTION"


def slack_http_request(*, channel: str, text: str, thread_ts: str = "") -> dict[str, Any]:
    """The Slack ``chat.postMessage`` call as an ``http``-connection request.

    Byte-identical to ``slack_transport._post``: the body is ``json.dumps(payload)``
    with the stdlib's DEFAULT separators (``", "`` / ``": "``). The general driver's
    dict-body auto-encoding uses COMPACT separators, so we pass a pre-encoded string
    to reproduce Slack's spaced form exactly, and set ``Content-Type`` explicitly.
    The Bearer bot token is applied in the broker child (``auth_scheme="bearer"``).
    """
    payload: dict[str, Any] = {"channel": channel, "text": text}
    if isinstance(thread_ts, str) and thread_ts.strip():
        payload["thread_ts"] = thread_ts.strip()
    return {
        "url": SLACK_POST_MESSAGE_URL,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(payload),
    }


def twitter_http_request(
    *, text: str, reply_to_tweet_id: str = "", quote_tweet_id: str = ""
) -> dict[str, Any]:
    """The X/Twitter ``POST /2/tweets`` call as an ``http``-connection request.

    Byte-identical to ``twitter_post._post_tweet``: COMPACT JSON body and the same
    ``Accept``/``Content-Type``/``User-Agent`` headers. The OAuth 1.0a
    ``Authorization`` is signed in the broker child from the ``oauth1a`` bundle —
    never here (the adapter never sees the four OAuth secrets).
    """
    body: dict[str, Any] = {"text": text}
    if reply_to_tweet_id:
        body["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
    if quote_tweet_id:
        body["quote_tweet_id"] = quote_tweet_id
    return {
        "url": TWITTER_TWEETS_URL,
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "tinyassets-twitter-post-effector/1.0",
        },
        "body": json.dumps(body, separators=(",", ":")),
    }


# --- GitHub pull-request flow ---------------------------------------------- #
# Channel-agnostic-outbound track 3 (design.md D6). GitHub is a MULTI-CALL
# TRANSACTION (blobs -> tree -> commit -> ref -> PR, plus reads), unlike the
# single-call Slack/Twitter channels. Each of its ``api.github.com`` PR-flow
# calls is expressed here as a credential-blind ``http``-connection request that
# reproduces ``effectors/github_pr.py``'s EXACT wire construction byte-for-byte.
#
# The migration ORACLE is ``github_pr``'s own request construction:
#   * ``_github_api_request`` (github_pr.py:1084) — POST create + labels.
#   * ``_git_data_api``       (github_pr.py:1107) — the Git Data reads/writes.
# BOTH encode the body with the stdlib's DEFAULT (spaced) ``json.dumps`` and
# carry the SAME five headers. The general driver's dict-body auto-encoding uses
# COMPACT separators, so — exactly like the Slack builder — every POST builder
# here passes a PRE-ENCODED default-``json.dumps`` string body and sets
# ``Content-Type`` explicitly, so the wire bytes match github_pr's. GET reads
# carry no body but still send ``Content-Type: application/json`` (github_pr's
# helpers set all five headers unconditionally). ``Authorization: Bearer
# <token>`` is applied INSIDE the broker child from the connection bundle
# (``auth_scheme="bearer"``) — these builders are CREDENTIAL-BLIND and never
# emit it.
#
# CREDENTIAL-BLINDNESS + parity is proven by the differential tests in
# ``tests/test_outbound_channel_migration.py``, which drive github_pr's REAL
# request construction end-to-end (``_materialize_branch`` /
# ``_invoke_github_api_pr_create`` / ``_fetch_file_at_ref``) against a loopback
# recorder and assert every builder here produces the identical wire request,
# AND (slice 2B) run github_pr's OWN dispatch flag-OFF vs flag-ON against the same
# loopback, asserting the wire request AND the parsed result / error shapes match.
#
# SLICE 2B: :func:`github_send_via_connection` routes github_pr's
# ``_github_api_request``/``_git_data_api`` (and the broker's ``read_for_commit``)
# through the SSRF-hardened driver + :func:`github_allowed_endpoints`, but ONLY
# when ``TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION`` is truthy. It stays DARK: the
# flag defaults off, and flag-off runs github_pr's legacy raw-urllib path verbatim.
GITHUB_API_BASE = "https://api.github.com"

#: Per-channel readiness flag: until truthy, GitHub keeps pushing PRs through
#: the legacy ``github_pr`` effector (no dual credential path). DARK in slice 1.
GITHUB_VIA_CONNECTION_FLAG = "TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION"

#: The five headers github_pr sends on EVERY api.github.com call, minus
#: ``Authorization`` (added in the broker child from the bearer bundle). Copied
#: verbatim from ``_github_api_request``/``_git_data_api`` (github_pr.py:1095).
_GITHUB_HEADERS: dict[str, str] = {
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "User-Agent": "tinyassets-github-pr-effector/1.0",
    "X-GitHub-Api-Version": "2022-11-28",
}

#: A 40-hex (SHA-1) or 64-hex (SHA-256) git object id, as one path segment.
_GH_SHA = r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})"
#: One repo-relative CONTENTS path segment: unreserved URL chars or a legal
#: ``%XX`` escape. github_pr url-quotes the contents path with ``safe="/"``, so a
#: segment is only ``[A-Za-z0-9._~-]`` plus percent-escapes, and the ``/``
#: separators survive. Encoded separators (``%2e``/``%2f``/``%5c``), ``%25``,
#: control and overlong bytes are ALREADY rejected on the concrete URL by
#: ``_reject_unsafe_encoded_path`` before this pattern runs, so a ``%XX`` here is a
#: safe byte only.
_GH_CONTENTS_SEG = r"(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})+"
#: A repo-relative contents path as a multi-segment ``{path+}`` rest tail:
#: one-or-more segments joined by ``/`` (the ``/`` here is the tail JOIN produced
#: by the matcher, never an encoded separator). Covers root files (``README.md``)
#: and subdirectory files (``src/pkg/module.py``).
_GH_CONTENTS_REST = rf"{_GH_CONTENTS_SEG}(?:/{_GH_CONTENTS_SEG})*"
#: One git branch-ref segment. github_pr leaves branch refs UNQUOTED, so the raw
#: name is on the wire; the class covers every ref github_pr reads (``main``/
#: ``master`` base branches, the enforced head ``tinyassets/cloud-<24hex>``,
#: ``feat/x``-style base branches) PLUS the git-legal ``+`` (e.g. ``release+hotfix``
#: — a parity case Codex flagged). Still far tighter than git check-ref-format:
#: ``@{`` is excluded (no ``@``/``{``), the git-forbidden ``~^:?*[\`` + space +
#: control are excluded, ``.``/``..``/empty segments are rejected by the matcher,
#: and there is no leading/trailing slash. ``.lock``-suffixed refs never occur in
#: this flow. Widening the ref VALUE only is safe: the owner/repo LITERALS pin the
#: destination, so a ref can never traverse ``/repos/<owner>/<repo>/git/ref/heads/``.
_GH_REF_SEG = r"[A-Za-z0-9._+-]+"
#: A git branch-ref name as a multi-segment ``{ref+}`` rest tail.
_GH_REF_REST = rf"{_GH_REF_SEG}(?:/{_GH_REF_SEG})*"
#: The contents ``?ref=`` value (``parse_qsl``-decoded): a branch/tag ref name.
#: Same shape as a ref tail (a slash-bearing ``feat/x`` decodes from ``feat%2Fx``);
#: it is a git ref interpreted by the API, never a URL path, so it cannot traverse
#: the destination-bound ``/repos/<owner>/<repo>/contents/`` prefix.
_GH_REF_QUERY = _GH_REF_REST


def github_allowed_endpoints(destination: str) -> tuple[OutboundEndpoint, ...]:
    """The api.github.com egress allowlist for ONE repository (Codex finding 2).

    DESTINATION-BOUND: ``owner``/``repo`` are baked in as path LITERALS derived
    from the connection's ``destination`` EXACTLY as the credential-blind broker
    does (``_github_repository_from_destination`` — lower-cased, single repository,
    ``[\\w.-]+/[\\w.-]+``, ``.``/``..`` rejected). A token scoped to ``acme/widget``
    can therefore ONLY egress to ``/repos/acme/widget/*`` — there is no
    ``{owner}``/``{repo}`` placeholder that could expand to a different account
    (the slice-1 allowlist's ``[\\w.-]+`` placeholders permitted ANY repo, the hole
    Codex flagged as REQUIRED-to-close before flip). Literal template segments are
    byte-compared by the matcher, so the owner/repo are NOT regex-escaped — they
    are already constrained to ``[\\w.-]`` and re-validated by
    ``_validate_path_template``. Variable-depth tails (subdir contents, slash
    branch refs) use the SSRF-safe ``{name+}`` rest placeholder (slice 2A). Built
    through the storage validator, so the returned allowlist is provably one
    ``create_connection`` would accept (fail-loud if any template/pattern invalid).
    """
    owner_repo = _github_repository_from_destination(destination)
    if _GH_ASCII_OWNER_REPO_RE.fullmatch(owner_repo) is None:
        # Defence-in-depth (Codex): the destination validator uses Unicode ``\w``;
        # the allowlist compares ASCII literals. Refuse anything the byte matcher
        # could not represent rather than build an endpoint that can never match.
        raise SsrfValidationError("github destination is not an ASCII owner/repo")
    base = f"/repos/{owner_repo}"
    return _parse_allowed_endpoints(
        [
            {  # PR create — github_pr.py:1789
                "host": "api.github.com",
                "path_template": f"{base}/pulls",
                "methods": ["POST"],
            },
            {  # Add labels — github_pr.py:1806
                "host": "api.github.com",
                "path_template": f"{base}/issues/{{pr_number}}/labels",
                "methods": ["POST"],
                "param_patterns": {"pr_number": r"[0-9]+"},
            },
            {  # Blob create — github_pr.py:1466
                "host": "api.github.com",
                "path_template": f"{base}/git/blobs",
                "methods": ["POST"],
            },
            {  # Tree create — github_pr.py:1488
                "host": "api.github.com",
                "path_template": f"{base}/git/trees",
                "methods": ["POST"],
            },
            {  # Commit create — github_pr.py:1504
                "host": "api.github.com",
                "path_template": f"{base}/git/commits",
                "methods": ["POST"],
            },
            {  # Ref create — github_pr.py:1538 / :1715
                "host": "api.github.com",
                "path_template": f"{base}/git/refs",
                "methods": ["POST"],
            },
            {  # Ref read — github_pr.py:1422 / :1558 / :1725 (slash-bearing refs)
                "host": "api.github.com",
                "path_template": f"{base}/git/ref/heads/{{ref+}}",
                "methods": ["GET"],
                "param_patterns": {"ref": _GH_REF_REST},
            },
            {  # Commit read — github_pr.py:1441 / :1574
                "host": "api.github.com",
                "path_template": f"{base}/git/commits/{{sha}}",
                "methods": ["GET"],
                "param_patterns": {"sha": _GH_SHA},
            },
            {  # Contents read — github_pr.py:1180 (subdir paths + exactly-one ref)
                "host": "api.github.com",
                "path_template": f"{base}/contents/{{path+}}",
                "methods": ["GET"],
                "param_patterns": {"path": _GH_CONTENTS_REST},
                "allowed_query": ["ref"],
                "query_patterns": {"ref": _GH_REF_QUERY},
                "required_query": ["ref"],
            },
            {  # PRs-for-commit read — outbound_connections.py:978 (broker path)
                "host": "api.github.com",
                "path_template": f"{base}/commits/{{sha}}/pulls",
                "methods": ["GET"],
                "param_patterns": {"sha": _GH_SHA},
                "allowed_query": ["per_page"],
                # The broker validates 1..100; encode that authority exactly (no
                # leading-zero / >100 spellings) so the allowlist matches it (Codex).
                "query_patterns": {"per_page": r"(?:100|[1-9][0-9]?)"},
                "required_query": ["per_page"],
            },
        ]
    )


def github_outbound_via_connection_enabled() -> bool:
    """Whether the DARK egress-unification flag is truthy (slice 2B).

    Until this is set, github_pr keeps pushing PRs through its legacy raw-urllib
    path verbatim (no dual credential path, no behavior change). The flag is
    read at call time so a test can flip it per-case.
    """
    return os.environ.get(GITHUB_VIA_CONNECTION_FLAG, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def github_send_via_connection(
    *,
    method: str,
    path: str,
    body: str | None,
    capability_token: str,
    destination: str,
) -> dict[str, Any]:
    """Send ONE github api call through the credential-blind SSRF-hardened driver.

    Slice 2B egress-unification seam (DARK). ``path`` and ``body`` come from the
    slice-1 builders (or an equivalent ``/repos/<owner>/<repo>/...`` path + a
    pre-encoded default-``json.dumps`` string body), so the wire request is
    byte-identical to github_pr's legacy urllib construction. The Bearer token is
    applied INSIDE the driver from a one-member ``ConnectionSecretBundle`` — this
    seam never emits ``Authorization`` itself. The egress boundary is the
    destination-bound :func:`github_allowed_endpoints`. Returns the driver's
    sanitized ``{status, reason, headers, body}``; raises the driver's secret-free
    ``SsrfValidationError``/``ProxyRequestError`` on refusal/failure (the caller
    maps those to github_pr's legacy return/raise shapes).
    """
    driver = _SsrfHardenedHttpDriver()
    return driver(
        bundle=ConnectionSecretBundle(token=capability_token),
        auth_scheme="bearer",
        method=method,
        url=f"{GITHUB_API_BASE}{path}",
        headers=dict(_GITHUB_HEADERS),
        body=body,
        allowed_endpoints=github_allowed_endpoints(destination),
    )


def _github_request(*, method: str, path: str, body: str | None) -> dict[str, Any]:
    """Assemble one credential-blind github request (shared shape)."""
    return {
        "method": method,
        "url": f"{GITHUB_API_BASE}{path}",
        "headers": dict(_GITHUB_HEADERS),
        "body": body,
    }


def github_pull_request_create_request(
    *,
    owner_repo: str,
    title: str,
    body: str = "",
    base_branch: str = "main",
    head_branch: str = "",
    draft: bool = True,
) -> dict[str, Any]:
    """``POST /repos/{owner}/{repo}/pulls`` — reproduces ``_invoke_github_api_``
    ``pr_create`` (github_pr.py:1778) byte-for-byte.

    Same normalizations the oracle applies (``title.strip()``, ``body or ""``,
    ``base_branch or "main"``, ``bool(draft)``, ``head`` only when non-empty) and
    the SAME key order (title, body, base, draft, head) so the default-separator
    ``json.dumps`` bytes match.
    """
    payload: dict[str, Any] = {
        "title": str(title).strip(),
        "body": body or "",
        "base": base_branch or "main",
        "draft": bool(draft),
    }
    if head_branch:
        payload["head"] = head_branch
    return _github_request(
        method="POST",
        path=f"/repos/{owner_repo}/pulls",
        body=json.dumps(payload),
    )


def github_add_labels_request(
    *, owner_repo: str, pr_number: int, labels: list[str]
) -> dict[str, Any]:
    """``POST /repos/{owner}/{repo}/issues/{pr_number}/labels`` — github_pr.py:1806."""
    return _github_request(
        method="POST",
        path=f"/repos/{owner_repo}/issues/{pr_number}/labels",
        body=json.dumps({"labels": list(labels)}),
    )


def github_git_blob_request(
    *, owner_repo: str, content: str, encoding: str = "utf-8"
) -> dict[str, Any]:
    """``POST /repos/{owner}/{repo}/git/blobs`` — github_pr.py:1464-1468."""
    return _github_request(
        method="POST",
        path=f"/repos/{owner_repo}/git/blobs",
        body=json.dumps({"content": content, "encoding": encoding}),
    )


def github_git_tree_request(
    *, owner_repo: str, base_tree: str, tree: list[dict[str, Any]]
) -> dict[str, Any]:
    """``POST /repos/{owner}/{repo}/git/trees`` — github_pr.py:1486-1490.

    ``tree`` entries carry github_pr's key order (``path``/``mode``/``type``/
    ``sha``, github_pr.py:1482) so the serialized bytes match.
    """
    return _github_request(
        method="POST",
        path=f"/repos/{owner_repo}/git/trees",
        body=json.dumps({"base_tree": base_tree, "tree": tree}),
    )


def github_git_commit_request(
    *, owner_repo: str, message: str, tree: str, parents: list[str]
) -> dict[str, Any]:
    """``POST /repos/{owner}/{repo}/git/commits`` — github_pr.py:1502-1510."""
    return _github_request(
        method="POST",
        path=f"/repos/{owner_repo}/git/commits",
        body=json.dumps({"message": message, "tree": tree, "parents": list(parents)}),
    )


def github_git_ref_create_request(
    *, owner_repo: str, ref: str, sha: str
) -> dict[str, Any]:
    """``POST /repos/{owner}/{repo}/git/refs`` — github_pr.py:1536-1540 / :1713-1720."""
    return _github_request(
        method="POST",
        path=f"/repos/{owner_repo}/git/refs",
        body=json.dumps({"ref": ref, "sha": sha}),
    )


def github_git_ref_read_request(*, owner_repo: str, branch: str) -> dict[str, Any]:
    """``GET /repos/{owner}/{repo}/git/ref/heads/{branch}`` — github_pr.py:1420-1423.

    github_pr does NOT url-quote ``branch`` here, so neither do we.
    """
    return _github_request(
        method="GET",
        path=f"/repos/{owner_repo}/git/ref/heads/{branch}",
        body=None,
    )


def github_git_commit_read_request(*, owner_repo: str, sha: str) -> dict[str, Any]:
    """``GET /repos/{owner}/{repo}/git/commits/{sha}`` — github_pr.py:1439-1442."""
    return _github_request(
        method="GET",
        path=f"/repos/{owner_repo}/git/commits/{sha}",
        body=None,
    )


def github_contents_read_request(
    *, owner_repo: str, path: str, ref: str
) -> dict[str, Any]:
    """``GET /repos/{owner}/{repo}/contents/{path}?ref={ref}`` — github_pr.py:1176-1181.

    Reproduces github_pr's exact quoting: ``quote(path, safe="/")`` (slashes in a
    file path are preserved) and ``quote(ref, safe="")``.
    """
    encoded = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    return _github_request(
        method="GET",
        path=f"/repos/{owner_repo}/contents/{encoded}?ref={encoded_ref}",
        body=None,
    )
