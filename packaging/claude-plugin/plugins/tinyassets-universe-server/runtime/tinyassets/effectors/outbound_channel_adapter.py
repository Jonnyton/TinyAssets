"""The ONE outbound-channel module — every external channel routes here.

Channel-agnostic-outbound (design.md D1–D6): instead of a bespoke effector module
per channel, GitHub PRs, Slack ``chat.postMessage``, and X/Twitter
``POST /2/tweets`` are ALL expressed as requests that the general credential-blind
SSRF-hardened driver (``storage/outbound_connections``) sends through a per-channel
credential bundle + an ``OutboundEndpoint`` allowlist. The auth material is applied
INSIDE the driver from the bundle (Bearer for GitHub/Slack; OAuth 1.0a signed in the
broker child for X) — the request builders in this module are credential-blind and
only shape the wire request.

This is the collapse target: the legacy bespoke per-channel effector modules are
GONE, their credential/HTTP paths replaced here by the one SSRF-hardened driver (no
feature flag, no legacy fallback). ``build_slack_transport`` and
``run_twitter_post_effector`` live here now; a channel with no vault credential FAILS
LOUD (a universe adds its connection as a user) — it never borrows ambient env.
Byte-identical wire-request parity for each channel is pinned by
``tests/test_outbound_channel_migration.py``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Any

from tinyassets.effectors.authority import DENIED as SOUL_AUTHORITY_DENIED
from tinyassets.effectors.authority import resolve_soul_effect_authority
from tinyassets.storage.outbound_connections import (
    ConnectionSecretBundle,
    OutboundEndpoint,
    ProxyRequestError,
    SsrfValidationError,
    _github_repository_from_destination,
    _parse_allowed_endpoints,
    _SsrfHardenedHttpDriver,
)

logger = logging.getLogger(__name__)

#: One ASCII owner/repo pair. ``_github_repository_from_destination`` validates the
#: destination with ``re``'s Unicode ``\w``, but the allowlist compares template
#: literals as ASCII strings — so the two grammars must agree or a Unicode
#: confusable could parse as one repo yet fail the literal segment validator
#: (Codex). This ASCII re-check pins the derived ``owner/repo`` to the byte
#: alphabet the matcher uses, failing closed with a clear error otherwise.
_GH_ASCII_OWNER_REPO_RE = re.compile(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+")

# --- Slack ------------------------------------------------------------------ #
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
#: The connection allowlist entry a Slack ``http`` connection carries.
SLACK_ALLOWED_ENDPOINT: dict[str, Any] = {
    "host": "slack.com",
    "path_template": "/api/chat.postMessage",
    "methods": ["POST"],
}
#: Parsed egress allowlist for the Slack send — built through the storage
#: validator so it is provably one ``create_connection`` would accept.
SLACK_ALLOWED_ENDPOINTS: tuple[OutboundEndpoint, ...] = _parse_allowed_endpoints(
    [SLACK_ALLOWED_ENDPOINT]
)
#: Bot tokens only. An ``xoxp-`` user token posts under a person's name.
BOT_TOKEN_PREFIX = "xoxb-"
#: Slack rejects oversized posts; bound the body before spending a round trip.
_SLACK_MAX_BODY_BYTES = 40_000

# --- X / Twitter ------------------------------------------------------------ #
TWITTER_TWEETS_URL = "https://api.x.com/2/tweets"
TWITTER_ALLOWED_ENDPOINT: dict[str, Any] = {
    "host": "api.x.com",
    "path_template": "/2/tweets",
    "methods": ["POST"],
}
#: Parsed egress allowlist for the X/Twitter send.
TWITTER_ALLOWED_ENDPOINTS: tuple[OutboundEndpoint, ...] = _parse_allowed_endpoints(
    [TWITTER_ALLOWED_ENDPOINT]
)


def slack_http_request(*, channel: str, text: str, thread_ts: str = "") -> dict[str, Any]:
    """The Slack ``chat.postMessage`` call as an ``http``-connection request.

    The body is ``json.dumps(payload)`` with the stdlib's DEFAULT separators
    (``", "`` / ``": "``); the general driver's dict-body auto-encoding uses COMPACT
    separators, so we pass a pre-encoded string to reproduce Slack's spaced form
    exactly, and set ``Content-Type`` explicitly. The Bearer bot token is applied in
    the driver (``auth_scheme="bearer"``). The wire request is pinned by
    ``tests/test_outbound_channel_migration.py``.
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

    COMPACT JSON body and the ``Accept``/``Content-Type``/``User-Agent`` headers X
    expects. The OAuth 1.0a ``Authorization`` is signed in the driver from the
    ``oauth1a`` bundle — never here (the adapter never sees the four OAuth secrets).
    The wire request is pinned by ``tests/test_outbound_channel_migration.py``.
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
# Each ``api.github.com`` PR-flow call is expressed as a credential-blind
# ``http``-connection request whose wire bytes are byte-identical to the request
# ``github_pr.py`` constructs: the body is the stdlib's DEFAULT (spaced)
# ``json.dumps`` string (pre-encoded so the driver's compact auto-encoding does not
# apply) and the SAME five headers ride on every call. GET reads carry no body but
# still send ``Content-Type: application/json`` (github_pr sets all five headers
# unconditionally). ``Authorization: Bearer <token>`` is applied INSIDE the driver
# from the connection bundle (``auth_scheme="bearer"``) — these builders never emit
# it. ``github_pr._github_api_request``/``_git_data_api`` and the broker's
# ``read_for_commit`` route through :func:`github_send_via_connection` +
# :func:`github_allowed_endpoints` UNCONDITIONALLY (no flag, no legacy urllib).
# Parity is pinned by the wire-request tests in
# ``tests/test_outbound_channel_migration.py``.
GITHUB_API_BASE = "https://api.github.com"

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


