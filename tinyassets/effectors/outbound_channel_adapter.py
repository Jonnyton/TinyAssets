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
import urllib.parse
from typing import Any

from tinyassets.storage.outbound_connections import (
    OutboundEndpoint,
    _parse_allowed_endpoints,
)

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
# recorder and assert every builder here produces the identical wire request.
#
# This is SLICE 1: request builders + allowlist + differential tests only. No
# dispatch is rewired, no flag flipped, ``github_pr.py`` is untouched, and the
# ``TINYASSETS_GITHUB_OUTBOUND_VIA_CONNECTION`` flag below stays dark.
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

#: One ``owner`` or ``repo`` path segment — matches ``_github_repository_from_``
#: ``destination``'s ``[\w.-]+/[\w.-]+`` (github_pr / outbound_connections).
_GH_REPO_SEGMENT = r"[\w.-]+"
#: A 40-hex (SHA-1) or 64-hex (SHA-256) git object id, as one path segment.
_GH_SHA = r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})"
#: One non-``/`` file/branch path segment (root-level file, non-slashed branch).
#: SHAPE FINDING: github_pr url-quotes contents ``{path}`` with ``safe="/"`` and
#: leaves branch refs (``tinyassets/cloud-...``) unquoted, so BOTH can expand to
#: MULTIPLE segments. The OutboundEndpoint template model matches exactly one
#: non-empty segment per ``{param}`` (fixed segment count), so a subdirectory
#: contents-read or a slash-bearing head-ref read is byte-identical on the wire
#: but REFUSED by this allowlist. Single-segment cases (root file, ``main``)
#: match. A variable-depth tail needs a template-model extension (a later slice);
#: proven by ``test_github_contents_subdir_path_refused_by_allowlist``.
_GH_ONE_SEGMENT = r"[\w.\-~%!$&'()*+,;=:@]+"

#: The api.github.com egress allowlist for the whole PR flow (design.md D3).
#: ``owner_repo`` is modeled as TWO placeholders because on the wire it is two
#: path segments (``octocat/hello-world``) — the recon's single ``{owner_repo}``
#: placeholder cannot match a slash. Built through the storage validator so the
#: shipped allowlist is provably one ``create_connection`` would accept
#: (fail-loud at import if any template/pattern is invalid).
GITHUB_ALLOWED_ENDPOINTS: tuple[OutboundEndpoint, ...] = _parse_allowed_endpoints(
    [
        {  # PR create — github_pr.py:1789
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/pulls",
            "methods": ["POST"],
            "param_patterns": {"owner": _GH_REPO_SEGMENT, "repo": _GH_REPO_SEGMENT},
        },
        {  # Add labels — github_pr.py:1806
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/issues/{pr_number}/labels",
            "methods": ["POST"],
            "param_patterns": {
                "owner": _GH_REPO_SEGMENT,
                "repo": _GH_REPO_SEGMENT,
                "pr_number": r"[0-9]+",
            },
        },
        {  # Blob create — github_pr.py:1466
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/git/blobs",
            "methods": ["POST"],
            "param_patterns": {"owner": _GH_REPO_SEGMENT, "repo": _GH_REPO_SEGMENT},
        },
        {  # Tree create — github_pr.py:1488
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/git/trees",
            "methods": ["POST"],
            "param_patterns": {"owner": _GH_REPO_SEGMENT, "repo": _GH_REPO_SEGMENT},
        },
        {  # Commit create — github_pr.py:1504
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/git/commits",
            "methods": ["POST"],
            "param_patterns": {"owner": _GH_REPO_SEGMENT, "repo": _GH_REPO_SEGMENT},
        },
        {  # Ref create — github_pr.py:1538 / :1715
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/git/refs",
            "methods": ["POST"],
            "param_patterns": {"owner": _GH_REPO_SEGMENT, "repo": _GH_REPO_SEGMENT},
        },
        {  # Ref read — github_pr.py:1422 / :1558 / :1725
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/git/ref/heads/{branch}",
            "methods": ["GET"],
            "param_patterns": {
                "owner": _GH_REPO_SEGMENT,
                "repo": _GH_REPO_SEGMENT,
                "branch": _GH_ONE_SEGMENT,
            },
        },
        {  # Commit read — github_pr.py:1441 / :1574
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/git/commits/{sha}",
            "methods": ["GET"],
            "param_patterns": {
                "owner": _GH_REPO_SEGMENT,
                "repo": _GH_REPO_SEGMENT,
                "sha": _GH_SHA,
            },
        },
        {  # Contents read — github_pr.py:1180
            "host": "api.github.com",
            "path_template": "/repos/{owner}/{repo}/contents/{path}",
            "methods": ["GET"],
            "param_patterns": {
                "owner": _GH_REPO_SEGMENT,
                "repo": _GH_REPO_SEGMENT,
                "path": _GH_ONE_SEGMENT,
            },
            "allowed_query": ["ref"],
        },
    ]
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
