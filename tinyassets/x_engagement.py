"""Read real-world engagement for posts this universe has made on X.

The feedback half of the posting loop. `effectors/twitter_post.py` writes a
receipt (post_id, post_url) for every real post; until this module NOTHING
read those posts back, so "learn from how posts perform" had no data source.
This reads the receipts, asks X for `public_metrics` (likes, replies,
retweets, quotes, bookmarks, impressions), and returns them joined — the
signal an evaluator/optimizer branch or the agent itself tunes against.

Read-only against X. Uses the same OAuth 1.0a user-context credentials the
post effector uses (a user-context GET also returns non-public
`impression_count` for the account's own tweets where the API tier allows
it). Missing credentials are an honest structured refusal, never a guess.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from tinyassets.effectors.twitter_post import (
    EXTERNAL_WRITE_SINK_TWITTER_POST,
    _oauth_header,
    _resolve_credentials,
)

logger = logging.getLogger(__name__)

_TWEETS_LOOKUP_URL = "https://api.x.com/2/tweets"
#: X caps ids-per-lookup at 100; we stay far below — recent posts are the
#: ones an optimize loop cares about.
MAX_POSTS = 25


def _posted_receipts(universe_dir: Path, *, limit: int) -> list[dict[str, Any]]:
    from tinyassets.storage.external_write_receipts import list_receipts

    rows = list_receipts(
        universe_dir, sink=EXTERNAL_WRITE_SINK_TWITTER_POST, limit=max(limit * 3, 30)
    )
    posts: list[dict[str, Any]] = []
    for row in rows:
        evidence = row.get("evidence") or {}
        if not isinstance(evidence, dict):
            continue
        post_id = str(evidence.get("post_id") or "").strip()
        if not post_id:
            # Reservations, dry-runs and held receipts have no post_id —
            # nothing was published, so there is nothing to measure.
            continue
        posts.append(
            {
                "post_id": post_id,
                "post_url": str(evidence.get("post_url") or ""),
                "destination": str(evidence.get("destination") or ""),
                "posted_at": evidence.get("recorded_at") or row.get("created_at"),
                "run_id": str(row.get("run_id") or ""),
            }
        )
        if len(posts) >= limit:
            break
    return posts


def _fetch_metrics(
    post_ids: list[str], *, handle: str, destination: str
) -> dict[str, Any]:
    credentials = _resolve_credentials(handle=handle, destination=destination)
    if credentials is None:
        return {
            "error": "no X credentials available to read engagement",
            "error_kind": "missing_credentials",
            "hint": (
                "Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN "
                "and TWITTER_ACCESS_TOKEN_SECRET (same credentials the post "
                "effector uses) — reading metrics needs the account's own "
                "user context."
            ),
        }
    query = urllib.parse.urlencode(
        {
            "ids": ",".join(post_ids),
            "tweet.fields": "public_metrics,created_at,text",
        }
    )
    url = f"{_TWEETS_LOOKUP_URL}?{query}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": _oauth_header(
                method="GET", url=url, credentials=credentials
            ),
            "User-Agent": "tinyassets-x-engagement/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:400]
        return {
            "error": f"X API HTTP {exc.code}: {body_text}",
            "error_kind": "x_api_http_error",
            "http_status": exc.code,
        }
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {
            "error": f"X API request failed: {exc}",
            "error_kind": "x_api_request_failed",
        }


def read_engagement(
    universe_dir: str | Path, *, limit: int = 10
) -> dict[str, Any]:
    """Metrics for this universe's recent real posts, most recent first.

    Returns ``{"posts": [...]}`` where each post carries its receipt fields
    plus ``metrics`` (like/reply/retweet/quote/bookmark/impression counts)
    and ``text``. A post X no longer returns (deleted, protected) keeps its
    receipt fields with ``metrics: null`` — a vanished post is itself signal.
    Structured error when there are no credentials; ``{"posts": []}`` when
    nothing has ever been posted.
    """
    base = Path(universe_dir)
    bounded = max(1, min(int(limit), MAX_POSTS))
    posts = _posted_receipts(base, limit=bounded)
    if not posts:
        return {
            "posts": [],
            "note": (
                "no real posts recorded yet — engagement starts existing "
                "after the first published post"
            ),
        }
    destination = next((p["destination"] for p in posts if p["destination"]), "")
    handle = destination or "@self"
    response = _fetch_metrics(
        [p["post_id"] for p in posts], handle=handle, destination=destination
    )
    if "error" in response:
        response["posts_awaiting_metrics"] = posts
        return response

    by_id: dict[str, dict[str, Any]] = {}
    for row in response.get("data") or []:
        if isinstance(row, dict) and row.get("id"):
            by_id[str(row["id"])] = row
    for post in posts:
        found = by_id.get(post["post_id"])
        if found is None:
            post["metrics"] = None
            post["note"] = "not returned by X (deleted or inaccessible)"
            continue
        post["text"] = str(found.get("text") or "")
        post["created_at"] = str(found.get("created_at") or "")
        metrics = found.get("public_metrics")
        post["metrics"] = metrics if isinstance(metrics, dict) else {}
    return {"posts": posts}


__all__ = ["MAX_POSTS", "read_engagement"]