# =========================================================================== #
# Slack — server-owned app reply transport (was a bespoke effector module).
#
# ``build_slack_transport`` supplies the injected ``Transport`` callback
# ``app_outbound_adapter`` calls. Three invariants it holds:
#   * the bot token never crosses the credential-blind boundary — it is resolved
#     from the per-universe vault here and applied INSIDE the driver;
#   * a vault-bound universe NEVER falls through to host env — an empty vault means
#     "not authorized", not "borrow the maintainer's token";
#   * the receipt carries no content (``ts`` is an identifier, not text).
# =========================================================================== #
class SlackTransportError(RuntimeError):
    """The reply could not be delivered to Slack.

    Deliberately carries no message body and no credential — it is raised across
    the governed boundary, and ``app_outbound_adapter`` wraps it into
    ``AppOutboundDeliveryError``.
    """


def resolve_slack_bot_token(
    universe_dir: str | Path | None,
    connection_id: str,
) -> str:
    """Return the Slack bot token for one connection, or an empty string.

    Vault-first, and a vault-bound universe never falls through to the process
    environment: an empty vault means this universe is not authorized, not "look at
    the host env". Never echoed into caller-visible evidence.
    """
    if universe_dir is None or not connection_id.strip():
        return ""
    from tinyassets.credential_vault import resolve_slack_token, vault_exists

    token = resolve_slack_token(universe_dir, connection_id.strip())
    if token or vault_exists(universe_dir):
        return token
    return ""


def slack_send_via_connection(
    *, channel: str, text: str, thread_ts: str, bot_token: str
) -> dict[str, Any]:
    """Post one Slack message through the credential-blind SSRF-hardened driver.

    Mirrors :func:`github_send_via_connection`: the Bearer bot token is applied
    INSIDE the driver from a one-member bundle (``auth_scheme="bearer"``); this seam
    never emits ``Authorization``. Returns the driver's sanitized
    ``{status, reason, headers, body}``; raises the driver's secret-free
    ``SsrfValidationError``/``ProxyRequestError`` on refusal/failure (the caller maps
    those to :class:`SlackTransportError`).
    """
    request = slack_http_request(channel=channel, text=text, thread_ts=thread_ts)
    driver = _SsrfHardenedHttpDriver()
    return driver(
        bundle=ConnectionSecretBundle(token=bot_token),
        auth_scheme="bearer",
        method="POST",
        url=request["url"],
        headers=request["headers"],
        body=request["body"],
        allowed_endpoints=SLACK_ALLOWED_ENDPOINTS,
    )


def build_slack_transport(universe_dir: str | Path | None):
    """Build the injected ``Transport`` callable for ``app_outbound_adapter``.

    The returned callable takes ``(ReplyDestination, str)`` (plus keyword-only
    ``thread_ts``) and returns an ``AppTransportReceipt`` whose
    ``provider_receipt_ref`` is the Slack message identifier — never the message
    text. Every send goes through the one SSRF-hardened driver; a missing/invalid
    vault credential FAILS LOUD.
    """
    from tinyassets.app_outbound_adapter import AppTransportReceipt
    from tinyassets.effectors.slack_errors import safe_error_code

    def _transport(
        destination: Any,
        body: str,
        *,
        thread_ts: str = "",
    ) -> Any:
        if destination.provider != "slack":
            raise SlackTransportError("slack transport received a non-slack destination")
        text = body if isinstance(body, str) else ""
        if not text.strip():
            raise SlackTransportError("refusing to deliver an empty reply")
        if len(text.encode("utf-8")) > _SLACK_MAX_BODY_BYTES:
            raise SlackTransportError("reply body exceeds the slack transport bound")

        token = resolve_slack_bot_token(universe_dir, destination.connection_id)
        if not token:
            # Fail closed. A missing credential must never degrade into "deliver
            # with whatever token happens to be around".
            raise SlackTransportError(
                "no requester-owned slack credential for this connection"
            )
        if not token.startswith(BOT_TOKEN_PREFIX):
            # Checked HERE, not only at startup: the token is re-read from the vault
            # on every post (so rotation is picked up), which makes a startup-only
            # check time-of-check/time-of-use. A user (``xoxp-``) token posts under a
            # HUMAN's name, so the agent would silently impersonate whoever installed
            # the app.
            raise SlackTransportError("the stored slack credential is not a bot token")

        send_failed = False
        result: dict[str, Any] = {}
        try:
            result = slack_send_via_connection(
                channel=destination.address,
                text=text,
                thread_ts=thread_ts,
                bot_token=token,
            )
        except (SsrfValidationError, ProxyRequestError):
            send_failed = True
        if send_failed:
            # Raised OUTSIDE the except block on purpose: `from None` clears
            # __cause__ but leaves __context__ holding the driver error, whose
            # text could quote a reflected header (the Authorization-echo leak
            # class). Raising here clears __context__ too. The driver's errors are
            # already secret-free; this is defense-in-depth.
            raise SlackTransportError("slack transport unreachable")

        status = int(result["status"])
        if not 200 <= status < 300:
            raise SlackTransportError(f"slack transport http {status}")
        try:
            decoded = json.loads(result["body"])
        except Exception:  # noqa: BLE001 - decode errors and hostile nesting alike
            raise SlackTransportError(
                "slack transport returned malformed JSON"
            ) from None
        if not isinstance(decoded, dict):
            raise SlackTransportError("slack transport returned a non-object response")
        if not decoded.get("ok"):
            # Slack reports failure in-band with HTTP 200. Surface the error CODE
            # only — never the echoed message payload Slack returns.
            code = safe_error_code(decoded.get("error"), default="unknown_error")
            raise SlackTransportError(f"slack rejected the reply: {code}")

        receipt_ref = str(decoded.get("ts") or "").strip()
        if not receipt_ref:
            raise SlackTransportError("slack accepted the reply without an identifier")
        channel = str(decoded.get("channel") or destination.address).strip()
        return AppTransportReceipt(provider_receipt_ref=f"slack:{channel}:{receipt_ref}")

    return _transport


# =========================================================================== #
# X / Twitter — external-write effector (was a bespoke effector module).
#
# The full authority → consent → idempotency → receipt lifecycle is preserved
# verbatim; only two things changed vs the legacy module: credentials move from
# host env to the per-universe vault (closing the cross-universe env hole,
# design.md §4), and the tweet POST goes through the one SSRF-hardened driver
# (``twitter_send_via_connection``) instead of a bespoke urllib + hand-rolled
# OAuth call. The OAuth 1.0a signature is built INSIDE the broker child from the
# four-value bundle (``auth_scheme="oauth1a"``); this module never signs it.
# =========================================================================== #
EXTERNAL_WRITE_SINK_TWITTER_POST = "twitter_post"
DESTINATION_RECONCILIATION = {
    "supported": False,
    "reason": (
        "the adapter has no stable destination lookup by system effect key; "
        "stale intents require operator inspection"
    ),
}

_DRY_RUN_ENV = "TINYASSETS_EXTERNAL_WRITE_DRY_RUN"
_DEFAULT_HANDLE = "@kwisatzh4derach"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


class TwitterCredentials:
    """The four OAuth 1.0a values (+ a resolution-source label)."""

    __slots__ = (
        "access_token",
        "access_token_secret",
        "api_key",
        "api_secret",
        "source",
    )

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        source: str,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_token_secret = access_token_secret
        self.source = source


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _parse_packet(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (TypeError, ValueError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None
    if packet.get("sink") != EXTERNAL_WRITE_SINK_TWITTER_POST:
        return None
    return packet


def _find_packet(
    *,
    output_keys: list[str],
    run_state: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    for key in output_keys or []:
        if not isinstance(key, str) or key not in run_state:
            continue
        packet = _parse_packet(run_state.get(key))
        if packet is not None:
            return key, packet
    return None, None


def _destination(packet: dict[str, Any]) -> str:
    value = packet.get("destination")
    if isinstance(value, str):
        return value.strip()
    return ""


def _payload(packet: dict[str, Any]) -> dict[str, Any]:
    value = packet.get("payload")
    return value if isinstance(value, dict) else {}


def _text(packet: dict[str, Any]) -> str:
    value = _payload(packet).get("text")
    if isinstance(value, str):
        return value.strip()
    return ""


def _optional_tweet_id(packet: dict[str, Any], key: str) -> str:
    value = _payload(packet).get(key)
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalize_handle(value: str) -> str:
    raw = value.strip()
    if raw.lower() in {"", "x:self", "self", "@self"}:
        return _DEFAULT_HANDLE
    if raw.lower().startswith("x:"):
        raw = raw.split(":", 1)[1].strip()
    if raw.startswith("https://x.com/") or raw.startswith("https://twitter.com/"):
        raw = raw.rstrip("/").rsplit("/", 1)[-1]
    if not raw.startswith("@"):
        raw = f"@{raw}"
    return raw


def _authorized_handle(packet: dict[str, Any]) -> str:
    """Account/handle the post will use — DERIVED FROM ``destination`` only.

    Authority, consent, and credential resolution all key off the authorized
    ``destination``. The account actually posted-from is bound to that same
    destination, never to an arbitrary payload-supplied handle. A packet whose
    payload names a *different* account is rejected upstream by
    :func:`_packet_handle_override` rather than silently honored.
    """
    destination = _destination(packet)
    if destination:
        return _normalize_handle(destination)
    return _DEFAULT_HANDLE


def _packet_handle_override(packet: dict[str, Any]) -> str:
    """Return any payload/packet-supplied handle, normalized; "" if none.

    Unlike :func:`_authorized_handle` this does NOT fall back to ``destination`` —
    it surfaces only an explicit caller-supplied handle so the effector can detect
    (and reject) a handle that disagrees with the authorized destination.
    """
    payload = _payload(packet)
    for key in ("sink_handle", "handle", "account_handle"):
        value = payload.get(key) or packet.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_handle(value)
    return ""


def _resolve_credentials(
    *, universe_dir: Path | None, destination: str
) -> TwitterCredentials | None:
    """Resolve the four OAuth 1.0a values from the per-universe vault.

    Vault-first and NO env fallback: the legacy ``TWITTER_*`` host-env resolution is
    gone — it was the cross-universe isolation hole design.md §4 closes. A universe
    that has not deposited a ``twitter`` connection for this destination resolves to
    ``None`` → the effector dry-runs ``missing_credentials``, never borrowing ambient
    env.
    """
    if universe_dir is None or not destination:
        return None
    from tinyassets.credential_vault import resolve_twitter_credentials

    values = resolve_twitter_credentials(universe_dir, destination)
    if not values:
        return None
    return TwitterCredentials(
        api_key=values["api_key"],
        api_secret=values["api_secret"],
        access_token=values["access_token"],
        access_token_secret=values["access_token_secret"],
        source="vault",
    )


def _universe_dir(base_path: str | Path | None) -> Path | None:
    if base_path is None:
        return None
    try:
        return Path(base_path)
    except (TypeError, ValueError):
        return None


def _check_consent(universe_dir: Path | None, destination: str) -> bool:
    if universe_dir is None or not destination:
        return False
    try:
        from tinyassets.storage.effector_consents import is_consent_active

        return is_consent_active(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            destination=destination,
        )
    except Exception:
        logger.exception("twitter_post consent lookup crashed")
        return False


def _derive_idempotency_hint(
    *,
    packet: dict[str, Any],
    run_id: str,
    handle: str,
    text: str,
    universe_dir: Path | None,
) -> str:
    from tinyassets.idempotency import resolve_effector_identity

    identity = resolve_effector_identity(
        packet,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        universe_dir=universe_dir,
    )
    if identity.active_key:
        return identity.active_key
    payload = _payload(packet)
    source_run_id = payload.get("source_run_id") or packet.get("source_run_id") or run_id
    seed = f"{source_run_id}|{EXTERNAL_WRITE_SINK_TWITTER_POST}|{handle}|{text}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _try_reserve(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    run_id: str,
) -> dict[str, Any]:
    if universe_dir is None or not idempotency_hint:
        return {"status": "no_hint"}
    from tinyassets.storage.external_write_receipts import try_reserve_receipt

    return try_reserve_receipt(
        universe_dir,
        idempotency_hint=idempotency_hint,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        run_id=run_id or "",
    )


def _finalize_receipt(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    evidence: dict[str, Any],
    run_id: str,
) -> bool:
    if universe_dir is None or not idempotency_hint:
        return False
    try:
        from tinyassets.storage.external_write_receipts import finalize_receipt

        return finalize_receipt(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            evidence=evidence,
            run_id=run_id or "",
        )
    except Exception:
        logger.exception("failed to finalize twitter_post receipt")
        return False


def _release_reservation(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    run_id: str,
) -> None:
    if universe_dir is None or not idempotency_hint:
        return
    try:
        from tinyassets.storage.external_write_receipts import release_reservation

        release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            run_id=run_id or "",
            mark_failed=True,
        )
    except Exception:
        logger.exception("failed to release twitter_post reservation")


def _is_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return any(token in msg for token in ("locked", "busy", "deadlock", "timeout"))


def twitter_send_via_connection(
    *,
    text: str,
    reply_to_tweet_id: str,
    quote_tweet_id: str,
    credentials: TwitterCredentials,
) -> dict[str, Any]:
    """Post one tweet through the credential-blind SSRF-hardened driver.

    Mirrors :func:`github_send_via_connection`: the OAuth 1.0a ``Authorization`` is
    signed INSIDE the driver from the four-value bundle (``auth_scheme="oauth1a"``);
    this seam never signs or sees the header. Returns the SAME response shape the
    legacy bespoke tweet POST produced — the parsed JSON dict on success, or a
    ``{"error", "error_kind", ...}`` dict — so the effector's downstream logic is
    unchanged.
    """
    request = twitter_http_request(
        text=text,
        reply_to_tweet_id=reply_to_tweet_id,
        quote_tweet_id=quote_tweet_id,
    )
    bundle = ConnectionSecretBundle(
        api_key=credentials.api_key,
        api_secret=credentials.api_secret,
        access_token=credentials.access_token,
        access_token_secret=credentials.access_token_secret,
    )
    driver = _SsrfHardenedHttpDriver()
    try:
        result = driver(
            bundle=bundle,
            auth_scheme="oauth1a",
            method="POST",
            url=request["url"],
            headers=request["headers"],
            body=request["body"],
            allowed_endpoints=TWITTER_ALLOWED_ENDPOINTS,
        )
    except (SsrfValidationError, ProxyRequestError) as exc:
        return {
            "error": f"X API request failed: {exc}",
            "error_kind": "x_api_request_failed",
        }
    status = int(result["status"])
    body_text = result["body"]
    if not 200 <= status < 300:
        return {
            "error": f"X API HTTP {status}: {body_text[:500]}",
            "error_kind": "x_api_http_error",
            "http_status": status,
        }
    try:
        return json.loads(body_text)
    except (TypeError, ValueError) as exc:
        return {
            "error": f"X API returned invalid JSON: {exc}",
            "error_kind": "x_api_invalid_json",
        }


def _post_id(response: dict[str, Any]) -> str:
    data = response.get("data")
    if isinstance(data, dict):
        value = data.get("id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = response.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _post_url(handle: str, post_id: str) -> str:
    screen_name = handle.strip().lstrip("@")
    return f"https://x.com/{screen_name}/status/{post_id}"


def _would_post_evidence(
    *,
    reason: str,
    packet: dict[str, Any],
    destination: str,
    handle: str,
    text: str,
    matched_key: str | None,
    idempotency_hint: str | None = None,
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "dry_run": True,
        "phase": "phase_2",
        "reason": reason,
        "destination": destination,
        "sink_handle": handle,
        "would_post": {
            "text": text,
            "reply_to_tweet_id": _optional_tweet_id(packet, "reply_to_tweet_id"),
            "quote_tweet_id": _optional_tweet_id(packet, "quote_tweet_id"),
        },
        "matched_output_key": matched_key,
        "intent": packet,
    }
    if idempotency_hint:
        evidence["idempotency_hint"] = idempotency_hint
    return evidence


def run_twitter_post_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Run one ``twitter_post`` external-write packet.

    The effector never raises to the run-completion path; every refusal, duplicate,
    or external API failure is returned as structured evidence.
    """
    matched_key, packet = _find_packet(output_keys=output_keys, run_state=run_state)
    if packet is None:
        return {
            "error": (
                f"node '{node_id}' declared effects=["
                f"{EXTERNAL_WRITE_SINK_TWITTER_POST}] but no output_key held "
                "a parseable twitter_post external_write_packet"
            ),
            "error_kind": "no_matching_packet",
        }

    destination = _destination(packet)
    # SECURITY INVARIANT: the account actually posted-from is bound to the
    # authorized ``destination``, never to an arbitrary payload handle. Authority,
    # consent, and credential resolution all key off this same destination.
    handle = _authorized_handle(packet)
    override_handle = _packet_handle_override(packet)
    text = _text(packet)
    universe_dir = _universe_dir(base_path)
    idempotency_hint = _derive_idempotency_hint(
        packet=packet,
        run_id=run_id,
        handle=handle,
        text=text,
        universe_dir=universe_dir,
    )

    if not destination:
        return {
            "error": "packet.destination is required for twitter_post",
            "error_kind": "invalid_destination",
            "phase": "phase_2",
            "matched_output_key": matched_key,
        }
    if override_handle and override_handle != handle:
        # The payload named an account that does not match the account the
        # authorized destination resolves to. Authority + consent only cover the
        # destination-derived account, so honoring this override would post from an
        # account that was never authorized. Reject, never post.
        return {
            "error": (
                "packet payload handle resolves to a different account than "
                "the authorized destination; refusing twitter_post to avoid "
                "posting from an unauthorized account"
            ),
            "error_kind": "handle_authority_mismatch",
            "phase": "phase_2",
            "destination": destination,
            "authorized_handle": handle,
            "requested_handle": override_handle,
            "matched_output_key": matched_key,
        }
    if not text:
        return {
            "error": "packet.payload.text is required for twitter_post",
            "error_kind": "invalid_payload",
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
        }

    if _env_truthy(_DRY_RUN_ENV):
        evidence = _would_post_evidence(
            reason="operator_kill_switch_active",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )
        evidence["kill_switch_env"] = _DRY_RUN_ENV
        return evidence

    authority = resolve_soul_effect_authority(
        universe_dir,
        EXTERNAL_WRITE_SINK_TWITTER_POST,
        destination,
    )
    if authority == SOUL_AUTHORITY_DENIED:
        return _would_post_evidence(
            reason="soul_not_authorized",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )

    if not _check_consent(universe_dir, destination):
        evidence = _would_post_evidence(
            reason="missing_consent",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )
        evidence["hint"] = (
            "Effector consent grants are not exposed by the advertised "
            "handles; an operator must authorize this destination through "
            "the internal consent surface before dispatching twitter_post "
            "effects."
        )
        return evidence

    credentials = _resolve_credentials(universe_dir=universe_dir, destination=destination)
    if credentials is None:
        evidence = _would_post_evidence(
            reason="missing_credentials",
            packet=packet,
            destination=destination,
            handle=handle,
            text=text,
            matched_key=matched_key,
            idempotency_hint=idempotency_hint,
        )
        evidence["hint"] = (
            "No vault twitter connection for this destination. Deposit a "
            "per-universe `social`/`twitter` credential (the four OAuth 1.0a "
            "values) keyed to this destination; the host-env TWITTER_* fallback "
            "was removed to close the cross-universe credential hole."
        )
        return evidence

    try:
        reservation = _try_reserve(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
    except sqlite3.OperationalError as exc:
        return {
            "error": (
                "receipt store unavailable; refusing twitter_post to avoid "
                f"duplicate posts: {exc}"
            ),
            "error_kind": (
                "receipt_store_locked"
                if _is_lock_error(exc) else "receipt_store_error"
            ),
            "phase": "phase_2",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
        }

    status = reservation.get("status")
    if status == "duplicate":
        recorded = reservation.get("row") or {}
        return {
            "idempotency_dedup_hit": True,
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
            "evidence": recorded.get("evidence") or {},
            "recorded_run_id": recorded.get("run_id"),
            "recorded_at": recorded.get("created_at"),
            "idempotency_hint": idempotency_hint,
        }
    if status == "in_flight":
        held = reservation.get("row") or {}
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "concurrent_in_flight",
            "destination": destination,
            "sink_handle": handle,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
            "held_by_run_id": held.get("run_id"),
            "reservation_created_at": held.get("created_at"),
            "intent": packet,
        }
    if status == "reconciliation_required":
        from tinyassets.effectors.outbound_boundary import (
            hold_unreconciled_pending,
        )

        hold = hold_unreconciled_pending(
            universe_dir=universe_dir,
            effect_key=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            run_id=run_id,
        )
        return {
            **hold,
            "dry_run": True,
            "phase": "phase_2",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
            "intent": packet,
        }
    if status not in (
        "reserved",
        "reserved_after_failed",
        "no_hint",
    ):
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "reservation_unknown_state",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "reservation_status": str(status),
            "matched_output_key": matched_key,
            "intent": packet,
        }

    response = twitter_send_via_connection(
        text=text,
        reply_to_tweet_id=_optional_tweet_id(packet, "reply_to_tweet_id"),
        quote_tweet_id=_optional_tweet_id(packet, "quote_tweet_id"),
        credentials=credentials,
    )
    if "error" in response:
        _release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
        response.setdefault("phase", "phase_2")
        response.setdefault("destination", destination)
        response.setdefault("sink_handle", handle)
        response.setdefault("idempotency_hint", idempotency_hint)
        response.setdefault("reservation_released", True)
        response.setdefault("matched_output_key", matched_key)
        return response

    post_id = _post_id(response)
    if not post_id:
        _release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
        return {
            "error": "X API response did not contain data.id",
            "error_kind": "x_api_invalid_response",
            "phase": "phase_2",
            "destination": destination,
            "sink_handle": handle,
            "idempotency_hint": idempotency_hint,
            "reservation_released": True,
            "matched_output_key": matched_key,
        }

    evidence = {
        "phase": "phase_2",
        "destination": destination,
        "sink_handle": handle,
        "post_id": post_id,
        "post_url": _post_url(handle, post_id),
        "matched_output_key": matched_key,
        "idempotency_hint": idempotency_hint,
        "credential_source": credentials.source,
        "recorded_at": time.time(),
    }
    if status == "reserved_after_failed":
        evidence["reservation_origin"] = status
    if not _finalize_receipt(
        universe_dir,
        idempotency_hint=idempotency_hint,
        evidence=evidence,
        run_id=run_id,
    ):
        from tinyassets.effectors.outbound_boundary import (
            hold_receipt_finalization_failure,
        )

        evidence = hold_receipt_finalization_failure(
            universe_dir=universe_dir,
            effect_key=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
            run_id=run_id,
            destination_evidence=evidence,
        )
    return evidence
